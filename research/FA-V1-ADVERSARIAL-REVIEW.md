---
title: FA-V1-ADVERSARIAL-REVIEW — fresh-eyes attack on the four layer designs
date: 2026-08-03
purpose: attack the seams of ~6,300 lines written partly in parallel; every finding measured, not asserted
status: REVIEW — 8 findings CONFIRMED, 3 candidate findings WITHDRAWN after checking
method: cross-doc numeric reconciliation + mechanism-vs-requirement contradiction hunting + running the tool against all three corpora
---

# Adversarial review of the four layer designs

Reviewed: `FA-V1-L1-L2-STORAGE-SCHEMA.md` (1,350) · `FA-V1-L3-L4-OPS-PROJECTIONS.md` (1,696) ·
`FA-V1-L5-L6-POLICY-ENGINE.md` (1,562) · `FA-V1-MIGRATION.md` (724), against
`FA-V1-DESIGN.md` (498). Fresh eyes are genuine: these four were authored by sub-agents in a prior
session, partly in parallel.

**8 findings confirmed. 3 candidate findings withdrawn** after checking — recorded below, because a
review that reports only its hits is not showing its work, and because two of the three were *my*
misreadings rather than the docs' errors.

**The single most important finding is F1**, which is not a defect in any one document: it is a
systematic assumption that runs through every layer and is falsified by measurement.

---

## F1 ⛔ SYSTEMATIC — the loaders encode ONE project's LAYOUT as if it were universal, which
## contradicts V-F across every layer, and it MANUFACTURES FALSE FINDINGS

**Severity: highest. Four independent instances, all measured this session.**

V-F says *"every project using the factory migrates"* and multi-tenancy is a v1 requirement. But
`datum`'s catalog and universe loaders resolve data by **vsdd-factory's directory layout and filename
conventions**, so a project that organises differently is not read — and the resulting absence is
reported as *the corpus's* defect.

| # | what is encoded | how prism/rivetry differ | measured consequence |
|---|---|---|---|
| 1 | **filename CASE** — `^(VP-\d+)` | prism names all 80 VPs `vp-001-*.md` | **80 → 0 rows, no error.** Instance nine. *(fixed this session)* |
| 2 | **BC LAYOUT** — `ss-NN/` dirs + one `ARCH-INDEX.md` regex | prism stores all 270 BCs FLAT; its ARCH-INDEX rows don't match the regex | subsystem catalog EMPTY → **all 269 BCs rejected**, `bc=0`, and **808 spurious dangling findings** *(fixed this session)* |
| 3 | **EPIC LAYOUT** — `Glob("stories/epics/E-*.md")` | prism declares epics in `specs/epics.md` (8,150 bytes, E-001…) | `epic=0` and **114 FALSE `story.epic_id -> missing epic` findings** *(NOT fixed)* |
| 4 | **FR / NFR catalogs** | neither project uses vsdd's catalog location | `fr=0`, `nfr=0` for **both** other projects *(NOT fixed)* |

**The universes, measured side by side:**

| corpus | adr | cap | di | epic | fr | nfr |
|---|---|---|---|---|---|---|
| vsdd-factory | 23 | 30 | 18 | **17** | **48** | **88** |
| prism | 57 | 39 | 30 | **0** | **0** | **0** |
| rivetry | 54 | 23 | 25 | **0** | **0** | **0** |

**Three of six universes are empty for two of three projects, and nothing flags it as suspicious.**
`adr`/`cap`/`di` load fine, which is exactly what makes this dangerous: the loader looks like it works.

### Why this is a DESIGN finding and not four bugs

1. **It inverts the finding's blame.** A missing universe turns every legitimate reference into a
   dangling one. prism's 114 "missing epic" findings are `datum` failing to read a file that exists.
   This is the measured class *"a normalisation rule aimed at the WRONG COLUMN manufactures exactly
   what it was added to prevent"* (292 self-inflicted findings), now at the scale of a whole universe.
2. **It defeats X1, the anti-instance-nine conservation gate.** X1 checks
   `files_on_disk(project,type) == rows + declared_out_of_scope + rejected_with_reason`. An epic
   catalog the loader never looks for contributes **0 to `files_on_disk`**, so X1 passes while the
   universe is empty. **A conservation gate cannot see input its own enumerator never enumerated.**
