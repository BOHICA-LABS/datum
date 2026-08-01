# HANDOFF — dolt-artifact-spike

## ⭐⭐⭐ SESSION SNAPSHOT — 2026-07-31 (wrap at `6341ab2`) — READ THIS FIRST

**Seven commits. The type registry was BUILT, ported into `fa`, and the knowledge graph got a
real projection engine.** Everything below is measured; every claim has a repro command.
`~/Dev/vsdd-factory`, `prism` and `rivetry` were **READ-ONLY the whole session** (verified: 0
files modified after 21:00).

| commit | what |
|---|---|
| `902da9d` | **THE REGISTRY** — 103 canonical types + 16 gap + 4 retired, 14 closed enums, 180 aliases, change-management package, validator (exit 0) |
| `30f7057` | **#671's exit criterion RUN** — prose extraction worth 21.8%, derived-data 25.3%, 37.9% beyond any parser |
| `d58b77c` | **`fa validate --registry`** — registry embedded in the binary, **67/67 rule parity** with the Python validator |
| `e62665b` | **Namespace reconciliation (story 1)** — the disagreement is **2**, not 17 |
| `6cc25cc` | **All four things taken from #671** folded in + machine-checked |
| `8713636` | **Knowledge-graph projection** (gonum) + `waves`/`graph metrics|dot|diff` + benchmarks |
| `c4d59d0` | **Centrality hypothesis TESTED** — betweenness loses to free degree; comes off the plan |
| `6341ab2` | **CSR engine** for 250k+ — 96× less memory, ~100× faster, parity-verified |

### The state in one screen

| | |
|---|---|
| Registry | `fa/registry/{artifact-type-registry,enums,aliases}.yaml` — the ONE canonical copy, `go:embed`'d into `fa` AND read by the Python tooling |
| `fa` | **62 tests · 9 benchmarks**, ~3.5 s, no network, no `dolt` binary |
| Gate on live corpus | **6,864 findings** (153 store-side + 6,711 registry-side), all baselined; ratchet proven (planted violation → exit 1 naming it) |
| Graph | **2,421 nodes · 4,060 edges**, CSR at **0.1 MB**; 148 stories in **16 waves**; **0 dependency cycles**; 50 articulation points |
| Repo | local-only, **NO remote**, clean at `6341ab2` |

### ⚠ FIVE CORRECTIONS TO MY OWN CLAIMS THIS SESSION — carry these forward

1. **"The standard already exists / ~12 legacy spellings."** True by mass, false by vocabulary.
   **Two** declared standards (path registry 46 `artifact_type` vs templates 81
   `document_type`, overlapping on **11**), and **181** non-canonical values over 1,138 files —
   but **108 appear exactly once**, so alias the head and gate the tail.
2. **"Split `verdict` into `gate`."** `gate:` is ALREADY a prism identifier
   (`gate: wave-3-integration-gate`). Field is **`gate_result`**. Same trap hit again with
   **`scope`** (prism already uses PR-LEVEL/LOCAL/spec) — measure a field name before claiming it.
3. **"17 namespace defects."** One boolean stood for THREE defects. Real:
   name_disagreement **2** · path_missing 4 · template_missing 11.
4. **"Betweenness is single-digit ms / fine at 10×."** 236 ms at 2.4k, **52 s at 24k**. Then the
   hypothesis test showed it is the **WORST** predictor (AUC 0.725) vs free **degree** (0.871).
   Measuring the alternative deleted the planned work rather than sizing it.
5. **"`topo.BiconnectedComponents` exists in gonum."** It does not. Articulation points are
   hand-rolled Hopcroft–Tarjan, pinned by 7 hand-worked cases + CSR parity.

### ▶▶▶ TOP PRIORITY NEXT — the session ended cleanly here; NOTHING is in flight

**Session task list: all 8 tasks ✓ COMPLETED. No WIP, no uncommitted work, nothing running.**

**NEXT ACTION, in this order (the F-\* measurement set it):**

1. **STORY 7 — make the indexes derived, via `shadow → proven → retired`.**
   **The highest-value single change: 25.3% ±9.1 of the adversary's findings**, eliminated
   rather than detected. All 23 derived types already ship at `derivation_stage: shadow`.
   Do NOT flip them: generate alongside the authored form, every disagreement a finding, and
   advance only on evidence. Targets by churn: `BC-INDEX` (218 commits), `STORY-INDEX` (381),
   `ARCH-INDEX` (151), `VP-INDEX` (140), `cycles/INDEX` (98), `epic.story_count`.
   Expect the first shadow diffs to be INFORMATIVE, not clean — the corpus asserts four
   different BC totals.
2. **STORY 4 — mint `adversarial-finding` as rows.** A template exists and **nothing uses it**;
   findings are prose tables inside review bodies. This is the enabler for `finding_count`,
   `severity_distribution` and `total_findings` becoming derived.
3. **STORY 12 — prose-reference extraction.** 21.8% ±8.7. Everything it needs is now declared:
   9 `prose_ref_kinds`, 7 `prose_ref_rules`, `pin_policy` on all 23 link types, and CSR to hold
   the section nodes. **Three rules are load-bearing or it manufactures false findings:**
   exclude code spans (`ADR-099` is an example CLI arg), resolve as-of through `id_alias`
   (`BC-1.12.008` was legitimately renumbered to `BC-3.05.004`), and report
   `unresolvable`-owner refs separately from `dangling`.
   ⚠ **This is also the 250k-node driver** — sections + sub-artifact ids is ~100k nodes from
   the existing 6,537 md files. CSR landed first deliberately.

**Smaller, known, not urgent:**
- Store loaders use `s.Strings()`/`s.Pairs()`, which materialise whole result sets — **stream
  them before 250k**.
- `graph dot` is meaningless above a few thousand nodes → make `--scope` mandatory past a bound.
- Precompute+store metrics per commit (`graph_metric(commit,node,measure,score)`) — now much
  less urgent, since the shipped measures are milliseconds.

**⛔ BLOCKED ON USER AUTHORIZATION (all need write access to vsdd-factory / GitHub):**
- The **2 namespace renames** (`story-spec`→`story`, `state`→`pipeline-state`) that close story 1.
  `validate_registry.py` prints **EXIT CRITERION NOT MET: 2** until they land.
- **Opening the ADR** and registering the policy.
- **Answering #671** on the issue. It is an open, unbuilt proposal by another author that the
  chosen direction now contradicts; leaving it silently contradicted is the worse outcome.

### The four settled one-way doors (user, 2026-07-31) — do not relitigate

- **D-A** prose = verbatim `body` bytes **+ a derived ordinal-keyed section partition**, gated
  byte-exact (`concat(sections)==body`, measured 0 mismatches / 6,537 files). Ordinal keys, never
  headings: 110 docs carry 1,968 duplicate `##`+ headings.
