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
of the eight.**

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

## 6. The production-grade bar

"Production grade" is a measurable claim, so it gets acceptance criteria rather than adjectives:

- **Lossless:** invariant 15 and 16 green over 100% of the corpus; per-form counts reported; nothing
  dropped silently. A parser that loses input is the single most repeated defect class in this
  spike — **eight instances** — and the migration is the worst possible place for a ninth.
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
