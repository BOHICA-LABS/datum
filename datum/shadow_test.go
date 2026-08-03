package main

// Tests for the shadow differ (story 7).
//
// Two kinds, and both are load-bearing:
//
//   - table-driven adjudication cases, hand-worked, one per outcome class;
//   - GUARD tests, which pin the properties that make a "0 findings" result meaningful.
//     A differ that matched no table, or silently ran against a type that had already been
//     flipped to derived, would report a clean pass while checking nothing. That failure
//     mode has appeared four separate times in this spike, so it is tested rather than
//     assumed.

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"io/fs"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// snapshotTree hashes every file under root, so "wrote nothing" is verified against CONTENT
// rather than against mtimes.
func snapshotTree(t *testing.T, root string) map[string]string {
	t.Helper()
	out := map[string]string{}
	err := filepath.WalkDir(root, func(path string, d fs.DirEntry, err error) error {
		if err != nil || d.IsDir() {
			return err
		}
		raw, err := os.ReadFile(path)
		if err != nil {
			return err
		}
		sum := sha256.Sum256(raw)
		rel, _ := filepath.Rel(root, path)
		out[rel] = hex.EncodeToString(sum[:])
		return nil
	})
	if err != nil {
		t.Fatalf("snapshotTree(%s): %v", root, err)
	}
	return out
}

func TestCompareCellOutcomes(t *testing.T) {
	enum := ShadowColumn{Name: "Status", Kind: ColEnum}
	title := ShadowColumn{Name: "Title", Kind: ColTitle}
	id := ShadowColumn{Name: "Capability", Kind: ColID}
	set := ShadowColumn{Name: "Stories", Kind: ColSet}
	cos := ShadowColumn{Name: "BCs", Kind: ColCountOrSet}

	for _, tc := range []struct {
		name     string
		col      ShadowColumn
		authored string
		derived  string
		want     string
	}{
		{"identical", enum, "draft", "draft", "agree"},
		{"case only", enum, "Merged", "merged", "agree-casefold"},
		{"annotation split", enum, "merged [superseded by ADR-015]", "merged", "agree"},
		{"real enum drift", enum, "retired", "draft", "disagree"},
		{"link normalised", id, "[CAP-001](x.md)", "CAP-001", "agree"},
		{"both empty", id, "--", "", "agree"},
		{"typed placeholder equals empty", id, "CAP-TBD", "", "agree"},
		{"index not filled in", id, "TBD", "CAP-003", "index-placeholder"},
		{"store lacks the value", id, "CAP-070", "", "store-empty"},
		{"real id drift", id, "CAP-070", "CAP-001", "disagree"},

		{"set order is not a claim", set, "S-2.07, S-15.01", "S-15.01, S-2.07", "agree-set"},
		{"set drift", set, "S-15.01", "S-1.02", "disagree"},
		{"prose in a set column", set, "S-9.07 SDK-ext (W-16)", "S-9.30", "prose-in-set"},

		{"title prefix of record", title, "hook-sdk crate", "hook-sdk crate (macro, types)", "title-abbreviates"},
		{"title extends record", title, "Resolver-Load Purity — must be pure", "Resolver-Load Purity", "title-elaborates"},
		{"title id prefix stripped", title, "Registry rejects x",
			"Behavioral Contract BC-1.01.001: Registry rejects x", "agree"},
		{"real title drift", title, "Single Source of Truth", "Resolver-Load Purity", "disagree"},

		{"count matches set size", cos, "3", "A-1, A-2, A-3", "agree"},
		{"count differs", cos, "16", "A-1, A-2", "disagree"},
		{"bracketed list matches", cos, "[BC-1.12.003, BC-1.12.004] (v1.4 — D-330)",
			"BC-1.12.003, BC-1.12.004", "agree-set"},
		{"unbracketed list matches", cos, "BC-7.03.081, BC-7.03.082 (PR #55)",
			"BC-7.03.081, BC-7.03.082", "agree-set"},

		// PIN: the rule-ORDER bug. `0` and `[]` are claims of ZERO and an empty derived set
		// satisfies them. Running the emptiness rules first reported 18 rows as "the index
		// states a value the store does not hold" where both stated zero — a finding that
		// says the opposite of what is true.
		{"zero count vs empty set", cos, "0 (pure scaffolding, justified)", "", "agree"},
		{"empty list vs empty set", cos, "[] (pending PO authorship)", "", "agree-set"},
		// ...and zero must still disagree when the store is NOT empty, or the fix above
		// would have bought agreement by going blind.
		{"zero count vs non-empty store", cos, "0", "BC-3.08.001", "disagree"},
	} {
		got, detail := compareCell(tc.col, tc.authored, tc.derived)
		if got != tc.want {
			t.Errorf("%s: compareCell(%s, %q, %q) = %q, want %q (detail: %s)",
				tc.name, tc.col.Name, tc.authored, tc.derived, got, tc.want, detail)
		}
	}
}

