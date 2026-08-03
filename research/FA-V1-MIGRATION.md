---
title: FA-V1-MIGRATION — the per-type, per-project migration and cutover plan
date: 2026-08-02
purpose: move EVERY project using the vsdd-factory methodology into `datum`, staged per artifact type, with the evidence that advances each stage and the gate that proves nothing was lost
status: DESIGN. No implementation. Corpora read-only throughout — 0 files modified in vsdd-factory, prism or rivetry.
binds_to: research/FA-V1-DESIGN.md (8 settled decisions, 23 invariants — including the three 2026-08-02 per-shape ratifications of 16/17/21) · research/FA-V1-L1-L2-STORAGE-SCHEMA.md (whose `id_alias` / `reserved_key` ledgers and "16 binds at capture, 15 binds at cutover" rule this plan uses rather than redefines) · registry/CHANGE-MANAGEMENT.md (ADR, policy, 16 stories, graduation ladder, 7 hazards)
companion: research/FA-V1-FACTORY-CHANGES.md (the vsdd-factory change spec this plan sequences against)
---

# Migrating three corpora into `datum`

Under **V-A** `datum` is the source and markdown is a rendered view; under **V-F** every project
migrates. This document is the *how*, and it is written against measurements taken today rather
than against the numbers the review quoted, because two of them moved and three of them were
wrong in a way that changes the plan.

**The headline result of re-measuring: `datum import` cannot ingest two of the three corpora at all,
and on the third it silently loses 80 files.** Details in §1.4. That is instance nine of the
defect class this spike has hit eight times, it is live in the tool that would run the migration,
and it is why §5 is the longest section here.

---

## 1. What was measured, and when

### 1.1 Corpus pins — every number below is a snapshot of these

| corpus | main branch | `factory-artifacts` (the `.factory` worktree) | worktree state at measurement |
|---|---|---|---|
| vsdd-factory | `82163b7f` (develop, 2026-06-01) | `0aaba144` (2026-06-08) | **29 dirty entries** — all ` D logs/*.jsonl` deletions |
| prism | `b226459d0` (develop, 2026-08-01 21:54) | **`7f0d93fe1` (2026-08-02 00:09)** | **8 dirty** — ` M stories/S-3.6.01…`, `S-3.7.0[0-5]…` |
| rivetry | `52bd25d` (main, 2026-07-09) | `2aea395` (2026-07-27) | 9 dirty — logs + `sidecar-learning.md` |

**prism was re-measured, as directed.** Its `.factory` advanced **5 commits / 75 markdown files
(+1,013 −236 lines)** past the registry's pin `9f3443d6f` — the `§Authority` rounds 1–3 recorded in
its own STATE (`D-2089`, `STATE v8.636→v8.637`) — and it has 8 story files dirty from the
concurrent session right now. Across that advance:

- prism conformance findings: **10,843 — unchanged**.
- prism `document_type` census: **byte-identical** (`types_measured.json` diffs empty; 32 canonical
  values / 1,253 files and 118 non-canonical / 646 files before and after).

So the prism baseline is not stale, and I can say *why*: the advance added `## Authority` sections,
which touch neither a required field nor a section the registry mandates. That is a load-bearing
fact for §7 — **shadow-stage evidence survives concurrent authoring**, measured, not assumed.

### 1.2 Scale, per project

| | vsdd-factory | prism | rivetry | total |
|---|---|---|---|---|
| files under `.factory/` | 3,145 | 3,054 | 1,111 | 7,310 |
| markdown files | 3,085 | 2,784 | 668 | **6,537** |
| markdown bytes | 27.99 MB | **47.64 MB** | 19.39 MB | 95.0 MB |
| md/yaml/yml scanned | 3,089 | 2,789 | 712 | 6,590 |
| carry a `document_type` | 2,724 (88%) | 1,899 (68%) | 590 (83%) | **5,213** |
| no frontmatter at all | 320 | 742 | 122 | **1,184** |
| frontmatter, no `document_type` | 45 | 148 | 0 | **193** |
| distinct RAW `document_type` values | 71 | **150** | 51 | 225 observed |
| distinct CANONICAL values after alias resolution | 47 | 61 | 40 | **80** in use (of 103 declared) |
| conformance findings ⚠ *as measured 2026-08-02; prism drifts — re-measure* | **6,951** | **10,843** → **10,953** (2026-08-03) | **1,032** | **18,826** → **18,936** |
| files type-resolved and checked by the registry gate | — | — | — | 4,989 |

`validate_registry.py` exits **0**; `D-A INVARIANT concat(sections) == body : HOLDS on every file`.
Story 1's gate still prints `EXIT CRITERION NOT MET: 2 name disagreement(s) remain`.

Per-corpus finding shape (top five classes):

| corpus | total | shape |
|---|---|---|
| vsdd-factory | 6,951 | missing-required 3,027 · retired-field 2,676 · missing-section 538 · empty-required 365 · type-alias-applied 240 |
| prism | 10,843 | missing-required 6,699 · retired-field 1,217 · missing-section 1,189 · type-alias-applied 641 · empty-required 549 |
| rivetry | 1,032 | retired-field 482 · type-retired 212 · missing-required 178 · missing-section 87 · type-alias-applied 40 |

Two whole-corpus classes dominate and both are *retirements*, not drift:
**`retired-field:input-hash` 3,433** (18.2% of the entire baseline) and
**`retired-field:verdict` 745**. `type-retired` 223 is almost entirely rivetry's `delta-archive`.

### 1.3 Type divergence: what each project uses that the others do not

