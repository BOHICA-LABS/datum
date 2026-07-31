#!/usr/bin/env python3
"""Spike tests: each test targets a SPECIFIC failure mode observed in the live
vsdd-factory factory-artifacts corpus. A pass means Dolt structurally prevents
(or trivially answers) something the markdown+git implementation gets wrong.

Run: .venv/bin/python poc/test_spike.py
"""
from __future__ import annotations

import re
import subprocess
import sys
import threading
import time
from pathlib import Path

import pymysql

PORT = 3308
DB = "factory_artifacts"
FACTORY = Path("/Users/jmagady/Dev/vsdd-factory/.factory")

RESULTS: list[tuple[str, bool, str]] = []


def conn(db=DB, autocommit=True):
    kw = dict(host="127.0.0.1", port=PORT, user="root", autocommit=autocommit,
              cursorclass=pymysql.cursors.DictCursor)
    if db:
        kw["database"] = db
    return pymysql.connect(**kw)


def q(c, sql, args=None):
    with c.cursor() as cur:
        cur.execute(sql, args or ())
        try:
            return cur.fetchall()
        except Exception:
            return cur.rowcount


def rowcount(c, sql, args=None):
    with c.cursor() as cur:
        cur.execute(sql, args or ())
        return cur.rowcount


def check(name, ok, detail=""):
    RESULTS.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}")
    if detail:
        for ln in detail.splitlines():
            print(f"        {ln}")


# ------------------------------------------------------------------ T1 counts


def t1_count_authority():
    """The live corpus asserts FOUR different BC totals. COUNT(*) is one number."""
    c = conn()
    db_count = q(c, "SELECT COUNT(*) n FROM bc")[0]["n"]

    bcidx = (FACTORY / "specs/behavioral-contracts/BC-INDEX.md").read_text(errors="replace")
    fm = re.search(r"^total_bcs:\s*(\d+)", bcidx, re.M)
    body_total = re.search(r"\|\s*\*\*Total\*\*\s*\|[^|]*\|\s*\*\*(\d+)\*\*", bcidx)
    arch = (FACTORY / "specs/architecture/ARCH-INDEX.md").read_text(errors="replace")
    arch_total = re.search(r"\*\*Total BCs:\s*([\d,]+)", arch)

    on_disk = len([p for p in (FACTORY / "specs/behavioral-contracts").rglob("BC-*.md")
                   if p.name != "BC-INDEX.md"])
    idx_ids = len(set(re.findall(r"BC-\d+\.\d+\.\d+", bcidx)))

    claims = {
        "BC-INDEX frontmatter total_bcs": int(fm.group(1)) if fm else None,
        "BC-INDEX body Total row": int(body_total.group(1)) if body_total else None,
        "ARCH-INDEX 'Total BCs'": int(arch_total.group(1).replace(",", "")) if arch_total else None,
        "distinct IDs in BC-INDEX rows": idx_ids,
        "BC-*.md files on disk": on_disk,
    }
    distinct = sorted({v for v in claims.values() if v is not None})
    detail = "\n".join(f"{k:34} = {v}" for k, v in claims.items())
    detail += f"\n{'DB SELECT COUNT(*)':34} = {db_count}"
    detail += f"\n-> markdown corpus asserts {len(distinct)} distinct values {distinct}; DB asserts 1"
    c.close()
    # The test proves the DRIFT EXISTS in markdown and that the DB has a single answer.
    check("T1 count authority: markdown drifts, COUNT(*) cannot",
          len(distinct) > 1 and db_count == on_disk, detail)


# ------------------------------------------------- T2 referential integrity


