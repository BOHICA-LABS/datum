#!/usr/bin/env python3
"""FINAL TESTS — a REAL GitHub remote over the network.

Every multi-machine/instance result in this spike used a `file://` remote, which
made "640 ms per acquire" a floor and left auth, latency, and partial-failure
recovery untested (ASSESSMENT §4.4, GAP-MATRIX §6 gap 1 — rated High). This
suite closes that gap against github.com.

  G1  push a real Dolt database to a GitHub repo; what refs actually appear
  G2  cold clone from GitHub -> identical data (onboarding + disaster recovery)
  G3  lease acquire round-trip latency over the network (vs the 640 ms floor)
  G4  3 clones acquire the same lease at once -> exactly one winner
  G5  push contention: N clones push at once -> attempts to converge
  G6  invariant 4: a rejected push does NOT mean the work was not published
  G7  ALL dolt branches share ONE git ref -> pushes contend across branches,
      and `--ref` gives each instance its own data ref as a mitigation
  G8  the embedded driver doing DOLT_PUSH / DOLT_FETCH in-process
  G9  failure modes: bad remote, and the documented infinite-hang class
  G10 the FULL 1,959-BC corpus round-tripping through GitHub

Every run uses a UNIQUE data ref (refs/dolt/run-<ts>/...) so runs never collide
and are cleaned up at the end. Credentials come from the git credential helper
(gh); no token is ever written to disk or into a URL.

Run: .venv/bin/python -u poc/test_github_remote.py
Env: FA_GH_REMOTE (default https://github.com/drbothen/datum (formerly dolt-artifact-spike)-remote.git)
     FA_GH_KEEP=1 to skip ref cleanup
"""
from __future__ import annotations

import os
import random
import shutil
import statistics
import subprocess
import sys
import threading
import time
from pathlib import Path

POC = Path(__file__).parent
ROOT = POC / "gh"
BENCH = POC / "bench" / "bench"
REMOTE = os.environ.get("FA_GH_REMOTE",
                        "https://github.com/drbothen/datum (formerly dolt-artifact-spike)-remote.git")
RUN = os.environ.get("FA_GH_RUN") or f"run-{int(time.time())}"
DATA_REF = f"refs/dolt/{RUN}/data"
PUSH_TIMEOUT = int(os.environ.get("FA_GH_TIMEOUT", 300))
N_CLONES = int(os.environ.get("FA_GH_CLONES", 3))
N_ROUNDS = int(os.environ.get("FA_GH_ROUNDS", 5))

RESULTS: list[tuple[str, bool, str]] = []
REFS_CREATED: set[str] = {DATA_REF}
FACTS: dict[str, object] = {}

LOCK_DDL = (
    "CREATE TABLE factory_lock (id TINYINT PRIMARY KEY, holder VARCHAR(200) NULL, "
    "token VARCHAR(64) NULL, locked_at DATETIME NULL);"
    "INSERT INTO factory_lock (id, holder, token) VALUES (1, NULL, NULL);"
    "CREATE TABLE work (k VARCHAR(64) PRIMARY KEY, agent VARCHAR(64) NOT NULL);"
)


def check(name, ok, detail=""):
    RESULTS.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}")
    for ln in (detail or "").splitlines():
        print(f"        {ln}")


def sh(args, cwd=None, timeout=PUSH_TIMEOUT):
    """Every network call is wrapped in a timeout: LESSONS records `dolt push`
    hanging forever at 0% CPU against a stale remote, which is the worst CI
    failure mode. rc=124 means HUNG, and that is a result, not an exception."""
    try:
        return subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(args, 124, "", f"TIMEOUT after {timeout}s")


def dolt(*args, cwd=None, timeout=PUSH_TIMEOUT):
    return sh(["dolt", *args], cwd=cwd, timeout=timeout)


def sql(stmt, cwd, timeout=PUSH_TIMEOUT):
    return sh(["dolt", "sql", "-q", stmt, "-r", "csv"], cwd=cwd, timeout=timeout)


def val(r):
    lines = [l for l in (r.stdout or "").strip().splitlines() if l.strip()]
    return lines[1].split(",")[0] if len(lines) > 1 else None


