package main

// `fa shadow` — STORY 7, the SHADOW stage of `generate -> prove equal -> retire`.
//
// The single highest-value change the F-* measurement identified: 25.3% (±9.1) of the
// adversary's findings are derived data disagreeing with its source, and a derived index
// makes them IMPOSSIBLE rather than detectable (research/FSTAR-COMPARISON.md class A).
//
// THIS COMMAND NEVER WRITES. That is the whole discipline taken from #671: a derived type is
// not FLIPPED to derived, because if the generator is subtly wrong then hand-maintained drift
// is replaced by GENERATED drift and the evidence that would have caught it is gone. So:
//
//	shadow   generate alongside the authored form; every disagreement is a finding   <- HERE
//	proven   they agree; `fa render` writes it; the authored one is still diffed
//	retired  the authored one is deleted
//
// A type may only advance on evidence, and `derivation_stage` in the registry is where the
// stage lives. This command REFUSES to run against a type whose stage is not `shadow`,
// rather than quietly doing the same thing at every stage.
//
// Scope note, so the two gates are not confused. `fa validate` already compares the COUNTS
// the markdown asserts against COUNT(*) (gateCountAssertions) and the BC ids BC-INDEX
// enumerates against the bc table (gateIndexEnumeration). This adds the layer neither
// reaches: the CELL CONTENT of every index row. That is where the measured drift lives —
// 330 Capability cells, 10 Status cells and 5 Title cells in BC-INDEX alone, none of which a
// count or an id-set comparison can see.

import (
	"context"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
)

// ClassShadow keeps shadow findings separately baselineable, so `advisory -> warn -> block`
// can graduate one index at a time (the graduation ladder is per type, never global).
const ClassShadow = "shadow"

// ColKind selects the comparison rule for a column. The kind is DECLARED per column rather
// than sniffed from the value, because sniffing is how `TBD` ends up meaning three things.
type ColKind int

const (
	// ColEnum is a short token, possibly carrying a bracketed prose annotation.
	ColEnum ColKind = iota
	// ColTitle is prose. Equal / prefix-related / different are three distinct outcomes:
	// the index legitimately abbreviates (47 story rows) and legitimately elaborates with a
	// version annotation (VP-070/073/074), and neither is the same event as VP-072's title
	// being about a different property altogether.
	ColTitle
	// ColID is an identifier: compared exactly after de-linking.
	ColID
	// ColCount is a number, possibly followed by prose.
	ColCount
	// ColSet is a comma-separated set; ORDER IS NOT A CLAIM.
	ColSet
	// ColCountOrSet is a column whose TYPE varies by table. STORY-INDEX's `BCs` column
	// holds a count (`26`) in the E-1 tables and a LIST
	// (`[BC-1.11.002, BC-1.12.001, ...]`) in the E-10 tables. Declaring it a count
	// produced 62 findings that said "states no number" about cells that state the
	// membership explicitly — a stricter claim than the count, not a missing one.
	//
	// This is the column-level form of the lesson the header parsing already encodes:
	// what varies between tables in one document is not only WHICH columns exist but
	// what a given column MEANS.
	ColCountOrSet
	// ColUnderivable is declared but has no source in the store today. Reported as a
	// COVERAGE GAP, never compared. A shadow that silently skipped such a column would
	// overstate what it proves — the failure mode this whole spike keeps catching.
	ColUnderivable
)

type ShadowColumn struct {
	Name string
	Kind ColKind
	// Field is the record field the derived value comes from. Empty for ColUnderivable.
	Field string
	// Why documents an underivable column, so the gap is legible rather than silent.
	Why string
}

