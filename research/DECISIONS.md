---
title: The three open decisions, settled
date: 2026-07-31
status: settled against measured evidence; each records what would reopen it
inputs: SPEC.md · GAP-MATRIX.md · ACCESS-CONTROL.md · ASSESSMENT.md · ACCESS-PATH.md · REMOTE.md · SCALE.md · CI-AGGREGATOR.md
---

# Decisions

The spike left three things undecided and flagged them as blockers before any `datum`
code (HANDOFF "TOP PRIORITY NEXT"). All three are settled here. Each decision
states the evidence, the cost it accepts, and what would reopen it.

---

## D1. Conflict-resolution policy

**Decision: `datum` never auto-resolves. Conflicts are re-applied as semantic
operations by whoever loses the push race, and a conflict inside a leased scope is
reported as a lease-scoping defect — not as a merge problem.**

### Why this shape

Classify every table by what a merge can even do to it. Two of the three classes
cannot conflict at all, which shrinks the problem to something a policy can cover:

| Class | Tables | Can a conflict occur? |
|---|---|---|
| **A — derived** | counts, indexes, rendered markdown | **No.** Nothing is stored (design rule 1). A conflict here is an `datum` bug, not a user decision. |
| **B — append-only** | counters, id allocators, `spec_change` ledger, task/phase events, the conflict log itself | **No.** Distinct primary keys per row (invariant 3), so cell merges never collide. Verified 8/8 across machines (D5b) and again over GitHub (G6). |
| **C — mutable record cells** | `bc.title/capability/version`, `story.status/wave`, `phase.verdict`, lease rows | **Yes.** This is the only genuine class. |

Class C is also small: cell-level merge means two agents editing *different fields
of the same record* merge cleanly (D2, M3) — the case a markdown store turns into a
textual conflict. What is left is two agents writing the **same cell**.

### The policy

1. **Abort, always, mechanically.** Any conflicting pull or merge gets
   `merge --abort` in the same code path, never in agent prose. This is invariant 2,
   and it is load-bearing: an unresolved conflict wedges the clone so that *every*
   later commit by *any* agent fails with `cannot merge with uncommitted changes` —
   an error that blames staging, not the conflict (D8). One careless agent otherwise
   downs its dev's whole fleet.
2. **Record it.** Append a row to a `conflict` table (class B, in the `open` zone):
   scope, table, primary key, base/ours/theirs values, both commit hashes, actor,
   timestamp. Conflicts become queryable history rather than an interactive prompt.
3. **Authority: the loser of the push race resolves.** It is the only assignment
   that needs no coordinator, and the loser is the one actor who still holds the
   intent — they know which semantic operation they were performing. G4 confirms the
   race has exactly one winner over a real remote, so "the loser" is always
   well-defined.
4. **Resolve by re-applying intent, never by picking text.**
   `datum conflict resolve <id> --reapply | --take-theirs | --take-mine` all land as
   ordinary **validated** writes on top of the winner's state. A resolution
   therefore appears in `datum history`, passes the same create/amend validation as any
   other write, and cannot bypass a gate. Cell-picking is not offered as a primitive.
5. **Escalate on cross-actor collision.** If the conflicting cell was written by a
   different actor holding a lease on that scope, `--take-mine` is refused and the
   conflict routes to the orchestrator, which is VSDD's declared authority. No new
   authority is invented.
6. **Diagnose the cause, not just the symptom.** Per-scope leases (invariant 11)
   exist precisely to prevent two actors editing one scope. So a class-C conflict
   *inside* a leased scope means the lease scoping is wrong, and `datum` says so in the
   error. Expect conflicts to be rare and to indicate a scoping bug; do not build a
   rich merge UI for them.
7. **Time-box it.** A conflict row older than the lease TTL escalates automatically.
   Nothing sits unresolved silently, because unresolved divergence blocks every
   other pusher's fast-forward. (G7 was read as "one git ref ⇒ global blocking"; the
   mechanism is actually per-BRANCH — see invariant 12 — but since the artifact store
   is a single branch, the blocking is global for artifacts either way.)

