#!/usr/bin/env python3
"""Which mutual-exclusion pattern actually holds on Dolt? (definitive)

Dolt has NO row locking and merges concurrent commits CELL BY CELL. Two
consequences, both documented by DoltHub:

  (a) "if all contenders wrote the same col=x, Dolt sees 'same cell changed to
      the same value', which is mergeable; all commits can succeed and all
      clients can receive affected_rows=1"
      -- https://www.dolthub.com/blog/2023-12-14-concurrent-transaction-example/
      -- https://www.dolthub.com/blog/2026-02-17-dolt-concurrency/

  (b) "Do not use row_lock = row_lock + 1 as the conflict token: concurrent
      snapshots can calculate the same next value, which Dolt regards as the
      same change and merges successfully."
      -- https://www.dolthub.com/blog/2021-05-19-dolt-transactions/

  Docs: "Row-level locks are not supported."
      -- https://docs.dolthub.com/sql-reference/sql-support/supported-statements
  Issue #7681 calls current conflict detection "too lenient" and proposes an
  UNIMPLEMENTED strict "No row merge" mode.
  beads (production) names the bug the "zombie-merge bug" and fixes it with a
  random row_lock cell + retry (internal/storage/issueops/lease.go).

So the ONLY safe patterns write a value that is UNIQUE PER ATTEMPT into a cell
every contender touches, or bypass merge semantics via GET_LOCK.

A pattern is SAFE only if EVERY trial yields exactly one winner.

Run: .venv/bin/python -u poc/test_cas_patterns.py     (TRIALS=n to change depth)
"""
from __future__ import annotations

import os
import secrets
import sys
import threading

import pymysql

PORT, DB = 3308, "factory_artifacts"
TRIALS = int(os.environ.get("TRIALS", 25))
WRITERS = int(os.environ.get("WRITERS", 4))
RESULTS: list[tuple[str, bool, str]] = []


def conn(autocommit=True):
    return pymysql.connect(host="127.0.0.1", port=PORT, user="root", database=DB,
                           autocommit=autocommit, cursorclass=pymysql.cursors.DictCursor)


def check(name, ok, detail=""):
    RESULTS.append((name, ok, detail))
    print(f"{'SAFE  ' if ok else 'UNSAFE'}  {name}")
    for ln in (detail or "").splitlines():
        print(f"          {ln}")


def setup():
    c = conn()
    with c.cursor() as k:
        k.execute("DROP TABLE IF EXISTS cas_gate")
        k.execute("""CREATE TABLE cas_gate (
                       id TINYINT NOT NULL PRIMARY KEY,
                       status   VARCHAR(16) NOT NULL,
                       holder   VARCHAR(40) NULL,
                       fence    BIGINT NOT NULL DEFAULT 0,
                       row_lock BIGINT NOT NULL DEFAULT 0)""")
    c.close()


def reset():
    c = conn()
    with c.cursor() as k:
        k.execute("DELETE FROM cas_gate")
        k.execute("INSERT INTO cas_gate (id,status,holder,fence,row_lock) "
                  "VALUES (1,'pending',NULL,0,0)")
    c.close()


