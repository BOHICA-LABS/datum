---
title: Access control — zones, agent identity, and what is actually enforceable
date: 2026-07-30
status: 25 tests (asymmetry 6 · zones 9 · identity 9, +1 corrected prediction)
verdict: zones give a real boundary; ENFORCEMENT needs something fa cannot ship alone
---

# Access control: zones and agent identity

VSDD's method depends on agents being **structurally unable** to see certain artifacts.
This document is the design for preserving that under a single artifact store, and an
honest account of what is and is not enforceable.

---

## 1. The requirement

Straight from the agent definitions:

> **holdout-evaluator:** "CANNOT access `.factory/specs/`, `src/` internals,
> `.factory/cycles/*/adversarial-reviews/`"
> **adversary:** "Cannot see prior review passes … **Read-only access enforces both
> constraints structurally**"
> **code-reviewer:** "You CANNOT see … **enforced by Lobster context exclusion**"

Today the wall is **path-based**: deny a directory. Rows in one database give path
exclusion nothing to bite on.

---

## 2. Zone design — a real boundary, invisible UX

### 2.1 Layout

```
<project>/
├── .factory-db/            # everything fa owns
│   ├── fa.yaml             # ONE config file — the whole zone map
│   ├── open/               # a Dolt database (trust zone)
│   └── walled/             # a Dolt database (trust zone)
└── .factory/               # rendered markdown (generated, committed)
```

`fa.yaml` in full:

```yaml
version: 1
default_zone: open
zones:
  open:
    artifacts: [bc, vp, story, epic, task, adr, wave, phase, state, template, lease,
                capability, domain_invariant, nfr, fr, subsystem, instance]
  walled:
    artifacts: [holdout_scenario, adversary_finding, evaluation]
    visible_to: [orchestrator, holdout-evaluator, adversary, state-manager]
```

### 2.2 The UX rule: nobody ever types a zone name

`fa get HS-001` and `fa get BC-1.01.001` are the same command. fa routes
**id → artifact type → zone** (Z2). Verified for `BC-`, `VP-`, `S-`, `HS-`, `ADR-`,
`NFR-`. Adding an artifact type is **one line** in `fa.yaml` (Z8); adding a whole zone
is three.

A role without access gets a refusal that names the zone, the role, the config key, and
says the wall is deliberate — so an agent does not "fix" it by retrying (Z3):

```
'HS-001' lives in the 'walled' zone, which role 'implementer' may not read.
This is an information-asymmetry wall, not an error — see fa.yaml zones.walled.visible_to
```

Every error names the fix rather than the internals: an unknown id lists valid prefixes;
an uninitialized store says `fa init` (Z9).

### 2.3 Two hard implementation rules

1. **Always invoke dolt with `cwd` set to a single zone.** Passing `--data-dir` over the
   parent exposes siblings and permits `SELECT … FROM walled.x` (measured, A2).
2. **Zones must be separate directories.** Separate *databases* under one data-dir is
   not a boundary (A2); separate directories is (A3).

### 2.4 Cost

| Cost | Measured |
|---|---|
| Extra process spawn per zone touched | ~144 ms (SC6, Z7) |
| Per-zone query performance | unaffected |
| **No cross-zone FK** — a holdout scenario cannot FK to the BC it verifies | A6 |
| Granularity is per-**directory**, not per-table | Z4 |

---

## 3. Agent identity — where this gets hard

Zones bound *directories*. Something must decide **which agent is asking**. `FA_ROLE`
is self-declared, so on its own it is a hint, not a boundary (ID1: the same process
sets `FA_ROLE=holdout-evaluator` and resolves the walled zone).

Three tiers were tested. **The results include one prediction I got wrong.**

### 3.1 Tier 2 — OS user per agent: unavailable here

Z5 proved the OS enforces this properly: with the walled directory at mode `000`, the
kernel refuses to even **spawn** a process there — stronger than dolt failing after
start. But ID2: this harness runs every agent as the **same uid** (501), and the process
is not root, so it cannot drop privileges. **Tier 2 requires the harness to run each
agent as its own user or container.** It is not available to `fa`.

### 3.2 Tier 3 — per-role DB credentials: sound at the database, defeated locally

The database side is genuinely sound:

- ID5: no login as `evaluator` with the wrong, empty, guessed, or another role's
  password (all `1045`).
- ID6: **two-way** table-level walls from one mechanism — evaluator denied `bc`,
  implementer denied `holdout_scenario` (both `1105`). This is the granularity the
  zone-directory design cannot reach.
- A5: `dolt_history_*`, `dolt_diff_*` and `dolt_log` are **also** denied, so the GRANT
  wall is not cosmetic.
- ID7: real attribution — commits show `implementer <implementer@agents>` instead of
  everything being `root`.

**But the credential must reach the agent, and in a same-uid fleet every delivery
channel tested is readable by siblings:**

