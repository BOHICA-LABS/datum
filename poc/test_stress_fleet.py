#!/usr/bin/env python3
"""STRESS TEST — 10 machines x 20 agent processes, 10 primary + 10 spikes, one project.

Every earlier concurrency result was small: 8 agents (D1), 32 agents through one mutex
(SC3), 3 clones contending (G4/G5), 8 clones pushing (H11). This runs the real shape at
the size the architecture claims to support, against the REAL GitHub remote.

Topology (forced by invariant 10 — a clone writes ONE branch at a time):

    10 machines
      each has 2 clones:  primary  (branch main)
                          spike    (branch spike_m<i>)
      each clone runs 10 agent PROCESSES behind its own flock mutex
      => 20 clones, 200 agent processes, all pushing to ONE remote data ref

Phases, each isolating one variable:

  S1  LOCAL      200 agents write under the mutex, no network at all
                 -> does flock hold at 20 clones x 10 processes? any lost writes?
  S2  GATE       one push per clone (20 pushes) — the granularity the spec prescribes
                 -> 20-way contention on one data ref
  S3  PER-WRITE  a second round pushing per WRITE instead of per gate (pathological)
                 -> where does push-as-CAS fall over? DECLARED SAMPLE + budget:
                    the full 200-agent version was measured at ~1 unit/min (~3.3 h)
  S4  GRADUATE   9 spikes merge into main concurrently; 1 spike deliberately conflicts
                 -> does one conflicting instance block the other nine?
  S5  REF-SPLIT  the invariant-12 mitigation at scale: 10 clones, 10 SEPARATE data refs
                 -> quantifies what `--ref` per instance buys
  S6  VERIFY     from a FRESH clone: is every single write present exactly once?

Run: .venv/bin/python -u poc/test_stress_fleet.py
Env: FA_ST_MACHINES=10 FA_ST_AGENTS=10 FA_ST_SEED=2000
     FA_ST_S3_AGENTS=3 FA_ST_S3_BUDGET=1800  (S3's declared sample + cap)
     FA_GH_REMOTE, FA_GH_KEEP=1, FA_ST_SKIP=s3,s5
Child: --agent <clone_key> <agent_id> <mode> <phase>
"""
from __future__ import annotations

import json
import os
import random
import resource
import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from clonelock import clone_write_lock  # noqa: E402

POC = Path(__file__).parent
ROOT = POC / "st"
RES = ROOT / "results"
SELF = str(Path(__file__).resolve())
REMOTE = os.environ.get("FA_GH_REMOTE",
                        "https://github.com/drbothen/dolt-artifact-spike-remote.git")
RUN = os.environ.get("FA_ST_RUN") or f"st-{int(time.time())}"
DATA_REF = f"refs/dolt/{RUN}/data"

N_MACH = int(os.environ.get("FA_ST_MACHINES", 10))
N_AG = int(os.environ.get("FA_ST_AGENTS", 10))          # per clone; x2 clones per machine
N_SEED = int(os.environ.get("FA_ST_SEED", 2000))
S3_BUDGET = int(os.environ.get("FA_ST_S3_BUDGET", 1800))
S3_AG = int(os.environ.get("FA_ST_S3_AGENTS", 3))      # per clone; declared sample, see s3
CMD_TIMEOUT = int(os.environ.get("FA_ST_CMD_TIMEOUT", 900))
LOCK_TIMEOUT = float(os.environ.get("FA_ST_LOCK_TIMEOUT", 7200))
SKIP = {s.strip().lower() for s in os.environ.get("FA_ST_SKIP", "").split(",") if s.strip()}

RESULTS: list[tuple[str, bool, str]] = []
REFS_CREATED: set[str] = {DATA_REF}
CLONES: dict[str, Path] = {}          # "m0p" / "m0s" -> path
FACTS: dict[str, object] = {}

DDL = (
    "CREATE TABLE vp (vp_id VARCHAR(16) PRIMARY KEY, title VARCHAR(120) NOT NULL);"
    "CREATE TABLE bc (bc_id VARCHAR(40) PRIMARY KEY, ss_id VARCHAR(8) NOT NULL, "
    "title VARCHAR(200) NOT NULL, capability VARCHAR(32) NULL, notes VARCHAR(200) NULL);"
    "CREATE TABLE bc_trace (bc_id VARCHAR(40) NOT NULL, vp_id VARCHAR(16) NOT NULL, "
    "PRIMARY KEY (bc_id, vp_id), "
    "CONSTRAINT fk_t_bc FOREIGN KEY (bc_id) REFERENCES bc (bc_id) ON DELETE CASCADE, "
    "CONSTRAINT fk_t_vp FOREIGN KEY (vp_id) REFERENCES vp (vp_id) ON DELETE CASCADE);"
    "CREATE TABLE audit (k VARCHAR(80) PRIMARY KEY, machine VARCHAR(8) NOT NULL, "
    "agent VARCHAR(8) NOT NULL, phase VARCHAR(16) NOT NULL);"
)


