# `fa` — phase 1

The first product code in this repo. Everything before it is a spike, a
specification and a decision record; this is the read-only shadow those documents
signed off ([DECISIONS D3](../research/DECISIONS.md), [SPEC §7](../research/SPEC.md)).

**What it does:** builds a throwaway Dolt store from the `.factory` markdown corpus
and runs the integrity gates as SQL, failing only on violations that are not in a
dated baseline allowlist.

**What it does not do:** write to the corpus, push anything, run a daemon, or need
a `dolt` binary. Markdown remains the single source of truth. If `fa` is wrong, a
CI job is wrong.

---

## Build

```sh
CGO_ENABLED=1 go build -tags gms_pure_go -o fa .
```

Both flags are mandatory. `CGO_ENABLED=1` is required by the embedded
`dolthub/driver/v2`; without `-tags gms_pure_go` the cgo build dies on ICU headers.
Measured cost: **39.5 s** wall / 200 s CPU on an M-series Mac from a cold build
cache, **148 MB** binary, 1.3 GB of build cache, 155 indirect dependencies. (On a
2-vCPU CI runner expect materially longer when the cache is cold — that is an
extrapolation from the CPU time, not a measurement.)

## Use

```sh
fa init   --db .fa-db                      # create both zone directories
fa import --db .fa-db ~/path/.factory      # shadow the corpus (idempotent)
fa validate --db .fa-db --baseline baseline.json
fa doctor --db .fa-db
fa count  --db .fa-db --by-subsystem       # counts, derived — never stored
fa baseline write --db .fa-db --out baseline.json --corpus ~/path
fa waves  --db .fa-db                      # wave schedule, derived from depends_on
fa graph build|metrics|dot|diff --db .fa-db
fa shadow --db .fa-db ~/path/.factory      # STORY 7: derived indexes, generated ALONGSIDE
```

`fa shadow` is story 7's **shadow** stage of `generate -> prove equal -> retire`. It
generates each derived index from the store, compares it cell by cell against the authored
document, and reports every disagreement — and it **writes nothing**, to either side. That
is the mechanism, not caution: flipping a subtly wrong generator replaces hand-maintained
drift with generated drift and destroys the evidence. 658 findings on the live corpus, of
which 573 are real drift, 44 are editorial and 41 are facts about derivation itself (a
declared scope predicate that keeps 41 retired stories from being resurrected, 38 planned
rows that cannot exist as records, one withdrawn-in-place row, one underivable column).
See [research/SHADOW-INDEXES.md](../research/SHADOW-INDEXES.md).

Exit codes: **0** the gate passed · **1** the gate failed · **2** `fa` itself
failed. Never collapse 1 and 2: in this spike one swallowed exit code caused an
infinite CI re-dispatch livelock with five green runs in a row.

---

## Measured on the live corpus

vsdd-factory `@82163b7f`, `.factory` on `factory-artifacts`, 3,145 files.

| | |
|---|---|
| `fa import` | **1.1–1.4 s** (scan + one transaction + Dolt commit) |
| `fa validate` | **0.15 s** |
| Records | 1,959 BC · 80 VP · 148 story · 10 subsystem |
| Edges | **1,509** |
| Node universes | cap 30 · di 18 · nfr 88 · fr 48 · adr 23 · epic 17 |
| Findings | **153** (type 44 · direction 58 · dangling 39 · count 7 · integrity 5) |

### Parity with the Python prototype

The port is verified against `poc/fa.py` + `poc/graph_import.py`, not merely
plausible. Identical record counts, identical universes, and the **82 import-path
findings match rule for rule** (44 type + 38 dangling):

```
27 story.blocks -> missing story          6 story.functional_requirements -> missing FR
16 VP.scope is multi-valued               5 story.behavioral_contracts -> missing BC
 8 VP.bcs holds an id plus prose          4 story.functional_requirements not an id
 7 VP.bcs value is not an id              3 story.depends_on value is not an id
 2 VP.domain_invariants id plus prose      2 bc.replacement holds prose
 2 story.subsystems holds an id plus prose
```

