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
	// STORY 12b: the minimal permanent prose extractor.
	ProseRefs        []ProseRefRow
	VersionCites     []VersionCiteRow
	CiteTargetsKnown int
	// Per-type match censuses. Held so `datum import` can PRINT per-form counts rather
	// than only recording findings — instance nine was invisible precisely because the
	// import report had no place to say "this type matched 0 of 80 files".
	BCCensus, VPCensus, StoryCensus MatchCensus
	// KeyCollisions are duplicate natural keys. Kept in FULL, never dropped.
	KeyCollisions []KeyCollision
	// LedgerFields are append-only ledgers found serialised into a scalar field.
	LedgerFields []LedgerField
	// Enumerated is the set of BC ids the index ENUMERATES in its own table's
	// first column — the index's claim about which BCs exist, checked separately
	// from its claim about how many.
	Enumerated []string
}

func (c *Corpus) find(rule, subject, class, detail string) {
	c.Findings = append(c.Findings, Finding{Rule: rule, Subject: subject, Class: class, Detail: detail})
}

// KeyCollision is a duplicate natural key, recorded IN FULL.
//
// One condition had three incompatible behaviours, which is its own defect:
//   - `bc`    filed a finding and DROPPED the second row
//   - `story` silently kept the FIRST file and dropped the second at scan time
//   - `vp`    had no check at all, so the PK insert HARD-ABORTED the whole import
//
// That third behaviour is why rivetry could not be imported at all: 211
// `.DELTA-ARCHIVE` sidecars produce 143 key collisions and one of them killed the run.
//
// The single behaviour is: FILE A FINDING AND KEEP BOTH. The winner (first in sorted
// path order, so it is deterministic) occupies the typed table; every loser is stored
// here in full, with the winner it collided with, so nothing is lost and the pair is
// queryable and adjudicable. Import stays tolerant at the INGEST boundary (V-J) and
// the duplicate becomes DATA rather than a crash or a silent drop.
type KeyCollision struct {
	Kind     string // artifact kind: bc | vp | story
	Key      string // the canonical natural key both files claim
	WinPath  string // the path that occupies the typed table
	LosePath string // the path recorded here instead
	Title    string
	Body     string
}

// collide records a duplicate natural key uniformly. Returns true if the caller must
// SKIP its typed-table insert (i.e. this key is already taken).
func (c *Corpus) collide(kind, key, winPath, losePath, title, body string) bool {
	c.find("two files claim the same "+kind+" id",
		key+" -> "+losePath, ClassIntegrity, "kept as a key_collision row; winner "+winPath)
	c.KeyCollisions = append(c.KeyCollisions, KeyCollision{
		Kind: kind, Key: key, WinPath: winPath, LosePath: losePath,
		Title: truncRunes(title, 1000), Body: body,
	})
	return true
}

// LedgerField is one frontmatter field that carries a serialised ledger, split into
// its entries. See ledger.go for why this is a field-level concern.
type LedgerField struct {
	CitingKey  string
	CitingType string
	Field      string
	Entries    []LedgerEntry
	Unbalanced bool
}

// sweepLedgers finds ledger-shaped fields across the WHOLE corpus.
//
// It is a corpus-wide sweep rather than a per-loader hook because the biggest ledger in
// the corpus is on a document no typed loader reads: `stories/STORY-INDEX.md` carries a
// 116-entry, 50,785-character `last_amended`, and its filename matches no typed id
// pattern. Hooking only bc/vp/story captured 62 entries and missed 116 in one field --
// the same completeness failure this whole task is about, one level up.
//
// KEY CHOICE: the typed canonical id when the filename yields one, otherwise the
// corpus-relative path. Using the path here does NOT violate D-C, which forbids path as
// IDENTITY, not path as a migration-time source -- exactly the latitude V-G already
// established for backfilling review keys. Cohort D will replace it with a declared key.
func (c *Corpus) sweepLedgers() {
	var files []string
	_ = filepath.WalkDir(c.Root, func(p string, d fs.DirEntry, err error) error {
		if err != nil {
			return nil
		}
		if d.IsDir() {
			if d.Name() == ".git" {
				return filepath.SkipDir
			}
			return nil
		}
		if strings.HasSuffix(d.Name(), ".md") {
			files = append(files, p)
		}
		return nil
	})
	sort.Strings(files) // deterministic: two imports must produce identical commits
	for _, p := range files {
		text, ok := read(p)
		if !ok {
			continue
		}
		fm, _ := ParseFrontmatter(text)
		if len(fm) == 0 {
			continue
		}
		base := filepath.Base(p)
		key := c.rel(p)
		switch {
		case reBCFile.MatchString(base) && !strings.EqualFold(base, "BC-INDEX.md"):
			key = canonicalID(reBCFile.FindStringSubmatch(base)[1])
		case reVPFile.MatchString(base):
			key = canonicalID(reVPFile.FindStringSubmatch(base)[1])
		case reStoryFile.MatchString(base):
			key = canonicalID(strings.TrimRight(reStoryFile.FindStringSubmatch(base)[1], "."))
		}
		ctype := fm.Scalar("document_type")
		if ctype == "" {
			ctype = "(untyped)"
		}
		c.scanLedgers(truncRunes(key, 300), truncRunes(ctype, 64), fm)
	}
}

