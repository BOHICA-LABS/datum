---
title: PROBE — `cycles/`, the worst-case artifact class
date: 2026-07-31
purpose: decide how the hardest 621 files would be stored, BEFORE designing around the easy 1,961
status: probe complete; GAP-MATRIX §2.7 partially OVERTURNED on evidence
corpus: vsdd-factory .factory @0aaba144 (factory-artifacts tip), read-only
---

# Probe: `cycles/`

## Why this class first

The vision changed on 2026-07-31: `fa` should be the source of truth for **everything**
that goes into `factory-artifacts`, prose included. That reverses
[SPEC §6](SPEC.md) non-goal 1 and the 12 prose non-goals in
[GAP-MATRIX §2.7](GAP-MATRIX.md), whose stated rationale was:

> ⊘ Stay as files. **No keys, no counts, nothing to derive.** Relationalizing them buys
> nothing and costs diff legibility.

`cycles/` is the largest and least structured of those classes — 621 files, 15.8 MB, the
second-biggest directory in the corpus after `specs/behavioral-contracts`. If the
whole-corpus vision survives `cycles/` it survives everything; if it fails, better to
learn that here than after modelling the easy 1,961 BCs. So this class was probed first,
against five decisions: **shape · authority · unit of change · retrieval · render
obligation**, sorted by the question that does the real work — *what breaks if two agents
change it concurrently and it merges badly?*

---

## 1. The rationale for the non-goal is false

**481 of 611 markdown files carry frontmatter**, and the keys are exactly what a gate
would want:

| key | files | key | files |
|---|---|---|---|
| `document_type` | 440 | `traces_to` | 267 |
| `verdict` | 399 | `version` | 266 |
| `producer` | 390 | `cycle` | 249 |
| `pass` | 388 | `previous_review` | 244 |
| `timestamp` | 370 | **`finding_count`** | **123** |
| `phase` | 323 | `inputs` | 291 |

So the class has **keys** (`pass`, `cycle`, `document_type`), **links**
(`previous_review`, `traces_to`, `inputs`), and **counts** (`finding_count`) — the three
things the non-goal said it lacked. `finding_count` is a hand-maintained count of data in
the same file, which is the exact shape of defect design rule 1 exists to eliminate.

### Two new drift classes, visible immediately

**One concept under six `document_type` spellings** (390 of 440 typed files):

```
247  adversarial-review          15  adversary-pass
 69  adversary-review             6  local-adversary-review
 47  adversarial-review-pass      6  per-story-adversary-review
```

An ENUM or an FK to a type registry makes that unrepresentable. Today nothing checks it,
and any query over "all adversary reviews" must know all six spellings or silently
under-count.

**`verdict` holds two incompatible vocabularies in one field** — severities
(`HIGH` 87, `MEDIUM` 12, `LOW` 11, `CRITICAL` 10, `NITPICK` 11, `NITPICK_ONLY` 88) mixed
with pass states (`SUBSTANTIVE` 63, `FINDINGS_REMAIN` 43, `CONVERGENCE_REACHED` 15,
`CLOCK_RESET` 15). That is a type violation of the kind `fa validate` already reports for
`VP.scope`.

---

## 2. Shape: the class is not one thing, it is three

Measured from git history over the whole `factory-artifacts` branch — **per-file commit
counts**, which is the direct measurement of "is this edited or written once":

| commits touching the file | files |
|---|---|
| **1** | **568** |
| 2 | 21 |
| 3–5 | 9 |
| 12–133 | ~11 |

**94% of the class is write-once.** And the churn is not spread thinly — it is
concentrated in **four file KINDS, repeated once per cycle**:

```
133  v1.0-feature-engine-discipline-pass-1/burst-log.md
106  v1.0-brownfield-backfill/lessons.md
105  v1.0-brownfield-backfill/burst-log.md
 98  v1.0-feature-engine-discipline-pass-1/INDEX.md
 97  v1.0-feature-engine-discipline-pass-1/decision-log.md
 85  v1.0-feature-engine-discipline-pass-1/lessons.md
 63  v1.0-feature-plugin-async-semantics-pass-1/burst-log.md
 60  v1.0-brownfield-backfill/decision-log.md
 42  v1.0-brownfield-backfill/INDEX.md
```

