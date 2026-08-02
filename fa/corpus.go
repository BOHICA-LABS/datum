package main

// Reading the markdown corpus. This file is pure: it turns a directory of
// markdown into records, edges, assertions and findings, and touches no database.
// That is what makes it unit-testable against a fixture (see corpus_test.go).
//
// Two rules make this a real check rather than a demo, and both were learned by
// getting them wrong:
//
//   1. Node universes come from AUTHORITATIVE DECLARING DOCUMENTS ONLY — the one
//      catalog that declares each ID class. If the universe were built from every
//      mention in the corpus, every reference would resolve trivially and the
//      integrity check would prove nothing.
//   2. A value that is not an ID, or an ID with prose glued on, is a TYPE
//      violation and is reported as such — never coerced, never dropped.

import (
	"fmt"
	"io/fs"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strconv"
	"strings"
)

// ---------------------------------------------------------------- model

// Finding is one violation. (Rule, Subject) is its stable identity — that pair is
// what the dated baseline allowlist keys on, so it must not embed line numbers,
// timestamps, or anything else that drifts without the violation changing.
type Finding struct {
	Rule    string `json:"rule"`
	Subject string `json:"subject"`
	Class   string `json:"class"`
	Detail  string `json:"detail,omitempty"`
}

// Finding classes.
const (
	ClassType      = "type"      // a field holds something that is not the declared ID type
	ClassDangling  = "dangling"  // a reference to a node that does not exist
	ClassCount     = "count"     // markdown asserts a count the data contradicts
	ClassIntegrity = "integrity" // structural: malformed id, prefix mismatch, duplicate
	ClassDirection = "direction" // the two hand-maintained directions disagree
	ClassCrossZone = "cross-zone"
)

type Assertion struct {
	Source  string
	Kind    string
	Subject string
	Claimed int64
	SrcPath string
}

type SubsystemRow struct {
	ID       string
	BCPrefix int
	Name     string
}

type BCRow struct {
	ID, SS, Title, Body, Capability, Version string
	LifecycleStatus, Status, Replacement     string
	SrcPath                                  string
}

type VPRow struct {
	ID, Title, Body, Version             string
	Scope, SourceBC, ProofMethod         string
	Feasibility, Module, VPType, SrcPath string
}

type StoryRow struct {
	ID, Title, Status               string
	Wave                            *int
	EpicID, Priority, Points, Cycle string
	Body, SrcPath                   string
}

// Edge is one relationship row. Label is the finding rule to record if a FOREIGN
// KEY refuses it — the rejection is the output, not an error to swallow.
type Edge struct {
	Table string
	Cols  []string
	Vals  []string
	Label string
}

type Corpus struct {
	Root       string
	Subsystems []SubsystemRow
	Universes  map[string]map[string]string // cap|di|nfr|fr|adr|epic -> id -> name
	BCs        []BCRow
	VPs        []VPRow
	Stories    []StoryRow
	Edges      []Edge
	Findings   []Finding
	Assertions []Assertion
	// STORY 4: review documents and their findings AS ROWS.
	Reviews  []ReviewRow
	FindingRows []FindingRow
	// Extraction accounting the caller must REPORT, never swallow.
	FindingDupes, FindingMalformed int
	// STORY 12a: AC/EC/PC/T-task as rows with typed links.
	SubArtifacts     []SubArtifactRow
	SubArtifactRefs  []SubArtifactRef
	SubArtifactDupes int
	// Enumerated is the set of BC ids the index ENUMERATES in its own table's
	// first column — the index's claim about which BCs exist, checked separately
	// from its claim about how many.
	Enumerated []string
}

func (c *Corpus) find(rule, subject, class, detail string) {
	c.Findings = append(c.Findings, Finding{Rule: rule, Subject: subject, Class: class, Detail: detail})
}

// ---------------------------------------------------------------- id patterns

var (
	reBCID    = regexp.MustCompile(`BC-\d+\.\d+\.\d+`)
	reBCIDFul = regexp.MustCompile(`^BC-\d+\.\d+\.\d+$`)
	reVPID    = regexp.MustCompile(`VP-\d+`)
	reSSID    = regexp.MustCompile(`SS-\d+`)
	reDIID    = regexp.MustCompile(`DI-\d+`)
	reNFRID   = regexp.MustCompile(`NFR-[A-Z]+-\d+`)
	reFRID    = regexp.MustCompile(`FR-[A-Z0-9-]*\d+`)
	reStoryID = regexp.MustCompile(`S-[\d.]+`)

	reBCFile    = regexp.MustCompile(`^(BC-\d+\.\d+\.\d+)`)
	reVPFile    = regexp.MustCompile(`^(VP-\d+)`)
	reStoryFile = regexp.MustCompile(`^(S-[\d.]+)`)
)

