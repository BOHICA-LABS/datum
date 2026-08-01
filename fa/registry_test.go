package main

// Tests for the registry gate. Every gate here is shown FAILING on a planted violation:
// a gate that has never been observed failing has been run, not tested.

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestRegistryEmbedLoads(t *testing.T) {
	b, err := LoadRegistry("")
	if err != nil {
		t.Fatalf("embedded registry does not load: %v", err)
	}
	if b.Reg.Version != 1 || b.En.Version != 1 || b.Al.Version != 1 {
		t.Fatalf("schema_version drift: reg=%d enums=%d aliases=%d",
			b.Reg.Version, b.En.Version, b.Al.Version)
	}
	if len(b.Reg.Types) < 90 {
		t.Fatalf("expected the full canonical type set, got %d", len(b.Reg.Types))
	}
	if len(b.Reg.GapTypes) == 0 {
		t.Fatal("gap_types missing — the honest counter-evidence to 'the standard already exists'")
	}
	// The whole point of embedding ONE copy is that the standard cannot ship twice and
	// disagree with itself. Assert the merged view really includes gap types, since a gap
	// type resolving as "unknown" would blame a project for a concept the standard forgot.
	for name := range b.Reg.GapTypes {
		if _, ok := b.allTypes[name]; !ok {
			t.Fatalf("gap type %q does not resolve", name)
		}
	}
}

// The registry's own completeness is a property of the registry, so it is a unit test
// here as well as a CI script: every alias must point at a declared type.
func TestRegistryAliasTargetsResolve(t *testing.T) {
	b, err := LoadRegistry("")
	if err != nil {
		t.Fatal(err)
	}
	for name, a := range b.Al.Aliases {
		if a == nil || a.Canonical == "" {
			continue // an explicit non-type disposition
		}
		if _, ok := b.allTypes[a.Canonical]; !ok {
			t.Errorf("alias %q -> %q which is not a declared type", name, a.Canonical)
		}
	}
}

func TestResolveCarriesAliasFieldDefaults(t *testing.T) {
	b, err := LoadRegistry("")
	if err != nil {
		t.Fatal(err)
	}
	// This is the reason aliases are not a rename map. `local-adversary-review` encoded
	// scope=story in its NAME; a rename alone destroys that, and the migration would
	// silently lose the dimension.
	canonical, ts, set, status := b.Resolve("local-adversary-review")
	if canonical != "adversarial-review" || status != "alias" || ts == nil {
		t.Fatalf("got canonical=%q status=%q ts=%v", canonical, status, ts != nil)
	}
	if set["scope"] != "story" {
		t.Errorf("alias must carry scope=story, got %q", set["scope"])
	}
	if set["reviewer_role"] != "adversary" {
		t.Errorf("alias must carry reviewer_role=adversary, got %q", set["reviewer_role"])
	}
	// pr-level-security-review and pr-level-pr-reviewer-review differ ONLY by reviewer.
	_, _, s1, _ := b.Resolve("pr-level-security-review")
	_, _, s2, _ := b.Resolve("pr-level-pr-reviewer-review")
	if s1["reviewer_role"] == s2["reviewer_role"] {
		t.Errorf("two aliases that differ only by reviewer collapsed to the same role: %q", s1["reviewer_role"])
	}
}

func TestResolveRetiredAndUnknown(t *testing.T) {
	b, _ := LoadRegistry("")
	if _, _, _, st := b.Resolve("delta-archive"); st != "retired" {
		t.Errorf("delta-archive must resolve as retired, got %q", st)
	}
	if _, _, _, st := b.Resolve("no-such-type-xyz"); st != "unknown" {
		t.Errorf("an undeclared value must resolve as unknown, got %q", st)
	}
}

func TestCheckEnumThreeWay(t *testing.T) {
	b, _ := LoadRegistry("")
	cases := []struct{ enum, val, want string }{
		{"gate_result", "BLOCKED", "ok"},
		{"gate_result", "BLOCKED-soft", "migratable"}, // the migration table knows where it goes
		{"gate_result", "WAT", "illegal"},
		{"priority", "P1", "ok"},        // NOT a severity: binding it to severity_max
		{"priority", "HIGH", "migratable"}, // produced 391 false findings before this split
		{"producer", "some-project-agent", "unchecked"}, // open_extension
		{"status", "draft", "ok"},
		{"status", "RED_GATE_VERIFIED", "migratable"}, // an outcome in a lifecycle field
	}
	for _, c := range cases {
		if got := b.CheckEnum(c.enum, c.val); got != c.want {
			t.Errorf("CheckEnum(%q,%q) = %q, want %q", c.enum, c.val, got, c.want)
		}
	}
}

