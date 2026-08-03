---
title: The real remote — measured against github.com
date: 2026-07-31
status: 21/21 — 10 remote mechanics (poc/test_github_remote.py) + 11 ported topology scenarios (poc/test_github_topology.py), against https://github.com/drbothen/datum (formerly dolt-artifact-spike)-remote
verdict: push-as-CAS works over the network; it costs ~10 s per acquire, a pull ~2.3 s, and one data ref serialises every instance
---

# Dolt on a real GitHub remote

Every multi-machine and multi-instance result in this spike used a `file://`
remote. That made the 640 ms acquire a **floor**, and left latency, auth,
partial-failure recovery, and what actually appears in the repo untested — rated
the highest-severity remaining gap in both [ASSESSMENT §4.4](ASSESSMENT.md) and
[GAP-MATRIX §6](GAP-MATRIX.md). This closes it.

**Remote:** `https://github.com/drbothen/datum (formerly dolt-artifact-spike)-remote` (private).
Each run uses a unique data ref (`refs/dolt/run-<ts>/…`) and deletes it afterwards,
so runs never collide and the repo does not accumulate. Credentials come from the
git credential helper; **no token is written to disk or into a URL**.

---

## 1. It works, and Dolt detects a git remote by itself

```
dolt remote add --ref refs/dolt/<run>/data origin https://github.com/…​.git
dolt push origin main
```

