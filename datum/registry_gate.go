package main

// `datum validate --registry` — the artifact type registry as a gate.
//
// This is a CORPUS-SIDE gate, not a store-side one: it reads the markdown corpus directly
// rather than querying the imported store, because it checks whether an artifact DECLARES
// itself correctly, which is a property of the authored file. The store-side gates in
// validate.go check whether the declared graph is CONSISTENT. Two different questions.
//
// Every finding carries a stable (rule, subject) pair so the existing dated baseline
// applies unchanged (baseline.go). That is deliberate: the registry reports ~18k findings
// against the three live corpora, and without the ratchet a gate this loud gets switched
// off on its first red build.

import (
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
)

// Registry finding classes. Distinct from the store-side classes so a baseline can be
// ratcheted per class and so `advisory -> warn -> block` can graduate one class at a time.
const (
	ClassRegType     = "reg-type"     // the document_type itself is wrong or unknown
	ClassRegField    = "reg-field"    // a required field is absent, or a retired one present
	ClassRegEnum     = "reg-enum"     // a value is outside its declared closed enum
	ClassRegSection  = "reg-section"  // a declared section is missing
	ClassRegInvariant = "reg-invariant" // a registry invariant (e.g. D-A losslessness) failed
)

type RegistryReport struct {
	Findings []Finding
	// Counted, because a gate that reports only failures cannot show progress.
	FilesScanned   int
	FilesTyped     int
	FilesResolved  int
	AliasApplied   int
	MigrationItems map[string]int // type -> files whose key still lives only in the filename
	ByStatus       map[string]int
}

type regGate struct {
	b   *RegistryBundle
	rep *RegistryReport
}

func (g *regGate) find(rule, subject, class, detail string) {
	g.rep.Findings = append(g.rep.Findings, Finding{Rule: rule, Subject: subject, Class: class, Detail: detail})
}

// ValidateRegistry walks a .factory corpus and checks every typed artifact against the
// registry. root is the corpus root (the directory holding STATE.md).
func ValidateRegistry(b *RegistryBundle, root string) (*RegistryReport, error) {
	g := &regGate{b: b, rep: &RegistryReport{
		MigrationItems: map[string]int{}, ByStatus: map[string]int{},
	}}

	forbidden := map[string]bool{}
	for _, f := range b.Reg.Defaults.Forbidden {
		forbidden[f] = true
	}
	// `input-hash` is retired as a STORED field (derived staleness replaces it). It is in
	// derived_never_authored rather than forbidden, so pick it up from there explicitly.
	for _, f := range b.Reg.Defaults.DerivedNeverAuthored {
		if f == "input-hash" {
			forbidden[f] = true
		}
	}

	// A missing corpus root must be datum FAILING (exit 2), never the gate failing (exit 1).
	// Without this check WalkDir silently walks nothing, the registry side validates ZERO
	// files, and the run still exits 1 from the store-side gates — indistinguishable in CI
	// from a real regression. That 1-vs-2 collapse already cost this spike an infinite
	// re-dispatch livelock once; it is not repeating it here.
	st, err := os.Stat(root)
	if err != nil {
		return nil, fmt.Errorf("registry gate: corpus root %q: %w", root, err)
	}
	if !st.IsDir() {
		return nil, fmt.Errorf("registry gate: corpus root %q is not a directory", root)
	}

	err = filepath.WalkDir(root, func(path string, d os.DirEntry, err error) error {
		if err != nil {
			return nil // an unreadable entry is not a corpus defect; keep walking
		}
		if d.IsDir() {
			if d.Name() == ".git" {
				return filepath.SkipDir
			}
			return nil
		}
		ext := strings.ToLower(filepath.Ext(path))
		if ext != ".md" && ext != ".yaml" && ext != ".yml" {
			return nil
		}
		g.rep.FilesScanned++
		raw, ok := read(path)
		if !ok {
			return nil
		}
		fm, body := ParseFrontmatter(raw)
		if fm == nil {
			return nil
		}
		dt := fm.Scalar("document_type")
		if dt == "" {
			return nil
		}
		g.rep.FilesTyped++
		rel, _ := filepath.Rel(root, path)
		g.check(rel, dt, fm, body, ext, forbidden)
		return nil
	})
	if err != nil {
		return nil, err
	}
	// Reported, never silent: a corpus with zero typed artifacts is almost certainly the
	// wrong path, and "0 findings" would otherwise read as a clean pass.
	if g.rep.FilesTyped == 0 {
		g.find("registry.corpus-empty", root, ClassRegInvariant,
			fmt.Sprintf("scanned %d file(s) and found no document_type at all — wrong corpus root?", g.rep.FilesScanned))
	}
	sort.Slice(g.rep.Findings, func(i, j int) bool {
		a, c := g.rep.Findings[i], g.rep.Findings[j]
		if a.Class != c.Class {
			return a.Class < c.Class
		}
		if a.Rule != c.Rule {
			return a.Rule < c.Rule
		}
		return a.Subject < c.Subject
	})
	return g.rep, nil
}

