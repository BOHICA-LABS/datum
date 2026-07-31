---
title: Dolt as the sole interface to factory artifacts — feasibility assessment
date: 2026-07-30
status: research spike complete, POC verified
verdict: GO (phased) — recommended topology = ONE clone + local flock mutex (§3e); no daemon, no token discipline
---

# Dolt as the sole interface to factory artifacts

**Question:** Can a Dolt-backed tool replace the `factory-artifacts` orphan git branch
as the only interface to all vsdd-factory artifacts?

**Verdict: GO, phased.** The current design is a hand-maintained relational database
implemented in markdown files, and it is measurably failing at exactly the guarantees a
database provides for free. **55/55 POC tests pass** against the live corpus across seven
suites (13 store + 8 relationship-graph + 6 multi-machine + 6 locking + 5 server-less +
8 single-clone mutex + 9 two-devs composite), plus a 5-pattern concurrency comparison.

**Recommended topology: ONE clone + a local `flock` write mutex (§3e).** It needs no
daemon, no single point of failure, and — because serialized writers cannot merge — none
of the unique-token discipline that a shared server would require. The single hard
constraint that remains is that markdown must become a generated export, plus one
operational rule: batch a unit of work into one Dolt session per lock hold (§3e X8).

Modelling the full spec graph surfaced **38 dangling references and 44 type violations**
that no existing gate catches, and quantified coverage nobody had measured: **90.2% of
behavioral contracts have no verifying verification property.**

Every number below was measured, not estimated. Sources: `/Users/jmagady/Dev/vsdd-factory`
@ `82163b7f`, its `.factory` worktree on `factory-artifacts`; beads @ `b1694a5`; Dolt 2.2.3.

---

## 1. Current state: what the orphan branch actually is

`.factory/` is a git worktree on an orphan `factory-artifacts` branch. Measured scale:

| Metric | Value |
|---|---|
| Files | 3,145 (3,085 markdown) |
| Size | 36 MB |
| Commits on `factory-artifacts` | 1,607 |
| Behavioral contract records | 1,959 |
| Spec files under `specs/` | 2,091 |
| `STATE.md` | 379 lines (target is <200; a hook blocks at 500) |

The artifacts are **ID-keyed records with foreign keys**: `BC-S.SS.NNN` contracts belong to
subsystems, trace to `VP-NNN` properties, and are referenced by `S-NN.NN` stories. Indexes
(`BC-INDEX.md`, `ARCH-INDEX.md`, `STORY-INDEX.md`) are hand-maintained materialized views.
Counts are denormalized into frontmatter (`total_bcs: 1955`).

This is a relational schema. It is being maintained by prose discipline and grep.

### 1.1 The discipline is documented, elaborate, and losing

The engine has built substantial machinery to hold this together:

- **`state-manager` agent** — the single write funnel, with a mandated "Defensive Sweep
  Discipline (S-7.02)": run a corpus-wide grep for the old count after any count change,
  and log the sweep in the commit message.
- **`verify-sha-currency.sh`** (269 lines) — a bespoke hook for cross-record SHA agreement.
- **Single-Commit Burst Protocol (TD-VSDD-053)** — replaced a two-commit protocol that was
  self-referential: Stage 2 wrote the Stage 1 SHA into content that Stage 1 had just
  committed. Documented cost: *"manifested 6× in one session, 5+ force-pushes."*
- **`factory-lock` / `factory-unlock` skills** — a cooperative cross-session lock.

The hook's own header comment is the clearest statement of the root cause:

> "That check was removed because the cite was self-referential — STATE.md sits on the
> factory-artifacts branch, so committing STATE.md changes HEAD, instantly staling any
> HEAD-SHA cite inside the same content."

A record cannot correctly describe the transaction that writes it. That is not a bug in the
protocol; it is a property of storing state inside the versioned object itself.

The corpus counts its own recurrences. `BC-INDEX.md` changelog entries include
*"19th L-P28-001 META"* and *"third recurrence of count-narrative drift class"*, with the
declared total walking 1863 → 1905 → 1909 → 1929 → 1943 → 1947 → 1954 → 1955.

### 1.2 The corpus is drifted right now (measured, T1)

Five hand-maintained assertions of one fact, in a corpus that is adversarially reviewed,
hook-gated, and has a dedicated sweep discipline:

| Source | Asserted BC total |
|---|---|
| `BC-INDEX.md` frontmatter `total_bcs:` | **1955** |
| `BC-INDEX.md` body `**Total**` row | **1949** |
| `ARCH-INDEX.md` `**Total BCs:**` | **1949** |
| Distinct `BC-…` IDs in `BC-INDEX.md` rows | **1962** |
| `BC-*.md` files on disk | **1959** |

Four distinct values. The frontmatter and the body of the **same file** disagree by 6.
`SELECT COUNT(*) FROM bc` returns 1959 and cannot disagree with itself.

### 1.3 Referential integrity is already broken (measured, T2/T3)

- **3 dangling references:** `BC-INDEX.md` cites `BC-1.06.011`, `BC-3.07.003`, `BC-3.07.004`.
  No record file exists for any of them.
- **1 identity violation:** `BC-2.02.013-host-run-subprocess.md` breaks the
  `BC-x.y.z.md` convention every index lookup and sweep regex depends on.