// ---------------------------------------------------------------- scan

// ScanCorpus reads a .factory tree. It never fails on a bad document: a document
// that cannot be interpreted becomes a finding, because silently skipping input
// is how a checker reports a false clean.
func ScanCorpus(root string) (*Corpus, error) {
	st, err := os.Stat(root)
	if err != nil {
		return nil, err
	}
	if !st.IsDir() {
		return nil, fmt.Errorf("%s is not a directory", root)
	}
	c := &Corpus{Root: root, Universes: map[string]map[string]string{}}

	c.loadUniverses()
	c.loadSubsystems()
	c.loadVPs() // before BCs: bc_trace and vp_bc point at VPs
	c.loadBCs()
	c.loadStories()
	c.loadAssertions()
	c.loadReviews()
	c.loadSubArtifacts()
	return c, nil
}

func read(path string) (string, bool) {
	b, err := os.ReadFile(path)
	if err != nil {
		return "", false
	}
	return string(b), true
}

// headings extracts an ID universe from ONE declaring document.
//
// The corpus declares IDs in three shapes, all authoritative:
//
//  1. heading:    ### NFR-PERF-001: ...
//  2. bold line:  **CAP-001 — ...**
//  3. table row:  | FR-037 | ... |
//
// The bold form must NOT be anchored to end-of-line: the corpus appends an
// amendment suffix after the closing '**', e.g.
//
//	**DI-019 — ASYNC_DRAIN_WINDOW_MS = 100** _(v1.5 — amended ...)_
//
// Anchoring there silently lost DI-017 and DI-019 from the universe, which then
// made two real dangling references look valid.
func headings(path, pat string) map[string]string {
	got := map[string]string{}
	text, ok := read(path)
	if !ok {
		return got
	}
	res := []*regexp.Regexp{
		regexp.MustCompile(`^#+\s+(` + pat + `)[:\s\x{2014}-]*(.*)$`),
		regexp.MustCompile(`^\*\*(` + pat + `)\s*[\x{2014}:-]*\s*(.*?)\*\*`),
		regexp.MustCompile(`^\|\s*\*{0,2}(` + pat + `)\*{0,2}\s*\|(.*)$`),
	}
	for _, ln := range strings.Split(text, "\n") {
		s := strings.TrimSpace(ln)
		for _, re := range res {
			m := re.FindStringSubmatch(s)
			if m == nil {
				continue
			}
			id := m[1]
			if _, exists := got[id]; !exists {
				name := strings.TrimSpace(strings.SplitN(m[2], "|", 2)[0])
				got[id] = truncRunes(name, 400)
			}
			break
		}
	}
	return got
}

func (c *Corpus) loadUniverses() {
	ds := filepath.Join(c.Root, "specs", "domain-spec")
	prd := filepath.Join(c.Root, "specs", "prd.md")

	c.Universes["cap"] = headings(filepath.Join(ds, "capabilities.md"), `CAP-\d+`)
	c.Universes["di"] = headings(filepath.Join(ds, "invariants.md"), `DI-\d+`)
	c.Universes["fr"] = headings(prd, `FR-\d+`)

	// NFRs: the authoritative registry is the phase-0 catalog (NOT under specs/),
	// unioned with the handful declared in the PRD table.
	nfr := headings(filepath.Join(c.Root, "phase-0-ingestion", "pass-4-nfr-catalog.md"), `NFR-[A-Z]+-\d+`)
	for k, v := range headings(prd, `NFR-[A-Z]+-\d+`) {
		if _, ok := nfr[k]; !ok {
			nfr[k] = v
		}
	}
	c.Universes["nfr"] = nfr

	adr := map[string]string{}
	matches, _ := filepath.Glob(filepath.Join(c.Root, "specs", "architecture", "*.md"))
	sort.Strings(matches)
	for _, f := range matches {
		for k, v := range headings(f, `ADR-\d+`) {
			adr[k] = v
		}
	}
	c.Universes["adr"] = adr

	epic := map[string]string{}
	eps, _ := filepath.Glob(filepath.Join(c.Root, "stories", "epics", "E-*.md"))
	sort.Strings(eps)
	reE := regexp.MustCompile(`^(E-\d+)`)
	for _, f := range eps {
		base := filepath.Base(f)
		m := reE.FindStringSubmatch(base)
		if m == nil {
			continue
		}
		stem := strings.TrimSuffix(base, ".md")
		name := ""
		if len(stem) > len(m[1])+1 {
			name = strings.ReplaceAll(stem[len(m[1])+1:], "-", " ")
		}
		epic[m[1]] = truncRunes(name, 400)
	}
	c.Universes["epic"] = epic
}

