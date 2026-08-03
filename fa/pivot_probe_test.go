package main

// pivot_probe_test.go — MEASURES the field-per-row (EAV) pivot cost at corpus scale.
//
// This is the L1-L2 design's ONE genuinely unmeasured assumption (its §9 Q9, and the
// spine's "the one genuinely unmeasured risk in the whole design"). A materialization
// fallback is specified but has NO TRIGGER, and a design resting on an unmeasured
// number is exactly what this repo's "never report a number a test could contradict"
// rule forbids.
//
// It answers, in order:
//
//   Q9a  Does GMS (the pure-Go engine, no `dolt` binary) support the design's
//        generated-view definition AT ALL? -- MAX(CASE WHEN ...) ... GROUP BY in a
//        CREATE VIEW. A "no" here invalidates L2-A's central mechanism, so it is
//        tested first and separately.
//   Q9b  Pivot latency vs the wide table it replaces, on IDENTICAL real data, across
//        the four query shapes the design actually issues.
//   Q9c  Row mass and on-disk growth.
//
// Discipline this probe holds to:
//   - REAL corpus data, real string lengths, real null rates, real cardinality. No
//     synthetic uniform rows -- a pivot's cost is driven by fan-in, and fan-in is a
//     property of the corpus (measured: p50 24, mean 20.4, max 127 field rows/artifact).
//   - PARITY FIRST. The wide read and the pivot read must return the SAME bytes before
//     any timing is reported. An unequal comparison is not a measurement.
//   - Report per-shape numbers, never one blended figure.
//
// Run explicitly (it is skipped in the normal suite -- it needs a corpus and it writes
// a scratch store):
//
//   FA_PIVOT_CORPUS=~/Dev/vsdd-factory/.factory \
//     CGO_ENABLED=1 go test -tags gms_pure_go -run TestPivotCost -v -timeout 30m .

import (
	"context"
	"crypto/sha1"
	"database/sql"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"testing"
	"time"
)

// sha1Bytes is the probe's stand-in for the design's BINARY(20) key_hash.
func sha1Bytes(s string) []byte {
	h := sha1.Sum([]byte(s))
	return h[:]
}

// The wide baseline: a typed table with one column per field, in the shape schema v4
// uses today.
//
// ⚠ The column width here is a MEASURED choice, not a convenience. VARCHAR(2000) x 12
// is REFUSED by GMS -- "expected size < 65504, found 100116" -- because utf8mb4 costs
// 4 bytes/char, so a VARCHAR(2000) column reserves 8002 bytes and only ~8 of them fit
// in a row. The real observed values across all 12 of these fields max out at 168
// chars (`wave`), with most <= 31, so VARCHAR(255) is generous against the corpus AND
// legal. Using the design's generic 2000 here would have made the wide table fail to
// exist and turned the comparison into a walkover -- an unequal comparison is not a
// measurement. The ceiling itself is measured separately, in TestWideRowCeiling.
const pivotWideDDL = `CREATE TABLE IF NOT EXISTS p_wide (
  key_hash   BINARY(20)   NOT NULL,
  key_json   VARCHAR(512) NOT NULL,
  path       VARCHAR(512) NOT NULL,
  f01 VARCHAR(255) NULL, f02 VARCHAR(255) NULL, f03 VARCHAR(255) NULL,
  f04 VARCHAR(255) NULL, f05 VARCHAR(255) NULL, f06 VARCHAR(255) NULL,
  f07 VARCHAR(255) NULL, f08 VARCHAR(255) NULL, f09 VARCHAR(255) NULL,
  f10 VARCHAR(255) NULL, f11 VARCHAR(255) NULL, f12 VARCHAR(255) NULL,
  PRIMARY KEY (key_hash),
  KEY idx_w_f01 (f01)
)`

