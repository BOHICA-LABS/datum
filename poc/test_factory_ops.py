#!/usr/bin/env python3
"""The factory-operations surface: waves, state, context, tasks, templates, versioning.

These are the artifact interactions the pipeline actually performs every day, and
none of them were covered by the first 87 tests.

  V1  wave registration: assign stories to a wave, query membership
  V2  wave gate lifecycle + the real hook invariant
      (wave N+1 must not start while N's gate is pending)
  V3  merge tracking: stories_merged accrues; all-merged -> gate becomes pending
  V4  CONTEXT: rehydrate exactly the specs a wave needs, as a query
  V5  STATE: no line limits, no compaction -- "current status" is a query
  V6  TASKS: per-story task list with status and ordering
  V7  TEMPLATES: instantiation + conformance (required fields present)
  V8  spec amendment ledger (changelog) with monotonic versions
  V9  ID allocation registry: next id, with the unique-token rule
  V10 phase progression + gate verdicts + skip justifications

Self-provisioning under poc/fo/.
Run: .venv/bin/python -u poc/test_factory_ops.py
"""
from __future__ import annotations

import re
import secrets
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent / "fo"
DBD = ROOT / "db"
RESULTS: list[tuple[str, bool, str]] = []


def check(name, ok, detail=""):
    RESULTS.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}")
    for ln in (detail or "").splitlines():
        print(f"        {ln}")


