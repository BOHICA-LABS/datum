---
title: FA-V1-L7-INTERFACES-DELIVERY — the interface layer (CLI · MCP · CI) and the phased delivery plan
date: 2026-08-03
purpose: design L7 under V-J/V-K, where the consumer is an LLM HARNESS and no op may be long-running; and set the phased delivery plan with per-phase exit criteria
status: DESIGN — L7-A..L7-M decided; 7 phases with exit criteria; 9 open questions at the end
inputs: FA-V1-DESIGN.md (V-A..V-K, invariants 15-23) · L1-L2 · L3-L4 (the 14-step ladder + exit codes) · L5-L6 · FA-V1-MIGRATION.md · FA-V1-PIVOT-MEASUREMENT.md · STORYBOARD-METHOD-ASSESSMENT.md (T-1..T-4)
---

# L7 — interfaces, and how v1 actually ships

L7 is the layer V-J and V-K reshaped after the other four were written, so it is the only layer
designed *with* their consequences rather than corrected by them. Two of those consequences are
load-bearing and neither existed in any prior layer doc:

1. **`fa` cannot verify a model claim, only record what the caller asserts.**
2. **No op may be long-running.** A harness tool call cannot block for a 6,537-file migration.

Everything below follows from those plus the standing rule that **`fa` is a tool, never an agent** —
no LLM client, no API keys, no model config, no provider network calls.

---

## 0. Decisions

| # | Decision | Because |
|---|---|---|
| **L7-A** | **One op set, three transports: CLI, MCP, CI. The transport is a THIN CODEC over L3 and holds no logic.** | Two surfaces that each interpret would drift, which is this repo's five-instance vocabulary-drift class. Transports are generated from the same registry as the ops (L3-1). |
| **L7-B** | **Every response is a `Result` envelope with a stable machine field set, on stdout, always — including on refusal.** Human-readable text goes to stderr and is never parsed. | An agent that must regex a diagnostic is an agent that will misparse it. Separating the streams is what makes exit codes usable as control flow. |
| **L7-C** | **Exit codes are the control-flow contract, and the vocabulary is CLOSED** (0–5, §2). Never collapse two codes. | Standing rule in this repo: never collapse exit 1 (gate failed) and exit 2 (`fa` failed). Extended to all six. |
| **L7-D** | **No op is long-running. Every op is bounded by a declared unit budget and returns a CONTINUATION when it hits it.** `fa` emits the *next* unit; the harness drives the loop. | V-K. A 6,537-file migration is thousands of round trips or it is nothing. |
| **L7-E** | **Every mutating op carries an idempotence key supplied by the CALLER**; `fa` refuses to mint one for a non-idempotent op (`TOKEN-REQUIRED`). | Harnesses retry. L3-4 §7 already established this; L7 makes it a transport-level requirement so no surface can omit it. |
| **L7-F** | **Attestation is typed `evidence_basis`, non-nullable, with `validate_by` mandatory whenever the basis is not `executed`.** | T-1, and V-K consequence 1. V-I's original defect was an unverifiable claim treated as a gate; recording an assertion honestly is progress, recording it as proof repeats the bug. |
| **L7-G** | **Every gate carries a WITNESS: a stored known-bad input it provably rejects. `fa gate register` refuses a gate with no witness.** | T-2 (ADD-CHECK-FIRST). Closes the three "green check that never ran" findings *and* the two prism findings with one rule, at registration time rather than by review. |
| **L7-H** | **Op-surface completeness is GATED: every op × every reachable exit code has a golden-file capture.** | T-3. `fa` has the exit vocabulary and the rule against collapsing codes, but no coverage gate over it. This is Stage 6's "name the states, then render each one" applied to a tool surface. |
| **L7-I** | **Error payloads are designed against the A1–A4 rubric** — every refusal names the ladder step, the registry rule that governs it, and a LEGAL NEXT ACTION. | T-4. An error message for an agent is an instruction, not a diagnostic. |
| **L7-J** | **MCP is generated, not hand-written, and is capability-gated to the caller's role.** The tool list an agent sees IS its permission set. | ~800 ops would drown a human but is an asset for an agent (V-K). Generating the manifest keeps it from drifting from the CLI. |
| **L7-K** | **The harness supplies identity — role token, session/trace id, asserted model — and `fa` records it as caller-asserted, never verified.** | `fa` cannot distinguish agents sharing a process and a uid. Established by the earlier access-control work; V-K makes it the declared mechanism. |
| **L7-L** | **CI is a THIRD role, not a special case:** a non-interactive caller with its own role token, the same ops, and no ability to approve anything. | Prevents "CI can do what an agent cannot" becoming an unaudited bypass of invariant 18. |
| **L7-M** | **Long-running work GCs periodically.** The migration driver issues a collect step every N units. | **Measured, not assumed:** EAV bulk load runs at **306.6× journal write amplification** — a populated store was 147 MB of which 143 MB was one uncollected journal file. Without this a migration writes hundreds of MB of journal for single-digit MB of data. |