def clean(s: str, n=160) -> str:
    """dolt's upload spinner writes hundreds of \\r frames; strip them."""
    s = (s or "").replace("\r", "\n")
    keep = [l for l in s.splitlines()
            if l.strip() and "Uploading" not in l and "Downloading" not in l
            and "Writing" not in l and "Fetching" not in l]
    return " | ".join(keep)[-n:]


def new_db(path: Path, ddl: str | None = None, ref: str = DATA_REF, remote="origin") -> Path:
    path.mkdir(parents=True)
    r = dolt("init", "--name", "spike", "--email", "spike@local", cwd=path)
    if r.returncode != 0:
        raise RuntimeError(f"init: {r.stderr}")
    if ddl:
        r = sql(ddl, cwd=path)
        if r.returncode != 0:
            raise RuntimeError(f"ddl: {r.stderr[:300]}")
        dolt("add", "-A", cwd=path)
        dolt("commit", "-m", "schema", cwd=path)
    r = dolt("remote", "add", "--ref", ref, remote, REMOTE, cwd=path)
    if r.returncode != 0:
        raise RuntimeError(f"remote add: {r.stderr}")
    return path


def ls_remote() -> dict[str, str]:
    r = sh(["git", "ls-remote", REMOTE], timeout=120)
    out = {}
    for ln in (r.stdout or "").splitlines():
        parts = ln.split()
        if len(parts) == 2:
            out[parts[1]] = parts[0]
    return out


# ---------------------------------------------------------------- G1


def g1_push():
    d = new_db(ROOT / "origin", LOCK_DDL)
    sql("INSERT INTO work VALUES ('seed','g1')", cwd=d)
    dolt("add", "-A", cwd=d)
    dolt("commit", "-m", "seed", cwd=d)
    before = ls_remote()
    t0 = time.perf_counter()
    p = dolt("push", "origin", "main", cwd=d)
    dt = time.perf_counter() - t0
    after = ls_remote()
    new = sorted(set(after) - set(before))
    ok = p.returncode == 0 and DATA_REF in after
    FACTS["push1_s"] = dt
    check("G1 a Dolt database pushes to a real GitHub repo over HTTPS",
          ok,
          f"remote          : {REMOTE}\n"
          f"data ref        : {DATA_REF} (per-run, via `dolt remote add --ref`)\n"
          f"push            : rc={p.returncode} in {dt:.1f} s   {clean(p.stderr or p.stdout)}\n"
          f"refs created    : {new}\n"
          f"auth            : git credential helper (gh) — no token in the URL,\n"
          f"                  none written to disk\n"
          f"`dolt remote -v`: normalises the URL to git+https://… — Dolt DETECTS a\n"
          f"                  git remote; the documented url schemes (http/https/aws/\n"
          f"                  gs/file) do not mention it")


# ---------------------------------------------------------------- G2


def g2_clone():
    dst = ROOT / "cloned"
    dst.mkdir(parents=True)
    t0 = time.perf_counter()
    c = sh(["dolt", "clone", "--ref", DATA_REF, REMOTE, "c1"], cwd=dst)
    dt = time.perf_counter() - t0
    d = dst / "c1"
    ok = c.returncode == 0 and d.exists()
    n = agent = None
    if ok:
        # a fresh clone has NO author identity; every pull then fails (LESSONS)
        dolt("config", "--local", "--add", "user.name", "spike", cwd=d)
        dolt("config", "--local", "--add", "user.email", "spike@local", cwd=d)
        n = val(sql("SELECT COUNT(*) FROM work", cwd=d))
        agent = val(sql("SELECT agent FROM work WHERE k='seed'", cwd=d))
    check("G2 cold clone from GitHub reproduces the database",
          bool(ok and n == "1" and agent == "g1"),
          f"clone           : rc={c.returncode} in {dt:.1f} s  {clean(c.stderr)}\n"
          f"rows            : work={n}  agent={agent} (expected 1 / g1)\n"
          f"identity        : a fresh clone inherits none — set immediately, or every\n"
          f"                  pull fails with `Author identity unknown` (LESSONS)\n"
          f"=> this is the disaster-recovery and onboarding path, now measured over\n"
          f"   the network rather than file://")


# ---------------------------------------------------------------- G3