// RequiredFor must NOT demand a key that today lives only in the filename. Getting this
// wrong produced 2,577 findings against correct files.
func TestRequiredForSkipsFilenameKeys(t *testing.T) {
	b, _ := LoadRegistry("")
	bc := b.Reg.Types["behavioral-contract"]
	if bc == nil {
		t.Fatal("behavioral-contract missing")
	}
	if bc.KeySource != "filename" {
		t.Fatalf("behavioral-contract key_source should be filename (measured: no BC file carries bc_id), got %q", bc.KeySource)
	}
	for _, f := range b.RequiredFor(bc) {
		if f == "bc_id" {
			t.Error("bc_id must not be a required FIELD while its only source is the filename")
		}
		if f == "version" || f == "timestamp" {
			t.Errorf("%q is derived on write and must not be required of an author", f)
		}
	}
	// config shape carries no status/producer, correctly: policies.yaml has neither.
	pol := b.Reg.Types["policies"]
	if pol == nil || pol.Shape != "config" {
		t.Fatal("policies should be shape config")
	}
	for _, f := range b.RequiredFor(pol) {
		if f == "status" || f == "producer" {
			t.Errorf("shape_overrides should exempt config from %q", f)
		}
	}
}

// ── D-A: the section partition ───────────────────────────────────────────────

func TestSectionPartitionIsByteExact(t *testing.T) {
	// Cases chosen to break a naive splitter: a heading inside a fence, duplicate
	// headings, no trailing newline, CRLF, a heading as the very first line.
	cases := []string{
		"intro\n## A\nbody\n## B\nmore\n",
		"## A\none\n## A\ntwo\n", // duplicate headings — why the key is the ORDINAL
		"pre\n```\n## not a heading\n```\npost\n",
		"no trailing newline\n## X\nend",
		"## first line heading\nx\n",
		"",
		"only body, no headings at all\n",
		"~~~\n## fenced with tildes\n~~~\n## real\n",
		"a\r\n## crlf heading\r\nb\r\n",
	}
	for i, c := range cases {
		if !SectionsLossless(c) {
			var got strings.Builder
			for _, s := range SplitSections(c) {
				got.WriteString(s.Body)
			}
			t.Errorf("case %d not byte-exact:\n in=%q\nout=%q", i, c, got.String())
		}
	}
}

func TestSectionPartitionIsFenceAware(t *testing.T) {
	secs := SplitSections("intro\n```\n## fake\n```\n## real\nbody\n")
	var heads []string
	for _, s := range secs {
		if s.Heading != "" {
			heads = append(heads, s.Heading)
		}
	}
	if len(heads) != 1 || heads[0] != "real" {
		t.Errorf("fenced `## fake` must not be a heading; got %v", heads)
	}
}

func TestSectionOrdinalsAreDenseAndOrdered(t *testing.T) {
	secs := SplitSections("a\n## X\nb\n### Y\nc\n## X\nd\n")
	for i, s := range secs {
		if s.Ord != i {
			t.Fatalf("section %d has Ord %d — ordinals must be dense for (doc_key, ord) to be a key", i, s.Ord)
		}
	}
	if secs[len(secs)-1].Heading != "X" || secs[1].Heading != "X" {
		t.Error("duplicate heading X must appear twice, distinguished only by Ord")
	}
}

// ── the gate, shown failing on planted violations ────────────────────────────

func writeCorpus(t *testing.T, files map[string]string) string {
	t.Helper()
	root := t.TempDir()
	for name, body := range files {
		p := filepath.Join(root, name)
		if err := os.MkdirAll(filepath.Dir(p), 0o755); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(p, []byte(body), 0o644); err != nil {
			t.Fatal(err)
		}
	}
	return root
}

func rules(rep *RegistryReport) map[string]int {
	out := map[string]int{}
	for _, f := range rep.Findings {
		out[f.Rule]++
	}
	return out
}

