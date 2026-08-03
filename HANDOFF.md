# HANDOFF — datum (formerly dolt-artifact-spike)

## ⛔⛔⛔ STANDING USER DIRECTIVE — PRODUCTION GRADE FROM DAY 1 (set 2026-08-03)

> **"Remember we want to always default to production grade from day 1, spend the time to do it
> right, don't defer unless I tell you to."** — the user, 2026-08-03

**This outranks any instinct to descope.** It applies to every session, every task, in this repo.

- **Do not defer.** No TODOs, no "filed as a follow-up", no "left for the migration" *unless the user
  says so explicitly*. If the right fix is bigger than the ticket, build the right fix.
- **Do not narrow a fix to its symptom.** The assigned task was "three importer defects"; doing it
  properly meant also fixing instance TEN (a silent 171,284-character loss in `datum`'s own frontmatter
  parser) and the subsystem-catalog gap that was zeroing 269 of prism's BCs. Both were found *because*
  the work was taken to completion instead of to the ticket boundary.
- **Every fix ships with its gate.** A fix without a test that would have caught it is not done. Prefer
  a gate over the REAL corpora to a gate over a fixture — the values that matter (a 51,566-byte
  ledger, an escaped quote at offset 18,287) are exactly the ones a hand-written fixture lacks.
- **Widening a limit is not a fix.** `VARCHAR(220)`→`1000` buys headroom; TRUNCATE-AND-REPORT instead
  of abort is the fix. A ledger in a scalar is not a too-small column.
- ⚠ **Where the user has explicitly chosen a LARGER scope, that choice stands** — e.g. "also make the
  importer split ledger fields into rows now" was chosen over my recommendation to file it. Build it.


## ⭐⭐⭐⭐⭐ CURRENT SNAPSHOT — 2026-08-03 (wrap at `b3d1bdc`) — READ THIS FIRST

**Workstream:** `datum` v1 — the sole home for every artifact of every project using the vsdd-factory
methodology. **v1 is DESIGNED (now L1–L7, all seven layers) and PARTLY BUILT.** This session moved the
code for the first time in three sessions.

**Repo:** `~/Dev/datum` · **local-only git, NO REMOTE** · clean at `b3d1bdc` ·
8 commits this session. The 148 MB `datum/datum` binary is gitignored — rebuild it (kick-start below).

**ONE-LINE RESUME:** read this block, then `research/FA-V1-DESIGN.md` (the spine — now **16** settled
decisions), then the task list below.

### What shipped this session

| commit | what |
|---|---|
| `18cc040` | **assessed the persona-storyboard process** (read all 1,951 lines) → its fix-burst register is a **THIRD validation register**; 7 transfer candidates, 3 load-bearing |
| `bfdb308` | ⭐ **closed the pivot cost** — the design's ONE unmeasured assumption — and **DERIVED the missing materialization trigger** |
| `bfa2807` | ⭐ **fixed all three importer defects + INSTANCE TEN + the subsystem-catalog gap** → `datum import` now ingests **ALL THREE corpora** (was one) |
| `f1df615` | recorded the **STANDING DIRECTIVE** (top of this file) |
| `2da3d57` | **L7 designed** — interfaces (CLI/MCP/CI) + a 7-phase delivery plan with per-phase exit criteria |
| `71a651f` | **adversarial review** of the four layer designs — 8 findings CONFIRMED, 3 WITHDRAWN |
| `02b4e00` | **RAN the storyboard process against `datum`** — 6 NEW gaps nothing else surfaced |
| `b3d1bdc` | ⭐ **V-L SETTLED** — the engine question the first 15 decisions left open |

### ⭐ V-L — the engine is now settled, and defended by a PROPERTY SET not a product name

**None of D-A..D-D or V-A..V-K had ever named a storage engine.** Dolt was the spike's *hypothesis*.
Asked directly whether to move to a graph database, the answer came out measured:

- **The data model is ALREADY graph.** `artifact_field(type,key_hash,field,ord,kind,v_text…)` **is
  subject–predicate–object**; `artifact_ref` is edges. L2-A specifies a **triple store in SQL**. The
  only live question was which engine stores the triples.
- ⭐ **Dolt IS the graph database for TRAVERSAL — measured.** GMS (pure Go, no `dolt` binary)
  **accepts recursive CTEs**: reachability with correct shortest depths, cycles **terminate**, cycle
  **detection** works. Real graph (1,547 of 4,060 edges): depth 1 → **1 ms**, 3 → 2 ms, 6 → 6 ms,
  12 → 13 ms (fixpoint at 6); **whole-graph transitive closure ≤8 = 19,628 pairs in 356–392 ms**.
- ⚠ **This CORRECTED an overclaim in our own code.** `datum graph`'s help said *"algorithms SQL cannot
  do"* — true only for **articulation points** and **betweenness**, FALSE for traversal, and
  **`degree` (the best predictor, AUC 0.871) is a `GROUP BY`.** Help text fixed. The CSR engine's live
  justification narrows to articulation points + the 250k-node scale case; betweenness was already
  tested and REJECTED.
- **L1-0 = the property set P1–P7** (versioned · branch+merge · cell-level merge · SQL **incl.
  recursive CTEs** · declarative referential integrity · embeddable with no server/binary/network ·
  transactional). **P1/P4/P6 are VETO properties.** Any engine satisfying all seven is admissible;
  Dolt is retained on that basis. TerminusDB named and declined, with reasons.

### Verified state — every number re-runnable from the kick-start

| | |
|---|---|
| `datum` | **134 tests PASS, 0 fail**, ~15 s · **schema v5** · no network, no `dolt` binary |
| `datum import` | ⭐ **all THREE corpora** — vsdd `bc=1959 vp=80 story=148` · prism `bc=269 vp=80 story=115 subsystem=22` (+7 collisions) · rivetry `bc=134 vp=55` (+**123** collisions) |
| `datum validate --registry` | **7,502** (was 7,487; +15 = the new census/ledger/subsystem findings — reconciles exactly with import findings 106→121) |
| `datum shadow` | **658 — UNCHANGED** |
| `datum refs --kind section` | resolved **2035** · dangling **30** · unresolvable **1550** — **UNCHANGED** |
| `validate_registry.py` | **18,936** (vsdd 6,951 · prism **10,953** · rivetry 1,032) ⚠ +105 vs session start is **prism corpus drift** (its concurrent session added 18 `DEFECT-*` files at 08:23–08:25), NOT our change |
| ledger fields | **18 → 229 entries**, byte-exact reversible; largest **51,566 bytes / 116 entries** |
| pivot | record read **1.0×** · filtered 2.9× · aggregate **21.7×** · full scan **152.9×** · trigger **190,000** field rows · largest type 49,121 (260 ms) = **3.9× headroom** |
| storage | at rest EAV **2.37×** · per-edit EAV **12× CHEAPER** · journal amplification **306.6×** |
| field mass | **133,674** total · **68,866** largest corpus (= order 10⁴, **not** the claimed 10⁵) |

### ▶▶▶ TOP PRIORITY NEXT — the task list, mirrored from the ephemeral tracker

**Session task list: 6 of 6 ✓ COMPLETE** (storyboard assessment · pivot measurement · importer fixes ·
L7 design · adversarial review · storyboard run) **+ V-L settled on request.** Nothing in flight.

⭐ **THE NEXT SESSION'S WORK, as the user framed it — PERSONAS RE-BASED ON THE FACTORY AGENTS:**

1. **RE-BASE the personas on the 34 real vsdd-factory agents** (measured:
   `~/Dev/vsdd-factory/plugins/vsdd-factory/agents/*.md` — adversary, architect, product-owner,
   story-writer, implementer, state-manager, holdout-evaluator, pr-reviewer, spec-reviewer,
   session-reviewer, code-reviewer, data-engineer, devops-engineer, test-writer, ux-designer,
   technical-writer, security-reviewer, formal-verifier, e2e-tester, performance-engineer,
   pr-manager, spec-steward, stub-architect, business-analyst, codebase-analyzer,
   consistency-validator, demo-recorder, dtu-validator, dx-engineer, github-ops, research-agent,
   accessibility-auditor, validate-extraction, visual-reviewer).
   ⚠ **This CORRECTS the storyboard run's cast.** The existing roster (SYS-CC / SYS-ALT / SYS-CI /
   HUM-OP) is the **TRANSPORT axis**, not the **ROLE axis**. Transport is a *dimension* of a persona;
   the **agent is the identity**. Why it matters: L3 already says *"a role is a set of permitted
   operations, not a set of writable globs"*, so **the persona roster and the role→operation manifest
   are the same artifact** — and X7 requires that manifest before any type can dual-write, putting
   this on the critical path. It also makes `DENIED-ASYMMETRY` concrete (the perimeter belongs to
   `adversary` and `holdout-evaluator` specifically) and gives V-I's six diversity-mandated roles
   real names.
   ⚠ **Use the runbook's OWN Stage 1 Step 2 distinct-behavioural-cluster test to collapse 34 → ~8–12
   personas** (merge if identical decision authority + goals across every workflow; split only if one
   named role holds two materially different authorization sets). Otherwise the coverage cube becomes
   34 × 42 ≈ 1,400 hand-built cells, and it is already flagged as needing to be GENERATED.
2. **Per persona: what QUESTIONS does it ask of the store?** The read/query workload, concretely —
   `adversary` needs *"this diff and nothing about prior passes"*; `state-manager` needs *"the current
   position"*; `product-owner` needs *"which BCs have no verifying VP"*. **Then verify the store can
   answer each, and TEST it.** We have measured query *shapes* but never the actual questions a named
   role would ask.
3. **Per persona: what CRUD ops does it need?** The write surface. This is where least privilege
   becomes real, and the ~800 generated ops are expected to be **very unevenly distributed** — that
   distribution IS the least-privilege argument. Produces the **role→operation manifest** (X7).
4. **FINISH the storyboard stages that were mapped but not executed.** Honest state: only **ONE**
   journey exists (`journey-sys-cc.md`); Stages 6 / 6.5 / 7 / 8 were mapped, not run; and the coverage
   cube's own verdict is **0 of 42 workflows evidenced**, which by the runbook's anti-pattern rule
   means every workflow currently fails its evidence gate.

5. ⭐⭐ **MODEL AND TEST MULTI-DEV / MULTI-INSTANCE OPERATION** (user-added 2026-08-03). How do N
   human devs running N instances of the factory coexist — state tracking, task/story claims,
   artifact attribution?

   **The concrete question asked, and its measured answer:** *does `datum` read the git environment /
   associate a username to state?* **No.** `commitName()`/`commitEmail()` (`datum/store.go`) read only
   `DATUM_COMMIT_NAME`/`DATUM_COMMIT_EMAIL` and otherwise return the synthetic `datum <datum@local>`; nothing
   reads `git config user.name`/`user.email`. ⚠ **Worse than synthetic — effectively UNSET:** a probe
   showed the real data commit recorded **`committer="root" email="root@%"`**, with `datum <datum@local>`
   appearing only on Dolt's own "Initialize data repository" commit. **So attribution is a constant
   today, and invariant 18's "attributable" bar plus the production-grade bar's "Attributable" claim
   are both currently FALSE.**

   **SHOULD it read git identity? Yes — but as ONE OF THREE AXES, never as authorization:**

   | axis | answers | supplied by | used for |
   |---|---|---|---|
   | **human** | which dev | git config / explicit flag | provenance, blame, review routing |
   | **agent role** | which of the 34 agents | the harness (role token) | **authorization** (L3: a role is a set of permitted operations) |
   | **session** | which instance/run | the harness (session/trace id) | correlating a write burst; detecting a retry storm |

   Constraints, each with a reason already on record:
   - **Git identity is trivially forgeable** (`git config user.email anyone@...`), so it is PROVENANCE
     only. Typed `caller-asserted`, never verified, never gated on — otherwise it repeats V-I's
     defect (an unverifiable claim treated as a gate) and violates L7-K.
   - **Do not collapse human into role.** That is the same wrong-axis error the persona cast already
     made. **Every write records the TRIPLE.**
   - **Fail closed, no silent fallback.** A container/CI runner with no git config must be REFUSED,
     not defaulted — a default that looks like a real identity is worse than absence
     (`unevaluable = block`).

   ⛔⛔ **CORRECTION (2026-08-03, after the user challenged this and I re-read the IMPLEMENTATION).
   MY FIRST WRITE-UP OF THIS TASK WAS WRONG ON THREE OF FOUR CLAIMS. The multi-dev coordination model
   is DESIGNED, MEASURED and largely SETTLED — it is NOT unmodelled, and `factory-lock` is not being
   reimplemented in `datum`, it is being made UNNECESSARY.** What follows replaces the wrong version.

   **HOW IT ACTUALLY WORKS — D3 staging refs + CI as the singleton aggregator**
   (`research/SCALE.md`, `research/CI-AGGREGATOR.md`, `poc/workflows/datum-aggregate.yml`,
   `datum/quarantine.go`):

   ```
   each writer  ──▶ dolt push refs/dolt/stage/<id>    a ref IT ALONE OWNS, outbound HTTPS only
                ──▶ fire repository_dispatch
   CI (singleton by construction):
     1 clone the artifact ref   2 enumerate refs/dolt/stage/*   3 merge each, deterministic order
     4 `datum validate`  ← ADMISSION CONTROL, before the artifact branch ever sees it
     5 ONE push to the artifact ref   6 delete consumed refs VIA THE API, only after the push landed
   ```

   - ✅ **Devs DO share the store** — through per-writer refs plus one aggregator. The committed
     render is a REVIEW SURFACE, not the sharing mechanism. *(My claim that "two devs never share a
     store, they share markdown through git" was simply wrong.)*
   - ✅ **Contention is ELIMINATED, not arbitrated.** SCALE.md rates D3 **"N (parallel,
     contention-free) → 1 push"**. The merge slot is supplied by the platform:
     `concurrency: {group: datum-aggregate, cancel-in-progress: false}`, which the workflow's own comment
     says replaces *"the entire O1-B lock-ref mechanism and every lock-ref cost: **no TTL, no
     break-glass, no unique-sha discipline**."* **That is why `factory-lock`/`unlock` go away — not
     replaced by store-side leases, made UNNECESSARY.** No lease is needed at the branch level.
   - ✅ **MEASURED, not just designed:** CI-AGGREGATOR **4/4 standard + 5/5 stressed at 20 writers,
     ~30 s median**, against real GitHub Actions; REMOTE.md **21/21** against a real github.com remote.
     `datum/quarantine.go` implements the stuck-ref policy today (pure, clock-free, tested): bounded
     re-attempts, then MOVE to `refs/dolt/quarantine/*` — **never delete, a quarantined ref still
     holds a writer's work.**
   - ⚠ **My "54 attempts with disjoint rows" citation was MISLEADING.** That figure is from the
     REJECTED one-branch free-for-all options; it is what MOTIVATED staging refs, not a cost of the
     chosen design.
   - The workflow already handles the failure modes I would have listed as gaps: a conflict isolates
     ONE writer while the others drain; an unrelated lineage is caught by *"no common ancestor"* and
     flagged loudly rather than merged; refs are deleted only AFTER the push lands so a crash leaves
     everything re-consumable; deletion goes through the refs API with the result **ASSERTED** (a
     swallowed `| tail -1` once produced an infinite re-dispatch livelock with five green runs); and
     re-dispatch fires **only on measurable progress**.

   **WHAT IS GENUINELY OPEN — and it is IDENTITY, which is worse than I first said:**
   - `datum` sets `datum <datum@local>` by default; the real data commit recorded **`committer="root"
     email="root@%"`**. The aggregator sets `user.name=datum-aggregate` / `user.email=datum-aggregate@ci`.
   - ⚠⚠ **The ONLY place a writer's identity exists is the staging ref NAME
     `refs/dolt/stage/<id>` — and step 6 DELETES that ref after consuming it.** So unless identity is
     written into the ROW DATA or set correctly on the writer's OWN commits, it is destroyed by
     design. **Invariant 18's "attributable" bar is false by MECHANISM, not by omission.**
   - ⚠ **NOT VERIFIED, and it decides the fix:** do merged writer commits retain their own authorship
     through the aggregator's DAG? Git/Dolt merge semantics say they should, but there is no remote
     here to test it against. **Test this first** — if authorship survives, the fix is at the writer
     (set the identity correctly); if not, it needs a row-level `written_by`.
   - **The three-axis identity model still stands** (human / agent role / session), and
     `refs/dolt/stage/<id>` is exactly where the human+session axes would come from. What generates
     `<id>` today is unknown — the workflow only globs `refs/dolt/stage/*`.

   **PHASE GAP, real:** `datum aggregate` is **"phase 2 plumbing pending"**;
   `poc/workflows/datum-aggregate.yml` is explicitly a **throwaway prototype** shelling out to the `dolt`
   CLI ("the real implementation is `datum aggregate`, a subcommand of the Go binary");
   `datum/workflows/datum-validate.yml` is phase-1 and states **"NO REMOTE, NO PUSH, NO DAEMON"**. So the
   MODEL is proven and the `datum`-NATIVE implementation is not written. **This repo has no remote.**

   **Sub-tasks, corrected:** (a) **test whether authorship survives aggregation** — it decides
   everything below; (b) the three-axis identity triple on every write, `caller-asserted`, failing
   CLOSED, and decide where `<id>` comes from; (c) get identity into the ROW DATA if the DAG does not
   carry it; (d) task/story CLAIMS — the one coordination primitive the aggregator model does NOT
   address (it serialises MERGES, not who is allowed to work on what); (e) pipeline-state per dev or
   per project (V-H helps: STATE.md is a position report, not truth); (f) build `datum aggregate` as the
   Go-native subcommand, retiring the prototype workflow.

