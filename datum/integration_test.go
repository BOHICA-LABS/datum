package main

// End-to-end tests against a real embedded Dolt store. These are the tests that
// prove the gates FAIL on a known-bad corpus and PASS after a baseline — the two
// behaviours phase 1 stands or falls on.

import (
	"context"
	"path/filepath"
	"testing"
)

func openTestStore(t *testing.T, root, zone string) *Store {
	t.Helper()
	s, err := Open(context.Background(), root, zone, true)
	if err != nil {
		t.Fatalf("open %s: %v", zone, err)
	}
	t.Cleanup(s.Close)
	if err := ensureSchema(context.Background(), s); err != nil {
		t.Fatalf("schema %s: %v", zone, err)
	}
	return s
}

// importFixture builds a store from the fixture corpus and returns both zones.
func importFixture(t *testing.T) (*Store, *Store, *ImportStats) {
	t.Helper()
	corpus := writeFixture(t)
	dbRoot := filepath.Join(t.TempDir(), "db")
	open := openTestStore(t, dbRoot, ZoneOpen)
	walled := openTestStore(t, dbRoot, ZoneWalled)
	st, err := Import(context.Background(), open, corpus, nil)
	if err != nil {
		t.Fatalf("import: %v", err)
	}
	return open, walled, st
}

func TestImportFixture(t *testing.T) {
	open, _, st := importFixture(t)
	ctx := context.Background()

	if st.BCs != 3 || st.VPs != 1 || st.Stories != 3 {
		t.Errorf("imported bc=%d vp=%d story=%d, want 3/1/3", st.BCs, st.VPs, st.Stories)
	}
	if n, _ := open.Int(ctx, "SELECT COUNT(*) FROM bc"); n != 3 {
		t.Errorf("bc rows = %d, want 3", n)
	}
	// The two dangling edges were REFUSED by their foreign keys, so they are absent
	// from the relation and present as findings. Both halves matter.
	if n, _ := open.Int(ctx, "SELECT COUNT(*) FROM vp_bc"); n != 1 {
		t.Errorf("vp_bc = %d, want 1 (BC-9.99.999 must be refused)", n)
	}
	if n, _ := open.Int(ctx,
		`SELECT COUNT(*) FROM finding WHERE rule='VP.bcs -> missing BC'`); n != 1 {
		t.Errorf("the refused vp_bc edge was not recorded as a finding (n=%d)", n)
	}
	if n, _ := open.Int(ctx,
		`SELECT COUNT(*) FROM finding WHERE rule='story.blocks -> missing story'`); n != 1 {
		t.Errorf("the refused story_dep edge was not recorded as a finding (n=%d)", n)
	}
}

// A re-import of an unchanged corpus must leave the working set byte identical.
// Otherwise every CI run rewrites history and `render --check`-style drift
// detection becomes meaningless.
func TestImportIsIdempotent(t *testing.T) {
	corpus := writeFixture(t)
	dbRoot := filepath.Join(t.TempDir(), "db")
	open := openTestStore(t, dbRoot, ZoneOpen)
	ctx := context.Background()

	first, err := Import(ctx, open, corpus, nil)
	if err != nil {
		t.Fatal(err)
	}
	if !first.Changed {
		t.Error("the first import reported no change")
	}
	second, err := Import(ctx, open, corpus, nil)
	if err != nil {
		t.Fatal(err)
	}
	if second.Changed {
		t.Error("a re-import of an unchanged corpus produced a commit")
	}
	if first.Fingerprint != second.Fingerprint {
		t.Errorf("fingerprint drifted across identical imports: %s vs %s",
			first.Fingerprint, second.Fingerprint)
	}
}

func TestImportRefusesEmptyScan(t *testing.T) {
	// A wrong path must be an ERROR, never an empty, clean-looking store.
	dbRoot := filepath.Join(t.TempDir(), "db")
	open := openTestStore(t, dbRoot, ZoneOpen)
	empty := t.TempDir()
	if _, err := Import(context.Background(), open, empty, nil); err == nil {
		t.Fatal("importing an empty directory must fail, not report success")
	}
}

