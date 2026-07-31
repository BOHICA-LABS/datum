---
title: fa — specification for the sole interface to factory artifacts
date: 2026-07-31
status: spec derived from a verified spike (193/194 checks, 24 suites, incl. a 200-agent fleet against a real GitHub remote; the one failure is the deliberately pathological per-write push arm)
evidence: vsdd-factory @82163b7f (.factory on factory-artifacts) · beads @b1694a5 · Dolt 2.2.3 · dolthub/driver/v2 v2.2.0 · github.com/drbothen/dolt-artifact-spike-remote
see_also: DECISIONS.md (the 3 settled calls) · ACCESS-PATH.md (which access path) · REMOTE.md (the real remote) · SCALE.md (200 agents + every decentralised contention fix) · CI-AGGREGATOR.md (the cross-internet answer)
---

# `fa` — the sole interface to factory artifacts

Every capability below is backed by a passing test against the **live** vsdd-factory
corpus (1,959 BCs, 3,145 files, 1,607 commits). Nothing here is aspirational; where
something is untested or deliberately excluded it says so.

**193 of 194 checks pass across twenty-four suites** — the single failure is S3, the
deliberately pathological "push per write" arm, which is *supposed* to be bad and is
kept red rather than tuned green. See [ASSESSMENT.md](ASSESSMENT.md) for the
feasibility argument and the measured problems in the current design, and
[DECISIONS.md](DECISIONS.md) for the three design calls that were open until
2026-07-31 and are now settled.

---

## 1. Architecture

**One clone per factory INSTANCE**, not per machine — forced by a measured constraint
(invariant 10 / I9): checkout is per-clone, so a clone can write only one branch at a
time. Clones cost ~0.2 s and share the remote.

```
  dev 1 machine                                dev 2 machine
  ├── clone → branch factory/primary           ├── clone → factory/dev2-main
  │     ├── flock mutex (per clone)            └── clone → factory/maint
  │     └── agents a0..aN (processes)
  ├── clone → branch factory/spike-a
  └── clone → branch factory/spike-b
        └─ mutexes are per-INSTANCE ⇒ instances never contend locally (I2)
                  │        dolt push / pull              │
                  └──────────────┬───────────────────────┘
                                 ▼
                  shared git remote (the project's OWN repo)
                    refs/dolt/data       ← the database
                    refs/heads/main      ← canonical specs + source code
                    factory/*            ← instance branches
                    rendered markdown    ← generated export, committed

  trust zones = separate database DIRECTORIES (invariant 9 / A1–A5):
      zones/open    ← specs, stories, waves, state        (most agents)
      zones/walled  ← holdout scenarios, adversary passes (restricted agents)
```

**No `sql-server`. No daemon. No new hosting.** Dolt data lives under `refs/dolt/data`
in the repo you already have (T12), so the `factory-artifacts` orphan branch is retired
without provisioning anything.

Four coordination layers, verified to compose (assessment §3f 9/9; I-suite 9/9):

| Layer | Mechanism | Scope |
|---|---|---|
| L1 | `flock` on a lockfile in the clone | orders one instance's agent processes |
| L2 | per-scope lease rows (wave / phase / cycle) | orders instances against each other |
| L3 | `dolt push` non-fast-forward rejection | arbitrates between clones and machines |
| L4 | Dolt 3-way **cell-level** merge on pull/merge | reconciles pre-push divergence |

Instance lifecycle: branch from `main` → work isolated → **graduate** by merging to
`main` (I4), or **abandon** by deleting the branch and flipping registry status (I5).

---

## 2. Data model

Records with real keys, replacing hand-maintained markdown indexes:

**Nodes** — `subsystem`, `bc`, `vp`, `story`, `epic`, `capability`, `domain_invariant`,
`nfr`, `fr`, `adr`, `task`, `template`, plus `pipeline_state`, `phase`, `wave`,
`factory_instance`, `instance_state`, `lease`, `spec_change`, `id_alloc`,
`schema_migrations`.

**Edges** (all with FKs on both ends) — `vp_bc`, `vp_di`, `vp_nfr`, `vp_subsystem`,
`story_bc`, `story_vp`, `story_fr`, `story_subsystem`, `story_dep` (the dependency DAG),
`bc_trace`, `bc_adr`, `wave_story`, `template_field`.

