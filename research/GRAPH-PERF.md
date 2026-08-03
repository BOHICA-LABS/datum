---
title: GRAPH-PERF — the knowledge-graph projection, and the speed claims it refuted
date: 2026-07-31
purpose: measure the projection rather than extrapolate from operation counts, and record what the measurement changed
method: Go benchmarks over synthetic graphs matching the live corpus's SHAPE at 1x / 10x / 100x, plus the live corpus end to end
status: two of my three performance claims were WRONG. Both are fixed; the design changed as a result.
hardware: M-series Mac, 16 logical cores, Go 1.26.5
---

# The projection, measured

## What I claimed, and what is true

| claim | verdict | measured |
|---|---|---|
| "Betweenness is O(V·E) ≈ 3.5M ops: single-digit milliseconds" | **WRONG** | **236 ms** at 2.4k nodes |
| "There is no performance problem at current scale" | **holds** | full metrics suite **73 ms** by default |
| "…and probably none at 10×" | **WRONG** | **52.2 s** at 24k nodes — 106× for a 10× node count |

The third one is the consequential error. An operation count is not a runtime, and "probably
fine at 10×" is exactly the kind of consequence-from-a-structural-fact this project has a
standing rule against. Betweenness is now **opt-in and bounded**.

## Per-algorithm cost at live scale (2,400 nodes / ~3,200 edges)

| algorithm | cost | scaling to 10× |
|---|---|---|
| `topo.TarjanSCC` | 0.8 ms | fine |
| collapse to `simple` | 1.6 ms | fine |
| `articulationPoints` (hand-rolled) | 5.0 ms | 59 ms |
| `community.Modularize` (Louvain) | 20 ms | — |
| `network.PageRankSparse` | **1.1 ms** | 16 ms |
| `network.PageRank` (dense) | **218 ms** | would allocate ~4.6 GB |
| `network.Betweenness` | **236 ms** | **~52 s** |

## The bug benchmarking found

**gonum's `network.PageRank` builds a dense V×V matrix.** At 2,400 nodes that is 5.76M
float64 — measured **47 MB allocated per call**. At 24,000 nodes it is 576M entries, roughly
**4.6 GB**. Our graph is sparse (4,060 edges over 2,421 nodes), so the correct call is
`PageRankSparse`:

| | time | allocated |
|---|---|---|
| `PageRank` dense, 2,400 nodes | 218 ms | 47.4 MB |
| `PageRankSparse`, 2,400 nodes | **1.1 ms** | **1.1 MB** |
| `PageRankSparse`, 24,000 nodes | 16 ms | 10.9 MB |

**197× faster and 43× less memory**, for identical output on a sparse graph. Nothing in the
design review would have caught this — only running it did.

## Whole-projection cost, live corpus (2,421 nodes · 4,060 edges)

| | before | after |
|---|---|---|
| `datum graph metrics` (default) | 577 ms | **73 ms** |
| `datum graph metrics --betweenness` | — | 322 ms |
| projection build alone | 85 ms | 85 ms |

Both fixes contribute: sparse PageRank, and betweenness off unless asked for.

## Scaling, 1× → 100×

Synthetic graphs matching the corpus's **shape** — a few hubs with high in-degree plus a long
tail — not uniform random graphs, because betweenness cost is very sensitive to structure and
a random graph would have flattered the numbers.

| | 1× (2.4k) | 10× (24k) | 100× (240k) |
|---|---|---|---|
| projection build | 3.3 ms | 37.8 ms | 643 ms |
| `Waves` (topological layering) | 2.8 ms | 45.7 ms | 710 ms |
| `articulationPoints` | 5.4 ms | 58.8 ms | 980 ms |
| full metrics **with** betweenness | 493 ms | **52.2 s** | not run — extrapolates to ~1.5 h |

Everything except betweenness is **linear-ish and fine to 100×**. Betweenness is the sole
superlinear cost, and the 100× figure is deliberately marked as an extrapolation rather than
measured — the point of this document is not to repeat the mistake it records.