// ShadowSpec declares one authored document, which of its tables to read, and how each
// column derives. `Type` must sit at `derivation_stage: shadow` in the registry.
type ShadowSpec struct {
	Type      string // registry type name
	Path      string // corpus-relative path of the authored document
	Universe  string // which record set the rows key into: bc | vp | story
	KeyColumn string
	// RequireHeader identifies the tables to read: a table qualifies when it carries
	// every one of these columns. Deliberately a SUBSET test, not equality — STORY-INDEX
	// carries five distinct header signatures over its 18 story tables.
	RequireHeader []string
	Columns       []ShadowColumn

	// ExcludeSrcPrefix narrows the DERIVED side to the records the index is ABOUT.
	//
	// This is the most consequential thing the shadow stage surfaced, and it is a
	// property of the derived TYPE rather than of any cell: the store holds 148 stories,
	// 41 of which live in `stories/v1.0-legacy/` and are a superseded generation that
	// STORY-INDEX deliberately does not enumerate (verified: the set of records "absent
	// from the index" is EXACTLY the set of files in that directory, 41 == 41).
	//
	// Generating the index from every record would therefore have RESURRECTED 41 retired
	// stories while every count still agreed. So a derived index needs a declared scope
	// predicate, or derivation silently changes the document's meaning — which is the
	// failure mode `generate -> prove equal -> retire` exists to catch, caught here at
	// the shadow stage exactly as intended.
	ExcludeSrcPrefix []string
	ExcludeWhy       string
}

// shadowSpecs is the declared set. Every column here was measured first by
// registry/probe_indexes.py; a column with no measured agreement shape is not listed.
var shadowSpecs = []ShadowSpec{
	{
		Type: "behavioral-contract-index", Path: "specs/behavioral-contracts/BC-INDEX.md",
		Universe: "bc", KeyColumn: "BC ID", RequireHeader: []string{"BC ID", "Title", "Status"},
		Columns: []ShadowColumn{
			{Name: "Title", Kind: ColTitle, Field: "title"},
			{Name: "Status", Kind: ColEnum, Field: "status"},
			{Name: "Capability", Kind: ColID, Field: "capability"},
			{Name: "Stories", Kind: ColSet, Field: "stories"},
		},
	},
	{
		Type: "verification-property-index", Path: "specs/verification-properties/VP-INDEX.md",
		Universe: "vp", KeyColumn: "VP ID", RequireHeader: []string{"VP ID", "Title"},
		Columns: []ShadowColumn{
			{Name: "Title", Kind: ColTitle, Field: "title"},
			{Name: "Type", Kind: ColEnum, Field: "vp_type"},
			{Name: "Proof Method", Kind: ColEnum, Field: "proof_method"},
			// Scope derives from the vp_subsystem EDGES, not from vp.scope. The column is
			// declared scalar and the corpus writes `SS-01, SS-03`, so the importer
			// already records the multi-value case as edges and leaves the scalar empty
			// (and files a type finding). Reading the scalar reported 16 VPs as "the index
			// states a value the store does not hold" when the store held it all along, in
			// the table modelled for exactly that purpose.
			{Name: "Scope", Kind: ColSet, Field: "subsystems"},
			{Name: "Domain Invariant", Kind: ColSet, Field: "dis"},
			// The vp table has no status column, so this is a STORE gap, not corpus drift.
			// Measured 100% agreement against the FILES, which is exactly why leaving it
			// silently uncompared would misrepresent the shadow's coverage.
			{Name: "Status", Kind: ColUnderivable,
				Why: "the vp table carries no status column; the field is only in the file's frontmatter"},
		},
	},
	{
		Type: "story-index", Path: "stories/STORY-INDEX.md",
		Universe: "story", KeyColumn: "Story ID", RequireHeader: []string{"Story ID", "Status"},
		Columns: []ShadowColumn{
			{Name: "Title", Kind: ColTitle, Field: "title"},
			{Name: "Status", Kind: ColEnum, Field: "status"},
			{Name: "Epic", Kind: ColID, Field: "epic_id"},
			{Name: "Points", Kind: ColEnum, Field: "points"},
			{Name: "Priority", Kind: ColEnum, Field: "priority"},
			{Name: "BCs", Kind: ColCountOrSet, Field: "bcs"},
		},
		ExcludeSrcPrefix: []string{"stories/v1.0-legacy/"},
		ExcludeWhy: "stories/v1.0-legacy/ is a superseded story generation (41 records) that " +
			"STORY-INDEX deliberately does not enumerate; deriving without this scope would " +
			"resurrect all 41",
	},
}

