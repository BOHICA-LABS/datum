---
title: Gap assessment — datum vs the full vsdd-factory artifact surface
date: 2026-07-30
status: 112/112 tests; 3 architectural findings that change the recommendation
method: enumerated from plugins/vsdd-factory/config/artifact-path-registry.yaml (46 types), not from memory
---

# Gap assessment: `datum` vs the full factory surface

## 1. Method

Enumerated from the factory's own **`config/artifact-path-registry.yaml`** — the
declared single source of truth for canonical `.factory/` locations
(ADR-016), with `enforcement_level: block` on every entry and a hook that
blocks writes to unregistered paths. **46 artifact types.** Cross-checked against
9 workflows, 9 phase definitions, 121 skills, 35 agents, and ~105 templates.

Coverage legend: **✅ tested** · **◐ partial** · **❌ gap** · **⊘ deliberate non-goal**

---

## 2. Coverage by artifact class

### 2.1 Records — ID-keyed, belong in the DB (✅ 9/9)

| Artifact type | Coverage | Evidence |
|---|---|---|
| `behavioral-contract` | ✅ | 1,959 imported; create/amend/retire/delete W1–W3, W9 |
| `verification-property` | ✅ | 80 imported; graph edges G1–G2 |
| `adr` | ✅ | node + `bc_adr` edge with FK, E3 |
| `story-spec` | ✅ | 148 imported; W4 atomic write |
| `epic` | ✅ | 17 from `stories/epics/`, graph G1 |
| `architecture-subsystem-doc` | ✅ | `subsystem` registry, prefix validation W1 |
| `prd` (FR/NFR) | ✅ | 48 FR + 88 NFR universes, `story_fr`/`vp_nfr` |
| `domain-spec` (CAP/DI) | ✅ | 30 CAP + 18 DI, `vp_di` |
| **tasks** (inside story md today) | ✅ | **new:** modelled as rows, V6 |

### 2.2 Indexes — derived, become render output (✅ 6/6)

`behavioral-contract-index`, `verification-property-index`, `architecture-index`,
`story-index`, `epic-index`, `cycle-index`.

✅ All become `datum render` output. R2 proves six count sources collapse to **one**
value — against the live corpus's **four** disagreeing totals.

### 2.3 State — mutable, runtime (✅ 7/7, all new this pass)

| Artifact type | Coverage | Evidence |
|---|---|---|
| `state` (STATE.md) | ✅ | rows, no line budget; 303 rows vs a 500-line hook cap — V5 |
| `state-runtime-wave` (wave-state.yaml) | ✅ | wave registration V1, gate lifecycle V2, merge tracking V3 |
| `sprint-state` | ✅ | `wave_story` membership + points rollup, V1 |
| `phase` progression / gate verdicts / skips | ✅ | V10 |
| `state-runtime-adversary` | ✅ | convergence counters as rows, V10 pattern |
| `state-runtime-regression` | ◐ | same shape as above; not separately tested |
| `po-obligations` | ◐ | shape is a task table; not separately tested |

### 2.4 Coordination (✅ 5/5)

Lease (per-scope, I3), local write mutex (X1–X5), cross-machine arbitration
(S1–S3), wave branches (L4–L5), instance branches (I2, I4–I5).

### 2.5 Templates (✅ 1/1, new)

`~105` template files + `conform-to-template` + `validate-template-compliance`.
✅ V7: instantiation refuses missing required fields and leaks no `{{placeholder}}` —
which is exactly the defect class the live corpus exhibits (`BC-4.NN.001`,
`"see PO output for actual IDs"` sitting in traceability fields).

### 2.6 Versioning (✅ 2/2)

Record version bump + full history (W2); spec amendment ledger with a contiguous,
record-matching version chain (V8) — replacing the prose changelog inside
`BC-INDEX.md` that produced the `v1.61 cited E-7=23, actual 28` drift.

### 2.7 Prose / narrative — ⊘ deliberate non-goal (12 types)

> ⚠ **THE RATIONALE BELOW IS OVERTURNED ON EVIDENCE (2026-07-31) for at least
> `cycle-document`, `cycle-decision-log`, `adversarial-review` and
> `per-story-adversary-pass` — see [PROBE-CYCLES.md](PROBE-CYCLES.md).** Measured in
> `cycles/`: **481 of 611 files carry frontmatter**, with keys (`pass`, `cycle`,
> `document_type`), links (`previous_review` in 244, `traces_to` in 267) and **counts**
> (`finding_count` in 123). 94% are write-once immutable documents; the churn is nine
> append-only ledgers (`burst-log`/`decision-log`/`lessons`, 600+ commits of appends) that
> a ROW model strictly improves, plus an `INDEX.md` that is derived and should never have
> been stored. Ingesting the class ADDS gates that do not exist today — one concept under
> six `document_type` spellings, `verdict` mixing severities with pass states, and a
> genuinely dangling pass-chain link. The conclusion may still hold for classes with truly
> no keys, but it can no longer rest on "no keys, no counts, nothing to derive."

