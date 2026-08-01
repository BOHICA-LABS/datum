package main

// The knowledge-graph PROJECTION.
//
// The Dolt store is the knowledge graph — typed nodes, typed edges, closure by recursive
// CTE. What SQL cannot do is graph ALGORITHMS: centrality, articulation points, community
// detection, proper cycle enumeration. This file projects the store's edge rows into
// gonum's graph types so those become available, and does nothing else.
//
// THE PROJECTION CONTRACT, which is what keeps this an asset rather than a second truth:
//   1. Rebuilt from a store query on every use. Never persisted, never hand-maintained.
//   2. No setters. Nothing mutates a Projection after Build returns.
//   3. Every OUTPUT is `authority: derived` and goes through shadow -> proven -> retired
//      like any other derived artifact.
// Break (1) and we have built exactly the second replica #671 warns about — an objection
// that does not apply to `fa` today only because the store is rebuilt from files per run.
//
// gonum, not petgraph-equivalent-of-the-week, for one hard reason: it is PURE GO. `fa`
// already requires CGO plus `-tags gms_pure_go`; a C-linked graph library would fight that
// build. gonum adds no build constraints.

import (
	"context"
	"fmt"
	"sort"
	"strings"

	"gonum.org/v1/gonum/graph"
	"gonum.org/v1/gonum/graph/multi"
	"gonum.org/v1/gonum/graph/simple"
)

// NodeKey is identity, and it comes from the REGISTRY's declared `key:` per type — which is
// why the registry had to exist before this could. Path is never identity (measured: 1,852
// BC renames, 0 deletes).
type NodeKey struct {
	Type string
	Key  string
}

func (n NodeKey) String() string { return n.Type + ":" + n.Key }

// EdgeMeta is what the store knows about a reference that a bare (u,v) pair loses.
type EdgeMeta struct {
	LinkType  string // a declared link_types name
	PinPolicy string // floating | pinned | as_of — from the registry
	FromProse bool   // frontmatter today; prose once story 12 lands
}

type Projection struct {
	// multi, NOT simple. simple.DirectedGraph permits ONE edge per (u,v) pair, and this
	// graph genuinely has parallel edges: a story points at a BC via behavioral_contracts
	// AND via traces_to, with different pin policies. simple would silently collapse them
	// and understate coupling — the quiet-data-loss class this project keeps catching.
	g   *multi.DirectedGraph
	ids map[NodeKey]int64
	key map[int64]NodeKey
	// declared separates an authoritative node universe from a merely-referenced id.
	// Node universes come from authoritative declaring documents only; otherwise every
	// reference resolves trivially and an integrity check proves nothing. In graph terms a
	// DANGLING REFERENCE is an edge whose head is not declared, which is how the
	// projection reproduces that finding class for free.
	declared map[NodeKey]bool
	meta     map[int64]EdgeMeta // keyed by multi line ID
	AsOf     string
}

func newProjection() *Projection {
	return &Projection{
		g: multi.NewDirectedGraph(), ids: map[NodeKey]int64{},
		key: map[int64]NodeKey{}, declared: map[NodeKey]bool{}, meta: map[int64]EdgeMeta{},
	}
}

// node returns the gonum id for a key, creating the node if new. gonum nodes are bare
// int64s, so a bimap is mandatory rather than a convenience.
func (p *Projection) node(k NodeKey) int64 {
	if id, ok := p.ids[k]; ok {
		return id
	}
	n := p.g.NewNode()
	p.g.AddNode(n)
	p.ids[k], p.key[n.ID()] = n.ID(), k
	return n.ID()
}

func (p *Projection) addEdge(from, to NodeKey, m EdgeMeta) {
	u, v := p.node(from), p.node(to)
	if u == v {
		return // a self-edge is a data defect, reported by validate, not modelled here
	}
	l := p.g.NewLine(simple.Node(u), simple.Node(v))
	p.g.SetLine(l)
	p.meta[l.ID()] = m
}