// ── the derived side: records out of the store ────────────────────────────────

// shadowRecords loads one universe as key -> field -> value, from the STORE. Deriving from
// the store rather than re-reading the corpus is the point: the store is what a derived
// index would be generated from, so a shadow that read the files would prove nothing about
// the generator that eventually replaces them.
func shadowRecords(ctx context.Context, s *Store, universe string) (map[string]map[string]string, error) {
	out := map[string]map[string]string{}

	switch universe {
	case "bc":
		rows, err := s.Query(ctx, `SELECT bc_id, title, IFNULL(status,''), IFNULL(lifecycle_status,''),
		                                  IFNULL(capability,''), ss_id, version FROM bc`)
		if err != nil {
			return nil, err
		}
		for rows.Next() {
			var id, title, st, life, cap, ss, ver string
			if err := rows.Scan(&id, &title, &st, &life, &cap, &ss, &ver); err != nil {
				rows.Close()
				return nil, err
			}
			out[id] = map[string]string{"title": title, "status": st, "lifecycle_status": life,
				"capability": cap, "ss_id": ss, "version": ver}
		}
		rows.Close()
		if err := rows.Err(); err != nil {
			return nil, err
		}
		if err := attachSet(ctx, s, out, `SELECT bc_id, story_id FROM story_bc`, "stories"); err != nil {
			return nil, err
		}

	case "vp":
		rows, err := s.Query(ctx, `SELECT vp_id, title, IFNULL(vp_type,''), IFNULL(proof_method,''),
		                                  IFNULL(scope,''), IFNULL(source_bc,'') FROM vp`)
		if err != nil {
			return nil, err
		}
		for rows.Next() {
			var id, title, ty, pm, sc, sb string
			if err := rows.Scan(&id, &title, &ty, &pm, &sc, &sb); err != nil {
				rows.Close()
				return nil, err
			}
			out[id] = map[string]string{"title": title, "vp_type": ty, "proof_method": pm,
				"scope": sc, "source_bc": sb}
		}
		rows.Close()
		if err := rows.Err(); err != nil {
			return nil, err
		}
		if err := attachSet(ctx, s, out, `SELECT vp_id, di_id FROM vp_di`, "dis"); err != nil {
			return nil, err
		}
		if err := attachSet(ctx, s, out, `SELECT vp_id, ss_id FROM vp_subsystem`, "subsystems"); err != nil {
			return nil, err
		}

	case "story":
		rows, err := s.Query(ctx, `SELECT story_id, title, status, IFNULL(epic_id,''),
		                                  IFNULL(points,''), IFNULL(priority,''), IFNULL(wave,-1),
		                                  IFNULL(src_path,'') FROM story`)
		if err != nil {
			return nil, err
		}
		for rows.Next() {
			var id, title, st, ep, pts, pri, src string
			var wave int64
			if err := rows.Scan(&id, &title, &st, &ep, &pts, &pri, &wave, &src); err != nil {
				rows.Close()
				return nil, err
			}
			w := ""
			if wave >= 0 {
				w = fmt.Sprint(wave)
			}
			out[id] = map[string]string{"title": title, "status": st, "epic_id": ep,
				"points": pts, "priority": pri, "wave": w, "src_path": src}
		}
		rows.Close()
		if err := rows.Err(); err != nil {
			return nil, err
		}
		// The anchored BCs as a SET. A count is then COUNT of that set, derived at
		// comparison time — the same "no count is ever stored" discipline the schema is
		// built on, and it lets one declared column serve both the count-shaped and the
		// list-shaped tables.
		if err := attachSet(ctx, s, out, `SELECT story_id, bc_id FROM story_bc`, "bcs"); err != nil {
			return nil, err
		}

	default:
		return nil, fmt.Errorf("shadow: unknown universe %q", universe)
	}
	return out, nil
}

