package main

// CSR correctness is established by PARITY with the gonum path on the same graph, not by
// inspection. Two implementations that disagree mean one is wrong; two that agree on hand-
// worked cases AND on generated graphs are trustworthy.

import (
	"fmt"
	"runtime"
	"sort"
	"testing"
)

func keysOf(c *CSR, ids []int32) []string {
	var out []string
	for _, id := range ids {
		out = append(out, c.Key(id).String())
	}
	sort.Strings(out)
	return out
}

func keyStrings(k []NodeKey) []string {
	var out []string
	for _, x := range k {
		out = append(out, x.String())
	}
	sort.Strings(out)
	return out
}

func eq(t *testing.T, what string, a, b []string) {
	t.Helper()
	if len(a) != len(b) {
		t.Errorf("%s: gonum %d vs csr %d\n gonum=%v\n   csr=%v", what, len(a), len(b), a, b)
		return
	}
	for i := range a {
		if a[i] != b[i] {
			t.Errorf("%s differs at %d: gonum %q vs csr %q", what, i, a[i], b[i])
			return
		}
	}
}

// The same hand-worked articulation cases the gonum implementation is pinned by, run through
// CSR. If these two ever disagree, one of them is wrong.
func TestCSRArticulationParity(t *testing.T) {
	cases := [][][2]NodeKey{
		{{s("A"), s("B")}, {s("B"), s("C")}},
		{{s("A"), s("B")}, {s("B"), s("C")}, {s("C"), s("A")}},
		{{s("A"), s("B")}, {s("B"), s("H")}, {s("H"), s("A")}, {s("C"), s("D")}, {s("D"), s("H")}, {s("H"), s("C")}},
		{{s("H"), s("A")}, {s("H"), s("B")}, {s("H"), s("C")}},
		{{s("A"), s("B")}, {s("C"), s("D")}},
		{{s("A"), s("B")}, {s("B"), s("C")}, {s("C"), s("D")}},
		{{s("A"), s("B")}, {s("B"), s("C")}, {s("C"), s("A")}, {s("C"), s("T")}},
	}
	for i, edges := range cases {
		t.Run(fmt.Sprint(i), func(t *testing.T) {
			p := testProjection(edges)
			c := csrFromProjection(p)
			eq(t, "articulation", keyStrings(p.articulationPoints()), keysOf(c, c.ArticulationPoints()))
		})
	}
}

func TestCSRParityOnGeneratedGraphs(t *testing.T) {
	for _, n := range []int{50, 500, 2400} {
		t.Run(fmt.Sprint(n), func(t *testing.T) {
			p := synthProjection(n, 7)
			c := csrFromProjection(p)

			if c.Nodes() != p.Nodes() {
				t.Fatalf("node count: gonum %d vs csr %d", p.Nodes(), c.Nodes())
			}
			if c.Edges() != p.Edges() {
				t.Fatalf("edge count: gonum %d vs csr %d — a collapse would show up here", p.Edges(), c.Edges())
			}
			eq(t, "articulation", keyStrings(p.articulationPoints()), keysOf(c, c.ArticulationPoints()))

			// degree parity, per node
			gd := p.Degrees()
			for id := int32(0); id < int32(c.Nodes()); id++ {
				k := c.Key(id)
				if got, want := c.Degree(id), gd[k]; got != want {
					t.Fatalf("degree %s: csr %d vs gonum %d", k, got, want)
				}
			}
			// SCC parity (count of size>1 components)
			var gs [][]NodeKey
			for _, comp := range p.ComputeMetrics(MetricsOpts{Top: 0}).SCCs {
				gs = append(gs, comp)
			}
			if len(gs) != len(c.SCC()) {
				t.Errorf("SCC count: gonum %d vs csr %d", len(gs), len(c.SCC()))
			}
		})
	}
}

func TestCSRWavesParity(t *testing.T) {
	p := testProjection([][2]NodeKey{
		{s("B"), s("A")}, {s("C"), s("B")}, {s("D"), s("A")},
	})
	c := csrFromProjection(p)
	gw, cw := p.Waves(), c.Waves()
	if len(gw.Waves) != len(cw.Waves) {
		t.Fatalf("wave count: gonum %d vs csr %d", len(gw.Waves), len(cw.Waves))
	}
	for i := range gw.Waves {
		a, b := gw.Waves[i].Stories, cw.Waves[i].Stories
		if fmt.Sprint(a) != fmt.Sprint(b) {
			t.Errorf("wave %d: gonum %v vs csr %v", i+1, a, b)
		}
	}
}

func TestCSRWavesRefusesCycle(t *testing.T) {
	c := csrFromProjection(testProjection([][2]NodeKey{
		{s("A"), s("B")}, {s("B"), s("C")}, {s("C"), s("A")},
	}))
	w := c.Waves()
	if len(w.Cycles) == 0 {
		t.Fatal("a cycle must be reported")
	}
	if len(w.Waves) != 0 {
		t.Errorf("no schedule exists for a cyclic graph, got %d waves", len(w.Waves))
	}
}

