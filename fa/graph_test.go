package main

// Tests and BENCHMARKS for the graph projection.
//
// Two jobs here, and the second one exists because I made an unmeasured speed claim.
//
// 1. CORRECTNESS on graphs whose answers are known by hand. This matters most for
//    articulationPoints, which is HAND-ROLLED: gonum v0.17.0 has no biconnectivity at all
//    (an earlier design note of mine claimed `topo.BiconnectedComponents` exists — it does
//    not). An unverified graph algorithm that returns a plausible-looking list is worse
//    than not having one.
// 2. SCALING, measured at 1x / 10x / 100x the live corpus, because "single-digit
//    milliseconds" was an extrapolation from an operation count and the real figure for the
//    metrics suite on the live corpus is ~577 ms.

import (
	"context"
	"fmt"
	"testing"

	"gonum.org/v1/gonum/graph/multi"
	"gonum.org/v1/gonum/graph/network"
	"gonum.org/v1/gonum/graph/topo"
)

// ── a hand-built projection, so tests do not need a store ────────────────────

func testProjection(edges [][2]NodeKey, declared ...NodeKey) *Projection {
	p := newProjection()
	for _, k := range declared {
		p.node(k)
		p.declared[k] = true
	}
	for _, e := range edges {
		p.addEdge(e[0], e[1], EdgeMeta{LinkType: "depends_on", PinPolicy: "as_of"})
	}
	return p
}

func s(k string) NodeKey { return NodeKey{"story", k} }

// ── articulation points: answers worked out by hand ──────────────────────────

func TestArticulationPointsKnownAnswers(t *testing.T) {
	cases := []struct {
		name  string
		edges [][2]NodeKey
		want  []string
	}{
		{
			// A path A-B-C. B is the only cut vertex; the endpoints never are.
			name:  "path of three",
			edges: [][2]NodeKey{{s("A"), s("B")}, {s("B"), s("C")}},
			want:  []string{"story:B"},
		},
		{
			// A triangle is biconnected: removing any single node keeps it connected.
			name:  "triangle has none",
			edges: [][2]NodeKey{{s("A"), s("B")}, {s("B"), s("C")}, {s("C"), s("A")}},
			want:  nil,
		},
		{
			// Two triangles joined at H: H is the sole cut vertex (a bowtie).
			name: "bowtie joint",
			edges: [][2]NodeKey{
				{s("A"), s("B")}, {s("B"), s("H")}, {s("H"), s("A")},
				{s("C"), s("D")}, {s("D"), s("H")}, {s("H"), s("C")},
			},
			want: []string{"story:H"},
		},
		{
			// A star: the hub is a cut vertex, every leaf is not.
			name:  "star hub",
			edges: [][2]NodeKey{{s("H"), s("A")}, {s("H"), s("B")}, {s("H"), s("C")}},
			want:  []string{"story:H"},
		},
		{
			// Two disjoint edges: two components, no cut vertex in either.
			name:  "disconnected pairs",
			edges: [][2]NodeKey{{s("A"), s("B")}, {s("C"), s("D")}},
			want:  nil,
		},
		{
			// A-B-C-D path: both interior nodes are cut vertices.
			name:  "path of four has two",
			edges: [][2]NodeKey{{s("A"), s("B")}, {s("B"), s("C")}, {s("C"), s("D")}},
			want:  []string{"story:B", "story:C"},
		},
		{
			// A triangle with a tail: the attachment point is the cut vertex.
			name: "triangle plus tail",
			edges: [][2]NodeKey{
				{s("A"), s("B")}, {s("B"), s("C")}, {s("C"), s("A")}, {s("C"), s("T")},
			},
			want: []string{"story:C"},
		},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			got := testProjection(c.edges).articulationPoints()
			var gs []string
			for _, k := range got {
				gs = append(gs, k.String())
			}
			if len(gs) != len(c.want) {
				t.Fatalf("got %v, want %v", gs, c.want)
			}
			for i := range gs {
				if gs[i] != c.want[i] {
					t.Fatalf("got %v, want %v", gs, c.want)
				}
			}
		})
	}
}

