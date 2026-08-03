---
title: FA-V1-DESIGN — the production-grade v1 architecture spine
date: 2026-08-02
purpose: settle the layering, invariants and acceptance bar for fa v1, where fa is the SOLE HOME of every factory artifact
status: SPINE — layer designs in progress; nothing implemented (design-only by direction)
decisions_settled: 2026-08-02 (authoring surface · v1 scope · type system · write access)
---

# `fa` v1 — the spine

## 0. The four decisions taken 2026-08-02

| # | Decision | Consequence |
|---|---|---|
| **V-A** | **`fa` is the source of truth. Markdown is a rendered view.** | Authoring goes through `fa` against a closed schema. Committed markdown is a generated review surface + offline backup, gated byte-exact. Every skill/agent that writes `.factory/**` is rewritten to call `fa`. |
| **V-B** | **v1 scope is the whole operational substrate** — store, gates, engine, scheduler, PR/CI join, cost, attestation. | `fa` replaces the markdown-plus-hooks machinery rather than sitting beside it. The 62 hooks, 5 bash helpers and 7 hand-maintained indexes are retirement targets, not integration targets. |
| **V-C** | **The canonical type set is designed, and the corpus migrates onto it.** | The registry's 103 canonical types + 180 aliases + 17 closed enums are the starting point, not the ceiling. Variant spellings are not ported; they resolve at migration and are then unrepresentable. |
| **V-D** | **vsdd-factory is writable on a branch; local commits only, ask before push.** | Template→schema conversion, hook retirement and the 2 namespace renames can proceed as local commits on a branch. |
| **V-E** | **This workstream builds `fa` only. The vsdd-factory changes are a separate workstream and are DOCUMENTED here, not made.** | Deliverable: `research/FA-V1-FACTORY-CHANGES.md` — a change spec precise enough to execute against without re-deriving it. |
| **V-F** | **Every project using the factory migrates, not just vsdd-factory.** | Multi-tenancy is a v1 requirement, not a later feature. Measured today: vsdd-factory **6,951** conformance findings · prism **10,843** · rivetry **1,032** (18,826 total). prism is the largest and is edited by a concurrent session — **re-measure before trusting any prism count.** |

### Ratified consequences of the L1–L2 design (2026-08-02)

Two of its calls change the spine and are adopted:

- **One store PER PROJECT, and no `project` column.** The predicate is discharged by *store
  selection* rather than by a `WHERE` clause. The argument that decides it is measured, not
  aesthetic: push contention is **per-branch and untunable** (`research/SCALE.md`: 10 clones on one
  branch produced 54 attempts *with disjoint rows*, versus 1 each on distinct refs, and backoff
  tuning made it **worse**). A shared store would therefore make vsdd-factory's writes reject
  prism's for no semantic reason. It also matches invariant 19's actual failure mode — **an
  omittable predicate is the defect; a store handle cannot be omitted.** The registry stays shared by
  living in the binary.
- **The registry GENERATES the schema** — one uniform model (`artifact` + `artifact_field` +
  `artifact_ref` + body/section) with per-type views, rather than 119 hand-written tables. Coverage
  stops being ~101 separate tasks and becomes definitional. The typed-core/generic-tail hybrid was
  rejected on this project's own evidence: 5 types carry 3,801 of ~3,900 artifacts while 62 of 119
  have 0–1 files, and **two homes for one field is precisely the defect this spike exists to kill.**

⚠ **The one genuinely unmeasured risk in the whole design** is the pivot cost of the field-per-row
model at corpus scale. Per this repo's standing rule it gets measured before it gets committed to —
a materialization fallback is specified but has **no trigger**, and a design resting on an
unmeasured assumption is exactly what "never report a number a test could contradict" forbids.

### Ratified consequences of the L5–L6 design (2026-08-02)

- **Evidence exists only if `fa` produced it.** `fa gate exec` is the *sole* writer of the evidence
  table; no flag accepts evidence bytes. This is the sharpest expression of invariant 22 and it
  collapses POLICY 5's six-level cure chain (`v1.3 → v1.3.1 → v1.3.3 → v1.3.4 → v1.3.5 → v1.3.6`,
  recorded in its own `last_amended`) into a single field — because reproducibility-at-a-SHA is a
  property only the executor can hold.
- **Unevaluable = `error` = block. No fail-open, anywhere.** Plus a mandatory vacuity guard, because
  the corpus already demonstrated a gate passing on an empty set.
- **`deferred` is abolished** as a gate status and replaced by deferral rows carrying an owner and an
  expiry. Today `gate_status: deferred` satisfies the wave prerequisite with no rationale, owner or
  expiry — and the sibling hook's error message *recommends* it.
- **`novelty` is NULL when N+D = 0, and NULL never satisfies a comparison.** That single typing choice
  kills the live `0.0 (0 / (0 + 0))` division-by-zero without a special case. N/D come from
  store-side `finding_link` rows, so the adversary's context wall stays intact — it is no longer
  asked to classify duplicates against a corpus it is forbidden to read.
- **ONE termination rule, `converge.v1`: keep 3 clean passes, and retire `novelty <= 0.15`
  entirely** rather than arbitrating between the hook's threshold and the skill's qualitative "LOW".
  Monotonicity forces `clean_streak = 0` until the regression is dispositioned.