A `FOREIGN KEY` makes the first class unrepresentable; a `PRIMARY KEY` makes the second
irrelevant. Verified: the POC's FK rejected the exact same reference with
`Foreign key violation on fk: fk_trace_bc`.

### 1.4 The lock has a documented race

`factory-lock` stores the lock as a YAML block **inside `STATE.md`** and achieves mutual
exclusion by `git fetch` then `git push --force-with-lease`. The skill documents its own
failure mode:

> "Acquire failed — concurrent lock write detected. … (TOCTOU acquire-race CWE-367:
> another session wrote the lock between your fetch and your push.)"

Beads reached the identical conclusion independently, in `PROPOSAL-cas-conditional-update.md`:

> "The scripts paper over it with re-reads … but re-reads only narrow the window; they
> cannot close it."

---

## 2. Reference implementation: what beads proves

beads (`github.com/steveyegge/beads`) is a production Dolt product — a distributed graph
issue tracker for AI agents. Directly transferable findings:

| Pattern | beads implementation | Applicability |
|---|---|---|
| **Two deployment modes** | embedded `dolthub/driver/v2` (in-process, **single writer**) vs external `dolt sql-server` (**concurrent writers**) | We need server mode — the factory is multi-agent by design |
| **Data in the git remote** | Dolt data under `refs/dolt/data`, safely sharing the project's own git remote | Replaces the orphan branch with **no new infrastructure** |
| **CAS for coordination** | `UPDATE … WHERE id=? AND assignee=?` in one tx; `RowsAffected==1` is the verdict; typed mismatch errors, never swallowed | Direct replacement for the lock's TOCTOU |
| **Markdown/JSONL is an export** | `.beads/issues.jsonl` is "an export for git-diffable review", not truth | The model for keeping human review workflows |
| **Collision-free IDs** | hash-based (`bd-a1b2`) so parallel branches never collide on ID allocation | Relevant to BC/VP/story ID allocation across waves |
| **Schema migration** | `schema_migrations` table + `MigrateUpWithLock` | Answers spec-schema evolution |
| **Testing** | `testcontainers-go/modules/dolt` | Real-DB integration tests in CI |

beads is the existence proof that the architecture works at scale with agent writers.

---

## 3. POC results — 13/13 against the live corpus

Built `poc/fa.py` (the sole interface) + `poc/schema.sql`, imported the **real**
`vsdd-factory/.factory` corpus, ran `poc/test_spike.py`. Each test targets a specific
observed failure. Re-runnable (verified twice, exit 0).

Import: **1,959 BCs + 80 VPs + 148 stories + 10 subsystems in 12.7s, zero skipped.**

| # | Test | Result |
|---|---|---|
| T1 | markdown asserts 4 totals; `COUNT(*)` asserts 1 | PASS |
| T2 | FK rejects reference to non-existent BC (3 live dangling cites) | PASS |
| T3 | PK rejects duplicate ID; filename drift becomes irrelevant | PASS |
| T4 | **16 concurrent acquirers → exactly one wins** (no TOCTOU) | PASS |
| T5 | non-holder release refused; expired lock reclaimable | PASS |
| T6 | per-record history via `dolt_history_bc` (no commit archaeology) | PASS |
| T7 | `dolt_diff_bc` gives cell-level deltas per commit | PASS |
| T8 | two agent branches edit different BCs → both merge cleanly | PASS |
| T9 | same-cell edits **surface a conflict**, never silent loss | PASS |
| T10 | rendered `BC-INDEX.md`: frontmatter == body == rows == `COUNT(*)` | PASS |
| T11 | cross-cutting questions in SQL, not grep sweeps | PASS |
| T12 | Dolt history pushes into a **plain git remote** (`refs/dolt/data`) | PASS |
| T13 | 1,959 rows: `COUNT(*)` 0ms, PK lookup 0ms, prefix scan 1ms | PASS |

Notable secondary result: the POC's `validate` command independently rediscovered exactly
the **5 cross-subsystem BC placements** that `ARCH-INDEX.md` documents as intentional
(`BC-7.06.001` → SS-01; `BC-8.29.001/002/003` + `BC-8.30.002` → SS-05) — evidence the
schema models the real domain rather than an idealization of it.

T11 also surfaced a fact no current artifact states: **1,470 of 1,959 BCs have no
capability assigned.** That is one `WHERE capability IS NULL`.

---

## 3a. The full relationship graph (second pass)

The first pass did **not** test referencing — `bc_trace` was empty because the
frontmatter parser skipped every line beginning with whitespace or `-`, which
discarded every list-valued edge in the corpus. Corrected and re-run.

The corpus declares a real graph in frontmatter: BCs carry `subsystem`,
`capability`, `replacement`; VPs carry `bcs[]`, `domain_invariants[]`, `nfrs[]`,
`source_bc`, `scope`; stories carry `epic_id`, `behavioral_contracts[]`,
`verification_properties[]`, `functional_requirements[]`, `subsystems[]`, and a
`depends_on[]`/`blocks[]` dependency DAG.

Modelled as 10 node types and 9 edge tables; **1,490 edges loaded** from the live
corpus. Node universes were built from authoritative declaring documents only
(`capabilities.md`, `invariants.md`, `pass-4-nfr-catalog.md`, `prd.md`,
architecture ADR headings, `stories/epics/`) — not from grep-over-everything,
which would make every reference resolve trivially and prove nothing.

