# HANDOFF — dolt-artifact-spike

## ⭐ CURRENT SNAPSHOT (2026-07-31)

**Active workstream:** research spike — can [Dolt](https://github.com/dolthub/dolt) back a
tool (`fa`) that is the **sole interface to all vsdd-factory artifacts**, replacing the
`factory-artifacts` orphan git branch?

**Status: SPIKE COMPLETE · 3 blocking decisions SETTLED · SCALED to 200 agents · every
decentralised contention fix EXHAUSTED · the cross-internet topology VALIDATED against
GitHub Actions. Verdict GO (phased). 193 of 194 checks, 24 suites**, all re-runnable
against the LIVE vsdd-factory corpus and a REAL GitHub remote. Still **no product code**:
this is a spike, a specification, a decision record, and now a measured scaling +
latency profile. Nothing in vsdd-factory has been changed.

⭐ **THE END STATE IS ONE GO BINARY, `fa`** (user-confirmed 2026-07-31). Everything below
lands as its subcommands — see TOP PRIORITY NEXT item 0.

**Repo state:** `~/Dev/scrap/dolt-artifact-spike`, **local-only git (NO remote — nothing
to push)**, clean. **12 spike passes. HEAD at this wrap = `d0567a4`.**

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

**ONE-LINE RESUME POINTER:** read `research/DECISIONS.md` (the 3 settled calls) →
`research/SPEC.md` (14 invariants) → `research/SCALE.md` + `research/CI-AGGREGATOR.md`
(what scale and the cross-internet topology actually cost). **Nothing is blocking.
The next work is BUILDING PHASE 1 as `fa` Go subcommands.**

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
Resume the dolt-artifact-spike in ~/Dev/scrap/dolt-artifact-spike (local-only git, clean).

READ FIRST, in this order:
  1. HANDOFF.md                    (this file — snapshot + next actions)
  2. research/DECISIONS.md         (the 3 blocking calls, SETTLED: conflict policy, zones, phase-1 scope)
  3. research/SPEC.md              (the spec: architecture, capability surface, 14 invariants, CLI, phasing)
  4. research/ACCESS-PATH.md       (embedded driver vs CLI vs server, measured — and why the headline changed)
  5. research/REMOTE.md            (the real github.com remote: ~10 s per acquire, one data ref per remote)
  5b. research/SCALE.md            (200 agents; EVERY decentralised contention fix, ranked)
  5c. research/CI-AGGREGATOR.md    (CROSS-INTERNET answer: CI as aggregator; 20 writers; ~30s latency)
  6. research/GAP-MATRIX.md        (coverage vs all 46 vsdd-factory artifact types; gaps 1/2/7 now closed)
  7. research/ACCESS-CONTROL.md    (zones + agent identity; what is actually enforceable)
  8. research/ASSESSMENT.md        (the feasibility argument + measured problems; §3g has the scale numbers)
  9. research/LESSONS.md           (every Dolt gotcha + every harness bug that faked a clean result)

RE-SCRAPE THE REFERENCE MATERIAL (beads was in /tmp and is gone):
  gh repo clone gastownhall/beads /tmp/_bd/b -- --depth=1     # pin b1694a5
  # the Dolt patterns worth re-reading in beads:
  #   internal/storage/issueops/lease.go   -> freshRowLock() + the "zombie-merge bug"
  #   PROPOSAL-cas-conditional-update.md   -> their CAS design
  #   docs/architecture/dolt.md            -> embedded vs server, refs/dolt/data
  # vsdd-factory is already local, DO NOT MODIFY:
  ls ~/Dev/vsdd-factory                                       # branch develop @ 82163b7f
  ls ~/Dev/vsdd-factory/.factory                              # the live corpus we tested against
  cat ~/Dev/vsdd-factory/plugins/vsdd-factory/config/artifact-path-registry.yaml   # the 46 artifact types

BOOTSTRAP THE ENVIRONMENT (.venv and poc/*/ are gitignored and disposable):
  brew install dolt && dolt version                          # 2.2.3; NO --user flag in 2.2.x
  python3 -m venv .venv && .venv/bin/pip -q install pymysql  # pymysql is the ONLY dep
  mkdir -p poc/db && (cd poc/db && dolt init --name spike --email spike@local)

RESTART THE TEST SERVER (7 suites need it; the rest self-provision):
  (cd poc/db && dolt sql-server --host 127.0.0.1 --port 3308 &) && sleep 7
  .venv/bin/python poc/fa.py init
  .venv/bin/python poc/fa.py import ~/Dev/vsdd-factory/.factory      # ~13s, 1,959 BCs
  .venv/bin/python poc/graph_import.py ~/Dev/vsdd-factory/.factory   # 1,490 edges + findings
  # verify the 16 original suites (137/137 expected, ~15 min):
  for s in test_spike test_graph test_multimachine test_locking test_serverless_lock \
           test_mutex test_two_devs test_write_api test_render test_schema_evolution \
           test_lifecycle test_asymmetry test_factory_ops test_multi_instance \
           test_zones test_identity; do
    printf "%-24s " $s; .venv/bin/python -u poc/$s.py >/tmp/$s.log 2>&1 \
      && echo "$(grep -cE '^PASS' /tmp/$s.log) passed" || echo FAILED; done
  SCALE_RECORDS=20000 SCALE_COMMITS=150 .venv/bin/python -u poc/test_scale.py

PASS-11/12 SUITES (scale, contention, CI aggregator — all self-provisioning, all
create per-run refs/dolt/* on the test remote and delete them in a finally block):
  .venv/bin/python -u poc/test_stress_fleet.py     # 5/6, ~45 min, 200 agents / 20 clones
  .venv/bin/python -u poc/test_stress_opt.py       # 3/3, ~15 min (O1 lock-ref, O2 spawns, O3 push cost)
  .venv/bin/python -u poc/test_decentral.py        # 5/5, ~45 min (D1 retry shapes .. D5 peer pull)
  gh workflow enable fa-aggregate -R drbothen/dolt-artifact-spike-remote   # cron is OFF
  .venv/bin/python -u poc/test_ci_aggregator.py    # 4/4, ~6 min
  FA_CI_WRITERS=20 FA_CI_BATCH=10 FA_CI_STRESS=1 .venv/bin/python -u poc/test_ci_aggregator.py
  FA_CI_ONLY=c5 FA_CI_LAT_N=3 .venv/bin/python -u poc/test_ci_aggregator.py   # latency
  # knobs: FA_ST_MACHINES/AGENTS/S3_AGENTS · FA_OPT_ONLY=o1 · FA_DC_ONLY=d5 · FA_GT_ONLY=h3,h6
  # the CI workflow lives at poc/workflows/fa-aggregate.yml and is deployed to the
  # test remote's .github/workflows/ — edit BOTH, and lint the YAML locally first

PASS-10 SUITES (embedded driver + the real remote; both self-provision):
  brew install go                                            # 1.26.5; needs Xcode clang for CGO
  cd poc/bench && CGO_ENABLED=1 go build -tags gms_pure_go -o bench . && codesign -s - -f bench
  # -tags gms_pure_go is MANDATORY: without it the cgo build dies on ICU headers
  cd ../.. && .venv/bin/python -u poc/test_embedded.py       # 13/13, ~4 min, own server on 3399
  .venv/bin/python -u poc/test_github_remote.py              # 10/10, ~9 min  (remote mechanics)
  .venv/bin/python -u poc/test_github_topology.py            # 11/11, ~12 min (every file:// scenario, re-run on GitHub)
  # the remote is private: github.com/drbothen/dolt-artifact-spike-remote; needs gh auth
  # each run uses per-run refs/dolt/<run>/* and deletes them in a finally block
  # G10 needs poc/eb/a/fa_cli, so run test_embedded.py first
  # FA_GT_ONLY=h3,h6 re-runs single topology tests while iterating (partial != a result)

OPERATING PRINCIPLES (these earned their place — the spike corrected its own claims
EIGHT times):
  - Measure, don't assume.
  - NEVER infer a consequence from a structural fact. Five of this session's errors were
    exactly that shape: "one git ref => global contention" (it is per-BRANCH), "slow
    pushes => commit churn" (push cost is FLAT in payload), "ticket ordering ~ a queue"
    (it was the WORST arm), "runner startup dominates latency" (it is ~0), "the Go binary
    saves 20-30 s of install" (2 s). Measure the consequence too.
  - Before recommending a lever, measure the ALTERNATIVES to that lever.
  - Never write a verdict into report text that the same test could contradict; derive
    it from the numbers at print time.
  - Never swallow a command's exit code. One `| tail -1` hid a total failure and caused
    an infinite CI re-dispatch livelock (five SUCCESSFUL runs in a row).
  - Report unreproduced anomalies as unreproduced; build node universes only from
    authoritative declaring documents.

STATE: spike complete; 3 blocking decisions settled; scaled to 200 agents; every
decentralised contention fix exhausted; cross-internet topology validated on GitHub
Actions (~30 s median latency). Verdict GO (phased), 193/194 checks, 24 suites.
NO PRODUCT CODE EXISTS YET. The end state is ONE GO BINARY, `fa`.

TASK: build PHASE 1 as `fa` Go subcommands — `fa import` + `fa validate` (gates as SQL),
a DATED BASELINE ALLOWLIST of the 82 existing findings so the CI gate can be switched on
without blocking every PR, a CI job that fails only on NEW violations, and the cross-zone
integrity check D2 makes mandatory. Phase-1 SCOPE is unchanged from DECISIONS D3, but its
"Python, no Go" implementation note is SUPERSEDED: `fa` is Go with the embedded driver
(CGO + `-tags gms_pure_go`). Carry two measured requirements in from the start:
`fa aggregate` must QUARANTINE stuck staging refs, and `fa doctor` must check
WRITABILITY (not openability).
```
