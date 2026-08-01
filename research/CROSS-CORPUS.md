---
title: CROSS-CORPUS — ten .factory corpora compared, to derive the core/profile boundary empirically
date: 2026-07-31
purpose: decide what belongs in fa's CORE schema vs a per-project PROFILE, from evidence rather than judgment
method: read-only measurement of ~/Dev/*/.factory across 12 candidates; 10 have a populated artifact set
status: the boundary is now measurable; vsdd-factory is an OUTLIER and must not be the template
---

# Ten corpora, one factory, no shared vocabulary

## Why this exists

The vision requires `fa` to own every factory artifact, which forces a decision:
**what is core (in the binary) and what is a per-project profile (declared data)?**
That boundary is a one-way door. Until now it was being reasoned about from a single
corpus — vsdd-factory — which is a factory building a factory. This measures nine more.

The question that prompted it: *"a local CLI todo app is much different than building a
SaaS IDAM and remote access tool."* Correct, and now quantified.

## 1. What was actually compared

12 projects under `~/Dev` carry a `.factory`. Two are not usable evidence:

| corpus | files | ex-`semport` | BC files | |
|---|---|---|---|---|
| vsdd-factory | 3,140 | 3,119 | **1,961** | |
| prism | 3,053 | 2,893 | 273 | Rust MCP server, MSSP security sensors |
| rivetry | 1,111 | 1,111 | 210 | CAD/PCB SaaS |
| monocle | 884 | 720 | 139 | |
| slideforge | 697 | 697 | 121 | |
| drift-lab | 609 | 609 | 130 | |
| pregolya | 528 | 481 | 130 | |
| game-factory | 331 | 331 | 194 | |
| brain-factory | 302 | 302 | 96 | |
| forge-mcp | 290 | 290 | 71 | |
| secops-factory | 143 | 143 | **0** | ⊘ no populated BC set |
| corverax | 9,291 | **18** | **0** | ⊘ scratch-dominated: 9,274 files are `semport/` ingestion |

⚠ **Method correction, recorded because it nearly became a finding.** A first pass ranked
corverax as the largest corpus and flagged it as the sole exception to the `BC-S.SS.NNN`
naming scheme. It is neither: its `specs/` holds 18 files and
`specs/behavioral-contracts` holds one. The "exception" was an empty directory. Counting
files is not counting artifacts.

**10 corpora have a populated behavioural-contract set.** All numbers below use those.

## 2. The structural spine is SMALL

Top-level `.factory/` directories, counting only **non-empty** ones:

| directory | in N of 10 |
|---|---|
| `cycles` | **10/10** |
| `specs` | **10/10** |
| `logs` | 9/10 |
| `planning` | 8/10 |
| `code-delivery` | 7/10 |
| `stories` | 7/10 |
| `semport` | 4/10 |
| `holdout-scenarios` · `hooks` · `phase-0-ingestion` · `proposals` · `research` | 3/10 |
| `demos` | 2/10 |

Inside `specs/`:

| subdir | in N of 12 candidates |
|---|---|
| `architecture` · `behavioral-contracts` | 11/12 |
| `prd-supplements` · `verification-properties` | 9/12 |
| `domain-spec` | 8/12 |
| `research` | 3/12 |
| `holdout-scenarios` · `ux-spec` | 2/12 |

ID schemes, by whether files are *named* that way:

| scheme | in N of 12 |
|---|---|
| `BC-S.SS.NNN` | 11/12 |
| `ADR-NNN` | 8/12 |
| `VP-NNN` | 6/12 |
| `E-NN` · `S-N.NN` | **2/12** |

**`stories/` exists in 7 corpora but only 2 name story files `S-N.NN`.** So story identity
is not standardised even where the directory is.

## 3. There are 28 singleton directories, and they track PRODUCT TYPE

Top-level dirs appearing in exactly one corpus:

| corpus | its own directories | product |
|---|---|---|
| rivetry | `design-system`, `ui-evidence`, `storyboard`, `analysis`, and in specs: `brand`, `ux` | CAD/PCB **SaaS with a UI** |
| prism | `objectives`, `tech-debt`, `reference`, `archive`, `lessons`, and in specs: `day2-design-decisions`, `day2-ui-design`, `test-strategy` | **security** MCP server |
| slideforge | `playbooks`, `preflight`, `reviews`, `seed` | presentation generation |
| drift-lab | `qa-gates`, `release` | |
| pregolya | `namespace-reservation`, `comparative` | |
| monocle | specs: `risk-acceptance` | |
| secops-factory | `feature`, `session-reviews`, `phase-f1-delta-analysis`, `phase-f2-spec-evolution` | |
| vsdd-factory | `feature-delta`, `measurements`, `legacy-design-docs`, `holdout-evaluations` | the factory itself |

This is the user's point, measured: the UI-bearing products grow `design-system` /
`ui-evidence` / `ux` / `brand`; the security product grows `test-strategy` and
security-review document types. **The variation is real, legible, and correlated with
product class** — and today it is expressed only as directories nobody declared.

## 4. The same concept is stored under different names — at least 8 clusters

| concept | names observed |
|---|---|
| demo evidence | `demo-evidence` (5) · `demos` (2) · `demo-recordings` (1) |
| planning | `planning` (8) · `plans` (2) |
| holdout | `holdout-scenarios` (7 declared / 3 populated) · `holdout-evaluations` (1 — vsdd, **empty**) |
| lessons | `lessons/` dir (prism) · `cycles/*/lessons.md` (vsdd) |
| tech debt | `tech-debt/` 43 files (prism) · `tech-debt-register.md` 1 file (vsdd) |
| reference | `reference/` 5 files (prism) · `reference-manifest.yaml` (vsdd) |
| research | `research` (3) · `analysis` (rivetry) · `comparative` (pregolya) |
| gates | `qa-gates` (drift-lab) · `preflight` (slideforge) · `gate-step-report` doc type (prism) |

## 5. The vocabularies do not agree AT ALL

Measured in `cycles/` frontmatter, vsdd-factory vs prism (611 and 1,165 documents):

| | vsdd-factory | prism |
|---|---|---|
| docs with frontmatter | 481/611 (79%) | 1,043/1,165 (**89%**) |
| `document_type` for "an adversary review" | `adversarial-review` 247 · `adversary-review` 69 · `adversarial-review-pass` 47 · `adversary-pass` 15 · `local-adversary-review` 6 · `per-story-adversary-review` 6 | `adversarial-review` 469 · `adversarial-review-pass` 84 · `adversarial-review-report` 46 · `adversarial-pass-report` 42 · `adversary-pass-report` 35 |
| shared `document_type` values | **2 of 12** | |
| `verdict` values | `NITPICK_ONLY` 88 · `HIGH` 87 · `SUBSTANTIVE` 63 · `FINDINGS_REMAIN` 43 · `CONVERGENCE_REACHED` 15 · `CLOCK_RESET` 15 · `MEDIUM` · `NITPICK` · `LOW` · `CRITICAL` | `BLOCKED` 143 · `CLEAN` 69 · `BLOCKED-soft` 31 · `FINDINGS_OPEN` 16 · `BLOCKED-hard` 15 · `CLOSED` 10 · `PASS` 8 · `APPROVE` 7 |
| shared `verdict` values | **ZERO** | |

Two projects, one factory, one concept, **not a single shared verdict value** — and each
drifts internally as well (`BLOCKED`/`-soft`/`-hard`; `CLEAN`/`PASS`/`APPROVE`/`CLOSED`).

**Therefore the drift is generated by the METHOD, not by a project.** Agents name things
per session against no declared vocabulary, so every corpus invents its own. No amount of
per-project tidying fixes it; only a declared, enforced vocabulary does. This is the same
conclusion [#671](https://github.com/drbothen/vsdd-factory/issues/671) reached from
citation drift ("POLICY 5 has been extended six times... **nothing actually parses the
reference graph**"), arriving from a second direction.

prism also carries product-specific document types vsdd has none of: `security-review` (9),
`pr-level-security-review` (8), `remediation-manifest` (31), `gate-step-report` (21).

## 6. vsdd-factory is an OUTLIER and must not be the template

- **1,961 BCs — 7.2× the next largest** (prism, 273).
- **4 singleton top-level directories**, more than any other corpus.
- Its `holdout-evaluations/` is both **uniquely named** and **empty**, while 7 corpora
  declare `holdout-scenarios/` (3 populate it).
- prism names BCs `BC-2.01.001-single-client-sensor-query.md` — flat, with a slug. The
  registry mandates `specs/behavioral-contracts/ss-{subsystem}/BC-{bc-id}.md`, and
  vsdd-factory treats the slug form as an **identity violation** (`BC-2.02.013-host-run-subprocess.md`,
  the one BC absent from its own index). prism's convention is vsdd's defect.
- **151 prism files sit in 4 `specs/` subdirs the registry does not declare at all**
  (`day2-design-decisions` 47, `day2-ui-design` 99, `prd-supplements` 4,
  `test-strategy` 1) — although the registry's own header states *"The hook always blocks
  writes to `.factory/` paths that match NO entry."*

So `artifact-path-registry.yaml`, which calls itself *"single source of truth for canonical
`.factory/` artifact locations"*, is in practice **vsdd-factory's own layout**. Deriving
`fa`'s core schema from it would encode the outlier as the standard — and would mark a
majority of prism, rivetry and slideforge as non-conformant on day one.

## 7. Two process findings, incidental but worth recording

- **Holdout scenarios are scaffolded almost everywhere and populated almost nowhere**
  (declared in 7, populated in 3; vsdd's variant is empty). A gate requiring them would
  fail nearly every project, so its severity is a profile decision, not a core one.
- **`.factory/.factory` nesting exists** in vsdd-factory (2 files) and monocle (2 files).
  Two corpora accreted a nested corpus root; nothing noticed.

## 8. What this settles

**The core is small and derivable:** `specs/{architecture, behavioral-contracts,
verification-properties, domain-spec, prd-supplements}` · `cycles` · `stories` ·
`code-delivery` · `logs` · `planning`, with `BC-S.SS.NNN` and `ADR-NNN` as the only
near-universal id schemes. Everything else — 28 top-level singletons, 7 `specs/`
singletons, every `verdict` and `document_type` value — is **profile**.

**The profile mechanism must be vocabulary-neutral.** Since prism and vsdd-factory share
zero verdict values, no canonical list can be imposed without invalidating one of them.
The workable shape is the one beads ships and its core queries depend on: projects declare
*names*, core reasons about *categories*.

```sql
-- beads, verified: core logic never enumerates project vocabulary
i.status = 'open' OR i.status IN (SELECT name FROM custom_statuses WHERE category='active')
```

So `BLOCKED`, `BLOCKED-hard` and `FINDINGS_REMAIN` all declare `category: blocked`;
`CLEAN`, `PASS`, `APPROVE` and `CONVERGENCE_REACHED` all declare `category: clean`.
Neither project renames anything; both become queryable. Core enumerates categories —
a closed set — and projects map onto them.

**And the migration is already built:** declare the profile → `fa validate` → date and
baseline the findings → ratchet, composing with the registry's existing
`enforcement_level: block|warn|advisory`.

## 9. Next

Draft the profile schema against **prism and rivetry as well as vsdd-factory** — a schema
validated against one corpus would simply re-encode that corpus. rivetry matters
particularly because it is the UI/SaaS shape (`brand`, `ux`, `design-system`,
`ui-evidence`, `storyboard`) and vsdd-factory has none of it.
