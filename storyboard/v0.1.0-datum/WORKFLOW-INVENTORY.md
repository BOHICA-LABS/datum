> **Type:** Stage 2 output. **CANONICAL `WF-*` store, append-only.** IDs are never reused; a refresh
> pass INSERTS into the correct lifecycle-stage table without renumbering anything existing.
> ⚠ `evidence_basis: spec-derived, unvalidated.` `validate_by:` Phase 6, first rivetry migration.

# Master workflow inventory — `datum`

## 1. The lifecycle-stage spine (Stage 2 step 1)

Seven ordered stages reflecting `datum`'s actual usage arc. Chosen to hold every workflow without forcing
a fit; they deliberately mirror the delivery phases so a WF row and a phase exit criterion can be
compared.

| stage | name | what happens |
|---|---|---|
| **S1** | Provision | a store exists, is writable, and matches its registry |
| **S2** | Ingest | messy markdown becomes rows; interpretation is recorded as data |
| **S3** | Author | typed ops write the store — the only write surface |
| **S4** | Project | render, indexes, counts, graph — derived, never stored |
| **S5** | Gate | gates as queries; evidence; convergence computed |
| **S6** | Migrate | the per-`(project,type)` cohort ladder |
| **S7** | Operate | waves, engine, scheduler, cost |

## 2. The inventory

Columns per the runbook, adapted: `Layer` replaces `CAP-NNN` (our capability surface is the L1–L7
layering); `Verification` names the gate or test that proves it.

**Path coverage** — `happy-only` / `happy+recovery` / `N/A` — is **generated** by the Cockburn
extension brainstorm (§3) and the state machines (§4), then audited, per the runbook's own refinement.

### S1 — Provision

| WF-ID | Workflow | Persona(s) | Layer | Key ops | Need/JTBD | Coverage | Path coverage | Verification | WSJF | Scope | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|
| WF-001 | Create/upgrade a store | HUM-OP, SYS-CI | L1 | `init` | HUM-OP: a place to put artifacts | 🔨 built | happy+recovery | `TestSchema*`, `doctor` | 3.0 | IN | both zones |
| WF-002 | Prove a store is writable, not merely openable | SYS-CI, HUM-OP | L1 | `doctor` | *"is this store usable"* | 🔨 built | happy+recovery | `doctor` probes WRITABILITY | **9.0** | IN | ⚠ a second opener silently becomes READ-ONLY and fails much later — this WF exists because of that measured failure |
| WF-003 | Assert the store matches its registry | SYS-CI | L1/L2 | `doctor` | *"is my schema the schema I think"* | 📐 designed | **happy-only** | L1–L2 hash gate | **9.5** | IN | ⚠ **F2** — as specified this re-couples every project; needs version compatibility, not hash equality |
| WF-004 | Collect garbage during long work | SYS-CC, SYS-CI | L1/L7 | `migrate step` (`gc_due`) | *"don't turn 1 MB into 143 MB"* | 📐 designed | happy-only | L7-M; measured 306.6× amplification | 7.0 | IN | NEW in L7 from measurement |

### S2 — Ingest