// attachSet folds an edge table into a comma-joined, SORTED set field. Sorted because the
// comparison is set-valued: an index listing the same members in another order is not drift.
func attachSet(ctx context.Context, s *Store, recs map[string]map[string]string, q, field string) error {
	pairs, err := s.Pairs(ctx, q)
	if err != nil {
		return err
	}
	acc := map[string][]string{}
	for _, p := range pairs {
		acc[p[0]] = append(acc[p[0]], p[1])
	}
	for k, v := range acc {
		sort.Strings(v)
		if r, ok := recs[k]; ok {
			r[field] = strings.Join(v, ", ")
		}
	}
	for _, r := range recs {
		if _, ok := r[field]; !ok {
			r[field] = ""
		}
	}
	return nil
}

// ── the shadow report ────────────────────────────────────────────────────────

type ShadowReport struct {
	Findings []Finding
	// Per-spec accounting. A differ that reports only disagreements cannot show that it
	// looked at anything, and "0 findings" from a differ that matched no table is
	// indistinguishable from a clean pass.
	Specs []ShadowSpecResult
}

type ShadowSpecResult struct {
	Type, Path, Stage string
	TablesMatched     int
	HeaderSignatures  int
	RowsRead          int
	RowsKeyed         int
	RowsNoRecord      int
	RowsStruckThrough int
	RecordsExcluded   int
	RecordsTotal      int
	RecordsNotInIndex int
	CellsCompared     int
	CellsAgreed       int
	ByOutcome         map[string]int
}