// the EAV model, verbatim in shape from FA-V1-L1-L2-STORAGE-SCHEMA.md §2.
const pivotArtifactDDL = `CREATE TABLE IF NOT EXISTS p_artifact (
  type       VARCHAR(64)  NOT NULL,
  key_hash   BINARY(20)   NOT NULL,
  key_json   VARCHAR(512) NOT NULL,
  authority  VARCHAR(12)  NOT NULL,
  shape      VARCHAR(20)  NOT NULL,
  cycle_id   VARCHAR(120) NULL,
  path       VARCHAR(512) NOT NULL,
  PRIMARY KEY (type, key_hash),
  UNIQUE KEY uk_p_path (path),
  KEY idx_p_cycle (type, cycle_id)
)`

const pivotFieldDDL = `CREATE TABLE IF NOT EXISTS p_artifact_field (
  type VARCHAR(64) NOT NULL, key_hash BINARY(20) NOT NULL,
  field VARCHAR(64) NOT NULL,
  ord   INT         NOT NULL DEFAULT 0,
  kind  VARCHAR(12) NOT NULL,
  v_text VARCHAR(2000) NULL, v_int BIGINT NULL, v_date DATETIME NULL,
  PRIMARY KEY (type, key_hash, field, ord),
  CONSTRAINT fk_paf FOREIGN KEY (type, key_hash)
    REFERENCES p_artifact (type, key_hash) ON DELETE CASCADE
)`

type pivotRow struct {
	keyHash []byte
	keyJSON string
	path    string
	typ     string
	// fields the WIDE table mirrors as columns -- the parity set.
	fields map[string]string
	// EVERY other frontmatter field. These exist only in the EAV table, because that
	// is the real asymmetry: the EAV table holds the WHOLE corpus's field mass in one
	// table and the pivot must scan past the rows it does not want, while a typed wide
	// table only ever holds its own declared columns. Populating only the 12 parity
	// fields understated the fan-in at 4.5 rows/artifact when the measured corpus mean
	// is 20.4 (probe_field_mass.py) -- reporting a latency at 4.5 would have been a
	// number the real mass contradicts.
	extra map[string]string
}

// pivotFieldSlots is the fixed field set the wide table mirrors, so the two models
// hold IDENTICAL data and the comparison is honest.
var pivotFieldSlots = []string{
	"document_type", "status", "lifecycle_status", "capability", "subsystem",
	"version", "owner", "epic", "story_id", "bc_id", "points", "wave",
}

