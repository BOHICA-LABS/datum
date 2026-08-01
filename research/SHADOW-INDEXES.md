---
title: SHADOW-INDEXES — story 7's shadow stage, run against the live corpus
date: 2026-08-01
purpose: generate each derived index ALONGSIDE the authored one, report every disagreement, and advance nothing without evidence
method: derive the index rows from the Dolt store; parse the authored document's tables; adjudicate cell by cell under declared normalisation rules
status: SHADOW STAGE BUILT AND RUN. 658 findings survive triage. Nothing flipped, nothing written.
corpus_pin: vsdd-factory .factory @ 0aaba144
---

# The indexes, shadowed

[FSTAR-COMPARISON](FSTAR-COMPARISON.md) measured derived-data staleness at **25.3% ±9.1** of
what the adversary reports — the largest single class, and the only one the registry addresses
by making it *impossible* rather than detectable. Story 7 is that change. This is its
**shadow** stage: generate alongside, treat every disagreement as a finding, and advance a
type only on evidence.

```sh
fa import --db /tmp/fadb ~/Dev/vsdd-factory/.factory
fa shadow --db /tmp/fadb ~/Dev/vsdd-factory/.factory
```

`fa shadow` **never writes**, to either side. That is not caution, it is the mechanism: if the
generator is subtly wrong, flipping replaces hand-maintained drift with *generated* drift and
destroys the evidence that would have caught it. Pinned by `TestShadowWritesNothing`, which
hashes the corpus before and after.

## What it found

| index | cells compared | agreed | authored rows | keyed to a record |
|---|---|---|---|---|
| `BC-INDEX.md` | 7,836 | 7,294 (**93.1%**) | 1,959 | 1,959 |
| `VP-INDEX.md` | 400 | 388 (**97.0%**) | 80 | 80 |
| `STORY-INDEX.md` | 618 | 555 (**89.8%**) | 145 | 107 |

**658 findings.** They divide three ways, and the division is the point — a single "658"
would hide that most of it is one systematic block and that 13% is not drift at all.

### Real drift: 573 findings

| n | class | what it is |
|---|---|---|
| **330** | `cell.disagree:Capability` | **the single largest block.** 330 BC-5.\* files all carry `capability: CAP-001` while BC-INDEX assigns them across **11** different capabilities (`CAP-070`…`CAP-080`). Verified by hand on BC-5.20.001: the file says `CAP-001`, the index row says `CAP-070`. One drift event explains half the total |
| 120 | `cell.index-placeholder:Stories` | the index's Stories cell says `TBD` while the store holds the anchoring story |
| 25 | `cell.disagree:Stories` | BC→story and story→BC disagree about the same anchor (`index=[S-15.01] store=[S-1.02]`) — two hand-maintained lists of one fact, the class `gateDependencyDirection` already catches for `depends_on`/`blocks` |
| 23 | `cell.disagree:Title` | genuine prose drift. VP-072's index title is about a different property than its record's; S-10.04 differs on `,` vs `and` mid-sentence |
| 21 | `cell.store-empty:Stories` | the index anchors a BC to a story that has no record — the same root as the 38 planned rows below |
| 15 | `cell.disagree:Status` | `retired` vs `draft` (BC-1.10.001/002, BC-3.05.001–003), `draft` vs `ready` (BC-2.02.011/012), `active` vs `draft` (BC-3.08.001, BC-5.39.003/004), and `merged` vs `draft` on S-15.07/08/09/17 |
| 12 | `cell.prose-in-set:Stories` | prose inside a set-valued column (`S-9.07 SDK-ext (W-16)`) — a TYPE violation, reported as one rather than as a phantom missing member |
| 8 | `cell.store-empty:Capability` | the index states a capability the store does not hold |
| 5 | `cell.disagree:BCs` | S-4.05 states 2 anchored BCs where the store holds 0; S-4.07 states 16 against 14; S-15.04/05 state `[]` against a non-empty set |
| 5 + 4 | `index-placeholder:Capability` / `:BCs` | index cells not yet filled in |
| 5 | one each: `disagree:Points`, `disagree:Type` (VP-075 `invariant` vs `postcondition`), `index-placeholder:Domain Invariant`, `index-placeholder:Priority`, `store-empty:Epic` | |

