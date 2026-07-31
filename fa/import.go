package main

// `fa import` — build the shadow store from the markdown corpus.
//
// Phase 1 is a READ-ONLY SHADOW (DECISIONS D3): markdown stays the single source
// of truth, nothing is written back, nothing is pushed, and the store is
// throwaway. If `fa` is wrong here, a CI job is wrong; the corpus is untouched.
//
// SPEC invariant 6 — ONE TRANSACTION per unit of work — is the whole performance
// story: per-statement autocommit costs ~5-7 ms in EVERY access path, so the same
// insert set is 15.7 s statement-by-statement and ~1 s inside one transaction.
// It is also exactly the boundary atomicity requires: a half-imported store must
// never be observable.

import (
	"context"
	"crypto/sha256"
	"database/sql"
	"encoding/hex"
	"fmt"
	"io"
	"sort"
	"strings"
	"time"
)

const faVersion = "0.1.0"

// deleteOrder clears the store for a deterministic refresh. Children before
// parents: a FOREIGN KEY is a real constraint here, not decoration.
var deleteOrder = []string{
	"vp_bc", "vp_di", "vp_nfr", "vp_subsystem",
	"story_bc", "story_vp", "story_fr", "story_subsystem", "story_dep", "bc_trace",
	"bc", "vp", "story",
	"capability", "domain_invariant", "nfr", "fr", "adr", "epic", "subsystem",
	"finding", "corpus_assertion", "index_entry", "import_run",
}

type ImportStats struct {
	Fingerprint string
	Subsystems  int
	Universes   map[string]int
	BCs         int
	VPs         int
	Stories     int
	Edges       map[string]int
	Findings    int
	Assertions  int
	Changed     bool
	Elapsed     time.Duration
}

func (s ImportStats) EdgeTotal() int {
	n := 0
	for _, v := range s.Edges {
		n += v
	}
	return n
}

// ensureSchema applies the zone's DDL. CREATE TABLE IF NOT EXISTS makes it
// idempotent; the migration ledger records the version so `fa doctor` can tell a
// current store from one built by an older binary.
func ensureSchema(ctx context.Context, s *Store) error {
	for _, stmt := range ddlFor(s.Zone) {
		if _, err := s.Exec(ctx, stmt); err != nil {
			return fmt.Errorf("ddl %q: %w", firstLine(stmt), err)
		}
	}
	if _, err := s.Exec(ctx,
		`INSERT INTO schema_migrations (version, name, applied_at) VALUES (?,?,NOW())
		 ON DUPLICATE KEY UPDATE name=VALUES(name)`,
		schemaVersion, fmt.Sprintf("fa %s zone %s", faVersion, s.Zone)); err != nil {
		return fmt.Errorf("record migration: %w", err)
	}
	return nil
}

func firstLine(s string) string {
	if i := strings.IndexByte(s, '\n'); i >= 0 {
		return strings.TrimSpace(s[:i])
	}
	return strings.TrimSpace(s)
}