### Graph tests (8/8, `poc/test_graph.py`)

| # | Test | Result |
|---|---|---|
| G1 | story → epic / BC → subsystem / VP → NFR + DI **in one query** | PASS |
| G2 | reverse blast radius: BC → verifying VPs + implementing stories | PASS |
| G3 | coverage gaps quantified | PASS |
| G4 | `A blocks B` vs `B depends_on A` reconciled by JOIN | PASS |
| G5 | cycle detection + transitive closure (recursive CTE) | PASS |
| G6 | cascade delete removes edges; rollback restores | PASS |
| G7 | **all 8 edge tables** reject a reference to a non-existent node | PASS |
| G8 | whole-corpus 4-hop rollup in 3ms | PASS |

G1 output — the artifact that does not exist anywhere in the markdown corpus:

```
story S-1.04 (epic E-1: dispatcher foundation)
  BC-1.05.001 [SS-01] -> VP-004 (unit-test) NFR=NFR-SEC-001,NFR-SEC-009 DI=DI-004
  BC-1.05.002 [SS-01] -> VP-021 (unit-test) NFR=NFR-SEC-001,NFR-SEC-005,... DI=DI-004,DI-005
  BC-1.05.005 [SS-01] -> None            (no VP verifies this contract)
```

### What the graph exposed

**Coverage (G3) — no artifact in the corpus states any of this:**

| Measure | Value |
|---|---|
| BCs with **no verifying VP** | **1,767 of 1,959 (90.2%)** |
| BCs with **no implementing story** | **1,648 of 1,959 (84.1%)** |
| Stories anchored to no BC | 67 |
| VPs verifying nothing | 0 |
| Least-verified subsystems | SS-10 **0/58**, SS-08 2/218, SS-06 8/586 |

SS-10 has 58 behavioral contracts and zero verification properties pointing at any
of them. That is one `LEFT JOIN … WHERE IS NULL`, and it is invisible to grep.

**Dangling references (38) — targets that do not exist:**

- **27 × `story.blocks` → missing story.** `S-8.09` declares it blocks
  `S-8.11`–`S-8.29`; the corpus contains `S-8.00`–`S-8.10` and `S-8.30`. Those 19
  stories were never written. `S-9.00` blocks `S-9.01`–`S-9.04`, also absent.
  Verified absent from the whole tree, not just the import.
- **5 × `story.behavioral_contracts` → missing BC.** `S-4.05` and `S-4.07` claim to
  implement `BC-1.06.011`, `BC-3.07.003`, `BC-3.07.004` — **the same three phantom
  BCs cited by `BC-INDEX.md`.** So the traceability chain terminates in nothing from
  both ends: the index lists them and stories claim to implement them, and no
  record exists.
- **6 × `story.functional_requirements` → missing FR** (`FR-RESOLVER-001`, a
  namespace absent from the PRD registry).

**Type violations (44) — field contains something other than its declared type:**

- 16 × `VP.scope` multi-valued (`"SS-01, SS-03"`) in a scalar-declared field.
- 8 × `VP.bcs` holds an ID plus prose; **7 × `VP.bcs` is not an ID at all** —
  including literal unfilled placeholders `BC-4.NN.001`, `BC-6.NN.002`, and the
  string `"see PO output for actual IDs — state-manager will cross-link"` sitting
  in a structured traceability field.
- 4 × `story.functional_requirements` contains **CAP** ids (`CAP-002`, `CAP-003`,
  `CAP-008`) — wrong namespace entirely.
- 3 × `story.depends_on` contains **epic** ids (`E-8`, `E-9`) in a story-typed field.
- 2 × `bc.replacement` holds a prose sentence where a BC id belongs.
- 2 × `story.subsystems` holds `"SS-04 (Plugin Ecosystem)"`.

**Dependency-direction disagreement (G4):** the corpus records `depends_on` and
`blocks` independently, so they can disagree. 22 `blocks` edges have no matching
`depends_on`, and 31 `depends_on` edges have no matching `blocks` — 53 one-directional
declarations. A scheduler reading only one field sees a different graph than one
reading the other.

**Good news, stated plainly:** the dependency graph is **acyclic** (26,130
transitive paths, traversed to depth 12), every referenced DI and NFR resolves
(all 18 DIs and 50 NFRs are declared — the NFR registry is real, it just lives in
`phase-0-ingestion/` rather than under `specs/`), and no VP verifies nothing.

## 3b. Multi-machine concurrency (the flagged gap)

Two **independent clones** — separate data directories, separate `dolt sql-server`
processes on ports 3401/3402, one shared remote. 6/6 (`poc/test_multimachine.py`).

| # | Test | Result |
|---|---|---|
| M1 | disjoint writes on 2 machines converge via push/pull | PASS |
| M2 | stale push refused (`! [rejected] non-fast-forward`) | PASS |
| M3 | **cell-level merge: same row, different columns, zero conflicts** | PASS |
| M4 | same-cell edit surfaces `CONFLICT (content): Merge conflict in bc` | PASS |
| M5 | **CAS lock does NOT span machines** (expected negative) | PASS |
| M6 | one shared server → exactly one of two clients acquires | PASS |