3. **It will recur under V-C.** The canonical type set is *"project-independent, with per-project
   divergence handled by the alias ledger"* — but the alias ledger resolves **type names**, not
   **locations**. There is no location-alias mechanism anywhere in the four designs.

### Recommended fix (a design addition, not a patch)

> **Locations must be REGISTRY DATA, not Go path literals.** Each type declares one or more
> `sources:` (glob or declaring-document patterns), per project where they diverge, in the same
> registry the schema is generated from. Then: (a) a project's divergent layout is *declared*, (b) X1's
> enumerator is derived from the same declaration as the loader, so conservation becomes checkable,
> and (c) a universe that resolves to **zero** entries while other artifacts *reference* that universe
> is a **loud finding** rather than silence.

⚠ Add the **zero-universe guard now**, independently: any universe that is empty while ≥1 artifact
references it is a finding. That alone converts all four instances from silent to loud.

---

## F2 ⛔ The registry hash gate RE-COUPLES every project, contradicting V-F's independence requirement

L1–L2 §2.1: the catalog mirror is *"gated by a content hash:
`hash(catalog rows) == hash(embedded registry)`, **asserted at every store open**, failing
`datum doctor` on mismatch."*

The registry is `go:embed`'d into **one shared binary**. The mirror is **per-project** (one store per
project). Therefore:

> **Any registry change ships a new binary whose hash matches NO project's mirror, so EVERY project's
> store fails its open-time gate simultaneously, until each is re-migrated.**

That is precisely what V-F forbids: *"Migration is N independent migrations … each independently
stageable and abandonable. **A project mid-migration must not block another project.**"*

The irony is structural: **L1–L2 chose one-store-per-project specifically to DECOUPLE projects** (push
contention is per-branch and untunable — 54 attempts with disjoint rows), then re-coupled them through
the schema path. It decoupled writes and re-coupled deploys.

**Fix:** the gate must be **version COMPATIBILITY**, not hash EQUALITY — a store may lag the binary by
N registry versions and stay readable, with writes refused only for types whose schema actually
changed. The mechanism already exists: `registry_state(registry_hash, registry_version, applied_at)`
records the version; only the *gate* is stated as equality. Keep the hash as a **drift detector**
(is this mirror what its recorded version says it should be?), not as an **admission test**.

---

## F3 ⛔ Cohort gate X4 embeds a VOLATILE SCALAR in a normative definition — and it has already gone
## stale TWICE during this one session

X4's pass condition: *"the `(project, type)` slice of **the 18,826 baseline** is reproduced by
`datum validate --registry` with delta 0."*

Measured, this session, on read-only corpora:

| when | total | what moved |
|---|---|---|
| doc as written | 18,826 | — |
| session start | **18,831** | prism 10,843 → 10,848 |
| session end | **18,936** | prism 10,848 → **10,953** (its concurrent session added 18 `DEFECT-*` story files at 08:23–08:25) |

**A gate whose pass condition names a literal count is a gate that expires.** The number moved twice
in one session without anyone touching vsdd-factory or rivetry.

⭐ **Independent confirmation from a different corpus.** `~/Dev/multi-repo`'s storyboard corpus derived
this exact rule the hard way as its **REVISION-ONLY PIN policy** (fix-burst 73): *"Live
instructional/normative text MUST cite artifact revisions … NEVER line counts."* And its own criterion
**self-spawned the defect it existed to kill** — it illustrated the rule with `design r9 (2543L)` when
r9 was 2514L. See `STORYBOARD-METHOD-ASSESSMENT.md`.

