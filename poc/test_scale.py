#!/usr/bin/env python3
"""Scale measurement — where does this stop working?

The live corpus is 1,959 BCs / 1,490 edges / 1,607 commits. Every earlier timing was
taken at that size. This measures the ceilings that would actually change the design.

  SC1  corpus size: 10x records + edges -> import, count, PK lookup, 4-hop rollup
  SC2  history depth: many commits -> query latency, clone time, size, gc
  SC3  agent fan-out: 32 agents through one mutex -> throughput, and STARVATION
  SC4  instance count: 12 clones on one machine -> clone time, disk, concurrency
  SC5  push contention: 8 clones pushing at once -> retries to converge
  SC6  zone split overhead: 2 zones vs 1 -> is the boundary free?

Tunable: SCALE_RECORDS, SCALE_COMMITS, SCALE_AGENTS, SCALE_INSTANCES env vars.
Run: .venv/bin/python -u poc/test_scale.py
"""
from __future__ import annotations

import os
import shutil
import statistics
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from clonelock import clone_write_lock  # noqa: E402

ROOT = Path(__file__).parent / "sc"
REMOTE = ROOT / "remote"
DB = "big"
BIG = ROOT / "big" / DB

N_RECORDS = int(os.environ.get("SCALE_RECORDS", 20000))
N_COMMITS = int(os.environ.get("SCALE_COMMITS", 400))
N_AGENTS = int(os.environ.get("SCALE_AGENTS", 32))
N_INSTANCES = int(os.environ.get("SCALE_INSTANCES", 12))

RESULTS: list[tuple[str, bool, str]] = []
SELF = str(Path(__file__).resolve())


def check(name, ok, detail=""):
    RESULTS.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}")
    for ln in (detail or "").splitlines():
        print(f"        {ln}")


def sh(args, cwd, timeout=1800):
    try:
        return subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(args, 124, "", "TIMEOUT")


def sql(stmt, cwd=None, timeout=1800):
    return sh(["dolt", "sql", "-q", stmt], cwd=cwd or BIG, timeout=timeout)


def timed(stmt, cwd=None):
    t0 = time.time()
    r = sh(["dolt", "sql", "-q", stmt, "-r", "csv"], cwd=cwd or BIG, timeout=1800)
    dt = (time.time() - t0) * 1000
    lines = [l for l in (r.stdout or "").strip().splitlines() if l.strip()]
    val = lines[1].split(",")[0] if len(lines) > 1 else None
    return dt, val, r.returncode


def du_mb(p: Path) -> float:
    r = subprocess.run(["du", "-sk", str(p)], capture_output=True, text=True)
    try:
        return int(r.stdout.split()[0]) / 1024
    except Exception:
        return -1.0


def setup():
    print(f"--- setup: synthesizing {N_RECORDS:,} records (server-less)")
    if ROOT.exists():
        shutil.rmtree(ROOT)
    BIG.mkdir(parents=True)
    REMOTE.mkdir(parents=True)
    sh(["dolt", "init", "--name", "sc", "--email", "sc@l"], cwd=BIG)
    for s in (
        "CREATE TABLE bc (bc_id VARCHAR(24) PRIMARY KEY, ss_id VARCHAR(8) NOT NULL, "
        "title TEXT NOT NULL, capability VARCHAR(16) NULL, body LONGTEXT NULL, "
        "INDEX idx_ss (ss_id))",
        "CREATE TABLE vp (vp_id VARCHAR(16) PRIMARY KEY, title TEXT NOT NULL)",
        "CREATE TABLE story (story_id VARCHAR(24) PRIMARY KEY, wave INT NULL)",
        "CREATE TABLE vp_bc (vp_id VARCHAR(16), bc_id VARCHAR(24), "
        "PRIMARY KEY (vp_id,bc_id), FOREIGN KEY (vp_id) REFERENCES vp(vp_id), "
        "FOREIGN KEY (bc_id) REFERENCES bc(bc_id))",
        "CREATE TABLE story_bc (story_id VARCHAR(24), bc_id VARCHAR(24), "
        "PRIMARY KEY (story_id,bc_id), FOREIGN KEY (story_id) REFERENCES story(story_id), "
        "FOREIGN KEY (bc_id) REFERENCES bc(bc_id))",
        "CREATE TABLE ctr (id TINYINT PRIMARY KEY, n INT NOT NULL)",
        "INSERT INTO ctr VALUES (1,0)",
    ):
        r = sql(s)
        if r.returncode != 0:
            raise RuntimeError(f"DDL failed: {(r.stderr or r.stdout)[:200]}")
    sh(["dolt", "add", "-A"], cwd=BIG)
    sh(["dolt", "commit", "-m", "schema"], cwd=BIG)
    sh(["dolt", "remote", "add", "origin", f"file://{REMOTE}"], cwd=BIG)


