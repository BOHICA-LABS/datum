---
title: Scale + contention — 200 agents, and every decentralised option measured
date: 2026-07-31
status: stress 5/6 (poc/test_stress_fleet.py) · optimisation 3/3 (poc/test_stress_opt.py) · decentralised options 5/5 (poc/test_decentral.py) · CI aggregator 4/4 (poc/test_ci_aggregator.py)
verdict: the fleet is correct at scale (zero lost writes); contention is solved decentrally by AGGREGATION, and no central server is required for it
---

# Scale and contention

Every earlier concurrency result was small: 8 agents (D1), 32 through one mutex
(SC3), 3 clones contending (G4), 8 clones pushing (H11). This pass runs the real
shape — **10 machines x 20 agent processes = 200 agents, 20 clones, one artifact
branch, real GitHub remote** — and then works the contention problem until the
decentralised options are exhausted.

---

## 1. Does it stay correct at 200 agents? Yes.

`poc/test_stress_fleet.py`, 5/6. Topology: 10 machines, each with a primary clone
(branch `main`) and a spike clone (branch `spike_m<i>`), 10 agent processes per
clone behind that clone's `flock` mutex.

| # | Phase | Result |
|---|---|---|
| S1 | 200 agents write locally, no network | **200/200**, 0 `cannot update manifest`, 0 lost writes, **18 s**. Mutex wait max/median **2.1x** — no starvation at 10 waiters per clone |
| S2 | one push per clone, 20 clones at once | 20/20 landed, 323 s — and the per-branch discovery, §2 |
| S3 | per-write pushing (declared 3/10 sample) | 60/60 landed but **1 manifest error**, 153 attempts, per-unit median **22 min**. FAILED, correctly |
| S4 | 10 spikes graduate into one `main` concurrently | **9/10 clean**, 288 s; the 10th conflicted deliberately and blocked nobody |
| S5 | 10 instances on 10 separate data refs | 10 attempts, 10 s |
| S6 | **verify from a fresh clone** | **247 expected / 247 present. 0 missing, 0 unexpected, 0 duplicates, 0 dangling FKs** |

**S6 is the load-bearing result.** After 200 concurrent writers and 9 concurrent
merges, every single write is present exactly once and the foreign keys still hold.
The expectation is *derived* — from each clone's own contents plus which pushes and
graduations actually landed — so a deliberately truncated phase cannot masquerade
as data loss, and data loss cannot hide behind one.

S3 earned its failure: at the full 200 agents the per-write shape degraded to ~1
unit per minute and projected ~3.3 h, so it runs a declared 3-of-10 sample and says
what it did not run. It also surfaced 8 transient `git` credential-helper failures
under load, and one `cannot update manifest` that the mutex did not prevent.

---

## 2. Where the contention actually is

Measured in S2 — 10 primary clones all pushing `main`, 10 spike clones each pushing
their own branch, **all sharing one git data ref**:

```
primary (all -> main)        [9,7,10,5,5,3,4,1,8,2]  total 54   <- O(N)=55 for N=10
spikes  (each -> own branch) [1,1,1,1,1,1,1,1,1,1]   total 10   <- no contention
```

**Contention is per-BRANCH, not per-ref.** A push is a compare-and-swap on a branch
pointer; if it moved since your last fetch you are rejected whether or not your data
overlaps anyone's. Every primary agent in the whole run wrote **disjoint** rows and
not one semantic conflict occurred — the only content conflict in 200 agents was the
one engineered on purpose in S4.

### This corrects invariant 12, twice over

The original wording said push contention is *global across instances* because all
branches share one git ref. The mechanism was wrong — but for the factory the
conclusion is right anyway, because **the artifact store is a single branch**, so
per-branch contention *is* global for artifacts. Two consequences:

- The `--ref`-per-instance mitigation the SPEC proposed is **inapplicable**, not
  merely unnecessary: it fragments the artifact store into separate lineages, which
  is what one-branch rules out. S5 measures what it would buy (10 attempts, 10 s)
  and it is recorded only as a reference point.
- What remains is not a coordination problem but an **aggregation** problem.

### The trade against markdown, stated plainly

