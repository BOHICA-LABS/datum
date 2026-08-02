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
	//
	// A `.` ends the capture ONLY when it is not part of a number: the corpus addresses
	// `§D-15.1`, `§BC-1.05.036` and `§9.2`, and a plain `[^.]` class truncated every one of them
	// at the first dot — `§D-15.1` was captured as `D-15`, which matches no heading, so the
	// reference was reported dangling against `### D-15.1 — Single physical stream for all
	// events`, a heading that is right there. RE2 has no lookahead, so "dot followed by a digit"
	// is spelled as an alternation rather than as `\.(?!\d)`.
	sectionRefRe = regexp.MustCompile(`§\s*((?:[^,;).]|\.\d){2,60})`)
	verNumRe     = regexp.MustCompile(`^\d+\.\d+$`)
	// `§7`, `§7:`, `§7 preamble`, `§1-§12` — an ordinal reference into the partition.
	numericSectionRe = regexp.MustCompile(`^(\d{1,3})\b`)
	// `Postcondition 5`, `Precondition 2`, `Invariant 4`, `Decision 1`, `Event 3`, `Scenario 8`
	itemInSectionRe = regexp.MustCompile(`^([A-Za-z][A-Za-z-]{3,20})\s+\d{1,3}\b`)
	// The leading artifact id of a FILENAME: `ADR-019-plugin-async-…` is referenced as `ADR-019`.
	docIDPrefixRe = regexp.MustCompile(`^((?:ADR|BC|VP|FR|NFR|DI|CAP|TD|S|E)-[0-9]+(?:\.[0-9]+){0,2})(?:-|$)`)
	// Any token that could name a document, so the owner can be looked up rather than pattern-matched.
	ownerTokenRe = regexp.MustCompile(`[A-Za-z][A-Za-z0-9._-]*`)
	// A token distinctive enough to name a document: carries a digit, a hyphen, or `.md`, or is
	// written in caps. Guards against `state`/`lessons`/`epic` colliding with English prose.
	distinctiveOwnerRe = regexp.MustCompile(`[0-9]|-|\.md$|^[A-Z][A-Z0-9]+$`)
	// An artifact id naming an ITEM inside a section — `CAP-009`, `FR-042`, `EC-008`, `S-5.03`.
	itemIDRe = regexp.MustCompile(`^((?:CAP|FR|NFR|EC|AC|PC|DI|BC|VP|ADR|TD|S|E)-[0-9]+(?:\.[0-9]+){0,2})\b`)
	// Markdown list, table, quote and emphasis markers, so a DEFINITION at the start of a line is
	// recognised through them: `**CAP-009 — …**`, `- CAP-009:`, `| CAP-009 |`.
	itemMarkerRe = regexp.MustCompile(`^[\s>|*_+-]*`)
	// A bold run opening a line — the corpus's item-definition convention. Backticks are dropped
	// from the label first so `**`event.category` taxonomy registry**` indexes as prose.
	itemBoldRe = regexp.MustCompile(`^\*\*([^*]{2,80})\*\*`)
	// List, table and quote markers ONLY — asterisks are preserved so the bold run survives.
	quoteMarkerRe = regexp.MustCompile("^[\\s>|+-]*|`")
)

// trimWordPunct strips the punctuation the surrounding sentence attaches to a section name.
//
// Only TRAILING punctuation, and only characters that cannot occur inside a heading: a heading
// legitimately contains `/`, `—`, `(`, `&` and `'`, so stripping those would corrupt the name it
// is trying to recover.
// A LEADING quote is stripped too, because the corpus quotes the name it is citing —
// `§"Audit Risk Items Carried Forward"`, `§"The sandboxing constraint" lines 41-52` — and no
// heading begins with a quote character, so this cannot corrupt a real name. That shape was the
// entire residual disagreement between this resolver and a hand check: 10 of 11 cases.
func trimWordPunct(words []string) []string {
	out := make([]string, 0, len(words))
	for _, w := range words {
		out = append(out, strings.Trim(strings.TrimRight(w, `:;,`), `"'`+"`"))
	}
	return out
}

// singleTokenIDRe is an id standing alone as a section name — `D-15.1`, `CAP-009`, `FR-042`,
// `BC-1.05.036`. Distinctive enough to attribute on its own, unlike a bare English word.
var singleTokenIDRe = regexp.MustCompile(`^[A-Z][A-Z]*-\d+(?:\.\d+)*$`)