// Shadow runs every declared spec against the store and the authored corpus.
func Shadow(ctx context.Context, s *Store, b *RegistryBundle, corpusRoot string) (*ShadowReport, error) {
	st, err := os.Stat(corpusRoot)
	if err != nil {
		return nil, fmt.Errorf("shadow: corpus root %q: %w", corpusRoot, err)
	}
	if !st.IsDir() {
		return nil, fmt.Errorf("shadow: corpus root %q is not a directory", corpusRoot)
	}

	rep := &ShadowReport{}
	find := func(rule, subject, detail string) {
		rep.Findings = append(rep.Findings, Finding{Rule: rule, Subject: subject, Class: ClassShadow, Detail: detail})
	}

	for _, spec := range shadowSpecs {
		res := ShadowSpecResult{Type: spec.Type, Path: spec.Path, ByOutcome: map[string]int{}}

		// STAGE GUARD. A derived type is never flipped; this command is the `shadow` stage
		// and refuses to pretend it is the others. An unknown type is a REGISTRY defect and
		// says so, rather than being read as a clean corpus.
		_, ts, _, status := b.Resolve(spec.Type)
		switch {
		case ts == nil:
			res.Stage = "type-unresolved:" + status
			find("shadow.type-unresolved", spec.Type,
				fmt.Sprintf("the registry does not resolve %q (%s) — a REGISTRY defect, not a corpus one", spec.Type, status))
			rep.Specs = append(rep.Specs, res)
			continue
		default:
			res.Stage = ts.DerivationStage
		}
		if ts.DerivationStage != "shadow" {
			find("shadow.stage-not-shadow", spec.Type,
				fmt.Sprintf("derivation_stage is %q; `fa shadow` implements the `shadow` stage only "+
					"(advance via proven -> retired on evidence, never by flipping)", ts.DerivationStage))
			rep.Specs = append(rep.Specs, res)
			continue
		}

		full := filepath.Join(corpusRoot, spec.Path)
		raw, ok := read(full)
		if !ok {
			find("shadow.document-absent", spec.Path, "the authored document declared by this spec is not present")
			rep.Specs = append(rep.Specs, res)
			continue
		}
		_, body := ParseFrontmatter(raw)

		recs, err := shadowRecords(ctx, s, spec.Universe)
		if err != nil {
			return nil, err
		}
		// Narrow the derived side to what the index is about, and REPORT the narrowing.
		// A scope rule that silently removed records would be indistinguishable from a
		// generator that never saw them.
		if len(spec.ExcludeSrcPrefix) > 0 {
			for k, r := range recs {
				for _, pre := range spec.ExcludeSrcPrefix {
					if strings.HasPrefix(r["src_path"], pre) {
						delete(recs, k)
						res.RecordsExcluded++
						break
					}
				}
			}
			find("shadow.scope-excludes", spec.Path,
				fmt.Sprintf("%d record(s) excluded from the derived side by declared scope %v: %s",
					res.RecordsExcluded, spec.ExcludeSrcPrefix, spec.ExcludeWhy))
		}
		res.RecordsTotal = len(recs)

		var tables []MDTable
		sigs := map[string]bool{}
		for _, t := range ParseMDTables(body) {
			hit := true
			for _, want := range spec.RequireHeader {
				if t.ColumnIndex(want) < 0 {
					hit = false
					break
				}
			}
			if hit {
				tables = append(tables, t)
				sigs[strings.Join(t.Header, "|")] = true
			}
		}
		res.TablesMatched, res.HeaderSignatures = len(tables), len(sigs)

		// Reported, never silent. A spec that matched no table would otherwise contribute
		// zero findings and read as agreement.
		if len(tables) == 0 {
			find("shadow.table-absent", spec.Path,
				fmt.Sprintf("no table carries every column of %v — the spec cannot be checked, which is NOT a pass",
					spec.RequireHeader))
			rep.Specs = append(rep.Specs, res)
			continue
		}

		// A declared column with no store source is a coverage gap, stated once per spec.
		for _, c := range spec.Columns {
			if c.Kind == ColUnderivable {
				find("shadow.column-underivable:"+c.Name, spec.Path, c.Why)
			}
		}

		seen := map[string]bool{}
		for _, t := range tables {
			ki := t.ColumnIndex(spec.KeyColumn)
			for _, r := range t.Rows {
				res.RowsRead++
				// A row shorter than its own header is malformed; reported rather than
				// padded, because padding turns a broken row into content findings.
				if len(r.Cells) < len(t.Header) {
					res.ByOutcome["row-truncated"]++
					find("shadow.row-truncated", fmt.Sprintf("%s:%d", spec.Path, r.Line),
						fmt.Sprintf("row has %d cells, header declares %d", len(r.Cells), len(t.Header)))
				}
				rawKey := r.Cell(ki)
				key := NormalizeCell(rawKey)
				if key == "" {
					continue
				}
				// A struck-out row is the index marking a record withdrawn IN PLACE. It
				// is a claim about the record, so it is reported as its own class — and it
				// still keys normally, which is what stops one `~~` from producing two
				// contradictory findings about the same id.
				if IsStruckThrough(rawKey) {
					res.RowsStruckThrough++
					find("shadow.row-struck-through", spec.Path+" -> "+key,
						fmt.Sprintf("the index strikes this row out (line %d); strikethrough is not a "+
							"representable state, so a derived index would silently lose the withdrawal", r.Line))
				}
				rec, ok := recs[key]
				if !ok {
					res.RowsNoRecord++
					// NOT a dangling reference. Measured: all 38 in STORY-INDEX are
					// PLANNED stories under open epics with no spec file yet. Under a
					// derived index those rows could not exist at all, so this is a
					// finding about story 7's own scope and is classed on its own.
					find("shadow.row-without-record", spec.Path+" -> "+key,
						fmt.Sprintf("the index enumerates %q but the store holds no such record (line %d)", key, r.Line))
					continue
				}
				if seen[key] {
					res.ByOutcome["row-duplicated"]++
					find("shadow.row-duplicated", spec.Path+" -> "+key,
						fmt.Sprintf("the index lists %q more than once (line %d)", key, r.Line))
				}
				seen[key] = true
				res.RowsKeyed++

				for _, c := range spec.Columns {
					if c.Kind == ColUnderivable {
						continue
					}
					ci := t.ColumnIndex(c.Name)
					if ci < 0 {
						res.ByOutcome["column-absent-from-this-table"]++
						continue
					}
					outcome, detail := compareCell(c, r.Cell(ci), rec[c.Field])
					res.CellsCompared++
					res.ByOutcome[outcome]++
					switch outcome {
					case "agree", "agree-casefold", "agree-set":
						res.CellsAgreed++
					default:
						find("shadow.cell."+outcome+":"+c.Name, spec.Path+" -> "+key+" "+c.Name, detail)
					}
				}
			}
		}

		// The other direction: a record the index omits. Only meaningful once the index
		// was read at all, which the table-absent guard above already established.
		var missing []string
		for k := range recs {
			if !seen[k] {
				missing = append(missing, k)
			}
		}
		sort.Strings(missing)
		res.RecordsNotInIndex = len(missing)
		for _, k := range missing {
			find("shadow.record-absent-from-index", spec.Path+" -> "+k,
				"the store holds this record and the index does not enumerate it")
		}

		rep.Specs = append(rep.Specs, res)
	}

	sort.Slice(rep.Findings, func(i, j int) bool {
		a, c := rep.Findings[i], rep.Findings[j]
		if a.Rule != c.Rule {
			return a.Rule < c.Rule
		}
		return a.Subject < c.Subject
	})
	return rep, nil
}