| | today (markdown) | under Dolt |
|---|---|---|
| two agents edit different fields of one BC | **textual conflict**, needs a human | clean cell merge (M3/D2/H1) |
| two agents write unrelated artifacts | fine | **push-pointer contention** |

Judgment-requiring collisions go down sharply; mechanical contention goes up. The
first needs a person, the second needs a queue or an aggregator.

---

## 3. The cost model

Three constants, each measured independently:

| Cost | Value | Evidence |
|---|---|---|
| a push attempt | **~8 s, fixed** | O3: 1 commit 7.6 s, 50 commits 7.9 s — payload-independent |
| ...not transport | ssh **8.6 s** vs https 7.7 s | D4 — ssh is *slower*; the constant is not the wire |
| ...not process spawn | embedded `DOLT_PUSH` 7.7 s | B8/G8 — same number in-process |
| a local unit of work | 0.21 s | O2, with one `dolt` invocation instead of three |
| a pull | ~2.3 s | H7 |

So: `naive retry = O(N^2/2) x 8 s`, `queued = O(N) x 8 s`, `aggregated = O(1) x 8 s`.
The only way to spend less is to **push fewer times**.

---

## 4. Every decentralised option, measured (N=20, one branch, no central server)

`poc/test_decentral.py` 5/5 plus `poc/test_stress_opt.py` O1.

| Approach | Writer pushes | Pushes to the artifact branch | Wall | Daemon | Cross-host |
|---|---|---|---|---|---|
| **D2 host relay** — instances push a local `file://` relay serialised by `flock`, then ONE network push per host | 0 (local) | **1** | **17 s** | none | no — per host |
| **D5 peer pull** — each writer serves itself (`--remotesapi-port`); the aggregator pulls straight from peers | **0** | **1** | **25 s** | **N listeners** | yes, if reachable |
| **D3 staging refs** — each writer publishes to its own ephemeral ref in parallel; one aggregator merges all N and pushes once | N (parallel, contention-free) | **1** | 64 s | none | yes |
| O1-B lock ref — create-only ref on a *different* ref gives up-front exclusion | N (queued) | N | 135 s *(N=10)* | none | yes |
| O1-A / D1-A free-for-all | N + waste | 159 attempts, **139 wasted** | 746 s | none | yes |
| D1-B exponential + jitter | worse | 185 attempts | **1007 s** | none | yes |
| D1-C deterministic ticket order | worse | 193 attempts | 894 s | none | yes |
| D4 transport (ssh) | — | — | no help | — | — |

### 4.1 Backoff makes it WORSE — measured, and against prediction

Immediate retry 159 attempts / 746 s; exponential+jitter 185 / 1007 s; ticket order
193 / 894 s. All three landed 60/60, so this is purely about cost.

The reason is structural: the branch pointer advances exactly N times regardless,
and you are rejected whenever it moved since your last fetch. Sleeping longer means
*more* pointers move while you wait, so you return staler and get rejected again.
**Backoff widens your exposure window instead of narrowing it.** It spreads the
losses out; it cannot remove them.

> Predicted before the run: a ticket order would approximate the lock's ~19
> attempts. It took 193. Recorded because it is the third prediction this pass
> overturned, and the pattern is consistent — reasoning from structure instead of
> measuring was wrong every time.

**Optimistic retry cannot be tuned out of this problem. Only removing the collision
helps** — up-front exclusion (O1-B) or aggregation (D2/D3/D5).

### 4.2 Two supporting wins, cheap and unconditional

- **O2 — 2.9x on the local path** by collapsing three `dolt` invocations per unit
  (`sql`, `add -A`, `commit`) into one (`dolt sql` doing the write *and*
  `CALL DOLT_COMMIT`). The median mutex hold falls 0.53 s -> **0.21 s**, which is
  what lets a clone absorb more agents.
- **O3 — 48x per commit** from batching, since a push costs the same for 1 commit
  as for 50. Same conclusion invariant 6 reaches for transactions, one layer up.

### 4.3 Refinements the numbers exposed

- Both O1-B and D2 still needed ~2 attempts per pusher because they push without
  pulling immediately after acquiring exclusion. A `pull` right after acquire takes
  both to exactly 1 attempt each.