- **Three-valued conditions: UNKNOWN blocks rather than skips**, and `step_dep.on_skip` is
  non-nullable. This is the fix for the 140 conditional-dependency edges, and it fails safe.
- **`manual: true` satisfies invariant 22 via a machine-produced attestation** — who, when, against
  which `store_version` — typed so queries can separate *attested* from *executed*. A refinement of
  22, not an exception to it.

### Ratified consequences of the L3–L4 design (2026-08-02)

- **The op vocabulary is GENERATED from the registry**, not authored — 103 types × ~8 verbs ≈ 800
  names. Hand-writing them would guarantee a sixth instance of this repo's
  vocabulary-drifts-from-vocabulary defect. And the enforcement of invariant 17 is beautifully cheap:
  **ops for `authority: derived` types are simply not emitted.** You cannot author a derived value
  because no verb exists to do it.
- **No op accepts a path, an id, or a count.** That one rule retires the ~28 unregistered homes, the
  SHA-transcription class, and the six-BC-totals class *by construction* rather than by check.
- **Validation is an ORDERED 14-step ladder, and the order is TESTED** (role → type → authority → key
  → enum → ref → required → placeholder …). Directly earned: this repo measured a rule that put
  emptiness before counting and thereby asserted **the opposite of the truth on 18 rows**. Rule order
  is a correctness property, so it gets a test.
- **A wall is a `read_deny` predicate returning `DENIED-ASYMMETRY` (exit 3), evaluated BEFORE the op
  learns whether the artifact exists.** The reasoning is the sharpest security point in any of the
  four designs: *a refusal that distinguishes forbidden from absent is an oracle.*
- **No write escape hatch** — four cases, four answers: prose goes through D-A, a missing field goes
  through `fa propose field` (exit 4), some requests are impossible by construction, and read-only
  curiosity gets `sql --read-only`. Never raw write SQL.
- **`fa render` is four renderers keyed on `(authority, shape)`** — ledger / authored / derived / blob.
  **Authored bodies are never regenerated**, which removes the 214,554-table-line round-trip hazard by
  decision rather than by code.
- **Invariant 15 is three gates (byte / store / hash), compared per-artifact per-field, never as a
  corpus digest** — because a corpus digest tells you only *that* something broke. Taken literally,
  byte-exactness is unachievable anyway: **1,189 distinct frontmatter key orders** and **169 keys
  written both quoted and bare**, so the legal normalizations must be declared and tested.
- **The scope predicate must be a FIELD predicate, not a path prefix.** The existing
  `ExcludeSrcPrefix` approach would promote path-as-identity into the standard, which D-C forbids.

⚠ **`fa render` is blocked on schemas, not on an engine.** **All 22 derived types declare zero
sections**, and the three highest-churn indexes (BC-INDEX 218 commits, VP-INDEX 140, cycle-index 140)
have no template either. Authoring those 22 render schemas is a discrete, assignable work item and it
is on the critical path — no renderer can be written against a type that does not say what it looks
like.

**`status` vs `lifecycle_status` — measured, and a resolution recommended (pending ratification).**
The L1 design asked for a PO call on the 1,949-of-1,959 disagreement. Measured over all 1,959 BCs:

| field | distribution |
|---|---|
| `status` | **draft 1,951** · active 6 · ready 2 · withdrawn 1 |
| `lifecycle_status` | active 1,945 · retired 5 · deprecated 4 · fulfilled 1 · draft 3 · withdrawn 1 |

The dominant pair is `('draft', 'active')` on **1,937** files. These are therefore **not two copies of
one fact** — they are authoring-maturity and lifecycle-state, and the first has degenerated to a
constant carrying no information (99.6% `draft`). D-D's "narrow `status` to lifecycle only" resolves
to: **retire `status` as a dead field, keep `lifecycle_status` as the lifecycle**, and have the
BC-INDEX Status projection read the live field. This also explains a correction already on record —
BC `Status` looked like 0.8% agreement until the probe was pointed at the field the index actually
tracks.

⚠ **The 2 namespace renames are now a hard precondition, not a tidiness item.** Schema generation
reads the registry, so `story-spec`→`story` and `state`→`pipeline-state` must land before generation
is meaningful. They were previously filed as blocked-on-user cleanup.

### What V-F changes about the design

The three corpora do not share conventions, and the registry already records where they diverge —
aliases carry per-corpus counts (`corpora: {prism: 109, vsdd-factory: 47}`), and the registry work
already found that **`gate:` is a prism identifier** (`gate: wave-3-integration-gate`) and that prism
uses `scope` with PR-LEVEL/LOCAL/spec values. So:

- The canonical type set must be **project-independent**, with per-project divergence handled by the
  alias ledger at import and unrepresentable thereafter.
- A field name cannot be claimed without measuring whether some project already uses it — this repo
  has been caught by that twice (`gate`, `scope`).
- Migration is **N independent migrations against one shared registry**, each independently stageable
  and abandonable. A project mid-migration must not block another project.
- Every query is scoped by project as well as by cycle (invariant 19).

These join the four one-way doors already settled 2026-07-31 (**D-A** prose = verbatim body bytes +
derived ordinal section partition, gated byte-exact · **D-B** store gitignored, render committed,
invariant 15 `import(render(store)) == store` · **D-C** per-type declared natural key, `path` derived
and never identity, plus an `id_alias` ledger · **D-D** `verdict` retired into
`gate_result`/`convergence`/`severity_max`, `status` narrowed to lifecycle). **Do not relitigate any
of the eight — nor V-G..V-L, settled in §§5b–5e.**

