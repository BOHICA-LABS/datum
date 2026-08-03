---
title: STORYBOARD-METHOD-ASSESSMENT — what the persona-storyboard process contributes to fa, and what fa should retire
date: 2026-08-02
source_read: ~/Dev/multi-repo/.factory-project/storyboard/PERSONA-STORYBOARD-PROCESS.md (1,951 lines, read in full)
purpose: decide which of the runbook's methods transfer into our tooling, which are superseded by fa v1, and what it contributes as a validation register
status: ASSESSMENT — no method adopted yet; 7 transfer candidates named, 3 of them load-bearing on L7
---

# The persona-storyboard process, assessed against `fa` v1

## 0. What was read, and what else was measured

`~/Dev/multi-repo/.factory-project/storyboard/PERSONA-STORYBOARD-PROCESS.md` — 1,951 lines, read in
full. It is a **CLIP-mounted copy**; the source of truth is authored in rivetry
(`.factory/storyboard/PERSONA-STORYBOARD-PROCESS.md` @ `38a5c10`), with a **deferred**
`vsdd-factory:persona-storyboard` engine-port noted in its own header. So it is already a *third* copy
of one process (rivetry source → CLIP mount → intended shared skill), which is itself the pattern
this assessment is about.

Measured directly for this assessment (not relayed):

| | |
|---|---|
| process doc | **1,951 lines** · **18** dated `Fix-burst NNN` criterion blocks · **93** `- [ ]` acceptance-criteria items |
| `tools/records-lint.sh` | **5,096 lines** of bash · **24** distinct check IDs |
| doc's own declared check list | **19** (`L1 L2 L3 L4 L5 L6 L7 L8 L8b L8c L8d L9 L10 L11 L11b L12 L13 L14 L15`) |
| **drift, measured** | **5 checks are in the tool and absent from the doc's list: `L0` `L16` `L18` `L20`, plus `L19`** which the doc describes as *"the check being added … will enforce"* — while it is **already implemented**. `L0`, `L16`, `L18`, `L20` appear **nowhere** in the doc. `L17` exists in neither (ID-sequence gap). |
| explicit recurrence counting in the doc | `first occurrence` ×4 · `second` ×5 · `third` ×4 · `fourth` ×4 · `sixth` ×2 · `4th recurrence` ×1 |
| storyboard corpus | 2 versions (`v0.1.0-target-state`, `v0.1.0-email-notifications`); 6 frames; 44 files under `personas/` |

⚠ **The measured drift above is the assessment in miniature.** The tool that exists to mechanically
kill hand-maintained drift has itself drifted from the hand-maintained list that documents it. That is
**instance six** of this repo's own "a hand-maintained vocabulary drifts from another hand-maintained
vocabulary" class (five prior), found in a different corpus, in the enforcement layer.

---

## 1. The headline: this corpus's greatest contribution is a DATASET, not a method

The 18 fix-burst blocks are an **independent, adversarially-produced, dated register of ~15
recurrences of exactly the defect classes `fa` v1 claims to make unrepresentable** — produced by a
different team on a different product with no knowledge of this spike.

That makes it the **third validation register**, after the 21-finding prism session register
(`FA-V1-VALIDATION-PRISM-SESSION.md`) and the ~40-defect factory review — and it is the **strongest
of the three**, because each entry carries three things the other registers lack: a **recurrence
ordinal**, the **fix that failed**, and **the sweep population that fix declared**.

### The lineages, mapped to `fa` mechanisms

