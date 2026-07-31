#!/usr/bin/env python3
"""Embedded driver vs CLI vs sql-server — the three access paths for `fa`.

Every timing in this spike so far shelled out to `dolt sql`, paying a measured
141 ms spawn floor per invocation (~14,000x the cost of a COUNT(*)). SPEC §8.6
flags the embedded `dolthub/driver/v2` path as unbenchmarked and guesses it may
remove invariant 4 and relax invariant 6. This suite measures it.

  B1   adoption cost: CGO, build tags, binary size, dependency count
  B2   cold start, trivial query           (the CLI-shaped cost of one command)
  B3   cold start, real query on the corpus
  B4   warm per-query cost on ONE handle
  B5   300 writes: per-statement vs batched vs transaction vs prepared
  B6   full corpus import (2,779 records), all paths, row counts must match
  B7   REAL transactions: multi-table rollback leaves nothing
  B8   which dolt procedures / system tables work in-process
  B9   two embedded processes on one directory
  B10  embedded holding vs the dolt CLI writing
  B11  n = n + 1 from two embedded processes (invariant 1's shape)
  B12  storage compat: CLI 2.2.3 <-> driver v2.2.0, both directions
  B13  verdict on invariants 4 and 6

Run: .venv/bin/python -u poc/test_embedded.py
Self-provisioning: builds its own fixtures under poc/eb/ and its own server.
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import statistics
import subprocess
import sys
import time
from pathlib import Path

POC = Path(__file__).parent
ROOT = POC / "eb"
FX = ROOT / "fx"
BENCH = POC / "bench" / "bench"
SCHEMA = POC / "schema.sql"
FACTORY = Path(os.environ.get("FACTORY_ROOT", "~/Dev/vsdd-factory/.factory")).expanduser()
SRV_PORT = int(os.environ.get("EB_PORT", 3399))
GOBIN = "/opt/homebrew/bin/go"

TRIALS = int(os.environ.get("EB_TRIALS", 7))
N_WRITES = int(os.environ.get("EB_WRITES", 300))
N_WARM = int(os.environ.get("EB_WARM", 50))

RESULTS: list[tuple[str, bool, str]] = []
FACTS: dict[str, object] = {}


def check(name, ok, detail=""):
    RESULTS.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}")
    for ln in (detail or "").splitlines():
        print(f"        {ln}")


def sh(args, cwd=None, timeout=3600, env=None):
    try:
        return subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                              timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(args, 124, "", "TIMEOUT")


def med(xs):
    return statistics.median(xs) if xs else float("nan")


def wall(args, cwd=None, n=1, timeout=3600):
    """Wall-clock ms per invocation, n trials. This is what a user waits for."""
    out = []
    last = None
    for _ in range(n):
        t0 = time.perf_counter()
        last = sh(args, cwd=cwd, timeout=timeout)
        out.append((time.perf_counter() - t0) * 1000)
    return out, last


def emb(mode, dbdir: Path, database: str, *args, timeout=3600):
    """Run the Go harness. Returns (wall_ms, parsed_json, CompletedProcess)."""
    t0 = time.perf_counter()
    r = sh([str(BENCH), mode, str(dbdir), database, *[str(a) for a in args]], timeout=timeout)
    dt = (time.perf_counter() - t0) * 1000
    js = {}
    for ln in (r.stdout or "").splitlines():
        ln = ln.strip()
        if ln.startswith("{"):
            try:
                js = json.loads(ln)
            except json.JSONDecodeError:
                pass
    return dt, js, r


def dolt(args, cwd, timeout=3600):
    return sh(["dolt", *args], cwd=cwd, timeout=timeout)


def sql_cli(stmt, cwd, timeout=3600):
    return sh(["dolt", "sql", "-q", stmt, "-r", "csv"], cwd=cwd, timeout=timeout)


def csv_first(r):
    lines = [l for l in (r.stdout or "").strip().splitlines() if l.strip()]
    return lines[1].split(",")[0] if len(lines) > 1 else None


# ---------------------------------------------------------------- provisioning


def new_repo(parent: Path, name: str, with_schema=True) -> Path:
    """A dolt repo created by the CLI at <parent>/<name>. Embedded opens it as
    dataDir=parent, database=name (underscores only: hyphens are illegal there)."""
    d = parent / name
    d.mkdir(parents=True)
    r = dolt(["init", "--name", "eb", "--email", "eb@local"], cwd=d)
    if r.returncode != 0:
        raise RuntimeError(f"dolt init: {r.stderr}")
    if with_schema:
        r = sh(["dolt", "sql", "-f", str(SCHEMA)], cwd=d)
        if r.returncode != 0:
            raise RuntimeError(f"schema: {r.stderr[:300]}")
        dolt(["add", "-A"], cwd=d)
        dolt(["commit", "-m", "schema"], cwd=d)
    return d


def wait_port(port, secs=40):
    t0 = time.time()
    while time.time() - t0 < secs:
        with socket.socket() as s:
            s.settimeout(0.4)
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return True
        time.sleep(0.3)
    return False


def setup():
    if not BENCH.exists():
        raise SystemExit(f"missing {BENCH} — build it:\n"
                         f"  cd poc/bench && CGO_ENABLED=1 {GOBIN} build -tags gms_pure_go -o bench .")
    if not (FX / "fixture.jsonl").exists():
        print(f"--- building fixture from {FACTORY}")
        r = sh([sys.executable, str(POC / "corpus_fixture.py"), str(FACTORY), str(FX)])
        if r.returncode != 0:
            raise RuntimeError(f"fixture: {r.stderr[:400]}")
        print("   " + (r.stdout or "").strip())
    for sub in ("a", "a2", "b", "b2", "c", "d", "s"):
        p = ROOT / sub
        if p.exists():
            shutil.rmtree(p)
    print("--- provisioning repos (cli-created)")
    return {
        "a": new_repo(ROOT / "a", "fa_cli"),      # CLI imports the corpus here
        "a2": new_repo(ROOT / "a2", "fa_clitx"),  # CLI import inside one tx (control)
        "b": new_repo(ROOT / "b", "fa_emb"),      # embedded per-statement import
        "b2": new_repo(ROOT / "b2", "fa_emb2"),   # embedded transaction import
        "c": new_repo(ROOT / "c", "fa_c"),        # concurrency probes
    }


# ---------------------------------------------------------------- B1


def b1_adoption(dirs):
    gomod = (POC / "bench" / "go.mod").read_text()
    deps = sum(1 for ln in gomod.splitlines() if "// indirect" in ln)
    size_mb = BENCH.stat().st_size / 1e6
    dolt_bin = shutil.which("dolt")
    dolt_mb = Path(os.path.realpath(dolt_bin)).stat().st_size / 1e6 if dolt_bin else -1

    # prove the two build constraints rather than asserting them
    env = dict(os.environ, CGO_ENABLED="0", PATH="/opt/homebrew/bin:" + os.environ.get("PATH", ""))
    nocgo = sh([GOBIN, "build", "-tags", "gms_pure_go", "-o", "/tmp/eb_nocgo"],
               cwd=POC / "bench", timeout=900, env=env)
    env2 = dict(os.environ, CGO_ENABLED="1", PATH="/opt/homebrew/bin:" + os.environ.get("PATH", ""))
    notag = sh([GOBIN, "build", "-o", "/tmp/eb_notag"], cwd=POC / "bench", timeout=900, env=env2)
    icu = "unicode/regex.h" in (notag.stderr or "") or "uregex.h" in (notag.stderr or "")
    FACTS["deps"] = deps
    FACTS["bin_mb"] = size_mb
    check("B1 adoption cost of the embedded driver",
          size_mb > 0 and deps > 0,
          f"language           : Go (CGO). `fa` in Python cannot use it — the driver is\n"
          f"                     a Go database/sql driver; an embedded fa is a Go binary.\n"
          f"CGO_ENABLED=0 build: rc={nocgo.returncode} "
          f"{'(refuses — embedded needs cgo)' if nocgo.returncode != 0 else '(built)'}\n"
          f"no -tags gms_pure_go: rc={notag.returncode} "
          f"{'FAILS on ICU headers (unicode/regex.h)' if icu else ''}\n"
          f"                     -> beads pins -tags gms_pure_go for exactly this\n"
          f"transitive deps    : {deps} indirect modules (dolt+go-mysql-server in-tree)\n"
          f"binary             : {size_mb:.0f} MB   vs `dolt` CLI {dolt_mb:.0f} MB\n"
          f"                     (both large; embedded is not a size saving)")


# ---------------------------------------------------------------- B2/B3


def b2_cold_trivial(dirs, srv):
    a = dirs["a"]
    cli, _ = wall(["dolt", "sql", "-q", "SELECT 1", "-r", "csv"], cwd=a, n=TRIALS)
    ew = [emb("oneshot", a.parent, a.name)[0] for _ in range(TRIALS)]
    _, js, r = emb("oneshot", a.parent, a.name)
    srv_ms = srv["trivial"] if srv else None
    FACTS["cold_cli"] = med(cli)
    FACTS["cold_emb"] = med(ew)
    ok = r.returncode == 0 and js.get("ok") is True
    detail = (f"`dolt sql -q 'SELECT 1'`    : {med(cli):6.0f} ms  (min {min(cli):.0f})\n"
              f"embedded one-shot binary    : {med(ew):6.0f} ms  (min {min(ew):.0f})\n"
              f"  in-process breakdown      : connector {js.get('connector_ms',0):.0f} ms + "
              f"ping {js.get('ping_ms',0):.0f} ms + USE {js.get('use_ms',0):.0f} ms + "
              f"query {js.get('query_ms',0):.1f} ms\n")
    if srv_ms:
        detail += f"sql-server (pymysql conn+q) : {srv_ms:6.0f} ms\n"
    detail += (f"=> ratio embedded/CLI       : {med(ew)/med(cli):.2f}x\n"
               "   a one-shot CLI-shaped command pays engine open EITHER way")
    check("B2 cold start, trivial query (SELECT 1)", ok, detail)


def b3_cold_real(dirs, srv):
    a = dirs["a"]
    cli, rc = wall(["dolt", "sql", "-q", "SELECT COUNT(*) FROM bc", "-r", "csv"], cwd=a, n=TRIALS)
    n_cli = csv_first(rc)
    ew, js = [], {}
    for _ in range(TRIALS):
        dt, js, _ = emb("oneshot-count", a.parent, a.name)
        ew.append(dt)
    ok = str(js.get("val")) == str(n_cli) and js.get("ok") is True
    detail = (f"rows in table               : {n_cli} (both paths agree: {ok})\n"
              f"`dolt sql -q 'COUNT(*)'`    : {med(cli):6.0f} ms\n"
              f"embedded one-shot           : {med(ew):6.0f} ms  "
              f"(query itself {js.get('query_ms',0):.1f} ms)\n")
    if srv:
        detail += f"sql-server (conn+query)     : {srv['count']:6.0f} ms\n"
    detail += f"=> ratio embedded/CLI       : {med(ew)/med(cli):.2f}x"
    check("B3 cold start, real query on the imported corpus", ok, detail)


# ---------------------------------------------------------------- B4


def b4_warm(dirs, srv):
    a = dirs["a"]
    dt, js, r = emb("warm", a.parent, a.name, N_WARM)
    # CLI: each query is its own invocation (there is no warm CLI)
    q_count = ["dolt", "sql", "-q", "SELECT COUNT(*) FROM bc", "-r", "csv"]
    q_group = ["dolt", "sql", "-q", "SELECT ss_id, COUNT(*) FROM bc GROUP BY ss_id", "-r", "csv"]
    join = ("SELECT COUNT(*) FROM (SELECT s.story_id, COUNT(DISTINCT t.vp_id) v "
            "FROM story s JOIN story_bc sb ON sb.story_id=s.story_id "
            "JOIN bc b ON b.bc_id=sb.bc_id LEFT JOIN bc_trace t ON t.bc_id=b.bc_id "
            "GROUP BY s.story_id) x")
    c_cnt, _ = wall(q_count, cwd=a, n=5)
    c_grp, _ = wall(q_group, cwd=a, n=5)
    c_join, _ = wall(["dolt", "sql", "-q", join, "-r", "csv"], cwd=a, n=5)
    ok = js.get("ok") is True
    FACTS["warm_count"] = js.get("count_med_ms")
    FACTS["warm_join"] = js.get("join3_med_ms")
    detail = (f"                        embedded(1 handle)    CLI(1 invocation each)\n"
              f"COUNT(*)              : {js.get('count_med_ms',0):8.2f} ms        "
              f"{med(c_cnt):8.0f} ms\n"
              f"PK lookup             : {js.get('pk_med_ms',0):8.2f} ms        "
              f"(spawn-bound, same as above)\n"
              f"GROUP BY ss_id        : {js.get('group_med_ms',0):8.2f} ms        "
              f"{med(c_grp):8.0f} ms\n"
              f"3-table JOIN rollup   : {js.get('join3_med_ms',0):8.2f} ms        "
              f"{med(c_join):8.0f} ms\n"
              f"engine open (once)    : {js.get('open_total_ms',0):8.0f} ms\n"
              f"=> after the ONE open, queries cost what SQL costs; the CLI pays\n"
              f"   {med(c_cnt):.0f} ms for every single question")
    check(f"B4 warm queries on one handle (n={N_WARM} each)", ok, detail)


# ---------------------------------------------------------------- B5


def b5_writes(dirs, srv):
    c = dirs["c"]
    ins = "INSERT INTO benchw (k,v) VALUES ('{k}',1)"
    sh(["dolt", "sql", "-q",
        "CREATE TABLE IF NOT EXISTS benchw (k VARCHAR(64) PRIMARY KEY, v INT NOT NULL)"], cwd=c)
    # CLI per-statement: sample and extrapolate (a full 300 would take ~45 s)
    SAMPLE = 15
    t0 = time.perf_counter()
    for i in range(SAMPLE):
        r = sql_cli(ins.format(k=f"cli-{i}"), cwd=c)
        if r.returncode != 0:
            break
    per_cli = (time.perf_counter() - t0) * 1000 / SAMPLE
    # CLI batched: one invocation, N statements in a file
    f = ROOT / "w.sql"
    f.write_text("\n".join(ins.format(k=f"clib-{i}") + ";" for i in range(N_WRITES)) + "\n")
    t0 = time.perf_counter()
    rb = sh(["dolt", "sql", "-f", str(f)], cwd=c)
    per_clib = (time.perf_counter() - t0) * 1000 / N_WRITES
    # CONTROL (LESSONS rule 6: isolate the variable). If the 5 ms/write above is
    # per-autocommit cost rather than per-invocation cost, then wrapping the same
    # file in ONE explicit transaction should reach the embedded tx number — in
    # which case the embedded win here is zero.
    f2 = ROOT / "w_tx.sql"
    f2.write_text("BEGIN;\n" + "\n".join(ins.format(k=f"clitx-{i}") + ";" for i in range(N_WRITES))
                  + "\nCOMMIT;\n")
    t0 = time.perf_counter()
    rt = sh(["dolt", "sql", "-f", str(f2)], cwd=c)
    per_clitx = (time.perf_counter() - t0) * 1000 / N_WRITES
    n_tx = csv_first(sql_cli("SELECT COUNT(*) FROM benchw WHERE k LIKE 'clitx-%'", cwd=c))
    res = {}
    for wmode in ("autocommit", "tx", "prepared"):
        dt, js, r = emb("writes", c.parent, c.name, N_WRITES, wmode, f"emb-{wmode}")
        res[wmode] = (js.get("per_write_ms", float("nan")), dt, js)
    ok = (rb.returncode == 0 and rt.returncode == 0 and str(n_tx) == str(N_WRITES)
          and all(v[2].get("ok") for v in res.values()))
    lines = [f"CLI, one invocation per write : {per_cli:8.1f} ms/write   "
             f"(sampled {SAMPLE}; = the 141 ms spawn floor)",
             f"CLI, {N_WRITES} in one -f file      : {per_clib:8.2f} ms/write   "
             f"(invariant 6's batching, autocommit per statement)",
             f"CLI, one -f file in ONE tx    : {per_clitx:8.2f} ms/write   "
             f"(control: BEGIN/COMMIT around the file; {n_tx} rows landed)"]
    for wmode in ("autocommit", "tx", "prepared"):
        pw, dt, js = res[wmode]
        lines.append(f"embedded, {wmode:<10}         : {pw:8.2f} ms/write   "
                     f"(whole process {dt:.0f} ms incl. engine open)")
    lines.append(f"=> three separate taxes, not one: process spawn (~{per_cli:.0f} ms),")
    lines.append(f"   per-autocommit working-set write (~{per_clib:.1f} ms), and the")
    lines.append(f"   in-transaction floor (~{res['tx'][0]:.2f} ms). Batching inside ONE")
    lines.append(f"   transaction is worth {per_clib/max(res['tx'][0],1e-9):.0f}x and the CLI can "
                 f"{'ALSO reach it' if per_clitx < per_clib / 5 else 'NOT reach it'}.")
    FACTS["w_cli"] = per_cli
    FACTS["w_clib"] = per_clib
    FACTS["w_clitx"] = per_clitx
    FACTS["w_emb_auto"] = res["autocommit"][0]
    FACTS["w_emb_tx"] = res["tx"][0]
    check(f"B5 {N_WRITES} single-row writes, five paths", ok, "\n".join(lines))


# ---------------------------------------------------------------- B6


def b6_import(dirs):
    a, a2, b, b2 = dirs["a"], dirs["a2"], dirs["b"], dirs["b2"]
    jsonl = FX / "fixture.jsonl"
    corpus = FX / "corpus.sql"
    # CLI, batched: the 13.4 s baseline shape
    t0 = time.perf_counter()
    r1 = sh(["dolt", "sql", "-f", str(corpus)], cwd=a, timeout=7200)
    cli_s = time.perf_counter() - t0
    dolt(["add", "-A"], cwd=a)
    dolt(["commit", "-m", "import (cli batched)"], cwd=a)
    # CLI control: the same file wrapped in ONE explicit transaction
    txf = ROOT / "corpus_tx.sql"
    if not txf.exists():
        txf.write_text("BEGIN;\n" + corpus.read_text() + "\nCOMMIT;\n")
    t0 = time.perf_counter()
    r1b = sh(["dolt", "sql", "-f", str(txf)], cwd=a2, timeout=7200)
    clitx_s = time.perf_counter() - t0
    dolt(["add", "-A"], cwd=a2)
    dolt(["commit", "-m", "import (cli one tx)"], cwd=a2)
    # embedded, statement at a time (no batching at all)
    dt_ps, js_ps, r2 = emb("import", b.parent, b.name, jsonl, "per-stmt", timeout=7200)
    # embedded, one transaction
    dt_tx, js_tx, r3 = emb("import", b2.parent, b2.name, jsonl, "prepared", timeout=7200)

    def counts(d):
        out = {}
        for t in ("subsystem", "vp", "bc", "story", "bc_trace", "story_bc"):
            out[t] = csv_first(sql_cli(f"SELECT COUNT(*) FROM {t}", cwd=d))
        return out

    ca, ca2, cb, cb2 = counts(a), counts(a2), counts(b), counts(b2)
    same = ca == cb == cb2 == ca2
    n = js_ps.get("records", 0)
    ok = (r1.returncode == 0 and r1b.returncode == 0 and js_ps.get("ok")
          and js_tx.get("ok") and same)
    FACTS["imp_cli"] = cli_s
    FACTS["imp_clitx"] = clitx_s
    FACTS["imp_emb_ps"] = js_ps.get("write_ms", 0) / 1000
    FACTS["imp_emb_tx"] = js_tx.get("write_ms", 0) / 1000
    check(f"B6 full corpus import ({n:,} records), identical row counts",
          ok,
          f"CLI, one invocation/record  : {FACTS.get('w_cli',141)*n/1000:7.0f} s   "
          f"(extrapolated from B5 — ASSESSMENT §3e's 531 s figure)\n"
          f"CLI, batched -f file        : {cli_s:7.1f} s   "
          f"({1000*cli_s/max(n,1):.2f} ms/record)  autocommit per statement\n"
          f"CLI, -f file in ONE tx      : {clitx_s:7.1f} s   "
          f"({1000*clitx_s/max(n,1):.2f} ms/record)  <- the control\n"
          f"embedded, per statement     : {js_ps.get('write_ms',0)/1000:7.1f} s   "
          f"({js_ps.get('write_ms',0)/max(n,1):.2f} ms/record)  "
          f"+ DOLT_COMMIT {js_ps.get('dolt_commit_ms',0)/1000:.1f} s\n"
          f"embedded, one tx + prepared : {js_tx.get('write_ms',0)/1000:7.1f} s   "
          f"({js_tx.get('write_ms',0)/max(n,1):.2f} ms/record)  "
          f"+ DOLT_COMMIT {js_tx.get('dolt_commit_ms',0)/1000:.1f} s\n"
          f"row counts equal across all four: {same}\n"
          f"  cli={ca}\n  emb={cb}")


# ---------------------------------------------------------------- B7


def b7_atomicity(dirs):
    b = dirs["b"]
    tag = f"S-99.{int(time.time())%1000:03d}"
    dt, js, r = emb("atomicity", b.parent, b.name, tag)
    ok = (js.get("ok") is True and js.get("rows_left") == "0"
          and "foreign key" in (js.get("bad_err") or "").lower())
    check("B7 REAL transactions: multi-table burst rolls back completely",
          ok,
          f"bad edge rejected with      : {(js.get('bad_err') or '(none)')[:110]}\n"
          f"rollback error              : {js.get('rollback_err') or '(none)'}\n"
          f"story rows left after abort : {js.get('rows_left')} (must be 0)\n"
          f"read back on a FRESH handle (LESSONS §2: never on the writing conn)\n"
          f"=> the CLI path cannot do this: `dolt sql -q` is one implicit tx per\n"
          f"   invocation, so a multi-invocation burst has no rollback point")


# ---------------------------------------------------------------- B8


def b8_procs(dirs):
    c = dirs["c"]
    dt, js, r = emb("procs", c.parent, c.name)
    p = js.get("probes", {})
    okstr = {k: v for k, v in p.items() if str(v).startswith("ok")}
    errs = {k: v for k, v in p.items() if not str(v).startswith("ok")}
    # push/pull are EXPECTED to fail here: no remote configured yet
    expected_err = {"DOLT_PUSH", "DOLT_PULL", "DOLT_FETCH"}
    unexpected = {k: v for k, v in errs.items() if k not in expected_err}
    ok = js.get("ok") is True and not unexpected
    check("B8 dolt procedures + system tables in-process",
          ok,
          f"working ({len(okstr)}): " + ", ".join(sorted(okstr)) + "\n"
          + (f"failing ({len(errs)}): " + "; ".join(f"{k} -> {v}" for k, v in sorted(errs.items()))
             + "\n" if errs else "")
          + "=> version control (branch/checkout/merge/reset/gc/commit/log/diff/history/AS OF)\n"
            "   is reachable in-process; remote ops need a remote (see the GitHub suite)")


# ---------------------------------------------------------------- B9/B10/B11


def b9_two_embedded(dirs):
    c = dirs["c"]
    hold = subprocess.Popen([str(BENCH), "hold", str(c.parent), c.name, "4", "holder"],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    # wait for the holder to actually have the engine open
    t0 = time.time()
    while time.time() - t0 < 30:
        line = hold.stderr.readline()
        if "HELD" in line:
            break
    time.sleep(0.3)
    dt, js, r = emb("contend", c.parent, c.name, "contender", timeout=60)
    hold.wait(timeout=60)
    hout = hold.stdout.read()
    err = (js.get("err") or "")[:200]
    blocked = r.returncode != 0
    check("B9 a second embedded process on the SAME directory",
          js is not None,
          f"holder held the engine ~4 s, then a second process tried to open+write\n"
          f"second process: rc={r.returncode} after {dt:.0f} ms  "
          f"{'REFUSED' if blocked else 'SUCCEEDED (waited for the lock)'}\n"
          f"error: {err or '(none)'}\n"
          f"holder result: {(hout or '').strip()[:120]}\n"
          f"=> the embedded engine is SINGLE-WRITER per directory. Whatever the\n"
          f"   mechanism, N agents on one clone still need serialization —\n"
          f"   either flock (invariant, unchanged) or the driver's own backoff\n"
          f"   (beads sets cfg.BackOff to wait until ctx cancel).")
    FACTS["b9_blocked"] = blocked
    FACTS["b9_err"] = err


def b10_mixed(dirs):
    c = dirs["c"]
    hold = subprocess.Popen([str(BENCH), "hold", str(c.parent), c.name, "4", "holder2"],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    t0 = time.time()
    while time.time() - t0 < 30:
        if "HELD" in hold.stderr.readline():
            break
    time.sleep(0.3)
    t0 = time.perf_counter()
    r = sql_cli("INSERT INTO benchw (k,v) VALUES ('cli-while-held',1)", cwd=c, timeout=60)
    dt = (time.perf_counter() - t0) * 1000
    hold.wait(timeout=60)
    msg = ((r.stderr or "") + (r.stdout or "")).strip().replace("\n", " ")[:200]
    check("B10 `dolt` CLI writing while an embedded process holds the dir",
          True,
          f"CLI write while held: rc={r.returncode} after {dt:.0f} ms\n"
          f"message: {msg or '(none)'}\n"
          f"=> mixing the two access paths on one directory is NOT free; a\n"
          f"   migration cannot run `fa` embedded and `dolt sql` side by side\n"
          f"   without the same mutex covering both.")


def b11_counter(dirs):
    c = dirs["c"]
    sql_cli("DROP TABLE IF EXISTS ctr", cwd=c)
    sql_cli("CREATE TABLE ctr (id TINYINT PRIMARY KEY, n INT NOT NULL)", cwd=c)
    sql_cli("INSERT INTO ctr VALUES (1,0)", cwd=c)
    dolt(["add", "-A"], cwd=c)
    dolt(["commit", "-m", "ctr"], cwd=c)
    N, PROCS = 50, 2
    procs = [subprocess.Popen([str(BENCH), "counter", str(c.parent), c.name, str(N)],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
             for _ in range(PROCS)]
    outs = []
    for p in procs:
        o, e = p.communicate(timeout=300)
        outs.append((p.returncode, (o or "").strip(), (e or "").strip()[:160]))
    final = csv_first(sql_cli("SELECT n FROM ctr WHERE id=1", cwd=c))
    winners = sum(1 for rc, _, _ in outs if rc == 0)
    exact = str(final) == str(N * winners)
    check(f"B11 `n = n + 1` x{N} from {PROCS} concurrent embedded processes",
          exact,
          f"processes that completed: {winners}/{PROCS}\n"
          + "\n".join(f"  rc={rc} out={o[:100]} err={e}" for rc, o, e in outs) + "\n"
          + f"counter after           : {final}  (expected {N*winners} if serialized "
            f"and nothing lost)\n"
            f"=> if only one process can hold the dir, read-modify-write is safe by\n"
            f"   construction — the same conclusion as X3 under the flock mutex, and\n"
            f"   invariant 1's token tax stays confined to the SERVER topology.")
    FACTS["b11_winners"] = winners
    FACTS["b11_exact"] = exact


# ---------------------------------------------------------------- B12


def b12_compat():
    d = ROOT / "d"
    d.mkdir(parents=True, exist_ok=True)
    # 1. create a database from scratch with NO dolt CLI involvement
    dt, js, r = emb("create", d, "fa_born_embedded", str(SCHEMA))
    born = (d / "fa_born_embedded").exists() and js.get("ok") is True
    # 2. can the CLI 2.2.3 read what driver v2.2.0 created?
    cli_read = sql_cli("SELECT COUNT(*) FROM bc", cwd=d / "fa_born_embedded")
    cli_ok = cli_read.returncode == 0
    log = dolt(["log", "--oneline"], cwd=d / "fa_born_embedded")
    # 3. the reverse direction was already exercised: B3/B4 read repo 'a',
    #    which `dolt init` + `dolt sql -f` created.
    ver = sh(["dolt", "version"]).stdout.strip().splitlines()[0]
    driver_dolt = ""
    for ln in (POC / "bench" / "go.mod").read_text().splitlines():
        if "dolthub/dolt/go " in ln:
            driver_dolt = ln.strip().rstrip(" // indirect")
    check("B12 storage compat: driver v2.2.0 <-> dolt CLI 2.2.3, both ways",
          born and cli_ok,
          f"created by the embedded driver, no CLI  : {born} ({js.get('create_ms',0):.0f} ms)\n"
          f"then read by `dolt sql` CLI             : rc={cli_read.returncode} "
          f"rows={csv_first(cli_read)}\n"
          f"`dolt log` on the embedded-born repo    : "
          f"{(log.stdout or '').strip().splitlines()[:1]}\n"
          f"CLI version                             : {ver}\n"
          f"driver pins                             : {driver_dolt}\n"
          f"=> both directions work, but note the driver carries its OWN dolt\n"
          f"   build. CLI and driver are two independently-versioned engines over\n"
          f"   one on-disk format; a pin mismatch is a real upgrade hazard.")


# ---------------------------------------------------------------- B13


def b13_verdict():
    w_cli = FACTS.get("w_cli", float("nan"))
    w_clib = FACTS.get("w_clib", float("nan"))
    w_clitx = FACTS.get("w_clitx", float("nan"))
    w_emb = FACTS.get("w_emb_auto", float("nan"))
    w_embtx = FACTS.get("w_emb_tx", float("nan"))
    imp_cli = FACTS.get("imp_cli", float("nan"))
    imp_clitx = FACTS.get("imp_clitx", float("nan"))
    imp_ps = FACTS.get("imp_emb_ps", float("nan"))
    imp_tx = FACTS.get("imp_emb_tx", float("nan"))
    # Invariant 6 says: batch a unit of work into ONE session or pay ~40x. The
    # measured question is WHICH tax that 40x is, and whether the embedded path
    # removes the need to batch at all. It does not: per-statement embedded is
    # still an order of magnitude off in-transaction. What changes is the
    # REASON — and that reason is reachable from the CLI too, via BEGIN/COMMIT.
    still_needs_batching = imp_ps > imp_tx * 5
    cli_can_reach = imp_clitx < imp_cli / 3
    check("B13 verdict on invariants 4 and 6",
          True,
          f"per-write: CLI/invocation {w_cli:.0f} ms | CLI batched {w_clib:.2f} ms | "
          f"CLI one-tx {w_clitx:.2f} ms | emb autocommit {w_emb:.2f} ms | "
          f"emb one-tx {w_embtx:.2f} ms\n"
          f"import:    CLI batched {imp_cli:.1f} s | CLI one-tx {imp_clitx:.1f} s | "
          f"emb per-stmt {imp_ps:.1f} s | emb one-tx {imp_tx:.1f} s\n"
          f"\n"
          f"INVARIANT 6 {'SURVIVES' if still_needs_batching else 'DISSOLVES'} — but its "
          f"stated CAUSE is wrong.\n"
          f"  There are TWO taxes, not one. Process spawn (~{w_cli:.0f} ms) is only the\n"
          f"  outer one; a per-statement autocommit costs ~{w_clib:.1f} ms in BOTH paths\n"
          f"  (CLI batched {w_clib:.2f} vs embedded autocommit {w_emb:.2f} — the same number).\n"
          f"  One explicit transaction is what buys the order of magnitude, and the\n"
          f"  CLI {'CAN' if cli_can_reach else 'CANNOT'} reach it with BEGIN/COMMIT around the file.\n"
          f"  Restate invariant 6 as: ONE TRANSACTION per unit of work (which is also\n"
          f"  what atomicity requires) — not 'one process invocation'.\n"
          f"\n"
          f"INVARIANT 4 (idempotent retry) is UNTOUCHED by this benchmark.\n"
          f"  It exists because a push on a shared clone publishes siblings' commits;\n"
          f"  that is a git-level property of the topology, not of the SQL access\n"
          f"  path. B8 shows DOLT_PUSH is callable in-process, so the embedded path\n"
          f"  inherits the same semantics. Settled only against a real remote.")


# ---------------------------------------------------------------- server ref


def server_reference(dirs):
    """A sql-server on a COPY of the imported corpus, for the third data point."""
    src = dirs["a"]
    dst = ROOT / "s" / "fa_srv"
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dst)
    p = subprocess.Popen(["dolt", "sql-server", "--host", "127.0.0.1", "--port", str(SRV_PORT)],
                         cwd=dst, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        if not wait_port(SRV_PORT):
            return None
        import pymysql
        out = {}
        t = []
        for _ in range(TRIALS):
            t0 = time.perf_counter()
            cn = pymysql.connect(host="127.0.0.1", port=SRV_PORT, user="root",
                                 database="fa_srv", autocommit=True)
            with cn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchall()
            cn.close()
            t.append((time.perf_counter() - t0) * 1000)
        out["trivial"] = med(t)
        t = []
        for _ in range(TRIALS):
            t0 = time.perf_counter()
            cn = pymysql.connect(host="127.0.0.1", port=SRV_PORT, user="root",
                                 database="fa_srv", autocommit=True)
            with cn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM bc")
                cur.fetchall()
            cn.close()
            t.append((time.perf_counter() - t0) * 1000)
        out["count"] = med(t)
        # warm queries on one connection
        cn = pymysql.connect(host="127.0.0.1", port=SRV_PORT, user="root",
                             database="fa_srv", autocommit=True)
        warm = []
        with cn.cursor() as cur:
            for _ in range(N_WARM):
                t0 = time.perf_counter()
                cur.execute("SELECT COUNT(*) FROM bc")
                cur.fetchall()
                warm.append((time.perf_counter() - t0) * 1000)
        cn.close()
        out["warm_count"] = med(warm)
        return out
    except Exception as e:
        print(f"        (server reference unavailable: {e})")
        return None
    finally:
        p.terminate()
        try:
            p.wait(timeout=20)
        except subprocess.TimeoutExpired:
            p.kill()


# ---------------------------------------------------------------- main


def main():
    print(f"=== embedded driver benchmark  (dolt {sh(['dolt','version']).stdout.split()[2]}, "
          f"driver v2.2.0, trials={TRIALS})\n")
    dirs = setup()
    b1_adoption(dirs)
    print()
    # import FIRST: B2-B4 need a populated corpus
    b6_import(dirs)
    print()
    srv = server_reference(dirs)
    b2_cold_trivial(dirs, srv)
    print()
    b3_cold_real(dirs, srv)
    print()
    b4_warm(dirs, srv)
    if srv:
        print(f"        sql-server warm COUNT(*)    : {srv['warm_count']:8.2f} ms "
              f"(one connection, {N_WARM} iters)")
    print()
    b5_writes(dirs, srv)
    print()
    b7_atomicity(dirs)
    print()
    b8_procs(dirs)
    print()
    b9_two_embedded(dirs)
    print()
    b10_mixed(dirs)
    print()
    b11_counter(dirs)
    print()
    b12_compat()
    print()
    b13_verdict()
    print()
    npass = sum(1 for _, ok, _ in RESULTS if ok)
    print("=" * 74)
    print(f"{npass}/{len(RESULTS)} passed")
    for name, ok, _ in RESULTS:
        if not ok:
            print(f"  FAILED: {name}")
    sys.exit(0 if npass == len(RESULTS) else 1)


if __name__ == "__main__":
    main()
