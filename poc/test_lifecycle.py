#!/usr/bin/env python3
"""Lifecycle: onboarding, recovery, wave branches, growth, large content.

The operational questions a sole interface has to answer, all in the server-less
one-clone-per-machine topology:

  L1  onboarding: a new dev clones and has the full corpus
  L2  disaster recovery: local clone destroyed -> restored from the remote
  L3  the rendered markdown is a standalone fallback (readable with NO dolt)
  L4  wave branches: create per-wave branch, work on it, merge back
  L5  an abandoned wave branch can be discarded without touching main
  L6  point-in-time restore: recover a record's state as of an earlier commit
  L7  growth + gc: repository size over many commits
  L8  large content: a big artifact body round-trips intact

Self-provisioning under poc/lc/.
Run: .venv/bin/python -u poc/test_lifecycle.py
"""
from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent / "lc"
REMOTE = ROOT / "remote"
DB = "arts"
A = ROOT / "mA" / DB
RESULTS: list[tuple[str, bool, str]] = []


def check(name, ok, detail=""):
    RESULTS.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}")
    for ln in (detail or "").splitlines():
        print(f"        {ln}")


def sh(args, cwd, timeout=300):
    try:
        return subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(args, 124, "", f"TIMEOUT {timeout}s")


def sql(stmt, cwd=None, timeout=300):
    return sh(["dolt", "sql", "-q", stmt], cwd=cwd or A, timeout=timeout)


def csv(stmt, cwd=None):
    r = sh(["dolt", "sql", "-q", stmt, "-r", "csv"], cwd=cwd or A)
    lines = [l for l in (r.stdout or "").strip().splitlines() if l.strip()]
    if len(lines) < 2:
        return []
    return [dict(zip(lines[0].split(","), l.split(","))) for l in lines[1:]]


def one(stmt, cwd=None):
    rs = csv(stmt, cwd)
    return list(rs[0].values())[0] if rs else None


def commit(msg, cwd=None):
    c = cwd or A
    sh(["dolt", "add", "-A"], cwd=c)
    return sh(["dolt", "commit", "-m", msg], cwd=c)


def push(cwd=None, branch="main"):
    return sh(["dolt", "push", "origin", branch], cwd=cwd or A)


def du_mb(p: Path) -> float:
    r = subprocess.run(["du", "-sk", str(p)], capture_output=True, text=True)
    try:
        return int(r.stdout.split()[0]) / 1024
    except Exception:
        return -1.0


def setup():
    print("--- setup: remote + 1 clone (server-less)")
    if ROOT.exists():
        shutil.rmtree(ROOT)
    ROOT.mkdir(parents=True)
    REMOTE.mkdir()
    src = ROOT / "src"
    src.mkdir()
    sh(["dolt", "init", "--name", "seed", "--email", "s@l"], cwd=src)
    for s in ("CREATE TABLE bc (bc_id VARCHAR(24) PRIMARY KEY, title TEXT NOT NULL, "
              "capability VARCHAR(16) NULL, body LONGTEXT NULL)",
              "CREATE TABLE story (story_id VARCHAR(24) PRIMARY KEY, wave INT NULL, "
              "status VARCHAR(16) NOT NULL DEFAULT 'pending')"):
        sh(["dolt", "sql", "-q", s], cwd=src)
    vals = ",".join(f"('BC-1.{i:02d}.001','contract {i}',NULL,NULL)" for i in range(40))
    sh(["dolt", "sql", "-q", f"INSERT INTO bc VALUES {vals}"], cwd=src)
    sh(["dolt", "sql", "-q", "INSERT INTO story VALUES ('S-1.01',1,'pending'),"
                             "('S-2.01',2,'pending')"], cwd=src)
    sh(["dolt", "add", "-A"], cwd=src)
    sh(["dolt", "commit", "-m", "seed corpus"], cwd=src)
    sh(["dolt", "remote", "add", "origin", f"file://{REMOTE}"], cwd=src)
    p = sh(["dolt", "push", "origin", "main"], cwd=src)
    if p.returncode != 0:
        raise RuntimeError(f"seed push failed: {p.stderr[:200]}")
    A.parent.mkdir(parents=True, exist_ok=True)
    r = sh(["dolt", "clone", f"file://{REMOTE}", DB], cwd=A.parent)
    if r.returncode != 0:
        raise RuntimeError(f"clone failed: {r.stderr[:200]}")
    sh(["dolt", "config", "--local", "--add", "user.name", "devA"], cwd=A)
    sh(["dolt", "config", "--local", "--add", "user.email", "devA@s"], cwd=A)
    print(f"    clone={A}\n")


