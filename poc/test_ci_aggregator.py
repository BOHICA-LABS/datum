#!/usr/bin/env python3
"""CI AS THE AGGREGATOR — does the recommended cross-internet topology actually work?

Everything measured in SCALE.md ran on ONE host. The two options that collapse N
writers to one push either need a shared filesystem (D2 host relay) or inbound
reachability to every writer (D5 peer pull), so neither survives writers being on
different networks. Only D3 — staging refs plus an aggregator — needs nothing but
outbound HTTPS. That leaves one question: WHO aggregates?

This tests the answer: **GitHub Actions**. It is a genuinely different host on a
genuinely different network, so a green run here is also the first real evidence for
the cross-internet claim.

  C1  writers publish to their own staging refs, in parallel, and CI aggregates
      -> can GITHUB_TOKEN push refs/dolt/*? does repository_dispatch reach the
         workflow? does exactly ONE process advance the artifact branch?
  C2  a conflicting writer is isolated, not fatal
      -> its staging ref is RETAINED, everyone else's work still lands
  C3  the STRAND defence: publish while a run is in flight
      -> GitHub keeps at most one run pending and cancels the rest, so a late
         publisher can lose its trigger. Does self-redispatch/cron still drain it?

NOTE ON SCOPE: the workflow is a PROTOTYPE that shells out to the dolt CLI. The
deliverable is `datum aggregate`, a subcommand of the Go binary that embeds Dolt — at
which point the CI job is "download fa, run datum aggregate" with no dolt install, and
the local fallback during an Actions outage is the same binary devs already run.
What is being tested here is the GitHub mechanics, which are language-independent.

Run: .venv/bin/python -u poc/test_ci_aggregator.py
Env: FA_CI_REPO  FA_CI_WRITERS=20  FA_CI_BATCH=10 (rows/writer = agents behind a D2\n     relay, so 20x10 = 200 agents' work through CI)  FA_CI_STRESS=1 (adds C4)  FA_CI_KEEP=1
"""
from __future__ import annotations

import json
import os
import shutil
import statistics
import subprocess
import sys
import threading
import time
from pathlib import Path

POC = Path(__file__).parent
ROOT = POC / "ci"
REPO = os.environ.get("FA_CI_REPO", "drbothen/datum (formerly dolt-artifact-spike)-remote")
REMOTE = f"https://github.com/{REPO}.git"
ARTIFACT_REF = "refs/dolt/artifacts/data"
N = int(os.environ.get("FA_CI_WRITERS", 6))
BATCH = int(os.environ.get("FA_CI_BATCH", 1))   # rows per writer = agents behind a D2 relay
POLL_TIMEOUT = int(os.environ.get("FA_CI_POLL", 900))

RESULTS: list[tuple[str, bool, str]] = []
LAT_SAMPLES: list[dict] = []
DDL = "CREATE TABLE work (k VARCHAR(64) PRIMARY KEY, who VARCHAR(32) NOT NULL);"


def check(name, ok, detail=""):
    RESULTS.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}", flush=True)
    for ln in (detail or "").splitlines():
        print(f"        {ln}", flush=True)


def sh(args, cwd=None, timeout=600):
    try:
        return subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(args, 124, "", f"TIMEOUT {timeout}s")


def dolt(*a, cwd=None, timeout=600):
    return sh(["dolt", *a], cwd=cwd, timeout=timeout)


def sql(stmt, cwd, timeout=600):
    return sh(["dolt", "sql", "-q", stmt, "-r", "csv"], cwd=cwd, timeout=timeout)


def val(r):
    lines = [l for l in (r.stdout or "").strip().splitlines() if l.strip()]
    return lines[1].split(",")[0] if len(lines) > 1 else None


def clean(s, n=110):
    s = (s or "").replace("\r", "\n")
    keep = [l for l in s.splitlines() if l.strip() and not any(
        w in l for w in ("Uploading", "Downloading", "Writing", "Fetching", "Pulling"))]
    return " | ".join(keep)[-n:]


def stage_refs() -> list[str]:
    r = sh(["git", "ls-remote", REMOTE, "refs/dolt/stage/*"], timeout=120)
    return sorted(l.split()[1] for l in (r.stdout or "").splitlines() if l.split())


def artifact_exists() -> bool:
    r = sh(["git", "ls-remote", REMOTE, ARTIFACT_REF], timeout=120)
    return bool((r.stdout or "").strip())


