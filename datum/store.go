package main

// The store layer. `datum` talks to Dolt through the EMBEDDED dolthub/driver/v2 —
// there is no `dolt` binary dependency anywhere, including CI (DECISIONS D3 as
// superseded 2026-07-31, SPEC §7 phase 3 access-path call brought forward).
//
// Two measured constraints shape this file, and neither is negotiable:
//
//   1. The connection must be PINNED (MaxOpenConns(1) + one *sql.Conn). `USE <db>`
//      is connection state; on a pool it applies to whichever connection happened
//      to run it. bench.go learned this the hard way.
//   2. A second opener of the same Dolt directory silently becomes READ-ONLY and
//      fails much later with `cannot update manifest: database is read only`.
//      So `datum doctor` must probe WRITABILITY, not openability — see doctor.go.

import (
	"context"
	"database/sql"
	"fmt"
	"net/url"
	"os"
	"path/filepath"
	"strings"

	doltembed "github.com/dolthub/driver/v2"
)

// Zone names. Trust zones are separate database DIRECTORIES, never databases
// under one --data-dir: a shared data dir leaks via `SELECT ... FROM walled.x`
// (SPEC invariant 9 / A2).
const (
	ZoneOpen   = "open"
	ZoneWalled = "walled"
)

// Database names, one per zone directory.
var zoneDB = map[string]string{
	ZoneOpen:   "factory_artifacts",
	ZoneWalled: "factory_walled",
}

// Store is one open zone, holding a pinned connection.
type Store struct {
	Zone string
	Dir  string // the zone directory (the Dolt data dir)
	DB   string // database name inside it

	db        *sql.DB
	conn      *sql.Conn
	connector *doltembed.Connector
}

// zoneDir returns the directory for a zone under the store root.
func zoneDir(root, zone string) string { return filepath.Join(root, zone) }

// Open opens one zone. create=false fails if the zone has never been initialised,
// so a typo'd --db never silently produces an empty, clean-looking store.
func Open(ctx context.Context, root, zone string, create bool) (*Store, error) {
	dbName, ok := zoneDB[zone]
	if !ok {
		return nil, fmt.Errorf("unknown zone %q (want %s or %s)", zone, ZoneOpen, ZoneWalled)
	}
	dir := zoneDir(root, zone)
	if create {
		if err := os.MkdirAll(dir, 0o755); err != nil {
			return nil, err
		}
	} else if _, err := os.Stat(filepath.Join(dir, dbName)); err != nil {
		return nil, fmt.Errorf("zone %s not initialised at %s (run `datum init`)", zone, dir)
	}

	v := url.Values{}
	v.Set(doltembed.CommitNameParam, commitName())
	v.Set(doltembed.CommitEmailParam, commitEmail())
	v.Set(doltembed.MultiStatementsParam, "true")
	cfg, err := doltembed.ParseDSN("file://" + dir + "?" + v.Encode())
	if err != nil {
		return nil, fmt.Errorf("parse dsn: %w", err)
	}
	connector, err := doltembed.NewConnector(cfg)
	if err != nil {
		return nil, fmt.Errorf("open %s: %w", dir, err)
	}
	db := sql.OpenDB(connector)
	db.SetMaxOpenConns(1)
	db.SetMaxIdleConns(1)
	db.SetConnMaxIdleTime(0)
	db.SetConnMaxLifetime(0)

	s := &Store{Zone: zone, Dir: dir, DB: dbName, db: db, connector: connector}
	if err := db.PingContext(ctx); err != nil {
		s.Close()
		return nil, fmt.Errorf("ping %s: %w", dir, err)
	}
	conn, err := db.Conn(ctx)
	if err != nil {
		s.Close()
		return nil, fmt.Errorf("pin connection: %w", err)
	}
	s.conn = conn

	if create {
		if _, err := conn.ExecContext(ctx, "CREATE DATABASE IF NOT EXISTS `"+dbName+"`"); err != nil {
			s.Close()
			return nil, fmt.Errorf("create database %s: %w", dbName, err)
		}
	}
	if _, err := conn.ExecContext(ctx, "USE `"+dbName+"`"); err != nil {
		s.Close()
		return nil, fmt.Errorf("use %s: %w", dbName, err)
	}
	return s, nil
}

