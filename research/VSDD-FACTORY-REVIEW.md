---
title: VSDD-FACTORY-REVIEW — how the factory is supposed to operate, and what `fa` must therefore provide
date: 2026-08-02
purpose: a full operational review of ~/Dev/vsdd-factory — phases, agents, artifacts, state, gates, modes — compiled into a feature list for `fa`
method: six parallel READ-ONLY reviews, each reading the skills/agents/workflows/hooks AND the live .factory corpus, every claim cited to file:line
status: COMPLETE — all 6 areas landed, consolidated into 32 `fa` features across 5 tiers (Tier 0 = migration/cutover, the prerequisite)
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

## AREA 5 — Non-greenfield modes, delivery, release

### What it is

**8 declared modes, 14 declared paths.** Step counts (via `bin/lobster-parse`): greenfield 72,
brownfield 26, feature 82, maintenance 34, discovery 29, planning 24, multi-repo 39, code-delivery 23.

**Mode detection** is a single 5-rule dispatch: `project.yaml` → multi-repo; else
`phase-0-ingestion/project-context.md` present + implementation → feature; absent + `src/` →
brownfield; absent + no `src/` → greenfield; human phrase → discovery/maintenance; explicit override
wins.

**Feature mode** replaces Phase 1 with F2 *delta* and Phase 2 with F3, skipping repo-init,
`adaptive-planning`, CI/CD setup and scenario rotation because "all work is scoped to the delta".
The delta is `NEW ∪ MODIFIED ∪ DEPENDENT`, **fixed at F1 and immutable** (expansion needs log →
present → human approve). The scoping matrix is the good part: F4/F6/F7 scope *primary* work to the
delta but **regression always runs the full suite** — "Silent breakage in unrelated modules is the
most dangerous kind of regression" — and dependency auditing must always scan the full tree.
Convergence is delta-only so a small feature isn't held hostage by pre-existing gaps; regression is
a separate binary check.

**Spec evolution is genuinely append-only.** Continue BC numbering, mark modified BCs UPDATED with
the previous version inline, "do NOT rewrite or restructure existing unaffected requirements". **L4
immutability is the hard rule**: once a VP has a passing proof it is `status: locked` and no agent may
change its pre/postconditions or invariants; refinement mints VP-NNN+1 with `amends:`; withdrawal
keeps the record with `withdrawal_reason`. Version bumps propagate *upward* (L4 → L3 patch → L2 minor
→ L1). Traceability extends by **appending** with an explicit `# Existing chain (DO NOT MODIFY)`
marker, and deprecated requirements stay in the chain as historical record.

