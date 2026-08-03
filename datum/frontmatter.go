package main

// YAML-ish frontmatter scraping. Deliberately not a real YAML parser: the corpus
// uses a small, stable subset and a full parser would accept shapes the corpus
// treats as violations.
//
// Every branch below exists because the Python prototype got it WRONG first and
// the bug faked a clean result. Do not "simplify" these away:
//
//   1. Block lists (`k:` then `  - a`). Skipping indented lines discarded EVERY
//      list-valued edge in the corpus, which is why the trace table came back
//      empty on pass 1.
//   2. Wrapped inline lists. The corpus wraps long ones across physical lines;
//      reading only the first line truncates the list mid-element.
//   3. Trailing YAML comments (`verification_properties: []  # [process-gap]`).
//   4. Quoted scalars.
//
// ⚠ RULE 3 WAS ITSELF A SILENT DATA-LOSS DEFECT — INSTANCE TEN, and the second one
// found inside `datum` itself.
//
// `trailingCommentRe` is `\s+#.*$`, and it was applied to EVERY value containing a
// `#`. But a `#` inside a QUOTED scalar is a literal character, not a comment
// introducer — and the corpus writes `last_amended: "… MERGED PR #164 9ed17b1d …"`.
// The stripper deleted from ` #164` to end of line, so `last_amended` on
// `stories/STORY-INDEX.md` parsed as **40 characters out of 50,785**.
//
// Measured over all three corpora before fixing: **210 values changed by the
// stripper, 113 of them quoted, 171,284 characters silently discarded** — worst
// single loss 50,748 chars. It was found because a conservation gate FAILED ITS OWN
// PREDICTION (it expected a 116-entry ledger and found none), and then by reading
// that one case rather than tuning the detector.
//
// The comment two rules up already warned that a looser rule here "made the index's
// headline count assertion invisible to the gate meant to check it — a checker
// missing its input reports a false clean." Rule 3 did the same thing by a different
// route.
//
// The fix distinguishes the two cases instead of guessing:
//   - QUOTED value  -> the value is the quoted span; a `#` inside it is LITERAL, and
//     only a `#` AFTER the closing quote is a comment. 113 unambiguous defects fixed.
//   - UNQUOTED value -> ` #` really does start a YAML comment, so it is still
//     stripped — but the strip is REPORTED as a note, because the corpus plainly
//     intends the whole line as the value and silent loss is the banned class.

import (
	"regexp"
	"strings"
)

var fmRe = regexp.MustCompile(`(?s)\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*\r?\n`)

var blockItemRe = regexp.MustCompile(`^\s+-\s+`)

// inlineListStartRe matches a top-level key whose value opens an inline list.
var inlineListStartRe = regexp.MustCompile(`^[^\s#:][^:]*:\s*\[`)
var trailingCommentRe = regexp.MustCompile(`\s+#.*$`)

// FMNote is something the parser had to DECIDE, surfaced so the caller can record it
// as a finding. A parser that makes a lossy decision silently is this repo's most
// repeated defect class (ten instances); this is how rule 3 stops being the eleventh.
type FMNote struct {
	Key    string
	Kind   string // comment-stripped-from-unquoted | unterminated-quote
	Lost   int    // characters removed
	Detail string
}

// closingQuote returns the index of the quote that CLOSES the scalar opened at v[0],
// or -1 if it is unterminated.
//
// Escapes are style-specific in YAML and both are handled, because getting this wrong
// silently truncates: `\"` escapes a double quote, and `''` is a literal single quote
// inside a single-quoted scalar.
func closingQuote(v string, q byte) int {
	for i := 1; i < len(v); i++ {
		switch {
		case q == '"' && v[i] == '\\':
			i++ // skip the escaped character, whatever it is
		case v[i] == q:
			if q == '\'' && i+1 < len(v) && v[i+1] == '\'' {
				i++ // '' is a literal quote, not the terminator
				continue
			}
			return i
		}
	}
	return -1
}