// ordAmbiguous marks a section NAME that the owner carries more than once. It is not an ordinal:
// a reference to it is `unresolvable` (undecidable), never `dangling` (absent).
const ordAmbiguous = -2

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

		// Indices, not just submatches: the owner of a reference is decided by what precedes
		// THIS `§`, so the match's position on the line is load-bearing.
		for _, ix := range sectionRefRe.FindAllStringSubmatchIndex(masked, -1) {
			name := strings.TrimSpace(masked[ix[2]:ix[3]])
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
			} else if owner := ownerNamedBefore(masked, ix[0], sectionsByDoc); owner != "" {
				// THE OWNER IS STATED, so the reference is resolvable — against THAT
				// document's partition, not this one's. Resolving only against the citing
				// document reported 3,576 of 3,609 refs (99%) as unresolvable: honest, and
				// useless. `ADR-019 §Consequences` names its owner on the line.
				row.Target = truncRunes(owner+" §"+name, 200)
				// normalizeCiteTarget folds `capabilities.md` onto `CAPABILITIES`, the same way a
				// version cite is folded, so one document is not two owners.
				if sec, ok := sectionsByDoc[normalizeCiteTarget(owner)]; ok {
					if nm, ord, ok := resolveSectionName(name, sec); ok {
						row.Status, row.SectionOrd = "resolved", ord
						row.Target, row.Raw = truncRunes(owner+" §"+nm, 200), truncRunes("§"+nm, 200)
					} else if ord == ordAmbiguous {
						// The owner HAS the name, several times over. Not a missing section.
						row.Status = "unresolvable"
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
	// Punctuation that ATTACHES to the section name defeats both passes: `§Description:` matches
	// no heading exactly, and `HasPrefix("description", "description:")` is false, so a citation
	// of a section every BC has was reported as missing. The colon is the corpus's own sentence
	// grammar — `BC-1.05.035 §Description:` introduces a quotation — and `§Related BCs:`,
	// `§FR-043: clean` and `§Subsystem Assignments:` are the same shape. MEASURED as the single
	// largest remaining cause: 15 of a 26-row hand-read sample.
	//
	// Trimmed per WORD rather than from the whole capture, because the name ends mid-capture:
	// in `§Purity Classification: "sink chain" + fabricated …` the colon sits on the LAST word of
	// the name with prose after it.
	words := trimWordPunct(strings.Fields(captured))
	// Pass 1: the longest leading run of words that is EXACTLY a heading.
	for n := len(words); n >= 1; n-- {
		cand := strings.Join(words[:n], " ")
		if ord, ok := sections[strings.ToLower(cand)]; ok {
			// The name exists in the owner but names SEVERAL sections, so which one the
			// reference means cannot be decided. That is `unresolvable`, and reporting it as
			// `dangling` asserts the owner does not contain the name — the opposite of what was
			// measured. MEASURED at 6 of a 30-row sample, the single largest cause: `PRD §FR-043`
			// is dangling today although `#### FR-043` is a heading FOUR times (one per subsystem
			// slice), which is D-A's duplicate-heading problem surfacing in the resolver.
			if ord == ordAmbiguous {
				return "", ordAmbiguous, false
			}
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
	// A ONE-word candidate is allowed only when that word is an ID. The refusal exists because
	// `§host` would match any heading beginning with "host" — a vague guess. `§D-15.1` is not
	// vague: it matches `### D-15.1 — Single physical stream for all events` and nothing else.
	//
	// MEASURED: 119 dangling references named an id that IS a heading, blocked purely by this
	// floor. `D-\d+` is included because an ADR states its decisions that way, and that form
	// matches neither the id-item index nor the two-word floor — 69 of the residual were ADR-015.
	floor := 2
	if len(words) > 0 && singleTokenIDRe.MatchString(words[0]) {
		floor = 1
	}
	for n := len(words); n >= floor; n-- {
		cand := strings.ToLower(strings.Join(words[:n], " "))
		best, bestOrd := "", -1
		for h, ord := range sections {
			if ord == ordAmbiguous {
				continue // not a heading, and not decidable
			}
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

// indexItemIDs adds the FOURTH addressing scheme: a section named by the ARTIFACT ID of an item
// inside it.
//
// `capabilities.md §CAP-009` is not a heading reference. capabilities.md has FIVE headings
// (`# Capabilities`, three priority bands, `## CHANGELOG`) and states each capability as a bold
// list item — `**CAP-009 — Author and publish WASM hook plugins using the Rust SDK**`. The
// citation therefore addresses a granularity FINER than D-A's partition, exactly as
// `§Postcondition 5` does, but the item is identified by an ID rather than by `Noun N`, so
// itemInSectionRe (which requires a space before the number) cannot see it.
//
// MEASURED over 592 dangling references: 134 name an id that sits in exactly ONE section, 119
// name an id that IS a heading, 86 name an id that appears in SEVERAL sections, and only 3 name
// an id the owner does not contain at all. So this scheme accounts for the overwhelming majority
// of what remained, and the residual truth is 3.
//
// An id is indexed only where a document DEFINES an item — in a heading, or at the start of a
// line once markdown list/table/quote/emphasis markers are stripped. A passing mention mid
// sentence is not a definition, and indexing those would resolve a reference to wherever the id
// was last gossiped about.
//
// An id claimed by MORE THAN ONE section is AMBIGUOUS and is not indexed at all: the reference
// then stays `unresolvable`, which is the honest answer. Picking a winner is how a checker
// converts an ambiguity it cannot adjudicate into a confident wrong claim.
func indexItemIDs(sec map[string]int, body string) {
	seen := map[string]int{}
	ambiguous := map[string]bool{}
	note := func(id string, ord int) {
		k := strings.ToLower(id)
		if _, isHeading := sec[k]; isHeading {
			return // a real heading already owns this name
		}
		if prev, ok := seen[k]; ok && prev != ord {
			ambiguous[k] = true
			return
		}
		seen[k] = ord
	}
	for _, sx := range SplitSections(body) {
		if m := itemIDRe.FindStringSubmatch(sx.Heading); m != nil {
			note(m[1], sx.Ord)
		}
		inFence := false
		for _, line := range strings.Split(sx.Body, "\n") {
			if fenceRe.MatchString(line) {
				inFence = !inFence
				continue
			}
			if inFence {
				continue
			}
			bare := itemMarkerRe.ReplaceAllString(line, "")
			if m := itemIDRe.FindStringSubmatch(bare); m != nil {
				note(m[1], sx.Ord)
			}
			// A BOLD RUN at the start of a line is how this corpus defines an item, whatever the
			// label: `**Class A — Cold-start dispatch …**`, `**CAP-009 — Author and publish …**`,
			// `**`event.category` taxonomy registry**`. The label is indexed whole and the
			// existing prefix pass does the rest, so `§Class A` reaches
			// `class a — cold-start dispatch (per-invocation binary spawn)`.
			//
			// MEASURED: 16 of the 53 remaining dangling references were `ADR-020 §Class A` and
			// `§Class B`, against an ADR whose `### Budget class taxonomy` defines exactly those
			// three items in bold. Generic labels (`**Severity:**`, `**Location:**`) recur across
			// many sections, so the ambiguity rule below drops them on its own rather than needing
			// a stop-list to maintain.
			if m := itemBoldRe.FindStringSubmatch(quoteMarkerRe.ReplaceAllString(line, "")); m != nil {
				if lbl := strings.TrimRight(strings.TrimSpace(m[1]), ":"); len(lbl) >= 2 {
					note(lbl, sx.Ord)
				}
			}
		}
	}
	for k, ord := range seen {
		if ambiguous[k] {
			sec[k] = ordAmbiguous
		} else {
			sec[k] = ord
		}
	}
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

// ownerNamedBefore returns the artifact id that owns the section reference starting at byte
// offset `at`, or "" when none is stated.
//
// The owner is the last id that ends BEFORE the `§` — never merely the last id on the line.
// Those two readings coincide only when a line carries one reference and nothing after it, and
// the corpus is full of lines that carry several:
//
//	Fresh-eyes sweep across ... PRD §FR-043, capabilities §CAP-016, ... BC-INDEX, ARCH-INDEX, ...
//
// A line-scoped "last match wins" gave EVERY reference on that line the owner `ARCH-INDEX`, so
// `PRD §FR-043` was adjudicated against ARCH-INDEX's partition, found absent, and reported
// DANGLING. That is the checker manufacturing exactly the confident-wrong finding set
// report-unresolvable-separately exists to prevent: MEASURED at 93 of 214 dangling refs (43%),
// with the owner the prose states sitting in plain text immediately before the `§`.
//
// The original comment already stated this rule correctly — "puts the owner immediately before
// its section" — so this is the implementation catching up to its own declared intent.
// The owner VOCABULARY is read from the documents the store actually holds, never from a second
// hardcoded list. `ownerNameRe` recognises id SHAPES, and it cannot recognise `PRD §FR-043` or
// `capabilities.md §CAP-009` — measured at 34 of 214 dangling references whose owner sat in plain
// text immediately before the `§` and whose section PRD.md / capabilities.md genuinely contains.
// A hand-maintained vocabulary drifting from another hand-maintained vocabulary is the defect
// class this corpus has already produced four times, so the recognised set is `sectionsByDoc`'s
// own keys.
//
// A token is only allowed to name a document when it is DISTINCTIVE — it carries a digit, a
// hyphen or a `.md`, or it is written in caps. Without that guard, ordinary English collides:
// `state`, `lessons`, `index`, `epic`, `glossary` and `convergence` are all document names in
// this corpus, and "the epic §Related BCs" would silently attribute to whichever file is called
// `epic.md`. 11 of 2,883 keys are all-alpha, so the guard costs almost nothing and a missed
// owner degrades to `unresolvable` rather than to a wrong finding.
// Only the token IMMEDIATELY before the marker can be the owner. If that token does not name a
// document, attribution is REFUSED — the scan never reaches further back for something that
// looks like an id.
//
// Reaching back is worse than giving up, because it does not fail to attribute, it attributes
// WRONGLY: in `The v1.26 burst did not sweep §Purity Classification` the nearest id is an
// `ADR-015` cited earlier in the sentence as a REASON, and in `S-3.03:23-24 declares VP-038; body
// §VP lines 62-69` it is a `VP-038` that the sentence names as the thing being declared. Both
// produced a confident dangling finding against a document the reference was never about; that
// shape was 7 of a 30-row hand-read sample. An unstated owner is `unresolvable`, which costs
// nothing but a count.
func ownerNamedBefore(s string, at int, docs map[string]map[string]int) string {
	if at > len(s) {
		return ""
	}
	var last string
	var lastStart int
	for _, loc := range ownerTokenRe.FindAllStringIndex(s[:at], -1) {
		last, lastStart = s[loc[0]:loc[1]], loc[0]
	}
	if last == "" {
		return ""
	}
	// A token that is ITSELF a section reference is not an owner. An enumeration puts the previous
	// section's NAME immediately before the next marker:
	//
	//	Sweep these sections: §Description, §Postconditions, §Invariants, §Edge Cases, …
	//
	// so `§Edge Cases` was attributed to `Invariants` — which happens to be a real document
	// (invariants.md, a domain-spec-section), making it a confident wrong owner rather than a
	// harmless miss. Every reference in such a list belongs to whatever the list belongs to, which
	// the line does not say: `unresolvable`.
	if strings.HasSuffix(strings.TrimRight(s[:lastStart], " \t"), "§") {
		return ""
	}
	if ownerNameRe.MatchString(last) {
		return last
	}
	// Otherwise the token must NAME a document the store holds. That set is read from the
	// documents themselves, so there is no second hand-maintained vocabulary to drift: only 11 of
	// 2,883 keys are all-alpha, and the position rule already excludes the English collision that
	// motivated a guard here — in `POST-MERGE STATE blockquote added to §Tasks` the token before
	// the marker is `to`, not `STATE`.
	if _, held := docs[normalizeCiteTarget(last)]; held {
		return last
	}
	return ""
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

	// Which documents may be named by FILENAME rather than by artifact id is read FROM THE
	// REGISTRY, never from the file tree.
	//
	// The registry already declares it: a type keyed `[project]` (prd, story-index, architecture)
	// or `[section]` (domain-spec-section — "`section` is the key, not the filename") is a
	// singleton a reference can name by name. Every other type is keyed by an id, a cycle or a
	// pass, and its files must be named by that id.
	//
	// MEASURED, and this guard is why it is registry-derived: accepting ANY markdown basename as
	// an owner attributed `Pass-5 §Cure-Extension Parsimony Note` — adversary pass 5 of an S-15.17
	// review — to `cycles/…/adversarial-reviews/pass-5.md`, an unrelated document in another
	// cycle, and reported the section missing. 55 references took that shape. `adversarial-review`
	// is keyed `[cycle, scope, target, pass]`, so the registry already knew `pass-5` is not a name.
	nameAddressable := map[string]bool{}
	if bundle, err := LoadRegistry(""); err == nil {
		for name, ts := range bundle.allTypes {
			if len(ts.Key) == 1 && (ts.Key[0] == "project" || ts.Key[0] == "section") {
				nameAddressable[name] = true
			}
		}
	}
	// A registry that will not load degrades to id-shaped owners only — an owner we fail to
	// recognise becomes `unresolvable`, which is the honest answer, never a dangling finding.

	// Pass 1b: every document's section partition, keyed by EVERY name a reference uses for it.
	//
	// Two keys per document, because the corpus names a document two ways and a single-key map
	// silently loses one of them:
	//
	//   full basename   `BC-1.05.036`, `capabilities`, `PRD`
	//   id prefix       `ADR-019`, for `ADR-019-plugin-async-semantics-at-registry-layer.md`
	//
	// MEASURED: basename-only keying left `ADR-019 §Consequences` unresolvable 14 times — the
	// owner was read correctly and the lookup then missed, because no file is *named* `ADR-019`.
	// 2,258 of 2,883 documents carry an id prefix.
	//
	// A key claimed by MORE THAN ONE file is AMBIGUOUS and resolves to nothing. Assignment
	// silently overwrote: 39 basenames are shared (`INDEX`, `LESSONS`, `DECISION-LOG`,
	// `BURST-LOG` — one per cycle directory) and 4 id prefixes are (`E-10` by 18 files), so the
	// last file walked won and every reference to those names was adjudicated against an
	// arbitrary document. Resolving an ambiguous name is how a checker produces a confident
	// wrong finding; `unresolvable` is the honest answer and the distinction
	// report-unresolvable-separately exists to carry it.
	sectionsByDoc := map[string]map[string]int{}
	ambiguous := map[string]bool{}
	claimedBy := map[string]string{}
	addKey := func(key, owner string, sec map[string]int) {
		if key == "" {
			return
		}
		if prev, seen := claimedBy[key]; seen && prev != owner {
			ambiguous[key] = true
			delete(sectionsByDoc, key)
			return
		}
		if ambiguous[key] {
			return
		}
		claimedBy[key] = owner
		sectionsByDoc[key] = sec
	}
	for _, d := range docs {
		sec := map[string]int{}
		for _, sx := range SplitSections(d.body) {
			if sx.Heading != "" {
				sec[strings.ToLower(sx.Heading)] = sx.Ord
			}
		}
		indexItemIDs(sec, d.body)
		base := strings.ToUpper(strings.TrimSuffix(filepathBase(d.key), ".md"))
		// An id prefix is always a legal name: `ADR-019-plugin-async-…md` IS `ADR-019`.
		if m := docIDPrefixRe.FindStringSubmatch(base); m != nil {
			addKey(m[1], d.key, sec)
			if m[1] == base {
				continue
			}
		}
		// A bare FILENAME is a legal name only for a registry-declared singleton.
		if nameAddressable[d.dtype] {
			addKey(base, d.key, sec)
		}
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
	// REPORTED IN AGGREGATE, DELIBERATELY, and STILL not one finding per reference — now for a
	// MEASURED reason rather than an unmeasured one.
	//
	// The set was reduced from 214 to 30 by fixing the resolver, and then ALL 30 were hand-read
	// against the corpus and adjudicated one by one: 11 are REAL (the owner is right and the
	// section is genuinely absent — `ADR-015 §Negative consequences` three times, where the
	// heading is `### Negative / Trade-offs`) and 19 are still the CHECKER's.
	//
	// 37% precision does not earn per-reference reporting. It is far better than the 0-of-30 the
	// same method measured before this work, and the 11 are individually verified, but a
	// hand-adjudicated batch is not a mechanical property: the gate must not claim a precision it
	// cannot reproduce on the next import.
	//
	// The 19 decompose into named causes, each with a worked example in
	// research/PROSE-REFS-OR-FIELDS.md:
	//   ABBREVIATED names    `§EC` for Edge Cases, `§Purity` for Purity Classification
	//   COMPOUND addresses   `§E-REG-003 §Postconditions` — two markers, one referent
	//   PLACEHOLDERS         `§FR-NNN` is a template slot, not a reference
	//   NOT A REFERENCE      `§FR Rows vs Stories FR Traces` is a finding title
	//   SPACING              `§Source/Origin` against the heading `Source / Origin`
	//   FENCED items         a bold item inside a code fence is not indexed
	//
	// Per-reference reporting is earned when a sample of this set is majority-REAL, not when the
	// count is small.
	if dang > 0 {
		v.find("section references naming an owner that has no such section",
			fmt.Sprintf("%d of %d", dang, un+res+dang), ClassDangling,
			"AGGREGATE ONLY: all 30 hand-read — 11 real, 19 the checker's, so 37% precision does "+
				"not yet earn a per-reference finding")
	}
	return nil
}
