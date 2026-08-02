package main

// `fa refs` — list prose references and version cites from the store.
//
// Exists because SAMPLING REQUIRES LISTING. The 329 `dangling` section references are reported
// in aggregate precisely because their owner attribution is unmeasured, and that precision
// cannot be measured without reading the rows. Re-deriving them in a script would create a
// second source of truth for the extraction — the defect this repo has now fixed three times.
//
// Read-only.

import (
	"context"
	"encoding/csv"
	"flag"
	"fmt"
	"os"
	"strconv"
)

func cmdRefs(ctx context.Context, args []string) error {
	fs := flag.NewFlagSet("refs", flag.ExitOnError)
	db := fs.String("db", defaultDB(), "store root")
	kind := fs.String("kind", "section", "section | version-cite")
	status := fs.String("status", "", "filter: resolved | dangling | unresolvable (section), or a verdict")
	limit := fs.Int("limit", 0, "0 = all")
	_ = fs.Parse(args)

	s, err := Open(ctx, *db, ZoneOpen, false)
	if err != nil {
		return err
	}
	defer s.Close()

	w := csv.NewWriter(os.Stdout)
	defer w.Flush()

	switch *kind {
	case "section":
		q := `SELECT citing_key, raw, target, section_ord, status, src_line FROM prose_ref WHERE kind='section'`
		var a []any
		if *status != "" {
			q += ` AND status = ?`
			a = append(a, *status)
		}
		q += ` ORDER BY citing_key, src_line`
		if *limit > 0 {
			q += ` LIMIT ` + strconv.Itoa(*limit)
		}
		rows, err := s.Query(ctx, q, a...)
		if err != nil {
			return err
		}
		defer rows.Close()
		_ = w.Write([]string{"citing_key", "raw", "target", "section_ord", "status", "line"})
		for rows.Next() {
			var k, raw, tgt, st string
			var ord, line int
			if err := rows.Scan(&k, &raw, &tgt, &ord, &st, &line); err != nil {
				return err
			}
			_ = w.Write([]string{k, raw, tgt, strconv.Itoa(ord), st, strconv.Itoa(line)})
		}
		return rows.Err()

	case "version-cite":
		q := `SELECT citing_key, citing_type, target, cited_version, pin_policy, verdict, src_line FROM version_cite`
		var a []any
		if *status != "" {
			q += ` WHERE verdict = ?`
			a = append(a, *status)
		}
		q += ` ORDER BY verdict, citing_key`
		if *limit > 0 {
			q += ` LIMIT ` + strconv.Itoa(*limit)
		}
		rows, err := s.Query(ctx, q, a...)
		if err != nil {
			return err
		}
		defer rows.Close()
		_ = w.Write([]string{"citing_key", "citing_type", "target", "cited", "pin_policy", "verdict", "line"})
		for rows.Next() {
			var k, ct, tgt, cv, pp, vd string
			var line int
			if err := rows.Scan(&k, &ct, &tgt, &cv, &pp, &vd, &line); err != nil {
				return err
			}
			_ = w.Write([]string{k, ct, tgt, cv, pp, vd, strconv.Itoa(line)})
		}
		return rows.Err()
	}
	return fmt.Errorf("unknown --kind %q (want section or version-cite)", *kind)
}