// compareCell is the whole adjudication, and every outcome name is a class a human has to be
// able to act on differently:
//
//	agree / agree-casefold / agree-set   no finding
//	disagree                             the index and the record state different things
//	title-abbreviates / title-elaborates one is a prefix of the other — legitimate editing,
//	                                     reported so it is visible without being called drift
//	index-placeholder                    the index has not been filled in
//	store-empty                          the index claims a value the store does not hold
func compareCell(c ShadowColumn, authoredRaw, derivedRaw string) (string, string) {
	authored := NormalizeCell(authoredRaw)
	derived := NormalizeCell(derivedRaw)

	if c.Kind == ColTitle {
		derived = StripIDPrefix(derived)
		authored = StripIDPrefix(authored)
	}
	annot := ""
	if c.Kind == ColEnum {
		authored, annot = SplitAnnotation(authored)
	}

	// COUNT COLUMNS ARE ADJUDICATED BEFORE THE EMPTINESS RULES.
	//
	// `0` and `[]` are CLAIMS OF ZERO, and an empty derived set SATISFIES them. Running the
	// generic placeholder logic first reported 18 rows as "the index states a value the
	// store does not hold" where the index stated zero and the store held zero — a finding
	// that says the opposite of what is true. The order of these two rules is the bug.
	if c.Kind == ColCount || c.Kind == ColCountOrSet {
		if out, det, done := compareCountCell(authored, derived); done {
			return out, det
		}
	}

	detail := func(kind string) string {
		s := fmt.Sprintf("%s: index=%q store=%q", kind, truncRunes(authored, 120), truncRunes(derived, 120))
		if annot != "" {
			s += fmt.Sprintf(" (index cell also carries the annotation %q)", truncRunes(annot, 60))
		}
		return s
	}

	switch {
	case authored == derived:
		return "agree", ""
	case strings.EqualFold(authored, derived):
		return "agree-casefold", ""
	}

	aEmpty, dEmpty := IsPlaceholder(authored), IsPlaceholder(derived)
	switch {
	case aEmpty && dEmpty:
		return "agree", ""
	case aEmpty:
		return "index-placeholder", detail("the index cell is a placeholder while the store holds a value")
	case dEmpty:
		return "store-empty", detail("the index states a value the store does not hold")
	}

	switch c.Kind {
	case ColSet:
		a, d := SplitList(authored), SplitList(derived)
		// A set-valued cell that carries prose alongside its ids (`S-9.07 SDK-ext (W-16)`)
		// is a TYPE violation of the column, reported as one. Comparing it as a set would
		// report the prose as a missing member, which names the wrong defect.
		if prose := nonIDTokens(a, setIDRe); len(prose) > 0 {
			return "prose-in-set", fmt.Sprintf("the index cell mixes prose into a set-valued column: %v (ids=%v store=%v)",
				prose, idTokens(a, setIDRe), d)
		}
		sort.Strings(a)
		sort.Strings(d)
		if strings.Join(a, ",") == strings.Join(d, ",") {
			return "agree-set", ""
		}
		return "disagree", fmt.Sprintf("set differs: index=%v store=%v", a, d)
	case ColCount:
		an, aok := LeadingInt(authored)
		dn, dok := LeadingInt(derived)
		// A cell with no number at all is NOT a claim of zero. Reporting it as 0 == 0
		// would be a false agreement, which is worse than a finding.
		if !aok {
			return "disagree", detail("the index cell states no number where a count is declared")
		}
		if dok && an == dn {
			return "agree", ""
		}
		return "disagree", fmt.Sprintf("count differs: index=%d store=%q", an, truncRunes(derived, 60))

	case ColCountOrSet:
		return "disagree", detail("the cell is neither a count nor a list of ids")
	case ColTitle:
		// Prefix relation in either direction is editing, not drift. Measured: the index
		// abbreviates 47 story titles and elaborates 3 VP titles with version annotations.
		lowA, lowD := strings.ToLower(authored), strings.ToLower(derived)
		if strings.HasPrefix(lowD, lowA) {
			return "title-abbreviates", detail("the index title is a prefix of the record title")
		}
		if strings.HasPrefix(lowA, lowD) {
			return "title-elaborates", detail("the index title extends the record title")
		}
	}
	return "disagree", detail("the index and the record state different things")
}

