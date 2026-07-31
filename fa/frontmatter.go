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

import (
	"regexp"
	"strings"
)

var fmRe = regexp.MustCompile(`(?s)\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*\r?\n`)

var blockItemRe = regexp.MustCompile(`^\s+-\s+`)

// inlineListStartRe matches a top-level key whose value opens an inline list.
var inlineListStartRe = regexp.MustCompile(`^[^\s#:][^:]*:\s*\[`)
var trailingCommentRe = regexp.MustCompile(`\s+#.*$`)

// Frontmatter is a parsed block. Values are either a scalar string or a list.
type Frontmatter map[string]any

// ParseFrontmatter splits a document into its frontmatter map and its body.
// A document with no frontmatter yields an empty map and the whole text.
func ParseFrontmatter(text string) (Frontmatter, string) {
	m := fmRe.FindStringSubmatchIndex(text)
	if m == nil {
		return Frontmatter{}, text
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
		// (3) strip a trailing comment
		if strings.Contains(v, "#") {
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
	return out, body
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
