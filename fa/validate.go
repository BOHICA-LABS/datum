package main

// `fa validate` — the gates, as queries.
//
// A gate that IS a query cannot disagree with the data it checks (SPEC §3.3).
// That is the whole argument for moving them here: the corpus today gates itself
// with bash sweeps and a 269-line verify-sha-currency.sh, and it has still
// accumulated a BC total that four documents state four different ways.
//
// Every gate returns FINDINGS with a stable (rule, subject) identity, because the
// dated baseline allowlist keys on that pair (see baseline.go). A gate that
// reports "3 problems" without naming them cannot be baselined, and a gate that
// cannot be baselined gets switched off on its first red build.

import (
	"context"
	"fmt"
	"sort"
)

type Report struct {
	Findings []Finding
	Metrics  map[string]int64
	// CrossZone records whether the walled zone was actually inspected. A
	// cross-zone check that silently skipped is indistinguishable from one that
	// passed, so this is reported, never assumed.
	CrossZoneChecked bool
	CrossZoneSkipped string
}

type validator struct {
	ctx context.Context
	s   *Store
	rep *Report
}

func (v *validator) find(rule, subject, class, detail string) {
	v.rep.Findings = append(v.rep.Findings, Finding{Rule: rule, Subject: subject, Class: class, Detail: detail})
}

// Validate runs every gate against an imported store. walled may be nil, in which
// case the cross-zone pass is reported as SKIPPED rather than as passing.
func Validate(ctx context.Context, s *Store, walled *Store) (*Report, error) {
	rep := &Report{Metrics: map[string]int64{}}
	v := &validator{ctx: ctx, s: s, rep: rep}

	for _, gate := range []func() error{
		v.gateImportedFindings,
		v.gateCountAssertions,
		v.gateIndexEnumeration,
		v.gateDanglingEdges,
		v.gateMalformedIDs,
		v.gateDuplicateIDs,
		v.gatePrefixAgreement,
		v.gateScalarRefs,
		v.gateDependencyDirection,
		v.metrics,
	} {
		if err := gate(); err != nil {
			return nil, err
		}
	}
	if err := v.gateCrossZone(walled); err != nil {
		return nil, err
	}

	sort.Slice(rep.Findings, func(i, j int) bool {
		a, b := rep.Findings[i], rep.Findings[j]
		if a.Class != b.Class {
			return a.Class < b.Class
		}
		if a.Rule != b.Rule {
			return a.Rule < b.Rule
		}
		return a.Subject < b.Subject
	})
	return rep, nil
}

// gateImportedFindings replays what only the import path could observe: a value
// that is not an id, an id with prose glued on, and every edge a FOREIGN KEY
// refused (that row does not exist, so no query can find it afterwards).
func (v *validator) gateImportedFindings() error {
	rows, err := v.s.Query(v.ctx, `SELECT rule, subject, class, IFNULL(detail,''), occurrences
	                               FROM finding ORDER BY class, rule, subject`)
	if err != nil {
		return err
	}
	defer rows.Close()
	for rows.Next() {
		var f Finding
		var occ int
		if err := rows.Scan(&f.Rule, &f.Subject, &f.Class, &f.Detail, &occ); err != nil {
			return err
		}
		// Occurrences > 1 means the identical violation appears more than once
		// under one key; carry the count in the detail so the baseline entry stays
		// a single stable line.
		if occ > 1 {
			f.Detail = fmt.Sprintf("%s (x%d)", f.Detail, occ)
		}
		v.rep.Findings = append(v.rep.Findings, f)
	}
	return rows.Err()
}

// gateCountAssertions is the headline gate: every count the markdown STATES must
// equal COUNT(*). The live corpus states its BC total in several places and they
// disagree — 1949 / 1953 / 1955 against 1959 records on disk.
func (v *validator) gateCountAssertions() error {
	total, err := v.s.Int(v.ctx, `SELECT COUNT(*) FROM bc`)
	if err != nil {
		return err
	}
	rows, err := v.s.Query(v.ctx,
		`SELECT source, kind, subject, claimed FROM corpus_assertion ORDER BY kind, subject, source`)
	if err != nil {
		return err
	}
	type as struct {
		source, kind, subject string
		claimed               int64
	}
	var all []as
	for rows.Next() {
		var a as
		if err := rows.Scan(&a.source, &a.kind, &a.subject, &a.claimed); err != nil {
			rows.Close()
			return err
		}
		all = append(all, a)
	}
	rows.Close()
	if err := rows.Err(); err != nil {
		return err
	}

	for _, a := range all {
		var actual int64
		switch a.kind {
		case "bc_total":
			actual = total
		case "bc_count_ss":
			actual, err = v.s.Int(v.ctx, `SELECT COUNT(*) FROM bc WHERE ss_id = ?`, a.subject)
			if err != nil {
				return err
			}
		default:
			continue
		}
		if a.claimed != actual {
			subj := a.source
			if a.subject != "" {
				subj += " " + a.subject
			}
			v.find("a stated count disagrees with the records", subj, ClassCount,
				fmt.Sprintf("states %d, actual %d", a.claimed, actual))
		}
	}
	return nil
}

