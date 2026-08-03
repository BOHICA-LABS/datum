package main

// Graph algorithms that SQL cannot do, and only those.
//
// Each one is here because it maps to a MEASURED problem in the corpus, not because gonum
// offers it. `impact` is deliberately absent: reverse closure is one recursive CTE and SQL
// already answers it in ~3 ms, so routing it through a projection for symmetry would be
// worse, not better.

import (
	"fmt"
	"io"
	"sort"

	"golang.org/x/exp/rand"
	"gonum.org/v1/gonum/graph/community"
	"gonum.org/v1/gonum/graph/multi"
	"gonum.org/v1/gonum/graph/network"
	"gonum.org/v1/gonum/graph/topo"
)

// ── waves: topological order (the registry's declared `waves` verb) ──────────

type Wave struct {
	N       int
	Stories []string
}

type WaveResult struct {
	Waves  []Wave
	Cycles [][]string // dependency cycles; a cycle makes a schedule impossible
}

// Waves derives the wave schedule from story dependencies. The registry declares
// `wave-schedule` as authority: derived, and measured: the template exists with ZERO files
// in all three corpora — consistent with being derivable and never worth hand-writing.
//
// Longest-path layering, not gonum's plain Sort: a story belongs in the wave AFTER its
// deepest dependency, which is the schedule a human means by "wave".
func (p *Projection) Waves() *WaveResult {
	res := &WaveResult{}

	// Restrict to the story subgraph: waves are about stories, and mixing BC/VP nodes in
	// would produce layers nobody can act on.
	stories := map[int64]bool{}
	for k, id := range p.ids {
		if k.Type == "story" {
			stories[id] = true
		}
	}
	deps := map[int64][]int64{} // node -> the nodes it depends on
	indeg := map[int64]int{}
	for id := range stories {
		indeg[id] = 0
	}
	for it := p.g.Edges(); it.Next(); {
		e := it.Edge()
		u, v := e.From().ID(), e.To().ID()
		if !stories[u] || !stories[v] {
			continue
		}
		onlyDep := false
		for li := e.(multi.Edge).Lines; li.Next(); {
			if p.meta[li.Line().ID()].LinkType == "depends_on" {
				onlyDep = true
			}
		}
		if !onlyDep {
			continue
		}
		deps[u] = append(deps[u], v)
		indeg[u]++
	}

	// Cycles first: reporting a schedule computed over a cyclic graph would be a lie.
	for _, c := range topo.TarjanSCC(p.Simple()) {
		if len(c) < 2 {
			continue
		}
		var names []string
		allStories := true
		for _, n := range c {
			k := p.key[n.ID()]
			if k.Type != "story" {
				allStories = false
			}
			names = append(names, k.String())
		}
		if allStories {
			sort.Strings(names)
			res.Cycles = append(res.Cycles, names)
		}
	}
	if len(res.Cycles) > 0 {
		return res // no schedule exists; say so rather than emit a plausible one
	}

	// Kahn, layered.
	layer := map[int64]int{}
	var ready []int64
	for id, d := range indeg {
		if d == 0 {
			ready = append(ready, id)
			layer[id] = 0
		}
	}
	rev := map[int64][]int64{} // dependency -> dependents
	for u, ds := range deps {
		for _, v := range ds {
			rev[v] = append(rev[v], u)
		}
	}
	for len(ready) > 0 {
		cur := ready
		ready = nil
		for _, v := range cur {
			for _, u := range rev[v] {
				if layer[v]+1 > layer[u] {
					layer[u] = layer[v] + 1
				}
				indeg[u]--
				if indeg[u] == 0 {
					ready = append(ready, u)
				}
			}
		}
	}
	byLayer := map[int][]string{}
	maxL := 0
	for id := range stories {
		l := layer[id]
		byLayer[l] = append(byLayer[l], p.key[id].Key)
		if l > maxL {
			maxL = l
		}
	}
	for l := 0; l <= maxL; l++ {
		s := byLayer[l]
		if len(s) == 0 {
			continue
		}
		sort.Strings(s)
		res.Waves = append(res.Waves, Wave{N: l + 1, Stories: s})
	}
	return res
}

// ── metrics ──────────────────────────────────────────────────────────────────

type Metric struct {
	Key   NodeKey
	Score float64
}

type Metrics struct {
	// Degree is FIRST because it is the best predictor measured and costs O(E).
	// See research/GRAPH-PERF.md: AUC 0.871 at predicting which artifacts the adversary
	// flags, versus 0.843 for PageRank and 0.725 for betweenness — which costs ~3,000x more.
	Degree []Metric
	// BetweennessSkipped says WHY betweenness is absent, if it is. Never silent.
	BetweennessSkipped string
	Communities   []Community
	Betweenness   []Metric
	PageRank      []Metric
	Articulation  []NodeKey
	SCCs          [][]NodeKey
	Dangling      []NodeKey
	Nodes, Edges  int
	ByType        map[string]int
}