---

## 1. The shape: `fa` emits work, the agent interprets, `fa` records

V-K inverts the control flow from what "AI-assisted ingest" suggests. `fa` never calls an AI.

```
  harness/agent ──▶ fa next --kind classify --limit 20     "what needs interpreting?"
  fa            ──▶ WORK UNIT + a CURSOR                   the files, their content, candidates
  agent         ──▶ (interprets — the part fa cannot do)
  harness/agent ──▶ fa record classify --cursor <c> ...     the answer + evidence + confidence
  fa            ──▶ validates · versions · audits · REPLAYS thereafter
```

The replay property is what keeps a non-deterministic classifier compatible with invariant 15: the
**recorded transformation** is deterministic even though the classifier is not, so a re-run replays
decisions instead of re-inferring them, and only genuinely new input invokes the agent again.

---

## 2. The exit-code contract

Closed vocabulary. L3–L4 already assigns every named condition a code; L7 fixes the *meaning* of each
code so a caller can branch on the number alone without reading the name.

| exit | meaning | agent's correct response | named conditions (from L3–L4) |
|---|---|---|---|
| **0** | the op succeeded | continue | — |
| **1** | **the op was well-formed but the DATA is wrong** | fix the payload and retry | `NO-SUCH-ARTIFACT` · `UNKNOWN-FIELD` · `BAD-ENUM` · `BAD-REF-TARGET` · `BAD-REF-TYPE` · `MISSING-REQUIRED` · `PLACEHOLDER` · `SECTION-POLICY` · `IDENTITY-IN-CONTENT` · `DERIVABLE-VALUE` · `BAD-KEY` · `TOKEN-REQUIRED` |
| **2** | **`fa` itself failed, or the request is unanswerable** | do NOT retry; report to the human | `UNKNOWN-TYPE` · `NO-PROJECT` · `PARTITION-LOSSY` |
| **3** | **refused by policy** | do not retry; do not probe | `DENIED-ROLE` · `DENIED-AUTHORITY` · `DENIED-PROJECT` · `DENIED-ASYMMETRY` |
| **4** | **the schema is insufficient** — a proposal was filed, nothing was written | re-submit the echoed op stream after the schema lands | `SCHEMA-INSUFFICIENT` (`fa propose field`) |
| **5** | **concurrent conflict** | re-read, rebase the intent, retry with the SAME idempotence key | `CONFLICT` · `CONFLICT-DIVERGENT` |
| **6** | ⭐ **NEW — incomplete by design: a bounded op hit its unit budget** | call again with the returned cursor | `CONTINUATION` (§3) |

⚠ **Exit 6 is new in L7 and is required by L7-D.** Without it, "the op did as much as it could" has to
be smuggled into exit 0 with a flag — and a caller that ignores the flag silently stops mid-migration
believing it finished. That is the silent-truncation class with a migration attached. A distinct code
makes "not finished" impossible to read as "finished".

