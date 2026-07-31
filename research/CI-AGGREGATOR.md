---
title: CI as the aggregator — the cross-internet answer, measured
date: 2026-07-31
status: 4/4 standard + 5/5 stressed at 20 writers + a 3-sample latency run (poc/test_ci_aggregator.py) against GitHub Actions
verdict: works end to end at 20 writers, ~30 s median latency; `concurrency:` supplies the merge slot for free. ONE required fix found: stuck refs must be quarantined, not retried forever
---

# CI as the aggregator

[SCALE.md](SCALE.md) exhausted the decentralised ways to collapse N writers to one
push, but every measurement ran on ONE host. Only one of the winners survives writers
being on different networks:

| Option | Across the internet? | Why |
|---|---|---|
| **D3 staging refs** | **yes, unchanged** | outbound HTTPS only, from everyone |
| O1-B lock ref | yes, degraded | outbound only, but polling cost grows with RTT |
| D2 host relay | **no** between machines | needs a shared filesystem + kernel for `flock` |
| D5 peer pull | **effectively no** | needs *inbound* TCP to every writer; laptops sit behind NAT |

So the 17 s and 25 s headline figures are LAN/single-host numbers. D2 remains the
*intra-machine* tier; D3 is the only cross-internet tier. That leaves one question:
**who aggregates?** This is the measured answer.

---

## 1. The loop

```
writers (each already collapsed locally by D2)
  └─ dolt push --ref refs/dolt/stage/<id>     outbound HTTPS, a ref it alone owns
  └─ fire repository_dispatch

CI, singleton by construction:
  1. clone the artifact ref
  2. enumerate refs/dolt/stage/*
  3. merge each, in deterministic order
  4. fa validate                              ← ADMISSION CONTROL
  5. ONE push to the artifact branch
  6. delete the consumed refs (API), then re-dispatch only on progress
```

Verified against GitHub Actions, 4/4 (`poc/test_ci_aggregator.py`):

| # | Result |
|---|---|
| C1a | 4 writers published to their own staging refs in parallel, 13 s, **zero contention** |
| C1b | `GITHUB_TOKEN` **can** create, update and delete `refs/dolt/*`; `repository_dispatch` reaches the workflow; 3 writers + base landed = 5 rows; **exactly one process advanced the artifact branch** |
| C2 | the conflicting writer was **isolated**: its staging ref RETAINED, every other ref drained, `main` kept the first writer's value |
| C3 | **strand defence holds** — and against the real mechanism: the run list shows a `cancelled` conclusion, i.e. GitHub genuinely cancelled a pending run, and the late writer's work still landed |

Verified content on the artifact branch after aggregation:

```
base,seed        w0,w0        w1,w1        w2,w2        shared,from-w0
                                          (w3 ABSENT — correctly conflicted)
```

---

## 2. `concurrency:` is the merge slot, for free

```yaml
concurrency:
  group: fa-aggregate
  cancel-in-progress: false
```

GitHub guarantees *"only a single job or workflow using the same concurrency group
will run at a time."* Two lines replace the entire O1-B lock-ref mechanism **and every
one of its honest costs**: no TTL, no break-glass path, no stale-lock recovery, and no
"each contender must present a unique sha" discipline. Exactly one process ever pushes
the artifact branch, so contention is zero by construction rather than by convention.

**The trap, verified:** by default *"at most one job or workflow run can be pending in
the concurrency group. When a new job or workflow run is queued, any existing pending
run in the same group is canceled and replaced."* With N writers firing dispatches,
most are dropped. Usually harmless — each run consumes *all* published staging refs —
but a writer that publishes *after* the running job started, whose dispatch was then
cancelled, has no run left to pick it up. Three layers stop that:

1. **Self-redispatch** — at the end of each run, re-enumerate; if refs remain, dispatch
   again. Liveness stops depending on queue semantics. (This is what C3 exercises.)