// MetricsOpts exists because BENCHMARKING refuted the design note that said "no performance
// problem at current scale, and probably none at 10x". Measured on synthetic graphs matching
// the live corpus's shape (hubs + long tail):
//
//	                    1x (2.4k nodes)   10x (24k nodes)
//	TarjanSCC                   0.8 ms
//	Simple collapse             1.6 ms
//	articulationPoints          5.0 ms         59 ms
//	Louvain                    20   ms
//	PageRankSparse              1.1 ms         16 ms
//	Betweenness               236   ms      ~52 s        <- O(V*E), superlinear
//
// So: everything except Betweenness is cheap and scales fine. Betweenness alone went 106x
// for a 10x node count, which makes it unusable as a default. It is therefore OPT-IN and
// guarded by a node threshold.
type MetricsOpts struct {
	Top int
	// Betweenness is opt-in: 236 ms at live scale, ~52 s at 10x.
	Betweenness bool
	// BetweennessMaxNodes refuses rather than hangs. 0 uses the default.
	BetweennessMaxNodes int
	// Seed makes Louvain reproducible; an unseeded run returns different communities each
	// time, which would make this unusable as a gate.
	Seed uint64
}

const defaultBetweennessMaxNodes = 5000

// ComputeMetrics runs the algorithms that earn their place.
//
// THE HYPOTHESIS WAS TESTED AND BETWEENNESS LOST. The reason betweenness was built was a
// claim that the adversary's propagation misses cluster on high-betweenness nodes. Measured
// against 2,138 extracted findings (AUC = P(a flagged artifact outranks an unflagged one)):
//
//	degree       0.871   O(E), free          <- BEST
//	pagerank     0.843   16 ms at 24k nodes
//	betweenness  0.725   ~52 s at 24k nodes  <- WORST, and ~3,000x the cost
//
// So the cheap measures predict BETTER. Betweenness stays opt-in for research and is off
// the critical path; degree and PageRankSparse are the shipped signals.
//
// CAVEAT, because the decision is robust but the causal story is not: the proxy is "the
// artifact id is mentioned in a finding", and well-connected artifacts get discussed more in
// general, so degree's edge is partly tautological. That undermines "centrality predicts
// risk" as an explanation; it does NOT undermine "betweenness is not worth 52 seconds",
// which holds under any reading.
//
// And the standing warning still applies: centrality means "structurally central", NOT
// "important".
func (p *Projection) ComputeMetrics(opts MetricsOpts) *Metrics {
	if opts.BetweennessMaxNodes == 0 {
		opts.BetweennessMaxNodes = defaultBetweennessMaxNodes
	}
	if opts.Seed == 0 {
		opts.Seed = 1
	}
	top := opts.Top
	m := &Metrics{Nodes: p.Nodes(), Edges: p.Edges(), ByType: map[string]int{}, Dangling: p.Dangling()}
	for k := range p.ids {
		m.ByType[k.Type]++
	}
	s := p.Simple()

	// Degree centrality: O(E) and the BEST predictor measured of adversary-flagged
	// artifacts (AUC 0.871). Computed always, because it is effectively free.
	for k, d := range p.Degrees() {
		if d > 0 {
			m.Degree = append(m.Degree, Metric{k, float64(d)})
		}
	}

	// Betweenness: how often a node sits on shortest paths between others. Hypothesis:
	// these are where propagation misses happen (module-criticality, the four indexes,
	// verification-coverage-matrix all show up in the adversary's findings repeatedly).
	// OPT-IN and BOUNDED — see MetricsOpts for the measurements that forced this.
	switch {
	case !opts.Betweenness:
		m.BetweennessSkipped = "not requested (--betweenness); it is O(V*E) and dominates the run"
	case m.Nodes > opts.BetweennessMaxNodes:
		// Refused, not silently skipped: a metrics report that quietly omitted its most
		// expensive column would be indistinguishable from one where nothing was central.
		m.BetweennessSkipped = fmt.Sprintf(
			"REFUSED: %d nodes exceeds the %d-node bound (measured ~52 s at 24k nodes); raise --betweenness-max to override",
			m.Nodes, opts.BetweennessMaxNodes)
	default:
		for id, v := range network.Betweenness(s) {
			if v > 0 {
				m.Betweenness = append(m.Betweenness, Metric{p.key[id], v})
			}
		}
	}
	// PageRankSPARSE, not PageRank. gonum's dense PageRank builds a V*V matrix: measured
	// 218 ms and 47 MB at 2,400 nodes, versus 1.1 ms and 1.1 MB sparse — 197x faster on a
	// graph with 4,060 edges over 2,421 nodes. The dense call would have allocated ~4.6 GB
	// at 10x. Found by benchmarking, not by reading.
	for id, v := range network.PageRankSparse(s, 0.85, 1e-6) {
		m.PageRank = append(m.PageRank, Metric{p.key[id], v})
	}
	byScore := func(x []Metric) {
		sort.Slice(x, func(i, j int) bool {
			if x[i].Score != x[j].Score {
				return x[i].Score > x[j].Score
			}
			return x[i].Key.String() < x[j].Key.String() // deterministic ties
		})
	}
	byScore(m.Betweenness)
	byScore(m.PageRank)
	byScore(m.Degree)
	if top > 0 {
		if len(m.Degree) > top {
			m.Degree = m.Degree[:top]
		}
		if len(m.Betweenness) > top {
			m.Betweenness = m.Betweenness[:top]
		}
		if len(m.PageRank) > top {
			m.PageRank = m.PageRank[:top]
		}
	}

	// Articulation points: an artifact whose removal disconnects the traceability graph.
	// Needs an UNDIRECTED view — biconnectivity is undefined on a digraph.
	m.Articulation = p.articulationPoints()

	m.Communities = p.Communities(opts.Seed)

	// SCCs of size > 1 are cycles. Reported for every node type, not just stories.
	for _, c := range topo.TarjanSCC(s) {
		if len(c) < 2 {
			continue
		}
		var g []NodeKey
		for _, n := range c {
			g = append(g, p.key[n.ID()])
		}
		sort.Slice(g, func(i, j int) bool { return g[i].String() < g[j].String() })
		m.SCCs = append(m.SCCs, g)
	}
	return m
}