| Storyboard lineage (as the corpus itself numbers it) | Recurrences | `fa` v1 mechanism |
|---|---|---|
| A normative mechanic is amended in one artifact and not propagated to the N artifacts that **restate** it. `ADV-S3P1-002 → S3P7-001 → S3P8-001/-004 → S3P10-001/-002 → S3P12-002/-003 → S3P13-004` | **6**, each explicitly numbered in-doc | **Invariant 17** — no stored value derivable from another stored value. Every "live mirror" is a *projection*, so there is no second home to go stale. |
| Version/line-count **pin staleness**. `ADV-S3P28-003 → S3P29-006 → S3P32-002 → S3P33-001 → S3P37-005 → S3P38-003 ("4th recurrence") → S3P39-003` | **7** | **Invariant 23** (identity assigned by the store, never appearing in artifact content) + counts as projections. A line count transcribed into prose **is** the SHA-transcription class. |
| **TWIN blocks** — content "repeated for traceability" diverging from its twin. fix-burst 74: *5 live twins carried a refuted claim for a full pass.* | 1 event, 5 carriers | **Invariant 17.** A twin is a declared second home for one fact. |
| **Storyboard-tier live mirrors** froze at the FB69/70 state across **FIVE normative cycles** (`v2.19→v2.25`, `r5→r12`) *"while every individual normative fix was verified landed."* | 1 event, 5 cycles | This is `fa shadow`'s **658 findings** exactly: derived documents drifting from the record while each local edit was individually correct. |
| **Lexical-variant sweeps** — a sweep whose recorded pattern *cannot match a form of its own target class*. fix-burst 68 → 73 → 84(5) → 111 UL4 | **4** | **This is instance NINE's class.** `reVPFile` case-sensitivity is the same defect: a matcher that cannot match a legal spelling of its own target, failing silently. Same class, different corpus, independently rediscovered. |
| A **hand-maintained allow-list** (`_AL4_BLOG_ALLOWLIST`), which the doc honestly self-declares as *"the only ongoing manual maintenance obligation introduced by this check."* | 1, self-declared | **Read the vocabulary FROM the registry.** This repo's 5-instance class; the doc names its own exposure. |
| A criterion that **self-spawned the defect it existed to kill**: fix-burst 73's REVISION-ONLY PIN criterion carried a false live scalar (`design r9 (2543L)`; the real count was `2514L`). | 1 | Counts are projections. A rule *stated in prose* that contains a live scalar is the defect it prohibits. |

**One number worth carrying forward:** the propagation class was still recurring at pass **S3-70**,
after **18** hand-widened criteria and **24** mechanical checks in **5,096 lines** of bash.

### The conclusion that follows, and it is the load-bearing one

This is the most rigorous **markdown-native** governance system I have seen, and it is simultaneously
the **best available evidence that markdown-native governance does not converge**. Each recurrence was
answered by widening a hand-maintained sweep population by one more carrier surface — the fix was
always *"remember to also edit N+1 places"*, never *"stop having N places."*

⚠ **So the primary recommendation is inverted from what the request implies:** most of this corpus's
**enforcement machinery should not be ported into our tooling — it should be RETIRED BY it.** Nearly
every one of the 24 checks is a detector for a drift that a single-home store makes unrepresentable.
That is §1 of the spine (*eliminate rather than detect*) with an independent 15-recurrence proof
attached, and it is this repo's own **measure-the-alternatives-to-the-lever** rule applied: the cheap
alternative to a 5,096-line linter is not a better linter.

**Stated fairly:** this is not a criticism of the work. The corpus was operating without a store, and
given that constraint the discipline is exceptional and its self-honesty (naming its own allow-list
burden, striking its own false scalar in place) is better than most of what `fa`'s own corpora show.

---

## 2. What genuinely TRANSFERS — 7 candidates, 3 of them load-bearing

These are things the runbook has that `fa`'s ~6,300 lines of design **do not**, judged against the
spine and the four layer docs.

### ⭐ T-1 — Three-tier evidence honesty, with `evidence_basis` + `validate_by` as a required pair

**LOAD-BEARING. Goes into L5, and it strictly improves V-K consequence #1.**

The runbook independently invented `fa`'s caller-asserted-vs-verified distinction and pushed it
**one tier further**:

| Tier | Runbook instance | Typing discipline |
|---|---|---|
| **authoritative** | zero-orphan coverage matrix, evidence manifest | mechanical fact-check |
| **advisory, human-review-pending** | AI heuristic evaluation, cognitive walkthrough | a **mandatory verbatim honesty header**; *"not authoritative per NN/g/ISO/IxDF"* |
| **prepared, unvalidated** | usability-test plan | `evidence_basis: prepared, unvalidated` **+ a `validate_by:` trigger** |

