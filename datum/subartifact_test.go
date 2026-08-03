package main

// Hand-worked cases for story 12a. Every rule is pinned by the exact corpus shape that
// exposed it, with the false-finding count it prevents.

import (
	"strings"
	"testing"
)

func TestExtractSubArtifactsBothAuthoredForms(t *testing.T) {
	body := strings.Join([]string{
		"### AC-001: Grafana panel query inventory captured (traces to ADR-015 Wave 0)",
		"",
		"| AC-1 | `bump-version.sh 1.0.0` still works | BC-9.01.001 postcondition 1 (version bump succeeds) |",
		"| EC-002 | Resolution called twice | Same result both times |",
		"### PC2",
		"| PC-2 | the same precondition, spelled with a hyphen |",
		"| T-3 | emit_event API call | BC-7.03.081 |",
	}, "\n")
	rows, refs, dupes := ExtractSubArtifacts("S-0.01", "story", body)

	got := map[string]SubArtifactRow{}
	for _, r := range rows {
		got[r.Kind+":"+r.SubID] = r
	}
	for _, want := range []string{"ac:AC-001", "ac:AC-1", "ec:EC-002", "pc:PC-2", "t_task:T-3"} {
		if _, ok := got[want]; !ok {
			t.Errorf("%s not extracted; got %v", want, subKeys(got))
		}
	}
	// PC2 and PC-2 are ONE precondition; the key must not depend on the spelling.
	if dupes != 1 {
		t.Errorf("dupes = %d, want 1 (PC2 and PC-2 are the same id)", dupes)
	}
	if got["ac:AC-001"].Form != "heading" || got["ac:AC-1"].Form != "table-row" {
		t.Errorf("forms wrong: %q / %q", got["ac:AC-001"].Form, got["ac:AC-1"].Form)
	}

	// the typed links, including the CLAUSE the trace names
	var acBC, tBC, acADR bool
	for _, r := range refs {
		if r.SubID == "AC-1" && r.TargetID == "BC-9.01.001" {
			acBC = true
			if r.Clause != "postcondition 1" {
				t.Errorf("clause = %q, want \"postcondition 1\"", r.Clause)
			}
		}
		if r.SubID == "T-3" && r.TargetID == "BC-7.03.081" {
			tBC = true
		}
		if r.SubID == "AC-001" && r.TargetID == "ADR-015" {
			acADR = true
		}
	}
	if !acBC || !tBC || !acADR {
		t.Errorf("typed links missing: acBC=%v tBC=%v acADR=%v", acBC, tBC, acADR)
	}
}

func TestDeclaredGapIsNotATrace(t *testing.T) {
	// PIN: S-0.02's AC-1 trace reads "[process-gap] (... uncontracted ...; v1.1 candidate
	// BC-10.13.012-...)". Reading that as a trace produced 55 POLICY-8 findings and 50 of the
	// 53 dangling-trace findings — blaming the document for correctly documenting a gap.
	body := "| AC-1 | Pushing a tag creates a release | " +
		"[process-gap] (Release.yml flag emission is uncontracted by SS-09 BCs; " +
		"v1.1 candidate BC-10.13.012-release-yml-prerelease-flag-emission) |"
	rows, refs, _ := ExtractSubArtifacts("S-0.02", "story", body)
	if len(rows) != 1 {
		t.Fatalf("the AC row itself must still be minted; got %d rows", len(rows))
	}
	if len(refs) != 0 {
		t.Errorf("a gap-marked cell asserted %d trace(s); want 0: %+v", len(refs), refs)
	}
}

func TestIDWithANameSuffixIsAProposedName(t *testing.T) {
	// PIN: `BC-10.13.012-release-yml-prerelease-flag-emission` NAMES a contract that does not
	// exist. prose_ref_boundary's `after` guard deliberately permits a following hyphen (D-426(a)
	// and BC-7.03 need it), so this needs its own rule.
	rows, refs, _ := ExtractSubArtifacts("S-X", "story",
		"| AC-1 | statement | future work: BC-10.13.012-release-yml-flag-emission |")
	if len(rows) != 1 {
		t.Fatalf("got %d rows, want 1", len(rows))
	}
	if len(refs) != 0 {
		t.Errorf("a name-suffixed id was read as a reference: %+v", refs)
	}
	// ...and a bare id in the same position IS a reference, or the rule would have bought
	// silence by going blind.
	_, refs2, _ := ExtractSubArtifacts("S-X", "story",
		"| AC-1 | statement | traces to BC-10.13.012 |")
	if len(refs2) != 1 || refs2[0].TargetID != "BC-10.13.012" {
		t.Errorf("a bare id must still resolve as a reference; got %+v", refs2)
	}
}

func TestSubArtifactCodeSpansExcluded(t *testing.T) {
	// prose_ref_rules exclude-code-spans, and the fenced-block half of it.
	body := strings.Join([]string{
		"| AC-1 | run `datum validate --bc BC-9.99.999` | BC-9.01.001 |",
		"```",
		"### AC-999: this is example markdown inside a fence, not a criterion",
		"```",
	}, "\n")
	rows, refs, _ := ExtractSubArtifacts("S-X", "story", body)
	for _, r := range rows {
		if r.SubID == "AC-999" {
			t.Error("a heading inside a code fence was minted as a sub-artifact")
		}
	}
	for _, r := range refs {
		if r.TargetID == "BC-9.99.999" {
			t.Error("an id inside a backtick span was read as a trace")
		}
	}
	if len(refs) != 1 || refs[0].TargetID != "BC-9.01.001" {
		t.Errorf("the real trace was lost: %+v", refs)
	}
}

func TestSubArtifactKeyIsScopedToItsOwner(t *testing.T) {
	// prose_ref_rules scope-sub-artifact-ids: AC-002 is not globally unique. Two owners may
	// each have one, and they are different rows.
	a, _, _ := ExtractSubArtifacts("S-1.01", "story", "### AC-002: first owner\n")
	b, _, _ := ExtractSubArtifacts("S-2.01", "story", "### AC-002: second owner\n")
	if len(a) != 1 || len(b) != 1 {
		t.Fatalf("got %d/%d rows, want 1/1", len(a), len(b))
	}
	if a[0].OwnerKey == b[0].OwnerKey {
		t.Error("two owners collapsed to one key")
	}
	if a[0].SubID != b[0].SubID {
		t.Error("the same sub_id must be allowed under different owners")
	}
}

func subKeys(m map[string]SubArtifactRow) []string {
	out := make([]string, 0, len(m))
	for k := range m {
		out = append(out, k)
	}
	return out
}