def run(pattern, label, note=""):
    """pattern(tag, barrier, token) -> (believes_it_won, outcome_note)"""
    hist: dict[int, int] = {}
    bad: list[list[str]] = []
    for _ in range(TRIALS):
        reset()
        c = conn()
        with c.cursor() as k:
            k.execute("SELECT row_lock FROM cas_gate WHERE id=1")
            old_token = k.fetchone()["row_lock"]
        c.close()

        won: list[str] = []
        out: list[str] = []
        lk = threading.Lock()
        bar = threading.Barrier(WRITERS)

        def worker(i):
            tag = f"w{i}"
            try:
                ok, n = pattern(tag, bar, old_token)
            except Exception as e:                                    # noqa: BLE001
                ok, n = False, f"raise:{type(e).__name__}"
            with lk:
                out.append(f"{tag}={n}")
                if ok:
                    won.append(tag)

        ts = [threading.Thread(target=worker, args=(i,)) for i in range(WRITERS)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        hist[len(won)] = hist.get(len(won), 0) + 1
        if len(won) != 1 and len(bad) < 2:
            bad.append(sorted(out))

    ok = hist.get(1, 0) == TRIALS
    d = f"winners/trial over {TRIALS} trials x {WRITERS} writers: {dict(sorted(hist.items()))}"
    if note:
        d += f"\n{note}"
    for b in bad:
        d += f"\n  bad trial: {b}"
    check(label, ok, d)


# ------------------------------------------------------- unsafe patterns


def p1_same_value_guard():
    """Documented lost update: every contender writes the SAME cell values, so
    Dolt coalesces them as 'same change' and they all succeed."""
    def pat(tag, bar, tok):
        cx = conn()
        try:
            with cx.cursor() as k:
                bar.wait()
                k.execute("UPDATE cas_gate SET status='passed', holder='SHARED' "
                          "WHERE id=1 AND status='pending'")
                return k.rowcount == 1, f"rows={k.rowcount}"
        except pymysql.err.Error as e:
            return False, f"e{e.args[0]}"
        finally:
            cx.close()
    run(pat, "P1 guarded UPDATE, contenders write IDENTICAL values",
        "expected UNSAFE: identical cell writes are mergeable, so all can report rows=1")


def p2_fence_increment():
    """The pattern used by this spike's ORIGINAL factory-lock test (fence=fence+1).
    DoltHub explicitly warns against it: concurrent snapshots compute the SAME
    next value, which merges."""
    def pat(tag, bar, tok):
        cx = conn()
        try:
            with cx.cursor() as k:
                bar.wait()
                k.execute("UPDATE cas_gate SET status='passed', fence=fence+1 "
                          "WHERE id=1 AND status='pending'")
                return k.rowcount == 1, f"rows={k.rowcount}"
        except pymysql.err.Error as e:
            return False, f"e{e.args[0]}"
        finally:
            cx.close()
    run(pat, "P2 guarded UPDATE + fence=fence+1  (this spike's original lock)",
        "DoltHub: 'Do not use row_lock = row_lock + 1 as the conflict token'")


# --------------------------------------------------------- safe patterns


def p3_unique_holder_value():
    """Each contender writes its OWN distinct holder value, so same-cell writes
    differ and Dolt raises a conflict for the losers."""
    def pat(tag, bar, tok):
        cx = conn()
        try:
            with cx.cursor() as k:
                bar.wait()
                k.execute("UPDATE cas_gate SET status='passed', holder=%s "
                          "WHERE id=1 AND status='pending'", (tag,))
                return k.rowcount == 1, f"rows={k.rowcount}"
        except pymysql.err.Error as e:
            return False, f"e{e.args[0]}"
        finally:
            cx.close()
    run(pat, "P3 guarded UPDATE writing a per-attempt UNIQUE value")


def p4_random_row_lock_token():
    """DoltHub's documented shape:
         UPDATE t SET col=?, row_lock=<fresh random> WHERE id=? AND row_lock=<old>
       The guard is the token itself, so the CAS does not depend on a business
       column, and the fresh random token guarantees a same-cell collision."""
    def pat(tag, bar, tok):
        cx = conn()
        try:
            with cx.cursor() as k:
                bar.wait()
                k.execute("UPDATE cas_gate SET status='passed', holder=%s, row_lock=%s "
                          "WHERE id=1 AND row_lock=%s",
                          (tag, secrets.randbits(62) | 1, tok))
                return k.rowcount == 1, f"rows={k.rowcount}"
        except pymysql.err.Error as e:
            return False, f"e{e.args[0]}"
        finally:
            cx.close()
    run(pat, "P4 row_lock token guard + fresh random token (DoltHub / beads pattern)")


def p5_get_lock_mutex():
    """GET_LOCK is a REAL session-scoped advisory lock in go-mysql-server's
    LockSubsystem — it sidesteps merge semantics entirely. Must be acquired,
    used, and released on ONE pinned connection."""
    def pat(tag, bar, tok):
        cx = conn()
        try:
            with cx.cursor() as k:
                bar.wait()
                k.execute("SELECT GET_LOCK('cas_gate:1', 10) AS g")
                if k.fetchone()["g"] != 1:
                    return False, "lock-timeout"
                try:
                    k.execute("SELECT status FROM cas_gate WHERE id=1")
                    if k.fetchone()["status"] != "pending":
                        return False, "guard-lost"
                    k.execute("UPDATE cas_gate SET status='passed', holder=%s WHERE id=1", (tag,))
                    return True, "won"
                finally:
                    k.execute("SELECT RELEASE_LOCK('cas_gate:1')")
                    k.fetchall()
        except pymysql.err.Error as e:
            return False, f"e{e.args[0]}"
        finally:
            cx.close()
    run(pat, "P5 GET_LOCK() advisory mutex on a pinned connection")


def main():
    print("=" * 78)
    print(f"Dolt CAS pattern comparison  ({TRIALS} trials x {WRITERS} concurrent writers)")
    print("=" * 78)
    setup()
    for t in (p1_same_value_guard, p2_fence_increment, p3_unique_holder_value,
              p4_random_row_lock_token, p5_get_lock_mutex):
        try:
            t()
        except Exception:
            import traceback
            check(f"{t.__name__} (ERROR)", False, traceback.format_exc()[-400:])
        print()
    print("=" * 78)
    for nm, ok, _ in RESULTS:
        print(f"  {'SAFE  ' if ok else 'UNSAFE'}  {nm}")
    sys.exit(0)


if __name__ == "__main__":
    main()