// gateIndexEnumeration checks the OTHER claim an index makes: which records exist.
// A count can be right while the list is wrong, and vice versa.
func (v *validator) gateIndexEnumeration() error {
	ghosts, err := v.s.Pairs(v.ctx, `SELECT e.id, e.source FROM index_entry e
	                                 LEFT JOIN bc b ON b.bc_id = e.id
	                                 WHERE e.kind='bc' AND b.bc_id IS NULL ORDER BY e.id`)
	if err != nil {
		return err
	}
	for _, g := range ghosts {
		v.find("an index enumerates a BC with no record", g[1]+" -> "+g[0], ClassDangling, "")
	}
	// Only meaningful once the index has been ingested at all.
	n, err := v.s.Int(v.ctx, `SELECT COUNT(*) FROM index_entry WHERE kind='bc'`)
	if err != nil {
		return err
	}
	if n == 0 {
		return nil
	}
	missing, err := v.s.Strings(v.ctx, `SELECT b.bc_id FROM bc b
	                                    LEFT JOIN index_entry e ON e.kind='bc' AND e.id = b.bc_id
	                                    WHERE e.id IS NULL ORDER BY b.bc_id`)
	if err != nil {
		return err
	}
	for _, id := range missing {
		v.find("a BC record is absent from the index", id, ClassDangling, "")
	}
	return nil
}

// edgeChecks are the FK-enforced relations. The FK already makes a dangling row
// unrepresentable, so these gates are expected to be silent — which is the point:
// they prove the guarantee holds rather than assuming it, and they are what would
// catch a future write path that bypassed the constraint.
var edgeChecks = []struct{ table, col, parent, parentCol string }{
	{"vp_bc", "bc_id", "bc", "bc_id"},
	{"vp_bc", "vp_id", "vp", "vp_id"},
	{"vp_di", "di_id", "domain_invariant", "di_id"},
	{"vp_nfr", "nfr_id", "nfr", "nfr_id"},
	{"vp_subsystem", "ss_id", "subsystem", "ss_id"},
	{"story_bc", "bc_id", "bc", "bc_id"},
	{"story_bc", "story_id", "story", "story_id"},
	{"story_vp", "vp_id", "vp", "vp_id"},
	{"story_fr", "fr_id", "fr", "fr_id"},
	{"story_subsystem", "ss_id", "subsystem", "ss_id"},
	{"story_dep", "dep_id", "story", "story_id"},
	{"bc_trace", "bc_id", "bc", "bc_id"},
	{"bc_trace", "vp_id", "vp", "vp_id"},
}

func (v *validator) gateDanglingEdges() error {
	for _, e := range edgeChecks {
		q := fmt.Sprintf(`SELECT c.%s FROM %s c LEFT JOIN %s p ON p.%s = c.%s
		                  WHERE p.%s IS NULL ORDER BY c.%s LIMIT 200`,
			e.col, e.table, e.parent, e.parentCol, e.col, e.parentCol, e.col)
		bad, err := v.s.Strings(v.ctx, q)
		if err != nil {
			return err
		}
		for _, id := range bad {
			v.find(fmt.Sprintf("dangling %s.%s -> %s", e.table, e.col, e.parent), id, ClassDangling, "")
		}
	}
	return nil
}

func (v *validator) gateMalformedIDs() error {
	checks := []struct{ table, col, pattern string }{
		{"bc", "bc_id", `^BC-[0-9]+\\.[0-9]+\\.[0-9]+$`},
		{"vp", "vp_id", `^VP-[0-9]+$`},
		{"story", "story_id", `^S-[0-9]+\\.[0-9]+$`},
		{"subsystem", "ss_id", `^SS-[0-9]+$`},
	}
	for _, c := range checks {
		q := fmt.Sprintf("SELECT %s FROM %s WHERE %s NOT REGEXP '%s' ORDER BY %s LIMIT 200",
			c.col, c.table, c.col, c.pattern, c.col)
		bad, err := v.s.Strings(v.ctx, q)
		if err != nil {
			return err
		}
		for _, id := range bad {
			v.find("malformed "+c.col, id, ClassIntegrity, "")
		}
	}
	return nil
}

