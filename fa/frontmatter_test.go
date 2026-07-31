package main

import (
	"reflect"
	"testing"
)

func TestFrontmatterShapes(t *testing.T) {
	doc := "---\n" +
		"story_id: \"S-1.01\"\n" +
		"status: merged\n" +
		"empty_list: []\n" +
		"inline: [A-1, \"A-2\", A-3]\n" +
		"commented: []  # [process-gap] deliberately empty\n" +
		"block:\n" +
		"  - B-1\n" +
		"  - \"B-2\"\n" +
		"nested:\n" +
		"  key: ignored\n" +
		"# a comment line\n" +
		"trailing: value\n" +
		"---\n" +
		"# Title here\n\nbody\n"

	fm, body := ParseFrontmatter(doc)
	if got := fm.Scalar("story_id"); got != "S-1.01" {
		t.Errorf("quoted scalar: got %q", got)
	}
	if got := fm.List("empty_list"); len(got) != 0 {
		t.Errorf("empty inline list: got %v", got)
	}
	if got := fm.List("inline"); !reflect.DeepEqual(got, []string{"A-1", "A-2", "A-3"}) {
		t.Errorf("inline list: got %v", got)
	}
	if got := fm.List("commented"); len(got) != 0 {
		t.Errorf("trailing comment must not become a value: got %v", got)
	}
	if got := fm.List("block"); !reflect.DeepEqual(got, []string{"B-1", "B-2"}) {
		t.Errorf("block list: got %v", got)
	}
	if got := fm.Scalar("trailing"); got != "value" {
		t.Errorf("key after a nested mapping: got %q", got)
	}
	if got := firstH1(body); got != "Title here" {
		t.Errorf("firstH1: got %q", got)
	}
}

// TestFrontmatterWrappedInlineList pins bug (2): the corpus wraps long inline
// lists across physical lines, and reading only the first line truncates the list
// mid-element — which silently drops real edges.
func TestFrontmatterWrappedInlineList(t *testing.T) {
	doc := "---\n" +
		"blocks: [\"S-8.11\", \"S-8.12\",\n" +
		"         \"S-8.18\", \"S-8.19\"]\n" +
		"after: yes\n" +
		"---\n\nbody\n"
	fm, _ := ParseFrontmatter(doc)
	want := []string{"S-8.11", "S-8.12", "S-8.18", "S-8.19"}
	if got := fm.List("blocks"); !reflect.DeepEqual(got, want) {
		t.Errorf("wrapped inline list: got %v want %v", got, want)
	}
	if got := fm.Scalar("after"); got != "yes" {
		t.Errorf("the key after a wrapped list was lost: got %q", got)
	}
}

// TestFrontmatterProseBracketDoesNotSwallowKeys is a REGRESSION test for a real
// bug found on 2026-07-31 while porting the prototype.
//
// The old continuation rule was "the previous line has more '[' than ']'". The
// corpus's own BC-INDEX.md holds a prose value with an unbalanced bracket:
//
//	last_amended: "2026-05-31 (v2.65) — ... [Prior: 2026-05-30 (v2.64) — ..."
//
// so EVERY key after it was joined into that value and disappeared. That hid
// `total_bcs: 1955` from the gate whose entire job is checking stated counts, and
// hid 19 real edges across 6 stories (S-15.10/12/13/14/15/17). A checker that
// silently loses its input reports a false clean, so this test must never be
// relaxed to accommodate a "simpler" rule.
func TestFrontmatterProseBracketDoesNotSwallowKeys(t *testing.T) {
	doc := "---\n" +
		"last_amended: \"2026-05-31 (v2.65) — body row draft→active [Prior: 2026-05-30 (v2.64) — x\"\n" +
		"total_bcs: 1955\n" +
		"depends_on: [S-15.07, S-15.09]\n" +
		"behavioral_contracts: [BC-5.39.006]\n" +
		"subsystems: [\"SS-05\"]\n" +
		"---\n\nbody\n"
	fm, _ := ParseFrontmatter(doc)
	if got := fm.Scalar("total_bcs"); got != "1955" {
		t.Fatalf("total_bcs was swallowed by an unbalanced bracket in prose: got %q", got)
	}
	if got := fm.List("depends_on"); !reflect.DeepEqual(got, []string{"S-15.07", "S-15.09"}) {
		t.Errorf("depends_on: got %v", got)
	}
	if got := fm.List("behavioral_contracts"); !reflect.DeepEqual(got, []string{"BC-5.39.006"}) {
		t.Errorf("behavioral_contracts: got %v", got)
	}
	if got := fm.List("subsystems"); !reflect.DeepEqual(got, []string{"SS-05"}) {
		t.Errorf("subsystems: got %v", got)
	}
}

func TestFrontmatterAbsent(t *testing.T) {
	// Legacy stories carry NO frontmatter — their references are prose bold lines
	// ("**Blocks:** S-2.8"). They must parse as empty rather than as an error, and
	// they are why the dangling-reference count is a FLOOR (known gap 2).
	doc := "# S-0.1: bump-version.sh prerelease support\n\n**Blocks:** S-2.8, S-4.8\n"
	fm, body := ParseFrontmatter(doc)
	if len(fm) != 0 {
		t.Errorf("expected empty frontmatter, got %v", fm)
	}
	if body != doc {
		t.Errorf("body must be the whole document when there is no frontmatter")
	}
	if got := fm.Scalar("missing"); got != "" {
		t.Errorf("absent key: got %q", got)
	}
	if got := fm.List("missing"); got != nil {
		t.Errorf("absent list: got %v", got)
	}
}

func TestScalarNullSpellings(t *testing.T) {
	doc := "---\na: null\nb: none\nc: \"\"\nd: []\ne: real\n---\n\nx\n"
	fm, _ := ParseFrontmatter(doc)
	for _, k := range []string{"a", "b", "c", "d"} {
		if got := fm.Scalar(k); got != "" {
			t.Errorf("%s: null spelling must be empty, got %q", k, got)
		}
	}
	if got := fm.Scalar("e"); got != "real" {
		t.Errorf("e: got %q", got)
	}
}

func TestTruncRunesNeverSplitsARune(t *testing.T) {
	// The corpus is full of em-dashes; byte slicing would corrupt them.
	s := "a—b—c"
	if got := truncRunes(s, 3); got != "a—b" {
		t.Errorf("got %q", got)
	}
	if got := truncRunes(s, 99); got != s {
		t.Errorf("got %q", got)
	}
}
