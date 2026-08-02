package main

// STORY 12b — the MINIMAL permanent prose extractor: section references and version cites.
//
// Equal priority to 12a, not a residual. Measured over corpus MASS these are 6.4% of reference
// candidates; measured over THE ADVERSARY'S FINDINGS — the denominator story 12's value claim
// uses — they are 36.8% of class C, the same as 12a (7 of 19 hand-classified,
// research/PROSE-REFS-OR-FIELDS.md). Inferring the value split from the mass split was an error
// this file exists partly to correct.
//
// These two kinds are the ones that genuinely CANNOT become rows: a `§Consequences` reference
// points INTO a document's body, and a version cite is a claim about a target's state at a
// moment. Everything else that looked like prose was a referent that should be a row.
//
// The three load-bearing rules, all declared in prose_ref_rules:
//   exclude-code-spans                    `ADR-099` in a backtick span is an example, not a ref
//   pin-policy-decides-the-verdict        the SAME syntax carries OPPOSITE verdicts
//   report-unresolvable-separately        an unstated owner is never reported as dangling

import (
	"fmt"
	"regexp"
	"strconv"
	"strings"
)

// ProseRefRow is a resolved-or-not reference found in narrative text.
type ProseRefRow struct {
	CitingKey  string
	CitingType string
	Kind       string // section | version_cite
	Raw        string
	Target     string // the document or section named
	SectionOrd int    // -1 when unresolved
	Status     string // resolved | unresolvable | dangling
	Line       int
}

// VersionCiteRow is a prose claim about a target's version.
//
// Verdict is decided by PIN POLICY, never by whether the cite matches today. Both sides are
// measured in the corpus: `ARCH-INDEX cite "per BC-INDEX v1.25" lags actual v1.26` is a real
// finding, and a review citing the index state it reviewed is CORRECT.
type VersionCiteRow struct {
	CitingKey    string
	CitingType   string
	Target       string
	CitedVersion string
	PinPolicy    string // floating | pinned
	Verdict      string // current | lagging-floating | lagging-pinned-ok | ahead-never-existed | target-unknown
	Line         int
}

var (
	// The plain `NAME vX.Y` form, which the registry now declares as `pattern` — the
	// prepositional form matched 39 of 1,612 measured cites (2.4%).
	versionCiteRe = regexp.MustCompile(`\b([A-Z][A-Z0-9-]{2,}(?:-INDEX)?(?:\.md)?)\s+v(\d+\.\d+)`)
	// A section reference. Bounded at the first separator so it cannot swallow a sentence.
	sectionRefRe = regexp.MustCompile(`§\s*([^,;)\.]{2,60})`)
	verNumRe     = regexp.MustCompile(`^\d+\.\d+$`)
	// `§7`, `§7:`, `§7 preamble`, `§1-§12` — an ordinal reference into the partition.
	numericSectionRe = regexp.MustCompile(`^(\d{1,3})\b`)
	// `Postcondition 5`, `Precondition 2`, `Invariant 4`, `Decision 1`, `Event 3`, `Scenario 8`
	itemInSectionRe = regexp.MustCompile(`^([A-Za-z][A-Za-z-]{3,20})\s+\d{1,3}\b`)
)

// citePinPolicy decides which link type a prose version cite belongs to, and therefore how it
// is judged.
//
// THIS IS THE DECISION THAT MAKES THE RULE USABLE. `pin_policy` lives on the link type, and
// `version_cite` declares `pin_policy_from: link_type` — but prose does not say which link it
// is. The corpus settles it: a REVIEW document citing `BC-INDEX v2.63` is recording the state
// it reviewed (pinned; lagging is CORRECT), while a spec or index citing an index is asserting
// currency (floating; lagging is a finding). FSTAR states both sides explicitly, which is why
// this is a declared mapping rather than a guess.
func citePinPolicy(citingType string) string {
	if reviewishType(citingType) {
		return "pinned"
	}
	return "floating"
}