| WF-ID | Workflow | Persona(s) | Layer | Key ops | Need/JTBD | Coverage | Path coverage | Verification | WSJF | Scope | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|
| WF-010 | Shadow a markdown corpus into rows | SYS-CC, SYS-CI | L2 | `import` | *"see the corpus as data"* | 🔨 built | happy+recovery | 132 tests; 3 corpora | 8.0 | IN | idempotent; content-keyed fingerprint |
| WF-011 | **Report per-form counts so nothing is lost silently** | all | L2 | `import` census | *"prove nothing was dropped"* | 🔍 gated | happy+recovery | `MatchCensus`; zero-match finding | **10.0** | IN | ⭐ built this session; **the anti-AP-5 workflow** |
| WF-012 | Keep BOTH records when a natural key collides | SYS-CC | L2 | `import` → `key_collision` | *"never drop a duplicate"* | 🔍 gated | happy+recovery | 123 rivetry collisions kept; arithmetic reconciles | 8.5 | IN | one behaviour replaced three |
| WF-013 | Split a ledger field into ordinal rows, reversibly | SYS-CC | L2 | `import` → `ledger_entry` | *"a ledger is not a scalar"* | 🔍 gated | happy+recovery | byte-exact join gate over 3 corpora, 18→229 | 7.5 | IN | brackets unbalanced 115/42 — recorded, **not repaired** |
| WF-014 | **Classify an untyped or unknown file (AI-mediated)** | SYS-CC | L2/L7 | `next --kind classify` → `record` | *"type the 1,132 files with no frontmatter"* | ⬜ | **happy-only** | — | **9.0** | IN | ⚠ V-J's core loop; **unbuilt**. Interpretation must be recorded as DATA and replayed |
| WF-015 | Capture a file no type claims | SYS-CC | L2 | `unmodeled_file` | *"never drop unknown input"* | 📐 designed | happy-only | — | 8.0 | IN | ⚠ **F8** — the partition is not currently REQUIRED to be total |
| WF-016 | **Resolve a type's LOCATION per project** | SYS-CC | L2 | (none) | *"read prism's layout, not vsdd's"* | ⬜ | **N/A — does not exist** | — | **10.0** | IN | ⚠⚠ **F1.** Locations are Go path literals. epic/fr/nfr = 0 for 2 of 3 projects; 114 FALSE findings |

### S3 — Author

| WF-ID | Workflow | Persona(s) | Layer | Key ops | Need/JTBD | Coverage | Path coverage | Verification | WSJF | Scope | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|
| WF-020 | Create an artifact with a minted key | SYS-CC | L3 | `<type> new` | *"add a BC"* | 📐 designed | happy+recovery | 14-step ladder | **9.5** | IN | ⚠ **no write path exists at all** (X7 blocks every cohort) |
| WF-021 | Set a declared field | SYS-CC | L3 | `<type> set-field` | *"change one value"* | 📐 designed | happy+recovery | V5/V6/V7 | **9.5** | IN | 1.0× pivot cost — the dominant shape, measured free |
| WF-022 | Append to an append-only ledger | SYS-CC | L3 | `<type> append` | *"add an amendment"* | 📐 designed | happy+recovery | idempotence token REQUIRED | 8.0 | IN | the only non-idempotent verb |
| WF-023 | Set prose (body/section) | SYS-CC | L3 | `set-body`/`set-section` | *"the content has no field"* | 📐 designed | happy-only | invariant 16 partition | 7.5 | IN | 26.3% of class C lives here |
| WF-024 | **Be refused, and know what to do next** | SYS-CC | L3/L7 | any op | *"tell me why, and the legal next action"* | 📐 designed | happy+recovery | L7-H golden files; A1–A4 | **10.0** | IN | ⭐ the highest-value agent workflow; **`next_action` is what makes it work** |
| WF-025 | Propose a field the schema lacks | SYS-CC | L3 | `propose field` (exit 4) | *"the corpus has it, the registry doesn't"* | 📐 designed | happy+recovery | proposal row; nothing written | 7.0 | IN | ⚠ **G-1** — no persona is accountable for adjudicating it |
| WF-026 | Refuse a conflict rather than merge it | SYS-CC | L1/L3 | any write | *"never lose an update"* | 📐 designed | happy+recovery | invariant 21; exit 5 | 9.0 | IN | op stream echoed = the retry payload |
| WF-027 | Explore read-only without faking a verb | HUM-OP, SYS-CC | L3 | `sql --read-only` | *"answer a one-off question"* | 🔨 built | N/A | — | 4.0 | IN | **not** a write hatch |

### S4 — Project