func TestGateCatchesUnknownType(t *testing.T) {
	b, _ := LoadRegistry("")
	root := writeCorpus(t, map[string]string{
		"a.md": "---\ndocument_type: totally-invented-type\nstatus: draft\nproducer: architect\n---\nbody\n",
	})
	rep, err := ValidateRegistry(b, root)
	if err != nil {
		t.Fatal(err)
	}
	if rules(rep)["type.unknown"] != 1 {
		t.Errorf("expected 1 type.unknown, got %v", rules(rep))
	}
}

func TestGateCatchesRetiredTypeAndField(t *testing.T) {
	b, _ := LoadRegistry("")
	root := writeCorpus(t, map[string]string{
		"arch.md": "---\ndocument_type: delta-archive\nstatus: draft\n---\nrotated changelog\n",
		"adr.md": "---\ndocument_type: adr\nstatus: draft\nproducer: architect\nadr_id: ADR-001\n" +
			"date: 2026-01-01\nsubsystems_affected: [SS-01]\nverdict: CLEAN\ninput-hash: \"abc1234\"\n---\n" +
			"## Context\nx\n## Decision\ny\n## Rationale\nz\n## Alternatives Considered\nw\n## Consequences\nv\n",
	})
	rep, _ := ValidateRegistry(b, root)
	r := rules(rep)
	if r["type.retired"] != 1 {
		t.Errorf("delta-archive should be reported retired: %v", r)
	}
	if r["field.retired:verdict"] != 1 {
		t.Errorf("verdict is retired and must be flagged: %v", r)
	}
	if r["field.retired:input-hash"] != 1 {
		t.Errorf("input-hash is retired and must be flagged: %v", r)
	}
	// A fully conformant adr must produce NO section finding — otherwise the gate is
	// reporting noise and its baseline can never reach zero.
	if r["section.missing:adr"] != 0 {
		t.Errorf("a conformant adr must not report missing sections: %v", r)
	}
}

// The three-state distinction: absent, present-but-empty, present. Collapsing them was a
// real defect, caught by a Go/Python parity diff.
func TestGateDistinguishesAbsentFromEmpty(t *testing.T) {
	b, _ := LoadRegistry("")
	root := writeCorpus(t, map[string]string{
		// depends_on ABSENT; blocks PRESENT BUT EMPTY (a declaration of "none")
		"s.md": "---\ndocument_type: story\nstatus: draft\nproducer: story-writer\n" +
			"story_id: S-1.01\nepic_id: E-1\nwave: 1\npoints: 3\npriority: P1\n" +
			"subsystems: [SS-01]\nbehavioral_contracts: [BC-1.01.001]\n" +
			"verification_properties: []  # [process-gap] a trailing comment must not hide emptiness\n" +
			"blocks: []\ntarget_module: m\n---\n## Narrative\nx\n",
	})
	rep, _ := ValidateRegistry(b, root)
	r := rules(rep)
	if r["field.missing:depends_on"] != 1 {
		t.Errorf("an ABSENT key must be field.missing: %v", r)
	}
	if r["field.empty:blocks"] != 1 {
		t.Errorf("`blocks: []` must be field.empty, not field.missing: %v", r)
	}
	if r["field.missing:blocks"] != 0 {
		t.Errorf("`blocks: []` must NOT be reported as missing: %v", r)
	}
	// the trailing-comment case: `[]  # comment` is still empty
	if r["field.empty:verification_properties"] != 1 {
		t.Errorf("an inline YAML comment must not hide an empty list: %v", r)
	}
}

func TestGateCatchesIllegalAndMigratableEnums(t *testing.T) {
	b, _ := LoadRegistry("")
	root := writeCorpus(t, map[string]string{
		"a.md": "---\ndocument_type: adr\nstatus: WAT\nproducer: architect\nadr_id: ADR-001\n" +
			"date: 2026-01-01\nsubsystems_affected: [SS-01]\n---\n## Context\n## Decision\n## Rationale\n## Alternatives Considered\n## Consequences\n",
		"b.md": "---\ndocument_type: adr\nstatus: ready\nproducer: architect\nadr_id: ADR-002\n" +
			"date: 2026-01-01\nsubsystems_affected: [SS-01]\n---\n## Context\n## Decision\n## Rationale\n## Alternatives Considered\n## Consequences\n",
	})
	rep, _ := ValidateRegistry(b, root)
	r := rules(rep)
	if r["enum.illegal:status"] != 1 {
		t.Errorf("status=WAT must be illegal: %v", r)
	}
	if r["enum.migratable:status"] != 1 {
		t.Errorf("status=ready is in migrated_from and must be reported as migratable, not illegal: %v", r)
	}
}

