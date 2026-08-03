> **Type:** Stage 3 output — one persona, one point of view. **Status:** first pass.
> ⚠ `evidence_basis: spec-derived, unvalidated.` `validate_by:` Phase 6, first rivetry migration.
> ⚠ **The emotion curve (Stage 3 step 5) is deliberately OMITTED with a reason** rather than faked: an
> agent has no trust curve, and inventing one would anthropomorphise past the boundary the runbook's
> own Step-3d warns about. Replaced by a **failure-cost curve** — where a misstep is cheap vs
> catastrophic — which is the property the emotion curve exists to surface and which *does* transfer.

# Journey — SYS-CC, the primary harness

## 1. Persona brief

See `personas/PERSONA-ROSTER.md` § SYS-CC. In one line: an LLM harness that holds a large op
vocabulary comfortably, retries tool calls, cannot block, and cannot be trusted to parse prose.

## 2. The end-to-end journey

### S2 — Ingest
> **Expectations entering this stage:** the corpus is a mess and I am the thing that reads a mess. I
> expect `datum` to hand me work, not to ask me to guess at its internals.

#### WF-010 · WF-011 — shadow a corpus, and be told what was skipped
- **Intent:** get the corpus into rows so I can reason about it as data.
- **Op:** `datum import <corpus>`
- **Agentic touchpoint:** none — this is deterministic. **A1** n/a. **A2** the import report IS the
  work-shown: per-form counts, skipped counts, collisions, ledger splits. **A3** n/a (no impactful
  action). **A4** a type directory that matched nothing is a finding, not a silence.
- **Decisions/branches:** none for me. This is the one stage where `datum` needs nothing from me.
- **Failure cost:** ⚠ **catastrophic-but-silent** before this session — 80 VPs vanished with no error,
  and 171,284 characters were eaten by a comment stripper. Now **loud**: WF-011's census is the control.
- **Handoffs:** to WF-014 for anything untyped.

#### WF-014 — classify what no rule can type *(⬜ unbuilt — this is the V-J loop)*
- **Intent:** type the 1,132 files carrying no frontmatter.
- **Op:** `datum next --kind classify --limit 20` → I interpret → `datum record classify --cursor <c> …`
- **Agentic touchpoint:** ⭐ **this is the one place `datum` genuinely needs an LLM.** **A1** `datum` states
  what it could not decide and why. **A2** I must supply evidence and confidence, not just a verdict —
  and it is stored as a transformation row with its `before`. **A3** my classification is a *proposal*
  through the same ops and the same ladder; it is not privileged. **A4** if I cannot decide, I say so
  and the unit stays open — I must never guess to clear a queue.
- **Decisions/branches:** classify · decline · propose a new type (exit 4).
- **Failure cost:** **high and delayed.** A wrong classification is recorded as data and *replayed*
  thereafter, so it becomes durable. This is exactly why interpretation is captured as data with its
  evidence rather than applied as a side effect.
- **Handoffs:** to WF-054 (replay), which makes my decision deterministic on re-run.

### S3 — Author
> **Expectations:** every write either succeeds or tells me precisely why not. I should never have to
> guess whether I corrupted the record.

#### WF-021 — set a field
- **Intent:** change one value on one artifact.
- **Op:** `datum bc set-field --key BC-5.39.009 --field lifecycle_status --value active --idem <key>`
- **Agentic touchpoint:** n/a — I am the caller, not an interpreter here.
- **Decisions/branches:** the 14-step ladder decides; I do not.
- **Failure cost:** **low, by design.** Measured at **1.0× pivot cost** (57 µs vs 58 µs), so the
  dominant op is also the cheapest — and every refusal is recoverable from its `next_action`.
- **Handoffs:** WF-024 on any refusal.

