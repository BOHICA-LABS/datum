package main

import "testing"

func TestClassifyMergeFailure(t *testing.T) {
	cases := map[string]FailureKind{
		"":                              FailureNone,
		"conflict in table bc, 3 cells": FailureTransient,
		"merge aborted: no common ancestor found":      FailurePermanent,
		"fatal: refusing to merge unrelated histories": FailurePermanent,
	}
	for in, want := range cases {
		if got := ClassifyMergeFailure(in); got != want {
			t.Errorf("ClassifyMergeFailure(%q) = %s, want %s", in, got, want)
		}
	}
}

// A ref nobody has tried yet is merged immediately.
func TestPlanFirstAttempt(t *testing.T) {
	got := PlanAggregate([]string{StagingPrefix + "w1/a"}, nil, 1, DefaultQuarantineConfig())
	if len(got) != 1 || got[0].Action != ActionMerge {
		t.Fatalf("got %+v", got)
	}
}

// THE MEASURED REQUIREMENT (CI-AGGREGATOR pass 12b): a ref that keeps conflicting
// must stop being re-merged on every run. Today it costs 17 s then ~8 s forever.
func TestPlanQuarantinesAfterMaxAttempts(t *testing.T) {
	cfg := DefaultQuarantineConfig() // MaxAttempts 3
	ref := StagingPrefix + "w1/a"
	st := RefState{}
	run := 1
	seenMerges := 0
	for i := 0; i < 40; i++ {
		d := PlanAggregate([]string{ref}, map[string]RefState{ref: st}, run, cfg)[0]
		switch d.Action {
		case ActionMerge:
			seenMerges++
			st = RecordFailure(st, ref, run, "conflict in table bc")
		case ActionSkip:
			// backing off, no work done
		case ActionQuarantine:
			if seenMerges != cfg.MaxAttempts {
				t.Fatalf("quarantined after %d merge attempts, want %d", seenMerges, cfg.MaxAttempts)
			}
			if want := QuarantinePrefix + "w1/a"; QuarantineTarget(ref) != want {
				t.Errorf("QuarantineTarget = %q, want %q", QuarantineTarget(ref), want)
			}
			return
		}
		run++
	}
	t.Fatalf("ref was never quarantined after 40 runs; it would be re-merged forever (%d attempts)", seenMerges)
}

// Backoff must actually skip runs — otherwise the bounded attempt count is spent
// in three consecutive runs and the "wait for the target to move" case is lost.
func TestPlanBacksOffBetweenAttempts(t *testing.T) {
	cfg := DefaultQuarantineConfig()
	ref := StagingPrefix + "w1/a"
	st := RecordFailure(RefState{}, ref, 5, "conflict")
	st = RecordFailure(st, ref, 6, "conflict") // 2 failures, backoff = 2 runs
	if d := PlanAggregate([]string{ref}, map[string]RefState{ref: st}, 7, cfg)[0]; d.Action != ActionSkip {
		t.Errorf("run 7 (1 run after failure): got %s, want skip — %s", d.Action, d.Reason)
	}
	if d := PlanAggregate([]string{ref}, map[string]RefState{ref: st}, 8, cfg)[0]; d.Action != ActionMerge {
		t.Errorf("run 8 (2 runs after failure): got %s, want merge — %s", d.Action, d.Reason)
	}
}

// Invariant 14: an unrelated lineage can NEVER be merged, only replayed. Spending
// three attempts on it wastes three runs to learn what the first one proved.
func TestPlanQuarantinesUnmergeableLineageImmediately(t *testing.T) {
	ref := StagingPrefix + "w9/z"
	st := RecordFailure(RefState{}, ref, 1, "merge failed: no common ancestor")
	if st.Attempts != 1 {
		t.Fatalf("attempts = %d", st.Attempts)
	}
	d := PlanAggregate([]string{ref}, map[string]RefState{ref: st}, 2, DefaultQuarantineConfig())[0]
	if d.Action != ActionQuarantine {
		t.Fatalf("got %s (%s), want quarantine on the first permanent failure", d.Action, d.Reason)
	}
}

// A published ref is deleted from the remote; leftover state must not resurrect it.
func TestPlanIgnoresStateForAbsentRefs(t *testing.T) {
	gone := StagingPrefix + "w1/old"
	state := map[string]RefState{gone: RecordFailure(RefState{}, gone, 1, "conflict")}
	if got := PlanAggregate(nil, state, 9, DefaultQuarantineConfig()); len(got) != 0 {
		t.Fatalf("got %+v, want no decisions", got)
	}
}

func TestPlanIsDeterministicallyOrdered(t *testing.T) {
	refs := []string{StagingPrefix + "c", StagingPrefix + "a", StagingPrefix + "b"}
	got := PlanAggregate(refs, nil, 1, DefaultQuarantineConfig())
	want := []string{StagingPrefix + "a", StagingPrefix + "b", StagingPrefix + "c"}
	for i := range want {
		if got[i].Ref != want[i] {
			t.Fatalf("decision %d = %s, want %s", i, got[i].Ref, want[i])
		}
	}
}

func TestBackoffIsCapped(t *testing.T) {
	cfg := DefaultQuarantineConfig()
	if got := backoffRuns(30, cfg); got != 64 {
		t.Errorf("backoffRuns(30) = %d, want the 64-run cap", got)
	}
	if got := backoffRuns(0, cfg); got != 0 {
		t.Errorf("backoffRuns(0) = %d, want 0", got)
	}
}
