# dolt-artifact-spike

Research spike: can [Dolt](https://github.com/dolthub/dolt) back a tool that is the **only**
interface to all vsdd-factory artifacts, replacing the `factory-artifacts` orphan git branch?

**Verdict: GO, phased.** See [research/ASSESSMENT.md](research/ASSESSMENT.md).

## What's here

| Path | What |
|---|---|
| **`research/SPEC.md`** | **The specification — capability surface, 11 invariants, CLI, phasing, non-goals** |
| **`research/GAP-MATRIX.md`** | **Gap assessment vs all 46 registry artifact types + the 3 findings that changed the design** |
| `research/ASSESSMENT.md` | The feasibility assessment — findings, gaps, phased recommendation |
| `poc/schema.sql` | Core schema (BCs, VPs, stories, subsystems, lock) |
| `poc/graph.sql` | Full relationship graph — 10 node types, 9 edge tables |
| `poc/fa.py` | `fa` — the sole-interface CLI (init/import/count/get/history/validate/lock/render) |
| `poc/graph_import.py` | Loads the graph from live frontmatter; reports every dangling ref |
| `poc/test_spike.py` | 13 tests — store-level failure modes |
| `poc/test_graph.py` | 8 tests — traversal + referential integrity |
| `poc/test_multimachine.py` | 6 tests — two clones, one remote (self-provisioning) |
| `poc/test_locking.py` | 6 tests — is the factory lock still needed? |
| `poc/test_cas_patterns.py` | 5-pattern concurrency comparison (which CAS actually holds) |
| `poc/test_serverless_lock.py` | 5 tests — cross-machine exclusion with **no server** |
| `poc/clonelock.py` | `flock` write mutex for a single shared clone |
| `poc/test_mutex.py` | 8 tests — single clone + mutex (cross-process) |
| `poc/test_two_devs.py` | 9 tests — **2 devs, 2 machines, 4 agents each, 1 repo** |
| `poc/test_write_api.py` | 9 tests — the mutation surface (create/amend/retire/atomic/gates) |
| `poc/test_render.py` | 7 tests — markdown as a deterministic, round-trippable export |
| `poc/test_schema_evolution.py` | 8 tests — migrations + cross-machine schema merge |
| `poc/test_lifecycle.py` | 8 tests — onboarding, recovery, wave branches, growth |
| `poc/test_asymmetry.py` | 6 tests — **information-asymmetry walls vs one store** |
| `poc/test_factory_ops.py` | 10 tests — waves, state, context, tasks, templates, versioning |
| `poc/test_multi_instance.py` | 9 tests — **N devs x M instances x K agents** |
| `poc/db/`, `mm/`, `sl/`, `mx/`, `td/`, `se/`, `lc/`, `asym/`, `fo/`, `mi/` | Dolt data dirs (gitignored) |

**112/112 passing** against the live corpus, fourteen suites.

**Read [`research/SPEC.md`](research/SPEC.md) first** — it is the deliverable: the full
capability surface with every capability traced to the test that proves it, the eight
invariants `fa` must enforce (each one a silent-data-loss risk if violated), the CLI
surface, phasing, non-goals, and the honest list of what is still unproven.

## Two devs, two machines, multiple agents each — it works

The realistic deployment: one git repo, two devs on separate machines, each with **one
clone shared by several agent processes**, no server anywhere. Three layers compose —
`flock` orders each machine's agents, push-rejection arbitrates between machines, and
Dolt's cell merge reconciles divergence. 9/9 (`poc/test_two_devs.py`).

- **8 agents across 2 machines, disjoint records → all 8 succeeded, 0 manifest errors,
  both clones identical.**
- **Dev A sets `capability` while dev B sets `notes` on the same artifact → both
  survive, no conflict.** A markdown store gets a frontmatter conflict here.
- A lease contended by both fleets resolves to one holder both machines agree on.

**Four rules it imposes** (each one measured, and each belongs in `fa`, not in agent prose):

1. **Every agent must abort/resolve on conflict.** An unguarded conflicting pull leaves
   the clone half-merged, and then *every* commit by *any* agent on that machine fails —
   with `cannot merge with uncommitted changes`, which blames staging, not the conflict.
   One careless agent downs its dev's whole fleet with a misleading error.
2. **Never use a mutable cell as a cross-machine counter/allocator.** Identical same-cell
   writes coalesce on the pull path, so two machines computing the same next value merge
   into one. `n = n + 1` was lossy 3/3 without a re-executing retry. Use **append-only
   rows with unique keys** (8/8 exact) — which is also what makes count drift impossible.
3. **A rejected push doesn't mean your work wasn't published.** On a shared clone a push
   carries siblings' committed work too, so retries must be idempotent — a duplicate-key
   error on retry means "already applied", and must fall through to push rather than bail.
4. **No cross-machine read consistency without a pull** (~150 ms). Pull at the start of
   every unit of work.

## Recommended topology: ONE clone + a local `flock` mutex

No daemon, no single point of failure, and **no unique-token discipline** — because
serialized writers cannot merge, ordinary `UPDATE x SET n = n + 1` becomes safe again
(8/8, `poc/test_mutex.py` + `poc/clonelock.py`, agents as separate processes).

| Without the mutex | With it |
|---|---|
| 8 writers → 3 ok, **5 fail** `cannot update manifest`; **5 increments lost** | 8/8 ok, counter exactly 8 |

Why it beats the alternatives:

- **Removes the token tax.** `n = n + 1` totals exactly N. The same shape
  (`fence = fence + 1`) fails 30/30 on a shared server — see the trap below.
- **Crash-safe for free.** `SIGKILL` the holder and the kernel releases the lock; a
  `holder`/`expires_at` row lease would stay held for its full 45-minute TTL and needs
  stale-lock detection plus a break-glass path.
- **Loud, not silent.** Every un-mutexed loss is a non-zero exit, so a partial rollout
  degrades into visible errors rather than corruption.

**One operational rule:** cost is per *invocation* (~140–270 ms), not per write. A
1,959-BC import is **531 s** one-statement-at-a-time versus **13.4 s** batching 300
statements per lock hold — so `fa` must take the mutex once per unit of work and do all
that unit's writes in one Dolt session.

Limits: one host / one filesystem (several clones need push-as-CAS below), and adding a
local `sql-server` for speed is ~2.4× faster per write but **reinstates the merge
hazard**, so batching is the better trade.

## Do you need to run a central server? No.

Exclusion needs a synchronous *arbiter*, but it can be the **remote** rather than a
server: `dolt push` is rejected on non-fast-forward, so push **is** an atomic CAS.
Verified with three clones and no `sql-server` anywhere — 3 simultaneous pushes,
exactly one wins, clean across 6 contended rounds.

The trade:

| | Shared `sql-server` | Server-less (push-as-CAS) |
|---|---|---|
| Exclusion | ~1 ms, refused **up front** | ~0.6–3 s, refused **after** local work |
| Writers per host | many | one per clone (`cannot update manifest` otherwise) |
| Moving parts | daemon, port, health, **SPOF** | none beyond git |
| Fit with today's factory | new operational surface | matches fetch/push-per-phase-gate |

Server-less is recommended for Phases 1–2: it keeps the current design's real
advantage (zero moving parts beyond git) while still fixing count drift, dangling
references, and the lock's TOCTOU.

## The concurrency trap (read before writing any code against Dolt)

Dolt has **no row locking** and merges concurrent commits **cell by cell**. So
`UPDATE … WHERE guard` + `affected_rows == 1` is **not** a safe compare-and-swap:
if contenders write the *same* value, Dolt treats it as "same change", merges, and
**every one of them gets `affected_rows = 1`**.

Measured, 30 trials × 6 writers (`poc/test_cas_patterns.py`):

| Pattern | Verdict |
|---|---|
| Contenders write identical values | **UNSAFE** — 6 of 6 win, every trial |
| `fence = fence + 1` as the token | **UNSAFE** — 6 of 6 win, every trial |
| Per-attempt **unique** value | SAFE — exactly 1, 30/30 |
| `row_lock` token + fresh random (DoltHub/beads) | SAFE — exactly 1, 30/30 |
| `GET_LOCK()` on a pinned connection | SAFE — exactly 1, 30/30 |

A `PRIMARY KEY` does not save you either: two concurrent writers inserting
**byte-identical** rows merge silently. Naive ID allocation produced `[1,1,1,1,1,1]`.

beads calls this the "zombie-merge bug"; Dolt issue
[#7681](https://github.com/dolthub/dolt/issues/7681) calls the conflict detection
"too lenient" and the strict mode is unimplemented.

## Headline findings

- The live `factory-artifacts` corpus asserts **four different values** for one fact
  (BC total: 1949 / 1955 / 1959 / 1962). The frontmatter and body of `BC-INDEX.md` disagree
  with each other by 6. `SELECT COUNT(*)` returns 1959 and cannot self-disagree.
- **3 dangling references** and **1 identity violation** exist right now. A `FOREIGN KEY`
  and a `PRIMARY KEY` make both classes unrepresentable.
- The factory lock is a YAML block inside `STATE.md` guarded by `push --force-with-lease`,
  with a **TOCTOU race the skill documents itself** (CWE-367). It is replaceable — but see
  the concurrency trap above: the *obvious* CAS replacement is unsafe, and the
  single-clone mutex is the cleanest fix.
- Dolt data rides in the project's **existing git remote** under `refs/dolt/data` — the
  orphan branch is replaceable with no new hosting.
- Modelling the **full spec graph** (story → BC → VP → NFR/DI, epics, subsystems, the
  story dependency DAG; 1,490 edges) surfaced **38 dangling references** and **44 type
  violations** no gate catches — including 19 stories `S-8.09` claims to block that were
  never written, and unfilled placeholders like `BC-4.NN.001` sitting in traceability fields.
- It also answered a question nothing in the corpus states: **90.2% of behavioral contracts
  have no verifying VP**; subsystem SS-10 has 58 BCs and zero.
- **Cell-level merge works across machines** — A edits `title`, B edits `capability`, same
  row, zero conflicts. A markdown store cannot do that.
- Ad-hoc per-clone locking is provably broken: two machines each acquired the same lock and
  each believed it won. You need *an* arbiter — but that can be a local mutex (one clone) or
  the remote (many clones), **not necessarily a daemon**.

## Quick start

```bash
brew install dolt                                                  # 2.2.3 verified

# The POC's own suites use a server on 3308 purely for convenience.
(cd poc/db && dolt sql-server --host 127.0.0.1 --port 3308 &)       # no --user in 2.2.x
.venv/bin/python poc/fa.py init
.venv/bin/python poc/fa.py import ~/Dev/vsdd-factory/.factory
.venv/bin/python poc/graph_import.py ~/Dev/vsdd-factory/.factory   # graph + findings

.venv/bin/python -u poc/test_spike.py            # 13/13  store
.venv/bin/python -u poc/test_graph.py            #  8/8   relationship graph
.venv/bin/python -u poc/test_multimachine.py     #  6/6   two clones, one remote
.venv/bin/python -u poc/test_locking.py          #  6/6   is the lock still needed?
.venv/bin/python -u poc/test_serverless_lock.py  #  5/5   no-server push-as-CAS
.venv/bin/python -u poc/test_mutex.py            #  8/8   single clone + flock mutex
.venv/bin/python -u poc/test_cas_patterns.py     #  which CAS patterns are safe
```

The mutex, server-less, and multi-machine suites provision their own clones and remotes
under `poc/mx/`, `poc/sl/`, `poc/mm/` and need no running server.

## Sources

- vsdd-factory `82163b7f` (+ its `.factory` worktree on `factory-artifacts`)
- beads `b1694a5` — production Dolt reference product
- Dolt 2.2.3
