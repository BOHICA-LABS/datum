---
title: PROSE-REFS-OR-FIELDS — should story 12 extract prose references, or should the referents become rows?
date: 2026-08-01
purpose: measure the ALTERNATIVE to story 12 before building it, and validate the answer against every error found in the measurement itself
method: census every id-shaped token in 2,768 markdown bodies; classify by WHAT THE REFERENT IS; then attack the conclusion with an adversarial bound and close it by sampling
status: ANSWERED, then CORRECTED. Over corpus mass 93.6% of references should be rows; over the ADVERSARY'S FINDINGS 12a and 12b are EQUAL (37%/37%) and 26% is beyond both. Story 12 splits; the two halves are equal priority.
corpus_pin: vsdd-factory .factory @ 0aaba144
---

# Prose references, or fields?

Story 12 (prose-reference extraction) is worth 21.8% ±9 of the adversary's findings and its own
declared rules warn that getting them wrong "manufactures false findings". Before building it,
the standing rule in this repo applies: **measure the alternatives to a lever before pulling
it.** That rule has already deleted planned work once (sampled+parallel Brandes, killed by free
`degree`). The alternative here is to promote the *referents* to rows and fields, making the
reference a typed link instead of something to extract forever.

## The answer

| | share | |
|---|---|---|
| **referent should be a ROW or FIELD** | **93.6%** (81,120) | has a declared owner type and a declared home |
| inherently PROSE | **6.4%** (5,556) | `§section` refs (3,944) + version cites (1,612) |

And two thirds of the row-shaped mass **is already someone else's story**:

| n | kind | where it belongs |
|---|---|---|
| 14,010 | `finding` | **already rows — story 4 shipped it** |
| 20,788 + 5,844 | `decision`, `lesson` | story 6: ledgers → append-only rows |
| 3,066 | `policy` | already a config file |
| 4,594 + 5,856 + 2,479 + 1,733 | `ac`, `ec`, `pc`, `t_task` | **the real gap: no row type exists** |

**The number that settles it:** 18.4% of candidates are `unresolvable` — the prose never says
*whose* `AC-005` it is — and a further 7.5% have no definition anywhere. **A permanent prose
extractor is structurally unable to adjudicate ~26% of what it finds.** Rows keyed
`(owner, id)` make that ambiguity *impossible* rather than *detected* — the same argument that
made story 7 the highest-value change.

## The recommendation: SPLIT story 12

- **12a — mint `AC` / `EC` / `PC` / `T-task` as rows** (14,662 references, the only gap with no
  owning story). `AC` rows carry a typed `bc` link, which turns *"5 stories have AC traces to
  BCs not in `bcs:` frontmatter"* — an actual class-C finding — from a prose diff into a
  **join**.
- **12b — a minimal permanent extractor** for `§section` refs (D-A already stores the ordinal
  section partition, so a ref resolves to `(doc_key, section_ord)`) and version cites (which is
  what `pin_policy` exists for).
- Extraction survives as the **one-time migration instrument** — you cannot mint rows without
  reading the prose once — but not as the permanent gate.

This also removes the ~100k-section-node driver from the critical path: 12b is far smaller than
full prose extraction.

⚠ **The PRIORITY implied by this section is corrected below.** Measured over corpus mass, 12b
looks like a 6.4% tail. Measured over the adversary's findings — the denominator the 21.8%
value claim actually uses — 12a and 12b are **equal**. Read the closed-gap section before
sequencing the work.

## Three defects IN THE DECLARED STANDARD, found by measuring it

These block any story-12 work, because the declared `prose_ref_kinds` are what it would build on.

