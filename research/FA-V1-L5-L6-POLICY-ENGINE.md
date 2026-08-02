---
title: FA-V1-L5-L6-POLICY-ENGINE — gates, convergence, and the pipeline engine as data
date: 2026-08-02
purpose: specify L5 (policy — gates as queries, findings, convergence, baselines, attestation) and L6 (engine — workflow-as-data, frontier, scheduler, PR/CI join, cost, modes)
status: DESIGN — nothing implemented (design-only by direction)
spine: research/FA-V1-DESIGN.md (8 settled decisions, invariants 1–23 BINDING, §7 keep-list PRESERVED)
builds_on: research/FINDINGS-AS-ROWS.md · fa/findings.go · fa/validate.go · fa/baseline.go
corpus_pin: vsdd-factory .factory @ 0aaba144 · plugin tree @ develop (rc.20 lineage) · rehydrate-wave read from ~/.claude/plugins/cache/claude-mp/vsdd-factory/1.0.0-rc.23
---

# `fa` v1 — L5 POLICY and L6 ENGINE

The spine's §1 argument is that most defects become *unrepresentable* under V-A + V-C. L5 and L6
are where that argument runs out. A gate verdict, a convergence declaration, an approval and a
budget decision are all **judgments about a moment in time**, and no schema makes a wrong judgment
impossible. What a schema *can* do is make an *unevidenced* judgment impossible, and make the same
judgment impossible to state twice differently. That is the entire design brief for these two
layers.

Everything below is measured. Where a number differs from the review's, mine is stated and the
delta is called out.

---

## 0. The census that shapes both layers

One measurement, taken over all 16 Lobster workflow files
(`~/Dev/vsdd-factory/plugins/vsdd-factory/workflows/*.lobster` + `phases/*.lobster`):

| | measured |
|---|---|
| workflow steps | **546** |
| step **types** in use | **10 spellings** — `agent` 280 · `skill` 130 · `gate` 38 · `human-approval` 37 · `sub-workflow` 25 · `loop` 24 · `parallel-foreach` **8** · `parallel` 2 · `compound` 2 |
| gates | **38** |
| gate **criteria** | **278** |
| criteria with an evaluator | **0** |
| `human-approval` nodes | **37** (8 distinct timeout values: 1h/2h/4h/8h/12h/24h/48h/72h) |
| `loop` steps | **24** — 21 declare `max_iterations`, 20 declare `exit_condition`, **3 declare neither** |
| distinct `exit_condition` expressions | **7**; 9 of 20 are the single string `adversary.verdict == 'CONVERGENCE_REACHED'` |
| `exit_condition`s referencing `passes_clean` or a 3-pass streak | **0** |
| conditional steps | **166** (30.4%) |
| **`depends_on` edges pointing at a conditional step** | **140** |
| `context.exclude` wall blocks in `greenfield.lobster` | 11 |
| `model_tier:` uses | 24 (`adversary` 13 · `review` 10 · `builder` 1), **resolver: none** |

Two numbers here are new and load-bearing.

**`parallel-foreach` is a seventh step type.** The review's list names six
(`gate`/`loop`/`human-approval`/`sub-workflow`/`parallel`/`compound`); the corpus also uses
`parallel-foreach` 8 times and it is semantically distinct — it iterates a set the workflow never
declares. Any "all six step types first-class" design would have shipped a hole. L6 models **ten
spellings resolving to seven kinds**.

**140 dependency edges point at a conditional step.** The review found two of these by hand
(`wave-gate` → `wave-ui-quality-gate`, `phase-7-convergence` → `phase-6-ui-fix-delivery`). There
are 140, distributed: `feature.lobster` 54 of 121 steps · `greenfield.lobster` 28 of 116 ·
`discovery.lobster` 14 of 29 · `brownfield.lobster` 11 of 26 · `code-delivery.lobster` 8 ·
`planning.lobster` 8 · `maintenance.lobster` 7 · `multi-repo.lobster` 7 · `phases/*` 3. Skip
propagation is not an edge case to patch; it is **26% of the entire dependency graph**, and its
semantics are defined nowhere.