`SectionsLossless` (D-A's partition, which runs over every markdown body on every import):
**156 µs for a 200-section document, 54 MB/s**. Not a bottleneck.

## What the measurements changed in the code

1. **`PageRank` → `PageRankSparse`.** 197×.
2. **Betweenness is opt-in** (`--betweenness`) and **refuses above 5,000 nodes** with a
   message naming the measurement, rather than hanging. It is *refused*, never silently
   skipped: a metrics report that quietly dropped its most expensive column would be
   indistinguishable from one where nothing was central.
3. **Louvain is seeded** (`--seed`, default 1). It is randomised; an unseeded run returns
   different communities every invocation, which would make it useless as a gate.

## Correctness, not just speed

`articulationPoints` is **hand-rolled**, because an earlier design note of mine claimed
`topo.BiconnectedComponents` exists in gonum. **It does not** — gonum v0.17.0's `topo` package
offers `ConnectedComponents`, `TarjanSCC`, `Sort`, `DirectedCyclesIn`, `KCore`,
`BronKerbosch` and no biconnectivity at all. So it is Hopcroft–Tarjan DFS lowlink, iterative
rather than recursive (a recursive DFS over a 100k-node projection would blow the stack), and
pinned by **7 tests whose answers are worked out by hand**: path-of-3, triangle, bowtie, star,
disconnected pairs, path-of-4, triangle-plus-tail — plus a 500-node pure cycle to prove it
terminates and reports no cut vertices. An unverified graph algorithm returning a
plausible-looking list is worse than not having one.

## Live corpus results (2,421 nodes · 4,060 edges)

- **0 strongly connected components of size > 1** — no dependency cycles anywhere, which is
  why the wave schedule exists at all.
- **148 stories in 16 waves**, derived from `depends_on` by longest-path layering (a plain
  topological *order* would let a story sit in the same wave as its own dependency).
- **50 articulation points** — artifacts whose removal disconnects the traceability graph,
  including `BC-1.12.002`, `BC-1.12.003`, `E-12`, `E-14`, `S-1.02`, `S-1.05`.
- **11 Louvain communities** of size > 1, the largest dominated by SS-05 (649) and SS-06 (581).
- Top betweenness is all **stories** (`S-2.08` at 4,183); top PageRank is all **subsystems**
  (`SS-06`, `SS-05`). Two differently-biased views, as intended.

⚠ **The edge count is 4,060, not the 1,509 quoted elsewhere.** Different extraction rules, and
both are correct: 1,509 counts frontmatter *reference* edges, while the projection also
materialises `bc → subsystem` (1,959) and `bc → capability` as edges. Stating the rule because
an unexplained second number is how the corpus ended up asserting four different BC totals.

## A second silent failure, caught

`datum graph diff --from no-such-ref` originally reported **`nodes 0 → 2421 (+2421 added)`** and
exited 0. Cause: `BuildGraph` tolerates a missing table (phase 1 does not populate every
universe), and that tolerance turned an unresolvable ref into an *empty* projection, which
diff then read as "everything is new". Fixed with a ref probe before building — a bad ref is
now `datum` failing (exit **2**) — plus a guard that errors if no artifact universe resolves at
all. Pinned by `TestBuildGraphRejectsBadRef`.

## ⭐ The hypothesis test that changed the plan

Betweenness existed for one reason: a claim that the adversary's propagation misses cluster
on high-betweenness nodes. Before building sampled/parallel Brandes to make it scale, that
claim was tested — measuring the alternatives to a lever before pulling it.

**Method.** An artifact is FLAGGED if its id appears in the statement / location / defect text
of any of the 2,138 extracted F-\* findings. AUC = P(a flagged artifact outranks an unflagged
one); 0.5 is no signal. 231 flagged artifacts against 2,190 unflagged.

| measure | AUC | flagged mean | unflagged mean | cost |
|---|---|---|---|---|
| **degree** | **0.871** | 18.2 | 1.66 | **O(E), free** |
| `PageRankSparse` | 0.843 | 0.00204 | 0.000241 | 16 ms @ 24k |
| `Betweenness` | **0.725** | 80.2 | 1.69 | **~52 s @ 24k** |

**Betweenness is the WORST of the three predictors and roughly 3,000× the cost.** All three
carry real signal (well above 0.5), but the cheapest measure predicts best.

**Consequences, and they are large:**
- Sampled Brandes, parallel Brandes and Brandes-over-CSR come **off the critical path**.
  Betweenness stays opt-in for research; nothing ships depending on it.
- **`degree` is promoted into the default metrics** — always computed, since it is free.
- CSR is still needed at 250k+, but now for **memory** (3.1 GB → ~10 MB) and general
  traversal speed, not to rescue one algorithm. Much smaller scope.

⚠ **Caveat, because the decision is robust but the explanation is not.** The proxy is "the id
is mentioned in a finding", and well-connected artifacts get discussed more in general, so
degree's advantage is partly tautological. That weakens *"centrality predicts risk"* as a
causal claim. It does **not** weaken *"betweenness is not worth 52 seconds"*, which holds
under any reading of the confound. The honest statement is: we know what NOT to build; we do
not yet know that centrality is a risk signal.

Reproduce:
```sh
datum graph centrality --db <store> > /tmp/cent.csv    # every node, all three measures
# then the AUC computation in the session log against registry/fstar_findings.json
```

## CSR — the compact engine for 250k+ (built)

Two int32 arrays instead of gonum's maps, with keys interned into one byte slab and ids
assigned in **sorted key order** so `Lookup` is a binary search and no `map[string]int32`
is retained (that map alone would be ~80 MB at 1M nodes).

### Memory — measured, and better than the 30× I estimated

| nodes | edges | gonum heap (incl. the `Simple()` every algorithm builds) | CSR | ratio |
|---|---|---|---|---|
| 2,410 | 3,199 | 7.2 MB | **0.1 MB** | **96×** |
| 24,010 | 31,999 | 69.9 MB | **0.8 MB** | **91×** |
| 240,010 | 319,999 | **756.5 MB** | **7.9 MB** | **96×** |

Extrapolating the ratio to 1M nodes: ~3.1 GB → **~33 MB**. The live corpus projection is
**0.1 MB**.

### Speed — CSR is also ~100× faster

| | gonum | CSR | speedup |
|---|---|---|---|
| articulation points, 2.4k | 5.36 ms | **51 µs** | 104× |
| articulation points, 240k | 980 ms | **8.1 ms** | 121× |
| SCC, 240k | — | **4.6 ms** | |
| waves, 240k | 710 ms | **121 ms** | 5.9× |

Cache-friendly array traversal, not a cleverer algorithm — same asymptotics, far better
constants.

### What still uses gonum

Louvain only, plus betweenness when explicitly requested. Everything on the default path —
build, degree, SCC, articulation, waves, dangling — is CSR.

### Correctness by PARITY, not inspection

CSR is verified against the gonum implementation on the same graphs: the 7 hand-worked
articulation cases, generated graphs at 50/500/2,400 nodes (node count, edge count, per-node
degree, articulation set, SCC count), waves layering, dangling, and parallel-edge survival.
Two implementations agreeing on hand-worked answers *and* on generated graphs is the standard
being met here; either alone would not be.

### A benchmark that measured nothing, caught

`BenchmarkCSRAlgorithms/Waves` first reported **1.1 µs at 240k nodes**. Implausible, and the
cause was real: `synthProjection` creates only `behavioral-contract` and `subsystem` nodes, so
`Waves()` found no `story` type and returned immediately. The benchmark was timing an early
return. Fixed with a story-shaped generator, and pinned by
`TestSynthStoriesActuallyProducesWaves` so it cannot silently regress to measuring nothing.
Real figures are in the table above.

## Reproduce

```sh
cd datum
CGO_ENABLED=1 go test -tags gms_pure_go -run XXX -bench 'BenchmarkAlgorithmsSeparately' -benchtime 3x ./...
CGO_ENABLED=1 go test -tags gms_pure_go -run XXX -bench 'BenchmarkPageRankDenseVsSparse' -benchmem -benchtime 3x ./...
CGO_ENABLED=1 go test -tags gms_pure_go -run XXX -bench 'BenchmarkWaves|BenchmarkArticulation|BenchmarkProjectionBuild' -benchtime 3x ./...
CGO_ENABLED=1 go test -tags gms_pure_go -run XXX -bench 'BenchmarkBetweenness' -benchtime 1x -timeout 60m ./...   # ~53 s
```

```sh
# CSR parity + the memory table
CGO_ENABLED=1 go test -tags gms_pure_go -count=1 -run 'TestCSR' -v ./...
CGO_ENABLED=1 go test -tags gms_pure_go -run XXX -bench 'BenchmarkCSR' -benchtime 3x ./...
```

62 tests · 9 benchmarks · no network · no `dolt` binary.
