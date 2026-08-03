package main

// STORY 4 — mint `adversarial-finding` as ROWS.
//
// A template for `adversarial-finding` exists in the plugin and **nothing uses it**: measured
// 0 files with that `document_type` across the corpus. Findings live as prose tables and
// headings inside review bodies, which is why `finding_count`, `findings_total` and
// `severity_distribution` are authored numbers that can drift from what the document contains.
// Rows are the enabler for making all three DERIVED.
//
// Every rule here came from `registry/probe_findings.py`, which ran first. Three of them are
// the whole story, and each was found by chasing a disagreement rather than by design:
//
//  1. SIX ID CONVENTIONS. The corpus writes `HIGH-P34-001`, `F-SP8-001`,
//     `ADV-S8P1-P01-HIGH-001`, `P2-001`, plus table and inline forms. The one the previous
//     extractor did NOT know is `ADV-<CYCLE>-P<N>-<SEV>-NNN` — **the convention the template
//     itself declares**. Six conventions in one corpus is not a parser problem to solve once;
//     it is the argument for this story.
//  2. ONE ROW PER (review, finding_id). A review states a finding as a heading AND repeats it
//     in a closure table, so counting MENTIONS gave exactly 2x the asserted distribution on
//     pass-34. Counting mentions is not counting findings.
//  3. OWNERSHIP IS STRUCTURAL. A pass-2 review has `## Part A — Fix Verification`, which
//     re-states PASS-1's findings, and `## Part B — New Findings`, which is what this pass
//     introduces. `findings_total` counts Part B only. Same class as the shadow stage's scope
//     predicate: a derived count needs a declared SCOPE or it counts mentions.

import (
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
)

// reviewTypeSet returns every document_type spelling that RESOLVES to `adversarial-review`,
// read from the registry's own alias map.
//
// Derived, never hand-listed. The first cut of this file carried a hardcoded set, and a
// diff against the Python extractor's hardcoded set showed the two disagreed on EIGHT
// spellings in both directions — a hand-maintained vocabulary drifting from another
// hand-maintained vocabulary, which is the exact defect the registry exists to remove. Two
// lists of one fact is the same shape as `depends_on`/`blocks` and as the two declared
// namespaces; the fix is always to have one source.
//
// The alias map is the right source rather than the canonical name alone, because aliases are
// a MIGRATION device: the legacy spellings are still in the corpus today.
func reviewTypeSet(b *RegistryBundle) map[string]bool {
	out := map[string]bool{"adversarial-review": true}
	if b == nil {
		return out
	}
	for spelling, a := range b.Al.Aliases {
		if a != nil && a.Canonical == "adversarial-review" {
			out[spelling] = true
		}
	}
	return out
}

// ReviewRow is one review document: the owner of its findings.
type ReviewRow struct {
	Key     string
	Cycle   string
	Pass    *int
	Target  string
	SrcPath string
}

