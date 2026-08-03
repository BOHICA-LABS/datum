package main

// STORY 12a — mint AC / EC / PC / T-task as ROWS with TYPED LINKS.
//
// These four are the only declared `prose_ref_kinds` with no owning story: `finding` became
// rows in story 4, `decision`/`lesson` are story 6's ledgers, `policy` is already a config
// file. Measured at 14,662 references, and worth 36.8% of the adversary's class-C findings
// (7 of 19 hand-classified — research/PROSE-REFS-OR-FIELDS.md).
//
// WHY ROWS RATHER THAN A PROSE RESOLVER. 18.4% of prose reference candidates are
// `unresolvable` — the text never says WHOSE `AC-005` it is — and 7.5% have no definition
// anywhere. A permanent extractor is structurally unable to adjudicate ~26% of what it finds.
// A row keyed `(owner_key, kind, sub_id)` makes that ambiguity IMPOSSIBLE instead of detected,
// which is the same argument that made story 7 the highest-value change.
//
// THE PAYOFF, concretely. `POLICY 8 violation: 5 stories have AC traces to BCs not in bcs:
// frontmatter` is a real class-C finding that today requires reading a body table and comparing
// it to frontmatter. With AC rows carrying typed bc links it is a JOIN — see
// gateACTracesAgainstStoryBCs.
//
// Extraction is the MIGRATION instrument here, not the permanent gate: once these are rows the
// prose form is what gets retired.

import (
	"fmt"
	"path/filepath"
	"regexp"
	"strings"
)

// SubArtifactRow is one AC / EC / PC / T-task.
//
// The key is COMPOSITE and scoped to its owner, exactly as prose_ref_rules
// scope-sub-artifact-ids requires: `AC-002` is not globally unique, so its identity is
// (owning artifact, kind, id). Story 4 reached the same conclusion for finding ids.
type SubArtifactRow struct {
	OwnerKey  string
	OwnerType string
	Kind      string // ac | ec | pc | t_task
	SubID     string
	Statement string
	Form      string // heading | table-row
	Line      int
}

// SubArtifactRef is a TYPED link out of a sub-artifact — the thing that turns a prose trace
// into a join. Clause carries the sub-element the trace names ("postcondition 1"), which is
// what `AC-005 mis-anchors ... to BC-7.03.081 (identity) vs BC-7.03.082 (emit_event)` is about.
type SubArtifactRef struct {
	OwnerKey   string
	Kind       string
	SubID      string
	TargetKind string // bc | vp | adr | fr
	TargetID   string
	Clause     string
}

var (
	// Two authored forms, both measured in the corpus:
	//   `### AC-001: <statement>`            heading form
	//   `| AC-1 | <statement> | <trace> |`   table-row form, where a later cell holds the trace
	subHeadingRe = regexp.MustCompile(`^#{2,6}\s+\*{0,2}(AC-\d+[a-z]?|EC-\d+|PC-?\d+|T-\d+)\*{0,2}\s*[:\x{2014}\x{2013}\-]?\s*(.*)$`)
	subRowRe     = regexp.MustCompile(`^\|\s*\*{0,2}(AC-\d+[a-z]?|EC-\d+|PC-?\d+|T-\d+)\*{0,2}\s*\|(.+)$`)

	bcIDRe  = regexp.MustCompile(`BC-\d+\.\d+\.\d+`)
	vpIDRe  = regexp.MustCompile(`VP-\d+`)
	adrIDRe = regexp.MustCompile(`ADR-\d+`)
	frIDRe  = regexp.MustCompile(`FR-[A-Za-z0-9.\-]+`)

	// The clause a trace names inside its target. Kept because the mis-anchor class is about
	// WHICH clause, not whether the target exists.
	clauseRe = regexp.MustCompile(`(?i)\b((?:pre|post)condition|invariant|inv|EC|PC)\s*-?\s*(\d+)`)

	// prose_ref_rules a-declared-gap-is-not-a-trace.
	gapMarkerRe = regexp.MustCompile(`(?i)\[process-gap\]|\bcandidate\b|\buncontracted\b|` +
		`\bproposed\b|\bwould need\b|\bdoes not exist\b|\bno existing\b`)

	// prose_ref_rules an-id-with-a-name-suffix-is-a-proposed-NAME. A full BC id followed by
	// `-<word>` names a contract that does not exist yet.
	idNameSuffixRe = regexp.MustCompile(`^BC-\d+\.\d+\.\d+-[A-Za-z]`)
)

// kindOf maps an id to its declared kind. `PC-?\d+` covers both PC2 and PC-2, so normalise.
func subKindOf(id string) (kind, norm string) {
	switch {
	case strings.HasPrefix(id, "AC-"):
		return "ac", id
	case strings.HasPrefix(id, "EC-"):
		return "ec", id
	case strings.HasPrefix(id, "PC"):
		// PC2 and PC-2 are the same precondition; the key must not depend on the spelling.
		return "pc", "PC-" + strings.TrimLeft(strings.TrimPrefix(id, "PC"), "-")
	case strings.HasPrefix(id, "T-"):
		return "t_task", id
	}
	return "", id
}

