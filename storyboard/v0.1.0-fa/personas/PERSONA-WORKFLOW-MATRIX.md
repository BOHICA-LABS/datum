> **Type:** Stage 2 step 7a — the COVERAGE CUBE. **This is a VIEW: it links into the canonical
> `WORKFLOW-INVENTORY.md` store and duplicates no content.** Pivoted from the inventory's Persona(s)
> and Coverage columns.
> ⚠ **Honestly typed, per the runbook's own instruction:** the 2-D persona × workflow matrix is a clean
> RTM extension; the explicit 3-D/4-D cube is *the runbook's own synthesis*, flagged there as **"an
> emerging view, not a codified standard."* Treat accordingly.
> ⚠ **Hand-built this pass.** It MUST become generated (WF-035) or it will diverge from the inventory —
> a hand-maintained view drifting from its canonical store is this repo's five-instance defect class.

# Coverage cube — persona × workflow × state

Glyphs per `STORYBOARD-INDEX.md`: `—` n/a · `⬜` not started · `📐` designed · `🔨` built ·
`🔍` gated · `📸` evidenced · `✅` in production. Monotonic; a regression is a real event.

| WF | stage | SYS-CC | SYS-ALT | SYS-CI | HUM-OP |
|---|---|---|---|---|---|
| WF-001 create store | S1 | — | — | 🔨 | 🔨 |
| WF-002 prove writable | S1 | — | — | 🔨 | 🔨 |
| WF-003 registry match | S1 | — | — | 📐 | — |
| WF-004 GC during long work | S1 | 📐 | 📐 | 📐 | — |
| WF-010 import corpus | S2 | 🔨 | 🔨 | 🔨 | — |
| WF-011 per-form counts | S2 | 🔍 | 🔍 | 🔍 | 🔍 |
| WF-012 keep both on collision | S2 | 🔍 | 🔍 | — | 🔍 |
| WF-013 ledger → rows | S2 | 🔍 | 🔍 | — | — |
| WF-014 classify untyped | S2 | ⬜ | ⬜ | — | — |
| WF-015 capture unmodeled | S2 | 📐 | 📐 | — | — |
| WF-016 resolve LOCATION | S2 | ⬜ | ⬜ | ⬜ | ⬜ |
| WF-020 create artifact | S3 | 📐 | 📐 | — | 📐 |
| WF-021 set field | S3 | 📐 | 📐 | — | 📐 |
| WF-022 append to ledger | S3 | 📐 | 📐 | — | — |
| WF-023 set prose | S3 | 📐 | 📐 | — | 📐 |
| WF-024 be refused usefully | S3 | 📐 | 📐 | 📐 | — |
| WF-025 propose a field | S3 | 📐 | 📐 | — | ⬜ |
| WF-026 refuse a conflict | S3 | 📐 | 📐 | 📐 | — |
| WF-027 read-only explore | S3 | 🔨 | 🔨 | — | 🔨 |
| WF-030 render | S4 | — | — | ⬜ | ⬜ |
| WF-031 round-trip proof | S4 | — | — | ⬜ | ⬜ |
| WF-032 shadow indexes | S4 | 🔨 | 🔨 | 🔨 | 🔨 |
| WF-033 counts | S4 | 🔨 | 🔨 | 🔨 | 🔨 |
| WF-034 graph | S4 | 🔨 | 🔨 | — | 🔨 |
| WF-035 coverage cube | S4 | — | — | — | ⬜ |
| WF-040 gates + ratchet | S5 | — | — | 🔨 | 🔨 |
| WF-041 machine evidence | S5 | — | — | 📐 | 📐 |
| WF-042 gate WITH witness | S5 | — | — | 📐 | 📐 |
| WF-043 block on unevaluable | S5 | — | — | 📐 | — |
| WF-044 compute convergence | S5 | — | — | 📐 | 📐 |
| WF-045 record an assertion | S5 | 📐 | 📐 | 📐 | — |
| WF-046 defer w/ owner+expiry | S5 | — | — | — | 📐 |
| WF-050 chunked migrate step | S6 | 📐 | 📐 | 📐 | — |
| WF-051 seven exit gates | S6 | — | — | 📐 | 📐 |
| WF-052 refuse a moved pin | S6 | — | — | 📐 | — |
| WF-053 abandon a cohort | S6 | — | — | — | 📐 |
| WF-054 replay interpretation | S6 | 📐 | 📐 | — | — |
| WF-060 wave schedule | S7 | 🔨 | 🔨 | — | 🔨 |
| WF-061 engine frontier | S7 | 📐 | 📐 | — | — |
| WF-062 cost reporting | S7 | — | — | ⬜ | ⬜ |
| WF-063 dirty worktrees | S7 | — | — | ⬜ | ⬜ |

## Coverage summary, per persona

| persona | WFs it is an actor for | `🔨`+ | `📐` only | `⬜` | evidenced (`📸`) |
|---|---|---|---|---|---|
| **SYS-CC** | 26 | 8 | 15 | 3 | **0** |
| **SYS-ALT** | 26 | 8 | 15 | 3 | **0** |
| **SYS-CI** | 20 | 6 | 11 | 3 | **0** |
| **HUM-OP** | 22 | 8 | 8 | 6 | **0** |

## What the cube makes visible that prose did not

1. ⚠⚠ **The `📸` column is EMPTY for every persona.** Nothing in `fa` has op × exit-code golden-file
   evidence, because L7-H was designed this session and is unbuilt. Per the runbook's own anti-pattern
   naming — *"a frame whose evidence set has only one captured resolution does not pass"* — **every
   workflow currently fails the evidence gate.** That is the honest state, and stating it is the point.
2. ⚠ **WF-016 is `⬜` for ALL FOUR personas** — the only row with no actor anywhere. A workflow every
   persona needs and nobody can perform is F1, seen from the persona axis rather than the code axis.
3. **`🔍` appears only in S2 (WF-011/012/013).** Everything gated is something built *this session*;
   the entire designed surface (S3–S6) has no witness-backed gate yet, which is what L7-G exists to
   force at registration time.
4. **SYS-ALT is identical to SYS-CC in every cell.** That is the desired result — it means no workflow
   assumes Claude Code. **If any cell ever diverges, V-K's portability requirement has been broken**,
   and this column is the cheapest possible detector for it.
5. **HUM-OP carries the most `⬜` (6).** The human-facing surface (render, round-trip proof, cost,
   worktree hygiene, the cube itself, proposal adjudication) is the least built — consistent with `fa`
   having been an agent-facing read-only shadow so far.

**Coverage: 0 of 42 workflows evidenced. 22 of 42 designed-only. Gaps: WF-014, WF-016, WF-030, WF-031,
WF-035, WF-062, WF-063, and WF-025's HUM-OP cell (G-1).**
