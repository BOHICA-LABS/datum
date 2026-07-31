#!/usr/bin/env python3
"""Multiple factory INSTANCES against one project.

Two axes:
  (a) N devs x M instances across machines
  (b) ONE dev running several instances at once -- a primary track plus research
      spikes -- on one machine

Architecture forced by a measured constraint: Dolt's checkout state is PER-CLONE.
Reads from another branch work (`SELECT ... AS OF 'branch'`), but writes do not
("table doesn't support UPDATE"). So a clone can only WRITE to one branch at a time,
which means:

    ONE CLONE PER FACTORY INSTANCE, each on its own branch.

Clones cost ~0.2s, so this is cheap. It also has a nice consequence: the flock mutex
becomes per-INSTANCE, so instances never contend locally -- only at push.

    dev 1 machine                                  dev 2 machine
    ├── clone: factory/primary   (branch)          ├── clone: factory/primary-b
    ├── clone: factory/spike-a   (branch)          └── clone: factory/maint
    └── clone: factory/spike-b   (branch)
                    \\____ shared remote: main = canonical specs ____/

  I1  instance registry: identity + per-instance state, isolated
  I2  one dev, 3 concurrent instances, each on its own branch
  I3  per-scope leases: different scopes concurrent, same scope exclusive
  I4  a spike GRADUATES: merge its spec change back to main
  I5  a spike is ABANDONED: discard, main untouched
  I6  two instances edit the SAME spec -> conflict surfaces at merge
  I7  instances share the same base specs (they branch from main)
  I8  cross-dev: two devs' instances both push; branches do not collide
  I9  the constraint itself: one clone cannot write two branches at once

Run: .venv/bin/python -u poc/test_multi_instance.py
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from clonelock import clone_write_lock  # noqa: E402

ROOT = Path(__file__).parent / "mi"
REMOTE = ROOT / "remote"
DB = "arts"
RESULTS: list[tuple[str, bool, str]] = []

# instance name -> (machine dir, branch)
INSTANCES = {
    "primary":   ("dev1", "factory/primary"),
    "spike-a":   ("dev1", "factory/spike-a"),
    "spike-b":   ("dev1", "factory/spike-b"),
    "dev2-main": ("dev2", "factory/dev2-main"),
}


def check(name, ok, detail=""):
    RESULTS.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}")
    for ln in (detail or "").splitlines():
        print(f"        {ln}")


def clone_dir(inst: str) -> Path:
    machine, _ = INSTANCES[inst]
    return ROOT / machine / inst / DB


def sh(args, cwd, timeout=240):
    try:
        return subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(args, 124, "", "TIMEOUT")


def sql(inst, stmt, timeout=240):
    return sh(["dolt", "sql", "-q", stmt], cwd=clone_dir(inst), timeout=timeout)


def rows(inst, stmt):
    r = sh(["dolt", "sql", "-q", stmt, "-r", "csv"], cwd=clone_dir(inst))
    lines = [l for l in (r.stdout or "").strip().splitlines() if l.strip()]
    if len(lines) < 2:
        return []
    hdr = lines[0].split(",")
    return [dict(zip(hdr, l.split(","))) for l in lines[1:]]


def one(inst, stmt):
    rs = rows(inst, stmt)
    return list(rs[0].values())[0] if rs else None


def commit(inst, msg):
    d = clone_dir(inst)
    sh(["dolt", "add", "-A"], cwd=d)
    return sh(["dolt", "commit", "-m", msg], cwd=d)


def push(inst, branch=None):
    _, br = INSTANCES[inst]
    return sh(["dolt", "push", "origin", branch or br], cwd=clone_dir(inst))


def setup():
    print("--- setup: remote with canonical `main`, then one clone per instance")
    if ROOT.exists():
        shutil.rmtree(ROOT)
    ROOT.mkdir(parents=True)
    REMOTE.mkdir()
    src = ROOT / "src"
    src.mkdir()
    sh(["dolt", "init", "--name", "seed", "--email", "s@l"], cwd=src)
    for s in (
        "CREATE TABLE bc (bc_id VARCHAR(24) PRIMARY KEY, title TEXT NOT NULL, "
        "capability VARCHAR(16) NULL)",
        "CREATE TABLE factory_instance (instance_id VARCHAR(24) PRIMARY KEY, "
        "owner VARCHAR(24) NOT NULL, mode VARCHAR(16) NOT NULL, "
        "branch VARCHAR(48) NOT NULL UNIQUE, status VARCHAR(16) NOT NULL DEFAULT 'active')",
        "CREATE TABLE instance_state (instance_id VARCHAR(24), k VARCHAR(32), v TEXT NOT NULL, "
        "PRIMARY KEY (instance_id, k), "
        "FOREIGN KEY (instance_id) REFERENCES factory_instance(instance_id) ON DELETE CASCADE)",
        # Leases are per-SCOPE now, not one global row.
        "CREATE TABLE lease (scope VARCHAR(48) PRIMARY KEY, holder VARCHAR(32) NULL, "
        "expires_at DATETIME NULL, token VARCHAR(48) NULL)",
        "INSERT INTO bc VALUES ('BC-1.01.001','shared contract one',NULL),"
        "('BC-1.02.001','shared contract two',NULL),"
        "('BC-1.03.001','shared contract three',NULL)",
    ):
        r = sh(["dolt", "sql", "-q", s], cwd=src)
        if r.returncode != 0:
            raise RuntimeError(f"seed DDL failed: {(r.stderr or r.stdout)[:180]}")
    sh(["dolt", "add", "-A"], cwd=src)
    sh(["dolt", "commit", "-m", "canonical main"], cwd=src)
    sh(["dolt", "remote", "add", "origin", f"file://{REMOTE}"], cwd=src)
    p = sh(["dolt", "push", "origin", "main"], cwd=src)
    if p.returncode != 0:
        raise RuntimeError(f"seed push failed: {p.stderr[:200]}")

    for inst, (machine, branch) in INSTANCES.items():
        d = ROOT / machine / inst
        d.mkdir(parents=True, exist_ok=True)
        r = sh(["dolt", "clone", f"file://{REMOTE}", DB], cwd=d)
        if r.returncode != 0:
            raise RuntimeError(f"clone {inst} failed: {r.stderr[:200]}")
        cd = d / DB
        sh(["dolt", "config", "--local", "--add", "user.name", inst], cwd=cd)
        sh(["dolt", "config", "--local", "--add", "user.email", f"{inst}@spike"], cwd=cd)
        sh(["dolt", "checkout", "-b", branch], cwd=cd)
    print("    dev1: primary, spike-a, spike-b   dev2: dev2-main\n")


# ---------------------------------------------------------------- tests


def i1_instance_registry():
    """Register each instance, then give each its own state rows. The key property:
    a spike's phase cannot be confused with the primary track's."""
    for inst, (machine, branch) in INSTANCES.items():
        mode = "feature" if "spike" in inst else "greenfield"
        sql("primary", f"INSERT INTO factory_instance VALUES "
                       f"('{inst}','{machine}','{mode}','{branch}','active')")
    dup = sql("primary", "INSERT INTO factory_instance VALUES "
                         "('other','dev1','feature','factory/primary','active')")
    for inst in INSTANCES:
        sql("primary", f"INSERT INTO instance_state VALUES ('{inst}','phase','1')")
    sql("primary", "UPDATE instance_state SET v='4' WHERE instance_id='primary' AND k='phase'")
    orphan = sql("primary", "INSERT INTO instance_state VALUES ('ghost','phase','9')")
    states = {r["instance_id"]: r["v"] for r in rows(
        "primary", "SELECT instance_id, v FROM instance_state WHERE k='phase' "
                   "ORDER BY instance_id")}
    commit("primary", "register instances")
    check("I1 instance registry: unique branch per instance, isolated per-instance state",
          dup.returncode != 0 and orphan.returncode != 0
          and states.get("primary") == "4" and states.get("spike-a") == "1",
          f"per-instance phase: {states}\n"
          f"duplicate branch refused={dup.returncode != 0}; "
          f"state for an unregistered instance refused={orphan.returncode != 0}\n"
          "=> replaces a single STATE.md whose 'phase:' field can only describe one run.\n"
          "   The primary track being at phase 4 while spike-a is at phase 1 is now\n"
          "   representable, and a UNIQUE branch stops two instances sharing a workspace.")


def i2_three_concurrent_instances_one_dev():
    """One dev, three instances, all writing at the same time. Because each has its
    own clone, the flock mutexes are independent -- no local contention."""
    results = {}
    lk = threading.Lock()
    bar = threading.Barrier(3)

    def work(inst, bc, cap):
        d = clone_dir(inst)
        try:
            with clone_write_lock(d, timeout=120):
                bar.wait()
                r = sql(inst, f"UPDATE bc SET capability='{cap}' WHERE bc_id='{bc}'")
                sh(["dolt", "add", "-A"], cwd=d)
                c = sh(["dolt", "commit", "-m", f"{inst}: set {cap}"], cwd=d)
                okk = r.returncode == 0 and (
                    c.returncode == 0 or "nothing to commit" in (c.stdout + c.stderr))
            with lk:
                results[inst] = "ok" if okk else f"rc={r.returncode}/{c.returncode}"
        except Exception as e:                                  # noqa: BLE001
            with lk:
                results[inst] = f"exc:{type(e).__name__}"

    jobs = [("primary", "BC-1.01.001", "CAP-PRIMARY"),
            ("spike-a", "BC-1.02.001", "CAP-SPIKEA"),
            ("spike-b", "BC-1.03.001", "CAP-SPIKEB")]
    ts = [threading.Thread(target=work, args=j) for j in jobs]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    # Each instance sees ONLY its own change on its own branch.
    seen = {}
    for inst, bc, cap in jobs:
        seen[inst] = one(inst, f"SELECT capability AS c FROM bc WHERE bc_id='{bc}'")
    cross = one("primary", "SELECT capability AS c FROM bc WHERE bc_id='BC-1.02.001'")
    all_ok = all(v == "ok" for v in results.values())
    own = all(seen[i] == c for i, _, c in jobs)
    check("I2 one dev, 3 concurrent instances: all succeed, each isolated on its branch",
          all_ok and own and cross in ("", None),
          f"outcomes={results}\n"
          f"each instance sees its own write: {seen}\n"
          f"primary's view of spike-a's record = {cross!r} (want empty -> isolated)\n"
          "=> separate clones mean separate mutexes: three instances write in parallel\n"
          "   with zero contention, and a spike's edits are invisible to the primary\n"
          "   track until it merges.")


def i3_per_scope_leases():
    """The lock can no longer be singular. Different scopes must be concurrent;
    the same scope must stay exclusive."""
    import secrets
    for scope in ("wave-1", "wave-2", "phase-6"):
        sql("primary", f"INSERT INTO lease (scope, holder) VALUES ('{scope}', NULL)")
    commit("primary", "seed leases")

    def acquire(inst, scope, holder):
        tok = secrets.token_hex(6)
        r = sql(inst, f"UPDATE lease SET holder='{holder}', token='{tok}', "
                      f"expires_at=DATE_ADD(NOW(), INTERVAL 600 SECOND) "
                      f"WHERE scope='{scope}' AND holder IS NULL")
        if r.returncode != 0:
            return False
        return one(inst, f"SELECT holder AS h FROM lease WHERE scope='{scope}'") == holder

    a = acquire("primary", "wave-1", "primary")
    b = acquire("primary", "wave-2", "spike-a")     # different scope, same clone
    c = acquire("primary", "wave-1", "spike-b")     # SAME scope -> must fail
    held = {r["scope"]: r["holder"] for r in rows(
        "primary", "SELECT scope, holder FROM lease ORDER BY scope")}
    commit("primary", "leases held")
    check("I3 per-scope leases: different scopes concurrent, same scope exclusive",
          a and b and not c and held.get("wave-1") == "primary"
          and held.get("wave-2") == "spike-a",
          f"acquire wave-1 by primary = {a}\nacquire wave-2 by spike-a = {b} "
          f"(concurrent, different scope)\nacquire wave-1 by spike-b = {c} "
          f"(want False -- already held)\nleases: {held}\n"
          "=> a single `factory_lock` row would have serialized the whole project.\n"
          "   Scoping the lease per wave/phase/cycle is what lets instances run in\n"
          "   parallel at all.")


def i4_spike_graduates():
    """A spike proves something out; its spec change merges back into main."""
    sql("spike-a", "UPDATE bc SET title='refined by spike-a' WHERE bc_id='BC-1.02.001'")
    commit("spike-a", "spike-a: refine contract")
    p = push("spike-a")
    # Integrate on the primary clone: fetch the spike branch and merge into main.
    d = clone_dir("primary")
    sh(["dolt", "fetch", "origin", INSTANCES["spike-a"][1]], cwd=d)
    sh(["dolt", "checkout", "main"], cwd=d)
    sh(["dolt", "pull", "origin", "main"], cwd=d)
    mg = sh(["dolt", "merge", f"remotes/origin/{INSTANCES['spike-a'][1]}", "--no-edit"], cwd=d)
    title = one("primary", "SELECT title AS t FROM bc WHERE bc_id='BC-1.02.001'")
    sh(["dolt", "add", "-A"], cwd=d)
    sh(["dolt", "commit", "-m", "graduate spike-a"], cwd=d)
    pm = sh(["dolt", "push", "origin", "main"], cwd=d)
    sh(["dolt", "checkout", INSTANCES["primary"][1]], cwd=d)
    check("I4 a spike graduates: its change merges into canonical main",
          p.returncode == 0 and mg.returncode == 0
          and title == "refined by spike-a" and pm.returncode == 0,
          f"spike push rc={p.returncode}; merge into main rc={mg.returncode}; "
          f"main push rc={pm.returncode}\n"
          f"main's title for the record = {title!r}\n"
          "=> promotion is a branch merge. The spike never touched main until it earned it.")


def i5_spike_abandoned():
    sql("spike-b", "UPDATE bc SET title='doomed spike idea' WHERE bc_id='BC-1.03.001'")
    commit("spike-b", "spike-b: doomed work")
    d = clone_dir("primary")
    sh(["dolt", "checkout", "main"], cwd=d)
    sh(["dolt", "pull", "origin", "main"], cwd=d)
    main_title = one("primary", "SELECT title AS t FROM bc WHERE bc_id='BC-1.03.001'")
    # Abandon: mark retired in the registry and delete the branch locally.
    sh(["dolt", "checkout", INSTANCES["primary"][1]], cwd=d)
    sql("primary", "UPDATE factory_instance SET status='abandoned' WHERE instance_id='spike-b'")
    commit("primary", "abandon spike-b")
    db = clone_dir("spike-b")
    sh(["dolt", "checkout", "main"], cwd=db)
    dl = sh(["dolt", "branch", "-D", INSTANCES["spike-b"][1]], cwd=db)
    status = one("primary", "SELECT status AS s FROM factory_instance "
                            "WHERE instance_id='spike-b'")
    check("I5 an abandoned spike leaves canonical main untouched",
          main_title == "shared contract three" and status == "abandoned"
          and dl.returncode == 0,
          f"main's title is still {main_title!r} (never polluted)\n"
          f"registry status={status}; branch delete rc={dl.returncode}\n"
          "=> abandoning a research spike costs a branch delete plus a status flip;\n"
          "   no revert archaeology, and the audit trail of what was tried survives\n"
          "   in the registry.")


def i6_two_instances_same_spec_conflict():
    """Two instances refine the SAME contract. The second merge must conflict."""
    d = clone_dir("primary")
    sh(["dolt", "checkout", "main"], cwd=d)
    sh(["dolt", "pull", "origin", "main"], cwd=d)
    sh(["dolt", "checkout", INSTANCES["primary"][1]], cwd=d)
    sh(["dolt", "merge", "main", "--no-edit"], cwd=d)
    sql("primary", "UPDATE bc SET capability='CAP-FROM-PRIMARY' WHERE bc_id='BC-1.01.001'")
    commit("primary", "primary: capability")
    push("primary")
    sql("dev2-main", "UPDATE bc SET capability='CAP-FROM-DEV2' WHERE bc_id='BC-1.01.001'")
    commit("dev2-main", "dev2: capability")
    d2 = clone_dir("dev2-main")
    sh(["dolt", "fetch", "origin", INSTANCES["primary"][1]], cwd=d2)
    mg = sh(["dolt", "merge", f"remotes/origin/{INSTANCES['primary'][1]}", "--no-edit"], cwd=d2)
    blob = (mg.stdout + mg.stderr).upper()
    conflicted = mg.returncode != 0 and "CONFLICT" in blob
    sh(["dolt", "merge", "--abort"], cwd=d2)
    check("I6 two instances refining the SAME spec -> conflict surfaced at merge",
          conflicted,
          f"merge rc={mg.returncode}; conflict detected={conflicted}\n"
          f"  {(mg.stdout + mg.stderr).strip().splitlines()[-1][:110] if blob else ''}\n"
          "=> parallel instances are safe on DISJOINT specs and conflict loudly on\n"
          "   overlapping ones. That is the correct boundary: the system does not\n"
          "   silently reconcile two competing design decisions.")


def i7_shared_base_specs():
    """All instances branch from main, so they share the canonical corpus."""
    counts = {}
    for inst in ("primary", "spike-a", "dev2-main"):
        counts[inst] = one(inst, "SELECT COUNT(*) AS c FROM bc")
    graduated = {}
    for inst in ("primary", "dev2-main"):
        d = clone_dir(inst)
        sh(["dolt", "fetch", "origin", "main"], cwd=d)
        graduated[inst] = one(inst, "SELECT title AS t FROM bc AS OF 'remotes/origin/main' "
                                    "WHERE bc_id='BC-1.02.001'")
    same = len(set(counts.values())) == 1
    check("I7 every instance shares the same canonical base specs",
          same and all(v == "refined by spike-a" for v in graduated.values()),
          f"bc COUNT(*) per instance: {counts} (identical={same})\n"
          f"each instance can read canonical main: {graduated}\n"
          "=> instances are VIEWS over one corpus, not forks of it. A spike reads the\n"
          "   real specs; only its own writes are isolated.")


def i8_cross_dev_branches_dont_collide():
    d1, d2 = clone_dir("primary"), clone_dir("dev2-main")
    p1 = push("primary")
    p2 = push("dev2-main")
    refs = sh(["git", "for-each-ref", "--format=%(refname)"], cwd=REMOTE)
    dolt_refs = [r for r in (refs.stdout or "").split() if "dolt" in r or "factory" in r]
    branches = sh(["dolt", "branch", "-r"], cwd=d1)
    check("I8 cross-dev: both devs' instance branches coexist on the remote",
          p1.returncode == 0 and p2.returncode == 0,
          f"dev1 primary push rc={p1.returncode}; dev2 push rc={p2.returncode}\n"
          f"remote refs mentioning dolt/factory: {len(dolt_refs)}\n"
          f"remote branches visible from dev1:\n"
          + "".join(f"    {l.strip()}\n" for l in (branches.stdout or "").splitlines()[:8])
          + "=> instance branches are namespaced (factory/<instance>), so N devs x M\n"
            "   instances share one remote without collision")


def i9_one_clone_cannot_write_two_branches():
    """The constraint that forces clone-per-instance. Documented as a test so a future
    Dolt change is noticed."""
    d = clone_dir("primary")
    cur = sh(["dolt", "branch", "--show-current"], cwd=d).stdout.strip()
    read_other = one("primary", "SELECT title AS t FROM bc AS OF 'main' "
                                "WHERE bc_id='BC-1.01.001'")
    w = sh(["dolt", "sql", "-q", "UPDATE bc AS OF 'main' SET title='x'"], cwd=d)
    blocked = w.returncode != 0
    check("I9 one clone cannot WRITE two branches at once (hence clone-per-instance)",
          bool(read_other) and blocked,
          f"current branch={cur}\n"
          f"cross-branch READ via AS OF works: {read_other!r}\n"
          f"cross-branch WRITE refused={blocked}: "
          f"{(w.stderr or w.stdout or '').strip()[:80]}\n"
          "=> server-less, checkout is per-clone working-set state. Concurrent instances\n"
          "   therefore need a clone each (~0.2s, and they share the remote). A shared\n"
          "   sql-server would allow `db/branch` connections instead -- the alternative.")


def main():
    print("=" * 74)
    print("Multiple factory instances against one project")
    print("=" * 74)
    setup()
    for t in (i1_instance_registry, i2_three_concurrent_instances_one_dev,
              i3_per_scope_leases, i4_spike_graduates, i5_spike_abandoned,
              i6_two_instances_same_spec_conflict, i7_shared_base_specs,
              i8_cross_dev_branches_dont_collide,
              i9_one_clone_cannot_write_two_branches):
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