// Import scans the corpus and loads it in one transaction.
func Import(ctx context.Context, s *Store, root string, out io.Writer) (*ImportStats, error) {
	t0 := time.Now()
	c, err := ScanCorpus(root)
	if err != nil {
		return nil, err
	}
	if len(c.BCs) == 0 && len(c.VPs) == 0 && len(c.Stories) == 0 {
		// A checker that finds nothing must not report success: an empty scan means
		// the path is wrong, not that the corpus is clean.
		return nil, fmt.Errorf("no records found under %s — wrong path?", root)
	}
	if err := ensureSchema(ctx, s); err != nil {
		return nil, err
	}

	st := &ImportStats{Universes: map[string]int{}, Edges: map[string]int{}}

	tx, err := s.Begin(ctx)
	if err != nil {
		return nil, fmt.Errorf("begin: %w", err)
	}
	committed := false
	defer func() {
		if !committed {
			_ = tx.Rollback()
		}
	}()

	for _, t := range deleteOrder {
		if _, err := tx.ExecContext(ctx, "DELETE FROM "+t); err != nil {
			return nil, fmt.Errorf("clear %s: %w", t, err)
		}
	}

	// ---- nodes
	for _, ss := range c.Subsystems {
		if _, err := tx.ExecContext(ctx,
			`INSERT INTO subsystem (ss_id, bc_prefix, name) VALUES (?,?,?)`,
			ss.ID, ss.BCPrefix, ss.Name); err != nil {
			return nil, fmt.Errorf("subsystem %s: %w", ss.ID, err)
		}
		st.Subsystems++
	}

	universeTables := []struct {
		key, table, idCol, nameCol string
	}{
		{"cap", "capability", "cap_id", "name"},
		{"di", "domain_invariant", "di_id", "name"},
		{"nfr", "nfr", "nfr_id", "name"},
		{"fr", "fr", "fr_id", "name"},
		{"adr", "adr", "adr_id", "title"},
		{"epic", "epic", "epic_id", "title"},
	}
	for _, u := range universeTables {
		ids := make([]string, 0, len(c.Universes[u.key]))
		for id := range c.Universes[u.key] {
			ids = append(ids, id)
		}
		sort.Strings(ids)
		q := fmt.Sprintf("INSERT INTO %s (%s, %s) VALUES (?,?)", u.table, u.idCol, u.nameCol)
		for _, id := range ids {
			if _, err := tx.ExecContext(ctx, q, id, c.Universes[u.key][id]); err != nil {
				return nil, fmt.Errorf("%s %s: %w", u.table, id, err)
			}
		}
		st.Universes[u.key] = len(ids)
	}

	vpStmt, err := tx.PrepareContext(ctx, `INSERT INTO vp
	  (vp_id, title, body, version, scope, source_bc, proof_method, feasibility, module, vp_type, src_path)
	  VALUES (?,?,?,?,?,?,?,?,?,?,?)`)
	if err != nil {
		return nil, err
	}
	for _, v := range c.VPs {
		if _, err := vpStmt.ExecContext(ctx, v.ID, v.Title, v.Body, v.Version,
			nullIf(v.Scope), nullIf(v.SourceBC), nullIf(v.ProofMethod), nullIf(v.Feasibility),
			nullIf(v.Module), nullIf(v.VPType), v.SrcPath); err != nil {
			return nil, fmt.Errorf("vp %s: %w", v.ID, err)
		}
		st.VPs++
	}
	_ = vpStmt.Close()

	bcStmt, err := tx.PrepareContext(ctx, `INSERT INTO bc
	  (bc_id, ss_id, title, body, capability, version, lifecycle_status, status, replacement, src_path)
	  VALUES (?,?,?,?,?,?,?,?,?,?)`)
	if err != nil {
		return nil, err
	}
	for _, b := range c.BCs {
		if _, err := bcStmt.ExecContext(ctx, b.ID, b.SS, b.Title, b.Body,
			nullIf(b.Capability), b.Version, nullIf(b.LifecycleStatus), nullIf(b.Status),
			nullIf(b.Replacement), b.SrcPath); err != nil {
			if isDuplicateKey(err) {
				// Two files claiming one BC id is a real corpus defect, not a crash.
				c.find("two files claim the same BC id", b.ID+" -> "+b.SrcPath, ClassIntegrity, "")
				continue
			}
			return nil, fmt.Errorf("bc %s: %w", b.ID, err)
		}
		st.BCs++
	}
	_ = bcStmt.Close()

	stStmt, err := tx.PrepareContext(ctx, `INSERT INTO story
	  (story_id, title, status, wave, epic_id, priority, points, cycle, body, src_path)
	  VALUES (?,?,?,?,?,?,?,?,?,?)`)
	if err != nil {
		return nil, err
	}
	for _, s2 := range c.Stories {
		var wave any
		if s2.Wave != nil {
			wave = *s2.Wave
		}
		if _, err := stStmt.ExecContext(ctx, s2.ID, s2.Title, s2.Status, wave,
			nullIf(s2.EpicID), nullIf(s2.Priority), nullIf(s2.Points), nullIf(s2.Cycle),
			s2.Body, s2.SrcPath); err != nil {
			return nil, fmt.Errorf("story %s: %w", s2.ID, err)
		}
		st.Stories++
	}
	_ = stStmt.Close()

	// ---- edges: a FOREIGN KEY rejection IS the finding
	//
	// Never INSERT IGNORE here. IGNORE downgrades an FK violation to a warning,
	// which makes every dangling reference silently vanish and this whole check
	// report a false clean. That bug happened once and is the reason this comment
	// exists.
	edgeStmts := map[string]*sql.Stmt{}
	defer func() {
		for _, s3 := range edgeStmts {
			_ = s3.Close()
		}
	}()
	for _, e := range c.Edges {
		key := e.Table + ":" + strings.Join(e.Cols, ",")
		stmt, ok := edgeStmts[key]
		if !ok {
			ph := strings.TrimSuffix(strings.Repeat("?,", len(e.Cols)), ",")
			q := fmt.Sprintf("INSERT INTO %s (%s) VALUES (%s)", e.Table, strings.Join(e.Cols, ","), ph)
			stmt, err = tx.PrepareContext(ctx, q)
			if err != nil {
				return nil, err
			}
			edgeStmts[key] = stmt
		}
		args := make([]any, len(e.Vals))
		for i, v := range e.Vals {
			args[i] = v
		}
		if _, err := stmt.ExecContext(ctx, args...); err != nil {
			switch {
			case isDuplicateKey(err):
				// The same edge declared twice is benign: the relation is a set.
			case isFKViolation(err):
				c.find(e.Label, e.Vals[0]+" -> "+e.Vals[1], ClassDangling, "")
			default:
				return nil, fmt.Errorf("edge %s %v: %w", e.Table, e.Vals, err)
			}
			continue
		}
		st.Edges[e.Table]++
	}

	// ---- what the markdown claims about itself
	for _, a := range c.Assertions {
		if _, err := tx.ExecContext(ctx,
			`INSERT INTO corpus_assertion (source, kind, subject, claimed, src_path) VALUES (?,?,?,?,?)`,
			a.Source, a.Kind, a.Subject, a.Claimed, nullIf(a.SrcPath)); err != nil {
			return nil, fmt.Errorf("assertion %s/%s: %w", a.Source, a.Subject, err)
		}
		st.Assertions++
	}

	// ---- what the index enumerates (checked separately from what it counts)
	for _, id := range c.Enumerated {
		if _, err := tx.ExecContext(ctx,
			`INSERT INTO index_entry (kind, id, source) VALUES ('bc', ?, 'BC-INDEX.md')
			 ON DUPLICATE KEY UPDATE id=VALUES(id)`, id); err != nil {
			return nil, fmt.Errorf("index_entry %s: %w", id, err)
		}
	}

	// ---- findings the data itself can no longer show
	findStmt, err := tx.PrepareContext(ctx,
		`INSERT INTO finding (rule, subject, class, detail, occurrences) VALUES (?,?,?,?,1)
		 ON DUPLICATE KEY UPDATE occurrences = occurrences + 1`)
	if err != nil {
		return nil, err
	}
	for _, f := range c.Findings {
		if _, err := findStmt.ExecContext(ctx, f.Rule, truncRunes(f.Subject, 400), f.Class, nullIf(f.Detail)); err != nil {
			return nil, fmt.Errorf("finding %s: %w", f.Rule, err)
		}
	}
	_ = findStmt.Close()
	st.Findings = len(c.Findings)

	st.Fingerprint = fingerprint(c)
	if _, err := tx.ExecContext(ctx,
		`INSERT INTO import_run (fingerprint, fa_version, n_bc, n_vp, n_story, n_edge) VALUES (?,?,?,?,?,?)`,
		st.Fingerprint, faVersion, st.BCs, st.VPs, st.Stories, st.EdgeTotal()); err != nil {
		return nil, fmt.Errorf("import_run: %w", err)
	}

	if err := tx.Commit(); err != nil {
		return nil, fmt.Errorf("commit: %w", err)
	}
	committed = true

	changed, err := s.DoltCommit(ctx, "import: shadow the markdown corpus ("+st.Fingerprint[:12]+")")
	if err != nil {
		return nil, fmt.Errorf("dolt commit: %w", err)
	}
	st.Changed = changed
	st.Elapsed = time.Since(t0)
	if out != nil {
		fmt.Fprintf(out, "imported in %.1fs  bc=%d vp=%d story=%d subsystem=%d edges=%d findings=%d assertions=%d\n",
			st.Elapsed.Seconds(), st.BCs, st.VPs, st.Stories, st.Subsystems, st.EdgeTotal(), st.Findings, st.Assertions)
		if !changed {
			fmt.Fprintln(out, "no change since the last import (idempotent re-run)")
		}
	}
	return st, nil
}

