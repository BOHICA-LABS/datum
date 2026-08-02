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