| defect | measured consequence |
|---|---|
| **the patterns are UNANCHORED** | `'D-\d+'` matches `D-074` inside `TD-074` and `D-069` inside `TD-VSDD-069`. Over-match **9,755** candidates: `t_task` was **73% noise** (6,565 → 1,733), `decision` 3,708, `lesson` 1,556 |
| **the kind list is INCOMPLETE** | ~**22,750** genuine reference forms match none of the 10 declared kinds — `F-7` (the `finding` pattern requires two segments), `BC-AUDIT-NNN`, `TD-VSDD-NNN`, `META-LEVEL-NN`, `BC-7.03` (partial BC id), `D-1.2`. **1,585 distinct forms, top 20 covering only 55%** — the same head-and-long-tail shape as the 181 non-canonical `document_type` values |
| **`version_cite` sees 2.4% of its own subject** | the declared pattern requires a `per\|see\|against` preposition: **39** matches, against **1,612** for the plain `NAME vX.Y` form. A 41× undercount of exactly the thing `pin_policy` was declared for |

The second one is the sixth instance in this spike of a parser silently losing input — and this
time it is in the standard, not in a probe.

## Validating the conclusion against its own measurement errors

The first cut of this analysis was wrong three times. The conclusion is reported with the
robustness check rather than the first number, because a recommendation that only holds under
one reading of the data is not a recommendation.

| denominator | rows | prose |
|---|---|---|
| original, unanchored patterns, declared kinds only | 94.5% | 5.5% |
| anchored, declared kinds only | 93.6% | 6.4% |
| anchored + loose version cites + undeclared forms | 94.4% | 5.6% |
| **adversarial bound: assume ALL 34,900 undeclared forms are prose** | **59.1%** | **40.9%** |

Only the adversarial bound flips the recommendation, and it hinges entirely on the 45% of
undeclared mass that the top-20 list does not cover. **So that tail was sampled rather than
assumed away** — a deterministic stride sample (every 25th of 1,565 tail forms, no RNG so it
reproduces), hand-read:

- **~20 of 26 are NOT REFERENCES AT ALL.** `A-timing`, `PASS-WITH-NITS`, `WASM-only`,
  `CI-only`, `SELF-VIOLATED`, `SPEC-wins`, `WONT-FIX`, `DD-API-KEY`, `DE-ID` — hyphenated
  English that a generic `[A-Z]+-…` census sweeps up. My census over-counted by ~12,150.
- **~6 of 26 are genuine**, and every one is a finding or decision variant (`NIT-N`,
  `CRIT-W15-3`, `CC-W15-2`, `F-P44`, `D-9-A`, `D-1.2.d`) — i.e. **row-shaped**.

So the adversarial bound is refuted by sampling, not by argument. ⚠ **That correction moves the
number in favour of the conclusion I had already reached, which is exactly when to be most
skeptical**: it rests on 26 of 1,585 tail forms, hand-classified, and a different sample would
move the ~22,750 genuine-undeclared estimate. It would not move the direction — the row-shaped
share is above 93% under all three non-adversarial readings and the referents' owner types are
*declared*, not inferred.

## ⭐ THE DENOMINATOR GAP, CLOSED — and it overturns the PRIORITY above

Everything above is measured over **id candidates in the corpus**. Story 12's value claim is
**21.8% of the adversary's findings**. Different denominators, so the 93.6/6.4 split cannot be
read as a value split — and when the right denominator is measured, it is not.

All **19** class-C findings in `registry/fstar_hand_sample.json` were hand-read and classified
by which instrument would catch them (`registry/class_c_decomposition.json`, one recorded
reason per finding):

| instrument | share of class C | 95% CI | share of ALL adversary findings |
|---|---|---|---|
| **12a** — referent as rows + typed links | **36.8%** (7/19) | ±22 pts | **8.0%** |
| **12b** — body-prose extraction | **36.8%** (7/19) | ±22 pts | **8.0%** |
| **neither** — semantic even with rows | **26.3%** (5/19) | ±20 pts | **5.7%** |

| | rows-shaped | prose |
|---|---|---|
| over ID CANDIDATES in the corpus | 93.6% | 6.4% |
| **over the ADVERSARY'S FINDINGS** | **37%** | **37%** |