def check(name, ok, detail=""):
    RESULTS.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}", flush=True)
    for ln in (detail or "").splitlines():
        print(f"        {ln}", flush=True)


def sh(args, cwd=None, timeout=CMD_TIMEOUT):
    try:
        return subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(args, 124, "", f"TIMEOUT after {timeout}s")


def dolt(*a, cwd=None, timeout=CMD_TIMEOUT):
    return sh(["dolt", *a], cwd=cwd, timeout=timeout)


def sql(stmt, cwd, timeout=CMD_TIMEOUT):
    return sh(["dolt", "sql", "-q", stmt, "-r", "csv"], cwd=cwd, timeout=timeout)


def val(r):
    lines = [l for l in (r.stdout or "").strip().splitlines() if l.strip()]
    return lines[1].split(",")[0] if len(lines) > 1 else None


def clean(s: str, n=130) -> str:
    s = (s or "").replace("\r", "\n")
    keep = [l for l in s.splitlines()
            if l.strip() and not any(w in l for w in
                                     ("Uploading", "Downloading", "Writing", "Fetching",
                                      "Pulling", "Pushing"))]
    return " | ".join(keep)[-n:]


def machine_of(key: str) -> int:
    return int(key[1:-1])


def branch_of(key: str) -> str:
    return "main" if key.endswith("p") else f"spike_{key[:-1]}"


# ---------------------------------------------------------------- the agent


def agent_main(argv):
    """One agent = one OS process. Unit of work = ONE transaction under the clone's
    mutex (invariant 6 as restated), then a dolt commit, then optionally a push.

    Writes its own result as JSON so the parent needs no pipes for 200 children.
    """
    key, agent_id, mode, phase = argv[0], argv[1], argv[2], argv[3]
    cwd = Path(os.environ["FA_ST_CLONE_" + key])
    m = machine_of(key)
    is_spike = key.endswith("s")
    branch = branch_of(key)
    out = {"key": key, "agent": agent_id, "mode": mode, "phase": phase,
           "ok": False, "attempts": 0, "lock_wait_s": 0.0, "total_s": 0.0,
           "conflict_aborted": False, "manifest_err": False, "err": ""}
    t_start = time.perf_counter()
    akey = f"{phase}-{key}-{agent_id}"

    # what this agent writes: primary agents create a record + its FK'd edge;
    # spike agents mutate ONE cell of a hot shared row (cell-merge stress).
    hot = f"BC-SEED.{m:02d}" if not (is_spike and m == N_MACH - 1) else "BC-SEED.00"
    if is_spike:
        payload = (f"UPDATE bc SET capability='CAP-{m}{agent_id}' WHERE bc_id='{hot}';")
    else:
        bcid = f"BC-{phase}.{m:02d}.{agent_id}"
        payload = (
            f"INSERT INTO bc (bc_id, ss_id, title) VALUES "
            f"('{bcid}','SS-{m:02d}','agent {agent_id} on machine {m}');"
            f"INSERT INTO bc_trace (bc_id, vp_id) VALUES ('{bcid}','VP-001');")
    unit = ("START TRANSACTION;" + payload
            + f"INSERT INTO audit (k, machine, agent, phase) VALUES "
              f"('{akey}','m{m}','{agent_id}','{phase}');" + "COMMIT;")

    tries = 12 if mode == "sync" else 1
    for attempt in range(tries):
        out["attempts"] = attempt + 1
        try:
            t_lock = time.perf_counter()
            with clone_write_lock(cwd, timeout=LOCK_TIMEOUT):
                if attempt == 0:
                    out["lock_wait_s"] = round(time.perf_counter() - t_lock, 2)
                if mode == "sync":
                    pl = dolt("pull", "origin", branch, cwd=cwd)
                    if pl.returncode != 0:
                        blob = ((pl.stdout or "") + (pl.stderr or "")).upper()
                        if "CONFLICT" in blob:
                            dolt("merge", "--abort", cwd=cwd)
                            out["conflict_aborted"] = True
                            out["err"] = "pull-conflict"
                            break
                        # a brand-new spike branch has no upstream yet: not an error
                        if "NO REMOTE" not in blob and "NOT FOUND" not in blob \
                                and "UNKNOWN" not in blob and "SPECIFY A BRANCH" not in blob:
                            out["err"] = "pull:" + clean(pl.stderr or pl.stdout, 70)
                w = dolt("sql", "-q", unit, cwd=cwd)
                if w.returncode != 0:
                    blob = ((w.stderr or "") + (w.stdout or "")).lower()
                    if "manifest" in blob:
                        out["manifest_err"] = True
                    if not ("duplicate" in blob or "unique" in blob):
                        out["err"] = "write:" + clean(w.stderr or w.stdout, 70)
                        break
                    # already applied on an earlier attempt -> fall through (invariant 4)
                dolt("add", "-A", cwd=cwd)
                cm = dolt("commit", "-m", f"{key}/{agent_id} {phase}", cwd=cwd)
                blob = (cm.stdout or "") + (cm.stderr or "")
                if cm.returncode != 0 and "nothing to commit" not in blob \
                        and "no changes added" not in blob:
                    if "manifest" in blob.lower():
                        out["manifest_err"] = True
                    out["err"] = "commit:" + clean(blob, 70)
                    break
                if mode == "local":
                    out["ok"] = True
                    break
                ps = dolt("push", "origin", branch, cwd=cwd)
                if ps.returncode == 0:
                    out["ok"] = True
                    break
                if "manifest" in ((ps.stderr or "") + (ps.stdout or "")).lower():
                    out["manifest_err"] = True
            time.sleep(0.4 + random.random() * 1.2 * (attempt + 1))   # jittered backoff
        except Exception as e:                                        # noqa: BLE001
            out["err"] = f"exc:{type(e).__name__}:{e}"[:120]
            break
    out["total_s"] = round(time.perf_counter() - t_start, 2)
    (RES / f"{phase}-{key}-{agent_id}.json").write_text(json.dumps(out))
    return 0


