---
title: FA-V1 L1–L2 — storage and schema
date: 2026-08-02
status: DESIGN. Nothing implemented. Decisions are proposed against the FA-V1-DESIGN spine and are
  binding on L3–L7 once ratified; the OPEN QUESTIONS section lists what needs a human call first.
inputs: research/FA-V1-DESIGN.md (spine, 8 settled decisions, invariants 15–23) · research/SPEC.md
  (invariants 1–14) · research/DECISIONS.md (D1 conflicts · D2 zones · D3 phase 1) ·
  research/SCALE.md (contention) · research/CROSS-CORPUS.md (10 corpora) ·
  research/ACCESS-CONTROL.md (zones/identity) · research/GAP-MATRIX.md ·
  research/VSDD-FACTORY-REVIEW.md (F1–F22, the measured coverage table) · HANDOFF.md (session state) ·
  datum/schema.go (the current 34-table shadow schema) · datum/registry/*.yaml (119 types, 17 enums, 180 aliases)
scope: L1 STORAGE and L2 SCHEMA only. L3 semantic ops, L4 projections, L5 policy, L6 engine,
  L7 interfaces and the migration/cutover plan are separate documents.
---

# `datum` v1 — L1 storage and L2 schema

## 0. What is binding, and what this document is allowed to decide

The eight one-way doors (**V-A..V-F**, **D-A..D-D**) and invariants **1–23** are inputs, not
subjects. This document decides only the mechanisms that discharge them, and it says explicitly
where a mechanism *bends* an input (§8) rather than quietly reinterpreting it.

Two standing rules from this repo govern the whole design and are quoted because they change what
counts as a finished decision:

- **Measure the alternatives before pulling the lever.** It has deleted planned work twice
  (HANDOFF.md:157–159). Every performance claim below that is *not* backed by a measurement in this
  repo is labelled as a required measurement, never asserted.
- **Parity, not inspection.** Every derived value gets an independent recomputation gate, not a
  review (HANDOFF.md:167).

### 0.1 Decision summary

| # | Decision | Discharges |
|---|---|---|
| **L1-A** | **One store per project**, each store a `.factory-db/` inside that project's own repo, with **zones as inner directories**. Projects are the OUTER physical dimension; zones the INNER. One shared registry, carried in the binary. | V-F · inv 9 · inv 12 · inv 19 · D-B |
| **L1-B** | **Version is a store-assigned monotonic integer per artifact key, and is NOT stored on the artifact row.** It is the ledger's `MAX(version)`. `datum show --at <v>` resolves version → txn → Dolt commit → `AS OF`. | inv 17 · inv 23 · D-C |
| **L1-C** | **Verbatim body bytes and an ordinal section partition live in TWO tables shared by all types** — never a `body` column on a typed table. Partition membership is per-shape and declared, not omitted. | inv 16 · D-A |
| **L1-D** | **The Dolt commit IS the write-ahead log.** One SQL transaction + one Dolt commit per unit of work, with the `txn` row written inside it. Recovery discards; replay is the caller's job via `idem_key`. Cross-store units are explicitly non-atomic and use a two-phase intent record. | inv 6 · inv 4 · inv 18 · F2 · F20 |
| **L1-E** | **Two-level store-side leases**: instance-local for narrow scopes, published for cross-instance scopes. Random 128-bit token presented on every write, fail-closed, store-side expiry clock. **No force path**; revocation is a human-authorized audited write to the lease table that touches no artifact. | inv 1 · inv 11 · inv 21 · F4 |
| **L1-F** | **One append-only `audit` table**, PK `(txn_id, ord)`, written in the same transaction as the data, with a parity gate `audit ops == version ledger ops`. Read-denies record role+type+zone and **never the key**. | inv 3 · inv 18 · F18 |
| **L1-G** | **Retention is a declared reachability predicate, not a time bound.** The pin-policy graph names the versions that must survive; pruned ≠ never-existed and is a recorded state. | inv 15 · registry `pinned-to-a-version-that-never-existed` |
| **L1-0** | ⭐ **The engine is defined by a PROPERTY SET (P1–P7), not by a product name.** Any engine satisfying all seven is admissible; Dolt is retained because it satisfies all seven. A candidate failing **P1, P4 or P6** is rejected without further measurement. | V-L (spine §5e) |
| **L2-A** | **The registry GENERATES the schema.** ONE uniform storage model (`artifact` + `artifact_field` + `artifact_ref` + body/section) plus **per-type generated VIEWS**. No typed tables, no hybrid, no second home. Materialize a view only on a measured need, with a parity gate. | inv 17 · inv 20 · V-C · V-F |
| **L2-B** | **Natural keys parsed as typed component tuples** with a per-kind parser and canonical form; `path` is a UNIQUE derived column with a recompute gate; `id_alias` and `reserved_key` ledgers. | D-C · inv 20 · F11 |
| **L2-C** | **Closed enums validated at write time**, with `illegal` refused on write, `migratable` accepted only on the import path, and `open_extension` names required to be declared in the project profile. `defaults.forbidden` fields are refused. | inv 20 · D-D · V-C |
| **L2-D** | **Typed refs with target-type checking and ONE closed `ref_state` enum** carrying the 7 measured incompleteness kinds (`resolved · placeholder · dangling · unresolvable · declared_gap · proposed_name · pruned`). Symmetric pairs stored once. Cite verdicts computed, never stored. | inv 20 · F10 · link_rules |
| **L2-E** | **`authority` enforced structurally: `derived` types are VIEWS by default** — there is nothing to author — and a derived type may not be derived at all until its **scope predicate is declared in the registry**. | inv 17 · inv 18 · HANDOFF result 1 |
| **L2-F** | **Scope predicate is discharged by physical store selection plus declared per-type scope axes.** An aggregate is a named verb whose definition must name its axes; an unnamed axis is a refusal, not a default. | inv 19 |
| **L2-G** | **A field, enum value, type, link or section name is not claimable until censused against every registered project**, recorded in a `field_claim` row and gated. | measured twice: `gate`, `scope` |
| **L2-H** | **All 119 registry types get a home by construction**, because the storage model is uniform; unknown `document_type` values go to an `unmodeled_file` capture table, never dropped. | inv 16 · M1/M6 |

---

# 1. L1 — STORAGE

## 1.1 L1-A · Multi-tenancy: one store per project, zones inside it

### The decision

```
~/.config/datum/projects.yaml            # name -> root. The ONLY place a path is written down.
<project-root>/.factory-db/
    datum.yaml                           # store identity: project name, registry version, zone map
    open/                             # a Dolt data dir  (zone: most agents)
    walled/                           # a Dolt data dir  (zone: holdout/adversary artifacts)
<project-root>/.factory/              # rendered markdown, COMMITTED (D-B)
```

- **Project = an outer physical boundary** (a directory tree bound to one git remote).
- **Zone = an inner physical boundary** (`datum/store.go:28–40`, invariant 9 / A2–A3).
- **Registry = one copy, in the binary** (`datum/registry.go:28–29`). Shared by construction; there is
  no per-project registry to drift.
- There is **no `project` column** on artifact rows. The project is the store.

### Why store-per-project, against the measured facts

**1. Push contention is per-BRANCH, and the artifact store is one branch (invariant 12,
SPEC.md:256–267).** SCALE.md:51–54 measured it directly:

```
primary (all -> main)        [9,7,10,5,5,3,4,1,8,2]  total 54   <- O(N)=55 for N=10
spikes  (each -> own branch) [1,1,1,1,1,1,1,1,1,1]   total 10   <- no contention
```

Every primary writer in that run wrote **disjoint rows** and not one semantic conflict occurred —
disjointness bought nothing. A single shared store would therefore make *vsdd-factory's* writes
reject *prism's* pushes for no semantic reason, at ~8 s fixed per attempt (SCALE.md:93), and
SCALE.md:119–136 measured that this **cannot be tuned out**: immediate retry 159 attempts,
exponential+jitter 185, ticket order 193 — backoff is *worse*, because sleeping lets more pointers
move. Store-per-project puts each project's data on its own ref in its own repo, which is exactly
the measured `[1,1,1,...]` column.

**2. The per-branch mitigation that is *inapplicable* within a project is *correct* between
projects.** SPEC.md:263–266 rejects `--ref`-per-instance because "it fragments the artifact store
into separate lineages". Between projects, separate lineages are the *desired* semantics — prism's
history has no business merging into rivetry's. So the one-way door that closes inside a project is
open here.

**3. Independently stageable, abandonable migrations (V-F).** Measured, per project:
- `delta-archive` is **211 rivetry files, rivetry's single largest `document_type`, larger than its
  own behavioral-contract count (151)** (registry yaml:2656–2679). Retiring it is a **data-bearing**
  migration ("the archive is the only place some of those versions exist ... must be gated by a
  count assertion, not assumed") that concerns *no other project*.
- The same alias has **opposite mass** in two corpora: `adversarial-review-pass` is prism 109 /
  vsdd 47 (aliases.yaml:39–44) while `adversary-review` is vsdd 69 / prism 4 (aliases.yaml:46–53).
  So the correct migration *order* differs per project.
- Baselines are already per-project: vsdd-factory **6,951** · prism **10,843** · rivetry **1,032**
  (FA-V1-DESIGN.md:20). A shared store would need every baseline query scoped by hand — the
  omittable-predicate failure mode invariant 19 exists to kill.
- Operationally, **prism's corpus is being edited by a concurrent session** (HANDOFF.md:149–152).
  One project's live churn must not be able to invalidate another project's baseline or wedge its
  clone (invariant 2's half-merge blast radius, SPEC.md:212–215).

With one store per project, `schema_migrations` (datum/schema.go:300–305) is per-project by
construction, so a project can sit at registry version *N* while another is at *N+1*.

**4. Write containment.** Multi-tenancy here is single-user, so cross-project *confidentiality* is
not a requirement — but cross-project *write isolation* is: an agent working prism must not be able
to write rivetry. Directory separation plus the harness's `permissions.deny` gives that for free,
using the enforcement point ACCESS-CONTROL.md:200–213 measured as the only one available (tier 1;
Claude Code runs every agent in ONE process, ACCESS-CONTROL.md:184–199).

**5. D-B binds the store to a git remote, and the remote is per-project.** SPEC.md:41–46: the data
lives under `refs/dolt/data` "in the repo you already have". A cross-project store has no single
repo to be. Invariant 14 (SPEC.md:285–288) makes this a one-way door: unrelated lineages fail with
`no common ancestor` and "cannot be aggregated at all, only replayed".

### Why `project` is not a column, and why that is *stronger*

Invariant 19's failure mode is **an omitted predicate that still produces an agreeing count** — the
41 retired stories under `stories/v1.0-legacy/` that generating-from-every-record would have
resurrected while every count agreed (HANDOFF.md:45–52). A `WHERE project = ?` clause is
omittable. **A store handle is not.** Making the project a physical selection rather than a filter
converts an invariant that must be *checked* into one that cannot be *expressed* wrongly.

Consequences, each with its mechanism:

| Consequence | Mechanism |
|---|---|
| A mis-targeted import silently merging two corpora | `datum.yaml` declares the store's project; `datum import` refuses a render whose declared project ≠ the store's. One check, one place. |
| Cross-project questions ("BCs across all projects") | An explicit `--all-projects` fan-out that opens N stores and returns **per-project rows, never one collapsed number**. A zone opens in ~25 ms in-process and one process can hold multiple handles (DECISIONS.md:104–107), so 24 registered projects × 2 zones is a bounded, measurable cost — **to be measured, not assumed**. |
| Attribution in fan-out output | The project is stamped by the query layer from `datum.yaml`, so it appears in output without being stored per row. |

### Rejected

| Rejected | Why |
|---|---|
| **One store, `project` column** | Cross-project push contention (fact 1, measured O(N)×8 s and untunable); one global `schema_migrations` breaks V-F's independent staging; no single git remote (D-B); invariant 14 makes lineage a one-way door; invariant 19's predicate stays omittable. |
| **One Dolt `--data-dir`, one database per project** | A2 measured this leaks: `SHOW DATABASES` lists both and `SELECT … FROM other.x` succeeds (GAP-MATRIX.md:153). It is a namespace, not a boundary. |
| **Projects as zones (drop the open/walled split)** | Contradicts invariant 9 directly; holdout scenarios are per-project, so the walled boundary must live *inside* a project. |
| **A shared `sql-server` with per-project GRANTs** | Reinstates the daemon (SPEC §6 non-goal) and is security theatre in a one-process fleet: any credential one agent's `Bash` can reach, every agent's can (ID5b, ACCESS-CONTROL.md:130–136). |

## 1.2 L1-B · Artifact versioning

### The decision

- **`version` is a monotonic integer, per artifact key, assigned by the store**, incremented only
  when the post-image differs from the pre-image over the canonical serialization.
- **`version` is not a column on the artifact row.** The current version is
  `MAX(version)` over the `artifact_version` ledger for that key. Storing it would be storing a
  count — the exact class of `total_bcs` / the four-way BC total (datum/schema.go:9–11), and a
  violation of invariant 17.
- **History addressing:** `datum show --at <version>` → ledger row → `dolt_commit` → read `AS OF` that
  commit. Dolt's point-in-time read is already proven (SPEC.md:128, test L6).
- The counter's scope is **(type, key)** — not global, not per-type, not the commit.

### Why per-artifact rather than the commit ordinal

The corpus's version cites are per-artifact and human-written: **1,612 plain-form `NAME vX.Y` cites
plus 39 prepositional**, over 2,768 documents (registry yaml:465), and `datum import` currently loads
**2,197 version cites** (HANDOFF.md:35). A global commit ordinal makes every one of them
unreadable, and it makes the registry's own `pinned-to-a-version-that-never-existed` check
(registry yaml:498–502) — explicitly "the clearest case where the store earns its keep" — a graph
walk instead of a lookup.

### What the ledger stores that Dolt history cannot

```sql
CREATE TABLE artifact_version (
  type        VARCHAR(64) NOT NULL,
  key_hash    BINARY(20)  NOT NULL,
  version     INT         NOT NULL,     -- 1,2,3...  monotonic per (type,key_hash)
  txn_id      BINARY(16)  NOT NULL,     -- per-attempt UNIQUE (invariant 1)
  dolt_commit CHAR(32)    NOT NULL,     -- the commit this version landed in
  op          VARCHAR(12) NOT NULL,     -- create|update|retire|withdraw|derive|ingest|prune
  PRIMARY KEY (type, key_hash, version),
  KEY idx_av_txn (txn_id)
)
```

A Dolt commit records *that bytes changed*; it does not record the version number, the semantic
operation, the lease, or the role. Those are not derivable from any other stored value, so the
ledger is not an invariant-17 violation — the same argument `corpus_assertion` already makes for
itself as "the one deliberate exception" (datum/schema.go:14–16), except here no exception is needed.

Note this **retires the authored `version VARCHAR(16) NOT NULL DEFAULT 'v1.0'` columns** on `bc`
(datum/schema.go:53) and `vp` (datum/schema.go:68). Those are hand-typed identity in content, i.e. exactly
what invariant 23 forbids.

### The cost this creates, and the table that pays it

Renumbering versions to integers breaks all 2,197 imported cites. That is not optional collateral —
it is the `BC-1.12.008 → BC-3.05.004` class one level down: *a checker that resolves historical
citations against today's numbering manufactures findings against correct documents*
(registry yaml:476–480). So:

```sql
CREATE TABLE version_alias (          -- MIGRATION device, retired with its baseline
  type VARCHAR(64) NOT NULL, key_hash BINARY(20) NOT NULL,
  cited_form VARCHAR(16) NOT NULL,    -- 'v1.25' as written in prose
  version    INT         NOT NULL,    -- the store version it denotes
  source     VARCHAR(24) NOT NULL,    -- delta-archive | dolt_history | adjudicated
  PRIMARY KEY (type, key_hash, cited_form)
)
```

Seeded from the two places the historical sequence actually exists: `delta-archive`'s 211 rotated
sidecars (registry yaml:2670–2674) and Dolt history. `retire_after` follows the alias convention
(aliases.yaml:27–31): history keeps resolving through it forever; new writes never use it.

### Idempotence and the no-op write

A write whose post-image is byte-identical to the pre-image **does not bump the version and does not
produce a Dolt commit**. This is what makes W5 (idempotent re-import, identical HEAD, zero
working-set churn) hold for the write path too, and it is the same discipline `import_run` already
encodes by keying on a content fingerprint and deliberately carrying no clock and no path
(datum/schema.go:308–322).

## 1.3 L1-C · Body and section storage

### The measured problem

| | |
|---|---|
| markdown files under `.factory/` | 3,085 |
| `document_type` has a table | 2,624 (85%) |
| **stores a verbatim body — the only ones renderable back** | **2,145 (69%)** |
| no table at all | 461 (14%) |
| distinct `document_type` / modeled | 70 / **18** |

(VSDD-FACTORY-REVIEW.md:787–798.) Only `bc`, `vp`, `story` and `holdout_scenario.expectation` carry
a body (datum/schema.go:51, 67, 88, 335) and **there is no section table** — D-A's partition is
computed in memory and discarded (datum/registry.go:288–325).

### The decision

Two tables, shared by every type. **No typed table ever carries a `body` column** — that is what
made "3 of 34 tables store a body" possible, and it makes invariant 16 a single gate over a single
table instead of a per-table audit.

```sql
CREATE TABLE artifact_body (
  type     VARCHAR(64) NOT NULL,
  key_hash BINARY(20)  NOT NULL,
  body     LONGBLOB    NOT NULL,     -- VERBATIM bytes. BLOB, not TEXT: no charset coercion.
  PRIMARY KEY (type, key_hash)
)

CREATE TABLE artifact_section (
  type      VARCHAR(64) NOT NULL,
  key_hash  BINARY(20)  NOT NULL,
  ord       INT         NOT NULL,    -- D-A: ORDINAL, never heading
  depth     TINYINT     NOT NULL,
  heading   VARCHAR(500) NOT NULL,   -- DATA, not key: 110 docs carry 1,968 duplicate headings
  body      LONGBLOB    NOT NULL,
  PRIMARY KEY (type, key_hash, ord),
  CONSTRAINT fk_sec_body FOREIGN KEY (type, key_hash)
    REFERENCES artifact_body (type, key_hash) ON DELETE CASCADE
)
```

- `body` is a BLOB deliberately. The measured defect class here is *a parser that silently loses
  input* — **eight instances** (FA-V1-DESIGN.md:144–146) — and a charset round-trip is a ninth
  waiting to happen.
- The partition generator already exists and is already lossless-by-test: `SplitSections` keeps line
  terminators so a missing final newline survives (datum/registry.go:327–342), is fence-aware, and
  `SectionsLossless` (datum/registry.go:344–351) asserts `concat(sections) == body`. Measured **0
  mismatches over 6,537 markdown files** (registry yaml:56–58).
- **The gate:** `concat(section.body ORDER BY ord) == artifact_body.body`, byte-exact, per artifact,
  run at write time *and* as a corpus sweep. It is a SQL/Go parity check, not an inspection.

### Which shapes carry which, declared not omitted

Invariant 16 says *every* artifact stores its verbatim body. Four of the five registry shapes need
that read precisely, or the invariant is either false or vacuous. The distribution (measured over
all 119 types): `document` 80 · `record` 18 · `append-only-event` 11 · `config` 6 ·
`blob-with-path` 4.

| shape | n | body | section partition | why |
|---|---|---|---|---|
| `document` | 80 | verbatim | full ordinal partition | D-A, unchanged |
| `record` | 18 | verbatim | full ordinal partition | a BC *is* a markdown file; its 8 declared sections are the render target |
| `config` | 6 | verbatim (YAML/JSON bytes) | one ord-0 section spanning the body | keeps the gate uniform without pretending YAML has `##` headings |
| `append-only-event` | 11 | **per ENTRY**; the file body is DERIVED | the entries *are* the partition | see below |
| `blob-with-path` | 4 | **not stored** — path + content hash | none | SPEC §6 non-goal: binaries stay on disk. **Exempt by declaration, not by omission.** |

**`append-only-event` is the one that matters.** Its whole point is that a ledger stored as a
document is what makes `burst-log.md` collide — 133/105/63 commits on three files, "every one an
append, every one currently a whole-document rewrite that can conflict. As rows they cannot"
(registry yaml:1373–1381). So for a ledger the file is a *render*, and the gate that binds is
invariant **15** (`import(render(store)) == store`), not invariant **16**
(`concat(sections) == body`). Stated as a rule:

> **Invariant 16 binds at capture; invariant 15 binds at cutover.** While a type is at migration
> stage `shadow` or `dual-write` its captured file body is stored verbatim and gated by 16. When it
> reaches `authoritative` the captured body is dropped and 15 takes over. A type may not advance to
> `authoritative` until 15 is green over 100% of its instances.

This is what structurally retires the 13 `rotation_archive_variants`
(registry yaml:2696–2706) and `delta-archive`'s 211 files: with rows there is nothing to rotate.

### Addressing a section — the three-scheme problem

HANDOFF.md:96–97 measured that **the corpus addresses a section three ways**: heading NAME · section
ORDINAL (D-A's own key) · ITEM within a section (`§Postcondition 5` where the doc has
`## Postconditions`). D-A settles the *storage* key as ordinal. The *reference* therefore needs all
three resolvers, which belongs in `artifact_ref` (§2.4): `target_ord` for the canonical form,
plus a resolver that maps a heading name and an item ordinal onto it. Collapsing the three is how a
prose extractor "produces a large, confident, wrong finding set" (registry yaml:520–524) — and the
214 currently-dangling section refs (HANDOFF.md:103) are the live evidence that this is not settled
by fiat.

## 1.4 L1-D · Transactions, idempotence, recovery

### The decision

**One SQL transaction plus one Dolt commit per unit of work, with the `txn` row written inside it.
The Dolt commit is the write-ahead log.**

```sql
CREATE TABLE txn (
  txn_id     BINARY(16)   NOT NULL,   -- random, per-attempt unique (invariant 1)
  idem_key   VARCHAR(120) NOT NULL,   -- caller-supplied; UNIQUE
  role       VARCHAR(64)  NOT NULL,
  actor      VARCHAR(120) NOT NULL,   -- instance/clone identity
  lease_token BINARY(16)  NULL,       -- NULL only for read-only and lease ops
  op         VARCHAR(24)  NOT NULL,   -- write|derive|ingest|migrate|lease|render|import
  state      VARCHAR(12)  NOT NULL,   -- open|committed|abandoned
  opened_at  DATETIME     NOT NULL,
  result_json LONGTEXT    NULL,       -- returned verbatim on replay
  PRIMARY KEY (txn_id),
  UNIQUE KEY uk_idem (idem_key)
)
```

Sequence, with no step outside the transaction:

```
BEGIN
  resolve+verify lease token (store-side clock)      -- refuse -> ROLLBACK, nothing written
  validate every row against the registry catalog    -- refuse -> ROLLBACK
  write artifact / field / ref / body / section rows
  append artifact_version rows                       -- assigns the versions
  append audit rows
  insert txn row (state='committed', result_json)
COMMIT
CALL DOLT_ADD('-A'); CALL DOLT_COMMIT(-m …)
```

- **Why one transaction:** invariant 6, measured at **17×** (15.7 s → 0.9 s for a 1,959-BC import)
  and "also exactly the boundary atomicity requires" (SPEC.md:230–238). `Store.Begin` already exists
  for this reason (datum/store.go:187–195).
- **Why the `txn` row goes inside:** writing it afterwards is the retired two-commit /
  SHA-backfill pattern (F1, VSDD-FACTORY-REVIEW.md:866–877; the `state-burst` skill explicitly
  refuses "reintroduction of the retired two-commit pattern"). Inside the transaction, there is
  never a committed state whose txn marker is missing.
- **Idempotence:** `idem_key` UNIQUE. Replay of a `committed` key returns `result_json` verbatim and
  writes nothing. Replay of an `open` key is refused as a concurrent duplicate. This is invariant 4
  read exactly: "a duplicate-key error on retry means *already applied* and must fall through, not
  bail — bailing strands the earlier commit" (SPEC.md:219–222).
- **Recovery is discard, not replay.** Because data and marker land atomically, an interrupted unit
  leaves only a dirty working set. `datum recover`: if the working set is dirty, record a
  `txn_abandoned` audit row, then `CALL DOLT_RESET('--hard')` to the last commit. `datum doctor` must
  probe **writability, not openability** — a second opener silently becomes read-only and fails much
  later with `cannot update manifest` (datum/store.go:11–14). This closes the measured
  "mid-burst crash has no recovery path in any of three windows" and the `git reset --soft HEAD`
  no-op (VSDD-FACTORY-REVIEW.md:1114–1121).
- **Merge is never auto-resolved** (invariant 21, DECISIONS D1): a conflicting pull gets
  `merge --abort` in the same code path, a row in a `conflict` table, and the push-race loser
  re-applies intent as a validated write.

### The one case a WAL is genuinely required: cross-store units

Two Dolt commits cannot be atomic. So:

- **Declared:** cross-store units of work are **non-atomic** and are permitted only where the
  registry declares a cross-zone link (today: `holdout-scenario.behavioral_contracts` → BC, the FK
  D2 gave up, ACCESS-CONTROL.md:88–89 / GAP-MATRIX.md:157).
- **Mechanism:** a two-phase **intent record**. The anchor store commits an `xstore_intent` row
  holding the idem_key and the full operation list; the participant store's write cites the intent
  and carries the same idem_key. `datum doctor` reports any intent whose participant leg is missing;
  `datum recover` re-applies that leg, which is safe precisely because the idem_key makes it
  idempotent.
- **Honest cost:** there is a window in which the intent exists and the participant leg does not.
  It is *detectable* and *repairable*, not *invisible* — which is the whole difference from
  `compact-state` writing five files where a failure at #4 leaves #1–3 written and its
  "abort without modifying STATE.md" claim unenforceable (VSDD-FACTORY-REVIEW.md:879–888).
- Everything else is single-store and therefore atomic. Bounding the exception is the design.

### A new hazard this design introduces, and its gate

Under §2.1 an artifact's fields are rows, not columns. Dolt merges row-wise, so **a merge can
produce an artifact that no writer wrote**: writer A removes required field *x*, writer B edits
field *y*, both states individually valid, the merge violating the type's `required` set. Wide
tables have the same hazard in a narrower window; a field-per-row model widens it.

**Mandatory gate:** after any merge, every artifact touched by the merge is re-validated against the
catalog, and a merge producing an invalid artifact is **refused, not resolved** — invariant 21's own
wording. This is a designed step, not a hope, and it is the reason `datum merge` cannot be a thin
wrapper over `DOLT_MERGE`.

## 1.5 L1-E · Store-side leases

### The decision

```sql
CREATE TABLE lease (
  scope_kind VARCHAR(16) NOT NULL,   -- project|type|cycle|wave|phase|story|subsystem
  scope_key  VARCHAR(120) NOT NULL,
  token      BINARY(16)  NOT NULL,   -- RANDOM 128-bit, per-acquire. Never a counter.
  level      VARCHAR(10) NOT NULL,   -- local | published
  holder_role VARCHAR(64) NOT NULL,
  holder_actor VARCHAR(120) NOT NULL,
  acquired_at DATETIME   NOT NULL,
  expires_at  DATETIME   NOT NULL,   -- store-side clock, evaluated at every write
  reason      VARCHAR(200) NOT NULL,
  PRIMARY KEY (scope_kind, scope_key)
)
CREATE TABLE lease_event (            -- append-only: acquire|renew|release|expire|revoke|refuse
  txn_id BINARY(16) NOT NULL, ord INT NOT NULL, ...  PRIMARY KEY (txn_id, ord)
)
```

**Granularity.** Per-scope, never singular — invariant 11: "one global lock serializes the whole
project and makes parallel instances pointless" (I3, GAP-MATRIX.md:184–188). Declared scope kinds
reuse the vocabulary that already exists in the registry keys (`cycle`, `wave`, `phase`, `story`,
`subsystem`) plus `type` (for a per-type migration-stage flip) and `project` (schema migration only).

**The covering rule, which is the fail-closed part.** A write must present a token whose scope
*contains every artifact it touches*. If no single held lease covers the target set, the write is
refused and **the missing scope is named**. This removes the practical incentive to force: today one
mutex covers the whole branch, so two sessions on disjoint subsystems serialize
(VSDD-FACTORY-REVIEW.md:906–908).

**Two levels, because the clock cannot be global.** beads' warning is load-bearing: leases are
clone-local and never replicate, so TTL must exceed the sync interval (SCALE.md:212–214). And an
acquire over GitHub costs **~10–11.4 s** (SPEC.md:377–383; DECISIONS.md:191–193; REMOTE §2).
Therefore:

| level | scope kinds | ordering mechanism | cost |
|---|---|---|---|
| `local` | `story`, `subsystem`, `phase` | store-side row + TTL, orders the ~10–20 agents inside one clone | free |
| `published` | `cycle`, `wave`, `type`, `project` | acquire is pushed; cross-instance exclusion arbitrated by the push CAS, measured to yield **exactly one winner** across 3 clones (D6/G4) | ~8–10 s **per unit of work**, amortised over a whole wave |

This is SPEC.md's four coordination layers (L1 flock / L2 lease rows / L3 push rejection / L4 cell
merge, SPEC.md:56–64) with each scope kind assigned to a layer instead of left implicit.

**The token is random, not a counter.** Invariant 1: Dolt has no row locking and merges cell-by-cell,
so contenders writing *identical* values all get `affected_rows = 1` and all "win" —
`fence = fence + 1` failed **30/30 with all six writers winning** (SPEC.md:206–210). Naive ID
allocation produced `[1,1,1,1,1,1]` (SPEC.md:239–241).

**Expiry.** `expires_at` is set from the store's clock at acquire and evaluated by the store on every
write. An expired token is rejected *at write time* — which closes the measured absent
holdership re-check "where a >45-minute burst pushes under an expired lease and wins"
(VSDD-FACTORY-REVIEW.md:905–907). An expired row is not deleted by the writer; the next acquirer
moves it to `lease_event(kind='expire')`, so expiry is observable and attributable rather than
silent.

**No force path (invariant 21).** There are exactly three ways a scope becomes acquirable:
the holder releases, the TTL expires, or a **revocation**. A revocation is *not* a force write:
it is an ordinary validated write to the `lease` table that (a) requires a `human` role token,
(b) requires a reason, (c) appears in `lease_event` and `audit`, and (d) **touches no artifact and
discards no version**. That last clause is the whole distinction from the measured defect:
`factory-cas-push.sh` read its `--force-with-lease` value from the ref the fetch had just updated and
never rebased onto it, so it was `--force` with extra steps and *discarded a concurrent writer's
commits* (VSDD-FACTORY-REVIEW.md:889–896). A revocation cannot do that, because it cannot write an
artifact. **This bends F4** (which permits audited `--force` breaks) in favour of invariant 21, and
it is listed for ratification in §9.

Cost accepted: a crashed holder blocks its scope until TTL. Mitigated by per-scope-kind TTLs
(story: minutes; cycle: hours) and by the fact that a `local` lease dies with its clone's store
handle. SCALE.md:196–197 records the counter-argument — "a remote-ref lock has no kernel release …
it needs a TTL and a break-glass path" — which is why revocation exists at all rather than being
omitted.

## 1.6 L1-F · Append-only audit

```sql
CREATE TABLE audit (
  txn_id  BINARY(16)  NOT NULL,
  ord     INT         NOT NULL,
  at      DATETIME    NOT NULL,
  role    VARCHAR(64) NOT NULL,
  actor   VARCHAR(120) NOT NULL,
  lease_token BINARY(16) NULL,
  op      VARCHAR(24) NOT NULL,   -- create|update|retire|derive|ingest|render|read_deny|
                                  -- lease_*|gate_record|migrate|merge_refuse|txn_abandon
  type    VARCHAR(64) NULL,
  key_hash BINARY(20) NULL,       -- NULL for read_deny (see below)
  version_before INT NULL,
  version_after  INT NULL,
  reason  VARCHAR(400) NOT NULL,
  evidence_ref VARCHAR(200) NULL, -- for gate_record: the (cmd,stdout,exit,sha) tuple id
  PRIMARY KEY (txn_id, ord)
)
```

- **Append-only rows with unique keys, never mutable cells** — invariant 3 (D4/D5/D5b, verified
  8/8 across machines and again over GitHub, DECISIONS.md:30). PK `(txn_id, ord)` where `txn_id` is
  the per-attempt unique, so there is no shared counter to lose increments the way
  `[1,1,1,1,1,1]` did.
- **Written inside the data transaction**, so invariant 18's "no bypass path" is structural rather
  than promised. **Parity gate:** for every `txn`, `count(audit ops in {create,update,retire,
  derive,ingest}) == count(artifact_version rows)`. Any mismatch is a store bug, reported by
  `datum doctor`.
- **Read-denies record `{role, type, zone, at}` and NOT the key.** Recording the key would make the
  audit a side channel that reveals which walled id was asked for. The precedent is explicit: the
  cross-zone validator "reports counts and ids of dangling cross-zone refs only — never walled
  content — so it does not become a side channel" (DECISIONS.md:131–137). This still answers
  session-review's Dimension 6 ("did the information asymmetry walls hold?"), which today is
  unanswerable because dispatch identity is captured in 1,045 `agent.start` events and then dropped
  before any write (VSDD-FACTORY-REVIEW.md:1086–1088).
- It replaces hand-typed `producer:` frontmatter, which already carries **8 identities that are not
  agents** including 330 files by `phase-1-4b-bcs-agent-4` (VSDD-FACTORY-REVIEW.md:1089–1091), and
  the compaction trail of 8 `git show <SHA>` pointers that no skill produces and nothing verifies.

## 1.7 L1-G · Retention and compaction

### The decision

**Retention is a declared reachability predicate over the reference graph, not a time bound.**

`datum retain --window <N>` computes the version set that must remain resolvable:

1. every **current** version of every artifact;
2. every version cited by a reference whose `pin_policy` is `pinned` or `as_of` — this is a *query*,
   because the registry declares `pin_policy` per link type (registry yaml:200–219,
   `PinPolicyFor` at datum/registry.go:241–249);
3. every version inside the retention window;
4. every version named by a `version_alias` row.

Those versions' Dolt commits are tagged (a tag is a ref, therefore a gc root), then `dolt gc` runs.
Growth is ~6 KB/commit measured over 40 commits and gc reclaims (SPEC.md:195–196, test L7).

### Why a predicate rather than "keep 90 days"

The registry's own rule is that *a cite naming a version the target never had IS a finding,
regardless of pin policy* (registry yaml:498–502). A time-bound retention would delete cited
versions and turn correct documents into findings — the exact failure mode
`resolve-as-of` exists to prevent. So compaction must be **derived from the same graph the checker
reads**, and gated by that checker: `datum retain` runs the pinned-cite resolution gate **before** the
gc and refuses to proceed on any failure. Measure, then act.

### Pruned is not never-existed

```sql
-- a row in artifact_version with op='prune' and dolt_commit = '' (the commit is gone)
```

`datum show --at 7` on a pruned version answers *"pruned by retention policy R after <date>"*, never
*"never existed"*. Conflating them manufactures findings, and it is the same `dangling` vs
`unresolvable` discipline the registry already mandates (registry yaml:520–524).

**Invariant 15 is unaffected**, because `render`/`import` operate on current versions only. State
that explicitly so a future reader does not couple them.

**Honest gap:** long-horizon growth is unmodelled — "~6 KB/commit measured over 40 commits; years of
history and `gc` cadence are unmodelled" (SPEC.md:396–397). So retention ships with a *measurement
task* (growth per project per month at real write rates), not a default window. Naming a number here
would be exactly the "infer a consequence from a structural fact" error this repo has recorded five
times.

---

# 2. L2 — SCHEMA


### L1-0 · The engine property set (V-L)

The real risk is defending *"Dolt"* because this repository is named `datum (formerly dolt-artifact-spike)`. So the
requirements are declared, and the engine is swappable against them.

| # | required property | why it is load-bearing (all measured or invariant-pinned) |
|---|---|---|
| **P1** | **versioned, with a durable version identity** | invariants 15/18; `store_version` in every L7 response; `datum migrate verify` refuses on a moved pin |
| **P2** | **branch + merge** | D-B (gitignored store, committed render); the PR/CI join; migration abandonable at any stage |
| **P3** | **cell-level merge** | two agents editing DIFFERENT fields of one record must not conflict (D2/M3) |
| **P4** | **SQL-queryable, including RECURSIVE CTEs** | gates are queries; and per V-L, **traversal is a query** — measured: reachability 1–13 ms, whole-graph closure 356 ms |
| **P5** | **declarative referential integrity** | a dangling ref is REFUSED at write, not swept for — how 39 dangling refs and 27 `story.blocks` to never-written stories were found |
| **P6** | **embeddable: no server, no external binary, offline** | 132 tests in ~12 s with no network and no `dolt` binary; V-K's offline-capable requirement |
| **P7** | **transactional, one txn per unit of work** | invariant 18; measured **17×** (15.7 s → 0.9 s) |

**P1, P4 and P6 are the veto properties** — they are what the invariants and V-K's harness constraint
pin directly. Note P4 now includes recursive CTEs, which is a *new* requirement as of V-L: it was
previously assumed that graph traversal needed a separate engine, and measurement showed otherwise.

⚠ **Consequence for the graph:** the graph is a **projection**, not a second store. `artifact_ref`
carries the edges, traversal is a recursive CTE, and the in-process CSR engine is retained only for the
metrics SQL cannot express (articulation points; betweenness, which was tested and rejected). Do not
introduce a second engine for the graph — see spine §5e for the measurements.

## 2.1 L2-A · The registry generates the schema

### The measured distribution the decision rests on

| | n |
|---|---|
| types declared | **103 canonical + 16 gap + 4 retired = 119 live rows** |
| authority | authored **82** · derived **23** · ingested **14** |
| shape | document **80** · record **18** · append-only-event **11** · config **6** · blob-with-path **4** |
| key arity | 1 component **68** · 2 **37** · 3 **11** · 4 **3** |
| `key: [project]` singletons | **30** |
| types with a measured population of **0 files** | **29** |
| types with ~**1 file** | **33** |
| the head | BC **2,362** · adversarial-review **725** (+425 aliased) · story **369** · VP **215** · ADR **130** = **3,801 of ~3,900** |
| distinct field→enum bindings across all 119 types | **11** |

So: **five types carry ~97% of the artifacts, and 62 of 119 types have zero or one file.** A
per-type typed table means ~114 tables that exist to hold 0–4 rows each, and 119 `ALTER TABLE`
migrations every time the shared spine changes — against **N independently staged project stores**.

### The decision

**One uniform storage model, plus per-type generated VIEWS.** This is the hybrid's ergonomics
without the hybrid's second home.

```sql
-- the identity + FK anchor. ONE row per artifact, all 119 types.
CREATE TABLE artifact (
  type       VARCHAR(64)  NOT NULL,
  key_hash   BINARY(20)   NOT NULL,   -- deterministic hash of the canonical key tuple
  key_json   VARCHAR(512) NOT NULL,   -- the canonical typed key tuple
  authority  VARCHAR(12)  NOT NULL,   -- authored|derived|ingested (from the catalog, IMMUTABLE)
  shape      VARCHAR(20)  NOT NULL,
  cycle_id   VARCHAR(120) NULL,       -- scope axis; NOT NULL for types declaring the cycle axis
  path       VARCHAR(512) NOT NULL,   -- DERIVED, UNIQUE, never identity (D-C). Recompute-gated.
  PRIMARY KEY (type, key_hash),
  UNIQUE KEY uk_path (path),
  KEY idx_cycle (type, cycle_id)
)

-- every declared field of every type, one row per field.
CREATE TABLE artifact_field (
  type VARCHAR(64) NOT NULL, key_hash BINARY(20) NOT NULL,
  field VARCHAR(64) NOT NULL,
  ord   INT         NOT NULL DEFAULT 0,   -- list position; 0 for scalars
  kind  VARCHAR(12) NOT NULL,             -- text|int|date|enum|ref|bool  (declared in the catalog)
  v_text VARCHAR(2000) NULL, v_int BIGINT NULL, v_date DATETIME NULL,
  PRIMARY KEY (type, key_hash, field, ord),
  CONSTRAINT fk_af_artifact FOREIGN KEY (type, key_hash)
    REFERENCES artifact (type, key_hash) ON DELETE CASCADE
)

-- per-type generated view, emitted by `datum migrate` from the catalog. NOT hand-written.
CREATE VIEW v_behavioral_contract AS
SELECT a.key_json AS bc_id, a.path, a.cycle_id,
       MAX(CASE WHEN f.field='subsystem'        THEN f.v_text END) AS subsystem,
       MAX(CASE WHEN f.field='capability'       THEN f.v_text END) AS capability,
       MAX(CASE WHEN f.field='lifecycle_status' THEN f.v_text END) AS lifecycle_status
FROM artifact a LEFT JOIN artifact_field f USING (type, key_hash)
WHERE a.type='behavioral-contract' GROUP BY a.type, a.key_hash;
```

### Why this, and not typed tables or a plain hybrid

**1. Migration cost is the binding constraint, and it is per-project × per-type.** V-F requires "N
independent migrations against one shared registry, each independently stageable and abandonable". A
field addition here is a catalog row plus a regenerated view — no `ALTER TABLE`, so no per-project
DDL coordination, and no risk of E6's "two devs adding the same column differently"
(SPEC.md:185) at the artifact level.

**2. It is the only shape in which coverage is *definitional*.** "18 of 70 types modeled" → 119 of
119 is not 101 engineering tasks; it is a consequence of `datum migrate` reading the registry. That is
the single strongest argument, and it is the acceptance criterion M1 already states
(VSDD-FACTORY-REVIEW.md:800–804).

**3. A hybrid has two homes, and two homes drift.** That is this repository's central measured
result — 46 vs 81 type names overlapping on 11 (registry yaml:23–34); four STORY-INDEX schemas; a
type definition split across four disagreeing places (VSDD-FACTORY-REVIEW.md:913–915). Choosing a
"typed core + generic tail" recreates it: the same field would have two representations, and a type
crossing the volume threshold would need a data migration between them. **Refused on the project's
own evidence.**

**4. FK integrity is preserved where it earns its keep.** Design rule 2 (every cross-reference is a
row with FKs on both ends) is what makes a dangling ref *refused* rather than swept for, and the
importer's practice of recording every FK-refused edge as a finding is how the 39 dangling refs and
the 27 `story.blocks` to never-written stories were found (registry yaml:974–983). The FK anchor
here is `artifact`, and edges (§2.4) are real rows with real FKs. **The node's field storage being
EAV costs nothing in referential integrity.**

**5. Under Dolt, field-per-row *reduces* the conflict surface.** DECISIONS.md:29–36 classifies
tables: A derived (cannot conflict), B append-only distinct PKs (cannot conflict), C mutable record
cells (the only genuine class). Cell-level merge already means two agents editing *different fields
of the same record* merge cleanly (D2/M3). With fields as rows, different fields are different
*rows* — a strictly smaller collision surface, leaving only same-field-same-artifact, which is
exactly the case that *should* conflict.

### The costs, stated plainly

| Cost | Mitigation | Status |
|---|---|---|
| A field's SQL type is not enforced by the database | `kind` column + write-time validation + a gate asserting every stored `kind` matches the catalog's declared kind | designed |
| Wide-row reads become a pivot | generated views; field mass is order 10⁵ rows per corpus and the measured workload is small (2,421 nodes / 4,060 edges; 4-hop whole-corpus rollup **3 ms**; FULLTEXT over 1,959 bodies **0.15 s**) | **must be measured, not assumed** — see §9 |
| More rows per commit → faster history growth | ~6 KB/commit is the only measurement we have (over 40 commits) | **must be measured** |
| A merge can synthesize an invalid artifact | mandatory post-merge revalidation, refuse not resolve (§1.4) | designed |

**Declared fallback, with its acceptance test:** if measurement shows a generated view is too slow
for the head types, materialize *that* view as a generated table and add a parity gate
`table == view` over the full population. Materialization is a measured response, never a default,
and it never becomes a second authoring surface.

### The catalog must be ROWS, not only Go structs

Gates are queries — "a gate that is a query cannot disagree with the data it checks"
(SPEC.md:146–148).
So the registry is mirrored into the store:

```sql
CREATE TABLE cat_type   (type, family, profile, shape, authority, section_policy,
                         gate_severity, enforcement_level, enforcement_point,
                         derivation_stage, scope_predicate, pending_template, PRIMARY KEY(type))
CREATE TABLE cat_field  (type, field, required, kind, enum_name, link_type, list, PRIMARY KEY(type,field))
CREATE TABLE cat_key    (type, ord, name, kind, format, PRIMARY KEY(type,ord))
CREATE TABLE cat_enum   (enum, value, category, rank, PRIMARY KEY(enum,value))
CREATE TABLE cat_enum_migration (enum, from_value, to_value, extra_json, PRIMARY KEY(enum,from_value))
CREATE TABLE cat_link   (link_type, target_type, cardinality, pin_policy, symmetric_with,
                         carries_version, PRIMARY KEY(link_type,target_type))
CREATE TABLE cat_section(type, ord, heading, PRIMARY KEY(type,ord))
CREATE TABLE cat_alias  (alias, canonical, set_json, retire_after, PRIMARY KEY(alias))
```

**This is a mirror, so it must not be able to drift.** It is `authority: derived`, regenerated at
`datum migrate`, and **gated by a content hash**: `hash(catalog rows) == hash(embedded registry)`,
asserted at every store open, failing `datum doctor` on mismatch. The registry stays the single
canonical copy in `datum/registry/` — embedded *and* read by the Python tooling
(datum/registry.go:5–10) — precisely so there is no second copy to drift; the mirror is a projection of
it, and the hash gate is the parity proof.

## 2.2 L2-B · Typed natural keys, `id_alias`, `reserved_key`

### Keys are parsed, not matched as path segments

D-C. Each type's `key:` list (arity 1–4, measured 68/37/11/3) plus its `key_format:` yields a parser
per key **kind**:

| kind | canonical form | example type |
|---|---|---|
| `bc_id` | `BC-{ss:int}.{grp:int}.{seq:int}` → 3 ints | behavioral-contract |
| `vp_id` / `adr_id` / `epic_id` / `hs_id` / `cap_id` | `PREFIX-{seq:int}` | verification-property, adr, epic, holdout-scenario |
| `story_id` | `S-{epic:int}.{seq:int}` | story |
| `cycle_id`, `slug`, `text` | normalized string | cycle-manifest, domain-spec-section |
| `int`, `date` | typed scalar | pr_number, measured_at |
| `path` | normalized relative path | the 5 `key: [path]` types |
| `project` | the store's declared project | the 30 singleton types |

The parser is the enforcement: `BC-2.02.013-host-run-subprocess.md` **fails the parse and is refused
at write**. Today it passes the path hook because `{bc-id}` matches a whole segment, and it is
simultaneously the one BC absent from its own index (VSDD-FACTORY-REVIEW.md:745–747). Normalization
also kills `"P1"` vs `P1` (measured 44 vs 17 inside one corpus, enums.yaml:293–296) and
`STORY-INDEX.md` vs `story-index.md` case drift that would break on Linux CI.

Storage: `artifact.key_json` (canonical) + `key_hash` for index width — the current schema already
had to check the 3,072-byte index limit by hand and says so (datum/schema.go:150–155). Typed components
also land as rows so prefix/range queries work:

```sql
CREATE TABLE artifact_key_part (
  type VARCHAR(64) NOT NULL, key_hash BINARY(20) NOT NULL, ord INT NOT NULL,
  v_text VARCHAR(200) NULL, v_int BIGINT NULL,
  PRIMARY KEY (type, key_hash, ord), KEY idx_kp (type, ord, v_int, v_text)
)
```

This is what makes the `bc_family` prose-ref kind (`BC-7.03`, **893 refs**) resolvable under its own
rule — "it is a reference to a SET, so it resolves iff at least one `BC-7.03.*` exists"
(registry yaml:447–454) — as a range scan instead of a LIKE over strings.

**Two types key from the filename today** — `behavioral-contract` and `verification-property`
carry no `bc_id`/`vp_id` field (registry yaml:719, 792). Declaring those keys `required` generated
**2,272 false findings on correct files** (registry yaml:125–134), which is why `RequiredFor` skips
`key_source: filename` components (datum/registry.go:203–222). L2's job is to make that a **one-time
migration step**, not a permanent tolerance: import materializes the id into the record, and after
cutover `key_source: filename` is no longer a legal declaration. Until the id is in the store, the
1,852 measured BC renames are silent identity changes.

### `path` is derived, unique, and recompute-gated

`path = compute_path(type, key)` from the path registry. It must be stored to be UNIQUE-enforced
(two artifacts computing one path is a real defect worth refusing), and storing a derivable value
needs an answer to invariant 17. The answer is `authority`, which is the mechanism invariant 17
names: **a value with `authority: derived` is a cache with a declared generator, not an independent
stored value.** So the reading is:

> Invariant 17 forbids an **authored** value derivable from another stored value. A **derived**
> value is regenerated, never edited, and gated by recomputation.

Load-bearing in exactly three places — `artifact.path`, the catalog mirror, and any materialized
view — each of which carries a recomputation gate. Listed in §9 for ratification because it is a
reading of a binding invariant.

### The two ledgers

```sql
CREATE TABLE id_alias (               -- D-C. History must keep resolving.
  type VARCHAR(64) NOT NULL, old_key_hash BINARY(20) NOT NULL,
  old_key_json VARCHAR(512) NOT NULL, new_key_hash BINARY(20) NOT NULL,
  from_version INT NOT NULL,          -- the version at which the rename took effect
  reason VARCHAR(400) NOT NULL, retire_after VARCHAR(200) NOT NULL,
  PRIMARY KEY (type, old_key_hash)
)
CREATE TABLE reserved_key (           -- the tombstone / reserved-id ledger
  type VARCHAR(64) NOT NULL, key_json VARCHAR(512) NOT NULL,
  state VARCHAR(16) NOT NULL,         -- retired|withdrawn|never_issued|aliased_away
  reason VARCHAR(400) NOT NULL, at DATETIME NOT NULL,
  PRIMARY KEY (type, key_json)
)
```

- `id_alias` is seeded from the two hand-maintained mapping documents that *are* an id_alias table in
  markdown — `behavioral-contract-id-mapping` and `story-id-mapping`, both declared
  `authority: derived` and "SUPERSEDED BY the id_alias ledger (D-C)" (registry yaml:764–781,
  1001–1015) — which then retire.
- Resolution is `as_of` by default, which is the safe default: "it can under-report, but it cannot
  manufacture a finding against a correct historical document" (registry yaml:238–240,
  datum/registry.go:241–249). `BC-1.12.008 → BC-3.05.004` was a *legitimate* renumbering.
- `reserved_key.state = withdrawn` is the representation HANDOFF.md:112–114 lists as missing —
  a withdrawn-in-place row (`~~BC-2.02.013~~`).
- `never_issued` covers reserved slots, e.g. the POLICY 11/12 slots that "the third custom policy
  silently consumes" (VSDD-FACTORY-REVIEW.md:983–984).
- **Minting** scans `artifact ∪ reserved_key ∪ id_alias(old)` inside the type's lease and one
  transaction. That kills `create-adr` being the only allocator and explicitly non-atomic ("Users
  SHOULD serialize") and `policy-add`'s `max_id + 1` race (F11).

## 2.3 L2-C · Closed enums validated at write time

**17 enums.** They bind in two distinct places, which is worth stating because it is why the catalog
must be rows:

- **10 bind to artifact FIELDS:** `status`, `producer`, `gate_result`, `level`, `severity_max`,
  `convergence`, `priority`, `lifecycle_status`, `scope`, `reviewer_role`.
- **7 bind to the CATALOG** (they describe types, not artifacts): `shape`, `authority`,
  `pin_policy`, `derivation_stage`, `enforcement_point`, `gate_severity`, `enforcement_level`.

Measured field→enum bindings across all 119 types: **11 distinct pairs**, mass concentrated in
`status`→`status` (91 types) and `producer`→`producer` (77). Note two subtleties the binding must
preserve: the field name is **not** the enum name (`severity` → enum `severity_max`, on
`adversarial-finding` and `tech-debt-register`), and `producer` is `open_extension` while every other
artifact-field enum is hard-closed.

### The write-path rule

`CheckEnum` already returns the right four verdicts (datum/registry.go:251–272). L2 assigns each a
behaviour, and the assignment is the design:

| verdict | write path | import path |
|---|---|---|
| `ok` | accept | accept |
| `illegal` | **REFUSE** (invariant 20) | record a finding; route the value to `unmodeled_file` adjudication |
| `migratable` | **REFUSE** — a legacy spelling is not writable | **accept once**, applying the migration's `extra` fields |
| `unchecked` (`open_extension`) | accept **only if the name is declared in the project's profile**; else refuse | accept, record the undeclared name |

`migratable` being refused on write is what makes V-C real: 21 verdict tokens, 17 severity tokens,
11 closure tokens resolve **once, at migration**, and are unrepresentable thereafter. And the
migration is not a rename — it splits axes: `BLOCKED-hard` → `{gate_result: BLOCKED,
severity_max: HIGH}`, `CLEAN_PASS_1_OF_3` → `{gate_result: CLEAN, convergence: CLEAN_STREAK,
streak: 1}` (enums.yaml:40–67). `cat_enum_migration.extra_json` carries exactly that.

`open_extension` needs the beads discipline verbatim, because it is what makes multi-tenancy possible
at all: **projects add NAMES; projects never add CATEGORIES; core logic queries `category`, never
`name`** (enums.yaml:8–11, CROSS-CORPUS.md:188–201). prism and vsdd-factory share **zero** `verdict`
values (CROSS-CORPUS.md:137), so no canonical name list can be imposed without invalidating one of
them — but both map onto the same categories.

### Forbidden fields are refused, not warned

`defaults.forbidden` = `verdict`, `delta`, `changelog` (registry yaml:157–163). A write carrying one
is **refused**, and for the types where a `## Changelog` *section* is retired the section is refused
too. That makes D-D irreversible rather than aspirational — `delta` is present on all 18
`ux-spec-flow` files and `verdict` on 476 vsdd values across 14 spellings.

### Two defects in the current schema this rule catches

- `version_cite.verdict` (datum/schema.go:294) **stores a derived value**: the verdict is
  `f(pin_policy, cited_version, target history)`, and the registry says so — "a version cite is
  judged by its link's pin_policy, not by whether it matches today" (registry yaml:491–497). Under
  L2 the verdict is computed at gate time and never stored.
- `finding.occurrences INT` (datum/schema.go:183) stores a count. It is defensible only if the things
  counted are not rows; if they are, it violates design rule 1. Resolve during migration — declare
  the exception with a reason, or make the occurrences rows.

## 2.4 L2-D · Typed references, and ONE declared incompleteness state

```sql
CREATE TABLE artifact_ref (
  src_type VARCHAR(64) NOT NULL, src_key_hash BINARY(20) NOT NULL,
  link_type VARCHAR(64) NOT NULL, ord INT NOT NULL,
  target_type VARCHAR(64) NOT NULL,
  target_key_hash BINARY(20) NOT NULL,       -- hash of the RAW target when unresolved
  target_key_json VARCHAR(512) NOT NULL,     -- verbatim as written; never normalized away
  clause   VARCHAR(64)  NOT NULL DEFAULT '', -- 'postcondition 1' — the mis-anchor class
  target_ord INT NOT NULL DEFAULT -1,        -- D-A section ordinal when the target is a section
  cited_version INT NULL,                    -- only when the link carries_version
  state    VARCHAR(16) NOT NULL,             -- the closed ref_state enum, below
  state_reason VARCHAR(200) NOT NULL DEFAULT '',
  PRIMARY KEY (src_type, src_key_hash, link_type, ord),
  KEY idx_ref_target (target_type, target_key_hash),
  CONSTRAINT fk_ref_src FOREIGN KEY (src_type, src_key_hash)
    REFERENCES artifact (type, key_hash) ON DELETE CASCADE
)
```

### Target-type checking at write time

`cat_link` holds `link_types[*].targets` (23 link types declared). A write whose target's *type* is
not in the declared universe is **refused**. That eliminates `capability: "E-12"` — 7 BCs carrying an
epic id in a capability field (VSDD-FACTORY-REVIEW.md:973) — at write time rather than by sweep. It
also enforces the link rules the registry already states: a link field holds **IDs ONLY**, against
the measured 16 `VP.scope is multi-valued`, 8 `VP.bcs holds an id plus prose`, 7 `VP.bcs value is
not an id`, 4 `story.functional_requirements not an id`, 2 `bc.replacement holds prose`, and
`see PO output for actual IDs` sitting in a traceability field (registry yaml:227–230).

**No FK on the target.** Deliberate, and the current schema already made this call for the right
reason: "the corpus traces to ids that do not exist, and an FK would refuse the import and DESTROY
the finding" (datum/schema.go:249–252). The integrity is bought back by `state` plus a gate, not by the
database. Cross-zone targets (holdout → BC) get the same treatment, which is D2's accepted cost with
its already-mandated remedy — the cross-zone validator as "a required deliverable, not an optional
extra" (DECISIONS.md:131–137).

### `ref_state` — one closed enum, seven measured values

The brief asks for placeholder/incompleteness as **ONE declared state**. It is one *enum*, and every
value is a measured distinction that has already produced false findings when collapsed:

| state | meaning | evidence |
|---|---|---|
| `resolved` | the target exists at the resolved version | — |
| `placeholder` | deliberate incompleteness; requires `state_reason` | **1,465 placeholders in 3 dialects** (`BC-4.NN.001`, `see PO output for actual IDs`, `TBD`) — FA-V1-DESIGN.md:58 |
| `dangling` | a well-formed id that does not resolve | 39 dangling refs, 27 of them `story.blocks` to never-written stories (S-8.09 alone claims 19) |
| `unresolvable` | the OWNER of a file-scoped sub-id is unstated | `report-unresolvable-separately`: collapsing this into `dangling` "is how a prose extractor produces a large, confident, wrong finding set" (registry yaml:520–524) |
| `declared_gap` | the cell marks itself a gap (`[process-gap]`, "v1.1 candidate", "uncontracted") | treating these as traces produced 55 POLICY-8 + 50 dangling findings, **50 of 53 of the entire dangling class**, blaming documents for correctly documenting a gap (registry yaml:503–512) |
| `proposed_name` | `BC-10.13.012-release-yml-prerelease-flag-emission` is a proposed NAME, not a ref | registry yaml:513–519 |
| `pruned` | the cited version existed and was removed by retention | §1.7 — distinct from "never existed", which IS a finding |

**Placeholders get a budget, not a prohibition** (F10): accepted at write with a reason, counted per
type by an aggregate gate, ratcheted down. That is the only shape that survives contact with a real
corpus, and it is the difference between "how complete is the capability link?" being answerable and
being ungreppable.

### Symmetric pairs, and cite verdicts

- `symmetric_with` pairs (`depends_on`/`blocks`, `supersedes`/`superseded_by`) are **stored once**;
  the reverse is a generated view. "The 58 `direction` findings in datum's baseline are one class with
  one fix: store a single dependency direction, not 58 corrected entries" (registry yaml:231–233).
  The store must *refuse* a write to the derived direction.
- `carries_version` links (`index_cite` → `floating`, `reviewed_version` → `pinned`) store
  `cited_version`; the **verdict is computed** from `pin_policy` + history at gate time.
  `floating + lagging` = finding; `pinned + lagging` = correct and reporting it is the checker's
  defect; `pinned` to a version that never existed = finding either way — the check that "requires
  HISTORY, so it is one a markdown-only checker cannot make" (registry yaml:498–502).
- Section refs use `target_ord` as the canonical form, with resolvers for the other two measured
  addressing schemes (heading name, item-within-section). 214 refs are currently dangling under the
  ordinal-only resolver, reported **aggregate-only on purpose** until per-reference precision is
  measured (HANDOFF.md:103–105) — L2 keeps that discipline: the state is stored per ref, the
  *reporting* granularity is earned.

## 2.5 L2-E · `authority` enforced structurally

`artifact.authority` is copied from `cat_type` at create and is **immutable**. The write path
branches on it, and — the part that makes this structural rather than a check — **a `derived` type
has no `artifact_field` rows at all: it is a VIEW.** There is nothing to author.

| authority | n | write surface | structural mechanism |
|---|---|---|---|
| `authored` | 82 | `datum <verb>` by a role the manifest permits | refused for derived/ingested types |
| `derived` | 23 | **none** — the derivation engine only | the type is a view by default; if materialized, only `txn.op='derive'` may write it and the parity gate must hold |
| `ingested` | 14 | `datum ingest` only, requiring `source` = (tool, version, invocation) | rows are marked non-authoritative for gates that require authored judgement |

The five highest-churn paths in the corpus are all derived — STORY-INDEX 381 commits, BC-INDEX 218,
ARCH-INDEX 151, VP-INDEX 140, cycles/INDEX 98 — and storing them "is the direct cause of the count
drift `datum validate` reports (ARCH-INDEX says 1949, BC-INDEX frontmatter says 1955, disk says 1959)"
(enums.yaml:337–343). As views, they cannot disagree with their source because they *are* their
source.

### `derivation_stage` and the missing scope predicate

All 23 derived types carry `derivation_stage: shadow` (measured: 23 of 23), because "an
`authority: derived` type cannot simply be FLIPPED to derived: if the generator is subtly wrong,
hand-maintained drift is replaced by generated drift AND the evidence is deleted"
(enums.yaml:382–407). L2 adds the piece HANDOFF.md:52 names as blocking:

> **A derived type may not be derived at all until its `scope_predicate` is declared in the
> registry.** The store refuses to materialize or view a derived type whose `cat_type.scope_predicate`
> is empty.

This is the fix for the single most valuable transferable result in the spike: 41 of 148 stories live
in `stories/v1.0-legacy/` and STORY-INDEX deliberately omits them (verified as exact set equality,
41 == 41). Generating from every record would have **resurrected 41 retired stories while every
count still agreed** — "a defect no count, id-set or cell check would catch" — and story 4 hit the
identical class independently, where `findings_total` counts only the findings a pass OWNS, not the
412 it re-states (HANDOFF.md:45–52, datum/schema.go:205–209). Today that scope lives in Go
(`shadowSpecs`); it belongs beside `derivation_stage`.

So the registry gains, per derived type:

```yaml
derivation:
  stage: shadow            # shadow | proven | retired
  scope_predicate: >       # REQUIRED. The declared subset the artifact means.
    story.path NOT LIKE 'stories/v1.0-legacy/%'
  inputs: [story, epic]    # the version-set that keys staleness (F8)
  ordering: [wave, story_id]
```

Staleness is then **computed from `inputs` + history**, never stored — which retires the `input-hash`
field on **3,890 files** whose own archive text admits it reports "spurious DRIFT" and which ships a
`PENDING-RECOMPUTE` sentinel, i.e. is routinely knowingly wrong (registry yaml:2681–2694).

## 2.6 L2-F · Scope, and refusing unscoped aggregates

Three axes, each with a mechanism:

| axis | mechanism | omittable? |
|---|---|---|
| **project** | physical store selection (§1.1) | **no** |
| **cycle / wave / story** | `artifact.cycle_id` + per-type declared `scope_axes` in `cat_type`; NOT NULL where the type declares the axis | no — a NULL where the axis is declared is refused at write |
| **lifecycle** | `status` (lifecycle only, D-D) and `lifecycle_status` for spec objects | no |

**Refusing an unscoped aggregate (invariant 19).** Aggregates are not free-form SQL. They are the
registry's **named query verbs** (`count`, `validate`, `waves`, `graph`, and phase-2's `get`,
`trace`, `coverage`, `history`, `asof`, `diff`, `impact` — registry yaml:254–288), and a verb's
catalog row **must name the scope axes it ranges over**. An unnamed axis is a refusal, not a default.
The reasoning is already settled by measurement: SQL does every hard part, so "the question was never
the language, it is WHO QUERIES HOLDING WHAT — an LLM composing joins across 25 tables returns
plausible-but-wrong answers with NO error" (registry yaml:242–253).

`datum sql --read-only` stays available for exploration — deliberately, "so nobody has to fake a verb to
ask a one-off question" — but its output is **non-citable as gate evidence**. Invariant 22 requires
machine-produced evidence, and `datum gate exec` produces a `(command, stdout, exit, sha)` tuple that
`datum` itself produced (VSDD-FACTORY-REVIEW.md:1036–1038).

### The `status` / `lifecycle_status` collision, which L2 cannot settle alone

Measured: **`status` and `lifecycle_status` disagree on 1,949 of the 1,959 BC files carrying both**,
and nothing reports it today (HANDOFF.md:90–92). Two fields for one concept is D-D's territory. L2
provides the *mechanism* and defers the *call*:

```sql
CREATE TABLE cat_lifecycle_compat (status_category VARCHAR(16), lifecycle_category VARCHAR(16),
                                   legal BOOL, PRIMARY KEY (status_category, lifecycle_category))
```

With a declared truth table the 1,949 disagreements become **one gate with one verdict** instead of
1,949 findings or zero. Which side wins per type is an adjudication (§9).

## 2.7 L2-G · Field-name collision safety

**The rule.** A **field**, **closed-enum value**, **type**, **link type** or **section** name may not
be claimed until it has been censused against **every project registered in `projects.yaml`** — not
against vsdd-factory, and not against the three corpora that happen to be convenient.

**The evidence is two instances, both caught only after the fact:**

- **`gate`** is already a prism *identifier*: `gate: wave-3-integration-gate`, beside `gate_step` and
  `gate_step_name`, **40 files**. Naming the outcome field `gate` would have collided with a live
  field carrying a different meaning, so it is `gate_result` (enums.yaml:27–30, registry
  yaml:2426–2429).
- **`scope`** is already in use with **two different meanings**: prism uses it for blast radius
  (PR-LEVEL 86 · LOCAL 86 · spec 36 = **208 files**) while vsdd uses it for the *target* (SS-01 20 ·
  SS-03 14 · s7-03-spec 15). The resolution kept prism's semantics and migrated vsdd's usage to a
  separate `target` field (enums.yaml:209–222).

**The mechanism.**

```sql
CREATE TABLE field_claim (
  namespace VARCHAR(16) NOT NULL,   -- field|enum_value|type|link|section
  name VARCHAR(64) NOT NULL,
  claimed_at DATETIME NOT NULL,
  censused_projects VARCHAR(500) NOT NULL,   -- the project set at claim time
  hits_json LONGTEXT NOT NULL,               -- per-project occurrence counts + sample values
  verdict VARCHAR(12) NOT NULL,              -- free|taken|taken_different_meaning
  note VARCHAR(400) NOT NULL,
  PRIMARY KEY (namespace, name)
)
```

- `datum registry claim <namespace> <name>` runs the census over every registered project and **refuses
  on `taken_different_meaning`**, printing the colliding corpus, count and sample values.
- New registry check `[1x]`: every name in `cat_field` / `cat_enum` / `cat_type` / `cat_link` has a
  `field_claim` row whose `censused_projects` ⊇ the registered project set *at claim time*. A claim
  made before a project was registered is re-censused when that project registers — otherwise adding
  a project silently invalidates old claims.
- Extend to **store-reserved names**: `version`, `timestamp`, `path`, `section`, `authority`,
  `project`, `cycle`, `body`, `key`, `txn`, `lease`, `audit`. A project field colliding with one of
  these is refused at claim time.
- **This design already had to apply the rule to itself.** "Quarantine" is taken: `quarantine` in
  this binary is the staging-ref policy for `datum aggregate`
  (`refs/dolt/quarantine/*`, datum/quarantine.go:32–34). Hence §2.8's capture table is `unmodeled_file`,
  not `quarantine`.

## 2.8 L2-H · Coverage: every type has a home; the tail is not special

Coverage is **definitional** under L2-A: `datum migrate` reads 119 catalog rows and every one of them
gets identity, body, sections, fields, and refs. There is no per-type table to write, so
"18 of 70 → 100%" is not 101 tasks. What remains is the *disposition ladder* for an observed
`document_type`, which `Resolve` already implements (datum/registry.go:174–198):

| resolution | disposition |
|---|---|
| **canonical** (103) | its home |
| **alias** (180) | canonical home **plus the `set:` fields the spelling was carrying** — a rename alone destroys `scope` and `reviewer_role` (aliases.yaml:1–11, 80–88) |
| **gap type** (16, `pending_template: true`) | a home, gated at `info`, until a template exists. "Gating a project for using a concept the standard forgot would be the registry's own defect" (registry yaml:2361–2363) |
| **retired** (4 + 6 alias-retired) | migrate per the declared `migration:`, verify by count assertion, **then** delete |
| **unresolved** (3) | declared unresolved; adjudicated, not guessed |
| **unknown** | **`unmodeled_file`** — verbatim bytes captured, never dropped |

```sql
CREATE TABLE unmodeled_file (
  src_path VARCHAR(512) NOT NULL,
  observed_document_type VARCHAR(200) NOT NULL,
  body LONGBLOB NOT NULL,           -- verbatim. A parser that loses input is the #1 repeated defect.
  reason VARCHAR(200) NOT NULL,     -- unknown_type | unparseable_key | forbidden_field | no_frontmatter
  at DATETIME NOT NULL,
  PRIMARY KEY (src_path)
)
```

This is what makes M6's acceptance a **query** rather than a declaration: every file accounted for
as migrated / declared-out-of-scope / rejected-with-reason, byte-exact round trip for 100% of
bodies, count parity per type, the 18,826-finding baseline preserved across the move, and **zero
unmodeled `document_type` values** (VSDD-FACTORY-REVIEW.md:832–837).

**The 108 singleton non-canonical values are deliberately NOT aliased.** "Aliasing 108 singletons
would encode the drift permanently under the appearance of fixing it" (aliases.yaml:21–25). They go
to `unmodeled_file` and are adjudicated — alias the head, gate the tail.

**14% of files (461) have no table today.** Under L2 they resolve to one of the rows above, and
`datum doctor` reports the count in each bucket per project. That number becoming zero is the migration
gate, not a design assumption.

---

# 3. Consolidated DDL sketch

Design, not implementation. Zone assignment noted; `open` unless stated.

```
IDENTITY + CONTENT
  artifact(type, key_hash, key_json, authority, shape, cycle_id, path)     PK(type,key_hash) UK(path)
  artifact_key_part(type, key_hash, ord, v_text, v_int)
  artifact_field(type, key_hash, field, ord, kind, v_text, v_int, v_date)
  artifact_body(type, key_hash, body)
  artifact_section(type, key_hash, ord, depth, heading, body)
  artifact_ref(src_type, src_key_hash, link_type, ord, target_type, target_key_hash,
               target_key_json, clause, target_ord, cited_version, state, state_reason)
  artifact_entry(type, key_hash, entry_ord, entry_id, entry_body, ...)   -- append-only-event shape
  blob_ref(type, key_hash, path, content_sha)                            -- blob-with-path shape

VERSION + PROVENANCE
  artifact_version(type, key_hash, version, txn_id, dolt_commit, op)      -- version lives HERE only
  version_alias(type, key_hash, cited_form, version, source)             -- migration device
  id_alias(type, old_key_hash, old_key_json, new_key_hash, from_version, reason, retire_after)
  reserved_key(type, key_json, state, reason, at)

TRANSACTION + COORDINATION
  txn(txn_id, idem_key, role, actor, lease_token, op, state, opened_at, result_json)
  xstore_intent(idem_key, anchor_store, participant_store, ops_json, at)
  lease(scope_kind, scope_key, token, level, holder_role, holder_actor, acquired_at, expires_at, reason)
  lease_event(txn_id, ord, kind, scope_kind, scope_key, role, actor, reason, at)
  conflict(txn_id, ord, scope, tbl, pk_json, base_json, ours_json, theirs_json, ours_commit,
           theirs_commit, actor, at)                                     -- DECISIONS D1, class B
  audit(txn_id, ord, at, role, actor, lease_token, op, type, key_hash,
        version_before, version_after, reason, evidence_ref)

CATALOG (derived mirror of the registry; hash-gated at every open)
  cat_type · cat_field · cat_key · cat_enum · cat_enum_migration · cat_link · cat_section ·
  cat_alias · cat_verb(verb, scope_axes, output_schema) · cat_lifecycle_compat
  field_claim(namespace, name, claimed_at, censused_projects, hits_json, verdict, note)

MIGRATION + OPS
  schema_migrations(version, name, applied_at)          -- exists; now per-project by construction
  registry_state(registry_hash, registry_version, applied_at)
  unmodeled_file(src_path, observed_document_type, body, reason, at)
  import_run(fingerprint, fa_version, ...)              -- exists; content-keyed, clock-free
  corpus_assertion(source, kind, subject, claimed)      -- exists; the declared exception

GENERATED VIEWS (one per type, emitted from cat_*; never hand-written)
  v_<type> ...                                          -- 119 of them
  v_<link>_reverse ...                                  -- derived direction of each symmetric pair

WALLED ZONE (separate directory; no cross-zone FK — bought back by `datum validate --cross-zone`)
  the same tables, holding only walled types (holdout-scenario, adversarial-finding, evaluation)
```

---

# 4. Invariant → mechanism map

| Inv | Mechanism in this design |
|---|---|
| **1** per-attempt unique value | lease `token` and `txn_id` are random 128-bit; `audit`/`lease_event` PK is `(txn_id, ord)`; no counter anywhere (§1.5, §1.6) |
| **2** abort/resolve on conflict | `merge --abort` in the one code path; `conflict` rows; post-merge revalidation refuses (§1.4) |
| **3** append-only counters | `artifact_version`, `audit`, `lease_event`, `artifact_entry`, `conflict` — all insert-only with unique PKs |
| **4** idempotent retries | `txn.idem_key` UNIQUE; committed replay returns `result_json`; no-op write produces no commit (§1.2, §1.4) |
| **6** one transaction per unit of work | one SQL txn + one Dolt commit; `txn` row inside it (§1.4) |
| **9** zones as directories | project → zone directory matrix; per-zone handles (§1.1) |
| **11** leases per-scope | 7 declared scope kinds + the covering rule (§1.5) |
| **12** per-branch contention | store-per-project puts each project on its own data ref (§1.1) |
| **14** every writer a clone | project = lineage; cross-project merge never attempted (§1.1) |
| **15** `import(render(store)) == store` | binds at cutover; per-type gate before `authoritative`; retention operates on current versions only (§1.3, §1.7) |
| **16** verbatim body + partition | `artifact_body` + `artifact_section`, all shapes, byte-exact gate; exemptions **declared** per shape (§1.3) |
| **17** nothing derivable stored | `version` not stored; counts derived; catalog/path/materialized views are `authority: derived` with recomputation gates (§1.2, §2.2, §2.5) |
| **18** lease→validate→transact→version→audit | one write path; all five inside one transaction; audit/version parity gate (§1.4, §1.6) |
| **19** declared scope predicate | project = store selection; `cat_type.scope_axes`; `cat_verb.scope_axes` mandatory; derived types blocked without `scope_predicate` (§2.5, §2.6) |
| **20** write-time validation | typed key parsers, `CheckEnum` refusing `illegal`/`migratable`, target-type checking, forbidden fields (§2.2–§2.4) |
| **21** no force path | lease revocation writes no artifact and discards no version; merges refused, never resolved (§1.4, §1.5) |
| **22** gate evidence | `audit.evidence_ref` → the `(cmd,stdout,exit,sha)` tuple; `datum sql` output non-citable (§2.6) |
| **23** store-assigned identity, never in content | `version` from the ledger; `path` derived; the authored `version`/`input-hash`/SHA fields are refused (§1.2, §2.5) |

---

# 5. Rejected alternatives

| # | Rejected | Why |
|---|---|---|
| 1 | One store with a `project` column | §1.1: measured cross-project push contention (O(N)×8 s, untunable), one global migration ledger, no per-project remote, invariant-14 lineage lock-in, omittable predicate |
| 2 | One `--data-dir`, database per project or per zone | A2 measured the leak: `SELECT … FROM other.x` succeeds. A namespace, not a boundary |
| 3 | Shared `sql-server` for multi-tenancy or per-table walls | Daemon (SPEC §6 non-goal) + security theatre in a one-process fleet (ID5b) |
| 4 | `version` as a stored column on the artifact row | It is a count; storing it recreates the `total_bcs` / four-way-total class (invariant 17, design rule 1) |
| 5 | Version = Dolt commit ordinal | Breaks 1,612 measured plain-form cites and makes the never-existed-version check a graph walk |
| 6 | 103–119 typed tables generated from the registry | ~114 tables for 0–4 rows; 119 `ALTER TABLE`s per spine change × N independently staged project stores |
| 7 | Typed core + generic tail (the plain hybrid) | Two homes for one field; a type crossing the volume threshold needs a data migration. Refused on this project's own two-namespaces evidence |
| 8 | `body` columns on typed tables | It is what produced "3 of 34 tables carry a body / 69% renderable". One body table makes invariant 16 one gate |
| 9 | Section keyed by heading | 110 documents carry 1,968 duplicate `##`+ headings (D-A) |
| 10 | A separate write-ahead log alongside Dolt | The Dolt commit already is one; a second log is a second truth. WAL used only where atomicity is genuinely impossible (cross-store) |
| 11 | Two-commit / SHA-backfill sequencing for the txn marker | The retired TD-VSDD-053 pattern; `state-burst` refuses its reintroduction |
| 12 | A single global lease | Invariant 11 / I3: serializes the project and makes parallel instances pointless |
| 13 | Monotonic counter as the lease token | Invariant 1: `fence = fence + 1` failed 30/30 with all six writers winning |
| 14 | `--force` lease break (as F4 proposes) | Invariant 21. Replaced by TTL expiry + audited, human-authorized revocation that writes no artifact |
| 15 | Time-bound retention ("keep 90 days") | Deletes cited versions and manufactures findings against correct documents; retention must derive from the pin-policy graph |
| 16 | Aliasing all 181 non-canonical `document_type` values | "Aliasing 108 singletons would encode the drift permanently under the appearance of fixing it" |
| 17 | Dropping unknown-typed files at import | A parser that silently loses input is the single most repeated defect class here — eight instances |
| 18 | Collapsing `dangling` / `unresolvable` / `declared_gap` into one "broken ref" state | Measured: 50 of 53 of the dangling class were `declared_gap`, i.e. blaming documents for correctly documenting a gap |
| 19 | Storing a cite's verdict (as `version_cite.verdict` does today) | Derivable from `pin_policy` + history; the same syntax carries opposite verdicts |
| 20 | Recording the artifact key in a read-deny audit row | Turns the audit into a side channel; precedent set by the cross-zone validator's counts-and-ids-only rule |

---

# 6. How each choice is proven (acceptance gates)

Every gate is a query or an independent recomputation. Nothing here is discharged by review.

| Choice | Gate |
|---|---|
| L1-A | `datum doctor --all-projects`: every registered store's `datum.yaml` project == its `registry_state`; an import of project X's render into project Y's store is refused; cross-project fan-out returns per-project rows and refuses to collapse |
| L1-B | `version == COUNT(*)` in the ledger for every key; every `artifact_version.dolt_commit` resolves; `datum show --at v` for every version of a sampled 100 artifacts; every one of the 2,197 imported cites resolves through `version_alias` |
| L1-C | `concat(section ORDER BY ord) == body` byte-exact for **100%** of bodies (today: 0 mismatches over 6,537 files, so any regression is visible); per-shape exemption list asserted non-empty-by-declaration; `blob-with-path` rows have no body and a resolvable path |
| L1-D | planted crash at each of 6 points in the sequence → `datum recover` leaves the store at the last commit with a `txn_abandoned` row; replay of a committed `idem_key` writes nothing and returns the prior result; a cross-store intent with a missing leg is reported by `datum doctor` and repaired by `datum recover` |
| L1-E | N writers, one scope → exactly one holder (re-run the measured 3-clone shape); an expired token is refused at write; a write not covered by a held lease is refused and names the missing scope; **no code path calls a force primitive** (grep-gated in CI) |
| L1-F | per-txn parity `audit ops == version ledger ops`; a read-deny row contains no key (asserted by schema + test); every gate `pass` row has a resolvable `evidence_ref` (invariant 22) |
| L1-G | before gc, every `pinned`/`as_of` cite resolves; after gc, the same set still resolves; a pruned version reports `pruned`, never `never existed` |
| L2-A | `hash(catalog rows) == hash(embedded registry)` at every open; every one of the 119 types has ≥1 generated view; **generated view vs an independent Go/Python projection over the same corpus, row-for-row** (the 67/67 parity precedent) |
| L2-B | every stored `path == compute_path(type,key)`; every `key_json` re-parses to itself; `BC-2.02.013-host-run-subprocess` refused; minting under contention yields no duplicate and no reuse of a `reserved_key` |
| L2-C | zero `illegal` enum values in the store after migration; a `migratable` write refused; an undeclared `open_extension` name refused; zero `forbidden` fields present |
| L2-D | every ref's `target_type` ∈ the declared universe; symmetric reverse direction refuses writes; placeholder count per type ≤ budget and ratcheting down; the 214 dangling section refs re-classified with per-state counts |
| L2-E | a write to a derived type refused with the generator named; a derived type with an empty `scope_predicate` refuses to derive; **the 41 legacy stories stay out of STORY-INDEX** (exact set equality, 41 == 41) |
| L2-F | every `cat_verb` row names ≥1 scope axis; an aggregate with an empty axis set refuses; `cat_lifecycle_compat` reduces the 1,949 BC disagreements to one verdict |
| L2-G | every catalog name has a `field_claim` row covering the registered project set; a colliding claim is refused with the corpus, count and samples printed |
| L2-H | zero unmodeled `document_type` values; every one of the 3,085 files in exactly one bucket; per-form counts reported and nothing dropped silently |

---

# 7. What this design costs

Stated once, plainly, so it is not discovered later.

1. **Cross-project atomicity is gone.** No unit of work spans projects. Acceptable because nothing
   in the corpus needs it; a `--all-projects` read is a fan-out, not a transaction.
2. **Cross-zone atomicity is gone** (it already was, A6). Bought back by the intent record plus
   `datum validate --cross-zone`, which was already a required deliverable.
3. **A crashed lease holder blocks its scope until TTL.** Bounded by per-scope TTLs; revocation
   requires a human.
4. **EAV loses database-level type enforcement.** Bought back by the `kind` column + write-time
   validation + a kind-parity gate.
5. **Pivot performance is unmeasured.** The design ships with the measurement and a declared
   materialization fallback. This is the one place where a wrong guess costs a rework.
6. **History growth is unmeasured at field-per-row granularity.** More rows per commit than a wide
   table. ~6 KB/commit over 40 commits is all we know.
7. **`version_alias` is a permanent-feeling migration table.** It retires with its baseline, but
   history resolves through it forever — the same shape as `id_alias`, and for the same reason.
8. **119 generated views are 119 things to regenerate correctly.** Mitigated by generating them from
   the same catalog the validator reads, and by the row-for-row parity gate.

---

# 8. Where this contradicts or bends its inputs

Listed explicitly rather than absorbed.

| # | Input | This design | Resolution |
|---|---|---|---|
| 1 | **F4**: "`--force` breaks are audited inside the same transaction as the break" (VSDD-FACTORY-REVIEW.md:901) | **No force path** (invariant 21). Revocation writes no artifact and discards no version | Invariant 21 wins; F4's *audit* requirement is kept and its *force* affordance is not. §9 Q1 |
| 2 | **SCALE.md:196**: "a remote-ref lock … needs a TTL and a break-glass path" | Break-glass exists but cannot touch an artifact | Same as (1). The measured need was for *liveness*, which TTL + revocation provides |
| 3 | **Invariant 16**: "every artifact stores its verbatim body" | `blob-with-path` (4 types) stores no body; `append-only-event` (11 types) stores entries and derives the file after cutover | A per-shape reading, declared not omitted; invariant 16 binds at capture, invariant 15 at cutover. §9 Q2 |
| 4 | **Invariant 17**: "no stored value is derivable from another stored value" | `artifact.path`, the catalog mirror, and any materialized view are stored derivables | Read through `authority`, which invariant 17 itself names as the enforcement: a `derived` value is a cache with a generator and a recomputation gate. §9 Q3 |
| 5 | **SPEC §2 design rule 4**: "prose stays as files … relationalizing them buys nothing" | Ledgers and reviews become rows | Already overturned on evidence by PROBE-CYCLES (GAP-MATRIX.md:78–89) and by story 4's 2,211 finding rows. Recorded, not re-litigated |
| 6 | **Current schema**: `version` columns on `bc`/`vp`; `version_cite.verdict`; `finding.occurrences` | All three refused as stored derivables | schema v4 is the phase-1 shadow, explicitly not the v1 target. `finding.occurrences` needs a declared exception or rows. §9 Q6 |
| 7 | **SPEC §6 non-goal**: "multi-repo mode is not modelled" | Untouched. A project is one repo | Multi-repo remains out of scope; `projects.yaml` gives N *projects*, not N repos per project. §9 Q7 |

---

# 9. OPEN QUESTIONS — these need a human call

**Q1 — Ratify no-force, and the shape of lease revocation.** Invariant 21 forbids a force path; F4
and SCALE.md both call for a break-glass. This design says revocation is a human-authorized, audited
write to the `lease` table that touches no artifact and discards no version. *Is that the intended
reading of invariant 21, and is "human role token" the right authority — or should it be the
orchestrator, per D1's escalation rule?*

**Q2 — Ratify the per-shape reading of invariant 16.** 4 `blob-with-path` types store no body; 11
`append-only-event` types store entries and derive the file at cutover. *Accept the declared
exemptions, or require a captured body for all 119 types forever (which makes the ledger file a
second truth)?*

**Q3 — Ratify the invariant-17 reading.** "No **authored** value derivable from another stored value;
a **derived** value is a gated cache." Load-bearing for `artifact.path` (needed for UNIQUE), the
catalog mirror (needed for gates-as-queries), and materialized views (needed only if measured).
*Accept, or forbid stored derivables outright — which means no UNIQUE path constraint and no
row-level catalog?*

**Q4 — `status` vs `lifecycle_status`.** They disagree on **1,949 of 1,959** BCs and nothing reports
it. This is a D-D adjudication, not a mechanism choice. *Which field survives per type, and is
`cat_lifecycle_compat` the right instrument, or should one of the two be retired outright?*

**Q5 — Version numbering form.** The store assigns integers; the corpus writes `v1.25` (1,612 plain
cites). `version_alias` preserves resolution. *Confirm integers-with-an-alias-table, or should the
render keep emitting a dotted `v1.<n>` form to keep human cites stable?*

**Q6 — `finding.occurrences` (datum/schema.go:183).** A stored count. *Declare it a documented
exception like `corpus_assertion`, or make the occurrences rows?* The same question applies to
`security-review`'s per-severity counts, which the registry says become derived "once
adversarial-finding rows exist" — and those rows now exist (2,211 of them).

**Q7 — Store location and multi-repo.** `.factory-db/` inside each project repo (D-B: gitignored,
synced via `refs/dolt/data` on that repo's remote). *Confirm. And confirm multi-repo mode
(`.factory-project/`) stays out of v1* — if it does not, `projects.yaml` needs a repo dimension and
L1-A's "project = one lineage" argument needs re-derivation.

**Q8 — Retention window.** The predicate is designed; the window is a number nobody has measured.
*Authorize the growth measurement (per project, per month, at real write rates) before any default
is chosen* — naming a number now would be the "infer a consequence from a structural fact" error
this repo has recorded five times.

**Q9 — Pivot performance, and the materialization fallback.** The design's one genuinely unmeasured
risk. *Authorize a measurement pass: generated-view pivot vs materialized table over 2,362 BCs and
2,211 finding rows in embedded Dolt, including whether GMS supports the view definitions at all.*
The fallback is specified; the trigger is not.

**Q10 — Are `projects.yaml` and per-project write containment enough?** Multi-tenancy here is
single-user, so no cross-project *confidentiality* is designed. *Confirm that assumption* — if a
project ever needs to be invisible to another project's agents, the zone mechanism has to be lifted
to the project level too.

**Q11 — Scope-predicate authoring.** L2-E requires a `scope_predicate` per derived type before it may
derive at all. Today one exists, in Go (`shadowSpecs`), for three index types. *Who authors the other
20, and is a SQL-ish predicate string the right form* — or should it be a structured filter the
catalog can validate?

**Q12 — The three blocked items from the prior session still block L2.** The 2 namespace renames
(`story-spec`→`story`, `state`→`pipeline-state`), the ADR, and answering #671
(HANDOFF.md:117–122). L2-A generates the schema *from* the registry, so the registry's own exit
criterion ("zero types with `namespace_status: name_disagreement`") is now a **precondition of
schema generation**, not a tidiness item.
