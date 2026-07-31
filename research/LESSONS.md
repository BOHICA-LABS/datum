---
title: LESSONS — Dolt gotchas and harness bugs that faked clean results
date: 2026-07-30
purpose: everything that cost time in this spike, so it costs nobody time again
---

# Lessons

Two kinds of thing, and the second kind matters more:

1. **Dolt behaviours** that are surprising and load-bearing.
2. **Bugs in my own test harness that produced FALSE PASSES.** These are the dangerous
   ones — a test that passes for the wrong reason is worse than no test.

---

## 1. Dolt behaviours (verified, with the test that pins each one)

### Concurrency — the big one

| Behaviour | Consequence | Test |
|---|---|---|
| **No row locking.** `SELECT … FOR UPDATE` parses but does not block. Docs: *"Row-level locks are not supported."* `LOCK TABLES` is also a no-op. | Pessimistic locking is unavailable. Use a unique-token CAS or `GET_LOCK`. | `test_locking` L2 |
| **Merges cell-by-cell.** Same row + different columns → both survive silently. | Great for parallel agents (D2). Fatal for counters. | `test_two_devs` D2 |
| **Identical cell writes COALESCE.** All contenders get `affected_rows = 1` and all "win". | `UPDATE … WHERE guard` is **not** a safe CAS. | `test_cas_patterns` P1 |
| **`fence = fence + 1` is the documented ANTI-pattern.** Concurrent snapshots compute the same next value → merges. | 30/30 trials, all 6 writers won. Use a fresh **random** token. | `test_cas_patterns` P2 |
| **A `PRIMARY KEY` is not concurrency control.** Two writers inserting byte-identical rows merge. | Naive ID allocation gave `[1,1,1,1,1,1]`. Allocators need a per-attempt token. | `test_locking` L4 |
| **1213 / 1205 is the loser's signal**, not a lock deadlock. Clients MUST retry from a fresh transaction. | Treat 1213 as "lost the race", not as an error. | diagnostic |
| **`GET_LOCK` is real** (go-mysql-server LockSubsystem) but **session-scoped — dies on disconnect**. | Fine for a short critical section; unusable as a 45-min lease. | `test_locking` L5 |
| **An unresolved merge conflict WEDGES the clone.** Every later commit AND pull by any agent fails. ⚠ **The two errors read differently:** a `commit` says `tables [x] have unresolved conflicts from the merge` (accurate), a `pull` says **`cannot merge with uncommitted changes`** (blames staging, not the conflict). | Every agent MUST `merge --abort` on conflict — one careless agent downs its dev's fleet. And `doctor` must test for a half-merge explicitly, not trust the error text an agent happens to hit first. | `test_two_devs` D8; localised in `test_github_topology` H3 |

Dolt's own framing: issue [#7681](https://github.com/dolthub/dolt/issues/7681) calls the
conflict detection *"too lenient"*; the strict "No row merge" mode is unimplemented.
beads names the bug the **"zombie-merge bug"** and fixes it with a random `row_lock` cell
plus a retry wrapper (`internal/storage/issueops/lease.go`).

### CLI and operational

