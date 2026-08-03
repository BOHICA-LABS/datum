package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// --- unit gates: the reversibility guarantee, on shapes chosen to break it ---------

func TestLedgerRoundTripIsByteExact(t *testing.T) {
	cases := []string{
		"",
		"no ledger here at all",
		"2026-05-31 (v3.84) — head only",
		"head [Prior: one]",
		"head [Prior: one [Prior: two]]",
		// the real shape: MORE openers than closers. Balancing is not attempted.
		"a [Prior: b [Prior: c [Prior: d]",
		// adjacent separators, and a separator at the very end
		"x [Prior:[Prior: y [Prior:",
		// a bare separator is still reversible
		"[Prior:",
		// unicode em dashes and backticks, as the corpus writes them
		"2026-05-30 (v3.83) — S-15.17 `AC-4/5/6` cycle-conditional [Prior: 2026-05-29 (v3.81) — SEALED]",
	}
	for _, v := range cases {
		if !VerifyLedgerRoundTrip(v) {
			t.Errorf("round trip FAILED (data loss) for %q\n  got %q", v, JoinLedger(SplitLedger(v)))
		}
	}
}

// TestQuotedScalarSurvivesHashAndEscapes pins INSTANCE TEN and the escaped-quote
// truncation found while fixing it. Both silently discarded tens of thousands of
// characters from real corpus values, and both were found by a gate failing its own
// prediction rather than by inspection.
func TestQuotedScalarSurvivesHashAndEscapes(t *testing.T) {
	cases := []struct{ name, line, want string }{
		{
			// instance ten: a literal `#` inside a quoted scalar is NOT a comment.
			// This exact shape truncated STORY-INDEX.md's last_amended to 40 of 50,785.
			"hash inside quotes",
			`last_amended: "2026-05-31 (v3.84) — S-15.17 MERGED PR #164 9ed17b1d; done."`,
			`2026-05-31 (v3.84) — S-15.17 MERGED PR #164 9ed17b1d; done.`,
		},
		{
			// the escaped-quote truncation: stopping at the first `"` cut a 50,787-char
			// value at offset 18,287.
			"escaped double quote inside quotes",
			`k: "before Path::file_name() == Some(\"burst-log.md\") after #123 tail"`,
			`before Path::file_name() == Some(\"burst-log.md\") after #123 tail`,
		},
		{
			"doubled single quote inside single quotes",
			`k: 'it''s a value with #hash and more'`,
			`it''s a value with #hash and more`,
		},
		{
			// a REAL trailing comment after the closing quote is still a comment
			"comment after closing quote",
			`k: "the value"   # this is a comment`,
			`the value`,
		},
		{
			// unquoted: YAML says this IS a comment, so it is still stripped.
			// NB the value is deliberately not `none`/`null`/`[]` — Scalar maps those
			// to "" as null sentinels, which would mask what this case is testing.
			"unquoted trailing comment is stripped",
			`status: merged  # [process-gap]`,
			`merged`,
		},
	}
	for _, c := range cases {
		fm, _, _ := ParseFrontmatterNotes("---\n" + c.line + "\n---\n")
		var key string
		for k := range fm {
			key = k
		}
		got := fm.Scalar(key)
		if got != c.want {
			t.Errorf("%s:\n  line %s\n  want %q\n  got  %q", c.name, c.line, c.want, got)
		}
	}
}

// TestUnquotedCommentStripIsReported proves the remaining lossy case is LOUD. YAML
// requires stripping ` #` from an unquoted scalar, so the strip stays — but a strip
// that nobody can see is the banned class, so it must produce a note.
func TestUnquotedCommentStripIsReported(t *testing.T) {
	_, _, notes := ParseFrontmatterNotes("---\nk: value here # and a comment\n---\n")
	if len(notes) != 1 {
		t.Fatalf("want 1 note for an unquoted comment strip, got %d: %+v", len(notes), notes)
	}
	if notes[0].Kind != "comment-stripped-from-unquoted" || notes[0].Lost <= 0 {
		t.Errorf("note not usable: %+v", notes[0])
	}
	// and a quoted value must produce NO note, because nothing was lost
	_, _, notes2 := ParseFrontmatterNotes("---\nk: \"value #1 here\"\n---\n")
	if len(notes2) != 0 {
		t.Errorf("quoted scalar should lose nothing and report nothing, got %+v", notes2)
	}
}