The edge sets were diffed row by row: the prototype's 1,490 edges are a strict
subset of `fa`'s 1,509 (see the correction below).

### What the new gates found, beyond the prototype's 82

| Class | N | What |
|---|---|---|
| `count` | 7 | a stated count disagrees with the records |
| `direction` | 58 | a dependency recorded in one direction only |
| `integrity` | 5 | a BC id prefix disagrees with its subsystem |
| `dangling` | 1 | `BC-2.02.013` has a record but the index does not enumerate it |

The count gate is the headline. It names each disagreeing claim individually:

```
ARCH-INDEX.md Total BCs                      states 1949, actual 1959
BC-INDEX.md body Total row                   states 1949, actual 1959
BC-INDEX.md frontmatter total_bcs            states 1955, actual 1959
BC-INDEX.md subsystem registry row SS-03     states   53, actual   56
BC-INDEX.md subsystem registry row SS-05     states  656, actual  655
BC-INDEX.md subsystem registry row SS-08     states  214, actual  218
BC-INDEX.md section heading SS-03            states   53, actual   56
```

The three per-subsystem drifts are new information: the spike measured the corpus's
four-way disagreement on the *total*, and this locates it in SS-03, SS-05 and SS-08.

---

## Two corrections to earlier claims

Both were found by building this, and both are the same shape — a parser that
silently lost input and therefore under-reported.

**1. The corpus graph has 1,509 edges, not 1,490.** The prototype's continuation
rule for wrapped inline lists was "the previous line has more `[` than `]`".
Frontmatter prose contains stray brackets — `BC-INDEX.md`'s own `last_amended`
holds `... [Prior: 2026-05-30 (v2.64) — ...` with 4 `[` against 3 `]` — so every
key after such a value was joined into it and vanished. That hid:

- `total_bcs: 1955`, the index's headline count claim, from the gate whose entire
  job is checking stated counts; and
- 19 real edges across 6 stories (`S-15.10/12/13/14/15/17`), whose
  `depends_on`, `blocks`, `behavioral_contracts` and `subsystems` all sat after a
  bracket-bearing `last_amended`.

`fa` requires the value to actually *open* an inline list before treating following
lines as continuations. Pinned by `TestFrontmatterProseBracketDoesNotSwallowKeys`.
The recovered edges resolved cleanly, so the finding count did not change — but the
direction gate went 53 → 58, since 7 of them are one-directional.

**2. "Distinct BC ids in BC-INDEX rows = 1962" needs its extraction rule stated.**
1962 is the count of distinct BC ids anywhere in the file, including changelog prose
citing BCs that were never written. Restricted to the enumeration table's first
column — the index's actual claim about which BCs exist — it is **1,959**, which
agrees with disk. `fa` therefore treats enumeration and counting as two separate
claims that fail independently, rather than as a fifth number.

---

## The baseline is the load-bearing part

`baseline.json`: **153 findings, dated 2026-07-31, corpus `82163b7f`**.

Without it the gate blocks every PR on day one and is switched off within a day.
With it:

| Scenario | Result |
|---|---|
| live corpus + baseline | `PASS  no new findings (153 baselined remain)` — exit 0 |
| live corpus + one planted dangling ref | `FAIL  1 new finding` naming `S-1.01 -> BC-9.99.999` — exit 1 |
| live corpus, `--strict` | `FAIL  153 finding(s), baseline ignored` — exit 1 |
| live corpus, no baseline | `FAIL  153 new finding(s)` — exit 1 |

Verified end to end against a **copy** of the corpus; the live one was never
modified. The ratchet only turns one way: new findings fail, fixed findings are
reported for removal, and `--strict` ignores the file entirely. A human-written
`waiver` on an entry survives regeneration, which is what D3's exit criterion
("each remaining item explicitly waived with a reason") needs.