def launch_fleet(keys, mode, phase, budget=None):
    """Spawn N_AG agents on every clone in `keys`, all at once. No pipes: each child
    writes a JSON result file, so 200 children cost 200 fds, not 600."""
    env = dict(os.environ)
    for k, v in CLONES.items():
        env["FA_ST_CLONE_" + k] = str(v)
    procs = []
    for k in keys:
        for j in range(N_AG):
            procs.append(subprocess.Popen(
                [sys.executable, SELF, "--agent", k, str(j), mode, phase],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env))
    t0 = time.perf_counter()
    deadline = (t0 + budget) if budget else None
    killed = 0
    for p in procs:
        remaining = None if not deadline else max(1, deadline - time.perf_counter())
        try:
            p.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            p.kill()
            killed += 1
    wall = time.perf_counter() - t0
    rows = []
    for k in keys:
        for j in range(N_AG):
            f = RES / f"{phase}-{k}-{j}.json"
            if f.exists():
                try:
                    rows.append(json.loads(f.read_text()))
                except json.JSONDecodeError:
                    pass
    return rows, wall, killed


def summarize(rows, expected):
    ok = [r for r in rows if r.get("ok")]
    waits = [r.get("lock_wait_s", 0) for r in rows]
    totals = [r.get("total_s", 0) for r in rows]
    att = [r.get("attempts", 0) for r in rows]
    return {
        "reported": len(rows), "expected": expected, "ok": len(ok),
        "manifest": sum(1 for r in rows if r.get("manifest_err")),
        "conflict_aborted": sum(1 for r in rows if r.get("conflict_aborted")),
        "errs": [f"{r['key']}/{r['agent']}:{r['err']}" for r in rows if r.get("err")][:8],
        "wait_med": statistics.median(waits) if waits else 0,
        "wait_max": max(waits) if waits else 0,
        "unit_med": statistics.median(totals) if totals else 0,
        "unit_max": max(totals) if totals else 0,
        "att_total": sum(att), "att_max": max(att) if att else 0,
    }


# ---------------------------------------------------------------- setup


