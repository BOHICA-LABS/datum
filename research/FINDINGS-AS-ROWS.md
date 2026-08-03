---
title: FINDINGS-AS-ROWS — story 4, minting adversarial-finding as rows
date: 2026-08-01
purpose: make finding_count / findings_total / severity_distribution DERIVED, by giving findings a row each
method: extract every finding from all 390 review bodies; key on (review, finding_id); compare each review's own claim against COUNT(*)
status: ROWS MINTED AND GATED. 390 reviews, 2,211 finding rows. 66 reviews disagree with their own bodies.
corpus_pin: vsdd-factory .factory @ 0aaba144
---

# Findings as rows

The `adversarial-finding` template exists in the plugin and **nothing uses it** — measured: **0
files** carry that `document_type`. Findings live as headings and tables inside review bodies,
so `finding_count`, `findings_total` and `severity_distribution` are authored numbers over
prose. Story 4 gives each finding a row, which is what lets all three become `COUNT(*)` and
`GROUP BY` — the discipline `schema.go` already applies to every other count.

```sh
datum import   --db /tmp/fadb ~/Dev/vsdd-factory/.factory
datum validate --db /tmp/fadb
```

## What it produced

| | |
|---|---|
| review documents | **390** |
| finding rows minted | **2,211** |
| duplicate MENTIONS collapsed | 183 |
| malformed candidate lines | 0 |
| rows MENTIONED but not OWNED | 412 |
| severity unresolved by any declared source | 499 of 2,211 (**23%**) |
| review claims recorded | ~199 |
| **claims that DISAGREE with the review's own body** | **68, across 66 documents** |

So roughly **two thirds of reviews that state a count agree with their own contents**, and a
third do not. That third is what story 4 eliminates: with rows there is no second number to
drift.

## The three rules, and the disagreement that produced each

Every rule came from `registry/probe_findings.py`, which ran BEFORE any Go was written. Each
was found by chasing a disagreement, never by design.

**1. SIX ID CONVENTIONS.** The corpus writes `HIGH-P34-001`, `F-SP8-001`,
`ADV-S8P1-P01-HIGH-001`, `P2-001`, plus table-row and inline-bold forms. The previous extractor
knew four of them. The two it missed:

- **`ADV-<CYCLE>-P<N>-<SEV>-NNN` — the convention the template itself declares.** Its absence
  meant `adv-s8.00-p1.md` claimed 14 findings and extracted **0**, while the document
  documents this very format in its own `## Finding ID Convention` section. Recovered 243 rows.
- **`P2-001`** — a pass-prefixed id with no severity or category word at all, severity in a
  bracket. `adv-e8-p2.md` claimed 7 and extracted 0; it defines exactly P2-001…P2-007.

Six conventions in one corpus is not a parser problem to be solved once. **It is the argument
for this story**: with rows the convention is declared once and enforced, instead of being
discovered one form at a time by a regex that fails silently in between. This is the *fifth*
silently-lost-input in this spike, so the per-form counts are printed on every import.

**2. ONE ROW PER (review, finding_id)** — the composite key the template already declares. A
review states a finding as a heading AND repeats it in a closure table, so counting mentions
gave **exactly 2×** the asserted distribution on pass-34 (2H/6M/4L against a claimed 1H/3M/2L).
**Counting mentions is not counting findings** — the same lesson as "counting files is not
counting artifacts", one level down. 183 mentions collapse.

**3. OWNERSHIP IS STRUCTURAL.** A pass-2 review has `## Part A — Fix Verification`, which
re-states PASS-1's findings to audit their fixes, and `## Part B — New Findings`, which is what
this pass introduces. `findings_total` counts Part B only; counting everything put
`adv-s8.08-p2.md` at 21 against a claimed 9. 412 rows are mentioned-not-owned.

This is the **same class as the shadow stage's scope predicate** (SHADOW-INDEXES): a derived
count needs a declared SCOPE, or it counts mentions. Two independent stories arrived at it.

