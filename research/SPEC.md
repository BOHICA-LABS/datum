---
title: fa — specification for the sole interface to factory artifacts
date: 2026-07-30
status: spec derived from a verified spike (112/112 tests against the live corpus)
evidence: vsdd-factory @82163b7f (.factory on factory-artifacts) · beads @b1694a5 · Dolt 2.2.3
---

# `fa` — the sole interface to factory artifacts

Every capability below is backed by a passing test against the **live** vsdd-factory
corpus (1,959 BCs, 3,145 files, 1,607 commits). Nothing here is aspirational; where
something is untested or deliberately excluded it says so.

**112/112 tests, fourteen suites.** See [ASSESSMENT.md](ASSESSMENT.md) for the
feasibility argument and the measured problems in the current design.

---

## 1. Architecture

```
  machine A (dev 1)                          machine B (dev 2)
  ┌───────────────────────────┐              ┌───────────────────────────┐
  │ ONE Dolt clone            │              │ ONE Dolt clone            │
  │  ├── flock write mutex    │              │  ├── flock write mutex    │
  │  └── agents a0..aN (procs)│              │  └── agents b0..bM (procs)│
  └───────────────┬───────────┘              └───────────┬───────────────┘
                  │        dolt push / pull              │
                  └──────────────┬───────────────────────┘
                                 ▼
                  shared git remote (the project's OWN repo)
                        refs/dolt/data          ← the database
                        refs/heads/main         ← source code
                        rendered markdown       ← generated export, committed
```

**No `sql-server`. No daemon. No new hosting.** Dolt data lives under `refs/dolt/data`
in the repo you already have (T12), so the `factory-artifacts` orphan branch is retired
without provisioning anything.

Three coordination layers, verified to compose (§3f of the assessment, 9/9):

| Layer | Mechanism | Scope |
|---|---|---|
| L1 | `flock` on a lockfile in the clone | orders one machine's agent processes |
| L2 | `dolt push` non-fast-forward rejection | arbitrates between machines |
| L3 | Dolt 3-way **cell-level** merge on pull | reconciles pre-push divergence |

---

## 2. Data model

Records with real keys, replacing hand-maintained markdown indexes:

**Nodes** — `subsystem`, `bc`, `vp`, `story`, `epic`, `capability`, `domain_invariant`,
`nfr`, `fr`, `adr`, plus `pipeline_state`, `phase`, `factory_lock`, `schema_migrations`.

**Edges** (all with FKs on both ends) — `vp_bc`, `vp_di`, `vp_nfr`, `vp_subsystem`,
`story_bc`, `story_vp`, `story_fr`, `story_subsystem`, `story_dep` (the dependency DAG),
`bc_trace`.

1,490 edges loaded from real frontmatter. Node universes come from **authoritative
declaring documents only** (`capabilities.md`, `invariants.md`,
`phase-0-ingestion/pass-4-nfr-catalog.md`, `prd.md`, ADR headings, `stories/epics/`) —
building them from grep-over-everything would make every reference resolve trivially.

### Design rules

1. **No count is ever stored.** Counts are `COUNT(*)`. This is what makes the corpus's
   current four-way total disagreement (1949/1955/1959/1962) unrepresentable.
2. **Every cross-reference is a row with FKs.** A dangling reference becomes impossible
   rather than "caught by a grep sweep" (T2, G7 — all 8 edge tables verified).
3. **Cross-machine counters are APPEND-ONLY rows, never mutable cells** (D4/D5/D5b).
4. **Prose stays as files.** Burst logs, adversarial review passes, and lessons are
   narrative; relationalizing them buys nothing.

---

## 3. Capability surface

Each row names the test that proves it.

### 3.1 Read