## 1. What V-A actually buys — the reason this is smaller than it looks

The six-area review found ~40 distinct defects. Under V-A + V-C most of them are not *fixed*; they
become **unrepresentable**. That is story 7's argument generalized: *eliminate rather than detect*,
which the F-* measurement put at 25.3% ±9.1 of the adversary's findings for indexes alone.

| Defect class found by the review | Under `fa` v1 |
|---|---|
| 7 spellings of one `document_type`; 21 verdict tokens in a 2-value field; 17 severity tokens; 11 closure tokens | **Impossible** — closed enum validated at write time. Aliases resolve on import only and are never writable. |
| Six BC totals; a table contradicting its own column sum; 5 of 10 subsystem counts; 5 of 17 epic rollups | **Impossible** — counts are derived projections with no stored copy to drift. |
| 37 phantom STORY-INDEX rows; 1 unindexed BC; 4 STORY-INDEX schemas | **Impossible** — indexes are projections, not artifacts. |
| ~28 unregistered artifact homes; 225 unmatched files; `planning` vs `plans`; case drift | **Impossible** — agents never name a path; `fa` computes it. |
| ~14 finding ID families; a format hook validating one of them | **Impossible** — one namespace, minted by `fa`. |
| Self-referential SHA chains; TD-VSDD-053/044; `verify-sha-currency.sh` | **Impossible** — identity is store-assigned, never transcribed into content. |
| `capability: "E-12"` (epic id in a capability field); 1,465 placeholders in 3 dialects | **Impossible** — typed reference with target-type checking; placeholder is one declared state. |
| CAS-push-as-force; lock inside the protected file; fetch-before-check that reads a local file | **Gone** — leases and versions are store-side; there is no force path. |
| Convergence read from hand-written JSON; novelty self-reported; monotonicity warned-not-failed | **Derived** — computed from finding rows, not claimed. |

**The residue that `fa` cannot make impossible** and must therefore *detect* well: semantic
correctness (an AC anchored to the wrong-but-existing BC), prose quality, and human judgment calls.
The class-C decomposition measured that residue at **26.3% of class C reachable by neither rows nor
extraction** — so the honest ceiling is detection, and v1 should not pretend otherwise.

## 2. Layering

Seven layers, each with one job. A layer may only call the layer below it.

```
L7  INTERFACES     CLI · MCP server · CI entrypoints · (later) HTTP
L6  ENGINE         workflow-as-data · phase/wave/loop/approval frontier · scheduler · budget
L5  POLICY         gates as queries · findings · convergence · baselines/ratchets · attestation
L4  PROJECTIONS    render (markdown view) · indexes · counts · graph · traceability
L3  SEMANTIC OPS   the only write surface: typed operations, never raw SQL
L2  SCHEMA         registry-driven types · closed enums · natural keys · references · scope
L1  STORAGE        versioned artifacts + bodies + sections · transactions · leases · audit
```

**Why the L3 boundary is load-bearing.** Agents and skills call semantic operations
(`fa bc set-postcondition`, `fa finding add`, `fa gate record`), never SQL and never file paths. That
single constraint is what makes L2's guarantees hold, what makes L1's audit complete and attributable,
and what lets the storage engine change without touching a caller. It is also the boundary at which
least-privilege becomes expressible: a role is a set of permitted operations, not a set of writable
globs.

## 3. Invariants — v1 is not production-grade until every one is gated

Existing invariants 1–14 carry forward from `research/SPEC.md`. v1 adds:

| # | Invariant | Why |
|---|---|---|
| **15** | `import(render(store)) == store`, byte-exact | D-B. The only honest proof migration is lossless and reversible. Currently declared and **unbuilt** — highest-priority gap. |
| **16** | Every artifact stores its **verbatim body**, and its section partition satisfies `concat(sections) == body` | D-A. Today only 3 tables carry a body, so 31% of the corpus cannot be rendered back. **Ratified per-shape 2026-08-02:** 4 `blob-with-path` types legitimately store no body, and 11 `append-only-event` types store *entries* and derive the file — so **16 binds at capture, 15 binds at cutover**. A type claiming an exemption must declare its shape in the registry; silence is not an exemption. |
| **17** | No stored value is derivable from another stored value | Kills the six-BC-totals class at the schema level rather than by check. Enforced by `authority` in the registry. **Ratified 2026-08-02:** read through `authority` — `artifact.path`, the catalog mirror and any materialized view are legal as **declared derived caches**, invalidated by the same derivation edges as any other projection. What is forbidden is an *authored* field that duplicates a derivable one. Three columns in the current schema are already violations and are migration targets: `bc/vp.version`, `version_cite.verdict`, `finding.occurrences`. |
| **18** | Every write is `lease → validate → transact → version → audit`, with no bypass path | Makes L1's audit complete and attribution total; kills the 8 non-agent `producer:` identities. |
| **19** | Every aggregate query declares a scope predicate; unscoped aggregates are refused | The 41-retired-stories result. A count that agrees while meaning something else is the defect no other check catches. |
| **20** | Every enum value, reference target and natural key is validated at write time, not at read time | The difference between "impossible" and "detected" in §1. |
| **21** | No force path, no auto-merge, no auto-rebase **on artifact data** | The CAS-as-force finding. Conflict is surfaced and refused, never resolved. **Ratified 2026-08-02:** the L1 design was right that this collided with F4's "audited `--force` lease break". Resolution — a lease is not artifact data, so revocation is permitted, but it is **TTL expiry or human-authorized revocation that writes no artifact**, never a force that overwrites a version. The factory's `factory.lock.stolen` mandatory-audit instinct is preserved; the force verb is not. |
| **22** | Every gate verdict cites machine-produced evidence; `pass` without evidence is rejected | Wave 15 declared CONVERGED with no record that three of six gates ran. |
| **23** | Identity is assigned by the store and never appears in artifact content | Retires the whole SHA-transcription class in one rule. |