| Channel | Result |
|---|---|
| Environment variable | **LEAKS.** `ps eww` / `ps -E` expose a same-uid sibling's full environment (ID3) |
| File, mode `0600` | **LEAKS.** `0600` protects against other *users*, not other agents running as you (ID4) |

ID5b is the attack end-to-end: a sibling read `FA_DB_PASSWORD=pw-eval` out of
`ps eww`, logged in as `evaluator`, and read the walled row.

**I predicted macOS would hide process environments. It does not.** That corrected
prediction is why tier 3 alone is insufficient.

### 3.3 The mechanism that does work: inherited file descriptors

ID8: the parent authenticates **once per role** and passes the **live connection** to
the agent as an inherited fd. The child used it (`CHILD_GOT:AUTHENTICATED-CHANNEL`)
while no secret ever existed in env, argv, or a file. A sibling cannot obtain it —
there is no `/proc/<pid>/fd` on this platform, and `/dev/fd` lists only the caller's own
descriptors. `lsof` can *observe* that a sibling holds sockets, but observing is not
opening.

This is the same pattern Chrome uses for renderer handles and CI runners use for
privileged sockets.

**The catch:** the *harness* must spawn agents with the fd. `fa` cannot do this for
itself. It is a **requirement on the harness**, not a feature `fa` can ship alone.

---

## 4. Recommendation

| Tier | Enforceable? | Requires | Granularity |
|---|---|---|---|
| **1. Advisory role + harness path denial** | Parity with today | nothing | per-zone |
| **2. OS user per agent + chmod** | **Yes, strongest** | harness runs agents as distinct uids/containers | per-zone |
| **3. Per-role DB credentials** | Only with fd-passing (§3.3) | server + harness fd inheritance | **per-table** |

**Ship tier 1 with the zone-directory layout.** It is honest parity with the current
design — the factory's wall is *already* enforced by the harness's tool profile rather
than by the OS, so this is not a regression — and it keeps the no-daemon property. `fa`'s
role check earns its place by preventing accidents and producing actionable errors.

**Escalate deliberately, not by default:**

- If the harness can run agents as separate OS users → **tier 2**, and the wall becomes
  OS-enforced, *stronger* than today.
- If you need per-**table** walls (e.g. an evaluator that may read *some* specs) → **tier
  3**, which means the server, the fd-passing requirement, and invariant 1's token
  discipline coming back (X7).

**Do not** ship tier 3 with credentials in env vars or files. ID5b shows that is
security theatre: it looks like authentication and provides none.

### What to write down before implementing

1. Which agents need which zones — the `visible_to` lists.
2. Whether per-directory granularity is sufficient, or per-table is required.
3. Whether the harness can provide distinct uids or fd inheritance. **This single
   answer decides the tier**, and it is a question about the harness, not about Dolt.

---

## 5. Open items

1. **Linux behaviour differs, and appears SAFER than macOS.** Researched rather than
   assumed:
   - `/proc/<pid>/environ` access is governed by a ptrace check —
     **`PTRACE_MODE_READ_FSCREDS`** via `ptrace_may_access()` — **not by uid equality**
     ([man proc_pid_environ(5)](https://man7.org/linux/man-pages/man5/proc_pid_environ.5.html),
     [kernel proc docs](https://docs.kernel.org/filesystems/proc.html)). Same-thread-group
     access is always allowed; otherwise the dumpable flag and capability checks apply,
     and `yama/ptrace_scope` restricts further (on Ubuntu's default `ptrace_scope=1` only
     ancestors qualify). `hidepid=1/2` are visibility controls layered on top, not a
     replacement for the ptrace check. **So a sibling agent typically cannot read another
     sibling's environ on Linux — unlike macOS, where `ps eww` leaked it outright (ID3).**
   - `/proc/<pid>/fd/<N>` for a socket is a symlink whose `readlink()` yields
     `socket:[inode]`; the documented operation is *inspection*, not reopening it as a
     usable socket
     ([man proc_pid_fd(5)](https://manpages.ubuntu.com/manpages/questing/ru/man5/proc_pid_fd.5.html)).
     **So ID8's fd-inheritance boundary holds on Linux too.**
   - Both still need an empirical re-run on the target Linux distro, since the outcome
     depends on `ptrace_scope`, `hidepid`, and the dumpable flag — all deployment
     settings, not language semantics.
2. **Cross-zone integrity tooling.** With zones split, the holdout→BC link is no longer
   FK-enforced (A6) and needs a validator.
3. **Broker alternative untested.** A local `fa` daemon holding all credentials and
   authenticating callers by peer identity was not tested; in a same-uid fleet peer uid
   does not discriminate, so it would still need fd inheritance or a per-agent socket.
4. **Credential rotation and lease expiry** for tier 3 are undesigned.
