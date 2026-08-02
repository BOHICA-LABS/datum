---
title: FA-V1-L3-L4 — the semantic operation API and the projection layer
date: 2026-08-02
purpose: specify L3 (the only write surface) and L4 (everything derived, incl. `fa render` and invariant 15) precisely enough to implement without re-deriving
status: DESIGN. Nothing implemented (design-only by direction). The 8 settled decisions and 23 invariants of FA-V1-DESIGN.md are treated as BINDING.
spine: research/FA-V1-DESIGN.md
corpus_pin: vsdd-factory .factory @ 0aaba144 · prism .factory (CONCURRENT session — re-measure before trusting any prism count) · rivetry .factory
measurements_reproduced_here: 6,537 md files · 5,405 with frontmatter · 1,189 distinct frontmatter key orders · 110 docs / 1,970 duplicate `##`+ headings · 4,861 authored / 54 derived / 73 ingested / 1,338 untyped · 21 of 103 types declare sections · 0 of 22 derived types do
reproduction: every number introduced here is emitted by probe P1–P4 in §25, and all four were RUN as written. Four draft numbers came from ad-hoc variants and were corrected to the probes' output; they are marked ⟲ below.
---

# `fa` v1 — L3 semantic operations and L4 projections

## 0. Scope, and what this document is allowed to change

L3 is the only write surface. L4 is everything derived. Both sit inside the spine's seven
layers (`FA-V1-DESIGN.md` §2) and may only call the layer below.

**Binding and not relitigated here:** V-A..V-F, D-A..D-D, invariants 1–23. Where this
document appears to conflict with one, that is a defect in this document and is called out
in §24 rather than resolved silently. Two places where the spine's own prose needs a
*correction of fact* rather than a change of decision are marked ⚠ **SPINE CORRECTION** and
are measured, not argued.

**One thing this document deliberately does NOT do:** it does not restate the type system.
The registry (`fa/registry/artifact-type-registry.yaml`, 2,713 lines) already declares 103
canonical types — 68 authored / 22 derived / 13 ingested — plus 16 `gap_types`, 4
`retired_types`, 23 `link_types`, 17 closed enums and 180 aliases. Everything below is
*generated from* or *validated against* that file. Re-deriving it would create the second
hand-maintained vocabulary this repo has now been bitten by five times (HANDOFF result 4).

### 0.1 ⚠ Two sibling designs landed while this was being drafted, and they change it

`FA-V1-L1-L2-STORAGE-SCHEMA.md` (commit `157917e`) and `FA-V1-L5-L6-POLICY-ENGINE.md`
(`bc4f6cd`) were written concurrently and **ratified decisions into the spine**. Both commits
also swept this file into themselves as collateral, so its history is not its own — recorded
because a reader tracing this document's provenance will otherwise find it under two unrelated
commit messages.

Six of their ratifications reach into L3–L4. Each is folded in at the named section rather than
appended, and each is marked ⚠ in place:

| ratified elsewhere | what it changes here |
|---|---|
| **One store per project, no `project` column** — the predicate is discharged by store *selection* | §3.4: `--project` is a **store selector**, not a field or a `WHERE` clause. **Resolves my Q11** — and it is the stronger answer, because invariant 19's real failure mode is an *omittable* predicate and a store handle cannot be omitted |
| **The registry GENERATES the schema** (one uniform `artifact`/`artifact_field`/`artifact_ref`/body model with per-type views) | Independent convergence with **L3-1** (§1.1): the op vocabulary is generated from the same registry that generates the schema, so ops and columns cannot drift apart. Two agents reached "generate it" from different directions |
| **Invariant 16 binds PER SHAPE** — 4 `blob-with-path` types store no body; **11 `append-only-event` types store entries and DERIVE the file**; a shape exemption must be *declared* | §11: **render is FOUR renderers, not three.** My authority-only split would have rendered `burst-log.md` as a verbatim authored body — precisely what the ledger shape exists to prevent. §15: the exemption must be declared. §24-Q14: §1.2's census is mis-keyed as a result |
| **Invariant 17 read through `authority`** — materialised views are legal as *declared* derived caches; three current columns (`bc/vp.version`, `version_cite.verdict`, `finding.occurrences`) are already violations | §12.1: those three are **excluded from the identity digest**. §21.1: the projection cache is legal *because declared* |
| **Evidence exists only if `fa` produced it**; `fa gate exec` is the sole writer of the evidence table; **`deferred` abolished** | §4.7: `gate record` → **`gate exec`**; `--evidence` survives only as a reference to a row `fa` wrote; `--defer` removed from `wave gate` |
| **Invariant 21 refined** — lease revocation is legal as TTL expiry or human-authorised revocation that **writes no artifact** | §4.7: `fa lease` gets a revocation path without a force path |

Two further corrections they forced on *my own* numbers, both recorded in place rather than
patched away:

- **"44 agent files, not 34."** Correct, and so is 35 roles — they measure different things.
  Reconciled in §8.2 with the command for each; my brief's 34 was wrong in both directions at once.
- **`status` vs `lifecycle_status` are NOT two fields for one concept.** My §16.3 example said they
  were. Measured, they are *authoring maturity* vs *lifecycle state*; what is true is that `status`
  has degenerated to a constant (1951 of 1959 `draft`). Corrected in §16.3 — and it is the same
  wrong-column error this session already made once, when a probe read `lifecycle_status` and
  reported BC `Status` agreement as 0.8% when it is 99.4%.

**One thing they independently confirm:** reviews still have no natural key, and the L5–L6 design
reports that *every convergence table FKs to it*. That raises my Q3 from "render is undefined for
390 documents" to a cutover blocker.

---

## 1. The two measured facts that shape everything below

### 1.1 The write surface has to be generated, because a hand-written one drifts

The spine's example ops — `fa bc set-postcondition`, `fa story add-ac`, `fa finding add`,
`fa gate record` — are a *vocabulary*. This repo's most reliable transferable result is that
**a hand-maintained vocabulary drifts from another hand-maintained vocabulary**, measured
three separate times in one session: story 4's hardcoded review-type list disagreed with the
Python extractor's on 8 spellings *in both directions*; the prose-ref probe's copy of the
patterns drifted from the registry's; and the registry's own patterns were unanchored
(`D-\d+` matching inside `TD-VSDD-069`, over-matching 9,755 candidates —
`artifact-type-registry.yaml:393-397`).

103 types × ~8 verbs is ~800 op names. Hand-writing them guarantees the fourth instance.

**Decision L3-1: the op vocabulary is DERIVED from the registry.** For each type, the op set
is a pure function of that type's `authority`, `shape`, `key`, `required+`, `optional+`,
`enums`, `links`, `sections` and `section_policy`. Adding a field to a type adds its op for
free; removing one removes the op. There is no file in which an op name is written twice.

The residue that cannot be generated — ops whose *meaning* is not a field write (`gate
record`, `lease acquire`, `wave merge`, `finding close`) — is small, enumerated in §4.7, and
each entry names the state machine it drives.

### 1.2 Mass and value point in opposite directions for `render`

Resolved per-file authority over all three corpora (6,537 markdown files):

| resolved authority | files | share |
|---|---|---|
| `authored` | **4,861** | 74.4% |
| **no frontmatter at all** | **1,132** | 17.3% |
| `retired` (211 of 211 are `delta-archive` — the type the registry already retires) | 211 | 3.2% |
| frontmatter but no `document_type` | 193 | 3.0% |
| `ingested` | 73 | 1.1% |
| **`derived`** | **54** | **0.8%** |
| genuinely unresolved `document_type` | **13** | 0.2% |

⟲ An earlier cut of this table reported 224 unresolved. Folding `retired_types` into the
authority map — which the registry declares and P4 confirms — resolves 211 of them as
`retired`, leaving **13**. Worth recording rather than silently improving: the registry already
knew the answer, and not reading it produced a 17× overstatement of the unresolved class. Same
shape as the five-times-measured lesson *read the vocabulary FROM the registry*.

Now the churn on the `factory-artifacts` branch (`git log --format= --name-only
factory-artifacts | sort | uniq -c | sort -rn`):

| path | commits | authority |
|---|---|---|
| `STATE.md` | 868 | authored (and is *three* artifacts in one file — registry:2080-2086) |
| `stories/STORY-INDEX.md` | 381 | derived |
| `specs/behavioral-contracts/BC-INDEX.md` | 218 | derived |
| `specs/architecture/ARCH-INDEX.md` | 151 | derived |
| `specs/verification-properties/VP-INDEX.md` | 140 | derived |
| `cycles/…pass-1/INDEX.md` | 98 | derived |
| `cycles/…backfill/INDEX.md` | 42 | derived |
| `specs/domain-spec/L2-INDEX.md` | 6 | derived |

**The seven hand-maintained index files carry 1,036 commits between them and are 7 of the
6,537 files (0.1%).** `render` is therefore prioritised by *churn and blast radius*, never by
file count — the direct application of HANDOFF result 3 (*mass ≠ value; I recommended the
wrong priority from a mass number*).

### 1.3 ⚠ The registry declares nothing about the shape of the documents `render` must generate

Measured over `types:` in the registry:

- All **22** derived types carry `section_policy: free`.
- **0 of 22** derived types declare a `sections:` list.
- ⟲ Only **21 of 103** types declare a non-empty `sections:` list at all; **70** are
  `section_policy: free`, 25 `expected`, 8 `required_unordered`. (An earlier cut said 31/75 —
  that grep counted `sections: []` as a declaration and swept in `gap_types`. The corrected
  figure makes the gap *larger*, not smaller.)
- **12 types carry `section_policy: expected` while declaring no sections at all** — a policy
  that warns on the absence of an empty list, i.e. a gate that cannot fire. Found by this
  measurement, not previously reported.
- **16 of 22** derived types have a template declaring them; the **6 that do not** are
  `behavioral-contract-index`, `verification-property-index`, `behavioral-contract-id-mapping`,
  `story-id-mapping`, `cycle-index`, `regression-state`.

So the three documents render most urgently needs to generate — **BC-INDEX (218 commits),
VP-INDEX (140), cycles/INDEX (140 across two files)** — have *neither* a declared section
schema *nor* a template. The registry already knows: they are its `template_missing`
namespace class (`artifact-type-registry.yaml:336-347`).

**This is the concrete content of the spine's "highest-priority missing piece".** `fa render`
is not blocked on a rendering engine. It is blocked on **22 missing render schemas**, of
which 6 have no prior art to lift at all. §17.2 specifies the schema; §24-Q1 records who
must author them.

---

# L3 — THE SEMANTIC OPERATION API

## 2. The one-sentence contract

> An op is a **typed, named, validated, attributable, idempotence-classified intent** to
> change a declared field, link, section or lifecycle state of one artifact identified by
> its **natural key**, executed inside exactly one transaction, permitted or refused by the
> caller's **role** and the type's **authority**, and recorded in the audit with its
> **writer class**.

Everything in §3–§10 is that sentence made mechanical.

## 3. Op naming grammar and argument shape

### 3.1 Grammar

```
fa <noun> <verb>[-<qualifier>] <key-component>... [--<field> <value>]... [--op-token <t>]
     |       |                    |                     |
     |       |                    |                     value flags: only DECLARED fields
     |       |                    positional: the type's `key:` components, IN DECLARED ORDER
     |       closed verb vocabulary (§3.3)
     noun = a canonical type name, or its family short-name where unambiguous
```

Three hard rules, each retiring a measured defect class:

1. **No op accepts a path.** There is no `--path`, no `--file`, no `--out`. `path` is
   `derived_never_authored` (`artifact-type-registry.yaml:149-156`) and D-C forbids it as
   identity. This is what makes the review's *~28 unregistered artifact homes · 225 unmatched
   files · `planning` vs `plans` · case drift* unrepresentable rather than detectable.
2. **No op accepts an id it mints.** Identity is store-assigned (invariant 23). `fa bc
   create` *returns* the `bc_id`; it does not take one, except under a migration op (§9.3)
   where the id is being *carried in* from the corpus.
3. **No op accepts a count.** Every count is a projection (§18). `epic.story_count` — a
   stored count of a derivable fact, flagged by the registry itself
   (`artifact-type-registry.yaml:1033-1036`) — has no setter and cannot get one, because the
   generator refuses to emit a setter for a field whose `authority` is derived (invariant 17).

### 3.2 Noun resolution

`fa bc …` and `fa behavioral-contract …` are the same op. The short-name table is generated
from the registry: a short name is legal iff it is unambiguous across all 103 canonical types
+ 16 gap types. **Aliases are NOT accepted as nouns.** `fa adversary-review add` fails with a
message naming the canonical type — because an alias is a *migration and history device, not
a permanent tolerance* (`aliases.yaml` header), and accepting 180 alias spellings on the
write surface is how V-C's "unrepresentable thereafter" quietly becomes "still representable".

### 3.3 The closed verb vocabulary

| verb | applies to | generated from | idempotence (§7) |
|---|---|---|---|
| `create` | every `authored` type | `key` + `required+` | **IDEMPOTENT-BY-KEY** |
| `set-<field>` | scalar fields in `required+`/`optional+` | field list minus `derived_never_authored` minus `forbidden` | IDEMPOTENT |
| `clear-<field>` | `optional+` scalars only | as above | IDEMPOTENT |
| `add-<link>` / `remove-<link>` | `links` with `cardinality: list` | `links` × `link_types` | IDEMPOTENT |
| `set-<link>` | `links` with `cardinality: scalar` | as above | IDEMPOTENT |
| `set-section <name>` | types with declared `sections` | `sections` | IDEMPOTENT |
| `set-body` | every `document`-shaped type | `shape` | IDEMPOTENT |
| `append` | `shape: append-only-event` | `shape` | **NON-IDEMPOTENT — token required** |
| `retire` / `deprecate` / `supersede` | types with `lifecycle_status` in `enums` | `enums.lifecycle_status` | IDEMPOTENT |
| `rm` | every `authored` type | — | IDEMPOTENT (refused while inbound refs exist, W9) |