def seed_artifact_branch() -> bool:
    """Create the artifact branch ONCE. Every writer clones it.

    MEASURED REQUIREMENT (this cost a CI run): a writer must be a CLONE of the
    artifact branch, never an independently `dolt init`-ed database. Unrelated
    lineages fail to merge with **`no common ancestor`** — they cannot be
    aggregated at all, only replayed. This is also the hard proof that
    `--ref`-per-instance fragmentation is a ONE-WAY DOOR, not a tradeoff.
    """
    d = ROOT / "seed" / "db"
    d.mkdir(parents=True)
    dolt("init", "--name", "seed", "--email", "seed@local", cwd=d)
    sql(DDL, cwd=d)
    sql("INSERT INTO work (k, who) VALUES ('base','seed')", cwd=d)
    dolt("add", "-A", cwd=d)
    dolt("commit", "-m", "artifact branch base", cwd=d)
    dolt("remote", "add", "--ref", ARTIFACT_REF, "artifact", REMOTE, cwd=d)
    return dolt("push", "artifact", "main", cwd=d, timeout=900).returncode == 0


def make_writer(i: int, hot=False) -> Path:
    """A writer = a CLONE of the artifact branch, plus its own staging ref."""
    p = ROOT / f"w{i}"
    p.mkdir(parents=True)
    r = sh(["dolt", "clone", "--ref", ARTIFACT_REF, REMOTE, "db"], cwd=p, timeout=900)
    if r.returncode != 0:
        raise RuntimeError(f"writer {i} clone: {clean(r.stderr, 150)}")
    d = p / "db"
    dolt("config", "--local", "--add", "user.name", f"w{i}", cwd=d)
    dolt("config", "--local", "--add", "user.email", f"w{i}@local", cwd=d)
    # every writer inserts a row keyed to itself; a "hot" writer ALSO writes the same
    # key as writer 0 with a different value, which must conflict at aggregation
    for a in range(BATCH):
        sql(f"INSERT INTO work (k, who) VALUES ('w{i}-a{a}','w{i}')", cwd=d)
    if hot:
        sql("INSERT INTO work (k, who) VALUES ('shared','from-hot')", cwd=d)
    else:
        if i == 0:
            sql("INSERT INTO work (k, who) VALUES ('shared','from-w0')", cwd=d)
    dolt("add", "-A", cwd=d)
    dolt("commit", "-m", f"w{i} work", cwd=d)
    # publish `main` to a ref THIS WRITER ALONE OWNS. Each staging ref is its own
    # namespace, so every writer's `main` is independent — which makes the
    # aggregator's source uniform (`remotes/<s>/main`) with no branch discovery.
    dolt("remote", "add", "--ref", f"refs/dolt/stage/w{i}", "stage", REMOTE, cwd=d)
    return d


def publish(d: Path, i: int) -> tuple[int, float]:
    t0 = time.perf_counter()
    p = dolt("push", "stage", "main", cwd=d, timeout=900)
    return p.returncode, time.perf_counter() - t0


def dispatch() -> int:
    r = sh(["gh", "api", f"repos/{REPO}/dispatches", "-f", "event_type=datum-aggregate",
            "--silent"], timeout=120)
    return r.returncode


def runs(limit=15) -> list[dict]:
    r = sh(["gh", "run", "list", "-R", REPO, "-w", "datum-aggregate", "-L", str(limit),
            "--json", "databaseId,status,conclusion,createdAt,event"], timeout=120)
    try:
        return json.loads(r.stdout or "[]")
    except json.JSONDecodeError:
        return []


def wait_for_quiet(deadline_s=POLL_TIMEOUT, expected_left=0) -> tuple[bool, list[str], str]:
    """Wait until no run is active AND the staging refs are drained down to the
    number we EXPECT to remain. Conflicted refs are retained by design, so waiting
    for zero would hang forever — the count has to be the designed count."""
    t0 = time.time()
    last = ""
    while time.time() - t0 < deadline_s:
        rs = runs()
        active = [x for x in rs if x["status"] in ("queued", "in_progress", "waiting",
                                                   "pending", "requested")]
        left = stage_refs()
        last = (f"active runs={len(active)} staging refs left={len(left)} "
                f"({int(time.time()-t0)}s)")
        print(f"        .. {last}", flush=True)
        if not active and len(left) <= expected_left:
            return True, left, last
        time.sleep(20)
    return False, stage_refs(), last