// setIDRe is the shape of an id in a set-valued cell. Deliberately broad across the id
// families the indexes cross-reference, because the point is to tell an ID from PROSE, not
// to re-validate the id (gateMalformedIDs already does that against the records).
var setIDRe = regexp.MustCompile(`^(?:BC-\d+\.\d+\.\d+|VP-\d+|S-\d+\.\d+[A-Za-z0-9.-]*|SS-\d+|DI-\d+|E-\d+|CAP-\d+)$`)

func idTokens(toks []string, re *regexp.Regexp) []string {
	var out []string
	for _, t := range toks {
		if re.MatchString(t) {
			out = append(out, t)
		}
	}
	return out
}

func nonIDTokens(toks []string, re *regexp.Regexp) []string {
	var out []string
	for _, t := range toks {
		if !re.MatchString(t) {
			out = append(out, t)
		}
	}
	return out
}

// trailingParenRe is the `(PR #50 60be88e 2026-05-02)`-shaped annotation an index cell
// appends to a list. Anchored at the END so it cannot eat a parenthesis that belongs to a
// member; the whole point of the anchor is that a greedy match here would silently drop data.
var trailingParenRe = regexp.MustCompile(`\s*\([^()]*\)\s*$`)

// unbracketedIDList recognises a bare comma-separated id list, with an optional trailing
// prose annotation. It returns false unless EVERY remaining token is an id — a cell that
// mixes prose into its members is not a list, and guessing which tokens were meant would
// invent data the index never stated.
func unbracketedIDList(s string) ([]string, bool) {
	body := trailingParenRe.ReplaceAllString(NormalizeCell(s), "")
	toks := SplitList(body)
	if len(toks) == 0 {
		return nil, false
	}
	for _, t := range toks {
		if !setIDRe.MatchString(t) {
			return nil, false
		}
	}
	return toks, true
}