`set-<field>` names are *derived*, so `fa bc set-postcondition` from the spine is really
`fa bc set-section Postconditions BC-1.05.036 --from-stdin` — because `Postconditions` is a
**section** of `behavioral-contract` (`artifact-type-registry.yaml:724`), not a field. That is
not pedantry: sections are the D-A partition of a verbatim body, and a `set-postcondition`
that pretended to be a field write would have to re-serialise the body, which is exactly the
lossy path invariant 16 exists to forbid.

`fa story add-ac` from the spine is real and is `fa ac create <story-key> --statement … [--traces
<bc-key> --clause "postcondition 3"]` — because story 12a already made AC/EC/PC/T-task **rows**
with a composite key `(owner_key, kind, sub_id)` and a typed `sub_artifact_ref`
(`fa/schema.go:233-263`). The op vocabulary follows the schema, not the sentence.

### 3.4 Value shape

- Every value is a **scalar string, a list of ids, or a body/section blob from stdin.**
- Lists take repeated flags (`--add-bc BC-1.01.001 --add-bc BC-1.02.003`), never a
  comma-joined string. Measured reason: the corpus writes both `[a, b]` (8,640 flow
  sequences) and block lists (12,860 items), and a single string arg would push the
  splitting decision to the shell, where quoting drifts per caller.
- **Blobs come from stdin, never from a path argument.** `--from-stdin` is the only body
  channel. A path argument would be a path in the write surface (rule 1) *and* would make the
  op non-reproducible from the audit.
- ⚠ **`--project` is a STORE SELECTOR, not a field.** The L1–L2 design was ratified into the
  spine after this section was drafted: **one store per project, and no `project` column** — the
  scope predicate is discharged by *store selection*, not by a `WHERE` clause, because push
  contention is per-branch and untunable (10 clones on one branch = 54 attempts *with disjoint
  rows*, vs 1 each on distinct refs, and backoff made it worse). That is a **stronger** form of
  what this section wanted: invariant 19's real failure mode is an *omittable* predicate, and a
  store handle cannot be omitted. There is still no default: `--project` (or `FA_PROJECT`)
  selects the store, and an unset one is `NO-PROJECT` (exit 2), never an implicit pick.

## 4. The op families