def setup():
    resource.setrlimit(resource.RLIMIT_NOFILE, (8192, resource.getrlimit(resource.RLIMIT_NOFILE)[1]))
    if ROOT.exists():
        shutil.rmtree(ROOT)
    RES.mkdir(parents=True)
    d = ROOT / "origin" / "db"
    d.mkdir(parents=True)
    if dolt("init", "--name", "st", "--email", "st@local", cwd=d).returncode != 0:
        raise RuntimeError("dolt init failed")
    if sql(DDL, cwd=d).returncode != 0:
        raise RuntimeError("ddl failed")
    # seed: VP-001 plus N_SEED bc rows, one batch inside ONE transaction (the
    # restated invariant 6 — this is the 17-23x path, dogfooded).
    f = ROOT / "seed.sql"
    with open(f, "w") as fh:
        fh.write("START TRANSACTION;\n")
        fh.write("INSERT INTO vp VALUES ('VP-001','the seed property');\n")
        for i in range(N_MACH):
            fh.write(f"INSERT INTO bc (bc_id, ss_id, title) VALUES "
                     f"('BC-SEED.{i:02d}','SS-{i:02d}','hot row for machine {i}');\n")
        B = 500
        for start in range(0, N_SEED, B):
            vals = ",".join(
                f"('BC-BULK.{i:06d}','SS-{i%N_MACH:02d}','bulk contract {i}')"
                for i in range(start, min(start + B, N_SEED)))
            fh.write(f"INSERT INTO bc (bc_id, ss_id, title) VALUES {vals};\n")
        fh.write("COMMIT;\n")
    t0 = time.perf_counter()
    r = sh(["dolt", "sql", "-f", str(f)], cwd=d)
    seed_s = time.perf_counter() - t0
    if r.returncode != 0:
        raise RuntimeError(f"seed: {clean(r.stderr, 200)}")
    dolt("add", "-A", cwd=d)
    dolt("commit", "-m", f"seed {N_SEED} rows", cwd=d)
    if dolt("remote", "add", "--ref", DATA_REF, "origin", REMOTE, cwd=d).returncode != 0:
        raise RuntimeError("remote add failed")
    p = dolt("push", "origin", "main", cwd=d, timeout=1800)
    if p.returncode != 0:
        raise RuntimeError(f"seed push: {clean(p.stderr, 200)}")
    print(f"--- seeded {N_SEED+N_MACH+1} rows in {seed_s:.1f}s (one transaction), "
          f"pushed to {DATA_REF}", flush=True)

    # 20 clones: primary + spike per machine
    t0 = time.perf_counter()
    for i in range(N_MACH):
        for suffix in ("p", "s"):
            key = f"m{i}{suffix}"
            parent = ROOT / key
            parent.mkdir(parents=True)
            c = sh(["dolt", "clone", "--ref", DATA_REF, REMOTE, "c"], cwd=parent,
                   timeout=1800)
            if c.returncode != 0:
                raise RuntimeError(f"clone {key}: {clean(c.stderr, 150)}")
            cd = parent / "c"
            dolt("config", "--local", "--add", "user.name", key, cwd=cd)
            dolt("config", "--local", "--add", "user.email", f"{key}@local", cwd=cd)
            if suffix == "s":
                dolt("checkout", "-b", branch_of(key), cwd=cd)
            CLONES[key] = cd
    print(f"--- provisioned {len(CLONES)} clones "
          f"({N_MACH} primary + {N_MACH} spike) in {time.perf_counter()-t0:.0f}s",
          flush=True)
    return d


# ---------------------------------------------------------------- S1


def s1_local():
    keys = list(CLONES)
    n = len(keys) * N_AG
    rows, wall, killed = launch_fleet(keys, "local", "local")
    s = summarize(rows, n)
    # nothing was pushed yet: every clone must hold exactly N_AG audit rows locally
    per_clone = {}
    for k in keys:
        per_clone[k] = val(sql("SELECT COUNT(*) FROM audit WHERE phase='local'",
                               cwd=CLONES[k]))
    bad = {k: v for k, v in per_clone.items() if v != str(N_AG)}
    ok = (s["ok"] == n and s["manifest"] == 0 and not bad and killed == 0)
    FACTS["s1"] = s
    check(f"S1 LOCAL: {n} agent processes across {len(keys)} clones, no network",
          ok,
          f"agents completing their unit : {s['ok']}/{n}   (results reported: "
          f"{s['reported']})\n"
          f"`cannot update manifest`     : {s['manifest']}  (must be 0 — the mutex's job)\n"
          f"lost writes                  : {len(bad)} clones off expected {N_AG}"
          f"{' -> ' + str(bad) if bad else ''}\n"
          f"wall clock                   : {wall:.0f}s for {n} units "
          f"({wall/n*1000:.0f} ms/unit amortised across {len(keys)} clones)\n"
          f"per-unit time                 : median {s['unit_med']:.1f}s  max "
          f"{s['unit_max']:.1f}s\n"
          f"mutex wait                    : median {s['wait_med']:.1f}s  max "
          f"{s['wait_max']:.1f}s  (ratio {s['wait_max']/max(s['wait_med'],0.01):.1f}x — "
          f"starvation check)\n"
          + (f"errors: {s['errs']}\n" if s['errs'] else "")
          + f"=> 10 agents per clone serialise behind flock; {len(keys)} clones run in\n"
            f"   genuine parallel. SC3 measured 32 agents on ONE mutex; this is "
            f"{n} across {len(keys)}.")


# ---------------------------------------------------------------- S2


