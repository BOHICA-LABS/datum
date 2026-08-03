> **Type:** Stage 1 output, canonical roster. **Status:** first pass.
> ⚠ `evidence_basis: proto-persona, spec/decision-derived, UNVALIDATED.`
> `validate_by:` first real agent-driven migration run against rivetry (Phase 6).
> ⚠ Personas SYS-* are the runbook's Step-3d **system/agent** class, which it types as *"a design
> spec, not a research-grounded model."* Honour that: these are specifications of what the caller must
> be able to do, not observations of what any caller does.

# Persona roster — `fa`

## Gate 1 of 2 — ecosystem / RACI pass (the runbook's precondition to the orphan check)

Every node annotated. No unannotated node — that is the gate.

| node | layer | annotation |
|---|---|---|
| **Claude Code harness** | primary | `persona-covered` → SYS-CC |
| **Codex (or any other harness)** | primary | `persona-covered` → SYS-ALT (V-K requires harness portability) |
| **CI runner** | primary | `persona-covered` → SYS-CI (L7-L makes CI a third role, not a special case) |
| **the human operator** | primary | `persona-covered` → HUM-OP |
| **the sub-agent an orchestrator spawns** | secondary | `shared-persona` with SYS-CC — same role token, fresh context; the perimeter is per-role, not per-process |
| **Dolt storage engine (GMS, embedded)** | system | `system-component-only` — not an actor; it has no intent |
| **the markdown corpus (`.factory/**`)** | served | `system-component-only` — under V-A it becomes a *rendered view*, so it is an output, not an actor |
| **the three projects (vsdd-factory, prism, rivetry)** | served | `system-component-only` — tenants, not actors |
| **the LLM provider** | — | `deliberately-out-of-scope` — V-K: `fa` contains no LLM client, no keys, no provider calls. It is NOT in `fa`'s ecosystem at all, and that is the decision, not an omission |
| **a remote git host** | — | `deliberately-out-of-scope` for v1 — local-only, no remote (phase-2 plumbing) |
| **an adversary reviewer agent** | primary | `shared-persona` with SYS-CC, but see **AP-3**: its information asymmetry is a *perimeter*, so its restrictions are modelled as an anti-persona defence rather than a persona trait |

⚠ **RACI finding — an accountable role with no persona.** *Who is accountable for adjudicating a
`fa propose field` (exit 4) proposal?* The op files a proposal and writes nothing; L3–L4 names a
change-management path but **no persona owns the decision**. Under the runbook's own rule (*"an
accountable RACI 'A' role that never appears as a designed-for persona is a MISSING persona"*) this is
a real gap. Routed in `WORKFLOW-INVENTORY.md` §7 as **G-1**.

## Gate 2 of 2 — orphan check

Every actor named in the design corpus maps to exactly one persona. **PASS**, with the caveat that
Gate 1 above is what makes that meaningful (a green orphan check alone gives false confidence).

## The cast

### SYS-CC — the primary harness (Claude Code)
**Role:** authenticated caller holding a role token injected by the harness (a `PreToolUse`-style hook).
**Auth posture:** identity is **caller-asserted, never verified** — `fa` cannot distinguish agents
sharing a process and a uid (L7-K).
**JTBD:** *"When I am asked to change a factory artifact, I want to make exactly that change through a
typed op that either succeeds or tells me precisely why not, so I can proceed without ever guessing
whether I corrupted the record."*
Functional success: exit 0, or an exit code + `next_action` I can act on without a retry-and-guess loop.
Emotional success: n/a — **and stating that is the honest part.** An agent has no trust curve; the
runbook's emotion-curve step (Stage 3 step 5) does not transfer, and pretending otherwise would be
anthropomorphising past the stated boundary the runbook itself warns about.
**Scenario expectations:** ~800 ops is an *asset* (V-K) — it expects a large, discoverable, closed
vocabulary and a machine-readable refusal, not prose.
**Context:** MCP preferred, CLI as universal fallback; retries tool calls; **cannot block** on a
long call.
**Devices:** MCP (rich) / CLI (universal). Both must expose an identical op set (L7-A).
**Hard boundaries:** cannot approve; cannot manufacture evidence; cannot write raw SQL.
**Known failure modes:** retries without an idempotence key → double-apply (mitigated: `TOKEN-REQUIRED`);
mis-parses prose diagnostics (mitigated: stdout machine-only, L7-B); loops forever on exit 2
(mitigated: exit 1 vs 2 never collapsed); **stops mid-migration believing it finished** (mitigated:
exit 6, L7-D — this failure mode is why exit 6 exists).

### SYS-ALT — a non-Claude harness (Codex, or any other)
Identical op surface; exists as its own persona **only** to keep V-K's harness-portability requirement
falsifiable. **Its purpose is to fail loudly if any design decision assumes Claude Code.**
**Hard boundary:** MCP is the rich surface; the CLI must be sufficient alone.
**Known failure mode:** a design that quietly assumes a Claude-specific hook. `fa` has exactly one
harness-dependent assumption — role-token injection (L7-K) — and it is **declared**, which is what
makes it acceptable rather than hidden.

### SYS-CI — the non-interactive runner
**Role:** third role, own token, same ops, **cannot approve anything** (L7-L).
**JTBD:** *"When a change lands, I want to run every gate and produce machine evidence, so a human can
see convergence computed rather than claimed."*
**Hard boundaries:** no approval; no interactive prompt; `fa gate exec` is the same op with the same
evidence typing.
**Known failure mode:** ⚠ a re-run job retries with a **new** idempotence key by default and would
double-apply. Open (L7 Q8): derive the key from the CI run id. Routed as **G-2**.

### HUM-OP — the human operator
**Role:** the only actor who may approve, adjudicate a proposal, revoke a lease, or authorise a push.
**JTBD:** *"When agents have been working, I want to see what changed and what is still unproven,
without reading 6,000 lines, so I can decide what to approve."*
Functional success: a report that distinguishes *executed* from *asserted* evidence (L7-F).
**Scenario expectations:** trusts nothing that cannot name how it was verified. **This is the persona
the three-tier `evidence_basis` typing exists for.**
**Context:** reads renders and gate reports; drives approvals; **never edits the store directly** (V-A
makes markdown a view, so the human's authoring surface is `fa`, same as an agent's).
**Devices:** terminal; committed markdown as the offline review surface + backup.

## Persona-Spectrum pass (Stage 1 step 3b), honestly scoped

The runbook's Persona Spectrum covers permanent/temporary/situational **human ability** mismatches. For
SYS-* personas there is no ability axis; the transferable analogue is **capability degradation**, and it
attaches as a *dimension* of an existing persona — never a new persona.

| demand | permanent | temporary | situational |
|---|---|---|---|
| hold a large op vocabulary | a weaker model with a smaller context | context nearly exhausted mid-migration | a long tool-result truncated by the harness |
| follow a multi-step protocol | no MCP support (CLI only) | a transient store lock | a retry storm after a network blip |
| interpret a refusal | cannot parse JSON reliably | prose and machine output interleaved | a partially-written response |

**Design consequences this pass produced, all already adopted:** `next` returns the *literal* next
invocation (so pagination need not be reconstructed); stdout is machine-only; every refusal carries
`next_action`; and exit 6 makes truncation-as-completion impossible.

For **HUM-OP**, the real human spectrum does apply and is **deliberately out of scope for v1** with a
stated reason: `fa`'s human surface is a terminal and a markdown render, and no accessibility work is
planned for v1. Recorded so the absence reads as a decision (Stage 6 step 7's discipline) rather than
an oversight. Routed as **G-3**.
