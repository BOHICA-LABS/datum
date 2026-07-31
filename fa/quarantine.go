package main

// The staging-ref quarantine policy for `fa aggregate`.
//
// WHY THIS EXISTS, measured (CI-AGGREGATOR.md pass 12b): when a writer's staging
// ref conflicts, the aggregator isolates it and RETAINS the ref — which is right.
// But it then re-fetches and re-merges that same ref on EVERY subsequent run: 17 s
// on the first wasted attempt and ~8 s on each one after, forever, with nothing
// new to do. At 20 stuck refs that dominates the job and the backlog only grows.
// Retention is correct; unbounded RE-ATTEMPT is the defect.
//
// So a stuck ref is attempted a bounded number of times, skipped in between, and
// finally MOVED to refs/dolt/quarantine/* — never deleted, because a quarantined
// ref still holds a writer's work.
//
// NOTE ON BACKOFF, so nobody reads this as contradicting SCALE.md: that measurement
// found backoff HARMFUL for the *push race* (159 -> 185 -> 193 attempts), because
// sleeping lets more branch pointers move while you wait. This is a different
// thing: it is spacing out doomed RE-MERGES of a ref that has already failed, where
// the work saved is real and the delay costs nothing anyone is waiting on.
//
// The policy is deliberately PURE and clock-free — decisions come from attempt
// counts and run numbers, never from time.Now() — so it is fully testable now,
// while the fetch/merge/push plumbing lands with the remote in phase 2.

import (
	"fmt"
	"sort"
	"strings"
)

const (
	StagingPrefix    = "refs/dolt/staging/"
	QuarantinePrefix = "refs/dolt/quarantine/"
)

type Action string

const (
	ActionMerge      Action = "merge"      // fetch and try to merge this ref now
	ActionSkip       Action = "skip"       // backing off: a recent attempt failed
	ActionQuarantine Action = "quarantine" // stop attempting; move it aside and report
)

// FailureKind separates a failure that MIGHT succeed later from one that never can.
type FailureKind string

const (
	FailureTransient FailureKind = "transient" // e.g. a cell conflict: the target moves, this may merge later
	FailurePermanent FailureKind = "permanent" // e.g. unrelated lineage: it can NEVER merge
	FailureNone      FailureKind = "none"
)

// RefState is the aggregator's memory of one staging ref. Persisted by the
// aggregator (single writer, serialised by the CI `concurrency:` group), so a
// mutable cell is safe here in a way it would not be for a fleet of writers.
type RefState struct {
	Ref         string `json:"ref"`
	Attempts    int    `json:"attempts"`
	LastRun     int    `json:"last_run"`     // run number of the last attempt, 0 = never
	LastFailure string `json:"last_failure"` // classified kind, "" if never failed
	LastError   string `json:"last_error,omitempty"`
}

type QuarantineConfig struct {
	// MaxAttempts is how many merge attempts a ref gets before quarantine.
	MaxAttempts int
	// BackoffBase spaces retries by run count: a ref that has failed n times is
	// skipped until BackoffBase*2^(n-1) runs have passed. Run-counted, not timed,
	// so the policy is deterministic.
	BackoffBase int
}

func DefaultQuarantineConfig() QuarantineConfig {
	return QuarantineConfig{MaxAttempts: 3, BackoffBase: 1}
}

type Decision struct {
	Ref    string
	Action Action
	Reason string
}

// ClassifyMergeFailure turns a merge error into a policy input.
//
// `no common ancestor` is PERMANENT and gets no retries: invariant 14 — a writer
// that is not a CLONE of the artifact branch is an unrelated lineage and can never
// be merged, only replayed. Retrying it three times just wastes three runs.
func ClassifyMergeFailure(errText string) FailureKind {
	if strings.TrimSpace(errText) == "" {
		return FailureNone
	}
	m := strings.ToLower(errText)
	for _, permanent := range []string{
		"no common ancestor",
		"unrelated histories",
		"refusing to merge unrelated",
	} {
		if strings.Contains(m, permanent) {
			return FailurePermanent
		}
	}
	return FailureTransient
}

// backoffRuns is how many runs a ref with n failures must sit out.
func backoffRuns(n int, cfg QuarantineConfig) int {
	if n <= 0 {
		return 0
	}
	base := cfg.BackoffBase
	if base < 1 {
		base = 1
	}
	runs := base
	for i := 1; i < n; i++ {
		runs *= 2
		if runs > 64 { // cap: past this the ref is heading for quarantine anyway
			return 64
		}
	}
	return runs
}

// PlanAggregate decides what to do with each known staging ref this run.
//
// `present` is the set of refs that actually exist on the remote right now; state
// for a ref that has since been published (and deleted) is simply dropped.
func PlanAggregate(present []string, state map[string]RefState, run int, cfg QuarantineConfig) []Decision {
	if cfg.MaxAttempts < 1 {
		cfg = DefaultQuarantineConfig()
	}
	refs := append([]string(nil), present...)
	sort.Strings(refs)

	var out []Decision
	for _, ref := range refs {
		st, known := state[ref]
		switch {
		case !known || st.Attempts == 0:
			out = append(out, Decision{ref, ActionMerge, "first attempt"})

		case FailureKind(st.LastFailure) == FailurePermanent:
			out = append(out, Decision{ref, ActionQuarantine,
				"unmergeable lineage (invariant 14): " + oneLine(st.LastError)})

		case st.Attempts >= cfg.MaxAttempts:
			out = append(out, Decision{ref, ActionQuarantine,
				fmt.Sprintf("%d failed attempts (max %d): %s", st.Attempts, cfg.MaxAttempts, oneLine(st.LastError))})

		default:
			if wait := backoffRuns(st.Attempts, cfg); run-st.LastRun < wait {
				out = append(out, Decision{ref, ActionSkip,
					fmt.Sprintf("backing off after %d failure(s): %d of %d run(s) elapsed",
						st.Attempts, run-st.LastRun, wait)})
			} else {
				out = append(out, Decision{ref, ActionMerge,
					fmt.Sprintf("retry %d of %d", st.Attempts+1, cfg.MaxAttempts)})
			}
		}
	}
	return out
}

// RecordFailure advances a ref's state after a failed merge.
func RecordFailure(st RefState, ref string, run int, errText string) RefState {
	st.Ref = ref
	st.Attempts++
	st.LastRun = run
	st.LastFailure = string(ClassifyMergeFailure(errText))
	st.LastError = oneLine(errText)
	return st
}

// QuarantineTarget is where a stuck ref is moved to. It keeps the writer's path so
// the owner of the work is still identifiable, because a quarantined ref must be
// recoverable — the point is to stop RE-ATTEMPTING it, not to lose it.
func QuarantineTarget(ref string) string {
	name := strings.TrimPrefix(ref, StagingPrefix)
	if name == ref { // not a staging ref: keep the tail only
		if i := strings.LastIndex(ref, "/"); i >= 0 {
			name = ref[i+1:]
		}
	}
	return QuarantinePrefix + name
}