**So 12b is not a 6.4% residual. It is half of class C, equal to 12a within any reading of the
interval.** My earlier framing — 12a large, 12b small — was wrong, and it was wrong for a
reason worth naming: **I inferred a value split from a mass split.** Thousands of `D-\d+`
mentions collapse into a handful of findings, while a single inlined `100ms` literal is one
finding on its own. Corpus mass and finding value are different measurements, and the mass one
barely informs priority. This is the same shape as the registry's own headline result —
*enforcement gap by mass, design gap by vocabulary*: 91% of files canonical but only 22 of 71
distinct values.

**Revised recommendation: 12a and 12b are EQUAL priority.** The split is still right — they
need different machinery, and 12a eliminates where 12b detects — but 12b may not be deferred as
a small tail.

### A correction this forces on FSTAR-COMPARISON's headline

That document states *"Combined, 62% of what the adversary reports becomes mechanically
detectable or structurally impossible under the registry plus prose extraction"*, treating class
C as fully addressable by prose extraction. **26% of class C is reachable by neither instrument**
— `BC-7.05.001 vs BC-7.05.003 exit-code inconsistency`, `AC-005` anchored to the wrong BC (the
link resolves; it is simply the wrong one), `D-413(b) misframing`. So the honest ceiling is
**40.2% + 16.1% = 56.3%**, not 62%, and the unreachable share is **43.6%**, not 37.9%.

## What this still does NOT establish

- **n=19.** A 7/19 share carries ±22 points, so **the ordering between 12a and 12b is not
  established** — only that both are substantial and neither is a residual. Separating them
  would need a larger hand-classified sample.
- The classification is one reader's judgement on 19 items, recorded reason-by-reason in
  `class_c_decomposition.json` so it can be disputed per finding rather than in aggregate.
- **The unclassified tail is real**, quantified above rather than hidden.
- Nothing here says extraction is unnecessary. It says extraction is the **migration**
  instrument, not the permanent gate, for 93.6% of the mass.

## Reproduce

```sh
python3 registry/probe_prose_refs.py    # census, per-rule cost, undeclared forms, tail sample
```

Read-only. `~/Dev/vsdd-factory` was not modified.


---

## Follow-up 2026-08-01: sampling the 329 dangling section refs

12b reported dangling section references in AGGREGATE only, because owner attribution was
unmeasured. Sampling it (deterministic stride, hand-read) was the gating item, and it found that
**the corpus addresses a section THREE different ways** — each discovered as a class of
"dangling" that was the RESOLVER's defect, not the document's:

| scheme | example | resolves via |
|---|---|---|
| heading NAME | `§Consequences` | exact, or the captured name as a PREFIX of the real heading |
| section ORDINAL | `§7`, `§1-§12` | D-A's partition is ordinal-keyed — this is the store's own key |
| ITEM within a section | `§Postcondition 5` | `BC-1.05.036` has `## Postconditions`; item 5 is an ordered-list entry inside it, i.e. FINER than the partition. The SECTION resolves |

Effect of the three passes: **resolved 854 → 1,408 (+65%)**, dangling **329 → 214 (−35%)**,
unresolvable 2,387 → 1,915.

⚠ **A PREDICTION OF MINE FAILED HERE, and checking it is what found the third scheme.** From the
first sample I judged that prefix-of-heading matching would recover ~160 of the remaining 250.
It recovered **46**. Rather than tune further, I read one failing case — `§Postcondition 5` in a
review of `BC-1.05.036` — and found the item-within-section scheme. Tuning would have buried it.

**Per-reference reporting is still NOT earned.** 214 remain dangling and their post-fix precision
is unmeasured; the whole point of the aggregate is that a confident wrong finding set is worse
than a count. What changed is that the residual is now much smaller and three known-good
resolution schemes are pinned by `TestSectionRefsHaveTHREEAddressingSchemes`.

`fa refs --kind section --status dangling` lists them, because sampling requires listing and
re-deriving them in a script would have created a second source of truth for the extraction —
the defect this repo has now fixed three times.

---

## Follow-up 2026-08-02: sampling the 214 — the residual was 86% the CHECKER's