func TestPivotCost(t *testing.T) {
	corpus := os.Getenv("FA_PIVOT_CORPUS")
	if corpus == "" {
		t.Skip("set FA_PIVOT_CORPUS to a .factory corpus to run the pivot measurement")
	}
	corpus = expandHome(corpus)
	if _, err := os.Stat(corpus); err != nil {
		t.Fatalf("corpus %s: %v", corpus, err)
	}

	rows := collectPivotRows(t, corpus)
	if len(rows) == 0 {
		t.Fatal("collected 0 artifacts -- refusing to report a timing over an empty set (vacuity guard)")
	}

	root := t.TempDir()
	ctx := context.Background()
	st, err := Open(ctx, root, ZoneOpen, true)
	if err != nil {
		t.Fatalf("open store: %v", err)
	}
	defer st.Close()

	for _, ddl := range []string{pivotWideDDL, pivotArtifactDDL, pivotFieldDDL} {
		if _, err := st.Exec(ctx, ddl); err != nil {
			t.Fatalf("ddl: %v\n%s", err, ddl)
		}
	}

	// ---- populate BOTH models with identical data, one transaction each ----------
	nFieldRows := populatePivot(t, ctx, st, rows)

	t.Logf("")
	t.Logf("======================================================================")
	t.Logf("PIVOT COST MEASUREMENT  (corpus: %s)", corpus)
	t.Logf("======================================================================")
	t.Logf("artifacts            : %d", len(rows))
	t.Logf("p_artifact_field rows: %d  (%.1f per artifact)", nFieldRows, float64(nFieldRows)/float64(len(rows)))

	// ---- Q9a: does GMS support the generated view AT ALL? -----------------------
	viewSQL := buildPivotView()
	viewOK := true
	if _, err := st.Exec(ctx, viewSQL); err != nil {
		viewOK = false
		t.Logf("")
		t.Logf("⛔ Q9a FAIL — GMS REFUSED the design's generated view definition:")
		t.Logf("    %v", err)
		t.Logf("    This invalidates L2-A's central mechanism (per-type generated VIEWS).")
	} else {
		t.Logf("")
		t.Logf("✓ Q9a — GMS ACCEPTED the generated view (MAX(CASE WHEN ...) + GROUP BY)")
	}

	// a view that exists is not a view that answers: probe it.
	if viewOK {
		var n int64
		if err := st.conn.QueryRowContext(ctx, "SELECT COUNT(*) FROM v_pivot").Scan(&n); err != nil {
			viewOK = false
			t.Logf("⛔ Q9a FAIL — the view was created but cannot be QUERIED: %v", err)
		} else if n != int64(len(rows)) {
			t.Logf("⛔ Q9a FAIL — view returns %d rows, expected %d", n, len(rows))
			viewOK = false
		} else {
			t.Logf("✓ Q9a — the view is queryable and returns all %d artifacts", n)
		}
	}

	// ---- PARITY GATE: identical bytes before any timing ------------------------
	if viewOK {
		checkPivotParity(t, ctx, st, rows)
	}

	// ---- Q9b: the four query shapes -------------------------------------------
	t.Logf("")
	t.Logf("--- Q9b  pivot latency by query shape (best of 5, after 1 warmup) -----")
	t.Logf("%-34s %12s %12s %9s", "query shape", "WIDE", "EAV/pivot", "ratio")

	sample := rows[len(rows)/2]

	shapes := []struct {
		name string
		wide string
		eav  string
		args []any
	}{
		{
			"1 artifact, all fields, by key",
			`SELECT f01,f02,f03,f04,f05,f06,f07,f08,f09,f10,f11,f12 FROM p_wide WHERE key_hash=?`,
			`SELECT field,v_text FROM p_artifact_field WHERE type=? AND key_hash=?`,
			nil,
		},
		{
			"full-type scan, all fields",
			`SELECT key_json,f01,f02,f03,f04,f05,f06,f07,f08,f09,f10,f11,f12 FROM p_wide`,
			`SELECT * FROM v_pivot`,
			nil,
		},
		{
			"aggregate gate: GROUP BY 1 field",
			`SELECT f01, COUNT(*) FROM p_wide GROUP BY f01`,
			`SELECT v_text, COUNT(*) FROM p_artifact_field WHERE field='document_type' AND ord=0 GROUP BY v_text`,
			nil,
		},
		{
			"filtered read on 1 field",
			`SELECT key_json FROM p_wide WHERE f02='draft'`,
			`SELECT a.key_json FROM p_artifact a JOIN p_artifact_field f USING (type,key_hash) WHERE f.field='status' AND f.ord=0 AND f.v_text='draft'`,
			nil,
		},
	}

	type result struct{ name string; wide, eav time.Duration; ratio float64 }
	var results []result

	for _, sh := range shapes {
		wargs, eargs := sh.args, sh.args
		if strings.Contains(sh.wide, "key_hash=?") {
			wargs = []any{sample.keyHash}
			eargs = []any{sample.typ, sample.keyHash}
		}
		w := timeQuery(t, ctx, st, sh.wide, wargs)
		var e time.Duration
		if strings.Contains(sh.eav, "v_pivot") && !viewOK {
			t.Logf("%-34s %12s %12s %9s", sh.name, w.Round(time.Microsecond), "N/A(view)", "-")
			continue
		}
		e = timeQuery(t, ctx, st, sh.eav, eargs)
		ratio := float64(e) / float64(w)
		results = append(results, result{sh.name, w, e, ratio})
		t.Logf("%-34s %12s %12s %8.1fx", sh.name,
			w.Round(time.Microsecond), e.Round(time.Microsecond), ratio)
	}

	// ---- Q9c: mass + on-disk -------------------------------------------------
	t.Logf("")
	t.Logf("--- Q9c  mass and storage -------------------------------------------")
	if _, err := st.DoltCommit(ctx, "pivot probe: both models populated"); err != nil {
		t.Logf("commit: %v", err)
	}
	sz := dirSize(filepath.Join(root, ZoneOpen))
	t.Logf("store on disk after commit: %.1f MB", float64(sz)/(1<<20))
	t.Logf("field rows per artifact   : %.1f (measured over this corpus)", float64(nFieldRows)/float64(len(rows)))

	// ---- verdict -------------------------------------------------------------
	t.Logf("")
	t.Logf("--- VERDICT ----------------------------------------------------------")
	if !viewOK {
		t.Logf("GMS view support: ⛔ NOT AVAILABLE -- materialization is MANDATORY, not a fallback")
	} else {
		worst := 0.0
		worstName := ""
		for _, r := range results {
			if r.ratio > worst {
				worst, worstName = r.ratio, r.name
			}
		}
		t.Logf("worst pivot penalty: %.1fx on %q", worst, worstName)
		t.Logf("(a TRIGGER for the materialization fallback is proposed in the write-up,")
		t.Logf(" derived from these numbers rather than asserted)")
	}
}