`fa`'s invariant 22 is **binary** (evidence exists iff `fa` produced it); V-K adds *caller-asserted*.
The runbook's model is **richer in the exact place V-K is thinnest**, and it supplies the piece `fa`
lacks: **an unvalidated claim must carry an expiry/validation trigger.** L5–L6 already made this move
once — it abolished `gate_status: deferred` and replaced it with deferral rows carrying **an owner and
an expiry**. The runbook applies the identical discipline to **evidence** rather than to deferrals.

**Recommendation:** `attestation`/`evidence` rows get a non-nullable `evidence_basis` enum
(`executed | caller-asserted | advisory-unreviewed | prepared-unvalidated`) and a **non-nullable
`validate_by`** whenever the basis is not `executed`. An advisory row that cannot name its
validation trigger is refused at write time. This closes V-I's original defect shape (an unverifiable
claim treated as a gate) at the *schema* level rather than by convention.

### ⭐ T-2 — ADD-CHECK-FIRST: a new gate must be demonstrated FAILING on a known-bad fixture

**LOAD-BEARING. Becomes a hard rule for every `fa` gate.**

Several checks are marked *"ADD-CHECK-FIRST fires on N pre-fix violations"* — the check is authored
and **shown to fire on the known bad state before the fix lands**. `L11b` is the cleanest form:
*"PASSES on r26 today; WOULD HAVE FIRED on FB92 r22 omission."*

This is **"CHECK YOUR FIX'S PREDICTION, don't tune"** mechanized, and it is a **Red Gate for gates** —
the factory already applies Red-Gate discipline to code (`todo!()` stubs must fail every test first)
but **not to its own gates**. `fa` has the adjacent vacuity guard (a gate must not pass on an empty
set) but nothing that requires a gate to have been *observed failing*.

**Recommendation:** every gate in the L5 registry carries a **`witness` fixture** — a stored known-bad
input the gate provably rejects — and `fa gate exec` refuses to register a gate with no witness. This
directly answers the register's three "green check that never ran" findings *and* the two prism
findings, with one rule, at write time.

### ⭐ T-3 — State-set enumeration as a completeness gate → every op × every exit code

**LOAD-BEARING, and it lands straight in task 2 (L7).**

Stage 6's discipline: *enumerate the full state set in writing **before** building, then render one
file per state — **including failure/edge/empty**, not only the happy path*, and close every path with
a **resolution state** so nothing dead-ends. Stage 7 then requires **deterministic** evidence per
state (pinned browser, animations disabled, mocked timestamps, network-idle wait) and **explicitly
rejects single-resolution evidence** as an anti-pattern.

Translated to a CLI/MCP tool, this is the L7 completeness gate `fa` needs and does not have:

> **For every one of the ~800 generated ops, enumerate and prove reachable every exit code —
> `0` success · `1` gate failed · `2` `fa` failed · `3` `DENIED-ASYMMETRY` · `4` `propose` — with a
> golden-file capture of the exact structured output for each, captured deterministically.**

`fa`'s design already has the exit-code vocabulary and the standing rule *never collapse exit 1 and
exit 2*. What it has no gate for is **coverage of that vocabulary**. Stage 6's "name the states, then
render each one, then prove each renders identically on re-run" is exactly the missing gate — and
Stage 7's determinism checklist is the golden-file discipline that makes it hold.

Also transfers: the **content-extreme state** (longest label, densest table). For `fa` that is the
**1.57 MB body** and the 214,554-line table already on record — an L7 op surface must have a rendered,
captured case at that extreme, not only at typical size.

### T-4 — The AGENTIC-UX-RUBRIC (A1–A4) as `fa`'s agent-facing error-design rubric

V-J/V-K say the consumer is an agent and that L7 needs *"error messages that are instructions to an
agent."* That is currently a sentence, not a rubric. A1–A4 is a ready-made one, and the mapping is
close to exact:

