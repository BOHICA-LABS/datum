#!/usr/bin/env python3
"""Multi-machine concurrency tests.

Two INDEPENDENT Dolt clones (separate data dirs, separate sql-servers, separate
ports) sharing one remote — the real topology for a factory whose agents run on
different machines. This is the gap the first spike pass explicitly left untested.

The question is not only "does it merge" but "what mutual exclusion actually
survives when writers do not share a server".

Run: .venv/bin/python -u poc/test_multimachine.py
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import time
from pathlib import Path

import pymysql

ROOT = Path(__file__).parent / "mm"
REMOTE = ROOT / "remote"
A, B = ROOT / "machineA", ROOT / "machineB"
PORT_A, PORT_B = 3401, 3402
DB = "factory_artifacts"
RESULTS: list[tuple[str, bool, str]] = []
SERVERS: list[subprocess.Popen] = []


def check(name, ok, detail=""):
    RESULTS.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}")
    for ln in (detail or "").splitlines():
        print(f"        {ln}")


def sh(args, cwd, timeout=180, check_rc=False):
    """Always bounded: dolt push/pull can hang indefinitely (seen in this spike)."""
    try:
        r = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(args, 124, "", f"TIMEOUT after {timeout}s")
    if check_rc and r.returncode != 0:
        raise RuntimeError(f"{' '.join(args)} failed: {r.stderr[:300]}")
    return r


def c(port, db=DB, autocommit=True):
    kw = dict(host="127.0.0.1", port=port, user="root", autocommit=autocommit,
              cursorclass=pymysql.cursors.DictCursor)
    if db:
        kw["database"] = db
    return pymysql.connect(**kw)


def q(cx, sql, args=None):
    with cx.cursor() as cur:
        cur.execute(sql, args or ())
        try:
            return cur.fetchall()
        except Exception:
            return cur.rowcount


def rc(cx, sql, args=None):
    with cx.cursor() as cur:
        cur.execute(sql, args or ())
        return cur.rowcount


def wait_port(port, timeout=45):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            cx = pymysql.connect(host="127.0.0.1", port=port, user="root")
            cx.close()
            return True
        except pymysql.err.Error:
            time.sleep(0.6)
    return False


# ---------------------------------------------------------------- setup


def setup():
    print("--- setup: building a shared remote and two independent clones")
    if ROOT.exists():
        shutil.rmtree(ROOT)
    for p in (ROOT, REMOTE, A, B):
        p.mkdir(parents=True, exist_ok=True)

    # A small purpose-built DB: the point is the topology, not corpus size.
    src = ROOT / "src"
    src.mkdir()
    sh(["dolt", "init", "--name", "spike", "--email", "spike@local"], cwd=src, check_rc=True)
    ddl = """
    CREATE TABLE bc (
      bc_id VARCHAR(24) NOT NULL PRIMARY KEY,
      title TEXT NOT NULL,
      capability VARCHAR(16) NULL,
      owner VARCHAR(32) NULL
    );
    CREATE TABLE factory_lock (
      id TINYINT NOT NULL PRIMARY KEY,
      holder VARCHAR(64) NULL,
      expires_at DATETIME NULL,
      fence BIGINT NOT NULL DEFAULT 0
    );
    INSERT INTO bc VALUES
      ('BC-1.01.001','dispatcher tier ordering',NULL,NULL),
      ('BC-1.01.002','plugin crash isolation',NULL,NULL),
      ('BC-2.02.001','host abi version pin',NULL,NULL);
    INSERT INTO factory_lock (id, holder) VALUES (1, NULL);
    """
    for stmt in [s.strip() for s in ddl.split(";") if s.strip()]:
        sh(["dolt", "sql", "-q", stmt], cwd=src, check_rc=True)
    sh(["dolt", "add", "-A"], cwd=src, check_rc=True)
    sh(["dolt", "commit", "-m", "seed"], cwd=src, check_rc=True)
    sh(["dolt", "remote", "add", "origin", f"file://{REMOTE}"], cwd=src, check_rc=True)
    sh(["dolt", "push", "origin", "main"], cwd=src, check_rc=True)

    for d, who in ((A, "machineA"), (B, "machineB")):
        r = sh(["dolt", "clone", f"file://{REMOTE}", DB], cwd=d)
        if r.returncode != 0:
            raise RuntimeError(f"clone into {d} failed: {r.stderr[:300]}")
        # A fresh clone inherits NO author identity, and `dolt pull` creates a
        # merge commit — so every pull fails with "Author identity unknown".
        # Real deployments must configure identity at clone time.
        sh(["dolt", "config", "--local", "--add", "user.name", who], cwd=d / DB, check_rc=True)
        sh(["dolt", "config", "--local", "--add", "user.email",
            f"{who}@spike.local"], cwd=d / DB, check_rc=True)

    for d, port in ((A, PORT_A), (B, PORT_B)):
        log = open(ROOT / f"server-{port}.log", "w")
        SERVERS.append(subprocess.Popen(
            ["dolt", "sql-server", "--host", "127.0.0.1", "--port", str(port)],
            cwd=d / DB, stdout=log, stderr=log))
    for port in (PORT_A, PORT_B):
        if not wait_port(port):
            raise RuntimeError(f"sql-server on {port} never came up")
    print(f"    machineA :{PORT_A}   machineB :{PORT_B}   remote {REMOTE}\n")


def teardown():
    for p in SERVERS:
        p.terminate()
    for p in SERVERS:
        try:
            p.wait(timeout=15)
        except subprocess.TimeoutExpired:
            p.kill()


def dolt_a(*args, **kw):
    return sh(["dolt", *args], cwd=A / DB, **kw)


def dolt_b(*args, **kw):
    return sh(["dolt", *args], cwd=B / DB, **kw)


# ---------------------------------------------------------------- tests


def m1_disjoint_writes_converge():
    """Two machines edit DIFFERENT rows, both push/pull. Both edits must survive."""
    ca, cb = c(PORT_A), c(PORT_B)
    q(ca, "UPDATE bc SET owner='machineA' WHERE bc_id='BC-1.01.001'")
    q(ca, "CALL DOLT_COMMIT('-Am','A: claim BC-1.01.001')")
    q(cb, "UPDATE bc SET owner='machineB' WHERE bc_id='BC-2.02.001'")
    q(cb, "CALL DOLT_COMMIT('-Am','B: claim BC-2.02.001')")

    pa = dolt_a("push", "origin", "main")               # A pushes first: fast-forward
    pb1 = dolt_b("push", "origin", "main")              # B is now stale
    pl = dolt_b("pull", "origin", "main")               # B merges A's work
    pb2 = dolt_b("push", "origin", "main")              # then succeeds
    dolt_a("pull", "origin", "main")

    ca.close(); cb.close()
    ca, cb = c(PORT_A), c(PORT_B)
    va = {r["bc_id"]: r["owner"] for r in q(ca, "SELECT bc_id, owner FROM bc ORDER BY bc_id")}
    vb = {r["bc_id"]: r["owner"] for r in q(cb, "SELECT bc_id, owner FROM bc ORDER BY bc_id")}
    ca.close(); cb.close()

    ok = (va == vb
          and va.get("BC-1.01.001") == "machineA"
          and va.get("BC-2.02.001") == "machineB")
    check("M1 disjoint writes on 2 machines converge via push/pull", ok,
          f"A push rc={pa.returncode}; B push(stale) rc={pb1.returncode} "
          f"(non-zero = correctly rejected); B pull rc={pl.returncode}; B push rc={pb2.returncode}\n"
          f"machineA sees: {va}\nmachineB sees: {vb}")


def m2_stale_push_rejected():
    """A stale push must be REFUSED, not silently overwrite the remote."""
    ca, cb = c(PORT_A), c(PORT_B)
    q(ca, "UPDATE bc SET title='A edits title' WHERE bc_id='BC-1.01.002'")
    q(ca, "CALL DOLT_COMMIT('-Am','A: retitle')")
    dolt_a("push", "origin", "main")
    # B has not pulled; its history diverges from the remote.
    q(cb, "UPDATE bc SET capability='CAP-777' WHERE bc_id='BC-1.01.002'")
    q(cb, "CALL DOLT_COMMIT('-Am','B: set capability')")
    pb = dolt_b("push", "origin", "main")
    ca.close(); cb.close()
    check("M2 stale push refused (no silent remote overwrite)", pb.returncode != 0,
          f"B push rc={pb.returncode}\n"
          f"stderr: {(pb.stderr or pb.stdout or '').strip()[:220]}")


def m3_different_cells_same_row_merge():
    """Dolt's cell-level merge: A changed `title`, B changed `capability`, on the
    SAME row. A line-based (git/markdown) store would conflict here."""
    pl = dolt_b("pull", "origin", "main")
    conflicts = ""
    cb = c(PORT_B)
    try:
        conflicts = str(q(cb, "SELECT COUNT(*) n FROM dolt_conflicts")[0]["n"])
    except pymysql.err.Error as e:
        conflicts = f"err {str(e)[:60]}"
    row = q(cb, "SELECT title, capability FROM bc WHERE bc_id='BC-1.01.002'")
    cb.close()
    pb = dolt_b("push", "origin", "main")
    ok = (pl.returncode == 0 and conflicts == "0" and row
          and row[0]["title"] == "A edits title" and row[0]["capability"] == "CAP-777")
    check("M3 cell-level merge: same row, different columns, no conflict", ok,
          f"B pull rc={pl.returncode} conflicts={conflicts}; then push rc={pb.returncode}\n"
          f"merged row: {row[0] if row else None}\n"
          f"(both machines' edits to ONE row survived — line-based merge could not do this)")


def m4_same_cell_conflict_surfaces():
    """Same row AND same column on both machines: must surface, never silently pick."""
    for d in (dolt_a, dolt_b):
        d("pull", "origin", "main")
    ca, cb = c(PORT_A), c(PORT_B)
    q(ca, "UPDATE bc SET owner='A-WINS' WHERE bc_id='BC-1.01.002'")
    q(ca, "CALL DOLT_COMMIT('-Am','A: owner')")
    q(cb, "UPDATE bc SET owner='B-WINS' WHERE bc_id='BC-1.01.002'")
    q(cb, "CALL DOLT_COMMIT('-Am','B: owner')")
    dolt_a("push", "origin", "main")
    pl = dolt_b("pull", "origin", "main")

    surfaced = pl.returncode != 0
    detail = f"B pull rc={pl.returncode}"
    if not surfaced:
        try:
            n = q(cb, "SELECT COUNT(*) n FROM dolt_conflicts")[0]["n"]
            surfaced = n > 0
            detail += f"; dolt_conflicts rows={n}"
        except pymysql.err.Error as e:
            detail += f"; conflicts probe err {str(e)[:60]}"
    else:
        detail += f"\nstderr: {(pl.stderr or pl.stdout or '').strip()[:200]}"
    # Neither side may have silently lost its value without a conflict signal.
    ca.close(); cb.close()
    check("M4 same-cell edit on 2 machines surfaces a conflict", surfaced, detail)

    # Leave B clean: an unresolved conflict blocks every later transaction on
    # that server ("@autocommit must be disabled so that merge conflicts...").
    ab = dolt_b("merge", "--abort")
    if ab.returncode != 0:
        dolt_b("conflicts", "resolve", "--ours", "bc")
        dolt_b("commit", "-am", "resolve: take ours")
    dolt_b("reset", "--hard", "origin/main")
    print(f"        [cleanup] B merge --abort rc={ab.returncode}, reset to origin/main")


def m5_lock_does_not_span_machines():
    """THE load-bearing negative result.

    The CAS lock is atomic within ONE server. With independent clones, each
    machine's lock table is local until push/pull, so BOTH machines can 'acquire'
    the same lock and each believes it won. Mutual exclusion does NOT come for
    free across machines.
    """
    dolt_a("pull", "origin", "main")
    dolt_b("pull", "origin", "main")
    ca, cb = c(PORT_A), c(PORT_B)
    q(ca, "UPDATE factory_lock SET holder=NULL, fence=0 WHERE id=1")
    try:
        q(ca, "CALL DOLT_COMMIT('-Am','reset lock')")
    except pymysql.err.Error as e:
        if "nothing to commit" not in str(e):
            raise
    dolt_a("push", "origin", "main")
    dolt_b("pull", "origin", "main")

    na = rc(ca, """UPDATE factory_lock SET holder='machineA', fence=fence+1,
                   expires_at=DATE_ADD(NOW(), INTERVAL 600 SECOND)
                   WHERE id=1 AND (holder IS NULL OR expires_at < NOW())""")
    nb = rc(cb, """UPDATE factory_lock SET holder='machineB', fence=fence+1,
                   expires_at=DATE_ADD(NOW(), INTERVAL 600 SECOND)
                   WHERE id=1 AND (holder IS NULL OR expires_at < NOW())""")
    ha = q(ca, "SELECT holder FROM factory_lock WHERE id=1")[0]["holder"]
    hb = q(cb, "SELECT holder FROM factory_lock WHERE id=1")[0]["holder"]
    ca.close(); cb.close()

    both_won = na == 1 and nb == 1 and ha == "machineA" and hb == "machineB"
    check("M5 CAS lock does NOT provide cross-machine mutual exclusion (expected)",
          both_won,
          f"A acquired={na == 1} (sees holder={ha});  B acquired={nb == 1} (sees holder={hb})\n"
          "BOTH acquired the same lock — each clone's table is local until sync.\n"
          "=> cross-machine exclusion requires ONE shared sql-server (or an\n"
          "   external lock). Per-machine clones give convergence, not exclusion.")


def m6_shared_server_does_exclude():
    """The remedy: both agents against ONE server. Exclusion is restored."""
    ca1, ca2 = c(PORT_A), c(PORT_A)          # two clients, one server
    q(ca1, "UPDATE factory_lock SET holder=NULL, expires_at=NULL WHERE id=1")
    n1 = rc(ca1, """UPDATE factory_lock SET holder='agent-1', fence=fence+1,
                    expires_at=DATE_ADD(NOW(), INTERVAL 600 SECOND)
                    WHERE id=1 AND (holder IS NULL OR expires_at < NOW())""")
    n2 = rc(ca2, """UPDATE factory_lock SET holder='agent-2', fence=fence+1,
                    expires_at=DATE_ADD(NOW(), INTERVAL 600 SECOND)
                    WHERE id=1 AND (holder IS NULL OR expires_at < NOW())""")
    holder = q(ca1, "SELECT holder FROM factory_lock WHERE id=1")[0]["holder"]
    ca1.close(); ca2.close()
    check("M6 one shared server: exactly one of two clients acquires",
          (n1 + n2) == 1 and holder in ("agent-1", "agent-2"),
          f"agent-1 got={n1 == 1}  agent-2 got={n2 == 1}  holder={holder}")


def main():
    print("=" * 74)
    print("Multi-machine: two independent Dolt clones + one shared remote")
    print("=" * 74)
    try:
        setup()
        for t in (m1_disjoint_writes_converge, m2_stale_push_rejected,
                  m3_different_cells_same_row_merge, m4_same_cell_conflict_surfaces,
                  m5_lock_does_not_span_machines, m6_shared_server_does_exclude):
            try:
                t()
            except Exception:
                import traceback
                check(f"{t.__name__} (ERROR)", False, traceback.format_exc()[-500:])
            print()
    finally:
        teardown()
    n = sum(1 for _, ok, _ in RESULTS if ok)
    print("=" * 74)
    print(f"{n}/{len(RESULTS)} passed")
    for nm, ok, _ in RESULTS:
        if not ok:
            print(f"  FAILED: {nm}")
    sys.exit(0 if n == len(RESULTS) else 1)


if __name__ == "__main__":
    main()