func TestValidateFixtureFindings(t *testing.T) {
	open, walled, _ := importFixture(t)
	rep, err := Validate(context.Background(), open, walled)
	if err != nil {
		t.Fatal(err)
	}

	for rule, want := range map[string]int{
		// count: frontmatter says 5, the body Total row says 4, actual is 3; the
		// SS-02 registry row says 2, actual is 1. ARCH-INDEX's 3 is correct.
		"a stated count disagrees with the records": 3,
		"an index enumerates a BC with no record":   1,
		"bc id prefix disagrees with its subsystem": 1,
		"bc.capability -> missing CAP":              1,
		"VP.bcs -> missing BC":                      1,
		"story.blocks -> missing story":             1,
	} {
		if got := countRule(rep.Findings, rule); got != want {
			t.Errorf("gate %q found %d, want %d", rule, got, want)
		}
	}

	// S-1.01 blocks S-1.02 and S-1.02 depends_on S-1.01 — reciprocated, so neither
	// may be reported. A direction gate that fires on agreeing edges is noise.
	for _, f := range rep.Findings {
		if f.Class == ClassDirection && f.Subject == "S-1.01 blocks S-1.02" {
			t.Errorf("a reciprocated dependency was reported as one-directional: %+v", f)
		}
	}

	if !rep.CrossZoneChecked {
		t.Error("the cross-zone pass did not run")
	}
	if rep.Metrics["bc"] != 3 {
		t.Errorf("metric bc = %d, want 3", rep.Metrics["bc"])
	}
}

// The guarantee D2 gives up and this tool buys back: a walled artifact cannot hold
// a foreign key to the open-zone record it references, so nothing but this pass
// will ever notice the reference going stale.
func TestCrossZoneIntegrity(t *testing.T) {
	open, walled, _ := importFixture(t)
	ctx := context.Background()

	for _, hs := range []struct{ id, expectation, bc string }{
		{"HS-001", "SECRET-EXPECTATION-A", "BC-1.01.001"}, // resolves
		{"HS-002", "SECRET-EXPECTATION-B", "BC-9.99.000"}, // dangles
	} {
		if _, err := walled.Exec(ctx,
			"INSERT INTO holdout_scenario (hs_id, expectation) VALUES (?,?)", hs.id, hs.expectation); err != nil {
			t.Fatal(err)
		}
		if _, err := walled.Exec(ctx,
			"INSERT INTO hs_bc (hs_id, bc_id) VALUES (?,?)", hs.id, hs.bc); err != nil {
			t.Fatal(err)
		}
	}

	rep, err := Validate(ctx, open, walled)
	if err != nil {
		t.Fatal(err)
	}
	if got := rep.Metrics["cross_zone_refs"]; got != 2 {
		t.Errorf("cross_zone_refs = %d, want 2", got)
	}
	n := countRule(rep.Findings, "cross-zone: holdout scenario references a missing BC")
	if n != 1 {
		t.Fatalf("cross-zone findings = %d, want exactly 1 (HS-002 -> BC-9.99.000)", n)
	}
	// The check must not become a side channel around the wall it protects: no
	// walled CONTENT may appear anywhere in the report.
	for _, f := range rep.Findings {
		for _, secret := range []string{"SECRET-EXPECTATION-A", "SECRET-EXPECTATION-B"} {
			if contains(f.Subject, secret) || contains(f.Detail, secret) {
				t.Errorf("walled content leaked into a finding: %+v", f)
			}
		}
	}
}

// A cross-zone pass that could not run must be reported as SKIPPED, never as a
// pass — otherwise "no cross-zone findings" is ambiguous.
func TestCrossZoneSkipIsVisible(t *testing.T) {
	open, _, _ := importFixture(t)
	rep, err := Validate(context.Background(), open, nil)
	if err != nil {
		t.Fatal(err)
	}
	if rep.CrossZoneChecked {
		t.Error("CrossZoneChecked is true with no walled zone")
	}
	if rep.CrossZoneSkipped == "" {
		t.Error("a skipped cross-zone pass must say why")
	}
}

