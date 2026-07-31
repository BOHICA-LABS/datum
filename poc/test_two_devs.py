#!/usr/bin/env python3
"""Two devs, two machines, one git repo, multiple agents each.

Topology under test (the composite of pass 4 + pass 5):

    machine A (dev 1)                     machine B (dev 2)
    ONE clone + flock mutex               ONE clone + flock mutex
    agents a0..aN (processes)             agents b0..bM (processes)
              \\                                   /
               \\____  shared remote (one repo) ___/
                        refs/dolt/data

Three coordination layers, and the question is whether they COMPOSE:
  L1  flock per machine  -> orders that machine's local agents
  L2  push / non-fast-forward rejection -> arbitrates BETWEEN machines
  L3  Dolt 3-way cell merge on pull -> reconciles pre-push divergence

No sql-server anywhere. Agents are real subprocesses.

Run: .venv/bin/python -u poc/test_two_devs.py
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from clonelock import clone_write_lock  # noqa: E402

ROOT = Path(__file__).parent / "td"
REMOTE = ROOT / "remote"
DB = "artifacts"
MACHINES = {"A": ROOT / "mA" / DB, "B": ROOT / "mB" / DB}
RESULTS: list[tuple[str, bool, str]] = []
SELF = str(Path(__file__).resolve())


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


def dsql(m, stmt, timeout=240):
    return sh(["dolt", "sql", "-q", stmt], cwd=MACHINES[m], timeout=timeout)


def csv(m, stmt):
    """Parse with -r csv. The default box format's header row was being read as data."""
    r = sh(["dolt", "sql", "-q", stmt, "-r", "csv"], cwd=MACHINES[m])
    lines = [l for l in (r.stdout or "").strip().splitlines() if l.strip()]
    if len(lines) < 2:
        return []
    return [dict(zip(lines[0].split(","), l.split(","))) for l in lines[1:]]


def conflicted(m) -> bool:
    r = sh(["dolt", "conflicts", "cat", "."], cwd=MACHINES[m])
    if "conflict" in (r.stdout + r.stderr).lower() and r.returncode != 0:
        return True
    st = sh(["dolt", "status"], cwd=MACHINES[m])
    return "conflict" in (st.stdout or "").lower()


def ensure_clean(m):
    """A clone left with unresolved conflicts fails EVERY later commit. Tests must
    not inherit that state from each other."""
    sh(["dolt", "merge", "--abort"], cwd=MACHINES[m])
    sh(["dolt", "reset", "--hard", "origin/main"], cwd=MACHINES[m])


def scalar(m, stmt):
    rs = csv(m, stmt)
    if not rs:
        return -1
    v = list(rs[0].values())[0]
    try:
        return int(v)
    except (TypeError, ValueError):
        return -1


def rows_of(m, stmt):
    return [tuple(d.values()) for d in csv(m, stmt)]


def setup():
    print("--- setup: 1 remote, 2 machines, 1 clone each, no sql-server")
    if ROOT.exists():
        shutil.rmtree(ROOT)
    ROOT.mkdir(parents=True)
    REMOTE.mkdir()
    src = ROOT / "src"
    src.mkdir()
    sh(["dolt", "init", "--name", "seed", "--email", "seed@spike"], cwd=src)
    for stmt in (
        "CREATE TABLE bc (bc_id VARCHAR(24) PRIMARY KEY, title TEXT NOT NULL, "
        "capability VARCHAR(16) NULL, owner VARCHAR(24) NULL, notes TEXT NULL)",
        "CREATE TABLE factory_lock (id TINYINT PRIMARY KEY, holder VARCHAR(32) NULL)",
        "CREATE TABLE ctr (id TINYINT PRIMARY KEY, n INT NOT NULL)",
        "INSERT INTO factory_lock VALUES (1,NULL)",
        "INSERT INTO ctr VALUES (1,0)",
    ):
        sh(["dolt", "sql", "-q", stmt], cwd=src)
    vals = ",".join(f"('BC-{i//10+1}.0{i%10}.001','contract {i}',NULL,NULL,NULL)"
                    for i in range(20))
    sh(["dolt", "sql", "-q", f"INSERT INTO bc VALUES {vals}"], cwd=src)
    sh(["dolt", "add", "-A"], cwd=src)
    sh(["dolt", "commit", "-m", "seed"], cwd=src)
    sh(["dolt", "remote", "add", "origin", f"file://{REMOTE}"], cwd=src)
    p = sh(["dolt", "push", "origin", "main"], cwd=src)
    if p.returncode != 0:
        raise RuntimeError(f"seed push failed: {p.stderr[:300]}")

    for m, path in MACHINES.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        r = sh(["dolt", "clone", f"file://{REMOTE}", DB], cwd=path.parent)
        if r.returncode != 0:
            raise RuntimeError(f"clone {m} failed: {r.stderr[:300]}")
        sh(["dolt", "config", "--local", "--add", "user.name", f"dev{m}"], cwd=path)
        sh(["dolt", "config", "--local", "--add", "user.email", f"dev{m}@spike"], cwd=path)
    print(f"    A={MACHINES['A']}\n    B={MACHINES['B']}\n    remote={REMOTE}\n")


