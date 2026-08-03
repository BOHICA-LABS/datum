package main

// Ledger fields — an append-only ledger serialised into a single frontmatter scalar.
//
// WHY THIS EXISTS, measured (registry/probe_field_mass.py, research/FA-V1-PIVOT-MEASUREMENT.md):
// 18 real frontmatter values exceed the L1-L2 design's `v_text VARCHAR(2000)`. The
// largest is 50,801 characters -- `last_amended` on `stories/STORY-INDEX.md` -- and it
// is ONE LINE containing 116 dated entries nested as
//
//	2026-05-31 (v3.84) — ... [Prior: 2026-05-30 (v3.83) — ... [Prior: ... ]]]
//
// That is not an oversized string. It is a LEDGER, and the corpus put it in a scalar
// only because markdown frontmatter has no other shape for one. `delta` and `modified`
// are the same class.
//
// Widening the column would preserve the defect, which is why that is not the fix.
// Invariant 16's ratified per-shape rule already says append-only-event TYPES store
// entries and derive the file; this applies the identical treatment at FIELD
// granularity, which is where the corpus actually put them.
//
// THE HARD REQUIREMENT IS REVERSIBILITY (D-A, invariant 15). The split must reproduce
// the original bytes exactly, so entries are stored VERBATIM -- including any trailing
// bracket run -- and the separator is re-inserted on join. `SplitLedger` therefore
// guarantees `strings.Join(entries, "[Prior:") == original` by construction, and
// `ledger_test.go` gates that over every real ledger value in all three corpora rather
// than over a fixture.
//
// It also does NOT attempt to repair the nesting. Measured on STORY-INDEX.md: 115
// `[Prior:` openers against 42 `]` closers, so the brackets do not balance. Balancing
// them would be interpretation, and interpretation at ingest is recorded as DATA, never
// applied as a side effect (V-J). The imbalance is reported as a finding instead.

import (
	"regexp"
	"strings"
)

// ledgerSep is the corpus's own nesting token. Splitting on it and re-joining with it
// is what makes the transformation byte-exact.
const ledgerSep = "[Prior:"

// ledgerFields are the frontmatter fields observed to carry ledger shape. This list is
// a HINT, not the trigger -- LooksLikeLedger decides by SHAPE, so a field nobody has
// enumerated yet is still handled. (A hand-maintained vocabulary drifting from another
// hand-maintained vocabulary is this repo's five-instance defect class; the shape test
// is what keeps this list from becoming a sixth.)
var ledgerFields = map[string]bool{
	"last_amended": true,
	"delta":        true,
	"modified":     true,
}

// reLedgerEntryHead matches an entry's leading date and optional version token, e.g.
//
//	2026-05-31 (v3.84) —
//
// Both parts are extracted for querying and stored ALONGSIDE the verbatim entry, never
// instead of it -- the entry text remains the source of truth.
var reLedgerEntryHead = regexp.MustCompile(`^\s*(\d{4}-\d{2}-\d{2})?\s*(?:\(\s*(v[\d.]+[^)\s]*)\s*\))?`)

// LedgerEntry is one entry of a serialised ledger, in original order.
type LedgerEntry struct {
	Ord     int    // 0 = the live head entry; 1..n = successively older
	Entry   string // VERBATIM, so join is byte-exact
	Version string // the version token this entry announces, if any
	Date    string // the date token as written; deliberately NOT parsed to a DATETIME
}

// LooksLikeLedger decides by SHAPE, so an unenumerated field still gets handled.
//
// Two independent signals, either sufficient:
//   - it contains the corpus's own nesting token, or
//   - it is a named ledger field carrying more than one dated entry.
//
// The length alone is deliberately NOT a signal: a long value is not necessarily a
// ledger, and treating it as one would manufacture entries out of prose.
func LooksLikeLedger(field, v string) bool {
	if strings.Contains(v, ledgerSep) {
		return true
	}
	if ledgerFields[field] {
		return len(reDatedEntry.FindAllString(v, 2)) > 1
	}
	return false
}

var reDatedEntry = regexp.MustCompile(`\d{4}-\d{2}-\d{2}\s*\(`)

// SplitLedger splits a serialised ledger into ordinal entries.
//
// GUARANTEE: strings.Join(entryTexts, ledgerSep) == v, byte for byte. Verified by
// VerifyLedgerRoundTrip and gated over every real ledger value in the corpora.
func SplitLedger(v string) []LedgerEntry {
	parts := strings.Split(v, ledgerSep)
	out := make([]LedgerEntry, 0, len(parts))
	for i, p := range parts {
		e := LedgerEntry{Ord: i, Entry: p}
		if m := reLedgerEntryHead.FindStringSubmatch(p); m != nil {
			e.Date, e.Version = m[1], m[2]
		}
		out = append(out, e)
	}
	return out
}

// JoinLedger is SplitLedger's exact inverse.
func JoinLedger(es []LedgerEntry) string {
	parts := make([]string, len(es))
	for i, e := range es {
		parts[i] = e.Entry
	}
	return strings.Join(parts, ledgerSep)
}

// VerifyLedgerRoundTrip is the conservation gate for one value. A ledger split that
// cannot be rejoined byte-exact is a data-loss event, not a formatting nit.
func VerifyLedgerRoundTrip(v string) bool { return JoinLedger(SplitLedger(v)) == v }

// LedgerImbalance reports the opener/closer counts when they disagree. Reported, never
// repaired: balancing the brackets would be interpretation applied as a side effect.
func LedgerImbalance(v string) (openers, closers int, unbalanced bool) {
	openers = strings.Count(v, ledgerSep)
	closers = strings.Count(v, "]")
	return openers, closers, openers != closers
}
