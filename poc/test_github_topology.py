#!/usr/bin/env python3
"""FINAL TESTS, part 2 — the file:// scenarios RE-RUN against the real GitHub remote.

`poc/test_github_remote.py` covered remote MECHANICS (push, clone, lease latency,
contention, invariant 4, one-ref, in-process remote ops, failure modes). It did NOT
re-run the merge-semantics and topology scenarios that the earlier suites proved
only against a `file://` stand-in. This closes that.

Ported here, one test per original:

  H1  cross-machine cell-level merge, same row / different columns   (M3, D2)
  H2  same-cell edit surfaces a conflict; identical writes coalesce  (M4, D3, D4)
  H3  an unresolved conflict WEDGES the clone; the abort guard saves it  (D8)
  H4  THE TARGET TOPOLOGY: 2 machines x 4 agent processes, flock + network  (D1)
  H5  a lease contended by 8 agents across 2 fleets -> one holder     (D6)
  H6  cross-machine counters: mutable cell lossy vs append-only exact (D5, D5b)
  H7  no cross-machine read consistency without a pull; its real cost (D7, inv 5)
  H8  do all Dolt branches survive a git-remote fetch? graduate / abandon (I4,I5,I8)
  H9  two instances refining the SAME record -> conflict at merge     (I6)
  H10 schema evolution across machines: different cols merge, same col conflicts (E5,E6)
  H11 8 clones pushing at once -> is it still linear O(N) over the network? (SC5)

Run: .venv/bin/python -u poc/test_github_topology.py
Env: FA_GH_REMOTE, FA_GT_CLONES (default 8, for H11), FA_GH_TIMEOUT, FA_GH_KEEP
Also runs as a child: --agent <machine> <sql> <mode> [tries] [gap]
"""
from __future__ import annotations

import os
import random
import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from clonelock import clone_write_lock  # noqa: E402

POC = Path(__file__).parent
ROOT = POC / "gt"
SELF = str(Path(__file__).resolve())
REMOTE = os.environ.get("FA_GH_REMOTE",
                        "https://github.com/drbothen/dolt-artifact-spike-remote.git")
RUN = os.environ.get("FA_GT_RUN") or f"gt-{int(time.time())}"
DATA_REF = f"refs/dolt/{RUN}/data"
TIMEOUT = int(os.environ.get("FA_GH_TIMEOUT", 300))
N_PUSHERS = int(os.environ.get("FA_GT_CLONES", 8))

RESULTS: list[tuple[str, bool, str]] = []
REFS_CREATED: set[str] = {DATA_REF}

DDL = (
    "CREATE TABLE rec (id VARCHAR(32) PRIMARY KEY, title VARCHAR(200) NULL, "
    "capability VARCHAR(32) NULL, notes VARCHAR(200) NULL);"
    "CREATE TABLE lock1 (id TINYINT PRIMARY KEY, holder VARCHAR(64) NULL, "
    "token VARCHAR(64) NULL);"
    "CREATE TABLE ctr (id TINYINT PRIMARY KEY, n INT NOT NULL);"
    "CREATE TABLE ctr_events (k VARCHAR(72) PRIMARY KEY, agent VARCHAR(32) NOT NULL);"
    "CREATE TABLE work (k VARCHAR(72) PRIMARY KEY, agent VARCHAR(32) NOT NULL);"
    "INSERT INTO lock1 (id, holder, token) VALUES (1, NULL, NULL);"
    "INSERT INTO ctr (id, n) VALUES (1, 0);"
)
SEED_ROWS = "".join(
    f"INSERT INTO rec (id,title,capability,notes) VALUES ('R{i}','seed',NULL,NULL);"
    for i in range(1, 12))


# ---------------------------------------------------------------- plumbing


def check(name, ok, detail=""):
    RESULTS.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}")
    for ln in (detail or "").splitlines():
        print(f"        {ln}")


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


def row(r):
    lines = [l for l in (r.stdout or "").strip().splitlines() if l.strip()]
    return lines[1] if len(lines) > 1 else ""


def clean(s: str, n=140) -> str:
    s = (s or "").replace("\r", "\n")
    keep = [l for l in s.splitlines()
            if l.strip() and not any(w in l for w in
                                     ("Uploading", "Downloading", "Writing", "Fetching"))]
    return " | ".join(keep)[-n:]


def identity(d: Path, who: str):
    dolt("config", "--local", "--add", "user.name", who, cwd=d)
    dolt("config", "--local", "--add", "user.email", f"{who}@local", cwd=d)


def clone(name: str, parent: Path) -> Path:
    parent.mkdir(parents=True, exist_ok=True)
    r = sh(["dolt", "clone", "--ref", DATA_REF, REMOTE, name], cwd=parent)
    d = parent / name
    if r.returncode != 0:
        raise RuntimeError(f"clone {name}: {clean(r.stderr)}")
    identity(d, name)
    return d