// articulationPoints finds cut vertices — an artifact whose removal disconnects the
// traceability graph — via Hopcroft-Tarjan DFS lowlink on the UNDIRECTED view.
//
// ⚠ HAND-ROLLED BECAUSE GONUM DOES NOT HAVE IT. An earlier design note of mine claimed
// `topo.BiconnectedComponents` exists; it does not. gonum v0.17.0's topo package offers
// ConnectedComponents / TarjanSCC / Sort / DirectedCyclesIn / KCore / BronKerbosch and no
// biconnectivity at all. This is the standard algorithm, and it is pinned by tests against
// graphs whose cut vertices are known by hand — because an unverified graph algorithm that
// returns a plausible-looking list is worse than not having one.
//
// O(V+E). Iterative rather than recursive: the corpus is shallow today, but a recursive DFS
// over a 100k-node projection would blow the stack, and that is not a failure worth
// discovering later.
func (p *Projection) articulationPoints() []NodeKey {
	u := p.Undirected()
	adj := map[int64][]int64{}
	var nodes []int64
	for it := u.Nodes(); it.Next(); {
		id := it.Node().ID()
		nodes = append(nodes, id)
		for nb := u.From(id); nb.Next(); {
			adj[id] = append(adj[id], nb.Node().ID())
		}
	}
	sort.Slice(nodes, func(i, j int) bool { return nodes[i] < nodes[j] }) // determinism
	for id := range adj {
		sort.Slice(adj[id], func(i, j int) bool { return adj[id][i] < adj[id][j] })
	}

	const none = int64(-1)
	disc := map[int64]int{}
	low := map[int64]int{}
	parent := map[int64]int64{}
	isCut := map[int64]bool{}
	visited := map[int64]bool{}
	timer := 0

	type frame struct {
		v        int64
		childIdx int
		children int
	}
	for _, root := range nodes {
		if visited[root] {
			continue
		}
		parent[root] = none
		stack := []*frame{{v: root}}
		visited[root] = true
		timer++
		disc[root], low[root] = timer, timer
		for len(stack) > 0 {
			f := stack[len(stack)-1]
			if f.childIdx < len(adj[f.v]) {
				w := adj[f.v][f.childIdx]
				f.childIdx++
				if !visited[w] {
					f.children++
					parent[w] = f.v
					visited[w] = true
					timer++
					disc[w], low[w] = timer, timer
					stack = append(stack, &frame{v: w})
				} else if w != parent[f.v] {
					if disc[w] < low[f.v] {
						low[f.v] = disc[w]
					}
				}
				continue
			}
			// done with v: fold into its parent
			stack = stack[:len(stack)-1]
			if pv := parent[f.v]; pv != none {
				if low[f.v] < low[pv] {
					low[pv] = low[f.v]
				}
				// a non-root parent is a cut vertex when a child cannot reach above it
				if parent[pv] != none && low[f.v] >= disc[pv] {
					isCut[pv] = true
				}
			}
			// a ROOT is a cut vertex iff it has more than one DFS child
			if parent[f.v] == none && f.children > 1 {
				isCut[f.v] = true
			}
		}
	}
	var out []NodeKey
	for id := range isCut {
		out = append(out, p.key[id])
	}
	sort.Slice(out, func(i, j int) bool { return out[i].String() < out[j].String() })
	return out
}