**Fix:** X4 cites the **baseline artifact and its version**, never the count. The count is a
projection; X4 already has the right mechanism in its second clause (*"or reconciled line by line to
registry evolution vs corpus drift"*) — it is only the literal that is wrong.

---

## F4 ⚠ L1–L2 justified its storage choice with the WRONG WORKLOAD; L5's central mechanism is the
## shape that model penalizes most

L1–L2's cost table concedes *"wide-row reads become a pivot"* and answers: *"the measured workload is
small (2,421 nodes / 4,060 edges; 4-hop whole-corpus rollup **3 ms**; FULLTEXT over 1,959 bodies
**0.15 s**)."*

Those are **graph and fulltext** numbers. They are not the shape L5 issues. L5's central mechanism is
**gates as queries** — *"a gate that is a query cannot disagree with the data it checks."* Measured
(`FA-V1-PIVOT-MEASUREMENT.md`):

| shape | penalty | who issues it |
|---|---|---|
| single artifact by key | **1.0×** | L3 ops |
| filtered read on one field | **2.9×** | L5 gate predicates |
| aggregate `GROUP BY` one field | **21.7×** | **L5 gates-as-queries** |
| full-type scan | **152.9×** | L4 render/projections |

**Not fatal** — 19.9 ms per aggregate gate is fine, and the trigger analysis shows no type within 3.9×
of needing materialization. But the *argument* cited a workload that isn't the one at risk, so the
conclusion was right by luck rather than by evidence. **L1–L2's cost table should cite these numbers.**

---

## F5 ⚠ Declared risk #6 is INVERTED by measurement

L1–L2 declared risk #6: *"History growth is unmeasured at field-per-row granularity. More rows per
commit → faster history growth."* Measured, each model in its own store, steady-state shape (one field
changed on 100 artifacts):

| | WIDE | EAV | |
|---|---|---|---|
| commit size | 640.7 KB | **54.0 KB** | **EAV 12× CHEAPER** |
| per artifact edited | 6.4 KB | 0.5 KB | |
| at rest, after `DOLT_GC` | 0.5 MB | 1.1 MB | EAV 2.37× larger |

Field-per-row makes a single-field edit dirty **one small row** instead of rewriting a **wide row**.
At-rest size is paid once; **history growth is paid on every write, forever, in a store whose history
never shrinks** — so the sign of #6 matters more than its magnitude. Correct the text.

*(The wide figure of 6.4 KB/artifact independently reproduces the design's own ~6 KB/commit
observation, which is a useful cross-check on both.)*

---

## F6 ⚠ `v_text VARCHAR(2000)` is insufficient, and the failure is a CATEGORY ERROR

18 real frontmatter values exceed it; the largest is **51,566 bytes** — `last_amended` on
`stories/STORY-INDEX.md`, one line of **116** nested `[Prior: …]` entries closing with 21 brackets,
with **unbalanced** nesting (115 openers, 42 closers).

**Widening the column would preserve the defect.** That value is an **append-only ledger serialised
into a scalar**, because markdown frontmatter has no other shape for one. Invariant 16's ratified
per-shape rule already says append-only-event **types** store entries and derive the file; this is the
identical situation at **field** granularity, which is where the corpus actually put it. *(Built this
session: `ledger.go` + `ledger_entry`, byte-exact reversible, gated over all three corpora — 18 fields
→ 229 entries.)*

---

## F7 ⚠ L1–L2's authorized measurement was specified against a population that CANNOT EXIST

§9 Q9: *"Authorize a measurement pass … over **2,362 BCs** and 2,211 finding rows."*

`1,959` (vsdd) `+ 269` (prism) `+ 134` (rivetry) `= 2,362` **exactly.** So Q9 sums BCs across all three
corpora — but L1–L2's own ratified decision is **one store per project**, so no store ever holds 2,362
BCs. The measurement it authorized was scoped to a population its own architecture makes impossible.

**Same error class as its field-mass claim**, which said *"order 10⁵ rows per corpus"* where the
largest corpus measures **68,866 = order 10⁴** (1.3×10⁵ is reached only by summing corpora). Both are
**"summing corpora that never share a store"** — worth naming as a class, because it is easy to repeat
and it always errs toward overestimating scale.

---

## F8 ⚠ The conservation gate cannot see what its enumerator never enumerates (a corollary of F1,
## recorded separately because it generalises)

X1 is called *"the anti-#9 gate — zero tolerance, no thresholds"* and it is the plan's most important
gate. But it compares rows against **`files_on_disk(project,type)`**, and that denominator is produced
by the same layout assumptions that F1 shows are wrong.

- prism's 80 VPs *were* countable by X1 (the files were in the expected directory, only the case
  differed) — X1 would have caught instance nine, as claimed. ✓
- prism's **epics are not**, because X1 would enumerate `stories/epics/E-*.md`, find 0 files, compare
  to 0 rows, and **pass**.

