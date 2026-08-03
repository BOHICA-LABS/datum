package main

// graphsql_probe_test.go — CAN DOLT BE THE GRAPH DATABASE?
//
// The design already stores a triple/graph model (artifact_field is
// subject-predicate-object; artifact_ref is edges). The open question is whether the
// GRAPH QUERY workload can be served by the same engine, or whether it genuinely needs
// a separate graph database.
//
// `fa graph` describes itself as "algorithms SQL cannot do", which is true for
// centrality and articulation points. But that phrase was never tested against the
// TRAVERSAL workload -- reachability, transitive closure, topological order, cycle
// detection -- which standard SQL does with WITH RECURSIVE.
//
// So the decisive fact is whether GMS (the pure-Go engine, no `dolt` binary) supports
// recursive CTEs at all. GMS feature support is a KNOWN variable here: the same
// question had to be asked about CREATE VIEW with MAX(CASE WHEN ...) and the answer
// happened to be yes. Assuming either way would be exactly the error this repo forbids.
//
//   CGO_ENABLED=1 go test -tags gms_pure_go -run TestGraphInSQL -v -timeout 20m .

import (
	"context"
	"fmt"
	"testing"
	"time"
)

func TestGraphInSQL(t *testing.T) {
	ctx := context.Background()
	st, err := Open(ctx, t.TempDir(), ZoneOpen, true)
	if err != nil {
		t.Fatalf("open: %v", err)
	}
	defer st.Close()

	if _, err := st.Exec(ctx, `CREATE TABLE edge (
	  src VARCHAR(64) NOT NULL, dst VARCHAR(64) NOT NULL,
	  kind VARCHAR(32) NOT NULL DEFAULT 'dep',
	  PRIMARY KEY (src, dst, kind), KEY idx_dst (dst))`); err != nil {
		t.Fatalf("ddl: %v", err)
	}

	// a chain plus a diamond plus a CYCLE -- the cycle matters, because an
	// unguarded recursive CTE over a cyclic graph runs forever.
	edges := [][2]string{
		{"a", "b"}, {"b", "c"}, {"c", "d"}, {"d", "e"},
		{"b", "x"}, {"x", "d"},
		{"e", "f"}, {"f", "g"},
		{"p", "q"}, {"q", "r"}, {"r", "p"}, // 3-cycle
	}
	tx, _ := st.Begin(ctx)
	for _, e := range edges {
		if _, err := tx.ExecContext(ctx, "INSERT INTO edge (src,dst) VALUES (?,?)", e[0], e[1]); err != nil {
			t.Fatalf("insert: %v", err)
		}
	}
	if err := tx.Commit(); err != nil {
		t.Fatalf("commit: %v", err)
	}

	// ---- Q1: does GMS support WITH RECURSIVE AT ALL? ------------------------
	t.Log("")
	t.Log("=== Q1 — WITH RECURSIVE support in GMS (pure Go, no dolt binary) ===")
	reach := `WITH RECURSIVE r (node, depth) AS (
	    SELECT 'a', 0
	  UNION
	    SELECT e.dst, r.depth + 1 FROM edge e JOIN r ON e.src = r.node WHERE r.depth < 10
	)
	SELECT node, MIN(depth) AS d FROM r GROUP BY node ORDER BY d, node`
	rows, err := st.Query(ctx, reach)
	if err != nil {
		// FATAL, not a log-and-return. Recursive-CTE support is **P4**, a VETO property
		// of the engine property set (V-L / L1-0): traversal is a query, and an engine
		// that cannot express it is inadmissible. Logging and returning here would let
		// the suite report green while the decision's premise had silently failed —
		// which is the "a green check that never ran is not evidence" class.
		t.Fatalf("⛔ P4 VIOLATED — GMS REFUSED a recursive CTE: %v\n"+
			"    Traversal cannot be served in SQL, so V-L's premise is false: either the\n"+
			"    in-process CSR engine becomes MANDATORY for traversal too, or the engine\n"+
			"    fails P4 and V-L must be reopened.", err)
	}
	got := map[string]int{}
	for rows.Next() {
		var n string
		var d int
		if err := rows.Scan(&n, &d); err != nil {
			t.Fatalf("scan: %v", err)
		}
		got[n] = d
	}
	rows.Close()
	t.Logf("✓ RECURSIVE CTE ACCEPTED. Reachability from 'a' with shortest depth:")
	for _, n := range []string{"a", "b", "c", "x", "d", "e", "f", "g"} {
		if d, ok := got[n]; ok {
			t.Logf("      %s at depth %d", n, d)
		} else {
			t.Errorf("      %s NOT REACHED (expected reachable)", n)
		}
	}
	// the diamond: d must be depth 3 via b->c->d AND b->x->d; MIN must be 3
	if got["d"] != 3 {
		t.Errorf("diamond shortest-path wrong: d at %d, want 3", got["d"])
	}
	if _, leaked := got["p"]; leaked {
		t.Errorf("reachability leaked into the disconnected cycle component")
	}

	// ---- Q2: is a CYCLE safe? ----------------------------------------------
	t.Log("")
	t.Log("=== Q2 — does a cycle terminate? (UNION dedupes; depth guard as belt-and-braces) ===")
	done := make(chan error, 1)
	go func() {
		var n int64
		e := st.conn.QueryRowContext(ctx, `WITH RECURSIVE r (node, depth) AS (
		    SELECT 'p', 0
		  UNION
		    SELECT e.dst, r.depth+1 FROM edge e JOIN r ON e.src=r.node WHERE r.depth < 50
		) SELECT COUNT(*) FROM r`).Scan(&n)
		if e == nil {
			t.Logf("✓ cycle terminated; %d distinct (node,depth) rows", n)
		}
		done <- e
	}()
	select {
	case e := <-done:
		if e != nil {
			t.Errorf("⛔ P4 — recursive CTE over a cycle FAILED: %v", e)
		}
	case <-time.After(30 * time.Second):
		t.Error("⛔ recursive CTE over a cycle DID NOT TERMINATE in 30s")
	}

	// ---- Q3: cycle DETECTION, which waves/dep-order needs ------------------
	t.Log("")
	t.Log("=== Q3 — cycle DETECTION in SQL (a node reachable from itself) ===")
	var cyc int64
	err = st.conn.QueryRowContext(ctx, `WITH RECURSIVE r (root, node, depth) AS (
	    SELECT src, dst, 1 FROM edge
	  UNION
	    SELECT r.root, e.dst, r.depth+1 FROM edge e JOIN r ON e.src=r.node WHERE r.depth < 20
	) SELECT COUNT(DISTINCT root) FROM r WHERE root = node`).Scan(&cyc)
	if err != nil {
		t.Errorf("⛔ P4 — cycle detection in SQL FAILED: %v; `waves` depends on it", err)
	} else {
		t.Logf("✓ nodes on a cycle: %d (expect 3 — p,q,r)", cyc)
		if cyc != 3 {
			t.Errorf("want 3 cyclic nodes, got %d", cyc)
		}
	}

	// ---- Q4: the real corpus graph, and SQL vs the CSR engine -------------
	//
	// A SUBTEST, so that a missing corpus skips ONLY this part. Q1-Q3 are the gate that
	// matters (they pin P4's recursive-CTE requirement on a synthetic graph) and must
	// never be skippable -- a check that did not run must not be readable as one that
	// passed.
	t.Run("real-corpus", func(t *testing.T) {
		graphSQLRealCorpus(t, ctx, st)
	})
}