## 4. The type system under V-C

The registry already does most of this and its analysis should be **used, not redone**: 103 canonical
types (68 authored / 22 derived / 13 ingested), 180 aliases, 17 closed enums, and `derivation_stage`
on all 22 derived types. What v1 must add:

1. **Store coverage.** 18 of 70 observed `document_type` values have a table. All canonical types need
   one. 14% of files have no home at all.
2. **Absorb what the variants carried.** The alias ledger records this precisely — `local-adversary-review`
   carries `diff_base`/`diff_head`/`streak`/`finding_count`/`finding_breakdown`, "the richest review
   frontmatter measured — evidence that the canonical type is UNDER-SPECIFIED, not that this one is
   deviant." Every alias with a non-empty `set:` clause is a field the canonical type is missing.
3. **Templates become schemas.** A template's frontmatter list and mandated sections are declarations
   in the registry, not prose in a markdown file. The render (L4) generates the human-facing document
   *from* the schema, which is what makes "the template and the validator disagree" unrepresentable.
4. **Retire rather than port.** 4 registry-retired types and the observed one-off types
   (`audit-table`, `vp-snapshot`, `investigation-report`, …) are migration decisions with a recorded
   reason, not schema entries.

## 5. Migration under V-A — the shape, not yet the detail

Staged **per artifact type**, reusing the ladder the registry already declares:

```
shadow  →  dual-write  →  authoritative  →  markdown retired
   |            |               |                  |
 fa shadow   fa writes      fa is the         the .md files and
 reports     + .md still    only writer;      their hooks are
 disagreement  authored     .md is rendered   deleted
```

`fa shadow` already implements stage 1 and reports 658 disagreements — that is precisely the evidence
stage 2 should be gated on, per type. Nothing flips wholesale; an in-flight project can move BCs
before it moves burst logs.

### Ratified consequences of the migration design (2026-08-02)

**⚠ INSTANCE NINE OF THE SILENT-INPUT-LOSS DEFECT IS ALREADY LIVE — IN `fa` ITSELF.** Verified
directly, not relayed: `reVPFile = ^(VP-\d+)` (`fa/corpus.go:138`) is **case-sensitive** and is used as
the *filter* in `walkMD` (`:373`); prism names all **80** of its verification properties
`vp-001-*.md`; non-matching files are skipped with no error. **prism's entire L4 layer imports as zero
rows and nothing reports it.** The bar in §6 warned that a migration is the worst possible place for a
ninth instance — it turns out #9 predates the migration and would have *been* the data-loss event.

Two more importer defects, also verified: **prism cannot be imported at all** (hard abort on a
`VARCHAR(220)` overflow in `prose_ref.target`), and **rivetry cannot** (duplicate `VP-001` from its 211
`.DELTA-ARCHIVE` sidecars — 143 key collisions). So **`fa import` today ingests one of three corpora.**
And duplicate keys are handled **three incompatible ways**: `bc` files a finding, `story` silently keeps
the first file, `vp` crashes. Three behaviours for one condition is its own defect.

**Per-project scale, measured (prism re-measured as instructed):**

| | vsdd-factory | prism | rivetry |
|---|---|---|---|
| markdown files / bytes | 3,085 / 28.0 MB | 2,784 / **47.6 MB** | 668 / 19.4 MB |
| distinct raw `document_type` | 71 | **150** | 51 |
| types no other project uses | 46 | **116** (511 files) | 29 (290 files) |
| conformance findings | 6,951 | 10,843 | 1,032 |
| **cannot round-trip under schema v4** | 579 (21.3%) | **1,287 (67.8%)** | **401 (68.0%)** |

prism advanced **5 commits / 75 md files** past the registry pin, and both its 10,843 total and its
type census are **byte-identical** — so the concurrent session did not move the numbers. 13 raw types
are shared by all three projects; **80 of 103 canonical types are in use**; and 940 typed files sit in
75 types with no table.

**Adopted decisions:**

- **Two ladders share the word *shadow* and must be composed by rule, not conflated** — the
  registry's *derivation* ladder (`shadow → proven → retired`) and the *migration* ladder
  (`shadow → dual-write → authoritative → markdown retired`) are orthogonal.
- **The unit of migration is the `(project, type)` PAIR**, not a type and not a project. That is what
  makes V-F's "N independent migrations" real.
- **Seven named stage-1 exit gates, with CONSERVATION as the explicit anti-#9 gate — zero tolerance,
  no thresholds.** Given #9 is live, this is the single most important gate in the plan.
- **Every transformation carries a mandatory `before`**, so revert is total rather than
  best-effort.
