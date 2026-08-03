---
title: FA-V1-PIVOT-MEASUREMENT — the field-per-row pivot cost, measured, with a derived materialization trigger
date: 2026-08-02
purpose: close the L1-L2 design's ONE unmeasured assumption (its §9 Q9) with numbers, and derive the materialization fallback's missing trigger from them
status: MEASURED — L2-A confirmed; the fallback is NOT needed by any type in any of the three corpora today
repro: fa/pivot_probe_test.go (TestPivotCost · TestPivotStorage · TestWideRowCeiling) + registry/probe_field_mass.py
---

# The field-per-row pivot, measured

The spine calls this **"the one genuinely unmeasured risk in the whole design"**, and L1–L2 §9 Q9
says *"the fallback is specified; the trigger is not."* A design resting on an unmeasured number is
what this repo's own rule forbids, so this measures it.

**Verdict up front: L2-A survives. The pivot is free on the op shape that dominates, expensive only
on full-type scans, and no type in any of the three corpora is within 3.9× of needing the
materialization fallback. Two of the design's own claims were wrong — one by an order of magnitude in
its favour, one pointed in the wrong direction entirely.**

## How to re-run every number here

```sh
cd fa
CGO_ENABLED=1 go test -tags gms_pure_go -run TestWideRowCeiling -v .           # no corpus needed
FA_PIVOT_CORPUS=~/Dev/vsdd-factory/.factory \
  CGO_ENABLED=1 go test -tags gms_pure_go -run 'TestPivotCost|TestPivotStorage' -v -timeout 30m .
cd .. && python3 registry/probe_field_mass.py
```

---

## 1. Field mass — the pivot's denominator, and the design was off by 10×

`registry/probe_field_mass.py`, over all three corpora, read-only:

| corpus | files | w/ frontmatter | no frontmatter | scalar keys | list keys | list items | **field rows** |
|---|---|---|---|---|---|---|---|
| vsdd-factory | 3,085 | 2,768 | 317 | 57,418 | 2,377 | 8,869 | **68,866** |
| prism | 2,785 | 2,048 | 737 | 34,585 | 2,151 | 10,184 | **46,644** |
| rivetry | 668 | 590 | 78 | 10,061 | 568 | 7,918 | **18,164** |
| **total** | **6,538** | **5,406** | **1,132** | **102,064** | **5,096** | **26,971** | **133,674** |

**Rows-per-artifact — the pivot's fan-in:** min 0 · **p50 24** · p90 36 · p99 70 · p99.9 101 ·
**max 127** · mean **20.4**.

⚠ **CORRECTION to L1–L2.** The design states field mass is *"order 10⁵ rows per corpus."* Measured,
the largest corpus is **68,866 = order 10⁴**. Since one store per project is ratified, per-corpus is
the number that governs, so the design **overstated the mass by an order of magnitude** — in the
direction that makes the pivot cheaper than assumed. The 1.3×10⁵ figure is only reached by summing
all three corpora, which no store ever does.

**Largest single type in any corpus** (this is what a per-type generated view actually scans):

| corpus | largest type | artifacts | **field rows** |
|---|---|---|---|
| vsdd-factory | `behavioral-contract` | 1,959 | **49,121** |
| prism | `story` | 264 | 12,710 |
| rivetry | `behavioral-contract` | 134 | 7,605 |

### ⚠ 18 values exceed the design's `v_text VARCHAR(2000)` — and the biggest is a LEDGER

The model would **refuse or truncate** 18 real frontmatter values. The largest is **50,801
characters** — `last_amended` on `stories/STORY-INDEX.md`, verified by reading the file, not relayed.
It is a single line: nested `[Prior: … [Prior: … ]]]` closing with **21 consecutive `]`**.

That is not a too-small-column problem. **`last_amended` is an append-only ledger that has been
serialised into one scalar because markdown frontmatter has no other shape for it.** The other
overlong values are the same class (`delta`, `modified` — all amendment ledgers).

**Consequence: this is Cohort D (ledgers → rows) hiding inside a FIELD, not inside a document.**
Invariant 16's ratified per-shape rule says 11 `append-only-event` types store *entries* and derive
the file — this says the same treatment is needed at **field** granularity. Widening `v_text` would
preserve the defect; the fix is that these fields are not scalars. Filed as a migration item, not a
column change.

---

## 2. Q9a — does GMS support the generated view at all? **Yes.**

The sharpest risk, tested first and separately, because a "no" would invalidate L2-A's central
mechanism outright.