**M3 is the strongest positive result in the whole spike.** Machine A changed
`title` and machine B changed `capability` **on the same row**; the merge produced
`{'title': 'A edits title', 'capability': 'CAP-777'}` with zero conflicts. A
line-based store cannot do this — in markdown, two agents editing different
frontmatter fields of the same BC file is a textual conflict.

**M5 is the load-bearing negative result.** With independent clones, each machine's
`factory_lock` row is local until sync, so **both machines acquired the same lock
and each believed it won** (A saw `holder=machineA`, B saw `holder=machineB`, both
`ROW_COUNT()==1`). Per-machine clones give *convergence*, not *exclusion*.

Consequence for the design: **the CAS lock only works if every agent talks to ONE
shared `dolt sql-server`** (M6 confirms exclusion is restored there). A
clone-per-machine topology needs a different mechanism entirely. This materially
tightens constraint 4.1.1 — server mode is not merely convenient, it is the only
topology in which the lock is correct.

Operational finding: a fresh `dolt clone` inherits **no author identity**, and
`dolt pull` creates a merge commit — so every pull fails with
`Author identity unknown` until `user.name`/`user.email` are configured in the
clone. This silently broke 3 of these tests on the first run, and one of them
*passed for the wrong reason* (a "conflict detected" that was really an identity
error). Clone provisioning must set identity.

## 3c. Do we still need the lock? (and a correction)

Short answer: **the lock's data-integrity job disappears; its coordination-lease job
does not — and it must be rebuilt, because the obvious CAS is unsafe on Dolt.**

### CORRECTION to §3 / §1.4

The pass-1 headline "T4 CAS lock: 16 concurrent acquirers, exactly one wins" was
**right by accident**. That UPDATE set `fence = fence + 1`, which DoltHub explicitly
documents as an invalid conflict token:

> "Do not use `row_lock = row_lock + 1` as the conflict token: concurrent snapshots
> can calculate the same next value, which Dolt regards as the same change and merges
> successfully." — [dolthub.com/blog/2021-05-19-dolt-transactions](https://www.dolthub.com/blog/2021-05-19-dolt-transactions/)

`poc/test_cas_patterns.py` P2 isolates that pattern: **30/30 trials, all 6 writers
won.** T4 only passed because it *also* wrote a per-agent-unique `holder` value; the
fence contributed nothing. `poc/fa.py` has been fixed to write a random token.

### Why the obvious CAS is unsafe

Dolt has **no row locking** and merges concurrent commits **cell by cell**:

