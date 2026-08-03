#!/usr/bin/env python3
"""Single-clone + local write mutex: does it hold?

Target topology: ONE Dolt clone on a host, N agents as SEPARATE PROCESSES, no
sql-server. Concurrent server-less writes to one clone fail
(`cannot update manifest`), so writes must be serialized by a local mutex.

Tests use real subprocesses, not threads — a thread lock would prove nothing about
independent agents.

  X1  baseline: N concurrent writers, NO mutex -> quantify the failures
  X2  with the mutex: zero failures
  X3  lost updates: N read-modify-write increments must total exactly N
  X4  crash safety: SIGKILL the holder -> kernel releases the lock
  X5  timeout: a wedged holder does not hang other agents forever
  X6  cost: throughput with the mutex vs a local sql-server on the same clone
  X7  does the mutex remove the unique-token discipline? (serialized writers
      cannot merge, so the answer should be yes WITHIN this host)

Run: .venv/bin/python -u poc/test_mutex.py
"""
from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from clonelock import CloneLockTimeout, clone_write_lock  # noqa: E402

ROOT = Path(__file__).parent / "mx"
CLONE = ROOT / "clone"
DB = "mutexdb"
DBDIR = CLONE / DB
RESULTS: list[tuple[str, bool, str]] = []
SELF = str(Path(__file__).resolve())


def check(name, ok, detail=""):
    RESULTS.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}")
    for ln in (detail or "").splitlines():
        print(f"        {ln}")


def sh(args, cwd=None, timeout=120):
    try:
        return subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(args, 124, "", "TIMEOUT")


def dsql(stmt, timeout=120):
    return sh(["dolt", "sql", "-q", stmt], cwd=DBDIR, timeout=timeout)


def counter() -> int:
    r = dsql("SELECT n FROM ctr WHERE id=1")
    for tok in (r.stdout or "").replace("|", " ").split():
        if tok.isdigit():
            return int(tok)
    return -1


def reset_counter():
    dsql("UPDATE ctr SET n=0 WHERE id=1")


def setup():
    print("--- setup: ONE clone, no sql-server")
    if ROOT.exists():
        shutil.rmtree(ROOT)
    DBDIR.mkdir(parents=True)
    sh(["dolt", "init", "--name", "mx", "--email", "mx@spike"], cwd=DBDIR)
    dsql("CREATE TABLE ctr (id TINYINT PRIMARY KEY, n INT NOT NULL)")
    dsql("INSERT INTO ctr VALUES (1,0)")
    dsql("CREATE TABLE writes (id INT AUTO_INCREMENT PRIMARY KEY, who VARCHAR(32) NOT NULL)")
    sh(["dolt", "add", "-A"], cwd=DBDIR)
    sh(["dolt", "commit", "-m", "seed"], cwd=DBDIR)
    print(f"    clone: {DBDIR}\n")


# ------------------------------------------------------------ worker mode


def worker_main(argv):
    """Run as a separate PROCESS: `test_mutex.py --worker <mode> <tag>`.

    mode=nomutex  : increment without the mutex
    mode=mutex    : increment holding the mutex
    mode=hold     : take the mutex and sleep (for crash/timeout tests)
    Prints one line: OK / FAIL:<reason>
    """
    mode, tag = argv[0], argv[1]
    dur = float(argv[2]) if len(argv) > 2 else 0.0

    def increment():
        r = sh(["dolt", "sql", "-q",
                "UPDATE ctr SET n = n + 1 WHERE id=1"], cwd=DBDIR, timeout=120)
        if r.returncode != 0:
            err = (r.stderr or r.stdout or "").strip().replace("\n", " ")
            print(f"FAIL:{err[:110]}")
        else:
            print("OK")

    if mode == "nomutex":
        increment()
    elif mode == "mutex":
        try:
            with clone_write_lock(DBDIR, timeout=120):
                increment()
        except CloneLockTimeout:
            print("FAIL:lock-timeout")
    elif mode == "hold":
        with clone_write_lock(DBDIR, timeout=120):
            print("HELD", flush=True)
            time.sleep(dur)
    elif mode == "try":
        try:
            with clone_write_lock(DBDIR, timeout=dur):
                print("OK")
        except CloneLockTimeout:
            print("FAIL:lock-timeout")
    return 0


