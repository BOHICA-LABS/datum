package main

// fa — the sole interface to factory artifacts.
//
// PHASE 1 ONLY (DECISIONS D3, as superseded 2026-07-31): a read-only shadow.
// `import` builds a throwaway Dolt store from the markdown corpus and `validate`
// runs the gates as SQL against it. Markdown stays the single source of truth.
// Nothing is written back to the corpus, nothing is pushed, no daemon runs, and
// there is no `dolt` binary dependency anywhere — including CI.
//
// Subcommands that belong to later phases are present only where their absence
// would be a design hole (see `aggregate`), and they say so rather than pretending.

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"
)

const usage = `fa — the sole interface to factory artifacts (phase 1: read-only shadow)

usage: fa <command> [flags]

  init                       create or upgrade the store (both zones)
  import <corpus>            shadow a markdown corpus into the store (idempotent)
  validate                   run the gates; fails on findings not in the baseline
      --registry <corpus>      also run the artifact type registry gate on that corpus
      --registry-dir <dir>     override the embedded registry YAML
  baseline write             record the current findings as the dated allowlist
      --registry <corpus>      include the registry gate's findings in the baseline
  count                      record counts, derived — never stored
  doctor                     store health: writable, unmerged, schema, imported
  aggregate plan             staging-ref quarantine policy (phase 2 plumbing pending)
  version

common flags:
  --db <dir>                 store root (default .fa-db, or $FA_DB)

`

func main() {
	if len(os.Args) < 2 {
		fmt.Fprint(os.Stderr, usage)
		os.Exit(2)
	}
	ctx := context.Background()
	var err error
	switch os.Args[1] {
	case "init":
		err = cmdInit(ctx, os.Args[2:])
	case "import":
		err = cmdImport(ctx, os.Args[2:])
	case "validate":
		err = cmdValidate(ctx, os.Args[2:])
	case "baseline":
		err = cmdBaseline(ctx, os.Args[2:])
	case "count":
		err = cmdCount(ctx, os.Args[2:])
	case "doctor":
		err = cmdDoctor(ctx, os.Args[2:])
	case "aggregate":
		err = cmdAggregate(ctx, os.Args[2:])
	case "version":
		fmt.Printf("fa %s (schema v%d, embedded dolthub/driver/v2)\n", faVersion, schemaVersion)
	case "-h", "--help", "help":
		fmt.Print(usage)
	default:
		fmt.Fprintf(os.Stderr, "unknown command %q\n\n%s", os.Args[1], usage)
		os.Exit(2)
	}
	if err != nil {
		// exitError carries a deliberate status: a gate that FAILED is not the same
		// event as a tool that BROKE, and CI must be able to tell them apart.
		if ee, ok := err.(exitError); ok {
			if ee.msg != "" {
				fmt.Fprintln(os.Stderr, ee.msg)
			}
			os.Exit(ee.code)
		}
		fmt.Fprintf(os.Stderr, "fa: %v\n", err)
		os.Exit(2)
	}
}

type exitError struct {
	code int
	msg  string
}

func (e exitError) Error() string { return e.msg }

func defaultDB() string {
	if v := os.Getenv("FA_DB"); v != "" {
		return v
	}
	return ".fa-db"
}

// ---------------------------------------------------------------- init

func cmdInit(ctx context.Context, args []string) error {
	fs := flag.NewFlagSet("init", flag.ExitOnError)
	db := fs.String("db", defaultDB(), "store root")
	_ = fs.Parse(args)

	for _, zone := range []string{ZoneOpen, ZoneWalled} {
		s, err := Open(ctx, *db, zone, true)
		if err != nil {
			return err
		}
		if err := ensureSchema(ctx, s); err != nil {
			s.Close()
			return err
		}
		changed, err := s.DoltCommit(ctx, "schema: initialise zone "+zone+" (fa "+faVersion+")")
		if err != nil {
			s.Close()
			return err
		}
		fmt.Printf("zone %-7s %s  schema v%d%s\n", zone, s.Dir, schemaVersion,
			map[bool]string{true: "", false: " (already current)"}[changed])
		s.Close()
	}
	return nil
}

// ---------------------------------------------------------------- import

