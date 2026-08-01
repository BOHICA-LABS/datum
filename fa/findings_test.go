package main

// Hand-worked cases for story 4's finding extraction.
//
// Each of the three headline rules is pinned by the exact shape that exposed it, because a
// rule without its counterexample is an intention. The extraction rules were measured by
// registry/probe_findings.py BEFORE this file existed.

import (
	"strings"
	"testing"
)

func TestExtractFindingsCoversAllSixIDConventions(t *testing.T) {
	body := strings.Join([]string{
		"## HIGH Findings",
		"",
		"### HIGH-P34-001: BC-1.05.035 NUL byte rejection mechanism factually wrong",
		"",
		"**Severity:** HIGH  ",
		"**Location:** BC-1.05.035 Postcondition 2",
		"",
		"#### ADV-S8P1-P01-MED-001: STORY-INDEX title missing qualifier",
		"",
		"### P2-003 [MED] D-1 rationale cites a non-anchored support matrix",
		"",
		"### F-SP8-002 — PC10 body PAPER-FIX",
		"",
		"| ID | Severity | Description |",
		"|----|----------|-------------|",
		"| CV-12 | LOW | a table-row finding |",
		"",
		"**LOW-007**: an inline finding",
	}, "\n")

	rows, _, malformed := ExtractFindings("r.md", body)
	if malformed != 0 {
		t.Errorf("malformed = %d, want 0", malformed)
	}
	got := map[string]string{}
	for _, r := range rows {
		got[r.FindingID] = r.Severity
	}
	// One per convention. The ADV- form is the one the previous extractor missed, and it is
	// the convention the adversarial-finding TEMPLATE itself declares.
	for id, wantSev := range map[string]string{
		"HIGH-P34-001":          "HIGH", // heading, severity from the bold line
		"ADV-S8P1-P01-MED-001":  "MED",  // TEMPLATE convention, severity embedded in the id
		"P2-003":                "MED",  // no severity word in the id at all; bracket in statement
		"F-SP8-002":             "HIGH", // category-prefixed id; severity from the section heading
		"CV-12":                 "LOW",  // table row, severity from its own column
		"LOW-007":               "LOW",  // inline, severity from the id prefix
	} {
		sev, ok := got[id]
		if !ok {
			t.Errorf("id convention %q was NOT extracted — a silently lost form", id)
			continue
		}
		if sev != wantSev {
			t.Errorf("%s severity = %q, want %q", id, sev, wantSev)
		}
	}
	if len(rows) != 6 {
		t.Errorf("extracted %d rows, want 6: %v", len(rows), got)
	}
}

func TestExtractFindingsCollapsesMentionsToOneRow(t *testing.T) {
	// PIN: a review states a finding as a heading AND repeats it in a closure table. Counting
	// MENTIONS gave EXACTLY 2x the asserted distribution on pass-34 (2H/6M/4L against a
	// claimed 1H/3M/2L). Counting mentions is not counting findings.
	body := strings.Join([]string{
		"## Part B — New Findings",
		"### HIGH-P34-001: the statement lives here",
		"**Severity:** HIGH",
		"",
		"## Closure Table",
		"| ID | Severity | Status |",
		"|----|----------|--------|",
		"| HIGH-P34-001 | HIGH | CLOSED |",
	}, "\n")
	rows, dupes, _ := ExtractFindings("r.md", body)
	if len(rows) != 1 {
		t.Fatalf("got %d rows, want 1 (the heading and the table row are ONE finding)", len(rows))
	}
	if dupes != 1 {
		t.Errorf("collapsed dupes = %d, want 1 — the count must be REPORTED, not swallowed", dupes)
	}
	// The heading wins: it carries the statement.
	if rows[0].Form != "heading" || !strings.Contains(rows[0].Statement, "statement lives here") {
		t.Errorf("the heading form must win: form=%q statement=%q", rows[0].Form, rows[0].Statement)
	}
}

func TestOwnershipIsStructural(t *testing.T) {
	// PIN: `findings_total` counts Part B ONLY. A pass-2 review re-states pass-1's findings in
	// its fix-verification section; counting them put adv-s8.08-p2 at 21 against a claimed 9.
	body := strings.Join([]string{
		"## Part A — Fix Verification (Pass-1 Closure Audit)",
		"### HIGH-P1-001: a PRIOR pass's finding, re-stated to audit its fix",
		"",
		"## Part B — New Findings (Pass-2 Fresh-Context Discovery)",
		"### HIGH-P2-001: a finding THIS pass introduces",
	}, "\n")
	rows, _, _ := ExtractFindings("r.md", body)
	owned := map[string]bool{}
	for _, r := range rows {
		owned[r.FindingID] = r.Owned
	}
	if owned["HIGH-P1-001"] {
		t.Error("a finding defined under a fix-verification section must not count as OWNED")
	}
	if !owned["HIGH-P2-001"] {
		t.Error("a finding defined under a new-findings section must count as OWNED")
	}
}