A third instance the review did not catch, in the same class as its two:
`greenfield.lobster:1379` — `session-review` `depends_on: [post-feature-validation, release]`, and
`post-feature-validation:1364` is gated on `config.post_feature_validation.enabled == true`, which
is **off by default** (`skills/post-feature-validation/SKILL.md:199` "Only runs when
post_feature_validation.enabled == true"; nothing in `.factory/` sets it). So in the default
configuration the entire post-pipeline tail — `session-review:1379`,
`session-review-approval:1386`, `process-review-decisions:1399` — is unreachable. The pipeline
cannot reach `COMPLETE`.

And the criteria are not as prose-bound as they look. Classifying all 278 by shape:

| shape | n | becomes |
|---|---|---|
| verdict / status reference (`X: CONVERGED`, `PASS`) | 56 | a join to another `criterion_result` row |
| existence (`X exists`, `*.md produced`) | 36 | an artifact-row query — **never a filesystem stat** |
| coverage (`Every X … at least one Y`) | 34 | anti-join with a declared scope predicate |
| absence (`no`, `zero`, `acyclic`) | 29 | `NOT EXISTS` + non-emptiness guard |
| threshold (`>= N`, `< N%`, `score`) | 25 | numeric comparison with a NULL rule |
| conditional (`If X: …`) | 2 | a criterion with `applies_when` |
| prose | 96 | restated into one of the above, or `manual: true` + named owner |

**182 of 278 (65%) already have a machine shape.** So the gate registry needs exactly five
predicate kinds, one conditional modifier, and one honest escape hatch. That is the design.

---

## 1. L5 POLICY

### 1.1 Evidence is a tuple `fa` produced, or it does not exist

The corpus's dominant evidence form is a shell transcript pasted into a markdown body that asserts
its own output. `POLICY 15` (`.factory/policies.yaml:258-271`,
`ll_n_verbatim_stdout_discipline`, severity HIGH, `lint_hook: null`) *mandates* it: "captured
`file:line:` stdout verbatim, OR sentinel `(zero output)`". In practice a burst log reads
`$ grep -c … / 18 / PASS` and nothing can tell whether the command ran.

`POLICY 5` is the six-level cure chain built on top of that hole. Its own `last_amended` field
records the recursion: `v1.3 → v1.3.1 → v1.3.3 → v1.3.4 → v1.3.5 → v1.3.6`, and v1.3.5 Part B
finally states the actual requirement — "adversary fresh-context replay against the SAME SHA
yields IDENTICAL stdout". `lint_hook: null`.

**The recursion has a single root cause: reproducibility-at-a-named-SHA is a property only the
executor can hold.** An agent transcribing its own output cannot establish it, no matter how many
sub-clauses are added. Six levels of policy are trying to reconstruct, from the artifact, a fact
that was destroyed when the executor was not the recorder.

So:

```
L5-A  An evidence record is created ONLY by `fa` executing something.
      There is no API, flag, file format or import path that accepts evidence bytes
      from a caller. `fa gate record --evidence-text` does not exist and will not.
```

```sql
CREATE TABLE evidence (
  project        VARCHAR(64)  NOT NULL,
  evidence_id    VARCHAR(32)  NOT NULL,   -- store-minted (invariant 23)
  kind           ENUM('query','command','attestation') NOT NULL,
  -- what was run
  spec           TEXT         NOT NULL,   -- SQL text, or argv JSON array
  cwd            VARCHAR(512) NULL,
  env_digest     CHAR(64)     NULL,       -- sha256 over the declared env allowlist
  -- what came back
  exit_code      INT          NULL,       -- NULL for kind='query'
  stdout_sha256  CHAR(64)     NULL,
  stdout_bytes   LONGTEXT     NULL,       -- retained per policy; see OQ-9
  stderr_sha256  CHAR(64)     NULL,
  row_count      BIGINT       NULL,       -- kind='query'
  result_digest  CHAR(64)     NULL,       -- kind='query': sha256 over the canonicalised result set
  -- when, against what, by whom
  store_version  VARCHAR(64)  NOT NULL,   -- read by fa, never typed
  repo_sha       CHAR(40)     NULL,       -- read by fa from the git object db
  produced_by    VARCHAR(64)  NOT NULL,   -- role token (F16), not a self-declared name
  produced_at    DATETIME(3)  NOT NULL,
  duration_ms    INT          NOT NULL,
  volatile       TINYINT      NOT NULL DEFAULT 0,
  replay_of      VARCHAR(32)  NULL,       -- append-only replay chain
  PRIMARY KEY (project, evidence_id),
  KEY idx_ev_digest (project, kind, result_digest)
);
```

`fa gate exec` is the only producer:

```
fa gate exec --gate phase-2 --subject cycle-15 [--criterion C-08] [--dry-run]
```

1. Resolves the gate from `gate_def` and every `criterion_def` whose `applies_when` evaluates TRUE
   for the run's facts (§2.2).
2. For `kind='query'`: runs the criterion's SQL **inside one read transaction pinned to a single
   `store_version`** (invariant 6's boundary), canonicalises the result set (column order, row
   order, NULL rendering, numeric formatting all declared), digests it, records `row_count` and
   the first N witness rows.
3. For `kind='command'`: resolves the argv from a **declared command registry** — an allowlisted
   `(command_id, argv template, permitted arg types, working zone)`. An agent supplies argument
   *values*, never an argv. Forks, captures stdout/stderr/exit, hashes, reads `repo_sha` from the
   git object database itself.
4. Writes one `criterion_result` row per criterion, each pointing at exactly one `evidence_id`.
5. Writes one `gate_run` row whose `verdict` is **derived at print time from the criterion rows**
   and never pre-written — the rule `fa/baseline.go:160-162` already states and enforces
   ("a report that states a conclusion its own numbers contradict is worse than no report").

Three properties fall out that the corpus has been trying to legislate:

- **Replay is a first-class operation.** `fa evidence replay <id>` re-executes the identical spec,
  records a new evidence row with `replay_of` set, and reports `identical | divergent |
  unreproducible`. POLICY 5 v1.3.5 Part B becomes one command. For `volatile: true` criteria
  replay compares the *verdict*, not the bytes, and the divergence is recorded rather than argued.
- **Staleness is arithmetic.** A `criterion_result` whose evidence's `store_version` predates the
  version the gate is being asserted against is `stale_evidence`, and `stale_evidence` is not
  `pass`. This retires the whole self-referential-SHA class (spine §1) at the gate layer as well
  as the artifact layer.
- **Attribution is total.** `produced_by` is the verified role token from F16, so the eight
  non-agent `producer:` identities the review found cannot recur.

**`manual: true` and invariant 22.** A criterion or policy with no machine predicate is not exempt
from invariant 22 — it is evidenced *differently*. `fa gate attest --criterion C-19 --owner
<role>` writes an `evidence` row with `kind='attestation'`: the attesting role, the moment, and
the `store_version` attested against, all read by `fa`. The *content* of the judgment is human;
the *record* is machine-produced and typed, so `SELECT … WHERE kind='attestation'` separates
attested criteria from executed ones in every report. Invariant 22 is preserved without pretending
a human sign-off is a command run.

### 1.2 Gate registry and per-criterion result rows

```sql
CREATE TABLE gate_def (
  project     VARCHAR(64) NOT NULL,
  gate_id     VARCHAR(64) NOT NULL,      -- 'phase-1', 'phase-2', 'wave', 'policy-sweep', …
  title       TEXT        NOT NULL,
  guards      VARCHAR(64) NOT NULL,      -- the TRANSITION it guards, named explicitly
  mode_scope  JSON        NOT NULL,      -- ['greenfield','feature',…]
  fail_action ENUM('block','warn') NOT NULL DEFAULT 'block',
  PRIMARY KEY (project, gate_id)
);

CREATE TABLE criterion_def (
  project     VARCHAR(64) NOT NULL,
  gate_id     VARCHAR(64) NOT NULL,
  crit_id     VARCHAR(16) NOT NULL,      -- C-01 … ; scoped to the gate, like AC-NNN to a story
  ord         INT         NOT NULL,
  text        TEXT        NOT NULL,      -- the verbatim criterion string, preserved
  kind        ENUM('coverage','threshold','existence','verdict_ref','absence',
                   'command','manual') NOT NULL,
  predicate   TEXT        NULL,          -- SQL, or command_id + arg binding; NULL iff kind='manual'
  scope_pred  TEXT        NULL,          -- REQUIRED for coverage/absence/threshold (invariant 19)
  nonempty    TEXT        NULL,          -- REQUIRED for coverage/absence: the vacuity guard
  applies_when TEXT       NULL,          -- condition expression; NULL = always
  severity    ENUM('CRITICAL','HIGH','MEDIUM','LOW') NOT NULL,
  owner       VARCHAR(64) NULL,          -- REQUIRED iff kind='manual'
  PRIMARY KEY (project, gate_id, crit_id)
);

CREATE TABLE gate_run (
  project VARCHAR(64) NOT NULL, run_id VARCHAR(32) NOT NULL,
  gate_id VARCHAR(64) NOT NULL, subject VARCHAR(128) NOT NULL,
  store_version VARCHAR(64) NOT NULL, repo_sha CHAR(40) NULL,
  started_at DATETIME(3) NOT NULL, finished_at DATETIME(3) NULL,
  verdict ENUM('pass','pass_with_skips','fail','error','blocked') NULL,
  PRIMARY KEY (project, run_id)
);

CREATE TABLE criterion_result (
  project VARCHAR(64) NOT NULL, run_id VARCHAR(32) NOT NULL, crit_id VARCHAR(16) NOT NULL,
  status ENUM('pass','fail','skip','error','stale_evidence','manual_attested') NOT NULL,
  evidence_id   VARCHAR(32) NULL,   -- REQUIRED for pass/fail/manual_attested
  witness       JSON        NULL,   -- offending rows for fail; the falsified condition for skip
  skip_reason   TEXT        NULL,   -- REQUIRED for skip
  skip_condition TEXT       NULL,   -- REQUIRED for skip: the expression, and the fact values
  at DATETIME(3) NOT NULL,
  PRIMARY KEY (project, run_id, crit_id),
  CONSTRAINT fk_cr_run FOREIGN KEY (project, run_id) REFERENCES gate_run (project, run_id)
);
```

Six rules, each keyed to a measured defect:

```
L5-B  `pass` requires exactly one resolvable evidence_id. A pass row with
      evidence_id IS NULL is refused at write time (invariant 20), not reported at read time.
```
Wave 15's `wave-15-gate-final-verdict.md` declares `verdict: CONVERGED` with no record that Gates
2, 4 or 5 ran; `.factory/holdout-evaluations/` contains only `.gitkeep`. Under L5-B that verdict
is a `gate_run` with three criteria having no result row at all, which derives to `fail`.

```
L5-C  A predicate that cannot be evaluated returns `error`, and `error` blocks.
      There is no fail-open path anywhere in L5.
```
This is the single highest-value rule in the layer, because the corpus's gates fail open in four
distinct ways: `validate-per-story-adversary-convergence/src/lib.rs:215-233`
(`graceful_degrade_outside_wave_gate` — any dispatch identity not literally starting `wave-gate`
skips the gate, with `"unknown"` as the default, and the comment states it "errs on the side of
Continue"); `validate-wave-gate-prerequisite.sh` returning `exit 0 # no wave-state file = project
hasn't opted in` when `.factory/wave-state.yaml` does not exist (**it does not exist**, confirmed);
gates failing open on a missing `jq`/`python3`; and `convergence-tracker.sh:56` `exit 0 # let the
format hook handle missing section`. Under L5-C every one of these is `error` → block. The
bootstrap exemption problem this creates is **OQ-5**.

```
L5-D  Every coverage/absence criterion carries BOTH a scope predicate (invariant 19)
      and a NON-EMPTINESS guard on that scope. A vacuously-true predicate is `error`.
```
Vacuous truth is the most repeated silent pass in this corpus and it appears in three unrelated
places: Gate 5's `mean satisfaction >= 0.85` over an empty scenario set; `RED_RATIO = 0.0` where
tests passed vacuously against stubs (and the compensating controls were retired "per wave gate
consensus" *because* of it); and merge prerequisites where a PR with zero declared prerequisites
satisfies an anti-join. One rule kills all three.

```
L5-E  `skip` requires the falsified condition AND the fact values that falsified it.
      A criterion cannot be skipped by omission.
```

```
L5-F  `deferred` is not a criterion status. A deferral is a row with
      (owner, rationale, expiry, target_gate), and the receiving gate BLOCKS while any
      deferral targeting it is undispositioned.
```
`validate-wave-gate-prerequisite.sh:138` accepts `gate_status: deferred` with no rationale, owner
or expiry — and the sibling hook's error message recommends it. The keep-list's typed
`deferred_findings[]` mechanism (`skills/wave-gate/SKILL.md:86,98`;
`skills/deliver-story/steps/step-d5-adversary-convergence.md:50,69`) is the correct design and is
preserved exactly: out-of-scope findings route to a *named receiving gate*, do not block the
originating pass, and **do** block the receiving gate until dispositioned. `deferral` rows are
that mechanism with an owner and an expiry attached.

```
L5-G  Criteria are stored once, referenced everywhere. `text` is preserved verbatim so
      the human-facing gate document renders from the row (L4), not beside it.
```
The corpus has the same gate defined twice with different content: `greenfield.lobster:231-255`
declares the Phase 1 gate with **21** criteria, while
`phases/phase-1-spec-crystallization.lobster:95-104` declares `spec-gate` with **5** — a subset
that also writes module criticality to a *different path* (`.factory/module-criticality.md` vs
`.factory/specs/module-criticality.md`). Likewise Phase 2: **26** criteria at
`greenfield.lobster:469-494` against **6** at `phases/phase-2-story-decomposition.lobster:99-104`.

*Note on the brief's numbers:* I count **21** for Phase 1 and **26** for Phase 2 at pin
`0aaba144`, not 21-and-27. The 27 is not reproducible in either definition. This is exactly the
class L5-G eliminates — a gate whose size is a different number depending on which of two files
you read.

### 1.3 Worked examples — eight real criteria as queries

Each is the verbatim criterion string, its file:line, and the query it becomes. `?scope` is the
run's declared scope predicate; every query is additionally scoped by `project` (invariant 19).

---

**E1 · `"Every L2 capability maps to at least one BC-S.SS.NNN"`** — `greenfield.lobster:237`
`kind: coverage`

```sql
-- scope_pred: capability rows in this project's live L2 spec, excluding retired
-- nonempty:  SELECT COUNT(*) FROM capability WHERE project=? AND status<>'retired'  > 0
SELECT c.cap_id AS witness
FROM capability c
WHERE c.project = ? AND c.status <> 'retired'
  AND NOT EXISTS (
    SELECT 1 FROM bc b
    WHERE b.project = c.project AND b.capability = c.cap_id AND b.status <> 'retired');
-- PASS iff row_count = 0 AND nonempty holds
```
Companion, not folded in: `bc.capability` is a *scalar reference*, not an FK, because the corpus
fills it with prose — `fa/validate.go:306-308` already reports `bc.capability -> missing CAP`, and
the measured instance is `capability: "E-12"` (an epic id in a capability field). Keep them
separate: E1 answers "is every capability covered", the scalar-ref gate answers "does every
capability field hold a capability". A single query conflating them reports a coverage gap for a
type error, and the fix is different.

---

**E2 · `"Dependency graph is acyclic (topological sort succeeds)"`** — `greenfield.lobster:476`
`kind: absence`

A boolean is not an acceptable result here; the evidence must carry the **witness cycle**, because
a gate that says "there is a cycle" and cannot name it gets waived. `fa/graph.go` and
`fa/graph_metrics.go` already compute this.

```sql
-- scope_pred: story_dep edges whose both endpoints are live stories in cycle ?
-- nonempty:  the scope has ≥1 story
SELECT cycle_path AS witness FROM fa_story_cycles(?cycle);   -- SCC projection, ordered, stable
-- PASS iff row_count = 0
```
The evidence row's `stdout_bytes` holds the ordered cycle members. Also note this criterion is a
*different* question from the one `fa/validate.go:337-355` already gates
(`gateDependencyDirection` — `depends_on`/`blocks` maintained as two hand-kept lists of one fact).
Acyclicity over a half-recorded graph is unsound, so E2 declares
`requires: [dependency-direction-clean]` and reports `error` if that criterion is not `pass` in
the same run. Ordering between criteria is declared, not implied by `ord`.

---

**E3 · `"Every BC-S.SS.NNN covered by at least one story"`** — `greenfield.lobster:470`
`kind: coverage`

```sql
SELECT b.bc_id AS witness
FROM bc b
WHERE b.project = ? AND b.status NOT IN ('retired','superseded')
  AND NOT EXISTS (SELECT 1 FROM story_bc x
                  WHERE x.project=b.project AND x.bc_id=b.bc_id)
  AND EXISTS (SELECT 1 FROM story s WHERE s.project=b.project);   -- vacuity guard inline
```
`fa/validate.go:507` already computes `bc_without_story` as a **metric**, deliberately not a
finding, on the stated grounds that coverage is "a fact about the project, not a violation of a
rule". L5 does not overturn that: the metric stays, and this criterion is the *gate* over the same
query with a declared scope. The distinction matters because 90.2% of BCs having no verifying VP
would otherwise make the gate unratchetable — which is precisely §1.5's job.

---

**E4 · `"Every AC-NNN traces to a BC precondition/postcondition"`** — `greenfield.lobster:471`
`kind: coverage`

Story 12a already minted AC/EC/PC/T-task as `sub_artifact` rows with typed links
(`fa/schema.go:233-271`), and `fa/validate.go:59` already runs
`gateACTracesAgainstStoryBCs`. The criterion is that gate with a scope:

```sql
SELECT CONCAT(a.owner_key,'/',a.sub_id) AS witness, 'unanchored' AS why
FROM sub_artifact a
WHERE a.project=? AND a.kind='AC' AND a.owner_type='story' AND a.owner_key IN (?scope)
  AND NOT EXISTS (
    SELECT 1 FROM sub_artifact_ref r
    JOIN sub_artifact t ON t.project=r.project AND t.owner_key=r.target_owner
                       AND t.kind=r.target_kind AND t.sub_id=r.target_sub_id
    WHERE r.project=a.project AND r.owner_key=a.owner_key AND r.sub_id=a.sub_id
      AND t.owner_type='bc' AND t.kind IN ('PC','EC','INV')
      AND EXISTS (SELECT 1 FROM story_bc sb                    -- anchor must be IN the story's set
                  WHERE sb.project=a.project AND sb.story_id=a.owner_key AND sb.bc_id=t.owner_key));
```
The last clause is the point. An AC anchored to a *real but wrong* BC is the spine §1 residue —
"semantic correctness (an AC anchored to the wrong-but-existing BC)" — and this query narrows the
residue by requiring the anchor to lie inside the story's declared `bcs:` set. It does not
eliminate it: an AC anchored to the wrong PC *of the right BC* still passes. Say so in the gate
report rather than implying full coverage.

---

**E5 · `"No story exceeds 13 story points"`** — `greenfield.lobster:474`
`kind: threshold`

The naive form is wrong and would ship a silent pass:

```sql
SELECT story_id FROM story WHERE points > 13;      -- ✗ NULL points never matches
```

```sql
-- ✓ absent value is a FAILURE, not a pass
SELECT s.story_id AS witness,
       CASE WHEN s.points IS NULL THEN 'points absent' ELSE 'points > 13' END AS why
FROM story s
WHERE s.project=? AND s.story_id IN (?scope)
  AND (s.points IS NULL OR s.points > 13);
```
```
L5-H  Every threshold criterion declares its NULL behaviour, and the default is FAIL.
      A threshold whose null_policy is unset is refused at registration.
```
The same trap has already fired once in this corpus in a different guise:
`convergence-tracker.sh:143-145` coerces a missing severity count with `PF_CRIT="${PF_CRIT:-0}"`,
so a pass file whose table it cannot parse counts as **clean** and *increments* the clean streak.
Absent-means-good is the shape; the fix is one declared field.

---

**E6 · `"Consistency validation score >= 90/100"`** — `greenfield.lobster:478`
**REJECTED as a criterion.**

This is a scalar aggregate over other criteria, and it is unauditable in both directions: 89
blocks with no named cause, 91 passes while hiding a CRITICAL. It also has no defensible
definition — the corpus's own consistency skill declares Checks 8 and 9
(`skills/validate-consistency/SKILL.md:62-64`, 99, 141) as **advisory** and states they "never
count toward `Failed`", so the score is computed over a deliberately incomplete check set.

Replacement: the ratchet (§1.5). The gate criterion becomes *"no NEW consistency finding beyond
the dated baseline"*, which is itemised, has a named cause per failure, and lets Checks 8 and 9
become blocking — which is what the corpus already decided it wanted. `POLICY 11`
(`no_test_tautologies`, MEDIUM) and `POLICY 12` (`bc_tv_emitter_consistency`, HIGH) exist in
`.factory/policies.yaml:195-224` precisely to promote those two checks to blocking, and both have
`lint_hook: null`. **The promotion decision was already taken; only the mechanism is missing.**

---

**E7 · `"Wave adversarial review converged (cosmetic only)"`** — `greenfield.lobster:948`
`kind: verdict_ref`

```sql
SELECT ? AS subject, fa_converged(?, ?subject) AS ok, fa_converge_reason(?, ?subject) AS why;
```
where `fa_converged` is the **single** termination predicate of §1.4 — not a re-statement of it.
The criterion stores a *reference* to the rule, never a copy. This is what makes the "3 clean
passes in five prose places, zero loop exit conditions" split unrepresentable.

---

**E8 · `"Holdout evaluator used different model family (GPT-5.4, not Claude)"`**
— `phases/phase-4-holdout-evaluation.lobster:33` · `kind: verdict_ref` over attestation

```sql
SELECT a_h.role AS holdout_role, a_h.model_family AS holdout_family,
       a_i.role AS impl_role,    a_i.model_family AS impl_family, a_h.status
FROM attestation a_h
JOIN attestation a_i ON a_i.project=a_h.project AND a_i.run_id=a_h.run_id
                    AND a_i.role='implementer'
WHERE a_h.project=? AND a_h.run_id=? AND a_h.role='holdout-evaluator';
-- PASS iff status='verified' AND holdout_family <> impl_family
-- status='unverifiable'  -> `error` -> BLOCK (L5-C). Never `pass`.
```

Today this criterion is unsatisfiable and *should* block. Measured, at the plugin tree:

| | |
|---|---|
| agent definition files | 44 |
| declaring `model:` | 34 — **`opus` 7, `sonnet` 27** |
| declaring a non-Claude model | **0** |
| `agents/holdout-evaluator.md:5` | `model: opus` |
| `agents/adversary.md:5` | `model: opus` |
| `docs/FACTORY.md:412` claims `adversary/primary` → GPT-5.4 for "Adversary, Code Reviewer, Holdout Evaluator, PR Reviewer" | contradicts both |
| `docs/FACTORY.md:439` names `openclaw.json` as the routing source of truth | **file does not exist** |
| `model_tier:` uses in workflows | 24, with no resolver (`config/` holds only `artifact-path-registry.yaml`) |

Three sources of truth for model identity, two of which contradict each other and the third of
which is absent. Model diversity is either resolved and attested or it is decoration; §1.7 makes
the call.

---

**E9 (honest negative) · `"Every HIGH-impact R-NNN addressed in architecture"`**
— `greenfield.lobster:252` · `kind: manual`, `owner: architect`

Risks (`R-NNN`) and assumptions (`ASM-NNN`) have **no table** in `fa/schema.go` today, and four
Phase 1 criteria plus five Phase 2 criteria depend on them
(`greenfield.lobster:250-253`, `485-490`). Two honest options, and only two: model the types (V-C
says the 103 canonical types are the floor, not the ceiling — do this), or register the criterion
`manual: true` with `owner: architect` so the gate report shows *nine attested, not evaluated*
criteria instead of nine silent passes. **Not permitted: leaving the criterion as prose with no
result row.** That is the state the corpus is in and it is why Wave 15 could declare CONVERGED.

### 1.4 Convergence computed, never claimed

#### The finding substrate already exists

`FINDINGS-AS-ROWS.md` did this work: **390 review documents, 2,211 finding rows**, keyed on
`(review, finding_id)`, with `owned` distinguishing findings a pass *introduced* from findings it
re-states to audit a prior fix (412 mentioned-not-owned), and `sev_source` recording which of six
prose conventions resolved each severity (499 unresolved, 23%). 68 claims across 66 documents
disagree with their own bodies. L5 adds no new extraction; it adds *linkage* and *derivation*.

Re-measured at pin `0aaba144`, `verdict:` — a field whose declared domain is 2 values — holds
**23 distinct tokens over 443 uses**:

```
106 HIGH · 88 NITPICK_ONLY · 63 SUBSTANTIVE · 43 FINDINGS_REMAIN · 19 MEDIUM · 18 CLEAN
 15 CONVERGENCE_REACHED · 15 CLOCK_RESET · 14 LOW · 11 NITPICK · 11 CRITICAL · 9 MINOR
  9 MED · 6 CLEAN_PASS_1_OF_3 · 4 FINDINGS · 3 CONVERGED · 2 CLEAN_PASS_2_OF_3 · 2 BLOCKED
  1 each: STREAK_RESET_VERIFIED_CRITICAL · NITPICK-only · MERGED · MEDIUM-HIGH · DRIFT_MINOR
```

**160 of 443 uses (36%) hold a severity, not a verdict.** The most common verdict, `NITPICK_ONLY`
(88) — the exact string the one Kani-proved gate keys on — is not a legal template value. And
`CLEAN_PASS_1_OF_3` / `CLEAN_PASS_2_OF_3` show the corpus inventing streak-encoding *inside* the
verdict field because there was nowhere else to put it. Under D-D `verdict` is already retired
into `gate_result`/`convergence`/`severity_max`; the streak gets a column.

#### Rows

```sql
CREATE TABLE converge_subject (
  project VARCHAR(64) NOT NULL, subject_id VARCHAR(128) NOT NULL,
  kind ENUM('spec','story','wave','phase5','brownfield-pass','pr') NOT NULL,
  perimeter ENUM('per-story','wave-cross-story','whole-system') NOT NULL,
  termination_rule VARCHAR(32) NOT NULL,     -- FK to ONE registered rule (§1.4 rule)
  opened_at DATETIME(3) NOT NULL, closed_at DATETIME(3) NULL,
  PRIMARY KEY (project, subject_id)
);

CREATE TABLE converge_pass (
  project VARCHAR(64) NOT NULL, subject_id VARCHAR(128) NOT NULL, pass_no INT NOT NULL,
  review_key VARCHAR(200) NOT NULL,          -- FK to review (see OQ-1)
  classification ENUM('SUBSTANTIVE','NITPICK_ONLY') NOT NULL,  -- strict binary, see below
  at DATETIME(3) NOT NULL,
  PRIMARY KEY (project, subject_id, pass_no),
  CONSTRAINT fk_cp_review FOREIGN KEY (project, review_key) REFERENCES review (project, review_key)
);
-- NOTE: no owned_count, no clean_streak, no novelty column. Invariant 17.

CREATE TABLE finding_link (                  -- append-only
  project VARCHAR(64) NOT NULL, subject_id VARCHAR(128) NOT NULL,
  review_key VARCHAR(200) NOT NULL, finding_id VARCHAR(64) NOT NULL,
  dup_of_review VARCHAR(200) NOT NULL, dup_of_finding VARCHAR(64) NOT NULL,
  link_method ENUM('exact-statement','location-and-category','declared-closes',
                   'declared-duplicates','triage-manual') NOT NULL,
  linked_by VARCHAR(64) NOT NULL, at DATETIME(3) NOT NULL,
  PRIMARY KEY (project, review_key, finding_id, dup_of_review, dup_of_finding)
);

CREATE TABLE regression (
  project VARCHAR(64) NOT NULL, subject_id VARCHAR(128) NOT NULL,
  from_pass INT NOT NULL, to_pass INT NOT NULL, from_count INT NOT NULL, to_count INT NOT NULL,
  disposition ENUM('open','explained','waived') NOT NULL DEFAULT 'open',
  rationale TEXT NULL, author VARCHAR(64) NULL, at DATETIME(3) NULL,
  PRIMARY KEY (project, subject_id, from_pass, to_pass)
);
```

#### Novelty: N/D from store-side linkage, and an explicit undefined state

The adversary is **forbidden to read the comparison set** —
`greenfield.lobster` excludes `.factory/cycles/**/adversarial-reviews/**` from the adversary's
context in 2 of its 11 wall blocks — and is simultaneously required to report
`Novelty = N/(N+D)`. That is incoherent, and the live artifact shows exactly what incoherence
produces. `ADV-S5.03-P14.md` (`.factory`, pin `0aaba144`):

```
| New findings              | 0                          |
| Duplicate/variant findings| 0                          |
| Novelty score             | 0.0 (0 / (0 + 0))          |
| Trajectory                | 14→15→5→8→4→0→6→6→0→1→1→0→0→0 |
| Verdict                   | CONVERGENCE_REACHED — 3_of_3 NITPICK_ONLY satisfied |
```

`0/0` rendered as `0.0` is not merely a division by zero: **it is the most favourable value the
scale admits**, and it therefore satisfies `convergence-tracker.sh:124-129`'s
`novelty ≤ 0.15` check. An undefined quantity passed a threshold gate.

The design keeps the wall and moves the arithmetic:

```
L5-I  N and D are computed by the STORE from finding_link rows. The adversary reports
      neither, and the context wall excluding prior passes is preserved unchanged.

      N(pass) = COUNT owned findings of that pass with no finding_link row
      D(pass) = COUNT owned findings of that pass with ≥1 finding_link row

L5-J  If N+D = 0, novelty is NULL with novelty_state='undefined_no_findings'.
      A NULL metric NEVER satisfies a comparison operator. Guarded explicitly,
      in one place, with a test.
```

```sql
CREATE FUNCTION fa_novelty(p VARCHAR(64), s VARCHAR(128), pass INT)
-- returns (novelty DECIMAL(5,4) NULL, novelty_state ENUM('defined','undefined_no_findings'), n INT, d INT)
WITH f AS (
  SELECT af.review_key, af.finding_id,
         EXISTS (SELECT 1 FROM finding_link l
                 WHERE l.project=p AND l.review_key=af.review_key
                   AND l.finding_id=af.finding_id) AS is_dup
  FROM adversarial_finding af
  JOIN converge_pass cp ON cp.project=p AND cp.subject_id=s AND cp.pass_no=pass
                       AND cp.review_key=af.review_key
  WHERE af.owned = 1)
SELECT CASE WHEN COUNT(*)=0 THEN NULL
            ELSE SUM(1-is_dup)/COUNT(*) END,
       CASE WHEN COUNT(*)=0 THEN 'undefined_no_findings' ELSE 'defined' END,
       SUM(1-is_dup), SUM(is_dup)
FROM f;
```

Linkage is **declared and deterministic in v1**, not learned, and each row records which method
won — the same discipline `sev_source` already applies (`fa/findings.go:268`, and the reasoning at
`FINDINGS-AS-ROWS.md:83-95`: reporting the source is what keeps "unresolved" a measured fact about
the corpus rather than a silent parser default). Methods, in resolution order:
`declared-closes` → `declared-duplicates` → `exact-statement` (normalised) →
`location-and-category` → `triage-manual`. Embedding similarity is rejected for v1 (§3).

**Novelty is REPORTED, not a termination input.** See the rule below.

#### Monotonicity is a hard fail

`skills/adversarial-review/SKILL.md:170-177` states the rule and its cure: "Finding counts must
decrease monotonically across passes… **Do NOT continue convergence passes until the regression is
explained and resolved.**" The hook implementing it appends to `WARNINGS`
(`convergence-tracker.sh:116-118`) and the script ends `exit 0` (`:186`).

On the S-5.03 trajectory `14→15→5→8→4→0→6→6→0→1→1→0→0→0` I count **four** strict increases —
14→15, 5→8, 0→6, 0→1 — not three. (The review says three; mine is the recount.) The last three
passes are `0,0,0`, so the *streak* component genuinely holds; what fails is monotonicity, four
times, unexplained.

```
L5-K  A strict increase between adjacent passes writes a `regression` row with
      disposition='open'. While ANY open regression exists for a subject:
        - clean_streak is FORCED to 0 and cannot increment
        - fa_converged() returns false with reason='undispositioned_regression'
      A regression clears only by an `explained` or `waived` row carrying
      (rationale, author, at). The waiver itself is a gate criterion, so waiving
      is visible in the gate report rather than being an argument in a body.
```
Monotonicity is evaluated over the **window since the last dispositioned regression**, not over
all history. Otherwise one early regression blocks a subject permanently, which is unusable and
would be waived wholesale within a week — the same failure mode `fa/baseline.go:8-10` already
documents for unbaselined gates.

#### ONE termination rule

Today, five spellings and two thresholds:

| source | rule |
|---|---|
| `validate-per-story-adversary-convergence/src/lib.rs:123-177` (+6 Kani proofs at `:717-827`) | `passes_clean >= 3 AND last_classification == "NITPICK_ONLY"` |
| `workflows/phases/per-story-delivery.md:125,127,167,169` | same, "no exceptions" |
| `agents/adversary.md:162` | "Minimum 3 clean passes. Maximum 10 before escalating" |
| `agents/orchestrator/orchestrator.md:113-120` | "always 3 clean passes minimum" × 5 levels |
| `hooks/convergence-tracker.sh:8,147-166` | 3, over `find -name 'pass-*.md'` |
| `docs/CONVERGENCE.md:26` | **"Novelty < 0.15 for 2 or more consecutive passes"** |
| `skills/convergence-tracking/SKILL.md:48` | **"Novelty < 0.15 for 2+ consecutive passes"** |
| `skills/adversarial-review/SKILL.md:151` / `agents/adversary.md:159` | qualitative **"novelty is LOW"** |
| all 20 workflow `exit_condition`s | **none of the above** — 9 are `adversary.verdict == 'CONVERGENCE_REACHED'` |

Two resolutions, both decisive.

**Keep 3, not 2.** Three is the stricter number, it is the number the corpus's *only* computed
gate encodes, and it already carries 6 Kani proofs. Reuse; do not relitigate. `docs/CONVERGENCE.md`
line 26 and `convergence-tracking/SKILL.md:48` are amended to reference the rule, not restate it.

**Retire `novelty <= 0.15` as a termination condition entirely.** The threshold is only meaningful
with a similarity model, `CONVERGENCE.md`'s similarity model is attributed to a plugin that does
not exist, and the live artifact shows the threshold being satisfied by an undefined value. A
convergence rule must not depend on a model whose output nothing can audit. This resolves the
`0.15`-vs-`LOW` conflict by **deleting the threshold rather than picking a spelling**. Novelty
stays as a reported metric with an explicit undefined state, which is what makes it useful for
observability without making it load-bearing.

```
L5-L  THE termination rule. Registered once as `converge.v1`. Referenced by every gate,
      every loop exit condition, and every workflow. A workflow may not restate it.

fa_converged(project, subject) ⟺
  (1) clean_streak(subject) >= 3
        -- consecutive trailing passes whose OWNED findings above NITPICK count = 0,
        --   derived from rows; never stored
  (2) AND last_pass.classification = 'NITPICK_ONLY'
        -- STRICT BINARY: only the literal token. "effectively converged",
        --   "borderline NITPICK", "NITPICK-only" are SUBSTANTIVE.
  (3) AND no regression row with disposition='open'
  (4) AND no deferral targeting this subject with disposition='open'
  (5) AND coverage_audit(subject).status = 'pass'
  (6) AND every criterion of the receiving gate has status IN ('pass','manual_attested')
        with a resolvable evidence_id

fa_converge_reason() returns the FIRST failing clause, by number. Never a bare boolean.
```

Clause (2) is `brownfield-ingest/SKILL.md:222-232` ported verbatim, including the sentence that
makes it work: *"The agent has no authority to declare convergence — only the protocol does."*
Under L6, `converge.v1` is evaluated by the engine, so there is no dispatch path on which an
agent's self-declaration is read at all. `no fixed maximum` (`:178`) is preserved: `max_iterations`
becomes an **escalation** trigger, never a success (§2.4).

The anti-fabrication clause (`brownfield-ingest/SKILL.md:238`) is preserved verbatim as the
required prompt preamble for every pass dispatch, and `fa` refuses to open a pass whose dispatch
record does not carry it — an integrity check on the dispatch, so the clause cannot be dropped by
editing a prompt.

The **coverage audit** (clause 5) is preserved as an independent criterion precisely because
novelty decay structurally cannot replace it: `brownfield-ingest/SKILL.md:266` records that "every
one of 5 repos showed genuine B.5 blind spots after 19-62 rounds of convergence", because
round-driven deepening selects targets from prior-round flags and drifts toward covered ground.
Its method is preserved too — `:268` "**Method must be grep-driven, not agent-judgment-driven** …
Don't ask the agent 'are there gaps' — make it prove coverage with greps" — which is exactly a
`kind='command'` criterion whose evidence is the grep output `fa` captured. (Where that grep runs
is **OQ-4**.)

The **two-phase validation arithmetic** is preserved as a distinct criterion family, not folded
into convergence: `agents/validate-extraction.md:28,110` and `brownfield-ingest/SKILL.md:323,327`
require, for every numeric claim, the triple `(claimed, recounted, delta)` where "the recounted
number either matches or it doesn't. **Any mismatch is an error regardless of how small.**" Under
L5 the `recounted` value is a query result and the `delta` is computed, so the criterion is
`delta = 0` over a table of claims — which is what `fa/validate.go:116-167`
(`gateCountAssertions`) and `:369-439` (`gateReviewFindingCounts`) already do. Its future under
V-A is **OQ-7**.

#### Trajectory and reviews resolved by type, never by filename

`convergence-tracker.sh:51` and `validate-novelty-assessment.sh:51` both skip `*ADV-*.md`. Measured
at pin `0aaba144` over documents whose `document_type` contains `review`: **400 documents, of which
28 are named `ADV-*.md`** and are therefore skipped — including both files that actually declare
`CONVERGENCE_REACHED` with a `3_of_3` streak. Worse, `convergence-tracker.sh:147` globs
`find -name 'pass-*.md'` for the sibling-pass streak check, and **exactly 6 of 400** review
documents have a basename matching `pass-<N>.md`. The 3-clean-pass rule is mechanically reachable
for 1.5% of the corpus.

```
L5-M  Reviews are resolved by document_type through the registry alias map, never by
      filename glob. `fa/findings.go:48-59` (reviewTypeSet) already does exactly this,
      and already has a test pinning it derived rather than hardcoded
      (TestReviewTypeSetIsDerivedFromTheRegistry) — because the first cut's hardcoded
      set disagreed with the Python extractor's on eight spellings in both directions.
```
Measured spellings resolving to `adversarial-review` at this pin: `adversarial-review` 257 ·
`adversary-review` 69 · `adversarial-review-pass` 47 · `per-story-adversary-review` 6 ·
`local-adversary-review` 6 · plus `review-findings` 4, `review-report` 1. Under V-C these are alias
entries; under L5-M every one is seen.

### 1.5 Baselines, ratchets, and time-series retention

`fa/baseline.go` is already the right design and needs three additions, not a rewrite. Its three
existing properties — itemised, dated + attributed to a corpus commit, ratcheting so tolerated sets
only shrink (`baseline.go:10-18`) — are what let a loud gate survive. Keep them exactly.

**Addition 1 — retention.** `regression-state.json` is a single overwritten record, so the autonomy
criterion "Zero regressions in last 20 runs" (`docs/CONVERGENCE.md:357`) is not merely unmet, it is
**unevaluable**. Same for "Mean >= 0.85 for 20 consecutive runs" (`:353`) and "Converges in <= 3
passes for 15/20 runs" (`:356`). Three of five Level-3→3.5 metrics need a history that does not
exist.

```sql
CREATE TABLE check_run (
  project VARCHAR(64) NOT NULL, run_id VARCHAR(32) NOT NULL,
  at DATETIME(3) NOT NULL, store_version VARCHAR(64) NOT NULL, repo_sha CHAR(40) NULL,
  baseline_snapshot VARCHAR(32) NULL, strict TINYINT NOT NULL,
  total INT NOT NULL, new_count INT NOT NULL, fixed_count INT NOT NULL, kept_count INT NOT NULL,
  verdict ENUM('pass','fail') NOT NULL,
  PRIMARY KEY (project, run_id), KEY idx_check_at (project, at)
);
CREATE TABLE check_run_class (project, run_id, class, n, PRIMARY KEY (project, run_id, class));
```
"Zero regressions in the last 20 runs" is then `SELECT COUNT(*) FROM (SELECT verdict FROM
check_run WHERE project=? ORDER BY at DESC LIMIT 20) t WHERE verdict='fail'` — with the vacuity
guard from L5-D: **fewer than 20 rows is `error`, not `pass`.** An autonomy promotion cannot be
earned by having no history.

**Addition 2 — waivers expire.** `BaselineEntry.Waiver` (`baseline.go:39`) carries a reason;
add `waived_by` and `expires_at`. An expired waiver is a NEW finding. Otherwise the ratchet has a
one-way valve.

**Addition 3 — per-criterion baselines.** `fa/baseline.go:53` keys on `(rule, subject)`; L5 keys
gate baselines on `(gate_id, crit_id, witness_key)` so one criterion can be ratcheted while its
siblings stay strict. This is what makes the E6 replacement work, and it is what lets
`POLICY 11`/`POLICY 12` flip from advisory to blocking without blocking every PR on day one.

### 1.6 Policy registry with a predicate or a named owner

Measured at `.factory/policies.yaml`: **18 policies, 16 with `lint_hook: null`.** Only POLICY 9
(`validate-vp-consistency.sh`, line 172) and POLICY 10
(`validate-demo-evidence-story-scoped.sh`, line 188) have a mechanism. The schema comment at
`:19` declares `severity: <HIGH|MEDIUM>` — so a CRITICAL policy is **inexpressible**, while
mis-anchoring is declared to "ALWAYS block convergence". Seven POLICY entries carry
`verification_steps` written *for the adversary to follow by hand*.

```
L5-N  A policy is a criterion. It registers into criterion_def under gate_id='policy-sweep'
      and evaluates through the same evaluator, with the same evidence requirement.
      There is no second mechanism.

L5-O  severity ENUM('CRITICAL','HIGH','MEDIUM','LOW'). A policy declared to block
      convergence registers CRITICAL.

L5-P  Every policy has EITHER a machine predicate OR manual: true WITH a named owner role.
      A policy with neither cannot be registered — `fa policy add` refuses it.
      `fa policy coverage` reports predicate / manual / unregistered counts, so
      "16 of 18 have no mechanism" is a number on a dashboard rather than a discovery.
```

The migration is mechanical and its output is a decision list: 16 policies × {write a predicate |
declare an owner}. Several are already predicates in prose. POLICY 1 (`append_only_numbering`)
is `SELECT id FROM <t> WHERE retired_at IS NOT NULL AND reused=1` plus an index-presence anti-join.
POLICY 2 (`lift_invariants_to_bcs`, "every DI-NNN must be cited by at least one BC's Traceability
L2 Invariants field") is `SELECT di_id FROM domain_invariant d WHERE NOT EXISTS (SELECT 1 FROM
vp_di / bc_trace …)` — an anti-join `fa/schema.go:101` already has the edge table for. POLICY 15's
verbatim-stdout mandate is not a predicate at all: it **becomes L5-A** and is retired, along with
POLICY 5's six cure levels.

### 1.7 `fa attest`

```sql
CREATE TABLE attestation (
  project VARCHAR(64) NOT NULL, attest_id VARCHAR(32) NOT NULL,
  run_id VARCHAR(32) NOT NULL, step_id VARCHAR(64) NULL, subject VARCHAR(128) NULL,
  role VARCHAR(64) NOT NULL,                 -- 'adversary','holdout-evaluator',…
  declared_model VARCHAR(64) NULL,           -- what the agent definition SAYS
  declared_tier  VARCHAR(64) NULL,           -- model_tier: from the workflow step
  resolved_model VARCHAR(128) NULL,          -- what the provider RETURNED
  model_family   VARCHAR(32)  NULL,          -- derived from resolved_model by a declared table
  provider VARCHAR(64) NULL, resolver VARCHAR(64) NULL,
  status ENUM('verified','unverifiable','mismatch') NOT NULL,
  evidence_id VARCHAR(32) NOT NULL,
  at DATETIME(3) NOT NULL,
  PRIMARY KEY (project, attest_id), KEY idx_att_run (project, run_id, role)
);
```

```
L5-Q  An attestation is written by the DISPATCHER, not by the attested agent, and
      resolved_model comes from provider response metadata that `fa` read. Frontmatter
      and model_tier: are recorded as `declared_*` and can never satisfy a criterion.

L5-R  status='unverifiable' when no resolver is configured or the provider returned no
      model identity. `unverifiable` is `error` under L5-C, therefore BLOCKING.
      `declared <> resolved` is `mismatch`, also blocking — this is the mechanism behind
      the prose-only "No silent model fallback ever" gate, made real.
```

The immediate consequence is uncomfortable and correct: with no resolver configured, every
model-family criterion blocks, so Phase 4 cannot pass on cutover day. That is the honest state of
the world — `agents/holdout-evaluator.md:5` says `model: opus`, `docs/FACTORY.md:412` says GPT-5.4,
and `openclaw.json` does not exist. Whether v1 ships that block or a declared bootstrap exemption
is **OQ-6**, and it is a user decision, not a design one.

Attestation is also the natural home for the *other* identity criteria the corpus asserts and
cannot check: fresh-context claims (attest that the dispatch carried no prior-pass context, by
recording the resolved context set — see L6 §2.2), and the "no source/spec access" wall for the
holdout evaluator, which becomes a recorded `DENIED_BY_WALL` count rather than a promise.

---

## 2. L6 ENGINE

### 2.1 Workflow as data — ten spellings, seven kinds

The current validator "permits only `agent|skill|command` and requires `task`", so it rejects
nearly every real step, and `run-phase` cannot execute any phase workflow. The census in §0 is the
requirement.

| kind | spellings | n | semantics L6 must hold |
|---|---|---|---|
| `agent` | `agent` | 280 | dispatch with a resolved context set + attestation |
| `skill` | `skill` | 130 | same, plus the skill's declared preconditions |
| `command` | `command` | 0 in workflows | allowlisted argv (shares the L5 command registry) |
| `gate` | `gate` | 38 | evaluate `gate_def`; `fail_action`; blocks a named transition |
| `approval` | `human-approval` | 37 | §2.5 |
| `nest` | `sub-workflow` | 25 | cycle-checked; `planning ↔ greenfield` is mutual |
| `loop` | `loop` | 24 | §2.4 — cap, exit reason, `converge.v1` reference |
| `fanout` | `parallel`, `parallel-foreach`, `compound` | 12 | **`parallel-foreach` needs a declared iteration set — see OQ-10** |

```sql
CREATE TABLE workflow (project, workflow_id, name, version, mode, source_sha CHAR(40),
                       PRIMARY KEY (project, workflow_id, version));
CREATE TABLE step (
  project VARCHAR(64), workflow_id VARCHAR(64), version VARCHAR(16), step_id VARCHAR(64),
  ord INT NOT NULL, parent_step VARCHAR(64) NULL,      -- loop/parallel/compound bodies
  kind ENUM('agent','skill','command','gate','approval','nest','loop','fanout') NOT NULL,
  spelling VARCHAR(24) NOT NULL,                        -- the source token, preserved
  agent VARCHAR(64) NULL, skill VARCHAR(256) NULL, gate_id VARCHAR(64) NULL,
  task TEXT NULL, model_tier VARCHAR(32) NULL,
  condition TEXT NULL, optional TINYINT NOT NULL DEFAULT 0, timeout_ms INT NULL,
  PRIMARY KEY (project, workflow_id, version, step_id)
);
CREATE TABLE step_dep (
  project, workflow_id, version, step_id, dep_id,
  on_skip ENUM('skip','ignore','block','substitute') NOT NULL,   -- NOT NULLABLE. See L6-C.
  substitute_step VARCHAR(64) NULL,
  PRIMARY KEY (project, workflow_id, version, step_id, dep_id)
);
CREATE TABLE ctx_rule (                       -- the walls, as TYPES not path spellings
  project, workflow_id, version, step_id, ord INT,
  mode ENUM('include','exclude') NOT NULL,
  artifact_type VARCHAR(64) NULL,             -- preferred
  path_pattern VARCHAR(256) NULL,             -- migration only; reported as a debt row
  PRIMARY KEY (project, workflow_id, version, step_id, ord)
);
CREATE TABLE fact_def (                       -- every condition variable, declared
  project, workflow_id, version, fact VARCHAR(64),
  type ENUM('bool','string','int','enum','set'), producer_step VARCHAR(64) NULL,
  source ENUM('config','step_output','store_query','mode_profile') NOT NULL,
  PRIMARY KEY (project, workflow_id, version, fact)
);
```

`ctx_rule` keyed on `artifact_type` rather than path is the F16 point applied to the engine: the 11
exclude blocks in `greenfield.lobster` are path globs, and the three adversary perimeters they
implement are *type* statements ("no prior adversarial reviews", "no implementer notes", "no
holdout scenarios"). Path-keyed walls break silently when a path is renamed — and the corpus has
~28 unregistered artifact homes and a `planning` vs `plans` split. Migration keeps
`path_pattern` and emits one debt row per wall until it is retyped.

### 2.2 Condition evaluation and skip propagation

**Three-valued logic, and UNKNOWN is not FALSE.**

```
L6-A  Every condition variable is declared in fact_def with a producer. Evaluating a
      condition over an undeclared variable is a REGISTRATION error, not a runtime false.
```
This is the root of the 140-edge problem. `ui_quality_gate.has_failures`,
`dtu_assessment.has_candidates`, `wave.has_critical_stories`, `config.post_feature_validation.enabled`,
`architect.verdict`, `human_approved_multi_repo` — none has a declared producer or type, so today
every one silently reads as false-ish and every dependent silently vanishes. Declaring them is
mechanical; leaving them undeclared is what makes the graph unsound.

```
L6-B  A condition evaluates to TRUE / FALSE / UNKNOWN.
        TRUE    -> step runs
        FALSE   -> step_run status='skipped' with skip_reason + the fact values
        UNKNOWN -> step_run status='blocked'. NEVER skipped. Blocked steps are a
                   frontier state a human or a producer step must resolve.
```

```
L6-C  step_dep.on_skip is NOT NULLABLE. `fa workflow validate` refuses any workflow with an
      edge to a conditional step whose on_skip is unset.

      Defaults applied at migration, then reviewed edge by edge:
        - target kind = 'gate'      -> `ignore` (the gate records a `skip` criterion result
                                       carrying the falsified condition — L5-E)
        - target kind = 'approval'  -> `ignore`
        - dep.optional = 1          -> `ignore`
        - otherwise                 -> `skip` (propagate)
      `block` and `substitute` are always explicit.
```
`ignore` as the gate default is exactly what fixes the review's two findings and my third:
`wave-gate:945` → `wave-ui-quality-gate:938` becomes satisfiable for a non-UI product, with the
gate reporting "UI quality gate: skipped (feature_type='cli')" as a **recorded skip with a
witness** rather than a silent hole; `phase-7-convergence:1246` → `phase-6-ui-fix-delivery:1236`
(doubly conditional) likewise; and `session-review:1379` → `post-feature-validation:1364` stops
stranding the entire post-pipeline tail.

**The migration cost is stated, not hidden: 140 edges each need one declared `on_skip`.** That is
the honest price of making skip propagation sound, and it is a one-time list `fa workflow validate`
prints.

```
L6-D  `fa workflow plan --mode <m> --profile <p> --facts <f>` resolves the WHOLE step set —
      every step, gate, criterion and approval — to one of
      {will_run, will_skip(reason), blocked(unknown fact), unreachable(cycle)}
      and emits it as rows. This is the artifact a human reviews before a run starts.
```
`fa workflow validate` additionally: resolves every `agent`/`skill` reference; detects `nest`
cycles (`planning.lobster` ↔ `greenfield.lobster` is mutual — permitted only with a declared
re-entry bound); refuses a `gate` step whose `gate_id` has no `gate_def`; and refuses a `loop`
with neither cap nor exit condition (3 exist today).

### 2.3 Typed pipeline state — the frontier as rows

Replaces six mutually incompatible `STATE.md` schemas, a 2,100-character `current_step:`, four
conflicting size budgets (200/415/500) enforced by a hook whose name does not exist, a 27-line
HTML-comment `wc -l` ledger, and the same transition restated in 6–7 hand-maintained places per
burst. `STATE.md` becomes an L4 render of these rows, gated byte-exact under invariant 15.

```sql
CREATE TABLE run (
  project VARCHAR(64), run_id VARCHAR(32), workflow_id VARCHAR(64), version VARCHAR(16),
  mode ENUM('greenfield','feature','brownfield','maintenance','discovery','quick-dev','multi-repo'),
  profile VARCHAR(64) NULL, cycle VARCHAR(64) NULL,
  started_at DATETIME(3), ended_at DATETIME(3) NULL,
  status ENUM('running','waiting_human_approval','blocked','paused_budget','hard_stopped',
              'completed','failed','abandoned') NOT NULL,
  PRIMARY KEY (project, run_id)
);
CREATE TABLE step_run (
  project VARCHAR(64), run_id VARCHAR(32), step_id VARCHAR(64), iteration INT NOT NULL DEFAULT 0,
  status ENUM('pending','ready','running','waiting_human_approval','blocked',
              'skipped','passed','failed','cancelled') NOT NULL,
  skip_reason TEXT NULL, skip_witness JSON NULL,
  attempt INT NOT NULL DEFAULT 1,
  started_at DATETIME(3) NULL, ended_at DATETIME(3) NULL,
  gate_run_id VARCHAR(32) NULL, attest_id VARCHAR(32) NULL,
  PRIMARY KEY (project, run_id, step_id, iteration),
  KEY idx_sr_status (project, run_id, status)
);
CREATE TABLE fact (                      -- resolved condition inputs, per run, append-only
  project, run_id, fact VARCHAR(64), value JSON NULL,
  state ENUM('resolved','unknown') NOT NULL,
  produced_by_step VARCHAR(64) NULL, at DATETIME(3) NOT NULL,
  PRIMARY KEY (project, run_id, fact, at)
);
```

```
L6-E  ONE status enum, nine values, including waiting_human_approval — which exists
      nowhere in the corpus today although `agents/orchestrator/HEARTBEAT.md:40` nudges on it.
L6-F  "Where are we" is a QUERY, not a string:
        SELECT step_id, status FROM step_run
        WHERE project=? AND run_id=? AND status IN ('ready','running','waiting_human_approval','blocked')
      The 2,100-character current_step: has no stored form.
```

### 2.4 Loop runs — cap, iterations, exit reason

Measured: 24 loops; 21 caps of which **19 are the same magic 10**, one is 3, one is 1; 3 loops with
no cap; 4 with no exit condition; 20 exit conditions with 7 distinct expressions, **zero**
referencing a streak. Nine are the string `adversary.verdict == 'CONVERGENCE_REACHED'` — the agent
declaring its own convergence, which `brownfield-ingest/SKILL.md:230` forbids in the same plugin.
And 4 exit conditions are disjunctions of the form
`spec_reviewer.verdict == 'APPROVED' OR spec_reviewer.findings.critical == 0`, so zero-CRITICAL
alone terminates and HIGH findings do not block.

```sql
CREATE TABLE loop_run (
  project VARCHAR(64), run_id VARCHAR(32), step_id VARCHAR(64),
  declared_cap INT NULL,                       -- NULL = no fixed maximum (brownfield's rule)
  termination_rule VARCHAR(32) NOT NULL,       -- FK: 'converge.v1' etc. Never an inline expression.
  iterations INT NOT NULL,
  exit_reason ENUM('converged','cap_hit','escalated','aborted','condition_unknown') NULL,
  escalated_to VARCHAR(64) NULL, at DATETIME(3) NOT NULL,
  PRIMARY KEY (project, run_id, step_id)
);
```

```
L6-G  A loop's exit condition is a REFERENCE to a registered termination rule, never an
      inline expression. `converge.v1` (L5-L) is one such rule.
L6-H  cap_hit is NOT success. Reaching declared_cap writes exit_reason='cap_hit' and
      escalates; the loop's parent gate sees `fail`, not `pass`.
      A loop_run with iterations>0 and exit_reason IS NULL is a CRASH record, recoverable
      from the log (F20), not a completion.
L6-I  declared_cap = NULL is legal and means "no fixed maximum" — preserving
      brownfield-ingest/SKILL.md:178 ("Round budgets are advisory floors, not stop conditions.
      The protocol stops; the agent never does."). Empirically load-bearing: Vault Pass 2
      needed 62 rounds, and R6/R10/R15/R30 each predicted "next is NITPICK" and were wrong.
```

### 2.5 Human approvals

37 nodes, 8 distinct timeouts, plus ~14 gates that exist only in prose (tool-installation approval
on *any* security finding, model-substitution approval, merge autonomy L3/L3.5/L4, story-split's
two separate human touches, UNJUSTIFIED green tests in the Red Gate check). None has a pending
state, a clock, or a recorded answer.

```sql
CREATE TABLE approval (
  project VARCHAR(64), run_id VARCHAR(32), step_id VARCHAR(64),
  reachable_at DATETIME(3) NOT NULL,     -- the clock starts HERE, not at prompt render
  prompted_at DATETIME(3) NULL, due_at DATETIME(3) NOT NULL,
  nudge_after_ms INT NOT NULL DEFAULT 14400000,       -- the heartbeat's 4h, as data
  last_nudged_at DATETIME(3) NULL, nudge_count INT NOT NULL DEFAULT 0,
  decided_at DATETIME(3) NULL,
  decision ENUM('approve','reject','investigate') NULL, decided_by VARCHAR(64) NULL,
  on_timeout ENUM('block','escalate') NOT NULL DEFAULT 'block',   -- NEVER 'approve'
  PRIMARY KEY (project, run_id, step_id)
);
CREATE TABLE approval_question (
  project, run_id, step_id, q_id VARCHAR(16), ord INT, text TEXT NOT NULL,
  kind ENUM('scope_completeness','anchor_correctness','coverage_gaps',
            'convention_consistency','free') NOT NULL,
  required TINYINT NOT NULL DEFAULT 1,
  PRIMARY KEY (project, run_id, step_id, q_id)
);
CREATE TABLE approval_answer (
  project, run_id, step_id, q_id, answer TEXT NOT NULL,
  answered_by VARCHAR(64) NOT NULL, at DATETIME(3) NOT NULL,
  PRIMARY KEY (project, run_id, step_id, q_id, at)          -- append-only
);
CREATE TABLE approval_artifact (project, run_id, step_id, artifact_key, ord, PRIMARY KEY (…));
```

```
L6-J  The pending row is written the moment the approval becomes REACHABLE, and the timeout
      clock runs from reachable_at. Clocking from prompt render lets a delayed prompt hide
      a breach, and the heartbeat's ">4h pending" nudge needs a state that exists before
      anyone looks.
L6-K  on_timeout NEVER includes 'approve'. A timeout blocks or escalates.
L6-L  A `required` question with no answer row blocks the decision. This is the gate
      presentation protocol (Summary -> Structured Questions -> Approve/Reject/Investigate)
      made enforceable, on its own stated grounds: "the user-as-senior-architect catches
      things the adversary doesn't."
```
The four Phase 2 questions at `greenfield.lobster:1313-1320` (story coverage / DTU scope / wave
ordering / naming consistency) are `approval_question` rows with `kind` set, and their answers are
rows. `investigate` is a first-class decision that returns the run to `blocked` with the answer
attached — today it is an option in a prompt with nowhere to land.

### 2.6 Waves, checkpoints, and the `rehydrate-wave` port

`.factory/wave-state.yaml` was **never instantiated** (confirmed absent), so three registered
hooks are no-ops and the prerequisite hook fails open. A second, incompatible representation
(`stories/sprint-state.yaml`) is what `bin/wave-state` reads and it is a month stale.

```sql
CREATE TABLE wave (project, cycle, wave_no INT, status ENUM('planned','open','gating','closed'),
                   opened_at, gate_run_id VARCHAR(32) NULL, closed_at,
                   PRIMARY KEY (project, cycle, wave_no));
CREATE TABLE wave_story (project, cycle, wave_no, story_id, PRIMARY KEY (…));
CREATE TABLE checkpoint (
  project, checkpoint_id VARCHAR(32), kind ENUM('wave-handoff','burst','phase','manual'),
  subject VARCHAR(128), store_version VARCHAR(64) NOT NULL, repo_sha CHAR(40) NULL,
  manifest_id VARCHAR(32) NULL, created_at DATETIME(3), PRIMARY KEY (project, checkpoint_id));
CREATE TABLE injection_manifest (project, manifest_id, checkpoint_id, closed_form TEXT NOT NULL,
                                 PRIMARY KEY (project, manifest_id));
CREATE TABLE injection_member (
  project, manifest_id, path VARCHAR(512),
  source ENUM('story_spec','arch_file','state_pointer') NOT NULL,
  PRIMARY KEY (project, manifest_id, path));
CREATE TABLE rehydration (
  project, rehydration_id VARCHAR(32), checkpoint_id VARCHAR(32),
  injected_count INT NOT NULL, missing_count INT NOT NULL, missing JSON NULL,
  method ENUM('manifest') NOT NULL,                 -- the enum has exactly one value. See L6-N.
  confirmed_by VARCHAR(64) NULL, confirmed_at DATETIME(3) NULL,
  at DATETIME(3) NOT NULL, PRIMARY KEY (project, rehydration_id));
```

`rehydrate-wave` is the best-specified subsystem in the corpus and is ported **almost unchanged**.
Read from `~/.claude/plugins/cache/claude-mp/vsdd-factory/1.0.0-rc.23/skills/rehydrate-wave/SKILL.md`
(it does not exist on `develop` — the version caveat that reframes AREA 4):

| ported property | source | L6 form |
|---|---|---|
| closed-form injection set `Set(stories[*].spec_files) ∪ Set(arch_files) ∪ {state_pointer}`, deduplicated | `:3`, `:81-82` (PC2 / invariant 2) | `injection_manifest.closed_form` stores the expression; `injection_member` stores its evaluation. Both, so the set is auditable *and* replayable |
| manifest read from the branch, no working-tree fallback | `:78-79` (PC1) | manifest is a store row at a pinned `store_version`; there is no working tree to fall back to |
| `INJECTED_FILE_COUNT=<n>` machine-stable sentinel on stdout | `:87` (PC2-SIGNAL) | `rehydration.injected_count`, and the sentinel is still emitted for the bats harness |
| warn-and-continue on a missing listed member | `:84`, `:183-184` (PC6) — "does NOT hard-block" | `missing_count` + `missing` JSON; warn |
| hard error on a missing manifest | `:155-158` (RehydrationError) | `error`, no degrade — the one place in L6 that is *not* warn |
| **no-RAG prohibition** | `:190-192` (invariant 3 / PC8 / ADR-026 §Decision 4) | `rehydration.method ENUM('manifest')` — a one-value enum. No retrieval path is representable |
| operator confirmation before any pipeline work | `:89`, `:103` (PC5) | `confirmed_by`/`confirmed_at`; the run stays `blocked` until set |
| postcondition→mechanism table | `:201-208` | becomes 8 `criterion_def` rows on gate `rehydration`, each with its own evidence |

```
L6-M  The manifest is the ONLY input to rehydration. A missing manifest is a hard error;
      a missing member is a warning. These two asymmetric behaviours are preserved exactly
      as specified, because they are correct: a partial manifest is recoverable, an absent
      one is a lie about what wave you are in.
L6-N  method ENUM has one value. RAG, semantic retrieval, vector similarity and
      LLM file-matching are UNREPRESENTABLE rather than prohibited by prose.
```
The anti-fabrication checks move into `fa` where an agent cannot skip the step that runs them:
40-char-hex validation on any SHA field, the no-hardcode/no-cache rule, the three-state
`precompact_flush_sha` that hard-blocks rather than writing a bad value, the non-empty `active_bcs`
requirement, and the CWE-116 interpolation guard.

### 2.7 Scheduler

Both `greenfield.lobster:1364-1374` and `feature.lobster:1446-1451` declare post-feature validation
at 7/30/90 days. The greenfield node is `type: agent, agent: orchestrator` whose entire task is the
sentence *"Schedule post-feature validation checks at 7, 30, and 90 days"*. There is no scheduler
and no schedule store. Nothing will ever fire. `discovery.lobster:31-36` declares five cadences
(market_research weekly, feedback_ingestion daily, competitive_monitoring weekly,
analytics_integration weekly, full_synthesis weekly) behind one run id.

```sql
CREATE TABLE schedule (
  project VARCHAR(64), schedule_id VARCHAR(32),
  subject VARCHAR(128) NOT NULL,                -- 'post-feature-validation:S-12.06'
  kind VARCHAR(64) NOT NULL,
  spec VARCHAR(64) NOT NULL,                    -- 'offset:7d,30d,90d' | 'every:7d' | 'cron:…'
  anchor_at DATETIME(3) NOT NULL,               -- offsets are relative to a REAL event
  last_fired DATETIME(3) NULL,
  next_due   DATETIME(3) NULL,                  -- NULL only when exhausted or disabled
  enabled TINYINT NOT NULL DEFAULT 1,
  missed INT NOT NULL DEFAULT 0, max_missed INT NOT NULL DEFAULT 3,
  workflow_id VARCHAR(64) NULL, mode VARCHAR(32) NULL,
  PRIMARY KEY (project, schedule_id), KEY idx_sched_due (project, enabled, next_due)
);
CREATE TABLE schedule_fire (
  project, schedule_id, due_at DATETIME(3), fired_at DATETIME(3) NULL, run_id VARCHAR(32) NULL,
  outcome ENUM('fired','skipped_disabled','missed','failed') NOT NULL,
  PRIMARY KEY (project, schedule_id, due_at));     -- append-only, one row per DUE window
```

```
L6-O  Durability is the whole feature. `next_due` is stored, so a window that passed
      unfired is a `missed` row rather than a window nobody knows existed. "Schedule X"
      as an agent instruction is not representable: `fa schedule add` is a semantic op.
L6-P  `fa schedule due --project <p>` is the ONLY read a driver needs, and it is scoped by
      project — a shared cron across N tenants is one query, not N.
L6-Q  missed >= max_missed disables the schedule and writes a finding. A schedule that
      silently stops is indistinguishable from one that never existed; this is the same
      class as the single-record regression-state.json.
```

### 2.8 PR / CI join, and merge prerequisites as verdicts

Today there is **no persisted story→PR mapping**, `pr-manager` is denied `exec` so every
`gh pr view` is a sub-agent dispatch, and dependency-ordered merge is an N-dispatch join. The merge
prerequisite hook checks that three *files exist* — `validate-pr-merge-prerequisites.sh:82`
(`pr-description.md`), `:88` (`pr-review.md`), `:94` (`security-review.md`) — and if
`security-review.md` is absent it satisfies "security review conducted" via
`:97`: `grep -qiE "security.*clean|security.*no finding|security.*pass|no security"` over
`pr-description.md`, **a file `pr-manager` writes itself.**

```sql
CREATE TABLE pr (project, repo VARCHAR(128), pr_number INT, story_id VARCHAR(32) NULL,
                 head_sha CHAR(40), base VARCHAR(64),
                 state ENUM('open','closed','merged'), opened_at, merged_at, merge_sha CHAR(40) NULL,
                 PRIMARY KEY (project, repo, pr_number), KEY idx_pr_story (project, story_id));
CREATE TABLE ci_run (project, repo, pr_number, head_sha CHAR(40), provider VARCHAR(32),
                     external_id VARCHAR(64),
                     conclusion ENUM('pending','success','failure','cancelled','skipped'),
                     started_at, ended_at, evidence_id VARCHAR(32) NOT NULL,
                     PRIMARY KEY (project, repo, pr_number, head_sha, provider, external_id));
CREATE TABLE merge_prereq (project, repo, pr_number, prereq_id VARCHAR(16),
                           gate_id VARCHAR(64) NOT NULL, crit_id VARCHAR(16) NOT NULL,
                           PRIMARY KEY (project, repo, pr_number, prereq_id));
```

```
L6-R  A merge prerequisite is a (gate_id, crit_id) REFERENCE. There is no filename in the
      table and no path in the predicate. "Security review conducted" resolves to a
      criterion_result whose evidence `fa` produced.
```

The whole join, one query:

```sql
SELECT s.story_id, w.wave_no, p.pr_number, p.state,
       c.conclusion AS ci,
       (SELECT COUNT(*) FROM merge_prereq m WHERE m.project=p.project
          AND m.repo=p.repo AND m.pr_number=p.pr_number)                          AS prereqs,
       (SELECT COUNT(*) FROM merge_prereq m
          JOIN criterion_result r ON r.project=m.project AND r.crit_id=m.crit_id
          JOIN gate_run g ON g.project=r.project AND g.run_id=r.run_id AND g.gate_id=m.gate_id
                         AND g.subject = s.story_id
         WHERE m.project=p.project AND m.repo=p.repo AND m.pr_number=p.pr_number
           AND r.status IN ('pass','manual_attested'))                            AS satisfied
FROM story s
JOIN wave_story w ON w.project=s.project AND w.story_id=s.story_id
LEFT JOIN pr p ON p.project=s.project AND p.story_id=s.story_id AND p.state='open'
LEFT JOIN ci_run c ON c.project=p.project AND c.repo=p.repo AND c.pr_number=p.pr_number
                  AND c.head_sha=p.head_sha
WHERE s.project=? AND w.cycle=? AND w.wave_no=?;
-- MERGEABLE iff prereqs > 0 AND satisfied = prereqs AND ci='success'
--   The `prereqs > 0` clause is L5-D. Without it a PR with no declared prerequisites merges.
```

Dependency-ordered merge is then a topological sort over `story_dep` filtered to `MERGEABLE` — one
query, not an N-dispatch join.

### 2.9 Cost, budget, and autonomy

`docs/FACTORY.md:993-1000` declares the five tiers (0-70 log · 70-85 WARN · 85-95 ALERT + downgrade
non-critical · 95-100 PAUSE · >100 HARD STOP) and five protected agents never downgraded
(adversary, holdout-evaluator, formal-verifier, pr-reviewer, security-reviewer). It reads
`.factory/cost-summary.md` maintained by `plugins/src/cost-tracker.ts` and configured by
`.factory/autonomy-config.yaml`. **All three do not exist** (confirmed: no `cost-summary.md`, no
`autonomy-config.yaml`, no `cost-tracker.ts` anywhere in the tree). The budget-driven control flow
has no data source, and `HEARTBEAT.md:36` alerts at 95% off the same absent file.

```sql
CREATE TABLE cost_event (               -- append-only, the ONLY primary cost record
  project VARCHAR(64), event_id VARCHAR(32), run_id VARCHAR(32) NULL, step_id VARCHAR(64) NULL,
  iteration INT NULL, subject VARCHAR(128) NULL, role VARCHAR(64) NULL,
  provider VARCHAR(64), model VARCHAR(128), tier VARCHAR(32) NULL,
  tokens_in BIGINT, tokens_out BIGINT, cache_read BIGINT, cache_write BIGINT,
  cost_micros BIGINT NOT NULL, at DATETIME(3) NOT NULL,
  PRIMARY KEY (project, event_id), KEY idx_cost_run (project, run_id, at));
CREATE TABLE budget (project, scope VARCHAR(64), limit_micros BIGINT NOT NULL,
                     window ENUM('run','cycle','month'), PRIMARY KEY (project, scope));
CREATE TABLE protected_role (project, role VARCHAR(64), PRIMARY KEY (project, role));
```

```
L6-S  Budget TIER is derived, never stored:
        tier(scope) = f(SUM(cost_micros) / limit_micros) over the declared window
      With no cost_event rows the ratio is 0 and the tier is `ok`. That is honest — but
      `fa cost status` reports coverage (`events=0`), and a budget-gated transition with
      zero events is `error` under L5-D's vacuity guard, not `pass`.
L6-T  hard_stop is enforced at the DISPATCH boundary by a store predicate, not in a driver's
      memory, so it survives a session restart. `run.status='hard_stopped'` and no step_run
      may transition to `running`.
L6-U  A role in protected_role is never downgraded at any tier. Preserved verbatim; the
      five rows are seeded from FACTORY.md:999.
```

Autonomy scoring becomes evaluable for the first time — and the derivation makes its
preconditions explicit:

```sql
-- AutonomyScore = .30·Satisfaction + .20·(1-FalsePositive) + .20·(1-Override)
--               + .15·ConvergenceSpeed + .15·(1-Regression)      [CONVERGENCE.md:330-331]
-- Over the last 20 runs. Each term names its source table:
--   Satisfaction      -> holdout evaluation rows (walled zone; ids+scores only, D2)
--   FalsePositiveRate -> finding rows linked to a high-satisfaction scenario
--   OverrideRate      -> approval.decision='reject' over auto-advanced steps
--   ConvergenceSpeed  -> converge_pass count per subject where fa_converged() first held
--   RegressionRate    -> check_run.verdict='fail' over the window
-- L6-V: fewer than 20 check_run rows -> `error`, never a promotion. And
--       "fast revocation, slow promotion" is asymmetric BY CONSTRUCTION:
--       promotion needs 20 rows >= 0.85; revocation fires on any 5-run window < 0.70.
```

### 2.10 Mode awareness

`routing: standard-F1-F7` exists exactly once in the corpus —
`.factory/feature-delta/F-block-ai-attribution-message-file-arm/F1-delta-analysis.md:13` — and
nothing consumes it (zero hits in `crates/` or `hooks/`). Meanwhile `quick-dev-routing/SKILL.md`
declares a real routing profile in prose: skip F2/F3/F6, always preserve the full regression suite,
at least one adversarial pass, and human merge authorization
(`skills/quick-dev-routing/SKILL.md:55-73`), plus a `ONE_SHOT` path.

```sql
CREATE TABLE mode_profile (
  project VARCHAR(64), mode VARCHAR(32), profile VARCHAR(64),
  workflow_id VARCHAR(64) NOT NULL, always_preserve JSON NOT NULL,   -- step ids that CANNOT skip
  PRIMARY KEY (project, mode, profile));
CREATE TABLE mode_step_disposition (
  project, mode, profile, step_id VARCHAR(64),
  disposition ENUM('include','skip','substitute') NOT NULL,
  reason TEXT NOT NULL,                              -- REQUIRED for skip/substitute
  substitute_step VARCHAR(64) NULL,
  PRIMARY KEY (project, mode, profile, step_id));
```

```
L6-W  A profile resolves the WHOLE step set, including gates, criteria and approvals —
      not just agent steps. `fa workflow plan --mode quick-dev` emits a row per step with
      its disposition and reason, and every skip's reason is RECORDED on the run
      (step_run.skip_reason), so "which phases did quick-dev skip and why" is a query.
L6-X  always_preserve is enforced against the profile at registration: a profile that skips
      a preserved step cannot be written. That is how "always preserved (never skipped, even
      for trivial changes)" stops being an instruction and starts being a constraint —
      including "regression always full, never delta-scoped".
L6-Y  `routing:` frontmatter resolves to (mode, profile) at import and is thereafter
      unrepresentable as free text (V-C).
```

---

## 3. Invariants added

Extending the spine's 1–23. None replaces or renumbers an existing invariant.

| # | Invariant | Gated by | Kills |
|---|---|---|---|
| **24** | Evidence records are created only by `fa` executing a query or a command. No API accepts evidence bytes. | `fa gate exec` is the only writer of `evidence`; write-path test asserts no other caller | the self-attesting `$ grep -c … / PASS` transcript; POLICY 15; POLICY 5's six cure levels |
| **25** | Every `criterion_result` carries exactly one of `evidence_id` / (`skip_reason` + `skip_condition`) / `attestation_id`. `pass` with none is refused at write time. | schema CHECK + write-path validation | Wave 15's CONVERGED with no record that Gates 2/4/5 ran |
| **26** | A predicate that cannot be evaluated is `error`, and `error` blocks. There is no fail-open path in L5 or L6. | every evaluator returns a 3-valued result; no `exit 0` default | `lib.rs:215-233`; `wave-state.yaml` absent → `exit 0`; missing `jq`/`python3` |
| **27** | Every coverage/absence/threshold criterion declares a scope predicate **and** a non-emptiness guard. Vacuous truth is `error`. | refused at registration | Gate 5 over an empty scenario set; `RED_RATIO = 0.0`; merge prereqs = 0 |
| **28** | Every threshold criterion declares its NULL behaviour; the default is FAIL. | refused at registration | `points > 13` missing NULLs; `PF_CRIT="${PF_CRIT:-0}"` counting an unparsed pass as clean |
| **29** | Every ratio guards its denominator and records which branch it took. A NULL metric never satisfies a comparison. | `fa_novelty` returns `(value, state)`; comparison operators refuse NULL | `Novelty 0.0 (0/(0+0))` satisfying `≤ 0.15`; `CI(i)` dividing by `Cost(i)` |
| **30** | Convergence is derived at read time from `converge_pass` + finding rows. No convergence value is stored. | no `passes_clean` / `novelty` / `clean_streak` column exists | `passes_clean: 3` beside `"fix_batches_pending": ["B3","B4"]` |
| **31** | A monotonicity regression is a hard fail; the clean streak cannot increment while a regression is undispositioned. | `fa_converged` clause (3) | `convergence-tracker.sh:116-118` warn-then-`exit 0` over four unexplained increases |
| **32** | There is exactly one termination rule, registered once and referenced. No workflow, hook, skill or doc may restate it. | `loop.termination_rule` is an FK; `fa doctor` diffs prose against the rule | 3-in-five-places / `2+` in two docs / `0.15` in a hook / `LOW` in a skill / 0 in exit conditions |
| **33** | Every policy has a machine predicate or `manual: true` with a named owner role. | `fa policy add` refuses otherwise | 16 of 18 with `lint_hook: null` |
| **34** | Policy severity includes CRITICAL. | enum | `severity: <HIGH\|MEDIUM>` making a CRITICAL policy inexpressible |
| **35** | Every condition variable is declared with a producer; an undeclared variable is a registration error, never a runtime false. | `fa workflow validate` | 166 conditional steps over undeclared facts |
| **36** | `step_dep.on_skip` is non-nullable; every edge to a conditional step declares its resolution. | `fa workflow validate` refuses | 140 edges, incl. `wave-gate`, `phase-7-convergence`, and the whole post-pipeline tail |
| **37** | Every loop run records `declared_cap`, `iterations` and `exit_reason`; `cap_hit` is not success; a missing `exit_reason` is a crash record. | schema + recovery | 19 loops sharing the magic cap 10; converged and cap-hit indistinguishable |
| **38** | An approval's pending row exists from reachability, and the clock runs from `reachable_at`. `on_timeout` never includes `approve`. | schema + scheduler | `waiting_human_approval` existing nowhere while the heartbeat nudges on it |
| **39** | Merge prerequisites are `(gate_id, crit_id)` references. No filename appears in a prerequisite. | schema has no path column | three file-existence checks + a regex over a self-written PR description |
| **40** | Model identity resolves through an `attestation` row whose `resolved_model` `fa` read from the provider. `unverifiable` and `mismatch` block. | L5-Q/L5-R | "different model family (GPT-5.4, not Claude)" against 44 agent files declaring only opus/sonnet |
| **41** | Every recurring subject has a durable `(subject, interval, last_fired, next_due)` row; a passed-unfired window is a `missed` row. | schema; `fa schedule due` | 7/30/90 declared twice with no scheduler; five discovery cadences behind one run id |
| **42** | Budget tier is derived from `cost_event` rows and enforced at the dispatch boundary. | L6-S/L6-T | five tiers reading three files that do not exist |
| **43** | Rehydration's only input is the manifest; RAG is unrepresentable, not prohibited. | `method` enum has one value | — (preserving what already works) |

---

## 4. Rejected alternatives

**R1 · Embedding-similarity novelty** (`docs/CONVERGENCE.md:38-44`, "average similarity > 0.75").
Rejected for v1. It is attributed to a `convergence-tracker` plugin that does not exist, it makes
the termination rule depend on a model whose output nothing audits, and it would sit downstream of
a linkage step that has never been measured. Replaced by declared deterministic linkage with a
recorded `link_method` — the `sev_source` pattern, which has already earned its keep once
(`FINDINGS-AS-ROWS.md:83-95`: the first cut reported 1,895 of 2,138 rows as severity-less, which
read as catastrophic corpus drift and was the parser). Revisit only with a measured
false-negative rate (OQ-2).

**R2 · The Convergence Index** `CI(i) = Novelty·(1-Similarity)·(6-MedianSeverity)/Cost(i)`
(`:166-180`, "Converged when CI < 0.3 AND declining for 3+"). Rejected as a gate input on three
counts: it divides by `Cost(i)` — a second unguarded denominator, and one that is *zero* today
because no cost data exists; it multiplies four quantities of different provenance (two derived,
one model-produced, one metered) so no threshold is interpretable; and "declining for 3
iterations" is a weaker statement than the streak counter it would replace. Retained as an
optional reported metric with every input's provenance labelled.

**R3 · Power-law decay fit** (`:160-164`, "converged when the fit projects < 0.5 expected
findings"). Rejected. Fitting an exponent to 3–14 points and projecting is not auditable by the
human who has to sign the gate, and the corpus's own trajectories are not monotone (four increases
in the S-5.03 series alone), so the fit is over data the same document says is invalid. A streak
counter is auditable by counting.

**R4 · Keeping `novelty <= 0.15` as a termination condition.** Rejected — see §1.4. The live
counter-example is a threshold satisfied by an undefined value.

**R5 · Self-reported confidence and hallucination fingerprinting as gate weights**
(`:46-80`, "findings matching 2+ fingerprints … their weight in the Convergence Index is halved").
Rejected as gate inputs: they are self-reports, and silently halving a weight is unauditable. The
honest version already exists in the same document — code-grounding (`:130-144`) — and it becomes
a *finding* about the finding: an ungrounded finding gets a `grounding` status row, is visible, and
is triaged. Nothing is silently discounted.

**R6 · Keeping the Kani-proved gate reading a JSON file.** Rejected. The 6 proofs at
`validate-per-story-adversary-convergence/src/lib.rs:717-827` are **kept** — they prove the
projection is sound and that is worth having — but re-pointed at a projection over rows. The
proofs never guaranteed the inputs were true, and `passes_clean: 3` sitting beside
`"fix_batches_pending": ["B3","B4"]` is what that gap looks like in production.

**R7 · An LLM evaluator for the 96 prose criteria.** Rejected. It reintroduces the self-attesting
transcript one level up: the evidence would be a model's assertion that a criterion holds. The 96
either get restated in one of the five machine shapes or get `manual: true` with a named owner.
Both are honest; a model verdict dressed as evidence is not.

**R8 · `deferred` as a legal gate status.** Rejected (`validate-wave-gate-prerequisite.sh:138`,
and the sibling hook's error message that recommends it). Replaced by a `deferral` row with owner,
rationale and expiry that blocks its receiving gate — which is the keep-list's own typed mechanism
with accountability attached.

**R9 · One canonical `STATE.md` schema.** Rejected. Picking one of six incompatible schemas
guarantees a seventh. The frontier is rows; `STATE.md` is an L4 render gated byte-exact under
invariant 15. This also disposes of the four size budgets, the `wc -l` HTML comment, and the
12-level source-of-truth precedence in which `STATE.md` outranks every spec.

**R10 · Porting Lobster's `depends_on` + `condition` semantics unchanged.** Rejected: the pair is
unsound without `on_skip`, and 140 edges depend on the resolution. Declaring them is a one-time
cost with a printed list; not declaring them means 26% of the graph resolves by accident.

**R11 · Hooks as the enforcement layer.** Rejected. 62 registered hooks, and the ones that matter
fail open, glob filenames the corpus does not use, or check that files exist. Hooks remain useful
as *notification*; enforcement is a store predicate. This is the spine's V-B applied to L5/L6:
hooks are retirement targets, not integration targets.

**R12 · An external scheduler (cron / systemd timers).** Rejected as the source of truth. Without
a stored `next_due`, a missed window is indistinguishable from a window that never existed —
exactly the `regression-state.json` failure one layer over. An external timer may *drive*
`fa schedule due`; it may not own the state. Multi-project (V-F) settles it: one query beats N
crontabs.

**R13 · Budget enforcement in the driver only.** Rejected. HARD STOP must survive a session
restart, and the corpus's own evidence is that anything living only in a driver's head or in an
unwritten file does not exist at all.

**R14 · Modelling `parallel-foreach` as `parallel`.** Rejected. It iterates a set, and the set is
undeclared (OQ-10). Collapsing the two would silently drop the iteration semantics — the same
class as the review's own list of six step types omitting it.

---

## 5. OPEN QUESTIONS

**OQ-1 · Reviews still have no declared natural key.** `FINDINGS-AS-ROWS.md:117-119` states it:
the key is the corpus-relative path today, which D-C says must never be identity. `converge_pass`
takes an FK to `review`, so **every table in §1.4 is blocked on this.** Candidate declared key:
`(project, cycle, target, pass)`. Needs a uniqueness measurement over the 400 review-typed
documents before it can be adopted — 186 prism files already share the basename
`pr-description.md`, so collision is not hypothetical.

**OQ-2 · Duplicate-linkage recall is unmeasured.** An unlinked-but-actually-duplicate finding
*inflates* novelty, which is the failure direction that matters (it makes a subject look
un-converged, so it is safe-by-default — but it also makes the metric useless). Needs a measured
false-negative rate against a hand-linked sample of the 2,211 existing rows before novelty is
reported at all, let alone used. Recommend: hand-link two full pass chains, publish the number.

**OQ-3 · Is `clean_streak >= 3` right at every level?** `orchestrator.md:113-120` applies 3
uniformly to spec convergence, story convergence, wave convergence, per-story delivery and Phase 5,
with no evidence per level. Three per *story* has 6 Kani proofs behind it; three for a
*whole-system* Phase 5 pass is the same number applied to a perimeter two orders of magnitude
larger. Should the rule be parameterised by `converge_subject.perimeter`? Design leans yes;
there is no data to set the values.

**OQ-4 · Where does the coverage audit's grep run?** `brownfield-ingest/SKILL.md:268` requires a
grep-driven inventory of the **source tree**, not `.factory`. So `fa gate exec` with
`kind='command'` needs a working zone outside the artifact store, which is a permission surface
(what can a criterion read? can it read the walled zone? can it read secrets?). Needs a declared
`working_zone` on the command registry and a rule for the walled case.

**OQ-5 · Bootstrap exemptions under L5-C.** If `error` blocks, a fresh clone with no toolchain
cannot pass its own preflight gate — `planning.lobster`'s environment-setup gate requires all three
model families reachable, and Phase 6 requires Kani/cargo-fuzz/semgrep. A declared bootstrap
exemption set is needed, and that set is itself a security surface: it is the list of criteria that
can be *not evaluated* without blocking. Recommend: exemptions are rows with an expiry, scoped to
`run.status='initialising'`, and reported on every gate.

**OQ-6 · Attestation on cutover day. USER DECISION.** With no resolver, every model-family
criterion is `unverifiable` → blocking, so `phase-4-gate` cannot pass. Three options: (a) ship the
block and require a resolver before Phase 4 (honest, and the criterion has been decorative for the
whole corpus's life); (b) declare the criterion `manual: true` with `owner: orchestrator` so it is
visibly attested rather than silently passed; (c) delete the criterion. **Recommend (b) as the
migration state and (a) as the target**, but this is not a design call.

**OQ-7 · Does the two-phase `(claimed, recounted, delta)` mechanism survive V-A?** Its premise is
that a *claim* exists in prose to be recounted. Under V-A there are no stored claims — that is the
point of invariant 17. Three candidate futures: it becomes an import-time-only gate (which is what
`fa/validate.go:116-167` already is); it retargets at agent *narrative* inside review bodies, where
numbers will still be written by hand; or it retires. The keep-list says preserve it, so retiring
it needs an explicit decision. Recommend the second: narrative claims persist even when artifact
claims do not, and `agents/validate-extraction.md:32`'s anchor (32 files/5279 LOC claimed vs 23
files/3859 LOC recounted) is exactly a narrative claim.

**OQ-8 · Autonomy is unevaluable for at least 20 runs after cutover.** No cost data exists
anywhere; three of five Level-3→3.5 metrics need a 20-run history that has never been retained. So
`AutonomyScore` cannot be computed until 20 runs *after* `cost_event` starts collecting. What is
the interim autonomy level, who sets it, and does the "fast revocation" arm operate on a partial
window (it can: 5 runs arrive sooner than 20, and asymmetric-by-construction is the point)?

**OQ-9 · Evidence retention.** A `kind='command'` evidence row stores stdout. At 38 gates × 278
criteria × N runs × M projects this is the store's dominant growth term. Needs a declared policy:
digest-only after K days? Retain full bytes only for `fail` and for the last `pass` per criterion?
Cap per row? Note the constraint this must respect: `fa evidence replay` needs the *spec*, not the
bytes, so digest-only retention preserves replay while losing the human-readable trail — which is
precisely what POLICY 15 was trying to keep.

**OQ-10 · `parallel-foreach` semantics are undocumented.** 8 uses, and nothing anywhere declares
what the iteration set is (a wave's stories? a glob? a story list from a fact?). Workflow-as-data
cannot round-trip until this is answered, and invariant 15's byte-exact requirement means guessing
is not available.

**OQ-11 · L6 depends on F16 landing first.** If `fa` schedules the loop bodies, `fa` must enforce
the `ctx_rule` exclude sets — otherwise the three adversary perimeters are still prose. That makes
role tokens and `DENIED_BY_WALL` a *prerequisite* for L6's dispatch path, not a parallel
workstream. Sequencing question for the migration plan.

**OQ-12 · Migration of existing regressions under L5-K.** The corpus has undispositioned
monotonicity regressions in live convergence subjects (four in the S-5.03 trajectory alone). Under
L5-K those force `clean_streak = 0` and retroactively un-converge subjects the corpus considers
closed. Backfill dispositions at migration, or open them as baselined findings? **Recommend
findings, baselined with a waiver and an expiry** — consistent with `fa/baseline.go`'s existing
argument that a gate which blocks everything on day one gets switched off, and it keeps the fact
visible instead of writing a rationale nobody held.

**OQ-13 · Two spine-adjacent renames are still pending user decision** (spine V-D), and one of
them affects L5: if `gate:` remains a prism identifier (`gate: wave-3-integration-gate`), then
`gate_def.gate_id` collides with an existing per-corpus field meaning at import. The alias ledger
handles it, but the canonical name needs confirming before `gate_def` is written down. This repo
has been caught by exactly this twice (`gate`, `scope`).