- ✓ GMS (pure-Go, no `dolt` binary) **accepted** `CREATE VIEW … MAX(CASE WHEN f.field='x' THEN
  f.v_text END) … GROUP BY`.
- ✓ The view is **queryable** and returns all 3,085 artifacts — a view that exists is not a view that
  answers, so both were checked.
- ✓ **PARITY GATE PASSED** — wide and pivot return byte-identical values over 200 artifacts × 12
  fields. No timing below was reported until parity held; an unequal comparison is not a measurement.

---

## 3. Q9b — latency by query shape

3,085 artifacts · **44,016 field rows** · 14.3 field rows/artifact · best of 5 after a warmup.

| query shape | WIDE | EAV / pivot | ratio | what issues it |
|---|---|---|---|---|
| **1 artifact, all fields, by key** | 57 µs | 58 µs | **1.0×** | L3 semantic ops — the dominant shape |
| filtered read on 1 field | 1.798 ms | 5.205 ms | **2.9×** | L5 gate predicates |
| aggregate gate: `GROUP BY` 1 field | 916 µs | 19.892 ms | **21.7×** | L5 gates-as-queries |
| **full-type scan, all fields** | 1.525 ms | 233.246 ms | **152.9×** | L4 render / projections |

**The shape that matters most is free.** Reading or writing one artifact — which is what every L3
semantic op does, and therefore what nearly every harness tool call does — shows **no measurable
penalty** (57 vs 58 µs). The penalty is concentrated entirely in whole-type scans.

⚠ **A correction I had to make to my own probe mid-measurement.** The first run populated only the 12
parity fields, giving a fan-in of **4.5** rows/artifact and a full-scan penalty of 69.1×. The measured
corpus mean is **20.4**. Reporting 69.1× would have been a number the real mass contradicts, so the
probe was changed to load **every** frontmatter field into the EAV table — which is the honest
asymmetry, since the EAV table holds the whole corpus's field mass in one table while a typed wide
table only ever holds its own declared columns. The penalty **doubled to 152.9×**. The probe's 14.3
is still *below* the 20.4 mean (it stores scalars only, not list items), so **the figures here remain
an understatement**.

### Scan rate is sub-linear, from two points rather than an extrapolation

| field rows scanned | full-scan time | per row |
|---|---|---|
| 13,962 | 90.6 ms | 6.49 µs |
| 44,016 | 233.2 ms | 5.30 µs |

Rows grew **3.15×**; time grew **2.57×**. Sub-linear, so extrapolating upward at 5.30 µs/row is
conservative.

---

## 4. Q9c — storage, and the design's declared risk #6 was pointed the WRONG WAY

Each model built in its **own** store, so the figure is attributable.

| | WIDE | EAV | EAV/WIDE |
|---|---|---|---|
| rows written | 3,085 | 44,016 | |
| **at rest (after `DOLT_GC`)** | **0.5 MB** | **1.1 MB** | **2.37×** |
| commit: 100 artifacts × 1 field | 640.7 KB | **54.0 KB** | **0.08×** |
| ↳ per artifact edited | 6.4 KB | **0.5 KB** | |
| journal, before GC | 34.5 MB | 332.4 MB | 9.63× |
| journal write amplification | 76.9× | **306.6×** | |

⚠ **A measurement I nearly reported wrongly.** Before GC the ratio looked like **9.63×** and I was
about to report it as storage. 332 MB for 44,016 short rows is ~7.9 KB/row, which is implausible for
the data — so I inspected the directory: a populated store was **147 MB, of which 143 MB was a single
chunk-journal file, with an empty `oldgen/`.** Nothing had been collected. That figure is **write
amplification**, a real but entirely different quantity from at-rest size. After `DOLT_GC` the true
at-rest ratio is **2.37×**.

⭐ **The design's declared risk #6 is inverted by measurement.** It says *"more rows per commit →
faster history growth"* and reports *"~6 KB/commit is the only measurement we have."* Measured, for
the steady-state write shape — one field changed on 100 artifacts — **EAV is 12× CHEAPER**
(54.0 KB vs 640.7 KB; 0.5 KB vs 6.4 KB per artifact). Field-per-row makes a single-field edit dirty
**one small row** instead of rewriting a **wide row**. And the wide figure of **6.4 KB per artifact
edited** independently reproduces the design's own ~6 KB/commit number, which is a useful cross-check
on both.

This matters more than the 2.37×, because at-rest size is paid **once** while history growth is paid
on **every write, forever, in a store whose history never shrinks.**

