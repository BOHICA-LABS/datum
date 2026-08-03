// bench — embedded dolthub/driver/v2 harness for the datum spike.
//
// Measures the EMBEDDED path so it can be compared against the `dolt sql` CLI
// path that every other timing in this spike used (141 ms spawn floor).
//
// Every mode prints ONE json object on stdout. Timings measured in-process are
// labelled *_ms; the caller (poc/test_embedded.py) measures wall clock for the
// whole invocation, which is the number that matters for a CLI-shaped tool.
//
// Usage: bench <mode> <dataDir> <database> [args...]
package main

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"net/url"
	"os"
	"sort"
	"strconv"
	"strings"
	"time"

	doltembed "github.com/dolthub/driver/v2"
)

func ms(d time.Duration) float64 { return float64(d.Microseconds()) / 1000.0 }

func emit(m map[string]any) {
	b, _ := json.Marshal(m)
	fmt.Println(string(b))
}

func die(stage string, err error) {
	emit(map[string]any{"ok": false, "stage": stage, "err": err.Error()})
	os.Exit(1)
}

// open mirrors beads' internal/storage/embeddeddolt/open.go, then PINS one
// connection (MaxOpenConns(1)) so `USE <db>` is guaranteed to apply to every
// later statement. Returns per-phase timings.
func open(ctx context.Context, dir, database string) (*sql.DB, *sql.Conn, func(), map[string]float64, error) {
	tim := map[string]float64{}
	v := url.Values{}
	v.Set(doltembed.CommitNameParam, "bench")
	v.Set(doltembed.CommitEmailParam, "bench@local")
	v.Set(doltembed.MultiStatementsParam, "true")
	dsn := "file://" + dir + "?" + v.Encode()

	t0 := time.Now()
	cfg, err := doltembed.ParseDSN(dsn)
	if err != nil {
		return nil, nil, nil, tim, fmt.Errorf("parse dsn: %w", err)
	}
	connector, err := doltembed.NewConnector(cfg)
	if err != nil {
		return nil, nil, nil, tim, fmt.Errorf("new connector: %w", err)
	}
	tim["connector_ms"] = ms(time.Since(t0))

	db := sql.OpenDB(connector)
	db.SetMaxOpenConns(1)
	db.SetMaxIdleConns(1)
	db.SetConnMaxIdleTime(0)
	db.SetConnMaxLifetime(0)

	cleanup := func() {
		dbErr := db.Close()
		cErr := connector.Close()
		_ = dbErr
		_ = cErr
	}

	t0 = time.Now()
	if err := db.PingContext(ctx); err != nil {
		cleanup()
		return nil, nil, nil, tim, fmt.Errorf("ping: %w", err)
	}
	tim["ping_ms"] = ms(time.Since(t0))

	t0 = time.Now()
	conn, err := db.Conn(ctx)
	if err != nil {
		cleanup()
		return nil, nil, nil, tim, fmt.Errorf("pin conn: %w", err)
	}
	if database != "" {
		if _, err := conn.ExecContext(ctx, "USE `"+database+"`"); err != nil {
			conn.Close()
			cleanup()
			return nil, nil, nil, tim, fmt.Errorf("use %s: %w", database, err)
		}
	}
	tim["use_ms"] = ms(time.Since(t0))

	full := func() {
		conn.Close()
		cleanup()
	}
	return db, conn, full, tim, nil
}

func scalarStr(ctx context.Context, c *sql.Conn, q string, args ...any) (string, error) {
	var s sql.NullString
	err := c.QueryRowContext(ctx, q, args...).Scan(&s)
	return s.String, err
}

// ---------------------------------------------------------------- corpus rec

type rec struct {
	T      string `json:"t"`
	ID     string `json:"id"`
	ID2    string `json:"id2"`
	SS     string `json:"ss"`
	Title  string `json:"title"`
	Body   string `json:"body"`
	Cap    string `json:"cap"`
	Ver    string `json:"ver"`
	Status string `json:"status"`
	Wave   *int   `json:"wave"`
	Prefix int    `json:"prefix"`
}