// Communities runs Louvain modularity and reports, per detected community, which declared
// subsystem its members mostly belong to. The point is NOT the clustering — it is the
// MISMATCH: a BC whose graph neighbourhood is overwhelmingly SS-07 while it declares SS-09
// is a mis-assignment, which generalises the current `integrity` finding class (5 prefix
// mismatches today) from string-prefix comparison to actual structure.
//
// Louvain is randomised, so the source is SEEDED: an unseeded run gives different
// communities each invocation, which would make this unusable as a gate.
func (p *Projection) Communities(seed uint64) []Community {
	r := community.Modularize(p.Undirected(), 1.0, rand.NewSource(seed))
	var out []Community
	for _, c := range r.Communities() {
		cc := Community{}
		ss := map[string]int{}
		for _, n := range c {
			k := p.key[n.ID()]
			cc.Members = append(cc.Members, k)
			if k.Type == "subsystem" {
				ss[k.Key]++
			}
		}
		if len(cc.Members) < 2 {
			continue
		}
		sort.Slice(cc.Members, func(i, j int) bool { return cc.Members[i].String() < cc.Members[j].String() })
		best, bestN := "", 0
		for s, n := range ss {
			if n > bestN || (n == bestN && s < best) {
				best, bestN = s, n
			}
		}
		cc.DominantSubsystem = best
		cc.Size = len(cc.Members)
		out = append(out, cc)
	}
	sort.Slice(out, func(i, j int) bool { return out[i].Size > out[j].Size })
	return out
}

type Community struct {
	Size              int
	DominantSubsystem string
	Members           []NodeKey
}

// ── DOT export ───────────────────────────────────────────────────────────────

// WriteDOT emits Graphviz. Hand-rolled rather than gonum's encoding/dot so the labels are
// the artifact KEYS rather than gonum's int64 ids, which would make the output useless.
//
// The output is a DERIVED artifact: if it is ever committed it goes through
// shadow -> proven -> retired like the indexes. A hand-tweaked diagram in the corpus would
// be a brand new drift source.
func (p *Projection) WriteDOT(w io.Writer, scope string) error {
	fmt.Fprintln(w, "digraph factory {")
	fmt.Fprintln(w, "  rankdir=LR; node [shape=box, fontname=\"Helvetica\", fontsize=10];")
	shape := map[string]string{
		"behavioral-contract": "box", "verification-property": "ellipse",
		"story": "component", "subsystem": "folder", "capability": "hexagon",
	}
	// scope selects a SUBGRAPH: nodes matching the scope PLUS their 1-hop neighbourhood.
	// Matching nodes alone is technically correct and useless — `--scope subsystem` would
	// emit 10 boxes and zero edges, because subsystems never point at each other.
	inScope := func(k NodeKey) bool { return scope == "" || k.Type == scope || k.Key == scope }
	keep := map[int64]bool{}
	seed := map[int64]bool{}
	for k, id := range p.ids {
		if inScope(k) {
			keep[id], seed[id] = true, true
		}
	}
	if scope != "" {
		s := p.Simple()
		for id := range seed {
			for it := s.From(id); it.Next(); {
				keep[it.Node().ID()] = true
			}
			for it := s.To(id); it.Next(); {
				keep[it.Node().ID()] = true
			}
		}
	}
	var ids []int64
	for id := range keep {
		ids = append(ids, id)
	}
	sort.Slice(ids, func(i, j int) bool { return p.key[ids[i]].String() < p.key[ids[j]].String() })
	for _, id := range ids {
		k := p.key[id]
		sh := shape[k.Type]
		if sh == "" {
			sh = "box"
		}
		style := ""
		if !p.declared[k] {
			style = ", style=dashed, color=red" // referenced but never declared
		}
		fmt.Fprintf(w, "  n%d [label=%q, shape=%s%s];\n", id, k.Key, sh, style)
	}
	type de struct{ s string }
	var lines []string
	for it := p.g.Edges(); it.Next(); {
		e := it.Edge()
		u, v := e.From().ID(), e.To().ID()
		if !keep[u] || !keep[v] {
			continue
		}
		for li := e.(multi.Edge).Lines; li.Next(); {
			m := p.meta[li.Line().ID()]
			lines = append(lines, fmt.Sprintf("  n%d -> n%d [label=%q, fontsize=8];\n", u, v, m.LinkType))
		}
	}
	sort.Strings(lines)
	for _, l := range lines {
		fmt.Fprint(w, l)
	}
	fmt.Fprintln(w, "}")
	return nil
}