### Cost accepted

Manual resolution stays manual. `datum` gets one new table, four subcommands, and a
`doctor` check for a half-merged clone. No automatic three-way semantic merge is
attempted; that is deliberate, because a wrong auto-resolution is silent data loss
and this whole project exists to eliminate that class.

### What would reopen it

If phase 4 (parallel waves) produces routine same-cell conflicts *despite* per-scope
leases, the fault is the lease scoping and D1 stays; if conflicts persist after
scoping is fixed, revisit with real conflict data — not before.

---

## D2. Zone granularity: per-directory or per-table?

**Decision: per-DIRECTORY zones. Ratified, with one new mandatory piece of work.**

### Why

The prior pass already selected tier 1 (ACCESS-CONTROL §4.2) because Claude Code
runs every agent inside **one OS process** — no per-agent uid (tier 2), no per-agent
process to inherit a credential fd (tier 3). Per-table walls come from database
`GRANT`s, which require the acting agent to hold a credential; in a one-process
fleet any credential reachable by one agent's `Bash` is reachable by every agent's
`Bash`, so per-table would be the security theatre ID5b demonstrated.

Two new measurements from this session **strengthen** per-directory rather than
merely confirming it:

- **The per-zone cost objection is gone.** Splitting zones cost ~144 ms of extra
  process spawn per zone touched on the CLI path (SC6/Z7). In-process a zone opens
  in ~25 ms, and one process can hold **both** zone handles at once. Zone count is
  no longer a performance argument in either direction.
- **An embedded `datum` needs no `dolt` binary at all** (B8 + G8: SQL, branch, merge,
  and `DOLT_PUSH`/`DOLT_FETCH` all work in-process). That makes the enforcement
  shape practical: a walled agent needs neither `dolt` nor `mysql` on `PATH`, so
  "deny `Bash`, allow only `datum`" stops being awkward. Today the wall leaks the
  moment a walled agent has `Bash` plus a `dolt` binary.

### The decision, concretely

- Zones are separate **directories** under `.factory-db/` (`open/`, `walled/`), each
  opened with `cwd` set to that one zone — never a shared `--data-dir`, which leaks
  via `SELECT … FROM walled.x` (A2).
- Enforcement is tier 1: `permissions.deny` on the zone paths, `PreToolUse` hooks,
  per-agent `allowed-tools`.
- **Hard requirement:** a walled agent gets **no unrestricted `Bash`**. Denying
  `Read` while leaving `Bash` open is not a wall — `cat` walks through it.
- Ids route to zones invisibly (`datum get HS-001` and `datum get BC-1.01.001` are the
  same command, Z2). Nobody types a zone name.
- Per-table is **deferred, not rejected**. Reopen only if an agent needs *partial*
  visibility inside a zone (e.g. an evaluator that may read some specs); the route
  is harness-side (deny `Bash`, allow only `datum`, inject the true role via a
  `PreToolUse` hook so the agent cannot forge it), not database `GRANT`s.

### Cost accepted, and the new work it creates

Splitting zones removes cross-zone foreign keys (A6): a holdout scenario cannot FK
to the BC it verifies. **`datum validate` therefore gains a cross-zone integrity pass
as a required deliverable, not an optional extra.** It is the one guarantee this
decision gives up, so it must be bought back in the tool. It runs privileged (it
can see both zones) and reports *counts and ids of dangling cross-zone refs only* —
never walled content — so it does not become a side channel.

### What would reopen it

A harness that gives each agent its own uid/container (tier 2 becomes available,
and the wall becomes OS-enforced — strictly stronger), or a genuine requirement for
partial in-zone visibility.

---

## D3. Phase-1 scope sign-off

**Decision: read-only shadow, as recommended — with the implementation now pinned
by measurement, and one addition without which the gate cannot be turned on.**

### Scope