// gateDuplicateIDs is the W8 "count agrees with itself" gate. Under a PRIMARY KEY
// it cannot fail — that is exactly what makes the corpus's four-way disagreement
// unrepresentable here, and it costs nothing to keep asserting.
func (v *validator) gateDuplicateIDs() error {
	for _, t := range []struct{ table, col string }{
		{"bc", "bc_id"}, {"vp", "vp_id"}, {"story", "story_id"}, {"subsystem", "ss_id"},
	} {
		n, err := v.s.Int(v.ctx, fmt.Sprintf("SELECT COUNT(*) - COUNT(DISTINCT %s) FROM %s", t.col, t.table))
		if err != nil {
			return err
		}
		if n != 0 {
			v.find("duplicate ids in "+t.table, fmt.Sprintf("%d duplicate(s)", n), ClassIntegrity, "")
		}
	}
	return nil
}

// gatePrefixAgreement: BC-S must match its subsystem's registered BC prefix.
// Five BCs currently live in a subsystem whose prefix their id contradicts.
func (v *validator) gatePrefixAgreement() error {
	rows, err := v.s.Query(v.ctx, `SELECT b.bc_id, b.ss_id, s.bc_prefix
	                               FROM bc b JOIN subsystem s ON s.ss_id = b.ss_id
	                               WHERE CAST(SUBSTRING_INDEX(SUBSTRING(b.bc_id,4),'.',1) AS UNSIGNED) <> s.bc_prefix
	                               ORDER BY b.bc_id`)
	if err != nil {
		return err
	}
	defer rows.Close()
	for rows.Next() {
		var id, ss string
		var prefix int
		if err := rows.Scan(&id, &ss, &prefix); err != nil {
			return err
		}
		v.find("bc id prefix disagrees with its subsystem", id+" -> "+ss, ClassIntegrity,
			fmt.Sprintf("%s registers prefix BC-%d", ss, prefix))
	}
	return rows.Err()
}

// gateScalarRefs covers the reference-shaped SCALAR columns. They are not FKs
// because the corpus fills them with prose often enough that an FK would refuse
// the import; the reference is validated here instead of being coerced silently.
func (v *validator) gateScalarRefs() error {
	checks := []struct {
		rule, query string
	}{
		{"bc.capability -> missing CAP", `SELECT b.bc_id, b.capability FROM bc b
			LEFT JOIN capability c ON c.cap_id = b.capability
			WHERE b.capability IS NOT NULL AND c.cap_id IS NULL ORDER BY b.bc_id`},
		{"bc.replacement -> missing BC", `SELECT b.bc_id, b.replacement FROM bc b
			LEFT JOIN bc r ON r.bc_id = b.replacement
			WHERE b.replacement IS NOT NULL AND r.bc_id IS NULL ORDER BY b.bc_id`},
		{"story.epic_id -> missing epic", `SELECT s.story_id, s.epic_id FROM story s
			LEFT JOIN epic e ON e.epic_id = s.epic_id
			WHERE s.epic_id IS NOT NULL AND e.epic_id IS NULL ORDER BY s.story_id`},
		{"vp.scope -> missing SS", `SELECT v.vp_id, v.scope FROM vp v
			LEFT JOIN subsystem s ON s.ss_id = v.scope
			WHERE v.scope IS NOT NULL AND s.ss_id IS NULL ORDER BY v.vp_id`},
		{"vp.source_bc -> missing BC", `SELECT v.vp_id, v.source_bc FROM vp v
			LEFT JOIN bc b ON b.bc_id = v.source_bc
			WHERE v.source_bc IS NOT NULL AND b.bc_id IS NULL ORDER BY v.vp_id`},
	}
	for _, c := range checks {
		pairs, err := v.s.Pairs(v.ctx, c.query)
		if err != nil {
			return err
		}
		for _, p := range pairs {
			v.find(c.rule, p[0]+" -> "+truncRunes(p[1], 60), ClassDangling, "")
		}
	}
	return nil
}

// gateDependencyDirection: the corpus maintains `blocks` and `depends_on` by hand,
// as two independent lists of one fact. Where only one side records an edge, the
// two disagree — the exact drift class a single stored direction makes impossible.
func (v *validator) gateDependencyDirection() error {
	rows, err := v.s.Query(v.ctx, `SELECT d.story_id, d.dep_id, d.kind FROM story_dep d
	                               WHERE NOT EXISTS (
	                                 SELECT 1 FROM story_dep r
	                                 WHERE r.story_id = d.dep_id AND r.dep_id = d.story_id AND r.kind <> d.kind)
	                               ORDER BY d.story_id, d.dep_id, d.kind`)
	if err != nil {
		return err
	}
	defer rows.Close()
	for rows.Next() {
		var a, b, kind string
		if err := rows.Scan(&a, &b, &kind); err != nil {
			return err
		}
		v.find("dependency recorded in one direction only", fmt.Sprintf("%s %s %s", a, kind, b),
			ClassDirection, "the reverse edge is absent")
	}
	return rows.Err()
}