// loadReviews walks `cycles/` and mints each review document plus its findings as rows.
//
// It also records what each review CLAIMS about its own findings as `corpus_assertion` rows,
// so `datum validate` can compare the claim against COUNT(*) — the same instrument the BC totals
// already use, which is what makes story 4's exit criterion mechanically checkable rather than
// a matter of opinion.
func (c *Corpus) loadReviews() {
	dir := filepath.Join(c.Root, "cycles")
	if st, err := os.Stat(dir); err != nil || !st.IsDir() {
		return
	}
	// The registry is EMBEDDED, so this is a local read, not I/O against the corpus. A load
	// failure must not silently yield "no reviews": that would report zero findings and read
	// as a clean corpus.
	bundle, err := LoadRegistry("")
	if err != nil {
		c.find("the embedded registry failed to load, so review types cannot be resolved",
			"loadReviews", ClassIntegrity, err.Error())
		return
	}
	reviewTypes := reviewTypeSet(bundle)

	seen := map[string]bool{}
	_ = filepath.WalkDir(dir, func(path string, d os.DirEntry, err error) error {
		if err != nil {
			return nil
		}
		if d.IsDir() {
			if d.Name() == ".git" {
				return filepath.SkipDir
			}
			return nil
		}
		if !strings.HasSuffix(path, ".md") {
			return nil
		}
		text, ok := read(path)
		if !ok {
			return nil
		}
		fm, body := ParseFrontmatter(text)
		if fm == nil || !reviewTypes[fm.Scalar("document_type")] {
			return nil
		}
		rel := c.rel(path)
		// The review's natural key is its corpus-relative path today, because reviews carry
		// no declared id. Recorded as a KEY rather than treated as identity-by-path: 186
		// prism files share the basename `pr-description.md` with different content, so a
		// basename key would collide. The registry's own answer is a declared natural key,
		// which reviews do not yet have — a story 4 follow-up, stated rather than papered over.
		key := rel
		if seen[key] {
			c.find("two review documents claim the same key", key, ClassIntegrity, "")
			return nil
		}
		seen[key] = true

		cycle := fm.Scalar("cycle")
		if cycle == "" {
			// fall back to the cycles/<cycle>/ directory component
			if parts := strings.Split(rel, string(filepath.Separator)); len(parts) > 1 {
				cycle = parts[1]
			}
		}
		var pass *int
		if n, err := strconv.Atoi(fm.Scalar("pass")); err == nil {
			pass = &n
		}
		c.Reviews = append(c.Reviews, ReviewRow{
			Key: key, Cycle: truncRunes(cycle, 120), Pass: pass,
			Target: truncRunes(fm.Scalar("target"), 400), SrcPath: rel})

		rows, dupes, malformed := ExtractFindings(key, body)
		for _, r := range rows {
			if r.Category != "" && !IsDeclaredCategory(r.Category) {
				c.find("a finding category is prose, not a declared category",
					key+" -> "+r.FindingID, ClassType, truncRunes(r.Category, 80))
			}
		}
		c.FindingRows = append(c.FindingRows, rows...)
		c.FindingDupes += dupes
		c.FindingMalformed += malformed

		// what the review CLAIMS about itself
		for _, f := range []string{"finding_count", "findings_total", "total_findings", "observations"} {
			if v := fm.Scalar(f); v != "" {
				if n, err := strconv.ParseInt(strings.TrimSpace(v), 10, 64); err == nil {
					c.Assertions = append(c.Assertions, Assertion{
						Source: rel + " " + f, Kind: "review_finding_count",
						Subject: key, Claimed: n, SrcPath: rel})
				}
			}
		}
		for _, f := range []string{"findings", "severity_distribution"} {
			v := fm.Scalar(f)
			if v == "" {
				continue
			}
			d, unknown := ParseSeverityDistribution(v)
			if len(unknown) > 0 {
				c.find("a severity distribution uses an unmapped token", rel+" "+f+"="+truncRunes(v, 40),
					ClassType, "unmapped: "+strings.Join(unknown, ","))
			}
			// Stored per BUCKET, so a disagreement names the severity that differs rather
			// than reporting one opaque string mismatch.
			for sev, n := range d {
				c.Assertions = append(c.Assertions, Assertion{
					Source: rel + " " + f, Kind: "review_severity_count",
					Subject: key + "|" + sev, Claimed: int64(n), SrcPath: rel})
			}
		}
		return nil
	})
}

// ── id forms ─────────────────────────────────────────────────────────────────

const (
	sevWords = `CRIT|CRITICAL|HIGH|MED|MEDIUM|LOW|NIT|NITPICK|OBS`
	// advID is the convention the adversarial-finding TEMPLATE declares.
	advID = `ADV-[A-Za-z0-9]+-P\d+[A-Za-z0-9]*-(?:` + sevWords + `)-\d+`
	// sevID is severity- or category-prefixed: HIGH-P34-001, F-SP8-001, CV-12, SEC-3, PG-1.
	sevID = `(?:` + sevWords + `|F|CV|SEC|PG)[A-Z0-9]*[-\x{2013}][A-Za-z0-9.\-]+`
	// passID carries no severity or category word at all: P2-001.
	passID = `P\d+[A-Za-z]?-\d+`
)