Generated per type; the tables below give the representative set per artifact **family** (the
registry's `family:` field), plus the hand-written semantic ops.

### 4.1 `family: spec` (behavioral-contract, verification-property, prd, domain-spec-section, …)

```
fa bc create        --project P --subsystem SS-05 --capability CAP-070 --origin greenfield \
                    --title "…" --introduced v1.3.0            -> returns BC-5.41.003
fa bc set-status            BC-5.41.003 --value ready
fa bc set-capability        BC-5.41.003 --value CAP-071
fa bc add-verified-by       BC-5.41.003 --value VP-088
fa bc set-section           BC-5.41.003 --name Postconditions --from-stdin
fa bc retire                BC-5.41.003 --replacement BC-5.42.001 --cycle v1.4.0
fa vp create        --project P --module … --proof-method kani --feasibility … --source-bc BC-…
fa vp add-behavioral-contract VP-088 --value BC-5.41.003
```

Note what is *absent* and why: there is no `fa bc set-bc-id` (invariant 23), no
`fa bc set-version` or `set-timestamp` or `set-input-hash` (`derived_never_authored`), no
`fa bc set-verdict` or `set-delta` or `set-changelog` (`defaults.forbidden`,
`artifact-type-registry.yaml:157-163`), and no `fa bc-index …` of any kind (authority:
derived — §4.6).

### 4.2 `family: delivery` (story, epic, pr-description, code-delivery-artifact)

```
fa story create     --project P --epic E-9 --points 5 --priority P1 --title "…" --target-module …
fa story add-depends-on   S-9.07 --value S-9.03      # `blocks` is DERIVED — see below
fa story set-wave         S-9.07 --value 16
fa story add-bc           S-9.07 --value BC-5.41.003
fa ac create              S-9.07 --statement "…" --traces BC-5.41.003 --clause "postcondition 3"
fa task done              S-9.07 --task T-4
fa epic set-status        E-9 --value complete
```

⚠ **`fa story add-blocks` DOES NOT EXIST.** `depends_on`/`blocks` are `symmetric_with`
(`artifact-type-registry.yaml:183-184`) and `link_rules` requires one direction stored and
the other derived (`:232-234`). One direction is arbitrary but must be *fixed*; `depends_on`
wins because it is the direction the wave scheduler consumes (`fa/graph_cmd.go:13-42`).
Consequence: all **58** `direction` findings in `fa`'s baseline become unrepresentable as a
class, not fixed as 58 entries — and `S-8.09`'s claim to block 19 stories that were never
written becomes a refused write, because `add-depends-on` on the *other* story would fail
V6 (§6).

### 4.3 `family: review` + findings

```
fa review open      --project P --cycle v1.4.0 --scope story --target S-9.07 --pass 3 \
                    --reviewer-role adversary --previous-review <key>
fa finding add      <review-key> --severity HIGH --category … --statement … --location … \
                    --owned true --op-token <t>
fa finding restate  <review-key> --of <origin-review-key>/<finding-id>
fa finding close    <review-key>/<finding-id> --by <fix-burst-key> --evidence <run-id>
fa review close     <review-key>              # gate_result / convergence / severity_max DERIVED
```

Three things this shape settles:

- **`finding_count`, `findings_total` and `severity_distribution` have no setters at all.**
  They are `COUNT(*)`/`GROUP BY` over `adversarial_finding` (`fa/schema.go:212-226`). Measured
  worth: **68 claims across 66 documents disagree with their own bodies** — roughly a third of
  reviews that state a count.
- **`restate` is a distinct op from `add`.** `owned` distinguishes a finding a pass
  *introduced* from one it re-states to audit a prior fix. Without it a derived count counts
  *mentions*: measured **412** mentioned-not-owned rows, which put `adv-s8.08-p2` at 21 against
  a claimed 9. This is the scope-predicate lesson arriving at the op layer — an op that
  conflated the two would make the count silently mean something else while agreeing.
- **`review close` takes no verdict.** `gate_result` / `convergence` / `severity_max` are
  computed from the finding rows (D-D, and invariant 22: *`pass` without evidence is
  rejected*). `fa gate record` (§4.7) is where a *gate* verdict enters, and it requires an
  `--evidence <run-id>` naming a machine-produced artifact row.

### 4.4 `family: ledger` (`shape: append-only-event` — burst-log, cycle-decision-log, lessons-learned, session-checkpoints, tech-debt-register, spec-open-questions)

```
fa burst append     --project P --cycle v1.4.0 --entry-date … --related-story S-9.07 \
                    --from-stdin --op-token <t>          -> returns D-525
fa decision append  --project P --cycle v1.4.0 --from-stdin --op-token <t>
fa lesson append    --project P --cycle v1.4.0 --from-stdin --op-token <t>
fa td append        --project P --severity HIGH --effort M --from-stdin --op-token <t>
fa td resolve       TD-VSDD-053 --by S-9.07 --resolved-date …
fa question append  --project P --from-stdin --op-token <t>
fa question resolve QQ-014 --by <adr-key>
```

`append` is the **only** non-idempotent verb, and it is the only verb that *requires*
`--op-token` (§7.3). It is also the whole point of the ledger shape: 301 commits across three
burst-log files, every one an append currently executed as a whole-document rewrite that can
conflict (`artifact-type-registry.yaml:1378-1381`). As rows they cannot conflict, and there is
nothing to rotate — which retires the 13 `*-archive` files and the rotation policies that
created them (`retired_types.rotation_archive_variants`).

### 4.5 `family: state` + config (pipeline-state, policies, wave-state, sprint-state)

```
fa state set-phase        --project P --value 3
fa state set-cycle        --project P --value v1.4.0
fa policy add             --project P --name … --enforced-by <hook|gate|op> --from-stdin
fa lease acquire|release  --scope wave-16|phase-3|cycle-v1.4.0
```

`fa state set-*` is a *record* op over three fields. The 868 commits on `STATE.md` are the
measured cost of that file also carrying a decisions ledger and a checkpoint ledger; under L3
those two become `fa decision append` and `fa checkpoint append` (§4.4) and the record has
three setters. **`fa policy add` requires `--enforced-by`** — a policy with no mechanical
enforcer is a comment, and POLICY 5 has been extended six times as META-LEVEL 31→36 trying to
fix cite drift with prose (`artifact-type-registry.yaml:2101-2104`).

### 4.6 `authority: derived` types have NO ops. That is the enforcement of invariant 17.

The generator emits **zero** write ops for the 22 derived types. `fa bc-index set-total-bcs`
does not exist and cannot be added without changing `authority:` in the registry, which is a
change-management event (`registry/CHANGE-MANAGEMENT.md`). Attempting a derived write returns
`DENIED-AUTHORITY` (§6, V2) naming the projection that owns the value.

Same for `ingested`: 13 types get `fa ingest <type> --from-stdin --tool … --run-id …` and
nothing else. An ingested artifact is the output of semgrep/cargo-audit/Kani, *not an authored
judgement* (`artifact-type-registry.yaml:1241`), so there is no field an agent may edit.

### 4.7 The hand-written semantic ops (the complete list — 14)

These are not field writes; each drives a state machine or a coordination primitive, and each
gets its own test, its own audit shape, and an entry here because it cannot be generated.

| op | drives | refuses when |
|---|---|---|
| `fa gate exec <gate>` | gate ledger + **the evidence table** | ⚠ renamed from my draft's `gate record` per the ratified L5–L6 decision: **evidence exists only if `fa` produced it**, `fa gate exec` is the *sole* writer of the evidence table, and **no flag accepts evidence bytes**. My draft's `--evidence <run-id>` survives only as a *reference* to a row `fa` itself wrote. Also ratified: **`deferred` is abolished** as a gate status, replaced by deferral rows with owner and expiry — so there is no `--defer` on this op |
| `fa gate present <gate>` | gate presentation protocol (spine §7 keep-list) | — |
| `fa lease acquire\|release\|status --scope S` | store-side leases | scope unset (invariant 11: never singular). ⚠ ratified refinement of invariant 21: revocation is legal as **TTL expiry or human-authorised revocation that WRITES NO ARTIFACT** — a lease is not artifact data, so this is not a force path |
| `fa wave register\|merge\|abandon <N>` | wave branches | dependency cycle unresolved |
| `fa wave gate <N> --pass\|--fail` | wave gate | `--pass` without evidence. ⚠ `--defer` removed: `deferred` is abolished (above); a deferral is a row with an owner and an expiry |
| `fa instance new\|graduate\|abandon` | factory instances | invariant 10 (one clone per instance) |
| `fa convergence advance <cycle>` | convergence clock | monotonicity violated |
| `fa derivation advance <type> --to proven\|retired` | `derivation_stage` ladder | shadow findings ≠ 0 for that type |
| `fa alias retire <alias>` | alias ledger | that type's baseline ≠ 0 |
| `fa idalias record <old> <new>` | `id_alias` (D-C) | either id unknown |
| `fa finding close` | finding lifecycle | no fix reference |
| `fa attest <artifact> --run <id>` | attestation | run not reproducible |
| `fa propose op\|field\|type` | escape hatch (§10) | never — it is the refusal path |
| `fa migrate apply <plan>` | bulk/migration writer class (§9.3) | plan lacks count assertions |

⚠ **Name check, because this repo has been caught twice claiming a field name without
measuring it.** `gate` is *already in live use in prism as an identifier* (`gate:
wave-3-integration-gate`, beside `gate_step` / `gate_step_name`, 40 files —
`artifact-type-registry.yaml:2427-2429`). That is why D-D named the *outcome field*
`gate_result`. Using `gate` as an **op noun** does not collide with a *field* name — the
namespaces are disjoint — but it is a near miss, and §24-Q9 records the check that must run
before the noun is fixed.

## 5. How ops compose into one transaction

### 5.1 `fa tx` — the only multi-op entry point

```sh
fa tx --project P --role implementer --actor-kind interactive <<'OPS'
{"op":"story.set-status","key":["S-9.07"],"fields":{"value":"in-progress"}}
{"op":"ac.create","key":["S-9.07"],"fields":{"statement":"…"},"refs":[{"link":"traces","target":"BC-5.41.003","clause":"postcondition 3"}]}
{"op":"finding.close","key":["adv-s9.07-p2","HIGH-P34-001"],"fields":{"by":"fb-14"}}
OPS
```

- **JSONL in, one op per line, executed as exactly one transaction.** Invariant 6: one
  transaction per unit of work. Measured, and the number is not marginal — a 1,959-BC import
  is 531 s per-statement/per-spawn, 15.7 s batched into one session, and **0.9 s** wrapped in
  one explicit transaction (SPEC invariant 6; a further 17×).
- **All-or-nothing.** A bad edge rolls back the story too (W4).
- **`lease → validate → transact → version → audit`, with no bypass path** (invariant 18).
  The lease is acquired for the *transaction*, not per op; validation runs over the *whole*
  op list before any write, because an op list that half-applies is the failure mode invariant
  18 exists to remove.
- **Ordering inside a transaction is the caller's, and is preserved in the audit.** Two ops
  touching the same field is not an error; last-write-wins *within* the transaction, and both
  are audited. Refusing it would make a generated op stream (§9.3) unusable.
- A single-op invocation (`fa bc set-status …`) is sugar for a one-line `fa tx`. There is one
  write path, not two — otherwise invariant 18's "no bypass" is a claim about half the code.

### 5.2 Conflict

`fa tx` **never merges and never forces** (invariant 21). On a push-race loss it returns
`CONFLICT` (exit 5) with the losing op stream echoed back verbatim on stdout, so the caller
re-applies *its intent as a validated operation* rather than re-resolving bytes. The echoed
stream is the retry payload, which is why idempotence classification (§7) is a per-op property
and not a per-command flag.

## 6. Validation: an ORDERED ladder, and the order is a correctness property

The single most expensive lesson in this spike's rule-writing is that **rule order is a
correctness property, not a performance choice.** Measured: in `fa/shadow.go:541-551`,
running the generic emptiness/placeholder rules *before* the count rules reported 18 rows as
"the index states a value the store does not hold" where the index stated zero and the store
held zero — *a finding that says the opposite of what is true*. The comment in that file ends
"The order of these two rules is the bug."

So the validation ladder is declared as an order, and the order is tested.

| # | check | refuses with | why it sits here |
|---|---|---|---|
| **V0** | **role permits this op** | `DENIED-ROLE` (exit 3) | first, so a forbidden op never learns *anything* about the artifact — including whether it exists. A refusal that leaks existence is an information-asymmetry leak (§8.3). |
| **V1** | noun resolves to a canonical type | `UNKNOWN-TYPE` (exit 2) | before authority: you cannot check the authority of a type you have not resolved. Aliases rejected here with the canonical name. |
| **V2** | **`authority` permits an author write** | `DENIED-AUTHORITY` (exit 3) | before required-field checks. Reversed, a derived write reports 15 missing fields on an op that was never permitted — noise that hides the real refusal. |
| **V3** | project scope declared and permitted | `DENIED-PROJECT` (exit 3) | before key resolution: a key is only unique *within* a project (V-F, invariant 19). |
| **V4** | **natural key well-formed and resolvable** | `BAD-KEY` / `NO-SUCH-ARTIFACT` (exit 1) | resolved through `id_alias` **as of the current version** (D-C), so a legitimately renumbered id (`BC-1.12.008` → `BC-3.05.004`) is not a false miss. |
| **V5** | field is declared for this type and not `forbidden` / `derived_never_authored` | `UNKNOWN-FIELD` (exit 1) | before enum: an undeclared field has no enum to check. |
| **V6** | **enum membership** (17 closed enums) | `BAD-ENUM` (exit 1) | before reference resolution: a value failing a closed enum is not an id, so resolving it as one names the wrong defect. `migrated_from` values are refused with the migration target, never silently accepted. |
| **V7** | **reference target exists AND its type is in `link_types.targets`** | `BAD-REF-TARGET` / `BAD-REF-TYPE` (exit 1) | the check that makes `capability: "E-12"` (an epic id in a capability field) unrepresentable. Cardinality checked here too (16 measured `VP.scope is multi-valued`). |
| **V8** | **required fields present and non-empty** | `MISSING-REQUIRED` (exit 1) | after refs, because a required *link* field must be a resolvable ref before its presence means anything. **A declared-empty value is a declaration of none and passes; an absent field fails.** Those are different states (§19). |
| **V9** | **placeholder / declared-gap discrimination** | `PLACEHOLDER` (exit 1) or accepted as `placeholder` state | ⚠ **must run AFTER V7/V8 and BEFORE V10.** Measured: treating a self-marking gap cell (`[process-gap]`, "v1.1 candidate", "uncontracted", "BC candidate", "proposed") as a trace produced **55** POLICY-8 findings and **50** dangling-trace findings — **50 of 53 of the entire dangling class** — *blaming the document for correctly documenting a gap* (`artifact-type-registry.yaml:503-512`). `placeholder` is **one declared state**, so the op accepts it explicitly and the projection can distinguish it. |
| **V10** | section policy (`required_ordered` / `required_unordered` / `expected` / `free`) | `SECTION-POLICY` (exit 1, or warn) | only meaningful once the body/section payload has passed the field checks. |
| **V11** | **invariant 16**: `concat(sections) == body`, byte-exact | `PARTITION-LOSSY` (exit 2) | a *tool* failure, not a gate failure: if the partition is lossy the store cannot render, so this is exit 2. Already implemented and checked rather than trusted (`fa/registry.go:344-350`, `fa/registry_gate.go:242-246`). |
| **V12** | **invariant 23**: no store-assigned identity appears in submitted content | `IDENTITY-IN-CONTENT` (exit 1) | last, because it scans the accepted payload. Retires the whole SHA-transcription class (TD-VSDD-053/044, `verify-sha-currency.sh`) in one rule. |
| **V13** | **invariant 17**: no submitted value is derivable from another stored value | `DERIVABLE-VALUE` (exit 1) | generated: any field the registry marks derived has no setter, so V13 only fires on *content* that restates a derived value (a body asserting `Total BCs: 1949`). §18.3. |

**Warn vs refuse** follows the registry's existing `gate_severity` × `enforcement_level`
ladder, unchanged: every type ships `advisory`, graduates to `warn` then `block` when its
finding baseline reaches zero (`artifact-type-registry.yaml:545-548`). A type at
`enforcement_level: block` **must** be enforced at `write` or `both` — the registry already
declares that constraint, and it is exactly the L3 statement of it: `block` enforced only in
CI is a contradiction, because the write already happened
(`artifact-type-registry.yaml:144-145`).

## 7. Idempotence and retry

Invariant 4 is the binding requirement: *a duplicate-key error on retry means already applied
and must fall through, not bail* — because on a shared clone a push publishes siblings'
commits too, so "my push failed" does not mean "my work was not published", and bailing
strands the earlier commit which the next reset discards.

### 7.1 Three classes, declared per op by the generator

| class | ops | retry semantics |
|---|---|---|
| **IDEMPOTENT** | `set-*`, `clear-*`, `add-<link>`, `remove-<link>`, `retire`, `rm` | re-execution is a no-op. Safe to retry unconditionally. `add-<link>` on an existing edge returns `OK (no change)`, never an error. |
| **IDEMPOTENT-BY-KEY** | `create` | a duplicate natural key returns `OK (already exists)` **iff every submitted field matches the stored row**; returns `CONFLICT-DIVERGENT` (exit 5) if any differs. Silently accepting a divergent create is how a retry becomes a lost update. |
| **NON-IDEMPOTENT** | `append` (all 11 `append-only-event` types), `finding add` | requires `--op-token`. |

### 7.2 `--op-token` is invariant 1, discharged

Invariant 1: *every guarded write carries a per-attempt UNIQUE value* — because Dolt merges
cell-by-cell and contenders writing **identical** values all get `affected_rows = 1` and all
"win" (`fence = fence + 1` failed 30/30 with all six writers winning). A `PRIMARY KEY` is not
a concurrency control (invariant 7): two concurrent writers inserting byte-identical rows
merge silently, and naive id allocation produced `[1,1,1,1,1,1]`.

So `--op-token` is a caller-supplied, per-attempt unique value, stored as part of the
append-only row's key. Effects:

- A retry with the **same** token is recognised as *already applied* and returns `OK
  (already applied)` — invariant 4, mechanically.
- A retry with a **new** token appends twice, correctly, because that is a second intent.
- Two agents appending concurrently cannot collide, because their tokens differ.

`fa tx` mints one token per *op* if the caller omits it and the op is non-idempotent — but
then the transaction is marked `retry_unsafe: true` in the audit, and a retry is refused with
`TOKEN-REQUIRED` (exit 1). Auto-minting a token and *pretending* it is retry-safe would be
the silent-double-append this whole invariant exists to prevent.

### 7.3 Sequence allocation

`create` on a type whose `key_format` carries a `{seq}` (BC, VP, ADR, story, epic, HS, FLOW,
SCR, TD, LESSON, …) allocates through **append-only allocator rows with per-attempt tokens**,
never a mutable counter cell (invariant 3). The allocated id is returned; it never appears in
the submitted content (invariant 23).

## 8. Least privilege: a role is a set of permitted OPERATIONS

### 8.1 Why op sets and not globs

Today's wall is path-based — deny a directory — and **rows in one database give path exclusion
nothing to bite on** (`research/ACCESS-CONTROL.md:26-30`). The measured ceiling is tier 1:
Claude Code runs *every agent inside one OS process at uid 501*, so there is no per-agent uid
(tier 2) and no per-agent process to inherit a credential fd (tier 3's only safe channel);
a credential in an env var leaks to a sibling via `ps eww` (ID3, ID5b end-to-end).

**Decision L3-2: a role is a set of op-name selectors plus a set of readable zones.** Both are
declared in `fa.yaml` beside the existing zone map, both are enumerable, and — the property
paths never had — **both are testable**: `fa role explain <role>` prints the permitted op set,
and a test can assert `role adversary` cannot execute `finding.restate` on a prior pass.

```yaml
roles:
  implementer:
    ops: ["story.set-status", "task.*", "ac.set-*", "finding.close", "tx"]
    deny_ops: ["*.create", "bc.*", "vp.*", "review.*", "derivation.*", "migrate.*"]
    read_zones: [open]
  adversary:
    ops: ["review.open", "review.close", "finding.add", "finding.restate"]
    read_zones: [open, walled]
    read_deny:                       # the information-asymmetry wall, as DATA
      - {type: adversarial-review, predicate: "cycle = $CURRENT and pass < $MY_PASS"}
      - {type: adversarial-finding, predicate: "review.pass < $MY_PASS"}
  holdout-evaluator:
    ops: ["evaluation.create", "evaluation.set-score"]
    read_zones: [walled]
    read_deny:
      - {type_family: spec}          # "CANNOT access .factory/specs/"
      - {type_family: review}
```

`deny_ops` beats `ops`, and both are evaluated **before** the op learns anything (V0).

### 8.2 The 35 role identities mapped onto op sets

⚠ **Three numbers are in circulation and all three are right, which is why the reconciliation
is written out rather than a number picked.** The L5–L6 design corrected my brief with "**44
agent files, not 34**". Measured:

| measurement | n | command |
|---|---|---|
| top-level `agents/*.md` | **34** | `ls plugins/vsdd-factory/agents/*.md \| wc -l` |
| all `agents/**/*.md` | **44** | `find plugins/vsdd-factory/agents -name '*.md' \| wc -l` |
| of the 10 under `orchestrator/`, declare "Not directly invokable" | **9** | `grep -l 'Not directly invokable' orchestrator/*.md` |
| **directly-invokable ROLE identities** | **35** | 34 + `orchestrator/orchestrator.md` |

So **44 files, 35 roles**: the 9 extra files are orchestrator *workflow references*, loaded by the
orchestrator agent and not invokable as agents. **The least-privilege unit is a role, so 35 is the
number that governs this section** — but 44 is the correct file count and my brief's 34 was wrong
in both directions at once (it undercounted files by 10 and roles by 1). The L5–L6 agent was right
to push, and the resolution is that the two numbers were never measuring the same thing.

The 35 roles collapse to **9 op-set classes**, which is the useful unit — a per-agent op list
would be a 35-row hand-maintained vocabulary, i.e. drift instance six.

| class | members | write ops | read | notes |
|---|---|---|---|---|
| **R-SPEC-AUTHOR** | product-owner, business-analyst, architect, story-writer, ux-designer, data-engineer | `bc.*`, `vp.*`, `prd.*`, `domain-spec*.*`, `adr.*`, `story.create`, `epic.*`, `ux-spec-*.*` | open | the only class that may `create` a spec artifact |
| **R-IMPL** | implementer, stub-architect, test-writer | `story.set-status`, `task.*`, `red-gate.append`, `ac.set-*` | open | **no `*.create` on specs** — a story's ACs are authored by R-SPEC-AUTHOR; the implementer marks, never mints |
| **R-REVIEW-OPEN** | code-reviewer, pr-reviewer, spec-reviewer, consistency-validator, security-reviewer, accessibility-auditor, visual-reviewer, performance-engineer | `review.*`, `finding.*` scoped to own `reviewer_role` | open | `reviewer_role` on the review row must equal the acting role — enforced at V0, not requested in a prompt |
| **R-REVIEW-WALLED** | adversary, holdout-evaluator | as above, plus walled | walled, **with `read_deny`** | §8.3 |
| **R-INGEST** | codebase-analyzer, research-agent, validate-extraction | `ingest.*`, `semport-artifact.*`, `research-note.*` | open | `authority: ingested` only |
| **R-VERIFY** | formal-verifier, dtu-validator, e2e-tester | `ingest.*` (fuzz/formal/perf reports), `attest` | open | verdicts arrive as ingested tool output, never as an authored claim |
| **R-OPS** | devops-engineer, github-ops, dx-engineer, demo-recorder | `merge-result.*` (derived-from-host), `demo-asset.*`, `runtime-log.*` | open | `merge-result` is `authority: derived` — merge facts come from the git host, *not from an agent's account of them* (`artifact-type-registry.yaml:2645`), so R-OPS ingests, it does not assert |
| **R-ORCH** | orchestrator, state-manager, pr-manager | `state.*`, `lease.*`, `wave.*`, `gate.*`, `convergence.advance`, `decision.append`, `checkpoint.append` | open + walled ids only | the only class holding `lease` and `gate`. **`derivation.advance` and `migrate.apply` are NOT here** — see R-ADMIN |
| **R-DOC** | technical-writer, session-reviewer, spec-steward | `lesson.append`, `session-review.*`, `question.*`, `idalias.record` | open | spec-steward gets `idalias.record` because renumbering is its job; it gets no field setters, matching "without modifying spec content" |
| *(not an agent)* **R-ADMIN** | human-authorised only | `derivation.advance`, `alias.retire`, `migrate.apply`, `registry.*` | all | §9.3, §10 |

⚠ **This mapping is derived from the agent names plus the three information-asymmetry walls
quoted verbatim in `ACCESS-CONTROL.md:20-27`.** The other 31 agent files declare tool profiles
and constraints that have **not** been read against this table. §24-Q8.

### 8.3 An information-asymmetry wall is a DENIED return code on a READ op

Today the wall is prose in a prompt plus a tool profile:

> **adversary:** "Cannot see prior review passes … Read-only access enforces both constraints
> structurally"
> **code-reviewer:** "You CANNOT see … enforced by Lobster context exclusion"

Under L3 it is a `read_deny` predicate, and the refusal is a structured code:

```
$ fa get adv-s9.07-p2 --role adversary
DENIED-ASYMMETRY (exit 3)
  'adv-s9.07-p2' is a prior pass of the review you are performing.
  role 'adversary' is denied reads matching fa.yaml roles.adversary.read_deny[0]
    (type=adversarial-review, predicate="cycle = $CURRENT and pass < $MY_PASS")
  This is an information-asymmetry wall, not an error. Do not retry; do not seek another route.
```

Four properties this buys that a prompt sentence does not:

1. **Enumerable.** `fa role explain adversary --walls` lists every wall. A wall that is a
   sentence in one of 35 prompt files is not inventoriable.
2. **Testable.** The wall becomes an assertion, not a hope. This is the same move
   `TestShadowWritesNothing` makes for "shadow never writes" — hash the corpus before and after
   rather than believing the comment.
3. **Non-leaking.** `DENIED-ASYMMETRY` is returned identically whether the artifact exists or
   not, and V0 runs before V4 for exactly this reason. A refusal that distinguishes
   "forbidden" from "absent" is an oracle: it tells the adversary how many prior passes there
   were.
4. **Self-limiting.** The message says *do not retry*, following the existing zone-refusal
   design (`ACCESS-CONTROL.md:66-73`) — so an agent does not "fix" the wall by trying another
   path.

**The hard requirement carried forward unchanged:** a walled role must not have unrestricted
`Bash`. Denying `Read` on a zone while leaving `Bash` open is not a wall — `cat` walks straight
through it. `fa`'s role check prevents accidents and produces actionable errors; the *boundary*
is the harness's `permissions.deny` + `PreToolUse` + per-agent `allowed-tools`, and the role
must be **injected by the hook, not passed as an argument the agent controls**
(`ACCESS-CONTROL.md:230-242`). `FA_ROLE` read from the environment is a hint; `fa` records
`role_source: env|hook` in every audit row so an unhooked deployment is *visible* rather than
silently advisory.

## 9. Writer classes: interactive vs bulk vs migration vs projection

### 9.1 Why they must be distinguishable in the audit

Two measured reasons, not one:

- The corpus carries **8 non-agent `producer:` identities** — the audit today cannot tell an
  agent's decision from a script's sweep.
- **1,852 BC renames with 0 deletes** (D-C). If a migration and an author share an audit
  shape, "nearly every BC has moved" and "an author moved this BC" are the same event, and the
  identity-change question cannot be asked.

### 9.2 Four classes, on every audit row

| `actor_kind` | who | volume | constraints |
|---|---|---|---|
| `interactive` | an agent role, one unit of work | 1–50 ops | full validation; leases; `retry_unsafe` tracked |
| `bulk` | an agent role, a declared batch | 50–10⁴ ops | requires `--batch-reason` and a **pre-declared expected count**; validation identical (never relaxed) |
| `migration` | R-ADMIN, one-time | 10⁴–10⁶ ops | requires a `migration_id`, an ADR reference, and **count assertions** (§9.3) |
| `projection` | `fa render` / projection refresh | any | may write **only** `authority: derived` rows; may write **no** authored field; cannot be invoked by an agent role |

Every audit row also carries `op_batch` (the transaction id), `role`, `role_source`,
`op_token`, `registry_digest` and `store_commit_before/after`. **`registry_digest` is not
optional:** an op validated against a different registry version is a different op, and the
baseline reconciliation in this repo already proved the point — the 18,418 → 18,804 shift on
*identical pinned input* was the registry's own tightening, **not corpus drift**, and it took a
per-version reconciliation to establish that.

### 9.3 Migration ops carry their own falsifiable prediction

```sh
fa migrate apply plans/M-004-delta-archive.yaml --dry-run
fa migrate apply plans/M-004-delta-archive.yaml --commit
```

A plan is refused unless it declares, per step, **the count it expects to change and the count
it expects to leave alone**. The measured case that forces this: `delta-archive` is **211
files** — rivetry's single largest `document_type`, larger than its behavioral-contract count
(151) — and *the archive is the only place some of those versions exist*, so it is a
data-bearing migration and "must be gated by a count assertion, not assumed"
(`artifact-type-registry.yaml:2670-2674`).

A migration whose actual delta ≠ its declared delta **aborts and rolls back**. This is the
two-phase validation arithmetic the spine's keep-list preserves — *any non-zero delta is an
error* — applied to the writer that can do the most damage.

## 10. The escape hatch: there is no write escape hatch

An agent needs something the vocabulary lacks. Four cases, four answers, and **none of them is
raw SQL**.

| case | answer | mechanism |
|---|---|---|
| **The content has no field** | Put it in **prose**. | D-A: the body is verbatim bytes and the section partition is derived. 26.3% of class C is unreachable by rows *anyway* (`PROSE-REFS-OR-FIELDS.md`), so prose is not a loophole — it is the honest home for judgement. `set-section` / `set-body` are always available on `document`-shaped types. |
| **The field exists in the corpus but not in the registry** | `fa propose field` | Returns exit 4 with a `field-extension-request` row. **Nothing is written to the artifact.** The registry already treats this as its primary evidence channel: *"Every alias with a non-empty `set:` clause is a field the canonical type is missing"* (spine §4.2), and `local-adversary-review` is called out as proof the canonical type is **UNDER-SPECIFIED, not deviant**. |
| **The op does not exist for a field that does** | Impossible by construction. | Ops are generated from the registry (L3-1). If the field is declared, the op exists. This is the whole return on generating rather than authoring the vocabulary. |
| **The question has no query verb** | `fa sql --read-only` | Already the declared answer: *"`fa sql --read-only` stays available for exploration precisely so nobody has to fake a verb"* (`artifact-type-registry.yaml:284-288`). **Read-only, and it is not a write hatch.** A verb enters properly via a registry entry + a declared JSON output schema + a test with a fixture corpus + a baseline entry. |

**Rejected: `fa tx --unsafe-freeform` / `fa sql --write` / an admin SQL console.** The reason
is measured, not stylistic: *an LLM composing joins across 25 tables returns
plausible-but-wrong answers with **NO error** — the exact failure class this project exists to
eliminate* (`artifact-type-registry.yaml:242-249`). A write hatch has the same property with
worse consequences, and it would make invariant 18's "no bypass path" false by construction.

**What happens on refusal, concretely.** Exit 4, plus a `proposal` row (a real canonical type,
`artifact-type-registry.yaml:2225-2248` — and the *one* path-registry entry that already does
schema), plus a message naming the change-management path. The agent's work is not lost: the
op stream is echoed to stdout so it can be re-submitted once the schema lands. That is the
same recovery shape as `CONFLICT` (§5.2), deliberately — an agent should learn one recovery
pattern, not five.

---

# L4 — PROJECTIONS

## 11. `fa render`: four renderers, chosen by `(authority, shape)`

**Decision L4-1: `render` is four functions, not one, and the selector is `(authority, shape)`
— shape first.** This is what reduces invariant 15 from "reproduce 6,537 arbitrary markdown
files" to a tractable, per-class contract.

⚠ **Corrected after drafting: it is FOUR renderers, and the fourth is forced by a ratified
invariant-16 refinement.** The L1–L2 design established that **invariant 16 binds PER SHAPE**: 4
`blob-with-path` types store no body at all, and **11 `append-only-event` types store entries and
DERIVE the file** — *"16 binds at capture, 15 at cutover"*, and a shape exemption must be
**declared**, silence is not an exemption. My draft's authority-only split would have rendered
`burst-log.md` as a verbatim authored body, which is exactly what the ledger shape exists to stop:
301 commits across three burst-logs, every one an append currently executed as a whole-document
rewrite. **Shape wins over authority for the 11 ledger types.**

| selector | types | files | renderer | round-trip guarantee |
|---|---|---|---|---|
| `shape: append-only-event` | **11** (`authority: authored`) | — | **generated from entry rows** — the file is a projection of the ledger, ordered by key | equality over **rows**; the file has no authored bytes |
| `authority: authored`, other shapes | 57 | 4,861 − ledger files | `"---\n" + canonicalFrontmatter(fields) + "---\n" + body` where **`body` is the stored verbatim bytes** | body byte-exact **by construction**. Only the frontmatter needs a normalisation contract (§13) |
| `authority: derived` | 22 | 54 | fully generated from a **render schema** + projection rows | equality over **rows**: `import(render(P)) == P` |
| `authority: ingested` + `shape: blob-with-path` | 13 + 4 | 73 | identity — bytes stored opaque, addressed by content hash. **No body**, so invariant 16 does not bind (declared exemption) | hash equality |

⚠ The ledger row count is **not** broken out in §1.2's authority census, because that census keyed
on `authority` alone. The three burst-logs, two decision-logs, lessons files, session-checkpoints,
tech-debt-register and sidecar-learning are inside the 4,861 `authored` figure. **Re-running the
census keyed on `(authority, shape)` is a prerequisite for sizing the render job**, and it was not
run — §24-Q14.

Everything else — 1,132 files with no frontmatter, 193 with frontmatter but no
`document_type`, 13 with a genuinely unresolved type — is **1,338 files (20.5%) that `render`
cannot own today** because they have no type. (The 211 `delta-archive` files are out of scope by
*declaration*, not by omission: the registry retires them and the store's own history replaces
them.) §12.4 makes that the honest denominator of invariant 15 rather than a rounding error.

### 11.0 The ledger renderer (`shape: append-only-event`, 11 types)

The file is a **projection of entry rows**, ordered by the type's key (`[cycle, entry_id]` for
burst-log, `[cycle, decision_id]`, `[cycle, lesson_id]`, `[td_id]`, …). There are no authored
bytes and invariant 16 does not bind. This is the renderer that pays for itself fastest: three
burst-logs carry **301 commits**, every one an append performed today as a whole-document rewrite
that can conflict — and *"as rows they cannot"* (`artifact-type-registry.yaml:1378-1381`). It also
retires the 13 `*-archive` rotation files and the rotation policies that created them, because a
row set has nothing to rotate.

It needs the same render schema machinery as §11.2 (a declared entry block, a declared order, a
declared heading form — the corpus already writes `D-524` / `LESSON-*` / `Session Resume
Checkpoint (<date>)` as H2s, so *"the row model is a transcription, not a redesign"*), and it has
the same blocker: no `sections:` declaration exists for any of the 11.

### 11.1 The authored renderer (other shapes, 57 types)

```
render_authored(artifact) =
    "---\n"
  + emit_frontmatter(artifact.fields, type.field_order, type.quoting, artifact.field_notes)
  + "---\n"
  + artifact.body                      # verbatim. NOT regenerated from sections.
```

**The body is never regenerated for an authored type.** Three measured reasons:

1. Bodies reach **1,568.8 KB** (`rivetry/.factory/cycles/v0.1.0-greenfield/burst-log.md`).
   ⚠ **SPINE CORRECTION:** the spine's round-trip hazard list says "prose bodies up to 211 KB";
   211 KB is the L8 *test* fixture. The measured maximum across the three corpora is **1.57
   MB**, with **8 files above 600 KB** and **17 above 300 KB**. Design against 1.57 MB, not
   211 KB — the difference is 7.4×, and it decides whether a whole-body diff is a viable
   diagnosis (it is not — §16).
2. Bodies contain **15,568 box-drawing characters** (`─`), 2,282 `│`, 1,416 `═` — hand-drawn
   ASCII diagrams. A regenerating renderer destroys them; a verbatim one cannot.
3. ⟲ Bodies contain **214,554 markdown table lines**, of which **31,400** are not canonically
   padded and **383** rows are missing their closing pipe. Reformatting them is a 31k-line diff
   that would bury every real change forever (§14).

The human-facing template shape (`behavioral-contract-template.md`, `story-template.md`) is
therefore reproduced **by the body being the body** — not by the renderer re-deriving `##
Description` / `## Preconditions` / `## Postconditions` / `## Invariants` / `## Edge Cases` /
`## Canonical Test Vectors` / `## Verification Properties` / `## Traceability`. The registry's
`sections:` list for `behavioral-contract` (`artifact-type-registry.yaml:724`) is what
`section_policy: required_unordered` *validates* against; it is not a print order.

Where the template shape *is* generated is at **instantiation**: `fa template instantiate
behavioral-contract` emits the declared sections as empty headings, which is what makes "the
template and the validator disagree" unrepresentable (spine §4.3). Instantiation and rendering
are different operations and must not share a code path — a renderer that could re-emit the
skeleton could also silently *replace* an authored body with it.

### 11.2 The derived renderer (22 types)

```
render_derived(type, scope) =
    "---\n" + emit_frontmatter(projected_fields)      + "---\n"
  + for each block in render_schema(type):
        emit_prose(block.preamble)                    # declared, not authored
      | emit_table(block.columns, projection_rows(block.query, block.scope, block.order))
      | emit_count(block.count_projection)
```

This is the piece that does not exist and has no prior art for 6 of the 22 types (§1.3). Its
schema is specified in §17.2.

### 11.3 The ingested / blob renderer (13 + 4 types)

Bytes in, bytes out, addressed by hash. **Open:** whether `render` writes them at all, or
whether the store holds only the hash and the file stays where the tool put it. The argument
for hash-only is `semport`: 9,274 of corverax's 9,291 files, *the scratch class that made
corverax look like the largest corpus* (`artifact-type-registry.yaml:2321-2326`). §24-Q7.

## 12. Invariant 15: exactly what "equal" means

> **15.** `import(render(store)) == store`, byte-exact.

Taken literally against today's corpus, invariant 15 is **false and unachievable**, for
reasons that are measured, not hypothetical: the corpus contains **1,189 distinct frontmatter
key orders** and **169 keys written both quoted and bare**, so no single canonical emitter can
reproduce every input file's bytes. Reading the invariant as "the current bytes round-trip"
would make the highest-priority gate in the design permanently red for reasons that have
nothing to do with data loss.

**Decision L4-2: invariant 15 is three gates, all three green, each with its own diagnosis.**

### 12.1 E1 — the invariant proper (STORE equality)

`import(render(store)) == store`, where equality is a **canonical row digest per (project,
type, key)** over:

- every declared field value, in registry-declared order, with a declared null encoding —
  ⚠ **excluding the three columns the L1–L2 design identified as existing invariant-17
  violations and therefore migration targets: `bc/vp.version`, `version_cite.verdict`,
  `finding.occurrences`.** Including a derivable column in the identity digest would make the
  digest disagree with itself the moment the column is retired;
- `body` **bytes** (SHA-256);
- the **section partition**: `(ord, depth, heading, len(body))` per section, plus the D-A
  identity `concat(sections) == body`;
- every outbound link row `(link_type, target_type, target_key, clause)`, sorted;
- every sub-artifact row `(kind, sub_id)` and its refs;
- `field_notes` (§13.3) and `frontmatter_comments` (§13.3).

**The comparison is per-artifact and per-field. There is no corpus-level digest.** A single
digest tells you "something moved" and nothing else; the spine's own requirement is that a
failure is "diagnosed to a specific artifact and field". A corpus digest cannot do that, and
would have hidden every one of the 658 cell-level disagreements `fa shadow` found — the
measured proof that *counts and id-sets cannot see cell content* (`fa/shadow.go:21-26`).

### 12.2 E0 — BYTE equality, on the normalised corpus

`render(import(bytes)) == bytes`, gated **only after a one-time normalising commit** (§13.4).
E0 is the gate that makes `render --check` meaningful in CI (invariant 8: *markdown is written
only by `fa render`, and `render --check` runs in CI*), and R1 already measured the
determinism side: 1,960 files, same digest across runs; R7: 9.2 MB in 0.4 s.

Before the normalising commit, E0 runs in **report mode** with a per-rule count, and that
report *is* the normalising commit's review surface.

### 12.3 E2 — hash equality for opaque bytes

`ingested` and `blob-with-path` types: content hash in, content hash out. Nothing is parsed,
so nothing can be lost.

### 12.4 Coverage: the honest denominator

The spine's bar is "invariant 15 and 16 green over **100% of the corpus**". Measured, the
denominator today is:

| | files | in E1's scope? |
|---|---|---|
| typed, resolved, authored/derived/ingested | **4,988** | yes |
| **no frontmatter** | **1,132** | **no — no type, no key, no render** |
| frontmatter, no `document_type` | 193 | no |
| genuinely unresolved type | 13 | no |
| `retired` (`delta-archive`) | 211 | out of scope **by declaration** |
| **coverage ceiling before typing work** | **76.3%** (4,988 / 6,537) | |

So **invariant 15 cannot reach 100% until 1,338 files acquire a type**, and reporting it as a
percentage without that denominator would be the "count that agrees while meaning something
else" failure invariant 19 exists to catch. `fa render --check` therefore reports
**four** numbers, never one: `equal`, `differs`, `unrenderable (no type)`, `out-of-scope
(ingested/retired)`.

## 13. Normalisation: what is legal, what is not, and the one-time commit

### 13.1 Legal normalisations (declared, counted, and never silent)

Each rule is declared in the registry, and every application is counted into a
`render_normalization` ledger row `(rule, artifact, count)`. **A normalisation with no count
is indistinguishable from data loss** — this repo has caught a parser silently losing input
**eight times**, and the migration is the worst possible place for a ninth (spine §6).

| # | rule | measured cost today |
|---|---|---|
| **N1** | frontmatter **key order** → the type's declared order | **1,189 distinct key orders** collapse to ≤103 declared orders. `document_type` is first in 5,085 of 5,405; the other 320 lead with `story_id` (137), `pass` (78), `review_id` (32), `story` (19), `pass_id` (16), `type` (7), `fix_burst` (6) |
| **N2** | scalar **quoting** → declared per field | **74,359 bare · 20,280 double · 9 single**; ⟲ **169 of 1,568 keys are written both ways**, including `status`, `version`, `producer`, `timestamp`, `level`, `phase`, `traces_to` |
| **N3** | strip trailing whitespace | **140 files, 901 lines** |
| **N4** | exactly one trailing newline | **19 files** end without one (vsdd 2 · prism 1 · rivetry 16) |
| **N5** | LF line endings | **0 CRLF files, 0 BOM.** Declared anyway: a Windows contributor is one commit away, and a rule that only exists after it is needed has already lost a round-trip. (P1's `Counter` omits zero-valued keys, so `crlf`/`bom`/`non_nfc` are *absent* from its output rather than printed as 0 — noted because an absent key and a zero are the same class of ambiguity this whole document is about) |
| **N6** | Unicode **NFC** | **0 non-NFC files.** Same reasoning as N5. 1 NBSP, 0 zero-width, 1,136 smart quotes present |
| **N7** | list style: flow vs block sequences → declared per field | **8,640 flow sequences · 12,860 block-sequence items** |
| **N8** | empty-value encoding (`[]` vs `null` vs bare) → one declared spelling per field type | **3,391 empty values** |
| **N9** | table cell padding — **ONLY in generated bodies** | ⟲ **214,554** table lines exist; **none of them are touched** for authored types |

### 13.2 ILLEGAL — must be modelled or refused, never normalised away

| # | shape | measured | disposition |
|---|---|---|---|
| **X1** | **duplicate YAML keys** | **12 files** | **REFUSE the import.** A YAML parser keeps the last silently; the earlier value is *gone* and cannot round-trip. Duplicate keys become unrepresentable, and the 12 files are a migration decision with a recorded reason. §24-Q5 |
| **X2** | **frontmatter comments** | ⟲ **406 files** carry them · **4,498 comment lines** · **71** inline (`key: value  # note`) | **MODEL** (§13.3). Some are load-bearing: `input-hash: "[md5]"  # advisory — used for drift detection, not gating` (`behavioral-contract-template.md:10`) and `origin: greenfield\|brownfield    # metadata-only — does not affect BC semantics` (`:12`) |
| **X3** | **nested frontmatter mappings** | **3,030 lines** | **FORBID by schema.** BC-INDEX's `last_amended` is *"tens of KB of nested prose inside YAML"* (`artifact-type-registry.yaml:762`) — and that type is `derived`, so it stops existing. Survivors migrate to body sections |
| **X4** | **block scalars** (`\|`, `>`) | **234** | Migrate to a body section, or model as a declared multi-line field with a declared re-emit style. Silently reflowing a block scalar changes bytes *and* meaning |
| **X5** | strikethrough as state (`~~BC-2.02.013~~`) | already measured by `fa shadow` | **MODEL as a lifecycle state.** *"strikethrough is not a representable state, so a derived index would silently lose the withdrawal"* (`fa/shadow.go:446-448`). Already on the HANDOFF next-list |

### 13.3 The two new stored shapes X2 forces

```sql
field_note          (project, type, key, field, note)            -- rendered as `field: v  # note`
frontmatter_comment (project, type, key, before_field, ord, text) -- rendered as standalone `# …` lines
```

The registry already invented the singular case: `producer_note`, added to *"absorb the
parenthetical prose measured in 48 prism `producer` values, keeping `producer` a clean enum"*
(`artifact-type-registry.yaml:123-124`). **Generalising it is the same move, and it is what
makes X2 legal to round-trip instead of legal to lose.**

Note the current parser cannot do this: `fa/frontmatter.go:73-74` skips comment lines and
`:99-101` strips trailing comments before storing. That is correct for *validation* and fatal
for *round-trip*, which is precisely why §16.2 requires a second, lossless reader.

### 13.4 The one-time normalising commit

```
fa normalize --project P --dry-run     # per-rule counts + full diff, writes nothing
fa normalize --project P --commit      # one reviewable commit, N1–N8 only
```

Properties, each answering a specific failure this repo has already had:

- **One commit, reviewable as a diff.** Not folded into a migration, not spread over types.
- **Per-rule counts asserted up front** and compared after. A rule that fires more than
  predicted aborts the whole commit — the `check-your-prediction` lesson (predicted ~160
  recoveries, got 46) turned into a gate.
- **Refuses to run while any X1–X5 shape survives**, so normalisation never runs *over* an
  unmodelled shape and thereby destroys it.
- **N9 never applies.** Authored table bytes are untouched, by construction.
- Reversible: the pre-normalisation tree is a commit.

## 14. The round-trip hazards, each with its design answer

| hazard | measured across 3 corpora | design answer |
|---|---|---|
| **heading duplication** | **110 docs / 1,970 duplicate `##`+ headings** (vsdd 38/579 · prism 61/848 · rivetry 11/543). ⚠ reproduced within 2 of the spine's 1,968 — methodology difference, direction identical | already solved: the partition is **ordinal-keyed**, heading is *data* (`fa/registry.go:288-325`). A resolver keyed on heading collides; a heading claimed by >1 section resolves to `ordAmbiguous = -2` and a reference to it is **`unresolvable`, never `dangling`** (`fa/proseref.go:113-114, 286-288`) |
| **YAML key order** | **1,189 distinct orders** | N1 + declared per-type order. **Not** "preserve the input order" — that would make the render a function of history, so two artifacts with identical data would render differently and `--check` could never distinguish drift from provenance |
| **YAML quoting** | 169 keys written both ways | N2, declared **per field** in the registry. A global rule cannot work: `version: "1.1"` must stay quoted (or YAML makes it a float) while `status: draft` must not |
| **trailing whitespace** | 140 files / 901 lines | N3 |
| **CRLF** | **0** | N5, declared before it is needed |
| **unicode** | 0 non-NFC; top: `—` 164,344 · `→` 92,003 · `§` **41,622** · `─` 15,568 | N6 + **verbatim bodies**. The `§` count matters twice: it is 41,622 live section markers, i.e. story 12b's whole subject. ⚠ these three counts drifted by 28 / 3 / 196 between two runs an hour apart — **prism is being edited by a concurrent session**, exactly as V-F warns. Any prism-inclusive number here is a snapshot, not a pin |
| **markdown table alignment** | ⟲ **214,554** table lines · 183,154 padded · **31,400** not · **383** missing closing pipe · 11 alignment-colon separators | **authored tables are never reformatted** (N9 excluded). Generated tables get one declared style. This is the single largest hazard *removed by a decision rather than solved by code* |
| **prose bodies to 1.57 MB** | **8 files > 600 KB · 17 > 300 KB** · max 1,568.8 KB | verbatim bytes; SHA-256 comparison; byte-diff reported as **offset + bounded window**, never as a whole-file diff |
| **no final newline** | 19 files | N4 — and note `splitKeepNL` (`fa/registry.go:329-342`) already exists *because* "splitting on `\n` and rejoining loses a missing final newline" |
| **line-number provenance** | **208 of 214** reported lines pointed at the wrong place; `actual == reported + frontmatter_lines` held **210/210** | every reported location carries **both** `file_line` and `body_line`, named. Still open in `fa refs` today (`PROSE-REFS-OR-FIELDS.md` follow-up) and a **prerequisite**, not a detail: a reference that cannot be opened cannot be adjudicated |

## 15. Invariant 16: `concat(sections) == body`

Already implemented, already measured at **0 mismatches over 6,537 files**, already checked at
runtime rather than trusted (`SectionsLossless`, `fa/registry.go:344-350`; gated at
`fa/registry_gate.go:242-246` with the message *"the derived partition is not byte-exact, so
render cannot be trusted"*).

⚠ **It binds PER SHAPE, ratified.** 4 `blob-with-path` types store no body and 11
`append-only-event` types derive the file from entries, so invariant 16 is vacuous for 15 of 103
types — **and the exemption must be DECLARED in the registry, because silence is not an
exemption.** An undeclared exemption is indistinguishable from a partition check that never ran,
which is the same class as `fa shadow`'s `table-absent` outcome: *a spec that matched no table
would contribute zero findings and read as agreement* (`fa/shadow.go:407-411`).

Three things L4 adds:

1. **It is a V11 write-time check** (§6), not only an import-time one. A `set-body` that
   produced a lossy partition is refused at exit **2** — a tool failure, not a gate failure,
   because a store that cannot partition cannot render.
2. **Section bodies include their own heading line** (`fa/registry.go:314-319`). That is what
   makes concat byte-exact, and it means `set-section` replaces *heading + content*, so an op
   cannot orphan a heading from its body.
3. **Fence awareness is part of the invariant.** A `## ` line inside a code block is not a
   heading (`fenceRe`, `fa/registry.go:278`). Every section-aware projection inherits this;
   one that re-implemented the scan would be vocabulary instance six.

## 16. Diagnosing a round-trip failure

### 16.1 Outcome vocabulary — reused, not reinvented

`fa render --check` adjudicates cell by cell and field by field using **the vocabulary
`fa/shadow.go:520-621` already earned**: `agree` / `agree-casefold` / `agree-set` /
`disagree` / `title-abbreviates` / `title-elaborates` / `index-placeholder` / `store-empty` /
`prose-in-set` / `row-truncated` / `row-duplicated` / `row-struck-through` /
`column-underivable`. That vocabulary is not a style choice: getting to it cost **~2,768
self-inflicted findings, 4× the 658 real ones**, and two named sub-classes (a rule aimed at
the wrong column manufactures what it was added to prevent — 292 self-inflicted; and rule
order is a correctness property — 18 rows asserted the opposite of the truth).

Render adds six outcomes:

`frontmatter-key-order` · `frontmatter-quoting` · `unmodelled-comment` · `unmodelled-nesting`
· `body-byte-diff@<offset>` · `section-partition-shape`

### 16.2 Two readers, and the difference between them is the diagnosis

- **The validating reader** is today's `ParseFrontmatter` (`fa/frontmatter.go`): deliberately
  not a real YAML parser, because *"a full parser would accept shapes the corpus treats as
  violations"* — and every branch in it exists because the Python prototype got it wrong and
  **the bug faked a clean result**.
- **The round-trip reader** is new and must be **lossless**: key order, quoting style, comment
  positions, block-scalar style, duplicate-key detection, byte offsets.

Neither replaces the other. Where they disagree is exactly the diagnosis: a shape the
validating reader accepts but the round-trip reader cannot reproduce is an **unmodelled shape**
(X1–X5), not drift. Collapsing the two readers into one is how a lossless renderer starts
accepting shapes the gates reject.

### 16.3 The report

```
fa render --check --project vsdd-factory
  authored  4861: equal 4820 · differs 41
  derived     54: equal  0 · differs 54   (22 types lack a render schema — 6 lack any prior art)
  ingested    73: hash-equal 73
  unrenderable 1325  (no frontmatter 1132 · no document_type 193)  <- NOT counted as equal
  out of scope  211  (delta-archive → retired_type)

  DIFFERS  behavioral-contract / BC-5.20.001
    field capability            frontmatter-quoting  store="CAP-070"  file=CAP-070
    field lifecycle_status      disagree             store=active     file=draft
      note: ⚠ MY DRAFT CALLED THIS "two fields for one concept" AND THAT IS WRONG.
            The L1-L2 design measured it: status = draft 1951 / active 6 / ready 2 /
            withdrawn 1; lifecycle_status = active 1945 / retired 5 / deprecated 4 /
            fulfilled 1 / draft 3 / withdrawn 1; dominant pair ('draft','active') on 1937.
            They are NOT two copies of one fact — AUTHORING MATURITY vs LIFECYCLE STATE.
            What is true is that `status` has degenerated to a CONSTANT (1951 of 1959) and
            therefore carries no information. Ratified recommendation: retire `status`,
            keep `lifecycle_status`, and point the index projection at the LIVE field.
            The 1,949-of-1,959 "disagreement" I cited is an artefact of comparing two
            different questions — the exact error the BC-Status probe already made once
            this session (0.8% agreement, actually 99.4%, because the probe read the
            wrong column).
    body                        equal (sha256 3f9c…, 12,844 bytes)
    section partition           equal (8 sections)
```

Per-artifact, per-field, with the class named. Never a single number.

## 17. Index projections: the 7 hand-maintained files, and the scope predicate

### 17.1 Scope predicate is FIRST-CLASS, and it must not be a path predicate

The measured result: **41 of 148 stories live in `stories/v1.0-legacy/` and STORY-INDEX
deliberately does not enumerate them.** Verified as *exact set equality* — the set "absent
from the index" is **exactly** the set of files in that directory, 41 == 41. Generating from
every record would have **resurrected 41 retired stories while every count still agreed**
(`fa/shadow.go:98-113`). Story 4 hit the identical class independently: `findings_total`
counts only the findings a pass **owns**, not the 412 it re-states.

**Decision L4-3: `scope` is a required field of every projection, it must be written
explicitly (there is no default, and `scope: all` is an affirmative declaration), and it is a
PREDICATE OVER FIELDS — never a path prefix.**

⚠ The second half of that decision is a **correction to the existing implementation**, and it
matters because the HANDOFF's next-priority item is "move the scope predicate into the
registry". Today the scope is `ExcludeSrcPrefix: ["stories/v1.0-legacy/"]`
(`fa/shadow.go:161-164`) — **a path predicate.** Moving it into the registry unchanged would
promote path-as-identity into the standard, which D-C forbids on measured grounds (1,852 BC
renames, 0 deletes: *nearly every BC has moved*). A path predicate breaks the moment a legacy
story is relocated, and it breaks **silently, by re-including the record**.

So the migration is two steps, not one:

1. **Materialise the generation as a field** on the story rows — `generation: v1.0-legacy`, or
   `lifecycle_status: superseded` (`lifecycle_status` is already a closed enum). This is a
   `migration` writer-class op with a count assertion: exactly 41 rows change.
2. **Then** the predicate is `lifecycle_status != 'superseded'`, and it survives relocation.

⚠ **Blocked, and this is the load-bearing blocker for the whole derived ladder:** the 41
legacy stories **have no frontmatter at all** and state `**Blocks:** S-2.8` in prose
(`artifact-type-registry.yaml:981-983`). There is no field to read, so step 1 cannot be
derived from the files — someone must *assign* it. §24-Q2.

**Every projection additionally declares its scope's expected cardinality as an assertion.**
`excluded == 41` is checked on every run, and the check is reported even when it passes —
because *"a scope rule that silently removed records would be indistinguishable from a
generator that never saw them"* (`fa/shadow.go:370-372`).

### 17.2 The projection schema

One projection may own **many table layouts**. Measured, this is not optional:

| index | KB (bytes) | tables | **distinct header signatures** | data rows | commits |
|---|---|---|---|---|---|
| `prism/STORY-INDEX.md` | **1,229.6** | 18 | **11** | 1,357 | — |
| `vsdd/STORY-INDEX.md` | 227.4 | 19 | 6 | 152 | 381 |
| `vsdd/BC-INDEX.md` | 378.1 | 11 | 2 | 1,970 | 218 |
| `vsdd/ARCH-INDEX.md` | 77.7 | 7 | **7** (every table different) | 73 | 151 |
| `vsdd/VP-INDEX.md` | 73.3 | 6 | 6 | 132 | 140 |
| `vsdd/L2-INDEX.md` | 5.3 | 6 | 6 | 35 | 6 |
| `cycles/*/INDEX.md` ×2 | — | — | — | — | 98 + 42 |

*"What varies between tables in one document is not only WHICH columns exist but what a given
column MEANS"* (`fa/shadow.go:64-69`) — the measured case is STORY-INDEX's `BCs` column, which
is a **count** (`26`) in the E-1 tables and a **list** (`[BC-1.11.002, …]`) in the E-10 tables.
Declaring it a count produced 62 findings saying "states no number" about cells that stated
membership *explicitly* — a **stricter** claim, not a missing one.

```yaml
projections:
  story-index:
    type: story-index                 # must have authority: derived
    derivation_stage: shadow          # the existing ladder; never flipped (fa/shadow.go:337-355)
    scope:                            # REQUIRED. No default.
      predicate: "lifecycle_status != 'superseded'"
      expect_excluded: 41
      why: >
        stories/v1.0-legacy/ is a superseded story generation that STORY-INDEX deliberately
        does not enumerate; deriving without this scope would resurrect all 41.
    frontmatter:
      version: {from: count_projection, name: story_index_version}
      total_stories: {from: count_projection, name: story_total_in_scope}
    blocks:
      - kind: heading            level: 1  text: "Story Index"
      - kind: count              name: story_total_in_scope  prose: "**Total stories:** {n}"
      - kind: table              key: story_id
        group_by: epic_id        order_by: [epic_id, story_id]
        scope: "inherit"                        # or a narrowing predicate; never a widening one
        columns:
          - {name: "Story ID",  kind: ColID,          field: story_id}
          - {name: "Title",     kind: ColTitle,       field: title}
          - {name: "Status",    kind: ColEnum,        field: status,   enum: status}
          - {name: "Epic",      kind: ColID,          field: epic_id}
          - {name: "Points",    kind: ColEnum,        field: points}
          - {name: "Priority",  kind: ColEnum,        field: priority, enum: priority}
          - {name: "BCs",       kind: ColCountOrSet,  field: bcs}
          - {name: "Wave",      kind: ColUnderivable, why: "story.wave is authored; …"}
```

Five properties, each from a measured failure:

- **`ColKind` per column, declared not sniffed** — *"sniffing is how `TBD` ends up meaning
  three things"* (`fa/shadow.go:41-43`).
- **`ColUnderivable` is a first-class kind**, reported as a **coverage gap** and never
  compared. *"A shadow that silently skipped such a column would overstate what it proves"*
  (`fa/shadow.go:70-73`). The live case is `VP-INDEX.Status`: the `vp` table has no status
  column, agreement against the *files* is 100%, and leaving it silently uncompared would
  misrepresent coverage (`fa/shadow.go:144-148`).
- **A sub-block's `scope` may narrow, never widen.** A widening block would let a table
  contain rows the document's own scope excludes — the resurrection bug at table granularity.
- **`order_by` is total.** A projection with a partial order is non-deterministic (§21).
- **Header signature is a declared property, not a discovered one.** Discovery (a subset test
  over `RequireHeader`, `fa/shadow.go:89-95`) is right for the *shadow* stage, which reads
  authored documents it did not write. It is wrong for `render`, which writes them.

### 17.3 The retirement ladder is unchanged and is not skipped

`shadow → proven → retired`. `fa derivation advance` refuses while that type's shadow findings
are non-zero, and `fa shadow` **writes nothing** — hash-verified by `TestShadowWritesNothing`.
The discipline, quoted because it is the reason `render` cannot simply be switched on:

> *if the generator is subtly wrong then hand-maintained drift is replaced by GENERATED drift
> and the evidence that would have caught it is gone.* — `fa/shadow.go:9-12`

Current evidence, per index: BC-INDEX **93.1%** cell agreement (7,294/7,836), VP-INDEX
**97.0%** (388/400), STORY-INDEX **89.8%** (555/618). **658 findings total** — 573 real drift,
44 editorial, 41 facts about derivation itself. **No index may advance past `shadow` today.**
And the single largest block is one drift event: 330 BC-5.\* files carry `capability: CAP-001`
while BC-INDEX distributes them across 11 capabilities (`CAP-070`…`080`) — half of `fa
shadow`'s total, and a **PO adjudication**, not a tool call.

## 18. Count projections: every stated total, owned

### 18.1 The shape

```yaml
count_projections:
  bc_total:      {expr: "COUNT(*) FROM bc", scope: {predicate: "lifecycle_status != 'removed'", why: …}}
  bc_by_subsystem: {expr: "COUNT(*) FROM bc GROUP BY ss_id", scope: {inherit: bc_total}}
  vp_coverage:   {expr: "…", scope: {predicate: "…", why: "measured 90.2% of BCs have no verifying VP"}}
```

Every count carries a scope predicate (invariant 19). A count without one is refused **at
registry load**, not at run — because the resurrection failure is one config omission away and
a load-time refusal cannot be forgotten under time pressure.

### 18.2 No copy exists to drift

The measured target: **six BC totals**. `ARCH-INDEX` 1949 / body `Total` 1949 / frontmatter
`total_bcs` 1955 / disk 1959, plus per-subsystem drifts SS-03 (53 vs 56), SS-05 (656 vs 655),
SS-08 (214 vs 218). Also `epic.story_count` — *"a STORED COUNT of a derivable fact, the same
defect class as the four BC totals"* (`artifact-type-registry.yaml:1033-1036`) — and 5 of 10
subsystem counts and 5 of 17 epic rollups from the review.

Under L4:

- **No count has a setter** (§3.1 rule 3, §4.6).
- **A count in a rendered body comes from a named count projection slot**, never from a
  literal. `emit_count` substitutes; the number is not authorable.
- **A count in an authored body is a V13 finding** (§6). It cannot be *refused* — prose may
  legitimately discuss numbers — but it is reported with the projection it contradicts.
- `corpus_assertion` (`fa/schema.go:156-163`) — the one table that deliberately stores a wrong
  number so a gate can compare it — **survives only for `ingested` and not-yet-migrated
  types.** Once a type renders, its assertions are the projection and there is nothing to
  compare.

### 18.3 Percentages are integers plus a declared rounding rule

`93.1%` in a rendered document must be emitted from `(7294, 7836)` with a declared rule, not
from a float. Otherwise the projection is not byte-reproducible across architectures, and §21's
determinism claim is false in a way nobody will notice for a year.

## 19. Traceability projections: five states, not two

### 19.1 The chain, as bidirectional edges

`L1 brief → L2 capability/domain-invariant → L3 BC → L4 VP → story → AC → test → PR → demo`,
projected as one edge relation:

```
trace_edge(project, from_type, from_key, to_type, to_key, link_type, pin_policy, provenance, direction)
```

- **`provenance` ∈ {frontmatter, sub_artifact_ref, prose_ref, projection}.** Story 12a's
  `sub_artifact_ref` is what turns *"5 stories have AC traces to BCs not in `bcs:`
  frontmatter"* — an actual class-C finding — from a prose diff into a **JOIN**.
- **Both directions are queryable; only one is stored.** `symmetric_with` pairs are stored once
  and reversed by derivation (`link_rules`, `artifact-type-registry.yaml:232-234`), retiring
  all 58 `direction` findings as a class.
- **`impact` is the reverse closure** and is one recursive CTE over the edge table. It is *the
  verb the adversary actually needs*: a VP count widened in one place and not its three
  siblings; `module-criticality` updated without `verification-coverage-matrix`; *"F-P27-005
  closure incomplete — VP-INDEX harmonized, source VP files NOT updated"*. Every one of those
  is a missing reverse-closure query (`artifact-type-registry.yaml:268-281`).

### 19.2 The five completeness states — the most important thing in this section

A completeness query that answers yes/no is wrong, and it is wrong in a way that manufactures
findings against correct documents. Measured on **both** sides:

| state | meaning | measured evidence |
|---|---|---|
| **SATISFIED** | declared, resolves | — |
| **DECLARED-EMPTY** | `verification_properties: []` — an affirmative claim of *none* | **3,391 empty values** in the corpus. The registry gate already treats this as its own class: *"a declaration of none, weaker than absence"* (`fa/registry_gate.go:191-194`) |
| **UNDECLARED** | the field is absent | distinct from empty. Collapsing them makes "we decided there are none" and "nobody looked" the same fact |
| **DECLARED-GAP** | the cell **marks itself** as a gap | markers measured in the corpus: `[process-gap]`, "v1.1 candidate", "uncontracted", "BC candidate", "proposed". Treating these as traces produced **55 POLICY-8 + 50 dangling findings — 50 of 53 of the whole dangling class** — *blaming the document for correctly documenting a gap* |
| **DANGLING** | declared, owner known, target absent | 39 frontmatter danglers today; **27 of them are `story.blocks` → a story never written** (`S-8.09` alone declares it blocks 19) |
| **UNRESOLVABLE** | the owner is unstated, so the reference cannot be adjudicated | 1,550 section refs. *"Collapsing the two is how a prose extractor produces a large, confident, wrong finding set"* — and the mirror error is worse: **an AMBIGUOUS name reported as DANGLING** asserts absence where `#### FR-043` is a heading **four times** (73 references) |

(Six rows for five states — SATISFIED plus the five failure modes. The point is that the
denominator has six cells and every projection must report all six.)

**Precision discipline carried forward:** section-ref dangling is reported **in AGGREGATE
only**. All 30 survivors were hand-adjudicated: **11 real, 19 the checker's — 37% precision**,
which *does not earn per-reference reporting* even though the set shrank 86% (214 → 30). A
traceability projection must inherit that rule: **a per-item finding requires a measured
majority-real sample, not a small count.**

### 19.3 Coverage numbers need their scope stated

*90.2% of BCs have no verifying VP* is the headline. Over which BCs? Active only, or including
`retired`/`deprecated`/`removed`? The number changes and so does its meaning. Every coverage
projection therefore prints its predicate beside its percentage — invariant 19 at the
presentation layer, which is where a correct number acquires a wrong meaning.

## 20. Graph projections: reuse the CSR, and `--scope` is mandatory

### 20.1 Reuse, do not rebuild

CSR is the default engine, measured against the gonum projection: **articulation points 5.36
ms → 51 µs (104×)** at 2.4k nodes, **980 ms → 8.1 ms (121×)** at 240k, waves 710 ms → 121 ms,
SCC 4.6 ms at 240k, and **96× less memory**. gonum stays for what CSR does not do (Louvain,
PageRank) and for nothing else. The projection contract is already right and is not
renegotiated: rebuilt from a store query on every use, never persisted, no setters, every
output `authority: derived` and subject to `shadow → proven → retired`
(`fa/graph.go:1-20`). Break rule 1 and it is the second replica.

`multi.DirectedGraph`, not `simple` — the graph genuinely has parallel edges (a story points
at a BC via `behavioral_contracts` **and** via `traces_to`, with different pin policies), and
`simple` would silently collapse them and understate coupling (`fa/graph.go:52-57`).

### 20.2 What `--scope` must be mandatory FOR

| case | why | measured |
|---|---|---|
| **`--betweenness`** | the sole superlinear algorithm | 236 ms at 2.4k · **52.2 s** at 24k · extrapolates to **~1.5 h** at 240k. Already refuses above 5,000 nodes. ⚠ **Two of three performance claims in this area were WRONG** ("single-digit milliseconds" → 236 ms), which is why the refusal is a hard limit and not a warning |
| **every multi-project query** | V-F + invariant 19 | 3 corpora = 6,537 files; today's single-project projection is 2,421 nodes, i.e. one project already sits at half the betweenness refusal threshold |
| **any aggregate** (centrality, community, coverage rollup) | invariant 19 verbatim: *unscoped aggregates are refused* | the 41-legacy result is a graph-scope failure as much as an index one — a legacy story is a **node** |
| **`graph diff`** | a diff between two store versions must fix the node set | otherwise a node added by an unrelated project reads as churn |
| **prospective: story 6** | ledgers → rows adds **26,632** references (`decision` 20,788 + `lesson` 5,844) | ~11× today's edge count, pushing every unscoped default past the betweenness refusal |

**One predicate language for all three projection kinds.** The `scope:` grammar of §17.2 is the
same grammar `count_projections` use (§18.1) and the same one `--scope` accepts. Three
predicate languages would be three vocabularies to drift.

### 20.3 What graph projections must refuse rather than approximate

`fa waves` already models this: a schedule over a cyclic dependency graph **does not exist**,
so it prints the cycles and exits 1 — *"emitting a plausible one would be worse than failing"*
(`fa/graph_cmd.go:26-35`). Every graph projection inherits the rule: no partial result is
emitted as if it were total.

## 21. Determinism, caching, staleness

### 21.1 The cache key is the reproducibility contract

```
projection_output_id = H(projection_id ‖ projection_version ‖ store_commit
                          ‖ scope_digest ‖ registry_digest ‖ fa_version)
```

- **Byte-identical output for an identical key.** R1 measured the property on the render side:
  1,960 files, same digest across runs.
- **Staleness is computable without running the projection** — recompute the key and compare.
  This is what retires `input-hash`: a hand-maintained content hash on **3,890 files** whose
  own archive text admits it reports *"spurious DRIFT"* under cascading recomputes, and which
  ships a `PENDING-RECOMPUTE` sentinel meaning *the field is routinely knowingly wrong*
  (`artifact-type-registry.yaml:2681-2694`). A derived hash cannot be stale and cannot cascade.
- **`registry_digest` is part of the key.** Already proven necessary: 18,418 → 18,804 findings
  on *identical pinned input* was the registry's own tightening, not corpus drift.
- The cache is **content-addressed and discardable**. A projection that cannot be recomputed
  from its key is a second truth.
- ⚠ **Ratified, and it legalises this section:** invariant 17 read through `authority` permits
  `path`, the catalog mirror and **materialised views as DECLARED derived caches**; what is
  forbidden is an *authored* field duplicating a derivable one. So a projection cache is not an
  invariant-17 violation *provided it is declared* — and an undeclared cache is.

### 21.2 The five non-determinism sources, each already bitten or nearly

| source | rule | evidence |
|---|---|---|
| **map iteration order** | every projection sorts explicitly | Go randomises map ranges. `fa/shadow.go:509-515` sorts findings; `attachSet` sorts set members *because* "an index listing the same members in another order is not drift" (`:268-270`) |
| **the clock** | no projection reads it | `import_run` deliberately holds **no timestamp and no path**, so a re-import leaves the working set byte-identical (`fa/schema.go:310-313`, W5) |
| **absolute paths** | never in output | `baseline write` records the corpus **basename** + git ref, not the machine's path — *"an absolute home path in a committed file is noise that differs on every machine and in CI"* (`fa/main.go:398-406`) |
| **collation** | byte-order sort, declared | locale-sensitive sort makes output host-dependent |
| **floating point** | integers + declared rounding | §18.3 |

### 21.3 Cost budget

Render is on the commit path, so it has a budget: **9.2 MB in 0.4 s** measured (R7); one field
change touches 2 files / 4 lines (R5). The 54 derived files are the expensive ones (1.2 MB
STORY-INDEX, 1,357 rows) and they are also the ones whose projections must be incremental —
re-rendering 1.2 MB on every story status change is 381 commits' worth of full-file churn,
which is the problem being solved, not the solution.

---

## 22. What each choice enforces

| invariant | enforced by |
|---|---|
| 15 `import(render(store)) == store` | §12 three gates · §13 declared normalisation with per-rule counts · §16 two readers |
| 16 `concat(sections) == body` | §15 · V11 · existing `SectionsLossless` — **binds PER SHAPE**, with 15 of 103 types (4 `blob-with-path` + 11 `append-only-event`) carrying a **declared** exemption |
| 17 nothing derivable is stored | §4.6 (derived types get no ops) · V13 · §18 (no count has a setter) |
| 18 `lease → validate → transact → version → audit`, no bypass | §5.1 (one write path; single-op is sugar) · §9.2 (audit shape) |
| 19 every aggregate declares a scope predicate | §17.1 (required, load-time refusal) · §18.1 · §20.2 |
| 20 enum/ref/key validated at **write** time | §6 V4/V6/V7 · registry constraint that `block` implies `write`/`both` |
| 21 no force path, no auto-merge | §5.2 (`CONFLICT` echoes the op stream; caller re-applies intent) |
| 22 every gate verdict cites machine evidence | §4.7 `gate record --evidence` · §4.3 (`review close` takes no verdict) |
| 23 identity assigned by the store, never in content | §3.1 rule 2 · §7.3 allocators · V12 |
| 1 per-attempt unique value | §7.2 `--op-token` |
| 3 append-only allocators | §7.3 |
| 4 idempotent retries | §7.1 three classes |
| 6 one transaction per unit of work | §5.1 (`fa tx`; 531 s → 15.7 s → 0.9 s) |
| 7 a PK is not concurrency control | §7.2 |
| 8 markdown written only by `fa render`; `--check` in CI | §12.2 E0 |
| 11 leases per-scope | §4.7 |
| 17-as-defect-elimination (the review's ~40) | §3.1 (no paths, no ids, no counts) + §4.6 + §6 |

## 23. Rejected alternatives

| # | alternative | rejected because |
|---|---|---|
| **R1** | **Raw SQL as the write surface** | *An LLM composing joins across 25 tables returns plausible-but-wrong answers with **no error*** — the exact failure class this project exists to eliminate (`artifact-type-registry.yaml:242-249`). Makes invariant 18's "no bypass" false by construction. `--read-only` SQL stays for exploration. |
| **R2** | **Hand-written op vocabulary** (~800 names) | A hand-maintained vocabulary drifts from another hand-maintained vocabulary — measured **three times in one session** (HANDOFF result 4). Generation makes the drift unrepresentable. |
| **R3** | **Path-glob least privilege** | Rows give path exclusion nothing to bite on (`ACCESS-CONTROL.md:26-30`). A role must be a set of *operations*. |
| **R4** | **Per-table DB `GRANT`s for asymmetry walls** | Sound at the database (ID5/ID6/A5, all denials real) and **defeated locally**: the credential leaks via `ps eww` (ID3) or a `0600` file (ID4), and ID5b is the attack end-to-end. Claude Code runs every agent in **one process at uid 501**, so there is no sibling boundary at all. Would be *security theatre*. |
| **R5** | **Asymmetry walls as prompt sentences** (status quo) | Not enumerable, not testable, and leaks by inconsistency. §8.3 makes each wall a `read_deny` predicate + `DENIED-ASYMMETRY`. |
| **R6** | **Render regenerating authored bodies from sections** | D-A: prose is verbatim bytes. Bodies reach **1.57 MB**, carry **15,568** box-drawing characters and **214,554** table lines of which **31,400** are non-canonically padded. Regeneration is a 31k-line diff that hides every real change. |
| **R7** | **Reformatting authored markdown tables to one style** | Same measurement. This is the largest hazard *removed by a decision* rather than solved by code. |
| **R8** | **Preserving input frontmatter key order** | Would make render a function of history: two artifacts with identical data would render differently, and `--check` could never separate drift from provenance. N1 imposes a declared order instead. |
| **R9** | **A comment-preserving YAML round-tripper as the whole answer** | Preserves what should be *modelled* (406 files / 4,498 comment lines → `field_note`, generalising the registry's own `producer_note`), and still cannot represent the **12 duplicate-key files**, where the earlier value is already gone. |
| **R10** | **A single corpus digest for invariant 15** | Cannot diagnose to artifact and field, which is the stated requirement. Would have hidden all 658 cell-level disagreements `fa shadow` found. |
| **R11** | **Path-prefix scope predicates** (today's `ExcludeSrcPrefix`) | Promotes path-as-identity into the standard against D-C (1,852 renames, 0 deletes) and breaks **silently by re-inclusion** when a legacy file moves. §17.1 requires a field predicate. |
| **R12** | **One projection per document** | `prism/STORY-INDEX.md` has 18 tables and **11 distinct header signatures**; `ARCH-INDEX` has 7 tables and 7 signatures. A projection owns *many* declared table layouts. |
| **R13** | **Discovering table layouts by header subset at render time** | Right for `shadow` (reading documents it did not write, `fa/shadow.go:89-95`); wrong for `render`, which writes them. Discovery on the write side means the output shape depends on the previous output. |
| **R14** | **Flipping derived types straight to derived** | *If the generator is subtly wrong, hand-maintained drift is replaced by GENERATED drift and the evidence that would have caught it is gone* (`fa/shadow.go:9-12`). Current agreement is 89.8–97.0% with 658 findings — nothing may advance. |
| **R15** | **Per-reference dangling reporting now** | 37% precision (11 real / 19 checker's of 30 hand-read). A confident wrong finding set is worse than a count. Earned by a majority-real sample, not by a small count. |
| **R16** | **Relaxing validation for `bulk`** | The volume is exactly when validation matters. `bulk` differs from `interactive` in *audit shape and required declarations*, never in checks. |
| **R17** | **Auto-minting `--op-token` and treating it as retry-safe** | Silent double-append: the failure invariant 1 exists to prevent. `fa tx` marks the transaction `retry_unsafe` and refuses the retry instead. |
| **R18** | **Reporting invariant-15 coverage as one percentage** | 1,338 files (20.5%) are unrenderable for lack of a type. A single percentage is the *count that agrees while meaning something else*. Four numbers, always. |

## 24. OPEN QUESTIONS

**Q1 — Who authors the 22 render schemas, and where do the 6 with no prior art come from?**
All 22 derived types carry `section_policy: free` and none declares `sections:`. 16 have a
template to lift; **`behavioral-contract-index` (218 commits), `verification-property-index`
(140), `cycle-index` (140 across 2 files), `behavioral-contract-id-mapping`,
`story-id-mapping`, `regression-state` have none.** The only surviving description of BC-INDEX's
shape is BC-INDEX itself — so the render schema must be *reverse-engineered from the artifact it
replaces*, which is the one input guaranteed to contain the drift. Proposal: derive a candidate
schema from the live document, then gate it by requiring `fa shadow` cell agreement to *rise*
under it. Not designed here.

**Q2 — Who assigns `generation`/`lifecycle_status` to the 41 legacy stories?** The scope
predicate cannot be a path predicate (§17.1) and the 41 files **have no frontmatter at all**.
This is a PO decision, and it blocks every derived type from advancing `shadow → proven` —
i.e. it blocks the HANDOFF's own priority 2 and, transitively, `render` for STORY-INDEX.

**Q3 — Reviews have no declared natural key.** The key is the corpus-relative **path** (390
reviews), which D-C forbids as identity. `render` must *compute* a path from a key; for reviews
the key *is* a path, so render is undefined for the largest review family in the corpus.
Candidate: `(project, cycle, scope, target, pass)` — already the registry's declared key for
`adversarial-review` — with a migration that derives it from the path and asserts uniqueness
across all 390.

**Q4 — Are frontmatter comments load-bearing enough to model, or should they be dropped with a
recorded count?** 406 files, 4,498 comment lines, 71 of them inline. At least two template comments *are* load-bearing
(`# advisory — used for drift detection, not gating`; `# metadata-only — does not affect BC
semantics`). A stride sample of 30 would settle it, and the sample is cheap. Not run here.

**Q5 — What do the 12 duplicate-key files mean, and what has already been lost?** A YAML
parser keeps the last value silently. The earlier value is not recoverable from the parsed
form, only from the bytes. Each of the 12 needs a hand read before X1's refusal lands, or the
refusal deletes information nobody has looked at.

**Q6 — Per-file disposition for 234 block scalars and 3,030 nested frontmatter lines.** Most
sit on types that become `derived` (so they vanish), but that is asserted, not measured. The
measurement is a one-liner and was not run.

**Q7 — Does `render` write `ingested`/`blob-with-path` types at all?** semport is 9,274 of
corverax's 9,291 files. Hash-only storage argues for "no". The counter-argument is invariant 8:
if `render` does not write them, something else does, and there are two truths again.

**Q8 — The role→op mapping needs the 34 agent files read.** §8.2 is derived from agent *names*
plus the three asymmetry walls quoted verbatim in `ACCESS-CONTROL.md`. The other 31 declare tool
profiles and constraints not yet reconciled. This is a 35-row table that must be measured, not
inferred — and a role that is *more* permissive than the agent's current tool profile is a
privilege escalation shipped as a refactor.

**Q9 — `gate` as an op noun.** `gate` is a live prism *field* holding an identifier
(`gate: wave-3-integration-gate`, 40 files), which is why D-D named the outcome `gate_result`.
Op nouns and field names are disjoint namespaces, so this is probably fine — but this repo has
been caught **twice** claiming a name without measuring it (`gate`, `scope`), and the check
(grep the three corpora for `gate` used as a *command word* in skills/hooks) has not been run.

**Q10 — Do committed rendered documents contain literal counts at all?** If yes, `render
--check` is the only thing between a hand edit and a re-drifted total. If no, the human review
surface loses its numbers and the "rendered markdown is the review surface" claim weakens. This
is a product decision about what the committed view is *for*, and it belongs to the user.

**Q11 — RESOLVED by the L1–L2 design, ratified into the spine while this document was being
drafted.** **One store per project, no `project` column**; the predicate is discharged by store
*selection*. Decided on measured grounds (per-branch push contention, untunable), and it is the
stronger answer: an omittable predicate is invariant 19's real failure mode and a store handle
cannot be omitted. Consequences already folded in: §3.4 (`--project` is a selector), §21.1
(`scope_digest` is per-store, so it no longer has to encode a tenant). **Registry stays shared in
the binary**, which is what keeps the generated op vocabulary (L3-1) identical across tenants.

**Q12 — Audit volume.** `STATE.md` alone carries 868 commits; op-level audit is one to two
orders of magnitude larger. Retention, compaction and whether the audit is itself an
append-only artifact type are undesigned. `dolt gc` reclaims ~6 KB/commit (L7), which is the
only relevant measurement so far.

**Q14 — The authority census must be re-run keyed on `(authority, shape)`.** §1.2 counted files
by `authority` alone, which folds the 11 `append-only-event` ledger types into the 4,861
`authored` figure — and those are the types whose files are **generated from entry rows**, not
rendered from a verbatim body (§11). The render job is therefore mis-sized in this document by
however many files the ledgers are, and the three burst-logs alone carry 301 commits. One-line
fix to probe P1; not run.

**Q15 — Does the ledger renderer own the WHOLE file or only the entry region?** `STATE.md` is
*three artifacts wearing one filename* — a mutable record plus two ledgers — so its render is a
composite of one record projection and two ledger projections, and the ordering/interleaving is
undeclared. 868 commits sit on this one file, so it is the highest-value render target in the
corpus and the least specified.

**Q13 — What is the scope-predicate language?** §17.2 writes predicates as SQL fragments. A
bounded DSL is the alternative (and is the precedent in the sibling Rivetry work). The decision
should be made *after* measuring the predicates the 7 real indexes actually need — measure the
alternative before pulling the lever. That measurement has not been made.

---

## 25. Reproduce every number in this document

Every number introduced by *this* document (as opposed to carried from the spine, the registry
or `fa`'s own gates) came from one of the four read-only probes below. Run from
`~/Dev/scrap/dolt-artifact-spike`. **A number in this document that is not reproducible by one
of these is a defect in this document.**

### P1 — file census by resolved `authority`, plus the byte-level hazards (§1.2, §11, §13.1, §14)

```sh
python3 - <<'PY'
import os,re,yaml,collections,unicodedata
R='fa/registry/'
reg=yaml.safe_load(open(R+'artifact-type-registry.yaml'))
canon={k:v['canonical'] for k,v in yaml.safe_load(open(R+'aliases.yaml'))['aliases'].items()}
auth={k:v.get('authority') for k,v in reg['types'].items()}
auth.update({k:v.get('authority') for k,v in reg.get('gap_types',{}).items()})
auth.update({k:'retired' for k in reg.get('retired_types',{})})
roots={'vsdd-factory':os.path.expanduser('~/Dev/vsdd-factory/.factory'),
       'prism':os.path.expanduser('~/Dev/prism/.factory'),
       'rivetry':os.path.expanduser('~/Dev/rivetry/.factory')}
by=collections.Counter(); s=collections.Counter(); sizes=[]; ch=collections.Counter()
for name,root in roots.items():
    for dp,dn,fn in os.walk(root):
        for f in fn:
            if not f.endswith('.md'): continue
            p=os.path.join(dp,f); b=open(p,'rb').read(); s['files']+=1
            sizes.append((len(b),p))
            if b'\r\n' in b: s['crlf']+=1
            if b.startswith(b'\xef\xbb\xbf'): s['bom']+=1
            if b and not b.endswith(b'\n'): s['no_final_newline']+=1
            if b'\t' in b: s['tabs']+=1
            t=b.decode('utf-8',errors='replace')
            if unicodedata.normalize('NFC',t)!=t: s['non_nfc']+=1
            for c in t:
                if ord(c)>127: ch[c]+=1
            tw=sum(1 for L in t.split('\n') if L!=L.rstrip() and L.strip())
            if tw: s['trailws_files']+=1; s['trailws_lines']+=tw
            m=re.match(r'^---\r?\n(.*?)\r?\n---',t,re.S)
            if not m: by['NO-FRONTMATTER']+=1; continue
            dm=re.search(r'^document_type:\s*["\']?([^"\'\n#]+)',m.group(1),re.M)
            if not dm: by['NO-document_type']+=1; continue
            dt=dm.group(1).strip()
            by[auth.get(canon.get(dt,dt),'UNRESOLVED-TYPE')]+=1
sizes.sort(reverse=True)
print('by authority:',dict(by))          # authored 4861 · derived 54 · ingested 73 · retired 211
print('byte hazards:',dict(s))           # crlf 0 · bom 0 · no_final_newline 19 · non_nfc 0
print('>600KB',sum(1 for z,_ in sizes if z>600*1024),' >300KB',sum(1 for z,_ in sizes if z>300*1024))
print('max',f'{sizes[0][0]/1024:.1f} KB',sizes[0][1])
print('top non-ASCII:',ch.most_common(6))   # — 164316 · → 92000 · § 41426 · ─ 15568
PY
```

### P2 — frontmatter census: key orders, quoting, comments, duplicate keys (§13.1, §13.2, §14)

```sh
python3 - <<'PY'
import os,re,collections
roots=[os.path.expanduser(p) for p in
       ('~/Dev/vsdd-factory/.factory','~/Dev/prism/.factory','~/Dev/rivetry/.factory')]
orders=collections.Counter(); first=collections.Counter(); perkey=collections.defaultdict(collections.Counter)
n=collections.Counter()
for root in roots:
    for dp,dn,fn in os.walk(root):
        for f in fn:
            if not f.endswith('.md'): continue
            t=open(os.path.join(dp,f),encoding='utf-8',errors='replace').read()
            if not t.startswith('---\n'): n['no_fm']+=1; continue
            e=t.find('\n---',3)
            if e<0: n['no_fm']+=1; continue
            n['fm']+=1; keys=[]; hascm=False
            for L in t[4:e].split('\n'):
                if L.lstrip().startswith('#'): n['comment_lines']+=1; hascm=True; continue
                m=re.match(r'^([A-Za-z_][\w.\-]*):(.*)$',L)
                if m:
                    k,v=m.group(1),m.group(2).strip(); keys.append(k)
                    if v=='': n['empty']+=1
                    elif v in ('|','>','|-','>-','|+','>+'): n['block_scalar']+=1
                    elif v.startswith('['): n['flow_seq']+=1; perkey[k]['flow']+=1
                    elif v.startswith('"'): n['double']+=1; perkey[k]['double']+=1
                    elif v.startswith("'"): n['single']+=1
                    else:
                        n['bare']+=1; perkey[k]['bare']+=1
                        if ' #' in v: n['inline_comment']+=1; hascm=True
                elif re.match(r'^\s+-\s',L): n['block_seq_items']+=1
                elif re.match(r'^\s+\S+:',L): n['nested_lines']+=1
            if hascm: n['files_with_comments']+=1
            if len(keys)!=len(set(keys)): n['DUPLICATE_KEY_FILES']+=1
            orders[tuple(keys)]+=1
            if keys: first[keys[0]]+=1
print(dict(n))                       # fm 5405 · no_fm 1132 · DUPLICATE_KEY_FILES 12
print('distinct key ORDERS',len(orders))       # 1189
print('first key',first.most_common(8))        # document_type 5085 · story_id 137 · …
mixed=[k for k,c in perkey.items() if c['double'] and c['bare']]
print('keys written BOTH quoted and bare:',len(mixed),'of',len(perkey))   # 169 of 1445
PY
```

### P3 — duplicate headings, table styles, index shapes (§14, §17.2)

```sh
python3 - <<'PY'
import os,re,collections
roots=[os.path.expanduser(p) for p in
       ('~/Dev/vsdd-factory/.factory','~/Dev/prism/.factory','~/Dev/rivetry/.factory')]
H=re.compile(r'^(#{2,6})\s+(.*)$'); F=re.compile(r'^\s*(```|~~~)')
dd=de=0; tl=pad=unp=nocl=colon=0
for root in roots:
    for dp,dn,fn in os.walk(root):
        for f in fn:
            if not f.endswith('.md'): continue
            t=open(os.path.join(dp,f),encoding='utf-8',errors='replace').read()
            heads=[]; inf=False
            for L in t.split('\n'):
                if F.match(L): inf=not inf; continue
                if inf: continue
                m=H.match(L)
                if m: heads.append((len(m.group(1)),m.group(2).strip()))
                if L.lstrip().startswith('|'):
                    tl+=1
                    if re.match(r'^\s*\|[\s:|-]+\|\s*$',L) and ':' in L: colon+=1
                    cs=[c for c in L.strip().strip('|').split('|') if c]
                    if cs and all(c.startswith(' ') and c.endswith(' ') for c in cs): pad+=1
                    else: unp+=1
                    if not L.strip().endswith('|'): nocl+=1
            c=collections.Counter(heads); x=sum(v-1 for v in c.values() if v>1)
            if x: dd+=1; de+=x
print('docs with duplicate ##+ headings',dd,'excess instances',de)   # 110 / 1970
print('table lines',tl,'padded',pad,'unpadded',unp,'no closing pipe',nocl,'align-colon',colon)
# 216141 / 183963 / 32178 / 1118 / 11
for p in ['~/Dev/vsdd-factory/.factory/specs/behavioral-contracts/BC-INDEX.md',
          '~/Dev/vsdd-factory/.factory/stories/STORY-INDEX.md',
          '~/Dev/vsdd-factory/.factory/specs/architecture/ARCH-INDEX.md',
          '~/Dev/vsdd-factory/.factory/specs/verification-properties/VP-INDEX.md',
          '~/Dev/vsdd-factory/.factory/specs/domain-spec/L2-INDEX.md',
          '~/Dev/prism/.factory/stories/STORY-INDEX.md']:
    p=os.path.expanduser(p); ls=open(p,encoding='utf-8',errors='replace').read().split('\n')
    sig=set(); tab=rows=0; cur=None
    for i,L in enumerate(ls):
        if L.lstrip().startswith('|'):
            if re.match(r'^\s*\|[\s:|-]+\|?\s*$',L) and i>0 and ls[i-1].lstrip().startswith('|'):
                cur=tuple(c.strip() for c in ls[i-1].strip().strip('|').split('|'))
                sig.add(cur); tab+=1
            elif cur: rows+=1
        else: cur=None
    print(f'  {os.path.getsize(p)/1024:8.1f} KB  tables {tab:3d}  sigs {len(sig):3d}  rows {rows:5d}  {p.split("/.factory/")[-1]}')
PY
```

### P4 — registry structure and the 22 missing render schemas (§1.3, §17.2, §24-Q1)

```sh
python3 - <<'PY'
import yaml,collections,os,re
d=yaml.safe_load(open('fa/registry/artifact-type-registry.yaml'))
t=d['types']
print('canonical',len(t),'gap',len(d['gap_types']),'retired',len(d['retired_types']))  # 103/16/4
print('authority',collections.Counter(v.get('authority') for v in t.values()))  # 68/22/13
print('link_types',len(d['link_types']),'enums',
      len(yaml.safe_load(open('fa/registry/enums.yaml'))['enums']),
      'aliases',len(yaml.safe_load(open('fa/registry/aliases.yaml'))['aliases']))  # 23/17/180
der=[k for k,v in t.items() if v.get('authority')=='derived']
print('derived with NO declared sections:',sum(1 for k in der if not t[k].get('sections')),'/',len(der))
print('section_policy over all types:',collections.Counter(v.get('section_policy') for v in t.values()))
# which derived types have a template declaring them
T=os.path.expanduser('~/Dev/vsdd-factory/plugins/vsdd-factory/templates')
decl=set()
for dp,dn,fn in os.walk(T):
    for f in fn:
        try: x=open(os.path.join(dp,f),encoding='utf-8',errors='replace').read()
        except: continue
        m=re.search(r'^document_type:\s*["\']?([\w./-]+)',x,re.M)
        if m: decl.add(m.group(1))
print('derived types with NO template (the §24-Q1 six):',[k for k in der if k not in decl])
PY
```

### The `fa` gate numbers carried from the HANDOFF (unchanged by this document)

```sh
cd fa && go build -o fa . && cd ..
./fa/fa init     --db /tmp/fadb
./fa/fa import   --db /tmp/fadb ~/Dev/vsdd-factory/.factory   # bc 1959 · vp 80 · story 148
./fa/fa validate --db /tmp/fadb                               # 776
./fa/fa validate --db /tmp/fadb --registry ~/Dev/vsdd-factory/.factory   # 7,487
./fa/fa shadow   --db /tmp/fadb ~/Dev/vsdd-factory/.factory   # 658
./fa/fa refs     --db /tmp/fadb --kind section --status dangling        # 30
```

### Churn (§1.2, §17.2)

```sh
cd ~/Dev/vsdd-factory/.factory && git log --format= --name-only factory-artifacts \
  | sort | uniq -c | sort -rn | head -20
# 868 STATE.md · 381 STORY-INDEX · 218 BC-INDEX · 151 ARCH-INDEX · 140 VP-INDEX
# + 98/42 cycles INDEX + 6 L2-INDEX = 1,036 across the seven derived indexes
```

Nothing in `~/Dev/vsdd-factory`, `~/Dev/prism` or `~/Dev/rivetry` was modified to produce this
document. All four probes are read-only walks; `git log` is read-only.