**Two guards, both earned here:**
- Exit 1 vs 2 is never collapsed. Exit 1 means *retrying with a better payload can work*; exit 2 means
  it cannot. An agent that retries an exit 2 loops forever.
- Exit 3 is returned **identically whether the artifact exists or not** (L3–L4 §8.3). A refusal that
  distinguishes forbidden from absent is an oracle.

---

## 3. Chunking: the load-bearing part of V-K

### The unit budget, and why it is stated in UNITS not seconds

Every bounded op declares a **unit budget** — artifacts, files, or field rows — never a wall-clock
timeout. A time budget makes the same call return different amounts on different machines, so a
migration's progress would stop being reproducible, and reproducibility is what `fa migrate verify`
rests on.

```
$ fa migrate step --project rivetry --cohort B --limit 200
{ "status":"CONTINUATION", "done":200, "remaining":4331,
  "cursor":"eyJjb2hvcnQiOiJCIiwiYWZ0ZXIiOiJCQy0yLjA2LjAxMCJ9",
  "next":"fa migrate step --project rivetry --cohort B --limit 200 --cursor eyJ…",
  "gc_due": false }
exit 6
```

Four properties, each with a reason:

| property | mechanism | why |
|---|---|---|
| **resumable** | an opaque, ordered `cursor` | the harness may die between calls; a cursor in the response is state the caller cannot corrupt |
| **ordered** | cursor is a key-ordered position, never an offset | an offset over a changing set skips and repeats rows — the silent-loss class |
| **idempotent** | `--cursor` + the caller's idempotence key | a retried step must not double-apply |
| **progress-reporting** | `done` / `remaining` in every response | so a human or agent can tell stall from slow, and so **no silent cap** is possible |

**`fa` emits the NEXT invocation verbatim** in `next`. That is deliberate: it removes the agent's need
to reconstruct pagination arguments correctly, which is exactly the sort of mechanical detail an LLM
gets subtly wrong.

### The default budget is derived from measurement, not chosen

From `FA-V1-PIVOT-MEASUREMENT.md`: a full-type pivot scan runs at **5.30 µs per field row**, and the
largest single type in any corpus is `behavioral-contract` at **49,121 field rows ≈ 260 ms**. The
per-call store budget implied by V-K is **~1 s**, so:

> **Default unit budget = 200 artifacts per step** (≈ 200 × 25 field rows × 5.3 µs ≈ 27 ms of pivot,
> leaving ample headroom for validation, write and audit within the 1 s envelope).

⚠ **This budget is a measured starting point, not a constant.** It must be re-measured once the write
path exists, because every number above is from a READ workload. Recorded as an open question (Q3)
rather than asserted.

### ⭐ GC is part of the loop (L7-M)

`gc_due` goes true every N steps, and `fa migrate step` refuses to proceed past a due collection —
because the measurement showed a 143 MB journal over ~1 MB of data at **306.6× write amplification**.
A migration that never collects converts a small corpus into a large store, and the harness has no way
to know it should ask.

---

## 4. The `Result` envelope (L7-B)

One shape for every op, every transport, success and refusal alike.

```json
{
  "op": "bc.set-field",
  "status": "BAD-ENUM",
  "exit": 1,
  "project": "vsdd-factory",
  "store_version": "hjq2…",
  "idempotence_key": "caller-supplied-uuid",
  "ladder_step": "V6",
  "rule": "enums.yaml#lifecycle_status",
  "subject": "BC-5.39.009",
  "field": "lifecycle_status",
  "submitted": "done",
  "legal_values": ["active","deprecated","retired","fulfilled","draft","withdrawn"],
  "next_action": "resubmit with one of legal_values, or `fa propose enum-value` to extend it",
  "message": "…human prose, ALSO on stderr, never to be parsed…"
}
```