func reviewishType(t string) bool {
	return strings.Contains(t, "adversar") || strings.Contains(t, "review") ||
		strings.Contains(t, "burst") || strings.Contains(t, "lesson") ||
		strings.Contains(t, "checkpoint") || strings.Contains(t, "decision-log")
}

// ExtractProseRefs pulls section references and version cites out of one document body.
//
// knownVersions maps a cite target name to the version that target actually carries, so the
// verdict can be computed. A target absent from the map yields `target-unknown` rather than a
// silent skip: a cite to something the store does not hold is a fact worth reporting, and
// dropping it would overstate the extractor's coverage.
func ExtractProseRefs(citingKey, citingType, body string, knownVersions map[string]string,
	ownSections map[string]int, sectionsByDoc map[string]map[string]int) (refs []ProseRefRow, cites []VersionCiteRow) {

	pin := citePinPolicy(citingType)
	inFence := false
	for i, raw := range strings.Split(body, "\n") {
		ln := strings.TrimRight(raw, "\r")
		if fenceRe.MatchString(ln) {
			inFence = !inFence
			continue
		}
		if inFence {
			continue
		}
		// prose_ref_rules exclude-code-spans, applied length-preserving so a reported line
		// offset still means what it meant.
		masked := maskCodeSpans(ln)

		for _, m := range versionCiteRe.FindAllStringSubmatch(masked, -1) {
			target, cited := m[1], m[2]
			row := VersionCiteRow{CitingKey: citingKey, CitingType: citingType, Target: target,
				CitedVersion: cited, PinPolicy: pin, Line: i + 1}
			actual, ok := knownVersions[normalizeCiteTarget(target)]
			switch {
			case !ok:
				row.Verdict = "target-unknown"
			case actual == cited:
				row.Verdict = "current"
			case versionLess(actual, cited):
				// The cite names a version LATER than the target ever reached. A finding
				// under EITHER pin policy — you cannot have reviewed a version that does not
				// exist. prose_ref_rules pinned-to-a-version-that-never-existed.
				row.Verdict = "ahead-never-existed"
			case pin == "pinned":
				// Correct BY DESIGN: the document records what it reviewed. Reporting this
				// would be the checker's defect, not the document's.
				row.Verdict = "lagging-pinned-ok"
			default:
				row.Verdict = "lagging-floating"
			}
			cites = append(cites, row)
		}

		for _, m := range sectionRefRe.FindAllStringSubmatch(masked, -1) {
			name := strings.TrimSpace(m[1])
			if name == "" {
				continue
			}
			row := ProseRefRow{CitingKey: citingKey, CitingType: citingType, Kind: "section",
				Raw: truncRunes("§"+name, 200), Target: truncRunes(name, 200),
				SectionOrd: -1, Line: i + 1}
			// D-A stores an ordinal-keyed section partition, so a section reference resolves
			// to (doc_key, section_ord) — which lets a finding name the SECTION it lives in
			// rather than a 615 KB document.
			if nm, ord, ok := resolveSectionName(name, ownSections); ok {
				row.Status, row.SectionOrd = "resolved", ord
				row.Target, row.Raw = nm, truncRunes("§"+nm, 200)
			} else if owner := ownerNamedOn(masked); owner != "" {
				// THE OWNER IS STATED, so the reference is resolvable — against THAT
				// document's partition, not this one's. Resolving only against the citing
				// document reported 3,576 of 3,609 refs (99%) as unresolvable: honest, and
				// useless. `ADR-019 §Consequences` names its owner on the line.
				row.Target = truncRunes(owner+" §"+name, 200)
				if sec, ok := sectionsByDoc[strings.ToUpper(owner)]; ok {
					if nm, ord, ok := resolveSectionName(name, sec); ok {
						row.Status, row.SectionOrd = "resolved", ord
						row.Target, row.Raw = truncRunes(owner+" §"+nm, 200), truncRunes("§"+nm, 200)
					} else {
						// Owner known, section absent from it. THIS is dangling — the
						// distinction report-unresolvable-separately exists to preserve.
						row.Status = "dangling"
					}
				} else {
					row.Status = "unresolvable" // the named owner is not a document we hold
				}
			} else {
				row.Status = "unresolvable" // no owner named: never reported as dangling
			}
			refs = append(refs, row)
		}
	}
	return refs, cites
}