- **D-B** store **gitignored**, synced via `refs/dolt/data`; rendered markdown **committed** as
  the review surface AND offline backup ⇒ **NEW INVARIANT 15: `import(render(store)) == store`**, gated.
- **D-C** per-type declared natural key; `path` is a **UNIQUE DERIVED** column, never identity
  (1,852 BC renames, 0 deletes); plus an **`id_alias` ledger** so renumbering keeps history valid.
- **D-D** `verdict` **RETIRED** → `gate_result` / `convergence` / `severity_max`; `status`
  narrowed to **lifecycle only**.

### Operating principles that earned their place THIS session

- **Measure the alternatives to a lever before pulling it.** It deleted sampled+parallel
  Brandes entirely (degree predicts better, for free).
- **Never report a number a test could contradict.** Two benchmarks measured NOTHING and said
  so plausibly: the F-\* extractor found 11 findings from 1 file (v1 knew 1 of 3 formats), and
  `BenchmarkCSRWavesReal` timed an early return (1.1 µs at 240k). Both now pinned by tests.
- **Never collapse exit 1 and exit 2.** Caught twice: a bad `--registry` path, and a bad
  `--as-of` ref that produced an EMPTY graph reported as "+2,421 nodes added".
- **A regex must not cross block boundaries.** A non-greedy match assigned 17 of 17
  `namespace_status` values to the WRONG types while parsing cleanly.
- **Parity, not inspection.** 67/67 rules Go-vs-Python; CSR-vs-gonum on hand-worked answers AND
  generated graphs.

---

## ⭐ CURRENT SNAPSHOT (2026-07-31)