func cmdImport(ctx context.Context, args []string) error {
	fs := flag.NewFlagSet("import", flag.ExitOnError)
	db := fs.String("db", defaultDB(), "store root")
	_ = fs.Parse(args)
	if fs.NArg() != 1 {
		return fmt.Errorf("usage: fa import <corpus-path>")
	}
	root, err := filepath.Abs(expandHome(fs.Arg(0)))
	if err != nil {
		return err
	}
	s, err := Open(ctx, *db, ZoneOpen, true)
	if err != nil {
		return err
	}
	defer s.Close()
	st, err := Import(ctx, s, root, os.Stdout)
	if err != nil {
		return err
	}
	fmt.Printf("universes  %s\n", joinCounts(st.Universes))
	fmt.Printf("fingerprint %s\n", st.Fingerprint[:16])
	return nil
}

func joinCounts(m map[string]int) string {
	keys := make([]string, 0, len(m))
	for k := range m {
		keys = append(keys, k)
	}
	sortStrings(keys)
	var parts []string
	for _, k := range keys {
		parts = append(parts, fmt.Sprintf("%s=%d", k, m[k]))
	}
	return strings.Join(parts, " ")
}

// ---------------------------------------------------------------- validate

func cmdValidate(ctx context.Context, args []string) error {
	fs := flag.NewFlagSet("validate", flag.ExitOnError)
	db := fs.String("db", defaultDB(), "store root")
	baselinePath := fs.String("baseline", "", "baseline allowlist to tolerate (default: none)")
	strict := fs.Bool("strict", false, "fail on ANY finding, ignoring the baseline")
	jsonOut := fs.String("json", "", "also write the full report as JSON to this path")
	crossZone := fs.Bool("cross-zone", true, "run the cross-zone integrity pass (D2)")
	regCorpus := fs.String("registry", "", "also run the artifact type registry gate over this .factory corpus")
	regDir := fs.String("registry-dir", "", "override the embedded registry YAML (for iterating on the standard)")
	_ = fs.Parse(args)

	s, err := Open(ctx, *db, ZoneOpen, false)
	if err != nil {
		return err
	}
	defer s.Close()

	var walled *Store
	if *crossZone {
		// Opening the walled zone is a PRIVILEGED act; this is the one command that
		// does it, and the check reads ids only (see gateCrossZone).
		if w, err := Open(ctx, *db, ZoneWalled, false); err == nil {
			walled = w
			defer w.Close()
		} else {
			fmt.Fprintf(os.Stderr, "note: cross-zone pass skipped: %v\n", err)
		}
	}

	rep, err := Validate(ctx, s, walled)
	if err != nil {
		return err
	}

	// The registry gate is corpus-side: it checks whether artifacts DECLARE themselves
	// correctly, where the gates above check whether the declared graph is CONSISTENT.
	// Its findings join the same report so the one dated baseline covers both — two
	// baselines for one gate would be exactly the drift this project exists to remove.
	var regRep *RegistryReport
	if *regCorpus != "" {
		bundle, err := LoadRegistry(*regDir)
		if err != nil {
			return err
		}
		regRep, err = ValidateRegistry(bundle, *regCorpus)
		if err != nil {
			return err
		}
		rep.Findings = append(rep.Findings, regRep.Findings...)
	}

	var b *Baseline
	if *baselinePath != "" {
		b, err = LoadBaseline(*baselinePath)
		if err != nil {
			return fmt.Errorf("baseline: %w", err)
		}
	}
	d := Compare(rep, b)
	if regRep != nil {
		PrintRegistryReport(os.Stdout, regRep)
	}
	PrintReport(os.Stdout, rep, b, d, *strict)

	if *jsonOut != "" {
		out := map[string]any{
			"metrics":            rep.Metrics,
			"cross_zone_checked": rep.CrossZoneChecked,
			"findings":           rep.Findings,
			"new":                d.New,
			"fixed":              d.Fixed,
			"counts": map[string]int{
				"total": len(rep.Findings), "new": len(d.New),
				"fixed": len(d.Fixed), "kept": len(d.Kept),
			},
			"by_class": ByClass(rep.Findings),
		}
		data, err := json.MarshalIndent(out, "", "  ")
		if err != nil {
			return err
		}
		if err := os.WriteFile(*jsonOut, append(data, '\n'), 0o644); err != nil {
			return err
		}
	}

	// Exit 1 = the gate failed. Exit 2 (elsewhere) = fa itself failed. Never swallow
	// the distinction: one wasted a whole CI debugging session in this spike.
	if *strict && len(rep.Findings) > 0 {
		return exitError{code: 1}
	}
	if len(d.New) > 0 {
		return exitError{code: 1}
	}
	return nil
}

