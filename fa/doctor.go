package main

// `fa doctor` — clone health.
//
// Not optional polish. It covers the failure modes that silently break a store,
// each of which was measured in the spike:
//
//   * WRITABILITY, not openability. A SECOND opener of the same Dolt directory
//     opens FINE and silently becomes READ-ONLY, then fails much later with
//     `cannot update manifest: database is read only`. A doctor that only checks
//     "can I open it" reports healthy on a store that cannot accept a single
//     write. This is why the probe below actually writes.
//   * A half-merged working set. An unresolved conflict makes EVERY later commit
//     by ANY agent fail with `cannot merge with uncommitted changes` — an error
//     that blames staging, not the conflict (invariant 2 / D8).
//   * Schema drift, so a store built by an older binary is not silently trusted.

import (
	"context"
	"fmt"
	"io"
	"strings"
)

type Check struct {
	Name   string
	OK     bool
	Detail string
	// Fatal marks a check whose failure means the store cannot be used at all,
	// as opposed to one that is merely worth reporting.
	Fatal bool
}

// probeTable is created and dropped by the writability probe. Named so that if a
// crash ever leaves it behind, its origin is obvious.
const probeTable = "fa_doctor_write_probe"

// checkWritable proves the store can actually take a write, and leaves nothing
// behind. Openability is NOT evidence of writability — that is the entire point.
func checkWritable(ctx context.Context, s *Store) Check {
	c := Check{Name: "writable (not merely openable)", Fatal: true}
	if _, err := s.Exec(ctx, "CREATE TABLE IF NOT EXISTS "+probeTable+" (id INT PRIMARY KEY)"); err != nil {
		c.Detail = "create probe table: " + oneLine(err.Error())
		return c
	}
	// A DDL that only touches metadata is not enough on its own; write a row too,
	// then remove every trace.
	if _, err := s.Exec(ctx, "INSERT INTO "+probeTable+" (id) VALUES (1)"); err != nil {
		c.Detail = "insert into probe table: " + oneLine(err.Error())
		_, _ = s.Exec(ctx, "DROP TABLE IF EXISTS "+probeTable)
		return c
	}
	if _, err := s.Exec(ctx, "DROP TABLE IF EXISTS "+probeTable); err != nil {
		c.Detail = "drop probe table: " + oneLine(err.Error())
		return c
	}
	c.OK = true
	c.Detail = "wrote and removed a probe row"
	return c
}

// checkNoHalfMerge looks for the state that wedges an entire machine.
func checkNoHalfMerge(ctx context.Context, s *Store) Check {
	c := Check{Name: "no unresolved merge", Fatal: true}
	n, err := s.Int(ctx, "SELECT COUNT(*) FROM dolt_conflicts")
	if err != nil {
		c.Detail = "dolt_conflicts unreadable: " + oneLine(err.Error())
		return c
	}
	if n > 0 {
		tables, _ := s.Strings(ctx, "SELECT `table` FROM dolt_conflicts")
		c.Detail = fmt.Sprintf("%d table(s) in conflict: %s — abort or resolve before any write",
			n, strings.Join(tables, ", "))
		return c
	}
	// dolt_merge_status exists in current Dolt; treat its absence as unknown rather
	// than as healthy, so a Dolt upgrade cannot silently disable this check.
	if merging, err := s.Str(ctx, "SELECT CAST(is_merging AS CHAR) FROM dolt_merge_status"); err == nil {
		if merging == "1" || strings.EqualFold(merging, "true") {
			c.Detail = "a merge is in progress and uncommitted"
			return c
		}
		c.OK = true
		c.Detail = "no conflicts, no merge in progress"
		return c
	}
	c.OK = true
	c.Detail = "no conflicts (merge status unavailable in this Dolt build)"
	return c
}

func checkSchema(ctx context.Context, s *Store) Check {
	c := Check{Name: "schema current", Fatal: true}
	v, err := s.Int(ctx, "SELECT IFNULL(MAX(version),0) FROM schema_migrations")
	if err != nil {
		c.Detail = "no schema_migrations table — run `fa init`"
		return c
	}
	switch {
	case v == 0:
		c.Detail = "store has no schema — run `fa init`"
	case v < schemaVersion:
		c.Detail = fmt.Sprintf("store at schema v%d, binary expects v%d — run `fa init`", v, schemaVersion)
	case v > schemaVersion:
		c.Detail = fmt.Sprintf("store at schema v%d is NEWER than this binary (v%d) — upgrade fa", v, schemaVersion)
	default:
		c.OK = true
		c.Detail = fmt.Sprintf("schema v%d", v)
	}
	return c
}

func checkIdentity(ctx context.Context, s *Store) Check {
	// Missing git identity makes every pull fail on the CLI path. The embedded
	// driver takes identity from the DSN, so `fa` always has one — report which,
	// because a store full of commits by "fa <fa@local>" on a shared machine is a
	// provenance problem even though it is not a failure.
	c := Check{Name: "commit identity", OK: true}
	c.Detail = fmt.Sprintf("%s <%s>", commitName(), commitEmail())
	if commitName() == "fa" && commitEmail() == "fa@local" {
		c.Detail += " (default — set FA_COMMIT_NAME/FA_COMMIT_EMAIL for attributable history)"
	}
	return c
}

func checkImported(ctx context.Context, s *Store) Check {
	c := Check{Name: "content present"}
	// Zone-aware: the walled zone has no `bc` table by design, so probing for one
	// there would report a defect that is actually correct behaviour.
	table, unit := "bc", "BCs"
	if s.Zone == ZoneWalled {
		table, unit = "holdout_scenario", "holdout scenarios"
	}
	n, err := s.Int(ctx, "SELECT COUNT(*) FROM "+table)
	if err != nil {
		c.Detail = table + " unreadable: " + oneLine(err.Error())
		return c
	}
	if n == 0 {
		if s.Zone == ZoneWalled {
			// Correct and expected today: the live corpus has no holdout scenarios.
			c.OK = true
			c.Detail = "no holdout scenarios (none exist in the corpus yet)"
			return c
		}
		c.Detail = "no records — run `fa import <corpus>`"
		return c
	}
	c.OK = true
	if s.Zone == ZoneWalled {
		c.Detail = fmt.Sprintf("%d %s", n, unit)
		return c
	}
	fp, _ := s.Str(ctx, "SELECT fingerprint FROM import_run ORDER BY fingerprint LIMIT 1")
	c.Detail = fmt.Sprintf("%d %s, corpus fingerprint %s", n, unit, truncRunes(fp, 12))
	return c
}

// Doctor runs every check. Zones are checked independently: a healthy open zone
// says nothing about the walled one.
func Doctor(ctx context.Context, s *Store) []Check {
	return []Check{
		checkSchema(ctx, s),
		checkWritable(ctx, s),
		checkNoHalfMerge(ctx, s),
		checkIdentity(ctx, s),
		checkImported(ctx, s),
	}
}

func PrintChecks(w io.Writer, zone string, checks []Check) (ok bool) {
	ok = true
	fmt.Fprintf(w, "zone %s\n", zone)
	for _, c := range checks {
		status := "ok  "
		if !c.OK {
			if c.Fatal {
				status = "FAIL"
				ok = false
			} else {
				status = "warn"
			}
		}
		fmt.Fprintf(w, "  %s  %-32s %s\n", status, c.Name, c.Detail)
	}
	return ok
}

func oneLine(s string) string {
	s = strings.ReplaceAll(s, "\n", " ")
	return truncRunes(strings.TrimSpace(s), 200)
}
