package main

// CSR — the compact projection, for 250k+ nodes.
//
// WHY THIS EXISTS. Measured, gonum's map-based graph types cost ~2 KB/node for the multigraph
// plus ~1.1 KB/node for the collapsed simple view every algorithm builds: 756 MB at 240k
// nodes and ~3.1 GB extrapolated at 1M. The graph is expected to reach that scale through our
// OWN roadmap — D-A sections and prose refs as nodes is ~100k section nodes from the existing
// 6,537 markdown files before any new artifact exists.
//
// Compressed Sparse Row is two int32 arrays. Per node: 4 (key offset) + 1 (type) + 4 (fwd
// offset) + 4 (rev offset) + 1 (declared) = 14 bytes plus the key text itself. Per edge: 4
// (dst) + 4 (reverse dst) + 1 (link type) = 9 bytes. At 1M nodes / 1.4M edges that is ~47 MB
// against ~3.1 GB — and it is cache-friendly, so traversal is faster too.
//
// TWO THINGS THIS DELIBERATELY DOES NOT DO:
//   - No Brandes. Betweenness was measured to be the WORST predictor of adversary-flagged
//     artifacts (AUC 0.725) at ~3,000x the cost of degree (0.871), so it is off the critical
//     path and there is nothing to port.
//   - No key->id map retained. Ids are assigned in SORTED key order, so Lookup is a binary
//     search over the slab. Retaining a map[string]int32 would cost ~80 MB at 1M nodes and
//     give back a third of the win.
//
// gonum is still used for Louvain, the one non-trivial algorithm not reimplemented here, via
// an explicit size-bounded conversion.

import (
	"bytes"
	"context"
	"fmt"
	"sort"

	"gonum.org/v1/gonum/graph/multi"
)

type CSR struct {
	n, m int32

	// interned keys: one byte slab, no per-node string header or map entry
	slab   []byte
	keyOff []int32 // n+1 offsets into slab
	keyTyp []uint8 // index into TypeNames
	TypeNames []string

	// forward adjacency
	off []int32 // n+1
	dst []int32 // m
	lnk []uint8 // m, index into LinkNames
	LinkNames []string

	// reverse adjacency: needed for in-degree, undirected views and articulation points
	roff []int32 // n+1
	rdst []int32 // m

	declared []bool // n

	AsOf string
}

func (c *CSR) Nodes() int { return int(c.n) }
func (c *CSR) Edges() int { return int(c.m) }

// Key returns the interned key of a node without allocating a string copy where possible.
func (c *CSR) Key(id int32) NodeKey {
	return NodeKey{Type: c.TypeNames[c.keyTyp[id]], Key: string(c.slab[c.keyOff[id]:c.keyOff[id+1]])}
}
func (c *CSR) rawKey(id int32) []byte { return c.slab[c.keyOff[id]:c.keyOff[id+1]] }

// Lookup finds a node id by (type, key). Binary search over sorted keys — see the header for
// why no map is retained. Returns -1 when absent.
func (c *CSR) Lookup(k NodeKey) int32 {
	want := k.Type + "\x00" + k.Key
	lo, hi := int32(0), c.n
	for lo < hi {
		mid := (lo + hi) / 2
		if c.cmpKey(mid, want) < 0 {
			lo = mid + 1
		} else {
			hi = mid
		}
	}
	if lo < c.n && c.cmpKey(lo, want) == 0 {
		return lo
	}
	return -1
}

func (c *CSR) cmpKey(id int32, want string) int {
	return bytes.Compare(
		append(append([]byte(c.TypeNames[c.keyTyp[id]]), 0), c.rawKey(id)...),
		[]byte(want))
}

func (c *CSR) Declared(id int32) bool { return c.declared[id] }

// Out / In iterate adjacency without allocating.
func (c *CSR) Out(id int32) []int32 { return c.dst[c.off[id]:c.off[id+1]] }
func (c *CSR) In(id int32) []int32  { return c.rdst[c.roff[id]:c.roff[id+1]] }

func (c *CSR) OutLink(id int32, i int) string { return c.LinkNames[c.lnk[c.off[id]+int32(i)]] }

// Degree is total degree. O(1) per node, O(V) overall — and it is the BEST measured predictor
// of adversary-flagged artifacts (AUC 0.871), which is why it is the shipped signal.
func (c *CSR) Degree(id int32) int {
	return int((c.off[id+1] - c.off[id]) + (c.roff[id+1] - c.roff[id]))
}

// ── build ────────────────────────────────────────────────────────────────────

type csrBuilder struct {
	ids     map[string]int32 // TEMPORARY: dropped before the CSR is returned
	keys    []string         // type\x00key, parallel to ids
	edges   []csrEdge
	declared map[string]bool
	links   map[string]uint8
	linkArr []string
}