func TestLedgerExtractsVersionAndDate(t *testing.T) {
	es := SplitLedger("2026-05-31 (v3.84) — head [Prior: 2026-05-30 (v3.83) — older]")
	if len(es) != 2 {
		t.Fatalf("want 2 entries, got %d", len(es))
	}
	if es[0].Date != "2026-05-31" || es[0].Version != "v3.84" {
		t.Errorf("entry 0: date=%q version=%q", es[0].Date, es[0].Version)
	}
	if es[1].Date != "2026-05-30" || es[1].Version != "v3.83" {
		t.Errorf("entry 1: date=%q version=%q", es[1].Date, es[1].Version)
	}
	if es[0].Ord != 0 || es[1].Ord != 1 {
		t.Errorf("ordinals wrong: %d %d", es[0].Ord, es[1].Ord)
	}
}

func TestLooksLikeLedgerDoesNotFireOnProse(t *testing.T) {
	// A long value is NOT a ledger. Firing on length would manufacture entries.
	long := strings.Repeat("this is ordinary prose that happens to be long. ", 200)
	if LooksLikeLedger("description", long) {
		t.Error("fired on long prose with no ledger shape")
	}
	if LooksLikeLedger("last_amended", "2026-05-31 (v1.0) — a single entry") {
		t.Error("fired on a single dated entry (nothing to split)")
	}
	if !LooksLikeLedger("summary", "a [Prior: b]") {
		t.Error("did not fire on an UNENUMERATED field carrying the nesting token")
	}
	if !LooksLikeLedger("last_amended", "2026-05-31 (v1.1) — x. 2026-05-30 (v1.0) — y") {
		t.Error("did not fire on a named ledger field with two dated entries")
	}
}

func TestLedgerImbalanceIsReportedNotRepaired(t *testing.T) {
	v := "a [Prior: b [Prior: c]"
	o, cl, bad := LedgerImbalance(v)
	if o != 2 || cl != 1 || !bad {
		t.Errorf("want 2 openers / 1 closer / unbalanced; got %d/%d/%v", o, cl, bad)
	}
	// and it must still round-trip despite the imbalance
	if !VerifyLedgerRoundTrip(v) {
		t.Error("an unbalanced ledger must still round-trip byte-exact")
	}
}

// --- the corpus gate: every REAL ledger value, not a fixture ----------------------

// TestLedgerRoundTripOverCorpora is the conservation gate. It runs over every ledger
// value in whichever corpora are present, because a fixture cannot prove a property
// about 6,538 real files -- and the one value that mattered (50,801 chars, 116 entries,
// unbalanced brackets) is exactly the kind a hand-written fixture would not contain.
func TestLedgerRoundTripOverCorpora(t *testing.T) {
	roots := []string{
		expandHome("~/Dev/vsdd-factory/.factory"),
		expandHome("~/Dev/prism/.factory"),
		expandHome("~/Dev/rivetry/.factory"),
	}
	checked, ledgers, entries, unbalanced, maxLen, maxEntries := 0, 0, 0, 0, 0, 0
	for _, root := range roots {
		if st, err := os.Stat(root); err != nil || !st.IsDir() {
			continue
		}
		_ = filepath.Walk(root, func(p string, info os.FileInfo, err error) error {
			if err != nil || info.IsDir() || !strings.HasSuffix(p, ".md") {
				return nil
			}
			b, err := os.ReadFile(p)
			if err != nil {
				return nil
			}
			fm, _ := ParseFrontmatter(string(b))
			for k := range fm {
				v := fm.Scalar(k)
				if v == "" {
					continue
				}
				checked++
				if !LooksLikeLedger(k, v) {
					continue
				}
				ledgers++
				es := SplitLedger(v)
				entries += len(es)
				if len(v) > maxLen {
					maxLen = len(v)
				}
				if len(es) > maxEntries {
					maxEntries = len(es)
				}
				if _, _, bad := LedgerImbalance(v); bad {
					unbalanced++
				}
				if got := JoinLedger(es); got != v {
					t.Errorf("⛔ LEDGER ROUND TRIP FAILED — DATA LOSS\n  file  %s\n  field %s\n  len   %d -> %d",
						p, k, len(v), len(got))
				}
			}
			return nil
		})
	}
	if checked == 0 {
		t.Skip("no corpora present")
	}
	if ledgers == 0 {
		// vacuity guard: a gate that passes on an empty set is not evidence.
		t.Fatalf("scanned %d scalar values and found 0 ledgers -- the detector is broken, "+
			"not the corpus (STORY-INDEX.md alone carries a 116-entry one)", checked)
	}
	t.Logf("scalar values scanned %d · LEDGER-SHAPED %d · entries split %d",
		checked, ledgers, entries)
	t.Logf("largest ledger %d chars · most entries in one field %d · unbalanced brackets %d",
		maxLen, maxEntries, unbalanced)
	t.Logf("all %d ledgers rejoined BYTE-EXACT", ledgers)
}
