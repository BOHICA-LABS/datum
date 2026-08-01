package main

// Hand-worked cases for the table parser and the cell normalisation rules.
//
// Every case below is either a hand-computed answer or a REGRESSION PIN for a specific
// self-inflicted finding class the shadow stage surfaced against the live corpus. The pins
// are named after the count they explain, because a normalisation rule that loses its
// justification is how a differ ends up tuned to look clean.

import (
	"reflect"
	"strings"
	"testing"
)

func TestSplitMDCellsKeepsEscapedPipes(t *testing.T) {
	// PIN: five BC-INDEX rows carry a literal `\|` inside a cell. Splitting on every pipe
	// truncated them to fragments like `value_len\`, producing 4 false Capability
	// disagreements and 1 false Title disagreement.
	got := SplitMDCells(`| BC-7.01.006 | validate-* family (24 validators on PostToolUse:Edit\|Write) | draft |`)
	want := []string{"BC-7.01.006", "validate-* family (24 validators on PostToolUse:Edit|Write)", "draft"}
	if !reflect.DeepEqual(got, want) {
		t.Errorf("escaped pipe lost\n got %q\nwant %q", got, want)
	}
}

func TestSplitMDCellsPlain(t *testing.T) {
	for _, tc := range []struct {
		in   string
		want []string
	}{
		{"| a | b | c |", []string{"a", "b", "c"}},
		{"|a|b|", []string{"a", "b"}},
		{"| a |  | c |", []string{"a", "", "c"}},
	} {
		if got := SplitMDCells(tc.in); !reflect.DeepEqual(got, tc.want) {
			t.Errorf("SplitMDCells(%q) = %q, want %q", tc.in, got, tc.want)
		}
	}
}

func TestParseMDTablesFenceAwareAndHeadingKeyed(t *testing.T) {
	body := "" +
		"## Alpha\n\n" +
		"| A | B |\n|---|---|\n| 1 | 2 |\n| 3 | 4 |\n\n" +
		"```\n| not | a | table |\n```\n\n" +
		"### Beta\n\n" +
		"| A | B | C |\n|---|---|---|\n| 5 | 6 | 7 |\n"
	got := ParseMDTables(body)
	if len(got) != 2 {
		t.Fatalf("parsed %d tables, want 2 (the fenced one must not count)", len(got))
	}
	if got[0].Heading != "Alpha" || len(got[0].Rows) != 2 {
		t.Errorf("table 0: heading=%q rows=%d, want Alpha/2", got[0].Heading, len(got[0].Rows))
	}
	if got[1].Heading != "Beta" || len(got[1].Header) != 3 || len(got[1].Rows) != 1 {
		t.Errorf("table 1: heading=%q cols=%d rows=%d, want Beta/3/1",
			got[1].Heading, len(got[1].Header), len(got[1].Rows))
	}
	// PIN: column sets vary WITHIN one document — STORY-INDEX carries five header
	// signatures — so the index of a column is per table, never per document.
	if got[0].ColumnIndex("C") != -1 {
		t.Error("a column absent from this table must resolve to -1, not to 0")
	}
	if got[1].ColumnIndex("C") != 2 {
		t.Errorf("ColumnIndex(C) in table 1 = %d, want 2", got[1].ColumnIndex("C"))
	}
}

func TestParseMDTablesSeparatorRowIsNotData(t *testing.T) {
	for _, sep := range []string{"|---|---|", "| :--- | ---: |", "|:-:|:-:|"} {
		body := "| A | B |\n" + sep + "\n| 1 | 2 |\n"
		got := ParseMDTables(body)
		if len(got) != 1 || len(got[0].Rows) != 1 {
			t.Errorf("separator %q: parsed %d tables with %d rows, want 1/1", sep, len(got), len(got[0].Rows))
		}
	}
}

func TestNormalizeCellStripsMarkupNotContent(t *testing.T) {
	for _, tc := range []struct{ in, want string }{
		{"[BC-1.01.001](ss-01/BC-1.01.001.md)", "BC-1.01.001"},
		{"**merged**", "merged"},
		{"~~BC-2.02.013~~", "BC-2.02.013"},
		{"`validate-artifact-path` Purity", "validate-artifact-path Purity"},
		{"  a   b  ", "a b"},
		// Content that merely LOOKS like markup must survive.
		{"exec_subprocess refuses setuid/setgid binaries (Unix)",
			"exec_subprocess refuses setuid/setgid binaries (Unix)"},
	} {
		if got := NormalizeCell(tc.in); got != tc.want {
			t.Errorf("NormalizeCell(%q) = %q, want %q", tc.in, got, tc.want)
		}
	}
}

func TestStrikethroughIsDetectedNotJustStripped(t *testing.T) {
	// PIN: leaving `~~` in the key made BC-INDEX's single struck row report TWICE and
	// contradict itself — once as an index row with no record (`~~BC-2.02.013~~`) and once
	// as a record absent from the index (`BC-2.02.013`). Stripping it fixes the key;
	// detecting it keeps the withdrawal visible.
	if !IsStruckThrough("~~BC-2.02.013~~") {
		t.Error("strikethrough not detected")
	}
	if IsStruckThrough("BC-2.02.013") {
		t.Error("false strikethrough")
	}
	if NormalizeCell("~~BC-2.02.013~~") != "BC-2.02.013" {
		t.Error("strikethrough not stripped for keying")
	}
}

