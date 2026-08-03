#!/usr/bin/env python3
"""EXHAUST THE DECENTRALISED OPTIONS — one artifact branch, no server, N=20 pushers.

Constraint from the design: the factory's artifact store is ONE branch. So the
question is how cheaply N writers can land work on one branch pointer with no
daemon anywhere.

Cost model, from measurements already in hand:
    a push attempt costs ~8 s FIXED, independent of payload (O3)
    naive retry      => O(N^2/2) attempts   (N=20: ~210 attempts)
    queued           => O(N)     attempts   (N=20:   20)
    AGGREGATED       => O(1)     attempts   (N=20:    1)   <- the only real win

Arms, in increasing cleverness. Every one is decentralised: no server, no daemon.

  D1  RETRY SHAPE      same free-for-all, three retry policies
                       A immediate retry   B exponential+jitter   C ticket order
                       -> how much waste is just a bad backoff?
  D2  HOST RELAY       instances on a host push to a LOCAL file:// relay serialised
                       by flock (free, kernel-released), then ONE network push per
                       host  -> N collapses from clones to HOSTS
  D3  STAGING REFS     each writer publishes to its own EPHEMERAL ref in parallel
                       (no contention), one aggregator merges all N and does ONE
                       push to the artifact branch, then deletes the refs
                       -> N collapses to 1. The artifact branch stays single and
                          canonical; the refs are transport, not storage.
  D4  TRANSPORT        what IS the fixed ~8 s? https vs ssh
                       -> can the constant itself be cut?
  D5  PEER PULL        every writer SERVES itself (`--remotesapi-port`); the
                       aggregator pulls straight from peers, so writers never touch
                       the shared remote -> O(1), no staging refs. Costs a listener
                       per writer + peer reachability.

Every arm must land IDENTICAL rows on the single artifact branch, verified from a
fresh clone.

Run: .venv/bin/python -u poc/test_decentral.py
Env: FA_DC_N=20 FA_DC_WORK=3 FA_DC_ONLY=d2,d3 FA_GH_REMOTE FA_GH_KEEP=1
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

sys.path.insert(0, str(Path(__file__).parent))
from clonelock import clone_write_lock  # noqa: E402

POC = Path(__file__).parent
ROOT = POC / "dc"
REMOTE = os.environ.get("FA_GH_REMOTE",
                        "https://github.com/drbothen/datum (formerly dolt-artifact-spike)-remote.git")
RUN = os.environ.get("FA_DC_RUN") or f"dc-{int(time.time())}"
N = int(os.environ.get("FA_DC_N", 20))
N_WORK = int(os.environ.get("FA_DC_WORK", 3))
TIMEOUT = int(os.environ.get("FA_DC_TIMEOUT", 900))
ONLY = {x.strip().lower() for x in os.environ.get("FA_DC_ONLY", "").split(",") if x.strip()}

RESULTS: list[tuple[str, bool, str]] = []
REFS: set[str] = set()
FACTS: dict[str, object] = {}

DDL = "CREATE TABLE work (k VARCHAR(64) PRIMARY KEY, who VARCHAR(32) NOT NULL);"


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


def seed(tag: str, remote=None) -> tuple[Path, str]:
    """Origin database on its own data ref (or a local file:// remote)."""
    ref = f"refs/dolt/{RUN}/{tag}"
    d = ROOT / tag / "origin" / "db"
    d.mkdir(parents=True)
    dolt("init", "--name", "dc", "--email", "dc@local", cwd=d)
    sql(DDL, cwd=d)
    dolt("add", "-A", cwd=d)
    dolt("commit", "-m", "schema", cwd=d)
    if remote:
        dolt("remote", "add", "origin", remote, cwd=d)
    else:
        REFS.add(ref)
        dolt("remote", "add", "--ref", ref, "origin", REMOTE, cwd=d)
    p = dolt("push", "origin", "main", cwd=d, timeout=1800)
    if p.returncode != 0:
        raise RuntimeError(f"seed push {tag}: {clean(p.stderr, 200)}")
    return d, ref


def clones(tag: str, ref: str | None, n: int, remote=None) -> list[Path]:
    """n clones, each in its OWN parent dir (parallel dolt clone collides in
    <cwd>/.dolt/tmp otherwise — that cost a run)."""
    base = ROOT / tag / "clones"
    out: list[Path] = [None] * n                                   # type: ignore
    errs = {}

    def one(i):
        p = base / f"p{i}"
        p.mkdir(parents=True, exist_ok=True)
        args = ["dolt", "clone"]
        if ref:
            args += ["--ref", ref]
        args += [remote or REMOTE, f"c{i}"]
        r = sh(args, cwd=p, timeout=1800)
        if r.returncode != 0:
            errs[i] = clean(r.stderr, 120)
            return
        d = p / f"c{i}"
        dolt("config", "--local", "--add", "user.name", f"c{i}", cwd=d)
        dolt("config", "--local", "--add", "user.email", f"c{i}@local", cwd=d)
        out[i] = d

    ts = [threading.Thread(target=one, args=(i,)) for i in range(n)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    if errs:
        raise RuntimeError(f"clone failures: {errs}")
    return out


def do_work(d: Path, who: str, tag: str, n=N_WORK):
    for j in range(n):
        sql(f"INSERT INTO work (k, who) VALUES ('{tag}-{who}-{j}','{who}')", cwd=d)
    dolt("add", "-A", cwd=d)
    dolt("commit", "-m", f"{who} work", cwd=d)


def landed(tag: str, ref: str | None, remote=None) -> str:
    v = ROOT / tag / "verify"
    v.mkdir(parents=True, exist_ok=True)
    args = ["dolt", "clone"]
    if ref:
        args += ["--ref", ref]
    args += [remote or REMOTE, "f"]
    if not (v / "f").exists():
        sh(args, cwd=v, timeout=1800)
    return val(sql(f"SELECT COUNT(*) FROM work WHERE k LIKE '{tag}-%'", cwd=v / "f"))


# ---------------------------------------------------------------- D1


def d1_retry_shape():
    """Same free-for-all, three retry policies. How much waste is just backoff?"""
    arms = {}
    for arm, label in (("A", "immediate retry"),
                       ("B", "exponential + jitter"),
                       ("C", "deterministic ticket order")):
        tag = f"d1{arm.lower()}"
        _, ref = seed(tag)
        cs = clones(tag, ref, N)
        for i, d in enumerate(cs):
            do_work(d, f"c{i}", tag)
        attempts, oks = {}, {}
        bar = threading.Barrier(N)

        def worker(i):
            d = cs[i]
            bar.wait()
            n = 0
            p = None
            for a in range(N + 10):
                n += 1
                p = dolt("push", "origin", "main", cwd=d)
                if p.returncode == 0:
                    break
                dolt("pull", "origin", "main", cwd=d)
                if arm == "A":
                    time.sleep(0.2)
                elif arm == "B":
                    time.sleep(min(30, (2 ** a) * 0.5) * (0.5 + random.random()))
                else:
                    # ticket: writer i waits i*T so the fleet self-orders instead of
                    # thundering. No coordination, no shared state.
                    time.sleep(1.5 * i + random.random())
            attempts[i], oks[i] = n, bool(p and p.returncode == 0)

        t0 = time.perf_counter()
        ts = [threading.Thread(target=worker, args=(i,)) for i in range(N)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        wall = time.perf_counter() - t0
        arms[arm] = {"label": label, "attempts": sum(attempts.values()),
                     "max": max(attempts.values()), "wall": wall,
                     "ok": sum(1 for i in oks if oks[i]),
                     "landed": landed(tag, ref)}
    exp = N * N_WORK
    ok = all(a["landed"] == str(exp) for a in arms.values())
    FACTS["d1"] = arms
    best = min(arms.values(), key=lambda a: a["wall"])
    check(f"D1 RETRY SHAPE: {N} pushers, one branch, three retry policies",
          ok,
          "\n".join(
              f"  {k} {a['label']:<28} attempts {a['attempts']:>4} (worst {a['max']:>2})  "
              f"wall {a['wall']:>6.0f}s  landed {a['landed']}/{exp}"
              for k, a in sorted(arms.items()))
          + f"\n  O(N) for N={N} predicts {N*(N+1)//2} attempts; a perfect queue is {N}\n"
          + f"=> backoff alone {'HELPS' if best['wall'] < arms['A']['wall'] * 0.8 else 'does NOT help much'}"
            f" (best: {best['label']}, {arms['A']['wall']/max(best['wall'],0.01):.2f}x vs immediate).\n"
            f"   Waste is inherent to optimistic retry: every loser pays a full ~8 s push\n"
            f"   to learn it lost. Backoff spreads the losses; it cannot remove them.")


# ---------------------------------------------------------------- D2


def d2_host_relay():
    """Instances on a host push to a LOCAL file:// relay, serialised by flock —
    both free — and ONE designated pusher syncs the relay to origin. N collapses
    from clones to HOSTS, and the artifact branch is still one branch."""
    tag = "d2"
    relay_dir = ROOT / tag / "relay"
    relay_dir.mkdir(parents=True, exist_ok=True)
    relay = f"file://{relay_dir}"
    # the relay is seeded from the same origin lineage
    _, ref = seed(tag)
    origin_db = ROOT / tag / "origin" / "db"
    dolt("remote", "add", "relay", relay, cwd=origin_db)
    if dolt("push", "relay", "main", cwd=origin_db).returncode != 0:
        raise RuntimeError("relay seed failed")
    cs = clones(tag, None, N, remote=relay)          # clones OF THE RELAY
    for i, d in enumerate(cs):
        do_work(d, f"c{i}", tag)

    lockdir = ROOT / tag / "lock"
    lockdir.mkdir(parents=True, exist_ok=True)
    local_attempts, local_s = {}, {}
    bar = threading.Barrier(N)

    def worker(i):
        d = cs[i]
        bar.wait()
        t0 = time.perf_counter()
        n = 0
        # flock makes the LOCAL relay push serial: free, and kernel-released if a
        # holder dies (X4). No network involved at all.
        with clone_write_lock(lockdir, timeout=1800):
            for _ in range(6):
                n += 1
                p = dolt("push", "origin", "main", cwd=d)
                if p.returncode == 0:
                    break
                dolt("pull", "origin", "main", cwd=d)
        local_attempts[i], local_s[i] = n, time.perf_counter() - t0

    t0 = time.perf_counter()
    ts = [threading.Thread(target=worker, args=(i,)) for i in range(N)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    local_wall = time.perf_counter() - t0

    # ONE network push for the whole host
    pusher = ROOT / tag / "pusher"
    pusher.mkdir(parents=True, exist_ok=True)
    sh(["dolt", "clone", relay, "hp"], cwd=pusher, timeout=1800)
    hp = pusher / "hp"
    dolt("config", "--local", "--add", "user.name", "hostpusher", cwd=hp)
    dolt("config", "--local", "--add", "user.email", "hp@local", cwd=hp)
    dolt("remote", "add", "--ref", ref, "gh", REMOTE, cwd=hp)
    t0 = time.perf_counter()
    p = dolt("push", "gh", "main", cwd=hp, timeout=1800)
    net_wall = time.perf_counter() - t0
    got = landed(tag, ref)
    exp = N * N_WORK
    ok = p.returncode == 0 and got == str(exp)
    FACTS["d2"] = {"local_wall": local_wall, "net_wall": net_wall,
                   "attempts": sum(local_attempts.values())}
    base = FACTS.get("d1", {}).get("A", {})
    check(f"D2 HOST RELAY: {N} instances -> local file:// relay (flock) -> ONE network push",
          ok,
          f"local relay pushes  : {sum(local_attempts.values())} attempts for {N} "
          f"instances, {local_wall:.0f}s total  (no network, flock-serialised)\n"
          f"  per instance      : median {statistics.median(local_s.values()):.2f}s\n"
          f"ONE network push    : {net_wall:.0f}s  rc={p.returncode}\n"
          f"TOTAL               : {local_wall + net_wall:.0f}s   rows landed {got}/{exp}\n"
          + (f"vs D1-A free-for-all: {base.get('wall', 0):.0f}s with "
             f"{base.get('attempts', 0)} network attempts\n" if base else "")
          + f"=> network pushes to the artifact branch: {N} -> 1. The branch pointer\n"
            f"   advances ONCE for the whole host. This is O(1) in instances-per-host,\n"
            f"   uses only flock + a file:// remote (both already proven: X1-X5, S1-S3),\n"
            f"   needs NO daemon, and keeps ONE canonical artifact branch.\n"
            f"   Limit: it collapses instances on ONE HOST. Across hosts, N = hosts.")


# ---------------------------------------------------------------- D3


def d3_staging_refs():
    """Cross-host aggregation with no server: each writer publishes to its own
    EPHEMERAL ref in parallel (no contention), then ONE aggregator merges all N and
    does a single push to the artifact branch. The refs are transport and are
    deleted; the artifact branch stays single and canonical."""
    tag = "d3"
    _, ref = seed(tag)
    cs = clones(tag, ref, N)
    stage_refs = []
    for i, d in enumerate(cs):
        do_work(d, f"c{i}", tag)
        sr = f"refs/dolt/{RUN}/stage-{i}"
        REFS.add(sr)
        stage_refs.append(sr)
        dolt("remote", "add", "--ref", sr, "stage", REMOTE, cwd=d)
        dolt("checkout", "-b", f"s_{i}", cwd=d)

    pub_attempts, pub_ok = {}, {}
    bar = threading.Barrier(N)

    def publisher(i):
        bar.wait()
        p = dolt("push", "stage", f"s_{i}", cwd=cs[i], timeout=1800)
        pub_attempts[i] = 1
        pub_ok[i] = p.returncode == 0
        if not pub_ok[i]:
            pub_attempts[i] = 2
            p = dolt("push", "stage", f"s_{i}", cwd=cs[i], timeout=1800)
            pub_ok[i] = p.returncode == 0

    t0 = time.perf_counter()
    ts = [threading.Thread(target=publisher, args=(i,)) for i in range(N)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    publish_wall = time.perf_counter() - t0

    # the aggregator: fetch every staging ref, merge, ONE push to the artifact branch
    agg = ROOT / tag / "agg"
    agg.mkdir(parents=True, exist_ok=True)
    sh(["dolt", "clone", "--ref", ref, REMOTE, "a"], cwd=agg, timeout=1800)
    ad = agg / "a"
    dolt("config", "--local", "--add", "user.name", "aggregator", cwd=ad)
    dolt("config", "--local", "--add", "user.email", "agg@local", cwd=ad)
    t0 = time.perf_counter()
    merged, failed = 0, []
    for i, sr in enumerate(stage_refs):
        dolt("remote", "add", "--ref", sr, f"st{i}", REMOTE, cwd=ad)
        f = dolt("fetch", f"st{i}", cwd=ad, timeout=1800)
        m = dolt("merge", f"remotes/st{i}/s_{i}", "--no-edit", cwd=ad)
        if m.returncode != 0:
            dolt("merge", "--abort", cwd=ad)
            failed.append((i, clean(m.stderr or m.stdout, 60)))
        else:
            merged += 1
    dolt("add", "-A", cwd=ad)
    dolt("commit", "-m", f"aggregate {merged} writers", cwd=ad)
    pa = 0
    for _ in range(4):
        pa += 1
        p = dolt("push", "origin", "main", cwd=ad, timeout=1800)
        if p.returncode == 0:
            break
        dolt("pull", "origin", "main", cwd=ad)
    aggregate_wall = time.perf_counter() - t0
    # tear the transport refs down — they are not storage
    t0 = time.perf_counter()
    for sr in stage_refs:
        sh(["git", "push", REMOTE, f":{sr}"], timeout=180)
        REFS.discard(sr)
    teardown = time.perf_counter() - t0
    got = landed(tag, ref)
    exp = N * N_WORK
    ok = got == str(exp) and merged == N
    FACTS["d3"] = {"publish": publish_wall, "aggregate": aggregate_wall,
                   "total": publish_wall + aggregate_wall}
    base = FACTS.get("d1", {}).get("A", {})
    check(f"D3 STAGING REFS: {N} writers publish in parallel, ONE aggregator push",
          ok,
          f"parallel publish to {N} ephemeral refs : {publish_wall:.0f}s   "
          f"attempts {sum(pub_attempts.values())} (contention-free by construction)\n"
          f"aggregator: {merged}/{N} merged + 1 push : {aggregate_wall:.0f}s"
          f"{'  FAILED MERGES: ' + str(failed[:3]) if failed else ''}\n"
          f"teardown of transport refs            : {teardown:.0f}s\n"
          f"TOTAL                                 : "
          f"{publish_wall + aggregate_wall:.0f}s   rows landed {got}/{exp}\n"
          + (f"vs D1-A free-for-all: {base.get('wall', 0):.0f}s / "
             f"{base.get('attempts', 0)} attempts\n" if base else "")
          + f"=> the artifact branch pointer advances exactly ONCE for {N} writers, with\n"
            f"   no server. Publishing is parallel because each writer owns its own ref.\n"
            f"   The refs are TRANSPORT: created, merged, deleted — the artifact store is\n"
            f"   still one branch. Costs: the aggregator is a role someone must hold, and\n"
            f"   its merge is where conflicts surface (DECISIONS D1 governs that).")


# ---------------------------------------------------------------- D4


def d4_transport():
    """The ~8 s is the constant everything else multiplies. What is it made of?"""
    tag = "d4"
    _, ref = seed(tag)
    d = ROOT / tag / "origin" / "db"
    rows = []
    # https (already configured)
    for i in range(3):
        sql(f"INSERT INTO work VALUES ('d4-https-{i}','x')", cwd=d)
        dolt("add", "-A", cwd=d)
        dolt("commit", "-m", f"h{i}", cwd=d)
        t0 = time.perf_counter()
        p = dolt("push", "origin", "main", cwd=d, timeout=1800)
        rows.append(("https", time.perf_counter() - t0, p.returncode))
    # ssh, if the host has a usable key
    ssh_url = "git@github.com:" + REMOTE.split("github.com/")[1]
    probe = sh(["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new",
                "-T", "git@github.com"], timeout=60)
    ssh_ok = "successfully authenticated" in ((probe.stdout or "") + (probe.stderr or ""))
    if ssh_ok:
        dolt("remote", "add", "--ref", ref, "sshorigin", ssh_url, cwd=d)
        for i in range(3):
            sql(f"INSERT INTO work VALUES ('d4-ssh-{i}','x')", cwd=d)
            dolt("add", "-A", cwd=d)
            dolt("commit", "-m", f"s{i}", cwd=d)
            t0 = time.perf_counter()
            p = dolt("push", "sshorigin", "main", cwd=d, timeout=1800)
            rows.append(("ssh", time.perf_counter() - t0, p.returncode))
    https = [t for k, t, rc in rows if k == "https" and rc == 0]
    ssh = [t for k, t, rc in rows if k == "ssh" and rc == 0]
    ok = bool(https)
    FACTS["d4"] = {"https": https, "ssh": ssh}
    check("D4 TRANSPORT: what is the fixed per-push cost made of?",
          ok,
          f"https pushes : {[f'{t:.1f}s' for t in https]}   median "
          f"{statistics.median(https):.1f}s\n"
          + (f"ssh pushes   : {[f'{t:.1f}s' for t in ssh]}   median "
             f"{statistics.median(ssh):.1f}s\n" if ssh else
             f"ssh          : not usable from this host "
             f"({clean((probe.stderr or probe.stdout), 70)})\n")
          + (f"=> ssh is {statistics.median(https)/max(statistics.median(ssh),0.01):.2f}x "
             f"https on the same push.\n" if ssh else
             "=> could not compare; the https number stands alone.\n")
          + f"   Either way the constant is ~{statistics.median(https):.0f}s and it is\n"
            f"   protocol/round-trip cost, not payload (O3) and not process spawn (the\n"
            f"   embedded driver's DOLT_PUSH measured 7.7 s too). So the only way to\n"
            f"   spend less is to push FEWER times — which is what D2 and D3 do.")


# ---------------------------------------------------------------- D5


def wait_port(port, secs=60):
    import socket
    t0 = time.time()
    while time.time() - t0 < secs:
        with socket.socket() as s:
            s.settimeout(0.4)
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return True
        time.sleep(0.3)
    return False


def d5_peer_pull():
    """The last decentralised option: every writer SERVES ITSELF over remotesapi
    (`dolt sql-server --remotesapi-port`), and the aggregator pulls straight from
    the peers. Writers never touch the shared remote at all — only the aggregator
    does, once.

    Still decentralised (no central authority), but NOT daemon-free: it costs a
    listener per writer and needs peer reachability.
    """
    tag = "d5"
    _, ref = seed(tag)
    cs = clones(tag, ref, N)
    for i, d in enumerate(cs):
        do_work(d, f"c{i}", tag)

    # each writer serves ITSELF. Note the consequence measured in B9/B10: while the
    # server holds the directory, the CLI cannot write it — so in a real deployment
    # a self-serving writer's own agents must go THROUGH its server.
    procs, ports = [], []
    t0 = time.perf_counter()
    for i, d in enumerate(cs):
        port = 4400 + i
        ports.append(port)
        procs.append(subprocess.Popen(
            ["dolt", "sql-server", "--host", "127.0.0.1", "--port", str(5400 + i),
             "--remotesapi-port", str(port)],
            cwd=d, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
    up = [wait_port(p) for p in ports]
    serve_wall = time.perf_counter() - t0

    try:
        agg = ROOT / tag / "agg"
        agg.mkdir(parents=True, exist_ok=True)
        sh(["dolt", "clone", "--ref", ref, REMOTE, "a"], cwd=agg, timeout=1800)
        ad = agg / "a"
        dolt("config", "--local", "--add", "user.name", "aggregator", cwd=ad)
        dolt("config", "--local", "--add", "user.email", "agg@local", cwd=ad)
        # probe the remotesapi URL shape once rather than guessing it N times
        url_form = None
        for cand in (f"http://127.0.0.1:{ports[0]}/c0", f"http://127.0.0.1:{ports[0]}"):
            dolt("remote", "add", "probe", cand, cwd=ad)
            f = dolt("fetch", "probe", cwd=ad, timeout=120)
            dolt("remote", "remove", "probe", cwd=ad)
            if f.returncode == 0:
                url_form = cand.replace(f":{ports[0]}", ":{port}").replace("/c0", "/c{i}")
                break
        if not url_form:
            check("D5 PEER PULL: aggregator pulls directly from per-writer remotesapi",
                  False,
                  f"servers up: {sum(up)}/{N} in {serve_wall:.0f}s\n"
                  f"could NOT fetch from a peer's remotesapi with either URL form\n"
                  f"  tried http://127.0.0.1:PORT/<db> and http://127.0.0.1:PORT\n"
                  f"  last error: {clean(f.stderr or f.stdout, 200)}\n"
                  f"=> peer-to-peer pull is not reachable this way from the CLI here;\n"
                  f"   D3 (staging refs) remains the cross-host aggregation answer.")
            return

        t0 = time.perf_counter()
        merged, failed = 0, []
        for i, port in enumerate(ports):
            u = f"http://127.0.0.1:{port}/c{i}"
            dolt("remote", "add", f"pw{i}", u, cwd=ad)
            f = dolt("fetch", f"pw{i}", cwd=ad, timeout=300)
            if f.returncode != 0:
                failed.append((i, clean(f.stderr or f.stdout, 60)))
                continue
            m = dolt("merge", f"remotes/pw{i}/main", "--no-edit", cwd=ad)
            if m.returncode != 0:
                dolt("merge", "--abort", cwd=ad)
                failed.append((i, "merge:" + clean(m.stderr or m.stdout, 50)))
            else:
                merged += 1
        dolt("add", "-A", cwd=ad)
        dolt("commit", "-m", f"aggregate {merged} peers via remotesapi", cwd=ad)
        pull_wall = time.perf_counter() - t0
        t0 = time.perf_counter()
        pa = 0
        for _ in range(4):
            pa += 1
            p = dolt("push", "origin", "main", cwd=ad, timeout=1800)
            if p.returncode == 0:
                break
            dolt("pull", "origin", "main", cwd=ad)
        push_wall = time.perf_counter() - t0
        got = landed(tag, ref)
        exp = N * N_WORK
        ok = merged == N and got == str(exp)
        d3 = FACTS.get("d3", {})
        FACTS["d5"] = {"serve": serve_wall, "pull": pull_wall, "push": push_wall,
                       "merged": merged}
        check(f"D5 PEER PULL: aggregator pulls directly from {N} per-writer remotesapi servers",
              ok,
              f"writers serving themselves : {sum(up)}/{N} up in {serve_wall:.0f}s "
              f"({N} listeners)\n"
              f"aggregator fetch+merge     : {merged}/{N} in {pull_wall:.0f}s"
              f"{'  FAILURES: ' + str(failed[:3]) if failed else ''}\n"
              f"ONE push to the artifact branch: {push_wall:.0f}s ({pa} attempt(s))\n"
              f"TOTAL (excluding server start) : {pull_wall + push_wall:.0f}s   "
              f"rows landed {got}/{exp}\n"
              + (f"vs D3 staging refs: {d3.get('total', 0):.0f}s\n" if d3 else "")
              + f"=> writers never touch the shared remote — ZERO network pushes from\n"
                f"   writers, one from the aggregator. Same O(1) as D3, and it removes\n"
                f"   the staging refs entirely.\n"
                f"   HONEST COSTS: (1) a listener per writer — decentralised but NOT\n"
                f"   daemon-free, which is the property the spike prized; (2) peers must\n"
                f"   be REACHABLE (fine on a LAN, awkward across NAT — and the factory's\n"
                f"   devs are on separate machines); (3) B9/B10 apply: while a writer's\n"
                f"   server holds its directory the CLI cannot write it, so that writer's\n"
                f"   own agents must go through its server — which is precisely the\n"
                f"   'server per site' shape beads adopts.")
    finally:
        for p in procs:
            p.terminate()
        for p in procs:
            try:
                p.wait(timeout=20)
            except subprocess.TimeoutExpired:
                p.kill()


# ---------------------------------------------------------------- main


def cleanup():
    if os.environ.get("FA_GH_KEEP"):
        print(f"--- keeping {len(REFS)} refs")
        return
    out = []
    for r in sorted(REFS):
        rr = sh(["git", "push", REMOTE, f":{r}"], timeout=180)
        out.append(f"{r.split('/')[-1]}={'ok' if rr.returncode == 0 else rr.returncode}")
    print(f"--- cleanup ({len(out)}): {'; '.join(out)}")


def main():
    print(f"=== DECENTRALISED OPTIONS, N={N} pushers x {N_WORK} rows, ONE artifact branch\n"
          f"    remote={REMOTE}\n    run={RUN}"
          f"{'  ONLY=' + str(sorted(ONLY)) if ONLY else ''}\n", flush=True)
    if ROOT.exists():
        shutil.rmtree(ROOT)
    ROOT.mkdir(parents=True)
    try:
        # candidates first, slow baseline last: S2 already gives a baseline
        # (10 same-branch pushers = 54 attempts / 323 s), so D1 is the
        # retry-POLICY comparison rather than the only reference point.
        for fn in (d4_transport, d2_host_relay, d3_staging_refs, d1_retry_shape,
                   d5_peer_pull):
            if ONLY and fn.__name__.split("_")[0] not in ONLY:
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
    for nm, ok, _ in RESULTS:
        if not ok:
            print(f"  FAILED: {nm}")
    sys.exit(0 if npass == len(RESULTS) else 1)


if __name__ == "__main__":
    main()