def t2_dangling_refs():
    """BC-INDEX cites 3 BC IDs that have NO record file. A FK makes that impossible."""
    bcidx = (FACTORY / "specs/behavioral-contracts/BC-INDEX.md").read_text(errors="replace")
    cited = set(re.findall(r"BC-\d+\.\d+\.\d+", bcidx))
    c = conn()
    present = {r["bc_id"] for r in q(c, "SELECT bc_id FROM bc")}
    dangling = sorted(cited - present)

    # Now prove the DB refuses to create such a reference.
    q(c, "INSERT IGNORE INTO vp (vp_id, title, body) VALUES ('VP-999','probe','probe')")
    refused = False
    err = ""
    try:
        q(c, "INSERT INTO bc_trace (bc_id, vp_id) VALUES (%s,'VP-999')",
          (dangling[0] if dangling else "BC-9.99.999",))
    except pymysql.err.Error as e:
        refused, err = True, str(e)[:110]
    q(c, "DELETE FROM vp WHERE vp_id='VP-999'")
    c.close()
    check("T2 dangling refs: FK rejects a reference to a non-existent BC",
          refused and len(dangling) > 0,
          f"live corpus dangling BC cites ({len(dangling)}): {dangling}\n"
          f"DB rejected the same reference: {err}")


def t3_unique_id():
    """A duplicate/renamed record cannot exist twice. The live corpus has
    BC-2.02.013-host-run-subprocess.md, a filename that breaks every index lookup."""
    c = conn()
    dup_refused = False
    err = ""
    try:
        q(c, """INSERT INTO bc (bc_id, ss_id, title, body)
                SELECT bc_id, ss_id, 'dup', 'dup' FROM bc LIMIT 1""")
    except pymysql.err.Error as e:
        dup_refused, err = True, str(e)[:110]
    odd = [p.name for p in (FACTORY / "specs/behavioral-contracts").rglob("BC-*.md")
           if p.name != "BC-INDEX.md" and not re.fullmatch(r"BC-\d+\.\d+\.\d+\.md", p.name)]
    c.close()
    check("T3 identity: PK rejects duplicate BC id; filename drift becomes impossible",
          dup_refused,
          f"live corpus non-canonical filenames: {odd}\nDB rejected duplicate PK: {err}")


# ------------------------------------------------------------- T4 CAS lock