### Editorial, reported but NOT called drift: 44 findings

25 `title-elaborates` and 19 `title-abbreviates` — one title is a strict prefix of the other.
The index legitimately shortens story titles and legitimately appends version annotations to
VP titles. Collapsing these into `disagree` would have inflated real drift by 8%; treating
them as agreement would have hidden VP-072, which is a genuinely different title. Three
outcomes, not two.

### Facts about DERIVATION ITSELF: 41 findings

These are the ones worth the whole exercise, because none of them is a cell disagreement and
none would have been visible from a count.

- **`scope-excludes` (1 finding, 41 records).** The store holds 148 stories; **41 live in
  `stories/v1.0-legacy/`** and are a superseded generation that STORY-INDEX deliberately does
  not enumerate. Verified as exact set equality: the records "absent from the index" are
  *precisely* the files in that directory, 41 == 41.

  **Generating STORY-INDEX from every record would have resurrected all 41 retired stories
  while every count still agreed.** So a derived index needs a **declared scope predicate**,
  which is a property of the derived *type*, not of any cell. This is the shadow stage doing
  the exact job it exists for: a defect that a count check, an id-set check and a cell check
  would all have passed.
- **`row-without-record` (38).** STORY-INDEX enumerates 38 **planned** stories (S-8.11…29,
  S-9.01…07, S-11.01…08, S-7.04/05, S-15.06/16) under open epics, with no spec file. Under a
  derived index those rows cannot exist. Either planned stories become records or the derived
  index loses the roadmap — a scope decision that has to be made before `proven`, not after.
  Deliberately NOT classed as a dangling reference: it is not one.
- **`row-struck-through` (1).** BC-INDEX strikes out `~~BC-2.02.013~~` to mark it withdrawn
  in place. Strikethrough is not a representable state, so a derived index would silently lose
  the withdrawal.
- **`column-underivable:Status` (1).** VP-INDEX's Status column agrees with the VP *files*
  100% of the time, but the `vp` table has no `status` column — so the shadow cannot check it
  and **says so**. A differ that skipped the column silently would have overstated its own
  coverage.

## The rules, and the 2,768 false findings they prevent

Every normalisation rule here was derived from measurement, and the measurement ran FIRST
(`registry/probe_indexes.py`). This matters more than it sounds: **the first cut of this work
reported ~2,768 findings that were artefacts of its own rules, more than four times the 658
that survive.** A differ built rules-first and measured-after would have "found" them all and
been tuned down until the numbers looked clean.