# ------------------------------------------------------------ agent (worker)


def agent_main(argv):
    """One agent = one process. `test_two_devs.py --agent <machine> <sql> <mode>`

    mode=local     : mutex + write + commit           (no network)
    mode=sync      : mutex + pull + write + commit + push, retrying on rejection
    The mutex wraps the ENTIRE unit including commit and push, because a push reads
    the same storage a sibling agent may be writing.
    """
    m, stmt, mode = argv[0], argv[1], argv[2]
    tries = int(argv[3]) if len(argv) > 3 else 4
    # gap: seconds to wait between pull and write. Widens the read-modify-write
    # window deterministically so cross-machine races are reproducible instead of
    # timing-dependent.
    gap = float(argv[4]) if len(argv) > 4 else 0.0
    cwd = MACHINES[m]

    def run(a, t=240):
        return sh(a, cwd=cwd, timeout=t)

    for attempt in range(tries):
        try:
            with clone_write_lock(cwd, timeout=300):
                if mode == "sync":
                    pl = run(["dolt", "pull", "origin", "main"])
                    if pl.returncode != 0:
                        blob = (pl.stdout + pl.stderr).upper()
                        if "CONFLICT" in blob:
                            # CRITICAL: leave the clone CLEAN. An unresolved conflict
                            # fails every later commit by ANY agent on this machine.
                            run(["dolt", "merge", "--abort"])
                            print("FAIL:conflict-aborted")
                            return 0
                        print(f"FAIL:pull:{(pl.stderr or pl.stdout or '')[:80]}")
                        return 0
                if gap:
                    time.sleep(gap)
                w = run(["dolt", "sql", "-q", stmt])
                if w.returncode != 0:
                    blob = (w.stderr or w.stdout or "").lower()
                    already = ("duplicate" in blob or "unique" in blob)
                    if not already:
                        print(f"FAIL:write:{(w.stderr or w.stdout or '').strip()[:90]}")
                        return 0
                    # Idempotency: this write landed on an earlier attempt. Fall through
                    # to commit+push instead of bailing -- bailing here strands the
                    # earlier attempt's local commit, which a later reset discards.
                run(["dolt", "add", "-A"])          # `commit -am` does not stage here
                cm = run(["dolt", "commit", "-m", f"{m}: agent write"])
                blob = (cm.stdout + cm.stderr)
                if cm.returncode != 0 and "nothing to commit" not in blob \
                        and "no changes added" not in blob:
                    print(f"FAIL:commit:{blob.strip()[:80]}")
                    return 0
                if mode == "local":
                    print("OK")
                    return 0
                ps = run(["dolt", "push", "origin", "main"])
                if ps.returncode == 0:
                    print(f"OK:pushed:attempt{attempt+1}")
                    return 0
            # push rejected: another machine won. Loop to pull+retry.
            time.sleep(0.15 * (attempt + 1))
        except Exception as e:                                  # noqa: BLE001
            print(f"FAIL:exc:{type(e).__name__}")
            return 0
    print("FAIL:exhausted")
    return 0