| WF-ID | Workflow | Persona(s) | Layer | Key ops | Need/JTBD | Coverage | Path coverage | Verification | WSJF | Scope | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|
| WF-030 | Render markdown from the store | HUM-OP | L4 | `render` | *"a review surface + offline backup"* | ⬜ | happy-only | invariant 15 | **9.5** | IN | ⚠ **blocked on 22 render schemas**, not on an engine |
| WF-031 | Prove the round trip byte-exact | SYS-CI | L4 | `render`+`import` | *"prove migration is lossless"* | ⬜ | happy-only | invariant 15, per-artifact per-field | **10.0** | IN | needs declared normalizations (1,189 key orders, 169 quoted/bare) |
| WF-032 | Derive an index and adjudicate it cell by cell | SYS-CI | L4 | `shadow` | *"is the authored index right"* | 🔨 built | happy+recovery | 658 findings, writes nothing | 8.0 | IN | stage-1 evidence for the ladder |
| WF-033 | Count without storing a count | all | L4 | `count` | *"one BC total, not six"* | 🔨 built | N/A | projections only | 8.5 | IN | 21.7× pivot on GROUP BY — measured, fine |
| WF-034 | Project the knowledge graph | SYS-CC | L4 | `graph` | *"what depends on what"* | 🔨 built | happy+recovery | CSR parity vs gonum | 5.0 | IN | 2,421 nodes; 3 ms rollup |
| WF-035 | **Prove every X × Y is covered** | HUM-OP | L4 | (none) | *"completeness at a glance"* | ⬜ | N/A — does not exist | — | 6.5 | IN | the coverage cube (T-6); this file's §6 is a hand-built instance |

### S5 — Gate

| WF-ID | Workflow | Persona(s) | Layer | Key ops | Need/JTBD | Coverage | Path coverage | Verification | WSJF | Scope | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|
| WF-040 | Run the gates against a baseline ratchet | SYS-CI | L5 | `validate` | *"did anything regress"* | 🔨 built | happy+recovery | 7,502; planted violation → exit 1 | 9.0 | IN | 67/67 Go-vs-Python parity |
| WF-041 | Produce machine evidence for a verdict | SYS-CI | L5 | `gate exec` | *"a pass must cite evidence"* | 📐 designed | happy+recovery | invariant 22; sole writer | **9.5** | IN | no flag accepts evidence bytes |
| WF-042 | **Register a gate WITH A WITNESS** | HUM-OP | L5/L7 | `gate register` | *"prove this gate CAN fail"* | 📐 designed | happy+recovery | L7-G refuses without one | **9.0** | IN | ⭐ ADD-CHECK-FIRST; closes 3 green-check findings |
| WF-043 | Block on an unevaluable gate | SYS-CI | L5 | `gate exec` | *"never fail open"* | 📐 designed | happy+recovery | vacuity guard mandatory | **9.5** | IN | `unevaluable = error = block` |
| WF-044 | Compute convergence rather than claim it | SYS-CI | L5 | `converge` | *"3 clean passes, computed"* | 📐 designed | happy-only | `converge.v1`; NULL novelty | 8.0 | IN | needs review identity (V-G, Cohort C) |
| WF-045 | Record a caller-asserted claim honestly | SYS-CC | L5/L7 | `attest` | *"record what I say, as an assertion"* | 📐 designed | happy+recovery | L7-F `evidence_basis` + `validate_by` | 8.5 | IN | ⭐ T-1; keeps V-I honest |
| WF-046 | Defer with an owner and an expiry | HUM-OP | L5 | `defer` | *"not now, but not forgotten"* | 📐 designed | happy+recovery | `deferred` abolished | 7.0 | IN | — |

### S6 — Migrate

| WF-ID | Workflow | Persona(s) | Layer | Key ops | Need/JTBD | Coverage | Path coverage | Verification | WSJF | Scope | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|
| WF-050 | **Migrate one `(project,type)` in resumable chunks** | SYS-CC | L6/L7 | `migrate step` | *"6,537 files in thousands of round trips"* | 📐 designed | happy+recovery | exit 6 + cursor; kill-and-resume test | **10.0** | IN | ⭐ V-K's biggest un-designed consequence, now designed |
| WF-051 | Pass the seven stage-1 exit gates | SYS-CI | L6 | `migrate verify` | *"is this cell safe to promote"* | 📐 designed | happy+recovery | X1–X7 | **9.5** | IN | ⚠ **F8** — X1's denominator is not independent |
| WF-052 | Refuse verification on a moved corpus pin | SYS-CI | L6 | `migrate verify` | *"don't verify against a moved target"* | 📐 designed | happy+recovery | pin check | 8.5 | IN | ⭐ measured need: prism moved twice this session |
| WF-053 | Abandon a cohort and keep authoring markdown | HUM-OP | L6 | `migrate abandon` | *"back out safely"* | 📐 designed | **happy-only** | mandatory `before` on every transformation | 9.0 | IN | ⚠ revert is total only if `before` is truly mandatory — **untested** |
| WF-054 | Replay a recorded interpretation instead of re-inferring | SYS-CC | L2/L6 | `migrate step` | *"determinism from the record, not the parser"* | 📐 designed | happy-only | — | 8.5 | IN | V-J's honesty rule; **unbuilt** |