func TestOwnershipDefaultsToOwned(t *testing.T) {
	// Most reviews have no Part A/B split at all. Defaulting to "mentioned" would silently
	// drop their findings, which is the failure mode this whole exercise keeps re-learning.
	rows, _, _ := ExtractFindings("r.md", "## Findings\n### HIGH-001: a finding\n")
	if len(rows) != 1 || !rows[0].Owned {
		t.Errorf("a review with no Part A/B split must yield OWNED findings, got %+v", rows)
	}
}

func TestSeverityAttrDoesNotCrossIntoTheNextFinding(t *testing.T) {
	// A regex in this repo once mis-assigned 17 of 17 values by crossing a block boundary.
	// The second finding here declares no severity of its own and must NOT inherit the first's
	// bold line.
	body := strings.Join([]string{
		"### F-A-001 — first",
		"**Severity:** CRIT",
		"### F-B-002 — second",
		"nothing declared here",
	}, "\n")
	rows, _, _ := ExtractFindings("r.md", body)
	sev := map[string]string{}
	for _, r := range rows {
		sev[r.FindingID] = r.Severity
	}
	if sev["F-A-001"] != "CRIT" {
		t.Errorf("F-A-001 severity = %q, want CRIT", sev["F-A-001"])
	}
	if sev["F-B-002"] == "CRIT" {
		t.Error("F-B-002 inherited the PREVIOUS finding's severity — the attribute scan crossed a block boundary")
	}
}

func TestUnresolvedSeverityIsReportedNotDefaulted(t *testing.T) {
	// 499 of 2,212 corpus rows resolve to no severity. That must stay visible: silently
	// defaulting to LOW (or to anything) would turn a measured corpus fact into a parser lie.
	rows, _, _ := ExtractFindings("r.md", "## Findings\n### F-X-001 — no severity anywhere\n")
	if len(rows) != 1 {
		t.Fatalf("got %d rows, want 1", len(rows))
	}
	if rows[0].Severity != "" || rows[0].SevSource != "" {
		t.Errorf("severity was invented: %q via %q", rows[0].Severity, rows[0].SevSource)
	}
}

func TestParseSeverityDistribution(t *testing.T) {
	for _, tc := range []struct {
		in   string
		want map[string]int
	}{
		{"1H/3M/2L", map[string]int{"HIGH": 1, "MED": 3, "LOW": 2}},
		// `0C` is an EXPLICIT claim of zero criticals — "we looked, there were none" — which is
		// not the same claim as omitting CRIT entirely. The bucket is KEPT at 0, the same
		// absent-is-not-zero rule the count columns already follow, and the per-bucket gate
		// then compares claimed 0 against COUNT(*) 0 and agrees.
		{"0C+4H+3M+1L+1N", map[string]int{"CRIT": 0, "HIGH": 4, "MED": 3, "LOW": 1, "NIT": 1}},
		{"2 CRIT, 1 MEDIUM", map[string]int{"CRIT": 2, "MED": 1}},
	} {
		got, unknown := ParseSeverityDistribution(tc.in)
		if len(unknown) != 0 {
			t.Errorf("%q: unexpected unknown tokens %v", tc.in, unknown)
		}
		for k, v := range tc.want {
			if got[k] != v {
				t.Errorf("%q: bucket %s = %d, want %d (full: %v)", tc.in, k, got[k], v, got)
			}
		}
		if len(got) != len(tc.want) {
			t.Errorf("%q: got %v, want %v", tc.in, got, tc.want)
		}
	}
	// An unmapped token is REPORTED. A distribution silently missing a bucket compares equal
	// to one that never had it.
	if _, unknown := ParseSeverityDistribution("3 BLOCKERS"); len(unknown) != 1 {
		t.Errorf("an unmapped severity token was dropped instead of reported: %v", unknown)
	}
}

func TestReviewTypeSetIsDerivedFromTheRegistry(t *testing.T) {
	// PIN: the first cut hardcoded this set, and it disagreed with the Python extractor's
	// hardcoded set on EIGHT spellings in both directions — one hand-maintained vocabulary
	// drifting from another, the exact defect the registry exists to remove.
	b, err := LoadRegistry("")
	if err != nil {
		t.Fatalf("LoadRegistry: %v", err)
	}
	got := reviewTypeSet(b)
	if !got["adversarial-review"] {
		t.Error("the canonical type is missing from the derived set")
	}
	if len(got) < 5 {
		t.Errorf("derived %d review spellings; the registry declares 12 aliases to "+
			"adversarial-review, so this is not reading the alias map", len(got))
	}
	// A nil bundle must still yield the canonical type, never an empty set: an empty set
	// would silently import zero reviews and report a clean corpus.
	if n := len(reviewTypeSet(nil)); n != 1 {
		t.Errorf("reviewTypeSet(nil) = %d entries, want exactly the canonical type", n)
	}
}

func TestIsDeclaredCategory(t *testing.T) {
	for _, c := range []string{"spec-gap", "consistency", "SECURITY"} {
		if !IsDeclaredCategory(c) {
			t.Errorf("%q is declared by the template but not recognised", c)
		}
	}
	// The corpus writes prose here; that must be a reportable violation, not a silent pass.
	if IsDeclaredCategory("Sibling propagation gap (S-7.01 partial-fix discipline)") {
		t.Error("prose was accepted as a declared category")
	}
}
