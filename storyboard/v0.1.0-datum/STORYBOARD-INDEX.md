> **Type:** storyboard exploration corpus, version `v0.1.0-datum`. **Status:** first pass, Stages 1–3
> executed; Stages 6/6.5/7 executed in their tool-surface form; Stages 4–5 declared N/A with reason.
> **Method:** `~/Dev/multi-repo/.factory-project/storyboard/PERSONA-STORYBOARD-PROCESS.md` (read in
> full, 1,951 lines), applied to `datum` as the product. **Legend:** CANONICAL stores hold each artifact
> once; VIEW dirs link into them and duplicate nothing.

# Storyboard — `datum` v1

## Why this exists, and the honesty typing that governs it

Run at the user's direction, after the four handoff tasks. It applies a UX exploration runbook to a
product with **no UI**, so the mapping is stated up front rather than assumed.

⚠ **MANDATORY HONESTY HEADER — this whole corpus is `evidence_basis: proto, spec-derived,
unvalidated`.** `validate_by:` first real agent-driven migration run against rivetry (Phase 6).

⚠⚠ **The primary persona class here is the runbook's OWN weakest-grounded one.** Under V-K the
consumer of `datum` is an **LLM harness**, not a human, so Stage 1's cast is almost entirely its Step-3d
**system/agent personas** — a class the runbook explicitly types as *"a design spec, not a
research-grounded model,"* noting *"no authority comparable to the Persona Spectrum or the NN/g
anti-persona template exists yet for this class."* Running Stage 1 as written therefore produces the
runbook's least-supported artifact as our **primary** one. That is typed on the way in, not discovered
later. Do not read these personas as research.

## Stage applicability — decided in advance, not discovered

| Stage | Applies? | Form here |
|---|---|---|
| 0 Overview | yes | this file |
| 1 Personas | **yes, reframed** | agent personas + **anti-personas** (unusually apt for `datum`) → `personas/` |
| 2 Workflow inventory | **yes — strongest fit** | `WORKFLOW-INVENTORY.md`: WF rows, coverage matrices, FMEA, state machines, WSJF |
| 3 Journeys | **yes, reframed** | agent task traces → `journeys/` |
| 4 Design-language directions | **NO** | the ~800 op names are **generated from the registry**; there is no design space to diverge over |
| 5 Divergence (fat-marker) | **NO** | same reason — nothing to sketch |
| 6 Hi-fi frames | **yes, as T-3** | a "frame" is an **op × exit-code** surface; state coverage = every reachable exit code |
| 6.5 Design validation | **yes, reframed** | heuristic evaluation of the **tool-call surface** against A1–A4 |
| 7 Evidence | **yes, as discipline** | deterministic golden-file capture, pinned, byte-identical on re-run |
| 8 Traceback | **yes** | every gap routed to an owner; **zero unrouted gaps** is the closing gate |

## Canonical stores and views

```
storyboard/v0.1.0-datum/
├── STORYBOARD-INDEX.md              this file — nav + legend + honesty typing
├── WORKFLOW-INVENTORY.md            CANONICAL WF-* store (append-only): rows, matrices, FMEA,
│                                    state machines, WSJF priority
├── personas/                        VIEW + canonical roster
│   ├── PERSONA-ROSTER.md            designed-for cast (agents, humans, CI)
│   ├── ANTI-PERSONA-ROSTER.md       SEPARATE file, EXEMPT from the orphan check by construction
│   └── PERSONA-WORKFLOW-MATRIX.md   the coverage cube (persona × workflow), a GENERATED view
└── journeys/
    └── journey-<code>.md            Stage 3 narrative task traces
```

## Status glyph lifecycle (closed vocabulary, monotonic)

Adapted from the runbook, mapped to `datum`'s own ladders. A cell advances in this order only; a
**regression is a real event** and carries a dated note, never a silent edit.

| glyph | meaning here | produced by |
|---|---|---|
| `—` | n/a — this persona is not an actor for this workflow | Stage 2 Persona(s) column |
| `⬜` | not started | — |
| `📐` | designed (a layer doc specifies it) | L1–L7 |
| `🔨` | built | implementation |
| `🔍` | gated (a test/gate covers it, **with a witness**) | L7-G |
| `📸` | evidenced (golden-file capture per exit code) | L7-H |
| `✅` | in production use against all three corpora | Phase 7 |

## Where this run's findings went

Stage 8 requires zero unrouted gaps. Every gap this run surfaced is routed in
`WORKFLOW-INVENTORY.md` §7, and the three that are new (not already on record) are called out there
explicitly.
