---
title: FA-V1-VALIDATION-PRISM-SESSION — would datum v1 have prevented the 2026-08-02 prism findings?
date: 2026-08-02
purpose: test the v1 design's central claim against an INDEPENDENT register of real findings, including where datum does nothing
source: /Users/jmagady/Dev/scrap/prism-session-findings-2026-08-02.md (21 entries, prism §Authority backfill rounds 4-5, decisions D-2090/D-2091)
method: classify every entry as PREVENTED (structurally impossible) / DETECTED (mechanically, continuously) / MITIGATED / OUT OF SCOPE / NOT A DEFECT
status: assessment complete
---

# Validation: the prism session of 2026-08-02

The v1 design claims most of the factory's defect classes become *unrepresentable* rather than
detected. That claim was made against defects **I** found, which is the weakest possible test. This
register is independent — a different project, a different session, findings surfaced by an
orchestrator doing real work — so it is a fair test.

**Result: 11 of 21 prevented outright, 5 detected mechanically where they were found by hand, 1
partially mitigated, 3 out of scope, 1 not a defect.**

| verdict | n | entries |
|---|---|---|
| **PREVENTED** — structurally impossible | **11** | B · C · G · PROCESS-GAP · R-1 · R-2 · R-3 · R-4 · S-2 · S-3 · E-4 |
| **DETECTED** — continuous query vs a manual catch | 5 | A · D · E · F · R-5 |
| **MITIGATED** — reduced, not eliminated | 1 | S-1 |
| **OUT OF SCOPE** — git/CI/worktree, not artifacts | 3 | E-1 · E-2 · E-3 |
| **NOT A DEFECT** — a real obligation, better tracked | 1 | E-5 |

---

## The single strongest result: the PROCESS-GAP disappears rather than being caught

**PROCESS-GAP — dual-commit TD-VSDD-053 breach, third recurrence.** Three bursts produced two commits
where the protocol mandates one. The register's own root cause:

> "The detector enforces a naming convention, not a commit count. A green detector result is NOT
> evidence of TD-VSDD-053 compliance."

And its remediation is a new story (`S-MAINT-BURST-COMMIT-COUNT-GATE-001`), itself blocked on an open
architecture question — i.e. **a better detector for a protocol violation**.

Under v1 there is nothing to detect, because **the protocol has no reason to exist.** The
single-commit-per-burst rule exists only because a commit's own SHA must be transcribed into content
that lives in the same commit — which is why the corpus shows a three-commit `SHA-patch` / `finalize`
chain. **Invariant 23** assigns identity in the store and forbids it from appearing in content, so
there is no second commit to make. The requirement, the detector, its three escapes, the remediating
story and the blocking architecture question all evaporate together.

This is the difference between fixing a bug and deleting its category. It is also the third
independent confirmation of that invariant's value: TD-VSDD-053, TD-VSDD-044 and now this.

The register's transferable lesson — **"probe-passes are not gate-fires"** — is invariant 22 stated in
their words.

---

## PREVENTED (11)