**1,509** edges loaded from real frontmatter. *(Corrected 2026-07-31 during the phase-1
build: the figure was 1,490 while the prototype's frontmatter parser treated a prose value
containing an unbalanced `[` as an unterminated inline list, swallowing every key after it.
That lost 19 edges across six S-15.x stories — and `BC-INDEX.md`'s own `total_bcs` claim.
See [LESSONS §2](LESSONS.md) and `fa/README.md`.)* Node universes come from **authoritative
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
5. **Nothing that can be derived is stored.** Wave membership derives the wave's spec
   set (V4); merge tracking derives the gate transition (V3); task status derives story
   progress (V6). Each of those is a hand-maintained list in the corpus today.

See [GAP-MATRIX.md](GAP-MATRIX.md) for how all **46** registry artifact types map onto
this model, including the 12 declared prose non-goals.

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
   commit, which the next reset discards. *(D5b; re-confirmed against github.com in
   G6, so it is not an artefact of the `file://` remote)*
5. **Pull at the start of every unit of work.**
   There is no cross-machine read consistency without it. **~150 ms on a `file://`
   remote, ~2.3 s median against github.com** — which is exactly why this is
   per-unit-of-work and not per-write. *(D7; H7)*
6. **One TRANSACTION per unit of work.**
   *(Restated 2026-07-31 — the original wording named the wrong cause. See
   [ACCESS-PATH.md](ACCESS-PATH.md).)* There are two taxes, not one. Process
   spawn (~140 ms) is the outer one, and batching statements into one session
   removes it: 531 s → 15.7 s for a 1,959-BC import. But **per-statement
   autocommit costs another ~5–7 ms in every path** — identical in the batched
   CLI (6.77 ms) and the embedded driver (5.53 ms). Wrapping the same batch in
   one explicit transaction takes it to **0.9 s**, a further **17×**, and that is
   also exactly the boundary atomicity requires. The same shape holds one layer
   up: a *push* costs the same for 1 commit as for 50, so batching is **48× per
   commit** (O3), and collapsing three `dolt` invocations per unit into one is
   **2.9×** on the local path (O2). *(X8; B5, B6, B13; O2, O3)*
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
12. **Push contention is per-BRANCH.** *(Corrected 2026-07-31 — the original
   wording named the wrong mechanism. See [SCALE.md §2](SCALE.md).)* A push is a
   compare-and-swap on a branch pointer: you are rejected whenever it moved since
   your last fetch, whether or not your data overlaps anyone's. Measured at
   scale: 10 clones pushing the SAME branch cost 54 attempts (O(N)=55), while 10
   clones pushing DISTINCT branches into the *same* git data ref cost exactly 1
   each. **Because the factory's artifact store is a single branch, this is
   nevertheless global for artifacts** — so the original conclusion stands on a
   different footing. The `--ref`-per-instance mitigation is **inapplicable**: it
   fragments the artifact store into separate lineages. All Dolt branches do share
   one git ref (`refs/dolt/data`), so a fresh unrelated database pushing to an
   existing data ref is still a non-fast-forward. *(G7, S2, S5; github.com)*
13. **Pushes to the artifact branch must be AGGREGATED, not coordinated.**
   The push cost is ~8 s fixed — independent of payload (O3), of transport (D4:
   ssh is slower) and of process spawn (embedded `DOLT_PUSH` is the same). So the
   only lever is pushing fewer times, and optimistic retry **cannot be tuned**:
   immediate retry cost 159 attempts, exponential+jitter 185, ticket order 193 —
   backoff makes it *worse*, because sleeping lets more pointers move while you
   wait. Collapse N writers to ONE push: a local `file://` relay serialised by
   `flock` within a host (17 s, no daemon), and staging refs plus an aggregator
   across hosts (64 s, no daemon). 20 writers -> 1 push. **Across the internet only
   the staging-ref form works** (a relay needs a shared filesystem; peer-pull needs
   inbound reachability), and the aggregator role is filled by **CI**, where a
   `concurrency:` group is the merge slot for free — measured 4/4 in
   [CI-AGGREGATOR.md](CI-AGGREGATOR.md) — stressed at 20 writers, **~30 s median
   end-to-end latency**, with one required feature: a stuck staging ref must be
   QUARANTINED, since re-merging it on every run costs 8-17 s forever. *(D1-D5, O1-O3,
   C1-C5;
   [SCALE.md §4](SCALE.md))*