`dolt remote -v` rewrites the URL to **`git+https://…`**. The documented url
schemes (`http`, `https`, `aws`, `gs`, `file`) never mention git remotes; the
`--ref` flag ("Git ref to use as the Dolt data ref for git remotes, default
`refs/dolt/data`") is the only hint in the CLI help. Auth is whatever git already
has — `gh`'s credential helper worked with no extra configuration.

What appears in the repo (G1):

| Ref | What it is |
|---|---|
| `refs/dolt/<name>` | **the entire database** — one ref, all branches |
| `refs/heads/__dolt_remote_info__` | Dolt's own bookkeeping branch. Shows up in every branch list. Cosmetic, permanent, confusing. |
| `refs/heads/main` | the ordinary git branch. Untouched by Dolt. |

Dolt **refuses a git remote with zero branches**, so the repo must be seeded with
a real commit on `main` first.

---

## 2. What it costs (median of 5 rounds, repeated across two full runs)

| Operation | file:// (earlier) | **github.com** |
|---|---|---|
| lease acquire round trip (fetch → reset → guarded UPDATE → commit → push) | 640 ms | **9.9–11.4 s** |
| acquire **+** release pair | ~1.3 s | **~20–23 s** |
| contended acquire, 3 clones | — | 15–19 s each |
| push a 2-table toy database | — | 9.7–16.5 s |
| push the **full 33 MB corpus** (1,959 BCs) | — | **10.4 s** |
| cold clone the full corpus back | — | **2.2 s** |
| push to a nonexistent repo (failure) | — | fails in **0.5 s**, loudly |

**The dominant cost is round-trip protocol overhead, not payload.** A two-table
toy and a 33 MB corpus both push in ~10 s. That has two consequences:

- **Coordination is expensive; data transfer is not.** Push-as-CAS is viable at
  *phase-gate* granularity — the factory already fetches and pushes at every gate,
  and a wave gate runs for ~45 minutes — and unusable at anything finer. A
  20-second acquire+release pair per write would be absurd; per wave gate it is
  noise.
- **Onboarding and disaster recovery are cheap.** A new machine, or a total loss,
  is one 2.2-second clone of the whole corpus. That is materially better than the
  36 MB / 3,145-file worktree checkout it replaces.

---

## 3. The findings that change the design

### 3.1 One data ref is one lineage — instance branches are NOT independent (G7)

Pushing a **new Dolt branch** created **no new git ref**. It rewrote the single
data ref. So:

- **Push contention is global across instances**, not per-instance. SC5 measured
  perfectly linear O(N) retries on `file://` ([1,2,…,8] attempts for 8 pushers);
  over the network that same O(N) now costs O(N) × ~10 s. Measured here: 3 clones
  → attempts `[2,3,1]`, converged in 36–44 s.
- A **fresh, unrelated database pushing to an existing data ref is a
  non-fast-forward** — which is why every run in this suite uses its own ref.
- The mitigation is real and one flag: `dolt remote add --ref
  refs/dolt/<instance>` gives each factory instance its own data ref, decoupling
  their pushes entirely (verified: a second ref pushed cleanly with zero
  contention). **The cost is that each ref is a separate lineage, so there is no
  cross-instance merge on the remote** — instances would have to reconcile
  locally, clone-to-clone.

This is a genuine design fork the SPEC did not contain. It is now invariant 12.

### 3.2 Invariant 4 is confirmed, not merely inferred (G6)

On a **shared clone**: agent A committed and never pushed; agent B committed and
pushed; a third machine then observed **both** rows on the remote. So "my push was
rejected" does not mean "my work was not published", against github.com and not
just `file://`. A retry that re-executes a write must treat a duplicate key as
*already applied* and fall through to push — bailing strands the earlier commit,
which the next `reset` discards.

### 3.3 Exclusion holds over the network (G4)

Three clones acquired the same lease simultaneously behind a barrier: **exactly one
won**, the remote agreed on the holder, and both losers got a clear
non-fast-forward message telling them to integrate first. S5's limitation is
unchanged and now expensive: **the loser learns only after doing its work**, and
over the network that is ~15 s of wasted round trips rather than 640 ms.

### 3.4 An embedded `datum` needs no `dolt` binary (G8)

`DOLT_FETCH` (45 ms) and `DOLT_PUSH` (7.7 s) both ran **in-process** through
`dolthub/driver/v2` against the GitHub remote. Combined with B8 (branch, checkout,
merge, reset, gc, log, diff, history, `AS OF` all in-process), a single Go binary
covers the entire surface — no pinned external binary in the toolchain. This is
the strongest argument for the embedded path; see [ACCESS-PATH.md](ACCESS-PATH.md)
for why it still is not a phase-1 concern.

`DOLT_PULL` needs an explicit branch argument when the remote is not the
configured upstream.

### 3.5 Failure is fast and legible (G9)

A push to a nonexistent repo failed in **0.5 s** with actionable credential hints —
not the silent-hang class. That hang remains real (LESSONS: `dolt push` stalling
forever at 0% CPU against a *recreated* remote), which is why every network call in
this suite is wrapped in a timeout and treats `rc=124` as a result rather than an
exception.

---

## 4. What this means for the recommendation

*(§4 covers the mechanics suite; §5 adds the ported topology scenarios, which did not
change any of the conclusions below.)*

Server-less push-as-CAS **survives** the real-network test, with its price now
known rather than assumed:

| | verdict |
|---|---|
| Correctness of exclusion | **holds** (G4), one winner, remote-agreed |
| Cost | **~10 s per acquire, ~20 s per acquire+release.** Fine per phase gate; wrong per write |
| Data volume | irrelevant — 33 MB pushes as fast as 2 rows |
| Recovery / onboarding | **2.2 s clone** of the whole corpus |
| Scaling instances | **worse than modelled** — one shared ref means global O(N) push retries at ~10 s each; use `--ref` per instance to decouple, forfeiting remote-side merge |
| Failure modes | fast and loud, but keep the timeout wrapper |

If a future phase needs sub-second, up-front exclusion for many agents per host,
that is still the argument for a shared `sql-server` — and it is now backed by a
number: the network arbiter is **~15,000× slower** than a server-local CAS (~1 ms),
not the ~1,000× that the `file://` floor suggested.

---

## 5. Part 2 — every file:// scenario, re-run on GitHub

The suite above tested remote *mechanics*. It did **not** re-run the merge-semantics
and topology scenarios that the earlier passes proved only against a `file://`
stand-in. `poc/test_github_topology.py` ports all of them (11/11):

| # | Ported from | Result over github.com |
|---|---|---|
| H1 | M3, D2 | **Cell-level merge holds.** A set `capability`, B set `notes` on the *same row*; B merged with zero conflicts and both values survived. The property markdown cannot have, now proven off `file://`. |
| H2 | M4, D3, D4 | **Different values on one cell → conflict** (`dolt_conflicts=1`, "Automatic merge failed"); **identical values → coalesce silently**, no conflict. Nothing is lost without being reported. |
| H3 | D8 | **The wedge reproduces, and is now localised** — see §5.1. |
| H4 | D1 | **The target topology works over the network:** 2 machines × 4 agent processes, 8/8 agents succeeded, **zero** `cannot update manifest`, both clones converged, 62 s wall clock. Most agents needed 2 push attempts. |
| H5 | D6 | A lease contended by **8 agents across 2 fleets** → one holder, both machines agree. Four agents "acquired" locally (each machine's mutex only orders its own); the remote collapsed them to one. |
| H6 | D5, D5b | **The retry shape is the whole bug** — see §5.2. |
| H7 | D7, inv 5 | Stale until pulled, as expected. **A pull costs ~2.3 s median** over the network vs ~150 ms on `file://`. |
| H8 | I4, I5, I8 | Instance branches, graduate and abandon all work through a git remote — with the asymmetry invariant 12 predicts. See §5.3. |
| H9 | I6 | Two instances refining the **same record** → conflict at graduation, `dolt_conflicts=1`, main keeps the first graduate's value and the loser still holds its branch. Exactly the case [D1](DECISIONS.md) governs. |
| H10 | E5, E6 | **Dolt merges SCHEMA across a real remote:** two machines adding *different* columns merged cleanly and both columns survived; the *same* column with different types (INT vs VARCHAR) surfaced a conflict rather than silently picking one. |
| H11 | SC5 | Push contention at 8 clones — see §5.4. |

### 5.1 D8's misleading error is on the PULL path, not the commit path

The wedge itself reproduces exactly: after one agent leaves an unresolved conflict,
another agent on that clone can neither commit nor pull. But the two failures do
*not* read the same:

- **commit** → `tables [rec] have unresolved conflicts from the merge. resolve the
  conflicts before committing` — accurate and actionable.
- **pull** → `cannot merge with uncommitted changes` — **this is D8's misleading
  message**, and it blames staging rather than the conflict.

So D8 stands, sharpened: the diagnosability problem is specific to the *pull* path
on dolt 2.2.3. `datum doctor` should therefore check for a half-merge explicitly rather
than relying on the error text an agent happens to hit first.

### 5.2 The counter bug is one line of retry logic, and it reports success

Three retry shapes on the same increment, variable isolated:

| Retry shape | Agents reporting success | Counter landed at |
|---|---|---|
| merge-and-repush **without** recomputing | **2 of 2** | **1** — silent loss |
| recompute the read-modify-write each attempt | 2 of 2 | 2 — exact |
| append-only rows with unique keys | 6 of 6 | 6 — exact |

The unsafe shape tells **both** agents they succeeded while losing an increment, with
no error anywhere — the precise class this whole project exists to eliminate. The
third shape cannot express the bug, which is why invariant 3 says counters are rows.

### 5.3 Instance branches over one data ref

Pushing an instance branch made it visible to another clone after `dolt fetch`
(as `remotes/origin/<branch>`), graduation by merge-to-main propagated the spike's row
to the other machine, and both local and remote branch deletion returned cleanly. The
asymmetry invariant 12 predicts is real: branch state travels **inside** the single
data ref, so there is no per-branch git ref, and "delete the remote branch" is not a
git ref operation.

### 5.4 Push contention: O(N) confirmed in magnitude, as a permutation

`file://` gave exactly `[1,2,3,4,5,6,7,8]` for 8 pushers — the tidy staircase. Over
the network, two runs of the same test:

| Run | Attempts per clone | Total | Converged in |
|---|---|---|---|
| 1 | `[5,4,2,6,7,2,1,4]` | 31 | 136 s |
| 2 | `[1,4,3,2,5,6,8,7]` | **36** — exactly the linear sum | 165 s |

**SC5's O(N) claim survives in magnitude** (36 = 1+2+…+8): the Nth contender still
needs about N attempts, and run 2 produced a straight *permutation* of 1..8. What the
network removes is the ordering — jitter decides who wins each round, not arrival
order. The number that matters for planning is the wall clock: **~2.3–2.8 minutes for
8 instances to converge**, growing with N. That is the real ceiling on how many
factory instances can comfortably share one remote data ref, and it is the strongest
practical argument for `--ref`-per-instance (invariant 12).

---

## 6. Reproducing

```bash
.venv/bin/python -u poc/test_github_remote.py       # 10/10, ~9 min  (mechanics)
.venv/bin/python -u poc/test_github_topology.py     # 11/11, ~12 min (ported scenarios)
# env: DATUM_GH_REMOTE (default drbothen/datum (formerly dolt-artifact-spike)-remote)
#      DATUM_GH_CLONES=3  DATUM_GH_ROUNDS=5  DATUM_GH_TIMEOUT=300  DATUM_GH_KEEP=1
#      DATUM_GT_CLONES=8 (H11)  DATUM_GT_ONLY=h3,h6 (partial re-run while iterating)
```

Both suites create per-run `refs/dolt/<run>/*` refs and delete them in a `finally`
block. G10 needs the imported corpus at `poc/eb/a/fa_cli`, i.e. run
`poc/test_embedded.py` first.