Measured over RAW `document_type` values (the migration's transformation domain):

| | values used by NO other project | files they carry |
|---|---|---|
| vsdd-factory | **46** | 112 |
| prism | **116** | 511 |
| rivetry | **29** | 290 |
| shared by all three | **13** | — |

The 13 values all three projects agree on: `adr`, `architecture-index`, `architecture-section`,
`behavioral-contract`, `burst-log`, `domain-spec-index`, `domain-spec-section`, `dtu-assessment`,
`pipeline-state`, `prd`, `security-review`, `session-checkpoints`, `verification-property`.

After alias resolution the overlap improves but the divergence does not vanish: **21 canonical
types are in use in all three**, while 12 are vsdd-only, 17 prism-only, 8 rivetry-only. The
project-unique canonical types are the ones with no cross-project evidence, so they migrate last
within their cohort:

- vsdd-only: `behavioral-contract-id-mapping`, `code-delivery-artifact`,
  `consistency-validation-report`, `cycle-index`, `delta-analysis-report`, `epic`, `fix`,
  `performance-report`, `po-obligations`, `policies`, `recovered-architecture`, `story-id-mapping`
- prism-only: `code-review`, `demo-evidence-report`, `epic-index`, `fix-burst-closure`,
  `holdout-evaluation`, `holdout-scenario`, `holdout-scenario-index`, `merge-result`,
  `preflight-findings`, `product-brief`, `proposed-adr`, `remediation-manifest`, `research-index`,
  `semport-artifact`, `session-review`, `test-strategy`, `uncertainty-map`
- rivetry-only: `brandbook`, `module-criticality`, `prd-supplement-error-taxonomy`,
  `prd-supplement-interface-definitions`, `persona-journey-map`, `storyboard-narrative`,
  `ux-spec-flow`, `ux-spec-screen`

Note `epic` is **vsdd-only** — prism has 265 story files and **zero** `stories/epics/`, and rivetry
has no `stories/` directory at all. A migration that assumes the vsdd layout is a migration that
works for one project. (CHANGE-MANAGEMENT hazard 6 said this; the layout measurement confirms it.)

### 1.4 Store coverage and lossiness — and the three live importer defects

The store's schema is **v4**. Exactly **three** tables carry a verbatim body — `bc`, `vp`, `story`
(`datum/schema.go:51`, `:67`, `:88`). `adr` and `epic` hold `(id, title)` only
(`datum/schema.go:42-45`); `holdout_scenario` holds `(hs_id, expectation)` (`:333`); `review` holds
`(review_key, cycle, pass, target, src_path)` (`:193`). There is **no `section` table** and no
`datum render` (`./datum/datum render` → `unknown command "render"`).

Classifying every typed file by what the store can hold today — B = verbatim body, R = a row but no
body, N = no table at all:

| project | typed files | B (renderable) | R (row only) | N (no table) | **cannot round-trip** |
|---|---|---|---|---|---|
| vsdd-factory | 2,724 | 2,145 | 473 | 106 | **579 (21.3%)** |
| prism | 1,899 | 612 | 796 | 491 | **1,287 (67.8%)** |
| rivetry | 590 | 189 | 58 | 343 | **401 (68.0%)** |
| **total** | **5,213** | **2,946** | **1,327** | **940** | **2,267 (43.5%)** |

Plus 1,184 markdown/yaml files with no frontmatter and 193 with frontmatter but no
`document_type`, which have no type and therefore no home at all. The vsdd B column reproduces the
review's 2,145 exactly; the review's "461 no table" is `3,085 − 2,624` over *all* markdown, i.e. it
counted the 320 + 45 untyped files into the same bucket. Same corpus, two rules, two answers — my
map is stated above so the number is checkable.

**Even the B column does not round-trip today, and this is the more serious finding.** `BCRow.Body`
is the *post-frontmatter* body (`datum/corpus.go:439`, `:485`); the frontmatter is field-extracted, so
every unmodeled key is dropped. Measured distinct frontmatter keys versus the columns that exist:

| type | vsdd | prism | rivetry | example unmodeled keys (with file counts) |
|---|---|---|---|---|
| behavioral-contract | 38 keys, **30 unmodeled** | 50 keys, **41 unmodeled** | 23 keys, **15 unmodeled** | `level` 1959 · `producer` 1959 · `timestamp` 1959 · `inputs` 1959 · `origin` 1959 · `introduced`/`modified`/`deprecated`/`deprecated_by`/`retired`/`removed` 1959 each |
| verification-property | 40 keys, **30 unmodeled** | 32 keys, **26 unmodeled** | 31 keys, **25 unmodeled** | `verification_lock` 80 · `proof_completed_date` 80 · `proof_file_hash` 80 · `traces_to` 80 |
| story | 63 keys, **50 unmodeled** | 106 keys, **93 unmodeled** | n/a | `story_id` · `target_module` · `estimated_days` · `assumption_validations` · `risk_mitigations` |

So invariant 15 is not merely unbuilt; it is **currently unsatisfiable for 100% of the corpus**,
including the 2,946 files the store nominally holds. That is the first thing §3 orders.

**Two shape exemptions, taken from the spine's 2026-08-02 per-shape ratification of invariant 16 —
they change the denominator, not the gate.** `blob-with-path` (4 types: `runtime-log`, `ui-asset`,
`demo-asset`, `hooks-dim2-gate-template`) stores path + content hash and legitimately has no body;
`append-only-event` (11 types — the whole of cohort D) stores *entries* and **derives** the file, so
for a ledger the markdown is a render. Hence the rule this plan adopts verbatim from
`FA-V1-L1-L2-STORAGE-SCHEMA.md`: **invariant 16 binds at capture, invariant 15 binds at cutover** —
while a type sits at shadow or dual-write its captured body is stored verbatim and gated by 16; when
it reaches authoritative the captured body is dropped and 15 takes over, and no type may advance to
authoritative until 15 is green over 100% of its instances. An exemption must be **declared as a
shape in the registry; silence is not an exemption.**

**One more consequence of the invariant-17 ratification, which is a migration item and not a design
one:** three columns in the *current* schema already store a derivable value and must be retired
during cohort A — `bc.version` / `vp.version` (derivable from the version chain),
`version_cite.verdict` (derivable from `pin_policy` + the cited vs current version), and
`finding.occurrences` (a stored `COUNT(*)`, incremented at `datum/import.go:402-403`).

**Three importer defects, found by running it against all three corpora rather than one:**

```
$ ./datum/datum import --db /tmp/fadb_v ~/Dev/vsdd-factory/.factory
imported in 5.6s  bc=1959 vp=80 story=148 subsystem=10 edges=1509 findings=106 assertions=217
reviews 390 · finding rows 2211 · sub-artifacts 4492 (+914 links) · prose refs 3615 · version cites 2197

$ ./datum/datum import --db /tmp/fadb_p ~/Dev/prism/.factory
datum: prose_ref stories/PLUGIN-MIGRATION-001-E-…-wasm-plugin.md: Error 1105: string 'ac-003: …' is too large for column 'target'

$ ./datum/datum import --db /tmp/fadb_r ~/Dev/rivetry/.factory
datum: vp VP-001: Error 1062: duplicate primary key given: [VP-001]
```

- **D1 — column overflow aborts the whole import.** `prose_ref.target` is `VARCHAR(220)`
  (`datum/schema.go:277`) and the insert passes `r.Target` untruncated (`datum/import.go:352`), while the
  sibling `adversarial_finding` insert truncates statement to 2,000 and location to 500
  (`datum/import.go:285-286`). prism cannot be imported at all. The transaction correctly rolls back,
  so this is loud, not silent — but it is a hard stop for the largest corpus.
- **D2 — duplicate natural keys are handled three different ways for one defect class.**
  `bc` catches `isDuplicateKey` at the insert and files a finding (`datum/import.go:191-195`);
  `story` catches it at *scan* time, files a finding, and **keeps the first file it walked**
  (`datum/corpus.go:502-506`) — silently discarding the second file's body; `vp` catches it
  **nowhere** and crashes. Measured collisions on filename-derived keys:
  rivetry **74 BC** + **49 VP** (every one a `*.DELTA-ARCHIVE.md` sidecar colliding with its live
  file), prism **7 story** (`S-5.01-mcp-bootstrap.md` vs `S-5.01-FOLLOWUP-MCP-BOOT-mcp-server.md`;
  also `S-1.12`, `S-3.04`, +4).
- **D3 — the ninth instance: `datum import` silently loses 80 of prism's files.**
  `reVPFile = ^(VP-\d+)` (`datum/corpus.go:138`) is case-sensitive; **prism names every verification
  property `vp-001-tenant-id-validation.md` in lowercase** — 80 files in
  `specs/verification-properties/`, zero of which the importer sees. The empty-scan guard only
  fires when BCs *and* VPs *and* stories are all zero (`datum/import.go:102-106`), so a project whose
  entire L4 layer is invisible imports "successfully". **This is exactly the failure mode
  §6 of FA-V1-DESIGN names as the worst possible place for a ninth instance, and it is live in the
  migration tool.** Related layout couplings, all hardcoded in `datum/corpus.go`: reviews are read
  only under `cycles/` (`datum/findings.go:77`), so **53 vsdd + 44 prism review-family files outside
  `cycles/` are invisible**; `stories/epics/E-*.md` (`:250`), `phase-0-ingestion/pass-4-nfr-catalog.md`
  (`:231`), `specs/behavioral-contracts/ss-*` (`:285`) all assume vsdd's tree.

### 1.5 What is already built, and re-verified today

| | measured today |
|---|---|
| `datum import` (vsdd) | **5.6 s** for 3,145 files, idempotent, one transaction (invariant 6) |
| `datum validate` (store-side) | 776 findings beyond baseline |
| `datum validate --registry` | 7,487 |
| `datum shadow` (story 7) | **658** findings · BC-INDEX 7,836 cells 93.1% agreed · VP-INDEX 400 cells 97.0% · STORY-INDEX 618 cells 89.8% · writes nothing |
| `datum` test suite | 117 tests, ~6.7 s |
| prose refs | **3,615** today (HANDOFF's snapshot says 3,537 — re-measured at the same corpus pin after `983df3d`; the newer number is the one to carry) |

---

## 2. Two ladders, not one

`derivation_stage` and the migration ladder both use the word *shadow*, and conflating them is the
first mistake available. They are orthogonal axes and both are per type.

```
DERIVATION ladder (registry, 23 derived types)     shadow ─► proven ─► retired
    "is this document generated, or authored?"      (datum shadow implements stage 1)

MIGRATION ladder (this document, all 103 types)    shadow ─► dual-write ─► authoritative ─► md retired
    "who is the source of truth for this type?"
```

**Composition rule (decision):** a *derived* type may not enter migration stage 2 (dual-write)
until its derivation stage is `proven`. Generating an index while it is still authored elsewhere
creates a second writer of the same artifact, which is the exact thing dual-write exists to
prevent. An *authored* type has no derivation stage and is unaffected.

**The unit of migration is the pair `(project, type)`**, not the type. 80 canonical types in use ×
3 projects = 240 cells, of which 21 × 3 = 63 are shared. Per-project cells are what make V-F's
"a project mid-migration must not block another project" mechanically true rather than aspirational.

### 2.1 Stage 0 — out of scope, on purpose

A `(project, type)` cell is **stage 0** until it has a declared **scope predicate** in the registry.
This is the one result the spike already paid for: 41 of 148 vsdd stories live in
`stories/v1.0-legacy/` and STORY-INDEX deliberately omits them (verified as exact set equality,
41 == 41), so generating from every record would have **resurrected 41 retired stories while every
count still agreed**. Today that predicate lives in Go (`datum/shadow.go:111` `ExcludeSrcPrefix`) and
it must move into the registry beside `derivation_stage` before any cell advances.

Stage 0 is also where the deliberate non-migrations live, each with a recorded reason:
`retired:` types (6 values, 223 files, 211 of them rivetry `delta-archive`), the 108 singleton
`document_type` values that are deliberately **not** aliased, and the 3 `unresolved:` values.

### 2.2 Stage 1 — SHADOW: the store follows, and writes nothing

**Entry evidence (all five, per cell):**

| # | evidence | today |
|---|---|---|
| S-E1 | the type resolves in the registry for this project — `validate_registry.py` PART 1 exits 0 over this project's values, and every raw spelling this project uses is canonical, aliased, gap-typed or explicitly retired | **green** — 0 undispositioned of 225 observed |
| S-E2 | the type has a store table with a **verbatim body column** and a stored **ordinal section partition** | **3 of 103** types have a body; **0** have a section table |
| S-E3 | a **declared scope predicate** in the registry for this `(project, type)` | in Go for 3 types; **absent for 100 others** |
| S-E4 | `datum import` completes for this project without aborting, and its per-form census for this type balances | **fails outright for prism and rivetry** (§1.4 D1/D2) |
| S-E5 | the type's filename/path pattern is read **from the registry**, not hardcoded — with per-project overrides where the layouts diverge | hardcoded in `datum/corpus.go`; costs prism 80 VP files |

**Exit evidence (stage 1 → stage 2). This is the question the brief asks precisely, so it gets
precise answers.** All seven, per cell, machine-produced, no adjectives:

| # | exit gate | pass condition | why this one |
|---|---|---|---|
| **X1** | **Conservation** | `files_on_disk(project,type) == rows + declared_out_of_scope + rejected_with_reason`, and `skipped_without_reason == 0` | The anti-#9 gate. prism's 80 VPs are 80 files skipped without a reason and nothing failed. |
| **X2** | **Invariant 16 at capture: the captured body is byte-exact and its partition is total** | for every file of the type: the stored body equals the file's bytes after the frontmatter, **the frontmatter bytes are stored verbatim including key order and every unmodeled key**, and `concat(sections) == body`; report `N compared / N equal`; one mismatch blocks. (The full `import(render(store)) == store` round trip is invariant **15** and gates stage 2 → 3, per the spine's capture/cutover split — see Y6.) | D-A + invariant 16. Today 30–93 frontmatter keys per body type are dropped, so this fails on 100% of files and *should*. `concat(sections) == body` already HOLDS on all 6,537 files, so the partition half is green and the capture half is the work. |
| **X3** | **Count parity** | `datum count --project P --type T` equals the on-disk count, and every count the corpus *asserts* about T either agrees or is an adjudicated finding with a named owner | The six-BC-totals class. `corpus_assertion` already holds 217 such claims for vsdd. |
| **X4** | **Baseline preservation** | the `(project, type)` slice of the **conformance baseline as of its recorded version** (⚠ **F3: cite the baseline ARTIFACT + VERSION, never a literal count** — "18,826" went stale twice in one session: → 18,831 → 18,936, entirely prism drift; re-run `python3 registry/validate_registry.py`) is reproduced by `datum validate --registry` with delta **0**, or reconciled line by line to *registry evolution* vs *corpus drift* | Precedent: 18,418 → 18,826 was +408 of registry tightening on byte-identical input and +22 untracked files. A migration that cannot tell those apart cannot be trusted to report loss. |
| **X5** | **Alias closure applied and recorded** | every raw spelling in this type's alias closure resolved, every non-empty `set:` clause applied, one `migration_event` row per application | 921 files carry an applied alias (vsdd 240 · prism 641 · rivetry 40); 22 aliases carry `set:` clauses over 87 files. A rename without the `set:` destroys `scope` and `reviewer_role`. |
| **X6** | **Every shadow/validate disagreement dispositioned** | fixed in the corpus · waived with reason + owner · or reclassified into a declared class. No open, unclassified disagreement. | 658 shadow findings today decompose 573 real drift / 44 editorial / 41 facts about derivation itself. The classes exist; the dispositions do not. |
| **X7** | **The write path exists for the type** | `datum new|set` validates against the type's schema at write time, mints its key transactionally, and a role→operation manifest names its writer | `datum` has **no write path at all** (self-describes as "phase 1: read-only shadow"). Nothing can dual-write until M3 lands. |

X2 and X7 are the two that currently block *every* cell. X1 is the one that would have caught
prism's VPs.

### 2.3 Stage 2 — DUAL-WRITE: `datum` first, markdown still authored

`datum` is written first and `datum render` regenerates the markdown; the markdown remains committed and
diffable, and `datum render --check` runs on every commit (invariant 8). Raw `Edit`/`Write` on that
type's paths is **denied** (M8) — without that, dual-write drifts and the round-trip gate starts
failing for reasons that have nothing to do with `datum`.

**Exit evidence (stage 2 → stage 3):**

| # | exit gate | pass condition |
|---|---|---|
| **Y1** | real usage, not synthetic | ≥20 real write operations of this type through `datum`, spanning ≥1 complete authoring cycle for the type |
| **Y2** | zero divergence events | every markdown diff touching the type joins to an `datum` transaction id; a diff with no txn is a divergence and resets the clock |
| **Y3** | `render --check` green on every commit for the whole window | not "mostly green" — a single failure resets Y1's counter |
| **Y4** | **the gate has caught ≥1 real regression in real work** | DECISIONS D3's own rule for `advisory → block`, reused verbatim: a gate that has never fired is unproven |
| **Y5** | every reader migrated | `datum doctor --readers` resolves every hook, skill and agent reference to this type's paths to either the committed render or an `datum` operation |
| **Y6** | **invariant 15 green over 100% of the type's instances** | `import(render(store)) == store` at store-fingerprint level, per instance, with a census. This is the gate the spine and the L1–L2 design both place here: the captured body is only dropped once the render can reproduce it. For `append-only-event` types this is the *only* body gate there ever is. |

### 2.4 Stage 3 — AUTHORITATIVE: `datum` is the only writer

**Exit evidence (stage 3 → stage 4):**

| # | exit gate | pass condition |
|---|---|---|
| **Z1** | 30 days authoritative, `render --check` green, zero manual edits to the type |
| **Z2** | **the restore drill** | `datum import` of the *committed render* into an empty store reproduces the store fingerprint exactly (`datum/import.go:463` `fingerprint`). This is the reversibility proof, and it is what makes stage 4 safe. |
| **Z3** | the retirement ledger entry for this type is executed and `datum doctor` finds no dangling reference to the deleted machinery |

### 2.5 Stage 4 — MARKDOWN RETIRED (a precise name for a narrower thing)

Per **D-B** the rendered markdown stays committed **forever**. What stage 4 retires is markdown as
an *authoring* surface: the hand-authored file is replaced in place by the render, and the hooks,
indexes and bash helpers that policed the hand-authored form are deleted per the retirement ledger.
`gh pr diff`, GitHub review and every human reader keep working unchanged. Nothing is ever deleted
from git history.

---

## 3. Order

Two orderings compose: a **cohort order over types** (dependency first, mass second) and a
**project order** (pilot first, then largest, then the concurrently-edited one). Neither is a
blocking dependency across projects — V-F requires independence, so the project order is a
scheduling preference and each project runs its own cohort ladder.

### 3.1 Why dependency before mass

Mass is a cost proxy, not a value proxy. This spike already got that wrong once — over corpus mass
prose refs are 93.6% row-shaped, but over the adversary's findings 12a and 12b are equal, and the
mass number produced the wrong priority. So the cohorts are ordered by what *unblocks* what, and
mass only orders within a cohort.

The dependency edges, each with its measured basis:

1. **subsystem → behavioral-contract.** `bc.ss_id` is an FK; a BC declaring an unknown subsystem is
   already refused with a finding (`datum/corpus.go:456-460`).
2. **declaring documents → the four ID universes.** `capability` (30), `domain_invariant` (18),
   `nfr` (88), `fr` (48) are extracted from `specs/domain-spec/`, `specs/prd.md` and
   `phase-0-ingestion/pass-4-nfr-catalog.md` (`datum/corpus.go:222-231`). Those documents —
   `domain-spec-section` (31 files), `prd` (3), `prd-supplement-*` (7) — **have no table**, so the
   universes are grep products of unmodeled documents. Model the documents or every reference into
   them is unverifiable.
3. **behavioral-contract → every index that enumerates it.** `behavioral-contract-index` (6 files),
   `traceability-matrix` (3), `story-index`, `epic-index`, and the 2,362-file BC set that
   `story_bc` / `vp_bc` / `hs_bc` all point at.
4. **findings before convergence.** `convergence` and novelty are derived from finding rows (F13);
   `convergence-report` (5) and `convergence-trajectory` (3) cannot be derived until
   `adversarial-review` (1,155 files) and its 2,211 finding rows are authoritative. This is the
   edge the brief names, and it is the one the corpus proves: the only Kani-proved gate in the
   factory reads hand-written JSON because there were no rows to compute from.
5. **verification-property needs `vp.status` first.** VP-INDEX's Status column is declared
   `ColUnderivable` today and says so in the code (`datum/shadow.go:146-147`).
6. **ledgers before `pipeline-state`.** STATE.md is three artifacts (story 11: a mutable record, a
   decisions ledger, a checkpoint ledger). The two ledgers need a home before the record can split.
7. **`delta-archive` retirement before rivetry's bc/vp.** Measured: 143 of rivetry's 211
   `*.DELTA-ARCHIVE.md` files collide on a keyed record type (74 BC, 49 VP, 18 ADR, plus 17 SCR /
   11 FLOW). rivetry cannot import at all until this is resolved, and story 8's own hazard is that
   these sidecars hold versions that exist nowhere else — so it is count-asserted, not deleted.
8. **`input-hash` retirement before any type reaches `block`.** 3,433 findings — 18.2% of the whole
   baseline — are one retired field. A type cannot reach a zero baseline while it carries it.

### 3.2 The cohorts

**Cohort A — schema prerequisites (no cutover; project-independent).** Not a migration of types but
the precondition for all of them: (a) a **body + section table for every type**, keyed by ordinal
per D-A; (b) **verbatim frontmatter bytes** stored alongside the parsed projection, so X2 is
reachable at all; (c) `datum render`; (d) the scope predicate and the filename patterns moved out of Go
into the registry; (e) ✅ **DONE 2026-08-03** — the three importer defects D1/D2/D3 fixed, with one declared collision policy (file a finding and KEEP BOTH, via `key_collision`), plus two further defects found by fixing them (INSTANCE TEN in the frontmatter parser, 171,284 chars silently lost; and a layout-derived subsystem catalog that zeroed 269 of prism's BCs)
per type — **first-wins is banned**; (f) the conservation census promoted from a printed line
(`datum/import.go:436-443`) to a hard assertion; (g) the three invariant-17 violations already in the
schema retired — `bc.version`, `vp.version`, `version_cite.verdict`, `finding.occurrences`; (h) a
declared `shape` on every type, because under the ratified invariant 16 an undeclared shape is gated
by every body rule at once.

**Cohort B — the record spine.** 3,097 files = **59.4% of typed mass**. Highest volume, declared
keys, real templates, best conformance. All five already have tables; three already have bodies.

| type | vsdd | prism | rivetry | total | notes |
|---|---|---|---|---|---|
| behavioral-contract | 1,959 | 269 | 134 | **2,362** | 45.3% of all typed files, on its own |
| story | 106 | 263 | 0 | 369 | prism has 7 key collisions; 41 vsdd stories are scope-excluded legacy |
| verification-property | 80 | 80 | 55 | 215 | **prism's 80 are invisible today** (D3); needs `vp.status` |
| adr | 23 | 57 | 54 | 134 | first-cohort `block` candidate: `adr_id`/`date`/`subsystems_affected` present on all 134 |
| epic | 17 | 0 | 0 | 17 | vsdd-only |

**Cohort C — the review family.** 1,226 files = 23.5% of typed mass, and the whole of the
convergence dependency.

| type | vsdd | prism | rivetry | total |
|---|---|---|---|---|
| adversarial-review | 433 | 718 | 4 | **1,155** |
| security-review | 2 | 21 | 8 | 31 |
| pr-review-findings | 11 | 17 | 0 | 28 |
| code-review | 0 | 12 | 0 | 12 |
| (already rows) adversarial-finding | — | — | — | 2,211 rows over 390 reviews |

This is the cohort where the alias table does the most work: 11 spellings resolve to
`adversarial-review` and the `set:` clauses are the only thing preserving `scope` and
`reviewer_role`. It is explicitly **not** a first-cohort `block` candidate — it targets `warn`, per
CHANGE-MANAGEMENT §4, because all 8 of its required fields are a tightening.

**Cohort D — the ledgers.** ~58 files, **26,632 references** (story 6: `decision` 20,788 +
`lesson` 5,844). The clearest case of mass-inside-files rather than mass-in-file-count:
`burst-log` 7, `session-checkpoints` 14, `red-gate-log` 15, `lessons-learned` 8,
`cycle-decision-log` 5, `tech-debt-register` 4, `blocking-issues-resolved` 2,
`spec-open-questions` 2, `po-obligations` 1, `sidecar-learning` 1. These are the **11
`append-only-event` types**, so they are the cohort where the file is a render from the start and
invariant 15 is the only body gate — and where the concurrency test is real work: two agents
appending concurrently must produce no conflict. Measured motive: `burst-log.md` alone carries
133/105/63 commits on three files, every one an append implemented as a whole-document rewrite that
can conflict. As rows they cannot.

**Cohort E — the long tail.** 940 files across **75 types with no table**, of which 16 are gap types
carrying `pending_template: true` (72 alias entries over 325 files). Order within the cohort by
mass, which is CHANGE-MANAGEMENT story 2's own list, re-measured:
`fix-burst-closure` 79 (prism) · `research-note` 69 · `architecture-section` 46 ·
`remediation-manifest` 34 · `domain-spec-section` 31 · `wave-gate-report` 28 · `proposed-adr` 28 ·
`consistency-report` 21 · `architect-decision` 21 · `holdout-scenario` 21 ·
`ux-spec-screen` 20 · `ux-spec-flow` 18 · `dispatch-package` 15 · `uncertainty-map` 14 · tail.

`ux-spec-flow` / `ux-spec-screen` (38 rivetry files, all required fields present) and
`holdout-scenario` (21 prism files, all 15 required fields present in every one) are the **first
`block` candidates in the whole plan** — highest conformance, lowest population.

**Cohort F — the derived layer.** 22–23 types. They migrate *last as authored artifacts* and
*first as shadows*: three are already shadowed (BC-INDEX, VP-INDEX, STORY-INDEX) and
`cycles/INDEX` is newly unblocked by story 4. Each advances `shadow → proven` on its own evidence,
and only then may its cell enter dual-write (the §2 composition rule).

**Cohort G — live operational state, last.** `pipeline-state` (3), `wave-state`, `sprint-state`,
`policies` (1), `release-config`, `regression-state`. This is the substrate a running session reads
on every startup; it moves after everything it points at has moved, and it is the cohort where
rollback matters most.

**Not a cohort — retired.** `delta-archive` 211 (rivetry) → versions, count-asserted, **before**
rivetry's cohort B. `decisions-archive` 4, `session-checkpoints-archive` 4,
`decisions-log-archive` 1, `lessons-archive` 1, `adversarial-review-cascade-summary` 2 → rows of
their live counterparts.

### 3.3 Project order

**rivetry first, vsdd-factory second, prism last.** Decided, with the reasons:

- **rivetry is the pilot.** Smallest by every measure (668 md files, 590 typed, 1,032 findings,
  40 applied aliases) and it is static (no concurrent session). Its one hard blocker —
  `delta-archive`, 211 files, 143 key collisions, data-bearing — is a problem that *must* be solved
  early regardless, and solving it on 211 files is cheaper than discovering the same class on
  prism's 2,784. Its `ux-spec-flow`/`ux-spec-screen`/`adr` cells are the best-conformance cells in
  the whole estate, so the ladder's upper stages get exercised early on cells that can actually
  reach them.
- **vsdd-factory second.** Largest single-type mass (1,959 BCs = 45% of the estate's typed files in
  one type in one project), 69% already body-bearing, and `datum import`/`datum shadow` already run
  against it end to end. It gets the *first cell to reach AUTHORITATIVE*.
- **prism last.** Largest by findings (10,843), by bytes (47.6 MB) and by vocabulary (150 raw
  values, 116 of them unique to it), **cannot be imported today**, and is edited by a concurrent
  session. It inherits a proven pipeline and a mature closed-enum gate rather than debugging both
  under live authoring.
- **vsdd-factory is explicitly NOT the reference implementation** (CHANGE-MANAGEMENT hazard 6), and
  the layout measurement now proves it: vsdd is the only project with `stories/epics/`, the only one
  with uppercase `VP-*` filenames, and a 7.2× BC outlier.

### 3.4 The resulting sequence

```
A  schema prerequisites            body+section tables · verbatim frontmatter · datum render
                                    · scope predicate + patterns into the registry
                                    · D1/D2/D3 · conservation as an assertion
   ├── rivetry:  delta-archive → versions (count-asserted)   ← unblocks rivetry entirely
   │
B  record spine        bc → story → vp → adr → epic          (59.4% of mass)
C  review family       adversarial-review → security/code/pr-review   (23.5%)
D  ledgers             26,632 references in ~58 files
E  long tail           gap templates first, by mass
F  derived layer       continuous, per index, shadow → proven → retired
G  operational state   pipeline-state / wave-state / sprint-state / policies      LAST

project lead:   rivetry ──(1 cohort ahead)──► vsdd-factory ──► prism
```

---

## 4. The transformation catalogue

Twelve transformation kinds. Every one is applied **only inside the write transaction that creates
the artifact version** (invariant 18: `lease → validate → transact → version → audit`), and every
one writes exactly one row into an append-only `migration_event` ledger:

```
migration_event(
  project, artifact_key, type, transform_id, field,
  before,            -- MANDATORY. A transform with no recorded `before` is REFUSED at write time.
  after,
  rule_cite,         -- e.g. aliases.yaml#adversarial-pass-report, enums.yaml#gate_result.migrated_from.HIGH
  registry_version, alias_version, corpus_pin,
  txn_id, actor, at
)
```

`before` being mandatory is what makes reversal *total* rather than best-effort:
`datum migrate revert --txn <id>` replays inverses in reverse order, and a transform that cannot state
its own inverse cannot be applied at all.

| # | transformation | domain, measured | how it is recorded / reversed |
|---|---|---|---|
| **T1** | **alias resolution** raw `document_type` → canonical | 180 aliases → 59 distinct canonical targets; **921 files** carry an applied alias (vsdd 240 · prism 641 · rivetry 40) | one row per file with `before` = the raw spelling. Reverse = write the raw spelling back. History keeps resolving through the alias **forever** (hazard 4: `BC-1.12.008` was legitimately renumbered to `BC-3.05.004`, so a flat existence check manufactures false findings against correct documents). |
| **T2** | **`set:` clause application** — the fields a spelling was carrying in its characters | **22 aliases** over **87 files**; fields set: `scope` ×17, `reviewer_role` ×9, `status` ×3, `producer` ×2, `iteration` ×1 | one row **per field**, not per file, so a partially-applied alias is visible. A rename with no `set:` is refused for any alias whose entry declares one — `local-adversary-review` (`scope: story`, `reviewer_role: adversary`) is the canonical example, and it also carries the richest review frontmatter measured. |
| **T3** | **enum coercion** via `migrated_from` | `verdict` 745 · `status` 220 migratable + 136 illegal · `scope` 170 · `level` 11 mappings · 17 closed enums total | one row per `(field, value)`, citing the `migrated_from` key. Table-driven — never inferred. Reverse = the recorded `before` token. |
| **T4** | **split fields (D-D)** — one token → up to three fields plus an int | `verdict` → `gate_result` / `convergence` / `severity_max` (+ `streak`). E.g. `CLEAN_PASS_1_OF_3` → `{gate_result: CLEAN, convergence: CLEAN_STREAK, streak: 1}`; `HIGH` (vsdd's most common `verdict`, 106 uses) → `{severity_max: HIGH, gate_result: BLOCKED}` | **one `migration_event` with N outputs and one `before`**, not N independent events — otherwise the inverse is undefined. The legacy token lives in the audit row and **never** in the artifact (invariant 17: no stored value derivable from another). |
| **T5** | **`id_alias` entries (D-C)** | the BC-1.12.008 → BC-3.05.004 corrigendum class; seeded from the two hand-maintained mapping documents that already *are* an id_alias table (`behavioral-contract-id-mapping`, `story-id-mapping`) | the `id_alias(type, old_key_hash, old_key_json, new_key_hash, from_version, reason, retire_after)` ledger defined in `FA-V1-L1-L2-STORAGE-SCHEMA.md` — **used, not redefined here**. Never a silent rewrite: the old key stays resolvable **as of the current version**, so historical documents citing it remain correct. |
| **T6** | **reserved keys** (the tombstone ledger) | retired / withdrawn / never-issued keys | the `reserved_key` ledger from the L1–L2 design. Minting scans `artifact ∪ reserved_key ∪ id_alias(old)` inside the type's lease and one transaction, so a retired id is never reissued. |
| **T7** | **key materialisation** (story 10) | `bc_id` **2,362 files** + `vp_id` **215 files** exist only in filenames | `key_materialised(path, key, source: filename)`. `path` becomes derived and never identity (D-C); the observed path is retained as `observed_path` so the render targets the same location. Note the registry validator caught its own bug here: declaring `bc_id`/`vp_id` as required frontmatter produced **2,577 false findings** on correct files. |
| **T8** | **retired-field capture** | `input-hash` **3,433** · `verdict` **745** · `delta` **188** · `changelog` | the value is captured in the `migration_event` row and **removed from the artifact**. Reversal restores it. `input-hash` is replaced by derived staleness from `inputs` + history (F8) — its own archive text already admits it reports "spurious DRIFT". |
| **T9** | **archive → versions (story 8)** | rivetry `delta-archive` **211 files**, of which 143 collide on a keyed type (74 BC · 49 VP · 18 ADR · 17 SCR · 11 FLOW) | `version_backfill(source_key, n_archived_entries, n_versions_created)` plus a **count assertion before any deletion**: `versions(source) == archived_entries(source) + live(source)`. This is the only place some versions exist; a fill-then-delete with no assertion is how a migration silently loses history. |
| **T10** | **section partition (D-A)** | fence-aware heading split, keyed by **ordinal** not heading (110 docs carry 1,968 duplicate `##`+ headings) | derived, not transformed — but gated: `concat(sections) == body` byte-exact, which currently HOLDS on all 6,537 markdown files. |
| **T11** | **verbatim frontmatter capture** | 30 / 41 / 93 unmodeled keys per body type (§1.4) | store the frontmatter **bytes** plus the parsed projection. The projection is derived from the bytes, never the reverse. This is the only design that makes X2 reachable; reconstructing frontmatter from fields loses the 30–93 keys and their order. |
| **T12** | **per-file adjudication** | `prd-supplement` (3 prism files, resolved by reading the `section` field) · `prd-supplement-edge-case-catalog` (1 rivetry) · the 3 `unresolved:` values · the 330-row Capability block · the 68 reviews whose stated count disagrees with their own body | an `adjudication(path, question, decision, decided_by, at)` row authored by a **human**. `requires_per_file_adjudication: true` **blocks bulk application** — the cell cannot leave shadow with an unadjudicated file. |

**Ordering rule inside a cell:** T1 → T2 → T3 → T4 → T7 → T8 → T11 → T10, then T5/T6/T9/T12 as
they arise. Order is a correctness property, not a preference — this spike measured a rule-order
bug that "asserted the *opposite* of the truth on 18 rows" (emptiness-before-counting in
`datum/shadow.go:541-551`), and the same class is available here: applying T3 before T1 coerces
against the wrong type's enum.

---

## 5. The acceptance gate — `datum migrate verify`

Completeness is a measurement. Six checks, plus the eight protections that keep the gate itself
honest.

### 5.1 The six checks

| # | check | pass condition | reported as |
|---|---|---|---|
| **V1** | **Conservation, in all three directions** | per `(project, type, form)`: `on_disk == migrated + declared_out_of_scope + rejected_with_reason`; `skipped_without_reason == 0`; and the reverse direction — every row resolves to a file or to a declared derivation | a census table, never a boolean |
| **V2** | **Byte-exact round trip for 100% of bodies** | `N_files_compared`, `N_equal`, `N_differ`, and a tree fingerprint. `N_differ > 0` fails. Both directions: `render(store) == md` byte-exact **and** `import(render(store)) == store` at store-fingerprint level (invariant 15). Evaluated **per shape**: `document`/`record` types are gated at capture by 16 and at cutover by 15; the 11 `append-only-event` types only by 15; the 4 `blob-with-path` types by path + content hash. **Any type not declaring a shape is gated by all of them** — silence is not an exemption. | per-type table + the first 20 differing paths with a byte offset |
| **V3** | **Per-type count parity** | `datum count` == on-disk == every `corpus_assertion` about the type (217 such claims for vsdd today) or an adjudicated exception with an owner | per-type triple `(counted, on_disk, asserted)` |
| **V4** | **Conformance-baseline preservation** | the conformance total and each project slice reproduced **against the baseline artifact at its recorded version, never a literal count (F3)**, with delta **0**, or reconciled to *registry evolution* vs *corpus drift* vs *untracked files* — the three causes the 18,418→18,826 reconciliation already established | a reconciliation table, and the `{registry_version, corpus_pin, dirty_file_list}` each number was taken at |
| **V5** | **Zero unmodeled `document_type`** | `validate_registry.py` PART 1 exits 0 per project; every raw value canonical, aliased, gap-typed or explicitly retired **with a reason** | per-project value census |
| **V6** | **Per-form counts, nothing dropped silently** | every extractor reports `(seen, kept, collapsed, malformed, skipped+reason)`. Any nonzero `skipped_without_reason` **fails**. Collapsing is legal only where the relation is a set, and the collapse count is printed | the census already printed at `datum/import.go:436-443`, promoted from print to assertion |

`datum migrate verify` **refuses to run** if the corpus pin recorded in `import_run` differs from the
working tree's current pin, including the dirty-file list. That is not pedantry: prism's `.factory`
moved 5 commits between the registry's pin and today, and the README already documents the failure
of "quoting a number whose input moved underneath it."

### 5.2 How this migration avoids being the ninth silent parser loss

A parser that loses input is the most repeated defect class in this spike — **eight instances**,
each recorded in `research/LESSONS.md §2` with what it faked:

1. frontmatter parser skipped lines starting with whitespace or `-` → dropped **every** list-valued
   edge; `bc_trace` came back empty and was reported as "unmigrated" rather than "unparsed";
2. multi-line inline lists truncated → hid **19 of 27** dangling story references;
3. bold-ID regex anchored to `$` → silently lost `DI-017`/`DI-019` (universe 16 vs 18 declared);
4. continuation rule keyed on bracket **balance** → every key after a prose bracket in
   `BC-INDEX.md` disappeared, hiding `total_bcs: 1955` — the index's own headline claim — from the
   gate whose job is checking stated counts, plus **19 real edges** (published total 1,490 was an
   undercount; it is 1,509);
5. `INSERT IGNORE` downgraded FK violations → reported **zero** dangling references;
6. splitting a DDL file on `;` → created an empty database that still had a valid `dolt log`;
7. `git rm --cached` aborting on any untracked path → untracked nothing while reporting success;
8. swallowing an exit code via `| tail -1` → a CI **livelock**, five successful runs in a row
   forever.

**The ninth already exists and I measured it today: prism's 80 verification properties, invisible
to `datum import` because of a case-sensitive filename regex, with no error and no finding** (§1.4 D3).
So the protections below are not hypothetical hardening; the first one is a fix for a live bug.

| # | protection | the instance it answers |
|---|---|---|
| **P1** | **A zero result is a failure, per type.** If a project's profile declares a type and the extractor yields 0 rows for it, `datum` fails. The existing guard is corpus-wide (`datum/import.go:102-106`, "no records found — wrong path?") and therefore missed a whole layer of one project. | #9 (prism VPs), #1, #3, #5 |
| **P2** | **Conservation as an assertion, not a print.** The census at `datum/import.go:436-443` already reports dupes/malformed and the comment says why ("an extractor that prints only its successes has silently lost input five times in this spike"). Promote it to a gate: unbalanced = FAIL. | #2, #4, #6 |
| **P3** | **Vocabularies and patterns read from the registry, never hardcoded.** Transferable result 4: three times in one session a hardcoded list *was* the defect, disagreeing with a sibling implementation on 8 spellings both ways. Filename/path patterns move into the registry per type with per-project overrides, and `datum doctor` fails on any file matching no declared pattern (the 225-unmatched-files class). | #9, and the `cycles/`-only review scan that hides 53 + 44 files |
| **P4** | **Two independent implementations, gated per file.** The Go importer and `validate_registry.py` already disagree-and-reconcile; keep both and gate on **per-file** agreement, not on totals. Precedent: the Go/Python parity diff caught 7 link fields and was "off by exactly ONE file". | #4 (found by chasing 6-vs-7), #2 |
| **P5** | **A hand-worked sample per type, measured before the rules are written.** ≥20 files per type, hand-classified, compared cell by cell. Precedent: `probe_indexes.py` ran before the shadow differ's rules existed, and the first rule cuts still produced **~2,768 findings that were artefacts of their own normalisation** — 4× the 658 real ones. | the whole class |
| **P6** | **No threshold anywhere.** No sample fraction, no "≥95% agreement", no rounding. The corpus already shipped a validation floor at **6.75% against a required 20% because nothing computed the ratio**, and a mutation gate specified as "exactly 80 — no rounding" was retired by consensus. `datum migrate verify` has one tolerance: zero. | #4, and the review's own extraction-validation finding |
| **P7** | **The verdict is derived at print time.** LESSONS rule 8: never write the conclusion into the report string while writing the test — it survives the test failing. `datum migrate verify` computes PASS from the census in the same expression that prints it. | the B12 "=> both directions work" false pass |
| **P8** | **A deliberate mutation suite.** Before the gate is trusted, inject each known loss shape and require a catch: drop a section · lowercase a filename · duplicate a natural key · overflow a column · remove a frontmatter key · reorder frontmatter keys · strike a row through · add an untracked file. A checker that finds nothing must not report success. | all eight, plus #9 |

---

## 6. Abandonment

Rollback is per `(project, type)` cell, never global, and every stage has a defined inverse.

| from | how to roll back | why it is safe |
|---|---|---|
| **stage 1 shadow** | delete the store directory | nothing was written. `datum shadow` writes nothing (hash-verified) and `datum import` is idempotent and re-runnable in 5.6 s. The corpus is untouched — 0 files modified in three corpora across this whole spike. |
| **stage 2 dual-write** | stop writing through `datum`; re-permit raw `Edit`/`Write` on the type's paths | the markdown was still authored and committed for the whole window; the store was a follower. The `datum`-side history is retained, not lost. |
| **stage 3 authoritative** | `datum render` the type, commit the render **as** the authored form, re-permit raw edits, revert the type's retirement-ledger entries | this is exactly what **Z2's restore drill** proves before stage 3 is entered: the committed render re-imports to the same fingerprint, so it is a complete authored artifact and not a lossy export. Stage 3 is reversible *because* Z2 passed. |
| **stage 4 md retired** | `git revert` the per-type deletion commit, then treat as stage 3 | deletions are per-type commits, and the render already sits at the same paths, so the revert restores authorship rather than content. |

**What makes the whole thing abandonable:**

- the render is committed from stage 2 onward, so the markdown tree is never more than one commit
  behind the store;
- the store is gitignored but its history is pushable, so rollback loses no history;
- **invariant 21** as ratified — no force path, no auto-merge, no auto-rebase **on artifact data** —
  so no rollback step can destroy a concurrent writer's work (the `factory-cas-push.sh` failure mode
  is structurally absent). A *lease* is not artifact data, so TTL expiry and human-authorized
  revocation are permitted and audited; what is forbidden is a force that overwrites a version;
- every transformation carries a mandatory `before`, so `datum migrate revert --txn` is total;
- cells are independent, so an abandonment is scoped to one type in one project.

**When to abandon (the criterion, not just the mechanism).** A cell rolls back if: (a)
`render --check` fails twice for a reason inside `datum` rather than inside the corpus; (b) a
conservation gate fails and the cause is not found within one working session; or (c) **a loss class
is found that the gate did not catch** — because that means the gate is unproven, and an unproven
gate on a migration is worse than no migration.

---

## 7. Concurrency

### 7.1 N projects, independently

- **One store per project** (M9), one shared registry — the single canonical copy already
  `go:embed`'d from `datum/registry/` and read by the Python tooling, so there is no second copy to
  drift.
- Stores are **separate databases in separate directories**, not branches of one database. Two
  measured reasons: invariant 9 (trust zones must be separate directories — zones under one
  `--data-dir` leak via cross-database query) and invariant 12 (push contention is per-branch, and
  all Dolt branches share one git data ref, so per-project *branches* of one store would serialise
  three projects behind one pointer while per-project databases with their own remotes do not).
- Every query is scoped by project as well as by cycle (invariant 19), and an unscoped aggregate is
  refused.
- Cells advance on their own evidence. There is no cross-project gate, so rivetry sitting at
  authoritative on `adr` while prism is still at stage 0 on `adr` is a normal state, not a
  divergence.

### 7.2 A project mid-migration, with the factory still running

This is prism's situation right now: 8 dirty story files, `.factory` advanced 5 commits during this
session, and a separate factory session doing the advancing.

- **Stage 1 requires nothing of the running factory.** Import is read-only, idempotent and 5.6 s.
  The measured evidence that this is safe: prism advanced 75 markdown files and both its conformance
  total (10,843) and its type census were **unchanged**.
- **Re-measure-on-advance is a gate, not a courtesy.** `import_run` records the corpus pin (commit
  sha + the dirty-file list); `datum migrate verify` refuses if the pin moved since the evidence was
  collected. The alternative is the failure the README already names.
- **A dirty working tree is a first-class state.** All three corpora are dirty right now (29 / 8 / 9
  entries). `datum migrate verify` neither ignores them — that is how the +22 untracked-prism-files
  delta happened — nor fails on them: it pins them as a named class and reports them.
- **Stage 2 needs a quiesce window scoped to one type, not to the project.** A store-side lease over
  that type's path set (F4). Invariant 11 is the measured reason a global lock is wrong: one mutex
  over the whole branch makes two sessions on disjoint subsystems serialise, which is precisely the
  incentive to `--force` that the current design created.
- **Stage 3 is the only stage that needs a scheduled window**, because it is the moment the running
  factory's writers change. It is per type, so the window is minutes for `adr` and a planned event
  for `behavioral-contract`.
- **Never migrate cohort G while a session is live.** `pipeline-state` / `wave-state` /
  `sprint-state` are read at session start; that is why they are last.

---

## 8. Risk register

| # | risk | measured basis | mitigation | detecting gate |
|---|---|---|---|---|
| **R1** | a parser silently drops a whole form | **LIVE:** prism's 80 VPs → 0 rows, no error (`datum/corpus.go:138`) | P1 zero-result-is-failure, per type; patterns from the registry (P3) | V1 conservation; `datum doctor` on unmatched files |
| **R2** | duplicate natural keys handled three ways, one of them lossy | **LIVE:** bc → finding at insert; story → **first-wins** at scan (`datum/corpus.go:502`); vp → crash. rivetry 74 BC + 49 VP, prism 7 story | one declared collision policy per type; **first-wins banned**; a collision is an `id_alias`, a version, or a hard failure | collision census must be 0 or fully adjudicated (T5/T12) |
| **R3** | a column overflow aborts the import mid-corpus | **LIVE:** `prose_ref.target VARCHAR(220)` untruncated (`datum/schema.go:277`, `datum/import.go:352`) while siblings truncate | every text column LONGTEXT, or truncation is an explicit recorded event | zero silent truncations; truncation is a row, not a `truncRunes` call |
| **R4** | deleting `delta-archive` loses the only copy of some versions | rivetry 211 files, 143 keyed | T9's count assertion **before** deletion | `versions(source) == archived + live`, per source |
| **R5** | a derived index resurrects retired records | 41 legacy stories, exact set equality 41==41 | scope predicate in the **registry**, not in Go | `shadow.scope-excludes` finding + the set-equality assertion |
| **R6** | frontmatter loss on round trip | 30 / 41 / 93 unmodeled keys per body type; `BCRow.Body` is post-frontmatter | T11: store frontmatter **bytes**, derive the projection from them | V2 byte-exact, including key order |
| **R7** | baseline drift mistaken for corpus drift (or vice versa) | 18,418 → 18,804 → 18,826, decomposed as +408 registry tightening on byte-identical input and +22 untracked files | every baseline carries `{registry_version, corpus_pin, dirty_list}`; a delta must be attributed to one of three causes | V4 reconciliation table; refuse on moved pin |
| **R8** | a concurrent factory session invalidates the evidence | prism advanced during the registry work **and** during this session | corpus pin in `import_run`; refuse-on-moved-pin | V4 / `datum migrate verify` precondition |
| **R9** | an alias bulk-applied where per-file adjudication was required | `prd-supplement` ×3, `prd-supplement-edge-case-catalog` ×1, 3 `unresolved:` values | `requires_per_file_adjudication` blocks bulk apply | X6/T12: no cell leaves shadow with an unadjudicated file |
| **R10** | a split-field transform is irreversible because the source token was discarded | `verdict` → 3 fields + `streak`, 745 files | mandatory `before` in `migration_event`; one event with N outputs | a revert drill on a sample, per type |
| **R11** | store and files diverge during dual-write | M8; and the corpus already has 5 competing authorities on where artifacts live | PreToolUse deny on the type's paths; every markdown diff must join to a txn id | `render --check` per commit + the divergence join (Y2) |
| **R12** | a path-coupled extractor misses a project's layout | prism has no `stories/epics/`, rivetry has no `stories/` at all; reviews read only under `cycles/` (53 + 44 files outside); 225 of 3,145 vsdd files match no registry pattern | per-type patterns in the registry with per-project overrides; **no hardcoded path in Go** | `datum doctor` fails on any file matching no declared pattern |
| **R13** | the migration needs writes to a corpus that is read-only by policy | the 2 namespace renames are **BLOCKED ON USER**; `validate_registry.py` prints `EXIT CRITERION NOT MET: 2` | `datum` writes only its own store until the ADR lands; factory changes are a separate workstream (V-E) | story 1's exit criterion in CI |
| **R14** | an enum coercion collides with a live field meaning | measured **twice**: `gate` is a prism identifier (`gate: wave-3-integration-gate`), and `scope` already carries two meanings (prism = blast radius 208 files; vsdd = target) | measure a field name across all projects before claiming it; record per-project semantics (vsdd's `scope` → `target`) | the registry validator's own false-finding checks (225 / 391 / 2,577 precedents) |
| **R15** | growth outruns the plan | `cycles/` 15.8 MB; prism markdown 47.6 MB; growth unmodelled (open gap 5) | measure store size per cohort; **no summarise-and-discard** — beads' 70% decay mitigation is forbidden for an authoritative spec corpus | a size report per cohort in `datum migrate verify` |
| **R16** | a review has no declared natural key, so its identity is its path | the key is the corpus-relative path today, which **D-C forbids as identity**; 186 prism files share the basename `pr-description.md` with different content | declare a composite key for the review family before cohort C leaves shadow | X1/X3 on cohort C; `two review documents claim the same key` finding |

---

## 9. Open questions — these need a human call

1. **Does prism's markdown get renamed, or does the registry learn lowercase?** prism's 80
   verification properties are `vp-001-*.md`; vsdd's are `VP-001*.md`. Either prism does 80
   `git mv`s (a real diff in a live project) or the registry declares a per-project filename pattern
   and the estate keeps two spellings forever. I lean **per-project pattern**, because hazard 6 says
   vsdd is not the reference and because a rename is a change to a corpus we are not authorised to
   write. **This blocks prism's cohort B.**
2. **prism's 7 colliding story ids** (`S-5.01-mcp-bootstrap` vs `S-5.01-FOLLOWUP-MCP-BOOT-mcp-server`,
   `S-1.12`, `S-3.04`, +4). Is a FOLLOWUP a **new version of the same story** or a **new story
   needing its own id**? The answer decides whether these become versions (T5) or renumberings, and
   it cannot be guessed from the files.
3. **rivetry's `delta-archive`: versions or history-only?** 211 files, 143 colliding on a keyed type.
   Story 8 says load them as versions of their `source_file` and then delete. Confirm that the
   reconstructed sequence is authoritative enough to delete the sidecars — this is the one place
   some versions exist.
4. **Does `epic` migrate at all for prism and rivetry?** vsdd has 17 epic files; the other two have
   none, and prism has 265 stories with no `stories/epics/`. Is `epic` a vsdd-local concept or a
   gap in the other two?
5. **`consistency-report` vs `consistency-validation-report`** — the registry's own near-duplicate,
   both with templates, neither obviously primary (aliases.yaml `unresolved:`). One of them has to
   lose, and only a human can say which.
6. **`proposed-adr`: a type, or `adr` with `status: draft`?** 28 prism files. `do_not_execute` is
   load-bearing and both readings are defensible (CHANGE-MANAGEMENT §6 left this open).
7. **What is the retirement date for the alias ledger's `retire_after`?** Aliases must keep
   resolving for history forever, but new *writes* of an aliased spelling should stop being legal at
   some point. Which stage? I propose: at the moment the cell reaches **authoritative** — but that
   is a policy call.
8. **Who owns the adjudication queue?** The cells cannot advance without human decisions on the
   330-row Capability block, the 218 POLICY-8 findings, and the 68 reviews whose stated finding
   count disagrees with their own body. These are product-owner calls, not tool calls, and the plan
   stalls without a named owner and a cadence.
9. **Do the 1,184 no-frontmatter markdown files and 193 typeless ones migrate, or stay as
   `blob-with-path`?** They are 21% of the markdown estate and have no type. A blanket
   `blob-with-path` is honest but means one fifth of the corpus is never schema-checked.
10. **Is prism authorised to be quiesced at all?** It is under active development by another
    session. Cohort G and the stage-2 windows need a scheduling agreement with whoever owns that
    session, or prism's migration is limited to stage 1 indefinitely.

---

*Every number in this document is reproducible from the kick-start in `HANDOFF.md` plus
`registry/validate_registry.py`. The three corpora were read-only for the whole of this work.*