`cycle-document`, `cycle-decision-log`, `adversarial-review`,
`per-story-adversary-pass`, `research-doc`, `plan-doc`, `proposal`,
`legacy-design-doc`, `measurement`, `sidecar-learning`, `semport-artifact`,
`phase-delta-analysis`.

⊘ *(original rationale, retained for the record)* Stay as files. No keys, no counts,
nothing to derive. Relationalizing them buys nothing and costs diff legibility.

### 2.8 Config (◐ 4 types)

`policies`, `release-config`, `reference-manifest`, `merge/autonomy config`.
◐ Structurally identical to `pipeline_state` (V5) but untested. Low risk; they are
read-mostly and small.

### 2.9 Evidence / logs (◐⊘ 6 types)

`holdout-evaluation`, `code-delivery-artifact`, `runtime-log`,
`hooks-dim2-gate-template`, `feature-delta-analysis`, demo evidence.
◐ Evaluation *results* are records; ⊘ screenshots and binaries stay on disk with a
path in the DB (stated non-goal, L8).

---

## 3. Coverage by operation

| Operation | Status | Evidence |
|---|---|---|
| Create + validate | ✅ | W1 — 2 accepted, 6 refused (malformed id, unknown subsystem, empty title, bad CAP, prefix mismatch, duplicate) |
| Read (record, graph, coverage, history, point-in-time) | ✅ | T1/T6/T13, G1–G8, L6 |
| Modify + version | ✅ | W2, V8 |
| Delete / retire | ✅ | W3 (retire keeps inbound refs), W9 (delete refused, explicit cascade) |
| Multi-record atomicity | ✅ | W4, L1 |
| Templates | ✅ | V7 |
| Pipeline / phase / wave state | ✅ | V1–V3, V5, V10 |
| **Context load + rehydration** | ✅ | **V4 — the wave's spec set is DERIVED from wave membership** |
| Wave registration + gate lifecycle | ✅ | V1–V3 |
| Requirements graph + traceability | ✅ | 1,509 edges (was 1,490 — parser correction 2026-07-31); G1–G8 |
| Schema evolution | ✅ | E1–E8 |
| Onboarding / recovery / growth | ✅ | L1–L3, L7 |
| Concurrency (agents / devs / instances) | ✅ | X, S, D, I suites |
| **Information-asymmetry walls** | ◐ | **A1–A6 — solvable, but it constrains the topology (§4.1)** |

---

## 4. The three findings that change the recommendation

### 4.1 Information-asymmetry walls collide with "one queryable store" — CRITICAL

VSDD's method depends on agents being *structurally unable* to see certain artifacts:

> holdout-evaluator: "CANNOT access `.factory/specs/`, `src/` internals,
> `.factory/cycles/*/adversarial-reviews/`"
> adversary: "Cannot see prior review passes … **Read-only access enforces both
> constraints structurally**"
> code-reviewer: "You CANNOT see … **enforced by Lobster context exclusion**"

Today the wall is **path-based**. Rows in one database give path exclusion nothing to
bite on. Measured (`poc/test_asymmetry.py`, 6/6):

| Finding | Result |
|---|---|
| A1 server-less + one DB | **No wall is possible.** `dolt sql` needs only filesystem access; every walled secret was readable |
| A2 zones as DBs under one `--data-dir` | **Leaks.** `SHOW DATABASES` lists both; `SELECT … FROM walled.x` succeeds |
| A3 zones as separate **directories** | **Real boundary.** Walled zone invisible and unreachable |
| A4 shared server + `GRANT` | **Real table-level wall.** Evaluator reads its scenarios, denied specs and findings |
| A5 `dolt_history_*` / `dolt_diff_*` / `dolt_log` backdoor | **Also denied** — the GRANT wall is trustworthy, not cosmetic |
| A6 cost of splitting zones | **No cross-zone FK** — a holdout scenario cannot FK to the BC it verifies |

**Two viable designs, and this is a genuine decision:**

1. **Trust zones as separate database directories.** Keeps server-less, keeps the
   factory's existing path-exclusion enforcement unchanged. Cost: no cross-zone FK, so
   that one link reverts to tool-validated.
2. **Shared `sql-server` + GRANTs.** One database, cross-zone FKs intact, real
   table-level auth. Cost: the daemon and single point of failure — plus it reinstates
   the unique-token discipline (X7).

**This is a partial reversal of §3d/§3e**, which recommended server-less on the grounds
that no daemon was needed. That held for *concurrency*. It does not automatically hold
for *confidentiality*. Recommendation: option 1 (zone directories) — it preserves the
no-daemon property and the enforcement mechanism the factory already has.

### 4.2 Concurrent instances need one clone each