// TestPivotStorage answers the L1-L2 design's declared unmeasured risk #6 -- "history
// growth is unmeasured at field-per-row granularity; ~6 KB/commit over 40 commits is
// all we know."
//
// It builds each model in its OWN store, so the number is per-model rather than a
// shared-store figure that cannot be attributed. It also measures the SECOND commit,
// because the risk is about history growth per commit, not one-time size.
func TestPivotStorage(t *testing.T) {
	corpus := os.Getenv("FA_PIVOT_CORPUS")
	if corpus == "" {
		t.Skip("set FA_PIVOT_CORPUS to a .factory corpus to run the storage measurement")
	}
	rows := collectPivotRows(t, expandHome(corpus))
	if len(rows) == 0 {
		t.Fatal("0 artifacts -- refusing to report a size over an empty set")
	}
	ctx := context.Background()

	type sizes struct{ empty, populated, afterEdit, afterGC int64 }
	measure := func(name string, ddl []string, fill func(*sql.Tx) int, edit func(*sql.Tx)) (sizes, int) {
		root := t.TempDir()
		st, err := Open(ctx, root, ZoneOpen, true)
		if err != nil {
			t.Fatalf("%s open: %v", name, err)
		}
		defer st.Close()
		for _, d := range ddl {
			if _, err := st.Exec(ctx, d); err != nil {
				t.Fatalf("%s ddl: %v", name, err)
			}
		}
		if _, err := st.DoltCommit(ctx, "schema"); err != nil {
			t.Fatalf("%s commit schema: %v", name, err)
		}
		zd := filepath.Join(root, ZoneOpen)
		var s sizes
		s.empty = dirSize(zd)

		tx, _ := st.Begin(ctx)
		n := fill(tx)
		if err := tx.Commit(); err != nil {
			t.Fatalf("%s fill: %v", name, err)
		}
		if _, err := st.DoltCommit(ctx, "populate"); err != nil {
			t.Fatalf("%s commit populate: %v", name, err)
		}
		s.populated = dirSize(zd)

		// one field changed on 100 artifacts -- the real steady-state write shape
		tx2, _ := st.Begin(ctx)
		edit(tx2)
		if err := tx2.Commit(); err != nil {
			t.Fatalf("%s edit: %v", name, err)
		}
		if _, err := st.DoltCommit(ctx, "edit 100 artifacts, 1 field each"); err != nil {
			t.Fatalf("%s commit edit: %v", name, err)
		}
		s.afterEdit = dirSize(zd)

		// ⚠ Without this the numbers above are the CHUNK JOURNAL, not the store.
		// Verified directly: a populated store was 147 MB of which 143 MB was a single
		// journal file with an EMPTY oldgen/ -- i.e. nothing had been collected yet. A
		// journal size is write amplification, which is a real and different quantity
		// from at-rest size, so both are reported rather than one being passed off as
		// the other.
		if _, err := st.Exec(ctx, "CALL DOLT_GC()"); err != nil {
			t.Logf("%s: DOLT_GC unavailable (%v) -- at-rest size not measured", name, err)
			s.afterGC = -1
		} else {
			s.afterGC = dirSize(zd)
		}
		return s, n
	}

	wcols := make([]string, len(pivotFieldSlots))
	for i := range pivotFieldSlots {
		wcols[i] = fmt.Sprintf("f%02d", i+1)
	}
	wq := "INSERT INTO p_wide (key_hash,key_json,path," + strings.Join(wcols, ",") +
		") VALUES (?,?,?," + strings.TrimSuffix(strings.Repeat("?,", len(wcols)), ",") + ")"

	wide, nWide := measure("wide", []string{pivotWideDDL},
		func(tx *sql.Tx) int {
			for _, r := range rows {
				args := []any{r.keyHash, r.keyJSON, r.path}
				for _, f := range pivotFieldSlots {
					if v, ok := r.fields[f]; ok {
						args = append(args, v)
					} else {
						args = append(args, nil)
					}
				}
				if _, err := tx.ExecContext(ctx, wq, args...); err != nil {
					t.Fatalf("wide insert: %v", err)
				}
			}
			return len(rows)
		},
		func(tx *sql.Tx) {
			for i, r := range rows {
				if i >= 100 {
					break
				}
				_, _ = tx.ExecContext(ctx, "UPDATE p_wide SET f02='edited' WHERE key_hash=?", r.keyHash)
			}
		})

	eav, nEav := measure("eav", []string{pivotArtifactDDL, pivotFieldDDL},
		func(tx *sql.Tx) int {
			n := 0
			for _, r := range rows {
				if _, err := tx.ExecContext(ctx,
					`INSERT INTO p_artifact (type,key_hash,key_json,authority,shape,cycle_id,path)
					 VALUES (?,?,?,'authored','record',NULL,?)`,
					r.typ, r.keyHash, r.keyJSON, r.path); err != nil {
					t.Fatalf("eav artifact: %v", err)
				}
				for _, set := range []map[string]string{r.fields, r.extra} {
					for f, v := range set {
						if _, err := tx.ExecContext(ctx,
							`INSERT INTO p_artifact_field (type,key_hash,field,ord,kind,v_text)
							 VALUES (?,?,?,0,'text',?)`, r.typ, r.keyHash, f, v); err != nil {
							t.Fatalf("eav field: %v", err)
						}
						n++
					}
				}
			}
			return n
		},
		func(tx *sql.Tx) {
			for i, r := range rows {
				if i >= 100 {
					break
				}
				_, _ = tx.ExecContext(ctx,
					`UPDATE p_artifact_field SET v_text='edited'
					 WHERE type=? AND key_hash=? AND field='status' AND ord=0`, r.typ, r.keyHash)
			}
		})

	mb := func(b int64) float64 { return float64(b) / (1 << 20) }
	t.Logf("")
	t.Logf("--- storage, each model in its OWN store (declared risk #6) -----------")
	t.Logf("%-28s %12s %12s %14s", "", "WIDE", "EAV", "EAV/WIDE")
	t.Logf("%-28s %12d %12d", "rows written", nWide, nEav)
	t.Logf("%-28s %11.1fM %11.1fM %13.2fx", "schema only (empty)", mb(wide.empty), mb(eav.empty),
		mb(eav.empty)/mb(wide.empty))
	t.Logf("%-28s %11.1fM %11.1fM %13.2fx", "after populate", mb(wide.populated), mb(eav.populated),
		mb(eav.populated)/mb(wide.populated))
	dw := wide.populated - wide.empty
	de := eav.populated - eav.empty
	t.Logf("%-28s %11.1fM %11.1fM %13.2fx", "  ^ data delta", mb(dw), mb(de), mb(de)/mb(dw))
	ew := wide.afterEdit - wide.populated
	ee := eav.afterEdit - eav.populated
	t.Logf("%-28s %11.1fK %11.1fK %13.2fx", "commit: 100 artifacts x 1 field",
		float64(ew)/1024, float64(ee)/1024, float64(ee)/float64(ew))
	t.Logf("%-28s %11.1fK %11.1fK", "  ^ per artifact edited",
		float64(ew)/1024/100, float64(ee)/1024/100)
	if wide.afterGC >= 0 && eav.afterGC >= 0 {
		t.Logf("%-28s %11.1fM %11.1fM %13.2fx", "AT REST (after DOLT_GC)",
			mb(wide.afterGC), mb(eav.afterGC), mb(eav.afterGC)/mb(wide.afterGC))
		t.Logf("%-28s %11.1fx %11.1fx", "  journal write amplification",
			float64(wide.afterEdit)/float64(wide.afterGC),
			float64(eav.afterEdit)/float64(eav.afterGC))
	}
}