// ExtractSubArtifacts pulls every sub-artifact and its typed links out of one document body.
//
// Returns dupes, which the caller must REPORT: a sub-artifact stated as a heading AND repeated
// in a trace table is ONE sub-artifact, the same lesson story 4 learned when counting mentions
// gave exactly 2x the asserted distribution.
func ExtractSubArtifacts(ownerKey, ownerType, body string) (rows []SubArtifactRow, refs []SubArtifactRef, dupes int) {
	lines := strings.Split(body, "\n")
	inFence := false
	seen := map[string]int{} // key -> index into rows

	for i, raw := range lines {
		ln := strings.TrimRight(raw, "\r")
		if fenceRe.MatchString(ln) {
			inFence = !inFence
			continue
		}
		// prose_ref_rules exclude-code-spans: a candidate inside a fence is not a reference,
		// and it is not a definition either.
		if inFence {
			continue
		}

		var id, rest, form string
		if m := subHeadingRe.FindStringSubmatch(ln); m != nil {
			id, rest, form = m[1], m[2], "heading"
		} else if m := subRowRe.FindStringSubmatch(ln); m != nil {
			id, rest, form = m[1], m[2], "table-row"
		} else {
			continue
		}
		kind, norm := subKindOf(id)
		if kind == "" {
			continue
		}

		cells := []string{rest}
		if form == "table-row" {
			cells = SplitMDCells("|" + rest)
		}
		statement := ""
		for _, c := range cells {
			if s := NormalizeCell(c); s != "" {
				statement = s
				break
			}
		}

		key := kind + "\x00" + norm
		if idx, ok := seen[key]; ok {
			dupes++
			// The heading form wins: it is where the statement lives. Its links still merge,
			// because a trace table repeating the id is where the trace usually IS.
			if form == "heading" && rows[idx].Form != "heading" {
				rows[idx].Form, rows[idx].Statement, rows[idx].Line = form, statement, i + 1
			}
		} else {
			seen[key] = len(rows)
			rows = append(rows, SubArtifactRow{OwnerKey: ownerKey, OwnerType: ownerType,
				Kind: kind, SubID: norm, Statement: truncRunes(statement, 2000), Form: form, Line: i + 1})
		}

		// TYPED LINKS. Scan every cell AFTER the id cell, plus the heading remainder: a trace
		// lives in a later column (`| AC-1 | statement | BC-9.01.001 postcondition 1 |`) or in
		// the heading's parenthetical (`### AC-001: ... (traces to ADR-015 Wave 0)`).
		for _, c := range cells {
			masked := maskCodeSpans(c)
			// prose_ref_rules a-declared-gap-is-not-a-trace. A cell that marks itself as a
			// gap is not asserting a trace to an existing artifact, and reading it as one
			// blames the document for correctly documenting the gap. Measured: this single
			// rule accounts for 50 of the 53 dangling-trace findings and 55 POLICY-8 ones.
			if gapMarkerRe.MatchString(masked) {
				continue
			}
			clause := ""
			if cm := clauseRe.FindStringSubmatch(masked); cm != nil {
				clause = strings.ToLower(cm[1]) + " " + cm[2]
			}
			for _, tgt := range []struct {
				kind string
				re   *regexp.Regexp
			}{{"bc", bcIDRe}, {"vp", vpIDRe}, {"adr", adrIDRe}, {"fr", frIDRe}} {
				for _, loc := range tgt.re.FindAllStringIndex(masked, -1) {
					t := masked[loc[0]:loc[1]]
					// A proposed NAME, not a reference: check the ORIGINAL text from the
					// match onward, because the id itself stops before the suffix.
					if idNameSuffixRe.MatchString(masked[loc[0]:]) {
						continue
					}
					refs = append(refs, SubArtifactRef{OwnerKey: ownerKey, Kind: kind,
						SubID: norm, TargetKind: tgt.kind, TargetID: t, Clause: clause})
				}
			}
		}
	}
	return rows, refs, dupes
}

// maskCodeSpans blanks backtick spans while PRESERVING LENGTH, so a match offset still means
// what it meant. prose_ref_rules exclude-code-spans, measured: `ADR-099` appears as an example
// CLI argument inside a code span, and a flat scan reports it as a dangling reference.
func maskCodeSpans(s string) string {
	out := []byte(s)
	inSpan := false
	for i := 0; i < len(out); i++ {
		if out[i] == '`' {
			inSpan = !inSpan
			out[i] = ' '
			continue
		}
		if inSpan {
			out[i] = ' '
		}
	}
	return string(out)
}

