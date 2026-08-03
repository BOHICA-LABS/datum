> **Type:** Stage 1 step 3c output. **A SEPARATE artifact from the designed-for roster, and EXEMPT
> from the Step-4 orphan check by construction** — an anti-persona deliberately maps to no designed-for
> workflow, and running it through the orphan check would both fail and pollute that check.
> Built around **behaviours and goals, never identities** (NN/g template).
> Anti-personas trace to the **abuse vectors** they are defended against, not to workflows.

# Anti-persona roster — `datum`

This is the stage of the runbook that transferred **best**. `datum`'s whole design is a set of perimeters,
so naming the adversaries it is built against is more natural here than for a UI. Every entry below is
grounded in a defence that already exists in the design — no speculative threats.

The runbook's trigger conditions all fire: `datum` touches **tenant isolation** (per-project stores),
**safety-load-bearing confirmations** (gate verdicts), **credentials** (role tokens), and **erasure**
(retired types, deleted markdown).

---

## AP-1 — The Confused Retrier
**Goal (the threat):** finish its task. It is not malicious; it is *stuck*.
**Motivations:** a tool call returned something it could not parse, or timed out.
**Actions:** replays the same mutating op tens of times, with variations, at speed.
**Tools:** the harness's own automatic retry.
**Needs (the absences that let the threat succeed):** ops that are not idempotent; a minted-on-its-behalf
retry token; error text that must be regexed; a code that does not distinguish "retry may help" from
"retry cannot help".
**Consequence if undefended:** duplicated appends, a lost update, or an infinite loop against exit 2.
**Defences in place:** caller-supplied idempotence keys with `TOKEN-REQUIRED` refusal (L7-E); `append`
is the only non-idempotent verb and it *requires* a token; `IDEMPOTENT-BY-KEY` returns
`OK (already exists)` only when every field matches, else `CONFLICT-DIVERGENT` — *"silently accepting a
divergent create is how a retry becomes a lost update"*; exit 1 vs 2 never collapsed.
**Status:** ⚠ **the single most likely real adversary**, because it needs no bad actor. This is the
anti-persona that justifies the idempotence work.

## AP-2 — The Plausible Fabricator
**Goal:** produce an answer that *looks* right. A confident wrong result is its success condition.
**Motivations:** it is rewarded for completing, not for being correct.
**Actions:** composes joins across 25 tables and reports the result as fact; asserts a gate passed;
transcribes a count into prose; claims a model identity it does not have.
**Needs:** a raw-SQL path; a way to write evidence; a gate that accepts a claim; an attestation field
that does not record *who says so*.
**Consequence:** the exact failure class this project exists to eliminate — *"plausible-but-wrong
answers with NO error."*
**Defences:** `datum gate exec` is the **sole** writer of the evidence table and no flag accepts evidence
bytes; `sql --read-only` is read-only and explicitly **not** a write hatch; `--unsafe-freeform` /
`sql --write` / an admin console are all **rejected by name**; counts are projections with no stored
copy; **invariant 23** keeps identity out of content; **L7-F** types every claim `caller-asserted` vs
`executed` so a claim can never be read as proof.
**Status:** fully defended in design. ⚠ The residue is stated honestly: `datum` **cannot verify** an
asserted model identity, only record it — which is why V-I's gate was retired rather than faked.