// The live corpus must have NO self-edges and the algorithm must not loop forever on
// cycles — the iterative DFS exists so a deep graph cannot blow the stack.
func TestArticulationPointsTerminatesOnCycle(t *testing.T) {
	var edges [][2]NodeKey
	for i := 0; i < 500; i++ {
		edges = append(edges, [2]NodeKey{s(fmt.Sprint(i)), s(fmt.Sprint((i + 1) % 500))})
	}
	got := testProjection(edges).articulationPoints()
	if len(got) != 0 {
		t.Errorf("a pure cycle has no cut vertices, got %d", len(got))
	}
}

// ── waves ────────────────────────────────────────────────────────────────────

func TestWavesLayersByDeepestDependency(t *testing.T) {
	// C depends on B depends on A; D depends on A only.
	// Correct layering: A=1, {B,D}=2, C=3. A plain topological ORDER would allow C=2,
	// which is why this uses longest-path layering.
	p := testProjection([][2]NodeKey{
		{s("B"), s("A")}, {s("C"), s("B")}, {s("D"), s("A")},
	})
	w := p.Waves()
	if len(w.Cycles) != 0 {
		t.Fatalf("unexpected cycles: %v", w.Cycles)
	}
	if len(w.Waves) != 3 {
		t.Fatalf("want 3 waves, got %d: %+v", len(w.Waves), w.Waves)
	}
	if got := w.Waves[0].Stories; len(got) != 1 || got[0] != "A" {
		t.Errorf("wave 1 should be [A], got %v", got)
	}
	if got := w.Waves[1].Stories; len(got) != 2 || got[0] != "B" || got[1] != "D" {
		t.Errorf("wave 2 should be [B D], got %v", got)
	}
	if got := w.Waves[2].Stories; len(got) != 1 || got[0] != "C" {
		t.Errorf("wave 3 should be [C], got %v", got)
	}
}

// A cyclic dependency graph has NO schedule. Emitting a plausible one would be a lie.
func TestWavesRefusesToScheduleACycle(t *testing.T) {
	p := testProjection([][2]NodeKey{
		{s("A"), s("B")}, {s("B"), s("C")}, {s("C"), s("A")},
	})
	w := p.Waves()
	if len(w.Cycles) == 0 {
		t.Fatal("a dependency cycle must be reported")
	}
	if len(w.Waves) != 0 {
		t.Errorf("no schedule exists for a cyclic graph, got %d waves", len(w.Waves))
	}
}

// ── multi-edge fidelity: the trap simple.DirectedGraph would have hidden ─────

func TestParallelEdgesAreNotCollapsedInTheProjection(t *testing.T) {
	p := newProjection()
	a, b := s("A"), s("B")
	p.addEdge(a, b, EdgeMeta{LinkType: "behavioral_contracts"})
	p.addEdge(a, b, EdgeMeta{LinkType: "traces_to"})
	if got := p.Edges(); got != 2 {
		t.Fatalf("two link types between one pair must be TWO edges, got %d", got)
	}
	// and the collapsed view must be explicitly lossy, i.e. exactly one
	sg := p.Simple()
	n := 0
	for it := sg.Edges(); it.Next(); {
		n++
	}
	if n != 1 {
		t.Errorf("the collapsed simple view should hold 1 edge, got %d", n)
	}
	// the link types must still be retrievable from the multigraph
	seen := map[string]bool{}
	for it := p.g.Edges(); it.Next(); {
		for li := it.Edge().(multi.Edge).Lines; li.Next(); {
			seen[p.meta[li.Line().ID()].LinkType] = true
		}
	}
	if !seen["behavioral_contracts"] || !seen["traces_to"] {
		t.Errorf("both link types must survive the projection, got %v", seen)
	}
}