// The ratchet: a baseline tolerates today's findings, a NEW violation fails, and a
// FIXED one is reported so the baseline can shrink.
func TestBaselineRatchet(t *testing.T) {
	open, walled, _ := importFixture(t)
	ctx := context.Background()

	rep, err := Validate(ctx, open, walled)
	if err != nil {
		t.Fatal(err)
	}
	if len(rep.Findings) == 0 {
		t.Fatal("the fixture must produce findings for this test to mean anything")
	}
	b := NewBaseline(rep, "2026-07-31", "fixture", "deadbeef", "fp", nil)

	if d := Compare(rep, b); len(d.New) != 0 || len(d.Fixed) != 0 || len(d.Kept) != len(rep.Findings) {
		t.Fatalf("a fresh baseline must tolerate everything: new=%d fixed=%d kept=%d",
			len(d.New), len(d.Fixed), len(d.Kept))
	}

	// Introduce a regression: a fourth BC in an unknown-prefix subsystem.
	if _, err := open.Exec(ctx,
		`INSERT INTO bc (bc_id, ss_id, title, body, version) VALUES ('BC-7.07.007','SS-01','regression','',
		 'v1.0')`); err != nil {
		t.Fatal(err)
	}
	rep2, err := Validate(ctx, open, walled)
	if err != nil {
		t.Fatal(err)
	}
	d2 := Compare(rep2, b)
	if len(d2.New) == 0 {
		t.Fatal("a new violation was not reported as new — the gate would never fail")
	}
	foundPrefix := false
	for _, f := range d2.New {
		if f.Rule == "bc id prefix disagrees with its subsystem" && f.Subject == "BC-7.07.007 -> SS-01" {
			foundPrefix = true
		}
	}
	if !foundPrefix {
		t.Errorf("expected the planted prefix regression among the new findings, got %+v", d2.New)
	}

	// Now FIX something that was baselined and confirm it is offered for ratcheting.
	if _, err := open.Exec(ctx, `DELETE FROM index_entry WHERE id='BC-4.04.004'`); err != nil {
		t.Fatal(err)
	}
	rep3, err := Validate(ctx, open, walled)
	if err != nil {
		t.Fatal(err)
	}
	d3 := Compare(rep3, b)
	foundFixed := false
	for _, e := range d3.Fixed {
		if e.Rule == "an index enumerates a BC with no record" {
			foundFixed = true
		}
	}
	if !foundFixed {
		t.Errorf("a resolved finding was not reported as fixed, so the baseline could never shrink: %+v", d3.Fixed)
	}
}

func TestBaselineRoundTripKeepsWaivers(t *testing.T) {
	open, walled, _ := importFixture(t)
	rep, err := Validate(context.Background(), open, walled)
	if err != nil {
		t.Fatal(err)
	}
	b := NewBaseline(rep, "2026-07-31", "fixture", "ref", "fp", nil)
	b.Findings[0].Waiver = "accepted: tracked in S-9.99"

	path := filepath.Join(t.TempDir(), "baseline.json")
	if err := b.Save(path); err != nil {
		t.Fatal(err)
	}
	loaded, err := LoadBaseline(path)
	if err != nil {
		t.Fatal(err)
	}
	if len(loaded.Findings) != len(b.Findings) {
		t.Fatalf("round trip lost findings: %d vs %d", len(loaded.Findings), len(b.Findings))
	}

	// Regenerating must preserve a human-written waiver.
	regen := NewBaseline(rep, "2026-08-01", "fixture", "ref", "fp", loaded)
	waivers := 0
	for _, e := range regen.Findings {
		if e.Waiver != "" {
			waivers++
		}
	}
	if waivers != 1 {
		t.Errorf("regenerating the baseline discarded the waiver (%d waivers)", waivers)
	}
}

func TestDoctorOnHealthyStore(t *testing.T) {
	open, walled, _ := importFixture(t)
	ctx := context.Background()
	for _, s := range []*Store{open, walled} {
		for _, c := range Doctor(ctx, s) {
			if !c.OK && c.Fatal {
				t.Errorf("zone %s: fatal check %q failed: %s", s.Zone, c.Name, c.Detail)
			}
		}
	}
	// The probe must leave nothing behind.
	if n, _ := open.Int(ctx,
		`SELECT COUNT(*) FROM information_schema.tables WHERE table_name = ?`, probeTable); n != 0 {
		t.Errorf("the writability probe left %s behind", probeTable)
	}
}

func contains(haystack, needle string) bool {
	return len(needle) > 0 && len(haystack) >= len(needle) &&
		(func() bool {
			for i := 0; i+len(needle) <= len(haystack); i++ {
				if haystack[i:i+len(needle)] == needle {
					return true
				}
			}
			return false
		})()
}