// splitScalarAndComment separates a raw YAML scalar from a trailing comment, honouring
// quoting. Returns the value (unquoted), and how many characters a comment strip
// removed (0 when nothing was stripped).
func splitScalarAndComment(v string) (val string, lost int, note string) {
	if v == "" {
		return v, 0, ""
	}
	q := v[0]
	if q == '"' || q == '\'' {
		// Find the closing quote, HONOURING ESCAPES. A naive IndexByte is wrong and was
		// measured wrong: `stories/STORY-INDEX.md`'s `last_amended` contains
		// `Some(\"burst-log.md\")` at offset 18,287, so the first `"` found is an
		// ESCAPED one and stopping there truncated a 50,787-char value to 18,287.
		// Found the same way as instance ten — a gate failed its prediction (it still
		// could not see the 116-entry ledger) and one case was read instead of tuning.
		//
		// YAML escaping differs by quote style: `\"` inside double quotes, `''` inside
		// single quotes.
		if end := closingQuote(v, q); end > 0 {
			inner := v[1:end]
			rest := v[end+1:]
			// a comment may follow the closing quote
			if i := strings.Index(rest, "#"); i >= 0 {
				lost = len(rest) - i
			}
			return inner, 0, ""
		}
		// Unterminated quote: the value runs to end of line. Do NOT strip on `#` —
		// that is what discarded 50,748 characters. Report the malformation instead.
		return strings.TrimLeft(v, string(q)), 0, "unterminated-quote"
	}
	// unquoted: YAML says ` #` introduces a comment. Strip, but report the loss.
	if strings.Contains(v, "#") {
		stripped := strings.TrimSpace(trailingCommentRe.ReplaceAllString(v, ""))
		if stripped != v {
			return stripped, len(v) - len(stripped), "comment-stripped-from-unquoted"
		}
	}
	return v, 0, ""
}

// Frontmatter is a parsed block. Values are either a scalar string or a list.
type Frontmatter map[string]any

// ParseFrontmatter splits a document into its frontmatter map and its body.
// A document with no frontmatter yields an empty map and the whole text.
func ParseFrontmatter(text string) (Frontmatter, string) {
	fm, body, _ := ParseFrontmatterNotes(text)
	return fm, body
}