func (p *Projection) Nodes() int { return p.g.Nodes().Len() }
func (p *Projection) Edges() int {
	n := 0
	for it := p.g.Edges(); it.Next(); {
		n += it.Edge().(multi.Edge).Lines.Len()
	}
	return n
}
func (p *Projection) Key(id int64) NodeKey { return p.key[id] }
func (p *Projection) Declared(k NodeKey) bool { return p.declared[k] }

// Dangling lists edges whose head was never declared by an authoritative document.
func (p *Projection) Dangling() []NodeKey {
	var out []NodeKey
	for k := range p.ids {
		if !p.declared[k] {
			out = append(out, k)
		}
	}
	sort.Slice(out, func(i, j int) bool { return out[i].String() < out[j].String() })
	return out
}

// Degrees is total degree per node. O(E) and effectively free — included because if it
// predicts the adversary's findings as well as betweenness does, the entire O(V*E) problem
// is moot. Measuring the alternative before optimising the lever.
func (p *Projection) Degrees() map[NodeKey]int {
	out := make(map[NodeKey]int, len(p.ids))
	sg := p.Simple()
	for k, id := range p.ids {
		n := 0
		for it := sg.From(id); it.Next(); {
			n++
		}
		for it := sg.To(id); it.Next(); {
			n++
		}
		out[k] = n
	}
	return out
}

func sortNodeKeys(k []NodeKey) {
	sort.Slice(k, func(i, j int) bool { return k[i].String() < k[j].String() })
}

// Simple returns a COLLAPSED single-edge view. Most centrality algorithms require it.
// The collapse is lossy and named as such: parallel link types become one edge.
func (p *Projection) Simple() *simple.DirectedGraph {
	s := simple.NewDirectedGraph()
	for it := p.g.Nodes(); it.Next(); {
		s.AddNode(simple.Node(it.Node().ID()))
	}
	for it := p.g.Edges(); it.Next(); {
		e := it.Edge()
		s.SetEdge(simple.Edge{F: simple.Node(e.From().ID()), T: simple.Node(e.To().ID())})
	}
	return s
}

// Undirected returns an undirected view, required by BiconnectedComponents (articulation
// points). gonum's graph.Undirect wraps a directed graph without copying.
func (p *Projection) Undirected() graph.Undirected {
	return graph.Undirect{G: p.Simple()}
}

// ── building it from the store ────────────────────────────────────────────────

// edgeSpec declares one SQL query that yields one link type. Adding an edge kind is adding
// a row here, and the link_type must be declared in the registry.
type edgeSpec struct {
	q                  string
	fromType, toType   string
	linkType           string
}

var edgeSpecs = []edgeSpec{
	{"SELECT bc_id, ss_id FROM bc", "behavioral-contract", "subsystem", "subsystems"},
	{"SELECT bc_id, capability FROM bc WHERE capability IS NOT NULL AND capability <> ''",
		"behavioral-contract", "capability", "capability"},
	{"SELECT bc_id, vp_id FROM bc_trace", "behavioral-contract", "verification-property", "verified_by"},
	{"SELECT vp_id, bc_id FROM vp_bc", "verification-property", "behavioral-contract", "behavioral_contracts"},
	{"SELECT vp_id, di_id FROM vp_di", "verification-property", "domain_invariant", "traces_to"},
	{"SELECT vp_id, nfr_id FROM vp_nfr", "verification-property", "nfr", "traces_to"},
	{"SELECT vp_id, ss_id FROM vp_subsystem", "verification-property", "subsystem", "subsystems"},
	{"SELECT story_id, bc_id FROM story_bc", "story", "behavioral-contract", "behavioral_contracts"},
	{"SELECT story_id, vp_id FROM story_vp", "story", "verification-property", "verification_properties"},
	{"SELECT story_id, fr_id FROM story_fr", "story", "fr", "prd_requirements"},
	{"SELECT story_id, ss_id FROM story_subsystem", "story", "subsystem", "subsystems"},
	{"SELECT story_id, epic_id FROM story WHERE epic_id IS NOT NULL AND epic_id <> ''",
		"story", "epic", "epic_id"},
	{"SELECT hs_id, bc_id FROM hs_bc", "holdout-scenario", "behavioral-contract", "behavioral_contracts"},
}