var (
	anyID = `(?:` + advID + `|` + sevID + `|` + passID + `)`

	// Heading form. `#{3,6}` because the corpus uses both `###` and `####`, and the
	// separator may be an em dash, en dash, hyphen, colon or nothing at all.
	findHeadingRe = regexp.MustCompile(`^#{3,6}\s+\*{0,2}(` + anyID + `)\*{0,2}\s*[\x{2014}\x{2013}\-:|]?\s*(.*)$`)
	// Table-row form.
	findTableRe = regexp.MustCompile(`^\|\s*\*{0,2}(` + anyID + `)\*{0,2}\s*\|(.+)$`)
	// Inline bold form, plus the `- Key: value` attribute bullets that follow it.
	findInlineRe = regexp.MustCompile(`^\*{0,2}((?:` + sevWords + `|F)-\d+)\*{0,2}\s*(?:\([^)]*\))?\s*:\s*(.+?)\*{0,2}$`)
	findAttrRe   = regexp.MustCompile(`^\s*[-*]\s*([A-Z][A-Za-z /]+):\s*(.*)$`)

	// Severity sources, in the order measured to resolve them (counts from 2,212 rows):
	// bracket-in-statement 803 · bold-line 670 · id-prefix 129 · ADV-embedded 76 ·
	// section-heading 61 · unresolved 499.
	sevBracketRe = regexp.MustCompile(`^\s*\[?\*{0,2}(` + sevWords + `)\*{0,2}\]?`)
	sevBoldRe    = regexp.MustCompile(`\*\*Severity:?\*\*:?\s*\*{0,2}\s*(` + sevWords + `)`)
	sevSectionRe = regexp.MustCompile(`^#{2,4}\s+\*{0,2}(` + sevWords + `)\b`)
	sevAdvRe     = regexp.MustCompile(`^ADV-[A-Za-z0-9]+-P\d+[A-Za-z0-9]*-([A-Za-z]+)-\d+$`)
	sevPrefixRe  = regexp.MustCompile(`^([A-Za-z]+)`)

	// Ownership. A finding DEFINED under a fix-verification section is MENTIONED, not owned.
	mentionSecRe = regexp.MustCompile(`(?i)(fix[- ]verification|closure audit|prior[- ]pass|` +
		`previous[- ]pass|pass-\d+ closure|carried[- ]forward|re-?verification|resolution status)`)
	ownedSecRe = regexp.MustCompile(`(?i)(new findings|fresh[- ]context|findings \(this pass\)|part b)`)

	topHeadingRe = regexp.MustCompile(`^#{1,2}\s+`)
	distTokRe    = regexp.MustCompile(`(\d+)\s*([A-Za-z]+)`)
)

// declaredCategories is the closed set the adversarial-finding template declares. The corpus
// writes free prose into the same field ("Sibling propagation gap (S-7.01 partial-fix
// discipline) + lesson-not-applied-retroactively recurrence pattern."), which is why the
// column is TEXT and why a non-declared value is reported as a TYPE finding rather than
// silently coerced — the same call the importer already makes for bc.replacement.
var declaredCategories = map[string]bool{
	"spec-gap": true, "consistency": true, "completeness": true,
	"edge-case": true, "security": true, "performance": true,
}

// IsDeclaredCategory reports whether a category value is one the template declares.
func IsDeclaredCategory(s string) bool {
	return declaredCategories[strings.ToLower(strings.TrimSpace(s))]
}

// canonSeverity maps every measured spelling to its bucket. The same review set writes CRIT
// and CRITICAL, MED and MEDIUM, NIT and NITPICK — so this is a measured alias map, not a guess.
func canonSeverity(s string) string {
	switch strings.ToLower(strings.TrimSpace(s)) {
	case "crit", "critical", "c":
		return "CRIT"
	case "high", "h":
		return "HIGH"
	case "med", "medium", "m":
		return "MED"
	case "low", "l":
		return "LOW"
	case "nit", "nitpick", "n":
		return "NIT"
	case "obs", "o", "observation":
		return "OBS"
	}
	return ""
}

// FindingRow is one adversarial finding, keyed by (review, finding_id) — the composite natural
// key the template already declares, and the same file-scoped discipline sub-artifact ids need.
type FindingRow struct {
	ReviewKey string
	FindingID string
	Severity  string
	SevSource string // which of the six sources resolved it; "" means unresolved
	Category  string
	Statement string
	Location  string
	Form      string // heading | table-row | inline
	Owned     bool   // introduced by THIS review, vs re-stated from a prior pass
	Line      int
}