14. **Every writer must be a CLONE of the artifact branch.** Unrelated lineages fail
   to merge with `no common ancestor` — they cannot be aggregated at all, only
   replayed. This is why fragmenting the store into per-instance refs is a one-way
   door rather than a tradeoff. *(CI-AGGREGATOR §4)*

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
- **`fa` does not resolve merge conflicts automatically.** It aborts cleanly,
  records the conflict, and requires the loser of the push race to re-apply its
  intent as a validated operation. **Policy now designed —
  [DECISIONS.md D1](DECISIONS.md).**
- **`fa` does not replace git for source code.** Only artifacts.
- **Multi-repo mode** (`.factory-project/` + `factory-project-artifacts`) is not
  modelled; single-project only.

---

## 7. Phasing

| Phase | Scope | Risk | Value |
|---|---|---|---|
| **1** | Read-only shadow: `import` + `validate` in CI **plus a dated baseline allowlist of the 82 existing findings**. Markdown stays truth. one transaction per unit of work (0.9 s import); no remote, no daemon. Implemented as `fa` subcommands — **the end state is one Go binary** (see DECISIONS D3). | Very low — zero agent changes, additive, read-only | Catches all 82 findings, including the four-way count drift. **The baseline is not optional:** a gate that blocks every PR on day one gets switched off. |
| **2** | Move the lease to `fa lease` (push-as-CAS). Delete the STATE.md YAML lock, the `--force-with-lease` machinery, and `verify-sha-currency.sh`. | Low | Closes a documented CWE-367 |
| **3** | Invert authority for **record-shaped** artifacts only (BC/VP/story/subsystem/phase). Markdown becomes `fa render` output. ~~Decide the access path here~~ — **settled: embedded, since `fa` is a Go binary** — this is where a long-lived process is worth ~4,000× on reads and where the embedded driver removes the `dolt` binary from the toolchain ([ACCESS-PATH.md](ACCESS-PATH.md)). | Medium — touches `state-manager` and every `create-*` skill | Drift becomes unrepresentable; 90.2%-style coverage gaps become visible |
| **4** | Parallel wave branches. | Medium | Concurrency the single-orphan-branch design forbids today |

Phase 1 delivers most of the correctness benefit at almost none of the cost, which is
why it goes first.

---

## 8. Known gaps

Honest list of what is **not** proven. **Gaps 1, 4 and 6 were closed on 2026-07-31**
and are struck through below rather than deleted, so the record of what was once
unproven survives.

1. ~~**Real network remote.**~~ **CLOSED — 21/21** against github.com
   ([REMOTE.md](REMOTE.md)): 10 mechanics tests plus **every `file://` scenario
   re-run on the real remote**. An acquire costs **~10 s**, not 640 ms, and a pull
   **~2.3 s**; payload size is irrelevant (33 MB and 2 rows both push in ~10 s); a
   full-corpus clone back is 2.2 s. Nothing that held on `file://` broke: cell-level
   merge, same-cell conflict surfacing, the 2×4-agent topology, the cross-fleet
   lease, append-only counters, instance graduate/abandon and schema merge all hold.
   One new finding became invariant 12.
2. **Prose-embedded references.** The graph was built from frontmatter. BC/VP bodies
   also cite ADRs and other BCs in prose; those edges are unextracted, so the 38
   dangling references are a **floor**, not a total.
3. **One unreproduced anomaly.** An 8-agent run of the cross-machine counter test
   produced 7 agents reporting success while only 6 increments landed. Not reproducible
   in the controlled setup; logged rather than explained. Invariant 3 avoids the class.
4. ~~**Conflict-resolution policy** is undesigned.~~ **CLOSED** — designed in
   [DECISIONS.md D1](DECISIONS.md): mechanical abort, an append-only conflict record,
   the push-race loser re-applies intent as a validated write, cross-actor collisions
   escalate to the orchestrator, and a conflict inside a leased scope is reported as a
   lease-scoping defect.
5. **Long-horizon growth.** ~6 KB/commit measured over 40 commits; years of history and
   `gc` cadence are unmodelled.
6. ~~**Embedded driver not benchmarked.**~~ **CLOSED** — 13/13
   ([ACCESS-PATH.md](ACCESS-PATH.md)), and the guess in this line was wrong. The embedded
   driver is ~2× on cold start, ~4,000× warm on a held handle, gives real cross-statement
   transactions, and needs no `dolt` binary — but it does **not** remove the write mutex
   (a second opener silently becomes read-only) and does **not** touch invariant 4, which
   is a git-level property. The actual lever was a missing `BEGIN`/`COMMIT`, worth 17–23×
   and reachable from the CLI. Decide the access path at phase 3.
