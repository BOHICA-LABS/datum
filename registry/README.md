# The artifact type registry

The standard for what a `.factory/` artifact **is**, as opposed to where it lives.
**PROPOSED, not adopted.** `~/Dev/vsdd-factory` and every sibling corpus were read-only
throughout; nothing outside this directory was modified.

| file | what |
|---|---|
| `artifact-type-registry.yaml` | **THE STANDARD.** 103 canonical types + 16 gap types + 4 retired, each declaring key · required fields · enums · link types · section schema · shape · authority · gate severity · enforcement level · profile |
| `enums.yaml` | 14 closed vocabularies, every value measured. Includes the `verdict` decomposition and its `migrated_from` migration table |
| `aliases.yaml` | 180 legacy spellings → canonical, each carrying the **field defaults** that preserve what the spelling encoded |
| `CHANGE-MANAGEMENT.md` | the ADR to open, the policy to register, 13 stories, the per-type graduation ladder, 7 sequencing hazards |
| `validate_registry.py` | the gate. Checks the registry's own completeness, then the corpora's conformance to it |
| `measure_types.py` · `observe.py` | the measurement passes everything is derived from |
| `probe_indexes.py` | STORY 7's per-column agreement measurement, run BEFORE the shadow differ's rules were written — see [research/SHADOW-INDEXES.md](../research/SHADOW-INDEXES.md) |
| `fstar_compare.py` · `fstar_hand_sample.json` | #671's exit criterion, run: extraction + the hand-classified sample behind the 40/22/38 split |
| `types_measured.json` · `types_observed.json` · `template_schemas.json` | measured output, regenerable |

```sh
python3 registry/measure_types.py && python3 registry/observe.py
python3 registry/validate_registry.py     # exit 0 today
```

## Corpus pins — every number here is a snapshot of these

| corpus | main | `factory-artifacts` |
|---|---|---|
| vsdd-factory | `82163b7f` | `0aaba144` |
| prism | `a41599fe0` | `9f3443d6f` (was `95b90d003`) |
| rivetry | `52bd25d` | `2aea395` |

prism's corpus **advanced again during the 2026-08-01 session** — the separate prism factory
session committed the 24 story files it had been holding in its working tree. Re-measured
across that advance: prism's conformance total is **10,843 either way**, because the
working-tree content this was measured against is exactly what got committed. Stated rather
than assumed, since the alternative is quoting a number whose input moved underneath it.

Pinned because **prism's corpus changed during the day this was measured** (20 files
between 09:34 and 19:18 on 2026-07-31, from a separate prism factory session — not from
this work, which was read-only and ran after 21:00). Re-run the three scripts after any
corpus advance rather than trusting a stale count.

## What running it says today

```
PART 1  registry completeness         all 7 checks OK · 0 undispositioned values of 225
PART 2  corpus conformance            18,826 findings — the ratchet's day-one baseline
        D-A invariant                 concat(sections) == body HOLDS on every file
```

⚠ **This number was 18,418 until 2026-08-01, and the change is the registry's own
evolution — not corpus drift.** Re-measured and reconciled exactly, because "off by a
little" always has a cause:

| | findings |
|---|---|
| the `902da9d` registry, on the PINNED corpora | 18,396 |
| \+ 56 untracked prism markdown files present in the working tree | **18,418** ← the number this file used to quote |
| the HEAD registry, on the PINNED corpora | 18,804 |
| the HEAD registry, on the working corpora | **18,826** ← today |

So **+408 is registry evolution on byte-identical input** — dominated by the
`missing-required` → `empty-required` three-state split (a missing key and a declared-empty
one are different claims) and by link fields becoming required. **+22 is untracked files.**
The 24 prism stories another session edited during this work contribute **0** findings: they
added `## Authority` sections, and the corpus pins are unchanged.

Exit **0** means the registry is complete and internally consistent. It exits **1** the
moment a new `document_type` appears with no disposition, which makes completeness a CI
gate rather than a claim.

## The five findings that shaped it

1. **There are TWO declared standards, not one.** The path registry declares 46
   `artifact_type` names, the templates declare 81 `document_type` names, and they overlap
   on **11**. Eight path-registry-only names are in live use as `document_type` values, so a
   template-only gate flags them as drift. Reconciled in `namespace_reconciliation`:
   **2 name disagreements** (`story`/`story-spec`, `pipeline-state`/`state`) ·
   4 path-missing · 11 template-missing. Only the first 2 are namespace defects — an
   earlier cut of this registry used one boolean for all three and so overstated it as 17.
2. **Enforcement gap by mass, design gap by vocabulary.** Canonical values cover 91% / 65% /
   57% of typed files but only **22 of 71 · 32 of 150 · 27 of 51 distinct values**.
3. **The drift tail is singletons.** Of 181 non-canonical values, **108 appear exactly
   once**; 12 values carry 783 of the 1,138 files. So: alias the head, gate the tail. An
   alias map for 181 values would be theatre.
4. **The 12 "adversarial review" spellings encode real dimensions** — `scope` and
   `reviewer_role`. A rename-only alias destroys them, which is why every alias carries
   `set:`.