// ExtractFindings pulls every finding from one review body.
//
// Returns the rows plus the counts a caller must REPORT rather than swallow: how many
// duplicate mentions were collapsed and how many candidate lines were malformed. An extractor
// that reports only its successes has silently lost input five times in this spike.
func ExtractFindings(reviewKey, body string) (rows []FindingRow, dupes, malformed int) {
	lines := strings.Split(body, "\n")

	// first pass: the section context each line sits in
	topAt := make([]string, len(lines))
	sevSecAt := make([]string, len(lines))
	top, sevSec := "", ""
	for i, ln := range lines {
		if topHeadingRe.MatchString(ln) {
			top = ln
		}
		if m := sevSectionRe.FindStringSubmatch(ln); m != nil {
			sevSec = m[1]
		}
		topAt[i], sevSecAt[i] = top, sevSec
	}

	type acc struct {
		row  FindingRow
		rank int
	}
	best := map[string]*acc{}
	var order []string
	// The heading form wins: it is where the statement and the `**Severity:**` line live.
	rank := map[string]int{"heading": 0, "inline": 1, "table-row": 2}

	add := func(r FindingRow) {
		if cur, ok := best[r.FindingID]; ok {
			dupes++
			if rank[r.Form] < cur.rank {
				// keep whatever the loser resolved that the winner did not
				if r.Severity == "" {
					r.Severity, r.SevSource = cur.row.Severity, cur.row.SevSource
				}
				if r.Location == "" {
					r.Location = cur.row.Location
				}
				best[r.FindingID] = &acc{row: r, rank: rank[r.Form]}
			} else if cur.row.Severity == "" && r.Severity != "" {
				cur.row.Severity, cur.row.SevSource = r.Severity, r.SevSource
			}
			return
		}
		best[r.FindingID] = &acc{row: r, rank: rank[r.Form]}
		order = append(order, r.FindingID)
	}

	for i, raw := range lines {
		ln := strings.TrimRight(raw, "\r")

		if m := findHeadingRe.FindStringSubmatch(ln); m != nil {
			stmt := strings.TrimSpace(m[2])
			if stmt == "" {
				malformed++
				continue
			}
			r := FindingRow{ReviewKey: reviewKey, FindingID: m[1], Statement: stmt,
				Form: "heading", Line: i + 1}
			r.Severity, r.SevSource = resolveSeverity(r, lines, i, sevSecAt[i])
			r.Location = attrNear(lines, i, "Location")
			r.Category = attrNear(lines, i, "Category")
			// Ownership is decided by the DEFINING occurrence. Deciding it from a finding's
			// first MENTION attributed Part B findings to Part A's audit table and
			// undercounted adv-s8.08-p2 to 5 against a claimed 9 — overshooting the very
			// bug the ownership rule exists to fix.
			r.Owned = ownedUnder(topAt[i])
			add(r)
			continue
		}
		if m := findTableRe.FindStringSubmatch(ln); m != nil {
			rest := m[2]
			cells := SplitMDCells("|" + rest)
			stmt := ""
			for _, c := range cells {
				if s := NormalizeCell(c); s != "" && canonSeverity(s) == "" {
					stmt = s
					break
				}
			}
			if stmt == "" {
				malformed++
				continue
			}
			r := FindingRow{ReviewKey: reviewKey, FindingID: m[1], Statement: stmt,
				Form: "table-row", Line: i + 1, Owned: ownedUnder(topAt[i])}
			for _, c := range cells {
				if sv := canonSeverity(NormalizeCell(c)); sv != "" {
					r.Severity, r.SevSource = sv, "table-column"
					break
				}
			}
			if r.Severity == "" {
				r.Severity, r.SevSource = resolveSeverity(r, lines, i, sevSecAt[i])
			}
			add(r)
			continue
		}
		if m := findInlineRe.FindStringSubmatch(ln); m != nil {
			r := FindingRow{ReviewKey: reviewKey, FindingID: m[1],
				Statement: strings.TrimSpace(m[2]), Form: "inline", Line: i + 1,
				Owned: ownedUnder(topAt[i])}
			r.Severity, r.SevSource = resolveSeverity(r, lines, i, sevSecAt[i])
			r.Location = attrNear(lines, i, "Location")
			add(r)
		}
	}

	for _, id := range order {
		rows = append(rows, best[id].row)
	}
	return rows, dupes, malformed
}

