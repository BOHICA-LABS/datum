---
title: Dolt as the sole interface to factory artifacts — feasibility assessment
date: 2026-07-30
status: research spike complete, POC verified
verdict: GO (phased), with two hard constraints
---

# Dolt as the sole interface to factory artifacts

**Question:** Can a Dolt-backed tool replace the `factory-artifacts` orphan git branch
as the only interface to all vsdd-factory artifacts?

**Verdict: GO, phased.** The current design is a hand-maintained relational database
implemented in markdown files, and it is measurably failing at exactly the guarantees a
database provides for free. **33/33 POC tests pass** against the live corpus across four
suites (13 store + 8 relationship-graph + 6 multi-machine + 6 locking), plus a 5-pattern
concurrency comparison. Three hard constraints apply:
**one shared server is mandatory** — the lock is provably incorrect across independent
clones — markdown must become a generated export, and **every guarded write must carry a
per-attempt unique token** or Dolt silently merges concurrent updates (§3c).

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

## 4. Gaps, risks, and things that are worse

Honest accounting. These are real and some are unattractive.

### 4.1 Hard constraints

1. **One shared server is mandatory, so there is now a daemon — and a single point of
   failure.** Embedded Dolt is single-writer, and M5 proves the CAS lock does **not** hold
   across independent clones (both machines acquired it). So correctness requires every
   agent to reach *one* `dolt sql-server`: a process, a port, liveness/health handling, a
   startup dependency for every agent, and a component whose loss halts the factory. The
   current design's genuine advantage — zero moving parts beyond git — is lost. beads
   carries an entire `internal/doltserver` package (7,750 lines incl. tests) plus circuit
   breakers and a `doctor` subsystem for exactly this. Budget for it.

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
```

All three suites are re-runnable and idempotent. `test_multimachine.py` builds its own
remote and two clones under `poc/mm/` and tears down its servers.

Evidence pinned at: vsdd-factory `82163b7f`, beads `b1694a5`, Dolt 2.2.3, 2026-07-30.