- O1-B spent ~500 cheap lock probes (median wait 59 s) to save 31 expensive pushes.
  It works, but aggregation beats it by 4-8x.
- D3's 64 s is dominated by the aggregator's **20 sequential fetches** (49 s).
  Fetching in parallel is an obvious further win, untested.

---

## 5. Recommendation — no central server needed for this

Compose the two daemon-free options into the hierarchy beads calls a *tree of hubs*:

```
   agents (10 per clone)  --flock-->  clone
   clones on one host     --file:// relay + flock-->  1 push per HOST      (D2, 17 s)
   hosts                  --staging refs + aggregator-->  1 push TOTAL     (D3, 64 s)
```

For the 10x2 fleet that is **20 writers -> 10 -> 1**, about **80 s** against 746 s
naive, and it is O(1) in fleet size rather than O(N^2).

**Across the internet only D3 survives** — D2 needs a shared filesystem, D5 needs
inbound reachability to every writer. The aggregator role is then filled by **CI**,
measured working 4/4 in [CI-AGGREGATOR.md](CI-AGGREGATOR.md), where GitHub's
`concurrency:` group supplies the merge slot for free and retires the lock-ref
mechanism entirely.

**Why a central server is not the answer to contention.** Its advantage was ~1 ms
up-front exclusion instead of a ~10 s network CAS. Under aggregation only *one*
writer ever touches the artifact branch, so there is almost nothing left to exclude.
A server would still buy faster reads and intra-host concurrency — those are
separate arguments, on their own merits, and D5 shows the shape they take
(a listener per site, which is what beads adopts *within* a site).

### Honest costs of the recommendation

1. **The aggregator is a role someone must hold**, and its merge is where conflicts
   surface — governed by [DECISIONS D1](DECISIONS.md).
2. **Feedback arrives later.** On a shared branch you learn you conflict at push
   time; with aggregation you learn at integration. Integrate every gate, not every
   wave.
3. **D2 only collapses one host.** Across hosts, N = hosts.
4. **A remote-ref lock has no kernel release.** Unlike `flock` (X4, where the kernel
   frees it on `SIGKILL`) it needs a TTL and a break-glass path.
5. **Each contender must present a UNIQUE sha** to a create-only ref push, or
   same-value pushes both "succeed" — invariant 1 reappearing at the git layer.
6. **D5 trades one central daemon for N.** Decentralised, but not daemon-free, and
   it needs peer reachability (fine on a LAN, awkward across NAT — and the
   factory's devs are on separate machines).

---

## 6. Prior art

- **beads has a `bd merge-slot`**: an exclusive primitive with `status`/`holder`/
  `metadata.waiters`, explicitly to stop *"monkey knife fights where multiple
  polecats race to resolve conflicts and create cascading conflicts."* That is the
  aggregator lock, in a production Dolt product for AI agents.
- **Its federation topologies list "Hierarchical — tree of hubs"**, and describe
  federation as *"peer-to-peer: no central server required; each town is
  autonomous."* Exactly the §5 composition.
- **beads warns that `leases` are clone-local and never replicate** — coordination
  across a decentralised boundary is stale by construction, so TTL must exceed the
  sync interval. Applies directly to any lock we build.
- beads reaches for **server mode for concurrent writers *within* a site** and
  decentralised federation *between* sites. "N sites pushing one branch" is the
  unusual shape; aggregation is what normalises it.
- The industry answer to many-writers-one-branch is a **merge queue** (GitHub merge
  queue, GitLab merge trains, Zuul gating). The aggregator is standard practice.

---

## 7. Reproducing

```bash
.venv/bin/python -u poc/test_stress_fleet.py    # 200 agents, ~45 min, 5/6
.venv/bin/python -u poc/test_stress_opt.py      # O1-O3 A/B, ~15 min
.venv/bin/python -u poc/test_decentral.py       # D1-D5, ~45 min, 5/5
# env: FA_ST_MACHINES/FA_ST_AGENTS/FA_ST_S3_AGENTS · FA_OPT_ONLY=o1 · FA_DC_ONLY=d5
# all three create per-run refs/dolt/<run>/* and delete them in a finally block
```