func TestGateCatchesMissingSections(t *testing.T) {
	b, _ := LoadRegistry("")
	root := writeCorpus(t, map[string]string{
		"a.md": "---\ndocument_type: adr\nstatus: draft\nproducer: architect\nadr_id: ADR-001\n" +
			"date: 2026-01-01\nsubsystems_affected: [SS-01]\n---\n## Context\nonly one section\n",
	})
	rep, _ := ValidateRegistry(b, root)
	if rules(rep)["section.missing:adr"] != 1 {
		t.Errorf("expected a section finding: %v", rules(rep))
	}
}

// An untyped file must be ignored entirely: the registry gates DECLARED artifacts, and
// blaming a README for having no document_type would make the gate unusable.
func TestGateIgnoresUntypedFiles(t *testing.T) {
	b, _ := LoadRegistry("")
	root := writeCorpus(t, map[string]string{
		"README.md":  "# just a readme\n",
		"notes.md":   "---\ntitle: no document_type here\n---\nbody\n",
		"data.json":  `{"not":"scanned"}`,
	})
	rep, _ := ValidateRegistry(b, root)
	// Untyped files produce no PER-FILE findings. The one expected finding is the
	// corpus-level "nothing typed here" report, which must not be silent.
	for _, f := range rep.Findings {
		if f.Rule != "registry.corpus-empty" {
			t.Errorf("untyped file produced a per-file finding: %+v", f)
		}
	}
	if rep.FilesTyped != 0 {
		t.Errorf("FilesTyped should be 0, got %d", rep.FilesTyped)
	}
}

// A bad corpus root must be fa FAILING, not the gate failing. Collapsing exit 1 and 2
// makes a typo in CI indistinguishable from a real regression.
func TestGateRejectsMissingCorpusRoot(t *testing.T) {
	b, _ := LoadRegistry("")
	if _, err := ValidateRegistry(b, filepath.Join(t.TempDir(), "does-not-exist")); err == nil {
		t.Fatal("a nonexistent corpus root must return an error, not an empty clean report")
	}
	f := filepath.Join(t.TempDir(), "a-file")
	if err := os.WriteFile(f, []byte("x"), 0o644); err != nil {
		t.Fatal(err)
	}
	if _, err := ValidateRegistry(b, f); err == nil {
		t.Fatal("a file passed as a corpus root must return an error")
	}
}

// An existing but untyped tree must SAY so rather than report a clean pass.
func TestGateReportsEmptyCorpus(t *testing.T) {
	b, _ := LoadRegistry("")
	root := writeCorpus(t, map[string]string{"README.md": "# nothing typed here\n"})
	rep, err := ValidateRegistry(b, root)
	if err != nil {
		t.Fatal(err)
	}
	if rules(rep)["registry.corpus-empty"] != 1 {
		t.Errorf("an untyped corpus must be reported, not pass silently: %v", rules(rep))
	}
}

func TestGateCountsMigrationItemsNotFindings(t *testing.T) {
	b, _ := LoadRegistry("")
	root := writeCorpus(t, map[string]string{
		"specs/behavioral-contracts/ss-01/BC-1.01.001.md": "---\ndocument_type: behavioral-contract\n" +
			"status: draft\nproducer: architect\nsubsystem: SS-01\ncapability: CAP-001\n" +
			"lifecycle_status: active\norigin: greenfield\nintroduced: v1.0\n---\n" +
			"## Description\n## Preconditions\n## Postconditions\n## Invariants\n## Edge Cases\n" +
			"## Canonical Test Vectors\n## Verification Properties\n## Traceability\n",
	})
	rep, _ := ValidateRegistry(b, root)
	if rep.MigrationItems["behavioral-contract"] != 1 {
		t.Errorf("a filename-keyed record must be counted as a migration item: %v", rep.MigrationItems)
	}
	if r := rules(rep)["field.missing:bc_id"]; r != 0 {
		t.Errorf("bc_id must NOT be a finding while its source is the filename, got %d", r)
	}
	if len(rep.Findings) != 0 {
		t.Errorf("a conformant BC must produce zero findings, got %v", rep.Findings)
	}
}