func TestDanglingIsAnEdgeToAnUndeclaredNode(t *testing.T) {
	// A is declared; B is only ever referenced.
	p := testProjection([][2]NodeKey{{s("A"), s("B")}}, s("A"))
	d := p.Dangling()
	if len(d) != 1 || d[0] != s("B") {
		t.Fatalf("want the undeclared head reported, got %v", d)
	}
}

func TestGraphDiffReportsNodesAndEdges(t *testing.T) {
	a := testProjection([][2]NodeKey{{s("A"), s("B")}})
	b := testProjection([][2]NodeKey{{s("A"), s("B")}, {s("B"), s("C")}})
	d := DiffGraphs(a, b)
	if len(d.NodesAdded) != 1 || d.NodesAdded[0] != s("C") {
		t.Errorf("want C added, got %v", d.NodesAdded)
	}
	if len(d.EdgesAdded) != 1 {
		t.Errorf("want 1 edge added, got %v", d.EdgesAdded)
	}
	if len(d.NodesRemoved) != 0 || len(d.EdgesRemoved) != 0 {
		t.Errorf("nothing was removed: %v %v", d.NodesRemoved, d.EdgesRemoved)
	}
}

// ── SCALING: synthetic graphs at 1x / 10x / 100x the live corpus ─────────────
//
// Live corpus, measured: 2,421 nodes / 4,060 edges. The synthetic generator matches its
// shape rather than a random graph — a few hub nodes (subsystems, indexes) with high
// in-degree and a long tail of leaves — because betweenness cost is very sensitive to
// structure and a uniform random graph would flatter the numbers.

func synthProjection(nodes, hubs int) *Projection {
	p := newProjection()
	for i := 0; i < nodes; i++ {
		k := NodeKey{"behavioral-contract", fmt.Sprintf("BC-%d", i)}
		p.node(k)
		p.declared[k] = true
	}
	for h := 0; h < hubs; h++ {
		hub := NodeKey{"subsystem", fmt.Sprintf("SS-%d", h)}
		p.node(hub)
		p.declared[hub] = true
	}
	for i := 0; i < nodes; i++ {
		from := NodeKey{"behavioral-contract", fmt.Sprintf("BC-%d", i)}
		p.addEdge(from, NodeKey{"subsystem", fmt.Sprintf("SS-%d", i%hubs)}, EdgeMeta{LinkType: "subsystems"})
		if i > 0 && i%3 == 0 { // a chain, so there are real shortest paths to sit on
			p.addEdge(from, NodeKey{"behavioral-contract", fmt.Sprintf("BC-%d", i-1)},
				EdgeMeta{LinkType: "traces_to"})
		}
	}
	return p
}

var scales = []struct {
	name  string
	nodes int
	hubs  int
}{
	{"1x_live", 2400, 10},
	{"10x", 24000, 30},
	{"100x", 240000, 100},
}

func BenchmarkProjectionBuildSynthetic(b *testing.B) {
	for _, sc := range scales {
		b.Run(sc.name, func(b *testing.B) {
			for i := 0; i < b.N; i++ {
				synthProjection(sc.nodes, sc.hubs)
			}
		})
	}
}

func BenchmarkBetweenness(b *testing.B) {
	// The expensive one: O(V*E). This is the claim that needs checking.
	for _, sc := range scales {
		if sc.nodes > 30000 {
			continue // see TestScalingReport: 100x betweenness is measured separately, once
		}
		p := synthProjection(sc.nodes, sc.hubs)
		b.Run(sc.name, func(b *testing.B) {
			for i := 0; i < b.N; i++ {
				p.ComputeMetrics(MetricsOpts{Top: 10, Betweenness: true, BetweennessMaxNodes: 1 << 30})
			}
		})
	}
}

func BenchmarkWaves(b *testing.B) {
	for _, sc := range scales {
		p := synthProjection(sc.nodes, sc.hubs)
		b.Run(sc.name, func(b *testing.B) {
			for i := 0; i < b.N; i++ {
				p.Waves()
			}
		})
	}
}