**Brownfield ingestion** is the most carefully-designed subsystem reviewed. Passes 0–6 with 7-tier
file prioritization, a two-sub-pass domain model, and **tests as first-class spec inputs** (test
assertions → postconditions, fixtures → preconditions, error cases → error contracts, property tests
→ invariants; confidence HIGH from tests / MEDIUM from code / LOW inferred). Then broad-then-converge
deepening, ordered 2 and 3 first because later passes benefit from the entity knowledge. Three
mechanisms make it converge rather than drift: **verbatim carryover** of next-round targets (the
agent must not pick its own, "which causes topic drift"), a **contradiction mandate** ("the most
recent round is not automatically right"), and a **negative-finding catalogue** — phantoms must be
retracted with `CONV-ABS-N` markers, not silently dropped.

Novelty decay is a **strict binary** and the enforcement language is exactly right:

> Only the literal token `NITPICK` counts as convergence. The orchestrator MUST ignore
> "borderline NITPICK" / "effectively converged" / "recommend halting"… **The agent has no authority
> to declare convergence — only the protocol does.** … Agents are systematically bad at predicting
> whether the next round will converge.

With no fixed maximum — "The protocol stops; the agent never does. Empirical: Vault Pass 2 needed 62
rounds (R6/R10/R15/R30 each predicted 'next is NITPICK' and were wrong)" — and an anti-fabrication
clause: "Fabricating findings is strictly worse than stopping."

And then a **coverage audit that novelty decay structurally cannot replace**: "every one of 5 repos
showed genuine B.5 blind spots after 19-62 rounds of convergence", because round-driven deepening
selects targets from prior-round flags and drifts toward already-covered areas. It must be
grep-driven: "Don't ask the agent 'are there gaps' — make it prove coverage with greps."

**Validation (B.6)** mandates a two-phase split — behavioral judgment, then **arithmetic** recount
producing `(claimed, recounted, delta)` where "any non-zero delta is an error regardless of
magnitude" — because "mixing the phases lets metric inflation slip through". Iteration cap 3
("diminishing returns, validated by AgenticAKM across 29 repositories"), and an L3 abort: >50%
hallucinated means re-run with better file prioritization.

**Delivery** is a 23-step typed sub-workflow: worktree → stubs → tests + **red gate** (`type: gate`,
"tests compile" + "all tests fail", `fail_action: block`) → implement → per-story adversarial
convergence → UI gates → demo recording (≥1 `.gif`/`.webm` per AC, **not** `.txt`, success *and*
error paths) → squash+push → PR → pr-reviewer (4th model family, walled from `.factory/**`) ∥
security-reviewer → convergence loop → brownfield full-regression (**HALT if any existing test
fails**) → CI → dependency-ordered merge → merge → cleanup.

**Two independent autonomy axes**, both metric-gated: merge autonomy L3/L3.5/L4 with risk thresholds
and a `restricted_file_patterns` list that always demands a human; and phase-gate autonomy where
promotion needs `AutonomyScore ≥ 0.85 sustained over 20 runs` with **"fast revocation, slow
promotion"** — one level auto-revoked if the score drops below 0.70 for any 5-run window.

**Release** defers to `RELEASING.md` as single source of truth, with seven **mandatory invariants**
each carrying its failure mode — branch from develop not main ("else marketplace ships stale
source"), merge with `--merge` not `--squash` ("squash collapses develop's ancestry; future releases
see false 'diverged' warnings"), tag on main, exact tag name because `release.yml` only fires on
`v*`. The automation split is deliberate: "Pre-tag is operator-driven on purpose: the human is the
one who knows what's ready to ship and who writes the CHANGELOG narrative." And the escalation
contract is unambiguous: **"If you encounter a failure mode not in the recovery section, STOP…
Do not improvise on the release pipeline."**

### What is broken

**The mode discriminator does not exist.** `phase-0-ingestion/project-context.md` — the file rule 2
branches on — is absent, so **feature mode is only reachable by human override**, yet
`feature-delta/` and two `cycles/v1.0-feature-*` directories prove it has run repeatedly.

**The scope predicate has no carrier.** `.factory/phase-f1-delta-analysis/affected-files.txt` is
referenced **11 times** across F1/F5/F6 and (a) does not exist, (b) is unregistered so writing it is
hook-blocked. The real artifact is a **markdown table** at a different path, so every consumer of
the delta must parse prose.

**~28 artifact homes are referenced but unregistered, and therefore hard-blocked**, with reference
counts: `planning` 84 (registry has `plans`), `discovery` 69, `design-system` 41,
`phase-0-ingestion` 39 (**20 real files already live there** — a retired home, readable but frozen),
`holdout-scenarios` 37, `session-reviews` 29, `maintenance` 28, `feature` 28, and the
`phase-f{1..7}-*` homes 128 between them. Consequence: **`.factory/discovery/` and
`.factory/maintenance/` are entirely absent from disk** while STATE.md records a completed
maintenance sweep. Both autonomy configs (`merge-config.yaml`, `autonomy-config.yaml`) are likewise
unregistered and absent — **autonomy is undefined at runtime on this project.**

**Declared skips are not expressible in the workflow.** Of 82 feature steps only 42 carry any
condition and 14 mention `trivial`; F5/F6/F7/release are unconditional. When `phase-f2-spec-evolution`
is skipped, five F2-labelled steps still run — including `phase-f2-gate` and
`phase-f2-human-approval`. So a "skip" removes the worker and leaves the gate and the human approval
live. Whether F5 runs on a trivial change has **three incompatible answers** across the skill, F1,
and the docs. Same pattern in maintenance, where `state-backup-sweep-N` is unconditional behind
conditional sweeps.

**The validation floor shipped at a third of spec and passed.** `extraction-validation.md` reports a
125-of-1,851 sample = **6.75%** against a required ≥20% — "because nothing computes the ratio".

**Seven spellings of one `document_type`** — `adversarial-review` (257), `adversary-review` (69),
`adversarial-review-pass` (47), `adversary-pass-report` (28), `adversary-pass` (21),
`per-story-adversary-review` (6), `local-adversary-review` (6) — and this is a **live gate bypass**:
`validate-template-compliance.sh` resolves a template by `document_type` and exits 0 "if no template
found". Every non-greenfield artifact class has no template. **Choosing a variant spelling silently
skips the structure gate.**

**A retired enum value is still hard-coded in three gates.** Phase 0 requires `origin: recovered`;
the template enum is `greenfield|brownfield`; the real census is 1,875 `brownfield` / 79 `greenfield`
/ 5 `spec-revision` — **zero `recovered`**, plus a third value not in the enum.

**Feature mode has two incompatible frontmatter schemas under one `document_type`** — one keyed
`feature_id`/`timestamp`/`producer` with `level: F1` and routing keys, the other keyed
`cycle_id`/`created`/`author` with none of them. Delivery artifacts are the least structured: 61
`pr-description.md` samples have **no frontmatter at all** (it's passed verbatim to `gh`), burying a
YAML block inside a `<details>` element instead. Four of six declared per-story artifacts exist
**zero** times; the one that actually carries the PR number and merge SHA is undeclared and exists in
2 of 64 directories.

**Maintenance findings have no ID, no status and no suppression**, so a false positive re-fires
weekly forever — and the session review's own goal, "review sweep effectiveness — false positive
rate", is uncomputable. The maintenance gate is `fail_action: warn`, i.e. non-blocking. Discovery has
**no `type: gate` step at all**.

**No time-series anywhere.** `regression-state.json` is a single overwritten record, so the autonomy
criterion "zero regressions in the last 20 runs" cannot be evaluated. Five sweeps require "compare
against last baseline" with no store.

**Nothing is scheduled.** Both greenfield and feature say "**Schedule** post-feature validation" at
7/30/90 days — with no scheduler and no schedule store, so nothing will ever fire.

**Discovery carries no provenance at all** — no `inputs:`, no `input-hash:`, no `traces_to:` on any
artifact, so drift detection is blind to the whole layer. The only signal→insight link is a prose
table of labels, `competitive-baseline.md` is mutated in place so the baseline an insight was
computed against is unrecoverable, and the URGENT route fires on two terms that live in different
artifacts **with no join key**. There is also no idea→ship→outcome link: the calibration loop is
explicitly specified ("if features with high discovery scores consistently MISS, the weights need
adjustment") but the only shared field is a date, so two runs on one day collide.

**On the factory's own repo, `quality_gates: {mode: standard}`** — which *disables* every VSDD
convergence, holdout, formal-verification and adversarial gate at release. Only four `pre_release`
shell checks run. And `publish: null`, so distribution is a marketplace PR, not a registry.

Also: `Mode:` is prose in the PR body with a real value (`fix-burst`) outside the template's enum;
demo-recording and record-demo both target `.factory/demo-evidence/` while the delivery gate requires
`docs/demo-evidence/` on the feature branch (and record-demo permits a `.txt` fallback the gate
rejects); `technical-writer` is not wired into delivery or release at all, and being denied `exec` it
cannot run `git log` to build a changelog; the maintenance sweep count is documented as 9, 10 and 11
(actual 11, with Sweeps 10 and 11 absent from the skill entirely); path numbering disagrees between
the orchestrator sequences and the paths guide; and the discovery composite score has three
different formulas.

---

## AREA 6 — The artifact model: types, keys, indexes, traceability

### What it is

`config/artifact-path-registry.yaml` — ~50 `artifact_type` entries, **every one
`enforcement_level: block`** — declares each type's home. Templates declare frontmatter and mandated
sections. The corpus is **3,145 files**: 2,091 under `specs/` (1,959 BCs across `ss-01`…`ss-10`, 80
VPs, 23 ADRs, 10 subsystem docs, 8 domain-spec shards, a 120 KB PRD), 621 across 5 cycles, 170
stories, 148 delivery artifacts.

The **traceability chain** is mostly carried by real frontmatter fields, and that part works:
`capability:` · `subsystem:` · `source_bc:` (VP→BC) · `behavioral_contracts:` /
`verification_properties:` / `anchored_adrs:` / `subsystems:` / `epic_id:` / `depends_on:` /
`blocks:` / `closes:` / `target_module:` on stories. Two of these are enforced *bidirectionally* by
real hooks — story↔BC sync (POLICY 8) and subsystem names (POLICY 6).

### What is broken

**Six mutually inconsistent BC totals in one corpus.** 1,959 files · 1,958 index rows ·
`total_bcs: 1955` · 1,953 (sum of the Summary column) · **1,949** (stated three times, including
`| **Total** | | **1949** |` in the same table whose column sums to 1953) · **1,851**
(`bc-id-mapping.md`, never revised). **5 of 10 per-subsystem counts are wrong**, and for SS-05 the
declared subtotal, ARCH-INDEX's stated premise, and the directory contents are three different
numbers for the same set.

**Nothing generates the indexes.** `validate-template-compliance/SKILL.md:148` reassures the reader
that INDEX files "have no template — they're auto-generated". They are hand-maintained by a
*voluntary* skill. Measured drift: BC-INDEX **1 missing row**, STORY-INDEX **37 phantom rows** (144
row IDs vs 107 files — the reverse direction is clean), **5 of 17** epic `story_count` rollups wrong
(E-11 declares 8 stories and **no file carries `epic_id: "E-11"`**), `sprint-state.yaml` three months
and 37 stories stale.

The two clean layers are the tell: **VP (80/80/`total_vps: 80`) and ADR (23/23) are exactly right** —
the two types with a real allocator or a population small enough to hand-maintain. Every larger
hand-maintained derived artifact has drifted.

**The capability link is 75% unusable and 7 rows are type-confused.** Of 1,959 BCs: `CAP-TBD` 807,
bare `TBD` 446, `""` 212, real `CAP-NNN` 487 — **three placeholder dialects for one absent value** —
and **7 BCs carry `capability: "E-12"`, an epic ID in a capability field.**

**AC→BC is unparseable prose.** The only carrier is free text inside an H3:
`### AC-001 — … (traces to BC-7.06.001 postcondition 1 + BC-1.14.001 precondition 1)`. 12+ stories
contain no `traces to` string at all. `AC → test` is a *naming convention*. And
`traceability-chain.md` — the file the traceability-extension skill governs — **does not exist
anywhere in the corpus**. Story→VP is `[]` for **58 of 107** stories, with deliberate deferral and
authoring omission indistinguishable.

**ID allocation is prose for every type except ADR.** `create-adr` is the only allocator, is
explicitly non-atomic ("Users SHOULD serialize"), and `policy-add` uses `max_id + 1` with **name**-based
collision defence. BC/VP/story/epic/SS have only POLICY 1 prose with no scan procedure and no source
of truth named. `register-artifact` **mints nothing** — its only defence is a duplicate-*row* check,
so two agents minting the same BC id are undetectable and the second is silently "already registered".

**225 of 3,145 files (7.2%) match no registry pattern** and are therefore unwritable under the
blocking hook — 124 adversarial reviews (the registry has only a *flat* `cycles/{id}/adv-{slug}.md`),
42 legacy stories, 20 ingestion passes, 16 nested semport files, `measurements/*.json|*.sh` (the
pattern allows only `.md`), and the nested `.factory/.factory/logs/`. `relocate-artifact` recorded
"0 violations" as a comment. Registry patterns are single-segment-per-placeholder and `.md`-only.

**Path enforcement fails open in four ways**: registry absent → Continue, malformed → Continue,
unknown `enforcement_level` → advisory, and `on_error = "continue"`. One bad YAML edit silently
disables all path enforcement. And `{placeholder}` matches any whole segment, so
`BC-2.02.013-host-run-subprocess.md` — the one BC with a slug in its name, `status: withdrawn`, and
**the only BC absent from BC-INDEX** — passes the path hook while violating the natural key.

**The structural blind spot, named precisely:** `validate-template-compliance.sh:63` exempts every
`*INDEX*` file from structure checks; `register-artifact` is voluntary; the only file↔index
divergence detector is an on-request skill; and `validate-count-propagation.sh:150` states
*"Absence of keyword in sibling is NOT drift"* — so an un-propagated count is silently fine. **The
failure the system cannot see is a correctly-located, correctly-shaped artifact that no index knows
about** — which is exactly the 1 unindexed BC, the 37 phantom rows, and the 225 unmatched files.

Also: STORY-INDEX uses **4 different table schemas** for one type (plus a `Depends-On` typo), never
caught because of that same INDEX exemption; the ARCH-INDEX decisions table has a **three-way** schema
conflict between template, writer skill and reality; VP filenames, epic ID format, and 8 PRD-cited BCs
with no file are all declared-vs-actual mismatches; a stale cross-index pin cites BC-INDEX **v1.84**
against a live v2.65; and one epic documents its own template non-conformance in an HTML comment
("Template update tracked as follow-up") while carrying 19 fields against the template's 6.

---

# ⚠ CORRECTIONS TO THIS REVIEW — from the v1 design measurements (2026-08-02)

Designing L5–L6 required re-measuring several of this review's claims exhaustively rather than by
sample. Six were wrong, and one of the corrections is materially worse than what I reported. Recorded
rather than patched in place, so the audit trail survives.

| this review said | measured | why it matters |
|---|---|---|
| the workflows use **six** step types | **seven** — `parallel-foreach` (8 uses) was omitted | an engine built to the six-type list cannot execute 8 real steps. Its iteration set is also undocumented, which **blocks byte-exact round-trip** |
| conditional steps in `depends_on` strand the wave gate and Phase 7 (**2** hand-found cases) | **140 edges — 26% of the dependency graph** | and a third stranding I missed: `session-review:1379` depends on `post-feature-validation:1364`, which is **off by default**, so **greenfield cannot reach COMPLETE at all** |
| `verdict:` holds **21** tokens | **23** tokens over 443 uses, 36% of them severities, incl. an invented `CLEAN_PASS_1_OF_3` | — |
| the convergence hooks skip **125 of 295** reviews | the `pass-*.md` glob resolves for **6 of 400** | the rule is not partially applied, it is effectively absent |
| Phase-2 gate has **27** criteria | **26**, and the count is not reproducible under either definition | — |
| the trajectory violates monotonicity **three** times | **four** strict increases | — |
| **34** agent definitions | **44** files declaring only `opus`/`sonnet` | widens the model-diversity gap: `holdout-evaluator.md:5` pins `model: opus` against `FACTORY.md:412`'s GPT-5.4, with `openclaw.json` absent |

Two new facts that shape the design rather than correcting it: **278 gate criteria across 38 gates
with 0 evaluators — but 65% already have a machine shape**, so the gate-as-query work is mostly
translation, not invention. And of **24 loops**, 19 share the magic cap 10, 3 have no cap, and of 20
exit conditions **zero** reference a streak — which is the mechanical proof of `CLAUDE.md`'s own
admission that the 3-clean-pass rule is "structurally impossible under prose-only codification."

---

# ⭐ CONSOLIDATED `fa` FEATURE LIST

Deduplicated across all six reviews. Ordered by leverage — how much of the measured failure mass each
one removes. **Tier 0 comes first because it is the prerequisite: the goal is that `fa` is the SOLE HOME
of every artifact — new projects start in `fa`, existing projects migrate in — and Tiers 1-4 all assume
that has already happened.** Every "eliminates" is a defect one of the reviews verified in this corpus.

The single most important observation: **the factory's design intent is consistently sharp, and
almost every failure is that intent expressed in the wrong substrate** — prose where a schema was
needed, a hook where a query was needed, bash-over-git where a transaction was needed, and an agent's
self-report where a derivation was needed. `fa` should not reimplement the factory's judgment. It
should give that judgment a substrate that can hold it.

---

## Tier 0 — getting the artifacts INTO `fa`, and keeping them there

⚠ **Tiers 1–4 describe what `fa` must do once artifacts live in it. This tier is the prerequisite,
and it is where the current build is thinnest.** The goal is that `fa` is the *sole home* of every
artifact — new projects start in `fa` and never grow a markdown corpus; existing projects migrate in.
Measured against that goal today:

| | |
|---|---|
| markdown files under `.factory/` | 3,085 |
| `document_type` has a table in the store | 2,624 (85%) |
| **stores a VERBATIM BODY — the only ones renderable back** | **2,145 (69%)** |
| no table at all | 461 (14%) |
| distinct `document_type` values / modeled | 70 / **18** |

Plus: only `bc`, `vp` and `story` carry a `body` column; there is **no `section` table** (D-A's
ordinal partition is computed in memory and discarded); there is **no `fa render`**; invariant 15 is
declared and unbuilt; and `fa` self-describes as *"phase 1: read-only shadow"* — **it has no write
path at all.** So the store is currently lossy for ~31% of the corpus and has no way back out.

### M1. Lossless capture for EVERY type — verbatim body + stored section partition
Every artifact keeps its body bytes; D-A's ordinal section partition becomes a real table rather than
an in-memory value. Acceptance: **100% of observed `document_type` values have a home**, and every
one stores its body. *Today: 18 of 70 types modeled, 3 tables carry a body.* Until this holds,
"move every artifact into `fa`" means losing 461 files outright and field-extracting 940 more.

### M2. `fa render` and the round-trip gate — the settled decision that was never built
D-B: store gitignored, **rendered markdown committed** as the review surface and the offline backup,
with **invariant 15 `import(render(store)) == store` gated byte-exact**. This is what keeps humans,
`gh pr diff`, GitHub review, and every existing reader working after the move — and it is the only
honest proof the migration is lossless. `rendered/` currently holds one hand-made sample file.
*This is the highest-priority missing piece in the whole list:* without it, migration is
irreversible and unverifiable.

### M3. The write path — `fa new|set|edit|retire`, schema-validated at write time
`fa` can import, validate and shadow; it has never written an artifact. Every Tier 1–4 feature
assumes this exists. Writes validate against F5's schema, mint ids via F11, take a lease via F4, land
in a transaction via F2, and emit an audit row via F18.

### M4. `fa init` as the greenfield entry point
A new project starts with a store and a schema — no orphan branch, no worktree, no markdown corpus to
migrate later. This replaces `repo-initialization`'s `factory-artifacts` orphan branch +
`.factory/` worktree setup, and with it the whole class of "which `.factory` am I in" failures
(F21), the two divergent worktree-health skills, and the nested `.factory/.factory/` bug.

### M5. Staged, per-TYPE cutover — never big-bang
Reuse the ladder the registry already declares for derived types, applied to *migration* per artifact
type: **`shadow` → `dual-write` → `authoritative` → `markdown retired`**. `fa shadow` already
implements stage 1 and reports 658 disagreements, which is exactly the evidence stage 2 should be
gated on. A type advances only on evidence; nothing flips wholesale. This also means an in-flight
project is never blocked on a full migration — it can move BCs before it moves burst logs.

### M6. Migration acceptance gate — `fa migrate verify`
Completeness is a measurement, not a declaration: every file accounted for (migrated / declared
out-of-scope / rejected-with-reason), **byte-exact round trip for 100% of bodies**, count parity per
type, the 18,826-finding conformance baseline preserved across the move, and **zero unmodeled
`document_type` values**. Report per-form counts and never drop silently — the corpus has already
demonstrated that a 6.75% sample can pass a 20% floor because nothing computed the ratio.

### M7. Compatibility for everything that reads `.factory/**` today
62 registered hooks, the `gh`/CI surface, and ~34 agent definitions read those paths. Each either
reads the committed render (M2) or calls `fa`. `fa path resolve <type> <ids>` becomes the only way an
agent learns where anything lives — which is also what closes F17's ~28 unregistered homes and the
225 unmatched files, because the path stops being something an agent types.

### M8. Write interception, or the store and the files silently diverge
While both exist, `Edit`/`Write` on artifact paths must be denied and only `fa` permitted (D2 already
anticipated "deny Bash, allow only `fa`"). Without this, dual-write drifts and the migration's own
round-trip gate starts failing for reasons unrelated to `fa`.

### M9. Multi-project hosting
`fa` already imports three corpora (vsdd-factory, prism, rivetry) one at a time. "New projects start
with `fa`" means it hosts many: one shared registry — the single canonical copy already `go:embed`'d
and read by the Python tooling — with a store per project, and every query scoped by project (F7).

### M10. A retirement ledger
Name, per cutover stage, which of the 62 hooks / 5 bash helpers / 7 hand-maintained INDEX files /
`sprint-state.yaml` / `wave-state.yaml` get **deleted**, and what replaces each. A migration that
only adds `fa` while leaving the markdown machinery live doubles the number of sources of truth
instead of collapsing them — and the review found the corpus already has 5 competing authorities on
where artifacts live.

---

## Tier 1 — the substrate. These delete whole classes rather than fixing instances.

### F1. Store-assigned identity and versions; no artifact ever transcribes its own identity
Every artifact gets a store-assigned monotonic version. Nothing writes its own SHA, its own HEAD, or
another artifact's version into its content.

*Eliminates:* the live **three-commit-per-burst chain** whose 2nd and 3rd commits exist only to write
the previous commit's SHA into content on the same branch — the exact self-referential loop
TD-VSDD-053 retired after "6 recurrences in one session costing 5+ force-pushes", now invisible to
its guard because the stage was renamed from `backfill` to `SHA-patch`. Also: STATE.md citing HEAD as
`f671ca50` when HEAD is `0aaba144`; the POLICY 14 "5-leg parity" ritual of hand-copying four index
versions into STATE.md and every story's `last_amended`; and the stale `per BC-INDEX v1.84` pin
against a live v2.65. **This single change retires TD-VSDD-053, TD-VSDD-044,
`verify-sha-currency.sh`, the entire burst protocol, and every hand-typed provenance string.**

### F2. Transactions: all-or-nothing across N artifacts, with idempotence keys
`fa txn begin / write / commit --key <id>`. Replay returns the prior result. One transaction spans
multiple scopes and repos.

*Eliminates:* `compact-state` appending to five files sequentially so a failure at #4 leaves #1–3
written, making its "abort without modifying STATE.md" claim unenforceable; duplicate-history on
retry; the non-atomic multi-repo dual-branch commit with no failure handling between the two pushes
and no CAS helper for the second branch; and `state-update`/`compact-state` committing without ever
pushing.

### F3. Optimistic concurrency with typed conflicts — and no force path at all
`fa write --if-version n`; mismatch returns a `Conflict` naming the artifact, both versions, and the
conflicting writer. The store has no force, no auto-merge, no auto-rebase.

*Eliminates:* the load-bearing concurrency bug — `factory-cas-push.sh` reads its
`--force-with-lease` value from the ref *the fetch just updated* and never rebases onto it, so it is
`--force` with extra steps and discards a concurrent writer's commits outright, while its own header
promises "Remote state MUST NOT be silently clobbered."

### F4. Store-side leases, scoped to path sets, with server-side expiry
`fa lease acquire --scope <glob> --ttl`. The lease lives in the store, never inside a protected
artifact. Every write presents the token; an expired token is rejected at write time. Fail-closed by
default. `--force` breaks are audited inside the same transaction as the break.

*Eliminates:* a mutex stored as YAML **inside the very file it protects, on the contended branch**;
a "fetch-before-check" that fetches and then reads a local file the fetch never touches, so a foreign
lock is invisible; both guard arms running `on_error = "continue"` (fail-open); and the absent
holdership re-check between commit and push, where a >45-minute burst pushes under an expired lease
and — via F3 — wins. Scoping also removes the practical incentive to `--force`: today one mutex covers
the whole branch, so two sessions on disjoint subsystems serialize.

### F5. One typed schema per artifact type — path, key, frontmatter, sections, index shape, in a single definition
Enforced at write time. Closed enums. Natural keys parsed as typed values (`BC-S.SS.NNN`, `VP-NNN`,
`S-N.MM`, `E-N`, `ADR-NNN`, `CAP-NNN`, `HS-NNN`), never as `[^/]+` path segments.

*Eliminates:* the type definition being split across four places that disagree (registry / template /
`register-artifact` routing / two divergent hard-coded section tables of 18 and 15 rows); the
malformed-key BC that passes the path hook because `{bc-id}` matches a whole segment; **seven
spellings of one `document_type`**, which is a live gate bypass because
`validate-template-compliance.sh` exits 0 when no template matches — so choosing a variant spelling
silently skips the structure gate; a retired enum value (`origin: recovered`) hard-coded into three
gates against a census of zero; 17 severity tokens, **21 verdict tokens in a field whose declared
domain is 2** (with 130 uses holding a *severity*), and 11 closure tokens against 5 declared. Also
`fa` must not exempt indexes from structure checks — that exemption is what hid four STORY-INDEX
schemas and a `Depends-On` typo.

---

## Tier 2 — derivation. Stop maintaining what can be computed.

### F6. Indexes and counts derived, never maintained
`fa index build bc|vp|story|arch|epic`; `fa count` owns every stated total. One canonical writer.

*Eliminates:* **six BC totals**, a Summary table contradicting its own column sum, 5 of 10 wrong
subsystem counts, 1 unindexed BC, **37 phantom STORY-INDEX rows**, 5 of 17 wrong epic rollups, a
three-months-stale `sprint-state.yaml`. It also makes the ordering rule "state-manager must run LAST
in every burst or you get version-race regressions" unnecessary rather than merely documented. The
VP and ADR layers being the only clean ones is the proof: hand-maintenance scales to 23 and 80, not
to 1,959.

### F7. A declared scope predicate on every derived view; refuse unscoped aggregates
Each artifact carries `cycle_id` and a lifecycle/cycle/local scope; every query states its predicate.

*This is the result this spike already paid for:* 41 of 148 stories live in `v1.0-legacy/` and
STORY-INDEX deliberately omits them, so generating from every record would **resurrect 41 retired
stories while every count still agreed**. It is also the missing carrier for feature mode's delta —
`affected-files.txt` is referenced 11 times, does not exist, is unregistered so writing it is
hook-blocked, and the real artifact is a markdown table at another path.

### F8. Derivation edges with version-sets as the staleness key; staleness computed, not stored
`fa derive --from --to`; `fa stale [--explain]` walks the DAG. Distinguish `stale` / `unverified` /
`unresolvable`, and keep `fa ack --reason` strictly separate from `fa derive`.

*Eliminates:* a **7-char truncated MD5 of a concatenation** as the staleness key — order-insensitive,
so swapping two inputs' contents is invisible; and STATE.md exempting itself via an unrecognised
`input-hash: "[live-state]"` sentinel so that, in the skill's own words, it "silently drops out of
drift detection" — **the one artifact every session reads is the one never checked**. Preserve the
existing good instincts verbatim: refuse partial input sets, cluster-triage before bulk update, and
the honest admission that acking a hash is not re-deriving content.

### F9. Structured traceability as edges, with completeness as a query
Promote `(traces to BC-7.06.001 postcondition 1)` out of H3 prose into a typed edge. `fa trace` walks
L1→L2→L3→L4→story→AC→VP→test→PR→demo in both directions.

*Eliminates:* AC→BC readable by no tool (12+ stories carry no trace string at all); AC→test being a
*naming convention*; `traceability-chain.md` not existing anywhere while a skill governs it; 58 of 107
stories with `verification_properties: []` where deferral and omission are indistinguishable; 8
PRD-cited BCs with no file. It also turns 33 spec-coherence criteria — currently executed weekly by an
LLM reading 1,959 BCs, 107 stories and 80 VPs — into `SELECT … WHERE NOT EXISTS`.

### F10. Referential integrity with the *target type* checked
`capability:` must resolve to a CAP; `epic_id:` to an epic; `source_bc:` to a BC. Placeholders are a
first-class incompleteness state with one canonical spelling and a budget.

*Eliminates:* 7 BCs carrying `capability: "E-12"` — an epic id in a capability field — and 1,465
placeholders in three dialects, which together make "how complete is the capability link?"
unanswerable by grep.

### F11. Transactional ID minting for every keyed type, with a tombstone ledger
Scan files ∪ index ∪ tombstones under lock. Retired, withdrawn and never-issued ids stay consumed.

*Eliminates:* `create-adr` being the only allocator and explicitly non-atomic ("Users SHOULD
serialize"); `policy-add`'s `max_id + 1` race with name-only collision defence; `register-artifact`
minting nothing, so two agents creating the same BC id are undetectable; the BC-1.12.008 →
BC-3.05.004 manual corrigendum class; and reserved POLICY 11/12 slots that the third custom policy
silently consumes.

---

## Tier 3 — making gates real.

### F12. Findings as rows: one ID namespace, declared enums, full lifecycle
`fa finding add|list --scope`, with severity/category/confidence as closed enums, status through
`open → … → resolved|suppressed`, first-seen dates, and `closes` links.

*Eliminates:* **~14 ID conventions** where the format hook validates one — the dominant `F-*` family
alone is >13,000 occurrences and is never inspected, while `per-story-delivery.md` prescribes
`STORY-NNN-FIX-001` and the hook **blocks it as legacy**; stated finding counts unchecked (210 of 295
reviews carry none; of the 85 that do, 6 disagree, and the disagreement is *representational* so no
single parse recovers the set); maintenance findings having **no ID, no status and no suppression**, so
a false positive re-fires weekly forever and "sweep false-positive rate" is uncomputable; and
write-denied reviewers being told to write files they cannot write. This is the enabler that lets
`finding_count`, `severity_distribution` and novelty become derived.

### F13. Convergence computed from finding rows, never claimed
`fa converge status|check|trajectory`. Novelty from the store's own duplicate-linkage, not the
adversary's self-report. Monotonicity a hard fail. One termination rule. Reviews resolved by
`document_type`, never by filename glob.

*Eliminates:* the only Kani-proved gate in the factory reading **hand-written JSON** — 6 proofs over
`passes_clean` and `last_classification` that nothing recomputes, with a live file asserting
`passes_clean: 3` beside `"fix_batches_pending": ["B3","B4"]`; `Novelty score | 0.0 (0 / (0 + 0))`
— division by zero — on a trajectory that violates monotonicity three times and declares
`CONVERGENCE_REACHED` anyway, because the hook records a stderr warning and exits 0; convergence
hooks skipping **125 of 295** reviews (including *both* files that actually declare
`CONVERGENCE_REACHED`) because the corpus's `ADV-*.md` naming is exactly what the glob excludes; and
the 3-clean-pass rule appearing in five prose locations and **zero** loop exit conditions — which
`CLAUDE.md` concedes outright: "structurally impossible under prose-only codification."

Keep verbatim what already works: brownfield's **strict-binary** rule that only the literal token
`NITPICK` closes a pass and *"the agent has no authority to declare convergence — only the protocol
does"*, with no fixed maximum, plus the verbatim-carryover, contradiction-mandate and
retraction-registry mechanisms. Encode all four in `fa` rather than in a prompt.

### F14. Gate registry + per-criterion result rows with mandatory evidence links
`fa gate record --status --evidence`; `fa gate block <transition>`. `pass` requires ≥1 resolvable
evidence reference; `skip` requires a reason. Gate definitions live once and are referenced.

*Eliminates:* 21- and 27-criterion gates that are prose strings with no evaluator and no record of
which criterion passed on what evidence; a wave gate satisfied by the *word* "Gate 3" so that
`Gate 3: FAILED — 5 CRITICAL` passes; `gate_status: deferred` with no rationale, owner or expiry
(recommended by the sibling hook's own error message); a wave gate that is **wholly inert because
`wave-state.yaml` was never instantiated**; gates failing open on a missing `jq`/`python3`;
`Wave 15` declaring `verdict: CONVERGED` with **no record that Gates 2, 4 or 5 ran** and
`holdout-evaluations/` containing only `.gitkeep`; an extraction-validation floor shipping at
**6.75% against a required 20% because nothing computes the ratio**; the mutation gate ("exactly 80 —
no rounding") retired by "deferred per wave gate consensus"; and 16 of 18 policies with
`lint_hook: null`. Add `fa gate exec` so evidence is a `(command, stdout, exit, sha)` tuple **`fa`
produced** — that retires the self-attesting `$ grep -c … / 18 / PASS` transcript pattern and the
six-level POLICY 5 cure recursion chasing it.

### F15. Baselines and ratchets: fail only on *new* violations
`fa baseline snapshot`; `fa check --since`; `fa ratchet tighten`. Plus time-series retention.

*Eliminates:* the binary choice that forced `validate-consistency` Checks 8/9 to be **permanently
non-blocking** ("these checks never flip the report's PASS/FAIL"); `regression-state.json` being a
single overwritten record, so the autonomy criterion "zero regressions in the last 20 runs" cannot be
evaluated at all; and five maintenance sweeps that require "compare against last baseline" with no
store.

---

## Tier 4 — access, identity, and operations.

### F16. Verified caller identity, a role→capability manifest, and walls as return codes
`fa` receives an unforgeable role token; a single machine-readable manifest replaces 34 prose
`## Tool Access` sections. `fa read` returns `DENIED_BY_WALL` instead of bytes. Walls are keyed to
*artifact type*, not path spelling. `fa walls verify` audits every dispatch site of a walled role.

*Eliminates:* the tool-profile source of truth (`openclaw.json`) **not existing**, so the audit
meant to catch profile mismatches cannot run and **29 of 34 agents run with all tools** including
those whose prose says "Denied: exec"; ten agents that cannot do their declared job with their
declared profile; the Phase-1d adversary being explicitly **handed the prior passes** the Phase-5
exclude forbids; holdout-evaluator dispatched at the wave gate with **no `context:` block at all**;
the same wall class spelled four ways across workflows, none in the path registry; and
`FACTORY.md`'s own concession that "soft instructions alone are insufficient for wall enforcement."
Note `holdout-evaluator` is granted `Bash` while "denied" `Grep` — denial of the tool, not the
capability; only a store-side read gate closes that.

### F17. Scoped writes by artifact type, single-writer ownership, write-without-commit
Agents never name a `.factory/` path — `fa` computes it from the registry. `fa` rejects a write to a
type owned by another role. `fa commit` is restricted.

*Eliminates:* **~28 referenced-but-unregistered artifact homes** that are consequently hard-blocked —
`planning` (84 refs), `discovery` (69), `phase-0-ingestion` (39, with 20 real files already there),
`maintenance` (28), all seven `phase-f*` homes (128 between them), and **both autonomy configs, so
autonomy is undefined at runtime**; `.factory/discovery/` and `.factory/maintenance/` being absent
from disk while STATE.md records a completed sweep; **225 of 3,145 files (7.2%) matching no
pattern**; and the never-stated distinction that makes the methodology coherent — *write freely, only
state-manager commits* — which appears in exactly one of 34 agent files while 19 declare direct
writes. Registry patterns also need recursion and non-`.md` extensions, and registry-vs-reference
diffing as a CI gate (that catches `planning` vs `plans`, `feature-delta` vs `feature-deltas`, and
`STORY-INDEX.md` vs `story-index.md` case drift that would break on Linux CI).

### F18. Append-only audit of every read-deny, write and commit, attributed to a role
`{role, lease, scope, txn, before/after version, reason}`. No write path bypasses it.

*Eliminates:* dispatch identity being captured (1,045 `agent.start` events) and then **dropped before
any write** — `hook.block` and `commit.made` carry no agent field and the tracking crate explicitly
*forbids* an `agent_id`; so session-review's Dimension 6, literally "did the information asymmetry
walls hold?", is unanswerable. It also replaces hand-typed `producer:` frontmatter, which already
holds **8 identities that are not agents** (330 files by `phase-1-4b-bcs-agent-4`, two spellings of
`codebase-analyzer`), and the compaction audit trail of **8 `git show <SHA>` pointers that no skill
produces and nothing verifies**, covering 41 archived rows.

### F19. Typed pipeline state: phase/step/wave/loop/approval frontier as rows
One status enum. Loop runs record declared cap, iterations used, and **exit reason** (`converged` vs
`cap_hit` vs `escalated`). Human approvals get pending state, a timeout clock, and recorded answers.
Skip-propagation semantics defined.

*Eliminates:* **six mutually incompatible STATE.md schemas** where the live file fails its own health
check on two fields and `PASSED` — the verdict the contract prescribes — appears nowhere in it; the
same transition restated in 6–7 hand-maintained places per burst; a 2,100-character `current_step:`
as the de-facto "where are we"; **four conflicting size budgets** (200/415/500) and 27 lines of
self-reported `wc -l` in an HTML comment; two shipped skills that cannot satisfy a third shipped
skill's schema, making recover→health-check a guaranteed FAIL; `waiting_human_approval` not existing
while the heartbeat wants to nudge on it after 4h; iteration caps disagreeing across four sources
(3/5/10 for Phase 5 alone) with **no record distinguishing convergence from cap-hit**; and
conditional steps in `depends_on` making the wave gate and Phase 7 **unsatisfiable for non-UI
products**.

### F20. Checkpoints and crash recovery from the log, never from a filesystem re-scan
`fa checkpoint create|rehydrate|status`; write-ahead log; `fa txn list --incomplete`; `fa recover`;
`fa fsck`.

*Eliminates:* `wave-handoff` **never pushing** while its exit-code table claims a push failure mode,
so CAP-032 losslessness holds only on one machine; a mid-burst crash having no recovery path in any of
three windows, with the next session's `git stash push -u` burying half-applied work as "sidecar
noise"; a documented FAIL recovery (`git reset --soft HEAD`) that is a **no-op** and then manufactures
the forbidden two-commit burst; `recover-state` scanning disk while ignoring `git log` and admitting
it cannot recover five sections that are all in history; and two divergent health skills where the
advisory one claims to detect divergence using `git status --porcelain` (which cannot) and whose
auto-repair is **blocked by the factory's own destructive-command guard**.

**Port `rehydrate-wave` almost unchanged** — the closed-form injection set, the `INJECTED_FILE_COUNT`
sentinel, warn-on-missing-member, hard-error-on-missing-manifest, the explicit no-RAG prohibition, and
its literal postcondition→mechanism table. It is the best-specified subsystem in the corpus. Move its
anti-fabrication checks (40-char-hex, no-hardcode/no-cache, three-state `precompact_flush_sha` that
hard-blocks rather than writing a bad value, non-empty `active_bcs`, CWE-116 interpolation guard) into
`fa`, where an agent cannot skip the step that runs them.

### F21. Agent handles instead of filesystem paths
An agent receives a scoped handle; it never resolves `.factory` against ambient cwd.

*Eliminates:* the entire "which `.factory` am I in" class — `resolve-worktree-identity.sh` exists
solely because naive git resolution read "the wrong `.factory` (the exact #169 regression)";
`EnterWorktree` has **zero occurrences** in the tree, so everything is raw `cd`/`git -C`; and
`.factory/.factory/logs/` exists on disk, caught only by a **PostToolUse** hook that fires *after*
the write it describes as "silently creates artifacts in the wrong place".

### F22. Operations the workflows already assume and nothing provides
- **`fa workflow validate|plan|run`** understanding all six real step types. Today the validator
  permits three and requires `task`, so it **rejects nearly every real step**, and `run-phase`
  cannot execute any phase workflow at all. Needs cycle detection for the mutual
  `planning ↔ greenfield` recursion and both gate-block shapes.
- **`fa schedule`** — both greenfield and feature say "**Schedule** post-feature validation" at
  7/30/90 days; there is no scheduler and no schedule store, so nothing will ever fire. Discovery
  declares five cadences behind one run id.
- **`fa pr`** — story ⇄ PR ⇄ CI ⇄ merge as one join. `pr-manager` is denied `exec`, so every
  `gh pr view` is a sub-agent dispatch, and dependency-ordered merge is an N-dispatch join with **no
  persisted story→PR mapping**. Merge prerequisites must be *verdicts*, not filenames: today the hook
  checks three files exist and satisfies "security review conducted" via a regex over a PR
  description that pr-manager writes itself.
- **`fa cost`** — the five-tier budget response up to HARD STOP reads `cost-summary.md`, which does
  not exist and is unregistered. Budget-driven control flow has no data source.
- **`fa attest`** — `phase-4-holdout-evaluation.lobster` **blocks** on "different model family
  (GPT-5.4, not Claude)", a claim nothing can verify and which every agent's `model: opus` frontmatter
  falsifies. The 23 `model_tier:` keys have no resolver, and the config they route through does not
  exist. Model diversity is either checkable or it is decoration.
- **`fa doctor`** — resolve the manifest, every declared read/write target, every walled role's
  dispatch sites, and every referenced hook plugin. This one command would have surfaced most of what
  six reviews found by hand.

---

## What to keep exactly as-is

`fa` should preserve, not redesign: the **three adversary perimeters** with typed
`deferred_findings` targeted at a receiving gate; **brownfield's strict-binary novelty rule** and its
anti-fabrication clause ("fabricating findings is strictly worse than stopping"); the **coverage audit
that novelty decay structurally cannot replace** ("make it prove coverage with greps" — it found blind
spots in 5 of 5 repos after 19–62 rounds); the **two-phase validation split** with its
`(claimed, recounted, delta)` arithmetic where any non-zero delta is an error; **L4 immutability** with
`amends:` refinement and withdrawal-in-place; **append-only traceability** with
`# Existing chain (DO NOT MODIFY)`; the **L0–L4 readiness routing** that refuses to assume the human
arrives with a finished brief; **regression always full, never delta-scoped**; **"fast revocation,
slow promotion"** on autonomy; the **release mandatory-invariants table** where each rule carries its
failure mode, and its escalation contract ("do not improvise on the release pipeline"); the
**gate presentation protocol** with structured questions, on the stated grounds that "the
user-as-senior-architect catches things the adversary doesn't"; and the **budget tiers** that never
downgrade the adversary, holdout-evaluator, formal-verifier, pr-reviewer or security-reviewer.

---