⚠ **New operational requirement for the migration surface (belongs in L7).** EAV bulk load runs at
**306.6× journal write amplification**. A 6,537-file migration that never collects will write
hundreds of MB of journal for single-digit MB of data — measured directly: 143 MB of journal from
~1 MB of data. **The chunked, resumable migration must GC periodically**, and that is a scheduling
obligation on the op that emits the next unit, not an afterthought.

---

## 5. The wide-table alternative has a ceiling the design never checked

`TestWideRowCeiling` — no corpus needed. GMS enforces a **65,504-byte row limit**, and utf8mb4 costs
4 bytes/char, so a `VARCHAR(n)` column reserves `4n+2` bytes.

| declared width | max columns/row | holds the median artifact (24 fields)? |
|---|---|---|
| `VARCHAR(2000)` — the design's own `v_text` width | **8** | ⛔ **no** |
| `VARCHAR(1000)` | 16 | ⛔ no |
| `VARCHAR(512)` | 31 | yes (but ⛔ fails the 127-field maximum) |
| `VARCHAR(255)` | 64 | yes (⛔ fails the 127-field maximum) |
| `VARCHAR(64)` | 200 | yes |
| `TEXT` | ≥60 accepted | yes — TEXT is stored out-of-row and escapes the budget |

**Measured, fairly.** Real values across those 12 fields max at **168 chars** (`wave`), most ≤ 31 —
so a **hand-sized** typed table is comfortable, and the probe's wide baseline uses `VARCHAR(255)`
(generous against the corpus) precisely so the comparison is not a walkover.

**But the design generates the schema from the registry.** A generator does not know a field's future
maximum length, so it must pick a generic width — and at a generic width the wide alternative
**cannot represent the median artifact**. That is a stronger argument for L2-A than the two the design
actually made (migration cost, and two-homes-drift), and it was not on the list.

---

## 6. The materialization trigger, DERIVED

L1–L2 specifies the fallback and says the trigger is missing. From §3's measured **5.30 µs per field
row** on a full-type scan:

> **TRIGGER.** Materialize a type's generated view as a table (with the parity gate
> `table == view` over the full population) when that type's **`artifact_field` row count exceeds
> 190,000** — the point at which its full-type scan crosses **~1 s**, which is the per-tool-call store
> budget V-K's no-long-running-ops rule implies.

Applying it to the corpora as they exist:

| corpus | largest type | field rows | projected full scan | materialize? | headroom |
|---|---|---|---|---|---|
| vsdd-factory | `behavioral-contract` | 49,121 | **260 ms** | **no** | **3.9×** |
| prism | `story` | 12,710 | 67 ms | no | 15.0× |
| rivetry | `behavioral-contract` | 7,605 | 40 ms | no | 25.0× |

**No type in any of the three corpora needs materialization, and the closest is 3.9× away.** The
fallback stays specified and unexercised, which is the correct state for a fallback — and it now has a
number attached instead of a hope.

**Two guards on that trigger, both earned here:**
1. The scan rate is **sub-linear** (§3), so 190,000 is conservative; re-measure rather than
   extrapolate if any type approaches it.
2. `behavioral-contract` at 25.1 field rows/artifact is the **fan-in outlier**, not the artifact-count
   outlier. A type's row count — not its artifact count — is the trigger's input. `prism/story` has
   **7× fewer artifacts** than `vsdd/behavioral-contract` but only **3.9×** fewer field rows.

---

## 7. What this changes in the design

| | change |
|---|---|
| **L2-A** | **CONFIRMED, on stronger grounds than it claimed.** Add the row-size ceiling (§5) as a third argument: at a generated width, the wide alternative cannot hold the median artifact. |
| L1–L2 field-mass claim | **CORRECTED**: order 10⁴ per corpus, not 10⁵. |
| L1–L2 declared risk #5 (pivot unmeasured) | **CLOSED.** Free on record reads (1.0×); 152.9× on full-type scans; trigger derived at 190,000 field rows. |
| L1–L2 declared risk #6 (history growth) | **INVERTED.** EAV is **12× cheaper** per edit, not more expensive. Correct the text. |
| `v_text VARCHAR(2000)` | **INSUFFICIENT** for 18 real values, max 50,801 chars — but the fix is that `last_amended`/`delta`/`modified` are **ledgers, not scalars** (Cohort D at field granularity). Do not widen the column. |
| Migration surface (L7) | **NEW REQUIREMENT**: periodic GC during bulk load; 306.6× journal write amplification measured. |
| §9 Q9 | answered. |