// ownedUnder decides ownership from the enclosing top-level section. DEFAULT OWNED: most
// reviews have no Part A/B split at all, and defaulting to "mentioned" would silently drop
// their findings — the failure mode this exercise keeps re-learning.
func ownedUnder(top string) bool {
	return !(mentionSecRe.MatchString(top) && !ownedSecRe.MatchString(top))
}

// resolveSeverity walks the six sources in the order measured to resolve them, and returns
// WHICH one won. Reporting the source is what makes "unresolved" a measured fact about the
// corpus rather than a silent parser default.
func resolveSeverity(r FindingRow, lines []string, i int, sevSec string) (string, string) {
	if v := attrNear(lines, i, "Severity"); v != "" {
		if c := canonSeverity(firstWord(v)); c != "" {
			return c, "attr-bullet"
		}
	}
	if m := sevBracketRe.FindStringSubmatch(r.Statement); m != nil {
		if c := canonSeverity(m[1]); c != "" {
			return c, "bracket-in-statement"
		}
	}
	for j := i; j < len(lines) && j < i+8; j++ {
		if m := sevBoldRe.FindStringSubmatch(lines[j]); m != nil {
			if c := canonSeverity(m[1]); c != "" {
				return c, "bold-line"
			}
		}
	}
	if m := sevAdvRe.FindStringSubmatch(r.FindingID); m != nil {
		if c := canonSeverity(m[1]); c != "" {
			return c, "id-embedded-ADV"
		}
	}
	if m := sevPrefixRe.FindStringSubmatch(r.FindingID); m != nil {
		if c := canonSeverity(m[1]); c != "" {
			return c, "id-prefix"
		}
	}
	if c := canonSeverity(sevSec); c != "" {
		return c, "section-heading"
	}
	return "", ""
}

// attrNear reads a `**Key:** value` or `- Key: value` attribute in the lines just after a
// finding. Bounded to 8 lines so it cannot reach into the NEXT finding — the block-boundary
// rule a regex in this repo already violated once, mis-assigning 17 of 17 values.
func attrNear(lines []string, i int, key string) string {
	bold := regexp.MustCompile(`(?i)^\s*\*\*` + regexp.QuoteMeta(key) + `:?\*\*:?\s*(.+)$`)
	for j := i; j < len(lines) && j < i+8; j++ {
		if j > i && findHeadingRe.MatchString(lines[j]) {
			break
		}
		if m := bold.FindStringSubmatch(lines[j]); m != nil {
			return strings.TrimSpace(strings.Trim(m[1], "*"))
		}
		if m := findAttrRe.FindStringSubmatch(lines[j]); m != nil && strings.EqualFold(m[1], key) {
			return strings.TrimSpace(m[2])
		}
	}
	return ""
}

func firstWord(s string) string {
	for i, r := range s {
		if !((r >= 'A' && r <= 'Z') || (r >= 'a' && r <= 'z')) {
			return s[:i]
		}
	}
	return s
}

// ParseSeverityDistribution reads `1H/3M/2L` or `0C+4H+3M+1L+1N` into buckets, and returns any
// token it could not map. An unmapped token is REPORTED, never dropped: a distribution silently
// missing a bucket compares equal to one that never had it.
func ParseSeverityDistribution(s string) (map[string]int, []string) {
	out := map[string]int{}
	var unknown []string
	for _, m := range distTokRe.FindAllStringSubmatch(s, -1) {
		n, err := strconv.Atoi(m[1])
		if err != nil {
			continue
		}
		if c := canonSeverity(m[2]); c != "" {
			out[c] += n
		} else {
			unknown = append(unknown, m[2])
		}
	}
	return out, unknown
}

// FormatSeverityDistribution renders buckets in a stable order, so a derived value and an
// authored one are comparable as strings.
func FormatSeverityDistribution(d map[string]int) string {
	var parts []string
	for _, k := range []string{"CRIT", "HIGH", "MED", "LOW", "NIT", "OBS"} {
		if n, ok := d[k]; ok && n > 0 {
			parts = append(parts, fmt.Sprintf("%d%s", n, k))
		}
	}
	return strings.Join(parts, "/")
}

func boolInt(b bool) int {
	if b {
		return 1
	}
	return 0
}