// TestWideRowCeiling measures how many columns a GENERATED wide table could actually
// hold in GMS, at the widths a generator would have to choose.
//
// This is the question the L1-L2 design never asked. It argued for the field-per-row
// model on migration cost and on "two homes drift" -- both correct -- but the binding
// constraint may simply be that the alternative CANNOT BE BUILT: a schema generated
// from a registry does not know a field's future maximum length, so it must pick a
// generic width, and a generic width exhausts the row budget long before the median
// artifact's field count (measured: p50 24 fields, max 127).
//
// Unlike the pivot probe this needs no corpus, so it runs in the normal suite.
func TestWideRowCeiling(t *testing.T) {
	ctx := context.Background()
	st, err := Open(ctx, t.TempDir(), ZoneOpen, true)
	if err != nil {
		t.Fatalf("open: %v", err)
	}
	defer st.Close()

	// widths a schema GENERATOR might plausibly choose, having no per-field knowledge
	for _, w := range []int{2000, 1000, 512, 255, 64} {
		maxCols := 0
		for n := 1; n <= 200; n++ {
			cols := make([]string, n)
			for i := range cols {
				cols[i] = fmt.Sprintf("f%03d VARCHAR(%d) NULL", i, w)
			}
			tbl := fmt.Sprintf("ceil_%d_%d", w, n)
			ddl := fmt.Sprintf("CREATE TABLE %s (k BINARY(20) NOT NULL, %s, PRIMARY KEY (k))",
				tbl, strings.Join(cols, ", "))
			if _, err := st.Exec(ctx, ddl); err != nil {
				break
			}
			_, _ = st.Exec(ctx, "DROP TABLE "+tbl)
			maxCols = n
		}
		verdict := "holds the median artifact (24 fields)"
		if maxCols < 24 {
			verdict = "⛔ CANNOT hold the median artifact (24 fields)"
		}
		t.Logf("VARCHAR(%-4d) -> max %3d columns per row   %s", w, maxCols, verdict)
		if w == 2000 && maxCols >= 24 {
			t.Errorf("expected VARCHAR(2000) to cap below 24 columns; got %d", maxCols)
		}
	}

	// TEXT is stored out-of-row, so it should escape the budget entirely: verify,
	// because "should" is not a measurement.
	cols := make([]string, 60)
	for i := range cols {
		cols[i] = fmt.Sprintf("f%03d TEXT NULL", i)
	}
	ddl := "CREATE TABLE ceil_text (k BINARY(20) NOT NULL, " + strings.Join(cols, ", ") +
		", PRIMARY KEY (k))"
	if _, err := st.Exec(ctx, ddl); err != nil {
		t.Logf("60 x TEXT columns: REFUSED -- %v", err)
	} else {
		t.Logf("60 x TEXT columns: accepted (TEXT escapes the row budget)")
	}
}