| Capability | Test | Measured |
|---|---|---|
| Count anything, by any grouping | T1, W8 | `COUNT(*)` 0 ms |
| Fetch a record by id | T13 | PK lookup 0 ms |
| Full traceability chain story → epic / BC → subsystem / VP → NFR + DI, one query | G1 | — |
| Reverse blast radius: BC → verifying VPs + implementing stories | G2 | — |
| Coverage gaps (unverified BCs, unimplemented BCs, orphan stories) | G3 | **90.2% of BCs have no VP** |
| Dependency-direction reconciliation (`blocks` vs `depends_on`) | G4 | 53 one-directional edges found |
| Cycle detection + transitive closure (recursive CTE) | G5 | acyclic; 26,130 paths |
| Whole-corpus 4-hop rollup | G8 | 3 ms |
| Per-record history / "when did this change and to what" | T6, W2 | — |
| Cell-level diff for a commit | T7 | — |
| Point-in-time read (`AS OF`) | L6 | — |
| Author + message per revision | W6 | — |

### 3.2 Write

| Capability | Test | Notes |
|---|---|---|
| `create` with validation in the write path | W1 | 2 accepted, 6 refused: malformed id, unknown subsystem, empty title, bad capability, BC-S/subsystem prefix mismatch, duplicate |
| `amend` with version bump + history retained | W2 | `v1.0 → v1.1 → v1.2` |
| `retire` (lifecycle change, inbound refs survive) | W3 | active-coverage queries exclude it |
| Multi-record atomic write | W4 | a bad edge rolls back the story too |
| `delete` refused while inbound refs exist; explicit cascade | W9 | — |
| Idempotent re-import | W5 | identical HEAD, zero working-set churn |
| Reads never blocked by a writer | W7 | 6 reads completed during a write hold |

### 3.3 Validate (gates as queries, not hooks)

`W8` expresses the real gates as SQL: count self-agreement, no BC in an unknown
subsystem, no dangling edge, no malformed id, lease well-formedness. **A gate that is a
query cannot disagree with the data it checks** — which retires
`verify-sha-currency.sh` (269 lines) and the mandated "Defensive Sweep Discipline".

`fa validate` on the live corpus found **38 dangling references and 44 type violations**
no existing gate catches — including `S-8.09` declaring it blocks 19 stories that were
never written, and literal placeholders (`BC-4.NN.001`, `"see PO output for actual IDs"`)
sitting in structured traceability fields.

### 3.4 Render (markdown as a generated export)

| Property | Test | Measured |
|---|---|---|
| Deterministic — byte-identical across runs | R1 | 1,960 files, same digest |
| Self-consistent — every stated count equals the data | R2 | 6 sources, **one** value |
| Complete — every record is a readable file | R3 | 1,959/1,959 |
| Round-trippable — reparsing reproduces the records | R4 | 0 mismatches |
| Diff-friendly — one field change touches 2 files / 4 lines | R5 | — |
| Hand-edit detected (`render --check`) | R6 | — |
| Fast enough for every commit | R7 | 9.2 MB in 0.4 s |

### 3.5 Coordinate

| Capability | Test | Notes |
|---|---|---|
| Local write mutex (cross-process, crash-safe, bounded wait) | X1–X5 | `SIGKILL` → kernel releases |
| Cross-machine lease via push-as-CAS | S1–S3, D6 | 3 clones → exactly one winner |
| Multi-table atomic burst | L1 (locking suite) | retires the Single-Commit Burst Protocol |
| Wave branches: isolate, merge back, or discard | L4, L5 | main unaffected until merge |

### 3.6 Evolve

| Capability | Test |
|---|---|
| Versioned migration ledger (`schema_migrations`) | E1 |
| Additive migration preserving existing rows | E2 |
| New table + new edge type with FKs | E3 |
| Idempotent `migrate` | E4 |
| Two devs adding **different** columns → schema merges | E5 |
| Two devs adding the **same** column differently → conflict surfaced | E6 |
| Unsafe migration refused (no data coercion) | E7 |
| Bad migration revertible — schema and ledger revert **together** | E8 |

### 3.7 Operate