var reArchSSRow = regexp.MustCompile(`\|\s*(SS-\d+)\s*\|\s*([^|]+?)\s*\|\s*BC-(\d+)\s*\|`)

func (c *Corpus) loadSubsystems() {
	rows := map[string]SubsystemRow{}
	if text, ok := read(filepath.Join(c.Root, "specs", "architecture", "ARCH-INDEX.md")); ok {
		for _, ln := range strings.Split(text, "\n") {
			if m := reArchSSRow.FindStringSubmatch(ln); m != nil {
				n, _ := strconv.Atoi(m[3])
				if _, exists := rows[m[1]]; !exists {
					rows[m[1]] = SubsystemRow{ID: m[1], BCPrefix: n, Name: truncRunes(strings.TrimSpace(m[2]), 200)}
				}
			}
		}
	}
	// Fall back to subsystems observed on disk, so import never silently drops BCs
	// because the registry is incomplete.
	dirs, _ := filepath.Glob(filepath.Join(c.Root, "specs", "behavioral-contracts", "ss-*"))
	sort.Strings(dirs)
	for _, d := range dirs {
		parts := strings.Split(filepath.Base(d), "-")
		if len(parts) < 2 {
			continue
		}
		n, err := strconv.Atoi(parts[1])
		if err != nil {
			continue
		}
		id := fmt.Sprintf("SS-%02d", n)
		if _, exists := rows[id]; !exists {
			rows[id] = SubsystemRow{ID: id, BCPrefix: n, Name: id}
		}
	}
	ids := make([]string, 0, len(rows))
	for id := range rows {
		ids = append(ids, id)
	}
	sort.Strings(ids)
	for _, id := range ids {
		c.Subsystems = append(c.Subsystems, rows[id])
	}
}

// ids coerces an ID-typed field to IDs, recording TYPE violations.
//
// The corpus writes things like `subsystems: ["SS-04 (Plugin Ecosystem)"]` — an
// ID with prose glued on. That is a schema violation in its own right, distinct
// from a dangling reference, so it is reported as such rather than surfacing as
// an opaque column-width error (or, worse, being silently trimmed).
//
// `owner` makes the finding subject stable and unique: the prototype recorded
// only the offending value, so two records committing the same violation
// collapsed into one baseline entry.
func (c *Corpus) ids(raw []string, re *regexp.Regexp, field, owner string) []string {
	var out []string
	for _, rv := range raw {
		m := re.FindString(rv)
		if m == "" {
			c.find(field+" value is not an id", owner+" -> "+truncRunes(rv, 60), ClassType, "")
			continue
		}
		if m != strings.TrimSpace(rv) {
			c.find(field+" holds an id plus prose", owner+" -> "+truncRunes(rv, 60), ClassType, "")
		}
		out = append(out, m)
	}
	return out
}

func (c *Corpus) edge(table string, cols, vals []string, label string) {
	c.Edges = append(c.Edges, Edge{Table: table, Cols: cols, Vals: vals, Label: label})
}

// walkMD walks a subtree calling fn for every .md file whose base name matches re.
// Sorted, so an import is deterministic and two runs produce identical commits.
func walkMD(root string, re *regexp.Regexp, fn func(path, base string)) {
	var found []string
	_ = filepath.WalkDir(root, func(p string, d fs.DirEntry, err error) error {
		if err != nil {
			return nil // an unreadable subtree is not a reason to abandon the scan
		}
		if d.IsDir() {
			return nil
		}
		if !strings.HasSuffix(d.Name(), ".md") || !re.MatchString(d.Name()) {
			return nil
		}
		found = append(found, p)
		return nil
	})
	sort.Strings(found)
	for _, p := range found {
		fn(p, filepath.Base(p))
	}
}

func (c *Corpus) rel(p string) string {
	if r, err := filepath.Rel(c.Root, p); err == nil {
		return r
	}
	return p
}