func graphSQLRealCorpus(t *testing.T, ctx context.Context, st *Store) {
	corpus := expandHome("~/Dev/vsdd-factory/.factory")
	c, err := ScanCorpus(corpus)
	if err != nil {
		t.Skipf("corpus unavailable: %v", err)
	}
	if _, err := st.Exec(ctx, "DELETE FROM edge"); err != nil {
		t.Fatalf("clear: %v", err)
	}
	tx2, _ := st.Begin(ctx)
	n := 0
	seen := map[string]bool{}
	for _, e := range c.Edges {
		if len(e.Vals) < 2 {
			continue
		}
		k := e.Table + "\x00" + e.Vals[0] + "\x00" + e.Vals[1]
		if seen[k] {
			continue
		}
		seen[k] = true
		if _, err := tx2.ExecContext(ctx, "INSERT INTO edge (src,dst,kind) VALUES (?,?,?)",
			e.Vals[0], e.Vals[1], truncRunes(e.Table, 32)); err != nil {
			continue
		}
		n++
	}
	if err := tx2.Commit(); err != nil {
		t.Fatalf("commit real edges: %v", err)
	}
	t.Log("")
	t.Logf("=== Q4 — the REAL corpus graph: %d edges loaded ===", n)

	var hub string
	if err := st.conn.QueryRowContext(ctx,
		`SELECT src FROM (SELECT src, COUNT(*) c FROM edge GROUP BY src ORDER BY c DESC LIMIT 1) z`).
		Scan(&hub); err != nil {
		t.Fatalf("hub: %v", err)
	}

	for _, depth := range []int{1, 3, 6, 12} {
		q := fmt.Sprintf(`WITH RECURSIVE r (node, depth) AS (
		    SELECT ?, 0
		  UNION
		    SELECT e.dst, r.depth+1 FROM edge e JOIN r ON e.src=r.node WHERE r.depth < %d
		) SELECT COUNT(DISTINCT node) FROM r`, depth)
		s := time.Now()
		var reached int64
		if err := st.conn.QueryRowContext(ctx, q, hub).Scan(&reached); err != nil {
			t.Logf("  depth %-2d : FAILED %v", depth, err)
			continue
		}
		t.Logf("  depth %-2d : %5d nodes reached from %q in %v", depth, reached, hub, time.Since(s).Round(time.Millisecond))
	}

	// whole-graph transitive closure — the heaviest traversal shape
	s := time.Now()
	var pairs int64
	if err := st.conn.QueryRowContext(ctx, `WITH RECURSIVE r (root, node, depth) AS (
	    SELECT src, dst, 1 FROM edge
	  UNION
	    SELECT r.root, e.dst, r.depth+1 FROM edge e JOIN r ON e.src=r.node WHERE r.depth < 8
	) SELECT COUNT(*) FROM (SELECT DISTINCT root, node FROM r) z`).Scan(&pairs); err != nil {
		t.Logf("whole-graph closure FAILED: %v", err)
	} else {
		t.Logf("  whole-graph transitive closure (depth<=8): %d reachable pairs in %v",
			pairs, time.Since(s).Round(time.Millisecond))
	}
	t.Log("")
	t.Log("  compare: the in-process CSR engine computes ALL metrics in 102 ms at 0.1 MB")
}