The gating item was to sample the 214 and earn per-reference reporting. Sampling it found **six
resolver defects and a fourth addressing scheme**, and the honest verdict is still *not yet* — but
for a measured reason, at a tenth of the volume.

| | before | after |
|---|---|---|
| resolved | 1,408 | **2,035** (+45%) |
| dangling | 214 | **30** (−86%) |
| unresolvable | 1,915 | 1,550 |
| total extracted | 3,537 | **3,615** |

Every other gate is byte-identical across the change: `validate` 776, `validate --registry` 7,487,
`shadow` 658, `validate_registry.py` 18,826, 16 waves, 0 cycles.

### The measurement that had to come first: the reported line is BODY-relative

**208 of the 214 reported line numbers do not point at the reference.** `prose_ref.src_line` is
computed over the body (`ExtractProseRefs(…, d.body, …)`, `Line: i+1`), which is correct under D-A
— prose *is* the body — but `fa refs` prints the column as `line`, and a reader lands in the wrong
place. The offset is exactly the frontmatter length, deterministic and recoverable: the hypothesis
`actual == reported + frontmatter_lines` held on **210 of 210** findable cases, 0 disagreements.
Per-reference reporting is impossible until a reference can be opened, so this is a prerequisite
rather than a detail. **Still open** — the column should be named `body_line`, or the offset added.

### Six resolver defects, each measured before it was fixed

| # | defect | measured |
|---|---|---|
| 1 | **owner taken from the whole LINE, not from before the `§`** | 93 of 214 (43%) stated a *different* owner in the prose. `Sweep across … PRD §FR-043, capabilities §CAP-016, … ARCH-INDEX` gave EVERY reference on that line the owner `ARCH-INDEX` |
| 2 | **reaching further back is worse than giving up** | when the token before the `§` is not a document, the old scan kept walking left and found `per ADR-015:` — a *reason*, not a referent. 7 of 30 |
| 3 | **`sectionsByDoc` keyed by basename only** | no file is *named* `ADR-019`; it is `ADR-019-plugin-async-…md`. 14 references resolved the owner correctly and then missed the lookup. 2,258 of 2,883 documents carry an id prefix |
| 4 | **the `{2,60}` floor counted units that excluded `.`** | `§B.1` produced a ONE-unit capture, failed the floor, and was never extracted. **81 references were entirely invisible** — not misclassified, absent |
| 5 | **punctuation the sentence attaches to the name** | `§Description:` matches no heading and `HasPrefix("description","description:")` is false. 15 of 26, the largest single cause. Leading quotes (`§"Audit Risk Items Carried Forward"`) were 10 of 11 more |
| 6 | **an AMBIGUOUS name was reported as DANGLING** | `PRD §FR-043` asserted PRD has no such section while `#### FR-043` is a heading **four times**, one per subsystem slice. Undecidable is `unresolvable`; dangling claims absence. 73 references |

Defect 4 is the **seventh** instance in this spike of a parser silently losing input, and defect 6
inverts the meaning of a status — the same class as "a rule aimed at the wrong column manufactures
what it was added to prevent".

### ⭐ THE FOURTH ADDRESSING SCHEME: an item is named, and items are not headings

`capabilities.md §CAP-009` is not a heading reference. **capabilities.md has five headings**
(`# Capabilities`, three priority bands, `## CHANGELOG`); every capability is a bold list item
`**CAP-009 — Author and publish WASM hook plugins using the Rust SDK**`. So the citation addresses
a granularity finer than D-A's partition — exactly like `§Postcondition 5` — but identified by an
**id**, which `itemInSectionRe` cannot match because it requires `Noun<space>N`.

Measured over 592 dangling at that moment: **134** named an id sitting in exactly one section,
**119** named an id that *is* a heading (blocked only by the two-word prefix floor), **86** named
an id present in several sections, and **3** named an id the owner does not contain at all.