type csrEdge struct {
	u, v int32
	lnk  uint8
}

func newCSRBuilder() *csrBuilder {
	return &csrBuilder{ids: map[string]int32{}, declared: map[string]bool{}, links: map[string]uint8{}}
}

func (b *csrBuilder) id(k NodeKey) int32 {
	s := k.Type + "\x00" + k.Key
	if id, ok := b.ids[s]; ok {
		return id
	}
	id := int32(len(b.keys))
	b.ids[s] = id
	b.keys = append(b.keys, s)
	return id
}

func (b *csrBuilder) link(name string) uint8 {
	if i, ok := b.links[name]; ok {
		return i
	}
	i := uint8(len(b.linkArr))
	b.links[name] = i
	b.linkArr = append(b.linkArr, name)
	return i
}

func (b *csrBuilder) addEdge(from, to NodeKey, linkType string) {
	u, v := b.id(from), b.id(to)
	if u == v {
		return // self-edges are a data defect, reported by validate, not modelled
	}
	b.edges = append(b.edges, csrEdge{u, v, b.link(linkType)})
}

// finish assigns final ids in SORTED key order, which is what makes Lookup a binary search
// and lets the build-time map be dropped.
func (b *csrBuilder) finish() *CSR {
	order := make([]int32, len(b.keys))
	for i := range order {
		order[i] = int32(i)
	}
	sort.Slice(order, func(i, j int) bool { return b.keys[order[i]] < b.keys[order[j]] })
	remap := make([]int32, len(b.keys))
	for newID, oldID := range order {
		remap[oldID] = int32(newID)
	}

	n := int32(len(b.keys))
	c := &CSR{n: n, m: int32(len(b.edges)), LinkNames: b.linkArr}
	typIdx := map[string]uint8{}
	c.keyOff = make([]int32, n+1)
	c.keyTyp = make([]uint8, n)
	c.declared = make([]bool, n)
	for newID := int32(0); newID < n; newID++ {
		s := b.keys[order[newID]]
		z := bytes.IndexByte([]byte(s), 0)
		typ, key := s[:z], s[z+1:]
		ti, ok := typIdx[typ]
		if !ok {
			ti = uint8(len(c.TypeNames))
			typIdx[typ] = ti
			c.TypeNames = append(c.TypeNames, typ)
		}
		c.keyTyp[newID] = ti
		c.keyOff[newID] = int32(len(c.slab))
		c.slab = append(c.slab, key...)
		c.declared[newID] = b.declared[s]
	}
	c.keyOff[n] = int32(len(c.slab))

	// counting sort into forward and reverse CSR
	c.off, c.roff = make([]int32, n+2), make([]int32, n+2)
	for i := range b.edges {
		u, v := remap[b.edges[i].u], remap[b.edges[i].v]
		b.edges[i].u, b.edges[i].v = u, v
		c.off[u+1]++
		c.roff[v+1]++
	}
	for i := int32(1); i <= n; i++ {
		c.off[i] += c.off[i-1]
		c.roff[i] += c.roff[i-1]
	}
	c.dst = make([]int32, c.m)
	c.lnk = make([]uint8, c.m)
	c.rdst = make([]int32, c.m)
	fpos := append([]int32(nil), c.off[:n+1]...)
	rpos := append([]int32(nil), c.roff[:n+1]...)
	for _, e := range b.edges {
		c.dst[fpos[e.u]] = e.v
		c.lnk[fpos[e.u]] = e.lnk
		fpos[e.u]++
		c.rdst[rpos[e.v]] = e.u
		rpos[e.v]++
	}
	c.off = c.off[:n+1]
	c.roff = c.roff[:n+1]
	b.ids = nil // drop the build-time index: ~80 MB at 1M nodes
	return c
}