### S7 — Operate

| WF-ID | Workflow | Persona(s) | Layer | Key ops | Need/JTBD | Coverage | Path coverage | Verification | WSJF | Scope | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|
| WF-060 | Derive the wave schedule | SYS-CC | L6 | `waves` | *"what can run in parallel"* | 🔨 built | happy+recovery | 148 stories/16 waves/0 cycles | 6.0 | IN | — |
| WF-061 | Advance the workflow frontier | SYS-CC | L6 | `engine step` | *"what is next"* | 📐 designed | happy-only | three-valued conditions | 7.5 | IN | ⚠ 140 conditional edges; greenfield cannot reach COMPLETE today |
| WF-062 | Report cost per phase/wave/story | HUM-OP | L6 | `cost` | *"what did this cost"* | ⬜ | N/A | — | 4.5 | OUT (v1.1) | budget tiers have no data source today |
| WF-063 | Surface unpushed/dirty worktrees | HUM-OP | L1 | `fsck` | *"real git-level data-loss risk"* | ⬜ | happy-only | — | 6.0 | IN | F20; prism's E-1/E-2 |

## 3. Cockburn extension-condition brainstorm (Stage 2 step 2a) — the generator behind Path coverage

Run against the two highest-WSJF main-success scenarios. Extensions that have their own state were
**promoted to their own WF row**, per the runbook, rather than left as notes.

**WF-050 `migrate step` main success:** select cell → lease → read N units → transform → validate →
write → version → audit → return cursor.

| step | condition the system can detect | handling | promoted? |
|---|---|---|---|
| select | no such cell | exit 1 | — |
| lease | lease held by another | exit 5, do not queue | — |
| lease | **holder crashed** | TTL expiry, or human revocation writing no artifact | — |
| read | **a file appeared/vanished since the pin** | refuse: WF-052 | ✅ WF-052 |
| read | budget hit before the unit set is exhausted | **exit 6 + cursor** | ✅ WF-050 core |
| transform | value exceeds a column | truncate-and-report, never abort | — |
| transform | a ledger cannot be rejoined byte-exact | **CONSERVATION FAILURE, block** | ✅ WF-013 |
| transform | needs interpretation | emit a work unit; do not guess | ✅ WF-014 |
| validate | any of the 14 ladder steps fails | exit 1 with `ladder_step` | ✅ WF-024 |
| write | conflict | exit 5, echo the op stream | ✅ WF-026 |
| write | **journal amplification unbounded** | `gc_due` blocks the next step | ✅ WF-004 |
| return | caller retries the same step | idempotence key → same result | ✅ AP-1 defence |
| return | **caller ignores exit 6** | ⚠ **undetectable by `datum`** — see G-7 | ⚠ NEW |

⚠ **G-7 (new).** `datum` cannot detect a caller that stops following `next`. A migration left half-done
looks identical to one not started since the last cursor. **Mitigation to design:** a cell in
`CONTINUATION` state past a declared staleness window is a finding surfaced by `doctor` — otherwise
exit 6 protects against *misreading* truncation but not against *abandoning* it.

## 4. State machines with explicit error/recovery states (Stage 2 step 3a)

Authoritative source for Stage-6 state enumeration and Stage-7 evidence rows.

**A `(project,type)` migration cell**

```
        ┌──────────────────────── abandon ────────────────────────┐
        v                                                          │
   not-started ──▶ shadow ──▶ dual-write ──▶ authoritative ──▶ md-retired
                     │            │               │
                     ├─ gate-failed (X1..X7) ─────┤        error states:
                     ├─ pin-moved (refuse verify) ┤        · conservation-failure (terminal, blocks)
                     ├─ continuation (resumable) ─┤        · lease-lost (recover: re-lease, resume cursor)
                     └─ awaiting-interpretation ──┘        · gc-due (recover: collect, resume)
```