Two refinements the first cut got wrong, both caught by overshooting:

- Ownership must be decided by a finding's **defining** occurrence, not its first *mention*.
  Deciding from the first mention attributed Part B findings to Part A's audit table and drove
  `adv-s8.08-p2` down to 5 against a claimed 9 — overshooting the very bug the rule exists to
  fix. Agreement went 100 → 113 when fixed.
- Defaulting ownership to *mentioned* would silently drop the findings of every review with no
  Part A/B split, which is most of them. **Default owned.**

## Severity resolves through six ordered sources, and reports which one won

Measured over 2,211 rows: `bracket-in-statement` 803 · `bold-line` 670 · `id-prefix` 129 ·
`id-embedded-ADV` 76 · `section-heading` 61 · **unresolved 499**.

The first cut resolved only an `- Severity: X` bullet and an id prefix, and reported **1,895 of
2,138 rows as having no severity** — which read as catastrophic corpus drift. It was the
parser: the reviews write `**Severity:** HIGH` in bold, and `IDPAT`'s `F`/`CV`/`SEC`/`PG`
prefixes are *categories*, not severities. `sev_source` is stored per row precisely so that
"unresolved" stays a measured fact about the corpus rather than a silent parser default.

**23% unresolved is itself the argument for rows:** with a declared closed enum, severity is a
required field instead of something recovered from six competing prose conventions.

## Two further corrections

- **The review-type vocabulary is now DERIVED from the registry's alias map.** The first cut
  hardcoded it, and it disagreed with the Python extractor's hardcoded set on **eight
  spellings in both directions** — one hand-maintained vocabulary drifting from another, which
  is the exact defect the registry exists to remove. Same shape as `depends_on`/`blocks` and as
  the two declared namespaces: the fix is always to have one source. Pinned by
  `TestReviewTypeSetIsDerivedFromTheRegistry`.
- **The probe over-counted reviews by one.** It reported 391 documents against `datum`'s 390.
  Chased rather than accepted: `fstar_compare.py` reads `document_type` from the frontmatter
  BLOCK, my probe fell through to a `re.M` search that also matched a `document_type:` line in
  a body. **390 is correct** and `datum` agrees with the correct method exactly.
- **`category` is prose, not an enum.** The template declares six values; the corpus writes
  sentences into the field. The column is `TEXT` and a non-declared value is a reported TYPE
  finding (24 today) rather than being silently coerced — the same call the importer already
  makes for `bc.replacement`. The import initially FAILED loudly on an over-long value, which
  is the correct behaviour and how this was found.

## What is NOT done

- **Reviews have no declared natural key.** The key is the corpus-relative path today, which
  D-C says must never be identity. Reviews need a declared key (cycle + pass + target is the
  obvious candidate) before this can graduate. Stated rather than papered over.
- `cycles/INDEX` can now be shadowed — its Findings column is a severity distribution over
  exactly these rows — but that is story 7 work, unblocked by this rather than done by it.
- The 66 disagreeing reviews need adjudication: some are genuine prose miscounts (the adversary
  reports this class about itself — "pass-39 Dim-2 Verification miscount: claimed 3 matches,
  actual 2"), and some are extraction gaps in a seventh id form nobody has hit yet. The gate
  names each one, which is the point.

`datum`: **106 tests** (was 97), ~6.8 s. Corpora READ-ONLY.

## Reproduce

```sh
python3 registry/probe_findings.py          # the measurement the rules came from
cd datum && CGO_ENABLED=1 go build -tags gms_pure_go -o datum .
./datum init --db /tmp/fadb && ./datum import --db /tmp/fadb ~/Dev/vsdd-factory/.factory
./datum validate --db /tmp/fadb --json /tmp/v.json
CGO_ENABLED=1 go test -tags gms_pure_go -count=1 -run 'TestExtractFindings|TestOwnership' ./...
```
