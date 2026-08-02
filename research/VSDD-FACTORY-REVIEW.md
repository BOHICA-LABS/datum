---
title: VSDD-FACTORY-REVIEW — how the factory is supposed to operate, and what `fa` must therefore provide
date: 2026-08-02
purpose: a full operational review of ~/Dev/vsdd-factory — phases, agents, artifacts, state, gates, modes — compiled into a feature list for `fa`
method: six parallel READ-ONLY reviews, each reading the skills/agents/workflows/hooks AND the live .factory corpus, every claim cited to file:line
status: IN PROGRESS — 2 of 6 areas landed
corpus_pin: vsdd-factory .factory @ 0aaba144 (read-only; 0 files modified)
---

# The factory, reviewed

Six areas, reviewed in parallel against both the *declared* machinery
(`plugins/vsdd-factory/{agents,skills,workflows,templates,config,hooks}`) and the *actual*
corpus (`.factory/**`, 3,145 files). The recurring shape of the findings is the one this spike
already knows: **the declaration and the mechanism disagree, and the corpus follows neither.**

Scale confirmed: 34 agent definitions + 10 orchestrator workflow references · 62 registered hooks ·
46 artifact-path-registry entries · 18 policies · 295 documents of `document_type:
adversarial-review` · 3 real cycles.

---

## AREA 1 — The agent roster, and the walls between agents

### What it is

34 agents in `plugins/vsdd-factory/agents/`. There is no `.claude/agents/` directory. Each carries a
`## Tool Access` section, a `## Context Discipline` block (`Load:` / `Do NOT load:`), and for eight
of them an **information asymmetry wall**.

Delegation is forced by design: the orchestrator is denied `write`/`edit`/`exec`
(`orchestrator.md:376-377`, "You NEVER write ANY files", `:101`) and must route every artifact write
through **state-manager**, every shell command for a shell-less reviewer through **github-ops**, and
every repo/CI action through **devops-engineer**. `FACTORY.md:496`: "Orchestrator is a scheduler,
not a doer."

### The walls (the load-bearing design idea)

`FACTORY.md:442-466` declares the walls and — importantly — concedes the mechanism problem itself:

> "**Soft instructions alone are insufficient for wall enforcement**… Walls must be structurally
> enforced through context exclusion."

| agent | cannot see | why |
|---|---|---|
| adversary | prior passes in `cycles/*/adversarial-reviews/`, implementation history | fresh eyes each pass (`adversary.md:21-24`) |
| holdout-evaluator | `specs/**`, `src/**` internals, prior reviews, test source | judge from OUTSIDE like a real user (`:21-34`) |
| pr-reviewer | all of `.factory/**` | must not "unconsciously trust the pipeline's prior review" (`:87-99`) |
| code-reviewer | adversary findings | cognitive diversity, no anchoring (`:118-127`) |
| security-reviewer | implementer notes; at wave scope, per-story reviews | independent security posture (`:156-175`) |
| formal-verifier | adversary findings | verify the spec surface uniformly, not where the adversary looked (`:207-217`) |
| spec-reviewer | implementation, red-gate logs (`:167-173`) | |
| accessibility-auditor | `specs/architecture/**` (`:75-78`) | |

Two agents explicitly have **no** wall, and say so: dtu-validator (`:123-126`) and session-reviewer
(`exclude: []`, `:62`).

Mechanically the walls are `context.exclude` blocks in `workflows/*.lobster`.

### What is broken

**The tool-profile source of truth does not exist.** Every `## Tool Access` section is prose. The
audit that would check it (`skills/agent-file-review/SKILL.md:15`, check 8) requires `openclaw.json`
at repo root; `find . -name "openclaw*"` returns nothing, and `FACTORY.md:402,439` also point at it.
**29 of 34 agents have no `tools:` frontmatter**, so they run with *all* tools — including the ones
whose prose says "Denied: exec".

**Ten agents cannot do their declared job with their declared profile.** The sharpest:

- **holdout-evaluator** is told to "Write to `.factory/holdout-scenarios/evaluations/`" (`:64`) with
  `tools: Bash, Read` and "Denied: `Write`, `Edit`, `Glob`, `Grep`" (`:94`) — and unlike
  session-reviewer, **no delegate is named**. It is also told to read a whole directory without Glob.