// BuildCSR streams the store straight into CSR, never materialising a gonum graph. That is
// the whole point: building the gonum projection first would pay the 3.1 GB it exists to
// avoid.
func BuildCSR(ctx context.Context, s *Store, reg *RegistryBundle, asOf string) (*CSR, error) {
	// Same ref probe as BuildGraph, for the same reason: a bad ref must be fa FAILING, not an
	// empty graph that every consumer misreads as "everything is new".
	if asOf != "" {
		if _, err := s.Int(ctx, asOfQuery("SELECT COUNT(*) FROM bc", asOf)); err != nil {
			return nil, fmt.Errorf("csr: ref %q does not resolve: %w", asOf, err)
		}
	}
	b := newCSRBuilder()
	universes := 0
	for typ, q := range declaringQueries {
		ids, err := s.Strings(ctx, asOfQuery(q, asOf))
		if err != nil {
			continue
		}
		universes++
		for _, id := range ids {
			if id == "" {
				continue
			}
			k := NodeKey{typ, id}
			b.id(k)
			b.declared[k.Type+"\x00"+k.Key] = true
		}
	}
	if universes == 0 {
		return nil, fmt.Errorf("csr: no artifact universe resolved — is this an imported store?")
	}
	for _, es := range edgeSpecs {
		pairs, err := s.Pairs(ctx, asOfQuery(es.q, asOf))
		if err != nil {
			continue
		}
		for _, pr := range pairs {
			if pr[0] == "" || pr[1] == "" {
				continue
			}
			b.addEdge(NodeKey{es.fromType, pr[0]}, NodeKey{es.toType, pr[1]}, es.linkType)
		}
	}
	rows, err := s.Query(ctx, asOfQuery("SELECT story_id, dep_id, kind FROM story_dep", asOf))
	if err == nil {
		defer rows.Close()
		for rows.Next() {
			var a, bb, kind string
			if rows.Scan(&a, &bb, &kind) != nil {
				continue
			}
			from, to := NodeKey{"story", a}, NodeKey{"story", bb}
			if kind == "blocks" { // normalise: X blocks Y == Y depends_on X
				from, to = to, from
			}
			b.addEdge(from, to, "depends_on")
		}
	}
	c := b.finish()
	c.AsOf = asOf
	return c, nil
}

// FromProjection exists ONLY so the CSR algorithms can be proved to agree with the gonum
// ones on the same graph. Production uses BuildCSR.
func csrFromProjection(p *Projection) *CSR {
	b := newCSRBuilder()
	for k := range p.ids {
		b.id(k)
		if p.declared[k] {
			b.declared[k.Type+"\x00"+k.Key] = true
		}
	}
	for _, ed := range projEdges(p) {
		b.addEdge(ed.from, ed.to, ed.link)
	}
	c := b.finish()
	c.AsOf = p.AsOf
	return c
}

type projEdge struct {
	from, to NodeKey
	link     string
}

// projEdges flattens the gonum multigraph's lines, so the CSR built from a Projection carries
// exactly the same parallel edges (a story->BC via behavioral_contracts AND traces_to must
// stay TWO edges, or the parity test would pass while hiding a collapse).
func projEdges(p *Projection) []projEdge {
	var out []projEdge
	for it := p.g.Edges(); it.Next(); {
		e := it.Edge().(multi.Edge)
		f, t := p.key[e.From().ID()], p.key[e.To().ID()]
		for li := e.Lines; li.Next(); {
			out = append(out, projEdge{f, t, p.meta[li.Line().ID()].LinkType})
		}
	}
	return out
}

// ── algorithms over CSR ──────────────────────────────────────────────────────

// Dangling: an edge whose head was never declared by an authoritative document.
func (c *CSR) Dangling() []NodeKey {
	var out []NodeKey
	for id := int32(0); id < c.n; id++ {
		if !c.declared[id] {
			out = append(out, c.Key(id))
		}
	}
	return out
}

// TarjanSCC over CSR, iterative. SCCs of size > 1 are dependency cycles.
func (c *CSR) SCC() [][]int32 {
	const unset = int32(-1)
	index := make([]int32, c.n)
	low := make([]int32, c.n)
	onStack := make([]bool, c.n)
	for i := range index {
		index[i] = unset
	}
	var stack []int32
	var out [][]int32
	next := int32(0)

	type frame struct {
		v int32
		i int
	}
	for root := int32(0); root < c.n; root++ {
		if index[root] != unset {
			continue
		}
		work := []frame{{root, 0}}
		index[root], low[root] = next, next
		next++
		stack = append(stack, root)
		onStack[root] = true
		for len(work) > 0 {
			f := &work[len(work)-1]
			adj := c.Out(f.v)
			if f.i < len(adj) {
				w := adj[f.i]
				f.i++
				if index[w] == unset {
					index[w], low[w] = next, next
					next++
					stack = append(stack, w)
					onStack[w] = true
					work = append(work, frame{w, 0})
				} else if onStack[w] && index[w] < low[f.v] {
					low[f.v] = index[w]
				}
				continue
			}
			v := f.v
			work = work[:len(work)-1]
			if len(work) > 0 {
				pv := work[len(work)-1].v
				if low[v] < low[pv] {
					low[pv] = low[v]
				}
			}
			if low[v] == index[v] {
				var comp []int32
				for {
					w := stack[len(stack)-1]
					stack = stack[:len(stack)-1]
					onStack[w] = false
					comp = append(comp, w)
					if w == v {
						break
					}
				}
				if len(comp) > 1 {
					out = append(out, comp)
				}
			}
		}
	}
	return out
}