def sync_reset(d: Path):
    """Discard local divergence and take the remote as truth."""
    dolt("merge", "--abort", cwd=d)
    dolt("fetch", "origin", cwd=d)
    dolt("reset", "--hard", "origin/main", cwd=d)


def commit(d: Path, msg: str):
    dolt("add", "-A", cwd=d)
    return dolt("commit", "-m", msg, cwd=d)


def push(d: Path, branch="main"):
    return dolt("push", "origin", branch, cwd=d)


def merge_remote(d: Path):
    """fetch + merge origin/main. Returns (rc, conflicted, text)."""
    dolt("fetch", "origin", cwd=d)
    m = dolt("merge", "origin/main", "--no-edit", cwd=d)
    blob = ((m.stdout or "") + (m.stderr or ""))
    conflicted = "conflict" in blob.lower()
    if not conflicted:
        c = sql("SELECT COUNT(*) FROM dolt_conflicts", cwd=d)
        try:
            conflicted = int(val(c) or 0) > 0
        except (TypeError, ValueError):
            pass
    return m.returncode, conflicted, clean(blob)


# ---------------------------------------------------------------- agent child


MACHINES: dict[str, Path] = {}


def agent_main(argv):
    """One agent = one OS process, exactly as test_two_devs.py models it:
    mutex around the WHOLE unit (pull, write, commit, push), abort on conflict,
    idempotent retry, bounded attempts."""
    m, stmt, mode = argv[0], argv[1], argv[2]
    tries = int(argv[3]) if len(argv) > 3 else 4
    gap = float(argv[4]) if len(argv) > 4 else 0.0
    cwd = Path(os.environ["FA_GT_MACHINE_" + m])

    # mode=stale-retry is the UNSAFE retry shape D5 isolated: on rejection, merge
    # and re-push the value already computed, WITHOUT re-executing the read-modify-
    # write. Two machines that computed the same next value then coalesce into one.
    if mode == "stale-retry":
        with clone_write_lock(cwd, timeout=600):
            pl = dolt("pull", "origin", "main", cwd=cwd)
            if pl.returncode != 0:
                dolt("merge", "--abort", cwd=cwd)
                print("FAIL:pull")
                return 0
            if gap:
                time.sleep(gap)
            if dolt("sql", "-q", stmt, cwd=cwd).returncode != 0:
                print("FAIL:write")
                return 0
            dolt("add", "-A", cwd=cwd)
            dolt("commit", "-m", f"{m}: stale-retry write", cwd=cwd)
            for attempt in range(6):
                ps = push(cwd)
                if ps.returncode == 0:
                    print(f"OK:pushed:attempt{attempt+1}")
                    return 0
                dolt("fetch", "origin", cwd=cwd)
                mg = dolt("merge", "origin/main", "--no-edit", cwd=cwd)
                if mg.returncode != 0:
                    dolt("merge", "--abort", cwd=cwd)
                    print("FAIL:conflict-aborted")
                    return 0
                dolt("add", "-A", cwd=cwd)
                dolt("commit", "-m", f"{m}: merge", cwd=cwd)
                time.sleep(0.3 * (attempt + 1))
        print("FAIL:exhausted")
        return 0

    for attempt in range(tries):
        try:
            with clone_write_lock(cwd, timeout=600):
                if mode in ("sync", "naive"):
                    pl = dolt("pull", "origin", "main", cwd=cwd)
                    if pl.returncode != 0:
                        blob = ((pl.stdout or "") + (pl.stderr or "")).upper()
                        if "CONFLICT" in blob:
                            dolt("merge", "--abort", cwd=cwd)
                            print("FAIL:conflict-aborted")
                            return 0
                        print(f"FAIL:pull:{clean(pl.stderr or pl.stdout, 70)}")
                        return 0
                if gap:
                    time.sleep(gap)
                w = dolt("sql", "-q", stmt, cwd=cwd)
                if w.returncode != 0:
                    blob = ((w.stderr or "") + (w.stdout or "")).lower()
                    if not ("duplicate" in blob or "unique" in blob):
                        print(f"FAIL:write:{clean(w.stderr or w.stdout, 70)}")
                        return 0
                    # already applied on an earlier attempt -> fall through to push
                dolt("add", "-A", cwd=cwd)
                cm = dolt("commit", "-m", f"{m}: agent write", cwd=cwd)
                blob = (cm.stdout or "") + (cm.stderr or "")
                if cm.returncode != 0 and "nothing to commit" not in blob \
                        and "no changes added" not in blob:
                    print(f"FAIL:commit:{clean(blob, 70)}")
                    return 0
                if mode == "local":
                    print("OK")
                    return 0
                ps = push(cwd)
                if ps.returncode == 0:
                    print(f"OK:pushed:attempt{attempt+1}")
                    return 0
            time.sleep(0.3 * (attempt + 1))
        except Exception as e:                                  # noqa: BLE001
            print(f"FAIL:exc:{type(e).__name__}:{e}")
            return 0
    print("FAIL:exhausted")
    return 0


