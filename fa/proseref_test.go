package main

// Hand-worked cases for story 12b. The pin-policy cases matter most: the SAME cite syntax
// carries OPPOSITE verdicts, and reporting a correct one "would be the checker's defect".

import (
	"strings"
	"testing"
)

func TestVersionCitePinPolicyDecidesTheVerdict(t *testing.T) {
	known := map[string]string{"BC-INDEX": "2.65"}
	for _, tc := range []struct{ citingType, body, want string }{
		// A SPEC citing an index asserts currency: floating, so lagging IS a finding.
		{"architecture-index", "traceability per BC-INDEX v1.25 holds", "lagging-floating"},
		// A REVIEW citing an index records what it reviewed: pinned, so lagging is CORRECT.
		{"adversarial-review", "reviewed against BC-INDEX v1.25", "lagging-pinned-ok"},
		// Current under either policy.
		{"architecture-index", "per BC-INDEX v2.65", "current"},
		{"adversarial-review", "per BC-INDEX v2.65", "current"},
		// A version the target NEVER REACHED is a finding under EITHER policy.
		{"adversarial-review", "reviewed against BC-INDEX v9.99", "ahead-never-existed"},
		{"architecture-index", "per BC-INDEX v9.99", "ahead-never-existed"},
	} {
		_, cites := ExtractProseRefs("d.md", tc.citingType, tc.body, known, nil, nil)
		if len(cites) != 1 {
			t.Fatalf("%s / %q: got %d cites, want 1", tc.citingType, tc.body, len(cites))
		}
		if cites[0].Verdict != tc.want {
			t.Errorf("%s / %q: verdict %q, want %q (pin=%s)",
				tc.citingType, tc.body, cites[0].Verdict, tc.want, cites[0].PinPolicy)
		}
	}
}

func TestVersionLessIsNumericNotLexical(t *testing.T) {
	// PIN: string comparison makes "2.10" < "2.9", which would INVERT lagging vs
	// ahead-never-existed — two verdicts with opposite meanings under pin policy. The bug would
	// be a wrong finding, not a missing one.
	if !versionLess("2.9", "2.10") {
		t.Error("2.9 must be less than 2.10")
	}
	if versionLess("2.10", "2.9") {
		t.Error("2.10 must not be less than 2.9")
	}
	if versionLess("3.0", "2.99") {
		t.Error("major version must dominate")
	}
}

func TestVersionCiteUnknownTargetIsReportedNotSkipped(t *testing.T) {
	_, cites := ExtractProseRefs("d.md", "story", "per NOSUCHDOC v1.0", map[string]string{}, nil, nil)
	if len(cites) != 1 || cites[0].Verdict != "target-unknown" {
		t.Errorf("a cite to an unheld target must be recorded as target-unknown, got %+v", cites)
	}
}

func TestSectionRefThreeWayResolution(t *testing.T) {
	// resolved / dangling / unresolvable are THREE outcomes. Collapsing the last two "is how a
	// prose extractor produces a large, confident, wrong finding set".
	byDoc := map[string]map[string]int{"ADR-019": {"consequences": 7}}
	own := map[string]int{"my own section": 2}

	for _, tc := range []struct{ body, want string }{
		{"see §My Own Section here", "resolved"},                  // this document's own
		{"per ADR-019 §Consequences", "resolved"},                 // owner named, section exists
		{"per ADR-019 §No Such Heading", "dangling"},              // owner named, section absent
		{"see §Consequences", "unresolvable"},                     // NO owner named
		{"per ADR-999 §Consequences", "unresolvable"},             // owner named but not held
	} {
		refs, _ := ExtractProseRefs("d.md", "story", tc.body, nil, own, byDoc)
		if len(refs) != 1 {
			t.Fatalf("%q: got %d refs, want 1", tc.body, len(refs))
		}
		if refs[0].Status != tc.want {
			t.Errorf("%q: status %q, want %q", tc.body, refs[0].Status, tc.want)
		}
		if tc.want == "resolved" && refs[0].SectionOrd < 0 {
			t.Errorf("%q: resolved but SectionOrd is %d — D-A's ordinal is the whole point",
				tc.body, refs[0].SectionOrd)
		}
	}
}

