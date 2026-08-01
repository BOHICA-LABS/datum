---
title: FSTAR-COMPARISON — #671's exit criterion, run at last
date: 2026-07-31
purpose: decide whether a frontmatter-only parser suffices, or whether the type registry needs prose-reference extraction, BEFORE 24 projects migrate onto it
method: extract the adversary's own findings from 390 review documents; hand-classify a random sample by what a parser would have to SEE
status: ANSWERED. #671 is partly right. The registry needs an ADDITION, not a redesign.
corpus_pin: vsdd-factory .factory @ 0aaba144
---

# Can `fa` reproduce the known F-\* findings?

[#671](https://github.com/drbothen/vsdd-factory/issues/671)'s phase-1 exit criterion is
*"reproduces known F-\* findings from recent adversarial passes without hand-tuning."*
`fa` reproduced the Python prototype's 82 findings rule-for-rule and found 71 more, but
had **never been compared to the F-\* findings** — the ones the adversary actually reported.
That comparison decides whether `fa`'s frontmatter-only parser is sufficient or whether
#671's insistence on **body prose** is where the real drift lives.

## The answer

| | share of real findings | 95% CI |
|---|---|---|
| **the registry + `fa` as designed already address** | **40.2%** | ±10.3 |
| ├─ A: derived-data staleness the registry makes *impossible* | 25.3% | ±9.1 |
| └─ B: frontmatter-reachable (today, or via a declared field/enum/link) | 14.9% | ±7.5 |
| **needs BODY-PROSE extraction — #671's claim** | **21.8%** | ±8.7 |
| **out of reach of ANY parser** | **37.9%** | ±10.2 |
| ├─ D: needs external state (source code, CI, PR, SHA) | 13.8% | ±7.2 |
| ├─ E: about how a gate was RUN, not about data | 12.6% | ±7.0 |
| └─ F: semantic judgement about meaning, not structure | 11.5% | ±6.7 |

**Three conclusions, in order of consequence:**

1. **#671 is partly right, and it matters.** 21.8% of findings require reading body prose —
   AC↔BC traces in body tables, `§`-section references, line-anchored prose claims. That is
   too large to leave out, so **the registry gains a prose-reference capability** (§4). It is
   an addition; nothing already written needs to change.
2. **But the registry's biggest design choice is worth MORE than prose extraction.** Making
   indexes and replicated counts `authority: derived` addresses **25.3%** — more than prose
   extraction's 21.8%, and it addresses them by making them *impossible* rather than by
   detecting them. That validates the derived-authority decision on independent evidence.
3. **38% is unreachable by any parser, and no amount of tooling changes that.** The adversary
   is doing work — semantic completeness judgement, spec-vs-code verification, gate-execution
   auditing — that neither `fa` nor #671's `factory-graph` can do. Any claim that a parser
   "replaces" adversarial review is false, and this is the number that says so.

Combined, **62% of what the adversary reports becomes mechanically detectable or structurally
impossible** under the registry plus prose extraction. That is the honest ceiling.

## Volume, for scale

| | |
|---|---|
| review documents in `cycles/` | **390** across 7 cycles |
| candidate finding lines extracted | 2,138 |
| after dropping closure/status rows | **1,894** |
| extractor precision (hand-measured) | **87%** — 87 of 100 sampled are real findings |
| estimated real findings corpus-wide | **~1,647** |
| findings `fa` reports today | **153** |

`fa` sees roughly **9% of the volume** — but the overlap is smaller still, because `fa`'s
153 are dominated by link/type/count classes while the adversary's are dominated by
body-prose and semantic classes. **They are largely disjoint, not redundant.** So the right
reading is not "`fa` catches 9%" but "`fa` and the adversary are looking at different things,
and roughly 40% of what the adversary looks at could be automated away."

## Method, stated in full

**Population.** Every document in `~/Dev/vsdd-factory/.factory/cycles/` whose
`document_type` is one of the 12 spellings that alias to `adversarial-review`. 390 documents.

**Extraction — and the correction it required.** A finding is any of three forms:

| form | count |
|---|---|
| `### <ID> — <statement>` heading | 1,464 |
| `\| <ID> \| <SEV> \| <location> \| <description> \|` table row | 419 |
| `**<SEV>-<NNN>: <statement>**` + following `- Key: value` bullets | 11 |

⚠ **The first version of this measurement recognised only the inline form and ran on 8
documents per cycle. It found ELEVEN findings, all from a single file, and would have
supported a confident verdict off 0.3% of the data.** That is the **fourth** instance in this
spike of a parser silently losing input, and it is why the per-form counts are printed on
every run. The rule now covers all three forms over the full population.

**Cleaning.** 244 extracted lines were closure-table status cells (`CLOSED`, `VERIFIED
FIXED`, `Subsumed by …`, `NO_ACTION`), not findings. Dropped by an explicit rule. A further
13 of the 100 sampled still turned out not to be findings on reading, which is where the 87%
precision figure comes from — measured, not assumed.

**Classification.** Keyword rules over statement + location + description classified only
33% of findings, so **the reported distribution is from a hand-classified random sample of
100** (`seed 2026`) rather than from the rules. Every one of the 100 was read and assigned;
the classification is committed in `registry/fstar_hand_sample.json` for audit. The keyword
rules remain in `registry/fstar_compare.py` and their hit counts are printed, but they are
**not** the basis of any number above — a 33% classification rate cannot support a verdict.

**Confidence.** n=87 real findings, so a proportion carries roughly ±7–10 percentage points
at 95%. The three headline shares (40 / 22 / 38) are separated by more than their intervals
where it matters — the "unreachable" and "addressed" shares are both clearly larger than the
prose share — but **A (25.3%) and C (21.8%) overlap**, so "derived-data elimination is worth
more than prose extraction" is the direction, not a proven ordering. It would take n≈400 to
separate them, and the decision does not depend on it: both are worth doing.

## What the classes look like

Verbatim, from the hand-classified sample.

**A — REGISTRY-ELIMINATES (25.3%).** Derived data that disagrees with its source.
- `3-cell trajectory-tail divergence (:44 "→7→7→7" vs :15 "→7" vs :195 ends "→7→7")` — one
  derived value replicated at three sites, and they drifted.
- `BC-7.04.051 body table row in BC-INDEX.md shows "draft | TBD | TBD"` while the record's
  `lifecycle_status` is `active`.
- `ARCH-INDEX cite "per BC-INDEX v1.25" lags actual BC-INDEX v1.26`.
- `INDEX.md "34 passes" vs STATE.md pass-count narrative inconsistency`.
- `VP-077 Property Statement lists 6 properties; VP-INDEX title enumerates 4`.

Every one of these is a *stored copy of something derivable*. Under the registry they cannot
be written, so they cannot drift. **This is the single largest class.**

**B — FRONTMATTER-REACHABLE (14.9%).**
- `Subsystem field format drift — 564 BCs use bare subsystem: SS-NN while remainder use
  quoted form` — a closed-enum + normalisation rule catches all 564.
- `VP-049 source_bc singular vs bcs:[BC-1.07.003, BC-1.07.004]` — a declared link cardinality.
- `BC-1.08.003 double-anchored across S-1.01 and S-1.02` — a link cardinality violation.
- `Pass-35 frontmatter missing observations: 0 field` — a required field.

**C — PROSE-REFERENCE (21.8%), #671's territory.**
- `POLICY 8 violation: 5 stories have AC traces to BCs not in bcs: frontmatter` — the AC
  traces are in the **body table**; the `bcs:` list is frontmatter. Comparing them requires
  reading both.
- `AC-005 BC trace mis-anchors bin/emit-event clause to BC-7.03.081 (identity) vs
  BC-7.03.082 (emit_event)`.
- `ADR-019 §Consequences "Async-task drain window" formula inlines literal 100ms (line 215)`.
- `S-1.01 ACs cite BC clauses that don't exist in the cited BCs` — a reference to a
  *sub-element* of another document's body.

Note the shape: these are **sub-artifact IDs** (`AC-NNN`, `EC-NNN`, `PC-N`, `§Section`) that
are file-scoped rather than globally unique — exactly what #671 identified.

**D — EXTERNAL-STATE (13.8%).** `BC-7.06.001:130 fabricated RegistryEntry.async: bool field`
· `WASI preopened_dir Grants Unrestricted Filesystem Access` · `VP-078 Rust unit tests still
use script = "..." form`. The spec is checked against **code**, which is outside `.factory`.

**E — PROCESS-UNREACHABLE (12.6%).** `D-448(a) codification itself used pseudocode not
literal shell` · `pass-39 Dim-2 Verification miscount: claimed 3 matches, actual 2` ·
`L-EDP1-033 sibling-corrigendum claimed but not written (D-410 rubber-stamp)`. These are
about whether a gate was *actually run*. No data model reaches them.

**F — SEMANTIC-JUDGEMENT (11.5%).** `VP-079 Scenario 4 is structurally untestable — VP design
conflicts with BC-1.14.001 PC4` · `Postcondition 1 grammar awkward` · `AC-007 newline
rendering not examined at pass-1`. Requires understanding what the spec *means*.

## Consequence for the registry: one addition

The registry does **not** need redesign. It needs a declared prose-reference capability,
which is added as `prose_refs` on the affected types:

```yaml
prose_ref_kinds:          # NEW — the sub-artifact ids #671 identified
  ac:      {pattern: 'AC-\d+',  scope: file, note: "acceptance criterion, story-scoped"}
  ec:      {pattern: 'EC-\d+',  scope: file, note: "edge case, BC-scoped"}
  pc:      {pattern: 'PC-?\d+', scope: file, note: "precondition, BC-scoped"}
  section: {pattern: '§[^,;)]+', scope: file}
```

Three rules that keep it from manufacturing false findings — all learned from measurement
already in this repo:

1. **Exclude code spans.** `ADR-099` appears as an example CLI argument inside a backtick
   span; a flat scan reports it as a dangling reference (PROBE-CYCLES §5).
2. **Resolve as-of, through `id_alias`.** `BC-1.12.008` was *legitimately renumbered* to
   `BC-3.05.004`. A flat existence check against today's corpus manufactures findings against
   correct historical documents.
3. **Scope sub-artifact ids to their file.** `AC-002` is not globally unique. Its key is
   `(owning_artifact_key, ac_id)` — the same composite-key discipline the registry already
   applies to documents.

And one that follows from D-A: because the section partition is stored and addressable, a
prose reference resolves to **`(doc_key, section_ord)`**, which means a finding can name the
section it lives in rather than the 615 KB document.

## What this changes in the plan

- **Story 12 (prose extraction) moves up**, and its scope is now known: 21.8% of findings,
  concentrated in sub-artifact ids and section references, not in free prose generally.
- **Story 7 (make indexes derived) is confirmed as the highest-value single change** — 25.3%
  of findings, eliminated rather than detected.
- **#671's exit criterion is now MET as a measurement** (it has been run) but **not as a
  pass**: `fa` today reproduces the B class only. A frontmatter-only parser was never going
  to clear that bar, and now the gap is quantified rather than argued.
- **A claim nobody should make:** that this replaces adversarial review. 37.9% of what the
  adversary finds is beyond any parser, and that number should appear in the ADR so the
  expectation is set correctly.

## Reproduce

```sh
python3 registry/fstar_compare.py        # extraction + rule-based classification + samples
cat registry/fstar_hand_sample.json      # the 100 hand-classified findings
```

Read-only. `FSTAR_RECENT=N` changes the recent-passes subset size; the headline numbers use
the full population.