def s2_gate_push():
    """The prescribed granularity: one push per clone per unit of work."""
    keys = list(CLONES)
    attempts, landed, errs = {}, {}, {}
    import threading
    bar = threading.Barrier(len(keys))

    def worker(k):
        d, br = CLONES[k], branch_of(k)
        bar.wait()
        n = 0
        for _ in range(len(keys) + 6):
            n += 1
            p = dolt("push", "origin", br, cwd=d)
            if p.returncode == 0:
                break
            pl = dolt("pull", "origin", br, cwd=d)
            if pl.returncode != 0:
                blob = ((pl.stdout or "") + (pl.stderr or "")).upper()
                if "CONFLICT" in blob:
                    dolt("merge", "--abort", cwd=d)
                    errs[k] = "conflict-aborted"
                    break
            time.sleep(0.5 + random.random() * 2)
        attempts[k] = n
        landed[k] = p.returncode == 0

    t0 = time.perf_counter()
    ts = [threading.Thread(target=worker, args=(k,)) for k in keys]
    [t.start() for t in ts]
    [t.join() for t in ts]
    wall = time.perf_counter() - t0
    at = [attempts.get(k, 0) for k in keys]
    n_ok = sum(1 for k in keys if landed.get(k))
    # THE question invariant 12 raises: all branches share one data ref, so does a
    # push contend with clones pushing a DIFFERENT branch, or only with clones
    # pushing the SAME one? Primary clones all target main; spikes each target
    # their own branch. Split the attempts and let the numbers answer it.
    pri = [attempts.get(k, 0) for k in keys if k.endswith("p")]
    spk = [attempts.get(k, 0) for k in keys if k.endswith("s")]
    per_branch = sum(spk) == len(spk) and sum(pri) > len(pri)
    FACTS["s2"] = {"attempts": at, "wall": wall, "landed": landed,
                   "pri": pri, "spk": spk}
    check(f"S2 GATE: one push per clone, {len(keys)} clones at once (the prescribed granularity)",
          n_ok == len(keys),
          f"clones whose push landed  : {n_ok}/{len(keys)}\n"
          f"attempts, primary (-> main): {pri}   total {sum(pri)}   "
          f"O(N) for {len(pri)} would be {len(pri)*(len(pri)+1)//2}\n"
          f"attempts, spikes (-> own branch): {spk}   total {sum(spk)}\n"
          f"wall clock                : {wall:.0f}s\n"
          + (f"errors: {errs}\n" if errs else "")
          + f"=> CONTENTION IS PER-BRANCH, NOT PER-REF: {per_branch}\n"
            f"   {len(pri)} clones pushing the SAME branch contend ~O(N); "
            f"{len(spk)} clones pushing\n"
            f"   DISTINCT branches into the SAME data ref "
            f"{'did not contend at all' if per_branch else 'also contended'}.\n"
            f"   That refines invariant 12, which was stated as global contention.")


# ---------------------------------------------------------------- S3


def s3_per_write():
    """Pathological: every agent pushes its own unit — a network round trip per write.

    DECLARED SAMPLE. A first attempt ran all 10 agents per clone and measured ~1 unit
    per minute across the fleet, i.e. ~3.3 h for 200 units, with single pushes taking
    ~3 minutes as fleet-wide commit churn grew. That is itself the result, so this
    phase runs S3_AGENTS of the N_AG agents per clone and says so rather than
    quietly truncating.
    """
    keys = list(CLONES)
    n = len(keys) * S3_AG
    saved = globals()["N_AG"]
    globals()["N_AG"] = S3_AG                     # launch_fleet uses N_AG
    try:
        rows, wall, killed = launch_fleet(keys, "sync", "perwrite", budget=S3_BUDGET)
    finally:
        globals()["N_AG"] = saved
    s = summarize(rows, n)
    exhausted = [f"{r['key']}/{r['agent']}" for r in rows
                 if not r.get("ok") and not r.get("conflict_aborted")]
    pri = [r for r in rows if r["key"].endswith("p")]
    spk = [r for r in rows if r["key"].endswith("s")]
    s["ok_keys"] = {f"perwrite-{r['key']}-{r['agent']}" for r in rows if r.get("ok")}
    ok = s["ok"] >= int(n * 0.95) and s["manifest"] == 0
    FACTS["s3"] = s
    check(f"S3 PER-WRITE (pathological): {n} agents push individually "
          f"({S3_AG} of {saved} per clone — a DECLARED sample)",
          ok,
          f"agents that landed a push : {s['ok']}/{n}"
          f"{f'  [BUDGET HIT: {killed} killed at {S3_BUDGET}s]' if killed else ''}\n"
          f"NOT RUN in this phase     : {(saved - S3_AG) * len(keys)} agents "
          f"({saved - S3_AG} per clone) — coverage deliberately bounded, see below\n"
          f"push attempts, total      : {s['att_total']}   worst single agent: "
          f"{s['att_max']}\n"
          f"  primary (-> main)       : max attempts "
          f"{max((r['attempts'] for r in pri), default=0)}\n"
          f"  spikes (-> own branch)  : max attempts "
          f"{max((r['attempts'] for r in spk), default=0)}\n"
          f"`cannot update manifest`  : {s['manifest']}\n"
          f"conflict-aborted (clean)  : {s['conflict_aborted']}\n"
          f"agents that gave up       : {len(exhausted)}"
          f"{' -> ' + str(exhausted[:6]) if exhausted else ''}\n"
          f"per-unit time             : median {s['unit_med']:.1f}s  max {s['unit_max']:.1f}s\n"
          f"mutex wait                : median {s['wait_med']:.1f}s  max {s['wait_max']:.1f}s\n"
          f"wall clock                : {wall:.0f}s\n"
          + (f"errors: {s['errs']}\n" if s['errs'] else "")
          + f"=> this is the shape the SPEC tells you NOT to build, and the earlier\n"
            f"   full-fleet attempt showed why: at 200 agents it degraded to ~1 unit per\n"
            f"   minute with individual pushes reaching ~3 MINUTES as commit churn grew,\n"
            f"   projecting ~3.3 h. It degrades LOUDLY and slowly, not by losing data —\n"
            f"   but a per-write network round trip is unusable at fleet scale.")


