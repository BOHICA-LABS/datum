#!/usr/bin/env python3
"""CAN WE MAKE IT FASTER, AND CAN WE SOLVE THE CONTENTION? — measured A/B.

The 200-agent stress run (poc/test_stress_fleet.py) found two independent costs:

  1. CONTENTION: 10 clones pushing the SAME branch needed 54 attempts (O(N) for
     N=10 is 55) and 323 s. 10 clones pushing DISTINCT branches into the same data
     ref needed exactly 1 attempt each. So contention is per-BRANCH, not per-ref.
  2. LATENCY inside the lock: an agent that holds the write mutex across a pull and
     a push makes every sibling on that clone wait for the network. Per-write
     pushing degraded to ~1 unit/minute at 200 agents.

This suite tests three fixes, each as an A/B on the same fleet, same remote, same
session — so the comparison is not across days or network conditions.

  O1  CONTENTION   Both arms push the SAME single branch — the factory's artifact
                   store is ONE branch, so branching is not an available answer.
                   A: free-for-all (push `main`, retry on rejection)
                   B: queued behind a create-only LOCK REF on a different ref
                   -> can O(N^2/2) wasted round trips become N sequential ones?
  O2  INVOCATIONS  A: write, `dolt add -A`, `dolt commit`      (3 process spawns)
                   B: one `dolt sql` doing the write AND CALL DOLT_COMMIT (1 spawn)
                   -> how much of the local phase is just process spawn?
  O3  PUSH COST    push duration vs unpushed-commit count, and what `dolt gc` does
                   -> explains the ~3-minute pushes seen under fleet churn

Run: .venv/bin/python -u poc/test_stress_opt.py
Env: FA_OPT_CLONES=10 FA_OPT_WORK=5 FA_OPT_AGENTS=10 FA_OPT_MACH=4 FA_GH_REMOTE
"""
from __future__ import annotations

import json
import os
import random
import shutil
import statistics
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from clonelock import clone_write_lock  # noqa: E402

POC = Path(__file__).parent
ROOT = POC / "opt"
RES = ROOT / "results"
SELF = str(Path(__file__).resolve())
REMOTE = os.environ.get("FA_GH_REMOTE",
                        "https://github.com/drbothen/datum (formerly dolt-artifact-spike)-remote.git")
RUN = os.environ.get("FA_OPT_RUN") or f"opt-{int(time.time())}"

N_CLONES = int(os.environ.get("FA_OPT_CLONES", 10))     # pushers in O1
N_WORK = int(os.environ.get("FA_OPT_WORK", 5))          # commits of work per clone
N_MACH = int(os.environ.get("FA_OPT_MACH", 4))          # clones in O2
N_AG = int(os.environ.get("FA_OPT_AGENTS", 10))         # agents per clone in O2
TIMEOUT = int(os.environ.get("FA_ST_CMD_TIMEOUT", 900))
ONLY = {x.strip().lower() for x in os.environ.get("FA_OPT_ONLY", "").split(",") if x.strip()}

RESULTS: list[tuple[str, bool, str]] = []
REFS: set[str] = set()
FACTS: dict[str, object] = {}

DDL = ("CREATE TABLE work (k VARCHAR(64) PRIMARY KEY, who VARCHAR(32) NOT NULL);"
       "CREATE TABLE pad (k INT PRIMARY KEY, v VARCHAR(200) NOT NULL);")


def check(name, ok, detail=""):
    RESULTS.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}", flush=True)
    for ln in (detail or "").splitlines():
        print(f"        {ln}", flush=True)


def sh(args, cwd=None, timeout=TIMEOUT):
    try:
        return subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(args, 124, "", f"TIMEOUT after {timeout}s")


def dolt(*a, cwd=None, timeout=TIMEOUT):
    return sh(["dolt", *a], cwd=cwd, timeout=timeout)


def sql(stmt, cwd, timeout=TIMEOUT):
    return sh(["dolt", "sql", "-q", stmt, "-r", "csv"], cwd=cwd, timeout=timeout)


def val(r):
    lines = [l for l in (r.stdout or "").strip().splitlines() if l.strip()]
    return lines[1].split(",")[0] if len(lines) > 1 else None


def clean(s: str, n=110) -> str:
    s = (s or "").replace("\r", "\n")
    keep = [l for l in s.splitlines()
            if l.strip() and not any(w in l for w in ("Uploading", "Downloading",
                                                     "Writing", "Fetching", "Pulling"))]
    return " | ".join(keep)[-n:]