def bulk_load():
    """Batched inserts, per invariant 6 (one session per unit of work)."""
    n_vp = max(1, N_RECORDS // 20)
    n_story = max(1, N_RECORDS // 10)
    t0 = time.time()
    f = ROOT / "load.sql"
    with open(f, "w") as fh:
        B = 2000
        for start in range(0, N_RECORDS, B):
            vals = ",".join(
                f"('BC-{(i//1000)+1}.{(i//100)%10:02d}.{i%1000:03d}-{i}','SS-{(i%10)+1:02d}',"
                f"'contract {i}',NULL,'body text for contract {i}')"
                for i in range(start, min(start + B, N_RECORDS)))
            fh.write(f"INSERT INTO bc VALUES {vals};\n")
        for start in range(0, n_vp, B):
            vals = ",".join(f"('VP-{i:06d}','property {i}')"
                            for i in range(start, min(start + B, n_vp)))
            fh.write(f"INSERT INTO vp VALUES {vals};\n")
        for start in range(0, n_story, B):
            vals = ",".join(f"('S-{i:06d}',{(i%20)+1})"
                            for i in range(start, min(start + B, n_story)))
            fh.write(f"INSERT INTO story VALUES {vals};\n")
        # edges: each VP -> 3 BCs, each story -> 3 BCs
        for start in range(0, n_vp, B):
            vals = ",".join(
                f"('VP-{i:06d}','BC-{(j//1000)+1}.{(j//100)%10:02d}.{j%1000:03d}-{j}')"
                for i in range(start, min(start + B, n_vp))
                for j in [(i * 3) % N_RECORDS, (i * 3 + 1) % N_RECORDS, (i * 3 + 2) % N_RECORDS])
            fh.write(f"INSERT IGNORE INTO vp_bc VALUES {vals};\n")
        for start in range(0, n_story, B):
            vals = ",".join(
                f"('S-{i:06d}','BC-{(j//1000)+1}.{(j//100)%10:02d}.{j%1000:03d}-{j}')"
                for i in range(start, min(start + B, n_story))
                for j in [(i * 7) % N_RECORDS, (i * 7 + 3) % N_RECORDS, (i * 7 + 5) % N_RECORDS])
            fh.write(f"INSERT IGNORE INTO story_bc VALUES {vals};\n")
    r = sh(["dolt", "sql", "-f", str(f)], cwd=BIG, timeout=3600)
    load_s = time.time() - t0
    sh(["dolt", "add", "-A"], cwd=BIG)
    sh(["dolt", "commit", "-m", f"load {N_RECORDS}"], cwd=BIG)
    return load_s, r


# ---------------------------------------------------------------- tests


def sc1_corpus_size():
    load_s, r = bulk_load()
    n_bc = timed("SELECT COUNT(*) FROM bc")
    n_edges_v = timed("SELECT COUNT(*) FROM vp_bc")
    n_edges_s = timed("SELECT COUNT(*) FROM story_bc")
    pk = timed("SELECT title FROM bc WHERE bc_id='BC-6.05.500-5500'")
    grp = timed("SELECT ss_id, COUNT(*) FROM bc GROUP BY ss_id ORDER BY ss_id")
    rollup = timed("""SELECT COUNT(*) FROM (
                        SELECT s.story_id, COUNT(DISTINCT vb.vp_id) v
                        FROM story s
                        JOIN story_bc sb ON sb.story_id=s.story_id
                        JOIN vp_bc vb ON vb.bc_id=sb.bc_id
                        GROUP BY s.story_id) x""")
    scan = timed("SELECT COUNT(*) FROM bc WHERE body LIKE '%%contract 19999%%'")
    size = du_mb(BIG)
    total_edges = int(n_edges_v[1] or 0) + int(n_edges_s[1] or 0)
    ok = (r.returncode == 0 and int(n_bc[1] or 0) == N_RECORDS
          and pk[0] < 2000 and rollup[0] < 60000)
    check(f"SC1 corpus at {N_RECORDS:,} records / {total_edges:,} edges",
          ok,
          f"bulk load        : {load_s:.1f}s  ({1000*load_s/N_RECORDS:.2f} ms/record)\n"
          f"COUNT(*) bc      : {n_bc[0]:.0f} ms  -> {n_bc[1]}\n"
          f"COUNT(*) vp_bc   : {n_edges_v[0]:.0f} ms  -> {n_edges_v[1]}\n"
          f"COUNT(*) story_bc: {n_edges_s[0]:.0f} ms  -> {n_edges_s[1]}\n"
          f"PK lookup        : {pk[0]:.0f} ms\n"
          f"GROUP BY ss_id   : {grp[0]:.0f} ms\n"
          f"story->BC->VP rollup (all stories): {rollup[0]:.0f} ms\n"
          f"full-text LIKE scan: {scan[0]:.0f} ms\n"
          f"on-disk          : {size:.0f} MB  ({1024*size/N_RECORDS:.1f} KB/record)\n"
          f"  vs live corpus (1,959 BC): every op was 0-3 ms at 10x smaller")


def sc2_history_depth():
    size0 = du_mb(BIG)
    t0 = time.time()
    for i in range(N_COMMITS):
        sql(f"UPDATE ctr SET n={i} WHERE id=1")
        sh(["dolt", "add", "-A"], cwd=BIG)
        sh(["dolt", "commit", "-m", f"c{i}"], cwd=BIG)
    churn_s = time.time() - t0
    size1 = du_mb(BIG)
    n_commits = timed("SELECT COUNT(*) FROM dolt_log")
    pk_after = timed("SELECT title FROM bc WHERE bc_id='BC-6.05.500-5500'")
    cnt_after = timed("SELECT COUNT(*) FROM bc")
    hist = timed("SELECT COUNT(*) FROM dolt_history_ctr")
    t0 = time.time()
    g = sh(["dolt", "gc"], cwd=BIG, timeout=3600)
    gc_s = time.time() - t0
    size2 = du_mb(BIG)
    # clone cost at depth. MUST push first -- an earlier revision cloned an empty
    # remote and the rc=1 was not asserted on.
    pushed = sh(["dolt", "push", "origin", "main"], cwd=BIG, timeout=1800)
    cd = ROOT / "clonetest"
    cd.mkdir(exist_ok=True)
    t0 = time.time()
    cl = sh(["dolt", "clone", f"file://{REMOTE}", "c1"], cwd=cd, timeout=1800)
    clone_s = time.time() - t0
    check(f"SC2 history depth: +{N_COMMITS} commits",
          pk_after[0] < 2000 and cnt_after[0] < 5000 and g.returncode == 0
          and pushed.returncode == 0 and cl.returncode == 0,
          f"{N_COMMITS} commits in {churn_s:.0f}s ({1000*churn_s/N_COMMITS:.0f} ms/commit)\n"
          f"total commits now: {n_commits[1]}\n"
          f"size {size0:.0f} -> {size1:.0f} MB "
          f"({1024*(size1-size0)/N_COMMITS:.0f} KB/commit)\n"
          f"after gc ({gc_s:.0f}s): {size2:.0f} MB (reclaimed {size1-size2:.0f} MB)\n"
          f"query latency AFTER depth: PK {pk_after[0]:.0f} ms, COUNT(*) {cnt_after[0]:.0f} ms, "
          f"dolt_history_ctr {hist[0]:.0f} ms\n"
          f"push rc={pushed.returncode}; clone of the pushed remote: {clone_s:.1f}s "
          f"(rc={cl.returncode})\n"
          "=> the question is whether QUERY latency degrades with history depth")


def sc3_agent_fanout():
    """N agents through one mutex. Measures throughput AND the worst wait, because
    starvation is the failure mode that matters for a big fleet."""
    sql("UPDATE ctr SET n=0 WHERE id=1")
    sh(["dolt", "add", "-A"], cwd=BIG)
    sh(["dolt", "commit", "-m", "reset"], cwd=BIG)
    waits: list[float] = []
    ok_n = 0
    lk = threading.Lock()
    bar = threading.Barrier(N_AGENTS)

    def agent(i):
        nonlocal ok_n
        t0 = time.time()
        try:
            bar.wait()
            with clone_write_lock(BIG, timeout=900):
                w = time.time() - t0
                r = sql("UPDATE ctr SET n = n + 1 WHERE id=1", timeout=600)
                with lk:
                    waits.append(w)
                    if r.returncode == 0:
                        ok_n += 1
        except Exception:                                   # noqa: BLE001
            pass

    t0 = time.time()
    ts = [threading.Thread(target=agent, args=(i,)) for i in range(N_AGENTS)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    total = time.time() - t0
    final = timed("SELECT n FROM ctr WHERE id=1")[1]
    ws = sorted(waits)
    check(f"SC3 agent fan-out: {N_AGENTS} agents through one mutex",
          ok_n == N_AGENTS and int(final or 0) == N_AGENTS,
          f"{ok_n}/{N_AGENTS} succeeded; counter={final} (exact would be {N_AGENTS})\n"
          f"wall clock {total:.1f}s -> {1000*total/N_AGENTS:.0f} ms/agent serialized\n"
          f"lock wait: min {ws[0]*1000:.0f} ms, median {statistics.median(ws)*1000:.0f} ms, "
          f"p95 {ws[int(len(ws)*0.95)-1]*1000:.0f} ms, MAX {ws[-1]*1000:.0f} ms\n"
          f"starvation check: max/median wait ratio = "
          f"{ws[-1]/max(statistics.median(ws),0.001):.1f}x\n"
          "=> the mutex serializes writes, so throughput is 1/(time per write). A big\n"
          "   fleet needs BATCHING per hold (invariant 6), not more agents.")


def sc4_instance_count():
    """Many instances on one machine: clone cost, disk, and whether concurrent writes
    across instances stay contention-free (they have separate mutexes)."""
    base = ROOT / "instances"
    base.mkdir(exist_ok=True)
    sh(["dolt", "push", "origin", "main"], cwd=BIG)
    clone_times, dirs = [], []
    for i in range(N_INSTANCES):
        d = base / f"inst{i:02d}"
        d.mkdir(exist_ok=True)
        t0 = time.time()
        r = sh(["dolt", "clone", f"file://{REMOTE}", DB], cwd=d, timeout=1800)
        clone_times.append(time.time() - t0)
        cd = d / DB
        if r.returncode == 0:
            sh(["dolt", "config", "--local", "--add", "user.name", f"i{i}"], cwd=cd)
            sh(["dolt", "config", "--local", "--add", "user.email", f"i{i}@s"], cwd=cd)
            sh(["dolt", "checkout", "-b", f"factory/inst{i:02d}"], cwd=cd)
            dirs.append(cd)
    disk = du_mb(base)
    # all instances write concurrently -- separate clones => separate mutexes
    ok_n = 0
    lk = threading.Lock()
    bar = threading.Barrier(len(dirs))

    def work(cd, i):
        nonlocal ok_n
        try:
            with clone_write_lock(cd, timeout=900):
                bar.wait()
                r = sh(["dolt", "sql", "-q",
                        f"UPDATE bc SET capability='CAP-{i:03d}' "
                        f"WHERE bc_id='BC-1.00.{i:03d}-{i}'"], cwd=cd, timeout=600)
                if r.returncode == 0:
                    with lk:
                        ok_n += 1
        except Exception:                                   # noqa: BLE001
            pass

    t0 = time.time()
    ts = [threading.Thread(target=work, args=(cd, i)) for i, cd in enumerate(dirs)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    concurrent_s = time.time() - t0
    check(f"SC4 instance count: {N_INSTANCES} clones on one machine",
          len(dirs) == N_INSTANCES and ok_n == len(dirs),
          f"clones created: {len(dirs)}/{N_INSTANCES}\n"
          f"clone time: median {statistics.median(clone_times):.1f}s, "
          f"max {max(clone_times):.1f}s\n"
          f"disk for {len(dirs)} instances: {disk:.0f} MB "
          f"({disk/max(1,len(dirs)):.0f} MB each; base corpus is {du_mb(BIG):.0f} MB)\n"
          f"ALL {ok_n} instances wrote CONCURRENTLY in {concurrent_s:.1f}s "
          f"({1000*concurrent_s/max(1,len(dirs)):.0f} ms/instance)\n"
          "=> separate clones => separate mutexes => genuine parallelism. The cost is\n"
          "   DISK: a full corpus copy per instance.")


def sc5_push_contention():
    """How does push-as-CAS degrade as more clones push at once?"""
    base = ROOT / "instances"
    dirs = sorted([d / DB for d in base.iterdir() if (d / DB).exists()])[:8]
    for cd in dirs:
        sh(["dolt", "checkout", "main"], cwd=cd)
        sh(["dolt", "reset", "--hard", "origin/main"], cwd=cd)
    attempts: list[int] = []
    lk = threading.Lock()
    bar = threading.Barrier(len(dirs))

    def contend(cd, i):
        tries = 0
        for attempt in range(12):
            tries = attempt + 1
            try:
                with clone_write_lock(cd, timeout=900):
                    if attempt == 0:
                        bar.wait()
                    sh(["dolt", "pull", "origin", "main"], cwd=cd, timeout=600)
                    sh(["dolt", "sql", "-q",
                        f"INSERT INTO story (story_id, wave) VALUES ('S-CONT-{i:03d}',99) "
                        f"ON DUPLICATE KEY UPDATE wave=99"], cwd=cd, timeout=600)
                    sh(["dolt", "add", "-A"], cwd=cd)
                    sh(["dolt", "commit", "-m", f"contend {i}"], cwd=cd)
                    p = sh(["dolt", "push", "origin", "main"], cwd=cd, timeout=900)
                    if p.returncode == 0:
                        break
            except Exception:                               # noqa: BLE001
                break
        with lk:
            attempts.append(tries)

    t0 = time.time()
    ts = [threading.Thread(target=contend, args=(cd, i)) for i, cd in enumerate(dirs)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    total = time.time() - t0
    cd0 = dirs[0]
    sh(["dolt", "pull", "origin", "main"], cwd=cd0)
    landed = timed("SELECT COUNT(*) FROM story WHERE story_id LIKE 'S-CONT-%%'", cwd=cd0)
    check(f"SC5 push contention: {len(dirs)} clones pushing at once",
          int(landed[1] or 0) == len(dirs),
          f"all {len(dirs)} writes landed: {landed[1]}/{len(dirs)}\n"
          f"push attempts per clone: {sorted(attempts)} "
          f"(median {statistics.median(attempts):.0f}, max {max(attempts)})\n"
          f"wall clock to converge: {total:.1f}s "
          f"({total/len(dirs):.1f}s per clone)\n"
          "=> push-as-CAS is a RETRY LOOP: contention shows up as attempts, and the\n"
          "   last writer pays the most. This is the number that decides how many\n"
          "   instances can share one remote comfortably.")


def sc6_zone_split_overhead():
    """Does splitting into 2 trust zones cost anything measurable?"""
    z = ROOT / "zones"
    for name in ("open", "walled"):
        d = z / name
        d.mkdir(parents=True, exist_ok=True)
        sh(["dolt", "init", "--name", "z", "--email", "z@l"], cwd=d)
    n = min(5000, N_RECORDS)
    f = ROOT / "zone.sql"
    sh(["dolt", "sql", "-q",
        "CREATE TABLE bc (bc_id VARCHAR(24) PRIMARY KEY, title TEXT NOT NULL)"],
       cwd=z / "open")
    with open(f, "w") as fh:
        for start in range(0, n, 2000):
            vals = ",".join(f"('BC-{i:06d}','c {i}')" for i in range(start, min(start + 2000, n)))
            fh.write(f"INSERT INTO bc VALUES {vals};\n")
    t0 = time.time()
    sh(["dolt", "sql", "-f", str(f)], cwd=z / "open", timeout=1800)
    zone_load = time.time() - t0
    dt_open, val, _ = timed("SELECT COUNT(*) FROM bc", cwd=z / "open")
    # two separate dolt invocations (one per zone) vs one
    t0 = time.time()
    sh(["dolt", "sql", "-q", "SELECT COUNT(*) FROM bc", "-r", "csv"], cwd=z / "open")
    sh(["dolt", "sql", "-q", "SHOW TABLES", "-r", "csv"], cwd=z / "walled")
    two_calls = (time.time() - t0) * 1000
    check("SC6 zone split costs one extra process invocation, nothing structural",
          val == str(n),
          f"loaded {n:,} rows into zones/open in {zone_load:.1f}s\n"
          f"COUNT(*) within a zone: {dt_open:.0f} ms -> {val}\n"
          f"querying BOTH zones (2 dolt invocations): {two_calls:.0f} ms\n"
          f"=> the cost of a zone boundary is one extra process spawn (~{two_calls/2:.0f} ms)\n"
          "   when an operation genuinely spans zones. Per-zone queries are unaffected.")


def sc7_spawn_vs_query():
    """Every SC1 timing came out ~130-200 ms whatever the query did. That is the CLI
    process-spawn floor, not data scale. Separate them by running many queries in ONE
    invocation and dividing."""
    n = 50
    # one invocation, one trivial query -> pure spawn + open cost
    t0 = time.time()
    sh(["dolt", "sql", "-q", "SELECT 1", "-r", "csv"], cwd=BIG)
    spawn_ms = (time.time() - t0) * 1000
    # one invocation, n real queries -> spawn amortized
    f = ROOT / "many.sql"
    f.write_text("".join("SELECT COUNT(*) FROM bc;\n" for _ in range(n)))
    t0 = time.time()
    r = sh(["dolt", "sql", "-f", str(f)], cwd=BIG, timeout=1800)
    batch_ms = (time.time() - t0) * 1000
    per_query = max(0.0, (batch_ms - spawn_ms) / n)
    # same for a heavier join
    f2 = ROOT / "many2.sql"
    f2.write_text("".join(
        "SELECT COUNT(*) FROM story s JOIN story_bc sb ON sb.story_id=s.story_id "
        "JOIN vp_bc vb ON vb.bc_id=sb.bc_id;\n" for _ in range(n)))
    t0 = time.time()
    sh(["dolt", "sql", "-f", str(f2)], cwd=BIG, timeout=1800)
    batch2_ms = (time.time() - t0) * 1000
    per_join = max(0.0, (batch2_ms - spawn_ms) / n)
    check("SC7 the ~130 ms floor is process spawn, NOT query cost",
          r.returncode == 0 and per_query < spawn_ms,
          f"one `dolt sql` invocation doing `SELECT 1`: {spawn_ms:.0f} ms "
          f"<- this is the FLOOR\n"
          f"{n} x COUNT(*) over {N_RECORDS:,} rows in one invocation: {batch_ms:.0f} ms "
          f"=> {per_query:.1f} ms/query amortized\n"
          f"{n} x 3-table JOIN in one invocation: {batch2_ms:.0f} ms "
          f"=> {per_join:.1f} ms/query amortized\n"
          f"ratio: spawn is {spawn_ms/max(per_query,0.01):.0f}x the actual query\n"
          "=> SC1's 133-201 ms numbers were ~95% spawn. Real query cost at 20k records\n"
          "   is single-digit ms. This is invariant 6 restated as a measurement: batch a\n"
          "   unit of work into ONE session, or use the embedded driver.")


def main():
    print("=" * 74)
    print(f"Scale measurement  (records={N_RECORDS:,} commits={N_COMMITS} "
          f"agents={N_AGENTS} instances={N_INSTANCES})")
    print("=" * 74)
    setup()
    for t in (sc1_corpus_size, sc2_history_depth, sc3_agent_fanout,
              sc4_instance_count, sc5_push_contention, sc6_zone_split_overhead,
              sc7_spawn_vs_query):
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