// resolveSectionName finds the LONGEST leading run of words in a captured section reference
// that is an actual section of the target.
//
// A section reference has NO DELIMITER in prose: `see §My Own Section here` and
// `per ADR-019 §Consequences of the change` both run into the surrounding sentence, so the
// capture cannot be parsed cleanly. It must be RESOLVED against the target's real section list
// — longest prefix wins — which is only possible because D-A stores the partition. A
// parse-then-lookup design reports every such reference as unresolved, which is what the first
// cut did.
func resolveSectionName(captured string, sections map[string]int) (string, int, bool) {
	if sections == nil {
		return "", -1, false
	}
	// A NUMERIC section reference addresses the partition by ORDINAL, not by name — `§7`,
	// `§1-§12`. D-A stores the partition ordinal-keyed precisely because headings are not
	// unique (110 documents carry 1,968 duplicate `##`+ headings), so this is the addressing
	// scheme the store already speaks.
	//
	// MEASURED: a name-only lookup can never resolve these, and they were ~10 of a 30-row
	// sample of the 329 "dangling" refs — a THIRD of that class was the resolver using the
	// wrong key, not the corpus citing a missing section.
	if m := numericSectionRe.FindStringSubmatch(captured); m != nil {
		n, err := strconv.Atoi(m[1])
		if err == nil && n >= 0 && n <= sectionCount(sections) {
			return "§" + m[1], n, true
		}
		// A numeric ref BEYOND the partition is genuinely out of range: report it, but as its
		// own thing rather than as a missing heading NAME.
		return "", -1, false
	}
	words := strings.Fields(captured)
	// Pass 1: the longest leading run of words that is EXACTLY a heading.
	for n := len(words); n >= 1; n-- {
		cand := strings.Join(words[:n], " ")
		if ord, ok := sections[strings.ToLower(cand)]; ok {
			return cand, ord, true
		}
	}
	// Pass 2: the MIRROR case — the captured name is a PREFIX OF a heading.
	//
	// The corpus writes `### Postcondition 5 — <description>` and cites it as
	// `§Postcondition 5 to state TIMEOUT/...`, so neither string contains the other whole:
	// the citation truncates the heading AND appends prose. Exact-match-on-prefix therefore
	// misses it.
	//
	// MEASURED: 16 of a 25-row sample of the remaining 250 "dangling" refs were this shape —
	// 64% of that class was the RESOLVER's defect, not the corpus citing a missing section.
	// Longest candidate first so the most specific citation wins, and a 1-word candidate is
	// refused as too weak to attribute: `§host` would otherwise match any heading beginning
	// with "host".
	for n := len(words); n >= 2; n-- {
		cand := strings.ToLower(strings.Join(words[:n], " "))
		best, bestOrd := "", -1
		for h, ord := range sections {
			if strings.HasPrefix(h, cand) && (best == "" || len(h) < len(best)) {
				best, bestOrd = h, ord
			}
		}
		if best != "" {
			return best, bestOrd, true
		}
	}
	// Pass 3: `§Postcondition 5` — a reference to a NUMBERED ITEM INSIDE a section.
	//
	// BC-1.05.036 has `## Postconditions` as its heading and states Postcondition 5 as an
	// ordered-list item within it. So the citation addresses a granularity FINER than D-A's
	// partition: the SECTION resolves, the item is below the partition's resolution.
	//
	// This is the third addressing scheme in the corpus (heading name · section ordinal ·
	// item-within-section), and getting it wrong put these on the WRONG SIDE of the
	// dangling/unresolvable distinction that report-unresolvable-separately exists to protect —
	// reporting a correct citation as a missing section.
	//
	// Found by CHECKING A FAILED PREDICTION: pass 2 was expected to recover ~160 of the 250
	// remaining, and recovered 46. Reading one case rather than tuning further is what exposed
	// the scheme.
	if m := itemInSectionRe.FindStringSubmatch(captured); m != nil {
		stem := strings.ToLower(m[1])
		for _, cand := range []string{stem + "s", stem} { // Postcondition 5 -> "Postconditions"
			if ord, ok := sections[cand]; ok {
				return cand, ord, true
			}
		}
	}
	return "", -1, false
}

