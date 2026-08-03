package main

// proseref_len_test.go — MEASURE BEFORE WRITING THE RULE.
//
// `fa import ~/Dev/prism/.factory` hard-aborts on `Error 1105: string '...' is too
// large for column 'target'` -- prose_ref.target is VARCHAR(220). The obvious fix is
// to widen the column. The obvious fix may be WRONG: the value in the error message
//
//   "ac-003: token acquisition via `post /oauth2/token` against dtu clone (traces to
//    bc-2.01.016 preconditions satisfied — `sensorauth` open and implementable; ...)"
//
// is not a reference TARGET, it is a paragraph. Widening the column would store
// garbage and call it success -- and this repo has already measured that "a
// normalisation rule aimed at the WRONG COLUMN manufactures exactly what it was added
// to prevent" (292 self-inflicted findings).
//
// So this measures the target-length distribution across all three corpora FIRST, and
// samples the tail, before any column or rule changes. ScanCorpus is pure and needs no
// database, so the abort does not block the measurement.
//
//   FA_LEN_CORPORA=~/Dev/vsdd-factory/.factory,~/Dev/prism/.factory,~/Dev/rivetry/.factory \
//     CGO_ENABLED=1 go test -tags gms_pure_go -run TestProseTargetLengths -v .

import (
	"os"
	"sort"
	"strings"
	"testing"
)

const proseTargetLimit = 220

func TestProseTargetLengths(t *testing.T) {
	spec := os.Getenv("FA_LEN_CORPORA")
	if spec == "" {
		t.Skip("set FA_LEN_CORPORA to a comma-separated list of .factory roots")
	}
	for _, root := range strings.Split(spec, ",") {
		root = expandHome(strings.TrimSpace(root))
		if root == "" {
			continue
		}
		c, err := ScanCorpus(root)
		if err != nil {
			t.Logf("SKIP %s: %v", root, err)
			continue
		}
		var lens, rawLens, keyLens []int
		over := map[string][]ProseRefRow{}
		byKind := map[string]int{}
		for _, p := range c.ProseRefs {
			lens = append(lens, len(p.Target))
			rawLens = append(rawLens, len(p.Raw))
			keyLens = append(keyLens, len(p.CitingKey))
			byKind[p.Kind]++
			if len(p.Target) > proseTargetLimit {
				over[p.Kind] = append(over[p.Kind], p)
			}
		}
		if len(lens) == 0 {
			t.Logf("%s: 0 prose refs", root)
			continue
		}
		sort.Ints(lens)
		pct := func(p float64) int { return lens[min(len(lens)-1, int(float64(len(lens))*p))] }
		nOver := 0
		for _, v := range over {
			nOver += len(v)
		}
		t.Logf("")
		t.Logf("=== %s ===", root)
		t.Logf("prose refs %d  by kind %v", len(lens), byKind)
		t.Logf("target length: p50 %d · p90 %d · p99 %d · p99.9 %d · MAX %d",
			pct(.50), pct(.90), pct(.99), pct(.999), lens[len(lens)-1])
		t.Logf("OVER VARCHAR(%d): %d (%.3f%%)", proseTargetLimit, nOver,
			100*float64(nOver)/float64(len(lens)))
		sort.Ints(rawLens)
		sort.Ints(keyLens)
		rp := func(p float64) int { return rawLens[min(len(rawLens)-1, int(float64(len(rawLens))*p))] }
		kp := func(p float64) int { return keyLens[min(len(keyLens)-1, int(float64(len(keyLens))*p))] }
		t.Logf("raw        length: p50 %d · p99 %d · p99.9 %d · MAX %d  (col VARCHAR(220), IN THE PK)",
			rp(.50), rp(.99), rp(.999), rawLens[len(rawLens)-1])
		t.Logf("citing_key length: p50 %d · p99 %d · MAX %d  (col VARCHAR(300), IN THE PK)",
			kp(.50), kp(.99), keyLens[len(keyLens)-1])
		for kind, rows := range over {
			t.Logf("  kind=%s: %d over", kind, len(rows))
			for i, r := range rows {
				if i >= 5 {
					t.Logf("    … and %d more", len(rows)-5)
					break
				}
				t.Logf("    len=%d status=%s line=%d", len(r.Target), r.Status, r.Line)
				t.Logf("      citing=%s", truncRunes(r.CitingKey, 90))
				t.Logf("      target=%q", truncRunes(r.Target, 160))
			}
		}
	}
}
