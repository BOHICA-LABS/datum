package main

// `datum graph` and `datum waves`.

import (
	"context"
	"flag"
	"fmt"
	"os"
	"time"
)

func cmdWaves(ctx context.Context, args []string) error {
	fs := flag.NewFlagSet("waves", flag.ExitOnError)
	db := fs.String("db", defaultDB(), "store root")
	asOf := fs.String("as-of", "", "project the graph as of a Dolt ref")
	_ = fs.Parse(args)

	// CSR, not the gonum projection: measured 96x less memory and 100x+ faster, and waves
	// needs none of what gonum provides.
	c, err := openCSR(ctx, *db, *asOf)
	if err != nil {
		return err
	}
	w := c.Waves()
	if len(w.Cycles) > 0 {
		// A schedule over a cyclic dependency graph does not exist. Emitting a plausible
		// one would be worse than failing.
		fmt.Printf("NO SCHEDULE — %d dependency cycle(s):\n", len(w.Cycles))
		for _, c := range w.Cycles {
			fmt.Printf("  %v\n", c)
		}
		return exitError{code: 1}
	}
	total := 0
	for _, wv := range w.Waves {
		total += len(wv.Stories)
	}
	fmt.Printf("wave schedule — %d stories in %d wave(s), derived from depends_on\n", total, len(w.Waves))
	for _, wv := range w.Waves {
		fmt.Printf("  wave %-2d (%3d): %v\n", wv.N, len(wv.Stories), truncList(wv.Stories, 8))
	}
	return nil
}

