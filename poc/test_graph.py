#!/usr/bin/env python3
"""Relationship-graph tests: full spec chaining.

The question these answer: "this story maps to these BCs and is also related to
these VPs, etc." — i.e. can the store traverse the whole traceability chain, and
does it hold the chain's integrity?

Run: .venv/bin/python -u poc/test_graph.py
"""
from __future__ import annotations

import sys

import pymysql

PORT, DB = 3308, "factory_artifacts"
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
            return []


def check(name, ok, detail=""):
    RESULTS.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}")
    for ln in (detail or "").splitlines():
        print(f"        {ln}")


# ------------------------------------------------------------------ G1


def g1_full_chain():
    """One query: story -> BC -> VP -> (DI, NFR), plus epic and subsystem.
    This is the artifact that does not exist in the markdown corpus at all."""
    c = conn()
    sid = q(c, """SELECT s.story_id FROM story s
                  JOIN story_bc sb ON sb.story_id=s.story_id
                  JOIN vp_bc vb   ON vb.bc_id=sb.bc_id
                  JOIN vp_nfr vn  ON vn.vp_id=vb.vp_id
                  GROUP BY s.story_id ORDER BY COUNT(*) DESC LIMIT 1""")
    if not sid:
        return check("G1 full chain story->BC->VP->NFR/DI", False, "no story spans the chain")
    sid = sid[0]["story_id"]
    chain = q(c, """SELECT s.story_id, s.epic_id, e.title AS epic,
                           sb.bc_id, b.ss_id,
                           vb.vp_id, v.proof_method,
                           GROUP_CONCAT(DISTINCT vn.nfr_id) AS nfrs,
                           GROUP_CONCAT(DISTINCT vd.di_id)  AS dis
                    FROM story s
                    LEFT JOIN epic e       ON e.epic_id = s.epic_id
                    JOIN story_bc sb       ON sb.story_id = s.story_id
                    JOIN bc b              ON b.bc_id = sb.bc_id
                    LEFT JOIN vp_bc vb     ON vb.bc_id = sb.bc_id
                    LEFT JOIN vp v         ON v.vp_id = vb.vp_id
                    LEFT JOIN vp_nfr vn    ON vn.vp_id = vb.vp_id
                    LEFT JOIN vp_di vd     ON vd.vp_id = vb.vp_id
                    WHERE s.story_id = %s
                    GROUP BY s.story_id, s.epic_id, e.title, sb.bc_id, b.ss_id,
                             vb.vp_id, v.proof_method
                    ORDER BY sb.bc_id LIMIT 6""", (sid,))
    d = [f"story {sid} (epic {chain[0]['epic_id']}: {str(chain[0]['epic'])[:34]})"]
    for r in chain:
        d.append(f"  {r['bc_id']} [{r['ss_id']}] -> {r['vp_id']} ({r['proof_method']}) "
                 f"NFR={r['nfrs']} DI={r['dis']}")
    c.close()
    check("G1 full chain: story -> epic / BC -> subsystem / VP -> NFR + DI in ONE query",
          len(chain) > 0 and any(r["vp_id"] for r in chain), "\n".join(d))


def g2_reverse_impact():
    """Reverse traversal: given a BC, what verifies it and what implements it.
    This is the 'blast radius' question asked before changing a contract."""
    c = conn()
    r = q(c, """SELECT b.bc_id,
                       (SELECT COUNT(*) FROM vp_bc   WHERE bc_id=b.bc_id) vps,
                       (SELECT COUNT(*) FROM story_bc WHERE bc_id=b.bc_id) stories
                FROM bc b
                WHERE (SELECT COUNT(*) FROM vp_bc WHERE bc_id=b.bc_id) > 0
                  AND (SELECT COUNT(*) FROM story_bc WHERE bc_id=b.bc_id) > 0
                ORDER BY vps DESC, stories DESC LIMIT 1""")
    if not r:
        return check("G2 reverse impact", False, "no BC has both VP and story edges")
    bc = r[0]["bc_id"]
    vps = [x["vp_id"] for x in q(c, "SELECT vp_id FROM vp_bc WHERE bc_id=%s ORDER BY vp_id", (bc,))]
    sts = [x["story_id"] for x in q(c, "SELECT story_id FROM story_bc WHERE bc_id=%s ORDER BY story_id", (bc,))]
    c.close()
    check("G2 reverse impact: BC -> verifying VPs + implementing stories",
          len(vps) > 0 and len(sts) > 0,
          f"{bc}\n  verified by : {vps}\n  implemented : {sts}")