// buildPivotView emits the design's generated view for the probe's field set.
func buildPivotView() string {
	var b strings.Builder
	b.WriteString("CREATE VIEW v_pivot AS SELECT a.key_json, a.path")
	for i, f := range pivotFieldSlots {
		fmt.Fprintf(&b, ", MAX(CASE WHEN f.field='%s' THEN f.v_text END) AS c%02d", f, i+1)
	}
	b.WriteString(" FROM p_artifact a LEFT JOIN p_artifact_field f USING (type, key_hash)")
	b.WriteString(" WHERE a.type='probe' GROUP BY a.type, a.key_hash, a.key_json, a.path")
	return b.String()
}

// checkPivotParity refuses to let a timing be reported over unequal data.
func checkPivotParity(t *testing.T, ctx context.Context, st *Store, rows []pivotRow) {
	t.Helper()
	mismatch, checked := 0, 0
	for _, r := range rows {
		if checked >= 200 { // a sample, but a stated one
			break
		}
		checked++
		wide := make([]sql.NullString, len(pivotFieldSlots))
		dest := make([]any, len(pivotFieldSlots))
		for i := range wide {
			dest[i] = &wide[i]
		}
		cols := make([]string, len(pivotFieldSlots))
		for i := range pivotFieldSlots {
			cols[i] = fmt.Sprintf("f%02d", i+1)
		}
		q := "SELECT " + strings.Join(cols, ",") + " FROM p_wide WHERE key_hash=?"
		if err := st.conn.QueryRowContext(ctx, q, r.keyHash).Scan(dest...); err != nil {
			t.Fatalf("parity: wide read: %v", err)
		}
		vcols := make([]string, len(pivotFieldSlots))
		for i := range pivotFieldSlots {
			vcols[i] = fmt.Sprintf("c%02d", i+1)
		}
		got := make([]sql.NullString, len(pivotFieldSlots))
		gdest := make([]any, len(pivotFieldSlots))
		for i := range got {
			gdest[i] = &got[i]
		}
		vq := "SELECT " + strings.Join(vcols, ",") + " FROM v_pivot WHERE key_json=?"
		if err := st.conn.QueryRowContext(ctx, vq, r.keyJSON).Scan(gdest...); err != nil {
			t.Fatalf("parity: view read: %v", err)
		}
		for i := range wide {
			if wide[i].String != got[i].String || wide[i].Valid != got[i].Valid {
				mismatch++
				if mismatch <= 3 {
					t.Errorf("PARITY MISMATCH %s field %s: wide=%q(%v) view=%q(%v)",
						r.keyJSON, pivotFieldSlots[i],
						wide[i].String, wide[i].Valid, got[i].String, got[i].Valid)
				}
			}
		}
	}
	if mismatch == 0 {
		t.Logf("✓ PARITY — wide and pivot return identical values over %d artifacts x %d fields",
			checked, len(pivotFieldSlots))
	} else {
		t.Fatalf("⛔ PARITY FAILED on %d cells -- timings below would be meaningless", mismatch)
	}
}

