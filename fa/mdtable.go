package main

// Markdown table parsing and CELL NORMALISATION for the shadow index differ (story 7).
//
// Split out from shadow.go because every rule in here was earned by a measurement, and the
// measurement is the justification. `registry/probe_indexes.py` ran first, deliberately: the
// first cut of the probe reported 2,145 "disagreements" that were entirely artefacts of its
// own normalisation, and a differ whose rules are invented before the data is seen produces
// exactly that — noise that looks like drift, tuned until the numbers look clean.
//
// So each rule below carries the count it explains. If a rule cannot name a measured shape,
// it does not belong here.

import (
	"regexp"
	"strconv"
	"strings"
)

// ── the table parser ─────────────────────────────────────────────────────────

type MDRow struct {
	Cells []string
	Line  int
}

type MDTable struct {
	// Heading is the nearest preceding heading. Load-bearing for BC-INDEX, whose
	// per-subsystem tables are distinguished only by their `### SS-NN` heading.
	Heading string
	Header  []string
	Rows    []MDRow
	Line    int
}

var mdHeadingRe = regexp.MustCompile(`^(#{1,6})\s+(.*)$`)

// mdSepRe matches an alignment cell: `---`, `:--`, `--:`, `:-:`, and the single-dash forms.
//
// Recognised BY POSITION, never by pattern alone: the separator is the row immediately after
// the header, which is markdown's actual rule. Sniffing the pattern anywhere would misread a
// data row of placeholder dashes (`| - | - |`, a shape the corpus writes) as an alignment
// row and silently drop it — and requiring two dashes to avoid THAT instead dropped
// legitimate `:-:` separators into the data. Position removes the ambiguity rather than
// trading one misread for the other.
var mdSepRe = regexp.MustCompile(`^:?-+:?$`)

// ParseMDTables extracts every pipe table from a markdown body.
//
// Three properties, each measured rather than assumed:
//
//  1. FENCE-AWARE. A `|` line inside a code fence is not a table row. Same rule
//     SplitSections already applies to headings, for the same reason.
//  2. HEADER-KEYED PER TABLE, never per document. STORY-INDEX carries FIVE distinct
//     header signatures across its 18 story tables (7, 8 and 9 columns, and one
//     spelling `Depends-On` against `Depends On`). A differ with one fixed column
//     map for the document would read every 8-column table against a 7-column
//     schema and report the shift as content drift.
//  3. ESCAPED PIPES SURVIVE. Five BC-INDEX rows carry a literal `\|` inside a cell
//     (`PostToolUse:Edit\|Write`). Splitting on every `|` truncated those cells to
//     fragments like `value_len\`, which then read as four Capability disagreements
//     and one Title disagreement. A splitter that silently loses input is the single
//     most repeated defect class in this spike.
func ParseMDTables(body string) []MDTable {
	var out []MDTable
	var cur *MDTable
	heading, inFence := "", false
	sepConsumed := false

	for ln, raw := range strings.Split(body, "\n") {
		if fenceRe.MatchString(raw) {
			inFence = !inFence
			cur = nil
			continue
		}
		if inFence {
			continue
		}
		if m := mdHeadingRe.FindStringSubmatch(strings.TrimRight(raw, "\r")); m != nil {
			heading = strings.TrimSpace(m[2])
			cur = nil
			continue
		}
		s := strings.TrimSpace(raw)
		if !strings.HasPrefix(s, "|") || !strings.HasSuffix(s, "|") || strings.Count(s, "|") < 2 {
			cur = nil
			continue
		}
		cells := SplitMDCells(s)
		switch {
		case cur == nil:
			out = append(out, MDTable{Heading: heading, Header: cells, Line: ln + 1})
			cur = &out[len(out)-1]
			sepConsumed = false
		case !sepConsumed && isSeparatorRow(cells):
			sepConsumed = true // the alignment row, positionally identified; carries no data
		default:
			sepConsumed = true
			cur.Rows = append(cur.Rows, MDRow{Cells: cells, Line: ln + 1})
		}
	}
	return out
}