def spawn(m, stmt, mode="sync", tries=5, gap=0.0):
    env = dict(os.environ)
    for k, v in MACHINES.items():
        env["FA_GT_MACHINE_" + k] = str(v)
    return subprocess.Popen(
        [sys.executable, SELF, "--agent", m, stmt, mode, str(tries), str(gap)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)


def run_fleet(jobs, timeout=1800, **kw):
    procs = [(j[0], spawn(*j, **kw)) for j in jobs]
    out = []
    for m, p in procs:
        try:
            o, e = p.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            p.kill()
            o, e = "", "TIMEOUT"
        out.append((m, (o or "").strip(), (e or "").strip()[:120]))
    return out


# ---------------------------------------------------------------- setup


def setup():
    if ROOT.exists():
        shutil.rmtree(ROOT)
    ROOT.mkdir(parents=True)
    d = ROOT / "origin" / "db"
    d.mkdir(parents=True)
    if dolt("init", "--name", "gt", "--email", "gt@local", cwd=d).returncode != 0:
        raise RuntimeError("dolt init failed")
    for stmt in (DDL, SEED_ROWS):
        r = sql(stmt, cwd=d)
        if r.returncode != 0:
            raise RuntimeError(f"ddl: {clean(r.stderr, 200)}")
    commit(d, "schema + seed")
    if dolt("remote", "add", "--ref", DATA_REF, "origin", REMOTE, cwd=d).returncode != 0:
        raise RuntimeError("remote add failed")
    p = push(d)
    if p.returncode != 0:
        raise RuntimeError(f"seed push failed: {clean(p.stderr, 200)}")
    print(f"--- seeded {DATA_REF} ({clean(p.stderr, 60) or 'ok'})")
    return d


# ---------------------------------------------------------------- H1 / H2


def h1_cell_merge(ma, mb):
    sync_reset(ma)
    sync_reset(mb)
    sql("UPDATE rec SET capability='CAP-A' WHERE id='R1'", cwd=ma)
    commit(ma, "A sets capability")
    pa = push(ma)
    sql("UPDATE rec SET notes='B note' WHERE id='R1'", cwd=mb)
    commit(mb, "B sets notes")
    rc, conflicted, txt = merge_remote(mb)
    got = row(sql("SELECT capability, notes FROM rec WHERE id='R1'", cwd=mb))
    pb = push(mb)
    ok = (pa.returncode == 0 and not conflicted and pb.returncode == 0
          and "CAP-A" in got and "B note" in got)
    check("H1 cell-level merge across machines, same row / different columns (M3, D2)",
          ok,
          f"A pushed capability (rc={pa.returncode}); B held notes locally\n"
          f"B merged origin/main: rc={rc} conflicted={conflicted} {txt}\n"
          f"row on B after merge: {got}   (both values must survive)\n"
          f"B pushed the merge: rc={pb.returncode}\n"
          f"=> the property markdown cannot have, now proven over the network and not\n"
          f"   just file://: two agents edited ONE artifact and neither lost work.")


def h2_same_cell(ma, mb):
    # (a) different values on the same cell -> must conflict
    sync_reset(ma)
    sync_reset(mb)
    sql("UPDATE rec SET title='A-title' WHERE id='R2'", cwd=ma)
    commit(ma, "A title")
    push(ma)
    sql("UPDATE rec SET title='B-title' WHERE id='R2'", cwd=mb)
    commit(mb, "B title")
    rc, conflicted, txt = merge_remote(mb)
    nconf = val(sql("SELECT COUNT(*) FROM dolt_conflicts", cwd=mb))
    dolt("merge", "--abort", cwd=mb)
    # (b) IDENTICAL value from both -> coalesces, no conflict (D4)
    sync_reset(mb)
    sql("UPDATE rec SET title='SAME' WHERE id='R3'", cwd=ma)
    commit(ma, "A same")
    push(ma)
    sql("UPDATE rec SET title='SAME' WHERE id='R3'", cwd=mb)
    commit(mb, "B same")
    rc2, conflicted2, txt2 = merge_remote(mb)
    push(mb)
    ok = conflicted and not conflicted2
    check("H2 same-cell edits: different values CONFLICT, identical values COALESCE (M4, D3, D4)",
          ok,
          f"(a) A='A-title' vs B='B-title' on rec.R2.title\n"
          f"    B merge: rc={rc} conflicted={conflicted} dolt_conflicts={nconf}\n"
          f"    {txt}\n"
          f"(b) both write title='SAME' on rec.R3\n"
          f"    B merge: rc={rc2} conflicted={conflicted2}  {txt2}\n"
          f"=> nothing is lost SILENTLY (a), and an identical write is not a conflict (b).\n"
          f"   (b) is why a counter must never be a mutable cell — see H6.")


# ---------------------------------------------------------------- H3


def h3_wedge(mw):
    """The operational landmine: an unresolved conflict fails EVERY later commit by
    ANY agent on that clone, with an error that blames staging."""
    try:
        sync_reset(mw)
        # make the remote diverge from mw on the same cell
        sql("UPDATE rec SET title='remote-wins' WHERE id='R4'", cwd=mw)
        commit(mw, "mw local")
        # a different clone pushes a conflicting value first
        other = clone("wedge_other", ROOT / "wedge")
        sql("UPDATE rec SET title='other-wins' WHERE id='R4'", cwd=other)
        commit(other, "other")
        po = push(other)
        rc, conflicted, txt = merge_remote(mw)     # deliberately NOT aborted
        st = sql("SELECT COUNT(*) FROM dolt_conflicts", cwd=mw)
        # an unrelated agent tries to COMMIT its own unit of work on this clone
        sql("INSERT INTO work (k,agent) VALUES ('h3-unrelated','other-agent')", cwd=mw)
        cm = commit(mw, "unrelated agent work")
        cblob = clean((cm.stdout or "") + (cm.stderr or ""), 190)
        # ...and to PULL, which is the path D8's misleading message came from
        pl = dolt("pull", "origin", "main", cwd=mw)
        pblob = clean((pl.stdout or "") + (pl.stderr or ""), 190)
        wedged = cm.returncode != 0
        pull_wedged = pl.returncode != 0
        names_conflict = "conflict" in (cblob + pblob).lower()
        blames_staging = "uncommitted changes" in (cblob + pblob).lower()
        # the guard: abort, and the clone is usable again
        dolt("merge", "--abort", cwd=mw)
        sync_reset(mw)
        sql("INSERT INTO work (k,agent) VALUES ('h3-after-abort','other-agent')", cwd=mw)
        cm2 = commit(mw, "after abort")
        ok = (po.returncode == 0 and conflicted and wedged and pull_wedged
              and cm2.returncode == 0)
        verdict = ("both messages NAME the conflict, so on dolt 2.2.3 this path is\n"
                   "   diagnosable — D8's `cannot merge with uncommitted changes` (which\n"
                   "   blames staging) did NOT reproduce here"
                   if names_conflict and not blames_staging else
                   "at least one message blames STAGING rather than the conflict, as D8\n"
                   "   recorded — the failure points at the wrong thing")
        check("H3 an unresolved conflict WEDGES the clone; abort restores it (D8)",
              ok,
              f"other clone pushed the conflicting value: rc={po.returncode}\n"
              f"mw merged WITHOUT the guard: rc={rc} conflicted={conflicted} "
              f"dolt_conflicts={val(st)}\n"
              f"then, on that same clone:\n"
              f"  an unrelated agent's COMMIT: rc={cm.returncode} "
              f"{'WEDGED' if wedged else 'still worked'}\n"
              f"    {cblob}\n"
              f"  an unrelated agent's PULL  : rc={pl.returncode} "
              f"{'WEDGED' if pull_wedged else 'still worked'}\n"
              f"    {pblob}\n"
              f"  message names the conflict: {names_conflict}   blames staging: "
              f"{blames_staging}\n"
              f"after `merge --abort` + reset, a commit works again: rc={cm2.returncode}\n"
              f"=> the WEDGE reproduces over a real remote: one careless agent stops every\n"
              f"   other agent sharing that clone from committing OR pulling, so invariant 2\n"
              f"   (abort in the code path) is load-bearing. On the diagnosability question,\n"
              f"   {verdict}.")
    finally:
        dolt("merge", "--abort", cwd=mw)
        sync_reset(mw)


# ---------------------------------------------------------------- H4 / H5


def h4_topology(ma, mb):
    """4 agents per machine, disjoint rows, flock locally + push over the network."""
    sync_reset(ma)
    sync_reset(mb)
    jobs = []
    for i in range(4):
        jobs.append(("A", f"INSERT INTO work (k,agent) VALUES ('h4-A{i}','A{i}')"))
        jobs.append(("B", f"INSERT INTO work (k,agent) VALUES ('h4-B{i}','B{i}')"))
    t0 = time.perf_counter()
    out = run_fleet(jobs, tries=8)
    dt = time.perf_counter() - t0
    ok_n = sum(1 for _, o, _ in out if o.startswith("OK"))
    manifest = sum(1 for _, o, e in out if "manifest" in (o + e).lower())
    sync_reset(ma)
    sync_reset(mb)
    na = val(sql("SELECT COUNT(*) FROM work WHERE k LIKE 'h4-%'", cwd=ma))
    nb = val(sql("SELECT COUNT(*) FROM work WHERE k LIKE 'h4-%'", cwd=mb))
    ok = ok_n == 8 and na == "8" and nb == "8" and manifest == 0
    check("H4 THE TARGET TOPOLOGY over GitHub: 2 machines x 4 agent processes (D1)",
          ok,
          f"agents reporting OK        : {ok_n}/8   in {dt:.0f} s wall clock\n"
          f"`cannot update manifest`   : {manifest} (must be 0 — the flock mutex's job)\n"
          f"rows visible on A / on B   : {na} / {nb} (both must be 8 — convergence)\n"
          + "\n".join(f"  {m}: {o}" for m, o, _ in out) + "\n"
          f"=> flock orders each machine's agents, push-rejection arbitrates between\n"
          f"   machines, cell-merge reconciles. Proven on file:// in D1; now proven\n"
          f"   against github.com, where every retry costs a real round trip.")


def h5_lease_two_fleets(ma, mb):
    sync_reset(ma)
    sync_reset(mb)
    sql("UPDATE lock1 SET holder=NULL, token=NULL WHERE id=1", cwd=ma)
    commit(ma, "free the lease")
    push(ma)
    sync_reset(mb)
    jobs = []
    for i in range(4):
        for m in ("A", "B"):
            tok = f"{m}{i}-{random.getrandbits(32):08x}"
            jobs.append((m, f"UPDATE lock1 SET holder='{m}{i}', token='{tok}' "
                            f"WHERE id=1 AND holder IS NULL"))
    out = run_fleet(jobs, tries=1)          # ONE attempt each: this is a race, not a retry
    pushed = [m + ":" + o for m, o, _ in out if o.startswith("OK:pushed")]
    sync_reset(ma)
    sync_reset(mb)
    ha = val(sql("SELECT holder FROM lock1 WHERE id=1", cwd=ma))
    hb = val(sql("SELECT holder FROM lock1 WHERE id=1", cwd=mb))
    ok = ha == hb and ha not in (None, "", "NULL") and len(pushed) >= 1
    check("H5 a lease contended by 8 agents across 2 fleets -> ONE holder (D6)",
          ok,
          f"agents that pushed a successful acquire: {len(pushed)}\n"
          f"  {pushed}\n"
          f"holder as seen by machine A / machine B : {ha} / {hb} (must be identical)\n"
          f"=> several agents can WRITE the row locally (each machine's mutex only\n"
          f"   orders its own), but the remote collapses them to one holder both\n"
          f"   machines agree on. Same result as D6 on file://.")


# ---------------------------------------------------------------- H6


def h6_counters(ma, mb):
    """Three retry shapes on the same increment, so the variable is isolated:
    (a) merge-and-repush WITHOUT recomputing -> the D5 loss
    (b) recompute on every attempt          -> exact, but only by luck of discipline
    (c) append-only rows with unique keys   -> exact by construction (invariant 3)"""
    def reset_ctr():
        sync_reset(ma)
        sync_reset(mb)
        sql("UPDATE ctr SET n=0 WHERE id=1", cwd=ma)
        commit(ma, "ctr=0")
        push(ma)
        sync_reset(mb)

    inc = "UPDATE ctr SET n = n + 1 WHERE id=1"
    # (a) the unsafe shape: both machines compute 0+1, then merge and re-push it
    reset_ctr()
    out_a = run_fleet([("A", inc), ("B", inc)], mode="stale-retry", gap=3.0)
    sync_reset(ma)
    n_a = val(sql("SELECT n FROM ctr WHERE id=1", cwd=ma))
    ok_a = sum(1 for _, o, _ in out_a if o.startswith("OK"))
    lossy = ok_a == 2 and str(n_a) == "1"
    # (b) the safe shape: each attempt re-executes the read-modify-write
    reset_ctr()
    out_b = run_fleet([("A", inc), ("B", inc)], mode="sync", tries=6, gap=3.0)
    sync_reset(ma)
    n_b = val(sql("SELECT n FROM ctr WHERE id=1", cwd=ma))
    ok_b = sum(1 for _, o, _ in out_b if o.startswith("OK"))
    exact_b = ok_b == 2 and str(n_b) == "2"
    # (c) append-only rows with unique keys
    sync_reset(mb)
    jobs = [(m, f"INSERT INTO ctr_events (k,agent) VALUES ('h6-{m}{i}','{m}')")
            for m in ("A", "B") for i in range(3)]
    out_c = run_fleet(jobs, tries=8)
    sync_reset(ma)
    n_ev = val(sql("SELECT COUNT(*) FROM ctr_events WHERE k LIKE 'h6-%'", cwd=ma))
    ok_c = sum(1 for _, o, _ in out_c if o.startswith("OK"))
    exact_c = str(n_ev) == str(ok_c) == "6"
    check("H6 cross-machine counters: which RETRY SHAPE loses data (D5, D5b)",
          lossy and exact_c,
          f"(a) merge-and-repush WITHOUT recomputing (the unsafe shape):\n"
          f"    agents reporting success: {ok_a}/2   counter landed at: {n_a}   "
          f"SILENT LOSS={lossy}\n"
          f"    {[o for _, o, _ in out_a]}\n"
          f"(b) recompute the read-modify-write on every attempt:\n"
          f"    agents ok: {ok_b}/2   counter landed at: {n_b}   EXACT={exact_b}\n"
          f"(c) append-only rows with unique keys, 3 per machine:\n"
          f"    agents ok: {ok_c}/6   rows on the remote: {n_ev}   EXACT={exact_c}\n"
          f"=> the difference between (a) and (b) is ONE line of retry logic, and (a)\n"
          f"   reports SUCCESS to both agents while losing an increment — no error\n"
          f"   anywhere. (c) cannot express the bug at all, which is why invariant 3\n"
          f"   says counters are ROWS. Confirmed over github.com, not just file://.")


# ---------------------------------------------------------------- H7


def h7_staleness(ma, mb):
    sync_reset(ma)
    sync_reset(mb)
    tag = f"stale-{random.getrandbits(24):06x}"
    sql(f"UPDATE rec SET notes='{tag}' WHERE id='R5'", cwd=ma)
    commit(ma, "A writes R5")
    pa = push(ma)
    before = val(sql("SELECT notes FROM rec WHERE id='R5'", cwd=mb))
    costs = []
    for _ in range(3):
        t0 = time.perf_counter()
        dolt("pull", "origin", "main", cwd=mb)
        costs.append((time.perf_counter() - t0) * 1000)
    after = val(sql("SELECT notes FROM rec WHERE id='R5'", cwd=mb))
    ok = pa.returncode == 0 and before != tag and after == tag
    check("H7 no cross-machine read consistency without a pull; the real cost (D7, invariant 5)",
          ok,
          f"A wrote+pushed notes='{tag}'\n"
          f"B read BEFORE pulling : {before}   (stale — correct behaviour)\n"
          f"B read AFTER pulling  : {after}\n"
          f"pull cost over github : median {statistics.median(costs):.0f} ms "
          f"(3 pulls: {[f'{c:.0f}' for c in costs]})\n"
          f"  vs ~150 ms measured on file:// in D7\n"
          f"=> invariant 5 ('pull at the start of every unit of work') now has its real\n"
          f"   price. It is per-unit-of-work, not per-write, for exactly this reason.")


# ---------------------------------------------------------------- H8 / H9


def h8_branches_over_one_ref(ma, mb):
    """G7 found that every Dolt branch lives in ONE git ref. The consequence nobody
    checked: does a git-remote FETCH still deliver every branch to another clone?
    And do graduate (merge to main) and abandon (delete) work through it?"""
    sync_reset(ma)
    inst = f"inst_{RUN.replace('-', '_')}"
    dolt("checkout", "-b", inst, cwd=ma)
    sql(f"INSERT INTO work (k,agent) VALUES ('h8-{inst}','spike')", cwd=ma)
    commit(ma, "spike work on an instance branch")
    pi = push(ma, inst)
    # does the OTHER clone see the branch after a fetch?
    dolt("fetch", "origin", cwd=mb)
    br = sql("SELECT name FROM dolt_branches ORDER BY name", cwd=mb)
    remote_br = sh(["dolt", "branch", "-a"], cwd=mb)
    sees = inst in (br.stdout or "") or inst in (remote_br.stdout or "")
    # graduate: merge the instance branch into main and push
    dolt("checkout", "main", cwd=ma)
    dolt("fetch", "origin", cwd=ma)
    dolt("reset", "--hard", "origin/main", cwd=ma)
    mg = dolt("merge", inst, "--no-edit", cwd=ma)
    commit(ma, f"graduate {inst}")
    pg = push(ma)
    sync_reset(mb)
    graduated = val(sql(f"SELECT COUNT(*) FROM work WHERE k='h8-{inst}'", cwd=mb))
    # abandon: delete the branch locally, then try to delete it on the remote
    dl = dolt("branch", "-d", "-f", inst, cwd=ma)
    rl = sh(["dolt", "push", "origin", f":{inst}"], cwd=ma)
    ok = pi.returncode == 0 and pg.returncode == 0 and graduated == "1"
    check("H8 instance branches through ONE data ref: fetch visibility, graduate, abandon (I4, I5, I8)",
          ok,
          f"pushed the instance branch      : rc={pi.returncode}\n"
          f"another clone sees it after fetch: {sees}\n"
          f"  dolt_branches on B: {(br.stdout or '').split()[1:] or '(none)'}\n"
          f"  dolt branch -a    : {clean(remote_br.stdout, 120)}\n"
          f"graduate (merge to main + push) : merge rc={mg.returncode} push rc={pg.returncode}"
          f" -> the spike's row on the other machine: {graduated}\n"
          f"abandon (local delete)          : rc={dl.returncode} {clean(dl.stderr,60)}\n"
          f"abandon (remote delete `push :{inst}`): rc={rl.returncode} "
          f"{clean(rl.stderr or rl.stdout, 90)}\n"
          f"=> graduate/abandon work through a git remote. Note the asymmetry that\n"
          f"   invariant 12 predicts: branch state travels INSIDE the single data ref,\n"
          f"   so there is no per-branch git ref to delete and remote branch deletion\n"
          f"   is not a git ref operation.")


def h9_two_instances_same_record(ma, mb):
    """I6 over the real remote: two instances refining the SAME record conflict at
    merge rather than one silently winning."""
    sync_reset(ma)
    sync_reset(mb)
    ia, ib = f"ia_{RUN.replace('-','_')}", f"ib_{RUN.replace('-','_')}"
    dolt("checkout", "-b", ia, cwd=ma)
    sql("UPDATE rec SET title='refined by instance A' WHERE id='R6'", cwd=ma)
    commit(ma, "instance A refines R6")
    pa = push(ma, ia)
    dolt("checkout", "-b", ib, cwd=mb)
    sql("UPDATE rec SET title='refined by instance B' WHERE id='R6'", cwd=mb)
    commit(mb, "instance B refines R6")
    pb = push(mb, ib)
    # graduate A, then try to graduate B on top
    dolt("checkout", "main", cwd=ma)
    dolt("fetch", "origin", cwd=ma)
    dolt("reset", "--hard", "origin/main", cwd=ma)
    dolt("merge", ia, "--no-edit", cwd=ma)
    commit(ma, "graduate A")
    push(ma)
    dolt("checkout", "main", cwd=mb)
    dolt("fetch", "origin", cwd=mb)
    dolt("reset", "--hard", "origin/main", cwd=mb)
    m2 = dolt("merge", ib, "--no-edit", cwd=mb)
    blob = ((m2.stdout or "") + (m2.stderr or "")).lower()
    nconf = val(sql("SELECT COUNT(*) FROM dolt_conflicts", cwd=mb))
    conflicted = "conflict" in blob or (nconf or "0") != "0"
    dolt("merge", "--abort", cwd=mb)
    sync_reset(mb)
    winner = val(sql("SELECT title FROM rec WHERE id='R6'", cwd=mb))
    ok = pa.returncode == 0 and pb.returncode == 0 and conflicted
    check("H9 two instances refining the SAME record -> conflict at graduation (I6)",
          ok,
          f"instance branches pushed: A rc={pa.returncode}  B rc={pb.returncode}\n"
          f"A graduated first; B's merge: rc={m2.returncode} conflicted={conflicted} "
          f"dolt_conflicts={nconf}\n"
          f"main after B aborted    : {winner} (A's value — B lost nothing, it still\n"
          f"                          holds its branch and must re-apply its intent)\n"
          f"=> this is exactly the case DECISIONS.md D1 governs: the LOSER re-applies\n"
          f"   its intent as a validated write, and a conflict inside one leased scope\n"
          f"   means the lease scoping was wrong.")


# ---------------------------------------------------------------- H10


def h10_schema_across_machines(ma, mb):
    sync_reset(ma)
    sync_reset(mb)
    a_col = f"col_a_{RUN.replace('-','_')[-6:]}"
    b_col = f"col_b_{RUN.replace('-','_')[-6:]}"
    sql(f"ALTER TABLE rec ADD COLUMN {a_col} VARCHAR(16) NULL", cwd=ma)
    commit(ma, f"add {a_col}")
    pa = push(ma)
    sql(f"ALTER TABLE rec ADD COLUMN {b_col} VARCHAR(16) NULL", cwd=mb)
    commit(mb, f"add {b_col}")
    rc, conflicted, txt = merge_remote(mb)
    cols = sh(["dolt", "sql", "-q", "DESCRIBE rec", "-r", "csv"], cwd=mb)
    both = a_col in (cols.stdout or "") and b_col in (cols.stdout or "")
    pb = push(mb)
    # same column, different types -> must surface
    sync_reset(ma)
    sync_reset(mb)
    same = f"col_x_{RUN.replace('-','_')[-6:]}"
    sql(f"ALTER TABLE rec ADD COLUMN {same} INT NULL", cwd=ma)
    commit(ma, f"add {same} INT")
    push(ma)
    sql(f"ALTER TABLE rec ADD COLUMN {same} VARCHAR(32) NULL", cwd=mb)
    commit(mb, f"add {same} VARCHAR")
    rc2, conf2, txt2 = merge_remote(mb)
    hard = rc2 != 0 or conf2
    dolt("merge", "--abort", cwd=mb)
    sync_reset(mb)
    ok = pa.returncode == 0 and not conflicted and both and pb.returncode == 0 and hard
    check("H10 schema evolution across machines over GitHub (E5, E6)",
          ok,
          f"(a) different columns: A added {a_col}, B added {b_col}\n"
          f"    B merge rc={rc} conflicted={conflicted}; both columns present: {both}\n"
          f"    B pushed the merged schema: rc={pb.returncode}\n"
          f"(b) SAME column, different types ({same} INT vs VARCHAR):\n"
          f"    B merge rc={rc2} conflicted={conf2} -> surfaced: {hard}\n"
          f"    {txt2}\n"
          f"=> Dolt merges SCHEMA as well as data across a real remote, and refuses to\n"
          f"   silently pick one type. E5/E6 hold off file://.")


# ---------------------------------------------------------------- H11


def h11_push_contention():
    """SC5 measured attempts [1..8] on file:// — perfectly linear. Does the network
    change the shape, and what does it cost in seconds?"""
    base = ROOT / "pushers"
    ds = []
    for i in range(N_PUSHERS):
        try:
            ds.append(clone(f"p{i}", base))
        except RuntimeError as e:
            check("H11 push contention", False, str(e))
            return
    for i, d in enumerate(ds):
        sql(f"INSERT INTO work (k,agent) VALUES ('h11-{i}','p{i}')", cwd=d)
        commit(d, f"p{i} work")
    attempts = {}
    landed = {}
    import threading
    bar = threading.Barrier(len(ds))

    def worker(i):
        d = ds[i]
        bar.wait()
        n = 0
        p = None
        for _ in range(N_PUSHERS + 4):
            n += 1
            p = push(d)
            if p.returncode == 0:
                break
            dolt("fetch", "origin", cwd=d)
            m = dolt("merge", "origin/main", "--no-edit", cwd=d)
            if m.returncode != 0:
                dolt("merge", "--abort", cwd=d)
                dolt("reset", "--hard", "origin/main", cwd=d)
                sql(f"INSERT IGNORE INTO work (k,agent) VALUES ('h11-{i}','p{i}')", cwd=d)
                commit(d, f"p{i} retry")
            time.sleep(0.2 * i)
        attempts[i] = n
        landed[i] = bool(p and p.returncode == 0)

    t0 = time.perf_counter()
    ts = [threading.Thread(target=worker, args=(i,)) for i in range(len(ds))]
    [t.start() for t in ts]
    [t.join() for t in ts]
    total = time.perf_counter() - t0
    sync_reset(ds[0])
    n_rows = val(sql("SELECT COUNT(*) FROM work WHERE k LIKE 'h11-%'", cwd=ds[0]))
    at = [attempts.get(i) for i in range(len(ds))]
    ok = str(n_rows) == str(len(ds)) and all(landed.values())
    check(f"H11 {N_PUSHERS} clones pushing at once over GitHub (SC5)",
          ok,
          f"attempts per clone : {at}\n"
          f"total attempts     : {sum(a or 0 for a in at)}  (linear O(N) would be "
          f"{N_PUSHERS*(N_PUSHERS+1)//2})\n"
          f"all landed         : {all(landed.values())}   rows on the remote: "
          f"{n_rows}/{len(ds)}\n"
          f"convergence        : {total:.0f} s wall clock\n"
          f"=> SC5's file:// result was exactly [1,2,3,4,5,6,7,8]. The shape over the\n"
          f"   network is above; each retry is now a real round trip, so this is the\n"
          f"   number that bounds how many instances can share one remote.")


# ---------------------------------------------------------------- main


def cleanup():
    if os.environ.get("FA_GH_KEEP"):
        print(f"--- keeping refs: {sorted(REFS_CREATED)}")
        return
    out = []
    for ref in sorted(REFS_CREATED):
        r = sh(["git", "push", REMOTE, f":{ref}"], timeout=120)
        out.append(f"{ref}={'ok' if r.returncode == 0 else 'rc=' + str(r.returncode)}")
    print(f"--- cleanup: {'; '.join(out)}")


def main():
    print(f"=== FINAL TESTS part 2: the file:// scenarios, re-run on github.com\n"
          f"    remote={REMOTE}\n    run={RUN}  data_ref={DATA_REF}\n")
    setup()
    ma = clone("machineA", ROOT / "A")
    mb = clone("machineB", ROOT / "B")
    mw = clone("machineW", ROOT / "W")
    MACHINES.update({"A": ma, "B": mb})
    only = {x.strip().lower() for x in os.environ.get("FA_GT_ONLY", "").split(",") if x.strip()}
    if only:
        print(f"--- FA_GT_ONLY={sorted(only)} (partial run — NOT a full result)")
    try:
        for fn, args in ((h1_cell_merge, (ma, mb)), (h2_same_cell, (ma, mb)),
                         (h3_wedge, (mw,)), (h4_topology, (ma, mb)),
                         (h5_lease_two_fleets, (ma, mb)), (h6_counters, (ma, mb)),
                         (h7_staleness, (ma, mb)), (h8_branches_over_one_ref, (ma, mb)),
                         (h9_two_instances_same_record, (ma, mb)),
                         (h10_schema_across_machines, (ma, mb)),
                         (h11_push_contention, ())):
            if only and fn.__name__.split("_")[0] not in only:
                continue
            try:
                fn(*args)
            except Exception:                                   # noqa: BLE001
                import traceback
                check(f"{fn.__name__} (ERROR)", False, traceback.format_exc()[-700:])
            print()
    finally:
        cleanup()
    npass = sum(1 for _, ok, _ in RESULTS if ok)
    print("=" * 74)
    print(f"{npass}/{len(RESULTS)} passed")
    for name, ok, _ in RESULTS:
        if not ok:
            print(f"  FAILED: {name}")
    sys.exit(0 if npass == len(RESULTS) else 1)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--agent":
        sys.exit(agent_main(sys.argv[2:]))
    main()