# ---------------------------------------------------------------- S4


def s4_graduate():
    """9 spikes hold disjoint cell edits and must graduate cleanly. Machine N-1 was
    aimed at machine 0's hot cell on purpose, so its graduation MUST conflict — and
    must not stop the other nine."""
    import threading
    keys = [f"m{i}s" for i in range(N_MACH)]
    res = {}
    bar = threading.Barrier(len(keys))

    def grad(k):
        d = CLONES[k]
        br = branch_of(k)
        bar.wait()
        # graduate = merge the instance branch into main, then push main
        for attempt in range(len(keys) + 6):
            dolt("checkout", "main", cwd=d)
            dolt("fetch", "origin", cwd=d)
            dolt("reset", "--hard", "origin/main", cwd=d)
            m = dolt("merge", br, "--no-edit", cwd=d)
            blob = ((m.stdout or "") + (m.stderr or "")).lower()
            if m.returncode != 0 or "conflict" in blob:
                dolt("merge", "--abort", cwd=d)
                res[k] = ("conflict", attempt + 1, clean(blob, 90))
                dolt("checkout", br, cwd=d)
                return
            dolt("add", "-A", cwd=d)
            dolt("commit", "-m", f"graduate {br}", cwd=d)
            p = dolt("push", "origin", "main", cwd=d)
            if p.returncode == 0:
                res[k] = ("graduated", attempt + 1, "")
                dolt("checkout", br, cwd=d)
                return
            time.sleep(0.5 + random.random() * 2)
        res[k] = ("exhausted", len(keys) + 6, "")
        dolt("checkout", br, cwd=d)

    t0 = time.perf_counter()
    ts = [threading.Thread(target=grad, args=(k,)) for k in keys]
    [t.start() for t in ts]
    [t.join() for t in ts]
    wall = time.perf_counter() - t0
    grads = [k for k, v in res.items() if v[0] == "graduated"]
    confs = [k for k, v in res.items() if v[0] == "conflict"]
    FACTS["s4"] = {"graduated": len(grads), "conflicts": len(confs), "wall": wall,
                   "graduated_keys": sorted(grads)}
    ok = len(grads) >= N_MACH - 1 and len(confs) >= 1
    check(f"S4 GRADUATE: {N_MACH} spikes merge into one main concurrently "
          f"(1 deliberately conflicting)",
          ok,
          f"graduated cleanly : {len(grads)}/{N_MACH}  {sorted(grads)}\n"
          f"conflicted+aborted: {len(confs)}  {sorted(confs)}\n"
          f"  (machines 0 and {N_MACH-1} deliberately target the SAME hot cell, so exactly\n"
          f"   one of that PAIR must conflict; which one depends on who graduates first)\n"
          f"attempts per spike: "
          f"{ {k: v[1] for k, v in sorted(res.items())} }\n"
          f"wall clock        : {wall:.0f}s\n"
          + "\n".join(f"  {k}: {v[0]} {v[2]}" for k, v in sorted(res.items()) if v[2])
          + f"\n=> the point: ONE conflicting instance must not block the other nine, and\n"
            f"   its abort must leave main and every other clone usable (invariant 2 +\n"
            f"   DECISIONS D1 at fleet scale).")


# ---------------------------------------------------------------- S5