Generalising it to the corpus's real convention — **a bold run opening a line defines an item** —
took the remainder: `ADR-020`'s `### Budget class taxonomy` defines `**Class A — Cold-start
dispatch (per-invocation binary spawn)**`, and 16 references to `ADR-020 §Class A` were dangling
against it. Generic labels (`**Severity:**`, `**Location:**`) recur across many sections, so the
ambiguity rule drops them without a stop-list to maintain.

So the schemes are now **five**: heading NAME · section ORDINAL · `Noun N` item · **artifact-id
item** · **bold-label item**. All five are pinned by tests.

### A PREDICTION FAILED AGAIN, and reading the case was again what paid

I predicted ~70 of the 93 mis-attributed references would resolve once the owner was read from the
right place. **17 did.** Rather than tune, one case was read — `PRD §FR-043`, where PRD.md plainly
carries `#### FR-043 …` headings — and it exposed defect 3 *and* the fact that `ownerNameRe`, a
hardcoded list of id shapes, cannot name `PRD` or `capabilities.md` at all. That is the **fifth**
time a hand-maintained vocabulary has been the defect here, so the owner vocabulary is now read
from the documents the store holds.

### A false positive I introduced, and how the registry killed it

Accepting *any* markdown basename as an owner attributed `Pass-5 §Cure-Extension Parsimony Note` —
adversary pass 5 of an S-15.17 review — to `cycles/…/adversarial-reviews/pass-5.md`, an unrelated
document in another cycle. 55 references took that shape. **The registry already knew**:
`adversarial-review` is keyed `[cycle, scope, target, pass]`, so `pass-5` is not a name, while
`prd` is keyed `[project]` and `domain-spec-section` by `[section]` — whose own note reads
"`section` is the key, not the filename". Name-addressability is now derived from that declaration.

A second self-inflicted one: in `Sweep these sections: §Description, §Postconditions, §Invariants,
§Edge Cases`, the token before each marker is the *previous section's name* — and `invariants.md`
exists, so `§Edge Cases` acquired a confidently wrong owner rather than none.

### Verdict: per-reference reporting is STILL NOT EARNED — at 37%

All 30 survivors were hand-read and adjudicated individually: **11 REAL, 19 the checker's.** The
11 are genuine corpus defects, the clearest being three BCs citing `ADR-015 §Negative consequences`
when that ADR's heading is `### Negative / Trade-offs`; also `BC-5.39.009 §Architecture Compliance
Rules`, `ADR-018 §Implementation Plan`, `ADR-019`/`S-15.01 §Implementation Modules`,
`ARCH-INDEX.md §Verification Architecture`, `BC-3.08.001 §event-type-4`.

**37% precision does not earn per-reference reporting**, and the number is reported rather than the
batch: a hand-adjudicated set of 30 is not a mechanical property the next import reproduces. It is
nonetheless a real change from the same method's earlier reading — a 30-row stride sample of the
214 found **26 of 30 to be the checker's and 0 confirmed real**.

The mirror-image error was checked too, because a fix that only shrinks the dangling set can be
buying it with false *resolutions*: 15 of the 686 newly-resolved were hand-read and all 15 are
sound (own-section refs, `§Decision 4` → `## Decision` per scheme 3, `capabilities.md §CAP-024` →
its band). No false resolutions found.

The 19 remaining decompose into named causes, so the next pass has a work-list rather than a count:
**abbreviated** names (`§EC` for Edge Cases, `§Purity` for Purity Classification) · **compound**
addresses (`§E-REG-003 §Postconditions` — two markers, one referent) · **placeholders** (`§FR-NNN`
is a template slot) · **not a reference at all** (`§FR Rows vs Stories FR Traces` is a finding
title) · **spacing** (`§Source/Origin` vs the heading `Source / Origin`) · bold items inside
**code fences**, which are correctly not indexed.

### Reproduce

```sh
./fa/fa refs --db /tmp/fadb --kind section --status dangling    # 30
./fa/fa refs --db /tmp/fadb --kind section --status resolved    # 2035
```