func timeQuery(t *testing.T, ctx context.Context, st *Store, q string, args []any) time.Duration {
	t.Helper()
	drain := func() {
		rows, err := st.Query(ctx, q, args...)
		if err != nil {
			t.Fatalf("query failed: %v\n%s", err, q)
		}
		cols, _ := rows.Columns()
		buf := make([]any, len(cols))
		raw := make([]sql.RawBytes, len(cols))
		for i := range buf {
			buf[i] = &raw[i]
		}
		for rows.Next() {
			_ = rows.Scan(buf...)
		}
		rows.Close()
	}
	drain() // warmup
	best := time.Duration(1 << 62)
	for i := 0; i < 5; i++ {
		s := time.Now()
		drain()
		if d := time.Since(s); d < best {
			best = d
		}
	}
	return best
}

func collectPivotRows(t *testing.T, corpus string) []pivotRow {
	t.Helper()
	var out []pivotRow
	seen := map[string]bool{}
	_ = filepath.Walk(corpus, func(p string, info os.FileInfo, err error) error {
		if err != nil || info.IsDir() {
			if info != nil && info.IsDir() && info.Name() == ".git" {
				return filepath.SkipDir
			}
			return nil
		}
		if !strings.HasSuffix(p, ".md") {
			return nil
		}
		b, err := os.ReadFile(p)
		if err != nil {
			return nil
		}
		fm, _ := ParseFrontmatter(string(b))
		rel, _ := filepath.Rel(corpus, p)
		if seen[rel] {
			return nil
		}
		seen[rel] = true
		r := pivotRow{
			keyHash: sha1Bytes(rel),
			keyJSON: rel,
			path:    rel,
			typ:     "probe",
			fields:  map[string]string{},
			extra:   map[string]string{},
		}
		isSlot := map[string]bool{}
		for _, f := range pivotFieldSlots {
			isSlot[f] = true
			if v := fm.Scalar(f); v != "" {
				if len(v) > 255 {
					v = v[:255] // the wide column's width; overflow is reported by probe_field_mass.py
				}
				r.fields[f] = v
			}
		}
		// every remaining frontmatter key becomes an EAV-only field row, so the pivot
		// pays the corpus's REAL fan-in rather than the parity set's.
		for k := range fm {
			if isSlot[k] {
				continue
			}
			v := fm.Scalar(k)
			if v == "" {
				continue
			}
			if len(v) > 2000 {
				v = v[:2000] // the model's declared v_text ceiling
			}
			if len(k) > 64 {
				continue // the model's field VARCHAR(64); reported by probe_field_mass.py
			}
			r.extra[k] = v
		}
		out = append(out, r)
		return nil
	})
	sort.Slice(out, func(i, j int) bool { return out[i].path < out[j].path })
	return out
}

