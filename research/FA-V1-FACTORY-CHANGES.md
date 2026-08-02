---
title: FA-V1-FACTORY-CHANGES — the change spec for ~/Dev/vsdd-factory
date: 2026-08-02
purpose: a change spec for the vsdd-factory repo precise enough that a separate workstream can execute it without re-deriving anything
status: SPEC. Nothing in ~/Dev/vsdd-factory was modified — 0 files written, no branch created. Every claim is cited to file:line, re-measured today.
authority: FA-V1-DESIGN V-E — "this workstream builds `fa` only; the vsdd-factory changes are DOCUMENTED here, not made"
sequences_against: research/FA-V1-MIGRATION.md (the four-stage per-type ladder these changes are keyed to)
---

# Changing vsdd-factory so `fa` can be the sole home

`fa` cannot become the source of truth while 72 skills write `.factory/**` with the Write tool, 63
hooks police the markdown form, and the type vocabulary lives in three files that disagree. This is
the list of changes to `~/Dev/vsdd-factory/plugins/vsdd-factory`, organized by artifact, each with
**files · what changes · why (cited) · what breaks if it is not done**, and a SEQUENCING section
keyed to the migration's four cutover stages.

**Path roots used throughout:**

```
PLG    = ~/Dev/vsdd-factory/plugins/vsdd-factory
AG     = PLG/agents
WF     = PLG/workflows
CRATES = ~/Dev/vsdd-factory/crates
LIVE   = ~/Dev/vsdd-factory/.factory        (git worktree, branch factory-artifacts @ 0aaba144)
```

## 0. Corrections to the review, measured today — read these before executing anything

The review is the input to this spec, and re-measuring it moved seven numbers and falsified five
premises. An executor working from the review alone would spend time on files that do not exist.

| the review said | measured today |
|---|---|
| "all 34 agent files point at `../../FACTORY.md`" | **30 of 34** agent files, plus `AG/orchestrator/orchestrator.md:53`, `PLG/skills/agent-file-review/SKILL.md:50` and `PLG/templates/agents-md-template.md:19` = **32 files**. Five agents carry no pointer: `adversary`, `codebase-analyzer`, `holdout-evaluator`, `research-agent`, `validate-extraction`. |
| "`VSDD.md` does not exist anywhere" | **it exists** at `PLG/docs/VSDD.md`. Both pointers are wrong by *path*, not by target: `../../FACTORY.md` from `AG/` resolves to `plugins/FACTORY.md`; the correct form is `../docs/FACTORY.md`, which the `AGENT-SOUL.md` footer already uses correctly in 33 of 34 files. |
| "19 agents declare direct `.factory/` writes" | **22** agent files, 33 declared write sites (§3.5). |
| "62 registered hooks" | **63 `[[hooks]]` blocks / 61 distinct names** (`worktree-hooks` and `protect-secrets` are each registered twice). Split: **35** via `legacy-bash-adapter.wasm`, **28** native WASM. The registry's own header (`PLG/hooks-registry.toml:8-9`) claims "21 native + 35 legacy" = 56 — **stale by 7**. |
| "~20 broken/nonexistent path references" | **47 distinct** broken references, because `PLG/docs/FACTORY.md:667-688` is a 20-row migration table that is unverifiable in *both* columns. |
| "`hooks/validate-artifact-path.sh`" | there is no such bash hook. Path enforcement is **WASM**: `CRATES/hook-plugins/validate-artifact-path/src/lib.rs` (670 lines) → `PLG/hook-plugins/validate-artifact-path.wasm`. |
| "pr-manager is denied `exec` so every `gh pr view` is a sub-agent dispatch" | **stale**: `AG/pr-manager.md:41` mandates delegation and all five `gh` sites (`:139,182,200,217,236`) are already wrapped in `Agent(subagent_type="vsdd-factory:github-ops", …)`. Do **not** "fix" this. Same for `AG/pr-reviewer.md:42`, `AG/session-reviewer.md:68`, `AG/research-agent.md:178`. |
| "5 bash helpers" (FA-V1-DESIGN V-B) | **13 files in `PLG/bin/`** (§6). 7 are keepers (the observability set), 2 have data sources that do not exist, and 4 are direct retirement targets. "5" undercounts the surface by 8. |
| `hooks/factory-lock-write.sh`, `hooks/resolve-worktree-identity.sh`, `hooks/factory-cas-push.sh`, `scripts/commit-to-artifacts.sh` | **none exist.** Zero occurrences of the string `factory-lock` under `PLG/`. `PLG/scripts/` does not exist. Skills `factory-lock`, `factory-unlock`, `wave-handoff`, `rehydrate-wave`, `wave-reset` have **no directory** under `PLG/skills/` — they are advertised commands with no implementation, living only in the operator cache at `~/.claude/plugins/cache/claude-mp/vsdd-factory/1.0.0-rc.23/`. **This is the review's own Area-4 caveat, confirmed: `develop` has no lock and no wave-handoff.** |
| — (not in the review) | `PLG/templates/verify-sha-currency.sh` is a **template, not an installed hook**. `LIVE/hooks/` contains only `dim2-gates/`. `skills/state-burst/SKILL.md:136,165` invokes `bash .factory/hooks/verify-sha-currency.sh`, and `validate-wave-gate-prerequisite.sh:64-69` fail-opens when it is absent — so **every SHA-currency gate in the live factory is already a no-op.** |

Two corrections make work *smaller* (pr-manager, and five nonexistent files), and five make it
larger. Net: fewer surgical fixes, more retirements.

---

## 1. Templates → registry schema declarations

### 1.1 The defect, measured

| | measured |
|---|---|
| template files | **136** (`PLG/templates/`, recursive) — 100 `.md`, 25 `.yaml`, 7 `.json`, 1 each `.ts` / `.tape` / `.sh` / extensionless (`project-justfile-template`). *Re-counted: a first pass reported 120 by missing 16 non-`.md` files, so the non-`.md` retirement set in T-8 is 36, not 20.* |
| `.md` templates carrying `document_type:` | **85 of 100 (85%)** |
| distinct `document_type` values declared | **81** |
| `.md` templates with **no** `document_type` | **15** — including `state-manager-checklist-template.md`, the *normative* burst checklist referenced by `skills/state-burst/SKILL.md:71` |
| `artifact_type` entries in `PLG/config/artifact-path-registry.yaml` | **46**, every one `enforcement_level: block` |
| **`template:` key in the path registry** | **does not exist.** There is *zero* declared linkage between the 46 artifact types and the 136 templates. |
| artifact types with **no** template | **35 of 46** |
| template `document_type` values with **no** registered artifact type | **70 of 81** |
| the intersection | **11** |

Three templates, three incompatible ways of declaring what is mandatory:

- `PLG/templates/behavioral-contract-template.md` — silence means required, plus a `(Recommended)`
  **suffix in the heading text** (`:97`, `:103`, `:109`, `:115`), plus conditionality in a heading
  (`:123` "include only when `origin: brownfield`"), plus enums as pipe-separated YAML comments
  (`:12` `greenfield|brownfield`, `:17` `active | deprecated | retired | removed`), plus
  required-vs-optional in prose (`:13` "brownfield only, omit for greenfield").
- `PLG/templates/adversarial-review-template.md` — silence means required; the finding-ID grammar is
  prose + bullets (`:20-31`) rather than a regex, and `:23-24` makes the cycle segment conditional on
  a **filesystem** fact (`.factory/current-cycle` existing).