**A conservation gate whose denominator is derived from the same enumerator as its numerator can only
catch filter bugs, never location bugs.** The gate needs an **independent** denominator — e.g. count
*every* `.md` file in the corpus once, and require that every file be attributed to exactly one type
or to `unmodeled_file`. That is a whole-corpus partition check, and it is the only shape that closes
the location class. `unmodeled_file` already exists in the L1–L2 table list; nothing currently
*requires* the partition to be total.

---

## WITHDRAWN candidate findings — checked, and the docs were right

Recorded because a review that reports only hits is hiding its method, and because two of these were
my misreading.

| candidate | why withdrawn |
|---|---|
| **"103 vs 119 types is a contradiction"** | Not a contradiction. The registry has **103 types + 16 `gap_types` + 4 `retired_types`**, verified by parsing it; `119 = 103 + 16`, and L1–L2 §"gap type (16, `pending_template: true`)" explicitly gives gap types *"a home, gated at `info`, until a template exists"*, with the reason stated. Consistent and deliberate. |
| **"the catalog mirror is a second home for the registry, violating invariant 17"** | Explicitly handled: mirror is `authority: derived`, regenerated at `datum migrate`, hash-gated, with the registry staying the single canonical copy embedded *and* read by the Python tooling. Invariant 17 is read through `authority` and names the enforcement. *(The hash gate has a different problem — see F2 — but the two-homes objection is answered.)* |
| **"enum/alias counts drift between docs"** | Checked by parsing the registry: **17 enums** (5 doc mentions, all "17") and **180 aliases**. No drift. |

---

## What this review does NOT cover — stated so the gap is not mistaken for coverage

- **L6 (the engine) remains unvalidated by any independent source.** The prism session register
  (11 of 21 prevented) touches no engine behaviour, and this review found no way to attack L6 with
  measurement because there is nothing built to measure. Carried forward unresolved from L5–L6, and
  restated as L7's Q9. **This is the largest untested surface in the design.**
- **I did not re-derive the 14-step ladder's ORDER.** L3–L4 asserts the order is correctness-critical
  and tested; I confirmed the claim is *made* and that a test is *specified*, not that the order is
  optimal.
- **The 22 derived types' render schemas** are still absent, so invariant 15 cannot be attacked at all
  yet — only its specification reviewed.

---

## Priority

> ⭐ **APPLIED 2026-08-03.** The text corrections this table asks for (F5, F7, F4) **have now been made
> in the layer docs**, along with the F3 de-scalaring of the two migration gates. Recording it here so
> "correct the text" cannot sit forever as an unactioned finding — which is the failure mode this
> review itself is about. What is applied vs still open is marked in the table.
>
> **Applied:** F5 (risk #6 corrected — it was inverted) · F7 (the 2,362-BC and 10⁵ figures corrected,
> and the error class NAMED as *"summing corpora that never share a store"*) · F4 (L1–L2's cost table
> now cites the **gate-shaped** latencies instead of graph/fulltext ones) · F3 (X4 and V4 now cite the
> baseline **artifact + version**, never a literal count; the per-project table is date-stamped) · plus
> the spine's stale state (4→16 decisions, "one unmeasured risk" → CLOSED, instance nine → FIXED,
> "ingests one of three corpora" → all three, L7 added to the layer list).
>
> **STILL OPEN — these are code/design changes, not text:** **F1** (locations must become registry
> data; ship the zero-universe guard first) and **F8** (X1 needs an independent denominator — a total
> whole-corpus partition into types ∪ `unmodeled_file`). **F2** (version-compatibility gate instead of
> hash equality) is also still open.

| | finding | action | status |
|---|---|---|---|
| **1** | **F1** locations encoded in Go | add `sources:` to the registry **+ ship the zero-universe guard immediately** (it converts all four instances from silent to loud, cheaply) | ⛔ **OPEN** |
| **2** | **F8** X1's denominator | require a **total whole-corpus partition** into types ∪ `unmodeled_file` | ⛔ **OPEN** |
| **3** | **F2** hash gate re-coupling | version-compatibility gate, keep hash as drift detector | ⛔ **OPEN** |
| **4** | **F3** volatile scalar in X4 | cite artifact + version, never the count | ✅ applied |
| 5 | **F5 · F7** | correct the text (risk #6's sign; the 10⁵ and 2,362 figures) | ✅ applied |
| 6 | **F4** | cite the gate-shaped latencies in L1–L2's cost table | ✅ applied |
| 7 | **F6** | already built this session; keep the *category* lesson | ✅ built |