| Capability | Test | Measured |
|---|---|---|
| Onboarding: clone + identity | L1 | 0.2 s |
| Disaster recovery from the remote | L2 | identical HEAD |
| Markdown fallback readable with no Dolt | L3 | — |
| Growth + `dolt gc` | L7 | ~6 KB/commit; gc reclaims |
| Large prose bodies round-trip | L8 | 211 KB intact |

---

## 4. Invariants `fa` MUST enforce

These are not style guidance. Each one, if violated, produces **silent** data loss or
corruption, and each was found empirically.

1. **Every guarded write carries a per-attempt UNIQUE value.**
   Dolt has no row locking and merges cell-by-cell, so contenders writing *identical*
   values all get `affected_rows = 1` and all "win". `fence = fence + 1` fails 30/30
   with all six writers winning. *(§3c; this invariant is relaxed only for writes
   serialized by the local mutex — X3.)*
2. **Every agent aborts or resolves on merge conflict.**
   An unguarded conflicting pull leaves the clone half-merged; then *every* commit by
   *any* agent on that machine fails with `cannot merge with uncommitted changes` —
   which blames staging, not the conflict. One careless agent downs its dev's fleet. *(D8)*
3. **Cross-machine counters/allocators are append-only rows with unique keys.**
   Not mutable cells. *(D4/D5/D5b)*
4. **Retries are idempotent.**
   On a shared clone a push publishes siblings' commits too, so "my push failed" does
   not mean "my work was not published". A duplicate-key error on retry means *already
   applied* and must fall through to push, not bail — bailing strands the earlier
   commit, which the next reset discards. *(D5b)*
5. **Pull at the start of every unit of work.**
   There is no cross-machine read consistency without it (~150 ms). *(D7)*
6. **One mutex hold = one unit of work, batched into one Dolt session.**
   Cost is per *invocation*, not per write: a 1,959-BC import is 531 s
   one-statement-at-a-time versus 13.4 s batched. *(X8)*
7. **A `PRIMARY KEY` is not a concurrency control.**
   Two concurrent writers inserting byte-identical rows merge silently; naive ID
   allocation produced `[1,1,1,1,1,1]`. Allocators need a per-attempt token. *(L4 locking)*
8. **Markdown is written only by `fa render`, and `render --check` runs in CI.**
   Otherwise there are two truths and strictly more drift than today. *(R6)*

9. **Trust zones are separate database DIRECTORIES (or a server with GRANTs).**
   VSDD requires that some agents structurally cannot see some artifacts. A single
   server-less database makes that impossible — `dolt sql` needs only filesystem
   access. Zones under one `--data-dir` leak via cross-database query. Only separate
   directories, or a shared server with table-level GRANTs, hold. *(A1–A5;
   [GAP-MATRIX.md §4.1](GAP-MATRIX.md))*
10. **One clone per factory INSTANCE.** Checkout is per-clone: cross-branch reads work,
   cross-branch writes are refused. Concurrent instances therefore need a clone each.
   *(I9)*
11. **Leases are per-scope, never singular.** One global lock serializes the whole
   project and makes parallel instances pointless. *(I3)*