func (c *Corpus) loadVPs() {
	dir := filepath.Join(c.Root, "specs", "verification-properties")
	walkMD(dir, reVPFile, func(path, base string) {
		id := reVPFile.FindStringSubmatch(base)[1]
		text, _ := read(path)
		fm, body := ParseFrontmatter(text)

		// `scope` is DECLARED scalar but the corpus also uses "SS-01, SS-03".
		// Model it as the M:N relation it actually is, and flag the multi-valued
		// ones — the field's own declaration is what is wrong.
		var scopes []string
		for _, tok := range regexp.MustCompile(`[,\s]+`).Split(strings.Join(fm.List("scope"), " "), -1) {
			tok = strings.TrimSpace(tok)
			if regexp.MustCompile(`^SS-\d+$`).MatchString(tok) {
				scopes = append(scopes, tok)
			}
		}
		if len(scopes) > 1 {
			c.find("VP.scope is multi-valued in a scalar-declared field",
				id+" -> "+strings.Join(scopes, ","), ClassType, "")
		}
		scope := ""
		if len(scopes) == 1 {
			scope = scopes[0]
		}
		title := firstH1(body)
		if title == "" {
			title = id
		}
		version := fm.Scalar("version")
		if version == "" {
			version = "v1.0"
		}
		c.VPs = append(c.VPs, VPRow{
			ID: id, Title: truncRunes(title, 1000), Body: body,
			Version: truncRunes(version, 16), Scope: scope,
			SourceBC: fm.Scalar("source_bc"), ProofMethod: truncRunes(fm.Scalar("proof_method"), 64),
			Feasibility: truncRunes(fm.Scalar("feasibility"), 64), Module: fm.Scalar("module"),
			VPType: truncRunes(fm.Scalar("type"), 64), SrcPath: c.rel(path),
		})

		for _, ss := range scopes {
			c.edge("vp_subsystem", []string{"vp_id", "ss_id"}, []string{id, ss}, "VP.scope -> missing SS")
		}
		for _, bc := range c.ids(fm.List("bcs"), reBCID, "VP.bcs", id) {
			c.edge("vp_bc", []string{"vp_id", "bc_id"}, []string{id, bc}, "VP.bcs -> missing BC")
		}
		for _, bc := range c.ids(fm.List("source_bc"), reBCID, "VP.source_bc", id) {
			c.edge("vp_bc", []string{"vp_id", "bc_id"}, []string{id, bc}, "VP.source_bc -> missing BC")
		}
		for _, di := range c.ids(fm.List("domain_invariants"), reDIID, "VP.domain_invariants", id) {
			c.edge("vp_di", []string{"vp_id", "di_id"}, []string{id, di}, "VP.domain_invariants -> missing DI")
		}
		for _, nf := range c.ids(fm.List("nfrs"), reNFRID, "VP.nfrs", id) {
			c.edge("vp_nfr", []string{"vp_id", "nfr_id"}, []string{id, nf}, "VP.nfrs -> missing NFR")
		}
	})
}

func (c *Corpus) loadBCs() {
	ssKnown := map[string]bool{}
	for _, s := range c.Subsystems {
		ssKnown[s.ID] = true
	}
	dir := filepath.Join(c.Root, "specs", "behavioral-contracts")
	walkMD(dir, reBCFile, func(path, base string) {
		if base == "BC-INDEX.md" {
			return
		}
		id := reBCFile.FindStringSubmatch(base)[1]
		text, _ := read(path)
		fm, body := ParseFrontmatter(text)

		// The authoritative subsystem is the FRONTMATTER, not the directory: the
		// corpus documents files whose directory and frontmatter disagree, and the
		// index was re-tallied to frontmatter for exactly that reason.
		ss := strings.TrimSpace(fm.Scalar("subsystem"))
		if ss == "" {
			ss = strings.TrimSpace(fm.Scalar("ss"))
		}
		if !regexp.MustCompile(`^SS-\d+$`).MatchString(ss) {
			parent := filepath.Base(filepath.Dir(path))
			if strings.HasPrefix(parent, "ss-") {
				p := strings.Split(parent, "-")
				ss = "SS-" + p[len(p)-1]
			}
		}
		if !ssKnown[ss] {
			c.find("bc declares an unknown subsystem", id+" -> "+truncRunes(ss, 40), ClassDangling,
				"file "+c.rel(path))
			return
		}

		cap := fm.Scalar("capability")
		if !regexp.MustCompile(`^CAP-\d+$`).MatchString(cap) {
			cap = ""
		}
		// `replacement` is declared as a BC pointer. Enforce the TYPE: anything
		// that is not a BC id is a schema violation, recorded rather than coerced.
		repl := fm.Scalar("replacement")
		if repl != "" && !reBCIDFul.MatchString(repl) {
			c.find("bc.replacement holds prose, not a BC id", id+" -> "+truncRunes(repl, 60), ClassType, "")
			repl = ""
		}
		title := firstH1(body)
		if title == "" {
			title = id
		}
		version := fm.Scalar("version")
		if version == "" {
			version = "v1.0"
		}
		c.BCs = append(c.BCs, BCRow{
			ID: id, SS: ss, Title: truncRunes(title, 1000), Body: body,
			Capability: cap, Version: truncRunes(version, 16),
			LifecycleStatus: truncRunes(fm.Scalar("lifecycle_status"), 24),
			Status:          truncRunes(fm.Scalar("status"), 24),
			Replacement:     repl, SrcPath: c.rel(path),
		})
	})
}

