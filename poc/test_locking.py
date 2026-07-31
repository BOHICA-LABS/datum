#!/usr/bin/env python3
"""Do we still need the factory lock if we adopt Dolt?

The existing lock does TWO different jobs. This suite separates them:

  Job 1 (DATA INTEGRITY): stop two sessions clobbering each other's multi-file
         state writes on the shared orphan branch.
  Job 2 (COORDINATION LEASE): stop a second orchestrator mutating the world
         while a 45-minute wave gate is being evaluated.

Expectations here encode DOCUMENTED Dolt behaviour (see test_cas_patterns.py for
citations): no row locking, cell-level merge, identical writes coalesce.

Run: .venv/bin/python -u poc/test_locking.py
"""
from __future__ import annotations

import secrets
import sys
import threading
import time

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


def setup():
    c = conn()
    with c.cursor() as k:
        # DROP, not CREATE IF NOT EXISTS: an earlier revision of this suite created
        # wave_state without row_lock, and IF NOT EXISTS silently keeps the old
        # shape, so every UPDATE then fails on an unknown column.
        k.execute("DROP TABLE IF EXISTS wave_state")
        k.execute("""CREATE TABLE wave_state (
                       wave INT NOT NULL PRIMARY KEY,
                       gate_status VARCHAR(24) NOT NULL,
                       remediation_sha VARCHAR(64) NULL,
                       row_lock BIGINT NOT NULL DEFAULT 0)""")
        k.execute("DROP TABLE IF EXISTS id_alloc")
        k.execute("""CREATE TABLE id_alloc (
                       ns VARCHAR(16) NOT NULL, seq INT NOT NULL,
                       owner VARCHAR(48) NOT NULL,
                       PRIMARY KEY (ns, seq))""")
        k.execute("DELETE FROM wave_state")
        k.execute("INSERT INTO wave_state (wave,gate_status) VALUES (1,'pending')")
        k.execute("INSERT INTO pipeline_state (k,v) VALUES ('phase','3') "
                  "ON DUPLICATE KEY UPDATE v='3'")
        k.execute("INSERT INTO phase (phase_id,status) VALUES ('phase-3','in_progress') "
                  "ON DUPLICATE KEY UPDATE status='in_progress'")
    c.close()


# ------------------------------------------------------------------ Job 1


def l1_multitable_atomicity():
    """The Single-Commit Burst Protocol exists because STATE.md + SESSION-HANDOFF.md
    + wave-state.yaml must move together and git can only do that by choreography.
    A transaction does it by definition."""
    c = conn(autocommit=False)
    committed = False
    try:
        with c.cursor() as cur:
            cur.execute("START TRANSACTION")
            cur.execute("UPDATE pipeline_state SET v='4' WHERE k='phase'")
            cur.execute("UPDATE phase SET status='PASSED' WHERE phase_id='phase-3'")
            cur.execute("UPDATE wave_state SET gate_status='passed' WHERE wave=1")
            # A real mid-burst failure (NOT 1/0 — Dolt returns NULL for that).
            cur.execute("INSERT INTO phase (phase_id,status) VALUES ('phase-3','dup')")
        c.commit()
        committed = True
    except pymysql.err.Error:
        c.rollback()
    c.close()

    # Read from a FRESH connection: the same connection would see its own
    # uncommitted writes and fake a pass.
    c2 = conn()
    after = (q(c2, "SELECT v FROM pipeline_state WHERE k='phase'")[0]["v"],
             q(c2, "SELECT status FROM phase WHERE phase_id='phase-3'")[0]["status"],
             q(c2, "SELECT gate_status FROM wave_state WHERE wave=1")[0]["gate_status"])
    c2.close()
    check("L1 multi-table burst is atomic: mid-burst failure rolls back ALL of it",
          not committed and after == ("3", "in_progress", "pending"),
          f"burst committed={committed} (want False)\n"
          f"state seen from a fresh connection = {after} (want ('3','in_progress','pending'))\n"
          "=> replaces the Single-Commit Burst Protocol and its 8 cite locations")