| In | Out |
|---|---|
| `datum import <path>` — build a throwaway Dolt store from the markdown corpus | any write back to the corpus |
| `datum validate [--strict]` — the gates as SQL (W8) | `datum render` (phase 3) |
| a CI job that fails on violations | the lease (phase 2), zones, instance branches |
| **a baseline allowlist of the 82 known findings** | any remote, any push, any daemon |

Markdown stays the single source of truth. Zero agent changes. Nothing pushes.

### ⚠ SUPERSEDED 2026-07-31: the end state is a single Go binary

The user has settled the implementation: **`datum` is one Go binary and everything lands
as its subcommands.** That retires the "no Go in phase 1" advice below, which was
correct only while the language was an open question. What changes:

- The embedded `dolthub/driver/v2` path becomes **the** access path, not a phase-3
  option — so there is **no `dolt` CLI dependency anywhere, including CI**. Its costs
  are now simply the binary's costs (CGO, `-tags gms_pure_go` mandatory, 155 indirect
  deps, ~147 MB, its own pinned Dolt build); its wins come along too (~2x cold start,
  ~4,000x warm, real cross-statement transactions, `DOLT_PUSH` in-process).
- The aggregator is **`datum aggregate`**, a subcommand — so the CI-outage fallback is
  "any dev runs the same binary", not a parallel script implementation
  ([CI-AGGREGATOR.md](CI-AGGREGATOR.md)).
- Phase 1's *scope* is unchanged (read-only shadow, import + validate, the dated
  baseline allowlist). Only the implementation language and access path change.

The measured facts below still hold and still bound the design; read them as
requirements on the binary rather than as an argument for Python.

### What measurement pinned

- ~~**Python + `dolt sql -f` with ONE transaction.**~~ **The transaction boundary is
  what mattered, not the language:** The corpus import lands at
  **0.9 s** (ACCESS-PATH §1), so import+validate is cheap enough to run on every
  commit and every PR. Phase 1 needs **no Go, no embedded driver, no CGO, no
  147 MB binary** — that decision is deferred to phase 3, where a long-lived
  process is worth ~4,000x on reads.
- **No network anywhere.** Phase 1 builds a local store from files and throws it
  away, so it never pays the measured **11.4 s** per lease acquire over GitHub
  (REMOTE §2) and needs no remote at all. Blast radius is zero: if `datum` is wrong,
  a CI job is wrong — the corpus is untouched.

### The addition: a baseline allowlist

`datum validate` finds **38 dangling references and 44 type violations in the corpus
today**. A gate with no baseline therefore blocks every PR on day one and will be
switched off within a day. Phase 1 must ship with the current 82 findings recorded
as an explicit, dated, itemised baseline that the gate tolerates and **refuses to
grow**. New violations fail; existing ones are visible, counted, and ratcheted down.
This is the difference between a gate that survives and a gate that gets disabled.

### Exit criterion into phase 2

The baseline is at zero (or each remaining item is explicitly waived with a reason),
**and** `datum validate` has caught at least one real regression in a real PR. Until a
gate has caught something, it has not earned authority over anything.

### What would reopen it

Nothing in phase 1 is hard to reverse — it is additive and read-only, which is why
it goes first.

---

## Consequences for the SPEC

| SPEC item | Change |
|---|---|
| §4 invariant 6 | **Restated.** "One transaction per unit of work", not "one process invocation". 17x on the CLI path, and it is the same boundary atomicity already requires. |
| §4 invariant 4 | Unchanged, and now **confirmed against github.com** (G6), not just `file://`. |
| §4 new invariant 12 | **A remote data ref is a single lineage.** All Dolt branches share one git ref (`refs/dolt/data`), so push contention is global across instances (G7). Either accept it or give each instance its own `--ref`, which decouples pushes but forfeits cross-instance merge on the remote. |
| §6 non-goals | "Conflict-resolution policy is out of scope" — **removed**, see D1. |
| §7 phasing | Phase 1 gains the baseline allowlist; the embedded-driver decision moves to phase 3. |
| §8 known gaps | gap 1 (real network remote) **closed**, gap 4 (conflict policy) **closed**, gap 6 (embedded driver) **closed**. |