`ladder_step` + `rule` + `legal_values` + `next_action` are what make this an **instruction** rather
than a diagnostic (L7-I). An agent can act on this without a retry-and-guess loop.

---

## 5. Errors as agent UX — the A1–A4 rubric (L7-I)

Adopted from `AGENTIC-UX-RUBRIC.md` (see `STORYBOARD-METHOD-ASSESSMENT.md` T-4). Every refusal payload
is checked against four dimensions, and a skipped dimension is a stated decision, never a blank.

| | dimension | L7's obligation | mechanism |
|---|---|---|---|
| **A1** | **trust calibration** — state capabilities, performance, and **limits** | every op declares what it does NOT guarantee; a `caller-asserted` row surfaces as such in every read | `evidence_basis` in the envelope (L7-F) |
| **A2** | **explainability / show your work** | a refusal names the ladder step and the registry rule, not just a message | `ladder_step` + `rule` |
| **A3** | **human-in-the-loop before impactful action** | `fa propose field` (exit 4) IS approve/reject/refine; conflicts are refused, never merged | exit 4 + invariant 21 |
| **A4** | **error / uncertainty / refusal handling with a recovery path** | every refusal carries `next_action` | `next_action` |

### ⚠ The A4 tension, stated rather than papered over

A4 requires a refusal to offer a recovery path. Exit 3 `DENIED-ASYMMETRY` must disclose **nothing** —
not even whether the artifact exists — because a refusal that distinguishes forbidden from absent is
an oracle. These pull in opposite directions.

**Resolution adopted:** `DENIED-ASYMMETRY` returns a `next_action` that is **constant across all
denied requests** — it names the *channel* for getting access adjudicated, never anything about the
subject. A constant string leaks nothing, and it still gives the agent somewhere to go instead of a
dead end.

```json
{ "status":"DENIED-ASYMMETRY", "exit":3,
  "next_action":"this op is outside your role's perimeter; request adjudication via `fa perimeter explain --role <self>` (which describes YOUR permissions and never mentions any subject)" }
```

⚠ **`fa perimeter explain` must be proven non-leaking**, because "describe your own permissions" is
one careless join away from "enumerate what exists". Gated by a test that runs it under every role and
asserts the output is a pure function of the role. Recorded as Q5.

---

## 6. Attestation: caller-asserted, never verified (L7-F)

`fa` records what the harness says and types it honestly. Three tiers, from T-1 — richer than the
binary invariant 22, and richer than V-K's two-way split:

| `evidence_basis` | meaning | `validate_by` | may satisfy a gate? |
|---|---|---|---|
| `executed` | `fa gate exec` produced it | n/a | **yes** — invariant 22's only qualifying tier |
| `caller-asserted` | the harness stated it (model identity, session, a manual step) | **required** | only where the gate registry declares `manual: true` with a named owner |
| `advisory-unreviewed` | an agent's judgement, recorded, not adjudicated | **required** | **no** |
| `prepared-unvalidated` | authored for a human to run later | **required** | **no** |

**`validate_by` is non-nullable for every basis except `executed`.** An unvalidated claim that cannot
name its validation trigger is refused at write time. This is the same move L5–L6 already made when it
abolished `gate_status: deferred` in favour of deferral rows carrying an owner and an expiry — applied
to *evidence* instead of to *deferrals*.

This is what makes V-I's growth target a config change later rather than a redesign: `fa` records the
asserted model on every agent-attributable op now, typed as an assertion, and the diversity criterion
stays in the gate registry as `manual: true` with an owner so it appears in every gate report as an
open gap rather than disappearing.

---

## 7. Gate witnesses — ADD-CHECK-FIRST (L7-G)

> **`fa gate register` REFUSES a gate that has no witness.**

A witness is a stored known-bad input the gate provably rejects, plus a known-good input it accepts.
Registration runs both and records the outcome. A gate that passes its own known-bad witness is not
registered.