- **`fa migrate verify` refuses on a moved corpus pin** — you cannot verify a migration against a
  corpus that changed underneath it.
- **Order:** Cohort A (schema prerequisites: bodies, sections, verbatim frontmatter, `fa render`,
  scope predicates out of Go, **the three importer defects**) → rivetry `delta-archive` retirement →
  **B record spine** (bc/story/vp/adr/epic — 59.4% of mass) → **C review family** (23.5%, and the whole
  convergence dependency) → **D ledgers** (58 files, 26,632 references) → **E tail** → **F derived**
  (continuous) → **G live operational state, last**.
- **Project order: rivetry (pilot) → vsdd-factory → prism.** rivetry is smallest; prism is both
  concurrently edited and un-importable, so it goes last.

## 5b. Decisions taken 2026-08-02 (second round)

| # | Decision | Consequence |
|---|---|---|
| **V-G** | **Review identity: backfill the four declared key fields at migration.** | `cycle` from the containing directory, `pass` from the filename (already on 402 of 435), `scope`/`target` from the filename pattern. Path is **one-time evidence during backfill**; thereafter identity is the tuple and the path is derived — which keeps D-C intact, because D-C forbids path as *identity*, not as a migration-time source. A residue that cannot be derived gets hand adjudication, counted and reported. Unblocks the convergence tables in L5–L6 and the projections in L3–L4, both of which called this a cutover blocker. |
| **V-H** | **Spec Supremacy wins.** Specs outrank operational state. | STATE.md is a *position report* about progress against the contract, not a source of truth that outranks it. Cohort G therefore migrates as operational data that **can be rebuilt from the record**, which is precisely what makes crash-recovery-from-the-log possible. `CLAUDE.md`'s 12-level precedence table — where STATE.md outranks every spec — is **corrected in the factory change spec**, and `FACTORY.md:189` stands. |
| **V-I** | **Model-family diversity is retired as a gate criterion for now — and explicitly KEPT as a capability to grow into.** | See below. Not deleted, not quietly dropped. |
| **V-L** | ⭐ **SETTLED 2026-08-03: the store is a VERSIONED RELATIONAL engine holding a TRIPLE model; the graph is a PROJECTION served by recursive CTEs.** | Closes the one question the first 15 decisions left open — **no decision had ever named an engine.** L1 declares a swappable **property set P1–P7**; Dolt is retained because it satisfies all seven, not because the repo is named for it. Measured: GMS accepts recursive CTEs, so traversal is SQL (1–13 ms bounded, 356 ms whole-graph closure); the CSR engine narrows to articulation points. See §5e. |

### V-I in full, because a retired aspiration is the thing that gets forgotten

**Now:** the Phase-4 criterion "different model family (GPT-5.4, not Claude)" is retired as a *gate*.
It is unverifiable today — 44 agent files pin `opus`/`sonnet`, the 23 `model_tier:` keys have no
resolver, and the `openclaw.json` they route through does not exist — and under "unevaluable = block"
it would make Phase 4 unpassable on cutover day. What remains enforced is the part that genuinely is:
**fresh context, information asymmetry (now a `DENIED-ASYMMETRY` return code rather than a prompt),
and perspective-diverse prompting.**

**Intended:** route the six diversity-mandated roles — adversary, holdout-evaluator, code-reviewer,
pr-reviewer, spec-reviewer, session-reviewer — to genuinely different model families, with `fa`
**attesting the model that actually ran**. This is a deliberate growth target, not a discarded idea.

**Why it must not be silently dropped:** the adversarial method's whole claim to catching what the
builder cannot rests on independence. Fresh context gives *forgetting*; a different model family gives
*different priors*. Retiring the gate removes an unverifiable assertion; it does not make the
underlying property unnecessary, and the honest accounting is that **the adversarial review is
currently weaker than FACTORY.md claims.** Recorded so the gap stays visible.

**What v1 must build now so this is a config change later, not a redesign:** `fa` records the model
and provider that executed every agent-attributable operation (F18/F22 attestation), and the gate
registry keeps the criterion present with `manual: true` and a named owner so it appears in every
gate report as an open gap rather than disappearing from the schema.

## 5c. V-J — `fa` IS RUN WITH AN AI. The AI is the parser for messy input.

**Decision (2026-08-02):** `fa` is not a tool a human drives against tidy input. It runs **with an AI
in the loop**, and **the AI is how the mess gets handled** — the accumulated drift across 6,537 files
that no deterministic parser can fully absorb.

This corrects a posture that ran through the first four layer designs. I had been treating messiness as
something to **reject** — closed enums, a 14-step validation ladder, refusing unregistered paths,
`unevaluable = block`, no escape hatch. That is right for the *store*. Applied to *ingestion* it is
wrong, and it is what produced most of the "declare it out of scope" and "needs hand adjudication"
residue in the layer docs.

### The architecture this actually implies: two boundaries, opposite postures

```
   messy world                    THE ADAPTER                     the store
   6,537 files                 (AI-mediated, tolerant,          (strict, closed,
   70/150/51 raw types   ──▶   interpretive, records its  ──▶    deterministic,
   1,338 with no type           reasoning as data)                validated)
   no frontmatter at all
```

