package main

// The artifact type registry, carried in the binary.
//
// `registry/` next to this file is the ONE canonical copy: it is embedded here AND read by
// the Python measurement tooling, so there is no second copy to drift. That matters more
// than usual for this file, because the whole point of the registry is to stop two
// declarations of the same thing from disagreeing — shipping it twice would be the
// registry's own defect (measured precedent: artifact-path-registry.yaml and templates/
// declare 46 and 81 type names and overlap on 11).
//
// Embedding rather than reading from disk means `fa validate --registry` works in a CI job
// that has only the binary, and it pins the standard to the binary's version. --registry-dir
// overrides it while iterating.

import (
	"embed"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"

	"go.yaml.in/yaml/v2"
)

//go:embed registry/artifact-type-registry.yaml registry/enums.yaml registry/aliases.yaml
var registryFS embed.FS

// ── the schema of the registry itself ────────────────────────────────────────

type TypeSpec struct {
	Family           string            `yaml:"family"`
	Profile          string            `yaml:"profile"`
	Shape            string            `yaml:"shape"`
	Authority        string            `yaml:"authority"`
	Key              []string          `yaml:"key"`
	KeySource        string            `yaml:"key_source"`
	PathRegistryType string            `yaml:"path_registry_type"`
	NamespaceDefect  bool              `yaml:"registry_namespace_defect"`
	RequiredPlus     []string          `yaml:"required+"`
	OptionalPlus     []string          `yaml:"optional+"`
	Enums            map[string]string `yaml:"enums"`
	Links            map[string]string `yaml:"links"`
	Sections         []string          `yaml:"sections"`
	SectionPolicy    string            `yaml:"section_policy"`
	GateSeverity     string            `yaml:"gate_severity"`
	EnforcementLevel string            `yaml:"enforcement_level"`
	PendingTemplate  bool              `yaml:"pending_template"`
	Evidence         string            `yaml:"evidence"`
}

type Defaults struct {
	Required            []string `yaml:"required"`
	Optional            []string `yaml:"optional"`
	DerivedNeverAuthored []string `yaml:"derived_never_authored"`
	Forbidden           []string `yaml:"forbidden"`
	ShapeOverrides      map[string]struct {
		Required []string `yaml:"required"`
	} `yaml:"shape_overrides"`
}

type Registry struct {
	Version         int                  `yaml:"version"`
	Defaults        Defaults             `yaml:"defaults"`
	Types           map[string]*TypeSpec `yaml:"types"`
	GapTypes        map[string]*TypeSpec `yaml:"gap_types"`
	RetiredTypes    map[string]struct {
		Authority string `yaml:"authority"`
		Kind      string `yaml:"kind"`
	} `yaml:"retired_types"`
	SectionPolicies map[string]interface{} `yaml:"section_policies"`
}

type EnumSpec struct {
	Description   string                            `yaml:"description"`
	Closed        *bool                             `yaml:"closed"`
	OpenExtension bool                              `yaml:"open_extension"`
	Values        map[string]map[string]interface{} `yaml:"values"`
	MigratedFrom  map[string]map[string]interface{} `yaml:"migrated_from"`
}

type Enums struct {
	Version int                  `yaml:"version"`
	Enums   map[string]*EnumSpec `yaml:"enums"`
}

type AliasSpec struct {
	Canonical       string            `yaml:"canonical"`
	Set             map[string]string `yaml:"set"`
	N               int               `yaml:"n"`
	PendingTemplate bool              `yaml:"pending_template"`
	NeedsAdjudication bool            `yaml:"requires_per_file_adjudication"`
	Disposition     string            `yaml:"disposition"`
}

type Aliases struct {
	Version    int                       `yaml:"version"`
	Aliases    map[string]*AliasSpec     `yaml:"aliases"`
	Retired    map[string]interface{}    `yaml:"retired"`
	Unresolved map[string]interface{}    `yaml:"unresolved"`
}

type RegistryBundle struct {
	Reg *Registry
	En  *Enums
	Al  *Aliases
	// allTypes merges types + gap_types: a gap type is still a type, it just has no
	// template yet, so it must resolve rather than report as unknown.
	allTypes map[string]*TypeSpec
}

// LoadRegistry reads the embedded registry, or from dir when dir != "".
func LoadRegistry(dir string) (*RegistryBundle, error) {
	read := func(name string) ([]byte, error) {
		if dir != "" {
			return os.ReadFile(filepath.Join(dir, name))
		}
		return registryFS.ReadFile("registry/" + name)
	}
	b := &RegistryBundle{Reg: &Registry{}, En: &Enums{}, Al: &Aliases{}}
	for _, f := range []struct {
		name string
		into interface{}
	}{
		{"artifact-type-registry.yaml", b.Reg},
		{"enums.yaml", b.En},
		{"aliases.yaml", b.Al},
	} {
		raw, err := read(f.name)
		if err != nil {
			return nil, fmt.Errorf("registry: read %s: %w", f.name, err)
		}
		if err := yaml.Unmarshal(raw, f.into); err != nil {
			return nil, fmt.Errorf("registry: parse %s: %w", f.name, err)
		}
	}
	b.allTypes = map[string]*TypeSpec{}
	for k, v := range b.Reg.Types {
		b.allTypes[k] = v
	}
	for k, v := range b.Reg.GapTypes {
		b.allTypes[k] = v
	}
	if len(b.allTypes) == 0 {
		return nil, fmt.Errorf("registry: no types declared")
	}
	return b, nil
}