**TWO DECISIONS TO SETTLE BEFORE BUILDING (do not assume):**
- Derive each agent's read/write needs from **its agent file** (what it says it does) or from **what
  the corpus shows it actually did**? Those will disagree — **and the disagreement is itself a
  finding.**
- Does a persona needing **zero writes** stay a persona, or become a pure reader?
- ⭐ ~~Private store per dev, or one shared store per project?~~ **ANSWERED by the implementation, not
  open:** per-writer clones publishing to per-writer staging refs, aggregated by CI into one artifact
  ref. The real open question is narrower — **does writer authorship survive the aggregator's merge
  DAG?** Untested, and it decides whether identity is fixed at the writer or needs a row-level
  `written_by`.
- ⭐ **Does a HUMAN hold a role in the perimeter model, or only agents?** L3's authorization is
  role-based; if humans have roles, the 34-agent roster is not the whole cast.

### ⛔ ALSO OUTSTANDING — carried forward, in priority order

From the adversarial review (`research/FA-V1-ADVERSARIAL-REVIEW.md`), highest first:
1. **F1 — locations are Go path literals, not registry data.** SYSTEMATIC across every layer;
   contradicts V-F; **manufactures FALSE findings.** Measured: `epic`/`fr`/`nfr` = 17/48/88 for vsdd
   but **0/0/0 for BOTH other projects**, producing **114 false "missing epic"** findings in prism,
   while `adr`/`cap`/`di` load fine — which is what makes it dangerous. **Ship the zero-universe guard
   immediately** (any universe empty while ≥1 artifact references it is a finding) — that alone makes
   all four instances loud, cheaply. Then `sources:` in the registry.
2. **F8 — X1's denominator shares its numerator's enumerator**, so the anti-instance-nine
   conservation gate can catch a *filter* bug but never a *location* bug (prism's epics: enumerate 0,
   compare 0, **PASS**). Needs a total whole-corpus partition into types ∪ `unmodeled_file`.
3. **F2 — the registry hash gate re-couples every project**, contradicting V-F's independence
   requirement. Version compatibility, not hash equality.
4. **F3 — cohort gate X4 embeds a volatile scalar** ("the 18,826 baseline"), which went stale TWICE
   in one session. Cite artifact + version.