| | INGEST boundary | WRITE boundary |
|---|---|---|
| posture | **tolerant + interpretive** | **strict + closed** |
| who handles ambiguity | **the AI**, and it records why | nobody — it is refused |
| unknown input | classified, with confidence + evidence | rejected |
| unevaluable | **surfaced for interpretation** | **blocks** (invariant 22 unchanged) |
| determinism | the AI is not deterministic; **its recorded decision is** | fully deterministic |

**The rule that keeps this honest: AI interpretation is captured as DATA, never applied as a side
effect.** Every classification, field derivation and normalization becomes a transformation row
carrying its `before`, its evidence, its confidence, and the fact that an AI produced it. Determinism
moves from *the parser* to *the recorded transformation* — so a re-run **replays decisions** rather
than re-inferring them, and only genuinely new input invokes the AI again. Without that rule,
AI-assisted ingest would collide head-on with invariant 15 and with the conservation gate.

### What this DISSOLVES — items I had recorded as blockers

- **The 1,338 untyped files (20.5%) and the 76.3% typed-round-trip ceiling.** An AI reads a file and
  says what it is. The ceiling is not a property of the corpus, it is a property of assuming a regex
  had to do the typing. The bar in §6 stands, but the *route* to it changes: type the untyped rather
  than blob them.
- **The 41 legacy stories with no frontmatter.** Nothing to derive a scope *field* from mechanically —
  but an AI reads the body and derives it, with the derivation recorded.
- **V-G's review-key backfill residue.** I wrote "a residue that cannot be derived gets hand
  adjudication". That residue is AI-adjudicated at scale, with the same recording discipline.
- **The 22 missing render schemas.** An AI can infer a schema from existing instances of a type and
  propose it for ratification — which is a far better first draft than authoring 22 from scratch.
- **The ~40 one-off types with 1–4 files each.** These were the awkward tail in every layer design.
  Interpretation, not modelling, is the right tool for a type with one instance.
- **The brittle-matcher class generally.** Instance nine (`reVPFile` case-sensitivity) is still a bug
  to fix, but the *category* — a regex deciding what a file is — stops being the mechanism.

### What this does NOT change, and must not

1. **Every invariant 15–23 stands.** Strictness at the write boundary is the entire reason the mess
   cannot come back. An AI-tolerant *store* would just relocate the drift.
2. **`unevaluable = block` remains, for gates.** An AI must never be the thing that decides a gate
   passed. It interprets *input*; it does not manufacture *evidence*. Invariant 22 is untouched:
   evidence exists only if `fa` produced it.
3. **No AI write path into the store that bypasses validation.** The AI's output is a *proposal* that
   goes through the same ops and the same ladder. L3–L4's `fa propose field` (exit 4) is exactly the
   right shape — it was designed for this without knowing it.
4. **The conservation gate gets stricter, not looser.** A non-deterministic classifier makes silent
   loss *easier*, and instance nine already proves this codebase's exposure. Zero tolerance stands.

### What it changes about L7, which is not yet designed

The primary consumer is an **AI agent**, not a human — so L7 should be designed for that:
error messages that are *instructions to an agent* rather than human diagnostics; stable structured
output; exit codes as control flow (the `DENIED-ASYMMETRY` / exit-3 and `propose` / exit-4 discipline
is already this); an **MCP surface as a first-class interface, not an afterthought**; and the ~800
generated op names become an asset rather than a usability problem, because an agent can hold a
vocabulary that would drown a human.

## 5d. V-K — SETTLED: the AI runs OUTSIDE. `fa` is a TOOL for an LLM harness, via CLI or MCP.

**Decision (2026-08-02), closing V-J's open question:** `fa` contains **no LLM client, no API keys, no
model configuration and no provider network calls.** It is a **tool designed to be used BY an LLM
harness** — Claude Code, Codex, or any other — exposed as a **CLI and an MCP server**. `fa` is not an
agent and never becomes one.

### The control flow is INVERTED from what "AI-assisted ingest" suggests

`fa` never calls an AI for help. **`fa` emits work; the agent interprets; `fa` records the answer.**

```
   harness/agent  ──calls──▶  fa           "what still needs classifying?"
   fa             ──emits──▶  work unit    the file, its content, its candidates
   agent          ──reads──▶  interprets   (this is the part fa cannot do)
   agent          ──calls──▶  fa           records the classification + evidence
   fa             ──validates, versions, audits, and REPLAYS thereafter
```

That keeps every property the design depends on: **deterministic, fully testable, offline-capable, no
provider dependency, and model choice plus cost stay with the caller.**

### Consequences already covered by the design

- **Two co-equal surfaces, one op set.** CLI and MCP both expose the same registry-generated ops — MCP
  is a first-class surface, not a wrapper bolted on later. The ~800 generated op names are an asset
  here, because an agent can hold a vocabulary that would drown a human.
- **Harness-portable.** It must work under Codex as well as Claude Code, so **no harness-specific
  assumptions** anywhere. MCP is the rich surface; the CLI is the universal fallback.
- **The harness supplies identity.** The role token (F16), session/trace id, and the model identity V-I
  wants. The earlier access-control work already established that an unforgeable role can only come
  from the harness injecting it — a `PreToolUse`-style hook — because `fa` cannot distinguish agents
  that share a process and a uid. V-K makes that the declared mechanism rather than a hypothetical.

### ⚠ Two consequences NOT yet in any layer design

