#!/usr/bin/env python3
"""Information-asymmetry walls — can they survive a single artifact store?

THE COLLISION. VSDD's method depends on agents being structurally unable to see
certain artifacts:

  holdout-evaluator: "CANNOT access .factory/specs/, src/ internals,
                      .factory/cycles/*/adversarial-reviews/"
  adversary:         "Cannot see prior review passes ... Read-only access enforces
                      both constraints STRUCTURALLY"
  code-reviewer:     "You CANNOT see ... (enforced by Lobster context exclusion)"

Today the wall is PATH-BASED: deny `.factory/specs/`, allow
`.factory/holdout-scenarios/`. If every artifact becomes a row in one queryable
database, path exclusion has nothing to bite on and the wall collapses.

Options tested:
  A1  server-less, one database  -> is any restriction possible? (expected NO)
  A2  does one data-dir leak sibling databases via SHOW DATABASES / cross-db query?
  A3  separate database DIRECTORIES as trust zones -> path exclusion still works
  A4  server + CREATE USER/GRANT  -> real DB-level restriction
  A5  can a restricted user still reach walled data via Dolt system tables
      (dolt_history_*, dolt_diff_*, dolt_log)? -- the sneaky path
  A6  cross-zone referential integrity: what do we LOSE by splitting zones?

Run: .venv/bin/python -u poc/test_asymmetry.py
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import time
from pathlib import Path

import pymysql

ROOT = Path(__file__).parent / "asym"
PORT = 3499
RESULTS: list[tuple[str, bool, str]] = []
SERVERS: list[subprocess.Popen] = []


def check(name, ok, detail=""):
    RESULTS.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}")
    for ln in (detail or "").splitlines():
        print(f"        {ln}")


def sh(args, cwd, timeout=180):
    try:
        return subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(args, 124, "", "TIMEOUT")


def csv_out(r):
    lines = [l for l in (r.stdout or "").strip().splitlines() if l.strip()]
    if len(lines) < 2:
        return []
    return [dict(zip(lines[0].split(","), l.split(","))) for l in lines[1:]]


def setup():
    print("--- setup: two trust zones as separate Dolt databases")
    if ROOT.exists():
        shutil.rmtree(ROOT)
    # Zone OPEN: specs the implementer may read.
    # Zone WALLED: holdout scenarios + adversarial reviews the evaluator must not read.
    for zone, stmts in (
        ("open", ["CREATE TABLE bc (bc_id VARCHAR(24) PRIMARY KEY, title TEXT NOT NULL)",
                  "INSERT INTO bc VALUES ('BC-1.01.001','public contract')"]),
        ("walled", ["CREATE TABLE holdout_scenario (hs_id VARCHAR(16) PRIMARY KEY, "
                    "secret TEXT NOT NULL)",
                    "INSERT INTO holdout_scenario VALUES ('HS-001','SECRET-EXPECTATION')",
                    "CREATE TABLE adversarial_finding (id VARCHAR(16) PRIMARY KEY, "
                    "finding TEXT NOT NULL)",
                    "INSERT INTO adversarial_finding VALUES ('ADV-001','SECRET-FINDING')"]),
    ):
        d = ROOT / "zones" / zone
        d.mkdir(parents=True)
        sh(["dolt", "init", "--name", "z", "--email", "z@l"], cwd=d)
        for s in stmts:
            sh(["dolt", "sql", "-q", s], cwd=d)
        sh(["dolt", "add", "-A"], cwd=d)
        sh(["dolt", "commit", "-m", f"seed {zone}"], cwd=d)

    # A single combined database, for the "one store" comparison.
    comb = ROOT / "combined"
    comb.mkdir(parents=True)
    sh(["dolt", "init", "--name", "z", "--email", "z@l"], cwd=comb)
    for s in ["CREATE TABLE bc (bc_id VARCHAR(24) PRIMARY KEY, title TEXT NOT NULL)",
              "INSERT INTO bc VALUES ('BC-1.01.001','public contract')",
              "CREATE TABLE holdout_scenario (hs_id VARCHAR(16) PRIMARY KEY, secret TEXT NOT NULL)",
              "INSERT INTO holdout_scenario VALUES ('HS-001','SECRET-EXPECTATION')",
              "CREATE TABLE adversarial_finding (id VARCHAR(16) PRIMARY KEY, finding TEXT NOT NULL)",
              "INSERT INTO adversarial_finding VALUES ('ADV-001','SECRET-FINDING')"]:
        sh(["dolt", "sql", "-q", s], cwd=comb)
    sh(["dolt", "add", "-A"], cwd=comb)
    sh(["dolt", "commit", "-m", "seed combined"], cwd=comb)
    print(f"    zones/open, zones/walled, combined  under {ROOT}\n")


def teardown():
    for p in SERVERS:
        p.terminate()
    for p in SERVERS:
        try:
            p.wait(timeout=15)
        except subprocess.TimeoutExpired:
            p.kill()


# ---------------------------------------------------------------- tests


def a1_serverless_one_db_has_no_wall():
    """In the recommended server-less topology, filesystem read access to the clone
    IS full read access to every artifact. There is no restriction to configure."""
    comb = ROOT / "combined"
    r = sh(["dolt", "sql", "-q", "SELECT secret FROM holdout_scenario", "-r", "csv"], cwd=comb)
    leaked = "SECRET-EXPECTATION" in (r.stdout or "")
    r2 = sh(["dolt", "sql", "-q", "SELECT finding FROM adversarial_finding", "-r", "csv"],
            cwd=comb)
    leaked2 = "SECRET-FINDING" in (r2.stdout or "")
    tables = [d.get("Table") or list(d.values())[0]
              for d in csv_out(sh(["dolt", "sql", "-q", "SHOW TABLES", "-r", "csv"], cwd=comb))]
    check("A1 server-less + ONE database: no wall is possible (expected, and it matters)",
          leaked and leaked2,
          f"SHOW TABLES reveals: {tables}\n"
          f"holdout secret readable = {leaked}; adversarial finding readable = {leaked2}\n"
          "=> `dolt sql` needs only filesystem access. Any agent that can run it reads\n"
          "   EVERYTHING. The path-based wall the factory relies on has nothing to bite\n"
          "   on once artifacts are rows in one database.")


def a2_datadir_leaks_siblings():
    """If trust zones are separate databases under ONE data-dir, does one leak the
    other? This decides whether 'separate database' is a real boundary."""
    zones = ROOT / "zones"
    r = sh(["dolt", "--data-dir", str(zones), "sql", "-q", "SHOW DATABASES", "-r", "csv"],
           cwd=ROOT)
    dbs = [list(d.values())[0] for d in csv_out(r)]
    both_visible = "open" in dbs and "walled" in dbs
    x = sh(["dolt", "--data-dir", str(zones), "sql", "-q",
            "SELECT secret FROM walled.holdout_scenario", "-r", "csv"], cwd=ROOT)
    cross = "SECRET-EXPECTATION" in (x.stdout or "")
    check("A2 a shared --data-dir DOES expose sibling databases (cross-db query works)",
          both_visible and cross,
          f"SHOW DATABASES with --data-dir=zones/: {dbs}\n"
          f"cross-database query `SELECT ... FROM walled.holdout_scenario` succeeded = {cross}\n"
          "=> 'separate database' is NOT a boundary if both live under one data-dir.\n"
          "   Zones must be separate DIRECTORIES that the agent's tool profile cannot\n"
          "   reach — i.e. the boundary stays FILESYSTEM-shaped.")


def a3_separate_directories_are_a_real_boundary():
    """Point Dolt at ONE zone directory only. The other must be unreachable."""
    open_d = ROOT / "zones" / "open"
    ok_read = sh(["dolt", "sql", "-q", "SELECT title FROM bc", "-r", "csv"], cwd=open_d)
    can_see_own = "public contract" in (ok_read.stdout or "")
    # Try to reach the walled zone from inside the open zone.
    t1 = sh(["dolt", "sql", "-q", "SELECT secret FROM holdout_scenario", "-r", "csv"], cwd=open_d)
    t2 = sh(["dolt", "sql", "-q", "SELECT secret FROM walled.holdout_scenario", "-r", "csv"],
            cwd=open_d)
    t3 = sh(["dolt", "sql", "-q", "SHOW DATABASES", "-r", "csv"], cwd=open_d)
    dbs = [list(d.values())[0] for d in csv_out(t3)]
    blocked = ("SECRET-EXPECTATION" not in (t1.stdout or "")
               and "SECRET-EXPECTATION" not in (t2.stdout or "")
               and "walled" not in dbs)
    check("A3 separate zone DIRECTORIES are a real boundary (path exclusion still works)",
          can_see_own and blocked,
          f"own zone readable = {can_see_own}\n"
          f"unqualified walled table: rc={t1.returncode} leaked={'SECRET' in (t1.stdout or '')}\n"
          f"qualified walled.table  : rc={t2.returncode} leaked={'SECRET' in (t2.stdout or '')}\n"
          f"SHOW DATABASES from the open zone: {dbs}\n"
          "=> KEEPS the factory's existing enforcement mechanism intact: deny the agent\n"
          "   the walled DIRECTORY, exactly as it denies `.factory/specs/` today.")


def a4_server_grants():
    """With a server, real DB-level auth is available. Verify GRANT actually denies."""
    comb = ROOT / "combined"
    log = open(ROOT / "srv.log", "w")
    SERVERS.append(subprocess.Popen(
        ["dolt", "sql-server", "--host", "127.0.0.1", "--port", str(PORT)],
        cwd=comb, stdout=log, stderr=log))
    up = False
    for _ in range(60):
        try:
            c = pymysql.connect(host="127.0.0.1", port=PORT, user="root")
            c.close()
            up = True
            break
        except Exception:                       # noqa: BLE001
            time.sleep(0.5)
    if not up:
        return check("A4 server + GRANT restricts table access", False, "server never started")

    root = pymysql.connect(host="127.0.0.1", port=PORT, user="root", autocommit=True,
                           cursorclass=pymysql.cursors.DictCursor)
    dbname = "combined"
    with root.cursor() as k:
        k.execute("SELECT DATABASE() d")
        try:
            k.execute("DROP USER IF EXISTS 'evaluator'@'%'")
        except pymysql.err.Error:
            pass
        k.execute("CREATE USER 'evaluator'@'%' IDENTIFIED BY 'pw'")
        # Grant ONLY the walled table the evaluator is allowed to see.
        k.execute(f"GRANT SELECT ON `{dbname}`.`holdout_scenario` TO 'evaluator'@'%'")
    root.close()

    ev = pymysql.connect(host="127.0.0.1", port=PORT, user="evaluator", password="pw",
                         database=dbname, autocommit=True,
                         cursorclass=pymysql.cursors.DictCursor)
    allowed, denied_specs, denied_adv = False, False, False
    notes = []
    with ev.cursor() as k:
        try:
            k.execute("SELECT secret FROM holdout_scenario")
            allowed = "SECRET-EXPECTATION" in str(k.fetchall())
        except pymysql.err.Error as e:
            notes.append(f"holdout read failed: {str(e)[:60]}")
        for tbl, flag in (("bc", "specs"), ("adversarial_finding", "adv")):
            try:
                k.execute(f"SELECT * FROM {tbl}")
                k.fetchall()
                notes.append(f"LEAKED {tbl}")
            except pymysql.err.Error as e:
                notes.append(f"{tbl} denied ({e.args[0]})")
                if flag == "specs":
                    denied_specs = True
                else:
                    denied_adv = True
    ev.close()
    check("A4 server + GRANT gives a real, table-level wall",
          allowed and denied_specs and denied_adv,
          f"evaluator CAN read holdout_scenario = {allowed}\n"
          f"evaluator DENIED bc (specs) = {denied_specs}; DENIED adversarial_finding = "
          f"{denied_adv}\n  " + "; ".join(notes) + "\n"
          "=> a shared server BUYS BACK the wall that server-less cannot enforce.\n"
          "   That is a real argument for the server topology, against §3d/§3e.")


def a5_system_tables_backdoor():
    """The sneaky path: even if a table is denied, can a restricted user reach the
    same data through Dolt's system tables (dolt_history_*, dolt_diff_*, dolt_log)?"""
    dbname = "combined"
    ev = pymysql.connect(host="127.0.0.1", port=PORT, user="evaluator", password="pw",
                         database=dbname, autocommit=True,
                         cursorclass=pymysql.cursors.DictCursor)
    probes = {
        "dolt_history_bc": "SELECT * FROM dolt_history_bc LIMIT 1",
        "dolt_diff_bc": "SELECT * FROM dolt_diff_bc LIMIT 1",
        "dolt_log (messages)": "SELECT message FROM dolt_log LIMIT 3",
        "dolt_history_adversarial_finding":
            "SELECT * FROM dolt_history_adversarial_finding LIMIT 1",
    }
    leaks, denials = [], []
    with ev.cursor() as k:
        for name, sql in probes.items():
            try:
                k.execute(sql)
                rows = k.fetchall()
                blob = str(rows)
                if "public contract" in blob or "SECRET-FINDING" in blob:
                    leaks.append(f"{name} LEAKED DATA")
                else:
                    leaks.append(f"{name} readable ({len(rows)} rows, no walled payload)")
            except pymysql.err.Error as e:
                denials.append(f"{name} denied ({e.args[0]})")
    ev.close()
    hard_leak = [x for x in leaks if "LEAKED DATA" in x]
    check("A5 system tables are NOT a backdoor around GRANTs",
          not hard_leak,
          "denials:\n  " + ("\n  ".join(denials) or "(none)")
          + "\nreadable:\n  " + ("\n  ".join(leaks) or "(none)")
          + "\n=> if any dolt_history_*/dolt_diff_* view returned walled payload, the\n"
            "   GRANT wall would be cosmetic. This is the check that decides whether\n"
            "   table-level grants are trustworthy for VSDD's method.")