var stmts = map[string]string{
	"ss":    "INSERT IGNORE INTO subsystem (ss_id, bc_prefix, name) VALUES (?,?,?)",
	"vp":    "INSERT IGNORE INTO vp (vp_id, title, body, version) VALUES (?,?,?,?)",
	"bc":    "INSERT IGNORE INTO bc (bc_id, ss_id, title, body, capability, version) VALUES (?,?,?,?,?,?)",
	"story": "INSERT IGNORE INTO story (story_id, title, status, wave, body) VALUES (?,?,?,?,?)",
	"trace": "INSERT IGNORE INTO bc_trace (bc_id, vp_id) VALUES (?,?)",
	"sbc":   "INSERT IGNORE INTO story_bc (story_id, bc_id) VALUES (?,?)",
}

func argsFor(r rec) []any {
	switch r.T {
	case "ss":
		return []any{r.ID, r.Prefix, r.Title}
	case "vp":
		return []any{r.ID, r.Title, r.Body, r.Ver}
	case "bc":
		var cap any
		if r.Cap != "" {
			cap = r.Cap
		}
		return []any{r.ID, r.SS, r.Title, r.Body, cap, r.Ver}
	case "story":
		var w any
		if r.Wave != nil {
			w = *r.Wave
		}
		return []any{r.ID, r.Title, r.Status, w, r.Body}
	case "trace", "sbc":
		return []any{r.ID, r.ID2}
	}
	return nil
}

func readJSONL(path string) ([]rec, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer f.Close()
	dec := json.NewDecoder(f)
	var out []rec
	for {
		var r rec
		if err := dec.Decode(&r); err != nil {
			if errors.Is(err, os.ErrClosed) || err.Error() == "EOF" {
				break
			}
			return out, nil // treat any decode tail as end
		}
		out = append(out, r)
	}
	return out, nil
}

// ---------------------------------------------------------------- queries

const qJoin = `SELECT COUNT(*) FROM (
  SELECT s.story_id, COUNT(DISTINCT t.vp_id) v
  FROM story s
  JOIN story_bc sb ON sb.story_id = s.story_id
  JOIN bc b ON b.bc_id = sb.bc_id
  LEFT JOIN bc_trace t ON t.bc_id = b.bc_id
  GROUP BY s.story_id) x`

func stat(xs []float64) (min, med, mean float64) {
	if len(xs) == 0 {
		return 0, 0, 0
	}
	s := append([]float64(nil), xs...)
	sort.Float64s(s)
	var sum float64
	for _, x := range s {
		sum += x
	}
	return s[0], s[len(s)/2], sum / float64(len(s))
}

// ---------------------------------------------------------------- main