This closes, with one rule at registration time:
- the three prism findings that were all *a check reported green without running*;
- the corpus's demonstrated gate passing on an empty set (the vacuity guard is necessary but not
  sufficient — a gate can be non-vacuous and still never able to fail);
- and "a green check that never ran is not evidence", which was previously a review discipline.

**Reporting rule that comes with it (also T-derived):** a gate report **omits any check that did not
run** from its list of clean checks, and names it as SKIPPED. A check that did not run must never be
readable as one that passed.

---

## 8. Op-surface completeness (L7-H)

The gate `fa` does not have and needs:

> For **every generated op**, every **reachable** exit code has a **golden-file capture** of the exact
> `Result` envelope, captured deterministically. Reachability is declared per op; an exit code declared
> unreachable must have a stated reason.

Rationale is T-3: `fa` has the exit vocabulary and the never-collapse rule but **no coverage gate over
either**. Naming the states in prose is necessary and not sufficient; each needs its rendered evidence.

Determinism requirements, lifted from the same source's capture discipline and already this repo's
practice (no network, no `dolt` binary, 132 tests in ~12 s): pinned versions, injected timestamps, no
wall-clock in output, byte-identical on re-run.

**Include the content extremes, not only the typical case.** The corpus's real extremes are measured:
a **51,566-byte** ledger field, a **1.57 MB** body, a **214,554-line** table, and an artifact with
**127** fields. An op surface with no captured case at those sizes is untested where it will break.

---

## 9. Transports

### 9.1 CLI — the universal fallback

`fa <noun> <verb> [--flags]`, machine JSON on stdout, prose on stderr, exit code as contract. Must work
under any harness, so **no harness-specific assumptions** (V-K). `--json` is the default, not a flag.

### 9.2 MCP — the rich surface, generated (L7-J)

- The manifest is **generated from the registry**, so it cannot drift from the CLI.
- **Capability-gated:** the tool list a caller sees is exactly its permitted op set. This is
  better than refusing at call time — an op an agent cannot see is an op it cannot waste a turn on —
  but it does **not** replace V0: the ladder still checks the role, because a manifest is a hint and
  the perimeter is a guarantee.
- ⚠ **The manifest must not leak the perimeter's shape.** Two roles' manifests differing tells a
  caller what exists elsewhere. Since a caller only ever sees its own, this is safe *provided* no op
  enumerates manifests. Recorded as Q6.
- Long ops return exit 6 + cursor exactly as the CLI does. **MCP gets no privileged streaming path**,
  because a second progress mechanism would be a second thing to get wrong.

### 9.3 CI — a third role (L7-L)

Same ops, own role token, non-interactive, **cannot approve**. `fa gate exec` in CI is the same op with
the same evidence typing; CI's asserted identity is recorded like any other caller's.

---

## 10. Delivery plan — 7 phases, each with exit criteria

Ordered so that **every phase leaves the tool usable and the migration abandonable.** No phase depends
on a later one.

### Phase 0 — Preconditions (BLOCKED ON THE USER)
Not engineering. Listed first because schema generation is meaningless without it.

**Exit criteria**
- [ ] the 2 namespace renames (`story-spec`→`story`, `state`→`pipeline-state`) landed;
      `validate_registry.py` stops printing `EXIT CRITERION NOT MET: 2`
- [ ] the ADR opened and the policy registered
- [ ] #671 answered
- [ ] rivetry's `delta-archive` disposition decided (it is the source of 123 of its key collisions)

### Phase 1 — L1/L2: the store the registry generates
**Exit criteria**
- [ ] `fa migrate schema` generates `artifact` + `artifact_field` + `artifact_ref` + body/section +
      the catalog mirror + **119 per-type views** from the registry, with **zero hand-written DDL**
- [ ] every generated view is queryable and returns the expected population (the pivot probe's Q9a
      check, generalised from 1 view to 119)
- [ ] `kind`-parity gate: every stored `kind` matches the catalog's declared kind
- [ ] the materialization trigger is **implemented and reports headroom**; no type is within 2× of it
      (measured today: closest is 3.9×)