// compareCountCell adjudicates a count-or-list cell against the derived SET, and reports
// whether it reached a verdict (done=false hands back to the generic rules).
//
// The derived side is always the set. Which claim the AUTHORED cell makes decides how it is
// compared: a list of members is the stricter claim and is compared as members; a bare
// number is compared against the set's cardinality. Both `0` and `[]` are claims of zero.
func compareCountCell(authored, derived string) (outcome, detail string, done bool) {
	d := SplitList(derived)
	sort.Strings(d)

	if members, annot, bracketed := SplitBracketList(authored); bracketed {
		ids := idTokens(members, setIDRe)
		sort.Strings(ids)
		if len(ids) != len(members) {
			return "prose-in-set", fmt.Sprintf("the bracketed list mixes prose into ids: %v (annotation %q)",
				nonIDTokens(members, setIDRe), truncRunes(annot, 60)), true
		}
		if strings.Join(ids, ",") == strings.Join(d, ",") {
			return "agree-set", "", true
		}
		return "disagree", fmt.Sprintf("set differs: index=%v store=%v (index annotation %q)",
			ids, d, truncRunes(annot, 60)), true
	}
	// An UNBRACKETED comma list is still a list. `BC-7.03.042, BC-7.03.043, BC-2.02.012
	// (PR #50 60be88e 2026-05-02)` is the same claim as the bracketed form and the corpus
	// writes both; requiring the brackets reported four such cells as "neither a count nor a
	// list of ids" while they enumerated their members perfectly well.
	if members, ok := unbracketedIDList(authored); ok {
		sort.Strings(members)
		if strings.Join(members, ",") == strings.Join(d, ",") {
			return "agree-set", "", true
		}
		return "disagree", fmt.Sprintf("set differs: index=%v store=%v", members, d), true
	}
	if n, ok := LeadingInt(authored); ok {
		if n == int64(len(d)) {
			return "agree", "", true
		}
		return "disagree", fmt.Sprintf("count differs: index states %d, store holds %d (%v)", n, len(d), d), true
	}
	// No number and no bracketed list: fall through to the generic rules, which will
	// classify a placeholder as a placeholder rather than guessing at a count.
	return "", "", false
}

// PrintShadowReport writes the human summary: counts first, so the ratchet is visible.
func PrintShadowReport(w *os.File, rep *ShadowReport) {
	fmt.Fprintf(w, "\nshadow (story 7 — generate alongside, never flip)\n")
	for _, r := range rep.Specs {
		fmt.Fprintf(w, "  %-30s stage=%-8s %s\n", r.Type, r.Stage, r.Path)
		fmt.Fprintf(w, "      tables %d (%d header signature(s)) · rows %d · keyed %d · no record %d · struck %d\n",
			r.TablesMatched, r.HeaderSignatures, r.RowsRead, r.RowsKeyed, r.RowsNoRecord, r.RowsStruckThrough)
		if r.RecordsTotal > 0 {
			fmt.Fprintf(w, "      store records %d (excluded by scope %d) · absent from the index %d\n",
				r.RecordsTotal, r.RecordsExcluded, r.RecordsNotInIndex)
		}
		if r.CellsCompared > 0 {
			fmt.Fprintf(w, "      cells compared %d · agreed %d (%.1f%%)\n",
				r.CellsCompared, r.CellsAgreed, 100*float64(r.CellsAgreed)/float64(r.CellsCompared))
		}
		var ks []string
		for k := range r.ByOutcome {
			ks = append(ks, k)
		}
		sort.Strings(ks)
		for _, k := range ks {
			fmt.Fprintf(w, "        %-34s %6d\n", k, r.ByOutcome[k])
		}
	}
	if len(rep.Findings) == 0 {
		fmt.Fprintf(w, "  no shadow findings\n")
		return
	}
	byRule := map[string]int{}
	for _, f := range rep.Findings {
		byRule[f.Rule]++
	}
	var rules []string
	for k := range byRule {
		rules = append(rules, k)
	}
	sort.Slice(rules, func(i, j int) bool {
		if byRule[rules[i]] != byRule[rules[j]] {
			return byRule[rules[i]] > byRule[rules[j]]
		}
		return rules[i] < rules[j]
	})
	fmt.Fprintf(w, "  shadow findings %d:\n", len(rep.Findings))
	for _, r := range rules {
		fmt.Fprintf(w, "      %6d  %s\n", byRule[r], r)
	}
}