def a6_cost_of_splitting_zones():
    """What do we LOSE by splitting trust zones into separate databases? Referential
    integrity cannot span them — a holdout scenario cannot FK to a BC."""
    walled = ROOT / "zones" / "walled"
    r = sh(["dolt", "sql", "-q",
            "ALTER TABLE holdout_scenario ADD COLUMN bc_id VARCHAR(24) NULL, "
            "ADD CONSTRAINT fk_hs_bc FOREIGN KEY (bc_id) REFERENCES open.bc (bc_id)"],
           cwd=walled)
    cross_fk_ok = r.returncode == 0
    # A same-database FK works, for contrast.
    comb = ROOT / "combined"
    r2 = sh(["dolt", "sql", "-q",
             "ALTER TABLE holdout_scenario ADD COLUMN bc_id VARCHAR(24) NULL, "
             "ADD CONSTRAINT fk_hs_bc2 FOREIGN KEY (bc_id) REFERENCES bc (bc_id)"], cwd=comb)
    same_fk_ok = r2.returncode == 0
    check("A6 splitting zones costs cross-zone referential integrity",
          not cross_fk_ok and same_fk_ok,
          f"cross-database FK (walled -> open): rc={r.returncode} allowed={cross_fk_ok}\n"
          f"  {(r.stderr or r.stdout or '').strip()[:110]}\n"
          f"same-database FK: rc={r2.returncode} allowed={same_fk_ok}\n"
          "=> the price of a filesystem-shaped wall: a holdout scenario cannot FK to the\n"
          "   BC it verifies, so THAT link reverts to being validated by tooling rather\n"
          "   than by the database. A real, bounded trade -- not a blocker.")


def main():
    print("=" * 74)
    print("Information-asymmetry walls vs a single artifact store")
    print("=" * 74)
    try:
        setup()
        for t in (a1_serverless_one_db_has_no_wall, a2_datadir_leaks_siblings,
                  a3_separate_directories_are_a_real_boundary, a4_server_grants,
                  a5_system_tables_backdoor, a6_cost_of_splitting_zones):
            try:
                t()
            except Exception:
                import traceback
                check(f"{t.__name__} (ERROR)", False, traceback.format_exc()[-500:])
            print()
    finally:
        teardown()
    n = sum(1 for _, ok, _ in RESULTS if ok)
    print("=" * 74)
    print(f"{n}/{len(RESULTS)} passed")
    for nm, ok, _ in RESULTS:
        if not ok:
            print(f"  FAILED: {nm}")
    sys.exit(0 if n == len(RESULTS) else 1)


if __name__ == "__main__":
    main()