**Active workstream:** research spike — can [Dolt](https://github.com/dolthub/dolt) back a
tool (`fa`) that is the **sole interface to all vsdd-factory artifacts**, replacing the
`factory-artifacts` orphan git branch?

**Status: SPIKE COMPLETE · 3 blocking decisions SETTLED · SCALED to 200 agents · every
decentralised contention fix EXHAUSTED · the cross-internet topology VALIDATED against
GitHub Actions. Verdict GO (phased). 193 of 194 checks, 24 suites**, all re-runnable
against the LIVE vsdd-factory corpus and a REAL GitHub remote. (**Superseded on the
"no product code" point** — phase 1 shipped on 2026-07-31; see the block at the top.) Nothing in vsdd-factory has been changed.

⭐ **THE END STATE IS ONE GO BINARY, `fa`** (user-confirmed 2026-07-31). Everything below
lands as its subcommands — see TOP PRIORITY NEXT item 0.

**Repo state:** `~/Dev/scrap/dolt-artifact-spike`, **local-only git (NO remote — nothing
to push)**, clean. **12 spike passes + the phase-1 build. HEAD = `e4db2ad`**
(`fa/fa`, the 148 MB binary, is gitignored — rebuild it, see the top block).

**Reference repos (both READ-ONLY here; we changed neither):**
| Repo | Where | Pin |
|---|---|---|
| vsdd-factory | `~/Dev/vsdd-factory` (exists, branch `develop`) | `82163b7f` |
| its artifact corpus | `~/Dev/vsdd-factory/.factory` (worktree on `factory-artifacts`) | 3,145 files / 1,959 BCs / 1,607 commits |
| beads (Dolt reference product) | **`/tmp/_bd/b` — EPHEMERAL, re-clone on resume** | pin `b1694a5`; a `--depth=1` clone now lands on `9fddc56` |
| Dolt | `brew install dolt` | 2.2.3 |
| Go — NEW, only for the embedded harness | `brew install go` | 1.26.5 + Xcode clang (CGO) |
| **test remote** | `https://github.com/drbothen/dolt-artifact-spike-remote` (PRIVATE, ours) | seeded `main`; suites create per-run `refs/dolt/*` and delete them in a `finally`. **Swept clean at wrap** — only `main` + Dolt's `__dolt_remote_info__` remain |
| **the CI aggregator workflow** | DEPLOYED at `.github/workflows/fa-aggregate.yml` in that test remote; source of truth copied to `poc/workflows/fa-aggregate.yml` here | **active, dispatch-only — the cron sweep is COMMENTED OUT** so an idle repo doesn't run forever. Re-enable the cron to test that layer. `/tmp/ciwork` was the scratch clone used to edit it — EPHEMERAL, re-clone if needed |

**ONE-LINE RESUME POINTER:** phase 1 is BUILT — read `fa/README.md` first, then
`research/DECISIONS.md` (the 3 settled calls) → `research/SPEC.md` (14 invariants) →
`research/SCALE.md` + `research/CI-AGGREGATOR.md` (what scale and the cross-internet
topology actually cost). **Nothing is blocking. The next work is DEPLOYING the phase-1
gate into vsdd-factory and ratcheting its baseline down.**

---

## ▶▶▶ TOP PRIORITY NEXT

### The three blocking decisions are SETTLED — `research/DECISIONS.md`

1. **Conflict-resolution policy — DESIGNED (D1).** `fa` never auto-resolves. Abort
   mechanically on any conflict (invariant 2), record it in an append-only `conflict`
   table, and the **loser of the push race re-applies its intent as a validated write**
   (`--reapply | --take-theirs | --take-mine`); cross-actor collisions escalate to the
   orchestrator; and **a conflict inside a leased scope is reported as a lease-scoping
   defect**, because that is what it is. Only mutable record cells can conflict at all —
   derived data and append-only tables structurally cannot.
2. **Zone granularity — per-DIRECTORY, ratified (D2).** Tier 1 remains the only
   enforceable option, and two new measurements strengthen it: a zone opens in ~25 ms
   in-process and one process can hold both handles (so the ~144 ms per-zone cost
   objection is gone), and an embedded `fa` needs no `dolt` binary (so "deny `Bash`,
   allow only `fa`" becomes practical). **New required deliverable:** a cross-zone
   integrity pass in `fa validate`, since splitting zones removes that FK (A6).
3. **Phase 1 — SIGNED OFF (D3).** Read-only shadow: `import` + `validate` in CI, markdown
   stays truth, **plus a dated baseline allowlist of the 82 existing findings** — without
   it the gate blocks every PR on day one and gets switched off. Python + `dolt sql -f` in
   ONE transaction; the corpus import lands at **0.9 s**. No Go, no remote, no daemon,
   zero blast radius.

### Then, in order

0. ⭐ **THE END STATE IS ONE GO BINARY, `fa`.** Everything lands as its subcommands.
   Settled consequences: the embedded `dolthub/driver/v2` is **THE** access path (so
   **no `dolt` CLI dependency anywhere, including CI**); `fa aggregate` is the
   aggregator, which makes the Actions-outage fallback "any dev runs the same binary";
   and **DECISIONS D3's "phase 1 = Python, no Go" is SUPERSEDED** (phase-1 SCOPE is
   unchanged — only language + access path). Build costs are fixed and non-negotiable:
   CGO, **`-tags gms_pure_go` MANDATORY** (else the build dies on ICU headers), 155
   indirect deps, ~147 MB binary, its own pinned Dolt build separate from the CLI's.

4. **BUILD PHASE 1.** Nothing blocks it now. Deliverables: `fa import`; `fa validate` with
   the gates as SQL (W8); the dated baseline of 38 dangling refs + 44 type violations; a
   CI job that fails on *new* violations only; and D2's cross-zone check.
   **Exit criterion into phase 2:** baseline at zero (or each item explicitly waived)
   **and** the gate has caught ≥1 real regression in a real PR.
   ⚠ **Two features that measurement made mandatory, do not drop them:**
   (a) **`fa aggregate` must QUARANTINE a stuck staging ref** — attempt count + backoff,
   or move it to `refs/dolt/quarantine/*`. A conflicted ref is re-fetched and re-merged
   on EVERY run today (measured 17 s then 8 s of pure waste with nothing new to do);
   at 20 stuck refs it dominates the job and the backlog only grows. Retention is
   right; unbounded RE-ATTEMPT is not. (b) **`fa doctor` must check WRITABILITY, not
   openability** — a second opener of a Dolt directory silently becomes read-only.
5. **Extract prose-embedded references.** The graph was built from frontmatter only; BC/VP
   bodies also cite ADRs and BCs in prose, so the **38 dangling refs are a floor**.
6. **Re-verify the identity findings on Linux.** macOS `ps eww` leaks a sibling's env;
   Linux gates `/proc/<pid>/environ` behind `PTRACE_MODE_READ_FSCREDS` (safer). Depends on
   deployment `ptrace_scope`/`hidepid`/dumpable, so it must be run, not reasoned about.
   Low priority — tier 1 does not depend on the answer.
7. ~~**Instance-count ceiling above 12**~~ — **MEASURED at 200 agents / 20 clones
   (`research/SCALE.md`).** Correctness holds absolutely (S6: 247/247 rows, 0 missing,
   0 dupes, 0 dangling FKs after 200 concurrent writers + 9 merges). Contention is
   per-BRANCH, and because the artifact store is ONE branch it is global for artifacts —
   but it is **solved decentrally by AGGREGATION** (new invariant 13): a local `file://`
   relay + `flock` collapses a host's instances to 1 push (17 s); staging refs +
   an aggregator collapse hosts to 1 (64 s); peer `--remotesapi-port` pull does it in
   25 s at the cost of a listener per writer. Backoff tuning makes contention WORSE
   (159 -> 185 -> 193 attempts). **No central server is needed for contention.**
8. ⭐ **THE END STATE IS A SINGLE GO BINARY, `fa`** (user-confirmed 2026-07-31). Everything
   above lands as ITS subcommands. Consequences: the embedded `dolthub/driver/v2` path is
   now the access path (not a phase-3 option), so there is **no `dolt` CLI dependency
   anywhere — including CI**; `fa aggregate` is the aggregator, which makes the
   Actions-outage fallback "any dev runs the same binary" rather than a parallel script;
   and **DECISIONS D3's "phase 1 = Python + dolt sql -f, no Go" is SUPERSEDED** and needs
   rewriting. Build costs are fixed: CGO, `-tags gms_pure_go` mandatory, 155 indirect
   deps, ~147 MB, its own pinned Dolt build.
9. Multi-repo mode (`.factory-project/`) is declared out of scope — revisit if needed.
10. **Offered and NOT chosen:** a DoltLite-from-Rust spike. DoltLite is a shipped C library
    (SQLite fork, prolly tree, `dolt_*` functions and `dolt_log`/`dolt_diff_*` virtual
    tables, v0.11.38, bindings for Python/Ruby/Node/WASM/Swift/Android but **not Rust**),
    so Rust *can* embed it via `rusqlite` — but it is a **different engine and on-disk
    format** whose remotes are `.doltlite` files or an HTTP `doltlite-remotesrv`, not the
    project's git remote. That makes it an architecture decision, not a language one.
    Dolt itself has **no C API and no Rust bindings**
    ([dolt#8953](https://github.com/dolthub/dolt/issues/8953) is open), so the embedded
    measurement can only be made from Go.

### Session task list (ephemeral tracker — mirrored here)

**No task-tracker entries were used this session; the narrative below IS the record.**
Passes 10 → 12b were all completed in one session (2026-07-31). Nothing is in progress,
no WIP, no uncommitted work, and no background jobs were left running.

Pass 12 / 12b (CI aggregator) **✓ complete**: built + deployed the `fa-aggregate`
workflow to the test remote · proved `GITHUB_TOKEN` can create/update/DELETE
`refs/dolt/*` · proved `repository_dispatch` reaches it and `on: push` never would ·
`concurrency:` = the merge slot for free · conflicting writer isolated with its ref
retained · **strand defence held against a REAL cancelled pending run** · stressed at
20 writers × 10 agents (publish FLAT in N) · **measured end-to-end latency: median
30 s** · found the ONE required fix (quarantine stuck refs) · new invariant 14 ·
`research/CI-AGGREGATOR.md`.

Pass 11 (scale + contention) **✓ complete**: 200-agent fleet on the real remote (5/6, S6
proves ZERO lost writes) · found contention is per-BRANCH · **exhausted every
decentralised contention fix** (D1-D5, O1-O3) · aggregation collapses 20 writers to 1
push · backoff measured HARMFUL · `research/SCALE.md` + invariant 13.
**Still open: nothing blocking. A central-instance comparison is the next optional step,
and it is now an argument about READ latency and intra-host concurrency ONLY — contention
no longer motivates it.**

Pass 10 tasks all **✓ complete**: benchmark the embedded driver (13/13) · add the missing
`BEGIN`/`COMMIT` control that overturned the pass-9 headline · settle the three decisions ·
real-GitHub-remote MECHANICS suite (10/10) · **port every `file://` scenario onto the real
remote (11/11) — merge semantics, the wedge, the 2×4-agent topology, the 8-agent lease,
counters, staleness, instance graduate/abandon, schema merge, 8-clone contention** ·
answer the Rust/DoltLite question · update SPEC / GAP-MATRIX / ASSESSMENT / LESSONS.
**Nothing in progress. No WIP.**

### Operating principles that must carry over

- **Measure, don't assume.** This spike corrected its own claims **eight** times (see LOG).
- **Never infer a consequence from a structural fact.** Three of this session's errors
  were exactly that: 'one git ref ⇒ global contention' (wrong, it is per-branch),
  'slow pushes ⇒ commit churn' (wrong, push cost is flat in payload), and 'ticket
  ordering ≈ a queue' (wrong, it was the WORST arm). Measure the consequence too.
- **Before recommending a lever, measure the alternatives to that lever.** Pass 9 called
  the embedded driver "the single biggest engineering lever" from a spawn-vs-query ratio.
  Pass 10 measured the thing neither side had tested — the transaction boundary — and the
  headline moved to a `BEGIN`/`COMMIT` the CLI already supports.
- **Report unreproduced anomalies as unreproduced** — don't promote them to findings.
- **Node universes come from authoritative declaring docs**, never grep-over-everything
  (otherwise every reference resolves trivially and integrity checks prove nothing).
- Never use `INSERT IGNORE` when testing FK enforcement — it downgrades violations to
  warnings and fakes a clean result.

---

## What was found (the substance, so resume doesn't re-derive it)

**The premise held:** `.factory/` is a hand-maintained relational database implemented in
markdown, and it is measurably failing at what a DB gives free.

- The live corpus asserts **four different BC totals** (1949 / 1955 / 1959 / 1962) — the
  frontmatter and body of `BC-INDEX.md` disagree by 6.
- **38 dangling references + 44 type violations** no gate catches, e.g. `S-8.09` declares
  it blocks 19 stories that were never written; `BC-4.NN.001` placeholders and
  `"see PO output for actual IDs"` sitting in structured traceability fields.
- **90.2% of BCs have no verifying VP**; subsystem SS-10 has 58 BCs and zero.
- The factory lock is a YAML block inside `STATE.md` with a **TOCTOU race the skill
  documents itself** (CWE-367).

**Architecture that emerged (see SPEC §1):** one clone **per factory instance** on branch
`factory/<instance>`, a `flock` write mutex per clone, per-scope leases, `dolt push`
non-fast-forward rejection as the cross-machine arbiter, Dolt cell-level merge to
reconcile, trust zones as separate database **directories**, markdown as a generated
export. **No daemon, no new hosting** — Dolt rides `refs/dolt/data` in the project's own repo.

**Hard-won gotchas (full list in ACCESS-CONTROL + the memory file):**
- Dolt has **no row locking** and merges **cell-by-cell** ⇒ guarded-UPDATE + affected_rows
  is NOT a safe CAS on a server; `fence = fence + 1` fails 30/30. Needs a per-attempt
  **random** token. Under the single-clone mutex the tax disappears.
- **Checkout is per-clone** (cross-branch reads work, writes don't) ⇒ clone-per-instance.
- An unresolved merge conflict **wedges the whole machine** — every later commit fails with
  `cannot merge with uncommitted changes`, which blames staging, not the conflict.
- Cost is per **invocation**, not per write: 1,959-BC import = 531 s per-statement vs
  13.4 s batched — **and then 0.9 s if that batch is wrapped in one transaction** (pass 10).
- **Claude Code runs ALL agents in ONE OS process** ⇒ no per-agent uid and no fd-passing,
  so access control must be the CLI permission layer (`permissions.deny` + `PreToolUse`
  hooks + per-agent `allowed-tools`), and a walled agent must NOT have unrestricted Bash.

**What pass 10 added (`research/ACCESS-PATH.md`, `research/REMOTE.md`):**
- **The real lever was a transaction, not the access path.** `dolt sql -f` autocommits per
  *statement*; wrapping the same file in `BEGIN`/`COMMIT` is 17–23× (15.7–18.5 s → 0.8–0.9 s).
  Per-statement autocommit costs the same ~5 ms in BOTH the CLI and the embedded driver.
- **Embedded driver, honestly:** ~2× on cold start (70 ms vs 136 ms — the engine opens
  either way), ~4,000× warm on a held handle (0.03 ms vs 132 ms per question), real
  cross-statement transactions, and **no `dolt` binary needed at all** (branch/merge/gc/
  `DOLT_PUSH` all work in-process). Costs: Go + **CGO**, `-tags gms_pure_go` mandatory
  (else the build dies on ICU headers), 155 indirect deps, 147 MB binary, and its own
  pinned Dolt build separate from the CLI's.
- **It does NOT remove the mutex.** A second opener of the same directory silently becomes
  **read-only** and fails later with `cannot update manifest: database is read only` — so
  `doctor` must check *writability*, and `fa` embedded + `dolt sql` cannot share a directory.
- **Real remote (github.com):** an acquire is **~10 s**, not 640 ms; an acquire+release
  pair ~20 s ⇒ push-as-CAS is a phase-gate mechanism only. **Payload size is irrelevant** —
  a 2-row database and the 33 MB corpus both push in ~10 s, and the corpus clones back in
  **2.2 s** (onboarding/DR is cheap).
- **New invariant 12:** all Dolt branches live in ONE git ref, so push contention is
  **global across instances**; `--ref` per instance decouples it but forfeits remote-side
  cross-instance merge.
- **No Rust path to embedded Dolt.** Dolt has no C API and no Rust bindings; only DoltLite
  (a separate C engine) is embeddable from Rust.

---

## Background / environment state at wrap

### ⭐ THIS WRAP (2026-07-31, `b96a668`) — environment facts

- **Nothing is running.** No `dolt sql-server`, no background builds, no agents. Verified.
- **No WIP.** Working tree clean at `b96a668`; the session task tracker is empty.
- **This repo has NO git remote** — local-only, so there is nothing to push, ever.
- **`~/Dev/vsdd-factory` and the 9 sibling corpora were READ-ONLY all session.** vsdd's
  `git status` shows 2 modified files + 1 untracked, all dating from **2026-05-30 and
  2026-07-23** — pre-existing, NOT from this session (verified by mtime).
- **Rebuild `fa/fa`** — the 148 MB binary is gitignored (39.5 s cold build).
- **Disposable `/tmp` ephemera from this session, all safe to delete / recreate:**
  `/tmp/fadb` + `/tmp/fadb_final` (fa stores built from the live corpus), `/tmp/fahist`
  (a 2-commit store used for the diff experiment — carries a FULLTEXT index added by
  hand), `/tmp/corpus_v2` + `/tmp/corpus_regress` (COPIES of the corpus used to plant
  regressions — the live corpus was never touched), `/tmp/_bd/b` (the beads clone at
  `35ccd0d`; re-clone with `gh repo clone gastownhall/beads /tmp/_bd/b -- --depth=1`.
  ⚠ the handoff's `b1694a5` pin is NOT reachable in a `--depth=1` clone).
- **Every finding is folded into the research docs** — no log file needs to survive.

### Earlier passes (still accurate)

- **No `dolt sql-server` is running at this wrap.** The 7 server-dependent suites
  (`test_spike`, `test_graph`, `test_write_api`, `test_render`, `test_factory_ops`, …) need
  one started per the kick-start prompt; the other 12 self-provision. `test_embedded.py`
  starts and stops its own server on port 3399.
- `poc/*/` Dolt data dirs are **gitignored and disposable** — every suite recreates what it
  needs. Pass 10 added `poc/eb/` (~150 MB) and `poc/gh/` (~40 MB) plus the 147 MB
  `poc/bench/bench` binary; **all three are gitignored** (the `.go`/`go.mod`/`go.sum`
  sources are tracked). Tracked tree stays source + docs only.
- **Go was installed this session** (`brew install go`, 1.26.5) purely to build the embedded
  harness. Reversible with `brew uninstall go`. Nothing else depends on it.
- **A GitHub repo was created:** `drbothen/dolt-artifact-spike-remote` (**private**), seeded
  with one commit on `main`. It holds `refs/heads/__dolt_remote_info__` (Dolt's own
  bookkeeping branch) permanently; per-run `refs/dolt/run-*` refs are deleted by the suite
  itself in a `finally` block. Auth is the `gh` git credential helper — **no token is
  written to disk or into any URL, and none is in the repo.**
- **No background agents or long-running jobs pending at this wrap** (verified: no
  `test_*` processes alive). Several long suites ran in the background during the
  session; their logs were in `/tmp/*.log` and are EPHEMERAL — every finding has been
  folded into the research docs, so the logs are not needed.
- **Disposable, gitignored, must be rebuilt on resume:** `poc/bench/bench` (141 MB Go
  binary — rebuild per the kick-start), and the Dolt data dirs `poc/eb` 197 MB,
  `poc/st` 201 MB, `poc/gh` 47 MB, `poc/opt` 16 MB, `poc/gt` 14 MB, `poc/dc` 4 MB,
  `poc/ci` 1 MB (~480 MB total). Every suite recreates what it needs.
- **`/tmp` ephemera that will NOT survive:** `/tmp/_bd/b` (the beads clone — re-clone
  per the kick-start) and `/tmp/ciwork` (the scratch clone of the test remote used to
  edit the CI workflow; the workflow's source of truth is committed here at
  `poc/workflows/fa-aggregate.yml` and is already DEPLOYED to the test remote).

---

## LOG

| Date | Commit | What |
|---|---|---|
| 2026-07-31 | `6341ab2` | **CSR ENGINE for 250k+ nodes.** Two int32 arrays + keys interned in ONE byte slab, ids in SORTED key order so `Lookup` is a binary search and NO `map[string]int32` is retained (~80 MB at 1M nodes saved). **MEASURED 96× less memory** (240k nodes: gonum 756.5 MB → CSR **7.9 MB**; live corpus **0.1 MB**; ~33 MB vs ~3.1 GB at 1M) **and ~100× faster** (articulation 240k: 980 ms → **8.1 ms**; SCC 240k 4.6 ms; waves 240k 710 → 121 ms). Parallel edges preserved. **NO Brandes ported** — betweenness was measured off the critical path. gonum retained for Louvain only. **Correctness by PARITY**: 7 hand-worked articulation cases + generated graphs at 50/500/2400 (node/edge counts, per-node degree, articulation set, SCC count), waves layering, dangling, parallel-edge survival. **A benchmark that measured NOTHING, caught:** waves reported 1.1 µs at 240k because `synthProjection` makes no `story` nodes, so `Waves()` returned immediately — now pinned by `TestSynthStoriesActuallyProducesWaves`. `fa graph build` + `fa waves` run on CSR. 62 tests, 9 benchmarks |
| 2026-07-31 | `c4d59d0` | **CENTRALITY HYPOTHESIS TESTED — AND BETWEENNESS LOST.** Betweenness existed for the claim that propagation misses cluster on high-betweenness nodes. Measured against 2,138 extracted findings, AUC = P(flagged outranks unflagged), 231 flagged vs 2,190 unflagged: **degree 0.871 (O(E), FREE) · pagerank 0.843 (16 ms@24k) · betweenness 0.725 (~52 s@24k)**. The cheapest measure predicts BEST and betweenness is ~3,000× the cost. ⇒ sampled Brandes, parallel Brandes and Brandes-over-CSR all came **OFF the critical path**; `degree` promoted into default metrics; CSR's scope shrank to memory. New `fa graph centrality` (CSV) + `Degrees()`. **Caveat recorded:** the proxy is "id mentioned in a finding" and well-connected artifacts get discussed more, so degree's edge is partly tautological — that weakens "centrality predicts risk" but NOT "betweenness isn't worth 52 s" |
| 2026-07-31 | `8713636` | **KNOWLEDGE-GRAPH PROJECTION** over gonum (pure Go — no CGO fight) + `fa waves` and `fa graph build|metrics|dot|diff`. Node identity from the REGISTRY's declared key; `multi.DirectedGraph` NOT `simple` (simple permits one edge per (u,v) and would have silently collapsed story→BC via behavioral_contracts AND traces_to); dangling = an edge whose head is undeclared. Live: 2,421 nodes/4,060 edges, 148 stories in 16 waves, 0 SCCs>1, 50 articulation points, 11 Louvain communities. **TWO OF MY THREE SPEED CLAIMS REFUTED:** betweenness is 236 ms at 2.4k (not "single-digit ms") and **52.2 s at 24k** (not "probably fine at 10×") ⇒ opt-in + bounded, REFUSED not silently skipped. **REAL BUG FOUND BY BENCHMARKING:** gonum's dense `PageRank` allocates 47 MB/call on a sparse graph; `PageRankSparse` is **197× faster, 43× less memory** ⇒ default `graph metrics` 577 ms → 73 ms. **`topo.BiconnectedComponents` DOES NOT EXIST** — articulation points hand-rolled Hopcroft–Tarjan, iterative, 7 hand-worked tests. **Third silent failure caught:** a bad `--as-of` ref produced an EMPTY projection reported as "+2,421 nodes added", exit 0 → now a ref probe, exit 2. `research/GRAPH-PERF.md` |
| 2026-07-31 | `6cc25cc` | **ALL FOUR THINGS TAKEN FROM #671**, each machine-checked (validator 1j–1m + 3 Go tests). (1) **`generate → prove equal → retire`** — new `derivation_stage` on all **23** derived types, all at `shadow`; story 7 was a one-way flip on BC-INDEX/STORY-INDEX and is now a ratchet. (2) **WRITE-TIME enforcement** — new `enforcement_point`, and `block` enforced only in CI is now a rejected CONTRADICTION. (3) **VERSION-PINNED citations** — new `pin_policy` on all 23 link types + `index_cite` (floating ⇒ lag IS a finding) and `reviewed_version` (pinned ⇒ lag is CORRECT); same syntax, opposite verdicts, which is why it had to land BEFORE prose extraction. (4) **`impact`** the reverse closure + a `query_verbs` catalogue with a declared growth path. NOT taken (with reasons): the Rust crate/no-DB architecture, in-memory petgraph, "not git-diffable". Already held stronger: #671's cannot-be-stale virtue IS invariant 15. **Defect caught:** `link_types` held a rules LIST beside entry MAPS → untypeable in Go, a test discarded the error, and a parse failure surfaced as a nil deref. Hoisted to `link_rules` |
| 2026-07-31 | `e62665b` | **NAMESPACE RECONCILIATION (story 1) — the disagreement is 2, not 17.** One boolean stood for THREE unrelated defects: `name_disagreement` **2** (`story`/`story-spec`, `pipeline-state`/`state`) · `path_missing` 4 · `template_missing` 11. Only the first two are namespace defects. **A full file merge would be WRONG** — the path registry is deliberately COARSER (`cycle-document` serves 8+ types), so requiring a unique path per type would force 8 invented subdirectories ⇒ `shared_path_patterns`, and story 1 shrinks to TWO renames. `namespace_reconciliation` declares resolution_rule (the `document_type` name WINS) + all 4 categories + the 4 path-registry-only entries + a validator-CHECKED exit criterion. **Second self-caught defect:** a non-greedy regex matched flag lines belonging to LATER type blocks and mis-assigned 17 of 17 values while parsing cleanly — caught by PRINTING the groups, fixed with block-scoped editing |
| 2026-07-31 | `d58b77c` | **`fa validate --registry` — ONE GATE, NOT TWO.** `fa/registry/*.yaml` is the ONE canonical copy: `go:embed`'d into the binary AND read by the Python tooling. **67/67 rules agree EXACTLY** with the Python validator on vsdd-factory (6,711 registry findings each). Getting there fixed THREE defects: (1) **three states not two** — `blocks: []` is a DECLARATION of none vs an absent key; Go called empty lists missing, Python called BLOCK-STYLE lists missing (it never parsed `key:\n  - item`); (2) **inline YAML comments** — `verification_properties: []  # ...` read as non-empty, found by a parity diff off by EXACTLY ONE FILE; (3) **exit 1 vs 2 collapse** — a bad `--registry` path validated ZERO files while exiting non-zero from the store gates. Ratchet proven end-to-end (baselined → 0, planted invented type → 1 naming it, `--strict` → 1, bad path → 2). `baseline write --registry` was ALSO required or every registry finding reads as new next run. Tests 24 → 43 |
| 2026-07-31 | `30f7057` | **#671's EXIT CRITERION RUN AT LAST.** Hand-classified random sample (n=100 of 1,894 cleaned findings, seed 2026; 87 real after 13 turned out to be closure rows): **registry+fa already address 40.2% ±10.3** (derived-data 25.3% + frontmatter 14.9%) · **prose extraction 21.8% ±8.7** · **beyond ANY parser 37.9% ±10.2** (external 13.8 + process 12.6 + semantic 11.5). ⇒ #671 is PARTLY RIGHT: registry GAINS `prose_ref_kinds` (9 kinds) + 5 rules, an ADDITION not a redesign; and **story 7 goes BEFORE story 12** since derived-data elimination is worth more AND eliminates rather than detects. The 37.9% belongs in the ADR: nothing here replaces adversarial review. **4th parser-lost-input caught:** v1 of the extractor knew 1 of 3 finding formats and ran on 8 docs/cycle → **11 findings, all from ONE file**, 0.3% of the data. v2 covers all three forms over 390 docs. Keyword rules classified only 33%, so the headline is HAND-classified and committed for audit. `research/FSTAR-COMPARISON.md` |
| 2026-07-31 | `902da9d` | **THE TYPE REGISTRY BUILT** (the session's headline deliverable). 103 canonical types + 16 gap types + 4 retired, each declaring key · required fields · enums · link types · section schema · shape · authority · gate severity · enforcement_level · profile; 14 closed vocabularies; 180 aliases carrying `set:` FIELD DEFAULTS (a rename-only map would destroy the scope/reviewer_role the 12 adversarial-review spellings encoded); a change-management package (ADR + policy + stories + graduation ladder + 7 hazards); a validator that exits 0. **FIVE FINDINGS:** two declared standards overlapping on 11 · enforcement gap by MASS but design gap by VOCABULARY (181 values/1,138 files; 22/71, 32/150, 27/51 distinct) · the tail is 108 SINGLETONS · the 12 review spellings encode real dimensions · **`delta-archive` (211 rivetry files, created by rivetry's own POLICY-22) and `input-hash` (3,890 files, admits "spurious DRIFT") exist ONLY because there is no versioned store ⇒ RETIRED**. **SEVEN defects the validator caught in my own registry**, incl. `bc_id`/`vp_id` required → 2,577 FALSE findings (ids live only in filenames) and `priority` bound to `severity_max` → 391 false findings on legitimate `P1` |
| 2026-07-31 | `b96a668` | **CROSS-CORPUS: ten `.factory` corpora compared** — prompted by "look at prism". **THE DRIFT IS METHOD-GENERATED:** vsdd-factory vs prism, same factory, `document_type` 6 spellings each with only **2 of 12 shared**, `verdict` with **ZERO** shared values. **The spine is SMALL** (`cycles` 10/10, `specs` 10/10, `logs` 9/10, `planning` 8/10, `code-delivery`+`stories` 7/10; `BC-S.SS.NNN` 11/12 but `S-N.NN` only 2/12). **28 singleton dirs track PRODUCT TYPE** (rivetry UI/SaaS: `design-system`/`ui-evidence`/`brand`/`ux`; prism security: `test-strategy`/`security-review`). **vsdd-factory is an OUTLIER** — 1,961 BCs = 7.2× the next, its `holdout-evaluations/` uniquely named AND empty vs `holdout-scenarios/` in 7, prism's flat-with-slug BC names are vsdd's own identity violation, and 151 prism files sit in 4 `specs/` dirs the path registry never declares. **METHOD CORRECTION: corverax is NOT the biggest corpus** — 9,274 of 9,291 files are `semport/` scratch and its BC dir holds ONE file; counting files ≠ counting artifacts. `research/CROSS-CORPUS.md` |
| 2026-07-31 | `3ce3aa1` | **PROBE `cycles/` + harvest beads.** **GAP-MATRIX §2.7 OVERTURNED** (banner added): 481/611 prose files carry frontmatter with keys, links AND counts. The class is **three shapes** — ~568 write-once immutable docs, nine append-only ledgers (`burst-log`/`decision-log`/`lessons`, 600+ append commits) that a ROW model strictly improves, and a DERIVED `INDEX.md`. **The worst case is the easiest to model.** Real blockers are general: composite keys (18 basenames collide, ALL with different content), **as-of resolution** (`BC-1.12.008` was legitimately renumbered; `ADR-099` is an example CLI arg — a flat check manufactures false findings), section-scoped semantics. **Dolt does FULLTEXT** (0.15 s / 1,959 bodies) ⇒ no new query language. NOT established: `finding_count` drift (all 6 comparable docs agree; 5 first-run 'mismatches' were dict-vs-Counter artefacts, caught pre-publish). `research/PROBE-CYCLES.md` + `research/BEADS-PROSE.md` (beads stores prose in 4 typed columns, has NO document table, NO markdown rendering, gitignores the DB, and decays prose LOSSILY — unusable for an authoritative corpus) |
| 2026-07-31 | `e4db2ad` | **PHASE 1 BUILT — first product code.** `fa` as a Go binary (`fa/`, embedded `dolthub/driver/v2`, CGO + `-tags gms_pure_go`, 148 MB, 39.5 s cold build): `import` (live corpus in **1.1-1.4 s**, ONE transaction, idempotent, FK rejections recorded as findings) · `validate` (**0.15 s**, every gate a query: W8's gates + a count-assertion gate + index enumeration + prefix agreement + scalar refs + dependency direction + **D2's mandatory cross-zone pass**, ids and counts only) · a **dated 153-finding baseline** that ratchets · `doctor` probing **WRITABILITY not openability** (verified against a real read-only second opener: `cannot update manifest: database is read only`, while the schema check passed on the same store) · the **`fa aggregate` quarantine policy** as pure tested code (bounded attempts, run-counted backoff, move to `refs/dolt/quarantine/*`, and an unmergeable lineage quarantined on the FIRST failure per invariant 14) · a CI workflow that fails on NEW findings only · 24 tests in 3.3 s with no network and no `dolt` binary. **PARITY PROVEN** against the Python prototype: identical records + universes, the 82 import-path findings match RULE FOR RULE, edge sets diffed row by row. **Gate proven to FAIL**: a dangling ref planted in a COPY of the corpus → exactly 1 new finding, exit 1; live corpus → exit 0. **CORRECTIONS #9-10:** the corpus graph has **1,509 edges, not 1,490** (the prototype's parser treated a prose value with an unbalanced `[` as an unterminated inline list, swallowing every key after `BC-INDEX`'s `last_amended` — hiding `total_bcs: 1955` from the count gate and 19 real edges across six S-15.x stories; THIRD instance of the parser-loses-input class, now pinned by a regression test), and **"1962 distinct BC ids" depends on its extraction rule** (first column of the enumeration table = 1,959, which agrees with disk). `fa/README.md` |
| 2026-07-30 | `e2620e0` | Pass 1: assessment + POC store; 13/13. Found the 4-way count drift, 3 dangling refs, the lock TOCTOU |
| 2026-07-30 | `f6762d1` | Pass 2: full relationship graph (1,490 edges) + multi-machine; 27/27. **Fixed 2 of my own bugs that faked clean results** (frontmatter parser dropped all list edges; `INSERT IGNORE` suppressed FK violations) |
| 2026-07-30 | `5002d16` | Pass 3: locking + **CORRECTION** — pass-1's "16 acquirers, one wins" was right by accident (`fence+1` is the documented anti-pattern) |
| 2026-07-30 | `76af355` | Pass 4: no central server needed — push-as-CAS; 38/38 |
| 2026-07-30 | `3415c1f` | Pass 5: single clone + `flock` mutex is the recommended topology; 46/46 |
| 2026-07-30 | `39c91b5`, `ac48116` | Pass 6: two devs × 4 agents × 1 repo; 55/55. Four disciplines the topology imposes |
| 2026-07-30 | `2da29cd` | Pass 7: `research/SPEC.md` + write-API / render / schema / lifecycle; 87/87 |
| 2026-07-30 | `11f0da3`, `b723569` | Pass 8: `research/GAP-MATRIX.md` vs all 46 registry artifact types; asymmetry + factory-ops + multi-instance; 112/112 |
| 2026-07-30 | `7f36c27`, `001f166` | Pass 9: scale + zones + identity; `research/ACCESS-CONTROL.md`; 137/137. **Corrected my prediction that macOS hides process envs — it does not** |
| 2026-07-31 | `700a776`, `7379abf` | Pass 12: **CI AS THE AGGREGATOR = the cross-internet answer, 4/4.** Only staging-refs survives dispersed writers (a relay needs a shared FS; peer-pull needs INBOUND TCP to laptops behind NAT). `GITHUB_TOKEN` can create/update/DELETE `refs/dolt/*`; `repository_dispatch` reaches the workflow and `on: push` never fires for `refs/dolt/*`; **`concurrency:` IS the merge slot for free**, retiring the lock-ref and its TTL/break-glass/unique-sha costs. Conflicting writer ISOLATED with its ref retained; **strand defence held against a REAL `cancelled` pending run**. **NEW INVARIANT 14:** writers must be CLONES of the artifact branch — unrelated lineages fail `no common ancestor` and can NEVER be merged, so per-instance-ref fragmentation is a ONE-WAY DOOR. Six CI gotchas incl. a LIVELOCK I caused by swallowing a failed `git push` rc. `research/CI-AGGREGATOR.md` |
| 2026-07-31 | `acad904` | Pass 12b: **stressed the aggregator at 20 writers × 10 agents (5/5)** — publish FLAT in N (14 s vs 13 s at N=4), 190/190 rows landed. **Found the one real flaw:** a conflicted staging ref is re-fetched and re-merged on EVERY run (17 s then 8 s wasted with nothing to do) ⇒ `fa aggregate` MUST quarantine. **Measured END-TO-END LATENCY: median 30 s** (27/44/30), ~22 s irreducible because the ~8 s push cost is paid TWICE. **Corrected two of my own estimates** — "~1-2 min, runner-startup-dominated" (really ~30 s, startup negligible) and "the Go binary saves 20-30 s of dolt install" (it saves 2 s) |
| 2026-07-31 | `cad9144` | Pass 11: SCALE + CONTENTION. 200 agents / 20 clones / real remote: **S6 = 247/247 rows, 0 missing, 0 dupes, 0 dangling FKs** after 200 concurrent writers + 9 merges. **CORRECTIONS #6-8:** contention is per-BRANCH not per-ref (so `--ref`-per-instance is inapplicable to a single-branch store); slow pushes were CONCURRENCY not churn (a push costs the same for 1 commit as 50); and backoff/ticket ordering make contention WORSE (159 → 185 → 193 attempts), not better. **Exhausted the decentralised option space** — aggregation (`file://` relay + flock per host, 17 s; staging refs + aggregator, 64 s; peer remotesapi pull, 25 s) collapses 20 writers to ONE push, so **no central server is needed for contention**. New invariant 13; `research/SCALE.md` |
| 2026-07-31 | `71ca16a`, `dd5fec0` | Pass 10: embedded-driver benchmark (13/13) + **real GitHub remote: 10/10 mechanics AND 11/11 ported `file://` scenarios** + the three decisions settled (`research/DECISIONS.md`, `ACCESS-PATH.md`, `REMOTE.md`); 171/171. **CORRECTION #5 — pass 9's "the embedded driver is the single biggest engineering lever" was wrong: the lever is a missing `BEGIN`/`COMMIT`, worth 17–23× and available from the CLI.** Also: invariant 6 restated, new invariant 12 (one git ref per remote ⇒ global push contention), and the embedded path does NOT remove the write mutex |

---

## KICK-START PROMPT (paste this cold)

```
Resume the dolt-artifact-spike in ~/Dev/scrap/dolt-artifact-spike (local-only git, NO remote,
clean at d564f36; the work itself is 902da9d..6341ab2).

READ FIRST — ONLY THESE FOUR:
  1. HANDOFF.md TOP BLOCK              (7 commits, the 4 settled doors, 5 self-corrections)
  2. registry/README.md                (the standard: what it declares + what running it says)
  3. research/FSTAR-COMPARISON.md      (#671's exit criterion RUN: 40% / 22% / 38% split —
                                        this is what ORDERS the remaining stories)
  4. research/GRAPH-PERF.md            (the graph engine, every number measured, incl. the
                                        two speed claims it refuted and the CSR tables)

  Then as needed: registry/CHANGE-MANAGEMENT.md (ADR + policy + 16 stories + hazards) ·
  research/STANDARDIZATION.md · CROSS-CORPUS.md · PROBE-CYCLES.md · SPEC.md · DECISIONS.md ·
  LESSONS.md · BEADS-PROSE.md · GAP-MATRIX.md · fa/README.md

REBUILD AND RE-VERIFY (the 148 MB binary is gitignored):
  cd fa && CGO_ENABLED=1 go build -tags gms_pure_go -o fa .   # BOTH flags mandatory
  CGO_ENABLED=1 go test -tags gms_pure_go ./...               # 62 tests, ~3.5s
  cd .. && python3 registry/validate_registry.py              # exit 0; prints the 3-way
                                                              # namespace split + all checks
  ./fa/fa init --db /tmp/fadb && ./fa/fa import --db /tmp/fadb ~/Dev/vsdd-factory/.factory
  ./fa/fa validate --db /tmp/fadb --registry ~/Dev/vsdd-factory/.factory   # 6,864 findings
  ./fa/fa graph build --db /tmp/fadb      # CSR: 2,421 nodes / 4,060 edges / 0.1 MB
  ./fa/fa waves --db /tmp/fadb            # 148 stories, 16 waves, 0 cycles

REFERENCE CORPORA — LOCAL and READ-ONLY. DO NOT WRITE until the standard is agreed:
  ~/Dev/vsdd-factory/.factory   (pin 0aaba144)   ~/Dev/prism/.factory   (95b90d003)
  ~/Dev/rivetry/.factory        (2aea395)
  ~/Dev/vsdd-factory/plugins/vsdd-factory/templates/            # the 81 document_types
  ~/Dev/vsdd-factory/plugins/vsdd-factory/config/artifact-path-registry.yaml   # the OTHER 46
  gh issue view 671 -R drbothen/vsdd-factory                    # unanswered; see below
  ⚠ prism is ACTIVELY WORKED BY ANOTHER SESSION (its corpus advanced 20 files at 09:34-19:18
    and 24 more at ~23:42-23:46 on 2026-07-31, NONE of it from this work). Every number here
    was measured at the pins above, so RE-RUN measure_types.py + observe.py before trusting
    any prism count. vsdd-factory and rivetry were static throughout.

TASK — in this order, because the F-* measurement set it:
  1. STORY 7: make the indexes DERIVED via shadow -> prove equal -> retire. Worth 25.3% +/-9.1
     of the adversary's findings, ELIMINATED not detected. All 23 derived types already sit at
     derivation_stage: shadow. DO NOT FLIP THEM — generate alongside, every disagreement a
     finding, advance only on evidence. Expect the first diffs to be informative, not clean:
     the corpus asserts FOUR different BC totals.
  2. STORY 4: mint `adversarial-finding` as ROWS. A template exists and NOTHING uses it;
     findings are prose tables inside review bodies. Enabler for finding_count /
     severity_distribution / total_findings becoming derived.
  3. STORY 12: prose-reference extraction, 21.8% +/-8.7. Everything needed is declared
     (9 prose_ref_kinds, 7 prose_ref_rules, pin_policy on all 23 link types, CSR for the
     section nodes). THREE rules are load-bearing or it manufactures false findings: exclude
     code spans, resolve as-of through id_alias, and report unresolvable-owner refs separately
     from dangling. This is ALSO the 250k-node driver (~100k section nodes).

  Known and not urgent: stream the store loaders (Strings/Pairs materialise whole result sets)
  before 250k; make `graph dot --scope` mandatory past a bound; precompute+store metrics per
  commit (now cheap, so low priority).

BLOCKED ON THE USER (all need write access to vsdd-factory / GitHub — ASK, do not assume):
  - the 2 namespace renames (story-spec->story, state->pipeline-state) that close story 1;
    validate_registry.py prints "EXIT CRITERION NOT MET: 2" until they land
  - opening the ADR + registering the policy
  - answering #671 (an open, unbuilt proposal by another author that this direction contradicts)

DO NOT RELITIGATE the four settled one-way doors (D-A prose = body bytes + derived ordinal
section partition, gated byte-exact; D-B gitignored store + committed render + invariant 15
import(render(store))==store; D-C declared natural keys, path is derived and never identity,
plus an id_alias ledger; D-D verdict retired -> gate_result/convergence/severity_max and
status = lifecycle only).

OPERATING PRINCIPLES (each one earned by a real error in this repo):
  - Measure, don't assume. NEVER infer a consequence from a structural fact.
  - MEASURE THE ALTERNATIVES TO A LEVER BEFORE PULLING IT. This deleted sampled+parallel
    Brandes outright: free `degree` predicts adversary findings BETTER (AUC 0.871) than
    betweenness (0.725) at ~1/3000 the cost.
  - Never report a number a test could contradict. TWO benchmarks measured NOTHING and said so
    plausibly this session (an extractor that knew 1 of 3 formats -> 11 findings from 1 file;
    a waves benchmark timing an early return -> 1.1us at 240k nodes). Both now pinned by tests.
  - Never collapse exit 1 (gate failed) and exit 2 (fa failed). Caught twice more this session.
  - Before claiming a field name, MEASURE whether it is already in use with another meaning
    (`gate` and `scope` both were).
  - A regex must not cross block boundaries: one mis-assigned 17 of 17 values while parsing
    cleanly. Print the resulting groups; don't trust the edit.
  - Parity, not inspection: 67/67 rules Go-vs-Python, CSR-vs-gonum on hand-worked answers AND
    generated graphs.
  - When a derived number is off by a little, CHASE it (an off-by-ONE-file diff exposed an
    inline-YAML-comment parsing bug).
  - Counting files is not counting artifacts. State the extraction rule with any count.

STATE: registry BUILT + embedded in fa + validated against 3 corpora (67/67 parity) ·
#671's exit criterion RUN · all four #671 borrowings folded in and machine-checked ·
knowledge-graph projection + CSR engine (96x less memory, ~100x faster) shipped ·
62 tests / 9 benchmarks green · corpora untouched · nothing in flight, no WIP, nothing running.
```