// scanLedgers records every ledger-shaped field on one document. Called by each loader
// that has already parsed a document's frontmatter, so no file is read twice.
//
// The round trip is asserted HERE, at ingest, not only in tests: a split that cannot be
// rejoined byte-exact is a data-loss event and must be a finding at the moment it
// happens (the conservation gate, zero tolerance).
func (c *Corpus) scanLedgers(citingKey, citingType string, fm Frontmatter) {
	keys := make([]string, 0, len(fm))
	for k := range fm {
		keys = append(keys, k)
	}
	sort.Strings(keys) // deterministic order, so two imports produce identical commits
	for _, k := range keys {
		v := fm.Scalar(k)
		if v == "" || !LooksLikeLedger(k, v) {
			continue
		}
		entries := SplitLedger(v)
		if JoinLedger(entries) != v {
			c.find("a ledger field could not be split reversibly",
				citingKey+" -> "+k, ClassIntegrity, "CONSERVATION FAILURE: split is not byte-exact")
			continue
		}
		_, _, unbalanced := LedgerImbalance(v)
		if unbalanced {
			o, cl, _ := LedgerImbalance(v)
			c.find("a ledger field has unbalanced nesting brackets",
				citingKey+" -> "+k, ClassIntegrity,
				fmt.Sprintf("%d openers vs %d closers; recorded as written, NOT repaired", o, cl))
		}
		c.LedgerFields = append(c.LedgerFields, LedgerField{
			CitingKey: citingKey, CitingType: citingType, Field: k,
			Entries: entries, Unbalanced: unbalanced,
		})
	}
}

// ---------------------------------------------------------------- id patterns

var (
	reBCID    = regexp.MustCompile(`BC-\d+\.\d+\.\d+`)
	reBCIDFul = regexp.MustCompile(`^BC-\d+\.\d+\.\d+$`)
	reVPID    = regexp.MustCompile(`VP-\d+`)
	reSSID    = regexp.MustCompile(`SS-\d+`)
	reSSIDFull = regexp.MustCompile(`^SS-\d+$`)
	reDIID    = regexp.MustCompile(`DI-\d+`)
	reNFRID   = regexp.MustCompile(`NFR-[A-Z]+-\d+`)
	reFRID    = regexp.MustCompile(`FR-[A-Z0-9-]*\d+`)
	reStoryID = regexp.MustCompile(`S-[\d.]+`)

	// ⚠ THESE ARE CASE-INSENSITIVE, AND THAT IS LOAD-BEARING.
	//
	// These patterns are not merely id extractors — walkMD uses them as its FILTER,
	// so a name they do not match is skipped WITH NO ERROR. `^(VP-\d+)` was
	// case-SENSITIVE, and prism names all 80 of its verification properties
	// `vp-001-*.md`: prism's entire L4 layer imported as ZERO ROWS and nothing
	// reported it. That was instance NINE of this repo's most-repeated defect class
	// — a parser that silently loses input — and the first one inside `datum` itself.
	//
	// A corpus is entitled to spell its filenames how it likes; a matcher that drops
	// legal input is the defect. Every id extracted through these MUST go through
	// canonicalID so `vp-001` and `VP-001` become one key rather than two.
	//
	// Case-insensitivity alone is not the fix: a future matcher can be wrong in some
	// new way. walkMD therefore also counts what it matched per case-form and what it
	// SKIPPED, and loadX reports a directory that exists but yielded nothing — so the
	// failure mode becomes loud instead of silent. See walkMDCounted.
	reBCFile    = regexp.MustCompile(`(?i)^(BC-\d+\.\d+\.\d+)`)
	reVPFile    = regexp.MustCompile(`(?i)^(VP-\d+)`)
	reStoryFile = regexp.MustCompile(`(?i)^(S-[\d.]+)`)
)