// loadSubArtifacts walks stories (AC, T-task) and behavioral contracts (EC, PC).
//
// The owner set is DECLARED, not guessed: prose_ref_kinds gives each kind an `owner_types`
// list, so scanning every document for `AC-\d+` would collect citations rather than
// definitions — which is the distinction that made 18.4% of prose candidates unresolvable in
// the first place.
func (c *Corpus) loadSubArtifacts() {
	type src struct {
		dir, ownerType string
		re             *regexp.Regexp
	}
	for _, s := range []src{
		{filepath.Join(c.Root, "stories"), "story", reStoryFile},
		{filepath.Join(c.Root, "specs", "behavioral-contracts"), "behavioral-contract", reBCFile},
	} {
		walkMD(s.dir, s.re, func(path, base string) {
			m := s.re.FindStringSubmatch(base)
			if m == nil {
				return
			}
			owner := strings.TrimRight(m[1], ".")
			text, ok := read(path)
			if !ok {
				return
			}
			fm, body := ParseFrontmatter(text)
			if fm != nil {
				if id := fm.Scalar("story_id"); id != "" && s.ownerType == "story" {
					owner = id
				}
			}
			rows, refs, dupes := ExtractSubArtifacts(owner, s.ownerType, body)
			c.SubArtifacts = append(c.SubArtifacts, rows...)
			c.SubArtifactRefs = append(c.SubArtifactRefs, refs...)
			c.SubArtifactDupes += dupes
		})
	}
}

// ── the gates 12a buys ───────────────────────────────────────────────────────

// gateACTracesAgainstStoryBCs IS the finding `POLICY 8 violation: 5 stories have AC traces to
// BCs not in bcs: frontmatter`, expressed as a join.
//
// Today that finding requires reading a body table and comparing it to frontmatter by eye,
// which is why FSTAR classified it as needing prose extraction. With AC rows carrying typed bc
// links it is one query, and the disagreement it reports is between two things the store holds.
func (v *validator) gateACTracesAgainstStoryBCs() error {
	n, err := v.s.Int(v.ctx, `SELECT COUNT(*) FROM sub_artifact`)
	if err != nil || n == 0 {
		return err
	}
	rows, err := v.s.Query(v.ctx, `
		SELECT r.owner_key, r.sub_id, r.target_id
		  FROM sub_artifact_ref r
		  JOIN story s ON s.story_id = r.owner_key
		 WHERE r.kind = 'ac' AND r.target_kind = 'bc'
		   AND NOT EXISTS (SELECT 1 FROM story_bc b
		                    WHERE b.story_id = r.owner_key AND b.bc_id = r.target_id)
		 GROUP BY r.owner_key, r.sub_id, r.target_id
		 ORDER BY r.owner_key, r.sub_id, r.target_id`)
	if err != nil {
		return err
	}
	defer rows.Close()
	for rows.Next() {
		var story, ac, bc string
		if err := rows.Scan(&story, &ac, &bc); err != nil {
			return err
		}
		v.find("an AC traces to a BC the story does not declare (POLICY 8)",
			story+" "+ac+" -> "+bc, ClassDangling,
			"the AC's trace names this BC; the story's behavioral_contracts frontmatter does not")
	}
	return rows.Err()
}

// gateSubArtifactRefsResolve reports a typed link whose TARGET does not exist.
//
// Reported as DANGLING, distinct from `unresolvable`: here the owner IS known (it is the row's
// own owner) and the target is simply absent. prose_ref_rules report-unresolvable-separately
// exists because collapsing those two is "how a prose extractor produces a large, confident,
// wrong finding set" — and rows are what make the distinction structural rather than heuristic.
func (v *validator) gateSubArtifactRefsResolve() error {
	n, err := v.s.Int(v.ctx, `SELECT COUNT(*) FROM sub_artifact_ref`)
	if err != nil || n == 0 {
		return err
	}
	for _, chk := range []struct{ target, table, col string }{
		{"bc", "bc", "bc_id"},
		{"vp", "vp", "vp_id"},
		{"adr", "adr", "adr_id"},
	} {
		q := fmt.Sprintf(`SELECT r.owner_key, r.kind, r.sub_id, r.target_id
		                    FROM sub_artifact_ref r
		                    LEFT JOIN %s t ON t.%s = r.target_id
		                   WHERE r.target_kind = ? AND t.%s IS NULL
		                   GROUP BY r.owner_key, r.kind, r.sub_id, r.target_id
		                   ORDER BY r.owner_key, r.sub_id LIMIT 300`, chk.table, chk.col, chk.col)
		rows, err := v.s.Query(v.ctx, q, chk.target)
		if err != nil {
			return err
		}
		for rows.Next() {
			var owner, kind, sub, tgt string
			if err := rows.Scan(&owner, &kind, &sub, &tgt); err != nil {
				rows.Close()
				return err
			}
			v.find(fmt.Sprintf("a %s trace names a %s with no record", kind, chk.target),
				owner+" "+sub+" -> "+tgt, ClassDangling, "")
		}
		rows.Close()
		if err := rows.Err(); err != nil {
			return err
		}
	}
	return nil
}