| Behaviour | Consequence |
|---|---|
| **Dolt 2.2.x REMOVED `--user`/`--password` from `sql-server`.** Create users via `CREATE USER`/`GRANT`. | Cost a failed startup; will bite CI. |
| **`dolt commit -am` does NOT stage here.** Use `dolt add -A` then `dolt commit -m`. | Silent `no changes added to commit`; broke 3 tests in `test_two_devs`. |
| **Parse with `-r csv`.** The default box format's header row gets read as data. | Produced `holder='holder'` and a false failure. |
| **`dolt push` HANGS FOREVER against a recreated remote** (stale remote-tracking state), at 0% CPU. | Wrap every push in a timeout. Silent-hang is the worst CI failure mode. |
| **A fresh `dolt clone` has NO author identity.** `dolt pull` makes a merge commit, so every pull fails `Author identity unknown`. | Clone provisioning MUST set `user.name`/`user.email`. This made one test *pass for the wrong reason*. |
| **Merge conflicts need `autocommit` OFF** to resolve via `dolt_conflicts`. | Error 1105 otherwise. |
| **Checkout state is PER-CLONE.** Cross-branch reads work (`SELECT … AS OF 'branch'`); cross-branch writes are refused (`table doesn't support UPDATE`). | Forces **one clone per factory instance**. |
| **Cost is per INVOCATION, not per query.** `SELECT 1` = 141 ms; 50 `COUNT(*)` over 20k rows in one invocation ≈ 0 ms each. Spawn is ~14,000×. | Batch a unit of work into ONE session, or use the embedded driver. |
| **`dolt sql -f` autocommits per STATEMENT.** Wrapping the same file in `BEGIN; … COMMIT;` is **17× faster** (15.7 s → 0.9 s for the corpus). Per-statement autocommit costs ~5–7 ms in BOTH the CLI and the embedded path — the identical number. | There are TWO taxes. Batching into one process removes only the outer one; the order of magnitude is the transaction boundary. |
| **`dolt remote add <https github url>` is auto-detected as a GIT remote** and rewritten to `git+https://…`. The documented url schemes (http/https/aws/gs/file) never mention it. `--ref` sets the data ref (default `refs/dolt/data`). | Dolt data can ride the project's own GitHub repo. Auth comes from the git credential helper. |
| **ALL Dolt branches live inside ONE git ref.** Pushing a new Dolt branch creates no new git ref; it rewrites the single data ref. | A fresh unrelated database pushing to an existing data ref is a non-fast-forward. ⚠ **But do NOT infer global contention from this — I did, and it was wrong.** Measured at scale: contention is per-BRANCH (10 clones on one branch = 54 attempts; 10 clones on distinct branches in the SAME ref = 1 each). `--ref` per instance is inapplicable to a single-branch artifact store anyway. | `test_stress_fleet` S2/S5 |
| **Dolt refuses a git remote with zero branches.** | Seed the repo with a real commit on `main` before adding it as a Dolt remote. |
| **`dolt push` writes hundreds of `\r` spinner frames** ("Uploading…") to stderr. | Strip `\r` before parsing or logging, or the output is unreadable. |
| **Parallel `dolt clone` needs one cwd EACH.** Dolt spools into `<cwd>/.dolt/tmp/nbs-spool-*`, so N clones sharing a parent directory collide there and fail with `no such file or directory`. | Give every parallel clone its own parent dir. Cost a whole run. | `test_stress_opt` |
| **A push costs the same for 1 commit as for 50** (7.6 s vs 7.9 s), and `dolt gc` does not change it. ssh is *slower* than https (8.6 vs 7.7 s); the embedded driver's `DOLT_PUSH` is the same 7.7 s. | The ~8 s is protocol round-trip cost. The ONLY lever is pushing fewer times — batching is 48× per commit. | `test_stress_opt` O3, `test_decentral` D4 |
| **Backoff makes push contention WORSE.** immediate retry 159 attempts/746 s; exponential+jitter 185/1007 s; ticket order 193/894 s. | The pointer advances N times regardless; sleeping lets MORE pointers move while you wait, so you return staler. Optimistic retry cannot be tuned — only exclusion or aggregation helps. | `test_decentral` D1 |
| **A second embedded/serving process makes the directory read-only to the CLI**, so a writer that serves itself over `--remotesapi-port` cannot also be written by `dolt sql`. | A self-serving writer's own agents must go through its server — which is why beads uses a server *within* a site. | B9/B10, D5 |
| **`DOLT_PULL` in-process needs an explicit branch** when the remote is not the configured upstream (`Error 1105: …did not specify a branch`). | Always pass the branch to remote procedures. |
| **A shared `--data-dir` exposes sibling databases** and permits `SELECT … FROM other.tbl`. | Trust zones must be separate DIRECTORIES, and dolt must run with `cwd` = one zone. |
| **`1/0` returns NULL**, it does not raise. | Don't use it to simulate a failure in a transaction test. |
| **`CAST(2.0 AS CHAR)` → `'2'`**, dropping the `.0`. | Version bumps need explicit MAJOR.MINOR parsing, not arithmetic on the string. |
| **macOS has no `timeout`** (that's `gtimeout` from coreutils). | Use in-language timeouts. |

### The embedded driver (`dolthub/driver/v2`)

| Behaviour | Consequence |
|---|---|
| **Requires CGO *and* `-tags gms_pure_go`.** A bare `CGO_ENABLED=1 go build` dies with `unicode/regex.h: file not found` — go-mysql-server links ICU by default under cgo. `CGO_ENABLED=0` builds a stub that refuses at runtime. | beads pins exactly this tag and documents the trap in `engdocs/ICU-POLICY.md`. Without it, nothing builds. |
| **A second process opening the same directory succeeds as READ-ONLY**, then fails at write time with `cannot update manifest: database is read only`. It does not refuse to open. | Single-writer per directory. A long-lived `fa` that opens early and writes later can be silently read-only for its whole life — `doctor` must check **writability**, not openability. |
| **The `dolt` CLI and an embedded process cannot write one directory concurrently** — the CLI gets the same read-only manifest error. | A migration cannot run `fa` embedded and `dolt sql` side by side without one mutex covering both. |
| **It carries its own Dolt build** (`dolthub/dolt/go v0.40.5-…`), independent of the installed CLI. 155 indirect modules, 147 MB binary. | Two independently-versioned engines over one on-disk format. Pin both. |
| Remote ops **do** work in-process: `DOLT_PUSH` to GitHub succeeded from the driver. | An embedded `fa` needs no `dolt` binary at all — that is the strongest argument for it. |
| macOS: the built binary should be `codesign -s - -f`'d. | beads does this in its Makefile. |

**There are no Rust bindings for Dolt and no C API** — the embedded driver is Go.
[dolthub/dolt#8953](https://github.com/dolthub/dolt/issues/8953) tracks "export as a
C library" and "compile to WASM"; neither has shipped. Rust can drive Dolt only via
the CLI (subprocess) or the MySQL wire protocol to `dolt sql-server` (the `mysql`
crate is officially supported, and DoltHub published a Diesel guide). The embedded
path that *is* reachable from Rust is **DoltLite** — a shipped SQLite fork in C
(prolly tree below `btree.h`, full `sqlite3_*` API plus `dolt_*` functions and
`dolt_log`/`dolt_diff_*`/`dolt_history_*` virtual tables, v0.11.38, official
Python/Ruby/Node/WASM/Swift/Android bindings but **no Rust one**; `rusqlite`
linking `libdoltlite` is the obvious route). It is a **different engine and
on-disk format** from Dolt, pre-1.0, and its remotes are `.doltlite` files or an
HTTP `doltlite-remotesrv` — not the project's git remote. So it is an architecture
decision, not a language decision.

### Platform (researched + cited, not assumed)

- **macOS: `ps eww` / `ps -E` DO expose a same-uid sibling's full environment.** So env is
  not a safe credential channel. (I predicted the opposite — see §2.)
- **Linux is safer:** `/proc/<pid>/environ` is gated by `PTRACE_MODE_READ_FSCREDS` via
  `ptrace_may_access()`, **not uid equality**
  ([man proc_pid_environ(5)](https://man7.org/linux/man-pages/man5/proc_pid_environ.5.html)).
  With Ubuntu's default `ptrace_scope=1` only ancestors qualify. `hidepid` layers on top.
- **`/proc/<pid>/fd` sockets are inspect-only** (`readlink` → `socket:[inode]`), so fd
  inheritance remains a boundary on Linux
  ([man proc_pid_fd(5)](https://manpages.ubuntu.com/manpages/questing/ru/man5/proc_pid_fd.5.html)).
- Both still need an empirical Linux re-run: the outcome depends on `ptrace_scope`,
  `hidepid`, and the dumpable flag — deployment settings, not language semantics.
- **Claude Code runs ALL agents in ONE OS process** (`ps` shows one `claude` pid parenting
  every Bash call) ⇒ no per-agent uid, no fd to inherit.

---

## 2. My own harness bugs that produced FALSE PASSES

Recorded because each one made a test lie, and the same traps are waiting for the real
implementation.

| Bug | What it faked | How it was caught |
|---|---|---|
| **Frontmatter parser skipped lines starting with whitespace or `-`** | Dropped **every list-valued edge** in the corpus. `bc_trace` came back empty and I reported the graph as "unmigrated" rather than "unparsed". | Reading a real VP file and seeing `bcs: [...]` |
| **`INSERT IGNORE` downgrades FK violations to warnings** | Reported **zero dangling references**. The exception handler never fired. | The DI universe count (16) disagreeing with references (18) while showing 0 rejections |
| **`fence = fence + 1` in the lock** | Pass-1's headline "16 acquirers, exactly one wins" was **right by accident** — a unique `holder` value saved it, not the fence. | Isolating the pattern in `test_cas_patterns` P2 |
| **Read-back on the same connection inside an open transaction** | Saw its own uncommitted writes and "proved" atomicity that hadn't happened. | Asserting `committed=False` and getting `True` |
| **Multi-line inline lists truncated** (`blocks: ["S-8.11",` wrapped) | Hid 19 of 27 dangling story references. | A `too large for column` error on the fragment |
| **Bold-ID regex anchored to `$`** | Silently lost `DI-017`/`DI-019`, whose lines carry an `_(v1.2 — amended …)_` suffix after the closing `**`. | Universe count 16 vs 18 declared |
| **Tests not idempotent** | Second run failed with `nothing to commit` because the value was already set. | Re-running a green suite |
| **`chmod 000` left in place after a test** | Broke the two following tests with `PermissionError`. | Cascading failures |
| **Non-idempotent retry** (re-running an `INSERT` that already applied, then bailing) | Stranded the earlier attempt's commit, which the next reset discarded — **lost a row**. | 7 of 8 rows landing |
| **`pass_fds` preserves the fd NUMBER**, it does not renumber to 3 | The child read the wrong descriptor and the fd test failed. | Child produced no output |
| **`git rm --cached` aborts entirely if ANY path is untracked** | Silently untracked nothing while reporting success. | `git ls-files` still listing the data |
| **`.gitignore` does not untrack already-committed files** | `poc/td/` Dolt data stayed in the repo for 3 passes after being ignored. | Wrap-time audit |
| **Test ordering: cloning before pushing** | Cloned an empty remote; `rc=1` went unasserted. | Reading the detail line |
| **`graph_import.py` TRUNCATES edge tables** | A later test's edge, created by an earlier test, had vanished. | `inbound refs=0` |
| **Splitting a DDL file on `;`** | Comment blocks precede statements, so "skip chunks starting with `--`" skips real DDL — and a *trailing* comment can itself contain a `;` (`-- CAP-008 etc; NULL = unassigned`), which cuts a statement in half. Created an empty database that still had a valid `dolt log`. | `syntax error at position 324 near 'NULL'` |
| **Conclusion text written alongside the assertion, not derived from it** | The B12 detail line read "=> both directions work" while the check was FAILING. The verdict prose was authored at the same time as the test, so it survived the failure. | Reading my own FAIL output |
| **Measuring the wrong axis and generalising** | The spike measured spawn-vs-query, found 14,000×, and concluded the access path was the biggest lever. It never measured the TRANSACTION boundary — which turned out to be the actual 17× and is available from the CLI. The headline recommendation was wrong for a whole pass. | Adding the one control (`BEGIN`/`COMMIT` around the same batch file) |
| **A retry budget of 1 turned a data-loss test into a race test** | H6 was meant to reproduce D5's silent lost increment. With `tries=1` the losing agent simply *bailed* on push rejection, so only one write ever landed and the counter was trivially "correct" — the test FAILED while Dolt was behaving exactly as documented. The bug needs the unsafe retry shape (merge and re-push WITHOUT recomputing) to be modelled explicitly. | The failing assertion said `LOSSY=False` with only 1 of 2 agents reporting success — the agent output, not the assertion, gave it away |
| **Asserting a claim the same test measures and contradicts** | H3's verdict text said the wedge fails "with an error that points at the wrong thing" while the line above it printed `blames staging: False`. Both were in the same output. Re-probing found the misleading message really does exist — on the *pull* path, not the commit path — so the claim was right about the world and wrong about what had been measured. | Printing the boolean next to the prose claim |

### The transferable rules

1. **Never use `INSERT IGNORE` (or any suppression) in a test that asserts a constraint.**
2. **Read back on a DIFFERENT connection** than the one that wrote.
3. **Assert the return code of every setup step**, not just the thing under test.
4. **Make fixtures run-unique** (timestamps/random) or tests are single-shot.
5. **Restore mutated global state in `finally`** (permissions, branches, merge state).
6. **When a result is convenient, isolate the variable.** The `fence+1` pass, the "exact"
   counter, and the "no dangling refs" clean were all convenient and all wrong.
7. **Report unreproduced anomalies as unreproduced.** One 8-agent run showed 7 agents OK
   with 6 increments landing; it never reproduced, and it is logged as unexplained rather
   than promoted to a finding.
8. **Derive the verdict from the numbers at print time.** Never write the conclusion
   into the report string while writing the test — it will survive the test failing.
9. **Before recommending a lever, measure the alternatives to that lever.** A ratio
   between two things you measured says nothing about a third thing you did not.

---

## 3. Method notes worth keeping

- **Build node universes from authoritative declaring documents only** — `capabilities.md`,
  `invariants.md`, `phase-0-ingestion/pass-4-nfr-catalog.md`, `prd.md`, ADR headings,
  `stories/epics/`. Grep-over-everything makes every reference resolve trivially and the
  integrity check proves nothing.
- **Enumerate from the target's own source of truth.** The 46 artifact types came from
  `plugins/vsdd-factory/config/artifact-path-registry.yaml` (ADR-016), not from memory.
- **Check before claiming a defect.** The NFR registry looked absent from `specs/`; it
  exists in `phase-0-ingestion/pass-4-nfr-catalog.md` and all 50 references resolve. I
  nearly reported a hole that wasn't there.
- **Verify a "missing" record is missing everywhere** before calling it dangling —
  `S-8.11`–`S-8.29` and `S-9.01`–`S-9.04` were checked against the whole tree.
