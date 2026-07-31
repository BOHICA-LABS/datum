# dolt-artifact-spike

Research spike: can [Dolt](https://github.com/dolthub/dolt) back a tool that is the **only**
interface to all vsdd-factory artifacts, replacing the `factory-artifacts` orphan git branch?

**Verdict: GO, phased.** See [research/ASSESSMENT.md](research/ASSESSMENT.md).

## What's here

| Path | What |
|---|---|
| `research/ASSESSMENT.md` | The feasibility assessment — findings, gaps, phased recommendation |
| `poc/schema.sql` | Core schema (BCs, VPs, stories, subsystems, lock) |
| `poc/graph.sql` | Full relationship graph — 10 node types, 9 edge tables |
| `poc/fa.py` | `fa` — the sole-interface CLI (init/import/count/get/history/validate/lock/render) |
| `poc/graph_import.py` | Loads the graph from live frontmatter; reports every dangling ref |
| `poc/test_spike.py` | 13 tests — store-level failure modes |
| `poc/test_graph.py` | 8 tests — traversal + referential integrity |
| `poc/test_multimachine.py` | 6 tests — two clones, one remote (self-provisioning) |
| `poc/db/`, `poc/mm/` | Dolt data dirs (gitignored) |

**27/27 passing** against the live corpus.

## Headline findings

- The live `factory-artifacts` corpus asserts **four different values** for one fact
  (BC total: 1949 / 1955 / 1959 / 1962). The frontmatter and body of `BC-INDEX.md` disagree
  with each other by 6. `SELECT COUNT(*)` returns 1959 and cannot self-disagree.
- **3 dangling references** and **1 identity violation** exist right now. A `FOREIGN KEY`
  and a `PRIMARY KEY` make both classes unrepresentable.
- The factory lock is a YAML block inside `STATE.md` guarded by `push --force-with-lease`,
  with a **TOCTOU race the skill documents itself** (CWE-367). The CAS replacement survives
  16 concurrent acquirers with exactly one winner.
- Dolt data rides in the project's **existing git remote** under `refs/dolt/data` — the
  orphan branch is replaceable with no new hosting.
- Modelling the **full spec graph** (story → BC → VP → NFR/DI, epics, subsystems, the
  story dependency DAG; 1,490 edges) surfaced **38 dangling references** and **44 type
  violations** no gate catches — including 19 stories `S-8.09` claims to block that were
  never written, and unfilled placeholders like `BC-4.NN.001` sitting in traceability fields.
- It also answered a question nothing in the corpus states: **90.2% of behavioral contracts
  have no verifying VP**; subsystem SS-10 has 58 BCs and zero.
- **Cell-level merge works across machines** — A edits `title`, B edits `capability`, same
  row, zero conflicts. A markdown store cannot do that.
- Hard cost: **one shared server is mandatory.** Embedded Dolt is single-writer, and the CAS
  lock is provably *incorrect* across independent clones — both machines acquired it and each
  believed it won. That means a daemon and a single point of failure, not a footnote.

## Quick start

```bash
brew install dolt                                                  # 2.2.3 verified
(cd poc/db && dolt sql-server --host 127.0.0.1 --port 3308 &)       # no --user in 2.2.x
.venv/bin/python poc/fa.py init
.venv/bin/python poc/fa.py import ~/Dev/vsdd-factory/.factory
.venv/bin/python -u poc/test_spike.py                              # 13/13
```

## Sources

- vsdd-factory `82163b7f` (+ its `.factory` worktree on `factory-artifacts`)
- beads `b1694a5` — production Dolt reference product
- Dolt 2.2.3