def seed_ref(tag: str) -> tuple[Path, str]:
    """A fresh origin database pushed to its own per-experiment data ref."""
    ref = f"refs/dolt/{RUN}/{tag}"
    REFS.add(ref)
    d = ROOT / tag / "origin"
    d.mkdir(parents=True)
    dolt("init", "--name", "opt", "--email", "opt@local", cwd=d)
    sql(DDL, cwd=d)
    dolt("add", "-A", cwd=d)
    dolt("commit", "-m", "schema", cwd=d)
    dolt("remote", "add", "--ref", ref, "origin", REMOTE, cwd=d)
    p = dolt("push", "origin", "main", cwd=d, timeout=1800)
    if p.returncode != 0:
        raise RuntimeError(f"seed push {tag}: {clean(p.stderr, 200)}")
    return d, ref


def clone_n(tag: str, ref: str, n: int, names=None) -> list[Path]:
    """Clone n times IN PARALLEL — serial cloning cost 50 s for 20 clones.

    GOTCHA (cost a failed run): every parallel `dolt clone` must have its OWN cwd.
    Dolt spools into `<cwd>/.dolt/tmp/nbs-spool-*`, so N clones sharing one parent
    directory collide there and fail with "no such file or directory".
    """
    base = ROOT / tag / "clones"
    base.mkdir(parents=True, exist_ok=True)
    out: list[Path] = [None] * n                                   # type: ignore
    errs: dict[int, str] = {}

    def one(i):
        nm = names[i] if names else f"c{i}"
        pdir = base / f"p{i}"                    # one parent dir per clone
        pdir.mkdir(parents=True, exist_ok=True)
        r = sh(["dolt", "clone", "--ref", ref, REMOTE, nm], cwd=pdir, timeout=1800)
        if r.returncode != 0:
            errs[i] = clean(r.stderr, 120)
            return
        d = pdir / nm
        dolt("config", "--local", "--add", "user.name", nm, cwd=d)
        dolt("config", "--local", "--add", "user.email", f"{nm}@local", cwd=d)
        out[i] = d

    ts = [threading.Thread(target=one, args=(i,)) for i in range(n)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    if errs:
        raise RuntimeError(f"clone failures: {errs}")
    return out


def do_work(d: Path, who: str, n: int, tag: str):
    """n separate local commits, so the push payload is comparable across arms."""
    for j in range(n):
        sql(f"INSERT INTO work (k, who) VALUES ('{tag}-{who}-{j}','{who}')", cwd=d)
        dolt("add", "-A", cwd=d)
        dolt("commit", "-m", f"{who} work {j}", cwd=d)


def push_with_retry(d: Path, branch: str, cap: int) -> tuple[int, bool, float]:
    """Push, and on rejection pull+merge and retry. Returns (attempts, ok, seconds)."""
    t0 = time.perf_counter()
    n = 0
    p = None
    for _ in range(cap):
        n += 1
        p = dolt("push", "origin", branch, cwd=d)
        if p.returncode == 0:
            break
        pl = dolt("pull", "origin", branch, cwd=d)
        if pl.returncode != 0 and "CONFLICT" in ((pl.stdout or "") + (pl.stderr or "")).upper():
            dolt("merge", "--abort", cwd=d)
            break
        time.sleep(0.4 + random.random() * 1.5)
    return n, bool(p and p.returncode == 0), time.perf_counter() - t0


# ---------------------------------------------------------------- O1


def gh_repo() -> str:
    return REMOTE.split("github.com/")[1].removesuffix(".git")


def lock_repo(i: int) -> Path:
    """A tiny git repo per writer whose ONLY job is to hold the lock ref. A dolt
    clone is not a git repo (`.dolt/`, not `.git/`), so the lock cannot be pushed
    from it — but it does not need to be: the lock lives on a DIFFERENT ref, which
    is exactly why it does not contend with the data ref."""
    d = ROOT / "locks" / f"l{i}"
    d.mkdir(parents=True, exist_ok=True)
    sh(["git", "init", "-q", "-b", "main", "."], cwd=d)
    sh(["git", "config", "user.email", f"l{i}@local"], cwd=d)
    sh(["git", "config", "user.name", f"l{i}"], cwd=d)
    # a UNIQUE commit per writer: two contenders must never present the same sha,
    # or a same-value push would look like success to both (invariant 1, at the
    # git layer this time)
    (d / "who").write_text(f"writer {i} {random.getrandbits(64):016x}\n")
    sh(["git", "add", "-A"], cwd=d)
    sh(["git", "commit", "-qm", f"lock token for writer {i}"], cwd=d)
    sh(["git", "remote", "add", "origin", REMOTE], cwd=d)
    return d


LOCK_REF = None


def lock_acquire(d: Path, timeout=600) -> tuple[bool, int, float]:
    """Create-only ref push = an atomic CAS on a ref nobody else's DATA touches.
    Returns (got, tries, seconds)."""
    t0 = time.perf_counter()
    n = 0
    while time.perf_counter() - t0 < timeout:
        n += 1
        r = sh(["git", "push", "origin", f"HEAD:{LOCK_REF}"], cwd=d, timeout=180)
        if r.returncode == 0:
            return True, n, time.perf_counter() - t0
        time.sleep(0.3 + random.random() * 0.7)
    return False, n, time.perf_counter() - t0


def lock_release(d: Path):
    return sh(["git", "push", "origin", f":{LOCK_REF}"], cwd=d, timeout=180)


def o1_contention():
    """Both arms push the SAME single branch — the factory's artifact branch is one
    branch, so branching is not an available answer.

      A  free-for-all: N clones push `main`, retrying on rejection
      B  queued: each acquires an out-of-band lock ref FIRST, then pushes

    The question is whether O(N^2/2) wasted round trips can be turned into N
    sequential ones without changing the data topology at all.
    """
    global LOCK_REF
    results = {}
    for arm in ("A", "B"):
        tag = f"o1{arm.lower()}"
        d0, ref = seed_ref(tag)
        clones = clone_n(tag, ref, N_CLONES)
        for i, d in enumerate(clones):
            do_work(d, f"c{i}", N_WORK, f"o1{arm}")
        locks = [lock_repo(i) for i in range(N_CLONES)] if arm == "B" else []
        if arm == "B":
            LOCK_REF = f"refs/locks/{RUN}-artifacts"
            sh(["git", "push", REMOTE, f":{LOCK_REF}"], timeout=120)   # ensure free
        attempts, oks, lock_tries, lock_s = {}, {}, {}, {}
        bar = threading.Barrier(N_CLONES)

        def worker(i):
            bar.wait()
            if arm == "B":
                got, lt, ls = lock_acquire(locks[i])
                lock_tries[i], lock_s[i] = lt, ls
                if not got:
                    attempts[i], oks[i] = 0, False
                    return
                try:
                    attempts[i], oks[i], _ = push_with_retry(clones[i], "main",
                                                             N_CLONES + 8)
                finally:
                    lock_release(locks[i])
            else:
                attempts[i], oks[i], _ = push_with_retry(clones[i], "main", N_CLONES + 8)

        t0 = time.perf_counter()
        ts = [threading.Thread(target=worker, args=(i,)) for i in range(N_CLONES)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        wall = time.perf_counter() - t0
        if arm == "B":
            sh(["git", "push", REMOTE, f":{LOCK_REF}"], timeout=120)
        v = ROOT / tag / "verify"
        v.mkdir(parents=True, exist_ok=True)
        sh(["dolt", "clone", "--ref", ref, REMOTE, "f"], cwd=v, timeout=1800)
        landed = val(sql(f"SELECT COUNT(*) FROM work WHERE k LIKE 'o1{arm}-%'",
                         cwd=v / "f"))
        results[arm] = {
            "attempts": [attempts.get(i, 0) for i in range(N_CLONES)],
            "total_attempts": sum(attempts.values()),
            "wall": wall, "landed": landed,
            "ok": sum(1 for i in oks if oks[i]),
            "lock_tries": [lock_tries.get(i, 0) for i in range(N_CLONES)],
            "lock_wait_med": statistics.median(lock_s.values()) if lock_s else 0,
        }
    a, b = results["A"], results["B"]
    expected = N_CLONES * N_WORK
    ok = (a["landed"] == str(expected) and b["landed"] == str(expected)
          and b["ok"] == N_CLONES and a["ok"] == N_CLONES)
    FACTS["o1"] = results
    waste_a = a["total_attempts"] - N_CLONES
    waste_b = b["total_attempts"] - N_CLONES
    check(f"O1 CONTENTION on ONE branch: {N_CLONES} clones x {N_WORK} commits — "
          f"free-for-all vs queued",
          ok,
          f"A  free-for-all, everyone pushes `main` and retries on rejection\n"
          f"     data-push attempts : {a['attempts']}  total {a['total_attempts']}\n"
          f"     WASTED round trips : {waste_a}   "
          f"(O(N) for {N_CLONES} predicts {N_CLONES*(N_CLONES+1)//2} total)\n"
          f"     wall clock         : {a['wall']:.0f}s      rows on main "
          f"{a['landed']}/{expected}\n"
          f"B  queued behind a create-only lock ref, then push `main`\n"
          f"     data-push attempts : {b['attempts']}  total {b['total_attempts']}\n"
          f"     WASTED round trips : {waste_b}\n"
          f"     lock acquire tries : {b['lock_tries']}  median wait "
          f"{b['lock_wait_med']:.0f}s\n"
          f"     wall clock         : {b['wall']:.0f}s      rows on main "
          f"{b['landed']}/{expected}\n"
          f"=> {a['wall']/max(b['wall'],0.01):.2f}x wall clock, and wasted data pushes\n"
          f"   {waste_a} -> {waste_b}. SAME single branch, same rows landed. The lock\n"
          f"   lives on a DIFFERENT ref, so it never contends with the data ref, and a\n"
          f"   loser waits cheaply instead of doing a full push it will have to discard.\n"
          f"   Honest costs: (1) ~2 extra network ops per push; (2) a remote ref lock has\n"
          f"   NO kernel release — unlike flock it needs a TTL and a break-glass path;\n"
          f"   (3) each contender must present a UNIQUE sha or same-value pushes both\n"
          f"   'succeed' — invariant 1 reappearing at the git layer.\n"
          f"   For reference, branch-per-writer measured 1 attempt each (S5/S2-spike) —\n"
          f"   but that is NOT applicable here: it fragments the single artifact branch.")


# ---------------------------------------------------------------- O2


def o2_invocations(argv_agent=False):
    """How much of the LOCAL phase is process spawn? 3 dolt calls per unit vs 1."""
    d0, ref = seed_ref("o2")
    clones = clone_n("o2", ref, N_MACH)
    env = dict(os.environ)
    for i, d in enumerate(clones):
        env[f"FA_OPT_CLONE_{i}"] = str(d)
    arms = {}
    for arm in ("A", "B"):
        procs = []
        for i in range(N_MACH):
            for j in range(N_AG):
                procs.append(subprocess.Popen(
                    [sys.executable, SELF, "--agent", str(i), str(j), arm],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env))
        t0 = time.perf_counter()
        [p.wait() for p in procs]
        wall = time.perf_counter() - t0
        rows = []
        for i in range(N_MACH):
            for j in range(N_AG):
                f = RES / f"{arm}-{i}-{j}.json"
                if f.exists():
                    rows.append(json.loads(f.read_text()))
        n_ok = sum(1 for r in rows if r["ok"])
        holds = [r["hold_s"] for r in rows if r["ok"]]
        arms[arm] = {"wall": wall, "ok": n_ok, "n": N_MACH * N_AG,
                     "hold_med": statistics.median(holds) if holds else 0}
    a, b = arms["A"], arms["B"]
    # both arms wrote to every clone; confirm nothing was lost either way
    counts = [val(sql("SELECT COUNT(*) FROM work", cwd=d)) for d in clones]
    ok = (a["ok"] == a["n"] and b["ok"] == b["n"]
          and all(c == str(N_AG * 2) for c in counts))
    FACTS["o2"] = arms
    check(f"O2 INVOCATIONS: {N_MACH*N_AG} local units, 3 dolt spawns per unit vs 1",
          ok,
          f"A  write + `dolt add -A` + `dolt commit`  (3 spawns)\n"
          f"     wall {a['wall']:.1f}s   median mutex hold {a['hold_med']:.2f}s   "
          f"ok {a['ok']}/{a['n']}\n"
          f"B  one `dolt sql` doing the write AND CALL DOLT_COMMIT  (1 spawn)\n"
          f"     wall {b['wall']:.1f}s   median mutex hold {b['hold_med']:.2f}s   "
          f"ok {b['ok']}/{b['n']}\n"
          f"rows per clone: {counts} (expected {N_AG*2} each — both arms landed)\n"
          f"=> {a['wall']/max(b['wall'],0.01):.1f}x on the local path, purely by not\n"
          f"   paying the ~136 ms spawn floor three times per unit of work. The mutex\n"
          f"   hold shrinks with it, which is what lets a clone absorb more agents.")


def agent_main(argv):
    """--agent <clone_idx> <agent_id> <arm>"""
    i, j, arm = argv[0], argv[1], argv[2]
    d = Path(os.environ[f"FA_OPT_CLONE_{i}"])
    key = f"{arm}-{i}-{j}"
    out = {"key": key, "ok": False, "hold_s": 0.0}
    ins = (f"INSERT INTO work (k, who) VALUES ('{key}','c{i}')")
    t0 = time.perf_counter()
    with clone_write_lock(d, timeout=3600):
        t_hold = time.perf_counter()
        if arm == "A":
            r1 = sql(ins, cwd=d)
            dolt("add", "-A", cwd=d)
            r2 = dolt("commit", "-m", key, cwd=d)
            out["ok"] = r1.returncode == 0 and r2.returncode == 0
        else:
            r = sql(f"START TRANSACTION;{ins};COMMIT;"
                    f"CALL DOLT_COMMIT('-Am','{key}');", cwd=d)
            out["ok"] = r.returncode == 0
        out["hold_s"] = round(time.perf_counter() - t_hold, 3)
    out["total_s"] = round(time.perf_counter() - t0, 3)
    RES.mkdir(parents=True, exist_ok=True)
    (RES / f"{key}.json").write_text(json.dumps(out))
    return 0


# ---------------------------------------------------------------- O3


def o3_push_cost():
    """Why did pushes reach ~3 minutes? Push duration vs unpushed commit count."""
    d, ref = seed_ref("o3")
    rows = []
    for n_commits in (1, 5, 20, 50):
        for j in range(n_commits):
            sql(f"INSERT INTO work (k, who) VALUES ('o3-{n_commits}-{j}','x')", cwd=d)
            dolt("add", "-A", cwd=d)
            dolt("commit", "-m", f"c{n_commits}-{j}", cwd=d)
        t0 = time.perf_counter()
        p = dolt("push", "origin", "main", cwd=d, timeout=1800)
        dt = time.perf_counter() - t0
        n_log = val(sql("SELECT COUNT(*) FROM dolt_log", cwd=d))
        rows.append((n_commits, dt, p.returncode, n_log))
    # does gc help?
    t0 = time.perf_counter()
    g = dolt("gc", cwd=d, timeout=1800)
    gc_s = time.perf_counter() - t0
    for j in range(20):
        sql(f"INSERT INTO work (k, who) VALUES ('o3-post-{j}','x')", cwd=d)
        dolt("add", "-A", cwd=d)
        dolt("commit", "-m", f"post{j}", cwd=d)
    t0 = time.perf_counter()
    p2 = dolt("push", "origin", "main", cwd=d, timeout=1800)
    post_gc = time.perf_counter() - t0
    per = [(n, dt / n) for n, dt, _, _ in rows]
    ok = all(rc == 0 for _, _, rc, _ in rows) and p2.returncode == 0
    FACTS["o3"] = rows
    check("O3 PUSH COST: does push time track unpushed commits or total history?",
          ok,
          "\n".join(f"  {n:>2} unpushed commits -> push {dt:6.1f}s "
                    f"({dt/n:5.2f}s per commit)   history now {log}"
                    for (n, dt, rc, log) in rows)
          + f"\n  after `dolt gc` ({gc_s:.0f}s): 20 commits -> push {post_gc:.1f}s "
            f"({post_gc/20:.2f}s per commit)\n"
          + f"=> per-commit cost {'FALLS' if per[-1][1] < per[0][1] else 'RISES'} as the\n"
            f"   batch grows ({per[0][1]:.2f}s -> {per[-1][1]:.2f}s per commit), so pushing\n"
            f"   MORE work per push is cheaper per unit — the same conclusion invariant 6\n"
            f"   reaches for transactions. A push has a fixed cost you pay either way.")


# ---------------------------------------------------------------- main


def cleanup():
    if os.environ.get("FA_GH_KEEP"):
        print(f"--- keeping refs: {sorted(REFS)}")
        return
    out = []
    for ref in sorted(REFS):
        r = sh(["git", "push", REMOTE, f":{ref}"], timeout=180)
        out.append(f"{ref.split('/')[-1]}={'ok' if r.returncode == 0 else r.returncode}")
    print(f"--- cleanup: {'; '.join(out)}")


def main():
    print(f"=== OPTIMISATION A/B  run={RUN}\n    remote={REMOTE}\n"
          f"    O1: {N_CLONES} clones x {N_WORK} commits | O2: {N_MACH} clones x {N_AG} agents\n",
          flush=True)
    if ROOT.exists():
        shutil.rmtree(ROOT)
    RES.mkdir(parents=True)
    try:
        for fn in (o1_contention, o2_invocations, o3_push_cost):
            if ONLY and fn.__name__.split('_')[0] not in ONLY:
                continue
            try:
                fn()
            except Exception:                                       # noqa: BLE001
                import traceback
                check(f"{fn.__name__} (ERROR)", False, traceback.format_exc()[-700:])
            print(flush=True)
    finally:
        cleanup()
    npass = sum(1 for _, ok, _ in RESULTS if ok)
    print("=" * 74)
    print(f"{npass}/{len(RESULTS)} passed")
    sys.exit(0 if npass == len(RESULTS) else 1)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--agent":
        sys.exit(agent_main(sys.argv[2:]))
    main()