- **adversary** is told twice to write findings (`:100`, `:46`) while read-only. Patched at `:326`
  (return chat text, state-manager persists) but the write instructions were never removed — and
  **392 corpus files carry `producer: adversary`**.
- **pr-reviewer** is walled off from `.factory/**` and simultaneously told to read
  `.factory/specs/architecture/api-surface.md` (`:68`) and write
  `.factory/code-delivery/STORY-NNN/pr-review.md` (`:57,:124`). The `.lobster` exclude is
  `".factory/**"`, which would block both its input and its output.
- **spec-reviewer** writes into `specs/adversarial-reviews/` (`:162`) while forbidden to read it
  (`:192`) — and its multi-pass protocol (`:147`) requires re-reading its own prior findings.
- **product-owner / architect / story-writer / business-analyst** are each told to run
  `compute-input-hash <file> --update` while declaring "Denied: `exec`".

**Write authority is not actually exclusive to state-manager.** `FACTORY.md:486` says "All
`.factory/` commits come from state-manager", but **19 agents declare direct `.factory/` writes**.
Only *commits* are centralized; *writes* are not — and that distinction is never stated. Only
`stub-architect.md:171` gets the rule right ("Do NOT write to `.factory/` — state-manager owns
those paths").

**16+ declared write targets are unregistered**, and `artifact-path-registry.yaml` blocks any
`.factory/` path matching no entry: `holdout-scenarios/**`, `specs/adversarial-reviews/**`,
`cycles/**/hardening/**`, `ui-evidence/**`, `demo-evidence/**`, `dtu-clones/**`,
`phase-0-ingestion/**` (which *exists in the live corpus*), `planning/**`, all four spec-steward
outputs, `cost-summary.md`, `session-reviews/`, `prd-supplements/**`, `ux-spec/**`.

**No hook is identity-aware.** `hooks/factory-branch-guard.sh` gates on branch/worktree state, not
on who is writing; `hooks/check-factory-commit.sh:3` is "advisory only… Exit 0 always". So "only
state-manager commits" and "the adversary may not read adversarial-reviews/" are both unenforceable.

**Writes and commits are not attributed.** Dispatch identity *is* captured — 1,045 `agent.start`
events carry a `subagent` field (353 adversary, 251 state-manager, 166 product-owner) — but
`hook.block` (7,761 events) and `commit.made` (373) carry no agent field, and
`track-agent-start/src/lib.rs:19` explicitly *forbids* an `agent_id` field. The corpus shows the
consequence directly: `producer:` frontmatter holds **8 identities that are not agents at all**,
including `phase-1-4b-bcs-agent-4` (330 files) and two spellings of `codebase-analyzer`.

**Wall coverage is partial, and one wall is inverted.** `greenfield.lobster:871-878` dispatches
holdout-evaluator with **no `context:` block at all**, at exactly the wave gate `FACTORY.md:451`
claims to cover. And `greenfield.lobster:286` explicitly `include:`s
`.factory/specs/adversarial-reviews/**` for the Phase-1d adversary — handing it the prior passes
that `adversary.md:22` and the Phase-5 exclude both forbid. The same artifact class is spelled four
ways across workflows (`specs/adversarial-reviews/`, `cycles/**/adversarial-reviews/`,
`phase-f5-adversarial/`, `phase-5-adversarial/`); none appears in the path registry.

**Model diversity is mandated and unsatisfiable.** `FACTORY.md:403` — the adversary "**NEVER
Claude**"; `phase-4-holdout-evaluation.lobster:33` makes "different model family (GPT-5.4, not
Claude)" a **blocking gate criterion**. But every agent frontmatter pins a Claude model:
`adversary.md:5` `model: opus`, `holdout-evaluator.md:5` `model: opus`, `pr-reviewer.md:4`,
`spec-reviewer.md:4`, `code-reviewer.md:4` `model: sonnet`. The 23 `model_tier:` keys in `.lobster`
have no resolver.

Also: all 34 agent files point at `../../FACTORY.md`, which resolves to `plugins/FACTORY.md`; the
real file is `plugins/vsdd-factory/docs/FACTORY.md`. `VSDD.md` does not exist anywhere.

---

## AREA 2 — Quality gates, review loops, convergence

### What it is

Gates at four levels: per-story (Red Gate, adversary convergence, demo evidence, PR prerequisites),
wave (6 gates), phase (1d spec review, 4 holdout, 5 refinement, 6 hardening, 7 convergence), plus
18 policies and 62 registered hooks.

The **one genuinely computed gate** in the factory is per-story adversary convergence:
`crates/hook-plugins/validate-per-story-adversary-convergence/src/lib.rs:123-177`, with **6 Kani
proofs** at `:717-827`. Criterion: `passes_clean >= 3 AND last_classification == "NITPICK_ONLY"`.

The adversary works to **three declared perimeters** (per-story diff+spec+`bcs:` / wave
cross-story / phase-5 whole system), with out-of-scope findings pushed to `deferred_findings[]`
targeted at `wave-gate` or `phase-5` — a genuinely good design.

### What is broken

**The Kani-proved gate reads hand-written JSON.** `passes_clean` and `last_classification` are
plain fields the orchestrator writes; nothing recomputes them from the pass files. The proofs
guarantee the projection is sound, not that the inputs are true. Live example:
`S-13.01/adversary-convergence-state.json` asserts `passes_clean: 3` beside a
`bootstrap_annotation` recording `"fix_batches_pending": ["B3","B4"]`. And `lib.rs:215-233`
degrades open: any dispatch whose identity does not literally start with `wave-gate` skips the gate,
with `"unknown"` as the default.

**Novelty is self-reported, by an agent forbidden to read the comparison set.**
`Novelty = N/(N+D)` where both N and D come from the same adversary that produced the findings —
which "CANNOT access `.factory/cycles/*/adversarial-reviews/` from prior passes". Live:
`ADV-S5.03-P14.md:117-126` reports `Novelty score | 0.0 (0 / (0 + 0))` — division by zero — with
trajectory `14→15→5→8→4→0→6→6→0→1→1→0→0→0`, which violates the monotonicity rule three times, and
declares `CONVERGENCE_REACHED` anyway. The rule it violates (`adversarial-review/SKILL.md:170-177`)
says "Do NOT continue convergence passes until the regression is explained"; the hook implementing
it records a stderr warning and `exit 0` (`convergence-tracker.sh:117,171-176`).

**The convergence hooks skip 125 of 295 real reviews.** `convergence-tracker.sh:50-52` and
`validate-novelty-assessment.sh:51` both skip `*ADV-*.md` — and `ADV-<story>-P<NN>.md` is exactly
the naming the corpus adopted, including **both files that actually declare
`CONVERGENCE_REACHED` + `3_of_3`**. For the 170 that are checked, the min-3-passes rule is still
unreachable: `:147` globs `-name 'pass-*.md'`, which matches none of the real filenames
(`wave-2-ss-03-pass-13.md`, `s7.03-pass-17.md`, `e7-spec-pass-4.md`).

**`docs/CONVERGENCE.md:5`: "All criteria are ADVISORY."** That document also specifies
embedding-similarity dedup, per-finding confidence, hallucination fingerprinting, a power-law decay
fit and a Convergence Index — attributed to a plugin that does not exist;
`hooks/convergence-tracker.sh` is 187 lines of bash computing none of it. And
`convergence-tracking/SKILL.md:18` reads a `pass-*/review-report.md` layout absent from the corpus,
so its inputs resolve to nothing.

**Wave gates pass on the word "Gate".** `validate-wave-gate-completeness.sh:107-119` greps for the
literal token `Gate N`; a report reading `Gate 3: FAILED — 5 CRITICAL` satisfies it. Statuses are
never parsed. `validate-wave-gate-prerequisite.sh:138` accepts `gate_status: deferred` — no
rationale, owner or expiry — and the sibling hook's error message *recommends* it. Both are moot:
**there is no `.factory/wave-state.yaml`**, so the prerequisite hook returns
`exit 0  # project hasn't opted in` on every dispatch. The wave gate also has **two incompatible
definitions** (6 gates in `wave-gate/SKILL.md:52-127` vs a 7-step a–g loop in
`per-story-delivery.md:48-70`, the latter declaring itself canonical).

**Wave 15 is the worked example of assertion-as-evidence.**
`wave-15-gate-final-verdict.md` declares `verdict: CONVERGED`; grepping it for
`gate [0-9]|GATE_CHECK|holdout|demo evidence|dtu` returns **nothing**. Gates 2/4/5 have no record
of running. `.factory/holdout-evaluations/` contains **only `.gitkeep`** and there are no holdout
scenario files anywhere, so Gate 5's `mean ≥ 0.85` has never produced a number. The mutation gate
("exactly 80 — no rounding") was retired by "deferred per wave gate consensus" — and the
compensating controls existed *because* RED_RATIO was 0.0, i.e. tests passed vacuously against
stubs.

**Vocabularies have drifted badly.** 17 distinct severity tokens in `**Severity:**`
(`MEDIUM`/`MED`, `NIT`/`NITPICK`, `PROCESS_GAP`/`PROCESS-GAP`/`PROCESS`, and six spellings of
"observation"). **21 tokens in `verdict:`, a field whose declared domain is 2** — and 130 uses hold
a *severity* instead of a verdict. The single most common verdict, `NITPICK_ONLY` (88 uses, the
exact string the one computed gate keys on), **is not a legal value per the template**. 11 closure
tokens against 5 declared. `pr-reviewer.md` declares three different severity vocabularies in one
file, and a finding tagged `WARNING` has no route in `pr-review-triage`'s table.

**Findings have ~14 ID conventions and the format hook sees one.**
`validate-finding-format.sh:51` accepts only `^ADV-[A-Z0-9]+-P[0-9]+-[A-Z]+-[0-9]+$`. The dominant
family — `F-P2-001`, `F-001`, `F-S12.06-P1-003`, … — is **8,698 + 3,158 + 1,059 + …** occurrences
and is never inspected. `per-story-delivery.md:66` prescribes `STORY-NNN-FIX-001`, which
`validate-finding-format.sh:70-75` **blocks as legacy**.

**Stated finding counts are unchecked.** `grep -rn "findings_count" plugins/ crates/` → zero hits;
the field is not in the template. 210 of 295 reviews carry no count; of the 85 that do, 6 disagree
with the body — and the disagreement is representational (OBS findings as bullets, CRIT/HIGH as
headings), so no single parse recovers the finding set. The mandated per-pass
`ADV-P<N>-INDEX.md` was **never produced** for any of the 295 reviews.

**16 of 18 policies have `lint_hook: null`.** Only POLICY 9 and 10 have a mechanism. Policy
`severity` is capped at `HIGH|MEDIUM`, so a CRITICAL policy violation is inexpressible — while
mis-anchoring is declared to "ALWAYS block convergence". POLICY 15 mandates verbatim stdout as
evidence, which in practice produces self-attesting transcripts (`burst-log.md`: `$ grep -c … / 18
/ PASS`); POLICY 5 has recursed to **v1.3.6 — a six-level cure chain** trying to close that hole,
with `lint_hook: null`.

Most thresholds are ultimately defended by an "Iron Law" + "Red Flags" table at the top of each
gate skill. The pipeline's primary defense against `0.84 ≈ 0.85` is a table telling the agent not
to do that.

---

## AREA 3 — The pipeline: phases, gates, loops, human approvals

### What it is

`workflows/greenfield.lobster` is the reference path and says so (`:9`). Phase entry-point skills are
thin wrappers delegating to `workflows/phases/phase-N-*.lobster`.

**Bootstrap** → repo-initialization → factory-worktree-health (gate) → scaffold-claude-md →
state-initialization → **adaptive planning** (`planning.lobster`): environment-setup (gate: all 3
model families reachable) → artifact-detection classifying readiness **L0–L4** → market-intelligence
→ then either the L0 track (brainstorm → guided-brief → validate → approve) or the L1–L4 track
(validate existing brief/PRD/architecture → implementation-readiness) → start-pipeline.

That readiness routing is a genuinely good idea: the factory does not assume the human arrives with
a finished brief.

**Phase 0** (brownfield) — 6 steps A–F, each followed by a state-manager backup commit; the
convergence-deepening step gets an 8h budget; 7-criterion exit gate; human approval.

**Phase 1** — create-brief → domain-spec → PRD → architecture → PO↔Architect feasibility revision
(**max 3, then escalate**) → spec gate → adversarial spec review → DTU assessment (mandatory, always
writes) → gene-transfusion assessment → CI/CD setup (mandatory) → UI track (design system,
multi-variant design, heuristics) → **fresh-context consistency audit** → `phase-1-gate` with **21
criteria** → Phase 1d adversarial spec review (max 10) → Gemini spec review (max 10) → human
approval (24h, 11 artifacts).

**Multi-repo fork** — reads `deployment_topology` from ARCH-INDEX; if multi-service, human confirms,
devops creates per-service repos, and greenfield **STOPs and hands off** to `multi-repo.lobster`.

**Phase 2** — epics → stories → dependency graph → wave schedule → holdout scenarios → gate (6) →
adversarial story review (max 10, walls) → `phase-2-gate` with **27 criteria** → Gemini review →
human approval with 4 structured questions.

**Preflight** — dx-engineer 9 checks; DTU gate; CI/CD gate.

**Phase 3** — loop over waves; within a wave, parallel story groups run: stub-architect →
test-writer → implementer → demo → push → PR → AI PR review (wall: no `.factory/**`) → security
review (wall: no implementer notes) → PR-review convergence (max 10) → CI → dependency-merge check →
merge → cleanup. Then a **wave integration gate**: full test → wave adversarial review (max 10, 2
walls) → wave security review → holdout regression → wave demo → integration fix loop (max 10) → UI
gates → `wave-gate` (6 criteria).

The canonical per-story playbook adds two blocking mechanisms: the **Red Gate Density Check**
(`RED_RATIO = RED_TESTS / (TOTAL_NEW_TESTS − EXEMPT_TESTS)`, threshold ≥0.5, remediation Option A/B
only) and **Step 4.5 per-story adversary convergence**.

**Phase 4** — scenario rotation (random 80% subset seeded from run ID) → DTU startup → holdout
evaluation → `phase-4-gate` with 8 criteria (different model family, no source/spec access, 3
executions per scenario geometric mean, mean ≥0.85, no must-pass <0.6, std dev <0.15, rotation
applied, full scenario text never revealed).

**Phase 5** — adversarial refinement loop (max 10; **4 walls**) → triage-and-fix → fix delivery →
optional Gemini secondary → holdout regression if fixes changed behaviour.

**Phase 6** — Kani proofs → fuzzing → mutation → security scan, each with a backup → hardening gate.

**Phase 7** — 7 dimension steps → convergence gate → drift check → demo → visual review → human
approval (48h). **NOT CONVERGED loops back to Phase 3.**

**Post-pipeline** — release → steady-state handoff (cycle archive, git tag, enable maintenance and
discovery schedules) → post-feature validation → session review → human approval (72h) → pipeline
COMPLETE.

Also genuinely good: a **budget-driven control flow** (70% WARN → 85% ALERT + downgrade
non-critical agents → 95% PAUSE → >100% HARD STOP) with five agents *never* downgraded (adversary,
holdout-evaluator, formal-verifier, pr-reviewer, security-reviewer); and an out-of-band
**heartbeat** monitor that nudges the human when an approval has been pending >4h.

### 15 declared human-approval nodes, plus 14 more that exist only in prose

Declared as workflow nodes: market-intel (48h), brief (24h, L0), intake (24h, L1–L4), planning
session review (72h), design-system (24h, UI), multi-variant (24h, UI), phase-1 (24h), multi-repo
(24h), phase-2 (24h), phase-7 (48h), session review (72h), phase-0 (24h) — plus **three duplicates**
where the sub-workflow re-declares the mode-level gate.

Prose-only gates include: tool-installation approval (*any* security finding of any severity blocks
install), model-substitution approval ("No silent model fallback ever"), merge autonomy levels
L3/L3.5/L4, story-split approval (two separate human touches), and UNJUSTIFIED green tests in the
Red Gate check ("cannot be waived without human sign-off").

The gate presentation protocol is worth keeping: Summary → **Structured Questions** (scope
completeness, anchor correctness, coverage gaps, convention consistency) → Approve/Reject/
Investigate, with the rationale *"the user-as-senior-architect catches things the adversary
doesn't."*

### What is broken

**`.factory/wave-state.yaml` was never instantiated.** Three registered hooks target it and the
prerequisite hook fails open (`exit 0  # no wave-state file = project hasn't opted in`), so
wave-N+1 dispatch blocking, merge auto-append, and the session-end pending-gate warning are **all
no-ops in this corpus**. A second, incompatible representation (`stories/sprint-state.yaml`) is
what `bin/wave-state` reads — and it is a month stale (`total: 70 / merged: 57` against STATE.md's
117 registered / 74 merged; `rc.11` against rc.20 shipped).

**Six mutually incompatible STATE.md schemas.** The live file uses a 70-character compound slug for
`phase:`, a ~1,400-character prose `current_step:`, a 3-column phase table, and seven status words.
The template wants an integer phase, `not-started`, and a 6-column table with `Gate` and `Finding
Progression` columns. The state-manager contract prescribes `PASSED` — which appears nowhere in the
real file. **The live file fails its own health check on two fields.** `state-update/SKILL.md:44` is
hardcoded `product: corverax`, a different project. 27 lines of STATE.md are an HTML comment
tracking the file's own line count, against **four conflicting size budgets** (200 / 415 / 500),
citing an enforcing hook whose name does not exist.

**The same transition is restated in 6–7 hand-maintained places per burst.**

**Gate names are off by one for Phases 5–7.** `phase-5-gate` guards Phase 6 output; `phase-6-gate`
guards Phase 7 output; `phase-6-human-approval` is the Phase 7 release authorisation;
`pre-phase-4-*-gate` actually guards Phase 3 entry. `state-update/SKILL.md:85-86` maps `phase-4` to
**two different phases**.

**Step 4.5 — declared non-skippable — is missing from the reference workflow.** It exists in
`phase-3-tdd-implementation.lobster` but `greenfield.lobster:651-793` has no such node, and the
Phase 3 skill silently omits the step file that exists on disk. **The Red Gate Density Check appears
in no workflow node anywhere.**

**Three files each claim to be the canonical per-story playbook**, each with a "if the two disagree,
this file wins" clause. The only one containing the 9 steps, the RED_RATIO formula, the Option A/B
rule and the full Step 4.5 contract is referenced by **nothing in the pipeline** — only by bats
tests.

**The workflow validator rejects the workflows.** It permits only `agent|skill|command` and requires
`task`; the real step types are `gate`, `loop`, `human-approval`, `sub-workflow`, `parallel`,
`compound`. `run-phase` handles only the first three, so it **cannot execute any phase workflow**.

**Conditional steps appear in `depends_on`, making phases unreachable.** `wave-gate` depends on the
UI-only `wave-ui-quality-gate`, so **for a non-UI product the wave gate is never satisfiable**;
`phase-7-convergence` depends on a doubly-conditional UI step, so **non-UI products can never reach
Phase 7**. Skip-propagation semantics are defined nowhere.

**The orchestrator is dispatched to itself and told to write files it cannot write** — six
`agent: orchestrator` steps exist, one instructing it to write
`.factory/holdout-evaluation/scenario-selection.json`, against "You cannot write ANY file."

**Three definitions of the 7 convergence dimensions, plus a fourth saying five** — and the
human-approval prompt says "all five" while the gate it depends on lists seven.

**~12 paths the phase machinery declares are unregistered** and therefore hard-blocked on write,
including `.factory/planning/gap-analysis.md` — which artifact-detection must write as the routing
gate's own exit criterion. The **8 architecture section files** that FACTORY.md, three skills, the
orchestrator playbook and the Phase 6 context block all instruct agents to load **do not exist**;
the disk uses `SS-NN-*.md` instead.

**The running project is not running the declared pipeline.** `CLAUDE.md` documents a continuous
F5 cycle-level asymptotic-convergence loop whose unit of work is a 5-commit fix burst driven by
state-manager — not a phase sequence — and establishes a 12-level source-of-truth precedence in
which STATE.md outranks every spec, the inverse of FACTORY.md's "Spec Supremacy".

And the 3-clean-pass rule, declared in five places, is encoded in **zero** loop exit conditions —
every loop exits on a single verdict string. `CLAUDE.md:230` says so outright: *"Currently
structurally impossible under prose-only codification."*

---

## AREA 4 — State, locking, wave boundaries, worktrees

### ⚠ A version caveat that reframes everything below

`factory-lock`, `factory-unlock`, `wave-handoff`, `rehydrate-wave` and `wave-reset` **do not exist in
`~/Dev/vsdd-factory` on `develop`** (`82163b7f`, rc.20 lineage). They exist only in the installed
operator cache at `~/.claude/plugins/cache/claude-mp/vsdd-factory/1.0.0-rc.23/`. Two independent
reviews hit this.

So: **the factory's own `.factory/` state was produced by an engine that had no lock and no
wave-handoff.** Every observation about the live corpus below predates the machinery meant to
protect it.

### What it is

**STATE.md** — 379 lines / 52,639 bytes. 18 frontmatter keys, including a 60-char slug `phase:`, a
**2,100-character single-line** `current_step:`, and a **27-line HTML-comment size ledger** with one
self-reported `wc -l` entry per burst. Body: 33 phase rows, a decisions log, drift/tech-debt rows,
and a **166-line Session Resume Checkpoint §1–§12** that is the actual zero-context resume payload.

**Single-writer discipline** is the core idea and it is stated crisply — state-manager is "a
bookkeeper, not a decision-maker", and the sole writer of the `factory_lock` block. Four write paths
(`state-update`, `state-burst`, `compact-state`, `factory-lock-write.sh`), all through it.

**Content routing** is genuinely well specified: burst narratives → `burst-log.md`, per-pass counts →
`convergence-trajectory.md`, findings → `adversarial-reviews/pass-N.md`, all but the latest
checkpoint → `session-checkpoints.md`, lessons → `lessons.md`, resolved blockers →
`blocking-issues-resolved.md` — with five explicit "NEVER" anti-patterns.

**The lock** is an advisory TTL'd cooperative lease (2700 s, non-configurable): fetch-before-check →
read `factory_lock` → decide (`PROCEED_ACQUIRE` / `NOOP_SELF_HELD` / `REFUSED_FOREIGN_LOCK`) → write
+ CAS push → emit `factory.lock.acquired`. Release returns one of five decision tokens.
`factory.lock.stolen` is **mandatory and cannot be suppressed** on force-stealing a foreign lock.
Two WASM guard arms cover `Edit|Write|MultiEdit|Agent` and `Bash` git-push. The TOCTOU race is named
in the error message as CWE-367.

**The wave boundary** is the best-specified subsystem in the corpus. `wave-state.yaml` carries
exactly 6 required fields; `HANDOFF.md` exactly 9; they are **co-committed in a single commit**
staging only those two files (explicitly not `git add -A`). Rehydration injects a closed-form set —
`Set(stories[*].spec_files) ∪ Set(arch_files) ∪ {state_pointer}` — read via `git show`, with a
machine-stable `INJECTED_FILE_COUNT` sentinel, warn-not-block on a missing member, hard error on a
missing manifest, and an explicit **no-RAG** prohibition. Ordering is a Kahn topological sort. A
wave reset is a **hard drop, not a `/compact`**, because summarizing leaks stale prior-wave specs.
Anti-fabrication checks are real: 40-char-hex enforcement, no-hardcode/no-cache, a three-state
`precompact_flush_sha` rule that hard-blocks rather than writing a bad value, non-empty `active_bcs`,
and a CWE-116 guard before YAML interpolation. There is a literal postcondition→mechanism table.

### What is broken

**The CAS push is `--force` with extra steps — and this is the load-bearing concurrency mechanism.**
`factory-cas-push.sh` fetches, then reads its lease value from the ref *the fetch just updated*, so
`--force-with-lease` can only fail inside a microsecond window. A concurrent commit that landed
*before* the fetch is force-overwritten, and the local branch is never rebased or merged onto the
fetched tip anywhere in the script. The header asserts the opposite: "Remote state MUST NOT be
silently clobbered."

**"Fetch-before-check" never reaches the check.** The precheck fetches, then reads `$STATE_MD` — a
*local worktree file*. `git fetch` updates only the remote-tracking ref. There is no `git show
origin/factory-artifacts:STATE.md`. So a foreign lock pushed by another session is **invisible**.
Unlock has no fetch step at all.

**The lock lives inside the file it protects, on the branch it protects** — so every acquire is
itself a `factory-artifacts` write that must survive the race it exists to prevent. Both guard arms
are `on_error = "continue"`, i.e. **fail-open**.

**No holdership re-check between commit and push**, with a 45-minute TTL: a long burst pushes with an
expired lock another session may own — and via the CAS defect, that push wins.

**The retired multi-commit pattern is live in production right now.** `git log -4` on `.factory`
shows a **three-commit chain per burst** whose 2nd and 3rd commits exist solely to write the previous
commit's SHA into content on the same branch — exactly the self-referential loop TD-VSDD-053 retired
after "6 consecutive recurrences in one session costing 5+ force-pushes". The guard fires only on the
literal token `backfill`; the project renamed the stage to `SHA-patch`/`finalize` and the guard went
quiet. Relatedly, STATE.md cites HEAD as `f671ca50` in two places while actual HEAD is `0aaba144` —
the "finalize" commit that could not cite itself.

**`wave-handoff` never pushes.** Its own exit-code table claims a "git push failed" mode;
`commit-to-artifacts.sh` is 55 lines with no push, and `rehydrate-wave.sh` reads the **local** ref
with no fetch. So CAP-032 losslessness holds only for a single machine, single clone.

**The compaction audit trail is 8 unverified strings.** STATE.md cites `git show
<SHA>:.factory/STATE.md` eight times; **no skill produces that pointer** (its only occurrence outside
`tests/` is zero), `compact-state` emits a plain path list with no SHA, and `D-430(a)` — the decision
authorising the compaction — appears nowhere outside `tests/`. Nothing resolves or verifies any of
those SHAs, for 41 archived rows. `compact-state` also appends to up to five files sequentially with
no idempotence key, so its "abort without modifying STATE.md" claim is unenforceable, and "last 5
rows only" silently drops the rest against "it never deletes content".

**A session dying mid-burst has no recovery path**, in any of three windows — and the next session's
`git stash push -u` classifies half-applied remediation as "sidecar noise". The documented FAIL
recovery, `git reset --soft HEAD`, **is a no-op** (HEAD to itself) that then manufactures the very
two-commit burst the protocol forbids; the author knew the right form (`HEAD~2`) and used it 35 lines
later.

**STATE.md exempts itself from staleness detection.** It carries `inputs: []` and
`input-hash: "[live-state]"` — an unrecognised sentinel — so it scans as NOINPUT and, in the skill's
own words, "silently drops out of drift detection". **The one artifact every session reads is the one
artifact never checked.** The hash itself is a **7-char truncated MD5 of a concatenation** — order-
insensitive, so swapping two inputs' contents is invisible.

**Gates fail open on missing tooling.** `validate-wave-gate-prerequisite.sh` exits 0 (pass) when
`jq` or `python3` is absent — a hook written specifically to stop "documentation says run the gate
but nothing mechanically enforces it".

**Two shipped skills cannot satisfy the schema a third shipped skill enforces.** `state-update`
omits three fields `check-state-health` marks required and writes the compound `phase:` form it
forbids; `recover-state` emits `1a`/`1b`/`3.5`, also rejected. recover→health-check is a guaranteed
FAIL. And `recover-state` scans the filesystem while ignoring `git log`, then admits it cannot
recover five sections — every one of which is in history.

**`EnterWorktree` has zero occurrences in the tree.** The harness's worktree-aware tool is unused;
everything is raw `cd` / `git -C`, which is precisely why `resolve-worktree-identity.sh` had to be
written to stop "reading the wrong `.factory` (the exact #169 regression)". Live consequence:
`.factory/.factory/logs/` exists — a nested factory root — caught only by a **PostToolUse** hook,
i.e. after the write it describes as "silently creates artifacts in the wrong place".

**Live, right now:** `git -C .factory status --porcelain` returns **29 entries** while STATE.md
asserts "expect clean". Nothing detects it.

Also: `factory-health`'s wrong-branch auto-repair is **blocked by the factory's own**
destructive-command guard; multi-repo dual-branch commit is non-atomic with no CAS helper for the
second branch; `state-update` and `compact-state` commit and never push; and `bin/multi-repo-scan`
cannot detect a canonically-initialised multi-repo project (wrong directory, and it requires `.git`
to be a directory when every worktree has `.git` as a *file*).

### The shape of it

The *intentions* here are unusually sharp — CAS pushes, TTL'd leases, mandatory theft audit, no-RAG
closed-set rehydration, anti-fabrication cross-checks, refusal to hash partial input sets. Almost
none of the failures are missing intent. They are **that intent implemented in bash over git**, where
the coordination primitive lives inside the contended artifact, the lease is read from a file the
fetch never updates, the CAS lease is taken from the ref the fetch just moved, identity must be
transcribed into the payload that defines it, and half the gates fail open on a missing `jq`.

---

*(Areas 5–6 — artifact model, alternate modes — pending.)*