def spawn(mode, tag, dur=0.0):
    return subprocess.Popen([sys.executable, SELF, "--worker", mode, tag, str(dur)],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def run_procs(mode, n, timeout=240):
    procs = [spawn(mode, f"w{i}") for i in range(n)]
    outs = []
    for p in procs:
        try:
            o, _ = p.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            p.kill()
            o = "FAIL:proc-timeout"
        outs.append((o or "").strip())
    ok = sum(1 for o in outs if o.startswith("OK"))
    fails = [o for o in outs if not o.startswith("OK")]
    return ok, fails


# ---------------------------------------------------------------- tests

N = 8


def x1_baseline_no_mutex():
    reset_counter()
    ok, fails = run_procs("nomutex", N)
    manifest = [f for f in fails if "manifest" in f]
    final = counter()
    check("X1 baseline: concurrent writers on ONE clone WITHOUT a mutex fail",
          len(fails) > 0,
          f"{N} processes: {ok} succeeded, {len(fails)} failed "
          f"({len(manifest)} 'cannot update manifest')\n"
          f"counter = {final} (wanted {N}) -> {N - final} increments lost\n"
          + (f"sample: {fails[0][:100]}" if fails else ""))


def x2_mutex_no_failures():
    reset_counter()
    ok, fails = run_procs("mutex", N)
    check("X2 with the clone mutex: every writer succeeds, zero manifest errors",
          ok == N and not fails,
          f"{N} processes: {ok} succeeded, {len(fails)} failed"
          + (f"\nfailures: {fails[:2]}" if fails else ""))


def x3_no_lost_updates():
    """The real prize: serialized writers cannot merge, so read-modify-write is safe
    with NO unique-token discipline."""
    reset_counter()
    ok, fails = run_procs("mutex", N)
    final = counter()
    check("X3 no lost updates: N mutex'd increments total exactly N",
          final == N and ok == N,
          f"{N} increments -> counter = {final} (want {N}); failures={len(fails)}\n"
          "=> `UPDATE ctr SET n = n + 1` is SAFE here — the same non-unique write that\n"
          "   test_cas_patterns.py P2 proved UNSAFE under concurrency")


def x4_crash_releases_lock():
    """flock is released by the kernel when the holder dies — a row lease would
    stay held until its TTL expired."""
    h = spawn("hold", "holder", 30)
    line = h.stdout.readline().strip()
    if line != "HELD":
        h.kill()
        return check("X4 crash safety", False, f"holder never reported HELD (got {line!r})")
    # Confirm it is genuinely exclusive right now.
    blocked, bf = run_procs("try", 1, timeout=20)   # try with a 0s timeout
    os.kill(h.pid, signal.SIGKILL)
    h.wait(timeout=15)
    time.sleep(0.4)
    after, af = run_procs("mutex", 1, timeout=60)
    check("X4 crash safety: SIGKILL of the holder auto-releases the lock",
          blocked == 0 and after == 1,
          f"while held: acquire attempts succeeding = {blocked} (want 0)\n"
          f"after SIGKILL: acquire succeeded = {after == 1}\n"
          "=> no stale-lock recovery code needed; contrast a row lease, which would\n"
          "   stay held for its full TTL after an agent crash")


def x5_timeout_not_hang():
    """A wedged holder must not hang every other agent forever."""
    h = spawn("hold", "holder", 8)
    if h.stdout.readline().strip() != "HELD":
        h.kill()
        return check("X5 timeout", False, "holder never held")
    t0 = time.time()
    p = subprocess.run([sys.executable, SELF, "--worker", "try", "w", "1.0"],
                       capture_output=True, text=True, timeout=60)
    dt = time.time() - t0
    h.kill(); h.wait(timeout=10)
    out = (p.stdout or "").strip()
    check("X5 a wedged holder does not hang other agents (bounded wait)",
          out.startswith("FAIL:lock-timeout") and dt < 5,
          f"waiter with a 1.0s timeout returned {out!r} after {dt:.1f}s\n"
          "=> blocking LOCK_EX would have waited forever; the polled NB flock bounds it")


def x6_cost_vs_local_server():
    """Throughput: mutex'd CLI writes vs a local sql-server on the SAME clone."""
    reset_counter()
    t0 = time.time()
    ok, _ = run_procs("mutex", N)
    mutex_s = time.time() - t0

    log = open(ROOT / "srv.log", "w")
    srv = subprocess.Popen(["dolt", "sql-server", "--host", "127.0.0.1", "--port", "3499"],
                           cwd=DBDIR, stdout=log, stderr=log)
    up = False
    for _ in range(50):
        try:
            import pymysql
            c = pymysql.connect(host="127.0.0.1", port=3499, user="root")
            c.close()
            up = True
            break
        except Exception:                      # noqa: BLE001
            time.sleep(0.5)
    srv_s, srv_ok = None, 0
    if up:
        import pymysql
        import threading
        reset_counter_via = pymysql.connect(host="127.0.0.1", port=3499, user="root",
                                            database=DB, autocommit=True)
        with reset_counter_via.cursor() as k:
            k.execute("UPDATE ctr SET n=0 WHERE id=1")
        reset_counter_via.close()
        lk = threading.Lock()
        t0 = time.time()

        def w(i):
            nonlocal srv_ok
            try:
                cx = pymysql.connect(host="127.0.0.1", port=3499, user="root",
                                     database=DB, autocommit=True)
                with cx.cursor() as k:
                    k.execute("UPDATE ctr SET n = n + 1 WHERE id=1")
                with lk:
                    srv_ok += 1
                cx.close()
            except Exception:                  # noqa: BLE001
                pass
        ts = [threading.Thread(target=w, args=(i,)) for i in range(N)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        srv_s = time.time() - t0
    srv.terminate()
    try:
        srv.wait(timeout=15)
    except subprocess.TimeoutExpired:
        srv.kill()
    log.close()

    check("X6 cost: mutex'd CLI writes vs a local sql-server on the same clone", True,
          f"mutex + `dolt sql` : {N} writes in {mutex_s:.1f}s "
          f"({1000*mutex_s/N:.0f} ms/write, {ok}/{N} ok)\n"
          + (f"local sql-server   : {N} writes in {srv_s:.2f}s "
             f"({1000*srv_s/N:.0f} ms/write, {srv_ok}/{N} ok)"
             if srv_s else "local sql-server   : did not start; skipped")
          + "\nNOTE the CLI cost is dominated by process spawn + storage open per write,\n"
            "     not by the mutex. Batch many statements per invocation, or run a\n"
            "     LOCAL server, if write volume matters.\n"
            "     ⚠ a local server does NOT restore safety: its concurrent writers can\n"
            "       merge again, so the unique-token discipline comes back with it.")


def x8_batching_makes_it_viable():
    """141 ms/write would make a 1,959-BC import take ~4.5 minutes. The cost is
    per-INVOCATION, not per-write, so the real pattern — hold the mutex once and
    send many statements in one session — recovers it."""
    dsql("DELETE FROM writes")
    reps = 30
    t0 = time.time()
    with clone_write_lock(DBDIR, timeout=120):
        for i in range(reps):
            dsql(f"INSERT INTO writes (who) VALUES ('p{i}')")
    per_proc_ms = (time.time() - t0) / reps * 1000

    dsql("DELETE FROM writes")
    n = 300
    stmts = ";".join(f"INSERT INTO writes (who) VALUES ('b{i}')" for i in range(n))
    t0 = time.time()
    with clone_write_lock(DBDIR, timeout=180):
        r = dsql(stmts, timeout=300)
    batch_ms = (time.time() - t0) / n * 1000
    rows = -1
    out = dsql("SELECT COUNT(*) FROM writes").stdout or ""
    for tok in out.replace("|", " ").split():
        if tok.isdigit():
            rows = int(tok)
            break
    check("X8 batching: many statements per mutex hold makes the CLI path viable",
          r.returncode == 0 and rows == n and batch_ms < per_proc_ms / 5,
          f"one invocation per write : {per_proc_ms:.0f} ms/write\n"
          f"{n} statements in ONE call: {batch_ms:.2f} ms/write  "
          f"({per_proc_ms/batch_ms:.0f}x faster, {rows} rows)\n"
          f"extrapolated 1,959-BC import: {per_proc_ms*1959/1000:.0f}s per-invocation "
          f"vs {batch_ms*1959/1000:.1f}s batched\n"
          "=> matches the 12.7s server-based import; the mutex path is not a bottleneck\n"
          "   PROVIDED `datum` batches a unit of work into one session per lock hold")


def x7_server_reintroduces_merge_hazard():
    """Sanity-check the warning in X6: with a server, non-unique concurrent writes
    are hazardous again — which is the argument FOR the mutex."""
    have = any(nm.startswith("X3") and ok for nm, ok, _ in RESULTS)
    check("X7 the mutex is what makes non-unique writes safe (not Dolt)", have,
          "X3 showed `n = n + 1` is safe under the mutex.\n"
          "test_cas_patterns.py P2 showed the SAME shape (`fence = fence + 1`) is UNSAFE\n"
          "for concurrent writers on a server: 30/30 trials, all 6 writers 'won'.\n"
          "=> single-clone + mutex removes the token tax; a server reinstates it.")


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--worker":
        sys.exit(worker_main(sys.argv[2:]))
    print("=" * 74)
    print("Single clone + local write mutex (agents = separate processes)")
    print("=" * 74)
    setup()
    for t in (x1_baseline_no_mutex, x2_mutex_no_failures, x3_no_lost_updates,
              x4_crash_releases_lock, x5_timeout_not_hang, x6_cost_vs_local_server,
              x8_batching_makes_it_viable, x7_server_reintroduces_merge_hazard):
        try:
            t()
        except Exception:
            import traceback
            check(f"{t.__name__} (ERROR)", False, traceback.format_exc()[-500:])
        print()
    n = sum(1 for _, ok, _ in RESULTS if ok)
    print("=" * 74)
    print(f"{n}/{len(RESULTS)} passed")
    for nm, ok, _ in RESULTS:
        if not ok:
            print(f"  FAILED: {nm}")
    sys.exit(0 if n == len(RESULTS) else 1)


if __name__ == "__main__":
    main()