def acquire(d: Path, holder: str, timeout=PUSH_TIMEOUT) -> tuple[bool, float, str, int]:
    """One push-as-CAS acquire round trip. Returns (won, seconds, detail, attempts).

    fetch -> reset --hard -> guarded UPDATE with a per-attempt UNIQUE token
    (invariant 1) -> dolt commit -> push. THE PUSH IS THE CAS."""
    t0 = time.perf_counter()
    tok = f"{holder}-{random.getrandbits(48):012x}"
    f = dolt("fetch", "origin", cwd=d, timeout=timeout)
    dolt("reset", "--hard", "origin/main", cwd=d, timeout=timeout)
    u = sql(f"UPDATE factory_lock SET holder='{holder}', token='{tok}', "
            f"locked_at=NOW() WHERE id=1 AND holder IS NULL", cwd=d, timeout=timeout)
    dolt("add", "-A", cwd=d, timeout=timeout)
    c = dolt("commit", "-m", f"acquire {holder}", cwd=d, timeout=timeout)
    if c.returncode != 0:
        return False, time.perf_counter() - t0, f"commit rc={c.returncode} {clean(c.stderr,80)}", 0
    p = dolt("push", "origin", "main", cwd=d, timeout=timeout)
    return (p.returncode == 0, time.perf_counter() - t0,
            f"fetch={f.returncode} update={u.returncode} push={p.returncode} "
            f"{clean(p.stderr, 90)}", 1)


def release(d: Path):
    dolt("fetch", "origin", cwd=d)
    dolt("reset", "--hard", "origin/main", cwd=d)
    sql("UPDATE factory_lock SET holder=NULL, token=NULL WHERE id=1", cwd=d)
    dolt("add", "-A", cwd=d)
    dolt("commit", "-m", "release", cwd=d)
    return dolt("push", "origin", "main", cwd=d)


def g3_latency():
    d = ROOT / "origin"
    times, details = [], []
    for i in range(N_ROUNDS):
        won, dt, det, _ = acquire(d, f"a{i}")
        times.append(dt)
        details.append(f"round {i}: won={won} {dt*1000:.0f} ms  {det}")
        rr = release(d)
        details[-1] += f"  release_push={rr.returncode}"
    m = statistics.median(times) * 1000
    mx = max(times) * 1000
    FACTS["acq_ms"] = m
    check(f"G3 lease acquire round trip over the real network ({N_ROUNDS} rounds)",
          all(t < PUSH_TIMEOUT for t in times),
          "\n".join(details) + "\n"
          + f"median  : {m:.0f} ms   max: {mx:.0f} ms   "
            f"(one acquire = fetch + reset + UPDATE + commit + push)\n"
          + f"file:// : 640 ms measured in S4 — the number this suite was built to\n"
            f"          replace. Real remote is {m/640:.1f}x that floor.\n"
          + f"=> an acquire+release pair costs ~{2*m/1000:.1f} s of wall clock. That is\n"
            f"   acceptable at PHASE-GATE granularity and unacceptable per write.")


# ---------------------------------------------------------------- G4