| # | finding | what makes it impossible |
|---|---|---|
| **B** | ADR status vocabulary inconsistent: `ACCEPTED`, `PROPOSED`, `COMMITTED`, lowercase `accepted`, "no canonical set is enforced" | **Invariant 20** — closed enum validated at write time. Identical class to the 7 `document_type` spellings and the 23 `verdict` tokens. The register's own concern is that "tooling that keys on the status field will produce incorrect results" — which is exactly why the enum binds at write, not at read. |
| **C** | Stories missing `## Changelog`, and the repair cost is *accelerating* (2 in round 3, 5 in round 4) | `sections` + `section_policy` are declared per type and validated at write time; for derived shapes the render generates them. The register asks for "a structural gate at story-authoring time" — that is precisely what write-time section validation is. |
| **G** | CLAUDE.md documents `Stage 1`/`Stage 2` detector arms that **do not exist** in the hook | Gate documentation becomes a **projection of the gate registry** (L4). You cannot document an arm that is not in the registry, because the document is derived from it. Same class as FACTORY.md citing an `openclaw.json` that does not exist. |
| **PROCESS-GAP** | Third dual-commit breach | See above — invariant 23 removes the requirement. |
| **R-1** | 14 phantom story IDs hardcoded in a resume snapshot; `S-3.8.*` does not exist at all | **Invariant 17** — nothing stored that is derivable. A story list is a *query*, never a stored list. The register's own going-forward rule is "never carry a story-ID list forward in a resume snapshot", which is invariant 17 restated. Same class as the 37 phantom STORY-INDEX rows. |
| **R-2** | Coverage tracked against a denominator of 237; disk truth is 264 | Counts are projections with no stored copy to go stale. Same class as the six BC totals. |
| **R-3** | Round-vs-batch unit conflation producing `29 × 24 = 696` against a 264-file corpus | Coverage is computed from rows, so there is no hand-derived ratio to get wrong — and an impossible magnitude is caught by the vacuity guard rather than by a reader noticing. |
| **R-4** | `FINDING-D` reused for two different findings, so a real spec correction "appears nowhere in STATE.md" | Findings are rows with **datum-minted ids** (F12). An id cannot be reused, and a correction cannot exist without a record because **the record *is* the write**. |
| **S-2** | A shell variable failed to expand, so a compliance grep received empty input and returned a **vacuous clean verdict** | **Mandatory vacuity guard** plus `datum gate exec` as the sole evidence producer. The register's lesson — "an empty grep result must be distinguished from a grep that never ran" — is the guard's exact specification. Its secondary issue (glob `S-6.0*` silently excluding `S-6.10`) is the same shape as `datum`'s own instance-9 bug, and under v1 sets are queries, not globs. |
| **S-3** | `records-lint` exits 0 while check L11 is `-proposed` and **not deployed**, so green carries no evidentiary weight | **Unevaluable = error = block. No fail-open.** A non-deployed criterion cannot report green; it blocks, or it is `manual: true` with a named owner and an attestation. |
| **E-4** | Cross-record SHA verification **skipped** because `python3`/`pyyaml` were unavailable | Prevented twice: `datum` is a single static Go binary with no external runtime dependency to be missing, *and* a skip is not a pass. Same class as `validate-wave-gate-prerequisite.sh` exiting 0 without `jq`. |

**Three of these — S-2, S-3, E-4 — are the same failure wearing three costumes: a check reported green
without having run.** That is one design rule (`unevaluable = block`, plus a vacuity guard, plus no
external deps), and it closes all three.

---

## DETECTED — mechanical and continuous, where the register caught them by hand (5)

These are not eliminated, but the difference matters: each was found because an orchestrator manually
read frontmatter or ran a cross-check. Under v1 each is a standing query that cannot be skipped.

- **A — six `PROPOSED` ADRs cited as authoritative by stories.** `story → adr` is a typed edge and
  `status` is a lifecycle field, so "no story cites an unratified ADR as authority" is a gate query —
  and it sits in the **65% of the 278 criteria that already have a machine shape**. Found here only
  because "the orchestrator read ADR frontmatter directly rather than trusting writer reports." The
  register's per-tier nuance (DTU stories consume an ADR as a fidelity target, not an implementation
  authority) is representable as a typed *link kind*, so the query can be as precise as the
  adjudication.
- **D — S-6.10 cited `COMP-DTU-005` where its own component is `COMP-DTU-004`.** The reference
  *resolves*, so reference-integrity alone would pass it. But once both facts are rows — the cited
  component and the story's own component — the disagreement is a **cross-field consistency query**.
  Worth being precise about the limit: this instance is catchable because both facts are in the store;
  the general class (semantically wrong yet valid) is the residue §1 of the spine measured at **26.3%
  of class C**.
- **E — POL-39 version pins in live normative text.** `datum` already extracts version cites (2,197 of
  them) and judges them by `pin_policy`. The register even describes the sites as "grandfathered
  under the L9 ratchet" — a baseline/ratchet (F15) they are hand-rolling.