// sectionCount is the highest ordinal in a partition, so an out-of-range numeric reference can
// be told from an in-range one.
func sectionCount(sections map[string]int) int {
	max := 0
	for _, o := range sections {
		if o > max {
			max = o
		}
	}
	return max
}

// ownerNameRe is any top-level artifact id, used only to tell "the owner is stated" from "the
// owner is unstated". prose_ref_rules report-unresolvable-separately turns on that distinction.
var ownerNameRe = regexp.MustCompile(`\b(?:BC-\d+\.\d+\.\d+|VP-\d+|S-\d+\.\d+|E-\d+|ADR-\d+|SS-\d+|` +
	`[A-Z][A-Z0-9-]{2,}-INDEX)\b`)

// ownerNamedOn returns the artifact id a line names, or "" when none is stated. The LAST match
// wins: `... per ADR-019 §Consequences` puts the owner immediately before its section, and an
// earlier id on the same line is usually the citing context rather than the referent.
func ownerNamedOn(s string) string {
	m := ownerNameRe.FindAllString(s, -1)
	if len(m) == 0 {
		return ""
	}
	return m[len(m)-1]
}

// normalizeCiteTarget folds `BC-INDEX.md` and `BC-INDEX` together.
func normalizeCiteTarget(s string) string {
	return strings.ToUpper(strings.TrimSuffix(strings.TrimSpace(s), ".md"))
}

// versionLess compares dotted versions NUMERICALLY. String comparison would make "2.10" < "2.9",
// which would silently invert the lagging/ahead verdict — and those two verdicts have opposite
// meanings under pin policy, so the bug would be a wrong finding rather than a missing one.
func versionLess(a, b string) bool {
	pa, pb := strings.SplitN(a, ".", 2), strings.SplitN(b, ".", 2)
	if len(pa) < 2 || len(pb) < 2 {
		return false
	}
	a0, _ := strconv.Atoi(pa[0])
	b0, _ := strconv.Atoi(pb[0])
	if a0 != b0 {
		return a0 < b0
	}
	a1, _ := strconv.Atoi(pa[1])
	b1, _ := strconv.Atoi(pb[1])
	return a1 < b1
}

// loadProseRefs walks every typed markdown document.
//
// Two passes: the first learns each cite target's ACTUAL version (an index's own `version:`),
// the second extracts and judges. A single pass would have to judge a cite before knowing what
// it is citing.
func (c *Corpus) loadProseRefs() {
	known := map[string]string{}
	type doc struct{ key, dtype, body string }
	var docs []doc

	walkAllMD(c.Root, func(path, rel string) {
		text, ok := read(path)
		if !ok {
			return
		}
		fm, body := ParseFrontmatter(text)
		if fm == nil {
			return
		}
		dt := fm.Scalar("document_type")
		if dt == "" {
			return
		}
		// A cite names a document by its BASENAME (`BC-INDEX`), so that is the key the
		// version index is built on.
		base := strings.TrimSuffix(filepathBase(rel), ".md")
		if v := strings.TrimSpace(fm.Scalar("version")); verNumRe.MatchString(v) {
			known[normalizeCiteTarget(base)] = v
		}
		docs = append(docs, doc{rel, dt, body})
	})

	// Pass 1b: every document's section partition, keyed by the name a cite would use.
	sectionsByDoc := map[string]map[string]int{}
	for _, d := range docs {
		sec := map[string]int{}
		for _, sx := range SplitSections(d.body) {
			if sx.Heading != "" {
				sec[strings.ToLower(sx.Heading)] = sx.Ord
			}
		}
		sectionsByDoc[strings.ToUpper(strings.TrimSuffix(filepathBase(d.key), ".md"))] = sec
	}

	for _, d := range docs {
		own := map[string]int{}
		for _, s := range SplitSections(d.body) {
			if s.Heading != "" {
				own[strings.ToLower(s.Heading)] = s.Ord
			}
		}
		refs, cites := ExtractProseRefs(d.key, d.dtype, d.body, known, own, sectionsByDoc)
		c.ProseRefs = append(c.ProseRefs, refs...)
		c.VersionCites = append(c.VersionCites, cites...)
	}
	c.CiteTargetsKnown = len(known)
}

