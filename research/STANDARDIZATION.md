---
title: STANDARDIZATION — the standard already exists; this is an enforcement gap
date: 2026-07-31
purpose: the design position for the type registry, and the evidence behind it, so the next session builds rather than re-derives
inputs: CROSS-CORPUS.md · PROBE-CYCLES.md · BEADS-PROSE.md · SPEC.md · GAP-MATRIX.md · DECISIONS.md
status: position agreed in conversation, NOT yet built. This doc is the input to building it.
---

# Standardization

Written because the session's most decisive finding existed only in conversation, and
**anything not written down is lost.** Everything here is measured; sources are named so
nothing needs re-deriving.

---

## 0. What changed, and what it invalidates

The vision (user, 2026-07-31): **`fa` is the source of truth for everything that goes into
`factory-artifacts`** — *"all the prose and everything, from product brief, to the discrete
tasks inside story executions and everything in between."* Markdown becomes a render for
humans.

Then two requirements that shape the whole design:

1. *"we need to standardize though where it makes sense. We can migrate projects to the
   standard."*
2. *"we also need to account for how dynamic software development is and how it can
   require variation depending on the type of product you are making. For instance a local
   CLI based todo app is much different then building a SaaS based IDAM and remote access
   tool."*

**Invalidated by (0):** [SPEC](SPEC.md) §6 non-goal 1 ("prose artifacts stay files") and
[GAP-MATRIX](GAP-MATRIX.md) §2.7's 12 prose non-goals — the latter already carries a
correction banner from [PROBE-CYCLES](PROBE-CYCLES.md).

---

## 1. THE STANDARD ALREADY EXISTS

This is the finding that reframes the work from *design* to *enforcement + migration*.

**`~/Dev/vsdd-factory/plugins/vsdd-factory/templates/` declares 81 distinct
`document_type` values**, including `adversarial-review`, `holdout-scenario`,
`holdout-evaluation`, `burst-log`, `red-gate-log`, `security-review`, `lessons-learned`,
`tech-debt-register`, `ux-spec-flow` / `ux-spec-index` / `ux-spec-screen`, `prd`,
`product-brief`, `story`, `epic`, `wave-schedule`, `traceability-matrix`.

**Every drifted value measured in either corpus is ABSENT from that set.** vsdd's
`adversary-review`, `adversary-pass`, `local-adversary-review`,
`per-story-adversary-review`; prism's `adversarial-review-report`,
`adversarial-pass-report`, `adversary-pass-report` — none are declared anywhere.

And the plugin's own usage is overwhelmingly canonical:

| concept | canonical form | drifted form |
|---|---|---|
| holdout directory | `holdout-scenarios` — **48** plugin files | `holdout-evaluations` — **1** (and vsdd's own corpus dir, which is **empty**) |
| review document | `adversarial-review` — **64** plugin files | `adversary-review` — **1** |

**⇒ This is an ENFORCEMENT gap, not a design gap.** Nothing needs inventing. Migration
means making the corpora match what the plugin already says — **including vsdd-factory's
own corpus, which is the deviant one** (see CROSS-CORPUS §6: it is a 7.2×-BC outlier whose
`holdout-evaluations/` is uniquely named *and* empty while 7 corpora declare
`holdout-scenarios/`).

**It also collapses the product-variation worry.** rivetry's UI types (`ux`,
`ux-spec-*`) and prism's `security-review` are **already in the canonical 81**. Products
differ in **which subset they use**, not in vocabulary.

### Two defects in the standard itself, fix before closing the vocabulary

- **The template set has its own drift:** it declares both `traceability-matrix` **and**
  `traceability-matrices`. The 81 needs a dedup pass first.
- **The factory ships two conflicting `verdict` vocabularies**, which is the root cause of
  the zero-overlap between corpora — not agent whimsy:

| source | vocabulary | inherited by |
|---|---|---|
| `templates/state-manager-checklist-template.md` | `verdict: BLOCKED\|CLEAN` | prism |
| `workflows/phases/per-story-delivery.md`, `agents/code-reviewer.md` | `NITPICK_ONLY` (27 refs) · `CONVERGENCE_REACHED` (20) · `FINDINGS_REMAIN` (6) | vsdd-factory |