**D3's exit criterion into phase 2 is not met yet** and cannot be met from here: it
requires the baseline at zero (or every item waived) *and* the gate catching a real
regression in a real PR. The planted-regression test above is a proof that the
mechanism works, not a substitute for that.

---

## The two requirements measurement made mandatory

**`fa doctor` checks WRITABILITY, not openability.** A second opener of a Dolt
directory opens *fine* and silently becomes read-only. Measured with a
`dolt sql-server` holding the store:

```
ok    schema current                   schema v1
FAIL  writable (not merely openable)   create probe table: Error 1105:
                                       cannot update manifest: database is read only
```

The schema check passed on the same store — which is exactly why openability proves
nothing. The probe writes a row and removes every trace; a test asserts it leaves
nothing behind.

**`fa aggregate` quarantines stuck staging refs.** A conflicted staging ref is
re-fetched and re-merged on *every* aggregator run — measured at 17 s then ~8 s of
pure waste, forever, with the backlog only growing. The policy is implemented and
tested here as pure, clock-free code (`quarantine.go`): bounded attempts,
run-counted backoff between them, then a move to `refs/dolt/quarantine/*` — never a
delete, because the ref still holds a writer's work. An unmergeable lineage
(`no common ancestor`, invariant 14) is quarantined on the *first* failure, since
retrying cannot change the answer.

The network plumbing is deliberately absent: phase 1 has no remote at all. Inspect
the policy with `fa aggregate plan --refs ... --state ... --run N`; `fa aggregate`
itself says what it is waiting for instead of pretending to work.

---

## Layout

| File | |
|---|---|
| `store.go` | embedded driver, zones, pinned connection, one transaction per unit of work |
| `schema.go` | the DDL, carried in the binary |
| `frontmatter.go` | the YAML-ish scraper and its four hard-won rules |
| `corpus.go` | pure corpus → records + edges + assertions + findings |
| `import.go` | one transaction, FK rejections recorded as findings |
| `validate.go` | every gate, as a query |
| `registry.go` · `registry_gate.go` | the artifact type registry, embedded, and its corpus-side gate |
| `mdtable.go` | markdown table parsing + cell normalisation, each rule carrying the false-finding count it prevents |
| `shadow.go` | story 7's shadow stage: derive each index, adjudicate cell by cell, never write |
| `findings.go` | story 4: adversarial findings as ROWS — six id conventions, one row per (review, finding_id), structural ownership |
| `subartifact.go` | story 12a: AC/EC/PC/T-task as rows with TYPED links; POLICY 8 becomes a join |
| `proseref.go` | story 12b: section refs (3-way resolution over D-A's partition) + version cites judged by pin_policy |
| `graph*.go` · `csr.go` | the knowledge-graph projection and the compact CSR engine for 250k+ |
| `baseline.go` | the dated allowlist and its ratchet |
| `doctor.go` | writability, half-merge, schema, content |
| `quarantine.go` | the `fa aggregate` staging-ref policy |
| `workflows/fa-validate.yml` | the CI gate (deploy to `.github/workflows/` in vsdd-factory) |

Tests: `CGO_ENABLED=1 go test -tags gms_pure_go ./...` — 116 tests (99 top-level functions, 116 including subtests), ~6.7 s, no
network and no `dolt` binary. The integration tests run against a real embedded
store built from a fixture corpus with one planted violation per gate: a gate that
has never been shown failing has been run, not tested.

## Not implemented (and why)

Phase 1 is `import` + `validate` only. `fa get/trace/coverage/history/asof/diff`,
the write API (`create/amend/retire/rm`), `render`, `lease`, `wave`, `instance` and
`sync` are phases 2–4 in [SPEC §7](../research/SPEC.md). `count` and `doctor` are
here because the gate needs them. The walled zone is created and its cross-zone
check is implemented and tested, but the live corpus has **zero** holdout scenarios
(`.factory/holdout-evaluations/` holds only a `.gitkeep`), so on real data that pass
reports 0 references — proven against a fixture instead, and reported as
`cross-zone checked, 0 refs` rather than silently as a pass.