def spawn(m, stmt, mode="sync", tries=4, gap=0.0):
    return subprocess.Popen(
        [sys.executable, SELF, "--agent", m, stmt, mode, str(tries), str(gap)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def run_fleet(jobs, timeout=600, gap=0.0, tries=4):
    """jobs = [(machine, sql), ...] all launched at once, across BOTH machines."""
    procs = [(m, spawn(m, s, tries=tries, gap=gap)) for m, s in jobs]
    outs = []
    for m, p in procs:
        try:
            o, _ = p.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            p.kill()
            o = "FAIL:proc-timeout"
        outs.append((m, (o or "").strip()))
    return outs


def sync(m):
    with clone_write_lock(MACHINES[m], timeout=300):
        sh(["dolt", "pull", "origin", "main"], cwd=MACHINES[m])


def summarize(outs):
    ok = sum(1 for _, o in outs if o.startswith("OK"))
    fails = [f"{m}:{o}" for m, o in outs if not o.startswith("OK")]
    return ok, fails


# ---------------------------------------------------------------- tests

NA, NB = 4, 4          # agents per dev


def d1_composite_disjoint():
    """Both devs' fleets write DISJOINT records concurrently. Everything must
    survive on BOTH machines."""
    jobs = ([("A", f"UPDATE bc SET owner='devA-a{i}' WHERE bc_id='BC-1.0{i}.001'")
             for i in range(NA)]
            + [("B", f"UPDATE bc SET owner='devB-b{i}' WHERE bc_id='BC-2.0{i}.001'")
               for i in range(NB)])
    outs = run_fleet(jobs)
    ok, fails = summarize(outs)
    manifest = [f for f in fails if "manifest" in f]
    for m in MACHINES:
        ensure_clean(m)
        sync(m)
    a = {r[0]: r[3] for r in rows_of("A", "SELECT * FROM bc WHERE owner IS NOT NULL")}
    b = {r[0]: r[3] for r in rows_of("B", "SELECT * FROM bc WHERE owner IS NOT NULL")}
    check("D1 composite: 4+4 agents on 2 machines, disjoint records, all converge",
          ok == NA + NB and not manifest and a == b and len(a) == NA + NB,
          f"{NA + NB} agents: {ok} ok, {len(fails)} failed ({len(manifest)} manifest)\n"
          f"after sync: A sees {len(a)} owned rows, B sees {len(b)}, identical={a == b}\n"
          + (f"failures: {fails[:3]}" if fails else ""))


def d2_same_row_different_fields():
    """Dev A edits `capability`, dev B edits `notes`, on the SAME row. Cell-level
    merge should keep both. A line-based store could not."""
    target = "BC-1.00.001"
    for m in MACHINES:
        ensure_clean(m)
        sync(m)
    outs = run_fleet([("A", f"UPDATE bc SET capability='CAP-AAA' WHERE bc_id='{target}'"),
                      ("B", f"UPDATE bc SET notes='from devB' WHERE bc_id='{target}'")])
    ok, fails = summarize(outs)
    for m in MACHINES:
        ensure_clean(m)
        sync(m)
    rowa = rows_of("A", f"SELECT bc_id,capability,notes FROM bc WHERE bc_id='{target}'")
    rowb = rows_of("B", f"SELECT bc_id,capability,notes FROM bc WHERE bc_id='{target}'")
    merged = bool(rowa) and rowa[0][1] == "CAP-AAA" and rowa[0][2] == "from devB"
    check("D2 same row, different columns, two machines -> cell merge keeps BOTH",
          merged and rowa == rowb,
          f"agents ok={ok} fails={fails}\nA sees {rowa}\nB sees {rowb}\n"
          "=> two devs editing different fields of one artifact do NOT conflict")


def d3_same_cell_conflict_surfaces():
    """Same row AND same column from both devs. Must SURFACE, never silently drop
    one dev's work."""
    target = "BC-1.01.001"
    for m in MACHINES:
        ensure_clean(m)
        sync(m)
    # Force true divergence: both write locally (no push), then reconcile.
    outs = run_fleet([("A", f"UPDATE bc SET capability='CAP-FROM-A' WHERE bc_id='{target}'")],
                     timeout=300)
    a_ok = outs[0][1].startswith("OK")
    p = subprocess.run([sys.executable, SELF, "--agent", "B",
                        f"UPDATE bc SET capability='CAP-FROM-B' WHERE bc_id='{target}'",
                        "local", "1"], capture_output=True, text=True, timeout=300)
    b_local = (p.stdout or "").strip()
    pull = sh(["dolt", "pull", "origin", "main"], cwd=MACHINES["B"])
    conflicted = pull.returncode != 0 and "CONFLICT" in (pull.stdout + pull.stderr).upper()
    # Clean up so later tests start from a consistent base.
    sh(["dolt", "merge", "--abort"], cwd=MACHINES["B"])
    sh(["dolt", "reset", "--hard", "origin/main"], cwd=MACHINES["B"])
    check("D3 same row+column from both devs -> conflict surfaced, work not lost silently",
          a_ok and b_local.startswith("OK") and conflicted,
          f"A pushed={a_ok}; B wrote locally={b_local}\n"
          f"B pull rc={pull.returncode} conflict-detected={conflicted}\n"
          f"  {(pull.stdout + pull.stderr).strip().splitlines()[-1][:110] if (pull.stdout+pull.stderr).strip() else ''}\n"
          "=> a human/agent must resolve; nothing is silently dropped")


def d4_identical_write_across_machines():
    """THE OPEN QUESTION. The in-server merge coalesces IDENTICAL cell writes (the
    zombie-merge bug). Does the PULL merge do the same? If it coalesces, then a
    non-unique write like `n = n + 1` is unsafe ACROSS machines even though the
    mutex makes it safe within one."""
    target = "BC-1.02.001"
    for m in MACHINES:
        ensure_clean(m)
        sync(m)
    # Both machines write the SAME value to the SAME cell, independently.
    a = subprocess.run([sys.executable, SELF, "--agent", "A",
                        f"UPDATE bc SET capability='CAP-SAME' WHERE bc_id='{target}'",
                        "local", "1"], capture_output=True, text=True, timeout=300)
    b = subprocess.run([sys.executable, SELF, "--agent", "B",
                        f"UPDATE bc SET capability='CAP-SAME' WHERE bc_id='{target}'",
                        "local", "1"], capture_output=True, text=True, timeout=300)
    pa = sh(["dolt", "push", "origin", "main"], cwd=MACHINES["A"])
    pull = sh(["dolt", "pull", "origin", "main"], cwd=MACHINES["B"])
    coalesced = pull.returncode == 0
    pb = sh(["dolt", "push", "origin", "main"], cwd=MACHINES["B"])
    val = rows_of("B", f"SELECT bc_id,capability FROM bc WHERE bc_id='{target}'")
    check("D4 identical same-cell write from both machines merges cleanly (documented)",
          a.stdout.strip().startswith("OK") and b.stdout.strip().startswith("OK")
          and coalesced,
          f"A local={a.stdout.strip()} B local={b.stdout.strip()}; A push rc={pa.returncode}\n"
          f"B pull rc={pull.returncode} (0 = coalesced, no conflict); B push rc={pb.returncode}\n"
          f"value = {val}\n"
          "=> identical writes coalesce on the PULL path too. Harmless for idempotent\n"
          "   field sets; but it means a NON-UNIQUE counter/lock write is NOT safe\n"
          "   across machines even though the local mutex makes it safe within one.")


def d5_counter_across_machines():
    """Naive cross-machine read-modify-write is not exact. Two configurations, because
    they fail DIFFERENTLY and the second one is the dangerous one:

      no-retry : the loser's push is REJECTED -> the loss is reported
      w/ retry : the loser pulls, its identical value coalesces (D4), its push then
                 SUCCEEDS -> both agents report OK and one increment is gone SILENTLY
    """
    total = 2                      # one agent per machine, wide window
    report = []
    for label, tries in (("no-retry", 1), ("with-retry", 3)):
        results = []
        for _ in range(3):
            for m in MACHINES:
                ensure_clean(m)
            with clone_write_lock(MACHINES["A"], timeout=300):
                dsql("A", "UPDATE ctr SET n=0 WHERE id=1")
                sh(["dolt", "add", "-A"], cwd=MACHINES["A"])
                sh(["dolt", "commit", "-m", "reset ctr"], cwd=MACHINES["A"])
                sh(["dolt", "push", "origin", "main"], cwd=MACHINES["A"])
            sync("B")
            outs = run_fleet([("A", "UPDATE ctr SET n = n + 1 WHERE id=1"),
                              ("B", "UPDATE ctr SET n = n + 1 WHERE id=1")],
                             gap=1.5, tries=tries)
            ok, _ = summarize(outs)
            for m in MACHINES:
                ensure_clean(m)
                sync(m)
            results.append((ok, scalar("A", "SELECT n FROM ctr WHERE id=1")))
        report.append((label, results))

    noretry = dict(report)["no-retry"]
    withretry = dict(report)["with-retry"]
    lossy_nr = [r for r in noretry if r[1] != total]
    silent_wr = [r for r in withretry if r[0] > r[1]]      # more OK than increments
    lines = [f"1 agent per machine, 1.5s pull->write gap, exact would be {total}"]
    for label, rs in report:
        lines.append(f"  {label:11} (agents_ok, final_counter): {rs}")
    lines += [
        f"no-retry  : {len(lossy_nr)}/3 rounds lost an increment -- REPRODUCIBLE. The",
        "            loss IS reported (the loser's push is rejected), but the increment",
        "            is gone unless the agent retries.",
        f"with-retry: exact in {sum(1 for r in withretry if r[1] == total)}/3 rounds,",
        "            because the retry RE-EXECUTES the read-modify-write against the",
        "            freshly merged base. Correctness therefore depends on the retry",
        "            recomputing, not merely re-pushing a committed value.",
        f"            (rounds where more agents reported OK than increments landed: "
        f"{len(silent_wr)}/3)",
        "",
        "UNREPRODUCED ANOMALY, recorded for honesty: an earlier 8-agent run of this",
        "  same test produced [(7,6),(8,8),(7,6)] -- 7 agents reporting OK while only 6",
        "  increments landed, i.e. a SILENT loss. It has not reproduced in the",
        "  controlled 2-agent wide-window setup, so it is logged as observed-but-",
        "  unexplained rather than a confirmed property.",
        "=> Do not rely on cross-machine mutable-cell RMW. Use append-only rows (D5b),",
        "   which is deterministic and needs no reasoning about merge semantics.",
    ]
    check("D5 naive cross-machine `n = n + 1` is not exact without a re-executing retry",
          len(lossy_nr) == 3, "\n".join(lines))


def d5b_append_only_is_safe():
    """The fix: model a counter as APPEND-ONLY rows with unique keys, not a mutable
    cell. Distinct primary keys can never coalesce, so the merge keeps every row."""
    for m in MACHINES:
        ensure_clean(m)
        sync(m)
    with clone_write_lock(MACHINES["A"], timeout=300):
        dsql("A", "CREATE TABLE IF NOT EXISTS ctr_log "
                  "(tag VARCHAR(40) PRIMARY KEY, machine VARCHAR(4) NOT NULL)")
        dsql("A", "DELETE FROM ctr_log")
        sh(["dolt", "add", "-A"], cwd=MACHINES["A"])
        sh(["dolt", "commit", "-m", "ctr_log"], cwd=MACHINES["A"])
        sh(["dolt", "push", "origin", "main"], cwd=MACHINES["A"])
    sync("B")
    total = NA + NB
    jobs = ([("A", f"INSERT INTO ctr_log VALUES ('A-{i}','A')") for i in range(NA)]
            + [("B", f"INSERT INTO ctr_log VALUES ('B-{i}','B')") for i in range(NB)])
    outs = run_fleet(jobs)
    ok, fails = summarize(outs)
    for m in MACHINES:
        ensure_clean(m)
        sync(m)
    n_a = scalar("A", "SELECT COUNT(*) AS c FROM ctr_log")
    n_b = scalar("B", "SELECT COUNT(*) AS c FROM ctr_log")
    check("D5b append-only rows with unique keys ARE exact across machines",
          n_a == total and n_b == total,
          f"{total} agents inserted; {ok} reported ok, {len(fails)} reported failure\n"
          f"COUNT(*): A sees {n_a}, B sees {n_b} (exact = {total})\n"
          f"NOTE all {total} rows landed even though {len(fails)} agents reported\n"
          "  failure: on a SHARED clone a push publishes everything committed locally,\n"
          "  including siblings' work. So an agent whose own push was rejected may still\n"
          "  have its write published by the next agent's push -- 'my push failed' does\n"
          "  NOT mean 'my work was not published'. Retries must be idempotent.\n"
          "=> distinct primary keys cannot coalesce, so nothing is absorbed. Prefer\n"
          "   append-only + COUNT(*)/aggregate over mutable counter cells; it is also\n"
          "   what makes the count-drift class impossible in the first place.")


def d6_lease_across_all_three_layers():
    """The factory lease under simultaneous contention from BOTH devs' fleets.
    Exactly one holder must result, and both machines must agree on who."""
    for m in MACHINES:
        ensure_clean(m)
        sync(m)
    with clone_write_lock(MACHINES["A"], timeout=300):
        dsql("A", "UPDATE factory_lock SET holder=NULL WHERE id=1")
        sh(["dolt", "add", "-A"], cwd=MACHINES["A"])
        sh(["dolt", "commit", "-m", "release lease"], cwd=MACHINES["A"])
        sh(["dolt", "push", "origin", "main"], cwd=MACHINES["A"])
    sync("B")
    # Each agent writes a UNIQUE holder (per the token rule) and pushes.
    jobs = ([("A", f"UPDATE factory_lock SET holder='A-a{i}' WHERE id=1 AND holder IS NULL")
             for i in range(NA)]
            + [("B", f"UPDATE factory_lock SET holder='B-b{i}' WHERE id=1 AND holder IS NULL")
               for i in range(NB)])
    outs = run_fleet(jobs)
    pushed = [f"{m}:{o}" for m, o in outs if o.startswith("OK:pushed")]
    for m in MACHINES:
        ensure_clean(m)
        sync(m)
    ha = csv("A", "SELECT holder FROM factory_lock WHERE id=1")
    hb = csv("B", "SELECT holder FROM factory_lock WHERE id=1")
    holder_a = ha[0]["holder"] if ha else None
    holder_b = hb[0]["holder"] if hb else None
    one_holder = holder_a not in (None, "", "NULL") and holder_a == holder_b
    check("D6 factory lease: 8 agents across 2 machines -> ONE holder, both agree",
          one_holder,
          f"agents whose lease write reached the remote: {len(pushed)}\n"
          f"final holder: A sees {holder_a!r}, B sees {holder_b!r}, agree={holder_a == holder_b}\n"
          "NOTE the guard `AND holder IS NULL` is evaluated against each agent's freshly\n"
          "  PULLED base, so *who* wins is not deterministic. That is fine for a lease,\n"
          "  but a loser learns it lost only by RE-READING after its push -- an agent\n"
          "  must never assume a successful push meant it acquired the lease.")


def d7_staleness_window():
    """How wrong can dev B be before pulling? This is the real operational cost of
    a no-daemon topology."""
    for m in MACHINES:
        ensure_clean(m)
        sync(m)
    target = "BC-2.09.001"
    p = subprocess.run([sys.executable, SELF, "--agent", "A",
                        f"UPDATE bc SET title='changed by devA' WHERE bc_id='{target}'",
                        "sync", "3"], capture_output=True, text=True, timeout=300)
    before = rows_of("B", f"SELECT bc_id,title FROM bc WHERE bc_id='{target}'")
    t0 = time.time()
    sync("B")
    pull_ms = (time.time() - t0) * 1000
    after = rows_of("B", f"SELECT bc_id,title FROM bc WHERE bc_id='{target}'")
    stale = bool(before) and before[0][1] != "changed by devA"
    fresh = bool(after) and after[0][1] == "changed by devA"
    check("D7 staleness: dev B reads the OLD value until it pulls",
          p.stdout.strip().startswith("OK") and stale and fresh,
          f"A pushed={p.stdout.strip()}\n"
          f"B before pull: {before}  (stale={stale})\n"
          f"B after  pull: {after}   (pull took {pull_ms:.0f}ms)\n"
          "=> there is NO cross-machine read consistency without a pull. Agents must\n"
          "   pull at the start of a unit of work; anything cached is a stale read.")


def d8_unresolved_conflict_wedges_the_machine():
    """THE OPERATIONAL LANDMINE. If any agent leaves an unresolved merge conflict,
    EVERY later commit on that machine fails -- all of that dev's agents are blocked,
    with an error that does not mention the real cause.

    Also verifies the guard: an agent that aborts the merge leaves the clone usable.
    """
    for m in MACHINES:
        ensure_clean(m)
        sync(m)
    target = "BC-1.03.001"
    # Diverge: A pushes one value, B writes another locally.
    subprocess.run([sys.executable, SELF, "--agent", "A",
                    f"UPDATE bc SET capability='CAP-WEDGE-A' WHERE bc_id='{target}'",
                    "sync", "3"], capture_output=True, text=True, timeout=300)
    subprocess.run([sys.executable, SELF, "--agent", "B",
                    f"UPDATE bc SET capability='CAP-WEDGE-B' WHERE bc_id='{target}'",
                    "local", "1"], capture_output=True, text=True, timeout=300)
    # Pull WITHOUT the guard -> leaves B conflicted.
    sh(["dolt", "pull", "origin", "main"], cwd=MACHINES["B"])
    wedged = conflicted("B")
    # Now an UNRELATED agent on machine B tries to do ordinary work.
    p = subprocess.run([sys.executable, SELF, "--agent", "B",
                        "UPDATE bc SET notes='unrelated work' WHERE bc_id='BC-2.05.001'",
                        "sync", "1"], capture_output=True, text=True, timeout=300)
    blocked = not (p.stdout or "").strip().startswith("OK")

    # The guarded path. Real divergence is required: B must commit locally FIRST,
    # and only THEN must A push a different value to the same cell. (Syncing B to
    # origin/main first would make B's commit a descendant, so the pull would
    # fast-forward and no conflict could occur.)
    ensure_clean("B")
    sync("B")
    subprocess.run([sys.executable, SELF, "--agent", "B",
                    f"UPDATE bc SET capability='CAP-WEDGE-B2' WHERE bc_id='{target}'",
                    "local", "1"], capture_output=True, text=True, timeout=300)
    subprocess.run([sys.executable, SELF, "--agent", "A",
                    f"UPDATE bc SET capability='CAP-WEDGE-A2' WHERE bc_id='{target}'",
                    "sync", "3"], capture_output=True, text=True, timeout=300)
    g = subprocess.run([sys.executable, SELF, "--agent", "B",
                        f"UPDATE bc SET capability='CAP-WEDGE-B3' WHERE bc_id='{target}'",
                        "sync", "1"], capture_output=True, text=True, timeout=300)
    guard_fired = "conflict-aborted" in (g.stdout or "")
    still_clean = not conflicted("B")
    # While the divergence stands, agents must still decline -- but with the
    # INFORMATIVE reason, not a misleading staging error. That is "correctly
    # blocked", which is different from "wedged".
    p2 = subprocess.run([sys.executable, SELF, "--agent", "B",
                         "UPDATE bc SET notes='work during divergence' WHERE bc_id='BC-2.06.001'",
                         "sync", "2"], capture_output=True, text=True, timeout=300)
    informative = "conflict-aborted" in (p2.stdout or "")
    # Once the divergence is actually resolved, work proceeds again.
    ensure_clean("B")
    sync("B")
    p3 = subprocess.run([sys.executable, SELF, "--agent", "B",
                         "UPDATE bc SET notes='work after resolution' WHERE bc_id='BC-2.07.001'",
                         "sync", "3"], capture_output=True, text=True, timeout=300)
    recovered = (p3.stdout or "").strip().startswith("OK")
    check("D8 an unresolved conflict WEDGES the machine; the guard downgrades it to "
          "a clean, informative block",
          wedged and blocked and guard_fired and still_clean and informative and recovered,
          f"UNGUARDED: pull left B conflicted = {wedged}\n"
          f"  an UNRELATED agent on B was blocked = {blocked}\n"
          f"  its error: {(p.stdout or '').strip()[:90]}\n"
          f"    ^ note it blames staging/uncommitted changes, NOT the conflict\n"
          f"GUARDED: agent aborted the merge = {guard_fired}; clone left clean = {still_clean}\n"
          f"  next agent declines with the informative reason = {informative}\n"
          f"  after the divergence is resolved, work proceeds = {recovered}\n"
          "=> MANDATORY: every agent must abort (or resolve) on conflict. Unguarded, one\n"
          "   careless agent wedges its whole machine with a misleading error. Guarded,\n"
          "   the machine stays clean and the divergence is reported for resolution --\n"
          "   but SOMETHING still has to resolve it before that dev can sync again.")


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--agent":
        sys.exit(agent_main(sys.argv[2:]))
    print("=" * 78)
    print("Two devs, two machines, one repo, multiple agents each")
    print("=" * 78)
    setup()
    for t in (d1_composite_disjoint, d2_same_row_different_fields,
              d3_same_cell_conflict_surfaces, d4_identical_write_across_machines,
              d5_counter_across_machines, d5b_append_only_is_safe,
              d6_lease_across_all_three_layers,
              d7_staleness_window, d8_unresolved_conflict_wedges_the_machine):
        try:
            t()
        except Exception:
            import traceback
            check(f"{t.__name__} (ERROR)", False, traceback.format_exc()[-500:])
        print()
    n = sum(1 for _, ok, _ in RESULTS if ok)
    print("=" * 78)
    print(f"{n}/{len(RESULTS)} passed")
    for nm, ok, _ in RESULTS:
        if not ok:
            print(f"  FAILED: {nm}")
    sys.exit(0 if n == len(RESULTS) else 1)


if __name__ == "__main__":
    main()
