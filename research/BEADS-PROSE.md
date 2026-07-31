---
title: How beads stores PROSE — harvest
date: 2026-07-31
source: github.com/gastownhall/beads @35ccd0d (a --depth=1 clone; the handoff's b1694a5 pin is not reachable in a shallow clone)
purpose: the only shipped Dolt-backed product we can copy from — what it does with prose, and what it refuses to do
---

# beads and prose

The question this answers: if `fa` is to own **all** factory artifacts including prose,
has anyone shipped that on Dolt, and what did it cost them?

## 1. Prose lives IN the database

The `issues` table (62 migrations, 25 tables, ~50 columns) has four dedicated prose
columns:

```sql
description         TEXT NOT NULL,
design              TEXT NOT NULL,
acceptance_criteria TEXT NOT NULL,
notes               TEXT NOT NULL,
```

plus `close_reason TEXT`, `payload TEXT`, `waiters TEXT`, `metadata JSON`, and a separate
`comments` table (`text TEXT NOT NULL`, FK to the issue).

So "prose in Dolt" is not speculative — it is a shipped product's core design. Note that
**`fa` already does this too**: `bc.body`, `vp.body` and `story.body` are `LONGTEXT` and
the importer stores every record's full prose (the spike proved a 211 KB body round-trips,
L8). Prose *storage* was never the gap.

## 2. But prose only exists as a typed SLOT on a record

There is **no `document`, `spec`, or `doc` table anywhere in the schema.** Every prose
blob belongs to an issue and lands in a named field. Markdown appears only as an **input**
format — `bd create -f <file>` parses a markdown file into multiple issues — never as a
stored artifact. beads' own design docs live as plain `.md` files in `docs/`, outside the
database entirely.

**This is the transferable rule:** beads made prose-in-a-DB work by guaranteeing every
blob has an owning record and a slot. Our `cycles/` documents, research docs and proposals
have neither by default — see [PROBE-CYCLES.md](PROBE-CYCLES.md), which finds that most of
`cycles/` *can* be given both.

It is also the merge-granularity lesson: four narrow prose columns rather than one `body`
means two agents editing the design and the acceptance criteria of one issue merge
cleanly. One `body` column would collide. Cell-level merge reconciles different
**fields**, never different **regions of one field**.

## 3. There is no markdown rendering. At all.

The only export is JSONL, and the docs call it *"Passive JSONL export for viewers and
interchange"*, explicitly lossy: *"Dolt-native backups preserve full commit history; a
JSONL export does not."*

beads simply **gave up git-diffable review of issue content**. That option is not open to
us — the factory's review is PR diffs on markdown — so `fa render` (or `fa diff` piped to
a PR comment) is a requirement beads never had to satisfy. No precedent to copy here.

## 4. The database is gitignored; the DB is the truth

```
.beads/embeddeddolt/   # Dolt database (embedded, default) — gitignored
.beads/dolt/           # Dolt database (server mode)       — gitignored
.beads/issues.jsonl    # Passive JSONL export
```

> *"The database directory for your mode is the only thing holding issue data; everything
> else is configuration, runtime state, or a derived export."*

Sync is `bd dolt push/pull` to a Dolt remote, which **may be `refs/dolt/data` on the same
git remote as the source code** — independently confirming the spike's topology (SPEC §1,
T12). Contributor onboarding is `bd bootstrap`, which probes `origin` for `refs/dolt/data`
and clones the database from it.

Worth noting: gitignoring the DB and riding `refs/dolt/data` are **not in conflict** —
they are the same design. But it decides whether a reviewer holding only a git clone can
see anything, which determines how much `render` has to carry.

## 5. Prose growth is solved by DECAY — and we cannot copy it

This is the part that most directly prices our vision.

Schema support: `issues.compaction_level`, `compacted_at`, `compacted_at_commit`,
`original_size`; `issue_snapshots` (`original_content TEXT`, `archived_events TEXT`);
`compaction_snapshots` (`snapshot_json BLOB`).

Behaviour (`bd admin compact`):

> *"Compaction reduces database size by summarizing closed issues that are no longer
> actively referenced. This is permanent graceful decay — original content is discarded."*
> **Tier 1: semantic compression (30 days closed, 70% reduction)**; Tier 2 planned.

Driven by agent summarisation (`--analyze` → `--apply`, with a legacy `--auto` needing an
API key). `bd restore` can step a level back down *if* a snapshot survives. Separately
`bd compact --days` squashes old **Dolt commits**, plus `bd gc` and `bd flatten`.

⚠ **This mitigation is unavailable to an authoritative spec corpus.** A closed issue can
be summarised away; a behavioural contract cannot. So absorbing `cycles/`, prose bodies
and `.jsonl` logs means inheriting beads' growth curve **without its release valve** — and
the spike only ever measured ~6 KB/commit over 40 commits (open gap 5).

## 6. One small thing worth stealing

> *"The schema is stable by default: prefer the `metadata` field for integration-,
> orchestrator-, or team-specific data before proposing new first-class columns."*

A JSON escape hatch instead of schema churn — in a repo that has still needed 62
migrations.

## Scorecard for our vision

| Vision element | beads precedent |
|---|---|
| Prose in the DB | ✅ shipped — but only as typed slots on records |
| Discrete tasks inside story execution | ✅ this is literally their core model (issues + deps + comments) |
| Standalone narrative documents | ❌ **none** — kept as files in git, outside the DB |
| Markdown as the reviewable rendering | ❌ **none** — abandoned in favour of passive JSONL |
| Prose growth control | ⚠ lossy decay, which our corpus forbids |

The vision splits into a well-trodden half (record-shaped prose and tasks) and an
unprecedented half (standalone documents + byte-faithful markdown rendering + no ability
to decay). The second half carries the risk, and beads offers no cover for it.