func TestProseRefsExcludeCodeSpansAndFences(t *testing.T) {
	body := strings.Join([]string{
		"a real cite: BC-INDEX v1.25",
		"an example in a span: `BC-INDEX v9.99` and `§NotASection`",
		"```",
		"BC-INDEX v8.88",
		"```",
	}, "\n")
	_, cites := ExtractProseRefs("d.md", "story", body, map[string]string{"BC-INDEX": "2.65"}, nil, nil)
	if len(cites) != 1 || cites[0].CitedVersion != "1.25" {
		t.Errorf("code spans/fences leaked into the cites: %+v", cites)
	}
}

func TestSectionRefsHaveTHREEAddressingSchemes(t *testing.T) {
	// The corpus addresses sections three different ways, and each was found by measuring a
	// class of "dangling" reference that turned out to be the RESOLVER's defect:
	//
	//   heading NAME        §Consequences            exact, or a prefix of the real heading
	//   section ORDINAL     §7                       D-A keys the partition on the ordinal
	//   ITEM within one     §Postcondition 5         finer than the partition: the SECTION resolves
	//
	// Getting the third wrong put correct citations on the DANGLING side of a distinction that
	// exists to keep them off it.
	sections := map[string]int{
		"consequences":                  3,
		"postconditions":                5,
		"precedence ladder — full form": 9,
	}
	for _, tc := range []struct {
		captured string
		wantOrd  int
		note     string
	}{
		{"Consequences", 3, "exact heading name"},
		{"7", 7, "section ordinal — D-A's own key"},
		{"Postcondition 5 to state TIMEOUT semantics", 5, "ITEM inside §Postconditions"},
		{"Precedence Ladder and then some prose", 9, "captured name is a PREFIX of the heading"},
	} {
		_, ord, ok := resolveSectionName(tc.captured, sections)
		if !ok || ord != tc.wantOrd {
			t.Errorf("%s: resolveSectionName(%q) = (%d, %v), want ord %d",
				tc.note, tc.captured, ord, ok, tc.wantOrd)
		}
	}
	// A single vague word must NOT attribute: `§host` would otherwise match any heading
	// beginning with "host", which is a confident wrong answer.
	if _, _, ok := resolveSectionName("host", map[string]int{"host functions": 1}); ok {
		t.Error("a one-word prefix was allowed to attribute; that is a confident guess")
	}
	// An ordinal beyond the partition is NOT resolved, so it cannot silently point at nothing.
	if _, _, ok := resolveSectionName("999", sections); ok {
		t.Error("an out-of-range ordinal resolved")
	}
}

// The FOURTH addressing scheme: a section named by the ARTIFACT ID of an item inside it.
//
// capabilities.md has FIVE headings and states each capability as a bold list item, so
// `capabilities.md §CAP-009` addresses something finer than the partition — like
// `§Postcondition 5`, but identified by an id, which itemInSectionRe cannot match because it
// requires a space before the number.
func TestSectionRefsFOURTHSchemeIsAnItemID(t *testing.T) {
	body := "## P0 Capabilities — Must-Have\n\n" +
		"**CAP-009 — Author and publish WASM hook plugins**\n\n" +
		"## P1 Capabilities\n\n" +
		"- CAP-031: something else\n\n" +
		"## Notes\n\nIt also discusses CAP-009 here in passing.\n"
	sec := map[string]int{}
	for _, sx := range SplitSections(body) {
		if sx.Heading != "" {
			sec[strings.ToLower(sx.Heading)] = sx.Ord
		}
	}
	indexItemIDs(sec, body)

	// The id resolves to the section that DEFINES it, at a line start through markdown markers.
	if _, ord, ok := resolveSectionName("CAP-031", sec); !ok || ord != sec["p1 capabilities"] {
		t.Errorf("CAP-031 = (%d,%v), want the P1 section", ord, ok)
	}
	// CAP-009 is DEFINED in P0 and merely MENTIONED mid-sentence in Notes. A mention is not a
	// definition, so this stays unambiguous rather than becoming undecidable.
	if _, ord, ok := resolveSectionName("CAP-009", sec); !ok || ord != sec["p0 capabilities — must-have"] {
		t.Errorf("CAP-009 = (%d,%v), want the P0 section: a mid-sentence mention is not a definition",
			ord, ok)
	}
	// THE LIMIT OF THAT RULE, asserted rather than left implicit: a sentence that BEGINS with the
	// id is indistinguishable from a definition, so it makes the name undecidable. That is the
	// safe direction to fail — undecidable becomes `unresolvable`, not a wrong section.
	body2 := "## A\n\n**CAP-050 — defined here**\n\n## B\n\nCAP-050 also appears at a line start.\n"
	sec2 := map[string]int{}
	for _, sx := range SplitSections(body2) {
		if sx.Heading != "" {
			sec2[strings.ToLower(sx.Heading)] = sx.Ord
		}
	}
	indexItemIDs(sec2, body2)
	if _, ord, ok := resolveSectionName("CAP-050", sec2); ok || ord != ordAmbiguous {
		t.Errorf("CAP-050 = (%d,%v), want ambiguous: a line-initial mention cannot be told from a definition",
			ord, ok)
	}
}