func (g *regGate) check(rel, dt string, fm Frontmatter, body, ext string, forbidden map[string]bool) {
	canonical, ts, set, status := g.b.Resolve(dt)
	g.rep.ByStatus[status]++

	switch status {
	case "retired":
		g.find("type.retired", rel, ClassRegType,
			fmt.Sprintf("document_type %q is retired; it exists only because there was no versioned store", dt))
		return
	case "unknown":
		g.find("type.unknown", rel, ClassRegType,
			fmt.Sprintf("document_type %q is not canonical, not aliased and not dispositioned", dt))
		return
	case "unresolved":
		// Explicitly recorded as needing a human decision. Reporting it as a defect would
		// blame the corpus for the registry's own open question.
		return
	case "alias-target-missing":
		g.find("registry.alias-target-missing", rel, ClassRegInvariant,
			fmt.Sprintf("alias %q -> %q which is not a declared type — a REGISTRY defect, not a corpus one", dt, canonical))
		return
	case "alias":
		g.rep.AliasApplied++
	}
	if ts == nil {
		return
	}
	g.rep.FilesResolved++

	if ts.KeySource == "filename" {
		g.rep.MigrationItems[canonical]++
	}

	// required fields — minus anything the alias supplies, because after migration it will
	// be present, and reporting it now would double-count the alias's own work.
	//
	// THREE STATES, NOT TWO. `blocks: []` is a DECLARATION that there are no blocks; a
	// missing `blocks:` key is silence. Collapsing them was a defect in the first cut of
	// this gate (and the Python cross-check collapsed them the other way, calling
	// block-style lists missing). The corpus's own adversary makes the same distinction:
	// "all 41 story behavioral_contracts frontmatter arrays are empty" is filed as a
	// NITPICK, not as a missing field.
	for _, f := range g.b.RequiredFor(ts) {
		if _, ok := set[f]; ok {
			continue
		}
		_, present := fm[f]
		if !present {
			g.find("field.missing:"+f, rel, ClassRegField,
				fmt.Sprintf("%s requires %q and the key is absent", canonical, f))
			continue
		}
		if strings.TrimSpace(fm.Scalar(f)) == "" && len(fm.List(f)) == 0 {
			g.find("field.empty:"+f, rel, ClassRegField,
				fmt.Sprintf("%s declares %q but it is empty — a declaration of none, weaker than absence", canonical, f))
		}
	}

	// retired / forbidden fields
	for f := range forbidden {
		if _, present := fm[f]; present {
			g.find("field.retired:"+f, rel, ClassRegField,
				fmt.Sprintf("%s is retired; %s still carries it", f, canonical))
		}
	}

	// closed enums
	for field, enumName := range ts.Enums {
		v := strings.TrimSpace(fm.Scalar(field))
		if v == "" {
			continue
		}
		switch g.b.CheckEnum(enumName, v) {
		case "migratable":
			g.find("enum.migratable:"+field, rel, ClassRegEnum,
				fmt.Sprintf("%s=%q is a known legacy value; enums.yaml migrated_from says where it goes", field, v))
		case "illegal":
			g.find("enum.illegal:"+field, rel, ClassRegEnum,
				fmt.Sprintf("%s=%q is outside the closed enum %q", field, v, enumName))
		}
	}

	// section schema
	switch ts.SectionPolicy {
	case "required_ordered", "required_unordered", "expected":
		have := map[string]bool{}
		for _, s := range SplitSections(body) {
			if s.Heading != "" {
				have[s.Heading] = true
			}
		}
		var missing []string
		for _, want := range ts.Sections {
			if !have[want] {
				missing = append(missing, want)
			}
		}
		if len(missing) > 0 {
			g.find("section.missing:"+canonical, rel, ClassRegSection,
				fmt.Sprintf("missing %d declared section(s): %s", len(missing), strings.Join(missing, ", ")))
		}
	}

	// D-A invariant, checked rather than trusted
	if ext == ".md" && !SectionsLossless(body) {
		g.find("invariant.section-partition-lossy", rel, ClassRegInvariant,
			"concat(sections) != body — the derived partition is not byte-exact, so render cannot be trusted")
	}
}