Each project inherited whichever surface it touched. **And the field is OVERLOADED** —
which is why vsdd's `verdict` mixes `HIGH` with `SUBSTANTIVE` with `CLOCK_RESET`, flagged
as a type violation in CROSS-CORPUS §5. Three axes are crammed into one field. **Fix =
split it:**

| field | closed vocabulary |
|---|---|
| `gate` | `BLOCKED` · `CLEAN` |
| `convergence` | `CONVERGENCE_REACHED` · `CLOCK_RESET` · `SUBSTANTIVE` · `NITPICK_ONLY` |
| `severity_max` | `CRITICAL` · `HIGH` · `MED` · `LOW` · `NIT` · `NONE` |

---

## 2. The classification: three ways, not two

An earlier position in this session — *"the profile must be vocabulary-neutral; core
reasons about categories, projects declare names"* — **was wrong as a standardization
answer**, and the user corrected it. Categories are a *tolerance* mechanism, and
tolerating accidental drift is not the same as accommodating genuine variation.
`adversarial-review` vs `adversary-review` is nobody's design decision.

| | rule | applies to |
|---|---|---|
| **1. Canonical** | one name, enforced, **projects migrate** | anything with a template-declared value; the `gate`/`convergence`/`severity_max` split; directory names (`holdout-scenarios`, `planning`, `demo-evidence`); the BC path form. **The large majority of everything measured.** |
| **2. Profile = PRESENCE, not naming** | a project declares *which* canonical types it uses; if it has the type, it uses the canonical name and shape | rivetry has `ux-spec-*`, prism doesn't. A CLI todo app declares ~12 types; a SaaS IDAM declares ~40. **This is where product variation lives.** |
| **3. New types enter by ADDING A TEMPLATE** | never by inventing a value inline | the growth path, and it is auditable |

**Aliases survive only as a migration + history device** — mapping the ~12 legacy
spellings to canonical so historical documents stay valid, with a retirement path.
Historical validity is required regardless: PROBE-CYCLES §5 found `BC-1.12.008` was
*legitimately renumbered* to `BC-3.05.004`, so a flat existence check against today's
corpus manufactures false findings against correct documents.

### Where `categories` DO still earn their place

Not as a licence to drift, but as the **migration mechanism** and for genuinely
project-local values. The pattern is verified in beads, whose core logic never enumerates
project vocabulary ([BEADS-PROSE](BEADS-PROSE.md) §6):

```sql
i.status = 'open' OR i.status IN (SELECT name FROM custom_statuses WHERE category='active')
```

So during migration, `BLOCKED` / `BLOCKED-hard` / `FINDINGS_REMAIN` all map to
`category: blocked` and nothing breaks while the rename lands. The **category set is
closed**; projects add names, never categories.

---

## 3. Three layers

| layer | lives in | contents | precedent |
|---|---|---|---|
| **Core** | `fa`, versioned with the binary | the VSDD spine + merge-safety semantics | CROSS-CORPUS §2/§8 derives it: `specs/{architecture, behavioral-contracts, verification-properties, domain-spec, prd-supplements}` · `cycles` · `stories` · `code-delivery` · `logs` · `planning`; ids `BC-S.SS.NNN` and `ADR-NNN` |
| **Project profile** | declared data in the corpus, validated by `fa` | per type: key · required fields · enums · link types · section schema · shape · authority · gate severity | `artifact-path-registry.yaml` (ADR-016) already does *paths* and stops one level short |
| **Escape hatch** | `metadata JSON` per record | project-, orchestrator- or integration-specific data | beads' rule verbatim: *"prefer the `metadata` field before proposing new first-class columns"* — and it still needed 62 migrations |

**Core membership test:** *does it have a merge-safety consequence?* "Append-only ledger
vs mutable record" is universal — PROBE-CYCLES §2 showed that getting it wrong is exactly
what makes `burst-log.md` collide. "Does this product need a threat model" is not.