- **F — stories citing components recorded as *planned, not on disk*.** The reference resolves to a
  record whose lifecycle says planned, so this is a lifecycle query, not a dangling reference. Note
  what the register is doing: registering the finding "pre-emptively so a later sweep does not mint
  this as a phantom-anchor defect" — i.e. **manually preventing a future false positive.** `datum`'s
  resolved / dangling / unresolvable distinction does that structurally, which is the same discipline
  the section-ref work earned the hard way.
- **R-5 — a process-gap marked `CLOSED` on the strength of one compliant burst.** `datum` cannot stop
  someone asserting closure, but it can make the assertion fail: **a finding may not reach `resolved`
  while its remediating story is `draft`** is a cross-reference rule, and closure requires evidence
  under invariant 22. The register notes the saving grace was that "the story anchor is named in the
  record" — under v1 that anchor is a typed link, so the rule has something to check.

---

## MITIGATED (1)

**S-1 — a scope claim generalized from one batch and falsified by the next.** `datum` cannot stop an agent
reasoning badly in prose. But **invariant 19** bites here more than I expected: if "exposure is
confined to the Wave-4 ops cluster" has to be expressed as a *scoped query* rather than a sentence,
the predicate must name its denominator — and a query over all stories would have included batch 14.
The register's own root cause is "a sampling artifact, not a structural boundary," which is the same
defect this repo has recorded twice under *never infer a consequence from a structural fact*. Reduced,
not eliminated.

---

## OUT OF SCOPE (3) — and this is a real boundary, not a gap to paper over

**E-1, E-2, E-3** are git and CI risks: two local-only worktrees holding unmerged, unpushed work (one
dirty), and a `stash@{0}` that would deadlock every PR against 24 required checks if applied with any
check-name shift.

**`datum` is the artifact substrate. It is not a replacement for git on source code**, and it should not
pretend to be. `datum fsck` / `datum doctor` can *surface* unpushed worktrees and diverged branches as
health signals — worth adding to F20's scope — but the underlying data-loss risk is git-level and stays
git-level. Any design that claimed otherwise would be overreaching.

---

## NOT A DEFECT (1)

**E-5 — S-5.11 cannot reach `status: ready` until the PO amends `BC-2.16.007` or splits a new BC.**
This is a correctly-identified blocking obligation, not a failure. `datum` improves the *tracking* — a
typed obligation with an owner and an expiry rather than a prose note, which is the same
`deferred`-abolition decision L5–L6 made — but the work itself is real and human.

---

## What this validation does NOT show, stated plainly

1. **`datum` introduces a new risk class of its own, and it is already proven.** Instance **nine** of
   silent input loss is live in `datum`'s own importer (`reVPFile` is case-sensitive; prism names all 80
   VPs `vp-001-*.md`; prism's entire L4 layer imports as **zero rows** with no error). The prism
   register has no equivalent — 3,085 independently readable markdown files fail *loudly* and
   partially, whereas a store fails *quietly* and totally. The migration's conservation gate exists
   for precisely this reason, and it is the most important gate in the plan.
2. **A single store is a single point of failure** where a file tree is not. That is what D-B's
   committed render and invariant 15 are for, and it is why round-trip is a blocking gate rather than
   a nice-to-have.
3. **This is one session on one project.** 21 entries is a sample, and the prevented share (11) is
   concentrated in the classes v1 was explicitly designed against — so it confirms the design does what
   it says, not that the design is complete. A different session would weight the categories
   differently.
4. **Nothing here tests the engine.** Every entry is an artifact- or gate-level finding. The L6
   claims — workflow-as-data, the approval frontier, the scheduler — are untested by this register.

## The honest summary

**The design's central claim survives an independent test.** 16 of 21 entries are addressed, 11 of them
by making the defect unrepresentable rather than by detecting it — and the register's two most-repeated
themes are exactly the two rules the design already leans on hardest: *a green check that never ran is
not evidence* (invariant 22 + vacuity guard, three entries) and *do not store what you can derive*
(invariant 17, three entries).

The most valuable single confirmation is the PROCESS-GAP: a third recurrence of a breach, with a story
and an open architecture question queued to build a better detector, where the correct answer is that
**the protocol it enforces should not exist.**