## AP-3 — The Wall Prober
**Goal:** learn what exists outside its perimeter.
**Motivations:** an adversary reviewer whose value depends on *not* having seen the spec has an
incentive gradient toward seeing it; a compromised or over-eager agent has the same behaviour.
**Actions:** issues ops against artifacts it may not read and **diffs the refusals**; asks "does X
exist?" by observing whether the error changes; enumerates its own permissions and infers the
complement.
**Needs:** a refusal that distinguishes *forbidden* from *absent*; per-role manifests it can compare;
a `perimeter explain` that mentions subjects; timing differences.
**Consequence:** the adversarial method's entire claim rests on information asymmetry. A leak does not
just expose data — **it silently invalidates every downstream convergence verdict**, which is worse,
because nothing reports it.
**Defences:** `DENIED-ASYMMETRY` (exit 3) is evaluated **FIRST in the ladder (V0)**, before the op
learns whether the artifact exists — *"a refusal that distinguishes forbidden from absent is an
oracle"*; the exit-3 `next_action` is **constant across all denials** (L7-I); MCP manifests are
capability-gated and no op enumerates manifests.
**Status:** ⚠ **two open gates**, both already recorded: `datum perimeter explain` must be **proven** a
pure function of the role (L7 Q5), and no op may enumerate manifests (L7 Q6). ⚠⚠ **Timing is
undefended and unmentioned anywhere in the design** — V0 runs first, so a denial should be *fast*, but
"fast" vs "fast because the artifact was not found" has not been analysed. **NEW FINDING → G-4.**

## AP-4 — The Cross-Tenant Leaker
**Goal:** read or write project B while acting for project A. Usually accidental.
**Actions:** omits `--project`; reuses a cursor across projects; runs an aggregate with no scope
predicate.
**Needs:** an *omittable* predicate; a shared store; a cursor that does not carry its project.
**Consequence:** one project's agents corrupting or reading another's — and V-F makes multi-tenancy a
v1 requirement, so this is not hypothetical.
**Defences:** **one store per project and no `project` column** — the predicate is discharged by
*store selection*, and *"an omittable predicate is the defect; a store handle cannot be omitted"*; an
unset project is `NO-PROJECT` (exit 2), **never an implicit pick**; invariant 19 refuses unscoped
aggregates.
**Status:** strongly defended, and the defence is *structural* rather than a check. ⚠ One open edge:
**a cursor must carry its project** and be refused against any other store, or AP-4 returns through
the chunking surface that L7 just introduced. **NEW FINDING → G-5.**

## AP-5 — The Silent Truncator
**Goal:** appear to have finished. This is the **only anti-persona that is a piece of code rather than
a caller**, and it is included because it is this repo's most-repeated adversary — **ten instances**.
**Actions:** a matcher skips input it cannot match; a comment stripper eats a value; a loop stops at a
budget and returns success; a sweep's pattern cannot match its own target class.
**Needs:** a filter with no census; a report that prints only successes; a completion signal that does
not distinguish "done" from "did what I could".
**Consequence:** measured, this session, from two instances in `datum`'s own code: **80 VPs → 0 rows** with
no error, and **171,284 characters** silently discarded by a comment stripper.
**Defences:** `MatchCensus` prints matched/skipped/per-case-form on every import; a type directory
holding markdown but matching nothing is a finding; **exit 6** makes truncation-as-completion
impossible; the ledger split asserts byte-exact reversibility *at ingest*; X1 conservation at zero
tolerance.
**Status:** ⚠ **the best-evidenced adversary in the entire corpus, and still not fully defended** —
`FA-V1-ADVERSARIAL-REVIEW.md` **F8** shows X1's denominator shares its numerator's enumerator, so it
cannot catch a *location* bug (prism's epics: enumerate 0, compare to 0, **pass**). Routed as F8.

---

## Coverage argument (necessary, not sufficient — the runbook is explicit that no completeness proof exists)

| `datum` surface handling something sensitive | anti-persona | or risk-accepted rationale |
|---|---|---|
| tenant isolation (per-project stores) | **AP-4** | — |
| gate verdicts / evidence | **AP-2** | — |
| information-asymmetry perimeter | **AP-3** | — |
| role tokens / identity | **AP-2**, **AP-3** | ⚠ `datum` cannot verify identity at all — accepted and declared (L7-K), not defended |
| retry / write duplication | **AP-1** | — |
| input completeness | **AP-5** | — |
| erasure (retired types, deleted markdown) | — | ⚠ **NO ANTI-PERSONA.** Cohort G retires markdown and `retired_types` deletes after verification. Nothing models an actor who deletes prematurely or whose "verify by count assertion" passes vacuously. **NEW FINDING → G-6.** |
| leases | **AP-1** (crash-then-retry) | partial — invariant 21 permits TTL/human revocation that writes no artifact |