5. **Two things exist only because there is no versioned store**, and are retired:
   `delta-archive` (211 rivetry files — hand-rotated changelog sidecars created by rivetry's
   own POLICY-22) and `input-hash` (3,890 files — a hand-maintained content hash whose own
   archive text admits it reports "spurious DRIFT").

## Taken from #671

Four things, each machine-checked by `validate_registry.py` (checks 1j–1m) and by Go tests:

| | where |
|---|---|
| **`generate -> prove equal -> retire`** — a derived type is never *flipped* | `derivation_stage` on all **23** derived types, all starting at `shadow` |
| **Write-time enforcement**, not only CI | `enforcement_point` (default `both`); a `block` type enforced only in CI is now rejected as a contradiction |
| **Version-pinned citations** — same syntax, opposite verdicts | `pin_policy` on all **23** link types, plus `index_cite` (floating) / `reviewed_version` (pinned) and the `version_cite` prose kind |
| **`impact`** — the reverse closure | `query_verbs`, with a declared "how to add a verb" path |

## The knowledge-graph projection

The Dolt store IS the knowledge graph; `fa/graph*.go` projects it into gonum so the
algorithms SQL cannot express become available. Measured, not asserted — see
[research/GRAPH-PERF.md](../research/GRAPH-PERF.md).

```sh
fa waves                                   # 148 stories in 16 waves, 0 cycles
fa graph build                             # 2,421 nodes · 4,060 edges in 85 ms
fa graph metrics                           # 73 ms default; --betweenness for the O(V*E) one
fa graph dot --scope subsystem | dot -Tsvg
fa graph diff --from HEAD                  # what a rehydrate-per-run graph cannot do
```

At 250k+ nodes the engine is **CSR** (two int32 arrays + an interned key slab): measured
**96x less memory** than gonum (756 MB -> 7.9 MB at 240k nodes) and ~100x faster
(articulation 980 ms -> 8.1 ms), verified by PARITY against the gonum implementation.
gonum is retained only for Louvain.

Two performance claims of mine were refuted by benchmarking them: betweenness is 236 ms at
live scale (not "single-digit milliseconds") and **52 s at 10x** (not "probably fine"). It is
now opt-in and bounded. And gonum's dense `PageRank` allocates 47 MB per call on a sparse
graph — `PageRankSparse` is **197x faster**. Default `graph metrics` went 577 ms -> 73 ms.

## Corrections this work made to its own inputs

- **"~12 legacy spellings"** → 181, with a singleton-dominated tail that changes the strategy.
- **"Split `verdict` into `gate`/`convergence`/`severity_max`"** → `gate:` is already in live
  use in prism as an *identifier* (`gate: wave-3-integration-gate`). The field is
  **`gate_result`**.
- **"18 basenames collide"** (cycles/ only) → corpus-wide vsdd 39 · **prism 173** · rivetry 8,
  with `pr-description.md` colliding **186×** in prism, every one different content.
- **Section storage is not lossy.** A fence-aware heading split → rejoin is **byte-exact on
  all 6,537 markdown files**, which is why D-A stores an addressable partition instead of an
  opaque body. Sections key on **ordinal**, not heading: 110 docs carry 1,968 duplicate
  `##`+ headings.
- **`derived` is not a shape, it is an authority.** An index is physically a document; who
  may write it is the other axis.

## Defects the validator caught in the registry itself

Kept as a record, because a registry that was never run is a wish list.

| defect | consequence had it shipped |
|---|---|
| `bc_id` / `vp_id` declared as required frontmatter | **2,577 false findings** on correct files — the ids exist only in filenames. Now `key_source: filename`, a one-time migration item |
| `scope` chosen without measuring it | **225 false findings**. `scope:` was already in use with TWO meanings: prism's matches the intent (208 files), vsdd's means *target*. Same collision class as `gate` |
| `priority` bound to the `severity_max` enum | **391 false findings** on legitimate `P1` values. A P1 story is not a HIGH finding |
| `spec-open-questions` referenced by 2 aliases, never declared | broken alias resolution |
| 2 rivetry `prd-supplement-*` values undispositioned | silent holes in the standard |
| full spine required of `config`/`blob` shapes | `policies.yaml` correctly carries no `status`; now a `shape_override` |
| `complexity` bound to an enum on no evidence | guessing dressed as a schema. Left unbound and marked unmeasured |
| one `registry_namespace_defect` boolean for THREE defects | overstated the namespace disagreement as **17** when it is **2**. Now `namespace_status: name_disagreement \| path_missing \| template_missing`, and the validator checks each kind separately |
| `link_types` held a rules LIST beside entry MAPS | untypeable in Go: `LoadRegistry` errored, a test discarded the error, and a schema-parse failure surfaced as a **nil dereference**. Hoisted to `link_rules`; tests no longer discard the load error. A schema only one of two readers can parse is the exact defect this file exists to prevent |
| a regex that matched flag lines belonging to LATER type blocks | silently mis-assigned 17 of 17 `namespace_status` values while parsing cleanly. Fixed with block-scoped editing; caught by printing the resulting groups instead of trusting the edit |