func TestStripIDPrefix(t *testing.T) {
	// PIN: the record H1 repeats its own id and the index cell carries the bare title.
	// Without this rule EVERY row was a Title disagreement: 2,145 across three indexes.
	for _, tc := range []struct{ in, want string }{
		{"Behavioral Contract BC-1.01.001: Registry rejects unknown schema version",
			"Registry rejects unknown schema version"},
		{"VP-001: Tier Execution Is Sequential", "Tier Execution Is Sequential"},
		{"S-0.01: bump-version.sh prerelease support", "bump-version.sh prerelease support"},
		// A title with no id prefix is untouched.
		{"Registry rejects unknown schema version", "Registry rejects unknown schema version"},
	} {
		if got := StripIDPrefix(tc.in); got != tc.want {
			t.Errorf("StripIDPrefix(%q) = %q, want %q", tc.in, got, tc.want)
		}
	}
}

func TestSplitAnnotation(t *testing.T) {
	tok, annot := SplitAnnotation("merged [superseded by ADR-015]")
	if tok != "merged" || annot != "[superseded by ADR-015]" {
		t.Errorf("SplitAnnotation = (%q,%q), want (merged, [superseded by ADR-015])", tok, annot)
	}
	tok, annot = SplitAnnotation("merged")
	if tok != "merged" || annot != "" {
		t.Errorf("SplitAnnotation(merged) = (%q,%q), want (merged, \"\")", tok, annot)
	}
}

func TestAnnotationRuleMustNotTruncateATitle(t *testing.T) {
	// PIN: applied to Title, the annotation rule truncated
	// `Registry rejects unknown entry fields (typo guard)` to its first clause and then
	// reported the truncation as drift — 252 self-inflicted BC findings and 40 story ones.
	// The rule is correct; its SCOPE was the bug. compareCell must only apply it to ColEnum.
	title := "Registry rejects unknown entry fields (typo guard)"
	if out, _ := compareCell(ShadowColumn{Name: "Title", Kind: ColTitle}, title, title); out != "agree" {
		t.Errorf("identical titles carrying a parenthetical compared as %q, want agree", out)
	}
	// The same string as an ENUM column does get its annotation split — that is the point
	// of scoping rather than deleting the rule.
	if tok, _ := SplitAnnotation(title); tok != "Registry rejects unknown entry fields" {
		t.Errorf("the annotation rule itself regressed: %q", tok)
	}
}

func TestLeadingIntDistinguishesAbsentFromZero(t *testing.T) {
	// A cell with no number is NOT a claim of zero. Collapsing them is a FALSE AGREEMENT,
	// which is strictly worse than a finding.
	for _, tc := range []struct {
		in   string
		n    int64
		ok   bool
	}{
		{"117 (114 active; 2 retired)", 117, true},
		{"1,959", 1959, true},
		{"**26**", 26, true},
		{"0 (pure scaffolding, justified)", 0, true},
		{"TBD", 0, false},
		{"", 0, false},
		{"[BC-1.12.003]", 0, false},
	} {
		n, ok := LeadingInt(tc.in)
		if n != tc.n || ok != tc.ok {
			t.Errorf("LeadingInt(%q) = (%d,%v), want (%d,%v)", tc.in, n, ok, tc.n, tc.ok)
		}
	}
}

func TestIsPlaceholderCoversTheMeasuredSpellings(t *testing.T) {
	for _, p := range []string{"", "--", "—", "TBD", "n/a", "CAP-TBD", "none"} {
		if !IsPlaceholder(p) {
			t.Errorf("%q not recognised as a placeholder", p)
		}
	}
	// PIN: `CAP-TBD` is a TYPED placeholder the importer already normalises to NULL on 212
	// BC rows. Treating it as a value reported all 212 as Capability drift.
	for _, v := range []string{"CAP-001", "draft", "0"} {
		if IsPlaceholder(v) {
			t.Errorf("%q wrongly treated as a placeholder", v)
		}
	}
}

func TestSplitBracketListSeparatesTheAnnotation(t *testing.T) {
	// PIN: splitting on commas alone glued ` (v1.4 — D-330)` onto the LAST id, producing 42
	// "set differs" findings whose printed sets were visibly identical apart from that tail.
	members, annot, ok := SplitBracketList("[BC-1.12.003, BC-1.12.004, BC-1.12.005] (v1.4 — D-330)")
	if !ok {
		t.Fatal("bracketed list not recognised")
	}
	want := []string{"BC-1.12.003", "BC-1.12.004", "BC-1.12.005"}
	if !reflect.DeepEqual(members, want) {
		t.Errorf("members = %q, want %q", members, want)
	}
	if !strings.Contains(annot, "D-330") {
		t.Errorf("annotation = %q, want it to carry D-330", annot)
	}
	if _, _, ok := SplitBracketList("26"); ok {
		t.Error("a bare count must not parse as a bracketed list")
	}
}

func TestUnbracketedIDListRejectsProseMixedCells(t *testing.T) {
	// An unbracketed comma list is still a list (4 cells did this), but a cell that MIXES
	// prose into its members is not one, and guessing which tokens were meant would invent
	// data the index never stated.
	got, ok := unbracketedIDList("BC-7.03.042, BC-7.03.043, BC-2.02.012 (PR #50 60be88e 2026-05-02)")
	if !ok || len(got) != 3 {
		t.Errorf("id list with a trailing annotation = (%q,%v), want 3 ids", got, ok)
	}
	if _, ok := unbracketedIDList("S-9.07 SDK-ext (W-16)"); ok {
		t.Error("a prose-mixed cell must not parse as an id list")
	}
	if _, ok := unbracketedIDList("26"); ok {
		t.Error("a bare count must not parse as an id list")
	}
}