func TestCSRLookupAndDangling(t *testing.T) {
	p := testProjection([][2]NodeKey{{s("A"), s("B")}}, s("A"))
	c := csrFromProjection(p)
	if id := c.Lookup(s("A")); id < 0 || c.Key(id) != s("A") {
		t.Errorf("Lookup(A) failed, got id %d", id)
	}
	if id := c.Lookup(s("ZZZ")); id != -1 {
		t.Errorf("Lookup of an absent key must return -1, got %d", id)
	}
	eq(t, "dangling", keyStrings(p.Dangling()), keyStrings(c.Dangling()))
}

func TestCSRPreservesParallelEdges(t *testing.T) {
	p := newProjection()
	p.addEdge(s("A"), s("B"), EdgeMeta{LinkType: "behavioral_contracts"})
	p.addEdge(s("A"), s("B"), EdgeMeta{LinkType: "traces_to"})
	c := csrFromProjection(p)
	if c.Edges() != 2 {
		t.Fatalf("CSR must keep parallel edges (it stores a link type per edge slot), got %d", c.Edges())
	}
	seen := map[string]bool{}
	a := c.Lookup(s("A"))
	for i := range c.Out(a) {
		seen[c.OutLink(a, i)] = true
	}
	if !seen["behavioral_contracts"] || !seen["traces_to"] {
		t.Errorf("both link types must survive, got %v", seen)
	}
}

// ── the reason CSR exists: memory ────────────────────────────────────────────

func TestCSRMemoryVsGonum(t *testing.T) {
	fmt.Printf("\n%-9s %10s %12s %12s %8s\n", "nodes", "edges", "gonum heap", "CSR bytes", "ratio")
	for _, n := range []int{2400, 24000, 240000} {
		runtime.GC()
		var a, b runtime.MemStats
		runtime.ReadMemStats(&a)
		p := synthProjection(n, 10)
		runtime.GC()
		runtime.ReadMemStats(&b)
		gonumHeap := float64(b.HeapAlloc - a.HeapAlloc)
		// gonum's number must include the Simple() collapse, since every algorithm builds it
		runtime.ReadMemStats(&a)
		_ = p.Simple()
		runtime.ReadMemStats(&b)
		gonumHeap += float64(b.TotalAlloc - a.TotalAlloc)

		c := csrFromProjection(p)
		csrBytes := float64(c.MemoryEstimate())
		fmt.Printf("%-9d %10d %9.1f MB %9.1f MB %7.1fx\n",
			c.Nodes(), c.Edges(), gonumHeap/(1<<20), csrBytes/(1<<20), gonumHeap/csrBytes)
		if csrBytes >= gonumHeap {
			t.Errorf("CSR (%.0f B) is not smaller than gonum (%.0f B) at n=%d", csrBytes, gonumHeap, n)
		}
	}
}

// synthStories builds a STORY dependency chain, because synthProjection makes only
// behavioral-contract and subsystem nodes — so Waves() returned instantly on it and the
// benchmark measured nothing. Caught by an implausible 1.1 microseconds at 240k nodes.
func synthStories(n int) *CSR {
	b := newCSRBuilder()
	for i := 0; i < n; i++ {
		k := NodeKey{"story", fmt.Sprintf("S-%d.%d", i%100, i/100)}
		b.id(k)
		b.declared[k.Type+"\x00"+k.Key] = true
	}
	// a wide, shallow dependency forest: each story depends on one earlier story, which is
	// the shape a real wave schedule has (16 waves over 148 stories in the live corpus)
	for i := 1; i < n; i++ {
		from := NodeKey{"story", fmt.Sprintf("S-%d.%d", i%100, i/100)}
		to := NodeKey{"story", fmt.Sprintf("S-%d.%d", (i-1)%100, (i-1)/100)}
		if i%7 != 0 {
			to = NodeKey{"story", fmt.Sprintf("S-%d.%d", (i/2)%100, (i/2)/100)}
		}
		b.addEdge(from, to, "depends_on")
	}
	return b.finish()
}

func TestSynthStoriesActuallyProducesWaves(t *testing.T) {
	// guards the benchmark above from silently measuring nothing again
	c := synthStories(5000)
	w := c.Waves()
	if len(w.Cycles) == 0 && len(w.Waves) < 2 {
		t.Fatalf("the waves generator must produce a real multi-wave schedule, got %d waves / %d cycles",
			len(w.Waves), len(w.Cycles))
	}
	total := 0
	for _, x := range w.Waves {
		total += len(x.Stories)
	}
	if len(w.Cycles) == 0 && total == 0 {
		t.Fatal("no stories scheduled")
	}
}

func BenchmarkCSRWavesReal(b *testing.B) {
	for _, n := range []int{2400, 24000, 240000} {
		c := synthStories(n)
		b.Run(fmt.Sprint(n), func(b *testing.B) {
			for i := 0; i < b.N; i++ {
				c.Waves()
			}
		})
	}
}

func BenchmarkCSRAlgorithms(b *testing.B) {
	for _, n := range []int{2400, 24000, 240000} {
		p := synthProjection(n, 10)
		c := csrFromProjection(p)
		b.Run(fmt.Sprintf("Articulation_%d", n), func(b *testing.B) {
			for i := 0; i < b.N; i++ {
				c.ArticulationPoints()
			}
		})
		b.Run(fmt.Sprintf("SCC_%d", n), func(b *testing.B) {
			for i := 0; i < b.N; i++ {
				c.SCC()
			}
		})
		// Waves is benchmarked in BenchmarkCSRWavesReal: this graph has no story nodes.
	}
}