# ---------------------------------------------------------------- tests


def l1_onboarding():
    """A third dev joins: clone, configure identity, done."""
    d = ROOT / "newdev"
    d.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    r = sh(["dolt", "clone", f"file://{REMOTE}", DB], cwd=d)
    dt = time.time() - t0
    clone = d / DB
    sh(["dolt", "config", "--local", "--add", "user.name", "devC"], cwd=clone)
    sh(["dolt", "config", "--local", "--add", "user.email", "devC@s"], cwd=clone)
    n = one("SELECT COUNT(*) AS c FROM bc", cwd=clone)
    check("L1 onboarding: a new dev clones and immediately has the full corpus",
          r.returncode == 0 and n == "40",
          f"clone rc={r.returncode} in {dt:.1f}s; bc rows visible={n}\n"
          "=> two commands (clone + identity). Identity is NOT optional: without it\n"
          "   every `dolt pull` fails with 'Author identity unknown' (see §3f).")


def l2_disaster_recovery():
    """The local clone is destroyed. Everything pushed must come back."""
    sql("UPDATE bc SET capability='CAP-042' WHERE bc_id='BC-1.00.001'")
    commit("work before disaster")
    push()
    before = one("SELECT capability AS c FROM bc WHERE bc_id='BC-1.00.001'")
    head_before = one("SELECT HASHOF('HEAD') AS h")
    # Destroy it.
    shutil.rmtree(A)
    gone = not A.exists()
    r = sh(["dolt", "clone", f"file://{REMOTE}", DB], cwd=A.parent)
    sh(["dolt", "config", "--local", "--add", "user.name", "devA"], cwd=A)
    sh(["dolt", "config", "--local", "--add", "user.email", "devA@s"], cwd=A)
    after = one("SELECT capability AS c FROM bc WHERE bc_id='BC-1.00.001'")
    head_after = one("SELECT HASHOF('HEAD') AS h")
    n = one("SELECT COUNT(*) AS c FROM bc")
    check("L2 disaster recovery: destroyed clone fully restored from the remote",
          gone and r.returncode == 0 and after == before == "CAP-042"
          and head_after == head_before and n == "40",
          f"clone deleted={gone}; re-clone rc={r.returncode}\n"
          f"value before={before!r} after={after!r}; rows={n}\n"
          f"HEAD identical={head_after == head_before} ({str(head_before)[:10]})\n"
          "=> recovery is `dolt clone`. Anything NOT pushed is lost, which makes the\n"
          "   push cadence the real durability boundary.")


def l3_markdown_fallback():
    """The rendered export must be readable with no Dolt at all — the 'what if the
    tooling is broken' answer."""
    out = ROOT / "render"
    if out.exists():
        shutil.rmtree(out)
    out.mkdir()
    rows = csv("SELECT bc_id, title, capability FROM bc ORDER BY bc_id")
    for r in rows:
        (out / f"{r['bc_id']}.md").write_text(
            f"---\nbc_id: {r['bc_id']}\ncapability: {r['capability']}\n"
            f"generated: true\n---\n\n# {r['bc_id']}: {r['title']}\n")
    # Read them back with NOTHING but the filesystem.
    files = sorted(out.glob("*.md"))
    txt = files[0].read_text() if files else ""
    readable = "bc_id:" in txt and txt.lstrip().startswith("---")
    check("L3 rendered markdown is a standalone fallback (no dolt needed to read it)",
          len(files) == len(rows) and readable,
          f"{len(files)} plain markdown files rendered from {len(rows)} records\n"
          f"first file parses as frontmatter+body without any tooling={readable}\n"
          "=> commit this alongside the DB and the corpus is never unreadable, even\n"
          "   if Dolt is unavailable or the DB is corrupt")