// gateCrossZone is the guarantee D2 gives up and this tool buys back.
//
// Trust zones are separate database DIRECTORIES, so a walled artifact CANNOT hold
// a foreign key to the open-zone record it references (A6). Nothing else in the
// system will ever notice that reference going stale, which is why D2 makes this
// pass a required deliverable rather than an optional extra.
//
// It runs privileged — it is the one caller that opens both zones — and it reports
// ONLY ids and counts. Walled CONTENT (a holdout expectation) is never read, so
// the check cannot become a side channel around the wall it is protecting.
func (v *validator) gateCrossZone(walled *Store) error {
	if walled == nil {
		v.rep.CrossZoneSkipped = "walled zone not present"
		return nil
	}
	v.rep.CrossZoneChecked = true

	// Deliberately SELECTs hs_id and bc_id only — never `expectation`.
	refs, err := walled.Pairs(v.ctx, `SELECT hs_id, bc_id FROM hs_bc ORDER BY hs_id, bc_id`)
	if err != nil {
		return fmt.Errorf("walled zone read: %w", err)
	}
	v.rep.Metrics["cross_zone_refs"] = int64(len(refs))
	if len(refs) == 0 {
		return nil
	}
	known := map[string]bool{}
	ids, err := v.s.Strings(v.ctx, `SELECT bc_id FROM bc`)
	if err != nil {
		return err
	}
	for _, id := range ids {
		known[id] = true
	}
	for _, r := range refs {
		if !known[r[1]] {
			v.find("cross-zone: holdout scenario references a missing BC", r[0]+" -> "+r[1], ClassCrossZone,
				"walled -> open reference cannot be a foreign key (D2)")
		}
	}
	return nil
}

// metrics collects the numbers a human wants next to a verdict. They are NOT
// findings: 90.2% of BCs having no verifying VP is a coverage fact about the
// project, not a violation of a rule, and mixing the two would make the gate
// unratchetable.
func (v *validator) metrics() error {
	for name, q := range map[string]string{
		"bc":               `SELECT COUNT(*) FROM bc`,
		"vp":               `SELECT COUNT(*) FROM vp`,
		"story":            `SELECT COUNT(*) FROM story`,
		"subsystem":        `SELECT COUNT(*) FROM subsystem`,
		"edges":            `SELECT (SELECT COUNT(*) FROM vp_bc)+(SELECT COUNT(*) FROM vp_di)+(SELECT COUNT(*) FROM vp_nfr)+(SELECT COUNT(*) FROM vp_subsystem)+(SELECT COUNT(*) FROM story_bc)+(SELECT COUNT(*) FROM story_vp)+(SELECT COUNT(*) FROM story_fr)+(SELECT COUNT(*) FROM story_subsystem)+(SELECT COUNT(*) FROM story_dep)+(SELECT COUNT(*) FROM bc_trace)`,
		"bc_without_vp":    `SELECT COUNT(*) FROM bc b WHERE NOT EXISTS (SELECT 1 FROM vp_bc x WHERE x.bc_id=b.bc_id)`,
		"bc_without_story": `SELECT COUNT(*) FROM bc b WHERE NOT EXISTS (SELECT 1 FROM story_bc x WHERE x.bc_id=b.bc_id)`,
	} {
		n, err := v.s.Int(v.ctx, q)
		if err != nil {
			return fmt.Errorf("metric %s: %w", name, err)
		}
		v.rep.Metrics[name] = n
	}
	return nil
}

// ByClass counts findings per class, for the report header.
func ByClass(fs []Finding) map[string]int {
	out := map[string]int{}
	for _, f := range fs {
		out[f.Class]++
	}
	return out
}

// ByRule counts findings per rule, sorted descending then by name.
func ByRule(fs []Finding) []struct {
	Rule  string
	Class string
	N     int
} {
	type key struct{ rule, class string }
	m := map[key]int{}
	for _, f := range fs {
		m[key{f.Rule, f.Class}]++
	}
	out := make([]struct {
		Rule  string
		Class string
		N     int
	}, 0, len(m))
	for k, n := range m {
		out = append(out, struct {
			Rule  string
			Class string
			N     int
		}{k.rule, k.class, n})
	}
	sort.Slice(out, func(i, j int) bool {
		if out[i].N != out[j].N {
			return out[i].N > out[j].N
		}
		return out[i].Rule < out[j].Rule
	})
	return out
}