**The risk of over-free profiles**, named so it is not forgotten: every project invents its
own dialect and cross-project agents stop working — the drift problem moved up a level.
Three guards: profiles **extend** a core they cannot override; the **category set is
closed**; and a profile is itself an artifact `fa` validates and gates.

---

## 4. The query surface: no new language, but a designed surface

Settled by measurement. SQL already does every hard part the spike tested — recursive CTEs
for cycle detection and transitive closure (26,130 paths), a whole-corpus 4-hop rollup in
3 ms, gates as queries — and **prose retrieval too**: Dolt supports `FULLTEXT` +
`MATCH … AGAINST` with relevance ranking, measured at **0.15 s over 1,959 bodies**
(PROBE-CYCLES §4; quirk: 24 rows for 22 distinct ids, callers need `DISTINCT`).

So the open question was never the language — it is **who queries, holding what**:

| consumer | interface | why |
|---|---|---|
| `fa` internals | SQL | already working |
| **agents** | **semantic verbs with stable JSON output** | an LLM composing joins across 25 tables returns plausible-but-wrong answers with no error — the exact failure class this project exists to eliminate. Verbs are testable contracts, gateable per zone, stable across schema change |
| humans, ad hoc | `fa sql --read-only` | exploration shouldn't need a feature request |

The work is therefore the **verb catalogue and its output schemas**, drafted in SPEC §5
(`trace`, `coverage`, `context <wave-N>`, `history`, `asof`, `diff`) plus `impact` from
[#671](https://github.com/drbothen/vsdd-factory/issues/671). GraphQL only if an external
consumer appears; #671 independently agreed *"No GraphQL server is required."*

**Accepted consequence:** every new question needs a new verb. That is a feature — it
forces each query to be named, tested and baselined — but the catalogue needs an explicit
"how to add a verb" path or people route around it via `fa sql`.

---

## 5. What "fa owns everything" costs, measured

Recorded because this gap analysis was delivered in conversation only.

**File coverage today:** `fa` ingests **2,191 of 3,145 files (~70%)** of vsdd-factory's
corpus and **0% of the other 954** — `cycles/` 621, `code-delivery/` 148, `logs/` 34
`.jsonl`, `specs/architecture/` 36 ADR documents (only headings are read), `semport/` 21,
`phase-0-ingestion/` 20, `legacy-design-docs/` 13, plus 9 loose root files (`STATE.md`,
`policies.yaml`, `tech-debt-register.md`, `sidecar-learning.md`, `regression-state.json`,
`reference-manifest.yaml`, `po-obligations.md`, `release-config.yaml`, `current-cycle`).

**Type coverage today:** of the **46 registry artifact types**, `fa` models **10** — and
for 6 of those 10 (`capability`, `domain_invariant`, `nfr`, `fr`, `adr`, `epic`) it stores
only the **id and name scraped from a heading**, not the document. Only `bc`, `vp`,
`story`, `subsystem` are real records with bodies.

**The authority inversion is the bulk of the work** (all absent from `fa` today, all
proven in the POC or designed):

| needed | status |
|---|---|
| write path `create`/`amend`/`retire`/`rm` with validation | POC W1–W9; absent from `fa` |
| `render` + `render --check` for the whole corpus | one generated file in the POC |
| conflict policy D1 — `conflict` table, 4 subcommands, `doctor` check | designed, unbuilt |
| `lease` (push-as-CAS); retire the `STATE.md` YAML lock + its CWE-367 | phase 2 |
| zone **enforcement** — `permissions.deny`, `PreToolUse` hooks, per-agent `allowed-tools`, no unrestricted `Bash` for a walled agent | directories exist; **no enforcement written** |
| instance/wave branches, graduate/abandon | phase 4 |
| `sync` + real `aggregate` plumbing + quarantine wiring | policy only (`fa/quarantine.go`) |
| migrating every writer: `state-manager`, `register-artifact`, `wave-handoff`, `state-burst`, the `create-*` skills, the 4 INDEX generators; retiring `verify-sha-currency.sh` and `validate-index-cite-refresh` | untouched |
| retiring the branch + the no-Dolt markdown fallback (L3) | untouched |

**Inherited hazards:**

- `BC-INDEX.md`'s `last_amended` is **tens of KB of nested prose inside YAML**. Either
  model it or preserve it byte-exact.
- **Growth is unmodelled** (~6 KB/commit over 40 commits, open gap 5). `cycles/` alone
  adds 15.8 MB, mean 26 KB/doc, largest 615 KB — and **beads' mitigation is unavailable to
  us**: it decays closed issues ~70% by summarisation and *discards the original*, which
  an authoritative spec corpus forbids.
- **Invariant 8 becomes absolute:** markdown written *only* by `fa render`, with
  `render --check` in CI, or there are two truths and strictly more drift than today.

**One correction to the pessimism:** *"`fa` as truth costs you diffs"* was too strong.
Dolt's diff is semantic and queryable — a one-word change at byte 1,280 of a 4.6 KB body
showed as **one modified row of 1,959**, `dolt_diff_bc` exposes `from_body`/`to_body`, and
`--diff-mode in-place` does **sub-cell** diffing. The real limit is narrower: that
presentation is **terminal-only** (redirected with `--color always` → **zero ESC bytes**,
leaving `theTHE` ambiguous), so it never reaches CI or a PR. But the **data is complete**,
so `fa diff` computing a unified diff from `from_body`/`to_body` is ~50 lines. **⇒ `render`
is not the sole critical path; `fa diff` + a PR surface is an equal route**, and it plays
to Dolt's strengths. beads chose neither and gave up reviewable content diffs; we don't
have to copy that.

---

## 6. Migration mechanics and cost

**Mechanism, all of it already built or already present:**

1. Declare the profile (canonical vocabulary + alias map).
2. `fa validate` reports deviations as findings.
3. `fa baseline write` dates and itemises them — the gate goes on **without blocking every
   PR on day one**, which is [DECISIONS](DECISIONS.md) D3's whole point.
4. Ratchet: new findings fail, fixed ones are reported for removal.
5. Graduate per type using the path registry's **existing** `enforcement_level:
   block | warn | advisory`. Land `advisory`, promote to `block` when that type's baseline
   hits zero.

**Cost, measured — do not re-derive:**

| coupling | files in `plugins/` |
|---|---|
| `document_type` as a **key** | 275 — but the key is stable; only VALUES change, a mechanical frontmatter rewrite with a reviewable diff |
| `cycles/` paths | **189** — the real coupling to watch, embedded in prompts |
| `holdout-scenarios` | 48 |
| `adversarial-review` | 64 |
| `verdict:` | 30 |
| `tech-debt-register` | 12 |

Directory renames are `git mv` plus a registry entry.

**Constraint:** this is a change to a **running factory across ~10 projects**. Per #671's
own warning about its later phases, it must flow through vsdd's change management — an ADR,
stories, a policy with `enforced_by` — not a unilateral rewrite.

---

## 7. Not decided — one-way doors, settle before building rows

- **Unit of change for prose.** One `body` cell, or typed sections? Cell-level merge
  reconciles different *fields*, never different *regions of one field*, so two agents
  editing different sections of one document collide where markdown would merge cleanly.
  beads chose four typed prose columns. Decide **before** prose moves in.
- **Committed or gitignored store.** beads gitignores the DB and pushes to a Dolt remote
  that may be `refs/dolt/data` **on the same git remote** — those are not in conflict, they
  are the same design. But it decides whether a reviewer holding only a git clone can see
  anything, which determines how much `render` must carry.
- **Composite key form** for documents: `(cycle, scope, kind, pass)` vs a content hash vs
  path. PROBE-CYCLES §3 proved filenames cannot key documents — 18 basenames collide and
  **all 18 hold different content**.

---

## 8. Disposition of issue #671 (`factory-graph`) — an ALTERNATIVE design exists

Recorded because it is an **open, unbuilt proposal by another author on the same repo**
that attacks the same problem, and a session that doesn't know it exists will duplicate or
contradict it.

**[#671](https://github.com/drbothen/vsdd-factory/issues/671)** — *"Proposal:
`factory-graph` — derived traceability graph rehydrated from `.factory/` markdown to
eliminate identifier cite drift"*. Open since 2026-07-16, author `Zious11`, **zero
comments, nothing built** (there is no `factory-graph` crate in `crates/`). It is the only
graph/traceability proposal in the tracker.

**What it proposes:** an in-tree **Rust crate** that rehydrates an in-memory `petgraph`
from `.factory/` on every invocation — frontmatter via Serde, **body prose via
`pulldown-cmark`** — with **no database at all**. Then a query CLI for agents, advisory →
blocking dispatcher hooks, and finally the four INDEX files become
`factory-graph generate-indexes` output. Sequencing principle: *observe → query → advise →
enforce → generate → retire.*

**It explicitly evaluated and REJECTED Dolt:** *"Git semantics but SQL, binary prolly-tree
storage (not git-diffable), no GraphQL."* Thesis: *"a standalone database dehydrated into
git would create a second replica of data that already lives in git — replicas needing
sync are precisely the current failure mode."*

| its claim | assessment |
|---|---|
| "not git-diffable" | **TRUE**, and the spike agrees — it is exactly why `fa render` and `fa diff` matter (§5) |
| "no GraphQL" | true and irrelevant; #671 itself says *"No GraphQL server is required"* |
| "a second replica needing sync" | **does not apply to phase 1 as built** — `fa`'s store is rebuilt from files per run and thrown away, the same lifecycle as its in-memory graph. The objection bites at the **authority inversion**, not here |

**A hard constraint decides more than the design debate does:** #671 wants an in-tree Rust
crate consumed by `factory-dispatcher` hooks. **Dolt has no C API and no Rust bindings**
([dolt#8953](https://github.com/dolthub/dolt/issues/8953) open); only DoltLite is
embeddable from Rust, and it is a different engine and on-disk format. So if the thing must
live in the Rust workspace inside dispatcher hooks, `fa`'s access path is **structurally
unavailable** to it.

**Scope it covers that `fa` does not** — and this is most of its value claim:
**body-prose references** (`ADR-NNN §Decision N`, `file.rs::test_fn`, BC version cells
copied into story tables), **composite sub-artifact IDs** (`AC-NNN`, `PC-N`, `EC-NNN` —
file-scoped, not globally unique), the **4-index version-cite ledger**, generated indexes,
`impact` and `waves`.

**Evidence it contributes, which independently corroborates this whole project's premise:**
E-19 reached **adversarial pass 29 with a 0/3 clean streak**, nearly all findings citation
misalignment rather than behaviour; **POLICY 5 has been extended six times**
(META-LEVEL 31→36) trying to fix cite drift with prose rules; and
`validate-index-cite-refresh` exists *solely* to police the 4-index version-cite ledger via
hand-rolled string scanning. Its conclusion — *"nothing actually parses the reference
graph"* — is the same one CROSS-CORPUS reaches from vocabulary drift.

**DISPOSITION under the new vision: they are a FORK IN THE ROAD, not complements.** #671 is
derived-data-only and keeps markdown authoritative **forever**; the vision has `fa` own the
artifacts. Both cannot be true. Before the vision changed they were arguably complementary
(#671 validates the present, `fa` remembers the past); now a choice is required, and the
choice has been made in `fa`'s favour — so #671 should be answered on the issue rather than
left open and silently contradicted.

**One thing from #671 still worth doing regardless, and NOT yet done:** its phase-1 exit
criterion is *"reproduces known F-* findings from recent adversarial passes without
hand-tuning."* `fa` reproduced the prototype's 82 findings rule-for-rule and found 71 more,
but **has never been checked against the F-* findings from those adversarial passes**. That
comparison is cheap and decides whether a frontmatter-only parser is sufficient or whether
the prose-reference extraction #671 insists on is where the real drift lives.

---

## 9. The next action

Build the type registry: seed from the 81 (**dedup first**), cross-check against **actual
usage in vsdd-factory AND prism AND rivetry** — never vsdd alone, it is the outlier — and
declare per type what the path registry does not: **key · required fields · enums · link
types · section schema · shape (record | document | append-only event | config |
blob-with-path) · authority · gate severity**, plus the three-way `verdict` split, the
alias map, composite keys, and per-type `enforcement_level`.