- [ ] round-trip harness exists and is RED (nothing renders yet) — a Red Gate, per L7-G's own logic

### Phase 2 — L3: the write path and the ladder
**Exit criteria**
- [ ] the ~800 ops are **generated**, and `authority: derived` types emit **no** setters (invariant 17
      enforced by absence)
- [ ] the 14-step ladder is implemented and **its ORDER is tested** — rule order is a correctness
      property here (emptiness-before-counting asserted the opposite of the truth on 18 rows)
- [ ] **no op accepts a path, an id, or a count** — asserted by a test over the generated surface, not
      by review
- [ ] invariant 18 holds: `lease → validate → transact → version → audit`, with no bypass; proven by
      an attempt-every-op test that shows each one audited
- [ ] every mutating op requires a caller idempotence key (`TOKEN-REQUIRED` otherwise)
- [ ] **L7-H golden-file coverage: 100% of ops × reachable exit codes**, extremes included

### Phase 3 — L4: render, and invariant 15
**Exit criteria**
- [ ] the **22 derived types' render schemas** are drafted (AI-inferred from existing instances under
      V-J) and **ratified** — this is on the critical path and is a review task, not 22 authoring tasks
- [ ] the three highest-churn indexes (BC-INDEX 218 commits, VP-INDEX 140, cycle-index 140) have
      templates
- [ ] **invariant 15 is GREEN**: `import(render(store)) == store`, compared **per-artifact
      per-field**, never as a corpus digest
- [ ] the legal normalizations are **declared and tested** — 1,189 distinct frontmatter key orders and
      169 keys written both quoted and bare, so literal byte-exactness is unachievable without them
- [ ] authored bodies are **never regenerated** (removes the 214,554-table-line hazard by decision)

### Phase 4 — L5/L6: gates, convergence, engine
**Exit criteria**
- [ ] `fa gate exec` is the **sole** writer of the evidence table; no flag accepts evidence bytes
- [ ] **every registered gate has a witness** (L7-G) — registration refuses without one
- [ ] `unevaluable = error = block` everywhere; **no fail-open**; vacuity guard mandatory
- [ ] `deferred` abolished; deferral rows carry owner + expiry
- [ ] `novelty` is NULL when N+D=0 and NULL never satisfies a comparison (kills the live
      `0.0 (0/(0+0))`)
- [ ] ONE termination rule `converge.v1` (3 clean passes); `novelty <= 0.15` retired
- [ ] three-valued conditions with **UNKNOWN blocking**, `step_dep.on_skip` non-nullable — the fix for
      the 140 conditional-dependency edges (26% of the graph)
- [ ] greenfield can **reach COMPLETE** on a fixture (it cannot today)
- [ ] `parallel-foreach`'s iteration set is **documented** — it is a seventh step type (8 uses) that
      every doc's "six step types" list omits, and its undocumented iteration set blocks byte-exact
      round-trip of any workflow containing it

### Phase 5 — L7: the interfaces
**Exit criteria**
- [ ] CLI + MCP generated from one op set; a **drift test** proves the two surfaces expose identical ops
- [ ] every response is a `Result` envelope; **stdout is machine-only** and stderr is never parsed
      (asserted by a test that pipes stdout through a strict JSON parser for every op)
- [ ] **exit 6 + cursor**: no op exceeds its unit budget; a test drives a full cohort to completion
      purely by following `next`
- [ ] resumability proven by **killing the driver mid-migration** and resuming from the cursor alone
- [ ] retry-safety proven by **replaying every step twice** with the same idempotence key and
      asserting the store is identical
- [ ] `evidence_basis` non-nullable; `validate_by` required for every non-`executed` basis
- [ ] `DENIED-ASYMMETRY` proven non-leaking under every role, including `fa perimeter explain`
- [ ] `gc_due` enforced; a full-corpus migration's journal stays bounded (measured against the
      306.6× amplification baseline)