def l2_no_row_locking():
    """DOCUMENTED: 'Row-level locks are not supported.' SELECT ... FOR UPDATE
    parses but acquires nothing. Asserting the DOCUMENTED behaviour so the suite
    fails loudly if a future Dolt changes it."""
    c = conn()
    q(c, "UPDATE wave_state SET gate_status='pending' WHERE wave=1")
    c.close()
    order: list[str] = []

    def holder():
        cx = conn(autocommit=False)
        try:
            with cx.cursor() as cur:
                cur.execute("START TRANSACTION")
                cur.execute("SELECT gate_status FROM wave_state WHERE wave=1 FOR UPDATE")
                cur.fetchall()
                order.append("holder:locked")
                time.sleep(1.2)
            cx.commit()
            order.append("holder:committed")
        except pymysql.err.Error as e:
            order.append(f"holder:err{e.args[0]}")
        finally:
            cx.close()

    def waiter():
        time.sleep(0.4)
        cx = conn(autocommit=False)
        try:
            with cx.cursor() as cur:
                cur.execute("START TRANSACTION")
                cur.execute("SELECT gate_status FROM wave_state WHERE wave=1 FOR UPDATE")
                cur.fetchall()
                order.append("waiter:acquired")
            cx.commit()
        except pymysql.err.Error as e:
            order.append(f"waiter:err{e.args[0]}")
        finally:
            cx.close()

    th, tw = threading.Thread(target=holder), threading.Thread(target=waiter)
    th.start(); tw.start(); th.join(); tw.join()
    not_blocked = "waiter:acquired" in order and order.index("waiter:acquired") < \
        (order.index("holder:committed") if "holder:committed" in order else 99)
    check("L2 FOR UPDATE does NOT block (documented: no row-level locks)",
          not_blocked,
          f"event order: {order}\n"
          "docs.dolthub.com/sql-reference/sql-support/supported-statements:\n"
          "  'Row-level locks are not supported.'  LOCK TABLES also parses but is a no-op.\n"
          "=> pessimistic locking is unavailable; use a unique-token CAS or GET_LOCK")


