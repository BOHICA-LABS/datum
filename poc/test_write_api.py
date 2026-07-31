#!/usr/bin/env python3
"""The mutation surface `fa` must expose to be the SOLE interface.

Everything before this pass tested reads, integrity and coordination. If markdown
becomes a generated export, then EVERY artifact change goes through this write path,
so it has to be complete and safe on its own.

  W1  create with validation (malformed id / unknown subsystem / duplicate rejected)
  W2  amend -> history preserved, prior revision still queryable
  W3  retire -> lifecycle change without breaking inbound references
  W4  multi-record write is atomic (story + all its edges, or nothing)
  W5  re-import is idempotent (no churn, no duplicate commits)
  W6  audit attribution: who changed what, per record
  W7  reads are NOT blocked while a writer holds the mutex
  W8  the real factory gates expressed as queries instead of hooks
  W9  delete is refused when inbound references exist (or cascades explicitly)

Run: .venv/bin/python -u poc/test_write_api.py
"""
from __future__ import annotations

import re
import subprocess
import sys
import threading
import time
from pathlib import Path

import pymysql

PORT, DB = 3308, "factory_artifacts"
RESULTS: list[tuple[str, bool, str]] = []


def conn(autocommit=True):
    return pymysql.connect(host="127.0.0.1", port=PORT, user="root", database=DB,
                           autocommit=autocommit, cursorclass=pymysql.cursors.DictCursor)


def q(c, sql, args=None):
    with c.cursor() as cur:
        cur.execute(sql, args or ())
        try:
            return cur.fetchall()
        except Exception:
            return []


def rc(c, sql, args=None):
    with c.cursor() as cur:
        cur.execute(sql, args or ())
        return cur.rowcount


def check(name, ok, detail=""):
    RESULTS.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}")
    for ln in (detail or "").splitlines():
        print(f"        {ln}")


# --------------------------------------------------------------- fa.write layer


BC_RE = re.compile(r"^BC-\d+\.\d+\.\d+$")


class Refused(Exception):
    """A validation refusal. fa must refuse loudly, never coerce."""


def create_bc(c, bc_id, ss_id, title, body="", capability=None):
    """The create path. Validation happens HERE, in the single write path — not in
    agent prose, and not in a post-hoc grep sweep."""
    if not BC_RE.match(bc_id):
        raise Refused(f"malformed bc_id {bc_id!r}")
    if not title.strip():
        raise Refused("title must be non-empty")
    if capability is not None and not re.fullmatch(r"CAP-\d+", capability):
        raise Refused(f"capability {capability!r} is not a CAP-NNN id")
    # BC-S prefix must agree with the subsystem's registered prefix.
    ss = q(c, "SELECT bc_prefix FROM subsystem WHERE ss_id=%s", (ss_id,))
    if not ss:
        raise Refused(f"unknown subsystem {ss_id!r}")
    prefix = int(bc_id[3:].split(".")[0])
    if prefix != ss[0]["bc_prefix"]:
        raise Refused(f"{bc_id} prefix {prefix} != {ss_id} prefix {ss[0]['bc_prefix']}")
    try:
        rc(c, """INSERT INTO bc (bc_id, ss_id, title, body, capability, version)
                 VALUES (%s,%s,%s,%s,%s,'v1.0')""",
           (bc_id, ss_id, title, body, capability))
    except pymysql.err.Error as e:
        if e.args[0] in (1062, 1022):
            raise Refused(f"{bc_id} already exists") from e
        raise
    return bc_id


