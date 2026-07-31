package main

// A miniature .factory corpus with DELIBERATELY planted violations, one per class
// the gates claim to catch. Tests assert exact counts against it: a gate that
// cannot be shown failing on a known-bad input has not been tested, only run.

import (
	"os"
	"path/filepath"
	"testing"
)

func writeFile(t *testing.T, root, rel, content string) {
	t.Helper()
	p := filepath.Join(root, rel)
	if err := os.MkdirAll(filepath.Dir(p), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(p, []byte(content), 0o644); err != nil {
		t.Fatal(err)
	}
}

// writeFixture builds the corpus and returns its root.
//
// Planted violations:
//
//	type      VP-001.scope is multi-valued in a scalar-declared field
//	type      VP-001.bcs holds an id plus prose
//	type      story S-1.01 subsystems holds an id plus prose
//	type      BC-1.02.001.replacement holds prose, not a BC id
//	dangling  VP-001.bcs -> BC-9.99.999 (no such BC)
//	dangling  S-1.01.blocks -> S-9.99 (no such story)
//	dangling  BC-1.01.002.capability -> CAP-999 (not in the capability universe)
//	dangling  BC-INDEX enumerates BC-4.04.004, which has no record
//	count     BC-INDEX frontmatter total_bcs: 5, body Total row 4, actual 3
//	count     BC-INDEX registry row SS-02 states 2, actual 1
//	integrity BC-1.02.001 sits in SS-02, whose registered prefix is BC-2
//	direction S-1.01 blocks S-9.99 has no reverse edge (dangling, so not counted),
//	          and S-1.02 depends_on S-1.01 is reciprocated by S-1.01 blocks S-1.02
func writeFixture(t *testing.T) string {
	t.Helper()
	root := t.TempDir()

	writeFile(t, root, "specs/architecture/ARCH-INDEX.md", `# ARCH-INDEX

| SS-ID | Name | Prefix | Section |
|---|---|---|---|
| SS-01 | Alpha Subsystem | BC-1 | ss-01/ |
| SS-02 | Beta Subsystem | BC-2 | ss-02/ |

**Total BCs: 3**

### ADR-001: Use a database
Some prose.
`)

	// The bold form must not be anchored to end-of-line: DI-001 carries an
	// amendment suffix after the closing '**', exactly as the real corpus does.
	writeFile(t, root, "specs/domain-spec/capabilities.md", "# Capabilities\n\n**CAP-001 — Dispatch things**\n")
	writeFile(t, root, "specs/domain-spec/invariants.md",
		"# Invariants\n\n**DI-001 — DRAIN_MS = 100** _(v1.5 — amended 2026-01-01)_\n")
	writeFile(t, root, "specs/prd.md", `# PRD

### FR-001: Do the thing

| ID | Requirement |
|---|---|
| NFR-PERF-001 | fast |
`)
	writeFile(t, root, "phase-0-ingestion/pass-4-nfr-catalog.md",
		"# NFR catalog\n\n### NFR-SCALE-001: scales\n")

	writeFile(t, root, "specs/behavioral-contracts/BC-INDEX.md", `---
document_type: bc-index
last_amended: "2026-05-31 (v2.65) — row draft→active [Prior: 2026-05-30 (v2.64) — x"
total_bcs: 5
---

# BC-INDEX

| Subsystem | Prefix | Count | Dir |
|---|---|---|---|
| SS-01 Alpha Subsystem | BC-1 | 2 | ss-01/ |
| SS-02 Beta Subsystem | BC-2 | 2 | ss-02/ |
| **Total** | | **4** | |

## Index by subsystem

| BC ID | Title | Status |
|---|---|---|
| [BC-1.01.001](ss-01/BC-1.01.001.md) | first | draft |
| [BC-1.01.002](ss-01/BC-1.01.002.md) | second | draft |
| [BC-1.02.001](ss-02/BC-1.02.001.md) | third | draft |
| [BC-4.04.004](ss-04/BC-4.04.004.md) | ghost with no record | draft |
`)

	writeFile(t, root, "specs/behavioral-contracts/ss-01/BC-1.01.001.md", `---
subsystem: SS-01
capability: CAP-001
version: v1.2
lifecycle_status: active
---

# Registry rejects unknown schema version
`)
	writeFile(t, root, "specs/behavioral-contracts/ss-01/BC-1.01.002.md", `---
subsystem: SS-01
capability: CAP-999
replacement: BC-4.04.005 read_file capability declaration; existing readers unaffected
---

# Second contract
`)
	// Prefix violation: id says BC-1, frontmatter puts it in SS-02 (prefix BC-2).
	writeFile(t, root, "specs/behavioral-contracts/ss-02/BC-1.02.001.md", `---
subsystem: SS-02
---

# Third contract
`)

	writeFile(t, root, "specs/verification-properties/VP-001.md", `---
scope: SS-01, SS-02
bcs: ["BC-1.01.001 (with prose glued on)", "BC-9.99.999"]
domain_invariants: [DI-001]
nfrs: [NFR-PERF-001]
proof_method: kani
---

# Property one
`)
	// Must be ignored: it is an index, not a VP record.
	writeFile(t, root, "specs/verification-properties/VP-INDEX.md", "# VP-INDEX\n")

	writeFile(t, root, "stories/epics/E-01-alpha-epic.md", "# E-01: Alpha epic\n")
	writeFile(t, root, "stories/S-1.01-alpha.md", `---
story_id: "S-1.01"
epic_id: "E-01"
status: merged
wave: 2
behavioral_contracts: [BC-1.01.001]
verification_properties: [VP-001]
functional_requirements: [FR-001]
subsystems: ["SS-01 (Alpha Subsystem)"]
blocks: [S-9.99, S-1.02]
---

# S-1.01: Alpha story
`)
	writeFile(t, root, "stories/S-1.02-beta.md", `---
story_id: "S-1.02"
status: pending
depends_on: [S-1.01]
---

# S-1.02: Beta story
`)
	// No frontmatter at all, prose references only — like the corpus's legacy
	// stories. Must parse, must get a row, must contribute no edges.
	writeFile(t, root, "stories/v1.0-legacy/S-0.1-legacy.md",
		"# S-0.1: legacy story\n\n**Blocks:** S-2.8, S-4.8\n")

	return root
}

func countRule(fs []Finding, rule string) int {
	n := 0
	for _, f := range fs {
		if f.Rule == rule {
			n++
		}
	}
	return n
}

func TestScanFixture(t *testing.T) {
	root := writeFixture(t)
	c, err := ScanCorpus(root)
	if err != nil {
		t.Fatal(err)
	}

	if len(c.Subsystems) != 2 {
		t.Errorf("subsystems = %d, want 2", len(c.Subsystems))
	}
	if len(c.BCs) != 3 {
		t.Errorf("bcs = %d, want 3", len(c.BCs))
	}
	if len(c.VPs) != 1 {
		t.Errorf("vps = %d, want 1 (VP-INDEX.md must be ignored)", len(c.VPs))
	}
	if len(c.Stories) != 3 {
		t.Errorf("stories = %d, want 3 (including the frontmatter-less legacy story)", len(c.Stories))
	}

	wantUni := map[string]int{"cap": 1, "di": 1, "fr": 1, "nfr": 2, "adr": 1, "epic": 1}
	for k, want := range wantUni {
		if got := len(c.Universes[k]); got != want {
			t.Errorf("universe %s = %d, want %d (%v)", k, got, want, c.Universes[k])
		}
	}

	// Type violations are found by the scan itself.
	for rule, want := range map[string]int{
		"VP.scope is multi-valued in a scalar-declared field": 1,
		"VP.bcs holds an id plus prose":                       1,
		"story.subsystems holds an id plus prose":             1,
		"bc.replacement holds prose, not a BC id":             1,
	} {
		if got := countRule(c.Findings, rule); got != want {
			t.Errorf("finding %q = %d, want %d", rule, got, want)
		}
	}

	// The index enumerates 4 BCs; one of them has no record.
	if len(c.Enumerated) != 4 {
		t.Errorf("enumerated = %v, want 4 entries", c.Enumerated)
	}

	// The count claims must all be captured, including the one hidden behind the
	// prose bracket in `last_amended`.
	claims := map[string]int64{}
	for _, a := range c.Assertions {
		claims[a.Source+" "+a.Subject] = a.Claimed
	}
	for src, want := range map[string]int64{
		"BC-INDEX.md frontmatter total_bcs ":       5,
		"BC-INDEX.md body Total row ":              4,
		"ARCH-INDEX.md Total BCs ":                 3,
		"BC-INDEX.md subsystem registry row SS-02": 2,
	} {
		if got, ok := claims[src]; !ok || got != want {
			t.Errorf("assertion %q = %d (present=%v), want %d", src, got, ok, want)
		}
	}

	// The legacy story contributes a row but no edges: its references are prose.
	for _, e := range c.Edges {
		for _, v := range e.Vals {
			if v == "S-0.1" {
				t.Errorf("legacy story produced an edge: %+v", e)
			}
		}
	}
}

func TestScanRejectsEmptyPath(t *testing.T) {
	if _, err := ScanCorpus(filepath.Join(t.TempDir(), "nope")); err == nil {
		t.Fatal("expected an error for a missing corpus path")
	}
}