// ParseFrontmatterNotes is ParseFrontmatter plus the decisions it had to make. Callers
// that can record findings should use this one; see corpus.go.
func ParseFrontmatterNotes(text string) (Frontmatter, string, []FMNote) {
	var notes []FMNote
	m := fmRe.FindStringSubmatchIndex(text)
	if m == nil {
		return Frontmatter{}, text, nil
	}
	block := text[m[2]:m[3]]
	body := text[m[1]:]
	out := Frontmatter{}

	// (2) Join wrapped inline lists before interpreting anything: the corpus wraps
	// long ones across physical lines, and reading only the first line truncates
	// the list mid-element.
	//
	// The continuation test must be "this key's value OPENED an inline list and has
	// not closed it" — NOT "this line has unbalanced brackets". Prose values contain
	// stray brackets: BC-INDEX's own `last_amended` holds "... [Prior: ...", and the
	// looser rule swallowed every key after it, silently including `total_bcs`. That
	// made the index's headline count assertion invisible to the gate meant to check
	// it — a checker missing its input reports a false clean.
	var joined []string
	openList := false
	for _, raw := range strings.Split(block, "\n") {
		raw = strings.TrimRight(raw, "\r")
		if openList {
			n := len(joined) - 1
			joined[n] += " " + strings.TrimSpace(raw)
			openList = strings.Count(joined[n], "[") > strings.Count(joined[n], "]")
			continue
		}
		joined = append(joined, raw)
		openList = inlineListStartRe.MatchString(raw) &&
			strings.Count(raw, "[") > strings.Count(raw, "]")
	}

	curKey := ""
	for _, raw := range joined {
		trimmed := strings.TrimSpace(raw)
		if trimmed == "" || strings.HasPrefix(trimmed, "#") {
			continue
		}
		// (1) continuation of a block list
		if blockItemRe.MatchString(raw) {
			if curKey != "" {
				item := strings.TrimSpace(strings.SplitN(strings.TrimSpace(raw), "-", 2)[1])
				item = strings.Trim(item, "\"'")
				if lst, ok := out[curKey].([]string); ok {
					out[curKey] = append(lst, item)
				} else if _, exists := out[curKey]; !exists {
					out[curKey] = []string{item}
				}
			}
			continue
		}
		if strings.HasPrefix(raw, " ") || strings.HasPrefix(raw, "\t") {
			continue // nested mapping we do not need
		}
		i := strings.Index(raw, ":")
		if i < 0 {
			continue
		}
		k := strings.TrimSpace(raw[:i])
		v := strings.TrimSpace(raw[i+1:])
		// (3) separate a trailing comment from the value, HONOURING QUOTES. See the
		// instance-ten note at the top of this file: applying the trailing-comment
		// regex to a quoted scalar discarded 171,284 characters across the corpora.
		isList := strings.HasPrefix(v, "[")
		if !isList {
			nv, lost, note := splitScalarAndComment(v)
			if note != "" {
				notes = append(notes, FMNote{Key: k, Kind: note, Lost: lost,
					Detail: truncRunes(v, 120)})
			}
			v = nv
		} else if strings.Contains(v, "#") {
			v = strings.TrimSpace(trailingCommentRe.ReplaceAllString(v, ""))
		}
		curKey = k
		switch {
		case strings.HasPrefix(v, "[") && strings.HasSuffix(v, "]"):
			inner := strings.TrimSpace(v[1 : len(v)-1])
			lst := []string{}
			if inner != "" {
				for _, x := range strings.Split(inner, ",") {
					if x = strings.Trim(strings.TrimSpace(x), "\"'"); x != "" {
						lst = append(lst, x)
					}
				}
			}
			out[k] = lst
		case v == "":
			out[k] = []string{} // a block list may follow
		default:
			out[k] = strings.Trim(v, "\"'") // (4)
		}
	}
	return out, body, notes
}

// List coerces a field to a list of non-empty strings.
func (f Frontmatter) List(key string) []string {
	v, ok := f[key]
	if !ok || v == nil {
		return nil
	}
	if lst, ok := v.([]string); ok {
		out := make([]string, 0, len(lst))
		for _, s := range lst {
			if strings.TrimSpace(s) != "" {
				out = append(out, s)
			}
		}
		return out
	}
	s := strings.TrimSpace(v.(string))
	switch s {
	case "", "[]", "null", "none", "None":
		return nil
	}
	return []string{s}
}

// Scalar coerces a field to a single value, or "" when it is absent, empty, a
// YAML null spelling, or a multi-element list (which is itself a schema
// violation the caller reports separately).
func (f Frontmatter) Scalar(key string) string {
	v, ok := f[key]
	if !ok || v == nil {
		return ""
	}
	if lst, ok := v.([]string); ok {
		if len(lst) == 1 {
			return strings.TrimSpace(lst[0])
		}
		return ""
	}
	s := strings.TrimSpace(v.(string))
	switch s {
	case "", "null", "none", "None", "[]":
		return ""
	}
	return s
}

// firstH1 returns the document's first `# ` heading, which is the authoritative
// title (the index's Title cell is a copy that has drifted 6 times).
func firstH1(body string) string {
	for _, ln := range strings.Split(body, "\n") {
		if strings.HasPrefix(ln, "# ") {
			return strings.TrimSpace(ln[2:])
		}
	}
	return ""
}

// truncRunes cuts to n runes, never mid-rune. Python slices by character; byte
// slicing here would corrupt the em-dashes the corpus is full of.
func truncRunes(s string, n int) string {
	if n <= 0 {
		return ""
	}
	r := []rune(s)
	if len(r) <= n {
		return s
	}
	return string(r[:n])
}
