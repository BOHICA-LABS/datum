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
database provides for free. 13/13 POC tests pass against the live corpus. Two hard
constraints apply (server mode is mandatory; markdown must become a generated export).

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

## 4. Gaps, risks, and things that are worse

Honest accounting. These are real and some are unattractive.

### 4.1 Hard constraints

1. **Server mode is mandatory, so there is now a daemon.** Embedded Dolt is single-writer;
   the CAS lock needs a real transaction. That means a `dolt sql-server` process, a port,
   liveness/health handling, and a startup dependency for every agent. The current design's
   genuine advantage — zero moving parts beyond git — is lost. beads carries an entire
   `internal/doltserver` package (7,750 lines incl. tests) plus circuit breakers and a
   `doctor` subsystem for exactly this. Budget for it.

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

- **Multi-machine concurrent writes.** Verified 16 concurrent writers against one local
  server. Not tested: two machines, push/pull contention, or the merge-on-pull path under
  real conflict. This is the main remaining technical risk.
- **`dolt gc` / long-term growth.** The DB is 29–41 MB for a 36 MB corpus at 1,607 commits
  and grew ~12 MB across a handful of test runs. Growth under years of commits is untested.
- **Trace edges were not migrated.** `bc_trace` is empty — traceability lives in BC prose,
  so extracting it is real migration work (and will surface more dangling refs).

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
.venv/bin/python poc/fa.py count --by-subsystem
.venv/bin/python poc/fa.py validate
.venv/bin/python poc/fa.py lock acquire --holder me
.venv/bin/python -u poc/test_spike.py               # 13/13
```

Evidence pinned at: vsdd-factory `82163b7f`, beads `b1694a5`, Dolt 2.2.3, 2026-07-30.