// ---------------------------------------------------------------- baseline

func cmdBaseline(ctx context.Context, args []string) error {
	if len(args) == 0 || args[0] != "write" {
		return fmt.Errorf("usage: fa baseline write [--out <path>] [--db <dir>] [--corpus <path>]")
	}
	fs := flag.NewFlagSet("baseline write", flag.ExitOnError)
	db := fs.String("db", defaultDB(), "store root")
	out := fs.String("out", "baseline.json", "where to write the allowlist")
	corpus := fs.String("corpus", "", "corpus path, recorded for provenance")
	date := fs.String("date", time.Now().UTC().Format("2006-01-02"), "the baseline date")
	regCorpus := fs.String("registry", "", "also baseline the artifact type registry gate over this .factory corpus")
	regDir := fs.String("registry-dir", "", "override the embedded registry YAML")
	_ = fs.Parse(args[1:])

	s, err := Open(ctx, *db, ZoneOpen, false)
	if err != nil {
		return err
	}
	defer s.Close()
	var walled *Store
	if w, err := Open(ctx, *db, ZoneWalled, false); err == nil {
		walled = w
		defer w.Close()
	}
	rep, err := Validate(ctx, s, walled)
	if err != nil {
		return err
	}
	// The baseline MUST be able to cover the registry gate's findings, or the ratchet does
	// not apply to them and `advisory -> warn -> block` has nothing to graduate on. Writing
	// a baseline without --registry while validating WITH it would silently mark every
	// registry finding as new on the next run.
	if *regCorpus != "" {
		bundle, err := LoadRegistry(*regDir)
		if err != nil {
			return err
		}
		regRep, err := ValidateRegistry(bundle, *regCorpus)
		if err != nil {
			return err
		}
		rep.Findings = append(rep.Findings, regRep.Findings...)
	}
	fp, _ := s.Str(ctx, "SELECT fingerprint FROM import_run ORDER BY fingerprint LIMIT 1")

	// Keep any waivers a human already wrote.
	var prev *Baseline
	if p, err := LoadBaseline(*out); err == nil {
		prev = p
	}
	// Record WHICH corpus, not where this machine keeps it: the commit ref is the
	// provenance that matters, and an absolute home path in a committed file is
	// noise that differs on every machine and in CI.
	corpusName := ""
	if *corpus != "" {
		corpusName = filepath.Base(strings.TrimRight(*corpus, string(filepath.Separator)))
	}
	b := NewBaseline(rep, *date, corpusName, gitRef(*corpus), fp, prev)
	if err := b.Save(*out); err != nil {
		return err
	}
	fmt.Printf("wrote %s: %d tolerated finding(s), dated %s, corpus %s\n",
		*out, len(b.Findings), b.Generated, shortRef(b.CorpusRef))
	for _, r := range ByRule(rep.Findings) {
		fmt.Printf("  %5d  %-12s %s\n", r.N, r.Class, r.Rule)
	}
	if prev != nil {
		d := Compare(rep, prev)
		fmt.Printf("  vs previous baseline: new=%d fixed=%d\n", len(d.New), len(d.Fixed))
	}
	return nil
}

// gitRef records WHICH corpus state a baseline was taken from. Best effort: `fa`
// does not require git, so an unavailable ref is recorded as empty rather than
// failing the command.
func gitRef(path string) string {
	if path == "" {
		return ""
	}
	cmd := exec.Command("git", "-C", path, "rev-parse", "HEAD")
	b, err := cmd.Output()
	if err != nil {
		return ""
	}
	return strings.TrimSpace(string(b))
}

// ---------------------------------------------------------------- count