Inspecting those four kinds settles their shape:

| kind | size | internal structure | shape |
|---|---|---|---|
| `decision-log.md` | 241 KB | 157 `\| D-NNN \|` table rows | **append-only rows** |
| `burst-log.md` | 373 KB | 144 `## D-NNN` sections | **append-only rows** |
| `lessons.md` | 306 KB | `## LESSON-YYYY-…` sections | **append-only rows** |
| `INDEX.md` | 30 KB | a listing of the cycle's own documents | **DERIVED — never stored** |

So `cycles/` decomposes cleanly:

| Shape | N | Merge risk |
|---|---|---|
| **Immutable documents** — review passes, written once, never touched again | ~568 | **none.** An immutable row cannot conflict |
| **Append-only ledgers** — burst/decision/lessons logs | ~9 files, 600+ commits of appends | **none IF decomposed into rows** (invariant 3); **severe if stored as one blob per file** |
| **Derived index** | ~3 | **none.** Generated, never stored (design rules 1 and 5) |

This is the probe's central result. **The worst-case class turns out to be the easiest
class to model correctly** — and the high-churn files, the only ones where a
blob-per-file model fails, are precisely the ones a row model fixes. Two agents appending
to `burst-log.md` collide on one cell; two agents inserting `D-533` and `D-534` do not.
That retires ~600 commits' worth of hand-appended ledger churn.

---

## 3. Unit of change and keys: the real constraint

**Basenames are not unique, and the collisions are not copies.** 18 basenames appear at
more than one path, and **all 18 hold different content**:

```
adversary-pass-1.md   x7   S-12.03 … S-12.08 (per story) + one cycle-level (6.5–21 KB each)
INDEX.md              x2   two cycles, 30 KB vs 18 KB
F1-delta-analysis.md  x2   two cycles, 29 KB vs 28 KB
```