// A BOLD RUN opening a line is how this corpus defines an item, and it is a NAME for the section
// that contains it. ADR-020's `### Budget class taxonomy` defines `**Class A — Cold-start
// dispatch …**`; 16 references to `ADR-020 §Class A` were reported dangling against it.
func TestBoldItemNamesItsSection(t *testing.T) {
	body := "## Context\n\nprose\n\n## Budget class taxonomy\n\n" +
		"**Class A — Cold-start dispatch (per-invocation binary spawn)**\n\n" +
		"- **Budget: p95 <= 1500ms.**\n\n" +
		"## Consequences\n\nmore prose\n"
	sec := map[string]int{}
	for _, sx := range SplitSections(body) {
		if sx.Heading != "" {
			sec[strings.ToLower(sx.Heading)] = sx.Ord
		}
	}
	indexItemIDs(sec, body)
	want := sec["budget class taxonomy"]
	// The short label the citation actually uses reaches the long definition by prefix.
	for _, captured := range []string{"Class A", "Class A cold-start dispatch budget", `Class A | Code review`} {
		if _, ord, ok := resolveSectionName(captured, sec); !ok || ord != want {
			t.Errorf("resolveSectionName(%q) = (%d,%v), want ord %d (the taxonomy section)",
				captured, ord, ok, want)
		}
	}
}

// Punctuation the SENTENCE attaches to a section name must not defeat the match, and a quoted
// name must not either. These were the two largest residual causes, 15 of 26 and 10 of 11.
func TestSectionNamePunctuationIsNotPartOfTheName(t *testing.T) {
	sections := map[string]int{
		"description":                        1,
		"related bcs":                        4,
		"audit risk items carried forward":   9,
		"architecture compliance rules v1.2": 11,
	}
	for _, tc := range []struct {
		captured string
		want     int
	}{
		{"Description:", 1},
		{`Related BCs: "BC-1.05.035 introduces a novel INVALID_ARGUMENT`, 4},
		{`"Audit Risk Items Carried Forward"`, 9},
		{"Architecture Compliance Rules code review gate\"", 11},
	} {
		if _, ord, ok := resolveSectionName(tc.captured, sections); !ok || ord != tc.want {
			t.Errorf("resolveSectionName(%q) = (%d,%v), want ord %d", tc.captured, ord, ok, tc.want)
		}
	}
	// But punctuation that can occur INSIDE a heading is preserved — trimming `/`, `(` or an
	// em-dash would corrupt the name being recovered.
	if _, _, ok := resolveSectionName("Source / Origin", map[string]int{"source / origin": 2}); !ok {
		t.Error("a heading containing '/' stopped resolving; only outer punctuation may be trimmed")
	}
}

// An enumeration of section names must not make each name the OWNER of the next reference.
func TestEnumeratedSectionNamesAreNotOwners(t *testing.T) {
	line := "Sweep these sections: §Description, §Postconditions, §Invariants, §Edge Cases."
	held := map[string]map[string]int{"INVARIANTS": {}, "PRD": {}}
	at := strings.Index(line, "§Edge Cases")
	if got := ownerNamedBefore(line, at, held); got != "" {
		t.Errorf("owner of §Edge Cases = %q, want none: `Invariants` there is a section name in a "+
			"list, not the owning document — and invariants.md exists, so this was a CONFIDENT "+
			"wrong owner rather than a harmless miss", got)
	}
}