func isSeparatorRow(cells []string) bool {
	any := false
	for _, c := range cells {
		if c == "" {
			continue
		}
		if !mdSepRe.MatchString(c) {
			return false
		}
		any = true
	}
	return any
}

// SplitMDCells splits one table row on UNESCAPED pipes, unescaping as it goes.
func SplitMDCells(s string) []string {
	body := strings.TrimSpace(s)
	body = strings.TrimPrefix(body, "|")
	body = strings.TrimSuffix(body, "|")
	var out []string
	var cur strings.Builder
	for i := 0; i < len(body); i++ {
		switch {
		case body[i] == '\\' && i+1 < len(body):
			cur.WriteByte(body[i+1])
			i++
		case body[i] == '|':
			out = append(out, strings.TrimSpace(cur.String()))
			cur.Reset()
		default:
			cur.WriteByte(body[i])
		}
	}
	out = append(out, strings.TrimSpace(cur.String()))
	return out
}

// ColumnIndex maps a header name to its position. Returns -1 when absent, so a caller
// must decide explicitly rather than defaulting to column 0.
func (t MDTable) ColumnIndex(name string) int {
	for i, h := range t.Header {
		if NormalizeCell(h) == NormalizeCell(name) {
			return i
		}
	}
	return -1
}

// Cell returns the cell at a column index, or "" when the row is short. A short row is
// itself reported by the differ (`shadow.row-truncated`) rather than silently padded.
func (r MDRow) Cell(i int) string {
	if i < 0 || i >= len(r.Cells) {
		return ""
	}
	return r.Cells[i]
}

// ── cell normalisation, each rule with the count it explains ──────────────────

var (
	// A link's TARGET is a path, and D-C makes path a derived column that is never
	// identity. So `[BC-1.01.001](ss-01/BC-1.01.001.md)` normalises to its TEXT.
	mdLinkRe = regexp.MustCompile(`\[([^\]]*)\]\([^)]*\)`)
	wsRe     = regexp.MustCompile(`\s+`)

	// A record document's H1 repeats its own id; the index cell carries the bare
	// title. Without this rule EVERY row is a Title disagreement — 2,145 of them
	// across the three indexes, measured on the probe's first run.
	idPrefixRe = regexp.MustCompile(`^\s*(?:Behavioral Contract\s+|Verification Property\s+|Story\s+)?` +
		`(?:BC-\d+\.\d+\.\d+|VP-\d+|S-\d+\.\d+[A-Za-z0-9.-]*|E-\d+)\s*[:\x{2014}-]\s*`)

	// An enum cell often carries its token plus a bracketed annotation:
	// `merged [superseded by ADR-015]`. The token is derivable; the annotation is
	// prose no store column holds.
	//
	// SCOPED TO ENUM COLUMNS ON PURPOSE. Applied to Title it truncated
	// `Registry rejects unknown entry fields (typo guard)` to its first clause and
	// reported the truncation as drift: 252 self-inflicted BC findings and 40 story
	// ones. A normalisation rule aimed at the wrong column manufactures precisely
	// what it was added to prevent.
	annotationRe = regexp.MustCompile(`^([^\[(]+?)\s*[\[(].*[\])]\s*$`)

	// A count cell carries the number plus prose:
	// `117 (114 active; 2 retired; 1 directory-mismatch from ss-07/)`.
	leadingIntRe = regexp.MustCompile(`^\*{0,2}([\d,]+)\*{0,2}`)
)