def g3_coverage_gaps():
    """Coverage questions no artifact in the corpus answers."""
    c = conn()
    tot = q(c, "SELECT COUNT(*) n FROM bc")[0]["n"]
    unverified = q(c, "SELECT COUNT(*) n FROM bc b WHERE NOT EXISTS (SELECT 1 FROM vp_bc v WHERE v.bc_id=b.bc_id)")[0]["n"]
    unimpl = q(c, "SELECT COUNT(*) n FROM bc b WHERE NOT EXISTS (SELECT 1 FROM story_bc s WHERE s.bc_id=b.bc_id)")[0]["n"]
    vp_no_bc = q(c, "SELECT COUNT(*) n FROM vp v WHERE NOT EXISTS (SELECT 1 FROM vp_bc x WHERE x.vp_id=v.vp_id)")[0]["n"]
    st_no_bc = q(c, "SELECT COUNT(*) n FROM story s WHERE NOT EXISTS (SELECT 1 FROM story_bc x WHERE x.story_id=s.story_id)")[0]["n"]
    worst = q(c, """SELECT s.ss_id, COUNT(b.bc_id) total,
                           SUM(CASE WHEN EXISTS (SELECT 1 FROM vp_bc v WHERE v.bc_id=b.bc_id)
                                    THEN 1 ELSE 0 END) verified
                    FROM subsystem s JOIN bc b ON b.ss_id=s.ss_id
                    GROUP BY s.ss_id ORDER BY (verified/total) ASC LIMIT 3""")
    c.close()
    check("G3 coverage: unverified / unimplemented BCs quantified", True,
          f"BCs total                : {tot}\n"
          f"BCs with NO verifying VP : {unverified} ({100*unverified/tot:.1f}%)\n"
          f"BCs with NO story        : {unimpl} ({100*unimpl/tot:.1f}%)\n"
          f"VPs verifying nothing    : {vp_no_bc}\n"
          f"stories anchored to no BC: {st_no_bc}\n"
          f"least-verified subsystems: "
          + ", ".join(f"{r['ss_id']} {r['verified']}/{r['total']}" for r in worst))


def g4_dep_symmetry():
    """The corpus records depends_on AND blocks independently, so they can
    disagree. If A declares 'blocks B', B should declare 'depends_on A'."""
    c = conn()
    asym = q(c, """SELECT b.story_id AS blocker, b.dep_id AS blocked
                   FROM story_dep b
                   WHERE b.kind='blocks'
                     AND NOT EXISTS (SELECT 1 FROM story_dep d
                                     WHERE d.kind='depends_on'
                                       AND d.story_id=b.dep_id
                                       AND d.dep_id=b.story_id)""")
    rev = q(c, """SELECT d.story_id AS dependent, d.dep_id AS dependency
                  FROM story_dep d
                  WHERE d.kind='depends_on'
                    AND NOT EXISTS (SELECT 1 FROM story_dep b
                                    WHERE b.kind='blocks'
                                      AND b.story_id=d.dep_id
                                      AND b.dep_id=d.story_id)""")
    tot = q(c, "SELECT COUNT(*) n FROM story_dep")[0]["n"]
    c.close()
    # This is a REPORT, not a pass/fail on the corpus: the query working is the point.
    check("G4 dependency symmetry: 'A blocks B' vs 'B depends_on A' reconciled", True,
          f"story_dep edges              : {tot}\n"
          f"'blocks' with no matching 'depends_on': {len(asym)}"
          + (f"  e.g. {asym[0]['blocker']} blocks {asym[0]['blocked']}" if asym else "")
          + f"\n'depends_on' with no matching 'blocks': {len(rev)}"
          + (f"  e.g. {rev[0]['dependent']} depends_on {rev[0]['dependency']}" if rev else "")
          + "\n(one-directional declarations are invisible to grep; here they are a JOIN)")


def g5_cycle_detection():
    """Story dependency cycles. A wave scheduler that hits one deadlocks."""
    c = conn()
    # Recursive CTE over depends_on; detect any story reachable from itself.
    try:
        cyc = q(c, """WITH RECURSIVE walk (root, node, depth) AS (
                        SELECT story_id, dep_id, 1 FROM story_dep WHERE kind='depends_on'
                        UNION ALL
                        SELECT w.root, d.dep_id, w.depth+1
                        FROM walk w JOIN story_dep d
                          ON d.story_id = w.node AND d.kind='depends_on'
                        WHERE w.depth < 12
                      )
                      SELECT DISTINCT root FROM walk WHERE node = root""")
        ok, note = True, f"cycles found: {len(cyc)}"
        if cyc:
            note += f"  e.g. {[r['root'] for r in cyc][:5]}"
        else:
            note += " (dependency graph is acyclic)"
        # depth reachability proves the recursion actually traversed
        d = q(c, """WITH RECURSIVE walk (root, node, depth) AS (
                      SELECT story_id, dep_id, 1 FROM story_dep WHERE kind='depends_on'
                      UNION ALL
                      SELECT w.root, dd.dep_id, w.depth+1 FROM walk w
                      JOIN story_dep dd ON dd.story_id=w.node AND dd.kind='depends_on'
                      WHERE w.depth < 12)
                    SELECT MAX(depth) m, COUNT(*) n FROM walk""")
        note += f"\ntransitive closure: {d[0]['n']} paths, max depth {d[0]['m']}"
    except pymysql.err.Error as e:
        ok, note = False, f"recursive CTE unsupported: {str(e)[:140]}"
    c.close()
    check("G5 cycle detection + transitive closure via recursive CTE", ok, note)