def l3_safe_cas_transition():
    """The SAFE guarded write: the value written must be UNIQUE PER ATTEMPT so
    contenders collide on the same cell. (A shared constant or fence+1 merges —
    see test_cas_patterns.py P1/P2.)"""
    c = conn()
    q(c, "UPDATE wave_state SET gate_status='pending' WHERE wave=1")
    c.close()
    won: list[str] = []
    lk = threading.Lock()
    bar = threading.Barrier(6)

    def agent(tag):
        cx = conn()
        try:
            with cx.cursor() as k:
                bar.wait()
                k.execute("""UPDATE wave_state
                             SET gate_status='passed', remediation_sha=%s, row_lock=%s
                             WHERE wave=1 AND gate_status='pending'""",
                          (tag, secrets.randbits(62) | 1))
                if k.rowcount == 1:
                    with lk:
                        won.append(tag)
        except pymysql.err.Error:
            pass
        finally:
            cx.close()

    ts = [threading.Thread(target=agent, args=(f"a{i}",)) for i in range(6)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    c = conn()
    fin = q(c, "SELECT gate_status, remediation_sha FROM wave_state WHERE wave=1")[0]
    c.close()
    check("L3 CAS with a per-attempt unique token: exactly one agent transitions the gate",
          len(won) == 1, f"winners={won}  final={fin}")


def l4_id_allocation_needs_a_token():
    """'Allocate the next id' — the classic reason people reach for a global lock.
    A PRIMARY KEY alone is NOT enough: two transactions inserting BYTE-IDENTICAL
    rows merge without conflict. Including a per-attempt unique column fixes it."""
    def attempt(naive: bool):
        c = conn()
        q(c, "DELETE FROM id_alloc")
        c.close()
        got: list[int] = []
        lk = threading.Lock()
        bar = threading.Barrier(6)

        def alloc(i):
            cx = conn()
            try:
                bar.wait()
                for _ in range(15):
                    nxt = q(cx, "SELECT COALESCE(MAX(seq),0)+1 AS n FROM id_alloc "
                                "WHERE ns='BC'")[0]["n"]
                    owner = "SHARED" if naive else f"w{i}-{secrets.token_hex(4)}"
                    try:
                        rc(cx, "INSERT INTO id_alloc (ns,seq,owner) VALUES ('BC',%s,%s)",
                           (nxt, owner))
                        with lk:
                            got.append(nxt)
                        return
                    except pymysql.err.Error as e:
                        if e.args[0] in (1062, 1022, 1213, 1205):
                            continue
                        raise
            finally:
                cx.close()

        ts = [threading.Thread(target=alloc, args=(i,)) for i in range(6)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        c = conn()
        stored = q(c, "SELECT COUNT(*) n FROM id_alloc")[0]["n"]
        c.close()
        return sorted(got), stored

    naive, naive_rows = attempt(True)
    toked, toked_rows = attempt(False)
    naive_dupes = len(naive) - len(set(naive))
    toked_dupes = len(toked) - len(set(toked))
    check("L4 ID allocation: PK alone is insufficient; a per-attempt unique column fixes it",
          naive_dupes > 0 and toked_dupes == 0 and toked_rows == 6,
          f"identical-row inserts : allocated={naive} duplicates={naive_dupes} "
          f"rows_stored={naive_rows}\n"
          f"unique-token inserts  : allocated={toked} duplicates={toked_dupes} "
          f"rows_stored={toked_rows}\n"
          "=> 'two transactions inserting byte-for-byte identical rows can merge\n"
          "   without conflict' — so an allocator must carry a unique owner token")


# ------------------------------------------------------------------ Job 2


def l5_get_lock_is_real():
    """GET_LOCK is a real session-scoped advisory lock in go-mysql-server's
    LockSubsystem — not a stub. It is the clean way to serialize a critical
    section without depending on merge semantics."""
    c1, c2 = conn(), conn()
    got1 = q(c1, "SELECT GET_LOCK('factory', 0) AS g")[0]["g"]
    got2 = q(c2, "SELECT GET_LOCK('factory', 0) AS g")[0]["g"]
    q(c1, "SELECT RELEASE_LOCK('factory')")
    got3 = q(c2, "SELECT GET_LOCK('factory', 0) AS g")[0]["g"]
    q(c2, "SELECT RELEASE_LOCK('factory')")
    # It is SESSION scoped: closing the holder's connection frees it.
    c3, c4 = conn(), conn()
    q(c3, "SELECT GET_LOCK('factory2', 0)")
    blocked = q(c4, "SELECT GET_LOCK('factory2', 0) AS g")[0]["g"]
    c3.close()                      # holder disconnects
    time.sleep(0.3)
    after_disconnect = q(c4, "SELECT GET_LOCK('factory2', 0) AS g")[0]["g"]
    q(c4, "SELECT RELEASE_LOCK('factory2')")
    c1.close(); c2.close(); c4.close()
    check("L5 GET_LOCK is a real advisory lock, and it dies with the session",
          got1 == 1 and got2 == 0 and got3 == 1 and blocked == 0 and after_disconnect == 1,
          f"excludes across connections: acquire={got1}, while-held={got2}, after-release={got3}\n"
          f"session-scoped: while-held={blocked}, after holder DISCONNECTED={after_disconnect}\n"
          "=> good for a short critical section; UNUSABLE as a 45-min cross-session lease")


def l6_long_lease_must_be_a_row():
    """The residual Job-2 case: a 45-minute wave gate cannot be a transaction or
    a GET_LOCK (both die with the session). It must be application state."""
    c = conn()
    q(c, "UPDATE factory_lock SET holder=NULL, expires_at=NULL WHERE id=1")
    n1 = rc(c, """UPDATE factory_lock SET holder='orchestrator-A',
                  expires_at=DATE_ADD(NOW(), INTERVAL 2700 SECOND)
                  WHERE id=1 AND (holder IS NULL OR expires_at < NOW())""")
    c.close()                                   # A's connection goes away
    c2 = conn()
    n2 = rc(c2, """UPDATE factory_lock SET holder='orchestrator-B',
                   expires_at=DATE_ADD(NOW(), INTERVAL 2700 SECOND)
                   WHERE id=1 AND (holder IS NULL OR expires_at < NOW())""")
    still = q(c2, "SELECT holder FROM factory_lock WHERE id=1")[0]["holder"]
    rc(c2, "UPDATE factory_lock SET holder=NULL, expires_at=NULL WHERE id=1")
    c2.close()
    check("L6 a 45-min lease must be a ROW: it survives disconnect, unlike GET_LOCK",
          n1 == 1 and n2 == 0 and still == "orchestrator-A",
          f"A acquired={n1==1}; A disconnected; B refused={n2==0}; holder still={still}\n"
          "=> the coordination lease genuinely survives Dolt adoption — but as an\n"
          "   ADVISORY row lease, not as the write-serializing mechanism it is today")


def main():
    print("=" * 74)
    print("Is the factory lock still needed under Dolt?")
    print("=" * 74)
    setup()
    for t in (l1_multitable_atomicity, l2_no_row_locking, l3_safe_cas_transition,
              l4_id_allocation_needs_a_token, l5_get_lock_is_real,
              l6_long_lease_must_be_a_row):
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