// canonicalID normalises an id extracted from a filename to its canonical form, so a
// case variant is the SAME artifact rather than a second one. Uppercasing the alpha
// prefix is sufficient for every declared id form (BC-, VP-, S-, SS-, DI-, NFR-, FR-)
// because all of them are uppercase-canonical with numeric tails.
func canonicalID(id string) string { return strings.ToUpper(id) }

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
	c.loadProseRefs()
	c.sweepLedgers()
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
	fromIndex := len(rows)

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
	fromDirs := len(rows) - fromIndex

	// THIRD SOURCE: the subsystems the BCs THEMSELVES DECLARE.
	//
	// Both sources above encode vsdd-factory's LAYOUT — an `ARCH-INDEX.md` whose rows
	// match one regex, and `ss-NN/` subdirectories. prism uses neither: it stores all
	// 270 BCs FLAT under specs/behavioral-contracts/, and its ARCH-INDEX.md rows do not
	// match reArchSSRow. So the catalog came back EMPTY and every one of prism's 269 BCs
	// was rejected as "bc declares an unknown subsystem" -- bc=0.
	//
	// The BCs were never ambiguous about it: 270 of them carry `subsystem: "SS-01"` and
	// friends in frontmatter, and loadBCs already treats frontmatter as authoritative
	// over the directory. Only the CATALOG was layout-derived. V-F says every project
	// migrates and conventions differ per project, so a catalog built from one project's
	// filesystem shape is not a catalog.
	//
	// Reading the vocabulary from the DATA rather than from a layout convention is the
	// same rule as "read the vocabulary FROM the registry" (five instances). The
	// shortfall is reported, so an incomplete ARCH-INDEX stays visible instead of being
	// silently papered over by this fallback.
	declared := map[string]bool{}
	walkMD(filepath.Join(c.Root, "specs", "behavioral-contracts"), reBCFile, func(path, base string) {
		if strings.EqualFold(base, "BC-INDEX.md") {
			return
		}
		text, ok := read(path)
		if !ok {
			return
		}
		fm, _ := ParseFrontmatter(text)
		ss := strings.TrimSpace(fm.Scalar("subsystem"))
		if ss == "" {
			ss = strings.TrimSpace(fm.Scalar("ss"))
		}
		if !reSSIDFull.MatchString(ss) {
			return
		}
		declared[ss] = true
		if _, exists := rows[ss]; !exists {
			n, _ := strconv.Atoi(strings.TrimPrefix(ss, "SS-"))
			rows[ss] = SubsystemRow{ID: ss, BCPrefix: n, Name: ss}
		}
	})
	if fromBCs := len(rows) - fromIndex - fromDirs; fromBCs > 0 {
		c.find("subsystem catalog is incomplete: subsystems exist only in BC frontmatter",
			fmt.Sprintf("%d recovered from BC frontmatter (index %d, dirs %d)",
				fromBCs, fromIndex, fromDirs), ClassIntegrity,
			"ARCH-INDEX.md and ss-*/ layout did not declare them")
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
	walkMDCounted(root, re, fn)
}

// MatchCensus is what walkMD SAW, not only what it kept. It exists because the filter
// silently dropping input is this repo's most repeated defect class (nine instances),
// and the ninth was in this very function's caller. "Print per-form counts; report
// malformed; never drop" is only enforceable if the walker actually counts.
type MatchCensus struct {
	DirExists bool
	MDFiles   int            // .md files seen in the subtree
	Matched   int            // .md files the filter accepted
	Skipped   int            // .md files the filter REJECTED — the silent-loss surface
	SkipSample []string      // up to 10 rejected names, so a report can name them
	Forms     map[string]int // matched id-prefix case form -> count (e.g. "VP-" 80, "vp-" 0)
}

// walkMDCounted is walkMD with a census. Every loader uses it so that "this directory
// exists but produced nothing" is reportable rather than indistinguishable from "this
// project does not use this type".
func walkMDCounted(root string, re *regexp.Regexp, fn func(path, base string)) MatchCensus {
	cen := MatchCensus{Forms: map[string]int{}}
	if st, err := os.Stat(root); err == nil && st.IsDir() {
		cen.DirExists = true
	}
	var found []string
	_ = filepath.WalkDir(root, func(p string, d fs.DirEntry, err error) error {
		if err != nil {
			return nil // an unreadable subtree is not a reason to abandon the scan
		}
		if d.IsDir() {
			return nil
		}
		if !strings.HasSuffix(d.Name(), ".md") {
			return nil
		}
		cen.MDFiles++
		m := re.FindStringSubmatch(d.Name())
		if m == nil {
			cen.Skipped++
			if len(cen.SkipSample) < 10 {
				cen.SkipSample = append(cen.SkipSample, d.Name())
			}
			return nil
		}
		cen.Matched++
		// record the CASE FORM actually on disk, so a case-only divergence between
		// projects is visible in the import report instead of being normalised away.
		if len(m) > 1 {
			if i := strings.IndexAny(m[1], "-0123456789"); i > 0 {
				cen.Forms[m[1][:i+1]]++
			}
		}
		found = append(found, p)
		return nil
	})
	sort.Strings(found)
	for _, p := range found {
		fn(p, filepath.Base(p))
	}
	return cen
}