func (c *Corpus) loadStories() {
	dir := filepath.Join(c.Root, "stories")

	// Pass 1: rows, keyed by the filename-derived id.
	known := map[string]bool{}
	walkMD(dir, reStoryFile, func(path, base string) {
		id := strings.TrimRight(reStoryFile.FindStringSubmatch(base)[1], ".")
		text, body := "", ""
		text, _ = read(path)
		fm, b := ParseFrontmatter(text)
		body = b
		if known[id] {
			c.find("two files claim the same story id", id+" -> "+c.rel(path), ClassIntegrity, "")
			return
		}
		known[id] = true
		var wave *int
		if w, err := strconv.Atoi(fm.Scalar("wave")); err == nil {
			wave = &w
		}
		title := firstH1(body)
		if title == "" {
			title = id
		}
		status := fm.Scalar("status")
		if status == "" {
			status = "pending"
		}
		c.Stories = append(c.Stories, StoryRow{
			ID: id, Title: truncRunes(title, 1000), Status: truncRunes(status, 24), Wave: wave,
			EpicID: fm.Scalar("epic_id"), Priority: truncRunes(fm.Scalar("priority"), 8),
			Points: truncRunes(fm.Scalar("points"), 8), Cycle: truncRunes(fm.Scalar("cycle"), 64),
			Body: body, SrcPath: c.rel(path),
		})
	})

	// Pass 2: edges. A story may declare its own id in frontmatter; prefer that,
	// fall back to the filename, and skip a file whose id has no row (its id form
	// differs from every row, which pass 1 would already have surfaced).
	walkMD(dir, reStoryFile, func(path, base string) {
		text, _ := read(path)
		fm, _ := ParseFrontmatter(text)
		sid := fm.Scalar("story_id")
		if sid == "" {
			sid = strings.TrimRight(reStoryFile.FindStringSubmatch(base)[1], ".")
		}
		if !known[sid] {
			return
		}
		for _, bc := range c.ids(fm.List("behavioral_contracts"), reBCID, "story.behavioral_contracts", sid) {
			c.edge("story_bc", []string{"story_id", "bc_id"}, []string{sid, bc}, "story.behavioral_contracts -> missing BC")
		}
		for _, vp := range c.ids(fm.List("verification_properties"), reVPID, "story.verification_properties", sid) {
			c.edge("story_vp", []string{"story_id", "vp_id"}, []string{sid, vp}, "story.verification_properties -> missing VP")
		}
		for _, fr := range c.ids(fm.List("functional_requirements"), reFRID, "story.functional_requirements", sid) {
			c.edge("story_fr", []string{"story_id", "fr_id"}, []string{sid, fr}, "story.functional_requirements -> missing FR")
		}
		for _, ss := range c.ids(fm.List("subsystems"), reSSID, "story.subsystems", sid) {
			c.edge("story_subsystem", []string{"story_id", "ss_id"}, []string{sid, ss}, "story.subsystems -> missing SS")
		}
		// depends_on / blocks are story-typed. The corpus puts EPIC ids in these
		// fields; ids() reports that as the type violation it is.
		for _, d := range c.ids(fm.List("depends_on"), reStoryID, "story.depends_on", sid) {
			c.edge("story_dep", []string{"story_id", "dep_id", "kind"}, []string{sid, d, "depends_on"},
				"story.depends_on -> missing story")
		}
		for _, b := range c.ids(fm.List("blocks"), reStoryID, "story.blocks", sid) {
			c.edge("story_dep", []string{"story_id", "dep_id", "kind"}, []string{sid, b, "blocks"},
				"story.blocks -> missing story")
		}
	})
}