**Invalid transitions that must be refused (error coverage):** `not-started → authoritative` (skips
evidence); `md-retired → dual-write` (markdown is gone); any forward move while a
`conservation-failure` is open; `authoritative → md-retired` without invariant 15 green.

**An op invocation** — this is the state set Stage 6 must render (one per exit code):

```
submitted ──▶ V0 role ──▶ V1..V13 ladder ──▶ transact ──▶ version ──▶ audit ──▶ 0 ok
                │              │                 │
                └─ 3 denied    ├─ 1 data-wrong   ├─ 5 conflict
                               ├─ 2 datum-failed    └─ 6 continuation
                               └─ 4 schema-insufficient
```

## 5. FMEA on the safety- and tenancy-bearing workflows (Stage 2 step 2b)

Severity × Occurrence × Detection, in user terms. RPN feeds WSJF's risk-reduction input.

| # | WF | failure mode | effect | S | O | D | RPN | control |
|---|---|---|---|---|---|---|---|---|
| F-1 | WF-016 | a type's location is not found | the universe is EMPTY; every reference to it becomes falsely dangling | 9 | **9** | **8** | **648** | ⚠ **none today** — F1. Zero-universe guard proposed |
| F-2 | WF-051 | X1 counts 0 files and 0 rows and passes | a whole type migrates as "complete" while absent | **10** | 6 | **9** | **540** | ⚠ **F8** — needs an independent denominator |
| F-3 | WF-024 | a refusal is misparsed | the agent retries wrongly or gives up | 6 | 8 | 4 | 192 | machine-only stdout; `next_action` |
| F-4 | WF-050 | caller abandons a `CONTINUATION` | half-migrated cell reads as not-started | 8 | 5 | **9** | **360** | ⚠ **G-7** — no control today |
| F-5 | WF-003 | registry hash mismatch after a binary upgrade | **every** project's store refuses to open at once | 8 | 7 | 2 | 112 | ⚠ **F2** — loud but wrong; needs version compatibility |
| F-6 | WF-041 | evidence is asserted, not executed, and read as proof | a gate passes on a claim | **10** | 4 | 6 | 240 | L7-F typing + `gate exec` sole writer |
| F-7 | WF-053 | `before` is missing on a transformation | revert is partial; corpus left inconsistent | **10** | 3 | 7 | 210 | mandatory `before` — ⚠ **untested** |
| F-8 | WF-026 | a divergent create is accepted on retry | lost update | 9 | 4 | 8 | 288 | `CONFLICT-DIVERGENT` |
| F-9 | any | cursor reused across projects | cross-tenant write | **10** | 2 | 8 | 160 | ⚠ **G-5** — cursor must carry its project |

**Top three by RPN: F-1 (648), F-2 (540), F-4 (360).** All three are *detection* failures — the effect
is invisible, which is exactly this repo's dominant defect class. **F-1 and F-2 are the same root
cause** (an enumerator that defines its own denominator), which is why F1/F8 are the review's top
priorities.

## 6. Coverage matrices (Stage 2 step 4) — zero-orphan findings stated explicitly

**Layer → WF(s).** Every layer maps to ≥1 workflow.

| layer | WFs | covered? |
|---|---|---|
| L1 storage | WF-001..004, 063 | ✅ |
| L2 schema/ingest | WF-010..016 | ✅ |
| L3 ops | WF-020..027 | ✅ |
| L4 projections | WF-030..035 | ✅ |
| L5 policy | WF-040..046 | ✅ |
| L6 engine | WF-050..054, 060..062 | ✅ |
| L7 interfaces | WF-004, 024, 050 (cross-cutting) | ✅ |

**Finding: ZERO layer orphans.**

**Invariant → WF(s).** The stricter direction — every v1 invariant must have a workflow that enforces it.