Invariants 1–7 exist because Dolt's conflict detection is documented as "too lenient"
([#7681](https://github.com/dolthub/dolt/issues/7681), strict mode unimplemented). They
must live in `fa`'s single write path, not in agent instructions.

---

## 5. CLI surface

```
fa init                      create/migrate the store
fa migrate [--check]         apply pending migrations; --check exits non-zero if pending
fa import <path>             ingest a markdown corpus (idempotent)
fa render [--check]          write the generated export; --check fails on drift
fa validate [--strict]       integrity + type + coverage gates; non-zero on violations

fa get <id>                  fetch any record by id
fa count [--by <dim>]        counts, never stored
fa trace <id> [--depth n]    full chain in either direction
fa coverage [--subsystem X]  unverified / unimplemented rollup
fa history <id>              per-record revisions
fa asof <commit> <id>        point-in-time read
fa diff <a>..<b>             cell-level change set

fa create <type> [fields]    validated create
fa amend <id> [fields]       validated amend + version bump
fa retire <id>               lifecycle transition
fa rm <id> [--cascade]       refused while inbound refs exist

fa lease acquire|release|status --scope <wave-N|phase-N|cycle-X>
fa wave register <N> <story...> | merge | abandon
fa wave gate <N> --pass|--defer <reason>|--fail
fa instance new <name> --mode <m> | list | graduate <name> | abandon <name>
fa context <wave-N>          derive the exact spec set for a wave
fa task next <story> | done <task>
fa template instantiate <type> [fields]
fa changelog <artifact>      the amendment ledger
fa sync                      pull, then push (conflict-guarded)
fa gc                        reclaim space
fa doctor                    clone health: identity set, no half-merge, schema current
```

`fa doctor` is not optional polish — it covers the two failure modes that silently
break a clone: missing git identity (every pull fails) and an unresolved half-merge
(every commit fails).

---

## 6. Non-goals

Stated explicitly so scope does not drift:

- **Prose artifacts stay files.** Burst logs, adversarial review passes, lessons,
  session checkpoints. They have no keys and no counts.
- **Binary/large attachments stay on disk** with a path in the DB. Demo evidence and
  screenshots are untested here and deliberately excluded.
- **No shared `sql-server`.** Only if a future phase needs sub-second, up-front
  exclusion for many agents per host — and it reinstates invariant 1 (X7).
- **`fa` does not resolve merge conflicts automatically.** It aborts cleanly and
  reports. Resolution policy is a separate decision, undesigned.
- **`fa` does not replace git for source code.** Only artifacts.
- **Multi-repo mode** (`.factory-project/` + `factory-project-artifacts`) is not
  modelled; single-project only.
- **Conflict-resolution policy** is out of scope. `fa` surfaces and aborts cleanly.

---

## 7. Phasing

| Phase | Scope | Risk | Value |
|---|---|---|---|
| **1** | Read-only shadow: `import` + `validate` in CI. Markdown stays truth. | Very low — zero agent changes, no daemon | Catches all 82 findings, including the four-way count drift |
| **2** | Move the lease to `fa lease` (push-as-CAS). Delete the STATE.md YAML lock, the `--force-with-lease` machinery, and `verify-sha-currency.sh`. | Low | Closes a documented CWE-367 |
| **3** | Invert authority for **record-shaped** artifacts only (BC/VP/story/subsystem/phase). Markdown becomes `fa render` output. | Medium — touches `state-manager` and every `create-*` skill | Drift becomes unrepresentable; 90.2%-style coverage gaps become visible |
| **4** | Parallel wave branches. | Medium | Concurrency the single-orphan-branch design forbids today |

Phase 1 delivers most of the correctness benefit at almost none of the cost, which is
why it goes first.

---

## 8. Known gaps

Honest list of what is **not** proven:

1. **Real network remote.** Every multi-machine test used a `file://` remote. GitHub
   latency, auth, and partial-failure recovery are untested; the 640 ms/acquire figure
   is a floor.
2. **Prose-embedded references.** The graph was built from frontmatter. BC/VP bodies
   also cite ADRs and other BCs in prose; those edges are unextracted, so the 38
   dangling references are a **floor**, not a total.
3. **One unreproduced anomaly.** An 8-agent run of the cross-machine counter test
   produced 7 agents reporting success while only 6 increments landed. Not reproducible
   in the controlled setup; logged rather than explained. Invariant 3 avoids the class.
4. **Conflict-resolution policy** is undesigned (who resolves, how, and with what
   authority).
5. **Long-horizon growth.** ~6 KB/commit measured over 40 commits; years of history and
   `gc` cadence are unmodelled.
6. **Embedded driver not benchmarked.** All timings shell out to `dolt sql`, paying
   ~140–270 ms of process spawn per invocation. beads' embedded `dolthub/driver/v2` path
   would keep one handle open under a single mutex hold and give real transactions —
   likely faster and cleaner than invariant 4's idempotent-retry shape. Benchmark before
   committing to an implementation.