// An AMBIGUOUS name is `unresolvable`, never `dangling`. Reporting it as dangling asserts the
// owner does not contain the name, which is the OPPOSITE of what was measured: `PRD §FR-043` was
// reported dangling although `#### FR-043` is a heading four times, one per subsystem slice.
func TestAmbiguousSectionNameIsNotDangling(t *testing.T) {
	body := "#### FR-043 (SS-05 slice) — one\n\ntext\n\n#### FR-043 (SS-06 slice) — two\n\ntext\n"
	sec := map[string]int{}
	for _, sx := range SplitSections(body) {
		if sx.Heading != "" {
			sec[strings.ToLower(sx.Heading)] = sx.Ord
		}
	}
	indexItemIDs(sec, body)
	_, ord, ok := resolveSectionName("FR-043", sec)
	if ok {
		t.Error("an ambiguous id resolved to a single section; that is a confident wrong answer")
	}
	if ord != ordAmbiguous {
		t.Errorf("ord = %d, want ordAmbiguous so the caller can say unresolvable, not dangling", ord)
	}
}

// The owner of a reference is the last id BEFORE the `§`, never merely the last id on the line.
// A line-scoped rule gave every reference on a multi-reference line the SAME owner — the last id
// anywhere on it — and adjudicated `PRD §FR-043` against ARCH-INDEX's partition.
func TestOwnerIsScopedToWhatPrecedesTheMarker(t *testing.T) {
	line := `Sweep across PRD §FR-043, capabilities §CAP-016, BC-INDEX, VP-INDEX, ARCH-INDEX.`
	held := map[string]map[string]int{"PRD": {}, "CAPABILITIES": {}, "ARCH-INDEX": {}}
	for _, tc := range []struct{ marker, want string }{
		{"§FR-043", "PRD"},
		{"§CAP-016", "capabilities"},
	} {
		at := strings.Index(line, tc.marker)
		if got := ownerNamedBefore(line, at, held); got != tc.want {
			t.Errorf("owner of %s = %q, want %q", tc.marker, got, tc.want)
		}
	}
	// A pass id is NOT a document name. `adversarial-review` is keyed [cycle, scope, target,
	// pass], so the registry already says `pass-5` does not name a document — attributing it
	// pointed 55 references at an unrelated cycle's pass-5.md.
	l2 := "Pass-5 §Cure-Extension Parsimony Note"
	if got := ownerNamedBefore(l2, strings.Index(l2, "§"), held); got != "" {
		t.Errorf("owner = %q, want none: a pass id is not a name-addressable document", got)
	}
}

// A `.` must not end the capture when it is part of a number. The corpus addresses `§D-15.1` and
// `§B.1`; a plain [^.] class truncated the first to `D-15` (matching no heading) and reduced the
// second to ONE character, which failed the {2,60} floor and dropped the reference entirely —
// 81 references were invisible.
func TestSectionCaptureKeepsDottedIDs(t *testing.T) {
	// The capture deliberately runs into the surrounding sentence — a section reference has no
	// closing delimiter, so the boundary is recovered by RESOLVING against the real partition
	// (longest prefix wins), not by parsing. What matters is that the dotted id SURVIVES into the
	// capture, and that a sentence-ending period still ends it.
	for _, tc := range []struct{ body, wantPrefix, wantExact string }{
		{"per ADR-015 §D-15.1 applies", "D-15.1", ""},
		{"see §B.1 for detail", "B.1", ""},
		{"see §Consequences. Next sentence.", "", "Consequences"},
	} {
		m := sectionRefRe.FindStringSubmatch(tc.body)
		if m == nil {
			t.Fatalf("%q: no section reference extracted at all", tc.body)
		}
		got := strings.TrimSpace(m[1])
		if tc.wantExact != "" && got != tc.wantExact {
			t.Errorf("%q: captured %q, want exactly %q — a period must end the capture",
				tc.body, got, tc.wantExact)
		}
		if tc.wantPrefix != "" && !strings.HasPrefix(got, tc.wantPrefix) {
			t.Errorf("%q: captured %q, want it to begin with the dotted id %q",
				tc.body, got, tc.wantPrefix)
		}
	}
	// The reference must be EXTRACTED AT ALL. `§B.1` produced a one-character capture under the
	// old class, failed the {2,60} floor, and vanished: 81 references were invisible this way.
	if sectionRefRe.FindStringSubmatch("see §B.1") == nil {
		t.Error("§B.1 extracted nothing; a dotted short reference must not fall below the length floor")
	}
	// And a dotted id must RESOLVE, which is the point of keeping the dot.
	if _, ord, ok := resolveSectionName("D-15.1 applies", map[string]int{
		"d-15.1 — single physical stream for all events": 4}); !ok || ord != 4 {
		t.Errorf("D-15.1 = (%d,%v), want ord 4 by prefix match", ord, ok)
	}
}