// declaringQueries are the AUTHORITATIVE universes. A node absent from these is referenced
// but never declared.
var declaringQueries = map[string]string{
	"behavioral-contract":   "SELECT bc_id FROM bc",
	"verification-property": "SELECT vp_id FROM vp",
	"story":                 "SELECT story_id FROM story",
	"subsystem":             "SELECT ss_id FROM subsystem",
	"capability":            "SELECT cap_id FROM capability",
	"domain_invariant":      "SELECT di_id FROM domain_invariant",
	"nfr":                   "SELECT nfr_id FROM nfr",
	"fr":                    "SELECT fr_id FROM fr",
	"adr":                   "SELECT adr_id FROM adr",
	"epic":                  "SELECT epic_id FROM epic",
	"holdout-scenario":      "SELECT hs_id FROM holdout_scenario",
}

// BuildGraph projects the store into a graph. asOf is a Dolt ref; empty means the working
// set. Registry-aware: pin_policy per edge comes from the registry, so an edge's version
// semantics travel with it instead of being re-derived by every consumer.
func BuildGraph(ctx context.Context, s *Store, reg *RegistryBundle, asOf string) (*Projection, error) {
	p := newProjection()
	p.AsOf = asOf

	// PROBE THE REF FIRST. Every query below tolerates a missing table, because phase 1
	// does not populate every universe — but that tolerance turned a BAD REF into an EMPTY
	// projection, which `graph diff` then reported as "+2,421 nodes added". A silent empty
	// graph is worse than an error: it is a confident, wrong answer. So a ref that does not
	// resolve is fa FAILING (exit 2), not a graph with nothing in it.
	if asOf != "" {
		if _, err := s.Int(ctx, asOfQuery("SELECT COUNT(*) FROM bc", asOf)); err != nil {
			return nil, fmt.Errorf("graph: ref %q does not resolve: %w", asOf, err)
		}
	}
	declaredOK := 0
	for typ, q := range declaringQueries {
		ids, err := s.Strings(ctx, asOfQuery(q, asOf))
		if err != nil {
			// A missing table is not a graph defect: phase 1 does not populate every
			// universe. Skip it rather than fail the whole projection.
			continue
		}
		declaredOK++
		for _, id := range ids {
			if id == "" {
				continue
			}
			k := NodeKey{typ, id}
			p.node(k)
			p.declared[k] = true
		}
	}

	for _, es := range edgeSpecs {
		pairs, err := s.Pairs(ctx, asOfQuery(es.q, asOf))
		if err != nil {
			continue
		}
		pin := "as_of"
		if reg != nil {
			pin = reg.PinPolicyFor(es.linkType)
		}
		for _, pr := range pairs {
			if pr[0] == "" || pr[1] == "" {
				continue
			}
			p.addEdge(NodeKey{es.fromType, pr[0]}, NodeKey{es.toType, pr[1]},
				EdgeMeta{LinkType: es.linkType, PinPolicy: pin})
		}
	}

	// If NOTHING resolved, the store is not a corpus store — say so rather than hand back an
	// empty graph that every downstream consumer will misread.
	if declaredOK == 0 {
		return nil, fmt.Errorf("graph: no artifact universe resolved — is this an imported store?")
	}

	// story_dep carries its direction in `kind`, and the registry declares depends_on and
	// blocks as a symmetric pair: store ONE direction, derive the other. Both are loaded
	// here as depends_on so the graph has a single consistent direction — which is also the
	// one-line fix for the 58 `direction` findings.
	rows, err := s.Query(ctx, asOfQuery("SELECT story_id, dep_id, kind FROM story_dep", asOf))
	if err == nil {
		defer rows.Close()
		for rows.Next() {
			var a, b, kind string
			if rows.Scan(&a, &b, &kind) != nil {
				continue
			}
			from, to := NodeKey{"story", a}, NodeKey{"story", b}
			if kind == "blocks" { // normalise: X blocks Y  ==  Y depends_on X
				from, to = to, from
			}
			pin := "as_of"
			if reg != nil {
				pin = reg.PinPolicyFor("depends_on")
			}
			p.addEdge(from, to, EdgeMeta{LinkType: "depends_on", PinPolicy: pin})
		}
	}
	return p, nil
}

