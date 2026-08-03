---
title: Access path — embedded driver vs CLI vs sql-server, measured
date: 2026-07-31
status: 13 tests (poc/test_embedded.py) + 10 against a real GitHub remote (poc/test_github_remote.py)
verdict: the embedded driver is NOT the big lever. A missing BEGIN/COMMIT was.
evidence: dolt 2.2.3 CLI · dolthub/driver/v2 v2.2.0 · live vsdd-factory corpus @82163b7f
---

# Which access path should `datum` use?

Every timing in this spike before now shelled out to `dolt sql`, paying a measured
**141 ms** of process spawn per invocation — about **14,000x** the cost of a
`COUNT(*)`. [HANDOFF](../HANDOFF.md) called benchmarking the embedded
`dolthub/driver/v2` path *"the single biggest engineering lever"* and guessed it
would remove invariant 4 and relax invariant 6.

**It measured out differently. The biggest lever was a transaction boundary, not
the access path.**

---

## 1. The headline correction

Bulk-writing the corpus, four ways, same 2,779 records, identical row counts
verified afterwards (B6):

| Path | Time (range over 3 runs) | ms/record |
|---|---|---|
| CLI, one invocation per record | ~380–400 s (extrapolated) | ~136–141 |
| CLI, batched into one `-f` file | **15.7–18.5 s** | 5.7–6.7 |
| **CLI, same file wrapped in `BEGIN; … COMMIT;`** | **0.8–0.9 s** | **0.29–0.31** |
| embedded, statement at a time | 14.3–20.4 s | 5.1–7.3 |
| embedded, one transaction + prepared | **0.4 s** | **0.15** |

The batched → one-transaction step is **17–23x, and it is free**. It needs no Go,
no new dependency, no rewrite — just a `BEGIN`/`COMMIT` around the batch `datum`
already writes. The remaining embedded advantage on bulk import is ~2x.

**There are two taxes, and the spike had only identified the outer one:**

| Tax | Cost | Present in |
|---|---|---|
| process spawn | ~136–140 ms per invocation | the CLI path only |
| per-statement autocommit (a working-set write) | ~4.5–7 ms per statement | **both** paths — e.g. CLI batched 5.00 ms vs embedded autocommit 4.52 ms in the same run, the same number |
| inside one explicit transaction | 0.09–0.53 ms per statement | both paths |

That middle row is the discovery. Batching statements into one *process* removes
only the outer tax; the order of magnitude lives in the transaction boundary, and
the CLI can reach it.

---

## 2. Where the embedded driver genuinely wins

| Measurement | CLI | embedded | sql-server |
|---|---|---|---|
| cold start + `SELECT 1` | 128–138 ms | **67–72 ms** | 13–15 ms (server already up) |
| cold start + `COUNT(*)` on the corpus | 130–142 ms | **67–71 ms** | 13–14 ms |
| warm `COUNT(*)`, one handle | 132 ms *(every time)* | **0.03 ms** | 0.12 ms |
| warm 3-table JOIN rollup | 136 ms | **1.62 ms** | — |
| engine open, in-process | — | 24–27 ms | — |

Two real wins:

1. **Cold start is ~2x better** (70 ms vs 136 ms). Of those 70 ms, ~25 ms is the
   Dolt engine opening and the rest is Go runtime + loading a 147 MB binary. So a
   one-shot CLI-shaped `datum` command is *twice as fast*, not a thousand times.
2. **A long-lived process pays engine open once**, after which queries cost what
   SQL costs (0.03 ms). This is the case that matters if `datum` ever becomes a
   daemon, an LSP-style server, or a single process handling a whole wave. It is
   worth **~4,000x** on read-heavy work like `datum validate` or a traceability
   rollup, which today pays 132 ms per question.

And one capability the CLI cannot offer at all:

3. **Real cross-statement transactions** (B7). A multi-table burst that hits a
   foreign key rolls back completely — verified by reading back on a *different*
   connection. `dolt sql -q` is one implicit transaction per invocation, so a
   multi-invocation burst has no rollback point. (A single `-f` file *can* hold
   `BEGIN`/`COMMIT`, so the gap is narrower than it looks — but the CLI cannot
   make a decision between two statements the way a program can.)

---

## 3. What it costs to adopt

Measured, not estimated (B1):