### Phase 6 — Migration, per `(project, type)`
Order is already decided: Cohort A → rivetry `delta-archive` → B record spine → C review family →
D ledgers → E tail → F derived → G live state last. Project order: **rivetry → vsdd-factory → prism**.

**Exit criteria, per `(project, type)` pair**
- [ ] the **seven named stage-1 gates** pass, with **CONSERVATION at zero tolerance, no thresholds**
- [ ] every transformation carries its mandatory `before`, so revert is total rather than best-effort
- [ ] `fa migrate verify` **refuses on a moved corpus pin**
- [ ] per-form counts reported; **nothing dropped silently**
- [ ] the pair can be **abandoned** and the markdown still authored (proven, not assumed)

### Phase 7 — Cutover
**Exit criteria**
- [ ] invariant 15 green over the **whole** corpus, per-artifact per-field
- [ ] the 62 hooks, 5 bash helpers and 7 hand-maintained indexes are **retired**, not integrated
- [ ] `.factory/**` markdown is **generated** and its writers all call `fa`
- [ ] the production-grade bar (spine §6) is met **with numbers**, not adjectives

---

## 11. What L7 changes in the other layers

| layer | change |
|---|---|
| L3–L4 | **exit 6 (`CONTINUATION`) joins the closed exit vocabulary.** Every op that can exceed a unit budget declares it. |
| L5 | `evidence`/`attestation` gain non-nullable `evidence_basis` + conditional `validate_by` (L7-F). Gate registration gains a **witness** requirement (L7-G). Gate reports must omit skipped checks from the clean list. |
| L6 | the scheduler is a **caller-driven loop**, not a daemon: `fa` never runs work on its own clock. |
| migration | reshaped into a **cursor-driven step function** with periodic GC — the biggest un-designed consequence of V-K, now designed. |

---

## 12. OPEN QUESTIONS

1. **Exit 6 vs a `status` field.** I chose a distinct exit code so "not finished" cannot be read as
   "finished". The cost is a sixth code every caller must handle. *Is the closed vocabulary worth
   widening here, or should incompleteness ride on exit 0 with a mandatory field?* My read: the
   distinct code, because the failure mode of the alternative is a silent partial migration.
2. **Cursor opacity.** An opaque cursor cannot be hand-edited (good) but cannot be inspected when a
   migration stalls (bad). *Do we ship a `fa cursor explain`, and does that re-introduce a leak?*
3. **The 200-artifact unit budget is derived from a READ workload.** Every latency in
   `FA-V1-PIVOT-MEASUREMENT.md` is a read. *Re-measure once the write path exists; do not carry 200
   forward as a constant.*
4. **Who owns the witness corpus?** L7-G needs a known-bad input per gate. *Is that a fixture tree in
   the repo, or rows in the store? A fixture tree is a second home for data; rows in the store make
   the witness itself subject to migration.*
5. **`fa perimeter explain` non-leakage** — is "describe your own permissions" provably a pure function
   of the role, given the role's permissions are registry rows that mention types?
6. **MCP manifest shape leakage** — safe only if no op enumerates manifests. *Confirm nothing does.*
7. **Batching vs chunking.** L7-D chunks one op; V-K also asks for **batchable** ops (many small writes
   in one call). *Is a batch one transaction (atomic, but a bigger blast radius on refusal) or N
   transactions (partial success, needing a per-item result array)?* My read: one transaction, with a
   per-item result array on refusal, because invariant 18's audit is per-write either way.
8. **Does CI need its own idempotence-key discipline?** A re-run CI job retries with a *new* key by
   default, which would double-apply. *Derive the key from the CI run id?*
9. **Nothing in any register tests L6.** The prism validation register found 11 of 21 prevented but
   touches no engine behaviour. *L6 remains unvalidated by any independent source* — this is carried
   forward from L5–L6 unresolved, and L7's scheduler decision does not fix it.