func cmdCount(ctx context.Context, args []string) error {
	fs := flag.NewFlagSet("count", flag.ExitOnError)
	db := fs.String("db", defaultDB(), "store root")
	bySubsystem := fs.Bool("by-subsystem", false, "break BCs down by subsystem")
	_ = fs.Parse(args)

	s, err := Open(ctx, *db, ZoneOpen, false)
	if err != nil {
		return err
	}
	defer s.Close()

	for _, t := range []string{"subsystem", "bc", "vp", "story"} {
		n, err := s.Int(ctx, "SELECT COUNT(*) FROM "+t)
		if err != nil {
			return err
		}
		fmt.Printf("%-10s %d\n", t, n)
	}
	if *bySubsystem {
		fmt.Println("\nby subsystem (claimed vs actual):")
		rows, err := s.Query(ctx, `SELECT s.ss_id, COUNT(b.bc_id) AS actual,
		    (SELECT claimed FROM corpus_assertion a
		     WHERE a.kind='bc_count_ss' AND a.subject=s.ss_id
		     ORDER BY a.source LIMIT 1) AS claimed
		  FROM subsystem s LEFT JOIN bc b ON b.ss_id = s.ss_id
		  GROUP BY s.ss_id ORDER BY s.ss_id`)
		if err != nil {
			return err
		}
		defer rows.Close()
		for rows.Next() {
			var ss string
			var actual int64
			var claimed *int64
			if err := rows.Scan(&ss, &actual, &claimed); err != nil {
				return err
			}
			flag := ""
			if claimed != nil && *claimed != actual {
				flag = fmt.Sprintf("   <-- markdown states %d", *claimed)
			}
			fmt.Printf("  %-7s %5d%s\n", ss, actual, flag)
		}
		return rows.Err()
	}
	return nil
}

// ---------------------------------------------------------------- doctor

func cmdDoctor(ctx context.Context, args []string) error {
	fs := flag.NewFlagSet("doctor", flag.ExitOnError)
	db := fs.String("db", defaultDB(), "store root")
	_ = fs.Parse(args)

	allOK := true
	for _, zone := range []string{ZoneOpen, ZoneWalled} {
		s, err := Open(ctx, *db, zone, false)
		if err != nil {
			fmt.Printf("zone %s\n  FAIL  open  %v\n", zone, err)
			allOK = false
			continue
		}
		if ok := PrintChecks(os.Stdout, zone, Doctor(ctx, s)); !ok {
			allOK = false
		}
		s.Close()
	}
	if !allOK {
		return exitError{code: 1, msg: "doctor: at least one fatal check failed"}
	}
	return nil
}

// ---------------------------------------------------------------- aggregate

func cmdAggregate(ctx context.Context, args []string) error {
	if len(args) == 0 || args[0] != "plan" {
		// Being explicit beats a stub that looks implemented. The quarantine POLICY
		// ships now because measurement made it mandatory; the fetch/merge/push
		// plumbing needs the remote, which phase 1 deliberately does not have.
		return fmt.Errorf("`fa aggregate` needs a remote, which phase 1 excludes (DECISIONS D3).\n" +
			"The quarantine policy it will use IS implemented and tested — inspect it with:\n" +
			"  fa aggregate plan --state <state.json> --refs <ref,ref,...> --run <n>")
	}
	fs := flag.NewFlagSet("aggregate plan", flag.ExitOnError)
	statePath := fs.String("state", "", "JSON file of per-ref attempt state")
	refs := fs.String("refs", "", "comma-separated staging refs present on the remote")
	run := fs.Int("run", 1, "current aggregator run number")
	maxAttempts := fs.Int("max-attempts", DefaultQuarantineConfig().MaxAttempts, "attempts before quarantine")
	_ = fs.Parse(args[1:])

	state := map[string]RefState{}
	if *statePath != "" {
		data, err := os.ReadFile(*statePath)
		if err != nil {
			return err
		}
		var list []RefState
		if err := json.Unmarshal(data, &list); err != nil {
			return fmt.Errorf("%s: %w", *statePath, err)
		}
		for _, st := range list {
			state[st.Ref] = st
		}
	}
	var present []string
	for _, r := range strings.Split(*refs, ",") {
		if r = strings.TrimSpace(r); r != "" {
			present = append(present, r)
		}
	}
	cfg := DefaultQuarantineConfig()
	cfg.MaxAttempts = *maxAttempts
	for _, d := range PlanAggregate(present, state, *run, cfg) {
		line := fmt.Sprintf("%-11s %s  (%s)", d.Action, d.Ref, d.Reason)
		if d.Action == ActionQuarantine {
			line += "\n            -> " + QuarantineTarget(d.Ref)
		}
		fmt.Println(line)
	}
	return nil
}

// ---------------------------------------------------------------- misc

func expandHome(p string) string {
	if strings.HasPrefix(p, "~/") {
		if h, err := os.UserHomeDir(); err == nil {
			return filepath.Join(h, p[2:])
		}
	}
	return p
}

func sortStrings(s []string) {
	for i := 1; i < len(s); i++ {
		for j := i; j > 0 && s[j] < s[j-1]; j-- {
			s[j], s[j-1] = s[j-1], s[j]
		}
	}
}