def s5_ref_split():
    """Invariant 12's mitigation, quantified: N clones each pushing its OWN data ref."""
    import threading
    base = ROOT / "refsplit"
    base.mkdir(parents=True, exist_ok=True)
    ds = []
    for i in range(N_MACH):
        ref = f"refs/dolt/{RUN}/inst{i}"
        REFS_CREATED.add(ref)
        p = base / f"i{i}"
        p.mkdir()
        d = p / "db"
        d.mkdir()
        dolt("init", "--name", f"i{i}", "--email", f"i{i}@l", cwd=d)
        sql("CREATE TABLE t (k VARCHAR(32) PRIMARY KEY, v INT NOT NULL)", cwd=d)
        dolt("add", "-A", cwd=d)
        dolt("commit", "-m", "schema", cwd=d)
        dolt("remote", "add", "--ref", ref, "origin", REMOTE, cwd=d)
        sql(f"INSERT INTO t VALUES ('i{i}',{i})", cwd=d)
        dolt("add", "-A", cwd=d)
        dolt("commit", "-m", f"work i{i}", cwd=d)
        ds.append(d)
    attempts, landed = {}, {}
    bar = threading.Barrier(len(ds))

    def worker(i):
        bar.wait()
        n = 0
        for _ in range(6):
            n += 1
            p = dolt("push", "origin", "main", cwd=ds[i])
            if p.returncode == 0:
                break
            time.sleep(0.5)
        attempts[i] = n
        landed[i] = p.returncode == 0

    t0 = time.perf_counter()
    ts = [threading.Thread(target=worker, args=(i,)) for i in range(len(ds))]
    [t.start() for t in ts]
    [t.join() for t in ts]
    wall = time.perf_counter() - t0
    at = [attempts.get(i) for i in range(len(ds))]
    shared = FACTS.get("s2", {}).get("attempts", [])
    ok = all(landed.values()) and sum(a or 0 for a in at) == len(ds)
    check(f"S5 REF-SPLIT: {N_MACH} instances, {N_MACH} SEPARATE data refs, pushing at once",
          ok,
          f"attempts per instance : {at}\n"
          f"total attempts        : {sum(a or 0 for a in at)} "
          f"(one each = zero contention)\n"
          f"wall clock            : {wall:.0f}s\n"
          f"same-ref comparison   : S2 needed {sum(shared)} attempts for "
          f"{len(shared)} clones in {FACTS.get('s2',{}).get('wall',0):.0f}s\n"
          f"=> this is what `dolt remote add --ref <per-instance>` buys, measured. The\n"
          f"   cost is that each ref is a separate LINEAGE: no cross-instance merge on\n"
          f"   the remote (invariant 12).")


# ---------------------------------------------------------------- S6


def keys_in(d: Path, where="1=1") -> set[str]:
    r = sh(["dolt", "sql", "-q", f"SELECT k FROM audit WHERE {where} ORDER BY k",
            "-r", "csv"], cwd=d, timeout=CMD_TIMEOUT)
    lines = [l.strip() for l in (r.stdout or "").splitlines() if l.strip()]
    return set(lines[1:]) if len(lines) > 1 else set()