5. F5 (risk #6's sign is inverted) · F7 (the 10⁵ / 2,362-BC figures) · F4 (cite gate-shaped latencies).

From the storyboard run (`storyboard/v0.1.0-datum/WORKFLOW-INVENTORY.md` §7) — **G-4..G-9 are NEW and
share one shape: a state entered with NO ROUTE BACK OUT.**
- **G-4** timing side channel on `DENIED-ASYMMETRY` — undefended and unmentioned in ANY design doc
- **G-5** a cursor must carry its project, or cross-tenant leakage returns via L7's new chunking
- **G-6** erasure has NO anti-persona (premature deletion; a vacuously-passing count assertion)
- **G-7** `datum` cannot detect an **abandoned** `CONTINUATION`
- **G-8** a recorded classification is replayed forever; no `reclassify` / re-open path
- **G-9** exit 2 is the only handoff leaving the machine and **who receives it is unrouted**

Also queued: add "surface unpushed/dirty worktrees" to `datum fsck` (F20).

### ⛔⛔ BLOCKED ON THE USER — Phase 0, and it gates schema generation

- the **2 namespace renames** (`story-spec`→`story`, `state`→`pipeline-state`) — a **hard
  precondition** of schema generation, not cleanup. `validate_registry.py` prints
  `EXIT CRITERION NOT MET: 2` until they land.
- **opening the ADR** and registering the policy · **answering #671**
- **rivetry's `delta-archive` disposition** — it is the source of 123 of its key collisions
- prism's 80 `vp-*.md`: **ANSWERED this session — fix the matcher** (done), do not rename the corpus
- prism's 7 `FOLLOWUP` story-id collisions: versions or new ids?

### Nothing was left running

No background commands, no sub-agents, no WIP. Working tree clean. **All three reference corpora were
READ-ONLY** — verified 0 `.factory` md/yaml written by us in vsdd-factory and rivetry; prism's 21
touched files are all its OWN concurrent session (18 `DEFECT-*` stories + its STORY-INDEX + its
STATE/SESSION-HANDOFF). ⚠ `~/Dev/multi-repo` was read in full and **not modified** (its 7 dirty files
predate this session: `.gitignore` 2026-07-08, `CLAUDE.md` 2026-07-24).

⚠ **A blind spot worth carrying:** `git status --porcelain | grep '\.md$'` **misses files inside an
untracked directory**, and prism's `.factory` is **gitignored entirely** — so a corpus can change with
zero porcelain output. Check file counts and mtimes, not just `git status`.

### ⭐ THE RESUME PROMPT — paste this whole block into a fresh session

```text
READ FIRST — ~/Dev/datum/HANDOFF.md. Read (a) the STANDING DIRECTIVE at the
very top, then (b) the CURRENT SNAPSHOT — 2026-08-03 block. Together they are a complete,
self-sufficient zero-context resume: the 8 commits, the 16 settled decisions, every re-runnable
number, what is outstanding, and what is blocked on me. Ignore the 2026-08-02 block's resume
prompt — it is marked stale and its tasks are done.

STANDING DIRECTIVE, which outranks any instinct to descope: production grade from day 1. Spend
the time to do it right. DO NOT DEFER unless I tell you to. Do not narrow a fix to its symptom.
Every fix ships with its gate, preferably over the REAL corpora rather than a fixture.

WHAT THIS PROJECT IS: `datum` becomes the SOLE HOME of every artifact for EVERY project using the
vsdd-factory methodology. v1 is DESIGNED across all seven layers L1-L7 and PARTLY BUILT — the
importer now ingests all three corpora, but there is still NO write path, NO `datum render`, and NO
section table.

THE TASK — personas re-based on the FACTORY AGENTS, then their queries and their CRUD:
 1. RE-BASE the storyboard personas on the 34 real vsdd-factory agents at
    ~/Dev/vsdd-factory/plugins/vsdd-factory/agents/*.md. The existing cast (SYS-CC/SYS-ALT/
    SYS-CI/HUM-OP) is the TRANSPORT axis, not the ROLE axis — transport is a dimension, the
    AGENT is the identity. This matters because L3 already says "a role is a set of permitted
    operations", so the persona roster and the role->operation manifest are THE SAME ARTIFACT,
    and X7 needs that manifest before any type can dual-write. Collapse 34 -> ~8-12 personas
    using the runbook's OWN Stage 1 Step 2 distinct-behavioural-cluster test (merge on identical
    decision authority + goals; split only on two materially different authorization sets),
    otherwise the coverage cube becomes 34 x 42 hand-built cells.
 2. Per persona: what QUESTIONS does it ask of the store? Concrete queries, not shapes. Then
    VERIFY the store can answer each one AND TEST IT.
 3. Per persona: what CRUD ops does it need? Expect a very uneven distribution over the ~800
    generated ops — that distribution IS the least-privilege argument. Output: the
    role->operation manifest.
 4. FINISH the storyboard stages that were mapped but not executed. Honest state: only ONE
    journey exists, Stages 6/6.5/7/8 were mapped not run, and the cube says 0 of 42 workflows
    are evidenced — so by the runbook's own rule every workflow currently fails its evidence gate.
 5. MODEL AND TEST MULTI-DEV / MULTI-INSTANCE. datum does NOT read git identity today, and attribution
    is effectively UNSET (a probe showed committer="root" email="root@%" on the real data commit), so
    invariant 18's "attributable" bar is currently FALSE. Should it read git identity? Yes, but as
    ONE OF THREE AXES — human (git, forgeable, PROVENANCE ONLY) / agent role (the harness's role
    token, which is what AUTHORIZATION uses) / session id — recorded as a triple on every write,
    typed caller-asserted, failing CLOSED with no silent fallback. ⛔ READ THE CORRECTION BLOCK IN
    TASK 5 FIRST: my first write-up was WRONG on three of four claims. The coordination model is
    DESIGNED AND MEASURED — D3 per-writer staging refs + CI as a singleton aggregator, contention
    ELIMINATED not arbitrated, and factory-lock goes away because GitHub's `concurrency:` group IS
    the merge slot (no TTL, no break-glass). 4/4 + 5/5 at 20 writers, ~30 s median; REMOTE 21/21.
    WHAT IS ACTUALLY OPEN: identity. The ONLY record of a writer is the staging ref NAME, and the
    aggregator DELETES it after consuming. So test FIRST whether writer authorship survives the
    merge DAG — that decides whether the fix is at the writer or needs a row-level written_by. Also
    open: task/story CLAIMS (the aggregator serialises MERGES, not who may work on what), and
    building `datum aggregate` as a Go-native subcommand (today it is a throwaway prototype workflow
    shelling out to the dolt CLI; datum is "phase 2 plumbing pending" and this repo has NO remote).

TWO DECISIONS TO SETTLE WITH ME FIRST, do not assume: (a) derive each agent's needs from its
AGENT FILE or from WHAT THE CORPUS SHOWS IT DID — they will disagree, and the disagreement is
itself a finding; (b) does a persona needing ZERO writes stay a persona or become a pure reader?

ALSO OUTSTANDING, highest first — F1 (locations are Go literals, not registry data; SYSTEMATIC,
contradicts V-F, and MANUFACTURES false findings: epic/fr/nfr are 0/0/0 for two of three
projects, producing 114 false "missing epic" findings; ship the zero-universe guard first, it is
cheap) · F8 (X1's denominator shares its numerator's enumerator, so it cannot catch a LOCATION
bug) · F2 (the registry hash gate re-couples every project) · F3 (X4 embeds a volatile scalar) ·
G-4..G-9 from the storyboard run, which share one shape: A STATE ENTERED WITH NO ROUTE BACK OUT.

BLOCKED ON ME — ASK, do not assume: the 2 namespace renames (a HARD PRECONDITION of schema
generation) · opening the ADR · answering #671 · rivetry's delta-archive disposition · prism's 7
FOLLOWUP story-id collisions.

DO NOT RELITIGATE the 16 settled decisions D-A..D-D and V-A..V-L (spine §§0, 5b-5e). V-L is the
newest: the store is a VERSIONED RELATIONAL engine holding a TRIPLE model, the graph is a
PROJECTION served by recursive CTEs, and the engine is defended by the property set P1-P7 (L1-0)
rather than by the name "Dolt".

OPERATING PRINCIPLES — every one earned by a real error here:
  - Measure, don't assume. NEVER infer a consequence from a structural fact.
  - MEASURE THE ALTERNATIVES TO THE LEVER BEFORE PULLING IT.
  - CHECK YOUR FIX'S PREDICTION, don't tune. Reading ONE case beat tuning twice more this
    session (instance ten, then the escaped-quote truncation).
  - A parser that silently loses input is the most repeated defect class here — TEN instances,
    two of them inside datum itself. Print per-form counts; report malformed; never drop.
  - A hand-maintained vocabulary drifts from another one. Read vocabulary FROM the registry.
  - A green check that never ran is not evidence — and a test that LOGS a failure instead of
    failing is that same defect (I shipped one this session and had to fix it).
  - Never report a number a test could contradict.
  - Corpora are READ-ONLY. `git status` MISSES gitignored/untracked-dir changes — check counts
    and mtimes. No AI attribution in commits. This repo has NO remote.

STATE: clean at b3d1bdc, local-only git, NO remote. 8 commits last session. Nothing in flight,
no WIP, nothing running.
```

### Kick-start (shell only)

```sh
cd ~/Dev/datum/datum
CGO_ENABLED=1 go build -tags gms_pure_go -o datum .      # BOTH flags mandatory
CGO_ENABLED=1 go test -tags gms_pure_go ./...          # 134 PASS, 0 fail, ~15 s
cd .. && python3 registry/validate_registry.py         # exit 0 · 18,936 (prism drifts — re-measure)
for c in vsdd-factory prism rivetry; do                # ALL THREE now import (exit 0)
  rm -rf /tmp/fa_$c && ./datum/datum init --db /tmp/fa_$c >/dev/null
  ./datum/datum import --db /tmp/fa_$c ~/Dev/$c/.factory
done
./datum/datum validate --db /tmp/fa_vsdd-factory --registry ~/Dev/vsdd-factory/.factory   # 7,502
./datum/datum shadow   --db /tmp/fa_vsdd-factory ~/Dev/vsdd-factory/.factory              # 658
# the measurement probes (opt-in; they need a corpus)
cd datum && CGO_ENABLED=1 go test -tags gms_pure_go -run TestWideRowCeiling -v .
DATUM_PIVOT_CORPUS=~/Dev/vsdd-factory/.factory CGO_ENABLED=1 go test -tags gms_pure_go \
  -run 'TestPivotCost|TestPivotStorage' -v -timeout 30m .
CGO_ENABLED=1 go test -tags gms_pure_go -run TestGraphInSQL -v .   # the V-L evidence
cd .. && python3 registry/probe_field_mass.py
```

### Read, in this order

`research/FA-V1-DESIGN.md` (**the spine — 16 settled decisions, incl. §5e V-L**) →
`research/FA-V1-ADVERSARIAL-REVIEW.md` (**what is wrong with the design, F1 first**) →
`research/FA-V1-L7-INTERFACES-DELIVERY.md` (the 7 phases + exit criteria) →
`storyboard/v0.1.0-datum/` (the persona work to re-base) →
`research/FA-V1-PIVOT-MEASUREMENT.md` · `research/STORYBOARD-METHOD-ASSESSMENT.md` → the layer docs.

---

## SESSION SNAPSHOT — 2026-08-02 (wrap at `1d2024b`) — superseded by 2026-08-03 above

**THE PROJECT CHANGED SHAPE THIS SESSION.** It is no longer "can Dolt back a tool that shadows the
factory's artifacts". The user set the goal: **`datum` becomes the SOLE HOME of every artifact for EVERY
project using the vsdd-factory methodology — new projects start in `datum`, existing projects migrate in
— and v1 must be production grade.** This session did the operational review and the v1 DESIGN.
**No v1 implementation exists yet, by direction ("for now, we are just designing").**

Repo: `~/Dev/datum`, **local-only git, NO remote**, clean at `1d2024b`.
The 148 MB `datum/datum` binary is gitignored — rebuild it (kick-start below).

| commit | what |
|---|---|
| `c66bbf6` | **story 12b follow-up — sampled the 214 dangling refs.** dangling 214→**30**, resolved 1408→**2035**, 81 refs that were never extracted at all now visible. 6 resolver defects, 2 new addressing schemes (now five, all test-pinned). |
| `b20f8c4` `490d05f` `1e725d3` | **six-area operational review of vsdd-factory** → `research/VSDD-FACTORY-REVIEW.md` (1,181 lines) |
| `f931ec8` | **TIER 0** — the migration/cutover tier the first feature list missed |
| `14068c6` | **the v1 SPINE** — `research/FA-V1-DESIGN.md`: decisions V-A..V-F, invariants 15–23, 7 layers |
| `157917e` | **L1–L2 storage/schema** (1,350 lines) + ratified its 3 corrections to the spine |
| `bc4f6cd` | **L5–L6 policy/engine** (1,562 lines) + **six corrections to my own review's numbers** |
| `76f41cb` | **L3–L4 ops/projections** (1,696 lines) — invalidated part of my production-grade bar |
| `726e419` | **migration + factory change spec** (724 + 639) — and **instance NINE is live in `datum`** |
| `1d2024b` | **validation against an independent prism register** + round-2 decisions V-G/V-H/V-I |

### ⛔⛔ THE ONE THING TO FIX FIRST — instance NINE of silent input loss, live in OUR code

`reVPFile = regexp.MustCompile("^(VP-\\d+)")` at **`datum/corpus.go:138`** is **case-sensitive** and is
used as the **filter** in `walkMD` at `:373`. prism names all **80** of its verification properties
`vp-001-*.md`. Non-matching files are skipped **with no error**, so **prism's entire L4 layer imports
as zero rows and nothing reports it.** Verified directly, not relayed.

Two more, also verified: **prism cannot be imported at all** (hard abort, `VARCHAR(220)` overflow on
`prose_ref.target`, `datum/schema.go:277`) and **rivetry cannot** (duplicate `VP-001` from its 211
`.DELTA-ARCHIVE` sidecars, 143 key collisions). **`datum import` today ingests ONE of THREE corpora.**
And duplicate keys are handled **three incompatible ways** — `bc` files a finding, `story` silently
keeps the first file, `vp` crashes.

### The nine settled decisions — DO NOT RELITIGATE (four more join D-A..D-D)

| | |
|---|---|
| **V-A** | `datum` is the SOURCE OF TRUTH; markdown is a **rendered view** |
| **V-B** | v1 scope is the **whole operational substrate** — store, gates, engine, scheduler, PR/CI join, cost, attestation |
| **V-C** | the canonical type set is **designed**; the corpus migrates onto it; variant spellings become unrepresentable |
| **V-D** | vsdd-factory writable **on a branch, local commits only, ASK before push** |
| **V-E** | this workstream builds **`datum` only**; factory changes are DOCUMENTED (`research/FA-V1-FACTORY-CHANGES.md`), not made |
| **V-F** | **every project migrates** — vsdd 6,951 findings / prism 10,843 / rivetry 1,032. Multi-tenancy is a v1 requirement |
| **V-G** | **review identity: backfill the 4 declared key fields at migration.** Path is one-time EVIDENCE during backfill, never identity after (keeps D-C) |
| **V-H** | **Spec Supremacy WINS.** STATE.md is a position report. Cohort G migrates as rebuildable operational data. `CLAUDE.md`'s precedence table gets corrected |
| **V-I** | **model-family diversity RETIRED as a gate for now, explicitly KEPT as a capability to grow into.** See the spine §5b — it is written out in full on purpose |
| **V-J** | ⭐ **`datum` IS RUN WITH AN AI, and the AI is the PARSER for messy input.** See the spine §5c |

### ⭐ V-J is the newest and it corrected a posture running through all four layer designs

`datum` is not a tool a human drives against tidy input. **Two boundaries, opposite postures:** the
**INGEST** boundary is tolerant and interpretive — the AI reads the mess and says what it is — while the
**WRITE** boundary stays strict and closed, which is the whole reason the mess cannot come back. I had
been applying write-boundary strictness to ingestion, which is what produced most of the "declare it out
of scope" and "needs hand adjudication" residue in the layer docs.

**The rule that keeps it honest: AI interpretation is captured as DATA, never applied as a side effect.**
Each classification/derivation becomes a transformation row with its `before`, evidence, confidence and
the fact that an AI produced it. **Determinism moves from the parser to the recorded transformation** —
a re-run REPLAYS decisions rather than re-inferring them. Without that rule, AI-assisted ingest collides
head-on with invariant 15 and the conservation gate.

**DISSOLVES these, which the top block previously listed as blockers:** the 1,338 untyped files and the
76.3% round-trip ceiling (that ceiling was a property of assuming a regex had to do the typing, not of
the corpus) · the 41 legacy stories with no frontmatter · V-G's un-derivable review-key residue · the 22
missing render schemas (an AI infers a draft from existing instances) · the ~40 one-off types with 1–4
files each · and the brittle-matcher CATEGORY (instance nine is still a bug; a regex deciding what a
file is stops being the mechanism).

**DOES NOT CHANGE:** all invariants 15–23 stand · `unevaluable = block` still holds **for gates** — an
AI interprets INPUT, it never manufactures EVIDENCE (invariant 22 untouched) · no AI write path bypasses
validation; AI output is a *proposal* through the same ops and the same 14-step ladder, which is exactly
what L3–L4's `datum propose field` (exit 4) already is · and **the conservation gate gets STRICTER, not
looser**, because a non-deterministic classifier makes silent loss easier and instance nine already
proves the exposure.

| **V-K** | ⭐ **SETTLED: the AI runs OUTSIDE. `datum` is a TOOL for an LLM harness (Claude Code, Codex, …), via CLI or MCP.** Spine §5d |

### ⭐ V-K — `datum` is a tool, never an agent

**No LLM client, no API keys, no model config, no provider network calls in `datum`.** The control flow is
**inverted** from what "AI-assisted ingest" suggests: `datum` never calls an AI for help — **`datum` emits
work, the agent interprets, `datum` records the answer**, and replays it thereafter. That preserves
deterministic / testable / offline-capable / no-provider-dependency, and keeps model choice and cost with
the caller.

- **Two co-equal surfaces, one op set:** CLI + MCP over the same registry-generated ops. MCP is
  first-class, not a later wrapper. The ~800 op names are an ASSET here — an agent holds a vocabulary
  that would drown a human.
- **Harness-portable:** must work under Codex as well as Claude Code ⇒ **no harness-specific assumptions
  anywhere.** MCP is the rich surface, CLI the universal fallback.
- **The harness supplies identity** — role token (F16), session/trace id, model identity for V-I. The
  earlier access-control work already proved an unforgeable role can ONLY come from the harness injecting
  it (a `PreToolUse`-style hook), because `datum` cannot distinguish agents sharing a process and a uid.
  V-K makes that the declared mechanism.

**⚠ TWO CONSEQUENCES NOT YET IN ANY LAYER DESIGN — both belong in L7:**

1. **`datum` cannot VERIFY a model claim, only record what the caller ASSERTS.** Attestation rows must be
   typed **caller-asserted, never verified**, and queries must distinguish them. This matters because
   V-I's original defect was *an unverifiable claim treated as a gate* — recording an assertion honestly
   is progress; recording it as proof repeats the bug somewhere new.
2. **Tool-call ergonomics are now a hard constraint, and this is the load-bearing one.** A harness tool
   call **cannot block for a 6,537-file migration**, so **no op may be long-running**: work must be
   **chunked, resumable, progress-reporting and batchable**, with `datum` emitting the NEXT unit rather than
   doing the whole job. Plus **harnesses RETRY tool calls, so every op needs an idempotence key**
   (F2/M-series already specify this). A migration expressed as thousands of round trips only works if
   each one is small, ordered, resumable and idempotent. **This reshapes the entire migration surface and
   is the biggest un-designed consequence of V-K.**

Plus **9 new invariants (15–23)** on top of SPEC.md's 1–14, three of which were sharpened by the L1–L2
design and are ratified in place: **21** covers artifact data only (a lease is not artifact data, so
revocation is TTL-or-human-authorized and **writes no artifact**); **16** binds **per shape** ("16 at
capture, 15 at cutover"); **17** permits **declared derived caches** but forbids an authored field
duplicating a derivable one.

### The reframe that makes the maximal scope tractable

Under V-A + V-C most of the ~40 review defects are **not fixed — they become UNREPRESENTABLE.** 7
`document_type` spellings, 23 verdict tokens in a 2-value field, six BC totals, 37 phantom index rows,
~14 finding ID families, the SHA-transcription class, epic-ids-in-capability-fields: all impossible
once enums close at write time, counts are projections, and **no op accepts a path, an id, or a
count.** That is story 7's argument generalized: **eliminate rather than detect.** The honest residue
`datum` CANNOT make impossible is semantic correctness — measured at **26.3% of class C**.

### ⭐ Validated against an INDEPENDENT register (`research/FA-V1-VALIDATION-PRISM-SESSION.md`)

Tested the design against `~/Dev/scrap/prism-session-findings-2026-08-02.md` (21 real findings, a
different project): **11 PREVENTED · 5 DETECTED mechanically · 1 mitigated · 3 out of scope · 1 not a
defect.** Best result: the **PROCESS-GAP** (third dual-commit breach, with a story + an open arch
question queued to build a *better detector*) **disappears** — the single-commit protocol exists only
because a SHA must be transcribed into content, and invariant 23 removes the requirement. Three
entries (S-2/S-3/E-4) are one failure in three costumes — *a check reported green without running* —
closed by one rule: **unevaluable = block, no fail-open**, + a vacuity guard, + a static binary with no
external dep to be missing. **Nothing in that register tests the engine, so L6 is unvalidated.**

### Verified state — every number re-runnable from the kick-start

| | |
|---|---|
| `datum` | **124 tests** (+9 benchmarks), ~7 s, no network, no `dolt` binary. Schema v4. |
| `validate_registry.py` | exit **0** · **18,826** findings (vsdd 6,951 · prism 10,843 · rivetry 1,032) |
| `datum validate` / `--registry` / `shadow` | **776** / **7,487** / **658** — all unchanged by the prose-ref work |
| `datum refs --kind section` | resolved **2035** · dangling **30** · unresolvable **1550** · total 3,615 |
| migration reality | vsdd 3,085 files/28.0 MB/71 raw types/21.3% can't round-trip · prism 2,784/47.6 MB/**150 types**/**67.8%** · rivetry 668/19.4 MB/51/**68.0%** |
| coverage gaps | **18 of 70** observed `document_type` values have a table · **1,338 files (20.5%) carry no type at all** · 940 typed files in 75 types with no table · 80 of 103 canonical types in use |
| bodies | only `bc`/`vp`/`story` carry one; **no `section` table**; max body **1.57 MB** (not the 211 KB SPEC.md says) |

### ▶▶▶ TOP PRIORITY NEXT — the user chose ALL THREE. Nothing is in flight.

**Session task list: 3 of 5 ✓ completed** (dangling-ref sampling · the factory review · the v1 design).
Two carried over and are now REFRAMED by the design, do not do them standalone:
- ~~"move the scope predicate into the registry"~~ → it is **Cohort A** of the migration, and L3–L4 adds
  that it must be a **FIELD predicate, not a path prefix** (a prefix would promote path-as-identity).
- ~~"STORY 6 — ledgers to rows"~~ → it is **Cohort D** (58 files, 26,632 refs).

1. **MEASURE the field-per-row pivot cost, then fix the three importer defects.** The pivot is the
   design's **one unmeasured assumption** (materialization fallback specified, **no trigger**) — and a
   design resting on an unmeasured number is what "never report a number a test could contradict"
   forbids. Then fix `corpus.go:138` case-sensitivity, the `VARCHAR(220)` overflow, and the three
   incompatible duplicate-key behaviours. All are Cohort A, all in `datum`, none in the factory.
2. **Design L7 (interfaces: CLI/MCP/CI) + the phased delivery plan with per-phase exit criteria.**
3. **Adversarially review the four layer designs with FRESH EYES** — ~6,200 lines written partly in
   parallel, so the seams are worth attacking. Do this in a fresh session on purpose; reviewing them
   with the authoring context still loaded is the anchoring the factory's own fresh-context rule exists
   to prevent.

**Also queued, smaller:** add "surface unpushed/dirty worktrees" to `datum fsck`'s scope (F20) — the prism
register's E-1/E-2 are real git-level data-loss risks `datum` can *report* without pretending to own.

### ⚠ FOUR OPEN ITEMS THE LAYER DESIGNS SURFACED — they live only in those docs, so they are repeated here

⚠ **Items 1 and 2 are RESHAPED by V-J** — still work, no longer blockers. Read V-J first.

1. **`datum render` is blocked on SCHEMAS, not on an engine.** **All 22 derived types declare ZERO
   sections**, and the three highest-churn indexes (BC-INDEX **218** commits, VP-INDEX 140,
   cycle-index 140) have no template either. No renderer can be written against a type that does not
   say what it looks like — invariant 15 cannot be gated without them. **Under V-J the AI infers a draft
   schema from existing instances of each type and proposes it for ratification**, so this is a review
   task rather than 22 authoring tasks. Still on the critical path.
2. **The 41 legacy stories in `stories/v1.0-legacy/` have NO frontmatter**, so there is nothing to
   derive a scope FIELD from mechanically — and L3–L4 ruled that the scope predicate must be a **field**
   predicate, not a path prefix (a prefix would promote path-as-identity, which D-C forbids). These 41
   are the same set whose deliberate omission from STORY-INDEX produced the scope-predicate result in the
   first place. **Under V-J the AI reads each body and derives the field, with the derivation recorded as
   a transformation row.** The declared-exemption route is no longer needed.
3. **`parallel-foreach` is a SEVENTH step type** (8 uses) that my own brief and every doc's
   "six step types" list omits — and **its iteration set is undocumented, which blocks byte-exact
   round-trip** of any workflow containing it.
4. **Greenfield cannot reach COMPLETE today.** **140 `depends_on` edges point at conditional steps —
   26% of the graph** — and `session-review:1379` depends on `post-feature-validation:1364`, which is
   **off by default**, so the post-pipeline tail is unreachable. The fix is L5–L6's three-valued
   condition model where **UNKNOWN blocks rather than skips**, with `step_dep.on_skip` non-nullable.

### Design doc sizes, for orientation before opening one

`FA-V1-DESIGN.md` **≈390** (the spine — read this first, it is the shortest and everything keys off it) ·
`FA-V1-L1-L2-STORAGE-SCHEMA.md` 1,350 · `FA-V1-L3-L4-OPS-PROJECTIONS.md` 1,696 ·
`FA-V1-L5-L6-POLICY-ENGINE.md` 1,562 · `FA-V1-MIGRATION.md` 724 ·
`FA-V1-FACTORY-CHANGES.md` 639 · `VSDD-FACTORY-REVIEW.md` 1,181 · `FA-V1-VALIDATION-PRISM-SESSION.md` ≈200.
**Each layer doc ends with its own OPEN QUESTIONS section** — L1–L2 has 12, L5–L6 has 13, L3–L4 has 15.
The blocking ones are already lifted into this handoff; the rest stay in place.

### ⛔ BLOCKED ON THE USER

- **The 2 namespace renames** (`story-spec`→`story`, `state`→`pipeline-state`) are now a **hard
  PRECONDITION of schema generation**, not the cleanup item they were filed as. `validate_registry.py`
  prints `EXIT CRITERION NOT MET: 2` until they land. They are one-line edits in vsdd-factory, which
  V-E makes a separate workstream.
- **Opening the ADR** and registering the policy · **answering #671**.
- From the migration design: does prism **rename its 80 `vp-*.md` files**, or does the matcher become
  case-insensitive (my read: fix the matcher — it is `datum`'s defect, not prism's naming)? Are prism's 7
  `FOLLOWUP` story-id collisions versions or new ids? Is rivetry's `delta-archive` safe to **delete**
  after backfill?
- From the prism register's own queue: **FINDING-A** (6 PROPOSED ADRs cited as authoritative) and
  **FINDING-G** (CLAUDE.md documents detector arms that do not exist) both need human mandates.

### Read, in this order, for the next session

`research/FA-V1-DESIGN.md` (**the spine — 9 decisions, 23 invariants, 7 layers; everything keys off
it**) → `research/FA-V1-VALIDATION-PRISM-SESSION.md` (what the design does and does not prevent) →
then the layer you are working on: `FA-V1-L1-L2-STORAGE-SCHEMA.md` · `FA-V1-L3-L4-OPS-PROJECTIONS.md` ·
`FA-V1-L5-L6-POLICY-ENGINE.md` · `FA-V1-MIGRATION.md` · `FA-V1-FACTORY-CHANGES.md`.
`research/VSDD-FACTORY-REVIEW.md` is the problem statement + its own corrections block.

### ⚠ STALE RESUME PROMPT (2026-08-02) — its "TASK — all three" are DONE. Use the 2026-08-03 one above.

```text
READ FIRST — ~/Dev/datum/HANDOFF.md, the TOP BLOCK. It is a complete,
self-sufficient zero-context resume: all 14 commits, the 15 settled decisions, the 23 invariants,
every re-runnable number, what is blocked on me, and the corrections I made to my own claims.
Read it before anything else.

Then, as the work requires:
  research/FA-V1-DESIGN.md      THE SPINE — 15 settled decisions (V-A..V-K + D-A..D-D), 23
                                invariants, 7 layers. Shortest doc; everything keys off it.
                                Read this second, always.
  research/FA-V1-VALIDATION-PRISM-SESSION.md  what the design does and does NOT prevent, tested
                                against an independent register (11 of 21 prevented)
  research/FA-V1-L1-L2-STORAGE-SCHEMA.md   one store per project; the registry GENERATES the schema
  research/FA-V1-L3-L4-OPS-PROJECTIONS.md  ops generated from the registry; render; invariant 15
  research/FA-V1-L5-L6-POLICY-ENGINE.md    gates as queries; convergence computed, not claimed
  research/FA-V1-MIGRATION.md              the per-(project,type) cohort ladder
  research/FA-V1-FACTORY-CHANGES.md        a SEPARATE workstream — documented, NOT to be done here
  research/VSDD-FACTORY-REVIEW.md          the problem statement + its own corrections block
Each layer doc ends with its own OPEN QUESTIONS (12 / 15 / 13). The blocking ones are already
lifted into the HANDOFF top block.

WHAT THIS PROJECT IS NOW: `datum` becomes the SOLE HOME of every artifact for EVERY project using the
vsdd-factory methodology — new projects start in datum, vsdd-factory + prism + rivetry migrate in —
production grade for v1. v1 is DESIGNED, NOT BUILT (~6,300 lines of design). The code is still
phase-1 read-only shadow: no write path, no `datum render`, no section table.

REBUILD AND RE-VERIFY (the 148 MB binary is gitignored):
  cd datum && CGO_ENABLED=1 go build -tags gms_pure_go -o datum .    # BOTH flags mandatory
  CGO_ENABLED=1 go test -tags gms_pure_go ./...                # 124 tests, ~7s
  cd .. && python3 registry/validate_registry.py               # exit 0 · 18,826
  ./datum/datum init --db /tmp/fadb && ./datum/datum import --db /tmp/fadb ~/Dev/vsdd-factory/.factory
  ./datum/datum validate --db /tmp/fadb --registry ~/Dev/vsdd-factory/.factory   # 7,487
  ./datum/datum shadow   --db /tmp/fadb ~/Dev/vsdd-factory/.factory              # 658
  ./datum/datum refs     --db /tmp/fadb --kind section --status dangling         # 30
  # these two FAIL — that is task 1 below, NOT your setup being wrong:
  ./datum/datum import --db /tmp/fap ~/Dev/prism/.factory     # aborts: VARCHAR(220) overflow
  ./datum/datum import --db /tmp/far ~/Dev/rivetry/.factory   # aborts: duplicate VP-001

REFERENCE CORPORA — LOCAL and READ-ONLY. DO NOT WRITE to any of them, not even a branch.
  ~/Dev/vsdd-factory/.factory  3,085 files · 71 raw types · pin 0aaba144
  ~/Dev/prism/.factory         2,784 files · 150 raw types · CONCURRENTLY EDITED, re-measure it
  ~/Dev/rivetry/.factory       668 files · 51 raw types
Verified at wrap: 0 md/yaml modified in vsdd-factory, 0 in prism; rivetry's 1 predates by 6 days.

TASK — all three, in this order:
 1. MEASURE the field-per-row pivot cost at corpus scale, THEN fix the three verified importer
    defects. The pivot is the design's ONE unmeasured assumption (materialization fallback
    specified, no trigger), and a design resting on an unmeasured number violates this repo's own
    rule. Then: (a) datum/corpus.go:138 `reVPFile` is CASE-SENSITIVE and is the walkMD FILTER, so
    prism's 80 `vp-001-*.md` import as ZERO ROWS with no error — INSTANCE NINE of this repo's
    most-repeated defect class, in our own importer; (b) the VARCHAR(220) overflow on
    prose_ref.target; (c) duplicate keys handled THREE incompatible ways (bc files a finding,
    story silently keeps the first, vp crashes). All Cohort A, all in datum, none in the factory.
 2. DESIGN L7 (interfaces) + the phased delivery plan with per-phase exit criteria. L7 has hard
    new inputs from V-J/V-K: the consumer is an LLM HARNESS (Claude Code, Codex) via CLI or MCP;
    datum is NEVER an agent; NO op may be long-running (a harness call cannot block for a 6,537-file
    migration ⇒ chunked, resumable, progress-reporting, batchable, datum emits the NEXT unit); every
    op needs an IDEMPOTENCE KEY because harnesses retry; and datum CANNOT VERIFY a model claim, only
    record what the caller ASSERTS (type it caller-asserted, never verified).
 3. ADVERSARIALLY REVIEW the four layer designs with FRESH EYES — ~6,300 lines written partly in
    parallel, so the seams are worth attacking. Doing this in a fresh session is deliberate.

DO NOT DO THESE STANDALONE — the design reframed both:
  "move the scope predicate into the registry" is Cohort A, and it must be a FIELD predicate, not
  a path prefix (a prefix would promote path-as-identity, which D-C forbids).
  "STORY 6 — ledgers to rows" is Cohort D (58 files, 26,632 references).

BLOCKED ON THE USER — ASK, do not assume: the 2 namespace renames (story-spec->story,
state->pipeline-state) are now a HARD PRECONDITION of schema generation, not cleanup · opening the
ADR · answering #671 · does prism rename its 80 vp-*.md files, or does the matcher become
case-insensitive (my read: fix the matcher — it is datum's defect, not prism's naming) · are prism's 7
FOLLOWUP story-id collisions versions or new ids · is rivetry's delta-archive safe to DELETE after
backfill.

DO NOT RELITIGATE the 15 settled decisions — D-A..D-D (prose = verbatim body bytes + a derived
ordinal section partition, gated byte-exact · gitignored store + committed render + invariant 15 ·
declared natural keys with path DERIVED and never identity, plus an id_alias ledger · verdict
retired into gate_result/convergence/severity_max) and V-A..V-K (datum is the source, markdown a
rendered view · v1 scope is the whole operational substrate · the canonical type set is designed
and migrated onto · vsdd-factory writable on a branch, local commits only, ASK before push · this
workstream builds datum ONLY, factory changes are DOCUMENTED not made · EVERY project migrates ·
review identity by backfilling the 4 declared key fields · Spec Supremacy beats STATE.md ·
model-diversity retired as a gate but KEPT as a capability to grow into · datum is run WITH an AI and
the AI is the PARSER for messy input — ingest tolerant, write strict, interpretation captured as
DATA never applied as a side effect · the AI runs OUTSIDE: datum is a TOOL for an LLM harness).

OPERATING PRINCIPLES — every one earned by a real error here:
  - Measure, don't assume. NEVER infer a consequence from a structural fact.
  - MEASURE THE ALTERNATIVES TO A LEVER BEFORE PULLING IT — it has deleted planned work 3 times.
  - CHECK YOUR FIX'S PREDICTION, don't tune. Failed again last session (predicted ~70, got 17);
    reading ONE case rather than tuning found the real cause, two sessions running.
  - A parser that silently loses input is the most repeated defect class here — NINE instances, the
    ninth in datum's own importer. Print per-form counts; report malformed; never drop.
  - A hand-maintained vocabulary drifts from another one — 5 instances. Read vocabulary FROM the
    registry.
  - RULE ORDER is a correctness property (emptiness-before-counting asserted the OPPOSITE of the
    truth on 18 rows).
  - A green check that never ran is not evidence. Three separate prism findings; one rule closes all.
  - NEVER report a number a test could contradict — including in the handoff. I wrote "121 tests"
    from arithmetic last session; it was 124.
  - Parity, not inspection. Counting files is not counting artifacts.
  - Corpora are READ-ONLY. Never push without confirmation. No AI attribution in commits.

STATE: clean at 653dd2b, local-only git, NO remote. 14 commits last session. Nothing in flight, no
WIP, nothing running. All 10 sub-agents completed; their outputs are the research/ docs above.
```

### Kick-start (shell only)

```sh
cd ~/Dev/datum/datum
CGO_ENABLED=1 go build -tags gms_pure_go -o datum .      # BOTH flags mandatory
CGO_ENABLED=1 go test -tags gms_pure_go ./...          # 121 tests, ~7 s
cd .. && python3 registry/validate_registry.py         # exit 0 · 18,826
./datum/datum init --db /tmp/fadb && ./datum/datum import --db /tmp/fadb ~/Dev/vsdd-factory/.factory
./datum/datum validate --db /tmp/fadb --registry ~/Dev/vsdd-factory/.factory   # 7,487
./datum/datum shadow   --db /tmp/fadb ~/Dev/vsdd-factory/.factory              # 658
./datum/datum refs     --db /tmp/fadb --kind section --status dangling         # 30
# these two FAIL TODAY — that is finding #1, not your setup being wrong:
./datum/datum import --db /tmp/fap ~/Dev/prism/.factory      # aborts: VARCHAR(220) overflow
./datum/datum import --db /tmp/far ~/Dev/rivetry/.factory    # aborts: duplicate VP-001
```

⚠ **Corpora were READ-ONLY all session and verified so at wrap:** 0 md/yaml modified in vsdd-factory,
0 in prism, and rivetry's 1 (`sidecar-learning.md`) is dated **2026-07-27**, six days before this
session. prism advanced 5 commits / 75 md files past the registry pin mid-session but its 10,843 total
and its type census are **byte-identical** — re-measure anyway before trusting a prism number.

### Nothing was left running

All 10 sub-agents (6 review + 4 design) completed and their outputs are committed as the `research/`
documents above. No background commands, no WIP, no uncommitted work.

### Operating principles — every one earned by a real error here

- **Measure, don't assume. NEVER infer a consequence from a structural fact.**
- **MEASURE THE ALTERNATIVES TO A LEVER BEFORE PULLING IT** — it has deleted planned work three times
  now (free `degree` beat betweenness; rows-vs-prose split story 12; and the registry already
  collapsing 14 adversary spellings meant V-C was not a taxonomy exercise).
- **CHECK YOUR FIX'S PREDICTION, don't tune.** Failed again this session: predicted ~70 resolutions,
  got 17. Reading ONE case rather than tuning is what found the real cause — second session running.
- **A parser that silently loses input is the most repeated defect class here — now NINE instances,
  the ninth in `datum`'s own importer.** Print per-form counts; report malformed; never drop.
- **A hand-maintained vocabulary drifts from another one** — five instances. Read vocabulary FROM the
  registry.
- **Rule ORDER is a correctness property** (emptiness-before-counting asserted the *opposite* of the
  truth on 18 rows) — so the L3 validation ladder's order is TESTED.
- **A green check that never ran is not evidence.** Three separate prism findings; one rule closes them.
- **Never report a number a test could contradict.** Chase every "off by a little".
- **Parity, not inspection.** **Counting files is not counting artifacts.**
- **Corpora are READ-ONLY. Never push without confirmation. No AI attribution in commits.**

---

## SESSION SNAPSHOT — 2026-08-01 (wrap at `983df3d`)

**STORY 7 (shadow stage), STORY 4 (findings as rows) and STORY 12 (split into 12a + 12b) ALL
SHIPPED, plus the three registry pattern defects they depended on.** Nothing in flight, no WIP.
Corpora READ-ONLY throughout: **0 md/yaml modified in vsdd-factory**; rivetry's 1 was already
dirty at session start; prism's are a CONCURRENT session, not this work.

Repo: `~/Dev/datum`, **local-only git, NO remote**, clean at `983df3d`.
The 148 MB `datum/datum` binary is gitignored — rebuild it (kick-start below).

| commit | what |
|---|---|
| `2922740` | **STORY 7 — the SHADOW stage.** `datum shadow` derives BC-INDEX / VP-INDEX / STORY-INDEX from the store and adjudicates them CELL BY CELL against the authored docs. Writes NOTHING (hash-verified). **658 findings.** |
| `9be0fcf` | **STORY 4 — findings as ROWS.** `review` + `adversarial_finding`; 390 reviews, 2,211 finding rows; each review's claim vs `COUNT(*)`. |
| `387425a` | handoff for the above |
| `90b43da` | **STORY 12 — measured the ALTERNATIVE first.** 93.6% of prose refs should be ROWS, not extracted. |
| `aa274dd` | **the DENOMINATOR GAP closed — it overturned my own priority.** |
| `6722cac` | **the three `prose_ref_kinds` defects fixed + gated** (check `[1n]`). |
| `d05be8a` | **STORY 12a** — AC/EC/PC/T-task as rows with typed links; POLICY 8 is a JOIN. |
| `632a6fa` | **STORY 12b** — section refs + version cites judged by `pin_policy`. |
| `0dc28cb` | corrected a test count I overstated in `632a6fa`'s own message (118 → 116). |
| `983df3d` | **12b follow-up** — sampled the dangling refs; the corpus addresses a section THREE ways. |

### Verified state — every number re-runnable from the kick-start

| | |
|---|---|
| `datum` | **117 tests**, ~6.7 s, no network, no `dolt` binary. **Schema v4.** |
| `registry/validate_registry.py` | exit **0** · **18,826** conformance findings · check `[1n]` reports **15** prose-ref kinds |
| `datum validate --registry` | **7,487** total (776 store-side + 6,711 registry-side) |
| `datum validate` (store-side only) | **776** — top: 306 floating cites lag · 218 POLICY-8 · 68 review-count · 58 dep-direction |
| `datum shadow` | **658** — 573 real drift · 44 editorial · 41 facts about derivation itself |
| `datum import` | bc 1,959 · vp 80 · story 148 · reviews 390 · finding rows 2,211 · sub-artifacts 4,492 (+914 typed links) · prose refs 3,537 · version cites 2,197 |
| graph / waves | unchanged: 2,421 nodes · 148 stories in 16 waves · 0 cycles |

**New subcommands:** `datum shadow <corpus>` (story 7) · `datum refs --kind section|version-cite
[--status X]` (read-only listing; sampling requires listing).
**New tables:** `review`, `adversarial_finding`, `sub_artifact`, `sub_artifact_ref`, `prose_ref`,
`version_cite`.

### ⭐⭐ THE FIVE TRANSFERABLE RESULTS — these change how the next work is done

1. **A DERIVED ARTIFACT NEEDS A DECLARED SCOPE PREDICATE**, or derivation silently changes the
   document's meaning. 41 of 148 stories live in `stories/v1.0-legacy/` and STORY-INDEX
   deliberately omits them (verified as EXACT set equality, 41 == 41). Generating from every
   record would have **RESURRECTED 41 retired stories while every count still agreed** — a
   defect no count, id-set or cell check would catch. **Story 4 hit the identical class
   independently** (`findings_total` counts only the findings a pass OWNS, not the pass-1 ones it
   re-states in its fix-verification section). ⚠ **Scope still lives in Go `shadowSpecs`; it
   belongs in the registry beside `derivation_stage`.**
2. **MEASURE BEFORE WRITING THE RULES.** The probes ran first, and the first cuts STILL reported
   **~2,768 findings that were artefacts of their own normalisation** — 4× the 658 real ones.
   Two named sub-classes: a normalisation rule aimed at the **WRONG COLUMN** manufactures exactly
   what it was added to prevent (292 self-inflicted), and **RULE ORDER IS A CORRECTNESS
   PROPERTY** (emptiness-before-counting asserted the *opposite* of the truth on 18 rows).
3. **MASS ≠ VALUE. Never infer a value split from a mass split.** Over corpus mass, prose refs
   are 93.6% row-shaped / 6.4% prose. Over **the adversary's findings** — the denominator the
   21.8% value claim uses — 12a and 12b are **EQUAL at 36.8% of class C each**, with 26.3% beyond
   both. I recommended the wrong priority from the mass number. Thousands of `D-\d+` mentions
   collapse into a handful of findings; one inlined `100ms` literal is a finding by itself.
4. **A HAND-MAINTAINED VOCABULARY DRIFTS FROM ANOTHER HAND-MAINTAINED VOCABULARY.** Three times
   this session a hardcoded list was the defect: story 4's review types (disagreed with the
   Python extractor's list on 8 spellings both ways), the prose-ref probe's pattern copy, and the
   registry's own unanchored patterns. **Always read the vocabulary FROM the registry.**
5. **CHECK YOUR FIX'S PREDICTION, don't tune.** I predicted prefix-of-heading matching would
   recover ~160 of 250 dangling refs; it recovered **46**. Reading ONE failing case instead of
   tuning is what exposed the third section-addressing scheme. Tuning would have buried it.

### Corrections I made to my OWN claims — carry these forward

- **BC `Status` looked like 0.8% agreement** (catastrophic). My probe read `lifecycle_status`.
  BC files carry **BOTH** `status: draft` (1,950) and `lifecycle_status: active` (1,945);
  BC-INDEX tracks `status` and real agreement is **99.4%**. Same error explained VP
  Type/Proof-Method/Scope, all actually 98.8–100%.
- **The 18,418 baseline was STALE.** Reconciled exactly: 902da9d registry on pinned corpora
  18,396, +22 untracked prism files = 18,418; HEAD registry on the SAME pinned input 18,804;
  working 18,826. **+408 is the registry's own tightening, NOT corpus drift.**
- **My probe over-counted reviews by ONE** (391 vs `datum`'s 390) — a `re.M` fallback matched a
  `document_type:` line in a BODY. 390 is correct.
- **My undeclared-forms census over-counted by ~12,150** — a generic `[A-Z]+-…` sweep captured
  hyphenated English (`PASS-WITH-NITS`, `WASM-only`, `WONT-FIX`). Found by SAMPLING the tail.
  ⚠ That correction moved the number in FAVOUR of a conclusion I had already reached, which is
  exactly when to be most skeptical; it rests on 26 of 1,585 tail forms.
- **I overstated a test count** in `632a6fa`'s message (118 vs 116). Corrected in `0dc28cb`.

### NEW findings no gate reported before

- **`status` and `lifecycle_status` DISAGREE on 1,949 of the 1,959 BC files carrying both.** Two
  fields for one concept — D-D's territory, and nothing reports it today.
- **The `adversarial-finding` template's OWN id convention was the one form the extractor
  missed.** `adv-s8.00-p1.md` claimed 14 findings and extracted 0 while documenting that exact
  format in its own `## Finding ID Convention` section. **Six id conventions** live in the corpus.
- **Severity is unresolved on 23% of finding rows** (499 of 2,211) across six prose conventions.
- **The corpus addresses a section THREE ways**: heading NAME · section ORDINAL (D-A's own key) ·
  ITEM within a section (`§Postcondition 5` where the doc has `## Postconditions`).
- **330 BC-5.\* files carry `capability: CAP-001`** while BC-INDEX distributes them across 11
  capabilities (`CAP-070`…`080`). One drift event = half of `datum shadow`'s findings.

### ▶▶▶ TOP PRIORITY NEXT — nothing is in flight

1. **Sample the remaining 214 dangling section refs** to earn PER-REFERENCE reporting. Currently
   AGGREGATE ONLY, deliberately: their post-fix precision is unmeasured and a confident wrong
   finding set is worse than a count. `datum refs --db X --kind section --status dangling` lists them.
2. **Move the SCOPE PREDICATE into the registry** beside `derivation_stage` (result 1 above). It
   is the one thing blocking any derived type from advancing `shadow → proven`.
3. **STORY 6 — ledgers to append-only rows.** The census puts it at **26,632 references**, the
   largest remaining row-shaped block (`decision` 20,788 + `lesson` 5,844).
4. **Adjudicate, as PO calls not tool calls:** the 330-row Capability block · the 218 POLICY-8
   findings · the 68 reviews whose stated finding count disagrees with their own body.
5. **Give the store what it lacks:** `vp.status` (VP-INDEX's Status column is UNDERIVABLE today
   and says so) · a representation for a withdrawn-in-place row (`~~BC-2.02.013~~`) · a **declared
   natural key for reviews** (the key is the corpus-relative PATH, which D-C forbids as identity).
6. `cycles/INDEX` is now shadowable — story 4 unblocked it.

### ⛔ BLOCKED ON THE USER (all need write access to vsdd-factory / GitHub — ASK, do not assume)

- the **2 namespace renames** (`story-spec`→`story`, `state`→`pipeline-state`) that close story 1.
  `validate_registry.py` prints **EXIT CRITERION NOT MET: 2** until they land.
- **opening the ADR** and registering the policy.
- **answering #671** — an open, unbuilt proposal by another author that this direction contradicts.

### Read, in this order, for the next session

`registry/README.md` (the standard + the 18,826 reconciliation) ·
`research/SHADOW-INDEXES.md` (story 7, and the false findings its rules prevent) ·
`research/FINDINGS-AS-ROWS.md` (story 4) ·
`research/PROSE-REFS-OR-FIELDS.md` (**why story 12 was split, the denominator gap, and the
dangling-ref follow-up**) · `registry/class_c_decomposition.json` (the 19 hand-classified
findings, one reason each) · `registry/CHANGE-MANAGEMENT.md` (ADR + policy + 16 stories).

### Kick-start

```sh
cd ~/Dev/datum/datum
CGO_ENABLED=1 go build -tags gms_pure_go -o datum .      # BOTH flags mandatory
CGO_ENABLED=1 go test -tags gms_pure_go ./...          # 117 tests, ~6.7 s
cd .. && python3 registry/validate_registry.py         # exit 0 · 18,826 · [1n] 15 kinds
./datum/datum init --db /tmp/fadb && ./datum/datum import --db /tmp/fadb ~/Dev/vsdd-factory/.factory
./datum/datum validate --db /tmp/fadb --registry ~/Dev/vsdd-factory/.factory   # 7,487
./datum/datum shadow   --db /tmp/fadb ~/Dev/vsdd-factory/.factory              # 658
./datum/datum refs     --db /tmp/fadb --kind section --status dangling         # 214
./datum/datum waves --db /tmp/fadb && ./datum/datum graph build --db /tmp/fadb
python3 registry/probe_indexes.py && python3 registry/probe_findings.py && \
  python3 registry/probe_prose_refs.py      # the measurements every rule came from
```

⚠ **prism's corpus is edited by a CONCURRENT session** (`.factory` advanced `95b90d003` →
`9f3443d6f` mid-session; 46 files dirty at wrap, none of it this work — verified 0 modified in my
active window). Its conformance total was **10,843 either way**. Re-measure before trusting any
prism count. vsdd-factory and rivetry were static.

### OPERATING PRINCIPLES — every one earned by a real error in this repo

- Measure, don't assume. **NEVER infer a consequence from a structural fact.**
- **MEASURE THE ALTERNATIVES TO A LEVER BEFORE PULLING IT.** It has now deleted planned work
  TWICE: free `degree` beat betweenness (AUC 0.871 vs 0.725 at 1/3000 the cost), and measuring
  rows-vs-prose split story 12 in half instead of building a permanent extractor.
- **Never report a number a test could contradict.** Chase every "off by a little" — an off-by-ONE
  review count exposed a frontmatter-parsing difference; an off-by-408 exposed a stale baseline.
- **Never collapse exit 1 (gate failed) and exit 2 (datum failed).**
- **Before claiming a field name, measure whether it is already in use** (`gate` and `scope` both
  were).
- **A regex must not cross block boundaries**, and **a parser that silently loses input is the
  single most repeated defect class here** — six instances, the sixth in the STANDARD itself.
- **Parity, not inspection.** 67/67 rules Go-vs-Python; CSR-vs-gonum on hand-worked answers.
- **Counting files is not counting artifacts; counting MENTIONS is not counting findings.**

---

## ⭐⭐⭐ SESSION SNAPSHOT — 2026-07-31 (wrap at `6341ab2`)

**Seven commits. The type registry was BUILT, ported into `datum`, and the knowledge graph got a
real projection engine.** Everything below is measured; every claim has a repro command.
`~/Dev/vsdd-factory`, `prism` and `rivetry` were **READ-ONLY the whole session** (verified: 0
files modified after 21:00).

| commit | what |
|---|---|
| `902da9d` | **THE REGISTRY** — 103 canonical types + 16 gap + 4 retired, 14 closed enums, 180 aliases, change-management package, validator (exit 0) |
| `30f7057` | **#671's exit criterion RUN** — prose extraction worth 21.8%, derived-data 25.3%, 37.9% beyond any parser |
| `d58b77c` | **`datum validate --registry`** — registry embedded in the binary, **67/67 rule parity** with the Python validator |
| `e62665b` | **Namespace reconciliation (story 1)** — the disagreement is **2**, not 17 |
| `6cc25cc` | **All four things taken from #671** folded in + machine-checked |
| `8713636` | **Knowledge-graph projection** (gonum) + `waves`/`graph metrics|dot|diff` + benchmarks |
| `c4d59d0` | **Centrality hypothesis TESTED** — betweenness loses to free degree; comes off the plan |
| `6341ab2` | **CSR engine** for 250k+ — 96× less memory, ~100× faster, parity-verified |

### The state in one screen

| | |
|---|---|
| Registry | `datum/registry/{artifact-type-registry,enums,aliases}.yaml` — the ONE canonical copy, `go:embed`'d into `datum` AND read by the Python tooling |
| `datum` | **62 tests · 9 benchmarks**, ~3.5 s, no network, no `dolt` binary |
| Gate on live corpus | **6,864 findings** (153 store-side + 6,711 registry-side), all baselined; ratchet proven (planted violation → exit 1 naming it) |
| Graph | **2,421 nodes · 4,060 edges**, CSR at **0.1 MB**; 148 stories in **16 waves**; **0 dependency cycles**; 50 articulation points |
| Repo | local-only, **NO remote**, clean at `6341ab2` |

### ⚠ FIVE CORRECTIONS TO MY OWN CLAIMS THIS SESSION — carry these forward

1. **"The standard already exists / ~12 legacy spellings."** True by mass, false by vocabulary.
   **Two** declared standards (path registry 46 `artifact_type` vs templates 81
   `document_type`, overlapping on **11**), and **181** non-canonical values over 1,138 files —
   but **108 appear exactly once**, so alias the head and gate the tail.
2. **"Split `verdict` into `gate`."** `gate:` is ALREADY a prism identifier
   (`gate: wave-3-integration-gate`). Field is **`gate_result`**. Same trap hit again with
   **`scope`** (prism already uses PR-LEVEL/LOCAL/spec) — measure a field name before claiming it.
3. **"17 namespace defects."** One boolean stood for THREE defects. Real:
   name_disagreement **2** · path_missing 4 · template_missing 11.
4. **"Betweenness is single-digit ms / fine at 10×."** 236 ms at 2.4k, **52 s at 24k**. Then the
   hypothesis test showed it is the **WORST** predictor (AUC 0.725) vs free **degree** (0.871).
   Measuring the alternative deleted the planned work rather than sizing it.
5. **"`topo.BiconnectedComponents` exists in gonum."** It does not. Articulation points are
   hand-rolled Hopcroft–Tarjan, pinned by 7 hand-worked cases + CSR parity.

### ▶▶▶ TOP PRIORITY NEXT — the session ended cleanly here; NOTHING is in flight

**Session task list: all 8 tasks ✓ COMPLETED. No WIP, no uncommitted work, nothing running.**

**NEXT ACTION, in this order (the F-\* measurement set it):**

1. **STORY 7 — make the indexes derived, via `shadow → proven → retired`.**
   **The highest-value single change: 25.3% ±9.1 of the adversary's findings**, eliminated
   rather than detected. All 23 derived types already ship at `derivation_stage: shadow`.
   Do NOT flip them: generate alongside the authored form, every disagreement a finding, and
   advance only on evidence. Targets by churn: `BC-INDEX` (218 commits), `STORY-INDEX` (381),
   `ARCH-INDEX` (151), `VP-INDEX` (140), `cycles/INDEX` (98), `epic.story_count`.
   Expect the first shadow diffs to be INFORMATIVE, not clean — the corpus asserts four
   different BC totals.
2. **STORY 4 — mint `adversarial-finding` as rows.** A template exists and **nothing uses it**;
   findings are prose tables inside review bodies. This is the enabler for `finding_count`,
   `severity_distribution` and `total_findings` becoming derived.
3. **STORY 12 — prose-reference extraction.** 21.8% ±8.7. Everything it needs is now declared:
   9 `prose_ref_kinds`, 7 `prose_ref_rules`, `pin_policy` on all 23 link types, and CSR to hold
   the section nodes. **Three rules are load-bearing or it manufactures false findings:**
   exclude code spans (`ADR-099` is an example CLI arg), resolve as-of through `id_alias`
   (`BC-1.12.008` was legitimately renumbered to `BC-3.05.004`), and report
   `unresolvable`-owner refs separately from `dangling`.
   ⚠ **This is also the 250k-node driver** — sections + sub-artifact ids is ~100k nodes from
   the existing 6,537 md files. CSR landed first deliberately.

**Smaller, known, not urgent:**
- Store loaders use `s.Strings()`/`s.Pairs()`, which materialise whole result sets — **stream
  them before 250k**.
- `graph dot` is meaningless above a few thousand nodes → make `--scope` mandatory past a bound.
- Precompute+store metrics per commit (`graph_metric(commit,node,measure,score)`) — now much
  less urgent, since the shipped measures are milliseconds.

**⛔ BLOCKED ON USER AUTHORIZATION (all need write access to vsdd-factory / GitHub):**
- The **2 namespace renames** (`story-spec`→`story`, `state`→`pipeline-state`) that close story 1.
  `validate_registry.py` prints **EXIT CRITERION NOT MET: 2** until they land.
- **Opening the ADR** and registering the policy.
- **Answering #671** on the issue. It is an open, unbuilt proposal by another author that the
  chosen direction now contradicts; leaving it silently contradicted is the worse outcome.

### The four settled one-way doors (user, 2026-07-31) — do not relitigate

- **D-A** prose = verbatim `body` bytes **+ a derived ordinal-keyed section partition**, gated
  byte-exact (`concat(sections)==body`, measured 0 mismatches / 6,537 files). Ordinal keys, never
  headings: 110 docs carry 1,968 duplicate `##`+ headings.
- **D-B** store **gitignored**, synced via `refs/dolt/data`; rendered markdown **committed** as
  the review surface AND offline backup ⇒ **NEW INVARIANT 15: `import(render(store)) == store`**, gated.
- **D-C** per-type declared natural key; `path` is a **UNIQUE DERIVED** column, never identity
  (1,852 BC renames, 0 deletes); plus an **`id_alias` ledger** so renumbering keeps history valid.
- **D-D** `verdict` **RETIRED** → `gate_result` / `convergence` / `severity_max`; `status`
  narrowed to **lifecycle only**.

### Operating principles that earned their place THIS session

- **Measure the alternatives to a lever before pulling it.** It deleted sampled+parallel
  Brandes entirely (degree predicts better, for free).
- **Never report a number a test could contradict.** Two benchmarks measured NOTHING and said
  so plausibly: the F-\* extractor found 11 findings from 1 file (v1 knew 1 of 3 formats), and
  `BenchmarkCSRWavesReal` timed an early return (1.1 µs at 240k). Both now pinned by tests.
- **Never collapse exit 1 and exit 2.** Caught twice: a bad `--registry` path, and a bad
  `--as-of` ref that produced an EMPTY graph reported as "+2,421 nodes added".
- **A regex must not cross block boundaries.** A non-greedy match assigned 17 of 17
  `namespace_status` values to the WRONG types while parsing cleanly.
- **Parity, not inspection.** 67/67 rules Go-vs-Python; CSR-vs-gonum on hand-worked answers AND
  generated graphs.

---

## ⭐ CURRENT SNAPSHOT (2026-07-31)

**Active workstream:** research spike — can [Dolt](https://github.com/dolthub/dolt) back a
tool (`datum`) that is the **sole interface to all vsdd-factory artifacts**, replacing the
`factory-artifacts` orphan git branch?

**Status: SPIKE COMPLETE · 3 blocking decisions SETTLED · SCALED to 200 agents · every
decentralised contention fix EXHAUSTED · the cross-internet topology VALIDATED against
GitHub Actions. Verdict GO (phased). 193 of 194 checks, 24 suites**, all re-runnable
against the LIVE vsdd-factory corpus and a REAL GitHub remote. (**Superseded on the
"no product code" point** — phase 1 shipped on 2026-07-31; see the block at the top.) Nothing in vsdd-factory has been changed.

⭐ **THE END STATE IS ONE GO BINARY, `datum`** (user-confirmed 2026-07-31). Everything below
lands as its subcommands — see TOP PRIORITY NEXT item 0.

**Repo state:** `~/Dev/datum`, **local-only git (NO remote — nothing
to push)**, clean. **12 spike passes + the phase-1 build. HEAD = `e4db2ad`**
(`datum/datum`, the 148 MB binary, is gitignored — rebuild it, see the top block).

**Reference repos (both READ-ONLY here; we changed neither):**
| Repo | Where | Pin |
|---|---|---|
| vsdd-factory | `~/Dev/vsdd-factory` (exists, branch `develop`) | `82163b7f` |
| its artifact corpus | `~/Dev/vsdd-factory/.factory` (worktree on `factory-artifacts`) | 3,145 files / 1,959 BCs / 1,607 commits |
| beads (Dolt reference product) | **`/tmp/_bd/b` — EPHEMERAL, re-clone on resume** | pin `b1694a5`; a `--depth=1` clone now lands on `9fddc56` |
| Dolt | `brew install dolt` | 2.2.3 |
| Go — NEW, only for the embedded harness | `brew install go` | 1.26.5 + Xcode clang (CGO) |
| **test remote** | `https://github.com/drbothen/datum (formerly dolt-artifact-spike)-remote` (PRIVATE, ours) | seeded `main`; suites create per-run `refs/dolt/*` and delete them in a `finally`. **Swept clean at wrap** — only `main` + Dolt's `__dolt_remote_info__` remain |
| **the CI aggregator workflow** | DEPLOYED at `.github/workflows/datum-aggregate.yml` in that test remote; source of truth copied to `poc/workflows/datum-aggregate.yml` here | **active, dispatch-only — the cron sweep is COMMENTED OUT** so an idle repo doesn't run forever. Re-enable the cron to test that layer. `/tmp/ciwork` was the scratch clone used to edit it — EPHEMERAL, re-clone if needed |

**ONE-LINE RESUME POINTER:** phase 1 is BUILT — read `datum/README.md` first, then
`research/DECISIONS.md` (the 3 settled calls) → `research/SPEC.md` (14 invariants) →
`research/SCALE.md` + `research/CI-AGGREGATOR.md` (what scale and the cross-internet
topology actually cost). **Nothing is blocking. The next work is DEPLOYING the phase-1
gate into vsdd-factory and ratcheting its baseline down.**

---

## ▶▶▶ TOP PRIORITY NEXT

### The three blocking decisions are SETTLED — `research/DECISIONS.md`

1. **Conflict-resolution policy — DESIGNED (D1).** `datum` never auto-resolves. Abort
   mechanically on any conflict (invariant 2), record it in an append-only `conflict`
   table, and the **loser of the push race re-applies its intent as a validated write**
   (`--reapply | --take-theirs | --take-mine`); cross-actor collisions escalate to the
   orchestrator; and **a conflict inside a leased scope is reported as a lease-scoping
   defect**, because that is what it is. Only mutable record cells can conflict at all —
   derived data and append-only tables structurally cannot.
2. **Zone granularity — per-DIRECTORY, ratified (D2).** Tier 1 remains the only
   enforceable option, and two new measurements strengthen it: a zone opens in ~25 ms
   in-process and one process can hold both handles (so the ~144 ms per-zone cost
   objection is gone), and an embedded `datum` needs no `dolt` binary (so "deny `Bash`,
   allow only `datum`" becomes practical). **New required deliverable:** a cross-zone
   integrity pass in `datum validate`, since splitting zones removes that FK (A6).
3. **Phase 1 — SIGNED OFF (D3).** Read-only shadow: `import` + `validate` in CI, markdown
   stays truth, **plus a dated baseline allowlist of the 82 existing findings** — without
   it the gate blocks every PR on day one and gets switched off. Python + `dolt sql -f` in
   ONE transaction; the corpus import lands at **0.9 s**. No Go, no remote, no daemon,
   zero blast radius.

### Then, in order

0. ⭐ **THE END STATE IS ONE GO BINARY, `datum`.** Everything lands as its subcommands.
   Settled consequences: the embedded `dolthub/driver/v2` is **THE** access path (so
   **no `dolt` CLI dependency anywhere, including CI**); `datum aggregate` is the
   aggregator, which makes the Actions-outage fallback "any dev runs the same binary";
   and **DECISIONS D3's "phase 1 = Python, no Go" is SUPERSEDED** (phase-1 SCOPE is
   unchanged — only language + access path). Build costs are fixed and non-negotiable:
   CGO, **`-tags gms_pure_go` MANDATORY** (else the build dies on ICU headers), 155
   indirect deps, ~147 MB binary, its own pinned Dolt build separate from the CLI's.

4. **BUILD PHASE 1.** Nothing blocks it now. Deliverables: `datum import`; `datum validate` with
   the gates as SQL (W8); the dated baseline of 38 dangling refs + 44 type violations; a
   CI job that fails on *new* violations only; and D2's cross-zone check.
   **Exit criterion into phase 2:** baseline at zero (or each item explicitly waived)
   **and** the gate has caught ≥1 real regression in a real PR.
   ⚠ **Two features that measurement made mandatory, do not drop them:**
   (a) **`datum aggregate` must QUARANTINE a stuck staging ref** — attempt count + backoff,
   or move it to `refs/dolt/quarantine/*`. A conflicted ref is re-fetched and re-merged
   on EVERY run today (measured 17 s then 8 s of pure waste with nothing new to do);
   at 20 stuck refs it dominates the job and the backlog only grows. Retention is
   right; unbounded RE-ATTEMPT is not. (b) **`datum doctor` must check WRITABILITY, not
   openability** — a second opener of a Dolt directory silently becomes read-only.
5. **Extract prose-embedded references.** The graph was built from frontmatter only; BC/VP
   bodies also cite ADRs and BCs in prose, so the **38 dangling refs are a floor**.
6. **Re-verify the identity findings on Linux.** macOS `ps eww` leaks a sibling's env;
   Linux gates `/proc/<pid>/environ` behind `PTRACE_MODE_READ_FSCREDS` (safer). Depends on
   deployment `ptrace_scope`/`hidepid`/dumpable, so it must be run, not reasoned about.
   Low priority — tier 1 does not depend on the answer.
7. ~~**Instance-count ceiling above 12**~~ — **MEASURED at 200 agents / 20 clones
   (`research/SCALE.md`).** Correctness holds absolutely (S6: 247/247 rows, 0 missing,
   0 dupes, 0 dangling FKs after 200 concurrent writers + 9 merges). Contention is
   per-BRANCH, and because the artifact store is ONE branch it is global for artifacts —
   but it is **solved decentrally by AGGREGATION** (new invariant 13): a local `file://`
   relay + `flock` collapses a host's instances to 1 push (17 s); staging refs +
   an aggregator collapse hosts to 1 (64 s); peer `--remotesapi-port` pull does it in
   25 s at the cost of a listener per writer. Backoff tuning makes contention WORSE
   (159 -> 185 -> 193 attempts). **No central server is needed for contention.**
8. ⭐ **THE END STATE IS A SINGLE GO BINARY, `datum`** (user-confirmed 2026-07-31). Everything
   above lands as ITS subcommands. Consequences: the embedded `dolthub/driver/v2` path is
   now the access path (not a phase-3 option), so there is **no `dolt` CLI dependency
   anywhere — including CI**; `datum aggregate` is the aggregator, which makes the
   Actions-outage fallback "any dev runs the same binary" rather than a parallel script;
   and **DECISIONS D3's "phase 1 = Python + dolt sql -f, no Go" is SUPERSEDED** and needs
   rewriting. Build costs are fixed: CGO, `-tags gms_pure_go` mandatory, 155 indirect
   deps, ~147 MB, its own pinned Dolt build.
9. Multi-repo mode (`.factory-project/`) is declared out of scope — revisit if needed.
10. **Offered and NOT chosen:** a DoltLite-from-Rust spike. DoltLite is a shipped C library
    (SQLite fork, prolly tree, `dolt_*` functions and `dolt_log`/`dolt_diff_*` virtual
    tables, v0.11.38, bindings for Python/Ruby/Node/WASM/Swift/Android but **not Rust**),
    so Rust *can* embed it via `rusqlite` — but it is a **different engine and on-disk
    format** whose remotes are `.doltlite` files or an HTTP `doltlite-remotesrv`, not the
    project's git remote. That makes it an architecture decision, not a language one.
    Dolt itself has **no C API and no Rust bindings**
    ([dolt#8953](https://github.com/dolthub/dolt/issues/8953) is open), so the embedded
    measurement can only be made from Go.

### Session task list (ephemeral tracker — mirrored here)

**No task-tracker entries were used this session; the narrative below IS the record.**
Passes 10 → 12b were all completed in one session (2026-07-31). Nothing is in progress,
no WIP, no uncommitted work, and no background jobs were left running.

Pass 12 / 12b (CI aggregator) **✓ complete**: built + deployed the `datum-aggregate`
workflow to the test remote · proved `GITHUB_TOKEN` can create/update/DELETE
`refs/dolt/*` · proved `repository_dispatch` reaches it and `on: push` never would ·
`concurrency:` = the merge slot for free · conflicting writer isolated with its ref
retained · **strand defence held against a REAL cancelled pending run** · stressed at
20 writers × 10 agents (publish FLAT in N) · **measured end-to-end latency: median
30 s** · found the ONE required fix (quarantine stuck refs) · new invariant 14 ·
`research/CI-AGGREGATOR.md`.

Pass 11 (scale + contention) **✓ complete**: 200-agent fleet on the real remote (5/6, S6
proves ZERO lost writes) · found contention is per-BRANCH · **exhausted every
decentralised contention fix** (D1-D5, O1-O3) · aggregation collapses 20 writers to 1
push · backoff measured HARMFUL · `research/SCALE.md` + invariant 13.
**Still open: nothing blocking. A central-instance comparison is the next optional step,
and it is now an argument about READ latency and intra-host concurrency ONLY — contention
no longer motivates it.**

Pass 10 tasks all **✓ complete**: benchmark the embedded driver (13/13) · add the missing
`BEGIN`/`COMMIT` control that overturned the pass-9 headline · settle the three decisions ·
real-GitHub-remote MECHANICS suite (10/10) · **port every `file://` scenario onto the real
remote (11/11) — merge semantics, the wedge, the 2×4-agent topology, the 8-agent lease,
counters, staleness, instance graduate/abandon, schema merge, 8-clone contention** ·
answer the Rust/DoltLite question · update SPEC / GAP-MATRIX / ASSESSMENT / LESSONS.
**Nothing in progress. No WIP.**

### Operating principles that must carry over

- **Measure, don't assume.** This spike corrected its own claims **eight** times (see LOG).
- **Never infer a consequence from a structural fact.** Three of this session's errors
  were exactly that: 'one git ref ⇒ global contention' (wrong, it is per-branch),
  'slow pushes ⇒ commit churn' (wrong, push cost is flat in payload), and 'ticket
  ordering ≈ a queue' (wrong, it was the WORST arm). Measure the consequence too.
- **Before recommending a lever, measure the alternatives to that lever.** Pass 9 called
  the embedded driver "the single biggest engineering lever" from a spawn-vs-query ratio.
  Pass 10 measured the thing neither side had tested — the transaction boundary — and the
  headline moved to a `BEGIN`/`COMMIT` the CLI already supports.
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
  13.4 s batched — **and then 0.9 s if that batch is wrapped in one transaction** (pass 10).
- **Claude Code runs ALL agents in ONE OS process** ⇒ no per-agent uid and no fd-passing,
  so access control must be the CLI permission layer (`permissions.deny` + `PreToolUse`
  hooks + per-agent `allowed-tools`), and a walled agent must NOT have unrestricted Bash.

**What pass 10 added (`research/ACCESS-PATH.md`, `research/REMOTE.md`):**
- **The real lever was a transaction, not the access path.** `dolt sql -f` autocommits per
  *statement*; wrapping the same file in `BEGIN`/`COMMIT` is 17–23× (15.7–18.5 s → 0.8–0.9 s).
  Per-statement autocommit costs the same ~5 ms in BOTH the CLI and the embedded driver.
- **Embedded driver, honestly:** ~2× on cold start (70 ms vs 136 ms — the engine opens
  either way), ~4,000× warm on a held handle (0.03 ms vs 132 ms per question), real
  cross-statement transactions, and **no `dolt` binary needed at all** (branch/merge/gc/
  `DOLT_PUSH` all work in-process). Costs: Go + **CGO**, `-tags gms_pure_go` mandatory
  (else the build dies on ICU headers), 155 indirect deps, 147 MB binary, and its own
  pinned Dolt build separate from the CLI's.
- **It does NOT remove the mutex.** A second opener of the same directory silently becomes
  **read-only** and fails later with `cannot update manifest: database is read only` — so
  `doctor` must check *writability*, and `datum` embedded + `dolt sql` cannot share a directory.
- **Real remote (github.com):** an acquire is **~10 s**, not 640 ms; an acquire+release
  pair ~20 s ⇒ push-as-CAS is a phase-gate mechanism only. **Payload size is irrelevant** —
  a 2-row database and the 33 MB corpus both push in ~10 s, and the corpus clones back in
  **2.2 s** (onboarding/DR is cheap).
- **New invariant 12:** all Dolt branches live in ONE git ref, so push contention is
  **global across instances**; `--ref` per instance decouples it but forfeits remote-side
  cross-instance merge.
- **No Rust path to embedded Dolt.** Dolt has no C API and no Rust bindings; only DoltLite
  (a separate C engine) is embeddable from Rust.

---

## Background / environment state at wrap

### ⭐ THIS WRAP (2026-07-31, `b96a668`) — environment facts

- **Nothing is running.** No `dolt sql-server`, no background builds, no agents. Verified.
- **No WIP.** Working tree clean at `b96a668`; the session task tracker is empty.
- **This repo has NO git remote** — local-only, so there is nothing to push, ever.
- **`~/Dev/vsdd-factory` and the 9 sibling corpora were READ-ONLY all session.** vsdd's
  `git status` shows 2 modified files + 1 untracked, all dating from **2026-05-30 and
  2026-07-23** — pre-existing, NOT from this session (verified by mtime).
- **Rebuild `datum/datum`** — the 148 MB binary is gitignored (39.5 s cold build).
- **Disposable `/tmp` ephemera from this session, all safe to delete / recreate:**
  `/tmp/fadb` + `/tmp/fadb_final` (datum stores built from the live corpus), `/tmp/fahist`
  (a 2-commit store used for the diff experiment — carries a FULLTEXT index added by
  hand), `/tmp/corpus_v2` + `/tmp/corpus_regress` (COPIES of the corpus used to plant
  regressions — the live corpus was never touched), `/tmp/_bd/b` (the beads clone at
  `35ccd0d`; re-clone with `gh repo clone gastownhall/beads /tmp/_bd/b -- --depth=1`.
  ⚠ the handoff's `b1694a5` pin is NOT reachable in a `--depth=1` clone).
- **Every finding is folded into the research docs** — no log file needs to survive.

### Earlier passes (still accurate)

- **No `dolt sql-server` is running at this wrap.** The 7 server-dependent suites
  (`test_spike`, `test_graph`, `test_write_api`, `test_render`, `test_factory_ops`, …) need
  one started per the kick-start prompt; the other 12 self-provision. `test_embedded.py`
  starts and stops its own server on port 3399.
- `poc/*/` Dolt data dirs are **gitignored and disposable** — every suite recreates what it
  needs. Pass 10 added `poc/eb/` (~150 MB) and `poc/gh/` (~40 MB) plus the 147 MB
  `poc/bench/bench` binary; **all three are gitignored** (the `.go`/`go.mod`/`go.sum`
  sources are tracked). Tracked tree stays source + docs only.
- **Go was installed this session** (`brew install go`, 1.26.5) purely to build the embedded
  harness. Reversible with `brew uninstall go`. Nothing else depends on it.
- **A GitHub repo was created:** `drbothen/datum (formerly dolt-artifact-spike)-remote` (**private**), seeded
  with one commit on `main`. It holds `refs/heads/__dolt_remote_info__` (Dolt's own
  bookkeeping branch) permanently; per-run `refs/dolt/run-*` refs are deleted by the suite
  itself in a `finally` block. Auth is the `gh` git credential helper — **no token is
  written to disk or into any URL, and none is in the repo.**
- **No background agents or long-running jobs pending at this wrap** (verified: no
  `test_*` processes alive). Several long suites ran in the background during the
  session; their logs were in `/tmp/*.log` and are EPHEMERAL — every finding has been
  folded into the research docs, so the logs are not needed.
- **Disposable, gitignored, must be rebuilt on resume:** `poc/bench/bench` (141 MB Go
  binary — rebuild per the kick-start), and the Dolt data dirs `poc/eb` 197 MB,
  `poc/st` 201 MB, `poc/gh` 47 MB, `poc/opt` 16 MB, `poc/gt` 14 MB, `poc/dc` 4 MB,
  `poc/ci` 1 MB (~480 MB total). Every suite recreates what it needs.
- **`/tmp` ephemera that will NOT survive:** `/tmp/_bd/b` (the beads clone — re-clone
  per the kick-start) and `/tmp/ciwork` (the scratch clone of the test remote used to
  edit the CI workflow; the workflow's source of truth is committed here at
  `poc/workflows/datum-aggregate.yml` and is already DEPLOYED to the test remote).

---

## LOG

| Date | Commit | What |
|---|---|---|
| 2026-07-31 | `6341ab2` | **CSR ENGINE for 250k+ nodes.** Two int32 arrays + keys interned in ONE byte slab, ids in SORTED key order so `Lookup` is a binary search and NO `map[string]int32` is retained (~80 MB at 1M nodes saved). **MEASURED 96× less memory** (240k nodes: gonum 756.5 MB → CSR **7.9 MB**; live corpus **0.1 MB**; ~33 MB vs ~3.1 GB at 1M) **and ~100× faster** (articulation 240k: 980 ms → **8.1 ms**; SCC 240k 4.6 ms; waves 240k 710 → 121 ms). Parallel edges preserved. **NO Brandes ported** — betweenness was measured off the critical path. gonum retained for Louvain only. **Correctness by PARITY**: 7 hand-worked articulation cases + generated graphs at 50/500/2400 (node/edge counts, per-node degree, articulation set, SCC count), waves layering, dangling, parallel-edge survival. **A benchmark that measured NOTHING, caught:** waves reported 1.1 µs at 240k because `synthProjection` makes no `story` nodes, so `Waves()` returned immediately — now pinned by `TestSynthStoriesActuallyProducesWaves`. `datum graph build` + `datum waves` run on CSR. 62 tests, 9 benchmarks |
| 2026-07-31 | `c4d59d0` | **CENTRALITY HYPOTHESIS TESTED — AND BETWEENNESS LOST.** Betweenness existed for the claim that propagation misses cluster on high-betweenness nodes. Measured against 2,138 extracted findings, AUC = P(flagged outranks unflagged), 231 flagged vs 2,190 unflagged: **degree 0.871 (O(E), FREE) · pagerank 0.843 (16 ms@24k) · betweenness 0.725 (~52 s@24k)**. The cheapest measure predicts BEST and betweenness is ~3,000× the cost. ⇒ sampled Brandes, parallel Brandes and Brandes-over-CSR all came **OFF the critical path**; `degree` promoted into default metrics; CSR's scope shrank to memory. New `datum graph centrality` (CSV) + `Degrees()`. **Caveat recorded:** the proxy is "id mentioned in a finding" and well-connected artifacts get discussed more, so degree's edge is partly tautological — that weakens "centrality predicts risk" but NOT "betweenness isn't worth 52 s" |
| 2026-07-31 | `8713636` | **KNOWLEDGE-GRAPH PROJECTION** over gonum (pure Go — no CGO fight) + `datum waves` and `datum graph build|metrics|dot|diff`. Node identity from the REGISTRY's declared key; `multi.DirectedGraph` NOT `simple` (simple permits one edge per (u,v) and would have silently collapsed story→BC via behavioral_contracts AND traces_to); dangling = an edge whose head is undeclared. Live: 2,421 nodes/4,060 edges, 148 stories in 16 waves, 0 SCCs>1, 50 articulation points, 11 Louvain communities. **TWO OF MY THREE SPEED CLAIMS REFUTED:** betweenness is 236 ms at 2.4k (not "single-digit ms") and **52.2 s at 24k** (not "probably fine at 10×") ⇒ opt-in + bounded, REFUSED not silently skipped. **REAL BUG FOUND BY BENCHMARKING:** gonum's dense `PageRank` allocates 47 MB/call on a sparse graph; `PageRankSparse` is **197× faster, 43× less memory** ⇒ default `graph metrics` 577 ms → 73 ms. **`topo.BiconnectedComponents` DOES NOT EXIST** — articulation points hand-rolled Hopcroft–Tarjan, iterative, 7 hand-worked tests. **Third silent failure caught:** a bad `--as-of` ref produced an EMPTY projection reported as "+2,421 nodes added", exit 0 → now a ref probe, exit 2. `research/GRAPH-PERF.md` |
| 2026-07-31 | `6cc25cc` | **ALL FOUR THINGS TAKEN FROM #671**, each machine-checked (validator 1j–1m + 3 Go tests). (1) **`generate → prove equal → retire`** — new `derivation_stage` on all **23** derived types, all at `shadow`; story 7 was a one-way flip on BC-INDEX/STORY-INDEX and is now a ratchet. (2) **WRITE-TIME enforcement** — new `enforcement_point`, and `block` enforced only in CI is now a rejected CONTRADICTION. (3) **VERSION-PINNED citations** — new `pin_policy` on all 23 link types + `index_cite` (floating ⇒ lag IS a finding) and `reviewed_version` (pinned ⇒ lag is CORRECT); same syntax, opposite verdicts, which is why it had to land BEFORE prose extraction. (4) **`impact`** the reverse closure + a `query_verbs` catalogue with a declared growth path. NOT taken (with reasons): the Rust crate/no-DB architecture, in-memory petgraph, "not git-diffable". Already held stronger: #671's cannot-be-stale virtue IS invariant 15. **Defect caught:** `link_types` held a rules LIST beside entry MAPS → untypeable in Go, a test discarded the error, and a parse failure surfaced as a nil deref. Hoisted to `link_rules` |
| 2026-07-31 | `e62665b` | **NAMESPACE RECONCILIATION (story 1) — the disagreement is 2, not 17.** One boolean stood for THREE unrelated defects: `name_disagreement` **2** (`story`/`story-spec`, `pipeline-state`/`state`) · `path_missing` 4 · `template_missing` 11. Only the first two are namespace defects. **A full file merge would be WRONG** — the path registry is deliberately COARSER (`cycle-document` serves 8+ types), so requiring a unique path per type would force 8 invented subdirectories ⇒ `shared_path_patterns`, and story 1 shrinks to TWO renames. `namespace_reconciliation` declares resolution_rule (the `document_type` name WINS) + all 4 categories + the 4 path-registry-only entries + a validator-CHECKED exit criterion. **Second self-caught defect:** a non-greedy regex matched flag lines belonging to LATER type blocks and mis-assigned 17 of 17 values while parsing cleanly — caught by PRINTING the groups, fixed with block-scoped editing |
| 2026-07-31 | `d58b77c` | **`datum validate --registry` — ONE GATE, NOT TWO.** `datum/registry/*.yaml` is the ONE canonical copy: `go:embed`'d into the binary AND read by the Python tooling. **67/67 rules agree EXACTLY** with the Python validator on vsdd-factory (6,711 registry findings each). Getting there fixed THREE defects: (1) **three states not two** — `blocks: []` is a DECLARATION of none vs an absent key; Go called empty lists missing, Python called BLOCK-STYLE lists missing (it never parsed `key:\n  - item`); (2) **inline YAML comments** — `verification_properties: []  # ...` read as non-empty, found by a parity diff off by EXACTLY ONE FILE; (3) **exit 1 vs 2 collapse** — a bad `--registry` path validated ZERO files while exiting non-zero from the store gates. Ratchet proven end-to-end (baselined → 0, planted invented type → 1 naming it, `--strict` → 1, bad path → 2). `baseline write --registry` was ALSO required or every registry finding reads as new next run. Tests 24 → 43 |
| 2026-07-31 | `30f7057` | **#671's EXIT CRITERION RUN AT LAST.** Hand-classified random sample (n=100 of 1,894 cleaned findings, seed 2026; 87 real after 13 turned out to be closure rows): **registry+datum already address 40.2% ±10.3** (derived-data 25.3% + frontmatter 14.9%) · **prose extraction 21.8% ±8.7** · **beyond ANY parser 37.9% ±10.2** (external 13.8 + process 12.6 + semantic 11.5). ⇒ #671 is PARTLY RIGHT: registry GAINS `prose_ref_kinds` (9 kinds) + 5 rules, an ADDITION not a redesign; and **story 7 goes BEFORE story 12** since derived-data elimination is worth more AND eliminates rather than detects. The 37.9% belongs in the ADR: nothing here replaces adversarial review. **4th parser-lost-input caught:** v1 of the extractor knew 1 of 3 finding formats and ran on 8 docs/cycle → **11 findings, all from ONE file**, 0.3% of the data. v2 covers all three forms over 390 docs. Keyword rules classified only 33%, so the headline is HAND-classified and committed for audit. `research/FSTAR-COMPARISON.md` |
| 2026-07-31 | `902da9d` | **THE TYPE REGISTRY BUILT** (the session's headline deliverable). 103 canonical types + 16 gap types + 4 retired, each declaring key · required fields · enums · link types · section schema · shape · authority · gate severity · enforcement_level · profile; 14 closed vocabularies; 180 aliases carrying `set:` FIELD DEFAULTS (a rename-only map would destroy the scope/reviewer_role the 12 adversarial-review spellings encoded); a change-management package (ADR + policy + stories + graduation ladder + 7 hazards); a validator that exits 0. **FIVE FINDINGS:** two declared standards overlapping on 11 · enforcement gap by MASS but design gap by VOCABULARY (181 values/1,138 files; 22/71, 32/150, 27/51 distinct) · the tail is 108 SINGLETONS · the 12 review spellings encode real dimensions · **`delta-archive` (211 rivetry files, created by rivetry's own POLICY-22) and `input-hash` (3,890 files, admits "spurious DRIFT") exist ONLY because there is no versioned store ⇒ RETIRED**. **SEVEN defects the validator caught in my own registry**, incl. `bc_id`/`vp_id` required → 2,577 FALSE findings (ids live only in filenames) and `priority` bound to `severity_max` → 391 false findings on legitimate `P1` |
| 2026-07-31 | `b96a668` | **CROSS-CORPUS: ten `.factory` corpora compared** — prompted by "look at prism". **THE DRIFT IS METHOD-GENERATED:** vsdd-factory vs prism, same factory, `document_type` 6 spellings each with only **2 of 12 shared**, `verdict` with **ZERO** shared values. **The spine is SMALL** (`cycles` 10/10, `specs` 10/10, `logs` 9/10, `planning` 8/10, `code-delivery`+`stories` 7/10; `BC-S.SS.NNN` 11/12 but `S-N.NN` only 2/12). **28 singleton dirs track PRODUCT TYPE** (rivetry UI/SaaS: `design-system`/`ui-evidence`/`brand`/`ux`; prism security: `test-strategy`/`security-review`). **vsdd-factory is an OUTLIER** — 1,961 BCs = 7.2× the next, its `holdout-evaluations/` uniquely named AND empty vs `holdout-scenarios/` in 7, prism's flat-with-slug BC names are vsdd's own identity violation, and 151 prism files sit in 4 `specs/` dirs the path registry never declares. **METHOD CORRECTION: corverax is NOT the biggest corpus** — 9,274 of 9,291 files are `semport/` scratch and its BC dir holds ONE file; counting files ≠ counting artifacts. `research/CROSS-CORPUS.md` |
| 2026-07-31 | `3ce3aa1` | **PROBE `cycles/` + harvest beads.** **GAP-MATRIX §2.7 OVERTURNED** (banner added): 481/611 prose files carry frontmatter with keys, links AND counts. The class is **three shapes** — ~568 write-once immutable docs, nine append-only ledgers (`burst-log`/`decision-log`/`lessons`, 600+ append commits) that a ROW model strictly improves, and a DERIVED `INDEX.md`. **The worst case is the easiest to model.** Real blockers are general: composite keys (18 basenames collide, ALL with different content), **as-of resolution** (`BC-1.12.008` was legitimately renumbered; `ADR-099` is an example CLI arg — a flat check manufactures false findings), section-scoped semantics. **Dolt does FULLTEXT** (0.15 s / 1,959 bodies) ⇒ no new query language. NOT established: `finding_count` drift (all 6 comparable docs agree; 5 first-run 'mismatches' were dict-vs-Counter artefacts, caught pre-publish). `research/PROBE-CYCLES.md` + `research/BEADS-PROSE.md` (beads stores prose in 4 typed columns, has NO document table, NO markdown rendering, gitignores the DB, and decays prose LOSSILY — unusable for an authoritative corpus) |
| 2026-07-31 | `e4db2ad` | **PHASE 1 BUILT — first product code.** `datum` as a Go binary (`datum/`, embedded `dolthub/driver/v2`, CGO + `-tags gms_pure_go`, 148 MB, 39.5 s cold build): `import` (live corpus in **1.1-1.4 s**, ONE transaction, idempotent, FK rejections recorded as findings) · `validate` (**0.15 s**, every gate a query: W8's gates + a count-assertion gate + index enumeration + prefix agreement + scalar refs + dependency direction + **D2's mandatory cross-zone pass**, ids and counts only) · a **dated 153-finding baseline** that ratchets · `doctor` probing **WRITABILITY not openability** (verified against a real read-only second opener: `cannot update manifest: database is read only`, while the schema check passed on the same store) · the **`datum aggregate` quarantine policy** as pure tested code (bounded attempts, run-counted backoff, move to `refs/dolt/quarantine/*`, and an unmergeable lineage quarantined on the FIRST failure per invariant 14) · a CI workflow that fails on NEW findings only · 24 tests in 3.3 s with no network and no `dolt` binary. **PARITY PROVEN** against the Python prototype: identical records + universes, the 82 import-path findings match RULE FOR RULE, edge sets diffed row by row. **Gate proven to FAIL**: a dangling ref planted in a COPY of the corpus → exactly 1 new finding, exit 1; live corpus → exit 0. **CORRECTIONS #9-10:** the corpus graph has **1,509 edges, not 1,490** (the prototype's parser treated a prose value with an unbalanced `[` as an unterminated inline list, swallowing every key after `BC-INDEX`'s `last_amended` — hiding `total_bcs: 1955` from the count gate and 19 real edges across six S-15.x stories; THIRD instance of the parser-loses-input class, now pinned by a regression test), and **"1962 distinct BC ids" depends on its extraction rule** (first column of the enumeration table = 1,959, which agrees with disk). `datum/README.md` |
| 2026-07-30 | `e2620e0` | Pass 1: assessment + POC store; 13/13. Found the 4-way count drift, 3 dangling refs, the lock TOCTOU |
| 2026-07-30 | `f6762d1` | Pass 2: full relationship graph (1,490 edges) + multi-machine; 27/27. **Fixed 2 of my own bugs that faked clean results** (frontmatter parser dropped all list edges; `INSERT IGNORE` suppressed FK violations) |
| 2026-07-30 | `5002d16` | Pass 3: locking + **CORRECTION** — pass-1's "16 acquirers, one wins" was right by accident (`fence+1` is the documented anti-pattern) |
| 2026-07-30 | `76af355` | Pass 4: no central server needed — push-as-CAS; 38/38 |
| 2026-07-30 | `3415c1f` | Pass 5: single clone + `flock` mutex is the recommended topology; 46/46 |
| 2026-07-30 | `39c91b5`, `ac48116` | Pass 6: two devs × 4 agents × 1 repo; 55/55. Four disciplines the topology imposes |
| 2026-07-30 | `2da29cd` | Pass 7: `research/SPEC.md` + write-API / render / schema / lifecycle; 87/87 |
| 2026-07-30 | `11f0da3`, `b723569` | Pass 8: `research/GAP-MATRIX.md` vs all 46 registry artifact types; asymmetry + factory-ops + multi-instance; 112/112 |
| 2026-07-30 | `7f36c27`, `001f166` | Pass 9: scale + zones + identity; `research/ACCESS-CONTROL.md`; 137/137. **Corrected my prediction that macOS hides process envs — it does not** |
| 2026-07-31 | `700a776`, `7379abf` | Pass 12: **CI AS THE AGGREGATOR = the cross-internet answer, 4/4.** Only staging-refs survives dispersed writers (a relay needs a shared FS; peer-pull needs INBOUND TCP to laptops behind NAT). `GITHUB_TOKEN` can create/update/DELETE `refs/dolt/*`; `repository_dispatch` reaches the workflow and `on: push` never fires for `refs/dolt/*`; **`concurrency:` IS the merge slot for free**, retiring the lock-ref and its TTL/break-glass/unique-sha costs. Conflicting writer ISOLATED with its ref retained; **strand defence held against a REAL `cancelled` pending run**. **NEW INVARIANT 14:** writers must be CLONES of the artifact branch — unrelated lineages fail `no common ancestor` and can NEVER be merged, so per-instance-ref fragmentation is a ONE-WAY DOOR. Six CI gotchas incl. a LIVELOCK I caused by swallowing a failed `git push` rc. `research/CI-AGGREGATOR.md` |
| 2026-07-31 | `acad904` | Pass 12b: **stressed the aggregator at 20 writers × 10 agents (5/5)** — publish FLAT in N (14 s vs 13 s at N=4), 190/190 rows landed. **Found the one real flaw:** a conflicted staging ref is re-fetched and re-merged on EVERY run (17 s then 8 s wasted with nothing to do) ⇒ `datum aggregate` MUST quarantine. **Measured END-TO-END LATENCY: median 30 s** (27/44/30), ~22 s irreducible because the ~8 s push cost is paid TWICE. **Corrected two of my own estimates** — "~1-2 min, runner-startup-dominated" (really ~30 s, startup negligible) and "the Go binary saves 20-30 s of dolt install" (it saves 2 s) |
| 2026-07-31 | `cad9144` | Pass 11: SCALE + CONTENTION. 200 agents / 20 clones / real remote: **S6 = 247/247 rows, 0 missing, 0 dupes, 0 dangling FKs** after 200 concurrent writers + 9 merges. **CORRECTIONS #6-8:** contention is per-BRANCH not per-ref (so `--ref`-per-instance is inapplicable to a single-branch store); slow pushes were CONCURRENCY not churn (a push costs the same for 1 commit as 50); and backoff/ticket ordering make contention WORSE (159 → 185 → 193 attempts), not better. **Exhausted the decentralised option space** — aggregation (`file://` relay + flock per host, 17 s; staging refs + aggregator, 64 s; peer remotesapi pull, 25 s) collapses 20 writers to ONE push, so **no central server is needed for contention**. New invariant 13; `research/SCALE.md` |
| 2026-07-31 | `71ca16a`, `dd5fec0` | Pass 10: embedded-driver benchmark (13/13) + **real GitHub remote: 10/10 mechanics AND 11/11 ported `file://` scenarios** + the three decisions settled (`research/DECISIONS.md`, `ACCESS-PATH.md`, `REMOTE.md`); 171/171. **CORRECTION #5 — pass 9's "the embedded driver is the single biggest engineering lever" was wrong: the lever is a missing `BEGIN`/`COMMIT`, worth 17–23× and available from the CLI.** Also: invariant 6 restated, new invariant 12 (one git ref per remote ⇒ global push contention), and the embedded path does NOT remove the write mutex |

---

## KICK-START PROMPT (paste this cold)

```
Resume the datum (formerly dolt-artifact-spike) in ~/Dev/datum (local-only git, NO remote,
clean at d564f36; the work itself is 902da9d..6341ab2).

READ FIRST — ONLY THESE FOUR:
  1. HANDOFF.md TOP BLOCK              (7 commits, the 4 settled doors, 5 self-corrections)
  2. registry/README.md                (the standard: what it declares + what running it says)
  3. research/FSTAR-COMPARISON.md      (#671's exit criterion RUN: 40% / 22% / 38% split —
                                        this is what ORDERS the remaining stories)
  4. research/GRAPH-PERF.md            (the graph engine, every number measured, incl. the
                                        two speed claims it refuted and the CSR tables)

  Then as needed: registry/CHANGE-MANAGEMENT.md (ADR + policy + 16 stories + hazards) ·
  research/STANDARDIZATION.md · CROSS-CORPUS.md · PROBE-CYCLES.md · SPEC.md · DECISIONS.md ·
  LESSONS.md · BEADS-PROSE.md · GAP-MATRIX.md · datum/README.md

REBUILD AND RE-VERIFY (the 148 MB binary is gitignored):
  cd datum && CGO_ENABLED=1 go build -tags gms_pure_go -o datum .   # BOTH flags mandatory
  CGO_ENABLED=1 go test -tags gms_pure_go ./...               # 62 tests, ~3.5s
  cd .. && python3 registry/validate_registry.py              # exit 0; prints the 3-way
                                                              # namespace split + all checks
  ./datum/datum init --db /tmp/fadb && ./datum/datum import --db /tmp/fadb ~/Dev/vsdd-factory/.factory
  ./datum/datum validate --db /tmp/fadb --registry ~/Dev/vsdd-factory/.factory   # 6,864 findings
  ./datum/datum graph build --db /tmp/fadb      # CSR: 2,421 nodes / 4,060 edges / 0.1 MB
  ./datum/datum waves --db /tmp/fadb            # 148 stories, 16 waves, 0 cycles

REFERENCE CORPORA — LOCAL and READ-ONLY. DO NOT WRITE until the standard is agreed:
  ~/Dev/vsdd-factory/.factory   (pin 0aaba144)   ~/Dev/prism/.factory   (95b90d003)
  ~/Dev/rivetry/.factory        (2aea395)
  ~/Dev/vsdd-factory/plugins/vsdd-factory/templates/            # the 81 document_types
  ~/Dev/vsdd-factory/plugins/vsdd-factory/config/artifact-path-registry.yaml   # the OTHER 46
  gh issue view 671 -R drbothen/vsdd-factory                    # unanswered; see below
  ⚠ prism is ACTIVELY WORKED BY ANOTHER SESSION (its corpus advanced 20 files at 09:34-19:18
    and 24 more at ~23:42-23:46 on 2026-07-31, NONE of it from this work). Every number here
    was measured at the pins above, so RE-RUN measure_types.py + observe.py before trusting
    any prism count. vsdd-factory and rivetry were static throughout.

TASK — in this order, because the F-* measurement set it:
  1. STORY 7: make the indexes DERIVED via shadow -> prove equal -> retire. Worth 25.3% +/-9.1
     of the adversary's findings, ELIMINATED not detected. All 23 derived types already sit at
     derivation_stage: shadow. DO NOT FLIP THEM — generate alongside, every disagreement a
     finding, advance only on evidence. Expect the first diffs to be informative, not clean:
     the corpus asserts FOUR different BC totals.
  2. STORY 4: mint `adversarial-finding` as ROWS. A template exists and NOTHING uses it;
     findings are prose tables inside review bodies. Enabler for finding_count /
     severity_distribution / total_findings becoming derived.
  3. STORY 12: prose-reference extraction, 21.8% +/-8.7. Everything needed is declared
     (9 prose_ref_kinds, 7 prose_ref_rules, pin_policy on all 23 link types, CSR for the
     section nodes). THREE rules are load-bearing or it manufactures false findings: exclude
     code spans, resolve as-of through id_alias, and report unresolvable-owner refs separately
     from dangling. This is ALSO the 250k-node driver (~100k section nodes).

  Known and not urgent: stream the store loaders (Strings/Pairs materialise whole result sets)
  before 250k; make `graph dot --scope` mandatory past a bound; precompute+store metrics per
  commit (now cheap, so low priority).

BLOCKED ON THE USER (all need write access to vsdd-factory / GitHub — ASK, do not assume):
  - the 2 namespace renames (story-spec->story, state->pipeline-state) that close story 1;
    validate_registry.py prints "EXIT CRITERION NOT MET: 2" until they land
  - opening the ADR + registering the policy
  - answering #671 (an open, unbuilt proposal by another author that this direction contradicts)

DO NOT RELITIGATE the four settled one-way doors (D-A prose = body bytes + derived ordinal
section partition, gated byte-exact; D-B gitignored store + committed render + invariant 15
import(render(store))==store; D-C declared natural keys, path is derived and never identity,
plus an id_alias ledger; D-D verdict retired -> gate_result/convergence/severity_max and
status = lifecycle only).

OPERATING PRINCIPLES (each one earned by a real error in this repo):
  - Measure, don't assume. NEVER infer a consequence from a structural fact.
  - MEASURE THE ALTERNATIVES TO A LEVER BEFORE PULLING IT. This deleted sampled+parallel
    Brandes outright: free `degree` predicts adversary findings BETTER (AUC 0.871) than
    betweenness (0.725) at ~1/3000 the cost.
  - Never report a number a test could contradict. TWO benchmarks measured NOTHING and said so
    plausibly this session (an extractor that knew 1 of 3 formats -> 11 findings from 1 file;
    a waves benchmark timing an early return -> 1.1us at 240k nodes). Both now pinned by tests.
  - Never collapse exit 1 (gate failed) and exit 2 (datum failed). Caught twice more this session.
  - Before claiming a field name, MEASURE whether it is already in use with another meaning
    (`gate` and `scope` both were).
  - A regex must not cross block boundaries: one mis-assigned 17 of 17 values while parsing
    cleanly. Print the resulting groups; don't trust the edit.
  - Parity, not inspection: 67/67 rules Go-vs-Python, CSR-vs-gonum on hand-worked answers AND
    generated graphs.
  - When a derived number is off by a little, CHASE it (an off-by-ONE-file diff exposed an
    inline-YAML-comment parsing bug).
  - Counting files is not counting artifacts. State the extraction rule with any count.

STATE: registry BUILT + embedded in datum + validated against 3 corpora (67/67 parity) ·
#671's exit criterion RUN · all four #671 borrowings folded in and machine-checked ·
knowledge-graph projection + CSR engine (96x less memory, ~100x faster) shipped ·
62 tests / 9 benchmarks green · corpora untouched · nothing in flight, no WIP, nothing running.
```