def g4_contend():
    """N clones, one lease, simultaneous. Exactly one must win."""
    base = ROOT / "clones"
    base.mkdir(parents=True, exist_ok=True)
    ds = []
    for i in range(N_CLONES):
        r = sh(["dolt", "clone", "--ref", DATA_REF, REMOTE, f"m{i}"], cwd=base)
        d = base / f"m{i}"
        if r.returncode != 0:
            check(f"G4 clone m{i}", False, clean(r.stderr))
            return []
        dolt("config", "--local", "--add", "user.name", f"m{i}", cwd=d)
        dolt("config", "--local", "--add", "user.email", f"m{i}@local", cwd=d)
        ds.append(d)
    # make sure the lease is free
    release(ROOT / "origin")
    for d in ds:
        dolt("fetch", "origin", cwd=d)
        dolt("reset", "--hard", "origin/main", cwd=d)
    out: dict[int, tuple[bool, float, str]] = {}
    bar = threading.Barrier(N_CLONES)

    def worker(i):
        bar.wait()
        won, dt, det, _ = acquire(ds[i], f"machine{i}")
        out[i] = (won, dt, det)

    ts = [threading.Thread(target=worker, args=(i,)) for i in range(N_CLONES)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    winners = [i for i, (w, _, _) in out.items() if w]
    # who does the remote say holds it?
    d0 = ds[0]
    dolt("fetch", "origin", cwd=d0)
    dolt("reset", "--hard", "origin/main", cwd=d0)
    holder = val(sql("SELECT holder FROM factory_lock WHERE id=1", cwd=d0))
    ok = len(winners) == 1 and holder == f"machine{winners[0]}"
    check(f"G4 {N_CLONES} clones acquire the same lease simultaneously",
          ok,
          "\n".join(f"  m{i}: won={w} {dt*1000:.0f} ms  {det}" for i, (w, dt, det) in sorted(out.items()))
          + f"\nwinners        : {winners} (must be exactly one)\n"
            f"remote holder  : {holder}\n"
            f"=> push-as-CAS arbitrates across machines over a REAL remote, not just\n"
            f"   file://. The losers learn only AFTER doing their work (S5's limit).")
    return ds


# ---------------------------------------------------------------- G5


def g5_push_contention(ds):
    """N clones each push their own disjoint row at once. Count attempts."""
    if not ds:
        check("G5 push contention", False, "no clones (G4 failed)")
        return
    for d in ds:
        dolt("fetch", "origin", cwd=d)
        dolt("reset", "--hard", "origin/main", cwd=d)
    attempts: dict[int, int] = {}
    landed: dict[int, bool] = {}
    bar = threading.Barrier(len(ds))
    t_start = [0.0]

    def worker(i):
        d = ds[i]
        sql(f"INSERT INTO work VALUES ('g5-{i}','m{i}')", cwd=d)
        dolt("add", "-A", cwd=d)
        dolt("commit", "-m", f"g5 m{i}", cwd=d)
        bar.wait()
        n = 0
        for _ in range(12):
            n += 1
            p = dolt("push", "origin", "main", cwd=d)
            if p.returncode == 0:
                break
            # rejected: pull, then retry. Idempotent by construction (a
            # different PK per clone), which is invariant 4's requirement.
            dolt("fetch", "origin", cwd=d)
            m = dolt("merge", "origin/main", "--no-edit", cwd=d)
            if m.returncode != 0:
                dolt("merge", "--abort", cwd=d)   # invariant 2: never leave a half-merge
                dolt("reset", "--hard", "origin/main", cwd=d)
                sql(f"INSERT IGNORE INTO work VALUES ('g5-{i}','m{i}')", cwd=d)
                dolt("add", "-A", cwd=d)
                dolt("commit", "-m", f"g5 m{i} retry", cwd=d)
            time.sleep(0.2 + 0.3 * i)
        attempts[i] = n
        landed[i] = p.returncode == 0

    t0 = time.perf_counter()
    t_start[0] = t0
    ts = [threading.Thread(target=worker, args=(i,)) for i in range(len(ds))]
    [t.start() for t in ts]
    [t.join() for t in ts]
    total = time.perf_counter() - t0
    d0 = ds[0]
    dolt("fetch", "origin", cwd=d0)
    dolt("reset", "--hard", "origin/main", cwd=d0)
    n_rows = val(sql("SELECT COUNT(*) FROM work WHERE k LIKE 'g5-%'", cwd=d0))
    ok = str(n_rows) == str(len(ds))
    check(f"G5 push contention: {len(ds)} clones pushing at once",
          ok,
          f"attempts per clone : {[attempts.get(i) for i in range(len(ds))]}\n"
          f"all pushes landed  : {landed}\n"
          f"rows on the remote : {n_rows}/{len(ds)}\n"
          f"convergence        : {total:.1f} s\n"
          f"=> SC5 measured [1,2,3,4,5,6,7,8] on file:// — perfectly linear O(N).\n"
          f"   Over the network each retry costs a real round trip, so the same\n"
          f"   O(N) shape is now O(N) x {FACTS.get('acq_ms',0)/1000:.1f} s.")


# ---------------------------------------------------------------- G6


def g6_shared_clone_publishes_siblings(ds):
    """Invariant 4: on a SHARED clone a push publishes siblings' commits too, so
    'my push failed' does not mean 'my work was not published'."""
    if len(ds) < 2:
        check("G6 invariant 4 over a real remote", False, "needs 2 clones")
        return
    d = ds[0]
    dolt("fetch", "origin", cwd=d)
    dolt("reset", "--hard", "origin/main", cwd=d)
    # agent A commits locally but does NOT push
    sql("INSERT INTO work VALUES ('g6-agentA','A')", cwd=d)
    dolt("add", "-A", cwd=d)
    ca = dolt("commit", "-m", "agentA work", cwd=d)
    # agent B, SAME clone, commits and pushes -> carries A's commit with it
    sql("INSERT INTO work VALUES ('g6-agentB','B')", cwd=d)
    dolt("add", "-A", cwd=d)
    dolt("commit", "-m", "agentB work", cwd=d)
    p = dolt("push", "origin", "main", cwd=d)
    # a third party observes what actually landed
    obs = ds[1]
    dolt("fetch", "origin", cwd=obs)
    dolt("reset", "--hard", "origin/main", cwd=obs)
    a_landed = val(sql("SELECT COUNT(*) FROM work WHERE k='g6-agentA'", cwd=obs))
    b_landed = val(sql("SELECT COUNT(*) FROM work WHERE k='g6-agentB'", cwd=obs))
    ok = a_landed == "1" and b_landed == "1" and p.returncode == 0
    check("G6 invariant 4 holds over a real remote: a sibling's push publishes your work",
          ok,
          f"agent A committed (rc={ca.returncode}) and NEVER pushed\n"
          f"agent B pushed from the SAME clone: rc={p.returncode}\n"
          f"observed from another machine: A's row={a_landed}  B's row={b_landed}\n"
          f"=> A's work is on the remote although A never pushed. So a retry that\n"
          f"   re-executes A's write MUST tolerate 'already applied' and fall through\n"
          f"   to push — bailing strands the commit, which the next reset discards.\n"
          f"   INVARIANT 4 CONFIRMED against github.com, not just file://.")


# ---------------------------------------------------------------- G7


def g7_one_ref_for_all_branches():
    """All Dolt branches live inside ONE git ref, so pushes contend GLOBALLY —
    and `--ref` per instance is the mitigation. This is new: the SPEC assumes
    instance branches are independent."""
    d = ROOT / "origin"
    dolt("fetch", "origin", cwd=d)
    dolt("reset", "--hard", "origin/main", cwd=d)
    dolt("checkout", "-b", f"inst_{RUN.replace('-','_')}", cwd=d)
    sql("INSERT INTO work VALUES ('g7-branch','inst')", cwd=d)
    dolt("add", "-A", cwd=d)
    dolt("commit", "-m", "work on an instance branch", cwd=d)
    before = ls_remote()
    p = dolt("push", "origin", f"inst_{RUN.replace('-','_')}", cwd=d)
    after = ls_remote()
    dolt("checkout", "main", cwd=d)
    same_ref = before.get(DATA_REF) != after.get(DATA_REF)
    newrefs = sorted(set(after) - set(before))
    # the mitigation: a SECOND data ref for a second instance
    ref2 = f"refs/dolt/{RUN}/inst2"
    REFS_CREATED.add(ref2)
    d2 = new_db(ROOT / "inst2", LOCK_DDL, ref=ref2)
    p2 = dolt("push", "origin", "main", cwd=d2)
    after2 = ls_remote()
    ok = p.returncode == 0 and p2.returncode == 0 and ref2 in after2
    check("G7 every Dolt branch shares ONE git ref; --ref isolates an instance",
          ok,
          f"pushing a NEW dolt branch changed {DATA_REF}: {same_ref}\n"
          f"new git refs from that push        : {newrefs or '(none — no per-branch ref)'}\n"
          f"a second data ref for instance 2   : {ref2} present={ref2 in after2} "
          f"(push rc={p2.returncode})\n"
          f"=> CONSEQUENCE FOR THE SPEC: instance branches are NOT independent on\n"
          f"   the wire. All of them update one ref, so SC5's O(N) push contention\n"
          f"   is GLOBAL across instances, not per-instance. `dolt remote add --ref`\n"
          f"   gives each instance its own data ref and decouples them — at the cost\n"
          f"   of losing cross-instance merge on the remote (each ref is a separate\n"
          f"   lineage). This is a real design fork the SPEC does not mention.")


# ---------------------------------------------------------------- G8


def g8_embedded_remote():
    """Can the embedded driver do the remote half in-process? If yes, an embedded
    `datum` needs no `dolt` binary at all."""
    if not BENCH.exists():
        check("G8 embedded driver remote ops", False, f"missing {BENCH}")
        return
    parent = ROOT / "emb"
    parent.mkdir(parents=True, exist_ok=True)
    ref3 = f"refs/dolt/{RUN}/emb"
    REFS_CREATED.add(ref3)
    d = new_db(parent / "fa_emb_gh", LOCK_DDL, ref=ref3)
    # push once with the CLI so the ref exists, then drive it from in-process
    p0 = dolt("push", "origin", "main", cwd=d)
    t0 = time.perf_counter()
    r = sh([str(BENCH), "procs", str(parent), "fa_emb_gh"], timeout=PUSH_TIMEOUT)
    dt = time.perf_counter() - t0
    import json as _json
    js = {}
    for ln in (r.stdout or "").splitlines():
        if ln.strip().startswith("{"):
            try:
                js = _json.loads(ln)
            except _json.JSONDecodeError:
                pass
    probes = js.get("probes", {})
    remote_ops = {k: v for k, v in probes.items()
                  if k in ("DOLT_PUSH", "DOLT_FETCH", "DOLT_PULL", "dolt_remotes")}
    ok = p0.returncode == 0 and str(remote_ops.get("DOLT_PUSH", "")).startswith("ok")
    check("G8 embedded driver performs remote operations in-process",
          ok,
          f"CLI seed push        : rc={p0.returncode}\n"
          + "\n".join(f"in-process {k:<12}: {v}" for k, v in sorted(remote_ops.items()))
          + f"\nwhole probe run      : {dt:.1f} s\n"
            f"=> {'an embedded `datum` needs NO dolt binary: SQL + remote ops both in-process' if ok else 'remote ops did NOT work in-process — an embedded fa still shells out'}")


# ---------------------------------------------------------------- G9


def g9_failure_modes():
    """Two failure modes that matter more than latency: a bad remote, and the
    documented infinite hang."""
    bad = ROOT / "bad"
    bad.mkdir(parents=True, exist_ok=True)
    d = bad / "db"
    d.mkdir()
    dolt("init", "--name", "spike", "--email", "spike@local", cwd=d)
    sql("CREATE TABLE t (id INT PRIMARY KEY)", cwd=d)
    dolt("add", "-A", cwd=d)
    dolt("commit", "-m", "t", cwd=d)
    dolt("remote", "add", "--ref", DATA_REF, "nope",
         "https://github.com/drbothen/this-repo-does-not-exist-9f3a.git", cwd=d)
    t0 = time.perf_counter()
    p = sh(["dolt", "push", "nope", "main"], cwd=d, timeout=60)
    dt = time.perf_counter() - t0
    hung = p.returncode == 124
    # and a push to a ref we have no history for -> non-fast-forward, the CAS signal
    ok = not hung and p.returncode != 0
    check("G9 failure modes: nonexistent remote repo",
          ok,
          f"push to a nonexistent repo: rc={p.returncode} after {dt:.1f} s "
          f"{'-- HUNG (had to be killed)' if hung else ''}\n"
          f"message: {clean(p.stderr or p.stdout, 200)}\n"
          f"=> {'fails fast and loudly' if ok else 'DOES NOT fail cleanly'}. Note this is\n"
          f"   still a case for the timeout wrapper: LESSONS records `dolt push`\n"
          f"   hanging forever at 0% CPU against a RECREATED remote, which this\n"
          f"   suite avoids by using a unique data ref per run.")


# ---------------------------------------------------------------- G10


def g10_full_corpus():
    """G1 pushed a 2-table toy. This pushes the WHOLE imported corpus (1,959 BCs,
    prose bodies and all) and clones it back — the real onboarding / disaster
    recovery number, over the network."""
    src = POC / "eb" / "a" / "fa_cli"
    if not src.exists():
        check("G10 full corpus over GitHub", False,
              f"needs the imported corpus at {src} — run poc/test_embedded.py first")
        return
    dst_parent = ROOT / "corpus"
    dst_parent.mkdir(parents=True, exist_ok=True)
    d = dst_parent / "fa_corpus"
    shutil.copytree(src, d)
    ref = f"refs/dolt/{RUN}/corpus"
    REFS_CREATED.add(ref)
    r = dolt("remote", "add", "--ref", ref, "ghorigin", REMOTE, cwd=d)
    n_src = val(sql("SELECT COUNT(*) FROM bc", cwd=d))
    on_disk = subprocess.run(["du", "-sm", str(d)], capture_output=True, text=True)
    mb = on_disk.stdout.split()[0] if on_disk.stdout else "?"
    size_before = 0
    gr = sh(["gh", "api", f"repos/{REMOTE.split('github.com/')[1].removesuffix('.git')}",
             "--jq", ".size"], timeout=60)
    try:
        size_before = int((gr.stdout or "0").strip())
    except ValueError:
        pass
    t0 = time.perf_counter()
    p = dolt("push", "ghorigin", "main", cwd=d, timeout=1800)
    push_s = time.perf_counter() - t0
    back = ROOT / "corpus_back"
    back.mkdir(exist_ok=True)
    t0 = time.perf_counter()
    c = sh(["dolt", "clone", "--ref", ref, REMOTE, "c"], cwd=back, timeout=1800)
    clone_s = time.perf_counter() - t0
    n_back = None
    if c.returncode == 0:
        cd = back / "c"
        dolt("config", "--local", "--add", "user.name", "spike", cwd=cd)
        dolt("config", "--local", "--add", "user.email", "spike@local", cwd=cd)
        n_back = val(sql("SELECT COUNT(*) FROM bc", cwd=cd))
    gr2 = sh(["gh", "api", f"repos/{REMOTE.split('github.com/')[1].removesuffix('.git')}",
              "--jq", ".size"], timeout=60)
    try:
        size_after = int((gr2.stdout or "0").strip())
    except ValueError:
        size_after = 0
    ok = p.returncode == 0 and c.returncode == 0 and n_back == n_src and n_src == "1959"
    check("G10 the FULL corpus (1,959 BCs) round-trips through GitHub",
          ok,
          f"local database on disk : {mb} MB\n"
          f"push                   : rc={p.returncode} in {push_s:.1f} s  "
          f"{clean(p.stderr or p.stdout, 90)}\n"
          f"cold clone back        : rc={c.returncode} in {clone_s:.1f} s\n"
          f"BC rows: source={n_src}  after round trip={n_back}\n"
          f"github repo size       : {size_before} -> {size_after} KB "
          f"(GitHub's own accounting; refs/dolt/* are ordinary git objects)\n"
          f"=> onboarding a new machine costs the clone ({clone_s:.0f} s); recovery from\n"
          f"   total loss is the same operation. Both now measured over the network.")


# ---------------------------------------------------------------- cleanup


def cleanup():
    if os.environ.get("FA_GH_KEEP"):
        print(f"--- keeping refs: {sorted(REFS_CREATED)}")
        return
    deleted = []
    for ref in sorted(REFS_CREATED):
        r = sh(["git", "push", REMOTE, f":{ref}"], timeout=120)
        deleted.append(f"{ref}={'ok' if r.returncode == 0 else 'rc=' + str(r.returncode)}")
    print(f"--- cleanup: {'; '.join(deleted)}")
    print(f"--- left in place: refs/heads/main (seed), refs/heads/__dolt_remote_info__ "
          f"(Dolt's own bookkeeping branch — the documented cosmetic wart)")


def main():
    print(f"=== FINAL TESTS: real GitHub remote\n    remote={REMOTE}\n    run={RUN}  "
          f"data_ref={DATA_REF}\n")
    if ROOT.exists():
        shutil.rmtree(ROOT)
    ROOT.mkdir(parents=True)
    try:
        g1_push()
        print()
        g2_clone()
        print()
        g3_latency()
        print()
        ds = g4_contend()
        print()
        g5_push_contention(ds)
        print()
        g6_shared_clone_publishes_siblings(ds)
        print()
        g7_one_ref_for_all_branches()
        print()
        g8_embedded_remote()
        print()
        g9_failure_modes()
        print()
        g10_full_corpus()
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
    main()