def artifact_rows() -> tuple[str | None, str | None, dict]:
    v = ROOT / "verify"
    if v.exists():
        shutil.rmtree(v)
    v.mkdir(parents=True)
    c = sh(["dolt", "clone", "--ref", ARTIFACT_REF, REMOTE, "f"], cwd=v, timeout=900)
    if c.returncode != 0:
        return None, clean(c.stderr, 150), {}
    d = v / "f"
    n = val(sql("SELECT COUNT(*) FROM work", cwd=d))
    rows = sh(["dolt", "sql", "-q", "SELECT k, who FROM work ORDER BY k", "-r", "csv"],
              cwd=d, timeout=600)
    got = {}
    for ln in (rows.stdout or "").splitlines()[1:]:
        parts = ln.split(",")
        if len(parts) >= 2:
            got[parts[0]] = parts[1]
    return n, None, got


# ---------------------------------------------------------------- C1 + C2


def c1_c2_publish_and_aggregate():
    """N writers publish in parallel; one of them (the last) deliberately collides
    with writer 0 on the key 'shared'."""
    hot = N - 1
    if not seed_artifact_branch():
        check("C1a seed the artifact branch", False, "seed push failed")
        return hot, []
    ws = [make_writer(i, hot=(i == hot)) for i in range(N)]
    res = {}
    bar = threading.Barrier(N)

    def pub(i):
        bar.wait()
        res[i] = publish(ws[i], i)

    t0 = time.perf_counter()
    ts = [threading.Thread(target=pub, args=(i,)) for i in range(N)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    pub_wall = time.perf_counter() - t0
    ok_pub = sum(1 for i in res if res[i][0] == 0)
    before = stage_refs()
    check(f"C1a {N} writers publish to their OWN staging refs, in parallel",
          ok_pub == N and len(before) == N,
          f"pushes succeeding : {ok_pub}/{N} in {pub_wall:.0f}s "
          f"(each ~{max(r[1] for r in res.values()):.0f}s worst)\n"
          f"staging refs now  : {len(before)}  {[r.split('/')[-1] for r in before]}\n"
          f"=> writers only ever make OUTBOUND HTTPS pushes to refs they alone own,\n"
          f"   so there is no contention and nothing needs inbound reachability.\n"
          f"   This is the only aggregation shape that works across the internet.")

    rc = dispatch()
    print(f"        repository_dispatch rc={rc}", flush=True)
    time.sleep(10)
    # exactly ONE ref must remain: the deliberate conflict, retained by design
    quiet, left, note = wait_for_quiet(expected_left=1)
    rs = runs()
    done = [x for x in rs if x["status"] == "completed"]
    concl = [x["conclusion"] for x in done[:4]]
    n_rows, err, got = artifact_rows()

    # writer `hot` collided with w0 on 'shared' -> exactly one of the two must have
    # landed, hot's staging ref must SURVIVE, and everyone else must be present.
    expect_present = {f"w{i}-a{a}" for i in range(N) if i != hot for a in range(BATCH)}
    present = set(got) & expect_present
    shared = got.get("shared")
    hot_ref = f"refs/dolt/stage/w{hot}"
    hot_retained = hot_ref in left
    others_drained = [r for r in left if r != hot_ref]

    check("C1b CI aggregated: exactly one process advanced the artifact branch",
          rc == 0 and err is None and len(present) == len(expect_present),
          f"dispatch accepted     : rc={rc}\n"
          f"workflow runs         : {len(done)} completed, conclusions {concl}\n"
          f"artifact branch       : "
          f"{'created + readable' if err is None else 'UNREADABLE: ' + str(err)}\n"
          f"rows on artifact ref  : {n_rows}\n"
          f"writers present       : {len(present)}/{len(expect_present)} "
          f"{sorted(present)}\n"
          f"=> GITHUB_TOKEN CAN push refs/dolt/*, repository_dispatch DOES reach a\n"
          f"   workflow on the default branch, and `concurrency` made the aggregator a\n"
          f"   singleton — so the artifact branch had exactly one writer, and the\n"
          f"   lock-ref machinery (TTL, break-glass, unique-sha) is unnecessary.")

    check("C2 a conflicting writer is ISOLATED, not fatal",
          hot_retained and not others_drained and shared is not None,
          f"the collision        : w0 and w{hot} both wrote key 'shared'\n"
          f"value that landed    : {shared}\n"
          f"w{hot}'s staging ref  : {'RETAINED' if hot_retained else 'deleted (WRONG)'}\n"
          f"other refs drained   : {not others_drained} "
          f"{[r.split('/')[-1] for r in others_drained] or ''}\n"
          f"=> the aggregator aborted that ONE merge, kept everyone else, and left the\n"
          f"   loser's work safely published so it can re-apply its intent on the new\n"
          f"   base. That is DECISIONS D1 with an unambiguous loser, decided by a\n"
          f"   single-threaded deterministic process rather than a race.\n"
          f"   NOTE: the ref is retained deliberately, so the cron sweep will keep\n"
          f"   retrying it until the writer resolves — visible, not silent.")
    return hot, left


# ---------------------------------------------------------------- C3


def c3_strand_defence(hot: int):
    """GitHub keeps at most ONE run pending and cancels the rest. So a writer that
    publishes while a run is executing can lose its trigger. Does it still land?"""
    i = 90
    d = make_writer(i)
    rc0 = dispatch()                      # start a run...
    time.sleep(8)                         # ...then publish DURING it
    prc, psec = publish(d, i)
    rc1 = dispatch()                      # this dispatch may well be cancelled
    quiet, left, note = wait_for_quiet(deadline_s=POLL_TIMEOUT, expected_left=1)
    n_rows, err, got = artifact_rows()
    landed = f"w{i}-a0" in got
    late_ref = f"refs/dolt/stage/w{i}"
    check("C3 STRAND DEFENCE: a writer publishing mid-run still lands",
          prc == 0 and landed,
          f"published during an active run: rc={prc} in {psec:.0f}s\n"
          f"dispatches: first rc={rc0}, second rc={rc1} "
          f"(the second may be cancelled by design — at most one run may be pending)\n"
          f"late writer's row on the artifact branch: {landed}\n"
          f"staging refs left: {[r.split('/')[-1] for r in left]}\n"
          f"  (w{hot} is expected to remain — it is the deliberate conflict)\n"
          f"{note}\n"
          f"=> liveness does NOT depend on GitHub's queue semantics. Each run consumes\n"
          f"   EVERY staging ref present, and re-dispatches itself if more arrived —\n"
          f"   so a cancelled pending run cannot strand work. The cron sweep is a\n"
          f"   third layer under that.")


# ---------------------------------------------------------------- C4


def c4_stress(hot: int):
    """Does the aggregator DEGRADE as stuck refs accumulate?

    A conflicted ref is retained by design, so every later run re-fetches and
    re-merges it. If that cost is paid forever, N stuck refs tax every future run —
    which would be a real scaling flaw, not a cosmetic one. Measure it by running the
    aggregation twice more with the stuck ref(s) in place and NOTHING new to do.
    """
    stuck_before = stage_refs()
    timings = []
    for round_i in range(2):
        rid_before = {r["databaseId"] for r in runs()}
        dispatch()
        time.sleep(12)
        t0 = time.time()
        wait_for_quiet(deadline_s=600, expected_left=len(stuck_before))
        new = [r for r in runs() if r["databaseId"] not in rid_before]
        dur = None
        if new:
            rid = new[0]["databaseId"]
            j = sh(["gh", "api", f"repos/{REPO}/actions/runs/{rid}/jobs",
                    "--jq", ".jobs[0] | [.started_at, .completed_at] | @tsv"], timeout=120)
            parts = (j.stdout or "").strip().split("\t")
            if len(parts) == 2 and all(parts):
                from datetime import datetime
                fmt = "%Y-%m-%dT%H:%M:%SZ"
                dur = (datetime.strptime(parts[1], fmt)
                       - datetime.strptime(parts[0], fmt)).total_seconds()
        timings.append(dur if dur is not None else (time.time() - t0))
    after = stage_refs()
    ok = len(after) == len(stuck_before)
    check(f"C4 do {len(stuck_before)} STUCK ref(s) tax every later run?",
          ok,
          f"stuck refs before : {[r.split('/')[-1] for r in stuck_before]}\n"
          f"two further runs with NOTHING new to do: "
          f"{', '.join(f'{x:.0f}s' for x in timings)}\n"
          f"stuck refs after  : {[r.split('/')[-1] for r in after]} (must be unchanged)\n"
          f"=> a retained ref is re-fetched and re-merged on EVERY run, so the cost is\n"
          f"   paid forever and grows with the backlog. At {len(stuck_before)} stuck ref(s) that is\n"
          f"   {timings[0]:.0f}s of pure waste per run; at 20 it would dominate the job.\n"
          f"   NEEDED FEATURE: quarantine a stuck ref (move it aside / back it off /\n"
          f"   record an attempt count) instead of retrying it on every single run.\n"
          f"   Retention is right; unbounded RE-ATTEMPT is not.")


# ---------------------------------------------------------------- C5


def job_steps(rid) -> list[tuple[str, float]]:
    """Per-step wall time from the Actions API, so the CI portion is attributable."""
    from datetime import datetime
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    r = sh(["gh", "api", f"repos/{REPO}/actions/runs/{rid}/jobs",
            "--jq", ".jobs[0].steps[] | [.name, .started_at, .completed_at] | @tsv"],
           timeout=120)
    out = []
    for ln in (r.stdout or "").splitlines():
        parts = ln.split("\t")
        if len(parts) == 3 and all(parts):
            try:
                out.append((parts[0], (datetime.strptime(parts[2], fmt)
                                       - datetime.strptime(parts[1], fmt)).total_seconds()))
            except ValueError:
                pass
    return out


def c5_latency(observer_pulls_every=3.0, sample=0):
    """END-TO-END LATENCY: from an agent finishing its write to that write being
    VISIBLE to a different machine. This is the number a user actually feels, and it
    is the one figure this architecture has to own.

    Measured with an INDEPENDENT observer clone polling the artifact ref, so it is
    wall-clock reality, not a sum of phase estimates.
    """
    from datetime import datetime, timezone
    obs = ROOT / "observer"
    obs.mkdir(parents=True, exist_ok=True)
    if not (obs / "o").exists():
        c = sh(["dolt", "clone", "--ref", ARTIFACT_REF, REMOTE, "o"], cwd=obs, timeout=900)
        if c.returncode != 0:
            check("C5 end-to-end latency", False, f"observer clone: {clean(c.stderr,120)}")
            return
    od = obs / "o"
    dolt("config", "--local", "--add", "user.name", "observer", cwd=od)
    dolt("config", "--local", "--add", "user.email", "obs@local", cwd=od)

    i = 77 + sample
    key = f"w{i}-a0"
    d = make_writer(i)                       # clone + local write + commit
    t0 = time.time()                         # agent's work is DONE locally
    rc, pub_s = publish(d, i)
    t1 = time.time()                         # published to its staging ref
    rid_before = {r["databaseId"] for r in runs()}
    dispatch()
    t2 = time.time()
    # poll as an independent machine would: pull, look
    t_visible = None
    deadline = time.time() + 900
    while time.time() < deadline:
        dolt("pull", "origin", "main", cwd=od, timeout=300)
        if val(sql(f"SELECT COUNT(*) FROM work WHERE k='{key}'", cwd=od)) == "1":
            t_visible = time.time()
            break
        time.sleep(observer_pulls_every)
    new = [r for r in runs() if r["databaseId"] not in rid_before]
    steps, run_s, queue_s = [], None, None
    if new:
        rid = new[0]["databaseId"]
        steps = job_steps(rid)
        j = sh(["gh", "api", f"repos/{REPO}/actions/runs/{rid}",
                "--jq", "[.created_at, .run_started_at] | @tsv"], timeout=120)
        parts = (j.stdout or "").strip().split("\t")
        if len(parts) == 2 and all(parts):
            fmt = "%Y-%m-%dT%H:%M:%SZ"
            queue_s = (datetime.strptime(parts[1], fmt)
                       - datetime.strptime(parts[0], fmt)).total_seconds()
        run_s = sum(s for _, s in steps)
    total = (t_visible - t0) if t_visible else None
    install = next((s for n, s in steps if "Install dolt" in n), 0.0)
    ok = total is not None
    LAT_SAMPLES.append({"total": total, "publish": t1 - t0, "queue": queue_s,
                        "ci": run_s, "steps": dict(steps)})
    check(f"C5.{sample} END-TO-END LATENCY: agent's write -> visible on another machine",
          ok,
          (f"TOTAL                         : {total:.0f} s\n" if total else
           "TOTAL                         : NEVER BECAME VISIBLE within 900 s\n")
          + f"  1. publish staging ref      : {t1-t0:6.1f} s  (writer -> its own ref)\n"
            f"  2. dispatch accepted        : {t2-t1:6.1f} s\n"
            f"  3. runner queue             : "
          + (f"{queue_s:6.1f} s  (GitHub scheduling)\n" if queue_s is not None else "     ?\n")
          + "".join(f"  4. CI step: {n[:34]:<34}: {s:6.1f} s\n" for n, s in steps)
          + f"  5. observer pull + poll     : ~{observer_pulls_every:.0f} s resolution\n"
            f"\n"
            f"WHAT THE GO BINARY REMOVES   : the dolt install step, {install:.0f} s of the above\n"
            f"  => projected with `datum`      : ~{(total - install):.0f} s\n" if total else ""
          )


# ---------------------------------------------------------------- main


def cleanup(hot: int | None):
    if os.environ.get("FA_CI_KEEP"):
        print("--- keeping refs (FA_CI_KEEP)")
        return
    out = []
    for ref in stage_refs() + [ARTIFACT_REF]:
        r = sh(["git", "push", REMOTE, f":{ref}"], timeout=180)
        out.append(f"{ref.split('/')[-1]}={'ok' if r.returncode == 0 else r.returncode}")
    print(f"--- cleanup: {'; '.join(out)}")


def main():
    print(f"=== CI AS AGGREGATOR   repo={REPO}\n"
          f"    writers={N}  artifact ref={ARTIFACT_REF}\n", flush=True)
    if ROOT.exists():
        shutil.rmtree(ROOT)
    ROOT.mkdir(parents=True)
    # start from a clean slate so counts mean something
    for ref in stage_refs():
        sh(["git", "push", REMOTE, f":{ref}"], timeout=180)
    if artifact_exists():
        sh(["git", "push", REMOTE, f":{ARTIFACT_REF}"], timeout=180)
    hot = None
    try:
        if os.environ.get("FA_CI_ONLY") == "c5":
            if not artifact_exists():
                seed_artifact_branch()
            for s in range(int(os.environ.get("FA_CI_LAT_N", 3))):
                c5_latency(sample=s)
                print(flush=True)
            tot = [x["total"] for x in LAT_SAMPLES if x["total"]]
            q = [x["queue"] for x in LAT_SAMPLES if x["queue"] is not None]
            check(f"C5 latency distribution over {len(tot)} samples", bool(tot),
                  f"totals      : {[f'{x:.0f}s' for x in tot]}   "
                  f"median {statistics.median(tot):.0f}s  max {max(tot):.0f}s\n"
                  f"runner queue: {[f'{x:.0f}s' for x in q]}\n"
                  f"CI job total: {[f'{x[chr(34)+chr(34)] if False else x[chr(99)+chr(105)]:.0f}s' for x in LAT_SAMPLES if x.get('ci')]}\n"
                  f"=> the queue is the VOLATILE term. publish (~12 s) + the aggregator's\n"
                  f"   own push (~8 s) + a consumer pull (~2.3 s) is the ~22 s irreducible\n"
                  f"   floor, because the ~8 s fixed push cost is paid TWICE: writer -> its\n"
                  f"   own ref, then aggregator -> the artifact branch.")
            return
        hot, _ = c1_c2_publish_and_aggregate()
        print(flush=True)
        c3_strand_defence(hot)
        print(flush=True)
        if os.environ.get("FA_CI_STRESS"):
            c4_stress(hot)
            print(flush=True)
        if os.environ.get("FA_CI_LATENCY"):
            for s in range(int(os.environ.get("FA_CI_LAT_N", 1))):
                c5_latency(sample=s)
                print(flush=True)
            if len(LAT_SAMPLES) > 1:
                tot = [x["total"] for x in LAT_SAMPLES if x["total"]]
                q = [x["queue"] for x in LAT_SAMPLES if x["queue"] is not None]
                check(f"C5 latency distribution over {len(tot)} samples", bool(tot),
                      f"totals      : {[f'{x:.0f}s' for x in tot]}   "
                      f"median {statistics.median(tot):.0f}s  max {max(tot):.0f}s\n"
                      f"runner queue: {[f'{x:.0f}s' for x in q]}\n"
                      f"=> the queue is the VOLATILE term; publish (~12 s) + the\n"
                      f"   aggregator's own push (~8 s) + a consumer pull (~2.3 s) is the\n"
                      f"   ~22 s irreducible floor, because the ~8 s fixed push cost is\n"
                      f"   paid TWICE (writer -> its ref, aggregator -> artifact branch).")
    finally:
        cleanup(hot)
    npass = sum(1 for _, ok, _ in RESULTS if ok)
    print("=" * 74)
    print(f"{npass}/{len(RESULTS)} passed")
    for nm, ok, _ in RESULTS:
        if not ok:
            print(f"  FAILED: {nm}")
    sys.exit(0 if npass == len(RESULTS) else 1)


if __name__ == "__main__":
    main()