- `PLG/templates/story-template.md` — an explicit `(MANDATORY)` suffix on 6 headings
  (`:116,130,144,154,163,173`), `(Required only for UI stories)` on `:84`, `(DF-037, UI stories
  only)` on `:90`, and optionality declared in **YAML comments** (`:22` "Planning extensions
  (optional — v1.1)", `:27` "ASM/R traceability (optional)"). `:31` puts a whole enum and its
  semantics into a trailing comment (`tdd_mode: strict  # strict | facade …`), and the default-value
  rule lives in a **blockquote** at `:34`.

### 1.2 The change

| # | files | what changes | why | what breaks if not done |
|---|---|---|---|---|
| **T-1** | all 100 `.md` templates | Each template's frontmatter list and mandated sections become **declarations in `fa`'s artifact type registry** (`required_fields`, `enums`, `section_schema`, `key`, `authority`, `shape`). The template file is deleted; `fa render` generates the human document from the schema. | FA-V1-DESIGN §4.3. "The template and the validator disagree" becomes unrepresentable. | The 15 templates with no `document_type` stay unvalidatable, and `validate-template-compliance.sh` keeps **exiting 0 when no template matches** — which is a live gate bypass: choosing a variant spelling silently skips the structure gate. |
| **T-2** | `PLG/config/artifact-path-registry.yaml` | **Merge into the type registry.** Path + shape become one declaration per type; `artifact_type` and `document_type` become one vocabulary. | CHANGE-MANAGEMENT §1's recommended option, and the measurement now settles it: with no `template:` key, the two files **cannot be joined programmatically at all**, so a mapping table would be a third thing to drift. | 35 artifact types keep having no template and 70 template types keep having no registered path. Every write of `product-brief`, `story`, `holdout-scenario`, `wave-schedule`, `burst-log`, `red-gate-log`, `convergence-report`, `traceability-matrix`, `module-criticality` or any `prd-supplement-*` has **no canonical path** while the path hook is declared `block`. |
| **T-3** | registry `section_schema` per type | One machine-readable mandatoriness vocabulary: `required` / `recommended` / `conditional(predicate)`. The three dialects above collapse into it. | §1.1. Two shipped validators (`PLG/bin/validate-template-compliance.sh` and `PLG/hooks/validate-template-compliance.sh` — a **name collision**, two unrelated scripts) must infer required-ness heuristically today. | Structure checks stay heuristic, and the `*INDEX*` exemption at `PLG/hooks/validate-template-compliance.sh:63` keeps hiding the four STORY-INDEX schemas and the `Depends-On` typo. |
| **T-4** | registry `key` + `key_source` per type | Natural keys become typed values (`BC-S.SS.NNN`, `VP-NNN`, `S-N.MM`, `E-N`, `ADR-NNN`, `CAP-NNN`, `HS-NNN`), and **filename patterns move into the registry with per-project overrides**. | Migration §5 P3. Measured cost of hardcoding: `fa/corpus.go:138` `^(VP-\d+)` is case-sensitive and prism names all 80 of its VPs `vp-001-*.md`. | A path-coupled extractor keeps missing whole layers of a project, and `{placeholder}` keeps matching any whole segment — which is how `BC-2.02.013-host-run-subprocess.md` passes the path hook while violating its own natural key. |
| **T-5** | `PLG/templates/architecture-index-template.md:12,27-34,38-40` | The 8 hardcoded architecture section filenames are deleted; the schema declares `architecture-section` keyed by subsystem. | The 8 files **do not exist**; disk uses `SS-NN-*.md` (11 of them, including a duplicate `SS-03` ordinal). `PLG/rules/spec-format.md:45` is the only doc that matches disk. | `AG/architect.md:39` and `WF/greenfield.lobster:372,386,396` keep instructing agents to load files that have never existed. |
| **T-6** | `PLG/templates/adversarial-review-template.md:20-31` | The finding-ID grammar becomes a registry regex, and IDs are **minted by `fa`**, not typed. Remove the filesystem-conditional segment. | `:29` sanctions `ADV-P01-MED-003`, which `PLG/hooks/validate-finding-format.sh:60-62` **blocks as legacy**. The template and the hook disagree about the canonical form. | ~14 finding ID families persist; the dominant `F-*` family (>13,000 occurrences) stays uninspected while a prescribed form stays blocked. |
| **T-7** | `PLG/templates/agents-md-template.md:19,124` | Fix the `../../FACTORY.md` pointer to `../docs/FACTORY.md`; delete `:124` ("Must exactly match this agent's configuration in openclaw.json") and replace it with a pointer to the role→operation manifest (§3.1). | `:124` is the **root cause** of 29 agents having prose profiles and no `tools:` key — the template pointed authors at an OpenClaw config as the source of truth and the migration to Claude Code frontmatter never happened. | Every new agent file reproduces the same two defects. |
| **T-8** | `PLG/templates/` — the 36 non-`.md` files | `autonomy-config-template.yaml`, `merge-config-template.yaml`, `wave-state-template.yaml`, `policies-template.yaml`, `reference-manifest-template.yaml`, `project-manifest-template.yaml` become `fa` config schemas with `shape: config`. | None of their instantiations exists in `LIVE`: `merge-config.yaml`, `autonomy-config.yaml` and `wave-state.yaml` are all absent, so **autonomy is undefined at runtime** and three hooks target a file that was never created. | The five-tier budget response, both autonomy axes and every wave-state hook stay inert. |

**Do not** delete `PLG/templates/adversary-prompt-templates/` in this pass: those are prompt inputs,
not artifact schemas.

---

## 2. The 2 namespace renames that close story 1

| # | file:line | change | why | what breaks if not done |
|---|---|---|---|---|
| **N-1** | `PLG/config/artifact-path-registry.yaml:63` | `artifact_type: story-spec` → `artifact_type: story` | `namespace_reconciliation` in the type registry: 2 name disagreements between the 46-name path vocabulary and the 81-name template vocabulary. The template declares `document_type: story` (`PLG/templates/story-template.md:2`). | `registry/validate_registry.py` prints **`EXIT CRITERION NOT MET: 2 name disagreement(s) remain`** — verified today. Story 1 cannot close, and story 1 gates the registry's adoption as a policy. |
| **N-2** | `PLG/config/artifact-path-registry.yaml:131` | `artifact_type: state` → `artifact_type: pipeline-state` | same; the template declares `document_type: pipeline-state`. Note `:136,:141,:146` (`state-runtime-*`) are **not** renamed — they are distinct types. | same. Also: `state` is the artifact type of `.factory/STATE.md` itself and it is one of the 35 with no template, so it is doubly invisible to any `document_type`-keyed check. |

Both are one-line edits. An earlier cut of the registry used one boolean for three different
namespace defects and so overstated this as 17; it is **2**, and only these two are name
disagreements. `git grep -n 'story-spec'` and `git grep -n "artifact_type: state$"` before and after
— the count must go 1 → 0 for each, and no other file may reference the old names.

**These two edits are BLOCKED ON THE USER** (write access to vsdd-factory). They are the smallest
unblocking change in this entire spec.

---

## 3. Agent definitions

### 3.1 `## Tool Access` prose → a role→operation-set manifest

**Measured:** 34 agent `.md` files under `AG/` + 10 under `AG/orchestrator/`. **Only 5 carry a
`tools:` frontmatter key** — `adversary.md:4` (`Read, Grep, Glob`), `codebase-analyzer.md:5`,
`holdout-evaluator.md:4` (`Bash, Read`), `research-agent.md:4`, `validate-extraction.md:4`. The
other **29 run with all tools**, so every `Denied:` line in them is unenforced documentation.
`AG/orchestrator/orchestrator.md` has **neither a `tools:` key nor a `model:` key**, while
`:374-377` declares `Denied: write, edit, apply_patch, exec, process` and `:101` says "You NEVER
write ANY files".

| # | files | change | why | what breaks if not done |
|---|---|---|---|---|
| **A-1** | all 44 files; `## Tool Access` at the line numbers in the table below | Delete the prose section. Replace with a single machine-readable manifest keyed by role → permitted **`fa` operations** (not tools, not path globs). `fa` receives an unforgeable role token and refuses operations outside the role's set. | F16. The audit that was supposed to catch profile mismatches reads `openclaw.json` (`PLG/skills/agent-file-review/SKILL.md:95`) — **which has never existed** (§3.4). So the check has always silently no-opped. | 29 agents keep running with all tools; the walls stay soft, which `PLG/docs/FACTORY.md:464-466` already concedes: "Soft instructions alone are insufficient for wall enforcement." |
| **A-2** | the manifest | `model:` moves in too. Measured: 40 of 44 pin a Claude model (`opus` ×7, `sonnet` ×33); `AG/orchestrator/orchestrator.md` pins none. | `PLG/docs/FACTORY.md:403` says the adversary is "NEVER Claude" and `WF/phases/phase-4-holdout-evaluation.lobster:33` makes "different model family (GPT-5.4, not Claude)" a **blocking gate criterion**. The 23 `model_tier:` keys in `.lobster` have no resolver. | A blocking gate keeps depending on a claim every agent's frontmatter falsifies. `fa attest` has nothing to attest against. |

`## Tool Access` line numbers, for the executor (`AG/`): accessibility-auditor 261 · adversary 320 ·
architect 408 · business-analyst 132 · code-reviewer 137 · codebase-analyzer 420 ·
consistency-validator 274 · data-engineer 111 · demo-recorder 121 · devops-engineer 360 ·
dtu-validator 116 · dx-engineer 222 · e2e-tester 209 · formal-verifier 239 · github-ops 114 ·
holdout-evaluator 90 · implementer 336 · performance-engineer 158 · pr-manager 313 · pr-reviewer 187 ·
product-owner 437 · research-agent 171 · security-reviewer 240 · session-reviewer 198 ·
spec-reviewer 175 · spec-steward 218 · state-manager 410 · story-writer 436 · stub-architect 166 ·
technical-writer 61 · test-writer 329 · ux-designer 170 · validate-extraction 143 ·
visual-reviewer 168 · orchestrator/orchestrator 372.

### 3.2 The walls become DENIED return codes

Walls are declared at `PLG/docs/FACTORY.md:442-466` — note the table at `:449-458` **declares seven
walls and lists eight rows** — and mechanically enforced by `context.exclude` blocks in
`WF/*.lobster`. Measured state:

| # | files | change | why | what breaks if not done |
|---|---|---|---|---|
| **A-3** | the 8 walled agent files + every dispatch site in `WF/*.lobster` | A wall becomes a store-side read gate keyed to **artifact type**, not path spelling. `fa read` returns `DENIED_BY_WALL` instead of bytes. `fa walls verify` audits every dispatch site of every walled role. | The wall coverage is partial and one wall is inverted — three confirmed instances below. Also, walls keyed to paths cannot work when the same artifact class is spelled four ways across workflows and none of the spellings is in the path registry. | Session-review's Dimension 6, literally "did the information asymmetry walls hold?", stays unanswerable. |
| **A-4** | `WF/greenfield.lobster:871-878` | Add the missing wall — or delete the dispatch and route through the store gate. | **CONFIRMED: the holdout-evaluator dispatch has NO `context:` block at all.** The steps immediately above (`:865-868`) and below (`:881-888`) both have one. `WF/feature.lobster:858-862` and `WF/multi-repo.lobster:391-401` prove the authors knew how; greenfield was simply missed. | The strictest wall in the system (`FACTORY.md:451`, "ML-style train/test separation") has zero structural enforcement in the reference workflow — at exactly the wave gate. |
| **A-5** | `WF/greenfield.lobster:286` | Delete `- ".factory/specs/adversarial-reviews/**"` from the `include:` list of `spawn-adversary-spec-review` (`:266-289`). | **CONFIRMED: the wall is INVERTED.** That glob sits inside `include:`, and the step is a loop with `max_iterations: 10` (`:263`), so pass N is handed passes 1..N−1 — the exact thing `AG/adversary.md:22` forbids. Contrast `:1093`, where the Phase-5 adversary *excludes* the same glob. | Fresh-context adversarial review is not fresh in Phase 1d, and the novelty metric computed from it is meaningless. Also `WF/greenfield.lobster:441-450` (Phase 2) excludes only `holdout-scenarios/**`, so prior story reviews leak there too. |
| **A-6** | `WF/greenfield.lobster:312-317` and `:514-520` | The spec-reviewer wall is `include: .factory/specs/**` (`:314`), which **admits** `adversarial-reviews/`; the `exclude:` (`:317`) is only `cycles/**/implementation/**`. Fix or replace with the store gate. | `AG/spec-reviewer.md:192` forbids reading `.factory/specs/adversarial-reviews/` while `:55` writes `spec-review-pass[N].md` **into that same directory**, and `:167-173` declares a completely different wall, ending with "You **CAN** see all spec and story artifacts". | Three contradictory wall declarations for one agent, none enforced. |
| **A-7** | `WF/greenfield.lobster:717-719`, `WF/code-delivery.lobster:283`, `:339`, `WF/multi-repo.lobster:454-455` | The pr-reviewer `exclude: .factory/**` must become a type-scoped deny that still permits its own output. | **CONFIRMED and self-defeating.** It is the only wall enforced in all four workflows, and it blocks the agent's own declared **output** (`AG/pr-reviewer.md:57,124`) and **input** (`:134,139` pass `--body-file …/pr-review.md` to `gh pr review`). `AG/pr-manager.md:299` and `WF/greenfield.lobster:743-747` then consume that path. | The one perfectly-enforced wall makes its agent's contract unexecutable. Under `fa`, `pr-review-findings` is a typed artifact the role may write and not read back — which is what the wall actually meant. |
| **A-8** | `WF/greenfield.lobster` (accessibility-auditor) | Add the a11y wall, present in `WF/feature.lobster:881-884`, `WF/maintenance.lobster:230-233`, `WF/multi-repo.lobster:440-442`. | `AG/accessibility-auditor.md:75-78,278` declares it; greenfield has no a11y step with an exclude, inverting `FACTORY.md:462`. | The declared wall coverage claim is false for the reference path. |

Keep, unchanged: `AG/dtu-validator.md:123-126` and `AG/session-reviewer.md:82-84`, which correctly
declare **no** wall. An explicit "no wall" is a design statement and must survive.

### 3.3 The agents whose declared profile cannot do their declared job

Of the review's 10, **8 hold**, 1 is stale, and re-measuring found **2 new** — one of them the worst
in the corpus.

| agent | denial | the instruction it cannot obey | verdict |
|---|---|---|---|
| **orchestrator** | `AG/orchestrator/orchestrator.md:376-377` `Denied: write, edit, apply_patch, exec, process`; `:101` "You NEVER write ANY files" | `:40` "**Write progress back to `.factory/STATE.md`** after each step"; and `WF/phases/phase-4-holdout-evaluation.lobster:16-21` dispatches `agent: orchestrator` to "**Write** selected scenario IDs to `.factory/holdout-evaluation/scenario-selection.json`" | **NEW — most severe.** A flat self-contradiction 336 lines apart, plus a workflow that dispatches the scheduler to itself as a doer. |
| **consistency-validator** | `:279` `Denied: exec, process` | `:337` criterion 77 "(git history check if available)"; `:187` criterion 33 "no git tag on factory-artifacts" | **NEW.** 2 of its 77 mandated criteria require git. |
| **holdout-evaluator** | `:4` `tools: Bash, Read`; `:94` `Denied: Write, Edit, Glob, Grep` | `:64` "Write to `.factory/holdout-scenarios/evaluations/`"; `:40` "Read all scenario files from …" (needs Glob) | **holds**, and no delegate is named. Note the wall is *also* unsound the other way: `Bash` is granted, so it can `cat src/**` and `> file`, defeating `:22-27`. Only a store-side read gate closes that. |
| **adversary** | `:4` `tools: Read, Grep, Glob`; `:324` `Denied: Write, Edit, Bash…` | `:100` "Write findings to `.factory/cycles/<current>/adversarial-reviews/`", **plus three Lobster task strings**: `WF/greenfield.lobster:273-274`, `:439-440`, `:1074-1075` | **holds, partly mitigated** at `:326` ("findings returned as chat text; state-manager persists"). The Lobster task strings are the harder defect and the review missed them. **392 corpus files carry `producer: adversary`.** |
| **story-writer** | `:440` `Denied: exec, process` | `:443` "run `compute-input-hash <file> --update`" (has an escape hatch) and **`:534` "run `ls <destination-directory>`" (no escape hatch)** | **holds — strongest of the four `compute-input-hash` cases.** |
| **technical-writer** | `:64` `Available: read, write, edit, apply_patch`; `:65` `Denied: exec, process` | `:41` inputs are "Source code with type signatures and doc comments (`src/`)" — no search tool granted; `:50` "Changelogs reflecting actual implemented changes" — needs git | **holds.** Also `:36`/`:49` say output goes to `.factory/` **or `docs/`** while `:67` says "under `.factory/`" only. |
| **product-owner** / **architect** / **business-analyst** | `:441` / `:412` / `:136` `Denied: exec, process` | `:444` / `:415` / `:139` "run `compute-input-hash <file> --update`" | **hold (soft)** — each supplies "(or ask state-manager to run it)". All three vanish with `input-hash` (§6, story 9). |
| **spec-reviewer** | `:179` `Denied: exec, process` | no shell-requiring instruction found | **stale as a shell mismatch.** The real defect is A-6's wall/output collision. |
| **pr-reviewer** | `:191` `Denied: exec, process` | `:41,43,130` "MUST post your review via `gh pr review`" | **stale** — `:42` mandates delegating to github-ops and `:134,139` show the correct `Agent(...)` form. The real defect is A-7. |
| **pr-manager** | `:317` `Denied: exec, process` | `:139,182,200,217,236` `gh` calls | **stale — do not touch.** All five are already wrapped in `Agent(subagent_type="vsdd-factory:github-ops", …)`; `:41` states the rule; `:320` grants the Agent tool. |

| # | files | change | why | what breaks if not done |
|---|---|---|---|---|
| **A-9** | the 10 files above | Reconcile each profile against its job **in the manifest**, not in prose. Under `fa` the write instructions become `fa` operations the role either has or does not have, and the mismatch becomes a `fa doctor` failure rather than an inconsistency nobody can run. | §3.3. Two agents already model the fix correctly and should be cited as the pattern: `AG/stub-architect.md:171` ("Do NOT write to `.factory/` — state-manager owns those paths") and `AG/session-reviewer.md:68`/`AG/research-agent.md:178`. | Ten agents keep carrying instructions they cannot execute, which is indistinguishable from an agent that fails silently. |

### 3.4 `openclaw.json` — 14 references to a file that has never existed

`find` across the repo (excluding `target/`) returns **zero** files matching `openclaw*`.
References: `PLG/skills/agent-file-review/SKILL.md:14,27,95` · `PLG/docs/FACTORY.md:14,35,118,402,439,742,922,1041` ·
`PLG/templates/agents-md-template.md:124` · `PLG/skills/phase-1d-adversarial-spec-review/SKILL.md:18` ·
`WF/multi-repo.lobster:128`.

| # | files | change | why | what breaks if not done |
|---|---|---|---|---|
| **A-10** | the 5 files above | Delete every reference. `agent-file-review` check 8 re-points at the §3.1 manifest; `FACTORY.md:35` and `:118` lose the OpenClaw workspace lines; `WF/multi-repo.lobster:128` loses "Generate openclaw.json workspace configuration". | `agent-file-review/SKILL.md:14` states its existence as a **precondition** that is false, and `:95` is the step that was meant to catch every tool-profile mismatch. | The audit designed to prevent §3.1 and §3.3 keeps no-opping, and `FACTORY.md` keeps describing a fleet configuration format the factory does not use. |

### 3.5 The 22 agent files that declare direct `.factory/` writes

`PLG/docs/FACTORY.md:477` says "state-manager owns `.factory/` branch"; `:486` says "All `.factory/`
commits come from state-manager". The distinction that makes the methodology coherent — *write
freely, only state-manager commits* — is stated in exactly one of 44 files.

`AG/accessibility-auditor.md:227` (+ shell redirects `:201,204,207`) · `adversary.md:100` ·
`architect.md:220,283` · `business-analyst.md:152` · `codebase-analyzer.md:416` ·
`consistency-validator.md:125` · `dtu-validator.md:91` · `formal-verifier.md:200` ·
`holdout-evaluator.md:64` · `implementer.md:278,284` · `performance-engineer.md:131` ·
`pr-manager.md:106,299` · `pr-reviewer.md:57,124` ·
`research-agent.md:21,28,35,176` (**three conflicting path sets in one file**) ·
`security-reviewer.md:124` · `spec-reviewer.md:55,56` · `story-writer.md:538` ·
`technical-writer.md:36,49` · `test-writer.md:102,241` · `ux-designer.md:182` ·
`validate-extraction.md:94,148` · `visual-reviewer.md:151`.

| # | files | change | why | what breaks if not done |
|---|---|---|---|---|
| **A-11** | those 22 files | Every declared path is replaced by an `fa` operation. **An agent never names a `.factory/` path** — `fa path resolve <type> <ids>` computes it. | F17. 16+ of these declared targets are **unregistered** in the path registry, which is declared `block`: `holdout-scenarios/**`, `specs/adversarial-reviews/**`, `cycles/**/hardening/**`, `ui-evidence/**`, `demo-evidence/**`, `dtu-clones/**`, `phase-0-ingestion/**` (which *exists on disk* with 20 real files), `planning/**`, `prd-supplements/**`, `ux-spec/**`, `cost-summary.md`, `session-reviews/`. | ~28 unregistered artifact homes stay hard-blocked-in-theory and silently-written-in-practice; 225 of 3,145 files keep matching no pattern; the path stays something an agent types. |
| **A-12** | `AG/state-manager.md` | Not a violation — it is the designated owner (`:32`, `:395`). Under `fa`, state-manager becomes the role holding the `commit` capability, and its four write paths (§6) become `fa` transactions. | `FACTORY.md:477`. | — |
| **A-13** | `AG/demo-recorder.md:38,160` | Keep. These are **prohibitions** and get the direction right. Only re-point `docs/demo-evidence/` per the D-8 path conflict (§7). | — | — |

### 3.6 The broken `../../FACTORY.md` pointer in 30 agent files (+2 more)

| # | files | change | why | what breaks if not done |
|---|---|---|---|---|
| **A-14** | 30 agent files + `AG/orchestrator/orchestrator.md:53` + `PLG/skills/agent-file-review/SKILL.md:50` + `PLG/templates/agents-md-template.md:19` | `../../FACTORY.md` → `../docs/FACTORY.md`; `../../VSDD.md` → `../docs/VSDD.md`. From `AG/orchestrator/`, both need `../../docs/`. | From `AG/`, `../../FACTORY.md` resolves to `plugins/FACTORY.md`, which does not exist; the real files are `PLG/docs/FACTORY.md` and `PLG/docs/VSDD.md`. **`VSDD.md` does exist** — the review was wrong about that. 33 of 34 agents already use the correct `../docs/AGENT-SOUL.md` form, so the fix is a known-good pattern. | Every agent's "Global Operating Rules" line silently resolves to nothing, so the factory-wide constraints are never loaded. |
| **A-15** | same files, `../../templates/` | Same fix: → `../templates/`. Sampled sites: `AG/architect.md:39,40,41,43,95,97,103,220,284` · `ux-designer.md:97,188,189,190,212-215` · `code-reviewer.md:31,42,67,135` · `technical-writer.md:34,43,55,59` · `security-reviewer.md:44,216` · `devops-engineer.md:176,375,376,377` · `performance-engineer.md:172` · `e2e-tester.md:232` · `spec-steward.md:233` · `state-manager.md:424,425` · `story-writer.md:458-461` · `product-owner.md:461,462` · `AG/orchestrator/orchestrator.md:381-383` | Same bug class, wider blast radius: `plugins/templates/` does not exist. | Every template reference in every agent file is dead — which under T-1 is moot, but until T-1 lands it means agents author from memory. |
| **A-16** | `AG/stub-architect.md:190` | `../../docs/AGENT-SOUL.md` → `../docs/AGENT-SOUL.md` | The one file of 34 that gets this wrong. | — |

Exclude from A-14: `adversary.md`, `codebase-analyzer.md`, `holdout-evaluator.md`,
`research-agent.md`, `validate-extraction.md` — they carry no pointer at all, which is its own gap
(they never load the global rules) and should be fixed by *adding* the correct line.

### 3.7 `producer:` becomes a closed enum

**Measured in `LIVE`:** 24 distinct raw values / 22 after normalization, 2,349 occurrences.
**8 values are not names of agent files, covering 1,228 occurrences — 52% of the corpus.**

| value | count | note |
|---|---|---|
| `phase-1-4b-bcs-agent-4` | 330 | ad-hoc parallel-shard worker id |
| `phase-1-4-b-bcs-agent-10` | 215 | |
| `phase-1-4b-agent-8` | 207 | |
| `PHASE_1_4_B_BCS_AGENT_9` | 192 | SCREAMING_SNAKE variant |
| `phase-1-4b-bc-extractor` | 167 | |
| `phase-1-4b-agent-5` | 115 | |
| `state-manager-stub` | 1 | a placeholder that shipped |
| `adversarial-reviewer` | 1 | near-miss for `adversary` |

All six shard ids live under `LIVE/specs/behavioral-contracts/ss-NN/`, in **four incompatible naming
schemes**, and **no BC anywhere carries `producer: product-owner`** even though
`PLG/docs/FACTORY.md:474` names product-owner as the BC producer. So BC provenance is untraceable to
an agent for the majority of the largest artifact type. Separately, `codebase-analyzer` appears
**428× bare and 197× double-quoted**, so any exact-string provenance query undercounts by 32%.

| # | files | change | why | what breaks if not done |
|---|---|---|---|---|
| **A-17** | the registry `producer` enum; `PLG/skills/agent-file-review/SKILL.md` | `producer:` becomes a closed enum derived from `basename(AG/**/*.md)`, and **`fa`'s audit row replaces the hand-typed field entirely** (F18: `{role, lease, scope, txn, before/after version, reason}`). | 1,045 `agent.start` events already carry a `subagent` field (353 adversary, 251 state-manager, 166 product-owner) — dispatch identity *is* captured and then dropped before any write. `hook.block` (7,761) and `commit.made` (373) carry no agent field, and `CRATES/hook-plugins/track-agent-start/src/lib.rs:19` explicitly **forbids** an `agent_id` field. | Provenance stays a hand-typed string with 8 non-agent values and 4 naming schemes, and "did the walls hold?" stays unanswerable. |

---

## 4. Skills that write `.factory/**` directly

**Measured: 72 of 121 skill directories** issue at least one direct filesystem write naming a
`.factory/` target. **None routes through state-manager.**

*The extraction rule, stated because the count depends on it:* a skill counts if a `SKILL.md` or a
referenced `steps/*.md` contains an instruction to **Write / Edit / append / `tee` / `mkdir` /
`git mv` / shell-redirect** to a path beginning `.factory/`. It does **not** count a skill that
merely *reads* such a path, names it in prose, or asserts it as a precondition — by the looser rule
"mentions `.factory/` anywhere", the count is **105 of 121**, and that number would be useless for
deciding what to change. The 72 are enumerated below by group; the change is uniform within a group.

| # | group (skill count) | representative sites | change | what breaks if not done |
|---|---|---|---|---|
| **S-1** | **specs** (14) | `create-brief/SKILL.md:79,130` · `create-domain-spec:105` · `create-prd:71,79,86,96,137` · `create-architecture:143` · `create-adr:214,215,216` · `phase-f2-spec-evolution:39,40,67,77,92,93,105,106,129,159` + `steps/step-02..06` · `phase-1-prd-revision:15` · `spec-versioning:57,93` · `spec-drift:54` · `create-story:107` | replace with `fa new|set` per type (`product-brief`, `domain-spec-section`, `prd`, `prd-supplement-*`, `architecture-section`, `adr`, `story`, `spec-changelog`) | `create-prd:71,79,86` writes into `.factory/specs/prd-supplements/`, which **does not exist** and has **no registry pattern** → three writes that the `block`-level path hook would refuse. `create-adr` is the only ID allocator in the factory and is explicitly non-atomic ("Users SHOULD serialize"). |
| **S-2** | **stories / waves / sprint state** (8) | `decompose-stories:71,80,95,120,124,136,154,159` + 3 step files · `phase-f3-incremental-stories:100,107,111,112` · `deliver-story:120,121` · `worktree-manage:39` · `register-artifact:22` · `relocate-artifact:73,76` | `fa new story`, `fa epic set`, and **indexes become derived** — `register-artifact` and `relocate-artifact` are deleted outright | `decompose-stories:71` writes the flat `.factory/stories/epics.md`, but disk has `stories/epics/` (a directory) and the registry pattern is `stories/epics/E-{epic-id}-{slug}.md` → blocked. `register-artifact` **mints nothing** (its only defence is a duplicate-*row* check), and `relocate-artifact` uses `.factory/specs/bc/BC-INDEX.md` while `validate-count-propagation.sh:67` uses `.factory/specs/behavioral-contracts/BC-INDEX.md` — **two path vocabularies for one file**. |
| **S-3** | **cycles / adversarial / convergence** (12) | `factory-cycles-bootstrap:66,102` · `convergence-tracking:96` · `convergence-check:88` · `formal-verify:135` · `perf-check:102` · `phase-f5-scoped-adversarial:124` + 3 steps · `phase-f6-targeted-hardening:47,61,82,96,109,142` + step · `phase-f7-delta-convergence:94,166` + 2 steps · `traceability-extension:94` · `deliver-story/steps/step-d5:37` · `phase-f4-delta-implementation:37,124` + 2 steps | `fa finding add`, `fa gate record --evidence`, `fa converge`, `fa trace` | `factory-cycles-bootstrap:102` writes `cycles/<cycle>/adversarial-reviews/pass-<N>.md`, and the registry's **only** adversarial-review pattern is the *flat* `cycles/{cycle-id}/adv-{slug}.md` (`PLG/config/artifact-path-registry.yaml:116`) — so the 94 real pass files under `adversarial-reviews/` match no pattern. `traceability-extension:94` and `phase-f7-delta-convergence/steps/step-03:8` declare `traceability-chain.md` a **precondition**; it exists nowhere, so F7 step 3 is unrunnable. |
| **S-4** | **state** (4, outside the state skills) | `recover-state:144` (full rewrite) · `run-phase:48` ("append a line with timestamp, phase, step, outcome") · `code-delivery:192` · `guided-brief-creation/steps/step-06:64` ("use the `state-update` skill **if available**") | all four route through `fa phase set` / `fa pipeline advance`; the optional-`if available` clause is deleted | Four writers of the single-writer artifact. `recover-state` emits `1a`/`1b`/`3.5` phase values that `check-state-health` rejects, so recover → health-check is a **guaranteed FAIL**. |
| **S-5** | **delivery / PR / demo** (5) | `code-delivery:81,192,193` · `pr-review-triage:60,74` · `record-demo:55,59` · `demo-recording:40,128,151,196,237,273,282-285` | `fa pr` (story ⇄ PR ⇄ CI ⇄ merge as one join) + `fa` demo-evidence artifacts | Merge prerequisites stay filenames rather than verdicts: the hook checks three files exist and satisfies "security review conducted" via a regex over a PR description **pr-manager writes itself**. Four of six declared per-story artifacts exist **zero** times. |
| **S-6** | **planning / discovery / intelligence** (13) | `guided-brief-creation:136,138` + 3 steps · `brainstorming:114` + step · `planning-research:48` · `validate-brief:129` · `implementation-readiness:125` · `artifact-detection/steps/step-01:56`, `step-04:18`, `SKILL.md:130` · `discovery-engine:107,122,174,190` · `analytics-integration:135` · `customer-feedback-ingestion:176,218` · `competitive-monitoring:120,148` · `intelligence-synthesis:171` · `post-feature-validation:139` | `fa new` per type; discovery artifacts get `inputs:`/`traces_to` as **typed edges** | `planning` is referenced 84× and the registry declares `plans`; `discovery` 69× and **`LIVE/discovery/` does not exist** while STATE.md records a completed sweep. `artifact-detection:130` writes `planning/gap-analysis.md`, which is the routing gate's **own exit criterion** and is unregistered. `competitive-monitoring:148` mutates `competitive-baseline.md` in place, so the baseline an insight was computed against is unrecoverable. |
| **S-7** | **feature-mode delta** (4) | `phase-f1-delta-analysis:137` + `steps/step-06:13,21,22` · `feature-mode-scoping-rules:94` · `quick-dev-routing:88` | the delta becomes a **declared scope predicate** (F7), not a text file | `affected-files.txt` is referenced 11× across F1/F5/F6, **does not exist**, is unregistered, and the real artifact is `LIVE/feature-delta/<id>/affected-files.md` — a different directory and a different extension. `phase-f2-spec-evolution:182` makes the nonexistent `phase-f1-delta-analysis/delta-analysis.md` a precondition, so **Phase F2 is unenterable as written**. |
| **S-8** | **ingestion / semport** (4) | `brownfield-ingest:78,82,121-154,284,344,368` + 6 steps · `semport-analyze:57,69,79` · `disposition-pass:62,121,134` · `multi-repo-phase-0-synthesis:34` | `fa new semport-artifact` / `recovered-architecture` / `extraction-validation` | `phase-0-ingestion` is referenced 39× with 20 real files on disk and is unregistered (a retired home, readable but frozen). `multi-repo-phase-0-synthesis:34` writes `project-context.md` — **the mode discriminator** — which is absent, so **feature mode is reachable only by human override** despite having run repeatedly. |
| **S-9** | **config / registries** (10) | `policy-add:50` · `policy-registry:37` · `release:135` · `toolchain-provisioning:80,186` · `track-debt:11,35` · `design-system-bootstrap:138` · `dtu-creation:65,77` · `dtu-validate:43` · `create-excalidraw:24` · `visual-companion/visual-guide.md:261,269` | `fa policy add` with transactional minting; `shape: config` types | `policy-add` uses `max_id + 1` with **name**-based collision defence, and reserved POLICY 11/12 slots are silently consumed by a third custom policy. `dtu-clones/` and `holdout-scenarios/` are both unregistered and absent. |
| **S-10** | **UI quality / maintenance / session review** (9) | `ui-quality-gate:126` · `ui-completeness-check:97` · `responsive-validation:94` · `ux-heuristic-evaluation:130` · `design-drift-detection:67` · `maintenance-sweep:30,31,34,37` (**shell `tee` redirects**) `,202` · `session-review:58` **and** `:107` | `fa finding add` with IDs, status and suppression; `fa baseline`/`fa ratchet` for the five "compare against last baseline" sweeps | Maintenance findings have **no ID, no status and no suppression**, so a false positive re-fires weekly forever and the session review's own goal ("sweep false-positive rate") is uncomputable. `session-review:58` writes directly while `:107` says state-manager writes — **contradictory in one file**. |

**The one skill that gets it right, and is still self-contradictory:**
`PLG/skills/adversarial-review/SKILL.md:143` explicitly declines Write access ("state-manager already
owns all `.factory/` commits") while `:104` still says "Write findings to
`.factory/cycles/<current>/adversarial-reviews/`". Fix `:104`; keep `:143` as the model sentence for
S-1..S-10.

---

## 5. Hook retirement ledger

**63 `[[hooks]]` blocks / 61 distinct names** in `PLG/hooks-registry.toml`; **35** route through
`legacy-bash-adapter.wasm`, **28** are native WASM. Events: PostToolUse 34 · PreToolUse 16 ·
SubagentStop 6 · Stop 2 · SessionStart/End 1 each · WorktreeCreate/Remove 1 each ·
PostToolUseFailure 1.

On disk, re-counted directly (a first pass reported 43 `.sh` and "~8 unregistered orphans including
`check-factory-commit.sh` and `verify-git-push.sh`" — **both of those are in fact registered**):
**35 `.sh` at the top level of `PLG/hooks/`**, of which the registry references **34 distinct
`script_path` values over 36 entries** (`hooks/protect-secrets.sh` is registered twice). So there is
exactly **one unregistered top-level orphan — `hooks/update-cargo-audit-cache.sh`**. A further
**12 `.sh` live in subdirectories** and are deliberately not registered: 11 in `hooks/dim2-gates/`
(the only hook directory that also exists in `LIVE/hooks/`) plus `hooks/lib/block.sh`. `PLG/hooks/`
holds 59 files in total, including the 5-platform `hooks/dispatcher/bin/*/factory-dispatcher`
binaries. `PLG/hook-plugins/` holds 43 `.wasm` with **12 duplicate underscore/hyphen name pairs**, of
which only the hyphen forms are referenced by the registry.

### 5.1 Retirement by cutover stage

| stage | retired | replaced by |
|---|---|---|
| **stage 1 — shadow** (nothing retired) | — | `fa validate --registry` runs **beside** every hook. Findings are baselined; no hook is touched. This is what makes stage 1 zero-risk. |
| **stage 2 — dual-write** | the 6 **structure/format** hooks for the migrated type only: `validate-template-compliance`, `validate-finding-format`, `validate-bc-title`, `validate-table-cell-count`, `validate-stable-anchors`, `validate-artifact-path` (per type) | write-time schema validation in `fa` (F5 + T-1). A closed enum validated at write time makes these unrepresentable rather than detected. |
| **stage 2** | the 5 **count/index** hooks: `validate-count-propagation`, `validate-index-cite-refresh`, `validate-index-self-reference`, `validate-state-index-status-coherence`, `validate-state-pin-freshness` | `fa index build` + `fa count` — derived, one canonical writer (F6). |
| **stage 3 — authoritative** | the 4 **state** hooks: `validate-state-structure`, `validate-state-size`, `validate-burst-log`, `validate-input-hash` | typed pipeline state as rows (F19) + derived staleness (F8). `validate-state-size` policed **four conflicting size budgets** (200/415/500) against a 27-line self-reported `wc -l` HTML comment. |
| **stage 3** | the 4 **branch/worktree** hooks: `factory-branch-guard`, `check-factory-commit`, `validate-factory-path-root`, `verify-git-push` | `fa`'s store-side leases + audit (F4 + F18) and scoped agent handles (F21). There is no orphan branch to guard. |
| **stage 3** | the 5 **convergence/gate** hooks: `convergence-tracker`, `validate-novelty-assessment`, `validate-wave-gate-completeness`, `validate-wave-gate-prerequisite`, `warn-pending-wave-gate` | `fa converge` computed from finding rows + `fa gate record --evidence` (F13 + F14). |
| **stage 3** | `update-wave-state-on-merge`, `regression-gate`, `red-gate`, `validate-red-ratio`, `validate-per-story-adversary-convergence`, `validate-dispatch-advance`, `validate-closes-completeness`, `validate-story-bc-sync`, `validate-subsystem-names`, `validate-vp-consistency`, `validate-anchor-capabilities-union`, `validate-trajectory-tail-cell-completeness`, `validate-policies-schema`, `validate-pr-description-completeness`, `validate-pr-merge-prerequisites`, `validate-pr-review-posted`, `pr-manager-completion-guard`, `handoff-validator`, `lint-registry-async-invariant` | `fa` gates as **queries** with mandatory evidence. Story↔BC sync (POLICY 8) is already **a JOIN** in `fa` producing 218 findings; subsystem names are an FK. |
| **stage 4 — md retired** | `validate-artifact-path` entirely; the whole `legacy-bash-adapter.wasm` route and its 35 entries; the 1 unregistered orphan `.sh`; the 12 duplicate `.wasm` pairs | — |
| **KEEP — never retire** | `session-start-telemetry`, `session-end-telemetry`, `session-learning`, `track-agent-start`, `track-agent-stop`, `tool-failure-hooks`, `capture-commit-activity`, `capture-pr-activity`, `worktree-hooks` (×2), `protect-secrets` (×2), `protect-bc`, `protect-vp`, `purity-check`, `brownfield-discipline`, `destructive-command-guard`, `block-ai-attribution` | These are **observability and guardrails**, not markdown policing. `track-agent-start` must gain the `agent_id` field its own crate currently forbids (`CRATES/hook-plugins/track-agent-start/src/lib.rs:19`). |
| **NEW** | — | one `PreToolUse` hook: `validate-artifact-type` calling `fa validate --registry` on the single file being written (CHANGE-MANAGEMENT story 13), and a **deny** arm on `Edit|Write` for any type at stage ≥2 (M8). |

### 5.2 The five broken hooks the review named — exact defects, re-measured

**`PLG/hooks/validate-wave-gate-completeness.sh`** (134 lines; registry `:512-522`, `PostToolUse`)

- `:108` — `grep -qiE "Gate ${gate_num}[^0-9]|GATE_CHECK:.*gate=${gate_num}"`: **presence only**. A
  report reading `Gate 3: FAILED — 5 CRITICAL` satisfies it.
- `:104-119` — the header at `:105` *claims* it accepts `✅`, `❌`, `PASS`, `SKIP`; those tokens
  appear **nowhere in executable code**. `grep -n 'PASS\|SKIP\|✅\|❌'` returns only line 105.
- `:66-71` — the YAML side reads only `gate_status == 'passed'` and `gate_report`. No individual gate
  status is ever read.
- `:130` — the block message **tells the caller how to bypass it**: "…OR set `gate_status: deferred`
  with rationale".
- fail-opens: `:34-36` no `jq`; `:51-53` no `python3`; `:74-76` nothing newly passed.

**`PLG/hooks/validate-wave-gate-prerequisite.sh`** (163 lines; registry `:796-806`, `PreToolUse`)

- `:138` — `if status not in ('passed', 'deferred')`: **`deferred` is treated identically to
  `passed`**, and the sibling hook recommends setting it.
- `:104-106` — `exit 0  # no wave-state file = project hasn't opted in`. **`LIVE/wave-state.yaml`
  does not exist**, so this hook is a no-op on the live factory.
- fail-opens: `:24-26` no `jq`; `:28-30` no `python3`; `:36-38` non-`Agent` tool; `:64-69` missing
  `verify-sha-currency.sh` (**which is not installed anywhere**); `:83` unlisted subagent (the
  allowlist at `:82` is five hardcoded names); `:88-90` no `S-N.NN` in the prompt; `:115-116` no
  `waves` key; `:130-131` story in no wave; `:141` `2>/dev/null || true` swallows every python error.

**`PLG/hooks/convergence-tracker.sh`** (186 lines; registry `:97-108`, `PostToolUse`)

- `:51` — skips `*ADV-*.md`. 28 `ADV-*.md` files exist in `LIVE/cycles/`, all unchecked, including
  both files that actually declare `CONVERGENCE_REACHED`.
- `:147` — `find … -name 'pass-*.md'`. **Measured: `LIVE/cycles/` has 419 files matching `*pass-N.md`
  and only 6 literally named `pass-*.md`** — so the "minimum 3 clean passes" rule sees 413 of 419
  real pass files as nonexistent. The `sort -t'-' -k2` also keys on the path, not the pass number.
- `:117` and `:94` — monotonicity and zero-findings-pass-1 violations are assigned to `WARNINGS`, not
  `ERRORS`; `:171-176` echoes them to stderr and `:186` exits 0.
- `:149,164-166` — the `CLEAN_STREAK < 3` error is nested inside `if [[ -n "$PASS_FILES" ]]`, so when
  the `:147` glob matches nothing the rule is **skipped rather than failed**.
- `:182` blocks with "See CONVERGENCE.md for the full quantitative criteria" — a document whose own
  line 5 says the criteria do not bind (§7).

**`PLG/hooks/validate-novelty-assessment.sh`** (97 lines; registry `:312-322`, `PostToolUse`)

- `:51` — same `*ADV-*.md` skip; `:52` also skips ADRs.
- `:40,41` — the path filter requires `.factory/cycles/*/adversarial-reviews/*pass-[0-9]*.md`.
  **Measured: 94 pass files are under `adversarial-reviews/`; 325 sit directly under
  `cycles/<cycle>/` and match no case arm — 78% of live pass files are never validated.**
- `:67,72,77,82` — field checks are whole-file greps, so e.g. `CONVERGENCE_REACHED` matches in prose
  or inside a quoted template.

**`PLG/hooks/validate-finding-format.sh`** (86 lines; registry `:252-262`, `PostToolUse`)

- `:51` — `^ADV-[A-Z0-9]+-P[0-9]+-[A-Z]+-[0-9]+$`. `[A-Z]+` accepts **any** uppercase token, so
  `ADV-X-P1-BANANA-001` passes. The extractor at `:47` permits `_`, but no branch handles `_`, so
  underscore IDs fall through all three branches and are **silently accepted**.
- `:55-57` and `:60-62` — blocks `^ADV-[0-9]+$` and `^ADV-P[0-9]+-[0-9]+$` as legacy. The second
  **contradicts `PLG/templates/adversarial-review-template.md:29`**, which explicitly sanctions
  `ADV-P01-MED-003`.

**`PLG/hooks/validate-count-propagation.sh`** (177 lines; registry `:532-542`, `PostToolUse`)

- `:150` — the comment "Absence of keyword in sibling is NOT drift"; `:151` implements it
  (`if [[ -n "$sib_count" ]] && …`), so a sibling index that dropped its count entirely is clean.
  Restated in the header at `:12`.
- `:96,102` — the keyword vocabulary is hardcoded to `BCs|VPs|stories|capabilities|subsystems`
  (Pattern A) / `BCs|VPs|stories|capabilities` (Pattern B — **`subsystems` silently dropped**).
- `:96,102,108,113` — every pattern is `[0-9][0-9,]+`, i.e. **two or more digits required**, so
  `9 BCs` or `total_vps: 8` is never extracted.
- `:120-127,141-147` — first-occurrence-wins plus `break` on the first sibling hit, so later correct
  occurrences are never compared.
- `:64-74` — 10 hardcoded sibling paths, including `specs/behavioral-contracts/BC-INDEX.md` while
  `relocate-artifact/SKILL.md:73,76` uses `specs/bc/BC-INDEX.md`.

**Artifact-path enforcement is WASM, and it fails open four ways**
(`CRATES/hook-plugins/validate-artifact-path/src/lib.rs`, 670 lines):

- `:426-437` registry absent → `HookResult::Continue` (BC-4.11.001 EC-001);
- `:442-453` registry malformed → `Continue` (EC-002);
- `:186-189` unknown `enforcement_level` → `Advisory`, and `:477-484` makes `advisory` non-blocking —
  so `warn`, `advisory` **and any typo** all pass;
- `PLG/hooks-registry.toml:847` `on_error = "continue"` — a panic or timeout in the module is
  swallowed;
- plus `:396-411` missing `file_path` → `Continue`, and `PLG/hooks-registry.toml:849-850`
  `path_allow` is a single **project-relative** path, so an out-of-tree install makes fail-open #1
  permanent.
- The only genuine block is `:488-495` (`NoMatch` on an in-scope `.factory/` path) — and the
  registry's only adversarial-review pattern (`PLG/config/artifact-path-registry.yaml:116`) matches
  none of the 94 real pass files, so if the hook were reachable it would block the writes
  `factory-cycles-bootstrap/SKILL.md:102` instructs.

| # | files | change | why | what breaks if not done |
|---|---|---|---|---|
| **H-1** | the 6 hook scripts above + `PLG/hooks-registry.toml` | **Delete them at their stage in §5.1 — do not repair them.** Every one of these defects is a symptom of policing markdown with bash greps. | The review's central observation: "the intent expressed in the wrong substrate — prose where a schema was needed, a hook where a query was needed." | Repairing them costs the same as `fa`'s gate layer and leaves the substrate unchanged. |
| **H-2** | `PLG/hooks-registry.toml:8-9` | Fix the stale header comment (claims 21 native + 35 legacy = 56; measured 28 + 35 = 63) and de-duplicate the `worktree-hooks` / `protect-secrets` double registrations. | a registry that miscounts itself. | Any tooling that trusts the header is wrong by 7. |
| **H-3** | `PLG/hooks/` and `PLG/hook-plugins/` | Delete the unregistered orphan `hooks/update-cargo-audit-cache.sh` and the 12 duplicate underscore `.wasm` pairs. `PLG/tests/check-bats-orphans.sh` detects only the inverse case — extend it. | dead code that reads as machinery. | Reviewers keep finding "the hook that does X" and it never runs. |

---

## 6. `bin/` helpers that `fa` subsumes

**13 files. Two have data sources that do not exist in `LIVE`.**

| helper | reads | subsumed by | disposition |
|---|---|---|---|
| `compute-input-hash` | the `inputs:` frontmatter of any artifact; `--update/--check/--resolve/--scan` | **`fa stale` / `fa derive`** (F8) | **DELETE.** It is a 7-char truncated MD5 of a concatenation — order-insensitive, so swapping two inputs' contents is invisible. `input-hash` appears in **3,890 files** and produces **3,433 of the 18,826 baseline findings**. Its own template line admits it is "advisory — used for drift detection, not gating" (`behavioral-contract-template.md:10`). Deleting it also removes the `Denied: exec` contradiction from four agents at once (§3.3). |
| `emit-event` | writes `.factory/logs/events-YYYY-MM-DD.jsonl`; "Exit 0 on every path. Period… silent drop" (`:9-11`) | `fa` audit (F18) | **KEEP through stage 3, then fold in.** 32 `events-*.jsonl` exist in `LIVE/logs/`. The silent-drop contract is exactly what an append-only audit must not do. |
| `factory-dashboard` | STATE.md · **`.factory/wave-state.yaml`** · the event log | `fa` status / MCP | **DELETE.** 1 of 3 sources missing: `LIVE/wave-state.yaml` **does not exist**. |
| `factory-obs` | `PLG/tools/observability/docker-compose.yml`; `~/.config/vsdd-factory/watched-factories` | — | **KEEP.** Genuinely orthogonal (OTel/Loki/Prometheus/Grafana). |
| `factory-query` · `factory-replay` · `factory-report` · `factory-sla` | `$VSDD_LOG_DIR`, default `.factory/logs/` | `fa` audit queries | **KEEP through stage 3.** `factory-sla` pairs `agent.start`↔`agent.stop`; its `open` subcommand exists because unpaired starts are expected — which `fa`'s transaction log makes impossible. |
| `lobster-parse` | `WF/*.lobster` (9 files); needs `yq` | **`fa workflow validate|plan|run`** (F22) | **DELETE at stage 3.** The shipped validator permits only `agent|skill|command` and requires `task`, while the real step types are `gate`, `loop`, `human-approval`, `sub-workflow`, `parallel`, `compound` — so `run-phase` **cannot execute any phase workflow**. |
| `multi-repo-scan` | `.worktrees/` + `.reference/` | `fa` project scope | **REWRITE, then delete.** It cannot detect a canonically-initialised multi-repo project: wrong directory, and it requires `.git` to be a directory when every worktree has `.git` as a *file*. |
| `research-cache` | `$VSDD_RESEARCH_CACHE_DIR`, default `.factory/research-cache` | `fa` ingested-artifact store | **KEEP as a cache, re-home it.** `LIVE/research-cache` **does not exist** and the path is **unregistered**, so writes would hit the `lib.rs:488` block. |
| `validate-template-compliance.sh` | `LIVE/specs/verification-properties/VP-*.md` — enforces "if `bcs:` has >1 entry then `source_bc:` must be non-empty" | `fa` write-time schema | **DELETE at stage 2.** Note the **name collision**: `PLG/hooks/validate-template-compliance.sh` is a different, unrelated script. |
| `wave-state` | `$VSDD_SPRINT_STATE`, default `.factory/stories/sprint-state.yaml`; needs `yq`; hard-fails at `:20` | `fa` wave/pipeline rows (F19) | **DELETE at stage 3.** It reads `sprint-state.yaml` — a second, incompatible representation of wave state that is **three months and 37 stories stale** (`total: 70 / merged: 57` against STATE.md's 117 registered / 74 merged). |

---

## 7. Retiring the orphan branch and the `.factory/` worktree

### 7.1 What exists, measured

**Four independent, non-shared implementations of orphan-branch creation**, plus a fifth in an agent
file, and they disagree:

| site | creates | seeds an empty commit | pushes |
|---|---|---|---|
| `PLG/skills/repo-initialization/SKILL.md:158` | `git checkout --orphan factory-artifacts` | no | **yes** `:161` |
| `PLG/skills/factory-health/SKILL.md:22` | same | **yes** `:24` | no |
| `PLG/skills/factory-worktree-health/SKILL.md:86` | same (`BRANCH_NAME` at `:75`) | no | no |
| `PLG/skills/release/SKILL.md:129` | same | **yes** `:131` | **yes** `:137` |
| `AG/devops-engineer.md:96` | same | no | **yes** `:99` |

Worktree mount sites: `repo-initialization:163`, `:211` (multi-repo `factory-project-artifacts`
`:206`), `:231`; `factory-health:36,42`; `factory-worktree-health:108,129`; `release:82,133`;
`devops-engineer.md:103,118`. Verification/assertion sites: `repo-initialization:168`;
`factory-health:51`; `AG/state-manager.md:51,55-56,70`; `worktree-manage/SKILL.md:65`; and
preconditions in `check-state-health:23`, `compact-state:30`, `recover-state:21`,
`phase-0-codebase-ingestion:35`, `phase-1-spec-crystallization:38`. Push sites:
`AG/state-manager.md:360,370,401`.

Guards: `PLG/hooks/factory-branch-guard.sh` — Check 1 `:68` (no worktree → block
`factory_no_worktree`), Check 2 `:78` (wrong branch → block `factory_wrong_branch`), **fail-open at
`:77`/`:78`** (git error sets `unknown`, which `:78` explicitly exempts) and `:76` (no git → Check 2
skipped entirely). `PLG/hooks/check-factory-commit.sh:14` **string-matches the command text** rather
than the worktree, and `:16-19` emits `additionalContext` and **exits 0** — its header `:3` says
"advisory only. Exit 0 always". It is also the only hook lacking the `jq` guard (`:6` uses `jq`
unconditionally). `PLG/hooks/validate-factory-path-root.sh:48` blocks nested `.factory/` inside a
story worktree — which exists because `LIVE/.factory/logs/` is real.

**There is no CAS-protected push anywhere on `develop`** (`factory-cas-push.sh` does not exist), and
no single canonical mount routine.

### 7.2 The change

| # | files | change | why | what breaks if not done |
|---|---|---|---|---|
| **W-1** | `PLG/skills/repo-initialization/SKILL.md:146-168,206-231` | Step 8 becomes **`fa init`**. No orphan branch, no worktree, no `.factory/` directory. A new project starts with a store and a schema. | M4. This retires the whole "which `.factory` am I in" class: `EnterWorktree` has **zero occurrences** in the tree, so everything is raw `cd`/`git -C`, and `LIVE/.factory/logs/` — a nested factory root — exists on disk, caught only by a **PostToolUse** hook that fires *after* the write it describes as "silently creates artifacts in the wrong place". | Every new project inherits five divergent bootstrap implementations, two divergent health skills, and a guard whose auto-repair is **blocked by the factory's own destructive-command guard**. |
| **W-2** | `PLG/skills/factory-health/`, `PLG/skills/factory-worktree-health/` | **Delete both.** Replace with `fa doctor`. | Two divergent health skills; the advisory one claims to detect divergence with `git status --porcelain`, which cannot. Live: `git -C .factory status --porcelain` returns **29 entries** while STATE.md asserts "expect clean", and nothing detects it. | Health checks keep disagreeing with each other and with reality. |
| **W-3** | `PLG/hooks/factory-branch-guard.sh`, `check-factory-commit.sh`, `validate-factory-path-root.sh`, `verify-git-push.sh:15` | Delete at stage 3. | There is no branch to guard once the store is the home. All four are fail-open anyway. | Fail-open guards keep being cited as enforcement. |
| **W-4** | `PLG/skills/release/SKILL.md:81,82,129,131,133,137` | The release path stops creating and mounting the artifact branch; it reads the store. | `release` is a *fourth* orphan-branch implementation living inside the release pipeline, whose own escalation contract says "do not improvise on the release pipeline". | A release can silently re-create the branch a migration just retired. |
| **W-5** | `AG/state-manager.md:51,55-56,70,134,188,222,360,370,401` | The four write paths become `fa` transactions; the wave-state co-commit mandate targets rows. | `state-update` and `compact-state` **commit and never push** (verified: zero `push` occurrences in either file); only `state-burst:156-160` pushes. `compact-state` appends to up to five files sequentially with no idempotence key, so its "abort without modifying STATE.md" claim is unenforceable. | `factory-artifacts` stays local-only for 2 of 3 writers, and the compaction audit trail stays **8 `git show <SHA>` pointers that no skill produces and nothing verifies**, covering 41 archived rows. |
| **W-6** | `PLG/templates/verify-sha-currency.sh`; `skills/state-burst/SKILL.md:136,165` | Delete the template and both invocations. | It is a **template, not an installed hook**; `LIVE/hooks/` holds only `dim2-gates/`, so every SHA-currency gate in the live factory is already a no-op, and `validate-wave-gate-prerequisite.sh:64-69` fail-opens on its absence. Under F1, identity is store-assigned and never transcribed — the whole class disappears. | A gate everyone believes is running continues not to run. |
| **W-7** | `PLG/skills/factory-cycles-bootstrap/`, `PLG/skills/compact-state/`, `PLG/skills/recover-state/`, `PLG/skills/check-state-health/` | Delete at stage 3. | Cycle bootstrap is a directory-layout migration; compaction/recovery/health are store operations (`fa checkpoint`, `fa recover`, `fa fsck`, F20). `recover-state` scans the filesystem while **ignoring `git log`**, then admits it cannot recover five sections — every one of which is in history. | Recovery keeps being a filesystem re-scan, which is why a mid-burst crash has no recovery path in any of three windows. |
| **W-8** | the 5 advertised-but-absent skills | Either implement them in `fa` or **remove them from the command surface**: `factory-lock`, `factory-unlock`, `wave-handoff`, `rehydrate-wave`, `wave-reset` have **no directory under `PLG/skills/`**. | They exist only in the operator cache at rc.23. The factory's own `.factory/` state was produced by an engine that had no lock and no wave-handoff. | The command surface advertises coordination primitives that do not exist on `develop`. **Port `rehydrate-wave` into `fa` almost unchanged** (F20) — the closed-form injection set, the `INJECTED_FILE_COUNT` sentinel, warn-on-missing-member, hard-error-on-missing-manifest, the no-RAG prohibition and its postcondition→mechanism table are the best-specified subsystem in the corpus. |

---

## 8. Docs that describe the retired substrate

**47 distinct broken path references**, measured by extracting every backtick-quoted path from
`PLG/docs/*.md` and resolving against 8 candidate roots, with placeholder patterns
(`BC-S.SS.NNN.md`, `VP-NNN.md`, …) excluded.

| # | file | what changes | why | what breaks if not done |
|---|---|---|---|---|
| **D-1** | `PLG/docs/FACTORY.md` — the `.factory/` layout section `:42-89` | Replace the directory tree with the **type registry** as the canonical inventory. | 21 of those lines cite paths that do not exist: `specs/product-brief.md` `:42` · `specs/domain-spec-L2.md` `:43,507,668` (disk has a *directory*) · `specs/prd-supplements/` `:45` · `specs/ux-spec.md` `:49,673` · `specs/module-criticality.md` `:50,583,686` · `specs/gene-transfusion-assessment.md` `:52,675` · `stories/epics.md` `:59,678` (disk has a *directory*) · `stories/dependency-graph.md` `:60,679` · `cycles/v1.0.0-greenfield/*` `:65-70` (**no cycle dir matches `vX.Y.Z-name`**; disk has `v1.0-brownfield-backfill`, two `v1.0-feature-*`, and `wave-11`/`wave-16`, which break the scheme entirely) · `holdout-scenarios/*` `:72-75` · `dtu-clones/` `:80` · `demo-evidence/` `:83` · `merge-config.yaml` `:88` · `autonomy-config.yaml` `:89`. | Agents load a documented layout that is not the layout, and both autonomy configs stay absent — so **autonomy is undefined at runtime**. |
| **D-2** | `PLG/docs/FACTORY.md:48` | "`architecture/` ← ARCH-INDEX.md + **7** section files" — the canonical list is 8 and disk has **11** `SS-NN-*.md` (with a duplicate `SS-03` ordinal). Replace with the schema. | both counts are wrong. | See T-5. |
| **D-3** | `PLG/docs/FACTORY.md:68,86,688,989` + `WF/feature.lobster:76` + `WF/multi-repo.lobster:530` | Delete every `cost-summary.md` reference; point at `fa cost`. | **Four different paths, none of which exists.** `:989` says a `cost-tracker` plugin at `plugins/src/cost-tracker.ts` maintains it — and `PLG/docs/not-portable.md:5,51` lists `cost-tracker.ts` as explicitly **not ported**. A cross-document contradiction. | The five-tier budget response up to HARD STOP keeps having no data source. |
| **D-4** | `PLG/docs/FACTORY.md:667-688` | **Delete the 20-row migration table.** It is unverifiable in **both** columns — none of the `phase-*` "old paths" exists and most "new paths" do not either. | it is the single largest source of broken references in the repo. | Every reader inherits 40 dead paths presented as authoritative. |
| **D-5** | `PLG/docs/FACTORY.md:704,844,925` | `workflows/skills/**/SKILL.md` → `skills/**/SKILL.md`. | wrong root: skills live at `PLG/skills/`; `PLG/workflows/` holds only `*.lobster` + `phases/`. | 3 dead references to the skill catalogue itself. |
| **D-6** | `PLG/docs/FACTORY.md:14,15,16,20,35,108,118,402,439,447,460,742,744,919,921,922,923,1041` | Delete references to `openclaw.json`, `SOUL.md`, `AGENTS.md`, `IDENTITY.md`, `docs/OPERATIONS.md`, `project.yaml`, `config/litellm-config.yaml`, and `agents/<name>/AGENTS.md`. | **none exists.** `PLG/docs/` = `AGENT-SOUL.md`, `CONVERGENCE.md`, `FACTORY.md`, `not-portable.md`, `VSDD.md`. `PLG/config/` contains **only** `artifact-path-registry.yaml`. `PLG/agents/` is flat `*.md`, no per-agent dirs. | The document that outranks every other doc cites 8 nonexistent files as its own structure. |
| **D-7** | `PLG/docs/FACTORY.md:508` | Delete `specs/domain-research.md` and `requirements-analysis.md`. | both missing, and `AG/consistency-validator.md:294` **explicitly forbids** `requirements-analysis.md` as a standalone file while FACTORY.md documents it as canonical. | A doc and an agent give opposite instructions. |
| **D-8** | `PLG/docs/FACTORY.md:83,878` vs `PLG/skills/code-delivery/SKILL.md:57` | Settle **one** demo-evidence home. Registry it. | `FACTORY.md:83` says `.factory/demo-evidence/` (absent from disk); `code-delivery:57` says `docs/demo-evidence/<STORY-ID>/` "**NOT `.factory/`**"; `record-demo`/`demo-recording` write to `.factory/`; the delivery gate requires the `docs/` form on the feature branch; and `record-demo` permits a `.txt` fallback the gate rejects. | Demo evidence keeps failing its own gate for path reasons. |
| **D-9** | `PLG/docs/CONVERGENCE.md:5` | **Delete "All criteria are ADVISORY."** Convergence becomes computed (F13); the human override becomes a recorded `fa gate record --status override --reason`. | It is line 5 of 554, before Dimension 1 at `:9`, and it nullifies the whole document as an enforcement source. `convergence-tracker.sh:182` blocks with "See CONVERGENCE.md for the full quantitative criteria" — pointing at a document whose line 5 says they do not bind. The `WARNINGS`-not-`ERRORS` design at `:94,117` is the code-level expression of it. | Every convergence threshold stays advisory, which is why `Novelty score | 0.0 (0 / (0 + 0))` on a trajectory violating monotonicity three times still declared `CONVERGENCE_REACHED`. |
| **D-10** | `PLG/docs/CONVERGENCE.md` (the rest) | Delete the specification of embedding-similarity dedup, per-finding confidence, hallucination fingerprinting, the power-law decay fit and the Convergence Index — or move them into `fa` as declared metrics. | They are attributed to a plugin that does not exist; `convergence-tracker.sh` is 187 lines of bash computing **none** of it. `convergence-tracking/SKILL.md:18` reads a `pass-*/review-report.md` layout absent from the corpus, so its inputs resolve to nothing. | A specification nobody implements reads as a specification somebody implements. |
| **D-11** | `PLG/docs/CONVERGENCE.md:353,482` | `holdout-evaluation/summary.md` → `holdout-evaluations/{filename}.md`; delete `module-criticality.md`. | `:353` is singular where disk is plural and has no `summary.md`. `module-criticality` has **three conflicting documented locations and zero of them exist** (`CONVERGENCE.md:482`, `FACTORY.md:686`, `rules/spec-format.md:175`). | See T-2. |
| **D-12** | the pipeline guides — `AG/orchestrator/{greenfield,brownfield,feature,maintenance,discovery,multi-repo,steady-state,per-story-delivery}.md` + `HEARTBEAT.md` | Re-point every `.factory/` path at an `fa` operation. Specifically: `greenfield-sequence.md:25,73`, `brownfield-sequence.md:32,104`, `multi-repo.md:37,39`. | These are the 10 files an orchestrator loads to decide what to do next, and they encode the orphan-branch model and the 8 nonexistent architecture files. | The scheduler keeps scheduling against a substrate that is being retired. |
| **D-13** | `PLG/docs/FACTORY.md:403` + `WF/phases/phase-4-holdout-evaluation.lobster:33` | Either make model diversity checkable (`fa attest`) or delete the blocking criterion. | "NEVER Claude" is a **blocking gate** falsified by every agent's `model:` frontmatter, and the 23 `model_tier:` keys have no resolver. | A gate blocks on a claim nothing can verify — which is decoration presented as enforcement. |
| **D-14** | `PLG/docs/not-portable.md` | Keep. Reconcile with `FACTORY.md:989` (see D-3). | This document is *correct* — the absences it lists are by design. `session-learning` exists as `PLG/hook-plugins/session-learning.wasm`, not `.sh`. | — |
| **D-15** | — | **Strike one false positive from the review:** `PLG/docs/VSDD.md:160` cites `red-gate.sh`, which **does exist** at `PLG/hooks/red-gate.sh`. | measured. | Wasted effort. |

Also: `~/Dev/vsdd-factory/CLAUDE.md` documents a continuous F5 cycle-level convergence loop whose
unit of work is a 5-commit fix burst, and establishes a **12-level source-of-truth precedence in
which STATE.md outranks every spec** — the inverse of `FACTORY.md`'s "Spec Supremacy". That
contradiction must be resolved by a human before stage 3 of cohort G (§9, OQ-4), because it decides
who wins when the store and a spec disagree.

---

## 9. SEQUENCING

Keyed to the migration ladder in `research/FA-V1-MIGRATION.md` §2. "Before stage N" means the
factory change must land before **any** `(project, type)` cell enters that stage.

### Before stage 1 (shadow) — nothing is required

Stage 1 is read-only and additive. `fa validate --registry` runs beside the existing hooks with its
findings baselined. **This is deliberate: no factory change is a prerequisite for measurement**, so
the migration can start today on all three projects while everything below is negotiated.

The only two things worth landing early because they are one-line edits and unblock a gate:

1. **N-1 + N-2** — the two namespace renames. `validate_registry.py` goes from
   `EXIT CRITERION NOT MET: 2` to met. *Blocked on user.*
2. **A-14 + A-15 + A-16** — the pointer fixes. Pure repair, no behaviour change, and they make the
   "Global Operating Rules" line actually load.

### Before stage 2 (dual-write), per type

| must land | why |
|---|---|
| **T-1, T-3, T-4** for that type | `fa` cannot validate a write against a schema that is still prose in a template. |
| **T-2** (registry merge) | the type needs one declared path + shape, or `fa path resolve` has nothing to resolve. |
| **A-1** (the manifest) + **A-11** for the skills/agents that write that type | dual-write requires that only `fa` writes it. |
| **S-1..S-10** for that type's writers | a skill still calling Write defeats the round-trip gate for reasons unrelated to `fa`. |
| **M8 write interception** — the new `PreToolUse` deny arm | without it, the markdown and the store diverge silently. |
| **H-1 stage-2 retirements** for that type — the 6 structure/format hooks and the 5 count/index hooks | two validators of one artifact produce contradictory verdicts; the count hooks would police a derived value. |

### During stage 2 → stage 3, per type

| must land | why |
|---|---|
| **A-3..A-8** (walls as return codes) for any walled type | the wall must move to the store before the paths stop existing. Do A-4 and A-5 **first** — they are the two walls that are currently absent and inverted, so they are wrong under either substrate. |
| **A-9** (profile↔job reconciliation) | the role→operation set is what makes a denied write a return code instead of a contradiction. |
| **A-17** (`producer:` → audit rows) + the `track-agent-start` `agent_id` field | attribution must exist before the hand-typed field is deleted. |
| **T-6** (finding IDs minted by `fa`) | must precede cohort C, because `adversarial-review` is where the 14 ID families live. |
| **D-9, D-10** | convergence cannot be computed while its own specification says it is advisory. Land these before cohort C reaches stage 3. |

### Before stage 3 (authoritative), globally

| must land | why |
|---|---|
| **W-1** (`fa init` replaces `repo-initialization` step 8) | a new project must never grow a markdown corpus to migrate later. |
| **W-2, W-3, W-5, W-6, W-7** | the store cannot be the only writer while five bootstrap implementations, four state write paths and four fail-open branch guards still exist. |
| **W-8** | decide the five phantom skills. `rehydrate-wave` must be ported, not lost — it is the best-specified subsystem in the corpus. |
| **H-1** stage-3 retirements (state · branch/worktree · convergence/gate · the 19 gate hooks) | — |
| **A-2 + D-13** | `fa attest`, or delete the unverifiable blocking criterion. |
| **D-1, D-2, D-4, D-5, D-6, D-7, D-8, D-11, D-12** | the docs must describe the new substrate before agents are told to trust them. |
| **the CLAUDE.md precedence contradiction** (§8) | resolve before cohort G. |

### Before stage 4 (markdown retired), globally

| must land | why |
|---|---|
| **H-1 stage-4**: delete `validate-artifact-path` and the entire `legacy-bash-adapter.wasm` route (35 entries) | — |
| **H-2, H-3** | registry header, the two double registrations, 1 orphan `.sh`, 12 duplicate `.wasm` pairs |
| **bin/ deletions**: `compute-input-hash`, `factory-dashboard`, `lobster-parse`, `multi-repo-scan`, `validate-template-compliance.sh`, `wave-state` | — |
| **T-5, T-7, T-8** | template deletions, once no reader remains |
| `sprint-state.yaml` and the never-instantiated `wave-state.yaml` are deleted | two incompatible representations of one thing, one of which was never created |

### Never (explicitly out of scope for this spec)

`factory-obs` and the observability stack · `emit-event`'s JSONL log format until `fa` audit is
proven · `PLG/templates/adversary-prompt-templates/` (prompt inputs, not schemas) ·
`PLG/docs/not-portable.md` (it is correct) · `PLG/docs/AGENT-SOUL.md` · the multi-repo
`.factory-project/` dual-branch design (CHANGE-MANAGEMENT §6 leaves multi-repo out of scope, and
this spec does not reopen it).

---

## 10. Open questions — these need a human call

1. **May this workstream write to `~/Dev/vsdd-factory` at all?** V-D says a branch with local commits
   is permitted and pushes need confirmation, but every change here is currently **blocked on the
   user**, including the two one-line renames. Which of the ~90 changes above is authorised, and on
   what branch?
2. **What replaces `state-manager` as a role?** Under `fa`, "only state-manager commits" becomes a
   capability in the role manifest. Does state-manager survive as an agent (bookkeeper for a store
   that already has transactions), or is it retired and its capability granted to the orchestrator?
   `AG/state-manager.md` is 410 lines of a genuinely good single-writer discipline; deleting it
   discards that reasoning, keeping it may keep a layer that `fa` makes unnecessary.
3. **The five advertised-but-absent skills** (`factory-lock`, `factory-unlock`, `wave-handoff`,
   `rehydrate-wave`, `wave-reset`). They exist only in the rc.23 operator cache. Port from the cache,
   reimplement in `fa`, or delete from the command surface? Note the factory's own `.factory/` was
   produced by an engine that had none of them.
4. **`FACTORY.md`'s Spec Supremacy vs `CLAUDE.md`'s 12-level precedence in which STATE.md outranks
   every spec.** These are opposites and both are live. Which wins when the store and a spec
   disagree? This decides cohort G's stage-3 semantics and cannot be inferred.
5. **`proposed-adr`, `consistency-validation-report`, and the demo-evidence home** — three vocabulary
   collisions inside the standard itself (28 prism files; two templates for one concept; three
   documented demo paths). Each needs one decision.
6. **Does the path registry merge into the type registry (T-2), or stay as a coarser sibling?**
   CHANGE-MANAGEMENT recommends merging and notes the path registry is *deliberately* coarser
   (`cycle-document` serves 8+ types), so a unique path per type would force 8 invented
   subdirectories. The measurement — no `template:` key, 11-of-46/81 overlap — argues for merging.
   Confirm.
7. **What happens to the 151 prism files in 4 unregistered `specs/` subdirectories?** The path
   registry's own header claims it blocks writes to any unregistered path, yet those files exist. So
   either the hook is not running there or the registry was never authoritative — settle which before
   relying on the hook as an enforcement surface (CHANGE-MANAGEMENT hazard 7).
8. **Is `wave-11` / `wave-16` a legal cycle id?** Two directories in `LIVE/cycles/` break the
   documented `vX.Y.Z-name` scheme entirely, and the cycle id is the scope key for most of the review
   family. Either the scheme changes or those two are renamed — and hazard 1 says `cycles/` paths are
   embedded in **189 plugin files**, so a rename is a prompt change, not a data change.
9. **Who answers issue #671?** It is an open, unbuilt proposal by another author on the same repo
   that this direction contradicts. Leaving it open while shipping the opposite is the one
   process failure this spec cannot fix.
10. **Does `agent-file-review` survive?** Its check 8 has never run (no `openclaw.json`). Under A-1
    the manifest makes most of its checks structural. Retire it, or rewrite it as `fa walls verify` +
    `fa doctor --agents`?

---

*Measured 2026-08-02 against `~/Dev/vsdd-factory` at develop `82163b7f` / factory-artifacts
`0aaba144`. Read-only throughout: 0 files written, no branch created. Every file:line in this
document was resolved on disk, and the seven corrections in §0 are the reason each one is quoted
rather than carried forward.*