1. **`fa` cannot VERIFY a model claim — only record what the caller asserts.** So an attestation row
   must be typed as **caller-asserted**, never as verified, and queries must be able to tell the two
   apart. This matters precisely because V-I's original defect was an *unverifiable claim treated as a
   gate*. Recording an assertion honestly is progress; recording it as proof would repeat the bug in a
   new place.
2. **Tool-call ergonomics become a hard design constraint, and this one is load-bearing.** A harness
   tool call cannot block for a 6,537-file migration. Therefore **no op may be long-running**: work must
   be **chunked, resumable, progress-reporting and batchable**, with `fa` emitting the *next* unit
   rather than doing the whole job. Combined with retry-safety — **harnesses retry tool calls, so every
   op needs an idempotence key** (F2/M-series already specify this) — this shapes the entire migration
   surface. A migration expressed as thousands of round trips only works if each is small, ordered,
   resumable and idempotent. **This is the biggest un-designed consequence of V-K and it belongs in
   L7.**

## 5e. V-L — SETTLED: a VERSIONED RELATIONAL engine holding a TRIPLE model; the graph is a PROJECTION

**Decision (2026-08-03).** This closes a question the first fifteen decisions left genuinely open:
**none of D-A..D-D or V-A..V-K named a storage engine.** Dolt was this spike's *hypothesis* — the
repository is named for testing it — and it had never been ratified. Asked directly ("should we commit
to a graph database instead?"), the answer is measured rather than argued.

### The question decomposes into two axes, and conflating them is the trap

| axis | status | answer |
|---|---|---|
| **is the DATA MODEL graph or relational?** | **already decided, implicitly** | **graph.** `artifact_field(type, key_hash, field, ord, kind, v_text…)` **is subject–predicate–object**, and `artifact_ref` is edges. L2-A already specifies a **triple store, written in SQL.** So the live question was never graph-vs-relational; it was only *which engine stores the triples.* |
| **is the STORE VERSIONED?** | **pinned by the invariants** | **yes, non-negotiably** — see below. This is the load-bearing axis. |

**Versioning is not a preference; it is already several invariants.** Invariant 15
(`import(render(store)) == store`) needs a version to compare *at*; invariant 18 versions and audits
every write; **D-B** gitignores the store and commits the render; L7 puts `store_version` in every
response envelope; `fa migrate verify` **refuses on a moved pin**; baselines and ratchets *are* diffs
between versions; the PR/CI join is a branch join; and cell-level merge is what lets two agents editing
different fields of one record merge cleanly. Remove versioning and every one of those moves into
application code — which is precisely the *two homes for one fact* this spike exists to kill.

### ⭐ Dolt IS the graph database for the TRAVERSAL workload — measured, not assumed

`fa/graphsql_probe_test.go` (`TestGraphInSQL`). GMS — pure Go, **no `dolt` binary** — accepts
**recursive CTEs**:

| capability | result |
|---|---|
| `WITH RECURSIVE` | ✓ accepted |
| reachability + shortest depth | ✓ correct (diamond resolved to depth 3 via both paths; no leak into a disconnected component) |
| a cycle | ✓ **terminates** (`UNION` dedupes) |
| cycle **detection** | ✓ exactly the 3 cyclic nodes |
| descendants, real graph (1,547 edges) | depth 1 → **1 ms** · depth 3 → **2 ms** · depth 6 → **6 ms** · depth 12 → **13 ms** (fixpoint at 6) |
| whole-graph transitive closure (depth ≤ 8) | 19,628 pairs in **356 ms** |

⚠ **This CORRECTS an overclaim in `fa`'s own help text**, which said *"algorithms SQL cannot do."* That
is true only for **articulation points** and **betweenness**. It is **false for traversal**: reachability,
shortest path, cycle detection, topological order and transitive closure are all recursive CTEs, and
**`degree` — the best measured predictor of adversary-flagged artifacts (AUC 0.871) — is a `GROUP BY`.**
Help text fixed (`main.go`).

**So the in-process CSR engine's live justification narrows to:** articulation points (50 found), plus
the 250k-node scale case it was actually built for (96× less memory, ~100× faster than gonum). Its
other headline metric, **betweenness, was tested and REJECTED** — it lost to free degree at 1/3000 the
cost. Keep the engine (built, cheap, correct); do not let it justify a separate graph database.

### Why a graph database loses, on this project's own measurements

| | measured |
|---|---|
| graph size | 2,421 nodes / 4,060 edges — **average degree 3.35**, very sparse |
| whole-graph metrics, in-process | **102 ms**, CSR at **0.1 MB** |
| record mass, for comparison | **68,866** field rows (vsdd alone) — the graph is ~6% of the mass |
| sophisticated graph algorithms | **tested and rejected** (betweenness < degree) |

A graph DB would replace a 0.1 MB in-memory structure, and add a server, to accelerate the ~6% that is
already measured in milliseconds — while giving up versioning, branch/merge, cell-level merge,
FK-refusal-at-write, and SQL gates.

**Dolt's real costs, stated honestly — and none is fixed by a graph DB:** push contention is
per-branch and untunable (54 attempts with disjoint rows; **worse** in graph engines, which mostly have
no branch model at all), **306.6×** journal write amplification on bulk load (answered by L7-M periodic
GC), **152.9×** on full-type scans (a property of the *triple* model, which a graph DB shares), and no
remote yet (phase-2 plumbing).

**The one honest alternative is named rather than ignored: TerminusDB** — git-like versioning *and* a
graph model. Declined for three measured reasons: SQL gates are load-bearing (*"a gate that is a query
cannot disagree with the data it checks"*, proven at **67/67** Go-vs-Python parity); embedded pure-Go
with **no server and no binary dependency** is load-bearing (132 tests, ~12 s, no network); and swapping
engines would reset every baseline at the moment the design's last unmeasured assumption just closed.

### ⭐ What v1 must do instead: defend a PROPERTY SET, not a product name

The real risk is defending *"Dolt"* because the repo is named `dolt-artifact-spike`. So **L1 declares
the requirements, and the engine is swappable against them:**

| # | required property | why it is load-bearing |
|---|---|---|
| P1 | **versioned, with a durable version identity** | invariants 15/18; `store_version`; `migrate verify` refuses on a moved pin |
| P2 | **branch + merge** | D-B; the PR/CI join; migration abandonable at any stage |
| P3 | **cell-level merge** | two agents editing different fields of one record must not conflict (D2/M3) |
| P4 | **SQL-queryable, incl. recursive CTEs** | gates are queries; traversal is a query (this decision) |
| P5 | **declarative referential integrity** | a dangling ref is *refused at write*, not swept for — how 39 dangling refs and 27 `story.blocks` were found |
| P6 | **embeddable: no server, no external binary, offline** | 132 tests in ~12 s, no network; V-K's offline-capable requirement |
| P7 | **transactional, one txn per unit of work** | invariant 18; measured 17× (15.7 s → 0.9 s) |

**Any engine satisfying P1–P7 is admissible.** Dolt satisfies all seven today and is retained on that
basis, not on the repository's name. A candidate failing **P1, P4 or P6** is rejected without further
measurement, because those three are what the invariants and the harness constraint pin directly.

### Two caveats carried forward, both new

1. **356 ms for whole-graph closure is not free**, and it was measured on 38% of the edges — the full
   graph is plausibly ~1 s. Under **L7-D** that makes any projection performing whole-graph closure a
   **chunked op**, not a single call. This is a real input to the unit budget and it was not previously
   known.
2. **Traversal interacts with the EAV model.** Traversal over `artifact_ref` is cheap and indexed, but
   traversal that *filters on a field* pays the pivot cost (measured **2.9×** filtered, **21.7×**
   aggregate). Measure before a projection leans on it.

## 6. The production-grade bar

"Production grade" is a measurable claim, so it gets acceptance criteria rather than adjectives:

- **Lossless — and the bar is split in two, because a single 100% claim is unachievable.**
  The L3–L4 design measured that **1,338 files (20.5% of 6,537 across the three corpora) carry no
  `document_type` at all**, so a typed round trip caps at **76.3%**. A bar that cannot be met is worse
  than no bar, so:
  - **Round trip (invariant 15) must be 100%** of what `fa` holds. An untyped file is held as a
    `blob-with-path` shape and round-trips byte-exact *without* schema validation — or it is declared
    out of scope with a recorded reason. Silence is not an option.
  - **Schema validation (invariant 20) applies to typed artifacts**, and its coverage is reported as a
    number, not asserted. Assigning types to the untyped 20.5% is a migration work item with an
    owner, not a rounding error.
  - Per-form counts reported; nothing dropped silently. A parser that loses input is the single most
    repeated defect class in this spike — **eight instances** — and the migration is the worst
    possible place for a ninth.
  - ⚠ Sizing correction: bodies reach **1.57 MB** (8 files above 600 KB), not the 211 KB this document
    first stated. The render and diff paths must be designed for that, not for the SPEC.md figure.
- **Reversible:** `fa render` reproduces a committed markdown tree that re-imports byte-identically.
  Migration is abandonable at any stage.
- **Attributable:** every write traceable to a role, lease and transaction.
- **Concurrent-safe:** no lost update under concurrent writers; conflicts refused, never merged. The
  200-agent / 20-clone scale result already measured correctness under contention; v1 must hold it
  with store-side leases instead of `--force-with-lease`.
- **Gated:** every gate verdict carries machine-produced evidence; every enum, reference and key
  validated at write time.
- **Observable:** structured audit + cost per phase/wave/story, so the budget tiers and the autonomy
  score have a real data source for the first time.
- **Parity-proven, not inspected:** the standing rule in this repo. Every migration and every
  projection is verified against an independent implementation or a hand-worked answer, not reviewed
  by reading.

## 7. What must NOT be redesigned

Carried forward verbatim from the review's keep-list, because these are better than a fresh design
would be: the three adversary perimeters with typed deferrals · brownfield's strict-binary novelty
rule and its anti-fabrication clause · the coverage audit novelty decay structurally cannot replace ·
the two-phase validation arithmetic where any non-zero delta is an error · L4 immutability with
`amends:` refinement · append-only traceability · L0–L4 readiness routing · regression always full,
never delta-scoped · fast-revocation/slow-promotion on autonomy · the release mandatory-invariants
table with a failure mode per rule · the gate presentation protocol's structured questions · and the
budget tiers that never downgrade the five protected reviewers.

---

*Layer designs (L1–L2 storage/schema · L3–L4 ops/projections · L5–L6 policy/engine · migration and
cutover) follow as separate sections.*