def s6_verify():
    """The only question that really matters: is every write present exactly once?

    The expectation is DERIVED from what each clone actually holds and what each
    phase actually reported — never from the ideal count. A truncated phase must
    not be able to masquerade as a lost write, and a lost write must not be able
    to hide behind a truncated phase.
    """
    v = ROOT / "verify"
    v.mkdir(parents=True, exist_ok=True)
    c = sh(["dolt", "clone", "--ref", DATA_REF, REMOTE, "fresh"], cwd=v, timeout=1800)
    if c.returncode != 0:
        check("S6 VERIFY", False, f"fresh clone failed: {clean(c.stderr)}")
        return
    d = v / "fresh"
    dolt("config", "--local", "--add", "user.name", "verify", cwd=d)
    dolt("config", "--local", "--add", "user.email", "verify@local", cwd=d)

    s2_landed = FACTS.get("s2", {}).get("landed", {})
    s3_ok = FACTS.get("s3", {}).get("ok_keys", set())
    graduated = set(FACTS.get("s4", {}).get("graduated_keys", []))

    expected: set[str] = set()
    reasons: list[str] = []
    for k, cd in CLONES.items():
        local_keys = keys_in(cd)
        if k.endswith("p"):
            # primary clones push straight to main: S1 rows arrive via the S2 gate
            # push, S3 rows arrive via whichever per-agent pushes landed.
            if s2_landed.get(k):
                expected |= {x for x in local_keys if x.startswith("local-")}
            else:
                reasons.append(f"{k}: S2 push did not land, its S1 rows are not expected")
            expected |= {x for x in local_keys if x.startswith("perwrite-")} & s3_ok
        else:
            # a spike's work reaches main ONLY by graduating, and graduation merges
            # the LOCAL branch — so everything it committed locally comes with it.
            if k in graduated:
                expected |= local_keys
            else:
                reasons.append(f"{k}: did not graduate, none of its rows are expected on main")

    got = keys_in(d)
    missing = sorted(expected - got)
    extra = sorted(got - expected)
    dupes = val(sql("SELECT COUNT(*) FROM (SELECT k FROM audit GROUP BY k "
                    "HAVING COUNT(*)>1) x", cwd=d))
    # FK integrity: the DB enforces it, so this checks the constraint SURVIVED the
    # whole fleet — 200 concurrent writers plus N concurrent merges.
    dangling = val(sql("SELECT COUNT(*) FROM bc_trace t LEFT JOIN bc b ON b.bc_id=t.bc_id "
                       "WHERE b.bc_id IS NULL", cwd=d))
    n_bc = val(sql("SELECT COUNT(*) FROM bc", cwd=d))
    n_edge = val(sql("SELECT COUNT(*) FROM bc_trace", cwd=d))
    caps = val(sql("SELECT COUNT(*) FROM bc WHERE bc_id LIKE 'BC-SEED.%' "
                   "AND capability IS NOT NULL", cwd=d))
    by_phase = sh(["dolt", "sql", "-q",
                   "SELECT phase, COUNT(*) FROM audit GROUP BY phase ORDER BY phase",
                   "-r", "csv"], cwd=d, timeout=CMD_TIMEOUT)
    ok = not missing and not extra and dupes == "0" and dangling == "0"
    FACTS["s6"] = {"expected": len(expected), "got": len(got),
                   "missing": len(missing), "extra": len(extra)}
    check("S6 VERIFY from a FRESH clone: is every write present exactly once?",
          ok,
          f"expected on main (derived, not assumed) : {len(expected)} audit rows\n"
          f"actually on main                        : {len(got)}\n"
          f"  MISSING (a real lost write)           : {len(missing)}"
          f"{' -> ' + str(missing[:8]) if missing else ''}\n"
          f"  UNEXPECTED (a phantom write)          : {len(extra)}"
          f"{' -> ' + str(extra[:8]) if extra else ''}\n"
          f"  duplicate keys                        : {dupes} (must be 0)\n"
          f"by phase                                : {clean(by_phase.stdout, 110)}\n"
          f"dangling FK edges                       : {dangling} (must be 0 — the FK\n"
          f"  survived {N_MACH*N_AG*2} concurrent writers and "
          f"{len(graduated)} concurrent merges)\n"
          f"bc rows {n_bc}, edges {n_edge}, hot rows with a capability: {caps}\n"
          + ("".join(f"  note: {r}\n" for r in reasons[:8]) if reasons else "")
          + f"=> the expectation is built from each clone's OWN contents plus which\n"
            f"   pushes and graduations actually landed, so a deliberately truncated\n"
            f"   phase cannot look like data loss — and data loss cannot hide behind one.")


# ---------------------------------------------------------------- main


def cleanup():
    if os.environ.get("FA_GH_KEEP"):
        print(f"--- keeping refs: {sorted(REFS_CREATED)}")
        return
    out = []
    for ref in sorted(REFS_CREATED):
        r = sh(["git", "push", REMOTE, f":{ref}"], timeout=180)
        out.append(f"{ref.split('/')[-1]}={'ok' if r.returncode == 0 else r.returncode}")
    print(f"--- cleanup ({len(out)} refs): {'; '.join(out)}")


def main():
    n_total = N_MACH * N_AG * 2
    print(f"=== STRESS: {N_MACH} machines x {N_AG*2} agents "
          f"({N_AG} primary + {N_AG} spike) = {n_total} agent processes\n"
          f"    {N_MACH*2} clones, one shared data ref, real remote\n"
          f"    remote={REMOTE}\n    run={RUN}  ref={DATA_REF}\n"
          f"    seed={N_SEED} rows  S3 sample={S3_AG}/{N_AG} agents per clone, budget={S3_BUDGET}s"
          f"{'  SKIP=' + str(sorted(SKIP)) if SKIP else ''}\n", flush=True)
    setup()
    try:
        for name, fn in (("s1", s1_local), ("s2", s2_gate_push), ("s3", s3_per_write),
                         ("s4", s4_graduate), ("s5", s5_ref_split), ("s6", s6_verify)):
            if name in SKIP:
                print(f"--- {name} SKIPPED (FA_ST_SKIP) — coverage NOT claimed\n", flush=True)
                continue
            try:
                fn()
            except Exception:                                       # noqa: BLE001
                import traceback
                check(f"{fn.__name__} (ERROR)", False, traceback.format_exc()[-800:])
            print(flush=True)
    finally:
        cleanup()
    npass = sum(1 for _, ok, _ in RESULTS if ok)
    print("=" * 74)
    print(f"{npass}/{len(RESULTS)} passed")
    for nm, ok, _ in RESULTS:
        if not ok:
            print(f"  FAILED: {nm}")
    sys.exit(0 if npass == len(RESULTS) else 1)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--agent":
        sys.exit(agent_main(sys.argv[2:]))
    main()