func asOfQuery(q, asOf string) string {
	if asOf == "" {
		return q
	}
	// "SELECT cols FROM tbl [rest]" -> "SELECT cols FROM tbl AS OF 'ref' [rest]"
	up := strings.ToUpper(q)
	i := strings.Index(up, " FROM ")
	if i < 0 {
		return q
	}
	rest := q[i+6:]
	tbl := rest
	if j := strings.IndexAny(rest, " \n"); j >= 0 {
		tbl = rest[:j]
		rest = rest[j:]
	} else {
		rest = ""
	}
	return q[:i+6] + tbl + fmt.Sprintf(" AS OF '%s'", asOf) + rest
}

// ── graph diff: the thing a rehydrate-per-invocation graph structurally cannot do ──

type GraphDiff struct {
	From, To                 string
	NodesAdded, NodesRemoved []NodeKey
	EdgesAdded, EdgesRemoved []string // "from -[link]-> to"
	NodesBefore, NodesAfter  int
	EdgesBefore, EdgesAfter  int
}

func edgeStrings(p *Projection) map[string]bool {
	out := map[string]bool{}
	for it := p.g.Edges(); it.Next(); {
		e := it.Edge().(multi.Edge)
		f, t := p.key[e.From().ID()], p.key[e.To().ID()]
		for li := e.Lines; li.Next(); {
			m := p.meta[li.Line().ID()]
			out[fmt.Sprintf("%s -[%s]-> %s", f, m.LinkType, t)] = true
		}
	}
	return out
}

// DiffGraphs compares two projections. Because the store keeps history, these can be the
// SAME corpus at two commits — which is the question the adversary answers by hand
// ("how did the reference graph change across this wave") and the one an in-memory graph
// rebuilt per invocation can never answer, since it only ever sees HEAD.
func DiffGraphs(a, b *Projection) *GraphDiff {
	d := &GraphDiff{From: a.AsOf, To: b.AsOf,
		NodesBefore: a.Nodes(), NodesAfter: b.Nodes(),
		EdgesBefore: a.Edges(), EdgesAfter: b.Edges()}
	for k := range b.ids {
		if _, ok := a.ids[k]; !ok {
			d.NodesAdded = append(d.NodesAdded, k)
		}
	}
	for k := range a.ids {
		if _, ok := b.ids[k]; !ok {
			d.NodesRemoved = append(d.NodesRemoved, k)
		}
	}
	ea, eb := edgeStrings(a), edgeStrings(b)
	for e := range eb {
		if !ea[e] {
			d.EdgesAdded = append(d.EdgesAdded, e)
		}
	}
	for e := range ea {
		if !eb[e] {
			d.EdgesRemoved = append(d.EdgesRemoved, e)
		}
	}
	sortKeys := func(s []NodeKey) { sort.Slice(s, func(i, j int) bool { return s[i].String() < s[j].String() }) }
	sortKeys(d.NodesAdded)
	sortKeys(d.NodesRemoved)
	sort.Strings(d.EdgesAdded)
	sort.Strings(d.EdgesRemoved)
	return d
}