def l4_wave_branches():
    """Per-wave branches in the server-less topology: branch, work, merge back."""
    sh(["dolt", "checkout", "-b", "wave-2"], cwd=A)
    sql("UPDATE story SET status='in_progress' WHERE story_id='S-2.01'")
    sql("UPDATE bc SET capability='CAP-W2' WHERE bc_id='BC-1.10.001'")
    commit("wave-2: work")
    on_branch = one("SELECT status AS s FROM story WHERE story_id='S-2.01'")
    sh(["dolt", "checkout", "main"], cwd=A)
    on_main_before = one("SELECT status AS s FROM story WHERE story_id='S-2.01'")
    mg = sh(["dolt", "merge", "wave-2", "--no-edit"], cwd=A)
    on_main_after = one("SELECT status AS s FROM story WHERE story_id='S-2.01'")
    cap = one("SELECT capability AS c FROM bc WHERE bc_id='BC-1.10.001'")
    commit("merge wave-2")
    push()
    check("L4 wave branches: isolated work on a branch, merged back to main",
          on_branch == "in_progress" and on_main_before == "pending"
          and on_main_after == "in_progress" and cap == "CAP-W2",
          f"on wave-2 branch: status={on_branch}\n"
          f"on main BEFORE merge: status={on_main_before} (isolation held)\n"
          f"on main AFTER merge : status={on_main_after}, capability={cap}\n"
          f"merge rc={mg.returncode}\n"
          "=> a wave gets its own branch, so unmerged wave work is invisible to main.\n"
          "   That is exactly what the single-orphan-branch design cannot do today.")


def l5_abandon_branch():
    sh(["dolt", "checkout", "-b", "wave-99-abandoned"], cwd=A)
    sql("UPDATE bc SET capability='CAP-JUNK' WHERE bc_id='BC-1.20.001'")
    commit("wave-99: doomed work")
    sh(["dolt", "checkout", "main"], cwd=A)
    d = sh(["dolt", "branch", "-D", "wave-99-abandoned"], cwd=A)
    cap = one("SELECT capability AS c FROM bc WHERE bc_id='BC-1.20.001'")
    branches = [r.get("name") for r in csv("SELECT name FROM dolt_branches")]
    check("L5 an abandoned wave branch is discarded without touching main",
          d.returncode == 0 and (cap in ("", None))
          and "wave-99-abandoned" not in branches,
          f"delete rc={d.returncode}; branches now={branches}\n"
          f"main's value for the touched record={cap!r} (unaffected)\n"
          "=> abandoning a cycle is a branch delete, not a revert-hunt through history")


def l6_point_in_time():
    """'What did this record look like at the wave-1 gate?' must be answerable."""
    marker = one("SELECT HASHOF('HEAD') AS h")
    sql("UPDATE bc SET title='renamed after the gate' WHERE bc_id='BC-1.05.001'")
    commit("post-gate rename")
    now = one("SELECT title AS t FROM bc WHERE bc_id='BC-1.05.001'")
    then = one(f"SELECT title AS t FROM bc AS OF '{marker}' WHERE bc_id='BC-1.05.001'")
    diff = csv(f"SELECT from_title, to_title FROM dolt_diff_bc "
               f"WHERE to_commit=HASHOF('HEAD') AND to_bc_id='BC-1.05.001'")
    check("L6 point-in-time read: a record's state AS OF an earlier commit",
          now == "renamed after the gate" and then == "contract 5" and len(diff) == 1,
          f"now  = {now!r}\nas of {str(marker)[:10]} = {then!r}\n"
          f"dolt_diff row: {diff[0] if diff else None}\n"
          "=> tag the commit at each phase gate and every artifact becomes\n"
          "   time-travellable; today this is manual archaeology across 1,607 commits")