| Cost | Finding |
|---|---|
| Language | **Go, with CGO.** `dolthub/driver/v2` is a Go `database/sql` driver. An embedded `datum` is a Go binary — a Python `datum` cannot use it at all. |
| `CGO_ENABLED=0` | build **refuses** (`//go:build cgo`); there is a stub that errors at runtime |
| Build tags | a bare `CGO_ENABLED=1 go build` **fails** on ICU headers (`unicode/regex.h`). `-tags gms_pure_go` is mandatory; beads pins exactly this and documents the trap |
| Dependencies | **155 indirect modules** — Dolt and go-mysql-server end up in your build tree |
| Binary | **147 MB** (vs the `dolt` CLI's 116 MB). Embedded is not a size saving |
| Versioning | the driver carries **its own Dolt build** (`dolthub/dolt/go v0.40.5-0.20260715…`) independent of the installed CLI (2.2.3) |

Compat is fine in both directions (B12): a database created **entirely by the
embedded driver** — `CREATE DATABASE`, DDL, `DOLT_COMMIT`, no CLI involved — is
read by `dolt sql` with all tables and commits intact, and the driver reads
CLI-created repos throughout this suite. But two independently-versioned engines
over one on-disk format is a real upgrade hazard to pin.

---

## 4. Concurrency: the embedded path does NOT remove the mutex

| # | Finding |
|---|---|
| B9 | A second embedded process on the same directory **opens successfully as READ-ONLY** and then fails at write time with `cannot update manifest: database is read only`. It does not refuse to open. |
| B10 | The same happens to `dolt sql` writing while an embedded process holds the directory. **The two access paths cannot share a directory** during a migration without one mutex covering both. |
| B11 | `n = n + 1` x50 from two embedded processes: one completed exactly 50, the other failed cleanly. **No lost updates, loud failure** — the same shape as X3 under `flock`. |

Consequences:

- **The embedded engine is single-writer per directory**, so invariant 6's
  companion — a write mutex — stays. `flock` still earns its place, or the
  driver's own backoff does (beads sets `cfg.BackOff` with `MaxElapsedTime = 0`,
  i.e. wait until context cancellation, precisely to turn this failure into a
  wait).
- **The read-only-on-open behaviour is a footgun.** A long-lived `datum` that opens
  the store early and writes later can be silently read-only for its whole life.
  `datum doctor` must check writability, not just openability.
- Invariant 1's token discipline stays confined to the **server** topology, as
  §3e already concluded.

`DOLT_ADD`, `DOLT_COMMIT`, `DOLT_BRANCH`, `DOLT_CHECKOUT`, `DOLT_MERGE`,
`DOLT_RESET`, `DOLT_GC`, `DOLT_REMOTE`, `dolt_log`, `dolt_status`,
`dolt_branches`, `dolt_conflicts`, `dolt_diff_*`, `dolt_history_*` and
`… AS OF` all work in-process (B8), and so do `DOLT_FETCH` and `DOLT_PUSH`
against a real GitHub remote (G8). **An embedded `datum` needs no `dolt` binary at
all** — which is the strongest single argument for the embedded path, because it
removes the pinned-external-binary problem from the toolchain.

---

## 5. Recommendation

**Do not rewrite for the embedded driver now. Fix the transaction boundary
instead.** Then decide the access path on the phase, not on the benchmark:

| Phase | Path | Why |
|---|---|---|
| 1 — read-only shadow | **CLI + one transaction per unit of work** | Gets 17x for free. Import + validate in CI lands at ~1–2 s, cheap enough for every commit. Zero new language, zero new dependency. |
| 2 — the lease | CLI | The cost is network (11.4 s/acquire, §6), not process spawn. The access path is irrelevant here. |
| 3 — invert authority | **revisit embedded seriously** | This is where `datum` starts doing many reads per command and where a long-lived process pays off 4,000x. It also removes the `dolt` binary from the toolchain. |
| 4 — parallel waves | embedded or server | Decide with phase-3 evidence. |

The honest summary: **the 141 ms spawn floor was real but not the bottleneck it
looked like.** It is 2x, not 14,000x, for the CLI-shaped commands `datum` actually
runs — because those commands run one query, and the engine has to open either
way. The 14,000x figure compares spawn against a query on an *already-open*
engine, which only a long-lived process can exploit.

### Invariant 6, restated

> ~~One mutex hold = one unit of work, batched into one Dolt session.~~
>
> **One TRANSACTION per unit of work.** This is the same boundary atomicity
> already requires, so it is not an extra discipline — and it is worth 17x on the
> CLI path and 50x on the embedded path. Batching into one *process* is a
> distant second-order effect (~140 ms once), not the cliff.

### Invariant 4, unchanged

Idempotent retry survives untouched. It exists because a push on a shared clone
publishes siblings' commits, which is a git-level property of the topology — not
of the SQL access path. It is **confirmed against github.com** in G6, and the
embedded path inherits the same semantics because `DOLT_PUSH` is the same
operation in-process.

---

## 6. Reproducing

```bash
cd poc/bench && CGO_ENABLED=1 go build -tags gms_pure_go -o bench .   # ~20 s, needs Go + cgo
codesign -s - -f bench                                               # macOS only
cd ../.. && .venv/bin/python -u poc/test_embedded.py                 # 13/13, ~4 min
```

`poc/corpus_fixture.py` builds the fixture in three interchangeable forms
(JSONL for the Go harness, batched SQL and per-statement SQL for the CLI) so
both paths are timed on identical work.