2. **`queue: max`** — up to 100 pending, FIFO. Can't combine with `cancel-in-progress`.
3. **A cron sweep** underneath both. It is also the only thing that retries a
   *conflicted* ref after its writer resolves it, so production should enable it.
   (Commented out in the test repo purely so an idle repo doesn't run forever.)

---

## 3. Three outcomes per staging ref, not two

The aggregator must distinguish them, because they have different owners:

| Outcome | Action | Whose problem |
|---|---|---|
| **merged** | consume, then delete the ref | nobody's |
| **conflicted** (`dolt_conflicts > 0`) | `merge --abort`, **retain** the ref, keep draining others | the writer's — it re-applies its intent on the new base ([D1](DECISIONS.md)) |
| **unrelated lineage** (`no common ancestor`) | retain, emit a warning, keep draining | the writer's — it published from a non-clone |
| anything else | **fail the run loudly** | the AGGREGATOR is broken; calling it a conflict would hide that |

That last row is the discipline: an error must never be reported as a conflict.

---

## 4. Findings that cost a run each

1. **Writers must be CLONES of the artifact branch.** Independently `dolt init`-ed
   databases have unrelated roots and fail with **`no common ancestor`** — they cannot
   be merged at all, only replayed. This is also the hard proof that
   `--ref`-per-instance fragmentation is a **one-way door**, not a tradeoff:
   [SCALE.md §2](SCALE.md) said it costs "no cross-instance merge on the remote"; in
   fact the data can never be reunited by merging.
2. **`on: push` does not fire for `refs/dolt/*`.** The `push` event is scoped to
   `refs/heads/*` and `refs/tags/*`; there is no `refs:` key. Publishing a staging ref
   is invisible to CI, so `repository_dispatch` / `workflow_dispatch` / `schedule` are
   the only triggers.
3. **`git push <url> :ref` needs a git repository.** The job has no `actions/checkout`
   and its cwd is a *Dolt* repo (`.dolt/`), so every deletion failed **in 0.7 ms with
   no network at all**. Use the refs API (`gh api -X DELETE repos/O/R/git/<ref>`).
4. **Swallowing that rc caused a livelock.** `git push … | tail -1` hid the failure, so
   refs were never deleted, so `refs remain` stayed true, so the run re-dispatched
   itself — five successful runs in a row, forever. The fix is two-part: assert the
   deletion result, **and** re-dispatch only on measurable *progress*.
5. **GitHub runs `bash -e`.** `VAR=$(cmd)` aborts the step, so my own error handling
   never ran and the step died with no output. Set the shell explicitly
   (`shell: bash -uxo pipefail {0}`) when the script manages its own control flow.
6. **A YAML block-scalar continuation must stay indented.** Dropping to column 1 made
   the workflow invalid — and the tell is subtle: `gh api …/workflows` reports the
   workflow's `name` as its *file path*, and dispatches are accepted (rc=0) while no
   run is created. Lint locally before pushing.

---

## 4a. Stressed at 20 writers x 10 agents (200 agents' work)

Same scale as the fleet test, with each writer carrying ten agents' rows — i.e. the
output of a D2 host relay — so the whole recommended topology runs end to end:

| Measurement | Result |
|---|---|
| publish, 20 writers in parallel | **14 s** (vs 13 s at N=4) — **flat in N**, as predicted: distinct refs cannot contend |
| refs drained 20 -> 1 | within ~66 s of dispatch |
| rows on the artifact branch | 192; **190/190** non-conflicting writer rows present |
| the conflicting writer's 10 rows | correctly **absent**, its ref retained |

### ⚠ The one real flaw: stuck refs are re-worked on EVERY run

A conflicted ref is retained by design — but the aggregator re-fetches and re-merges
it every single run. Measured by running the aggregation twice more with **nothing new
to do**: **17 s, then 8 s of pure waste**. At 20 stuck refs that dominates the job, and
the backlog only grows, because a stuck ref stays until its writer resolves it.

**Required `fa aggregate` feature: quarantine, not just retention.** Record an attempt
count per staging ref and back off (or move it to `refs/dolt/quarantine/*`) so a stuck
writer cannot tax the whole fleet indefinitely. Retention is right; unbounded
re-attempt is not.

---

## 4b. End-to-end latency — the number a user feels

From an agent finishing its local write to that write being visible **on another
machine**, measured with an independent observer clone polling the artifact ref
(3 samples):

```
totals            27 s · 44 s · 30 s        median 30 s, max 44 s
  1. publish staging ref      9-11 s        the writer's push
  2. dispatch accepted        1-2  s
  3. runner queue             0    s        all three samples
  4. CI aggregate step        7-13 s
  5. observer pull + poll    ~3    s        measurement resolution
```

**The ~22 s floor is irreducible:** the ~8 s fixed push cost ([SCALE.md §3](SCALE.md))
is paid **twice** — writer to its own ref, then aggregator to the artifact branch —
plus a consumer pull (~2.3 s).

Two things this corrected:

- I estimated "~1-2 min dominated by runner startup". It is **~30 s** and startup was
  negligible in every sample.
- I claimed the Go binary would remove 20-30 s of `dolt` install. It is **2 s**. The
  real argument for `fa` is toolchain simplicity and one code path, **not** latency.

**Caveat that matters:** the runner queue was 0 s in all three samples, i.e. GitHub
scheduled instantly on this repo. That is the volatile term — a busier org or a
different plan can add minutes, and nothing in this design can absorb that. Anything
needing sub-30-second visibility must not go through CI.

---

## 5. Honest costs

- **Latency: ~30 s median, 44 s worst of 3** (§4b), with the runner queue as the
  volatile term. Fine at 45-minute gate cadence; **per-write visibility is gone.**
- **CI is on the critical path.** Mitigated by the end state: the aggregator is
  **`fa aggregate`**, a subcommand of the Go binary, so during an Actions outage any
  dev runs the identical code path. Nothing is lost meanwhile — work sits in staging
  refs. This is why the aggregator must NOT be logic living in YAML.
- **It centralises *coordination*** even though storage stays decentralised. What it
  avoids is a daemon anyone operates, a port, and a stateful SPOF; the trust anchor is
  the git remote the project already has.
- **The prototype is throwaway.** `poc/workflows/fa-aggregate.yml` shells out to the
  `dolt` CLI to learn the mechanics quickly. Once `fa` embeds Dolt the whole job is
  "download `fa`, run `fa aggregate`" — no dolt install, and the same binary devs run.

---

## 6. Reproducing

```bash
gh workflow enable fa-aggregate -R drbothen/dolt-artifact-spike-remote   # cron is off
.venv/bin/python -u poc/test_ci_aggregator.py        # 4/4, ~6 min
# env: FA_CI_REPO  FA_CI_WRITERS=4  FA_CI_POLL=900  FA_CI_KEEP=1
```

The workflow lives at `poc/workflows/fa-aggregate.yml` here and is deployed to
`.github/workflows/` in the test remote. The suite sweeps its own refs at start and
in a `finally` block.