| invariant | WF | covered? |
|---|---|---|
| 15 round trip | WF-031 | ✅ (unbuilt) |
| 16 verbatim body + partition | WF-023, X2 | ✅ |
| 17 nothing derivable stored | WF-033, generated ops | ✅ |
| 18 lease→validate→transact→version→audit | WF-020..022 | ✅ |
| 19 scoped aggregates | WF-033 | ✅ |
| 20 write-time validation | WF-021 | ✅ |
| 21 no force path | WF-026 | ✅ |
| 22 evidence for every verdict | WF-041, 042 | ✅ |
| 23 identity never in content | V12 in WF-020/021 | ✅ |

**Finding: ZERO invariant orphans.**

**Persona → WF(s).** ⚠ **ONE ORPHAN.** Every persona has workflows *except* the accountable role for
adjudicating a `datum propose field` proposal (WF-025) — see **G-1**. Per the runbook, an accountable RACI
"A" role with no designed-for persona **is a missing persona**, not a missing note.

**Anti-persona → defence.** AP-1..AP-5 all trace to at least one control (see the anti-roster's own
coverage argument). ⚠ **erasure has no anti-persona → G-6.**

**Silently-missed-capability audit (Stage 2 step 6).** Re-diffed the WF list against the **current**
layer set this pass: L7 exists now and did not when the other four layer docs were written, so
WF-004/024/050 are new this pass. ⭐ **This audit is the reason they are here** — the inventory would
otherwise have "still ended where it always ended," which is the exact defect the runbook's step 6
exists to catch and which its own corpus demonstrated (a matrix silently stopping at CAP-022).

## 7. Routed gaps (Stage 8 step 1) — ZERO unrouted

| id | gap | surfaced at | owner / route |
|---|---|---|---|
| **G-1** | no persona is accountable for adjudicating an exit-4 proposal | Stage 1 RACI | **HUM-OP**; add to L3–L4's change-management path as a named role |
| **G-2** | CI re-run mints a NEW idempotence key → double-apply | Stage 1, SYS-CI | L7 **Q8**; derive the key from the CI run id |
| **G-3** | human accessibility deliberately out of scope for v1 | Stage 1 Spectrum | **risk-accepted, recorded** so absence reads as a decision |
| **G-4** | ⭐ NEW — **timing side channel on `DENIED-ASYMMETRY`** is undefended and unmentioned in any design doc | AP-3 | L7 §5; add to the non-leakage gate alongside Q5/Q6 |
| **G-5** | ⭐ NEW — **a cursor must carry its project** and be refused against another store | AP-4 | L7 §3; else AP-4 returns via the new chunking surface |
| **G-6** | ⭐ NEW — **erasure has no anti-persona**; nothing models premature deletion or a vacuously-passing "verify by count assertion" | anti-roster coverage | migration doc, Cohort G + `retired_types` |
| **G-7** | ⭐ NEW — `datum` cannot detect an **abandoned** `CONTINUATION` | §3 extension brainstorm | L7 §3; `doctor` finding past a staleness window |
| **F1** | locations are Go literals, not registry data | adversarial review | registry `sources:` + zero-universe guard |
| **F8** | X1's denominator shares its numerator's enumerator | adversarial review | total whole-corpus partition |
| **F2** | registry hash gate re-couples all projects | adversarial review | version-compatibility gate |
| **F3** | X4 embeds a volatile scalar | adversarial review | cite artifact + version |

| **G-8** | ⭐ NEW — a recorded classification is REPLAYED forever; no `reclassify` / re-open path exists | journey-sys-cc S2 | L2/L7; a wrong interpretation is durable without it |
| **G-9** | ⭐ NEW — exit 2 is the only handoff that leaves the machine, and **who receives it is unrouted** | journey-sys-cc S3 | L7 §4; name the escalation channel |

⭐ **Six gaps (G-4..G-9) are NEW — surfaced by this storyboard run and by nothing else.** That is the
run's concrete return: three came from the **anti-persona** stage (the runbook's least-used stage here
transferred best), one from the **Cockburn extension brainstorm** on WF-050, and two from the single
**journey walk** — all four of those stages being ones a purely code-first review does not perform.
**Common shape across G-7/G-8/G-9: a state entered with no route back out** (an abandoned cursor, a
durable misclassification, an unrouted escalation). None of the four layer designs names that class.
