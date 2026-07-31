#!/usr/bin/env python3
"""Can we get cross-machine mutual exclusion WITHOUT running a central server?

Motivation: M5 (test_multimachine.py) showed the CAS lock does not span independent
clones. The unique-token CAS fix does NOT change that — two clones are two separate
databases, so their lock rows never interact until push/pull, by which time both
agents already "hold" the lock and have started work.

But exclusion needs a synchronous *arbiter*, not necessarily a *server*. `dolt push`
is rejected on non-fast-forward, so the shared REMOTE may be able to serve as the
arbiter — infrastructure you already have (GitHub) and do not operate.

This suite tests push-as-CAS:

  S1  two clones write the lock locally and push SIMULTANEOUSLY -> exactly one push
      must succeed (the arbiter test)
  S2  the loser can detect it lost and observe the true holder
  S3  many rounds, to check push-as-CAS is not racy
  S4  cost: how long does one acquire round-trip take vs a server-local CAS
  S5  the failure mode it CANNOT fix: work already done before the push is rejected

Run: .venv/bin/python -u poc/test_serverless_lock.py
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).parent / "sl"
REMOTE = ROOT / "remote"
CLONES = ("mA", "mB", "mC")
DB = "lockdb"
RESULTS: list[tuple[str, bool, str]] = []


def check(name, ok, detail=""):
    RESULTS.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}")
    for ln in (detail or "").splitlines():
        print(f"        {ln}")


def sh(args, cwd, timeout=180):
    """Bounded: dolt push can hang indefinitely."""
    try:
        return subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(args, 124, "", f"TIMEOUT {timeout}s")


def dolt(clone, *args, **kw):
    return sh(["dolt", *args], cwd=ROOT / clone / DB, **kw)


def sql(clone, stmt, **kw):
    """No server: `dolt sql -q` operates directly on the local clone."""
    return dolt(clone, "sql", "-q", stmt, **kw)


def setup():
    print("--- setup: bare remote + 3 server-less clones (no sql-server anywhere)")
    if ROOT.exists():
        shutil.rmtree(ROOT)
    ROOT.mkdir(parents=True)
    REMOTE.mkdir()
    src = ROOT / "src"
    src.mkdir()
    sh(["dolt", "init", "--name", "spike", "--email", "s@l"], cwd=src)
    sh(["dolt", "sql", "-q",
        "CREATE TABLE factory_lock (id TINYINT PRIMARY KEY, holder VARCHAR(32) NULL, "
        "token BIGINT NOT NULL DEFAULT 0)"], cwd=src)
    sh(["dolt", "sql", "-q", "INSERT INTO factory_lock VALUES (1,NULL,0)"], cwd=src)
    sh(["dolt", "add", "-A"], cwd=src)
    sh(["dolt", "commit", "-m", "seed"], cwd=src)
    sh(["dolt", "remote", "add", "origin", f"file://{REMOTE}"], cwd=src)
    p = sh(["dolt", "push", "origin", "main"], cwd=src)
    if p.returncode != 0:
        raise RuntimeError(f"seed push failed: {p.stderr[:300]}")
    for cl in CLONES:
        d = ROOT / cl
        d.mkdir()
        r = sh(["dolt", "clone", f"file://{REMOTE}", DB], cwd=d)
        if r.returncode != 0:
            raise RuntimeError(f"clone {cl} failed: {r.stderr[:300]}")
        sh(["dolt", "config", "--local", "--add", "user.name", cl], cwd=d / DB)
        sh(["dolt", "config", "--local", "--add", "user.email", f"{cl}@spike"], cwd=d / DB)
    print(f"    clones: {', '.join(CLONES)}   remote: {REMOTE}\n")


def release_all():
    """Reset the lock at the remote from one clone."""
    dolt(CLONES[0], "fetch", "origin", "main")
    dolt(CLONES[0], "reset", "--hard", "origin/main")
    sql(CLONES[0], "UPDATE factory_lock SET holder=NULL, token=0 WHERE id=1")
    dolt(CLONES[0], "commit", "-am", "release")
    dolt(CLONES[0], "push", "origin", "main")
    for cl in CLONES[1:]:
        dolt(cl, "fetch", "origin", "main")
        dolt(cl, "reset", "--hard", "origin/main")


def try_acquire(clone: str, tag: str, token: int):
    """Push-as-CAS acquire, entirely without a server.

    1. fetch + reset to the remote's truth (so our base is current)
    2. guarded local UPDATE (only if unheld)
    3. dolt commit
    4. push -- THE PUSH IS THE ATOMIC CAS. Non-fast-forward => we lost.
    """
    dolt(clone, "fetch", "origin", "main")
    dolt(clone, "reset", "--hard", "origin/main")
    r = sql(clone, f"UPDATE factory_lock SET holder='{tag}', token={token} "
                   f"WHERE id=1 AND holder IS NULL")
    if r.returncode != 0:
        return False, f"sql-rc{r.returncode}"
    cm = dolt(clone, "commit", "-am", f"{tag}: acquire")
    if cm.returncode != 0:
        return False, "guard-failed"        # nothing to commit => already held
    p = dolt(clone, "push", "origin", "main")
    return p.returncode == 0, ("pushed" if p.returncode == 0 else "push-rejected")


def read_remote_holder(clone: str):
    dolt(clone, "fetch", "origin", "main")
    dolt(clone, "reset", "--hard", "origin/main")
    r = sql(clone, "SELECT holder FROM factory_lock WHERE id=1")
    out = (r.stdout or "").replace("|", " ").split()
    for tok in out:
        if tok.startswith("m") and tok in CLONES:
            return tok
    return "NULL" if "NULL" in (r.stdout or "") else (r.stdout or "").strip()[:40]


# ---------------------------------------------------------------- tests


def s1_simultaneous_push_is_the_arbiter():
    release_all()
    got: list[str] = []
    notes: list[str] = []
    lk = threading.Lock()
    bar = threading.Barrier(len(CLONES))

    def worker(i, cl):
        bar.wait()
        ok, note = try_acquire(cl, cl, 1000 + i)
        with lk:
            notes.append(f"{cl}={note}")
            if ok:
                got.append(cl)

    ts = [threading.Thread(target=worker, args=(i, cl)) for i, cl in enumerate(CLONES)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    holder = read_remote_holder(CLONES[0])
    check("S1 push-as-CAS: 3 clones push simultaneously, exactly one wins",
          len(got) == 1 and holder == got[0],
          f"outcomes: {sorted(notes)}\nwinners={got}  remote holder={holder}\n"
          "=> the REMOTE is the arbiter; no sql-server involved anywhere")


def s2_loser_detects_and_sees_truth():
    loser = [c for c in CLONES if c != read_remote_holder(CLONES[0])]
    if not loser:
        return check("S2 loser detects loss", False, "no loser to inspect")
    cl = loser[0]
    ok, note = try_acquire(cl, cl, 777)
    holder = read_remote_holder(cl)
    check("S2 a second acquirer is refused and can read the true holder",
          not ok and holder not in (cl, "NULL"),
          f"{cl} acquire -> ok={ok} ({note}); true holder as seen by {cl} = {holder}")


def s3_repeated_rounds():
    rounds, bad = 6, []
    for r in range(rounds):
        release_all()
        got: list[str] = []
        lk = threading.Lock()
        bar = threading.Barrier(len(CLONES))

        def worker(i, cl):
            bar.wait()
            ok, _ = try_acquire(cl, cl, 2000 + r * 10 + i)
            if ok:
                with lk:
                    got.append(cl)

        ts = [threading.Thread(target=worker, args=(i, cl)) for i, cl in enumerate(CLONES)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        if len(got) != 1:
            bad.append((r, got))
    check("S3 push-as-CAS holds across repeated contended rounds",
          not bad, f"{rounds} rounds x {len(CLONES)} clones; anomalies={bad or 'none'}")


def s4_cost_of_a_roundtrip():
    release_all()
    t0 = time.time()
    ok, _ = try_acquire(CLONES[0], CLONES[0], 4242)
    dt = (time.time() - t0) * 1000
    check("S4 cost: one server-less acquire = fetch+reset+commit+push round trip",
          ok,
          f"local `file://` remote: {dt:.0f}ms per acquire\n"
          "NOTE this is a LOCAL remote. Over the network (GitHub) add real latency\n"
          "per acquire AND per release; a server-local CAS was ~1ms (test_spike T13).")


def s5_what_push_cas_cannot_fix():
    """The honest limit: the push only rejects AFTER the loser has already done its
    local work. For a lock that is fine (cheap). For a 45-minute wave gate it is
    not — both agents would run the whole gate before one is told it lost."""
    release_all()
    ok_a, _ = try_acquire(CLONES[0], CLONES[0], 9001)
    # B starts from a stale base, does 'expensive work', and only then pushes.
    dolt(CLONES[1], "fetch", "origin", "main")
    stale_base = dolt(CLONES[1], "sql", "-q", "SELECT holder FROM factory_lock WHERE id=1")
    b_saw_free = "NULL" in (stale_base.stdout or "")
    sql(CLONES[1], f"UPDATE factory_lock SET holder='{CLONES[1]}', token=9002 WHERE id=1")
    dolt(CLONES[1], "commit", "-am", "B: acquire on stale base")
    work_done = True                       # stand-in for a 45-min gate evaluation
    p = dolt(CLONES[1], "push", "origin", "main")
    check("S5 the limit: rejection arrives only AFTER the loser did its work",
          ok_a and p.returncode != 0 and work_done,
          f"A acquired={ok_a}; B's stale base showed the lock free={b_saw_free}\n"
          f"B did its work, THEN push was rejected (rc={p.returncode})\n"
          "=> fine for a cheap lock; NOT fine for a long gate — the wasted work is\n"
          "   already spent. A shared server refuses B up front, in ~1ms.")


def main():
    print("=" * 74)
    print("Cross-machine exclusion WITHOUT a central server (push-as-CAS)")
    print("=" * 74)
    setup()
    for t in (s1_simultaneous_push_is_the_arbiter, s2_loser_detects_and_sees_truth,
              s3_repeated_rounds, s4_cost_of_a_roundtrip, s5_what_push_cas_cannot_fix):
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