// NormalizeCell is the normalisation every comparison starts from: de-link, drop bold,
// strikethrough and code markup, collapse whitespace. Backticks are markup, not content —
// VP-069..071 write the title's code span in the record H1 and drop it in the index cell.
//
// Strikethrough is stripped for KEYING but is a real signal about the row, so callers use
// IsStruckThrough to report it separately. Leaving `~~` in the key made BC-INDEX's one
// struck row report TWICE: once as an index row with no record (`~~BC-2.02.013~~`) and once
// as a record absent from the index (`BC-2.02.013`). One markup character, two false
// findings pointing in opposite directions.
func NormalizeCell(s string) string {
	s = mdLinkRe.ReplaceAllString(s, "$1")
	s = strings.ReplaceAll(s, "**", "")
	s = strings.ReplaceAll(s, "~~", "")
	s = strings.ReplaceAll(s, "`", "")
	return strings.TrimSpace(wsRe.ReplaceAllString(s, " "))
}

// IsStruckThrough reports whether a cell was struck out, which the corpus uses to mark a
// row as withdrawn in place rather than deleting it.
func IsStruckThrough(s string) bool { return strings.Contains(s, "~~") }

// StripIDPrefix removes a record's own id from the front of its title.
func StripIDPrefix(s string) string { return strings.TrimSpace(idPrefixRe.ReplaceAllString(s, "")) }

// SplitAnnotation returns (token, annotation) for an enum cell.
func SplitAnnotation(s string) (string, string) {
	if m := annotationRe.FindStringSubmatch(s); m != nil {
		return strings.TrimSpace(m[1]), strings.TrimSpace(s[len(m[1]):])
	}
	return s, ""
}

// LeadingInt reads the count a count-cell claims, and reports whether it found one.
// Never returns a bare 0 for "no number present": a missing count and a claimed zero are
// different claims, and collapsing them is how a gate reports a false agreement.
func LeadingInt(s string) (int64, bool) {
	m := leadingIntRe.FindStringSubmatch(strings.TrimSpace(NormalizeCell(s)))
	if m == nil {
		return 0, false
	}
	n, err := strconv.ParseInt(strings.ReplaceAll(m[1], ",", ""), 10, 64)
	if err != nil {
		return 0, false
	}
	return n, true
}

// placeholders are the spellings the corpus uses for "no value". Measured across the three
// indexes: `--` and `—` dominate, `TBD` appears in Points and Stories cells, and `CAP-TBD`
// is a typed placeholder the importer already normalises to NULL (212 BC rows). Treating
// these as values would report 212 Capability findings that are not drift at all.
var placeholders = map[string]bool{
	"": true, "-": true, "--": true, "---": true, "—": true, "–": true,
	"tbd": true, "n/a": true, "na": true, "none": true, "null": true, "cap-tbd": true,
}

func IsPlaceholder(s string) bool { return placeholders[strings.ToLower(strings.TrimSpace(s))] }

// bracketListRe captures a bracketed list plus whatever prose follows it. The corpus writes
// `[BC-1.12.003, BC-1.12.004, BC-1.12.005] (v1.4 — D-330)`, and splitting on commas alone
// glues ` (v1.4 — D-330)` onto the LAST id — which then reported 42 set differences whose
// printed sets were visibly identical apart from that tail. The annotation has to come off
// before the list is split, not after.
var bracketListRe = regexp.MustCompile(`^\s*\[([^\]]*)\]\s*(.*)$`)

// SplitBracketList returns (members, trailingAnnotation) for a bracketed list cell, and
// reports whether the cell was bracketed at all.
func SplitBracketList(s string) ([]string, string, bool) {
	m := bracketListRe.FindStringSubmatch(NormalizeCell(s))
	if m == nil {
		return nil, "", false
	}
	return SplitList(m[1]), strings.TrimSpace(m[2]), true
}

// SplitList parses a set-valued cell (`S-1.01, S-1.02`) into its members, dropping
// placeholders. Comparison is as a SET: the index's ordering is not a claim.
func SplitList(s string) []string {
	var out []string
	for _, part := range strings.FieldsFunc(NormalizeCell(s), func(r rune) bool {
		return r == ',' || r == ';' || r == '\n'
	}) {
		if p := strings.TrimSpace(part); !IsPlaceholder(p) {
			out = append(out, p)
		}
	}
	return out
}