func (s *Store) Close() {
	if s.conn != nil {
		_ = s.conn.Close()
	}
	if s.db != nil {
		_ = s.db.Close()
	}
	if s.connector != nil {
		_ = s.connector.Close()
	}
}

func (s *Store) Exec(ctx context.Context, q string, args ...any) (sql.Result, error) {
	return s.conn.ExecContext(ctx, q, args...)
}

func (s *Store) Query(ctx context.Context, q string, args ...any) (*sql.Rows, error) {
	return s.conn.QueryContext(ctx, q, args...)
}

// Int runs a scalar query. A gate that is a query cannot disagree with the data
// it checks (SPEC §3.3), so every gate in validate.go comes through here.
func (s *Store) Int(ctx context.Context, q string, args ...any) (int64, error) {
	var n sql.NullInt64
	if err := s.conn.QueryRowContext(ctx, q, args...).Scan(&n); err != nil {
		return 0, err
	}
	return n.Int64, nil
}

func (s *Store) Str(ctx context.Context, q string, args ...any) (string, error) {
	var v sql.NullString
	err := s.conn.QueryRowContext(ctx, q, args...).Scan(&v)
	return v.String, err
}

// Strings collects a single-column result.
func (s *Store) Strings(ctx context.Context, q string, args ...any) ([]string, error) {
	rows, err := s.Query(ctx, q, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []string
	for rows.Next() {
		var v sql.NullString
		if err := rows.Scan(&v); err != nil {
			return nil, err
		}
		out = append(out, v.String)
	}
	return out, rows.Err()
}

// Pairs collects a two-column result.
func (s *Store) Pairs(ctx context.Context, q string, args ...any) ([][2]string, error) {
	rows, err := s.Query(ctx, q, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out [][2]string
	for rows.Next() {
		var a, b sql.NullString
		if err := rows.Scan(&a, &b); err != nil {
			return nil, err
		}
		out = append(out, [2]string{a.String, b.String})
	}
	return out, rows.Err()
}

// Begin starts an explicit transaction on the pinned connection.
//
// SPEC invariant 6: ONE TRANSACTION per unit of work. Per-statement autocommit
// costs ~5-7 ms in EVERY access path, embedded included; wrapping the corpus
// import in one transaction is worth 17x (15.7 s -> 0.9 s) and is also exactly
// the boundary atomicity requires.
func (s *Store) Begin(ctx context.Context) (*sql.Tx, error) {
	return s.conn.BeginTx(ctx, nil)
}

// DoltCommit commits the working set. Dolt refuses an empty commit, which is how
// an idempotent re-import proves itself (W5): the second run has nothing to say.
func (s *Store) DoltCommit(ctx context.Context, msg string) (changed bool, err error) {
	if _, err := s.Exec(ctx, "CALL DOLT_ADD('-A')"); err != nil {
		return false, err
	}
	_, err = s.Exec(ctx, "CALL DOLT_COMMIT('-m', ?)", msg)
	if err != nil {
		if isNothingToCommit(err) {
			return false, nil
		}
		return false, err
	}
	return true, nil
}

func isNothingToCommit(err error) bool {
	m := strings.ToLower(err.Error())
	return strings.Contains(m, "nothing to commit") || strings.Contains(m, "no changes")
}

// isFKViolation reports whether an INSERT was refused by a foreign key.
//
// This is load-bearing, not cosmetic: the importer records every edge the FK
// refuses as a FINDING (see import.go). The prototype's lesson was the inverse
// — `INSERT IGNORE` downgrades FK violations to warnings and fakes a clean
// result, so it must never be used on an edge insert.
func isFKViolation(err error) bool {
	if err == nil {
		return false
	}
	m := strings.ToLower(err.Error())
	return strings.Contains(m, "foreign key") || strings.Contains(m, "fk_")
}

func isDuplicateKey(err error) bool {
	if err == nil {
		return false
	}
	m := strings.ToLower(err.Error())
	return strings.Contains(m, "duplicate primary key") ||
		strings.Contains(m, "duplicate entry") ||
		strings.Contains(m, "duplicate key")
}

func commitName() string {
	if v := os.Getenv("DATUM_COMMIT_NAME"); v != "" {
		return v
	}
	return "datum"
}

func commitEmail() string {
	if v := os.Getenv("DATUM_COMMIT_EMAIL"); v != "" {
		return v
	}
	return "datum@local"
}