def t4_cas_lock_race():
    """The factory lock is a YAML block in STATE.md guarded by fetch + push
    --force-with-lease, which the skill itself documents as TOCTOU (CWE-367).
    Here: N threads race one UPDATE. Exactly one must win."""
    c0 = conn()
    q(c0, "UPDATE factory_lock SET holder=NULL, locked_at=NULL, expires_at=NULL WHERE id=1")
    c0.close()

    N = 16
    wins: list[str] = []
    lock = threading.Lock()
    barrier = threading.Barrier(N)

    def worker(i):
        c = conn()
        try:
            barrier.wait()  # maximize contention
            n = rowcount(c, """UPDATE factory_lock
                               SET holder=%s, locked_at=NOW(),
                                   expires_at=DATE_ADD(NOW(), INTERVAL 600 SECOND),
                                   fence=fence+1
                               WHERE id=1 AND (holder IS NULL OR expires_at < NOW())""",
                         (f"agent-{i}",))
            if n == 1:
                with lock:
                    wins.append(f"agent-{i}")
        except pymysql.err.Error:
            pass  # a serialization failure is a legitimate loss, not a win
        finally:
            c.close()

    ts = [threading.Thread(target=worker, args=(i,)) for i in range(N)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()

    c = conn()
    holder = q(c, "SELECT holder, fence FROM factory_lock WHERE id=1")[0]
    c.close()
    check("T4 CAS lock: 16 concurrent acquirers, exactly one wins (no TOCTOU)",
          len(wins) == 1 and holder["holder"] == wins[0],
          f"winners={wins} final holder={holder['holder']} fence={holder['fence']}")


def t5_lock_expiry_and_release():
    c = conn()
    q(c, """UPDATE factory_lock SET holder='stale-agent', locked_at=NOW(),
            expires_at=DATE_SUB(NOW(), INTERVAL 10 SECOND) WHERE id=1""")
    # A non-holder must NOT be able to release someone else's lock.
    bad = rowcount(c, "UPDATE factory_lock SET holder=NULL WHERE id=1 AND holder=%s", ("other",))
    # But an expired lock IS reclaimable.
    took = rowcount(c, """UPDATE factory_lock SET holder='fresh-agent', fence=fence+1,
                          expires_at=DATE_ADD(NOW(), INTERVAL 600 SECOND)
                          WHERE id=1 AND (holder IS NULL OR expires_at < NOW())""")
    rel = rowcount(c, "UPDATE factory_lock SET holder=NULL WHERE id=1 AND holder='fresh-agent'")
    c.close()
    check("T5 lock semantics: non-holder release refused, expired lock reclaimable",
          bad == 0 and took == 1 and rel == 1,
          f"foreign_release_rows={bad} (want 0), reclaim={took} (want 1), release={rel} (want 1)")


# -------------------------------------------------------- T6 history / audit


def t6_time_travel():
    """'When did BC-1.05.010 change and to what' currently means archaeology across
    1,607 commits. Here it is one query against dolt_history_*."""
    c = conn()
    target = q(c, "SELECT bc_id FROM bc ORDER BY bc_id LIMIT 1")[0]["bc_id"]
    q(c, "UPDATE bc SET title=CONCAT(title,' [rev2]'), version='v2.0' WHERE bc_id=%s", (target,))
    q(c, "CALL DOLT_COMMIT('-Am','test: amend one BC for history check')")
    hist = q(c, """SELECT commit_hash, version, title FROM dolt_history_bc
                   WHERE bc_id=%s ORDER BY commit_date DESC""", (target,))
    versions = [h["version"] for h in hist]
    c.close()
    check("T6 audit: per-record history via dolt_history_bc (no commit archaeology)",
          len(hist) >= 2 and "v2.0" in versions,
          f"{target}: {len(hist)} revisions, versions={versions[:4]}")


def t7_diff_between_commits():
    c = conn()
    rows = q(c, """SELECT to_bc_id, from_version, to_version, diff_type
                   FROM dolt_diff_bc
                   WHERE to_commit = HASHOF('HEAD') LIMIT 5""")
    c.close()
    check("T7 change review: dolt_diff_bc yields cell-level deltas for a commit",
          len(rows) >= 1,
          f"changed rows in HEAD: {len(rows)}; sample={rows[0] if rows else None}")


# ------------------------------------------------------- T8 branch + merge


def t8_parallel_branch_merge():
    """Two agents edit DIFFERENT BCs on separate branches. Both merge cleanly.
    This is the wave-parallelism case that currently forces sequential
    single-commit bursts on one orphan branch."""
    c = conn(autocommit=True)
    for b in ("agent_a", "agent_b"):
        try:
            q(c, f"CALL DOLT_BRANCH('-D','{b}')")
        except pymysql.err.Error:
            pass
    ids = [r["bc_id"] for r in q(c, "SELECT bc_id FROM bc ORDER BY bc_id LIMIT 2")]
    q(c, "CALL DOLT_BRANCH('agent_a')")
    q(c, "CALL DOLT_BRANCH('agent_b')")
    c.close()

    # Run-unique values: re-running with the same value is a no-op write, and
    # DOLT_COMMIT errors with 'nothing to commit'.
    tag = int(time.time()) % 100000
    cap_a, cap_b = f"CAP-A{tag}", f"CAP-B{tag}"
    for br, bcid, cap in (("agent_a", ids[0], cap_a), ("agent_b", ids[1], cap_b)):
        cx = conn(db=f"{DB}/{br}")
        q(cx, "UPDATE bc SET capability=%s WHERE bc_id=%s", (cap, bcid))
        q(cx, f"CALL DOLT_COMMIT('-Am','{br}: set capability on {bcid}')")
        cx.close()

    c = conn()
    q(c, "CALL DOLT_CHECKOUT('main')")
    m1 = q(c, "CALL DOLT_MERGE('agent_a')")
    m2 = q(c, "CALL DOLT_MERGE('agent_b')")
    confl = q(c, "SELECT COUNT(*) n FROM dolt_conflicts")[0]["n"]
    got = {r["bc_id"]: r["capability"]
           for r in q(c, "SELECT bc_id, capability FROM bc WHERE bc_id IN (%s,%s)", tuple(ids))}
    c.close()
    check("T8 parallel work: two agent branches merge cleanly, both edits survive",
          confl == 0 and got.get(ids[0]) == cap_a and got.get(ids[1]) == cap_b,
          f"merge1={m1} merge2={m2}\nconflicts={confl} result={got}")


def t9_conflict_is_detected():
    """Two agents edit the SAME cell. Dolt must SURFACE a conflict, not silently pick."""
    c = conn()
    for b in ("conf_a", "conf_b"):
        try:
            q(c, f"CALL DOLT_BRANCH('-D','{b}')")
        except pymysql.err.Error:
            pass
    bcid = q(c, "SELECT bc_id FROM bc ORDER BY bc_id LIMIT 1")[0]["bc_id"]
    q(c, "CALL DOLT_BRANCH('conf_a')")
    q(c, "CALL DOLT_BRANCH('conf_b')")
    c.close()

    tag = int(time.time()) % 100000
    for br, cap in (("conf_a", f"CAP-X{tag}"), ("conf_b", f"CAP-Y{tag}")):
        cx = conn(db=f"{DB}/{br}")
        q(cx, "UPDATE bc SET capability=%s WHERE bc_id=%s", (cap, bcid))
        q(cx, f"CALL DOLT_COMMIT('-Am','{br}: conflicting capability')")
        cx.close()

    c = conn()
    q(c, "CALL DOLT_CHECKOUT('main')")
    q(c, "CALL DOLT_MERGE('conf_a')")
    detected, note = False, ""
    try:
        r = q(c, "CALL DOLT_MERGE('conf_b')")
        n = q(c, "SELECT COUNT(*) n FROM dolt_conflicts")[0]["n"]
        detected = n > 0
        note = f"merge returned {r}; dolt_conflicts rows={n}"
        if detected:
            q(c, f"CALL DOLT_CONFLICTS_RESOLVE('--ours','bc')")
            q(c, "CALL DOLT_COMMIT('-Am','resolve: take ours')")
    except pymysql.err.Error as e:
        detected, note = True, f"merge raised: {str(e)[:120]}"
    try:
        q(c, "CALL DOLT_MERGE('--abort')")
    except pymysql.err.Error:
        pass
    c.close()
    check("T9 conflict safety: same-cell edits surface a conflict, never silent loss",
          detected, note)


# ------------------------------------------------------------- T10 render


def t10_render_is_derived():
    """Markdown stays available for humans/diff review, but it is GENERATED.
    The rendered index's total must equal COUNT(*) by construction."""
    out = Path("rendered")
    subprocess.run([sys.executable, "poc/fa.py", "render", "--out", str(out)],
                   check=True, capture_output=True)
    txt = (out / "BC-INDEX.md").read_text()
    fm = int(re.search(r"^total_bcs:\s*(\d+)", txt, re.M).group(1))
    body = int(re.search(r"\|\s*\*\*Total\*\*\s*\|[^|]*\|\s*\*\*(\d+)\*\*", txt).group(1))
    rows = len(set(re.findall(r"^\| (BC-\d+\.\d+\.\d+) \|", txt, re.M)))
    c = conn()
    db_count = q(c, "SELECT COUNT(*) n FROM bc")[0]["n"]
    c.close()
    check("T10 rendered export: frontmatter == body total == row count == COUNT(*)",
          fm == body == rows == db_count,
          f"frontmatter={fm} body_total={body} index_rows={rows} db={db_count}")


# ------------------------------------------------------------- T11 queries


def t11_cross_cutting_query():
    """Questions that currently require grep sweeps across 3,085 files."""
    c = conn()
    tbd = q(c, "SELECT COUNT(*) n FROM bc WHERE capability IS NULL")[0]["n"]
    top = q(c, """SELECT s.ss_id, COUNT(*) n FROM bc b JOIN subsystem s ON s.ss_id=b.ss_id
                  GROUP BY s.ss_id ORDER BY n DESC LIMIT 3""")
    t0 = time.time()
    q(c, "SELECT COUNT(*) FROM bc WHERE body LIKE '%%idempoten%%'")
    dt = (time.time() - t0) * 1000
    c.close()
    check("T11 cross-cutting queries answered in SQL, not grep sweeps", True,
          f"BCs with no capability: {tbd}\n"
          f"largest subsystems: {[(r['ss_id'], r['n']) for r in top]}\n"
          f"full-text scan over 1,959 bodies: {dt:.0f}ms")


# ------------------------------------------------------ T12 git remote push


def t12_dolt_rides_git_remote():
    """Beads claims Dolt data lives under refs/dolt/data and can share the
    project's own git remote. If true, this replaces the factory-artifacts
    orphan branch with NO new infrastructure. Verify against a real bare repo."""
    # Unique names per run: Dolt keeps remote-tracking state, so reusing a remote
    # name against a freshly-recreated bare repo makes `dolt push` stall forever.
    tag = str(int(time.time()))
    remote_name = f"gitorigin{tag}"
    bare = Path(f"/tmp/_spike_bare_{tag}.git")
    seed = Path(f"/tmp/_spike_seed_{tag}")
    subprocess.run(["rm", "-rf", str(bare), str(seed)], check=True)
    subprocess.run(["git", "init", "--bare", "-q", str(bare)], check=True)
    # Dolt refuses a git remote with zero branches, so seed it like a real project.
    subprocess.run(["git", "init", "-q", "-b", "main", str(seed)], check=True)
    (seed / "README.md").write_text("seed\n")
    for cmd in (["git", "add", "-A"],
                ["git", "-c", "user.email=s@l", "-c", "user.name=s", "commit", "-qm", "seed"],
                ["git", "remote", "add", "origin", str(bare)],
                ["git", "push", "-q", "origin", "main"]):
        subprocess.run(cmd, cwd=seed, check=True, capture_output=True)
    db_dir = Path("poc/db") / DB

    def dolt(*args, cwd=db_dir, timeout=180):
        try:
            return subprocess.run(["dolt", *args], cwd=cwd, capture_output=True,
                                  text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return subprocess.CompletedProcess(args, 124, "", f"TIMEOUT after {timeout}s")

    add = dolt("remote", "add", remote_name, f"file://{bare}")
    push = dolt("push", remote_name, "main")
    ls = subprocess.run(["git", "for-each-ref", "--format=%(refname)"],
                        cwd=bare, capture_output=True, text=True)
    refs = [r for r in ls.stdout.split() if r]
    dolt_refs = [r for r in refs if "dolt" in r]
    ok = push.returncode == 0 and len(dolt_refs) > 0
    check("T12 infrastructure: Dolt history pushes into a plain git remote (refs/dolt/*)",
          ok,
          f"remote add rc={add.returncode} push rc={push.returncode}\n"
          f"stderr={(push.stderr or '').strip()[:200]}\n"
          f"refs in bare repo: {refs[:6]}")


# ---------------------------------------------------------------- T13 scale


def t13_scale():
    c = conn()
    t0 = time.time()
    n = q(c, "SELECT COUNT(*) n FROM bc")[0]["n"]
    t_count = (time.time() - t0) * 1000
    t0 = time.time()
    q(c, "SELECT bc_id, title FROM bc WHERE bc_id LIKE 'BC-5.%%' LIMIT 50")
    t_scan = (time.time() - t0) * 1000
    t0 = time.time()
    q(c, "SELECT * FROM bc WHERE bc_id='BC-1.05.010'")
    t_pk = (time.time() - t0) * 1000
    sz = subprocess.run(["du", "-sh", f"poc/db/{DB}"], capture_output=True, text=True).stdout.split()[0]
    c.close()
    check("T13 scale: full corpus in DB, sub-second answers", t_count < 500 and t_pk < 200,
          f"rows={n}  COUNT(*)={t_count:.0f}ms  prefix-scan={t_scan:.0f}ms  "
          f"PK-lookup={t_pk:.0f}ms  on-disk={sz}")


# ---------------------------------------------------------------- runner


def main():
    print("=" * 74)
    print("Dolt-as-factory-artifact-store: spike tests against the LIVE corpus")
    print("=" * 74)
    tests = [t1_count_authority, t2_dangling_refs, t3_unique_id, t4_cas_lock_race,
             t5_lock_expiry_and_release, t6_time_travel, t7_diff_between_commits,
             t8_parallel_branch_merge, t9_conflict_is_detected, t10_render_is_derived,
             t11_cross_cutting_query, t12_dolt_rides_git_remote, t13_scale]
    for t in tests:
        try:
            t()
        except Exception as e:
            import traceback
            check(f"{t.__name__} (ERROR)", False, traceback.format_exc()[-600:])
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