// ---------------------------------------------------------------- assertions

var (
	reIdxTotalRow = regexp.MustCompile(`^\|\s*\*{0,2}Total\*{0,2}\s*\|[^|]*\|\s*\*{0,2}([\d,]+)\*{0,2}`)
	reIdxSSRow    = regexp.MustCompile(`^\|\s*(SS-\d+)[^|]*\|\s*BC-\d+\s*\|\s*([\d,]+)`)
	reIdxSSHead   = regexp.MustCompile(`^#+\s+(SS-\d+)\b.*?\x{2014}\s*([\d,]+)\s+BCs`)
	reArchTotal   = regexp.MustCompile(`\*\*Total BCs:\s*\*{0,2}([\d,]+)`)
	reIdxEnumRow  = regexp.MustCompile(`^\|\s*\[?(BC-\d+\.\d+\.\d+)\]?`)
)

func atoiCommas(s string) int64 {
	n, _ := strconv.ParseInt(strings.ReplaceAll(s, ",", ""), 10, 64)
	return n
}

// loadAssertions records what the markdown CLAIMS about itself.
//
// This is the one place the store keeps a number rather than deriving it, and it
// is deliberate: `fa validate` compares each claim against COUNT(*). The live
// corpus asserts the BC total in several places and they do not agree — the
// headline finding of the whole spike.
func (c *Corpus) loadAssertions() {
	idx := filepath.Join(c.Root, "specs", "behavioral-contracts", "BC-INDEX.md")
	if text, ok := read(idx); ok {
		rel := c.rel(idx)
		fm, body := ParseFrontmatter(text)
		if v := fm.Scalar("total_bcs"); v != "" {
			c.Assertions = append(c.Assertions, Assertion{
				Source: "BC-INDEX.md frontmatter total_bcs", Kind: "bc_total", Claimed: atoiCommas(v), SrcPath: rel})
		}
		for _, ln := range strings.Split(body, "\n") {
			s := strings.TrimSpace(ln)
			switch {
			case reIdxTotalRow.MatchString(s):
				m := reIdxTotalRow.FindStringSubmatch(s)
				c.Assertions = append(c.Assertions, Assertion{
					Source: "BC-INDEX.md body Total row", Kind: "bc_total", Claimed: atoiCommas(m[1]), SrcPath: rel})
			case reIdxSSRow.MatchString(s):
				m := reIdxSSRow.FindStringSubmatch(s)
				c.Assertions = append(c.Assertions, Assertion{
					Source: "BC-INDEX.md subsystem registry row", Kind: "bc_count_ss",
					Subject: m[1], Claimed: atoiCommas(m[2]), SrcPath: rel})
			case reIdxSSHead.MatchString(s):
				m := reIdxSSHead.FindStringSubmatch(s)
				c.Assertions = append(c.Assertions, Assertion{
					Source: "BC-INDEX.md section heading", Kind: "bc_count_ss",
					Subject: m[1], Claimed: atoiCommas(m[2]), SrcPath: rel})
			}
			// The index's claim about WHICH BCs exist, kept separate from its claim
			// about how many. Only the first column counts: a BC id in a Title or
			// Stories cell is a mention, not an enumeration.
			if m := reIdxEnumRow.FindStringSubmatch(s); m != nil {
				c.Enumerated = append(c.Enumerated, m[1])
			}
		}
	}

	arch := filepath.Join(c.Root, "specs", "architecture", "ARCH-INDEX.md")
	if text, ok := read(arch); ok {
		for _, ln := range strings.Split(text, "\n") {
			if m := reArchTotal.FindStringSubmatch(strings.TrimSpace(ln)); m != nil {
				c.Assertions = append(c.Assertions, Assertion{
					Source: "ARCH-INDEX.md Total BCs", Kind: "bc_total",
					Claimed: atoiCommas(m[1]), SrcPath: c.rel(arch)})
				break // the first statement is the authoritative one; the rest is changelog prose
			}
		}
	}

	// Deduplicate: the same (source, kind, subject) may appear twice in a file
	// (e.g. a registry table repeated in a changelog quote). First wins, so the
	// PK insert cannot collide.
	seen := map[string]bool{}
	var keep []Assertion
	for _, a := range c.Assertions {
		k := a.Source + "\x00" + a.Kind + "\x00" + a.Subject
		if seen[k] {
			continue
		}
		seen[k] = true
		keep = append(keep, a)
	}
	c.Assertions = keep
}