// ── the gate ─────────────────────────────────────────────────────────────────

// gateVersionCites is prose_ref_rules pin-policy-decides-the-verdict, as a query.
//
// It reports ONLY the two verdicts that are defects. A `lagging-pinned-ok` cite is correct by
// design and reporting it "would be the checker's defect, not the document's" — which is the
// whole reason pin_policy had to land BEFORE this story.
func (v *validator) gateVersionCites() error {
	n, err := v.s.Int(v.ctx, `SELECT COUNT(*) FROM version_cite`)
	if err != nil || n == 0 {
		return err
	}
	rows, err := v.s.Query(v.ctx, `SELECT citing_key, target, cited_version, verdict, src_line
	                                 FROM version_cite
	                                WHERE verdict IN ('lagging-floating','ahead-never-existed')
	                                ORDER BY verdict, citing_key, target LIMIT 400`)
	if err != nil {
		return err
	}
	defer rows.Close()
	for rows.Next() {
		var key, target, cited, verdict string
		var line int
		if err := rows.Scan(&key, &target, &cited, &verdict, &line); err != nil {
			return err
		}
		switch verdict {
		case "ahead-never-existed":
			v.find("a version cite names a version the target never reached", key+" -> "+target+" v"+cited,
				ClassIntegrity, "a finding under EITHER pin policy: you cannot cite a version that does not exist")
		default:
			v.find("a floating version cite lags its target", key+" -> "+target+" v"+cited,
				ClassCount, "an index_cite is declared floating, so it must track the current version")
		}
	}
	return rows.Err()
}

// gateProseRefsUnresolvable reports section references that cannot be resolved, as their OWN
// class. Collapsing `unresolvable` into `dangling` "is how a prose extractor produces a large,
// confident, wrong finding set" — so the count is reported in aggregate rather than as one
// finding per reference, which would swamp every other class.
func (v *validator) gateProseRefsUnresolvable() error {
	n, err := v.s.Int(v.ctx, `SELECT COUNT(*) FROM prose_ref`)
	if err != nil || n == 0 {
		return err
	}
	un, err := v.s.Int(v.ctx, `SELECT COUNT(*) FROM prose_ref WHERE status = 'unresolvable'`)
	if err != nil {
		return err
	}
	res, err := v.s.Int(v.ctx, `SELECT COUNT(*) FROM prose_ref WHERE status = 'resolved'`)
	if err != nil {
		return err
	}
	dang, err := v.s.Int(v.ctx, `SELECT COUNT(*) FROM prose_ref WHERE status = 'dangling'`)
	if err != nil {
		return err
	}
	if un > 0 {
		v.find("section references whose owning document is unstated", fmt.Sprintf("%d of %d", un, un+res+dang),
			ClassType, "reported as UNRESOLVABLE, never as dangling: the reference may be perfectly "+
				"correct and simply not say which document it is in")
	}
	// REPORTED IN AGGREGATE, DELIBERATELY, and not yet one finding per reference.
	//
	// `ownerNamedOn` takes the LAST artifact id on the line, which is right for
	// `per ADR-019 §Consequences` and WRONG for `per ADR-019 and BC-1.02.003 §Consequences`.
	// Until that precision is measured on a sample, emitting 513 individually-named findings
	// would be exactly the "large, confident, wrong finding set" the rules warn about. The
	// count is visible; the per-reference claim is not made.
	if dang > 0 {
		v.find("section references naming an owner that has no such section",
			fmt.Sprintf("%d of %d", dang, un+res+dang), ClassDangling,
			"AGGREGATE ONLY: owner attribution takes the last id on the line, whose precision is "+
				"not yet measured, so no per-reference finding is claimed")
	}
	return nil
}