| self-inflicted class | n | the rule that fixed it |
|---|---|---|
| every Title row "disagreed" | **2,145** | the record H1 repeats its own id (`Behavioral Contract BC-1.01.001: …`); the index cell carries the bare title |
| Titles truncated at their first clause | **292** | the annotation rule (`merged [superseded by ADR-015]`) is **scoped to enum columns**. Applied to Title it cut `…unknown entry fields (typo guard)` and reported its own cut as drift |
| `CAP-TBD` vs NULL | **212** | `CAP-TBD` is a typed placeholder the importer already normalises to NULL on 212 rows |
| `stories/v1.0-legacy/` | **41** | declared scope predicate (above) |
| bracketed lists with a trailing annotation | **26** | `[BC-1.12.003, …] (v1.4 — D-330)` — strip the annotation BEFORE splitting, or it glues onto the last id |
| `0` / `[]` vs an empty set | **18** | count columns are adjudicated BEFORE the emptiness rules. `0` is a claim of zero and an empty set satisfies it; the reverse order reported 18 rows as stating a value the store lacked, when both stated zero |
| multi-valued `scope` | **16** | derive VP Scope from the `vp_subsystem` EDGES. The importer already models `SS-01, SS-03` there and leaves the scalar empty — the store held it all along |
| unbracketed comma lists | **11** | `BC-7.03.081, BC-7.03.082 (PR #55)` is a list too; requiring brackets called it "neither a count nor a list" |
| escaped pipes | **5** | 5 BC-INDEX cells carry a literal `\|`; splitting on every pipe truncated them to `value_len\` |
| one strikethrough | **2** | `~~BC-2.02.013~~` keyed as a different id, so ONE markup character produced two findings that contradicted each other — an index row with no record AND a record absent from the index, for the same BC |

Two of these deserve naming as classes rather than bugs:

- **A normalisation rule aimed at the wrong column manufactures exactly what it was added to
  prevent.** The annotation rule is correct; its SCOPE was the defect.
- **Rule ORDER is a correctness property.** Emptiness-before-counting produced findings that
  asserted the opposite of the truth.

And one correction to my own measurement, caught by chasing rather than by believing a
percentage: the probe's first run reported BC `Status` at **0.8% agreement**, which looked
like catastrophic corpus drift. It was the probe reading `lifecycle_status`. BC files carry
**both** `status: draft` (1,950 files) and `lifecycle_status: active` (1,945), and BC-INDEX
tracks `status`. Real agreement is **99.4%**. The same error explained VP `Type` (the field is
`type`, not `vp_type`) and VP `Proof Method`/`Scope` (both actually 100%). Four apparent
disasters, all mine.

⚠ **A genuinely new finding that fell out of that chase, unrelated to the indexes:** BC files
carry `status` and `lifecycle_status` as two fields for one concept, and **they disagree on
1,949 of the 1,959 files that carry both**. That is D-D's territory (`status` narrowed to
lifecycle only) and it is not currently reported by any gate.

## Guards, because "0 findings" has to mean something

A differ that matched no table reports nothing and reads as a clean pass. That failure mode
has appeared four separate times in this spike, so each guard is a test rather than an
intention:

| guard | test |
|---|---|
| a declared table that matches nothing is a FINDING, not a pass | `TestShadowReportsMissingTableRatherThanPassing` |
| a bad corpus root is `fa` failing (exit 2), never a clean gate | `TestShadowRejectsBadCorpusRoot` |
| every spec resolves in the registry and sits at `derivation_stage: shadow` | `TestShadowSpecsAreDeclaredAndAtShadowStage` |
| shadow writes nothing, verified by content hash | `TestShadowWritesNothing` |
| a scope exclusion is reported, never silent | `shadow.scope-excludes` is emitted with its count and reason |
| an underivable column is reported, never skipped | `shadow.column-underivable` |

`fa`: **97 tests** (was 62), ~6.4 s, no network, no `dolt` binary.

## What has to happen before any type reaches `proven`

Not yet earned, and the shadow diffs say why:

1. **Decide the 330-row Capability question.** 330 files claiming one capability while the
   index distributes them across 11 is one edit on one side; which side is authoritative is a
   PO call, not a tool call.
2. **Declare the scope predicate in the registry**, not in Go. It currently lives in
   `shadowSpecs`; it belongs next to `derivation_stage` as part of the derived type's
   declaration, or the next generator will omit it.
3. **Settle the 38 planned rows.** Derived indexes cannot enumerate non-records.
4. **Give the store what it lacks**: `vp.status`, and a representation for a withdrawn-in-place
   row.
5. **Story 4 first for `cycles/INDEX`.** Its Findings column is a severity distribution over
   prose tables, so it cannot be derived until `adversarial-finding` exists as rows.

Only then is `proven` (they agree, `fa render` writes it, the authored one is still diffed)
an evidence-based step rather than a flip.

## Reproduce

```sh
cd fa && CGO_ENABLED=1 go build -tags gms_pure_go -o fa .
./fa init   --db /tmp/fadb
./fa import --db /tmp/fadb ~/Dev/vsdd-factory/.factory
./fa shadow --db /tmp/fadb ~/Dev/vsdd-factory/.factory --json /tmp/shadow.json
CGO_ENABLED=1 go test -tags gms_pure_go -count=1 -run 'TestShadow|TestCompareCell|TestParseMD' ./...

python3 registry/probe_indexes.py            # the per-column measurement the rules came from
```

Read-only throughout. `~/Dev/vsdd-factory` was not modified.