// Resolve maps an observed document_type to its canonical type plus the field defaults the
// legacy spelling was encoding. The `set` payload is the whole reason aliases are not a
// rename map: `local-adversary-review` carried scope=story and reviewer_role=adversary in
// its NAME, and a rename alone would have destroyed both.
func (b *RegistryBundle) Resolve(dt string) (canonical string, spec *TypeSpec, set map[string]string, status string) {
	if _, ok := b.Al.Retired[dt]; ok {
		return "", nil, nil, "retired"
	}
	if _, ok := b.Reg.RetiredTypes[dt]; ok {
		return "", nil, nil, "retired"
	}
	if a, ok := b.Al.Aliases[dt]; ok && a != nil && a.Canonical != "" {
		if ts, ok := b.allTypes[a.Canonical]; ok {
			st := "alias"
			if a.Canonical == dt {
				st = "canonical"
			}
			return a.Canonical, ts, a.Set, st
		}
		return a.Canonical, nil, a.Set, "alias-target-missing"
	}
	if ts, ok := b.allTypes[dt]; ok {
		return dt, ts, nil, "canonical"
	}
	if _, ok := b.Al.Unresolved[dt]; ok {
		return "", nil, nil, "unresolved"
	}
	return "", nil, nil, "unknown"
}

// RequiredFor returns the required field set for a type: the spine (or its shape override)
// plus the type's own delta, minus fields that are derived on write, minus key components
// whose only source today is the filename.
func (b *RegistryBundle) RequiredFor(ts *TypeSpec) []string {
	base := b.Reg.Defaults.Required
	if ov, ok := b.Reg.Defaults.ShapeOverrides[ts.Shape]; ok && len(ov.Required) > 0 {
		base = ov.Required
	}
	skip := map[string]bool{"version": true, "timestamp": true}
	if ts.KeySource == "filename" {
		for _, k := range ts.Key {
			skip[k] = true
		}
	}
	var out []string
	for _, f := range append(append([]string{}, base...), ts.RequiredPlus...) {
		if !skip[f] {
			out = append(out, f)
		}
	}
	sort.Strings(out)
	return out
}

// CheckEnum classifies a value against a declared enum.
//
//	"ok"          a declared value
//	"migratable"  a declared migrated_from value: the migration table knows what to do
//	"illegal"     not declared anywhere -> a finding
//	"unchecked"   the enum is open_extension or explicitly not closed
func (b *RegistryBundle) CheckEnum(enumName, value string) string {
	e, ok := b.En.Enums[enumName]
	if !ok || e == nil {
		return "unchecked"
	}
	if e.OpenExtension || (e.Closed != nil && !*e.Closed) {
		return "unchecked"
	}
	if _, ok := e.Values[value]; ok {
		return "ok"
	}
	if _, ok := e.MigratedFrom[value]; ok {
		return "migratable"
	}
	return "illegal"
}

// ── the section partition (D-A) ──────────────────────────────────────────────

var (
	headingRe = regexp.MustCompile(`^(#{2,6})\s+(.*)$`)
	fenceRe   = regexp.MustCompile("^\\s*(```|~~~)")
)

type Section struct {
	Ord     int
	Depth   int
	Heading string
	Body    string
}

// SplitSections is the derived, ordinal-keyed section partition from D-A.
//
// Two properties this must have, both measured rather than assumed:
//  1. LOSSLESS — concat of every Body equals the input exactly. Verified byte-exact on
//     6,537 markdown files across three corpora, and asserted by a test here.
//  2. ORDINAL-KEYED — the heading is DATA, not the key. 110 documents in those corpora
//     carry 1,968 duplicate `##`+ headings, so keying on the heading would collide.
//
// Fence-aware, because a `## ` line inside a code block is not a heading.
func SplitSections(body string) []Section {
	var out []Section
	var cur strings.Builder
	head, depth, inFence, started := "", 0, false, false
	flush := func() {
		if started || cur.Len() > 0 {
			out = append(out, Section{Ord: len(out), Depth: depth, Heading: head, Body: cur.String()})
		}
		cur.Reset()
	}
	for _, line := range splitKeepNL(body) {
		if fenceRe.MatchString(line) {
			inFence = !inFence
			cur.WriteString(line)
			continue
		}
		if !inFence {
			if m := headingRe.FindStringSubmatch(strings.TrimRight(line, "\r\n")); m != nil {
				flush()
				head, depth, started = strings.TrimSpace(m[2]), len(m[1]), true
				cur.WriteString(line)
				continue
			}
		}
		cur.WriteString(line)
	}
	flush()
	return out
}

// splitKeepNL splits into lines KEEPING their terminators, which is what makes the
// partition byte-exact. Splitting on "\n" and rejoining loses a missing final newline.
func splitKeepNL(s string) []string {
	var out []string
	start := 0
	for i := 0; i < len(s); i++ {
		if s[i] == '\n' {
			out = append(out, s[start:i+1])
			start = i + 1
		}
	}
	if start < len(s) {
		out = append(out, s[start:])
	}
	return out
}

// SectionsLossless is the D-A invariant, checkable at runtime rather than trusted.
func SectionsLossless(body string) bool {
	var sb strings.Builder
	for _, s := range SplitSections(body) {
		sb.WriteString(s.Body)
	}
	return sb.String() == body
}