func populatePivot(t *testing.T, ctx context.Context, st *Store, rows []pivotRow) int {
	t.Helper()
	tx, err := st.Begin(ctx)
	if err != nil {
		t.Fatalf("begin: %v", err)
	}
	nField := 0
	wcols := make([]string, len(pivotFieldSlots))
	for i := range pivotFieldSlots {
		wcols[i] = fmt.Sprintf("f%02d", i+1)
	}
	wq := "INSERT INTO p_wide (key_hash,key_json,path," + strings.Join(wcols, ",") +
		") VALUES (?,?,?," + strings.TrimSuffix(strings.Repeat("?,", len(wcols)), ",") + ")"

	for _, r := range rows {
		args := []any{r.keyHash, r.keyJSON, r.path}
		for _, f := range pivotFieldSlots {
			if v, ok := r.fields[f]; ok {
				args = append(args, v)
			} else {
				args = append(args, nil)
			}
		}
		if _, err := tx.ExecContext(ctx, wq, args...); err != nil {
			t.Fatalf("insert wide: %v", err)
		}
		if _, err := tx.ExecContext(ctx,
			`INSERT INTO p_artifact (type,key_hash,key_json,authority,shape,cycle_id,path)
			 VALUES (?,?,?,?,?,?,?)`,
			r.typ, r.keyHash, r.keyJSON, "authored", "record", nil, r.path); err != nil {
			t.Fatalf("insert artifact: %v", err)
		}
		for _, set := range []map[string]string{r.fields, r.extra} {
			for f, v := range set {
				if _, err := tx.ExecContext(ctx,
					`INSERT INTO p_artifact_field (type,key_hash,field,ord,kind,v_text)
					 VALUES (?,?,?,0,'text',?)`, r.typ, r.keyHash, f, v); err != nil {
					t.Fatalf("insert field %q: %v", f, err)
				}
				nField++
			}
		}
	}
	if err := tx.Commit(); err != nil {
		t.Fatalf("commit: %v", err)
	}
	return nField
}

func dirSize(p string) int64 {
	var n int64
	_ = filepath.Walk(p, func(_ string, info os.FileInfo, err error) error {
		if err == nil && !info.IsDir() {
			n += info.Size()
		}
		return nil
	})
	return n
}
