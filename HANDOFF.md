# HANDOFF — dolt-artifact-spike

## ⭐ CURRENT SNAPSHOT (2026-07-30)

**Active workstream:** research spike — can [Dolt](https://github.com/dolthub/dolt) back a
tool (`fa`) that is the **sole interface to all vsdd-factory artifacts**, replacing the
`factory-artifacts` orphan git branch?

**Status: SPIKE COMPLETE. Verdict GO (phased). 137/137 tests, 17 suites, all re-runnable
against the LIVE vsdd-factory corpus.** No product code written — this is a spike plus a
specification. Nothing has been changed in vsdd-factory itself.

**Repo state:** `~/Dev/scrap/dolt-artifact-spike`, **local-only git (NO remote)**, clean.
9 spike passes. HEAD before this wrap = `001f166`.

**Reference repos (both READ-ONLY here; we changed neither):**
| Repo | Where | Pin |
|---|---|---|
| vsdd-factory | `~/Dev/vsdd-factory` (exists, branch `develop`) | `82163b7f` |
| its artifact corpus | `~/Dev/vsdd-factory/.factory` (worktree on `factory-artifacts`) | 3,145 files / 1,959 BCs / 1,607 commits |
| beads (Dolt reference product) | **was `/tmp/_bd/b` — EPHEMERAL, re-clone on resume** | `b1694a5` |
| Dolt | `brew install dolt` | 2.2.3 |

**ONE-LINE RESUME POINTER:** read `research/SPEC.md` → `research/GAP-MATRIX.md` →
`research/ACCESS-CONTROL.md`, then decide the 3 open design questions in TOP PRIORITY
NEXT before writing any `fa` code.

---

## ▶▶▶ TOP PRIORITY NEXT

### Decisions to settle BEFORE building (all three are the user's call)

1. **Conflict-resolution policy — undesigned, and now the biggest gap.** Conflicts
   provably surface (D3, I6, M4) but *who* resolves them, how, and with what authority is
   unspecified. This matters more as instances multiply.
2. **Zone granularity: per-directory or per-table?** **Tier 1 is SELECTED** (tiers 2/3
   are structurally unavailable — Claude Code runs all agents in one OS process). Default
   = per-**directory** zone dirs, no daemon. Per-**table** is still reachable but the
   enforcement point must move out of the DB into the harness (deny `Bash`, allow only
   `fa`, inject the role via a `PreToolUse` hook so the agent cannot forge it) — strictly
   more machinery, so only if genuinely needed. See ACCESS-CONTROL §4.2.
3. **Phase-1 scope sign-off.** Recommended: read-only shadow (`fa import` + `fa validate`
   in CI, markdown stays truth). Catches all 82 findings, zero agent changes, no daemon.

### Then, in order

4. **Benchmark the embedded driver** (`dolthub/driver/v2`, as beads uses it) against the
   `dolt sql` CLI path. **This is the highest-leverage engineering task:** measured spawn
   floor is **141 ms/invocation vs ~0–2 ms/query** (~14,000× for a `COUNT(*)`). The
   embedded driver keeps one handle open under a single mutex hold and gives real
   transactions — it would likely simplify invariant 4 (idempotent retry) out of existence.
5. **Re-verify the identity findings on Linux.** macOS `ps eww` leaks a sibling's env;
   Linux gates `/proc/<pid>/environ` behind `PTRACE_MODE_READ_FSCREDS` (safer). Depends on
   deployment `ptrace_scope`/`hidepid`/dumpable, so it must be run, not reasoned about.
6. **Test push-as-CAS against a REAL network remote (GitHub).** Everything used `file://`,
   so 640 ms/acquire is a floor and auth/partial-failure recovery is untested.
7. **Extract prose-embedded references.** The graph was built from frontmatter only; BC/VP
   bodies also cite ADRs and BCs in prose, so the **38 dangling refs are a floor**.
8. Instance-count ceiling above 12 (disk + push contention is O(N) retries for N pushers).
9. Multi-repo mode (`.factory-project/`) is declared out of scope — revisit if needed.

### Session task list (ephemeral tracker — mirrored here)

All 20 tasks from this session are **✓ complete**: scan factory-artifacts layer · harvest
beads · research Dolt · write assessment · build+test POC · model the full graph · test
graph integrity · multi-machine · write API · render round-trip · schema evolution ·
lifecycle · capability SPEC · 46-type gap matrix · asymmetry walls · wave/state/context/
tasks/templates · multi-instance · scale ceilings · zone design · agent identity.
**Nothing in progress. No WIP, no uncommitted work.**

### Operating principles that must carry over

- **Measure, don't assume.** This spike corrected its own claims four times (see LOG).
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
  13.4 s batched.
- **Claude Code runs ALL agents in ONE OS process** ⇒ no per-agent uid and no fd-passing,
  so access control must be the CLI permission layer (`permissions.deny` + `PreToolUse`
  hooks + per-agent `allowed-tools`), and a walled agent must NOT have unrestricted Bash.

---

## Background / environment state at wrap

- **A `dolt sql-server` was left running on port 3308** (pid 10054 at wrap, cwd
  `poc/db/factory_artifacts`). It will NOT survive a reboot. `test_spike`, `test_graph`,
  `test_write_api`, `test_render`, `test_factory_ops` need it; the others self-provision.
- `poc/*/` Dolt data dirs (~207 MB, largest `poc/db` 186 MB) are **gitignored and
  disposable** — every suite recreates what it needs.
- **Hygiene fixed at wrap:** `poc/td/` Dolt data had been committed in pass 6 *before* it
  was gitignored (gitignore does not untrack). Now `git rm --cached`'d; 30 tracked files,
  all source + docs.
- No background agents or long-running jobs pending. One Perplexity deep-research call
  timed out mid-session; its narrow follow-up succeeded and is cited in ACCESS-CONTROL §5.

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

---

## KICK-START PROMPT (paste this cold)

```
Resume the dolt-artifact-spike in ~/Dev/scrap/dolt-artifact-spike (local-only git, clean).

READ FIRST, in this order:
  1. HANDOFF.md                    (this file — snapshot + next actions)
  2. research/SPEC.md              (the spec: architecture, capability surface, 11 invariants, CLI, phasing)
  3. research/GAP-MATRIX.md        (coverage vs all 46 vsdd-factory artifact types + the 3 findings that changed the design)
  4. research/ACCESS-CONTROL.md    (zones + agent identity; what is actually enforceable)
  5. research/ASSESSMENT.md        (the feasibility argument + measured problems; §3g has the scale numbers)
  6. research/LESSONS.md           (every Dolt gotcha + every harness bug that faked a clean result)

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
  # verify all 17 suites (137/137 expected, ~15 min):
  for s in test_spike test_graph test_multimachine test_locking test_serverless_lock \
           test_mutex test_two_devs test_write_api test_render test_schema_evolution \
           test_lifecycle test_asymmetry test_factory_ops test_multi_instance \
           test_zones test_identity; do
    printf "%-24s " $s; .venv/bin/python -u poc/$s.py >/tmp/$s.log 2>&1 \
      && echo "$(grep -cE '^PASS' /tmp/$s.log) passed" || echo FAILED; done
  SCALE_RECORDS=20000 SCALE_COMMITS=150 .venv/bin/python -u poc/test_scale.py

OPERATING PRINCIPLE: measure, don't assume. This spike corrected its own claims four
times. Report unreproduced anomalies as unreproduced. Build node universes only from
authoritative declaring documents.

STATE: spike complete, verdict GO (phased), 137/137. No product code exists yet.

TASK: settle the three open decisions in HANDOFF "TOP PRIORITY NEXT" (conflict-resolution
policy · zone granularity per-directory vs per-table · phase-1 scope), then benchmark the
embedded dolthub/driver/v2 against the CLI path — the 141 ms spawn floor vs ~0–2 ms query
cost is the single biggest engineering lever and may remove an invariant.
```