#### WF-024 — be refused, and know what to do next ⭐
- **Intent:** recover without a retry-and-guess loop.
- **Op:** any. The refusal is the deliverable.
- **Agentic touchpoint:** ⭐ **the highest-value beat in this journey**, because it is where an agent
  either recovers or thrashes. **A1** the payload states the limit that was hit. **A2** `ladder_step`
  + `rule` name *which* check refused me and *which* registry rule governs it — not a message I must
  interpret. **A3** exit 4 is approve/reject/refine; exit 5 hands me the op stream back as the retry
  payload. **A4** `next_action` is present on **every** refusal, including exit 3, where it is a
  **constant** string that discloses nothing.
- **Decisions/branches:** exit 1 → fix payload, retry. exit 2 → **stop, tell the human.** exit 3 →
  stop, do not probe. exit 4 → resubmit after the schema lands. exit 5 → re-read, rebase, retry with
  the *same* key. exit 6 → follow `next`.
- **Failure cost:** ⚠ **this is where AP-1 (the Confused Retrier) is born.** Every mitigation —
  machine-only stdout, never collapsing 1 and 2, `next_action` — exists at this beat.
- **Handoffs:** exit 2 hands off to HUM-OP; that is the only handoff in this journey that leaves the
  machine.

### S6 — Migrate
> **Expectations:** I cannot block, so a 6,537-file job must be thousands of small calls, and I must
> be able to die and resume.

#### WF-050 — migrate one cell in resumable chunks ⭐
- **Intent:** move a `(project,type)` cell without ever holding a long call.
- **Op:** `datum migrate step --project rivetry --cohort B --limit 200 [--cursor …]`
- **Agentic touchpoint:** **A1** `done`/`remaining` on every response, so I can tell stall from slow.
  **A2** `next` is the *literal* next invocation — I do not reconstruct pagination, which is precisely
  the mechanical detail I get subtly wrong. **A3** n/a. **A4** exit 6 is not an error; conflating it
  with success is the failure this code exists to prevent.
- **Decisions/branches:** exit 6 → call `next`. `gc_due` → collect first (**refused otherwise**).
  exit 5 → another writer holds the cell.
- **Failure cost:** ⚠⚠ **the highest in the whole journey.** Three named ways to lose here, all
  designed against: reading exit 6 as done (**exit 6 is a distinct code for this reason**), retrying
  without a key (**idempotence key required**), and never collecting (**`gc_due` blocks** — measured
  306.6× journal amplification).
- **Handoffs:** ⚠ **G-7 — if I simply stop, nothing notices.** `datum` cannot distinguish a cell I
  abandoned from one nobody has started since the last cursor. This is the one beat in this journey
  with **no control at all**, and this walk is what surfaced it.

## 3. Failure-cost curve *(replacing the emotion curve, with the reason stated)*

| stage | S2 import | S2 classify | S3 set | S3 refused | S6 migrate |
|---|---|---|---|---|---|
| cost of a misstep | **was catastrophic-silent → now loud** | high + **durable** (replayed) | low | low **if** the payload is machine-readable | **highest** |
| is it controlled? | ✅ WF-011 census | ⚠ partly — replay yes, wrong-classification no | ✅ | ✅ | ⚠ **G-7 uncontrolled** |

**The two peaks are S2-classify and S6-migrate**, and both peak for the same reason: they are the beats
where a mistake becomes **durable** rather than immediately visible. Everything else fails fast.

## 4. Gaps (every one routed — Stage 3 step 7)

| gap | surfaced at | owner / route |
|---|---|---|
| WF-014 unbuilt — the V-J loop has no ops | S2 classify | L7 §1; blocks typing 1,132 files |
| a wrong classification is durable once replayed | S2 classify | needs a **re-open** path: `datum reclassify` must exist, or a recorded decision is permanent. **NEW → G-8** |
| **G-7** abandoned `CONTINUATION` is undetectable | S6 migrate | L7 §3; `doctor` staleness finding |
| exit 2 is the only human handoff and is unrouted | S3 refused | who receives it, and how? **NEW → G-9** |

⭐ **Two further new gaps (G-8, G-9) from this single journey walk** — bringing this run's novel finding
count to six. Both are of the same kind: a recorded decision or a raised error with **no route back
out**. Added to `WORKFLOW-INVENTORY.md` §7.