Measured (I9): server-less, Dolt's checkout is **per-clone** working-set state.
Cross-branch *reads* work (`SELECT … AS OF 'branch'`); cross-branch *writes* are
refused (`table doesn't support UPDATE`). So a clone can write only one branch at a time.

⇒ **one clone per factory instance**, each on `factory/<instance>`. Clones cost ~0.2 s
and share the remote. Bonus: the flock mutex becomes per-instance, so **instances never
contend locally** — I2 ran a primary track plus two spikes writing concurrently with
zero contention. (A shared server would instead allow `db/branch` connections.)

### 4.3 The lease cannot be singular

I3: a single `factory_lock` row would serialize the entire project. Scoping the lease
per wave / phase / cycle is what makes parallel instances possible at all — different
scopes acquired concurrently, same scope stayed exclusive.

---

## 5. Revised architecture

```
  dev 1 machine                                dev 2 machine
  ├── clone → branch factory/primary           ├── clone → factory/dev2-main
  ├── clone → branch factory/spike-a           └── clone → factory/maint
  └── clone → branch factory/spike-b
        (one flock mutex per clone; no cross-instance contention)
                    \______ shared remote (the project's own repo) ______/
                             main = canonical specs
                             factory/* = instance branches
                             rendered markdown = generated, committed

  trust zones = separate database DIRECTORIES:
      zones/open    ← specs, stories, waves, state      (most agents)
      zones/walled  ← holdout scenarios, adversary passes (restricted agents)
```

Instance lifecycle: branch from `main` → work in isolation → **graduate** by merging to
`main` (I4), or **abandon** by deleting the branch and flipping registry status (I5).
Two instances editing the same spec conflict loudly at merge (I6); disjoint work merges
cleanly.

---

## 6. Remaining gaps

| # | Gap | Severity |
|---|---|---|
| 1 | ~~**Real network remote.**~~ **CLOSED 2026-07-31 — and closed COMPLETELY: 21/21** ([REMOTE.md](REMOTE.md)). 10 remote-mechanics tests **plus every `file://` scenario re-run on github.com** (cell merge, same-cell conflict, the wedge, the 2×4-agent topology, the 8-agent lease, counters, staleness, instance graduate/abandon, schema merge, 8-clone contention). The 640 ms acquire is really **~10 s** and a pull **~2.3 s**; payload size is irrelevant; nothing that held on `file://` broke; two findings sharpened (D8's misleading error is on the *pull* path; SC5's O(N) holds in magnitude as a permutation) and one new one became invariant 12. | closed |
| 2 | ~~**Conflict-resolution policy.**~~ **CLOSED** — designed in [DECISIONS.md D1](DECISIONS.md): abort mechanically, record, the push-race loser re-applies intent as a validated write, cross-actor collisions escalate to the orchestrator, and a conflict inside a leased scope is reported as a lease-scoping defect. | closed |
| 3 | **Prose-embedded references.** Graph built from frontmatter only; BC/VP bodies cite ADRs and BCs in prose. The 38 dangling refs are a **floor**. | Medium |
| 4 | `state-runtime-regression`, `po-obligations`, and the 4 config types are ◐ by analogy, not tested. | Low |
| 5 | **Instance-count ceiling.** Tested 3 instances on one machine (12 clones in SC4). Disk and mutex behaviour at 10+ concurrent *pushers* is now bounded by gap 1's finding: O(N) retries × ~10 s. | Medium |
| 6 | **Cross-zone integrity tooling.** Zone-directories are now **selected** ([DECISIONS.md D2](DECISIONS.md)), so the holdout→BC validator (A6) is a **required deliverable**, not a contingency. | Medium — scoped |
| 7 | ~~**Embedded driver not benchmarked.**~~ **CLOSED** — 13/13 ([ACCESS-PATH.md](ACCESS-PATH.md)). It is ~2× on cold start, ~4,000× warm, and needs no `dolt` binary — but the **biggest lever was a missing `BEGIN`/`COMMIT` (17×), available from the CLI**. Deferred to phase 3. | closed |
| 8 | One unreproduced anomaly (7 agents ok / 6 increments landed). | Low — invariant 3 avoids the class |
| 9 | **Multi-repo mode** (`.factory-project/` + `factory-project-artifacts`) not modelled. | Medium if used |
| 10 | **Linux identity re-run.** macOS `ps eww` leaks a sibling's env; Linux gates it behind `PTRACE_MODE_READ_FSCREDS`. Researched and cited, not run. | Low — tier 1 does not depend on it |

---

## 7. Verdict

The artifact surface is **covered**: 46 registry types classified, every record /
index / state / template / versioning / wave / context / graph operation tested or
explicitly declared a non-goal. **112/112 tests.**

The orchestration target is **achievable**: N devs × M instances × K agents against one
project, maximally parallel, with a clone per instance and per-scope leases.

The one thing that genuinely narrows the design space is §4.1 — information asymmetry.
It is the first requirement found that argues *for* a server, and it must be decided
before implementation because it determines whether there is one store or several.