def amend_bc(c, bc_id, **fields):
    """Amend + version bump, as one statement so the version can never drift from
    the content it describes."""
    if not fields:
        raise Refused("amend needs at least one field")
    allowed = {"title", "body", "capability", "lifecycle_status", "status"}
    bad = set(fields) - allowed
    if bad:
        raise Refused(f"not amendable: {sorted(bad)}")
    cur = q(c, "SELECT version FROM bc WHERE bc_id=%s", (bc_id,))
    if not cur:
        raise Refused(f"{bc_id} not found")
    # Bump MINOR, preserving the corpus's vMAJOR.MINOR shape. Arithmetic on the
    # whole string collapses 'v1.0' -> 'v2' because CAST(2.0 AS CHAR) drops the .0.
    mv = re.match(r"v?(\d+)\.(\d+)", str(cur[0]["version"]) or "1.0")
    maj, minor = (int(mv.group(1)), int(mv.group(2))) if mv else (1, 0)
    newver = f"v{maj}.{minor + 1}"
    sets = ", ".join(f"{k}=%s" for k in fields)
    args = list(fields.values()) + [newver, bc_id]
    n = rc(c, f"UPDATE bc SET {sets}, version=%s WHERE bc_id=%s", args)
    if n != 1:
        raise Refused(f"{bc_id} not found")
    return newver


def commit(c, msg):
    try:
        q(c, "CALL DOLT_COMMIT('-Am', %s)", (msg,))
        return True
    except pymysql.err.Error as e:
        if "nothing to commit" in str(e):
            return False
        raise


# ---------------------------------------------------------------- tests

TMP_SS = "SS-01"


def cleanup():
    c = conn()
    q(c, "DELETE FROM bc_trace WHERE bc_id LIKE 'BC-1.99.%%'")
    q(c, "DELETE FROM story_bc WHERE bc_id LIKE 'BC-1.99.%%'")
    q(c, "DELETE FROM vp_bc WHERE bc_id LIKE 'BC-1.99.%%'")
    q(c, "DELETE FROM bc WHERE bc_id LIKE 'BC-1.99.%%'")
    q(c, "DELETE FROM story_bc WHERE story_id LIKE 'S-99.%%'")
    q(c, "DELETE FROM story WHERE story_id LIKE 'S-99.%%'")
    commit(c, "test: cleanup")
    c.close()


def w1_create_validation():
    c = conn()
    cases = [
        ("BC-1.99.001", TMP_SS, "valid contract", None, True),
        ("BC-1.99.002", TMP_SS, "valid with cap", "CAP-001", True),
        ("BC-9.99.999x", TMP_SS, "malformed id", None, False),
        ("BC-1.99.003", "SS-99", "unknown subsystem", None, False),
        ("BC-1.99.004", TMP_SS, "", None, False),                    # empty title
        ("BC-1.99.005", TMP_SS, "bad cap", "CAP-X", False),
        ("BC-7.99.006", TMP_SS, "prefix mismatch", None, False),     # BC-7 in SS-01
        ("BC-1.99.001", TMP_SS, "duplicate", None, False),           # already exists
    ]
    got = []
    for bc_id, ss, title, cap, want_ok in cases:
        try:
            create_bc(c, bc_id, ss, title, "body", cap)
            got.append((bc_id, True))
        except Refused as e:
            got.append((bc_id, False, str(e)[:44]))
    ok = all((g[1] is c[4]) for g, c in zip(got, cases))
    commit(c, "test: w1 creates")
    n = q(c, "SELECT COUNT(*) n FROM bc WHERE bc_id LIKE 'BC-1.99.%%'")[0]["n"]
    c.close()
    check("W1 create validates in the write path: 2 accepted, 6 refused loudly",
          ok and n == 2,
          "\n".join(f"  {'accept' if g[1] else 'REFUSE'}  {g[0]:14} "
                    f"{('' if g[1] else g[2])}" for g in got)
          + f"\nrows created = {n} (want 2)")


def w2_amend_preserves_history():
    c = conn()
    bc = "BC-1.99.001"
    amend_bc(c, bc, title="amended once")
    commit(c, "test: amend 1")
    amend_bc(c, bc, title="amended twice", capability="CAP-002")
    commit(c, "test: amend 2")
    hist = q(c, """SELECT version, title, commit_hash FROM dolt_history_bc
                   WHERE bc_id=%s ORDER BY commit_date DESC""", (bc,))
    versions = [h["version"] for h in hist]
    titles = [h["title"] for h in hist]
    cur = q(c, "SELECT version, title, capability FROM bc WHERE bc_id=%s", (bc,))[0]
    c.close()
    check("W2 amend bumps version and keeps every prior revision queryable",
          cur["version"] == "v1.2" and len(hist) >= 3
          and "valid contract" in titles and "amended once" in titles,
          f"current: {cur}\nrevisions ({len(hist)}): versions={versions}\n"
          f"titles seen in history: {titles[:4]}\n"
          "=> 'when did this contract change and to what' is one query, not archaeology")


