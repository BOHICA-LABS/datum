# dolt-artifact-spike

Research spike: can [Dolt](https://github.com/dolthub/dolt) back a tool that is the **only**
interface to all vsdd-factory artifacts, replacing the `factory-artifacts` orphan git branch?

**Verdict: GO, phased.** See [research/ASSESSMENT.md](research/ASSESSMENT.md).

## What's here

| Path | What |
|---|---|
| `research/ASSESSMENT.md` | The feasibility assessment — findings, gaps, phased recommendation |
| `poc/schema.sql` | Relational schema for factory artifacts (BCs, VPs, stories, traces, lock) |
| `poc/fa.py` | `fa` — the sole-interface CLI (init/import/count/get/history/validate/lock/render) |
| `poc/test_spike.py` | 13 tests, each targeting a failure mode measured in the live corpus |
| `poc/db/` | Dolt data dir (gitignored) |

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
- Hard cost: **server mode is mandatory** (embedded Dolt is single-writer), so this
  introduces a daemon. That is a real architectural trade, not a footnote.

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
