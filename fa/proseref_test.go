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