// PrintRegistryReport writes the human summary. Counts first: a gate that prints only
// failures gives no way to see the ratchet moving.
func PrintRegistryReport(w *os.File, rep *RegistryReport) {
	fmt.Fprintf(w, "\nregistry gate\n")
	fmt.Fprintf(w, "  scanned %d files · %d typed · %d resolved · %d via alias\n",
		rep.FilesScanned, rep.FilesTyped, rep.FilesResolved, rep.AliasApplied)
	if len(rep.ByStatus) > 0 {
		var keys []string
		for k := range rep.ByStatus {
			keys = append(keys, k)
		}
		sort.Strings(keys)
		var parts []string
		for _, k := range keys {
			parts = append(parts, fmt.Sprintf("%s %d", k, rep.ByStatus[k]))
		}
		fmt.Fprintf(w, "  type resolution: %s\n", strings.Join(parts, " · "))
	}
	if len(rep.MigrationItems) > 0 {
		var keys []string
		for k := range rep.MigrationItems {
			keys = append(keys, k)
		}
		sort.Strings(keys)
		fmt.Fprintf(w, "  ONE-TIME migration (key lives only in the filename today):\n")
		for _, k := range keys {
			fmt.Fprintf(w, "      %6d  %s\n", rep.MigrationItems[k], k)
		}
	}
	byClass := map[string]int{}
	byRule := map[string]int{}
	for _, f := range rep.Findings {
		byClass[f.Class]++
		byRule[f.Class+" "+f.Rule]++
	}
	if len(rep.Findings) == 0 {
		fmt.Fprintf(w, "  no registry findings\n")
		return
	}
	var classes []string
	for c := range byClass {
		classes = append(classes, c)
	}
	sort.Strings(classes)
	fmt.Fprintf(w, "  findings %d:", len(rep.Findings))
	for _, c := range classes {
		fmt.Fprintf(w, " %s %d", c, byClass[c])
	}
	fmt.Fprintln(w)
	type kv struct {
		k string
		n int
	}
	var rules []kv
	for k, n := range byRule {
		rules = append(rules, kv{k, n})
	}
	sort.Slice(rules, func(i, j int) bool {
		if rules[i].n != rules[j].n {
			return rules[i].n > rules[j].n
		}
		return rules[i].k < rules[j].k
	})
	for i, r := range rules {
		if i >= 12 {
			fmt.Fprintf(w, "      ... and %d more rules\n", len(rules)-12)
			break
		}
		fmt.Fprintf(w, "      %6d  %s\n", r.n, r.k)
	}
}