func main() {
	if len(os.Args) < 4 {
		die("args", errors.New("usage: bench <mode> <dataDir> <database> [args...]"))
	}
	mode, dir, database := os.Args[1], os.Args[2], os.Args[3]
	rest := os.Args[4:]
	ctx := context.Background()
	procStart := time.Now()

	switch mode {

	// one-shot: the CLI-shaped cost. Compare with `dolt sql -q "SELECT 1"`.
	case "oneshot":
		_, conn, done, tim, err := open(ctx, dir, database)
		if err != nil {
			die("open", err)
		}
		t0 := time.Now()
		v, err := scalarStr(ctx, conn, "SELECT 1")
		if err != nil {
			die("query", err)
		}
		qms := ms(time.Since(t0))
		out := map[string]any{"ok": true, "mode": mode, "val": v, "query_ms": qms,
			"in_process_ms": ms(time.Since(procStart))}
		for k, x := range tim {
			out[k] = x
		}
		emit(out)
		done()

	// one-shot doing the real work of `datum count`: open + COUNT(*).
	case "oneshot-count":
		_, conn, done, tim, err := open(ctx, dir, database)
		if err != nil {
			die("open", err)
		}
		t0 := time.Now()
		v, err := scalarStr(ctx, conn, "SELECT COUNT(*) FROM bc")
		if err != nil {
			die("query", err)
		}
		out := map[string]any{"ok": true, "mode": mode, "val": v,
			"query_ms": ms(time.Since(t0)), "in_process_ms": ms(time.Since(procStart))}
		for k, x := range tim {
			out[k] = x
		}
		emit(out)
		done()

	// warm: one handle, N iterations of each query kind.
	case "warm":
		n, _ := strconv.Atoi(rest[0])
		_, conn, done, tim, err := open(ctx, dir, database)
		if err != nil {
			die("open", err)
		}
		defer done()
		pk, err := scalarStr(ctx, conn, "SELECT bc_id FROM bc ORDER BY bc_id LIMIT 1")
		if err != nil {
			die("pick-pk", err)
		}
		kinds := []struct {
			name, q string
			args    []any
		}{
			{"count", "SELECT COUNT(*) FROM bc", nil},
			{"pk", "SELECT title FROM bc WHERE bc_id = ?", []any{pk}},
			{"join3", qJoin, nil},
			{"group", "SELECT ss_id, COUNT(*) FROM bc GROUP BY ss_id ORDER BY ss_id", nil},
		}
		out := map[string]any{"ok": true, "mode": mode, "n": n, "pk": pk,
			"open_total_ms": tim["connector_ms"] + tim["ping_ms"] + tim["use_ms"]}
		for k, x := range tim {
			out[k] = x
		}
		for _, kd := range kinds {
			var xs []float64
			for i := 0; i < n; i++ {
				t0 := time.Now()
				if kd.name == "group" {
					rows, err := conn.QueryContext(ctx, kd.q)
					if err != nil {
						die("q-"+kd.name, err)
					}
					for rows.Next() {
					}
					rows.Close()
				} else {
					if _, err := scalarStr(ctx, conn, kd.q, kd.args...); err != nil {
						die("q-"+kd.name, err)
					}
				}
				xs = append(xs, ms(time.Since(t0)))
			}
			mn, md, mean := stat(xs)
			out[kd.name+"_min_ms"] = mn
			out[kd.name+"_med_ms"] = md
			out[kd.name+"_mean_ms"] = mean
		}
		emit(out)

	// writes: N single-row writes. mode = autocommit | tx | prepared
	case "writes":
		n, _ := strconv.Atoi(rest[0])
		wmode := rest[1]
		tag := rest[2]
		_, conn, done, _, err := open(ctx, dir, database)
		if err != nil {
			die("open", err)
		}
		defer done()
		if _, err := conn.ExecContext(ctx,
			"CREATE TABLE IF NOT EXISTS benchw (k VARCHAR(64) PRIMARY KEY, v INT NOT NULL)"); err != nil {
			die("ddl", err)
		}
		ins := "INSERT INTO benchw (k, v) VALUES (?, ?)"
		t0 := time.Now()
		switch wmode {
		case "autocommit":
			for i := 0; i < n; i++ {
				if _, err := conn.ExecContext(ctx, ins, fmt.Sprintf("%s-%d", tag, i), i); err != nil {
					die("insert", err)
				}
			}
		case "tx":
			tx, err := conn.BeginTx(ctx, nil)
			if err != nil {
				die("begin", err)
			}
			for i := 0; i < n; i++ {
				if _, err := tx.ExecContext(ctx, ins, fmt.Sprintf("%s-%d", tag, i), i); err != nil {
					die("insert", err)
				}
			}
			if err := tx.Commit(); err != nil {
				die("commit", err)
			}
		case "prepared":
			tx, err := conn.BeginTx(ctx, nil)
			if err != nil {
				die("begin", err)
			}
			st, err := tx.PrepareContext(ctx, ins)
			if err != nil {
				die("prepare", err)
			}
			for i := 0; i < n; i++ {
				if _, err := st.ExecContext(ctx, fmt.Sprintf("%s-%d", tag, i), i); err != nil {
					die("insert", err)
				}
			}
			st.Close()
			if err := tx.Commit(); err != nil {
				die("commit", err)
			}
		default:
			die("wmode", errors.New("unknown write mode "+wmode))
		}
		total := ms(time.Since(t0))
		emit(map[string]any{"ok": true, "mode": mode, "wmode": wmode, "n": n,
			"total_ms": total, "per_write_ms": total / float64(n),
			"in_process_ms": ms(time.Since(procStart))})

	// import: the whole corpus from jsonl. imode = per-stmt | tx | prepared
	case "import":
		jsonl := rest[0]
		imode := rest[1]
		recs, err := readJSONL(jsonl)
		if err != nil {
			die("jsonl", err)
		}
		_, conn, done, tim, err := open(ctx, dir, database)
		if err != nil {
			die("open", err)
		}
		defer done()
		t0 := time.Now()
		counts := map[string]int{}
		switch imode {
		case "per-stmt":
			for _, r := range recs {
				q, okq := stmts[r.T]
				if !okq {
					continue
				}
				if _, err := conn.ExecContext(ctx, q, argsFor(r)...); err != nil {
					die("insert-"+r.T+"-"+r.ID, err)
				}
				counts[r.T]++
			}
		case "tx", "prepared":
			tx, err := conn.BeginTx(ctx, nil)
			if err != nil {
				die("begin", err)
			}
			prep := map[string]*sql.Stmt{}
			for _, r := range recs {
				q, okq := stmts[r.T]
				if !okq {
					continue
				}
				if imode == "prepared" {
					st, have := prep[r.T]
					if !have {
						st, err = tx.PrepareContext(ctx, q)
						if err != nil {
							die("prepare-"+r.T, err)
						}
						prep[r.T] = st
					}
					if _, err := st.ExecContext(ctx, argsFor(r)...); err != nil {
						die("insert-"+r.T+"-"+r.ID, err)
					}
				} else {
					if _, err := tx.ExecContext(ctx, q, argsFor(r)...); err != nil {
						die("insert-"+r.T+"-"+r.ID, err)
					}
				}
				counts[r.T]++
			}
			for _, st := range prep {
				st.Close()
			}
			if err := tx.Commit(); err != nil {
				die("commit", err)
			}
		default:
			die("imode", errors.New("unknown import mode "+imode))
		}
		writeMS := ms(time.Since(t0))
		t0 = time.Now()
		if _, err := conn.ExecContext(ctx, "CALL DOLT_COMMIT('-Am', 'import: embedded')"); err != nil {
			die("dolt_commit", err)
		}
		commitMS := ms(time.Since(t0))
		out := map[string]any{"ok": true, "mode": mode, "imode": imode,
			"records": len(recs), "write_ms": writeMS, "dolt_commit_ms": commitMS,
			"in_process_ms": ms(time.Since(procStart))}
		for k, v := range counts {
			out["n_"+k] = v
		}
		for k, x := range tim {
			out[k] = x
		}
		emit(out)

	// atomicity: a multi-table burst that hits a constraint must leave NOTHING.
	case "atomicity":
		_, conn, done, _, err := open(ctx, dir, database)
		if err != nil {
			die("open", err)
		}
		defer done()
		tag := rest[0]
		tx, err := conn.BeginTx(ctx, nil)
		if err != nil {
			die("begin", err)
		}
		if _, err := tx.ExecContext(ctx,
			"INSERT INTO story (story_id, title, status, body) VALUES (?,?,?,?)",
			tag, "atomicity probe", "pending", "b"); err != nil {
			die("insert-story", err)
		}
		// bad edge: FK to a BC that does not exist
		_, badErr := tx.ExecContext(ctx,
			"INSERT INTO story_bc (story_id, bc_id) VALUES (?,?)", tag, "BC-9.99.999")
		rbErr := tx.Rollback()
		// read back on a FRESH connection (LESSONS §2: never read back on the
		// connection that wrote inside an open transaction)
		_, conn2, done2, _, err := open(ctx, dir, database)
		if err != nil {
			die("reopen", err)
		}
		defer done2()
		left, err := scalarStr(ctx, conn2, "SELECT COUNT(*) FROM story WHERE story_id = ?", tag)
		if err != nil {
			die("readback", err)
		}
		be := ""
		if badErr != nil {
			be = badErr.Error()
		}
		rb := ""
		if rbErr != nil {
			rb = rbErr.Error()
		}
		emit(map[string]any{"ok": true, "mode": mode, "bad_err": be, "rollback_err": rb,
			"rows_left": left})

	// procs: which dolt stored procedures / system tables work in-process?
	case "procs":
		_, conn, done, _, err := open(ctx, dir, database)
		if err != nil {
			die("open", err)
		}
		defer done()
		probes := []struct{ name, q string }{
			{"dolt_log", "SELECT COUNT(*) FROM dolt_log"},
			{"dolt_status", "SELECT COUNT(*) FROM dolt_status"},
			{"dolt_history_bc", "SELECT COUNT(*) FROM dolt_history_bc"},
			{"dolt_diff_bc", "SELECT COUNT(*) FROM dolt_diff_bc"},
			{"dolt_conflicts", "SELECT COUNT(*) FROM dolt_conflicts"},
			{"dolt_branches", "SELECT COUNT(*) FROM dolt_branches"},
			{"dolt_remotes", "SELECT COUNT(*) FROM dolt_remotes"},
			{"as_of", "SELECT COUNT(*) FROM bc AS OF 'HEAD'"},
			{"DOLT_ADD", "CALL DOLT_ADD('-A')"},
			{"DOLT_COMMIT", "CALL DOLT_COMMIT('-Am','bench probe','--allow-empty')"},
			{"DOLT_BRANCH", "CALL DOLT_BRANCH('bench_probe_branch')"},
			{"DOLT_CHECKOUT", "CALL DOLT_CHECKOUT('bench_probe_branch')"},
			{"DOLT_CHECKOUT_back", "CALL DOLT_CHECKOUT('main')"},
			{"DOLT_MERGE", "CALL DOLT_MERGE('bench_probe_branch')"},
			{"DOLT_RESET", "CALL DOLT_RESET('--hard')"},
			{"DOLT_GC", "CALL DOLT_GC()"},
			{"DOLT_PUSH", "CALL DOLT_PUSH('origin','main')"},
			{"DOLT_PULL", "CALL DOLT_PULL('origin')"},
			{"DOLT_FETCH", "CALL DOLT_FETCH('origin')"},
			{"DOLT_REMOTE_add", "CALL DOLT_REMOTE('add','probe','file:///tmp/bench_probe_remote')"},
		}
		res := map[string]any{}
		for _, p := range probes {
			t0 := time.Now()
			rows, err := conn.QueryContext(ctx, p.q)
			if err == nil {
				for rows.Next() {
				}
				rows.Close()
			}
			if err != nil {
				// some procedures return no rowset; retry as Exec
				if _, e2 := conn.ExecContext(ctx, p.q); e2 == nil {
					err = nil
				} else {
					err = e2
				}
			}
			if err != nil {
				res[p.name] = "ERR: " + strings.SplitN(err.Error(), "\n", 2)[0]
			} else {
				res[p.name] = fmt.Sprintf("ok %.0fms", ms(time.Since(t0)))
			}
		}
		emit(map[string]any{"ok": true, "mode": mode, "probes": res})

	// hold: open, write, hold the engine open for N seconds (concurrency probe)
	case "hold":
		secs, _ := strconv.ParseFloat(rest[0], 64)
		tag := rest[1]
		_, conn, done, _, err := open(ctx, dir, database)
		if err != nil {
			die("open", err)
		}
		defer done()
		if _, err := conn.ExecContext(ctx,
			"CREATE TABLE IF NOT EXISTS benchw (k VARCHAR(64) PRIMARY KEY, v INT NOT NULL)"); err != nil {
			die("ddl", err)
		}
		if _, err := conn.ExecContext(ctx, "INSERT INTO benchw (k,v) VALUES (?,1) ON DUPLICATE KEY UPDATE v=v+1", tag); err != nil {
			die("write", err)
		}
		fmt.Fprintln(os.Stderr, "HELD")
		time.Sleep(time.Duration(secs * float64(time.Second)))
		emit(map[string]any{"ok": true, "mode": mode, "held_s": secs,
			"in_process_ms": ms(time.Since(procStart))})

	// contend: try to open + write while someone else holds the dir.
	case "contend":
		tag := rest[0]
		_, conn, done, tim, err := open(ctx, dir, database)
		if err != nil {
			emit(map[string]any{"ok": false, "mode": mode, "stage": "open",
				"err": err.Error(), "in_process_ms": ms(time.Since(procStart))})
			os.Exit(3)
		}
		defer done()
		if _, err := conn.ExecContext(ctx,
			"CREATE TABLE IF NOT EXISTS benchw (k VARCHAR(64) PRIMARY KEY, v INT NOT NULL)"); err != nil {
			emit(map[string]any{"ok": false, "mode": mode, "stage": "ddl", "err": err.Error()})
			os.Exit(4)
		}
		if _, err := conn.ExecContext(ctx, "INSERT INTO benchw (k,v) VALUES (?,1) ON DUPLICATE KEY UPDATE v=v+1", tag); err != nil {
			emit(map[string]any{"ok": false, "mode": mode, "stage": "write", "err": err.Error()})
			os.Exit(5)
		}
		if _, err := conn.ExecContext(ctx, "CALL DOLT_COMMIT('-Am','contend "+tag+"')"); err != nil {
			emit(map[string]any{"ok": false, "mode": mode, "stage": "dolt_commit", "err": err.Error()})
			os.Exit(6)
		}
		out := map[string]any{"ok": true, "mode": mode, "tag": tag,
			"in_process_ms": ms(time.Since(procStart))}
		for k, x := range tim {
			out[k] = x
		}
		emit(out)

	// counter: read-modify-write N times (invariant-1 shape) under whatever
	// serialization the caller provides.
	case "counter":
		n, _ := strconv.Atoi(rest[0])
		_, conn, done, _, err := open(ctx, dir, database)
		if err != nil {
			die("open", err)
		}
		defer done()
		if _, err := conn.ExecContext(ctx,
			"CREATE TABLE IF NOT EXISTS ctr (id TINYINT PRIMARY KEY, n INT NOT NULL)"); err != nil {
			die("ddl", err)
		}
		conn.ExecContext(ctx, "INSERT IGNORE INTO ctr VALUES (1,0)")
		for i := 0; i < n; i++ {
			if _, err := conn.ExecContext(ctx, "UPDATE ctr SET n = n + 1 WHERE id = 1"); err != nil {
				die("update", err)
			}
		}
		v, err := scalarStr(ctx, conn, "SELECT n FROM ctr WHERE id = 1")
		if err != nil {
			die("read", err)
		}
		emit(map[string]any{"ok": true, "mode": mode, "n": n, "value": v,
			"in_process_ms": ms(time.Since(procStart))})

	// create: make a database from scratch in-process (no dolt CLI at all)
	case "create":
		_, conn, done, tim, err := open(ctx, dir, "")
		if err != nil {
			die("open", err)
		}
		defer done()
		t0 := time.Now()
		if _, err := conn.ExecContext(ctx, "CREATE DATABASE IF NOT EXISTS `"+database+"`"); err != nil {
			die("create-db", err)
		}
		if _, err := conn.ExecContext(ctx, "USE `"+database+"`"); err != nil {
			die("use", err)
		}
		ddl := rest[0]
		b, err := os.ReadFile(ddl)
		if err != nil {
			die("read-ddl", err)
		}
		// Strip `--` comments FIRST, to end of line, INCLUDING trailing ones.
		// Two traps here, both hit: (1) splitting on ';' leaves each chunk
		// prefixed with the comment block above its statement, so skipping
		// chunks that "start with --" skips real DDL; (2) a trailing comment
		// can itself contain a ';' ("-- CAP-008 etc; NULL = unassigned"), which
		// splits a statement in half. Naive for string literals, fine for DDL.
		var clean []string
		for _, ln := range strings.Split(string(b), "\n") {
			if i := strings.Index(ln, "--"); i >= 0 {
				ln = ln[:i]
			}
			if strings.TrimSpace(ln) == "" {
				continue
			}
			clean = append(clean, ln)
		}
		for _, s := range strings.Split(strings.Join(clean, "\n"), ";") {
			s = strings.TrimSpace(s)
			if s == "" {
				continue
			}
			if _, err := conn.ExecContext(ctx, s); err != nil {
				die("ddl", fmt.Errorf("%s: %w", strings.SplitN(s, "\n", 2)[0], err))
			}
		}
		if _, err := conn.ExecContext(ctx, "CALL DOLT_COMMIT('-Am','schema (embedded)')"); err != nil {
			die("dolt_commit", err)
		}
		out := map[string]any{"ok": true, "mode": mode, "create_ms": ms(time.Since(t0)),
			"in_process_ms": ms(time.Since(procStart))}
		for k, x := range tim {
			out[k] = x
		}
		emit(out)

	default:
		die("mode", errors.New("unknown mode "+mode))
	}
}