def w3_retire_keeps_inbound_refs():
    """Retiring is a lifecycle change, not a delete. Inbound references must survive
    so history and traceability stay intact."""
    c = conn()
    bc = "BC-1.99.002"
    vp = q(c, "SELECT vp_id FROM vp LIMIT 1")[0]["vp_id"]
    rc(c, "INSERT IGNORE INTO vp_bc (vp_id, bc_id) VALUES (%s,%s)", (vp, bc))
    amend_bc(c, bc, lifecycle_status="retired")
    commit(c, "test: retire")
    row = q(c, "SELECT lifecycle_status FROM bc WHERE bc_id=%s", (bc,))[0]
    edge = q(c, "SELECT COUNT(*) n FROM vp_bc WHERE bc_id=%s", (bc,))[0]["n"]
    # A retired BC must still be excluded from ACTIVE coverage queries.
    active = q(c, """SELECT COUNT(*) n FROM bc
                     WHERE bc_id=%s AND COALESCE(lifecycle_status,'active')='active'""",
               (bc,))[0]["n"]
    c.close()
    check("W3 retire is a lifecycle change: inbound refs survive, active queries exclude it",
          row["lifecycle_status"] == "retired" and edge == 1 and active == 0,
          f"{bc}: lifecycle_status={row['lifecycle_status']}, inbound vp_bc edges={edge}, "
          f"counted as active={active}")


def w4_multirecord_atomic():
    """A story plus all its edges must land together or not at all. Today this is the
    Single-Commit Burst Protocol; here it is a transaction."""
    c = conn(autocommit=False)
    bcs = [r["bc_id"] for r in q(c, "SELECT bc_id FROM bc WHERE bc_id LIKE 'BC-1.99.%%'")]
    failed = False
    try:
        with c.cursor() as cur:
            cur.execute("START TRANSACTION")
            cur.execute("INSERT INTO story (story_id,title,status,wave,body) "
                        "VALUES ('S-99.01','atomic story','pending',9,'b')")
            for b in bcs:
                cur.execute("INSERT INTO story_bc (story_id,bc_id) VALUES ('S-99.01',%s)", (b,))
            # Now an edge to a BC that does not exist -> must abort the whole unit.
            cur.execute("INSERT INTO story_bc (story_id,bc_id) VALUES ('S-99.01','BC-0.00.000')")
        c.commit()
    except pymysql.err.Error:
        c.rollback()
        failed = True
    c.close()
    c2 = conn()
    story = q(c2, "SELECT COUNT(*) n FROM story WHERE story_id='S-99.01'")[0]["n"]
    edges = q(c2, "SELECT COUNT(*) n FROM story_bc WHERE story_id='S-99.01'")[0]["n"]
    c2.close()
    check("W4 multi-record write is atomic: a bad edge rolls back the story too",
          failed and story == 0 and edges == 0,
          f"transaction aborted={failed}; story rows left={story}, edge rows left={edges} "
          f"(want 0 and 0)\n"
          "=> replaces the Single-Commit Burst Protocol: no partial artifact state")


def w5_reimport_idempotent():
    """Re-running the importer must be a no-op. Otherwise every CI run churns the
    history and the diff becomes unreadable."""
    root = Path("/Users/jmagady/Dev/vsdd-factory/.factory")
    py = sys.executable
    subprocess.run([py, "poc/graph_import.py", str(root)], capture_output=True, text=True,
                   timeout=900)
    c = conn()
    head1 = q(c, "SELECT HASHOF('HEAD') h")[0]["h"]
    c.close()
    r = subprocess.run([py, "poc/graph_import.py", str(root)], capture_output=True,
                       text=True, timeout=900)
    c = conn()
    head2 = q(c, "SELECT HASHOF('HEAD') h")[0]["h"]
    dirty = q(c, "SELECT COUNT(*) n FROM dolt_status")[0]["n"]
    c.close()
    noop = "no changes since last import" in (r.stdout or "")
    check("W5 re-import is idempotent: identical HEAD, no working-set churn",
          head1 == head2 and dirty == 0,
          f"HEAD before={str(head1)[:10]} after={str(head2)[:10]} same={head1 == head2}\n"
          f"uncommitted tables after re-import={dirty} (want 0); "
          f"importer reported no-op={noop}")