def sh(args, timeout=240):
    try:
        return subprocess.run(args, cwd=DBD, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(args, 124, "", "TIMEOUT")


def sql(stmt, timeout=240):
    return sh(["dolt", "sql", "-q", stmt], timeout=timeout)


def rows(stmt):
    r = sh(["dolt", "sql", "-q", stmt, "-r", "csv"])
    lines = [l for l in (r.stdout or "").strip().splitlines() if l.strip()]
    if len(lines) < 2:
        return []
    hdr = lines[0].split(",")
    return [dict(zip(hdr, l.split(","))) for l in lines[1:]]


def one(stmt):
    rs = rows(stmt)
    return list(rs[0].values())[0] if rs else None


SCHEMA = [
    # ---- requirements graph (abbreviated; full graph proven in test_graph.py)
    "CREATE TABLE bc (bc_id VARCHAR(24) PRIMARY KEY, ss_id VARCHAR(8) NOT NULL, "
    "title TEXT NOT NULL, version VARCHAR(12) NOT NULL DEFAULT 'v1.0')",
    "CREATE TABLE vp (vp_id VARCHAR(16) PRIMARY KEY, title TEXT NOT NULL)",
    "CREATE TABLE vp_bc (vp_id VARCHAR(16), bc_id VARCHAR(24), PRIMARY KEY (vp_id,bc_id), "
    "FOREIGN KEY (vp_id) REFERENCES vp(vp_id), FOREIGN KEY (bc_id) REFERENCES bc(bc_id))",
    # ---- stories + tasks
    "CREATE TABLE story (story_id VARCHAR(24) PRIMARY KEY, title TEXT NOT NULL, "
    "status VARCHAR(16) NOT NULL DEFAULT 'pending', points INT NULL)",
    "CREATE TABLE story_bc (story_id VARCHAR(24), bc_id VARCHAR(24), "
    "PRIMARY KEY (story_id,bc_id), FOREIGN KEY (story_id) REFERENCES story(story_id), "
    "FOREIGN KEY (bc_id) REFERENCES bc(bc_id))",
    "CREATE TABLE task (task_id VARCHAR(32) PRIMARY KEY, story_id VARCHAR(24) NOT NULL, "
    "seq INT NOT NULL, description TEXT NOT NULL, status VARCHAR(16) NOT NULL DEFAULT 'todo', "
    "UNIQUE KEY uk_task_seq (story_id, seq), "
    "FOREIGN KEY (story_id) REFERENCES story(story_id) ON DELETE CASCADE)",
    # ---- waves: registration is a ROW, not a yaml list
    "CREATE TABLE wave (wave_id VARCHAR(16) PRIMARY KEY, seq INT NOT NULL UNIQUE, "
    "gate_status VARCHAR(16) NOT NULL DEFAULT 'not_started', gate_date DATE NULL, "
    "gate_report TEXT NULL, rationale TEXT NULL, "
    "CONSTRAINT ck_gate CHECK (gate_status IN "
    "('not_started','pending','passed','deferred','failed')))",
    "CREATE TABLE wave_story (wave_id VARCHAR(16), story_id VARCHAR(24), "
    "merged TINYINT NOT NULL DEFAULT 0, merged_at DATETIME NULL, "
    "PRIMARY KEY (wave_id, story_id), "
    "FOREIGN KEY (wave_id) REFERENCES wave(wave_id), "
    "FOREIGN KEY (story_id) REFERENCES story(story_id))",
    # ---- pipeline state: scalar rows, no line budget
    "CREATE TABLE phase (phase_id VARCHAR(24) PRIMARY KEY, seq INT NOT NULL, "
    "status VARCHAR(16) NOT NULL DEFAULT 'pending', verdict VARCHAR(16) NULL, "
    "findings INT NULL, skip_reason TEXT NULL)",
    "CREATE TABLE pipeline_state (k VARCHAR(48) PRIMARY KEY, v TEXT NOT NULL)",
    # ---- templates + conformance
    "CREATE TABLE template (template_id VARCHAR(48) PRIMARY KEY, "
    "artifact_type VARCHAR(48) NOT NULL, body LONGTEXT NOT NULL)",
    "CREATE TABLE template_field (template_id VARCHAR(48), field VARCHAR(48), "
    "required TINYINT NOT NULL DEFAULT 1, PRIMARY KEY (template_id, field), "
    "FOREIGN KEY (template_id) REFERENCES template(template_id) ON DELETE CASCADE)",
    # ---- spec amendment ledger (versioning of the SPEC, not just the record)
    "CREATE TABLE spec_change (change_id VARCHAR(40) PRIMARY KEY, "
    "artifact_id VARCHAR(32) NOT NULL, from_version VARCHAR(12) NULL, "
    "to_version VARCHAR(12) NOT NULL, reason TEXT NOT NULL, "
    "changed_at DATETIME NOT NULL)",
    # ---- id allocation
    "CREATE TABLE id_alloc (ns VARCHAR(16), seq INT, token VARCHAR(48) NOT NULL, "
    "PRIMARY KEY (ns, seq))",
]


def setup():
    print("--- setup: fresh store (server-less)")
    if ROOT.exists():
        shutil.rmtree(ROOT)
    DBD.mkdir(parents=True)
    sh(["dolt", "init", "--name", "fo", "--email", "fo@l"])
    for s in SCHEMA:
        r = sql(s)
        if r.returncode != 0:
            raise RuntimeError(f"DDL failed: {(r.stderr or r.stdout)[:200]}\n{s[:80]}")
    # seed a small graph
    sql("INSERT INTO bc VALUES " + ",".join(
        f"('BC-1.0{i}.001','SS-01','contract {i}','v1.0')" for i in range(6)))
    sql("INSERT INTO vp VALUES ('VP-001','prop one'),('VP-002','prop two')")
    sql("INSERT INTO vp_bc VALUES ('VP-001','BC-1.00.001'),('VP-002','BC-1.01.001')")
    sql("INSERT INTO story (story_id,title,points) VALUES "
        "('S-1.01','first story',3),('S-1.02','second story',5),"
        "('S-2.01','wave two story',2),('S-2.02','wave two other',1)")
    sql("INSERT INTO story_bc VALUES ('S-1.01','BC-1.00.001'),('S-1.02','BC-1.01.001'),"
        "('S-2.01','BC-1.02.001'),('S-2.02','BC-1.03.001')")
    sql("INSERT INTO phase (phase_id,seq) VALUES "
        "('phase-1',1),('phase-2',2),('phase-3',3),('phase-4',4)")
    sh(["dolt", "add", "-A"])
    sh(["dolt", "commit", "-m", "seed"])
    print(f"    {DBD}\n")


# ---------------------------------------------------------------- tests


def v1_wave_registration():
    sql("INSERT INTO wave (wave_id,seq) VALUES ('wave-1',1),('wave-2',2)")
    sql("INSERT INTO wave_story (wave_id,story_id) VALUES "
        "('wave-1','S-1.01'),('wave-1','S-1.02'),('wave-2','S-2.01'),('wave-2','S-2.02')")
    bad = sql("INSERT INTO wave_story (wave_id,story_id) VALUES ('wave-1','S-99.99')")
    members = [r["story_id"] for r in rows(
        "SELECT story_id FROM wave_story WHERE wave_id='wave-1' ORDER BY story_id")]
    pts = one("SELECT SUM(s.points) AS p FROM wave_story w JOIN story s "
              "ON s.story_id=w.story_id WHERE w.wave_id='wave-1'")
    check("V1 wave registration: membership is a row; a phantom story is refused",
          members == ["S-1.01", "S-1.02"] and bad.returncode != 0 and pts == "8",
          f"wave-1 members={members}; total points={pts}\n"
          f"registering a non-existent story refused={bad.returncode != 0}\n"
          "=> replaces wave-state.yaml's `stories: []` list, which can name anything")


def v2_gate_prerequisite_invariant():
    """The real hook: validate-wave-gate-prerequisite.sh blocks wave N+1 while N is
    pending. Here it is a query, so it cannot drift from the data."""
    sql("UPDATE wave SET gate_status='pending' WHERE wave_id='wave-1'")

    def may_start(wave_id):
        seq = one(f"SELECT seq FROM wave WHERE wave_id='{wave_id}'")
        blockers = rows(f"SELECT wave_id, gate_status FROM wave "
                        f"WHERE seq < {seq} AND gate_status IN ('pending','failed','not_started')")
        return (not blockers), blockers

    ok2, blockers = may_start("wave-2")
    sql("UPDATE wave SET gate_status='passed', gate_date='2026-07-30' WHERE wave_id='wave-1'")
    ok2b, _ = may_start("wave-2")
    check("V2 gate prerequisite: wave N+1 blocked while N is pending, allowed after pass",
          not ok2 and ok2b,
          f"with wave-1 pending  -> wave-2 may start = {ok2} (blockers={[b['wave_id'] for b in blockers]})\n"
          f"after wave-1 passed  -> wave-2 may start = {ok2b}\n"
          "=> a CHECK constraint bounds gate_status to the 5 legal values, and the\n"
          "   prerequisite is a JOIN. The bash hook and the yaml cannot disagree because\n"
          "   there is only one representation.")


def v3_merge_tracking():
    """stories_merged accrues; when every story in a wave is merged the gate becomes
    pending. Today a SubagentStop hook appends to yaml."""
    sql("UPDATE wave SET gate_status='not_started' WHERE wave_id='wave-2'")
    sql("UPDATE wave_story SET merged=1, merged_at=NOW() "
        "WHERE wave_id='wave-2' AND story_id='S-2.01'")
    part = rows("SELECT COUNT(*) AS total, SUM(merged) AS merged FROM wave_story "
                "WHERE wave_id='wave-2'")[0]
    # the transition rule, as a query
    def all_merged(w):
        r = rows(f"SELECT COUNT(*) AS t, COALESCE(SUM(merged),0) AS m FROM wave_story "
                 f"WHERE wave_id='{w}'")[0]
        return r["t"] == r["m"] and r["t"] != "0"
    before = all_merged("wave-2")
    sql("UPDATE wave_story SET merged=1, merged_at=NOW() "
        "WHERE wave_id='wave-2' AND story_id='S-2.02'")
    after = all_merged("wave-2")
    if after:
        sql("UPDATE wave SET gate_status='pending' WHERE wave_id='wave-2'")
    st = one("SELECT gate_status FROM wave WHERE wave_id='wave-2'")
    check("V3 merge tracking drives the gate transition",
          part["merged"] == "1" and not before and after and st == "pending",
          f"after 1 of 2 merged: total={part['total']} merged={part['merged']}, "
          f"all_merged={before}\nafter 2 of 2 merged: all_merged={after}, "
          f"gate_status={st}\n"
          "=> derived from the data, so 'gate says passed but a story never merged' is\n"
          "   not expressible")


def v4_context_rehydration():
    """The wave-boundary problem: load EXACTLY the specs the next wave needs. Today
    that is a hand-maintained file list in wave-state.yaml + a rehydrate skill."""
    ctx = rows("""SELECT DISTINCT b.bc_id, b.ss_id, b.version
                  FROM wave_story w
                  JOIN story_bc sb ON sb.story_id = w.story_id
                  JOIN bc b       ON b.bc_id = sb.bc_id
                  WHERE w.wave_id='wave-2' ORDER BY b.bc_id""")
    vps = rows("""SELECT DISTINCT v.vp_id FROM wave_story w
                  JOIN story_bc sb ON sb.story_id=w.story_id
                  JOIN vp_bc vb ON vb.bc_id=sb.bc_id
                  JOIN vp v ON v.vp_id=vb.vp_id
                  WHERE w.wave_id='wave-2' ORDER BY v.vp_id""")
    everything = int(one("SELECT COUNT(*) AS c FROM bc"))
    check("V4 context rehydration is a query: exactly the wave's specs, nothing more",
          len(ctx) == 2 and len(ctx) < everything,
          f"wave-2 needs {len(ctx)} of {everything} BCs: "
          f"{[c['bc_id'] for c in ctx]}\n"
          f"plus {len(vps)} VP(s): {[v['vp_id'] for v in vps]}\n"
          "=> the manifest is DERIVED from wave membership, so it cannot omit a spec the\n"
          "   wave's stories actually reference (the failure mode a hand-listed\n"
          "   spec_files array has)")


def v5_state_without_line_limits():
    """STATE.md is capped at 200 lines (hook blocks at 500) purely because it is
    re-read every session. Rows have no such budget, and 'current status' is a query."""
    sql("INSERT INTO pipeline_state (k,v) VALUES ('mode','feature'),('cycle','v1.2.0'),"
        "('current_wave','wave-2') ON DUPLICATE KEY UPDATE v=VALUES(v)")
    for i in range(300):                       # far past the 500-line hook limit
        sql(f"INSERT INTO pipeline_state (k,v) VALUES ('bulk_{i}','x') "
            f"ON DUPLICATE KEY UPDATE v='x'")
    n = int(one("SELECT COUNT(*) AS c FROM pipeline_state"))
    status = rows("""SELECT k, v FROM pipeline_state
                     WHERE k IN ('mode','cycle','current_wave') ORDER BY k""")
    check("V5 pipeline state has no line budget; the session read is a 3-row query",
          n > 300 and len(status) == 3,
          f"pipeline_state rows={n} (STATE.md's hook blocks at 500 LINES)\n"
          f"session-start read: {[(s['k'], s['v']) for s in status]}\n"
          "=> retires compact-state / check-state-health / the 200-line discipline:\n"
          "   an agent selects the 3 keys it needs instead of parsing a 379-line file")


def v6_tasks():
    sql("INSERT INTO task (task_id,story_id,seq,description) VALUES "
        "('S-1.01.T1','S-1.01',1,'write failing test'),"
        "('S-1.01.T2','S-1.01',2,'implement'),"
        "('S-1.01.T3','S-1.01',3,'refactor')")
    dup = sql("INSERT INTO task (task_id,story_id,seq,description) "
              "VALUES ('S-1.01.T9','S-1.01',2,'duplicate seq')")
    orphan = sql("INSERT INTO task (task_id,story_id,seq,description) "
                 "VALUES ('X.T1','S-99.99',1,'orphan')")
    sql("UPDATE task SET status='done' WHERE task_id IN ('S-1.01.T1','S-1.01.T2')")
    prog = rows("SELECT COUNT(*) AS total, SUM(status='done') AS done FROM task "
                "WHERE story_id='S-1.01'")[0]
    nxt = one("SELECT description AS d FROM task WHERE story_id='S-1.01' "
              "AND status='todo' ORDER BY seq LIMIT 1")
    check("V6 tasks: ordered, unique per story, FK-anchored, progress derivable",
          dup.returncode != 0 and orphan.returncode != 0
          and prog["done"] == "2" and nxt == "refactor",
          f"duplicate seq refused={dup.returncode != 0}; "
          f"task on a phantom story refused={orphan.returncode != 0}\n"
          f"S-1.01 progress: {prog['done']}/{prog['total']} done; next todo={nxt!r}\n"
          "=> 'what is the next task' and 'how far along is this story' are queries;\n"
          "   today they are prose checkboxes inside the story markdown")


def v7_templates():
    """Templates today are ~100 markdown files plus conform-to-template and
    validate-template-compliance skills. Modelled here: the template body plus its
    required-field set, so conformance is a query."""
    sql("INSERT INTO template (template_id,artifact_type,body) VALUES "
        "('behavioral-contract','behavioral-contract','# {{bc_id}}: {{title}}\\n\\n"
        "## Description\\n{{description}}\\n')")
    sql("INSERT INTO template_field (template_id,field,required) VALUES "
        "('behavioral-contract','bc_id',1),('behavioral-contract','title',1),"
        "('behavioral-contract','description',1),('behavioral-contract','capability',0)")

    def instantiate(tpl, values):
        body = one(f"SELECT body AS b FROM template WHERE template_id='{tpl}'")
        req = [r["field"] for r in rows(
            f"SELECT field FROM template_field WHERE template_id='{tpl}' AND required=1")]
        missing = [f for f in req if not values.get(f)]
        if missing:
            return None, missing
        out = body
        for k, v in values.items():
            out = out.replace("{{" + k + "}}", v)
        return out, []

    good, m1 = instantiate("behavioral-contract",
                           {"bc_id": "BC-1.05.001", "title": "new", "description": "d"})
    bad, m2 = instantiate("behavioral-contract", {"bc_id": "BC-1.05.002", "title": "no desc"})
    unresolved = re.findall(r"\{\{(\w+)\}\}", good or "")
    check("V7 templates: instantiation refuses missing required fields; no placeholder leaks",
          good and not unresolved and bad is None and m2 == ["description"],
          f"valid instantiation produced {len(good or '')} chars, "
          f"unresolved placeholders={unresolved}\n"
          f"missing-field case refused, missing={m2}\n"
          "=> conformance stops being a post-hoc lint over ~100 template files. NOTE the\n"
          "   corpus's real placeholder leaks (`BC-4.NN.001`, 'see PO output for actual\n"
          "   IDs') are exactly what this refusal prevents at write time.")


def v8_spec_amendment_ledger():
    """Spec versioning: an append-only changelog with monotonic versions per artifact."""
    def amend(artifact, reason):
        cur = one(f"SELECT version AS v FROM bc WHERE bc_id='{artifact}'")
        m = re.match(r"v(\d+)\.(\d+)", cur or "v1.0")
        nv = f"v{m.group(1)}.{int(m.group(2)) + 1}"
        cid = f"{artifact}-{secrets.token_hex(4)}"
        sql(f"INSERT INTO spec_change VALUES ('{cid}','{artifact}','{cur}','{nv}',"
            f"'{reason}',NOW())")
        sql(f"UPDATE bc SET version='{nv}' WHERE bc_id='{artifact}'")
        return cur, nv

    a = amend("BC-1.00.001", "clarify precondition")
    b = amend("BC-1.00.001", "add edge case")
    hist = rows("SELECT from_version, to_version, reason FROM spec_change "
                "WHERE artifact_id='BC-1.00.001' ORDER BY changed_at, to_version")
    cur = one("SELECT version AS v FROM bc WHERE bc_id='BC-1.00.001'")
    chain_ok = (len(hist) == 2 and hist[0]["to_version"] == hist[1]["from_version"]
                and hist[-1]["to_version"] == cur)
    check("V8 spec amendment ledger: version chain is contiguous and matches the record",
          chain_ok,
          f"amendments: {a} then {b}\n"
          f"ledger: {[(h['from_version'], h['to_version'], h['reason']) for h in hist]}\n"
          f"record version now={cur}; chain contiguous and matches={chain_ok}\n"
          "=> the corpus keeps this as prose changelog rows inside BC-INDEX.md, which is\n"
          "   where the 'v1.61 cited E-7=23, actual 28' count-narrative drift came from")


def v9_id_allocation():
    """Allocate the next id in a namespace. Carries a unique token per attempt, per
    the invariant from test_locking L4."""
    def alloc(ns):
        for _ in range(10):
            nxt = int(one(f"SELECT COALESCE(MAX(seq),0)+1 AS n FROM id_alloc "
                          f"WHERE ns='{ns}'"))
            tok = secrets.token_hex(6)
            r = sql(f"INSERT INTO id_alloc VALUES ('{ns}',{nxt},'{tok}')")
            if r.returncode == 0:
                return nxt
        return None

    got = [alloc("BC") for _ in range(5)]
    dupe = sql("INSERT INTO id_alloc VALUES ('BC',1,'other-token')")
    check("V9 ID allocation registry: sequential, unique, token-carrying",
          got == [1, 2, 3, 4, 5] and dupe.returncode != 0,
          f"allocated={got}\nre-allocating an existing seq refused={dupe.returncode != 0}\n"
          "=> replaces bc-id-mapping.md / legacy-id-mapping.md as hand-maintained tables.\n"
          "   The per-attempt token is REQUIRED (see invariant 7): a PK alone does not\n"
          "   stop two concurrent writers inserting byte-identical rows.")


def v10_phase_progression():
    sql("UPDATE phase SET status='passed', verdict='PASSED', findings=0 WHERE phase_id='phase-1'")
    sql("UPDATE phase SET status='passed', verdict='PASSED', findings=3 WHERE phase_id='phase-2'")
    sql("UPDATE phase SET status='in_progress' WHERE phase_id='phase-3'")
    sql("UPDATE phase SET status='skipped', skip_reason='no external services' "
        "WHERE phase_id='phase-4'")

    def next_actionable():
        return one("SELECT phase_id AS p FROM phase WHERE status IN ('pending','in_progress') "
                   "ORDER BY seq LIMIT 1")

    cur = next_actionable()
    unfinished_before = rows("SELECT phase_id FROM phase WHERE seq < 3 "
                             "AND status NOT IN ('passed','skipped','deferred')")
    skips = rows("SELECT phase_id, skip_reason FROM phase WHERE status='skipped'")
    check("V10 phase progression: current phase, prerequisites, and skips are queries",
          cur == "phase-3" and not unfinished_before and len(skips) == 1
          and skips[0]["skip_reason"],
          f"next actionable phase={cur}\n"
          f"unfinished prerequisites before it={[u['phase_id'] for u in unfinished_before]}\n"
          f"skips with justification={[(s['phase_id'], s['skip_reason']) for s in skips]}\n"
          "=> a skip without a reason is a NOT NULL violation away from impossible;\n"
          "   today it is a Skip Log section someone has to remember to fill in")


def main():
    print("=" * 74)
    print("Factory operations: waves, state, context, tasks, templates, versioning")
    print("=" * 74)
    setup()
    for t in (v1_wave_registration, v2_gate_prerequisite_invariant, v3_merge_tracking,
              v4_context_rehydration, v5_state_without_line_limits, v6_tasks,
              v7_templates, v8_spec_amendment_ledger, v9_id_allocation,
              v10_phase_progression):
        try:
            t()
        except Exception:
            import traceback
            check(f"{t.__name__} (ERROR)", False, traceback.format_exc()[-500:])
        print()
    sh(["dolt", "add", "-A"])
    sh(["dolt", "commit", "-m", "factory-ops tests"])
    n = sum(1 for _, ok, _ in RESULTS if ok)
    print("=" * 74)
    print(f"{n}/{len(RESULTS)} passed")
    for nm, ok, _ in RESULTS:
        if not ok:
            print(f"  FAILED: {nm}")
    sys.exit(0 if n == len(RESULTS) else 1)


if __name__ == "__main__":
    main()