// noteCensus turns a census into findings. Two conditions are reported:
//
//   - a directory that EXISTS and holds .md files but matched NONE. This is exactly
//     the instance-nine signature and it must never again be silent.
//   - matched files spelled in more than one case form, which means the corpus itself
//     is inconsistent and some other tool keyed on case will disagree with this one.
func (c *Corpus) noteCensus(kind, dir string, cen MatchCensus) {
	if !cen.DirExists {
		return // a project need not use every type; an absent directory is not a defect
	}
	if cen.MDFiles > 0 && cen.Matched == 0 {
		c.find("a type directory holds markdown but NO file matched its name pattern",
			kind+" -> "+dir+" ("+strconv.Itoa(cen.MDFiles)+" .md, 0 matched; e.g. "+
				strings.Join(cen.SkipSample, ", ")+")", ClassIntegrity, "")
	}
	if len(cen.Forms) > 1 {
		var forms []string
		for f, n := range cen.Forms {
			forms = append(forms, f+"="+strconv.Itoa(n))
		}
		sort.Strings(forms)
		c.find("one id type is spelled in multiple case forms on disk",
			kind+" -> "+strings.Join(forms, " "), ClassIntegrity, "")
	}
}

func (c *Corpus) rel(p string) string {
	if r, err := filepath.Rel(c.Root, p); err == nil {
		return r
	}
	return p
}

func (c *Corpus) loadVPs() {
	vpKnown := map[string]string{} // canonical id -> the path that first claimed it
	dir := filepath.Join(c.Root, "specs", "verification-properties")
	cen := walkMDCounted(dir, reVPFile, func(path, base string) {
		id := canonicalID(reVPFile.FindStringSubmatch(base)[1])
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
		// vp had NO duplicate check, so a collision reached the PK insert and
		// hard-aborted the whole import — that is why rivetry (143 collisions from its
		// 211 .DELTA-ARCHIVE sidecars) could not be imported at all. Same behaviour as
		// bc and story now: record it, keep both, continue.
		if win, dup := vpKnown[id]; dup {
			c.collide("vp", id, win, c.rel(path), title, body)
			return
		}
		vpKnown[id] = c.rel(path)
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
	c.noteCensus("verification-property", c.rel(dir), cen)
	c.VPCensus = cen
}

func (c *Corpus) loadBCs() {
	bcKnown := map[string]string{} // canonical id -> the path that first claimed it
	ssKnown := map[string]bool{}
	for _, s := range c.Subsystems {
		ssKnown[s.ID] = true
	}
	dir := filepath.Join(c.Root, "specs", "behavioral-contracts")
	cen := walkMDCounted(dir, reBCFile, func(path, base string) {
		if strings.EqualFold(base, "BC-INDEX.md") {
			return
		}
		id := canonicalID(reBCFile.FindStringSubmatch(base)[1])
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
		if win, dup := bcKnown[id]; dup {
			c.collide("bc", id, win, c.rel(path), title, body)
			return
		}
		bcKnown[id] = c.rel(path)
		c.BCs = append(c.BCs, BCRow{
			ID: id, SS: ss, Title: truncRunes(title, 1000), Body: body,
			Capability: cap, Version: truncRunes(version, 16),
			LifecycleStatus: truncRunes(fm.Scalar("lifecycle_status"), 24),
			Status:          truncRunes(fm.Scalar("status"), 24),
			Replacement:     repl, SrcPath: c.rel(path),
		})
	})
	c.noteCensus("behavioral-contract", c.rel(dir), cen)
	c.BCCensus = cen
}

func (c *Corpus) loadStories() {
	dir := filepath.Join(c.Root, "stories")

	// Pass 1: rows, keyed by the filename-derived id.
	known := map[string]string{} // canonical id -> the path that first claimed it
	cen := walkMDCounted(dir, reStoryFile, func(path, base string) {
		id := canonicalID(strings.TrimRight(reStoryFile.FindStringSubmatch(base)[1], "."))
		text, body := "", ""
		text, _ = read(path)
		fm, b := ParseFrontmatter(text)
		body = b
		if win, dup := known[id]; dup {
			c.collide("story", id, win, c.rel(path), firstH1(body), body)
			return
		}
		known[id] = c.rel(path)
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
		sid = canonicalID(sid)
		if _, ok := known[sid]; !ok {
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
	c.noteCensus("story", c.rel(dir), cen)
	c.StoryCensus = cen
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
// is deliberate: `datum validate` compares each claim against COUNT(*). The live
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
