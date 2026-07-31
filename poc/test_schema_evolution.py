#!/usr/bin/env python3
"""Schema evolution — because the spec schema WILL change.

New frontmatter fields, new artifact types, new edge kinds: the factory's schema is
not static. If schema change is painful or unsafe, this whole proposal is a dead end
in six months. Dolt merges SCHEMA as well as data, which is the part to verify.

  E1  versioned migration ledger (which migrations have run)
  E2  additive migration: new column, existing rows keep their data
  E3  new table + new edge type
  E4  migration is idempotent (safe to re-run)
  E5  two devs each add a DIFFERENT column -> schema merges
  E6  two devs add the SAME column with DIFFERENT types -> conflict, not silent pick
  E7  a migration that would break existing data is refused
  E8  rollback: a bad migration can be reverted (Dolt commit history)

Self-provisioning: builds its own remote + 2 clones under poc/se/.
Run: .venv/bin/python -u poc/test_schema_evolution.py
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent / "se"
REMOTE = ROOT / "remote"
DB = "sch"
M = {"A": ROOT / "mA" / DB, "B": ROOT / "mB" / DB}
RESULTS: list[tuple[str, bool, str]] = []


def check(name, ok, detail=""):
    RESULTS.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}")
    for ln in (detail or "").splitlines():
        print(f"        {ln}")


def sh(args, cwd, timeout=240):
    try:
        return subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(args, 124, "", f"TIMEOUT {timeout}s")


def sql(m, stmt, timeout=240):
    return sh(["dolt", "sql", "-q", stmt], cwd=M[m], timeout=timeout)


def csv(m, stmt):
    r = sh(["dolt", "sql", "-q", stmt, "-r", "csv"], cwd=M[m])
    lines = [l for l in (r.stdout or "").strip().splitlines() if l.strip()]
    if len(lines) < 2:
        return []
    return [dict(zip(lines[0].split(","), l.split(","))) for l in lines[1:]]


def cols(m, table):
    return [d["Field"] for d in csv(m, f"DESCRIBE {table}")]


def commit_push(m, msg):
    sh(["dolt", "add", "-A"], cwd=M[m])
    sh(["dolt", "commit", "-m", msg], cwd=M[m])
    return sh(["dolt", "push", "origin", "main"], cwd=M[m])


def clean(m):
    sh(["dolt", "merge", "--abort"], cwd=M[m])
    sh(["dolt", "reset", "--hard", "origin/main"], cwd=M[m])


def setup():
    print("--- setup: remote + 2 clones (no server)")
    if ROOT.exists():
        shutil.rmtree(ROOT)
    ROOT.mkdir(parents=True)
    REMOTE.mkdir()
    src = ROOT / "src"
    src.mkdir()
    sh(["dolt", "init", "--name", "seed", "--email", "s@l"], cwd=src)
    for s in (
        "CREATE TABLE schema_migrations (version INT PRIMARY KEY, name VARCHAR(80) NOT NULL, "
        "applied_at DATETIME NOT NULL)",
        "CREATE TABLE bc (bc_id VARCHAR(24) PRIMARY KEY, title TEXT NOT NULL)",
        "INSERT INTO bc VALUES ('BC-1.01.001','first'),('BC-1.01.002','second')",
        "INSERT INTO schema_migrations VALUES (1,'baseline',NOW())",
    ):
        sh(["dolt", "sql", "-q", s], cwd=src)
    sh(["dolt", "add", "-A"], cwd=src)
    sh(["dolt", "commit", "-m", "baseline schema v1"], cwd=src)
    sh(["dolt", "remote", "add", "origin", f"file://{REMOTE}"], cwd=src)
    p = sh(["dolt", "push", "origin", "main"], cwd=src)
    if p.returncode != 0:
        raise RuntimeError(f"seed push failed: {p.stderr[:200]}")
    for k, path in M.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        r = sh(["dolt", "clone", f"file://{REMOTE}", DB], cwd=path.parent)
        if r.returncode != 0:
            raise RuntimeError(f"clone {k} failed: {r.stderr[:200]}")
        sh(["dolt", "config", "--local", "--add", "user.name", f"dev{k}"], cwd=path)
        sh(["dolt", "config", "--local", "--add", "user.email", f"dev{k}@s"], cwd=path)
    print(f"    A={M['A']}\n    B={M['B']}\n")


# ------------------------------------------------------------- migration runner


MIGRATIONS = [
    (2, "add bc.capability", "ALTER TABLE bc ADD COLUMN capability VARCHAR(16) NULL"),
    (3, "add bc.lifecycle_status",
     "ALTER TABLE bc ADD COLUMN lifecycle_status VARCHAR(24) NOT NULL DEFAULT 'active'"),
    (4, "add adr table",
     "CREATE TABLE adr (adr_id VARCHAR(16) PRIMARY KEY, title TEXT NOT NULL)"),
    (5, "add bc_adr edge",
     "CREATE TABLE bc_adr (bc_id VARCHAR(24) NOT NULL, adr_id VARCHAR(16) NOT NULL, "
     "PRIMARY KEY (bc_id, adr_id), "
     "CONSTRAINT fk_bcadr_bc FOREIGN KEY (bc_id) REFERENCES bc (bc_id) ON DELETE CASCADE, "
     "CONSTRAINT fk_bcadr_adr FOREIGN KEY (adr_id) REFERENCES adr (adr_id) ON DELETE CASCADE)"),
]


def applied(m) -> set[int]:
    return {int(r["version"]) for r in csv(m, "SELECT version FROM schema_migrations")}


def migrate(m) -> list[int]:
    """Apply every pending migration in order, recording each in the ledger."""
    done = applied(m)
    ran = []
    for ver, name, ddl in MIGRATIONS:
        if ver in done:
            continue
        r = sql(m, ddl)
        if r.returncode != 0:
            raise RuntimeError(f"migration {ver} failed: {(r.stderr or r.stdout)[:160]}")
        sql(m, f"INSERT INTO schema_migrations VALUES ({ver},'{name}',NOW())")
        ran.append(ver)
    return ran


# ---------------------------------------------------------------- tests


def e1_ledger():
    before = applied("A")
    ran = migrate("A")
    after = applied("A")
    commit_push("A", "schema: migrate to v5")
    check("E1 versioned migration ledger records what has been applied",
          before == {1} and ran == [2, 3, 4, 5] and after == {1, 2, 3, 4, 5},
          f"applied before={sorted(before)}; ran={ran}; applied after={sorted(after)}\n"
          "=> `schema_migrations` is the same pattern beads uses (MigrateUpWithLock);\n"
          "   it makes 'which schema is this clone on' a query, not a guess")


def e2_additive_keeps_data():
    rows = csv("A", "SELECT bc_id, title, capability, lifecycle_status FROM bc ORDER BY bc_id")
    have_cols = cols("A", "bc")
    ok = (len(rows) == 2
          and all(r["title"] in ("first", "second") for r in rows)
          and all(r["lifecycle_status"] == "active" for r in rows))
    check("E2 additive migration: new columns appear, existing rows keep their data",
          ok and "capability" in have_cols and "lifecycle_status" in have_cols,
          f"bc columns now: {have_cols}\nrows: {rows}\n"
          "=> NOT NULL DEFAULT backfills existing rows; nothing had to be rewritten")


def e3_new_table_and_edge():
    sql("A", "INSERT INTO adr VALUES ('ADR-001','first decision')")
    good = sql("A", "INSERT INTO bc_adr VALUES ('BC-1.01.001','ADR-001')")
    bad = sql("A", "INSERT INTO bc_adr VALUES ('BC-1.01.001','ADR-999')")
    n = csv("A", "SELECT COUNT(*) AS c FROM bc_adr")[0]["c"]
    commit_push("A", "schema: adr + bc_adr")
    check("E3 new table + new edge type, with the FK enforced from day one",
          good.returncode == 0 and bad.returncode != 0 and n == "1",
          f"valid edge inserted={good.returncode == 0}; "
          f"edge to a non-existent ADR refused={bad.returncode != 0}\n"
          f"bc_adr rows={n}\n"
          f"  refusal: {(bad.stderr or bad.stdout or '').strip()[:100]}")


def e4_idempotent():
    ran = migrate("A")
    check("E4 migrate is idempotent: re-running applies nothing",
          ran == [], f"second migrate run applied: {ran or 'nothing'}\n"
                     "=> safe to run on every agent start / CI job")


def e5_different_columns_merge():
    """Two devs evolve the schema independently. Dev A adds a column, dev B adds a
    different one. Both must survive."""
    for k in M:
        clean(k)
        sh(["dolt", "pull", "origin", "main"], cwd=M[k])
    sql("A", "ALTER TABLE bc ADD COLUMN owner VARCHAR(32) NULL")
    sql("A", "INSERT INTO schema_migrations VALUES (10,'add bc.owner',NOW())")
    pa = commit_push("A", "schema: add bc.owner")
    sql("B", "ALTER TABLE bc ADD COLUMN risk VARCHAR(16) NULL")
    sql("B", "INSERT INTO schema_migrations VALUES (11,'add bc.risk',NOW())")
    sh(["dolt", "add", "-A"], cwd=M["B"])
    sh(["dolt", "commit", "-m", "schema: add bc.risk"], cwd=M["B"])
    pull = sh(["dolt", "pull", "origin", "main"], cwd=M["B"])
    merged_cols = cols("B", "bc")
    pb = sh(["dolt", "push", "origin", "main"], cwd=M["B"])
    clean("A")
    sh(["dolt", "pull", "origin", "main"], cwd=M["A"])
    a_cols = cols("A", "bc")
    both = "owner" in merged_cols and "risk" in merged_cols
    check("E5 two devs adding DIFFERENT columns -> schema merges, both survive",
          pa.returncode == 0 and pull.returncode == 0 and both
          and "owner" in a_cols and "risk" in a_cols,
          f"A push={pa.returncode}, B pull={pull.returncode}, B push={pb.returncode}\n"
          f"bc columns on B after merge: {merged_cols}\n"
          f"bc columns on A after pull : {a_cols}\n"
          "=> Dolt merges SCHEMA, not just rows. Independent additive evolution works.")


def e6_same_column_conflict():
    """Both devs add a column with the SAME name but DIFFERENT types. That must
    surface, not silently pick one."""
    for k in M:
        clean(k)
        sh(["dolt", "pull", "origin", "main"], cwd=M[k])
    sql("A", "ALTER TABLE bc ADD COLUMN sev INT NULL")
    commit_push("A", "schema: sev as INT")
    sql("B", "ALTER TABLE bc ADD COLUMN sev VARCHAR(8) NULL")
    sh(["dolt", "add", "-A"], cwd=M["B"])
    sh(["dolt", "commit", "-m", "schema: sev as VARCHAR"], cwd=M["B"])
    pull = sh(["dolt", "pull", "origin", "main"], cwd=M["B"])
    blob = (pull.stdout + pull.stderr)
    surfaced = pull.returncode != 0
    kind = "schema conflict" if "schema" in blob.lower() else "conflict"
    clean("B")
    check("E6 same column, different types -> conflict surfaced, not silently picked",
          surfaced,
          f"B pull rc={pull.returncode} ({kind} detected={surfaced})\n"
          f"  {blob.strip().splitlines()[-1][:120] if blob.strip() else ''}\n"
          "=> divergent schema decisions are a REAL conflict needing a human decision;\n"
          "   silently taking one dev's type would corrupt the other dev's data")


def e7_unsafe_migration_refused():
    """A migration that would violate existing data must fail, not truncate."""
    for k in M:
        clean(k)
        sh(["dolt", "pull", "origin", "main"], cwd=M[k])
    # capability is nullable and unset on the seed rows, so NULLs already exist.
    sql("A", "UPDATE bc SET capability=NULL WHERE bc_id='BC-1.01.001'")
    sh(["dolt", "add", "-A"], cwd=M["A"])
    sh(["dolt", "commit", "-m", "ensure a NULL capability exists"], cwd=M["A"])
    # NOT NULL on a column that contains NULLs
    r = sql("A", "ALTER TABLE bc MODIFY COLUMN capability VARCHAR(16) NOT NULL")
    still_null = csv("A", "SELECT COUNT(*) AS c FROM bc WHERE capability IS NULL")
    n_null = still_null[0]["c"] if still_null else "?"
    check("E7 a migration that would break existing data is refused",
          r.returncode != 0 and int(n_null) >= 1,
          f"ALTER ... NOT NULL rc={r.returncode} (want non-zero)\n"
          f"  {(r.stderr or r.stdout or '').strip()[:110]}\n"
          f"rows still NULL afterwards={n_null} (data untouched, nothing coerced)\n"
          "=> fa must surface this as a migration failure and require an explicit\n"
          "   backfill step, rather than coercing data")


def e8_rollback():
    """A bad migration must be revertible. The Dolt commit graph is the mechanism."""
    for k in M:
        clean(k)
        sh(["dolt", "pull", "origin", "main"], cwd=M[k])
    before = cols("A", "bc")
    good_head = csv("A", "SELECT HASHOF('HEAD') AS h")[0]["h"]
    sql("A", "ALTER TABLE bc ADD COLUMN oops TEXT NULL")
    sql("A", "INSERT INTO schema_migrations VALUES (99,'bad migration',NOW())")
    sh(["dolt", "add", "-A"], cwd=M["A"])
    sh(["dolt", "commit", "-m", "schema: bad migration"], cwd=M["A"])
    with_oops = cols("A", "bc")
    # Revert to the pre-migration commit.
    sh(["dolt", "reset", "--hard", good_head], cwd=M["A"])
    after = cols("A", "bc")
    ledger = applied("A")
    check("E8 a bad migration is revertible via the commit graph",
          "oops" in with_oops and "oops" not in after and after == before
          and 99 not in ledger,
          f"columns before={len(before)}, after bad migration={len(with_oops)} "
          f"(oops present={'oops' in with_oops})\n"
          f"after reset to {str(good_head)[:10]}: oops present={'oops' in after}, "
          f"columns match original={after == before}\n"
          f"ledger no longer claims migration 99 = {99 not in ledger}\n"
          "=> schema and ledger revert TOGETHER because they are in the same commit.\n"
          "   That is the property a separate migrations directory does not have.")


def main():
    print("=" * 74)
    print("Schema evolution + cross-machine schema merge")
    print("=" * 74)
    setup()
    for t in (e1_ledger, e2_additive_keeps_data, e3_new_table_and_edge, e4_idempotent,
              e5_different_columns_merge, e6_same_column_conflict,
              e7_unsafe_migration_refused, e8_rollback):
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