So the key is composite — **(cycle, scope, kind, pass)** — never the filename. This
confirms at *document* level the hazard [#671](https://github.com/drbothen/vsdd-factory/issues/671)
flagged at sub-artifact level ("file-scoped, not globally unique → composite keys
required").

It also weakens one of this probe's own results: the `previous_review` check below
resolves *a* file of that name, not necessarily *the* intended one.

**Prose bodies are one cell unless deliberately split.** For the ~568 immutable documents
that is harmless. For anything editable it is the one-way door: cell-level merge
reconciles different *fields*, never different *regions of one field*. beads' answer was
four typed prose slots (`description` / `design` / `acceptance_criteria` / `notes`) rather
than one body — see [BEADS-PROSE.md](BEADS-PROSE.md).

---

## 4. Retrieval: full-text works, and it is SQL

Measured on the live store (1,959 BC bodies, `fa`'s open zone):

```sql
ALTER TABLE bc ADD FULLTEXT INDEX ft_bc_body (body);          -- accepted
SELECT bc_id, MATCH(body) AGAINST('drain window') score ...   -- 0.15 s, ranked
```

Dolt supports `FULLTEXT` + `MATCH … AGAINST` with relevance scoring. So the one retrieval
mode the prose vision adds — "which review discussed X" — needs **no new query language**.

⚠ One quirk, observed and not diagnosed: the same query returned **24 rows for 22 distinct
ids**. Callers must `SELECT DISTINCT`. Logged as an anomaly, not explained.

---

## 5. Prose-embedded references: high volume, LOW precision

The 611 cycle documents contain **12,526 id mentions in prose**. Checked against the
universes on disk:

| type | distinct ids cited | do not exist |
|---|---|---|
| BC | 362 | **23** |
| VP | 80 | 0 |
| ADR | 24 | **1** |

That looks like 24 new dangling references. **It is not**, and this is the most important
warning in the probe — inspecting them found at least two distinct false-positive classes:

1. **Legitimate history.** `BC-1.12.008` does not exist *today* because
   `ARCH-INDEX.md:322` records *"Renumbering history — BC-1.12.008 → BC-3.05.004
   (D-311/D-312)"*. A 2026-05 review document citing it was **correct when written**. A
   flat existence check calls a historically accurate document broken.
2. **Id-shaped tokens that are not references.** `ADR-099` appears inside a code span as
   an *example CLI argument*: `` `--id ADR-099` ``. It is illustrative, not a citation.

A residue does look genuinely phantom — `BC-10.13.001/.005/.011/.012`, a cluster in a
subsystem that only ever contained `BC-10.01.*`, resembling the `S-8.09` case where 19
declared blocked stories were never written. Each needs adjudication; none can be
asserted from the regex alone.

**Consequences for the "extract prose references" work (open gap 2, and #671's core
claim):** it needs (a) code-span and example exclusion, (b) **as-of resolution** — a
historical document must be validated against the corpus *as it was*, which is exactly
what `AS OF` gives and a flat parser cannot, or an explicit renumbering-alias edge as
#671 proposed, and (c) per-id human adjudication for the residue. Naive extraction would
generate confident false findings — the failure mode this project exists to eliminate.

---

## 6. What this probe did NOT establish

Recorded because a probe that only reports what it found is half a result.

- **`finding_count` drift is NOT demonstrated.** The hypothesis was that these documents
  restate their finding counts in frontmatter, in prose, and in the body headings — the
  BC-INDEX four-way pattern, 400× over. Of the 6 documents where a conservative parser
  could compare both sides, **all 6 agree** once absent zero-valued severities are
  handled (my first comparison reported 5 mismatches; all 5 were artefacts of comparing
  a dict against a Counter that omits zeros — caught before publishing).
- **The 108 `finding_count: <scalar>` documents are not comparable by pattern-matching.**
  Findings are **section-scoped**: in `s-15.08-local-adversary-pass-2.md`,
  `finding_count: 0` is *correct* — the `### O-001 [LOW]` headings sit under *"Part B —
  Observations (non-finding, below NITPICK)"* and the `### F-001` headings under *"Part D
  — Closure Verification"*. An identically-shaped heading means something different
  depending on the section it is under. Counting findings requires parsing document
  **structure**, not headings. Priced accordingly.
- **`previous_review` integrity is soft.** 229 documents declare it; 228 resolve by
  basename and **1 does not**: `wave-11-ss-03-pass-14.md → wave-11-ss-03-pass-13.md`,
  which exists nowhere in the corpus **and never appears in the branch's git history**.
  That one is real. But because basenames are ambiguous (§3), "resolves" means *a* file
  matched, so the other 228 are not proof of a valid chain.

---

## 7. Verdict

**`cycles/` is not the blocker the non-goal assumed.** It is 94% immutable documents with
real keys, plus nine append-only ledgers that a row model strictly improves, plus a
derived index that should never have been stored. Ingesting it adds gates that do not
exist today (`document_type` vocabulary, `verdict` vocabulary, pass-chain integrity) and
removes ~600 commits of ledger churn.

**GAP-MATRIX §2.7's rationale is overturned on evidence** for at least
`cycle-document`, `cycle-decision-log`, `adversarial-review` and
`per-story-adversary-pass`. Its *conclusion* may still hold for classes with genuinely no
keys — but it can no longer rest on "no keys, no counts, nothing to derive", because for
this class that is measurably false.

**The real blockers are elsewhere, and they are the same three everywhere:**

1. **Composite keys.** Filenames collide, with different content, at document level.
2. **As-of resolution for historical prose.** Validating yesterday's document against
   today's corpus manufactures false findings. This is an argument *for* the versioned
   store, not against it.
3. **Section-scoped semantics.** These documents have an internal schema (Part A/B/C/D)
   and a pattern-matcher that ignores it will miscount. Demonstrated on myself.

**Cost to ingest this class:** 15.8 MB of prose, mean 26 KB per document, largest 615 KB
(`burst-log.md`). Growth is the open question — and note beads' mitigation is
**unavailable to us**: it decays closed issues by ~70% via agent summarisation and
discards the original, which an authoritative spec corpus forbids.

**Next probe, by file mass:** `specs/behavioral-contracts` (1,961) is already modelled;
`stories/` (170) and `code-delivery/` (148) are next, and `logs/` (34 `.jsonl`) is the
only class with a genuinely different shape (high-volume append-only events).