// nullIf maps "" to SQL NULL. A column that means "genuinely unassigned" must not
// hold an empty string that later compares unequal to NULL in a gate.
func nullIf(s string) any {
	if s == "" {
		return nil
	}
	return s
}

// fingerprint is a content hash of the scanned model. Same corpus in, same
// fingerprint out, on any machine — so it can key an append-only ledger row
// without breaking idempotence.
func fingerprint(c *Corpus) string {
	h := sha256.New()
	add := func(parts ...string) {
		for _, p := range parts {
			h.Write([]byte(p))
			h.Write([]byte{0})
		}
		h.Write([]byte{'\n'})
	}
	for _, s := range c.Subsystems {
		add("ss", s.ID, fmt.Sprint(s.BCPrefix), s.Name)
	}
	keys := make([]string, 0, len(c.Universes))
	for k := range c.Universes {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	for _, k := range keys {
		ids := make([]string, 0, len(c.Universes[k]))
		for id := range c.Universes[k] {
			ids = append(ids, id)
		}
		sort.Strings(ids)
		for _, id := range ids {
			add("u", k, id, c.Universes[k][id])
		}
	}
	for _, b := range c.BCs {
		add("bc", b.ID, b.SS, b.Version, b.Capability, b.LifecycleStatus, b.Status, b.Replacement, hashOf(b.Body))
	}
	for _, v := range c.VPs {
		add("vp", v.ID, v.Version, v.Scope, v.SourceBC, hashOf(v.Body))
	}
	for _, s := range c.Stories {
		w := ""
		if s.Wave != nil {
			w = fmt.Sprint(*s.Wave)
		}
		add("story", s.ID, s.Status, w, s.EpicID, hashOf(s.Body))
	}
	for _, e := range c.Edges {
		add(append([]string{"e", e.Table}, e.Vals...)...)
	}
	for _, a := range c.Assertions {
		add("a", a.Source, a.Kind, a.Subject, fmt.Sprint(a.Claimed))
	}
	return hex.EncodeToString(h.Sum(nil))
}

func hashOf(s string) string {
	h := sha256.Sum256([]byte(s))
	return hex.EncodeToString(h[:8])
}