// ArticulationPoints over CSR: Hopcroft-Tarjan on the UNDIRECTED view (forward + reverse
// adjacency), iterative so a 1M-node graph cannot blow the stack. Verified against the gonum
// path by TestCSRArticulationParity and against hand-worked answers by the shared cases.
func (c *CSR) ArticulationPoints() []int32 {
	const none = int32(-1)
	disc := make([]int32, c.n)
	low := make([]int32, c.n)
	parent := make([]int32, c.n)
	isCut := make([]bool, c.n)
	visited := make([]bool, c.n)
	for i := range parent {
		parent[i] = none
	}
	timer := int32(0)

	// undirected neighbours without materialising a new graph
	nbr := func(v int32, i int) int32 {
		o := c.Out(v)
		if i < len(o) {
			return o[i]
		}
		return c.In(v)[i-len(o)]
	}
	deg := func(v int32) int { return len(c.Out(v)) + len(c.In(v)) }

	type frame struct {
		v        int32
		i        int
		children int
	}
	for root := int32(0); root < c.n; root++ {
		if visited[root] {
			continue
		}
		visited[root] = true
		timer++
		disc[root], low[root] = timer, timer
		work := []frame{{v: root}}
		for len(work) > 0 {
			f := &work[len(work)-1]
			if f.i < deg(f.v) {
				w := nbr(f.v, f.i)
				f.i++
				if !visited[w] {
					f.children++
					parent[w] = f.v
					visited[w] = true
					timer++
					disc[w], low[w] = timer, timer
					work = append(work, frame{v: w})
				} else if w != parent[f.v] && disc[w] < low[f.v] {
					low[f.v] = disc[w]
				}
				continue
			}
			v, kids := f.v, f.children
			work = work[:len(work)-1]
			if pv := parent[v]; pv != none {
				if low[v] < low[pv] {
					low[pv] = low[v]
				}
				if parent[pv] != none && low[v] >= disc[pv] {
					isCut[pv] = true
				}
			}
			if parent[v] == none && kids > 1 {
				isCut[v] = true
			}
		}
	}
	var out []int32
	for id := int32(0); id < c.n; id++ {
		if isCut[id] {
			out = append(out, id)
		}
	}
	return out
}

// Waves over CSR: longest-path layering restricted to story->story depends_on edges, the same
// semantics as the gonum path. Returns nil waves plus the cycles when no schedule exists.
func (c *CSR) Waves() *WaveResult {
	res := &WaveResult{}
	storyTyp := int32(-1)
	for i, t := range c.TypeNames {
		if t == "story" {
			storyTyp = int32(i)
		}
	}
	if storyTyp < 0 {
		return res
	}
	isStory := func(id int32) bool { return int32(c.keyTyp[id]) == storyTyp }
	depIdx := -1
	for i, l := range c.LinkNames {
		if l == "depends_on" {
			depIdx = i
		}
	}

	indeg := map[int32]int{}
	rev := map[int32][]int32{}
	for v := int32(0); v < c.n; v++ {
		if !isStory(v) {
			continue
		}
		if _, ok := indeg[v]; !ok {
			indeg[v] = 0
		}
		o := c.Out(v)
		for i, w := range o {
			if !isStory(w) || depIdx < 0 || int(c.lnk[c.off[v]+int32(i)]) != depIdx {
				continue
			}
			indeg[v]++
			rev[w] = append(rev[w], v)
		}
	}
	for _, comp := range c.SCC() {
		all := true
		var names []string
		for _, id := range comp {
			if !isStory(id) {
				all = false
			}
			names = append(names, c.Key(id).String())
		}
		if all {
			sort.Strings(names)
			res.Cycles = append(res.Cycles, names)
		}
	}
	if len(res.Cycles) > 0 {
		return res
	}
	layer := map[int32]int{}
	var ready []int32
	for v, d := range indeg {
		if d == 0 {
			ready = append(ready, v)
			layer[v] = 0
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
	for v := range indeg {
		l := layer[v]
		byLayer[l] = append(byLayer[l], c.Key(v).Key)
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

// MemoryEstimate reports the CSR's own footprint. Reported rather than estimated in a comment,
// because the claim "~47 MB at 1M nodes" is the reason this file exists.
func (c *CSR) MemoryEstimate() int64 {
	return int64(len(c.slab)) +
		int64(len(c.keyOff))*4 + int64(len(c.keyTyp)) +
		int64(len(c.off))*4 + int64(len(c.dst))*4 + int64(len(c.lnk)) +
		int64(len(c.roff))*4 + int64(len(c.rdst))*4 +
		int64(len(c.declared))
}