def g6_cascade_integrity():
    """Deleting a BC must not leave orphan edges. Verified, then rolled back."""
    c = conn(autocommit=False)
    try:
        with c.cursor() as cur:
            cur.execute("START TRANSACTION")
        bc = q(c, """SELECT bc_id FROM bc b
                     WHERE EXISTS (SELECT 1 FROM vp_bc v WHERE v.bc_id=b.bc_id)
                       AND EXISTS (SELECT 1 FROM story_bc s WHERE s.bc_id=b.bc_id)
                     LIMIT 1""")[0]["bc_id"]
        before = (q(c, "SELECT COUNT(*) n FROM vp_bc WHERE bc_id=%s", (bc,))[0]["n"],
                  q(c, "SELECT COUNT(*) n FROM story_bc WHERE bc_id=%s", (bc,))[0]["n"])
        with c.cursor() as cur:
            cur.execute("DELETE FROM bc WHERE bc_id=%s", (bc,))
        after = (q(c, "SELECT COUNT(*) n FROM vp_bc WHERE bc_id=%s", (bc,))[0]["n"],
                 q(c, "SELECT COUNT(*) n FROM story_bc WHERE bc_id=%s", (bc,))[0]["n"])
        c.rollback()
        restored = q(c, "SELECT COUNT(*) n FROM bc WHERE bc_id=%s", (bc,))[0]["n"]
        check("G6 cascade: deleting a BC removes its edges; rollback restores all",
              before != (0, 0) and after == (0, 0) and restored == 1,
              f"{bc}: edges before={before} after delete={after}; "
              f"row restored after rollback={restored == 1}")
    finally:
        c.close()


def g7_orphan_edge_impossible():
    """The core claim: an edge to a non-existent node cannot be stored.
    Tested on every edge table, not just one."""
    c = conn()
    cases = [
        ("vp_bc", "(vp_id, bc_id)", ("VP-001", "BC-9.99.999")),
        ("vp_di", "(vp_id, di_id)", ("VP-001", "DI-999")),
        ("vp_nfr", "(vp_id, nfr_id)", ("VP-001", "NFR-NOPE-999")),
        ("story_bc", "(story_id, bc_id)", ("S-0.01", "BC-9.99.999")),
        ("story_vp", "(story_id, vp_id)", ("S-0.01", "VP-9999")),
        ("story_fr", "(story_id, fr_id)", ("S-0.01", "FR-9999")),
        ("story_subsystem", "(story_id, ss_id)", ("S-0.01", "SS-99")),
        ("story_dep", "(story_id, dep_id, kind)", ("S-0.01", "S-99.99", "blocks")),
    ]
    rejected, leaked = [], []
    for tbl, cols, vals in cases:
        ph = ",".join(["%s"] * len(vals))
        try:
            q(c, f"INSERT INTO {tbl} {cols} VALUES ({ph})", vals)
            leaked.append(tbl)
            q(c, f"DELETE FROM {tbl} WHERE {cols.strip('()').split(',')[1].strip()}=%s", (vals[1],))
        except pymysql.err.Error as e:
            (rejected if e.args[0] in (1452, 1216, 1217) else leaked).append(tbl)
    c.close()
    check("G7 every edge table rejects a reference to a non-existent node",
          len(leaked) == 0,
          f"rejected ({len(rejected)}/{len(cases)}): {rejected}"
          + (f"\nLEAKED: {leaked}" if leaked else ""))


def g8_graph_scale():
    c = conn()
    import time
    tot = 0
    for t in ("vp_bc", "vp_di", "vp_nfr", "vp_subsystem", "story_bc", "story_vp",
              "story_fr", "story_subsystem", "story_dep"):
        tot += q(c, f"SELECT COUNT(*) n FROM {t}")[0]["n"]
    t0 = time.time()
    q(c, """SELECT s.story_id, COUNT(DISTINCT sb.bc_id) bcs, COUNT(DISTINCT vb.vp_id) vps,
                   COUNT(DISTINCT vn.nfr_id) nfrs
            FROM story s
            LEFT JOIN story_bc sb ON sb.story_id=s.story_id
            LEFT JOIN vp_bc vb    ON vb.bc_id=sb.bc_id
            LEFT JOIN vp_nfr vn   ON vn.vp_id=vb.vp_id
            GROUP BY s.story_id""")
    dt = (time.time() - t0) * 1000
    c.close()
    check("G8 graph scale: whole-corpus 4-hop rollup", dt < 2000,
          f"total edges: {tot}\nfull story->BC->VP->NFR rollup over all stories: {dt:.0f}ms")


def main():
    print("=" * 74)
    print("Spec relationship graph — traversal + integrity (LIVE corpus)")
    print("=" * 74)
    for t in (g1_full_chain, g2_reverse_impact, g3_coverage_gaps, g4_dep_symmetry,
              g5_cycle_detection, g6_cascade_integrity, g7_orphan_edge_impossible,
              g8_graph_scale):
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