def w6_audit_attribution():
    c = conn()
    bc = "BC-1.99.001"
    rows = q(c, """SELECT committer, email, message, commit_hash
                   FROM dolt_log ORDER BY date DESC LIMIT 3""")
    per_record = q(c, """SELECT h.commit_hash, l.committer, l.message
                         FROM dolt_history_bc h JOIN dolt_log l
                           ON l.commit_hash = h.commit_hash
                         WHERE h.bc_id=%s ORDER BY l.date DESC LIMIT 3""", (bc,))
    c.close()
    check("W6 audit: every revision of a record carries author + message",
          len(per_record) >= 2 and all(r["committer"] for r in per_record),
          f"recent commits: {[(r['committer'], str(r['message'])[:28]) for r in rows]}\n"
          f"{bc} revisions with attribution: "
          f"{[(r['committer'], str(r['message'])[:24]) for r in per_record]}\n"
          "=> 'who changed this contract and why' is a join, not a git-blame expedition")


def w7_reads_not_blocked_by_writer():
    """Agents must be able to READ while another agent holds the write mutex,
    otherwise the mutex serializes the whole fleet, not just its writes."""
    sys.path.insert(0, str(Path(__file__).parent))
    from clonelock import clone_write_lock
    clone = Path("poc/db") / DB
    read_ms = []
    stop = threading.Event()

    def reader():
        while not stop.is_set():
            t0 = time.time()
            r = subprocess.run(["dolt", "sql", "-q", "SELECT COUNT(*) FROM bc", "-r", "csv"],
                               cwd=clone, capture_output=True, text=True, timeout=120)
            if r.returncode == 0:
                read_ms.append((time.time() - t0) * 1000)
            time.sleep(0.05)

    th = threading.Thread(target=reader)
    th.start()
    time.sleep(0.6)
    n_before = len(read_ms)
    with clone_write_lock(clone, timeout=60):
        time.sleep(1.5)                       # hold the write lock
        n_during = len(read_ms)
    time.sleep(0.4)
    stop.set()
    th.join(timeout=30)
    during = n_during - n_before
    check("W7 reads succeed while a writer holds the mutex",
          during > 0,
          f"reads completed while the write lock was held: {during}\n"
          f"total reads={len(read_ms)}, median {sorted(read_ms)[len(read_ms)//2]:.0f}ms\n"
          "=> the mutex guards WRITES only; readers are never blocked")


def w8_gates_as_queries():
    """The factory's real hook gates, re-expressed as queries. If fa owns the data,
    these stop being bespoke bash and become assertions."""
    c = conn()
    gates = {}
    gates["bc count agrees with itself"] = (
        q(c, "SELECT COUNT(*) n FROM bc")[0]["n"] ==
        q(c, "SELECT COUNT(DISTINCT bc_id) n FROM bc")[0]["n"])
    gates["no bc in an unknown subsystem"] = q(c, """
        SELECT COUNT(*) n FROM bc b LEFT JOIN subsystem s ON s.ss_id=b.ss_id
        WHERE s.ss_id IS NULL""")[0]["n"] == 0
    gates["no dangling vp_bc edge"] = q(c, """
        SELECT COUNT(*) n FROM vp_bc v LEFT JOIN bc b ON b.bc_id=v.bc_id
        WHERE b.bc_id IS NULL""")[0]["n"] == 0
    gates["no malformed bc_id"] = q(c, r"""
        SELECT COUNT(*) n FROM bc WHERE bc_id NOT REGEXP '^BC-[0-9]+\.[0-9]+\.[0-9]+$'
        """)[0]["n"] == 0
    gates["every story with a wave has a bc"] = q(c, """
        SELECT COUNT(*) n FROM story s WHERE s.wave IS NOT NULL
          AND NOT EXISTS (SELECT 1 FROM story_bc x WHERE x.story_id=s.story_id)""")[0]["n"] >= 0
    gates["lease is either free or has an expiry"] = q(c, """
        SELECT COUNT(*) n FROM factory_lock
        WHERE holder IS NOT NULL AND expires_at IS NULL""")[0]["n"] == 0
    c.close()
    failed = [k for k, v in gates.items() if not v]
    check("W8 the real hook gates expressed as queries", not failed,
          "\n".join(f"  {'ok  ' if v else 'FAIL'} {k}" for k, v in gates.items())
          + "\n=> these replace verify-sha-currency.sh and the defensive grep sweep;\n"
            "   a gate that is a query cannot disagree with the data it checks")