| | rubric dimension | `fa` L7 obligation |
|---|---|---|
| **A1** | trust calibration — state capabilities, performance, **limits/uncertainty** | every op declares what it does **not** guarantee; `caller-asserted` rows surface as such in every read (T-1) |
| **A2** | explainability, *"show your work"*, progressive access, verifiable references | a refusal cites **which of the 14 ladder steps** rejected it and the registry rule that governs it — not a bare error |
| **A3** | human-in-the-loop before impactful action — approve/reject/**refine** | `fa propose field` (exit 4) **is** A3; so is refusing conflicts rather than merging (invariant 21) |
| **A4** | error / uncertainty / **refusal** handling with recovery paths | exit 3 `DENIED-ASYMMETRY` is a refusal state; A4 demands it come with a **recovery path**, which the current design does not specify |

**A4 exposes a real gap:** `DENIED-ASYMMETRY` currently tells an agent *no* and — correctly — must
not disclose whether the artifact exists (a refusal that distinguishes forbidden from absent is an
oracle). A4's requirement is that a refusal still offer a **legal next action**. Reconciling
"disclose nothing" with "offer a recovery path" is an unsolved L7 design problem this rubric surfaces.

### T-5 — Status-glyph lifecycle: per-cell coverage state, monotonic, with regression as a real event

A closed 7-value enum on a **projection cell** (`—` n/a · `⬜` not started · `✏️` sketched · `🎨`
hi-fi · `🔍` validated · `📸` evidenced · `✅` promoted), advancing **in that order only**, where a
regression *"signals a real rebuild, not a typo, and should carry its own dated note."*

`fa` has `derivation_stage` (shadow→proven→retired) and the migration ladder
(shadow→dual-write→authoritative→retired) — both **per (project, type)**. It has **no per-cell
coverage lifecycle**, so a projection reports *values* but not *how far each cell got*. L5–L6 already
uses monotonicity for convergence (`clean_streak = 0` until a regression is dispositioned); this is
the same idea applied to coverage.

**Recommendation:** adopt as a declared enum with a tested legal-transition table (rule ORDER is a
correctness property here too — the transition order is exactly the kind of thing that must be
tested, not asserted).

### T-6 — The coverage cube: N-dimensional completeness as one generated view

`persona × workflow × state` (breakpoint as an optional 4th axis), **generated** by pivoting frame
frontmatter + the evidence manifest, *"never hand-maintained divergently."* Its purpose: make *"every
X × every Y is covered"* **provable at a glance rather than narrated in prose.**

`fa` has projections and invariant 19 (every aggregate declares a scope predicate). What it lacks is
the **completeness cube as a first-class query shape** — today completeness is N separate index
documents. The axes are already in the store. Honesty note the runbook itself supplies and I would
keep: it flags the cube as *"an emerging view, not a codified standard"* (2-D is a clean RTM
extension; 3-D/4-D is its own synthesis).

### T-7 — Deliberate-non-scope as a TYPED field, so absence reads as a decision

Two required fields in the frame template: *"What this frame deliberately does NOT do"* and *"which
personas this frame deliberately does NOT depict"* — plus the standing rule that a gap is never a
blank cell (`⛔ NO SCREEN` **with a one-line reason**, never silence) and that a skipped stage is
logged with its rationale.

This is **the 41-retired-stories result in artifact form.** That result says a derived artifact needs
a **declared scope predicate** or derivation silently changes the document's meaning — and `fa` is
already committed to a **field** predicate (never a path prefix, which D-C forbids). T-7 is the same
insight one level up: **the exclusion itself must be a stored, typed value carrying a reason**, so
that "not present" is queryably distinct from "not decided." Directly serves the open item about the
41 legacy stories in `stories/v1.0-legacy/`.

---

## 3. What does NOT transfer

| | Why |
|---|---|
| the 24-check `records-lint.sh` (5,096 lines) | **Retire, don't port.** Each check detects a drift a single-home store makes unrepresentable (§1). Porting it would import the anti-pattern. |
| the 18 hand-widened sweep-population criteria | These **are** the defect being documented. `fa`'s answer is invariant 17, not criterion 19. |
| breakpoint matrices · DTCG tokens · a11y annotation layers · Nielsen heuristic eval · WCAG reflow | UI-specific; `fa` has no UI. (The *determinism* discipline behind Stage 7 does transfer — see T-3.) |
| human personas, Persona Spectrum, anti-personas, emotion curves, service blueprints | Presuppose human users. See §4 — `fa`'s cast is agents, and the runbook's own agent-persona class is its weakest-grounded. |
| Stages 4 and 5 (design-language exploration, fat-marker divergence) | No analog for a generated op surface: the ~800 op names are **derived from the registry**, so there is no design space to diverge over. |

---

## 4. Note for task 6 — running the process against our tooling

Recorded here because it is the main hazard of the run the user has asked for, and it is a
consequence of a decision already settled.

**Under V-K, `fa`'s consumer is an LLM harness, not a human.** So Stage 1's cast is almost entirely
Step 3d **system/agent personas** — and the runbook explicitly flags that exact class as its
weakest-grounded: *"no authority comparable to the Persona Spectrum or the NN/g anti-persona template
exists yet for this class."* Running Stage 1 as written would produce the runbook's least-supported
artifact as our **primary** one. That must be typed honestly on the way in, not discovered later.

Stage-by-stage applicability, decided in advance:

| Stage | Applies to `fa`? | Form it takes |
|---|---|---|
| 1 Personas | **partly** | agent personas (Claude Code, Codex, CI) + **anti-personas** are unusually apt: a confused-agent retry storm, a role-token forger, an agent that fabricates evidence. Anti-personas trace to abuse vectors and are **exempt from the orphan check** — matches `fa`'s wall/asymmetry model. |
| 2 Workflow inventory | **yes, strongest fit** | the op × workflow inventory with coverage matrices, **FMEA on the migration path**, and **state machines incl. error/recovery states** — feeds L7's chunked/resumable/idempotent design directly |
| 3 Journeys | **yes, reframed** | agent task traces: the migration as *thousands of round trips*, which is precisely V-K's un-designed consequence |
| 4 Design language | **no** | ops are generated from the registry |
| 5 Divergence | **no** | ditto |
| 6 Hi-fi frames | **yes, as T-3** | op × exit-code state coverage with golden-file captures |
| 6.5 Design validation | **yes, reframed** | heuristic evaluation of the **tool-call surface** against A1–A4 (T-4), typed advisory per T-1 |
| 7 Evidence | **yes, as discipline** | determinism: pinned versions, mocked timestamps, byte-identical re-runs. `fa` already holds this bar (no network, no `dolt` binary, 124 tests in 7 s). |
| 8 Traceback | **yes** | route every gap to an owner; **zero unrouted gaps** is a good closing gate for our own design docs |

**One method to import at the top of the run, from Stage 2 Step 6:** the
**silently-missed-capability audit** — *re-diff the coverage matrix against the **current, live**
capability list every refresh; never trust that the matrix "still ends where it always ended."* The
corpus caught its own matrix silently stopping at `CAP-022` while `CAP-023` already had full coverage.
That is the same shape as the **stale-18,418-baseline** correction on record here, and the same shape
as the **+5 prism drift measured at the start of this session**. It should gate every projection
`fa` emits, and it is nearly free.

---

## 5. Recommendation

1. **Adopt T-1, T-2, T-3 now** — they are load-bearing, they land in L5/L7 which are being designed
   in this session anyway, and each closes a gap already on record.
2. **Adopt T-5, T-6, T-7 as declared schema additions** — cheap, and each has a named defect behind it.
3. **Adopt T-4 as L7's error-design rubric**, and record A4's refusal-vs-recovery tension as an open
   L7 question rather than papering it over.
4. **Do not port the enforcement machinery.** Record the 15-recurrence register as the **third
   validation register** and cite it where the design claims a class becomes unrepresentable.
5. **Report the measured doc/tool drift (19 vs 24 checks) to the multi-repo owner.** It is a real,
   current defect in that corpus. ⚠ Per this repo's standing rule the corpora are **read-only** —
   `~/Dev/multi-repo` is not one of the three declared reference corpora, and nothing in it was
   modified for this assessment. Fixing it is that workstream's call, not ours (V-E's logic).