func BenchmarkArticulationPoints(b *testing.B) {
	for _, sc := range scales {
		p := synthProjection(sc.nodes, sc.hubs)
		b.Run(sc.name, func(b *testing.B) {
			for i := 0; i < b.N; i++ {
				p.articulationPoints()
			}
		})
	}
}

func BenchmarkSectionPartition(b *testing.B) {
	// D-A's partition runs over every markdown body on every import, so its cost is
	// per-corpus rather than per-graph.
	body := ""
	for i := 0; i < 200; i++ {
		body += fmt.Sprintf("## Section %d\nsome prose line\nand another\n", i)
	}
	b.SetBytes(int64(len(body)))
	for i := 0; i < b.N; i++ {
		if !SectionsLossless(body) {
			b.Fatal("partition not byte-exact")
		}
	}
}

// Per-algorithm cost, because "the metrics suite takes 493 ms" does not say WHICH
// algorithm to gate. Measured separately so the default command can include the cheap ones.
func BenchmarkAlgorithmsSeparately(b *testing.B) {
	p := synthProjection(2400, 10)
	sg := p.Simple()
	b.Run("Simple_collapse", func(b *testing.B) {
		for i := 0; i < b.N; i++ {
			p.Simple()
		}
	})
	b.Run("Betweenness", func(b *testing.B) {
		for i := 0; i < b.N; i++ {
			network.Betweenness(sg)
		}
	})
	b.Run("PageRank", func(b *testing.B) {
		for i := 0; i < b.N; i++ {
			network.PageRank(sg, 0.85, 1e-6)
		}
	})
	b.Run("TarjanSCC", func(b *testing.B) {
		for i := 0; i < b.N; i++ {
			topo.TarjanSCC(sg)
		}
	})
	b.Run("Articulation", func(b *testing.B) {
		for i := 0; i < b.N; i++ {
			p.articulationPoints()
		}
	})
	b.Run("Louvain", func(b *testing.B) {
		for i := 0; i < b.N; i++ {
			p.Communities(1)
		}
	})
}

// gonum's network.PageRank builds a DENSE V*V matrix: 2,400 nodes = 5.76M float64 = 46 MB,
// and 24,000 nodes = 576M entries = ~4.6 GB. Our graph is sparse (4,060 edges over 2,421
// nodes), so PageRankSparse is the correct call. Measured here rather than assumed.
func BenchmarkPageRankDenseVsSparse(b *testing.B) {
	for _, n := range []int{2400, 24000} {
		p := synthProjection(n, 10)
		sg := p.Simple()
		b.Run(fmt.Sprintf("Sparse_%d", n), func(b *testing.B) {
			for i := 0; i < b.N; i++ {
				network.PageRankSparse(sg, 0.85, 1e-6)
			}
		})
		if n <= 2400 { // the dense one at 24k allocates GBs; measured once at 1x only
			b.Run(fmt.Sprintf("Dense_%d", n), func(b *testing.B) {
				for i := 0; i < b.N; i++ {
					network.PageRank(sg, 0.85, 1e-6)
				}
			})
		}
	}
}

// A bad ref must be fa FAILING, never an empty graph. Before the ref probe, a nonexistent
// ref produced an EMPTY projection which `graph diff` then reported as "+2,421 nodes added"
// — a confident, wrong answer, which is worse than an error.
func TestBuildGraphRejectsBadRef(t *testing.T) {
	ctx := context.Background()
	dir := t.TempDir()
	st, err := Open(ctx, dir, ZoneOpen, true) // create
	if err != nil {
		t.Skipf("store unavailable: %v", err)
	}
	defer st.Close()
	reg, err := LoadRegistry("")
	if err != nil {
		t.Fatal(err)
	}
	if _, err := BuildGraph(ctx, st, reg, "definitely-not-a-ref"); err == nil {
		t.Fatal("a nonexistent ref must return an error, not an empty projection")
	}
}