// TestShadowSpecsAreDeclaredAndAtShadowStage keeps the command honest against the registry.
// If a type were renamed or advanced past `shadow`, this fails loudly instead of the differ
// quietly reporting nothing.
func TestShadowSpecsAreDeclaredAndAtShadowStage(t *testing.T) {
	b, err := LoadRegistry("")
	if err != nil {
		t.Fatalf("LoadRegistry: %v", err)
	}
	if len(shadowSpecs) == 0 {
		t.Fatal("no shadow specs declared — the command would report a vacuous pass")
	}
	for _, spec := range shadowSpecs {
		_, ts, _, status := b.Resolve(spec.Type)
		if ts == nil {
			t.Errorf("spec %q does not resolve in the registry (status %s)", spec.Type, status)
			continue
		}
		if ts.DerivationStage != "shadow" {
			t.Errorf("spec %q is at derivation_stage %q; `datum shadow` implements the shadow stage only",
				spec.Type, ts.DerivationStage)
		}
		if spec.KeyColumn == "" || len(spec.RequireHeader) == 0 || len(spec.Columns) == 0 {
			t.Errorf("spec %q is under-declared: key=%q header=%v cols=%d",
				spec.Type, spec.KeyColumn, spec.RequireHeader, len(spec.Columns))
		}
	}
}

// TestShadowReportsMissingTableRatherThanPassing is the anti-vacuous-pass guard.
func TestShadowReportsMissingTableRatherThanPassing(t *testing.T) {
	open, _, _ := importFixture(t)
	defer open.Close()
	b, err := LoadRegistry("")
	if err != nil {
		t.Fatalf("LoadRegistry: %v", err)
	}
	// The fixture corpus has a BC-INDEX with no per-BC table carrying the declared columns.
	corpus := writeFixture(t)
	rep, err := Shadow(context.Background(), open, b, corpus)
	if err != nil {
		t.Fatalf("Shadow: %v", err)
	}
	var sawSignal bool
	for _, f := range rep.Findings {
		switch {
		case strings.HasPrefix(f.Rule, "shadow.table-absent"),
			strings.HasPrefix(f.Rule, "shadow.document-absent"):
			sawSignal = true
		}
	}
	if !sawSignal {
		t.Errorf("a corpus with no matching index tables produced no table/document-absent finding; "+
			"got %d findings — 'nothing to check' must never look like 'everything agrees'", len(rep.Findings))
	}
}

// TestShadowRejectsBadCorpusRoot: a wrong path must be datum FAILING, not a clean gate.
func TestShadowRejectsBadCorpusRoot(t *testing.T) {
	open, _, _ := importFixture(t)
	defer open.Close()
	b, _ := LoadRegistry("")
	if _, err := Shadow(context.Background(), open, b, filepath.Join(t.TempDir(), "nope")); err == nil {
		t.Error("Shadow accepted a nonexistent corpus root; it must return an error (exit 2), not a pass")
	}
}

// TestShadowWritesNothing is the discipline itself: the shadow stage generates ALONGSIDE the
// authored form. A `shadow` that could mutate either side would defeat its own purpose,
// since the whole point is to keep the authored evidence available for comparison.
func TestShadowWritesNothing(t *testing.T) {
	open, _, _ := importFixture(t)
	defer open.Close()
	b, _ := LoadRegistry("")
	corpus := writeFixture(t)
	before := snapshotTree(t, corpus)

	if _, err := Shadow(context.Background(), open, b, corpus); err != nil {
		t.Fatalf("Shadow: %v", err)
	}
	after := snapshotTree(t, corpus)
	if len(before) != len(after) {
		t.Fatalf("shadow changed the file COUNT: %d -> %d", len(before), len(after))
	}
	for path, sum := range before {
		if after[path] != sum {
			t.Errorf("shadow modified %s", path)
		}
	}
}