- Docs: *"Row-level locks are not supported."* `LOCK TABLES` parses but is a no-op
  ([supported-statements](https://docs.dolthub.com/sql-reference/sql-support/supported-statements)).
  Confirmed empirically — L2 shows `SELECT … FOR UPDATE` does not block.
- Same row, **different** columns → both commits succeed, both changes land.
- Same column, **same value** → both succeed, *both* get `affected_rows=1`.
- Same column, different values → one commits, the other gets **1213** and must retry.
- Issue [#7681](https://github.com/dolthub/dolt/issues/7681) calls conflict detection
  *"too lenient"* and proposes a strict "No row merge" mode — **not implemented**.
- beads names this the **"zombie-merge bug"** and fixes it with a random `row_lock`
  cell plus a retry wrapper (`internal/storage/issueops/lease.go`).

So `affected_rows == 1` proves only that the row matched **in this transaction's
snapshot** — not that this connection was the unique global winner.

### Measured (`poc/test_cas_patterns.py`, 30 trials × 6 writers)

| Pattern | Verdict | Winners/trial |
|---|---|---|
| Guarded UPDATE, contenders write **identical** values | **UNSAFE** | 6 of 6, every trial |
| Guarded UPDATE + `fence = fence + 1` (pass-1 design) | **UNSAFE** | 6 of 6, every trial |
| Guarded UPDATE writing a **per-attempt unique** value | SAFE | exactly 1, 30/30 |
| `row_lock` token guard + fresh random token (DoltHub/beads) | SAFE | exactly 1, 30/30 |
| `GET_LOCK()` advisory mutex on a pinned connection | SAFE | exactly 1, 30/30 |

And the same trap bites uniqueness (`poc/test_locking.py` L4): a PRIMARY KEY does
**not** stop two concurrent writers inserting **byte-identical** rows. Naive ID
allocation gave `[1,1,1,1,1,1]` — six writers each believing they had allocated
seq 1, with one row stored. Adding a per-attempt `owner` token gave `[1,2,3,4,5,6]`.
This qualifies the pass-1 T3 claim: PK/UNIQUE rejects duplicates **sequentially**,
not for concurrent identical inserts.

### What Dolt replaces, and what survives

| The lock's job today | Under Dolt |
|---|---|
| Serialize multi-file state writes (STATE + handoff + wave-state) | **Gone.** A transaction is atomic by definition — L1 shows a mid-burst failure rolling back all three tables. This retires the Single-Commit Burst Protocol and its 8 cite locations. |
| Prevent lost updates on a record | **Gone**, *if* every guarded write carries a per-attempt unique token (L3). Not free — it is a discipline the schema must enforce. |
| Serialize ID allocation | **Gone**, via unique-token insert + bounded retry (L4). No global lock needed. |
| Stop a second orchestrator acting during a 45-min wave gate | **Survives.** No transaction or session lock can span it: L5 shows `GET_LOCK` dies the moment the holder disconnects. L6 shows the lease must be an ordinary **row** with an expiry. |

### Recommendation

**Keep a lock, but a much smaller and weaker one.** It stops being the mechanism that
makes writes safe and becomes an *advisory coordination lease*: "orchestrator A is
driving wave 3 until 14:05". Concretely:

1. **Delete** the `--force-with-lease` CAS-on-push machinery, the STATE.md YAML lock
   block, and `verify-sha-currency.sh`'s cross-record checks. Transactions do that job.
2. **Keep** a `factory_lock`-style row lease with `holder` + `expires_at`, acquired by
   a token-carrying CAS. It can now be **scoped** — per wave, per cycle, per story —
   rather than locking the entire artifact store, because rows no longer share a file.
3. **Add** a mandatory `row_lock BIGINT` (fresh random per write) to every table with
   contended coordination columns, plus a retry-on-1213/1205 wrapper. This is not
   optional polish; without it the store silently loses updates.
4. Use `GET_LOCK()` only for short critical sections on one pinned connection — never
   as the session lease.

The uncomfortable part: **item 3 is a permanent correctness tax on every writer.**
Get it wrong in one code path and you reintroduce silent lost updates with no error
anywhere — which is precisely the class of bug the current markdown design at least
makes *visible* as a merge conflict. Any adoption must encode the token discipline in
the single write path (`fa`) so no agent can bypass it.

## 3d. Do we need a central server? (refines constraint 4.1.1)

**No — a shared server is one option, not a requirement.** §3b concluded "one shared
server is mandatory". That was too strong. Exclusion needs a synchronous *arbiter*, and
the **remote can be the arbiter** because `dolt push` is an atomic
compare-and-swap: non-fast-forward is rejected.

Note first that the §3c token fix does **not** help across machines. Two clones are two
databases; their lock rows never interact until push/pull, by which point both agents
already "hold" the lock. The token fixes same-server merge, not cross-machine exclusion.

### Push-as-CAS, verified (5/5, `poc/test_serverless_lock.py`)

Three clones, **no `sql-server` anywhere** — just `dolt sql -q` on local clones and a
shared remote. Acquire = `fetch` → `reset --hard origin/main` → guarded local `UPDATE`
→ `dolt commit` → `push`. **The push is the CAS.**

| # | Test | Result |
|---|---|---|
| S1 | 3 clones push simultaneously → exactly one wins | PASS (`mB=pushed`, `mA`/`mC`=`push-rejected`) |
| S2 | loser is refused and can read the true holder | PASS |
| S3 | 6 contended rounds × 3 clones, no anomalies | PASS |
| S4 | cost of one acquire round trip | 640 ms (local `file://` remote) |
| S5 | rejection arrives only AFTER the loser did its work | PASS (the limit) |

### The three costs of going server-less

1. **Latency: ~640 ms per acquire against a LOCAL remote** — and that is the floor.
   Over GitHub add real network time per acquire *and* per release. A server-local CAS
   was ~1 ms. That is roughly a 1000× difference in coordination cost.
2. **Wasted work on loss (S5).** The remote rejects you only after you have already
   done the work locally. Fine for a cheap lock; wrong for a 45-minute wave gate, where
   both agents would evaluate the entire gate before one is told it lost. A shared
   server refuses the loser up front, in ~1 ms.
3. **One writer at a time per clone.** Four concurrent `dolt sql` writers on a single
   clone: **2 succeeded, 2 failed** with `cannot update manifest`. The failures are loud
   (non-zero exit), not silent — but it means several agents on one host must either
   serialize through a local write mutex, or each get their own clone.

### Choosing

| | Shared `sql-server` | Server-less (push-as-CAS) |
|---|---|---|
| Exclusion | ~1 ms, refused **up front** | ~0.6–3 s, refused **after** local work |
| Concurrent writers per host | many | one per clone |
| Moving parts | daemon, port, health, **SPOF** | none beyond git |
| Multi-table atomicity | transactions | the Dolt commit itself |
| Cell-level merge | yes | yes (via push/pull) |
| Fit with today's factory | new operational surface | matches the existing fetch/push-per-phase-gate rhythm |

**Recommendation: go server-less for Phases 1–2.** It preserves the current design's
genuine advantage — zero moving parts beyond git — while still fixing the count drift,
the dangling references, and the lock's TOCTOU. The factory already pushes at every phase
gate and already tolerates that latency, so the 640 ms is paid where a fetch/push is paid
today. Introduce a shared server only if and when Phase 4 (parallel wave branches with
many agents per host) actually needs sub-second, up-front exclusion.

This materially reduces the adoption cost: **the daemon and its single point of failure
are no longer entry requirements.**

## 3e. Single clone + local write mutex — the recommended topology

If the deployment is **one clone**, with N agents as separate processes on that host,
a local write mutex is enough — and it is the *simplest and safest* of the three
options tested. 8/8 (`poc/test_mutex.py`, `poc/clonelock.py`).

Mechanism: `fcntl.flock` on a lockfile inside the clone. Cross-process (agents are
processes, not threads), kernel-released on crash, zero network cost. Bounded wait via
non-blocking flock + jittered poll, so a wedged holder cannot hang the fleet.

| # | Test | Result |
|---|---|---|
| X1 | 8 writers, **no** mutex → failures quantified | 3 ok, **5 failed** `cannot update manifest`; counter 3 of 8 — **5 increments lost** |
| X2 | 8 writers **with** the mutex | 8/8 ok, zero errors |
| X3 | **no lost updates**: 8 increments total exactly 8 | PASS |
| X4 | `SIGKILL` the holder → kernel releases the lock | PASS |
| X5 | wedged holder does not hang others (1 s bounded wait) | PASS |
| X6 | cost vs a local `sql-server` on the same clone | 141 ms/write vs 58 ms/write |
| X8 | batching: 300 statements per mutex hold | 6.8 ms/write, **40× faster** |
| X7 | the mutex — not Dolt — is what makes non-unique writes safe | PASS |

### Why this is the best option

**X3 removes the token tax.** Under the mutex, `UPDATE ctr SET n = n + 1` totals
exactly N. That is the *same shape* as `fence = fence + 1`, which §3c proved UNSAFE on
a server (30/30 trials, all 6 writers "won"). Serialized writers cannot merge, so the
whole zombie-merge hazard class disappears — and with it the permanent correctness tax
I flagged as the main objection in §3c. **Ordinary read-modify-write SQL becomes safe.**

**X4 beats a row lease.** The kernel releases `flock` the instant the holder dies. A
`holder`/`expires_at` row lease stays held for its full TTL after an agent crash (up to
45 minutes of a wedged factory), and needs stale-lock detection and a break-glass
`--force` path — the current design has exactly that. None of it is needed here.

**X1's failure mode is loud, not silent.** Without the mutex you lose writes, but every
loss is a non-zero exit with `cannot update manifest`. That matters: it means an
incomplete rollout degrades into visible errors rather than silent corruption.

### The one operational rule

X8 is a constraint, not a nicety. Cost is per **invocation** (~140–270 ms of process
spawn + storage open), not per write. Per-statement invocations extrapolate to **531 s**
for a 1,959-BC import; batching 300 statements into one session gives **13.4 s** —
matching the 12.7 s server-based import. So: **`fa` must take the mutex once per unit of
work and do all of that unit's writes in one Dolt session.** A naive implementation that
shells out per row is ~40× slower and will feel broken.

### Where this stops working

- **More than one clone.** The mutex is one host / one filesystem. Two clones need
  push-as-CAS (§3d) — the mutex says nothing across machines.
- **Adding a local `sql-server` for speed reinstates the hazard.** X6 shows a local
  server is ~2.4× faster per write, but X7 is the warning: its concurrent writers can
  merge again, so the unique-token discipline comes back with it. Batching (X8) closes
  the speed gap without giving up the safety, which is why the mutex is preferred.
- **Writes that must be visible to other machines** still need a push; the mutex only
  orders local writes.

### Revised topology recommendation

| Topology | Exclusion | Token discipline | Moving parts |
|---|---|---|---|
| **One clone + flock mutex** (recommended) | local, immediate, crash-safe | **not needed** (X3) | none |
| Many clones + push-as-CAS | ~0.6–3 s, after-the-fact | not needed (serialized per clone) | none beyond git |
| Shared `sql-server` | ~1 ms, up front | **required** (§3c) | daemon + SPOF |

The single-clone mutex is the only option that needs neither a daemon nor the token
discipline. Adopt it first; it is also the least code.

## 3f. Two devs, two machines, multiple agents each — the composite

The realistic deployment: **one git repo, two devs on separate machines, each with one
clone shared by several agent processes, no `sql-server` anywhere.** Three coordination
layers have to compose:

    L1  flock mutex per machine   -> orders that machine's local agents        (§3e)
    L2  push / non-fast-forward   -> arbitrates BETWEEN the two machines       (§3d)
    L3  Dolt 3-way cell merge on pull -> reconciles pre-push divergence

9/9 (`poc/test_two_devs.py`, 4 agents per dev, all real subprocesses).

| # | Test | Result |
|---|---|---|
| D1 | 4+4 agents, disjoint records → all converge, both machines identical | PASS (8/8 ok, 0 manifest errors) |
| D2 | same row, **different columns**, two machines → cell merge keeps both | PASS |
| D3 | same row **and column** → conflict surfaced, nothing silently dropped | PASS |
| D4 | **identical** same-cell write from both machines → coalesces, no conflict | PASS |
| D5 | naive cross-machine `n = n + 1` → not exact without a re-executing retry | PASS (3/3 lossy with no retry) |
| D5b | append-only rows with unique keys → exact across machines | PASS (8/8) |
| D6 | factory lease, 8 agents across 2 machines → one holder, both agree | PASS |
| D7 | staleness: dev B reads the old value until it pulls | PASS |
| D8 | an unresolved conflict **wedges the whole machine**; the guard prevents it | PASS |

### It composes — the good news

**D1** is the headline: eight agents across two machines writing concurrently, all
succeeded, zero `cannot update manifest`, and both clones converged to identical state.
The mutex handles intra-machine ordering while pushes are happening; the remote handles
inter-machine arbitration. They do not interfere.

**D2** is the property a markdown store cannot have: dev A sets `capability`, dev B sets
`notes`, **on the same artifact**, and both survive with no conflict. In markdown that is
a textual conflict in one file's frontmatter.

**D6**: a lease contended by both fleets simultaneously resolves to exactly one holder
that both machines agree on.

### The four rules this topology imposes

1. **Every agent MUST abort or resolve on conflict (D8).** This is the operational
   landmine. An unguarded `dolt pull` that conflicts leaves the clone half-merged, and
   then *every* subsequent commit by *any* agent on that machine fails — with
   `cannot merge with uncommitted changes`, which **blames staging, not the conflict**.
   One careless agent takes down its dev's whole fleet with a misleading error. With the
   guard (abort on conflict), the clone stays clean and the next agent declines with an
   informative reason; the divergence still has to be resolved before that dev can sync.
2. **Never use a mutable cell for a counter or an allocator across machines (D4/D5).**
   Identical same-cell writes coalesce on the pull path too, so two machines computing
   the same next value silently merge into one. `n = n + 1` was lossy 3/3 with no retry.
   With a retry that *re-executes* the read-modify-write it came out exact 3/3 — so
   correctness depends on the retry recomputing rather than re-pushing. **Use
   append-only rows with unique keys instead (D5b): 8/8 exact, and no merge-semantics
   reasoning required.** This also happens to be what makes the §1.2 count-drift class
   impossible, since counts become `COUNT(*)`.
3. **A rejected push does not mean the work was not published (D5b).** On a shared clone
   a push publishes *everything* committed locally, including siblings' work. An agent
   whose own push was rejected may still have its write carried to the remote by the next
   agent's push. Retries must therefore be **idempotent** — a re-run write that hits a
   duplicate key means "already applied", and must fall through to push rather than
   bail. Bailing strands the earlier attempt's commit, which the next reset discards.
   (This was a real bug in the harness that cost one row.)
4. **There is no cross-machine read consistency without a pull (D7).** Dev B reads stale
   values until it syncs (~150 ms). Agents must pull at the start of a unit of work, and
   anything cached across a unit boundary is a stale read.

### Honest gap

D5's `with-retry` case came out exact 3/3 in the controlled wide-window test, but an
earlier 8-agent run of the same test produced `[(7,6),(8,8),(7,6)]` — **7 agents
reporting success while only 6 increments landed**, a silent loss. It has not reproduced
deterministically and is logged as observed-but-unexplained rather than a confirmed
property. It is another reason to take rule 2 (append-only) rather than reason about
merge semantics.

### Verdict for this topology

**It works, and it is the right target.** Two devs with multiple agents each need no
daemon, no shared server, and no new infrastructure — just the repo they already have.
The cost is four disciplines that must live in the single write path (`fa`), not in agent
prose: conflict-abort, append-only counters, idempotent retry, pull-before-work. All four
are mechanical and testable, which is exactly what makes them suitable for a tool rather
than a protocol document.

## 4. Gaps, risks, and things that are worse

Honest accounting. These are real and some are unattractive.

### 4.1 Hard constraints

1. **Cross-machine exclusion needs an arbiter — either a shared server or the remote.**
   M5 proves the CAS lock does **not** hold across independent clones (both machines
   acquired it), and the §3c token fix does not change that. Two topologies work:
   a shared `dolt sql-server` (~1 ms, refused up front, but a daemon + port + health
   handling + a **single point of failure**; beads carries a 7,750-line
   `internal/doltserver` package plus circuit breakers and a `doctor` subsystem for
   exactly this), or **server-less push-as-CAS** (§3d — no daemon, but ~0.6–3 s per
   acquire, the loser learns only after doing its work, and one writer at a time per
   clone). Server-less is recommended for Phases 1–2; see §3d for the trade table.
   What is NOT optional either way is having *an* arbiter — ad-hoc per-clone locks are
   provably broken.

2. **Markdown must become a generated export.** The value only materializes if the DB is
   the sole writer. If agents keep editing `.md` directly, you get two truths and strictly
   more drift than today. This requires changing `state-manager`, every `create-*` skill,
   and the hooks. It is the bulk of the migration cost and it is not optional.

### 4.2 Operational footguns found during the spike

- **Dolt 2.2.x removed `--user`/`--password` from `sql-server`.** Users must be created via
  `CREATE USER`/`GRANT`. Cost me a failed startup; will bite CI.
- **`dolt push` stalls indefinitely against a recreated remote.** Reusing a remote name
  after the target repo was recreated hung with 0% CPU and no timeout. Any automation must
  wrap pushes in a timeout. This is a silent-hang class, the worst kind in CI.
- **Merge conflicts require `autocommit` off.** `DOLT_MERGE` errors with
  *"@autocommit must be disabled so that merge conflicts can be resolved"* — the conflict
  path needs explicit transaction management, not the default connection.
- **`refs/heads/__dolt_remote_info__`** appears as a visible branch in the shared git
  remote. Cosmetic, but it will show up in branch lists and confuse people.

### 4.3 What genuinely gets worse

- **Diff review.** `git diff` on a markdown PR is legible to humans and to review agents
  today. Dolt's storage is not diffable by `git diff`; you review via `dolt diff` /
  `dolt_diff_*` or via the rendered export. The `adversary` and `pr-reviewer` agents read
  diffs — their inputs change.
- **Prose-heavy artifacts fit the model poorly.** BCs/VPs/stories are records. But
  `burst-log.md`, adversarial review passes, and lessons are narrative documents. Forcing
  them into `LONGTEXT` columns buys nothing. Keep them as files; only relationalize what
  has an ID and a count.
- **Recovery story is less obvious.** Today: `clone + worktree add` = full restore, and
  every artifact is a readable file even with no tooling. With Dolt, a corrupted DB needs
  Dolt to read it. Mitigation: keep the rendered markdown export committed to git — it is
  a complete human-readable backup that costs nothing extra.
- **One more binary in the toolchain**, pinned and version-managed across dev and CI.

### 4.4 Unverified

- **`dolt gc` / long-term growth.** The DB is 29–41 MB for a 36 MB corpus at 1,607 commits
  and grew ~12 MB across a handful of test runs. Growth under years of commits is untested.
- **Prose-embedded references.** The graph was built from *frontmatter*. BC/VP bodies also
  cite ADRs, ECs, and other BCs in prose; those edges are not extracted and would surface
  more dangling references. The 38 found are a floor, not a total.
- **Story-ID normalization.** 148 story rows imported; graph edges were only attached to
  stories already present under a canonical `story_id`. Stories in legacy subdirectories
  with variant ID forms may contribute additional unmeasured edges.
- **Real network remote.** Multi-machine used a `file://` remote as the stand-in. Push/pull
  against GitHub over the network (auth, large-object handling, partial-failure recovery)
  is untested.
- **Conflict resolution *policy*.** M4 proves conflicts surface. Who resolves them, and how
  an agent is supposed to, is undesigned — and an unresolved conflict **blocks every
  subsequent transaction on that server** until cleared, which is a live outage mode.

---

## 5. Recommendation

**Phase it. Do not big-bang the orphan branch.**

**Phase 1 — read-only shadow (low risk, immediate value).**
Keep markdown as truth. Import into Dolt on every commit and run `fa validate` in CI.
This alone would have caught all four drift classes found here, and it needs zero changes
to how agents write. Ship this first; it earns the rest.

**Phase 2 — move the lock.** Replace the STATE.md-YAML lock with the CAS table. Smallest
self-contained win, closes a documented CWE-367, and retires `verify-sha-currency.sh`'s
cross-record checks. Requires the server, so it also proves out the daemon.

**Phase 3 — invert authority for record-shaped artifacts only.** BCs, VPs, stories,
subsystems, phase/pipeline state. Markdown becomes `fa render` output, committed for
review and backup. Indexes and counts stop being written by hand. Narrative artifacts stay
as files.

**Phase 4 — parallel wave branches.** Only once 1–3 are stable. This is where the upside
beyond hygiene is: T8 shows agents can work concurrently and merge cell-level, which the
single-orphan-branch design currently forbids.

**Do not** relationalize burst logs, adversarial reviews, or lessons. They are prose.

### Why this is worth doing

The strongest argument is not that Dolt is elegant. It is that the factory has already paid
for a database twice: once building the sweep disciplines, bespoke hooks, and burst
protocols, and again in the recurring drift those mechanisms still fail to prevent —
19 documented recurrences of one class, and a corpus that is inconsistent in four ways
right now. `SELECT COUNT(*)` has no recurrence class.

The counter-argument deserves equal weight: this trades a zero-daemon, plain-text,
trivially-recoverable store for a database with a server process. That is a real
architectural cost. Phase 1 buys most of the correctness benefit while paying almost none
of it, which is why it should go first.

---

## Appendix — reproducing

```bash
cd ~/Dev/scrap/dolt-artifact-spike
brew install dolt                                   # 2.2.3 verified
(cd poc/db && dolt sql-server --host 127.0.0.1 --port 3308 &)   # NOTE: no --user in 2.2.x
.venv/bin/python poc/fa.py init
.venv/bin/python poc/fa.py import ~/Dev/vsdd-factory/.factory
.venv/bin/python poc/graph_import.py ~/Dev/vsdd-factory/.factory   # graph + findings report
.venv/bin/python poc/fa.py count --by-subsystem
.venv/bin/python poc/fa.py validate

.venv/bin/python -u poc/test_spike.py               # 13/13  store
.venv/bin/python -u poc/test_graph.py               #  8/8   relationship graph
.venv/bin/python -u poc/test_multimachine.py        #  6/6   multi-machine (self-provisions)
.venv/bin/python -u poc/test_locking.py             #  6/6   is the lock still needed?
.venv/bin/python -u poc/test_serverless_lock.py     #  5/5   no-server push-as-CAS
.venv/bin/python -u poc/test_mutex.py               #  8/8   single clone + flock mutex
.venv/bin/python -u poc/test_two_devs.py            #  9/9   2 devs x 4 agents, 1 repo
.venv/bin/python -u poc/test_cas_patterns.py        #  which CAS patterns are safe
```

All three suites are re-runnable and idempotent. `test_multimachine.py` builds its own
remote and two clones under `poc/mm/` and tears down its servers.

Evidence pinned at: vsdd-factory `82163b7f`, beads `b1694a5`, Dolt 2.2.3, 2026-07-30.