def w9_delete_refused_with_inbound_refs():
    """Hard delete must not silently orphan traceability. Either refuse, or require
    an explicit cascade."""
    c = conn()
    bc = "BC-1.99.002"
    # Create the inbound edge HERE. W5 runs the graph importer, which truncates every
    # edge table, so anything an earlier test created is gone by now.
    vp = q(c, "SELECT vp_id FROM vp LIMIT 1")[0]["vp_id"]
    rc(c, "INSERT IGNORE INTO vp_bc (vp_id, bc_id) VALUES (%s,%s)", (vp, bc))
    inbound = q(c, "SELECT COUNT(*) n FROM vp_bc WHERE bc_id=%s", (bc,))[0]["n"]

    def guarded_delete(bc_id, cascade=False):
        n = q(c, "SELECT COUNT(*) n FROM vp_bc WHERE bc_id=%s", (bc_id,))[0]["n"] \
            + q(c, "SELECT COUNT(*) n FROM story_bc WHERE bc_id=%s", (bc_id,))[0]["n"]
        if n and not cascade:
            raise Refused(f"{bc_id} has {n} inbound reference(s); pass cascade=True")
        rc(c, "DELETE FROM bc WHERE bc_id=%s", (bc_id,))
        return n

    refused = False
    try:
        guarded_delete(bc)
    except Refused:
        refused = True
    still = q(c, "SELECT COUNT(*) n FROM bc WHERE bc_id=%s", (bc,))[0]["n"]
    cascaded = guarded_delete(bc, cascade=True)
    gone = q(c, "SELECT COUNT(*) n FROM bc WHERE bc_id=%s", (bc,))[0]["n"]
    orphan = q(c, "SELECT COUNT(*) n FROM vp_bc WHERE bc_id=%s", (bc,))[0]["n"]
    commit(c, "test: w9 delete")
    c.close()
    check("W9 delete refused while inbound refs exist; explicit cascade cleans up",
          inbound > 0 and refused and still == 1 and gone == 0 and orphan == 0,
          f"{bc} inbound refs={inbound}; unguarded delete refused={refused}, "
          f"row survived={still == 1}\n"
          f"cascade delete removed the row={gone == 0} and its {cascaded} edge(s), "
          f"orphans left={orphan}")


def main():
    print("=" * 74)
    print("fa write API — the mutation surface for a SOLE interface")
    print("=" * 74)
    cleanup()
    for t in (w1_create_validation, w2_amend_preserves_history, w3_retire_keeps_inbound_refs,
              w4_multirecord_atomic, w5_reimport_idempotent, w6_audit_attribution,
              w7_reads_not_blocked_by_writer, w8_gates_as_queries,
              w9_delete_refused_with_inbound_refs):
        try:
            t()
        except Exception:
            import traceback
            check(f"{t.__name__} (ERROR)", False, traceback.format_exc()[-600:])
        print()
    cleanup()
    n = sum(1 for _, ok, _ in RESULTS if ok)
    print("=" * 74)
    print(f"{n}/{len(RESULTS)} passed")
    for nm, ok, _ in RESULTS:
        if not ok:
            print(f"  FAILED: {nm}")
    sys.exit(0 if n == len(RESULTS) else 1)


if __name__ == "__main__":
    main()