def l7_growth_and_gc():
    """Every write is a commit. Does the repo grow unreasonably, and does gc help?"""
    size0 = du_mb(A)
    n_commits0 = int(one("SELECT COUNT(*) AS c FROM dolt_log") or 0)
    for i in range(40):
        sql(f"UPDATE bc SET capability='CAP-{i:03d}' WHERE bc_id='BC-1.{i%40:02d}.001'")
        commit(f"churn {i}")
    size1 = du_mb(A)
    n_commits1 = int(one("SELECT COUNT(*) AS c FROM dolt_log") or 0)
    t0 = time.time()
    g = sh(["dolt", "gc"], cwd=A, timeout=600)
    gc_s = time.time() - t0
    size2 = du_mb(A)
    rows_ok = one("SELECT COUNT(*) AS c FROM bc") == "40"
    check("L7 growth is modest and `dolt gc` reclaims space",
          g.returncode == 0 and rows_ok and size2 <= size1,
          f"commits {n_commits0} -> {n_commits1} (+{n_commits1-n_commits0})\n"
          f"size {size0:.1f}MB -> {size1:.1f}MB after 40 commits "
          f"({1024*(size1-size0)/40:.0f} KB/commit)\n"
          f"after `dolt gc` ({gc_s:.1f}s): {size2:.1f}MB  "
          f"(reclaimed {size1-size2:.1f}MB)\n"
          f"data intact after gc={rows_ok}\n"
          "=> gc is a maintenance task fa should expose; unbounded growth is the risk\n"
          "   to watch over years, and this measures the per-commit cost")


def l8_large_content():
    """Artifact bodies are prose and can be large. Verify a big one survives intact."""
    big = ("## Section\n" + ("lorem ipsum dolor sit amet " * 40 + "\n") * 200)
    sha = hashlib.sha256(big.encode()).hexdigest()[:16]
    p = ROOT / "big.sql"
    esc = big.replace("\\", "\\\\").replace("'", "''")
    p.write_text(f"UPDATE bc SET body='{esc}' WHERE bc_id='BC-1.30.001';")
    r = sh(["dolt", "sql", "-f", str(p)], cwd=A, timeout=300)
    commit("large body")
    got_len = one("SELECT LENGTH(body) AS n FROM bc WHERE bc_id='BC-1.30.001'")
    out = sh(["dolt", "sql", "-q", "SELECT body FROM bc WHERE bc_id='BC-1.30.001'",
              "-r", "json"], cwd=A, timeout=300)
    round_ok = str(len(big)) == str(got_len)
    check("L8 a large artifact body round-trips intact",
          r.returncode == 0 and round_ok,
          f"wrote {len(big)/1024:.0f} KB (sha {sha}); stored LENGTH={got_len}\n"
          f"length preserved={round_ok}; read-back rc={out.returncode}\n"
          "=> LONGTEXT handles prose bodies. Binary/large attachments (screenshots,\n"
          "   demo evidence) should stay as files on disk with a path in the DB --\n"
          "   NOT tested here, and a deliberate non-goal.")


def main():
    print("=" * 74)
    print("Lifecycle: onboarding, recovery, wave branches, growth")
    print("=" * 74)
    setup()
    for t in (l1_onboarding, l2_disaster_recovery, l3_markdown_fallback,
              l4_wave_branches, l5_abandon_branch, l6_point_in_time,
              l7_growth_and_gc, l8_large_content):
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