func cmdGraph(ctx context.Context, args []string) error {
	if len(args) == 0 {
		return fmt.Errorf("usage: datum graph <build|metrics|dot|diff> [flags]")
	}
	sub, rest := args[0], args[1:]
	switch sub {
	case "build":
		fs := flag.NewFlagSet("graph build", flag.ExitOnError)
		db := fs.String("db", defaultDB(), "store root")
		asOf := fs.String("as-of", "", "project as of a Dolt ref")
		_ = fs.Parse(rest)
		t0 := time.Now()
		c, err := openCSR(ctx, *db, *asOf)
		if err != nil {
			return err
		}
		fmt.Printf("projection  %d nodes · %d edges  (CSR, built in %s, %.1f MB)\n",
			c.Nodes(), c.Edges(), time.Since(t0).Round(time.Millisecond),
			float64(c.MemoryEstimate())/(1<<20))
		byType := map[string]int{}
		for id := int32(0); id < int32(c.Nodes()); id++ {
			byType[c.Key(id).Type]++
		}
		for _, t := range sortedKeys(byType) {
			fmt.Printf("   %-24s %5d\n", t, byType[t])
		}
		if d := c.Dangling(); len(d) > 0 {
			fmt.Printf("referenced but NEVER DECLARED: %d (a dangling reference IS an edge to an undeclared node)\n", len(d))
			for _, k := range d[:min(len(d), 8)] {
				fmt.Printf("   %s\n", k)
			}
		}
		return nil

	case "metrics":
		fs := flag.NewFlagSet("graph metrics", flag.ExitOnError)
		db := fs.String("db", defaultDB(), "store root")
		top := fs.Int("top", 15, "how many ranked entries to show")
		asOf := fs.String("as-of", "", "project as of a Dolt ref")
		betw := fs.Bool("betweenness", false, "include betweenness centrality (O(V*E): ~236ms at 2.4k nodes, ~52s at 24k)")
		betwMax := fs.Int("betweenness-max", defaultBetweennessMaxNodes, "refuse betweenness above this node count")
		seed := fs.Uint64("seed", 1, "Louvain seed (fixed so communities are reproducible)")
		_ = fs.Parse(rest)
		p, err := openProjection(ctx, *db, *asOf)
		if err != nil {
			return err
		}
		t0 := time.Now()
		m := p.ComputeMetrics(MetricsOpts{Top: *top, Betweenness: *betw,
			BetweennessMaxNodes: *betwMax, Seed: *seed})
		el := time.Since(t0)
		fmt.Printf("graph  %d nodes · %d edges   metrics computed in %s\n", m.Nodes, m.Edges, el.Round(time.Millisecond))
		fmt.Printf("\nDEGREE (O(E) — the best measured predictor of adversary-flagged artifacts, AUC 0.871)\n")
		for _, x := range m.Degree {
			fmt.Printf("  %12.0f  %s\n", x.Score, x.Key)
		}
		if m.BetweennessSkipped != "" {
			fmt.Printf("\nBETWEENNESS  skipped — %s\n", m.BetweennessSkipped)
		} else {
			fmt.Printf("\nBETWEENNESS (structurally central — NOT a claim of importance)\n")
			for _, x := range m.Betweenness {
				fmt.Printf("  %12.1f  %s\n", x.Score, x.Key)
			}
		}
		fmt.Printf("\nPAGERANK\n")
		for _, x := range m.PageRank {
			fmt.Printf("  %12.6f  %s\n", x.Score, x.Key)
		}
		fmt.Printf("\nARTICULATION POINTS (%d) — removing one disconnects the traceability graph\n", len(m.Articulation))
		for _, k := range m.Articulation[:min(len(m.Articulation), *top)] {
			fmt.Printf("  %s\n", k)
		}
		fmt.Printf("\nSTRONGLY CONNECTED COMPONENTS of size>1 (%d) — these are cycles\n", len(m.SCCs))
		for _, c := range m.SCCs[:min(len(m.SCCs), 8)] {
			fmt.Printf("  %d: %v\n", len(c), c[:min(len(c), 6)])
		}
		fmt.Printf("\nCOMMUNITIES (Louvain, seeded) %d of size>1 — mismatch vs declared subsystem is the signal\n", len(m.Communities))
		for _, c := range m.Communities[:min(len(m.Communities), 10)] {
			fmt.Printf("  size %4d  dominant subsystem %-8s\n", c.Size, orDash(c.DominantSubsystem))
		}
		return nil

	case "centrality":
		// Dumps EVERY node's scores so the "does centrality predict findings?" hypothesis
		// can be tested outside the binary. Degree is included because it is O(E) and would
		// make the whole betweenness problem moot if it predicts as well.
		fs := flag.NewFlagSet("graph centrality", flag.ExitOnError)
		db := fs.String("db", defaultDB(), "store root")
		betw := fs.Bool("betweenness", true, "include betweenness (expensive)")
		betwMax := fs.Int("betweenness-max", 1<<30, "node bound for betweenness")
		_ = fs.Parse(rest)
		p, err := openProjection(ctx, *db, "")
		if err != nil {
			return err
		}
		m := p.ComputeMetrics(MetricsOpts{Top: 0, Betweenness: *betw, BetweennessMaxNodes: *betwMax})
		bt := map[string]float64{}
		for _, x := range m.Betweenness {
			bt[x.Key.String()] = x.Score
		}
		pr := map[string]float64{}
		for _, x := range m.PageRank {
			pr[x.Key.String()] = x.Score
		}
		deg := p.Degrees()
		fmt.Println("node,type,betweenness,pagerank,degree")
		var keys []NodeKey
		for k := range p.ids {
			keys = append(keys, k)
		}
		sortNodeKeys(keys)
		for _, k := range keys {
			fmt.Printf("%s,%s,%g,%g,%d\n", k.Key, k.Type, bt[k.String()], pr[k.String()], deg[k])
		}
		return nil

	case "dot":
		fs := flag.NewFlagSet("graph dot", flag.ExitOnError)
		db := fs.String("db", defaultDB(), "store root")
		scope := fs.String("scope", "", "restrict to a node type or a single key")
		out := fs.String("out", "", "write here instead of stdout")
		_ = fs.Parse(rest)
		p, err := openProjection(ctx, *db, "")
		if err != nil {
			return err
		}
		w := os.Stdout
		if *out != "" {
			f, err := os.Create(*out)
			if err != nil {
				return err
			}
			defer f.Close()
			w = f
		}
		return p.WriteDOT(w, *scope)

	case "diff":
		fs := flag.NewFlagSet("graph diff", flag.ExitOnError)
		db := fs.String("db", defaultDB(), "store root")
		from := fs.String("from", "", "Dolt ref (required)")
		to := fs.String("to", "", "Dolt ref (default: working set)")
		_ = fs.Parse(rest)
		if *from == "" {
			return fmt.Errorf("--from is required")
		}
		a, err := openProjection(ctx, *db, *from)
		if err != nil {
			return err
		}
		b, err := openProjection(ctx, *db, *to)
		if err != nil {
			return err
		}
		d := DiffGraphs(a, b)
		fmt.Printf("graph diff  %s -> %s\n", orDash(d.From), orWorking(d.To))
		fmt.Printf("  nodes %d -> %d   (+%d / -%d)\n", d.NodesBefore, d.NodesAfter, len(d.NodesAdded), len(d.NodesRemoved))
		fmt.Printf("  edges %d -> %d   (+%d / -%d)\n", d.EdgesBefore, d.EdgesAfter, len(d.EdgesAdded), len(d.EdgesRemoved))
		for _, k := range d.NodesAdded[:min(len(d.NodesAdded), 10)] {
			fmt.Printf("  + %s\n", k)
		}
		for _, k := range d.NodesRemoved[:min(len(d.NodesRemoved), 10)] {
			fmt.Printf("  - %s\n", k)
		}
		for _, e := range d.EdgesAdded[:min(len(d.EdgesAdded), 10)] {
			fmt.Printf("  + %s\n", e)
		}
		for _, e := range d.EdgesRemoved[:min(len(d.EdgesRemoved), 10)] {
			fmt.Printf("  - %s\n", e)
		}
		return nil
	}
	return fmt.Errorf("unknown: datum graph %s", sub)
}

// openCSR is the default engine. openProjection is retained for the gonum-only algorithms
// (Louvain, and betweenness when explicitly requested).
func openCSR(ctx context.Context, db, asOf string) (*CSR, error) {
	s, err := Open(ctx, db, ZoneOpen, false)
	if err != nil {
		return nil, err
	}
	defer s.Close()
	reg, err := LoadRegistry("")
	if err != nil {
		return nil, err
	}
	return BuildCSR(ctx, s, reg, asOf)
}

func openProjection(ctx context.Context, db, asOf string) (*Projection, error) {
	s, err := Open(ctx, db, ZoneOpen, false)
	if err != nil {
		return nil, err
	}
	defer s.Close()
	reg, err := LoadRegistry("")
	if err != nil {
		return nil, err
	}
	return BuildGraph(ctx, s, reg, asOf)
}

func truncList(s []string, n int) []string {
	if len(s) <= n {
		return s
	}
	return append(s[:n:n], "…")
}
func orDash(s string) string {
	if s == "" {
		return "—"
	}
	return s
}
func orWorking(s string) string {
	if s == "" {
		return "working set"
	}
	return s
}
func sortedKeys(m map[string]int) []string {
	out := make([]string, 0, len(m))
	for k := range m {
		out = append(out, k)
	}
	for i := 0; i < len(out); i++ {
		for j := i + 1; j < len(out); j++ {
			if out[j] < out[i] {
				out[i], out[j] = out[j], out[i]
			}
		}
	}
	return out
}
