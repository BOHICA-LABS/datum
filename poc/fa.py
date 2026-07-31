#!/usr/bin/env python3
"""fa - the only interface to factory artifacts.

POC for the Dolt-backed artifact store. Every read and write goes through here;
nothing touches artifact files directly. Markdown is a RENDERED EXPORT, never truth.

Modes:
  server   - talks MySQL wire to a `dolt sql-server` (multi-writer, real transactions)
  cli      - shells out to `dolt sql -q` (single-writer, no server needed)

The POC uses server mode for anything needing atomicity, because the CAS lock
requires a real transaction. That is a finding, not an implementation detail.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import pymysql

DB = "factory_artifacts"


# ---------------------------------------------------------------- connection


@dataclass
class Conn:
    host: str = "127.0.0.1"
    port: int = 3308
    user: str = "root"
    db: str | None = DB

    def connect(self, db: str | None = "", autocommit: bool = True):
        # db="" means "use the default"; db=None means "connect with no database
        # selected" (needed before CREATE DATABASE exists).
        target = self.db if db == "" else db
        kw = dict(
            host=self.host,
            port=self.port,
            user=self.user,
            autocommit=autocommit,
            cursorclass=pymysql.cursors.DictCursor,
        )
        if target:
            kw["database"] = target
        return pymysql.connect(**kw)


def q(conn, sql: str, args=None, fetch: bool = True):
    with conn.cursor() as cur:
        cur.execute(sql, args or ())
        if fetch:
            try:
                return cur.fetchall()
            except Exception:
                return []
        return cur.rowcount


# ---------------------------------------------------------------- init


def cmd_init(a):
    c = Conn(port=a.port)
    conn = c.connect(db=None)
    q(conn, f"CREATE DATABASE IF NOT EXISTS {DB}", fetch=False)
    conn.close()

    conn = c.connect()
    ddl = (Path(__file__).parent / "schema.sql").read_text()
    # Strip `--` comments BEFORE splitting on ';' — comment prose contains
    # semicolons, and splitting first tears statements in half.
    stripped = "\n".join(re.sub(r"--.*$", "", ln) for ln in ddl.splitlines())
    for stmt in [s.strip() for s in stripped.split(";")]:
        if stmt:
            q(conn, stmt, fetch=False)
    q(conn, "INSERT IGNORE INTO factory_lock (id, holder) VALUES (1, NULL)", fetch=False)
    q(conn, "CALL DOLT_COMMIT('-Am', 'schema: initialize factory artifact store')", fetch=False)
    conn.close()
    print(f"initialized {DB} on port {a.port}")


# ---------------------------------------------------------------- import


FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.S)


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Minimal YAML-ish frontmatter scrape. Only scalar keys, which is all we need."""
    m = FM_RE.match(text)
    if not m:
        return {}, text
    fm = {}
    for line in m.group(1).splitlines():
        if line.startswith((" ", "\t", "-")) or ":" not in line:
            continue
        k, _, v = line.partition(":")
        fm[k.strip()] = v.strip().strip("\"'")
    return fm, text[m.end():]


def first_h1(body: str) -> str:
    for ln in body.splitlines():
        if ln.startswith("# "):
            return ln[2:].strip()
    return ""


BC_ID_RE = re.compile(r"^(BC-\d+\.\d+\.\d+)")
VP_ID_RE = re.compile(r"^(VP-\d+)")


def cmd_import(a):
    """Ingest the REAL .factory corpus. This is the migration-feasibility test."""
    root = Path(a.factory).expanduser()
    c = Conn(port=a.port)
    conn = c.connect(autocommit=False)

    t0 = time.time()
    stats = {"subsystem": 0, "bc": 0, "vp": 0, "story": 0, "skipped_no_ss": 0}

    # --- subsystems, from the architecture registry (authoritative BC-S prefixes)
    arch = root / "specs/architecture/ARCH-INDEX.md"
    ss_rows = {}
    if arch.exists():
        for ln in arch.read_text(errors="replace").splitlines():
            m = re.match(r"\|\s*(SS-\d+)\s*\|\s*([^|]+?)\s*\|\s*BC-(\d+)\s*\|", ln)
            if m:
                ss_rows[m.group(1)] = (int(m.group(3)), m.group(2).strip())
    # Fall back to subsystems observed on disk so import never silently drops BCs.
    for d in sorted((root / "specs/behavioral-contracts").glob("ss-*")):
        ss_id = "SS-" + d.name.split("-")[1]
        ss_rows.setdefault(ss_id, (int(d.name.split("-")[1]), ss_id))
    for ss_id, (pfx, name) in sorted(ss_rows.items()):
        q(conn, "INSERT IGNORE INTO subsystem (ss_id, bc_prefix, name) VALUES (%s,%s,%s)",
          (ss_id, pfx, name[:200]), fetch=False)
        stats["subsystem"] += 1

    # --- VPs first (bc_trace FKs point at them)
    for f in sorted((root / "specs/verification-properties").glob("VP-*.md")):
        m = VP_ID_RE.match(f.name)
        if not m:
            continue
        fm, body = parse_frontmatter(f.read_text(errors="replace"))
        q(conn, "INSERT IGNORE INTO vp (vp_id, title, body, version) VALUES (%s,%s,%s,%s)",
          (m.group(1), first_h1(body)[:1000] or m.group(1), body,
           str(fm.get("version", "v1.0"))[:16]), fetch=False)
        stats["vp"] += 1

    # --- BCs. Subsystem comes from FRONTMATTER, not the directory: the live corpus
    #     documents 4 files whose directory and authoritative subsystem disagree.
    for f in sorted((root / "specs/behavioral-contracts").rglob("BC-*.md")):
        if f.name == "BC-INDEX.md":
            continue
        m = BC_ID_RE.match(f.name)
        if not m:
            continue
        bc_id = m.group(1)
        fm, body = parse_frontmatter(f.read_text(errors="replace"))
        ss = str(fm.get("subsystem") or fm.get("ss") or "").strip()
        if not re.match(r"^SS-\d+$", ss):
            ss = "SS-" + f.parent.name.split("-")[-1] if f.parent.name.startswith("ss-") else ""
        if not re.match(r"^SS-\d+$", ss) or ss not in ss_rows:
            stats["skipped_no_ss"] += 1
            continue
        cap = str(fm.get("capability", "")).strip()
        cap = cap if re.match(r"^CAP-\d+$", cap) else None
        q(conn, """INSERT INTO bc (bc_id, ss_id, title, body, capability, version)
                   VALUES (%s,%s,%s,%s,%s,%s)
                   ON DUPLICATE KEY UPDATE body=VALUES(body), title=VALUES(title)""",
          (bc_id, ss, first_h1(body)[:1000] or bc_id, body, cap,
           str(fm.get("version", "v1.0"))[:16]), fetch=False)
        stats["bc"] += 1

    # --- stories
    for f in sorted((root / "stories").rglob("S-*.md")):
        m = re.match(r"^(S-[\d.]+)", f.name)
        if not m:
            continue
        fm, body = parse_frontmatter(f.read_text(errors="replace"))
        wave = fm.get("wave")
        try:
            wave = int(str(wave))
        except (TypeError, ValueError):
            wave = None
        q(conn, """INSERT INTO story (story_id, title, status, wave, body)
                   VALUES (%s,%s,%s,%s,%s)
                   ON DUPLICATE KEY UPDATE body=VALUES(body)""",
          (m.group(1).rstrip("."), first_h1(body)[:1000] or m.group(1),
           str(fm.get("status", "pending"))[:24], wave, body), fetch=False)
        stats["story"] += 1

    conn.commit()
    q(conn, "CALL DOLT_COMMIT('-Am', 'import: ingest factory corpus')", fetch=False)
    conn.close()
    dt = time.time() - t0
    print(f"imported in {dt:.1f}s: " + ", ".join(f"{k}={v}" for k, v in stats.items()))


# ---------------------------------------------------------------- reads


def cmd_count(a):
    conn = Conn(port=a.port).connect()
    rows = q(conn, """SELECT 'bc' t, COUNT(*) n FROM bc
                      UNION ALL SELECT 'vp', COUNT(*) FROM vp
                      UNION ALL SELECT 'story', COUNT(*) FROM story
                      UNION ALL SELECT 'trace', COUNT(*) FROM bc_trace""")
    for r in rows:
        print(f"{r['t']:8} {r['n']}")
    if a.by_subsystem:
        print("\nby subsystem:")
        for r in q(conn, """SELECT s.ss_id, s.name, COUNT(b.bc_id) n
                            FROM subsystem s LEFT JOIN bc b ON b.ss_id = s.ss_id
                            GROUP BY s.ss_id, s.name ORDER BY s.ss_id"""):
            print(f"  {r['ss_id']}  {r['n']:5}  {r['name'][:48]}")
    conn.close()


def cmd_get(a):
    conn = Conn(port=a.port).connect()
    rows = q(conn, "SELECT * FROM bc WHERE bc_id=%s", (a.id,))
    if not rows:
        print(f"not found: {a.id}", file=sys.stderr)
        sys.exit(1)
    r = rows[0]
    print(f"{r['bc_id']}  [{r['ss_id']}]  {r['version']}  cap={r['capability']}")
    print(f"title: {r['title']}")
    conn.close()


def cmd_history(a):
    """Time travel. Replaces reading 1,607 git commits to answer 'when did this change'."""
    conn = Conn(port=a.port).connect()
    rows = q(conn, """SELECT commit_hash, committer, commit_date, title
                      FROM dolt_history_bc WHERE bc_id=%s
                      ORDER BY commit_date DESC LIMIT %s""", (a.id, a.limit))
    if not rows:
        print("no history")
    for r in rows:
        print(f"{str(r['commit_hash'])[:10]}  {r['commit_date']}  {str(r['title'])[:60]}")
    conn.close()


def cmd_validate(a):
    """Referential + count integrity. In the markdown corpus this is a grep sweep
    that has failed 19 documented times. Here the FKs make most of it unrepresentable;
    what remains is a query."""
    conn = Conn(port=a.port).connect()
    problems = 0

    orphan_trace = q(conn, """SELECT t.bc_id FROM bc_trace t
                              LEFT JOIN bc b ON b.bc_id=t.bc_id WHERE b.bc_id IS NULL""")
    if orphan_trace:
        problems += len(orphan_trace)
        print(f"FAIL dangling bc_trace -> bc: {len(orphan_trace)}")

    bad_ss = q(conn, """SELECT b.bc_id FROM bc b
                        LEFT JOIN subsystem s ON s.ss_id=b.ss_id WHERE s.ss_id IS NULL""")
    if bad_ss:
        problems += len(bad_ss)
        print(f"FAIL bc with unknown subsystem: {len(bad_ss)}")

    malformed = q(conn, r"SELECT bc_id FROM bc WHERE bc_id NOT REGEXP '^BC-[0-9]+\\.[0-9]+\\.[0-9]+$'")
    if malformed:
        problems += len(malformed)
        print(f"FAIL malformed bc_id: {[r['bc_id'] for r in malformed][:5]}")

    # Prefix agreement: BC-S must match the subsystem's registered bc_prefix.
    mism = q(conn, """SELECT b.bc_id, b.ss_id, s.bc_prefix
                      FROM bc b JOIN subsystem s ON s.ss_id=b.ss_id
                      WHERE CAST(SUBSTRING_INDEX(SUBSTRING(b.bc_id,4),'.',1) AS UNSIGNED) <> s.bc_prefix""")
    if mism:
        problems += len(mism)
        print(f"WARN bc_id prefix != subsystem bc_prefix: {len(mism)} "
              f"(e.g. {mism[0]['bc_id']} in {mism[0]['ss_id']} prefix {mism[0]['bc_prefix']})")

    print("OK  no integrity violations" if problems == 0 else f"\n{problems} violation(s)")
    conn.close()
    sys.exit(1 if problems else 0)


# ---------------------------------------------------------------- lock (CAS)


def cmd_lock(a):
    """Atomic CAS lock. One UPDATE, guarded WHERE, ROW_COUNT() is the verdict.
    Guard-read and write are in the SAME statement, so there is no TOCTOU window."""
    conn = Conn(port=a.port).connect(autocommit=True)
    ttl = a.ttl
    if a.action == "acquire":
        n = q(conn, """UPDATE factory_lock
                       SET holder=%s, locked_at=NOW(), expires_at=DATE_ADD(NOW(), INTERVAL %s SECOND),
                           fence=fence+1
                       WHERE id=1 AND (holder IS NULL OR holder=%s OR expires_at < NOW())""",
              (a.holder, ttl, a.holder), fetch=False)
        if n == 1:
            r = q(conn, "SELECT holder, expires_at, fence FROM factory_lock WHERE id=1")[0]
            print(f"ACQUIRED by {r['holder']} fence={r['fence']} expires={r['expires_at']}")
        else:
            r = q(conn, "SELECT holder, expires_at FROM factory_lock WHERE id=1")[0]
            print(f"REFUSED held by {r['holder']} until {r['expires_at']}", file=sys.stderr)
            sys.exit(1)
    elif a.action == "release":
        n = q(conn, """UPDATE factory_lock SET holder=NULL, locked_at=NULL, expires_at=NULL
                       WHERE id=1 AND holder=%s""", (a.holder,), fetch=False)
        if n == 1:
            print("RELEASED")
        else:
            print("REFUSED not the holder", file=sys.stderr)
            sys.exit(1)
    else:
        r = q(conn, "SELECT * FROM factory_lock WHERE id=1")[0]
        print(f"holder={r['holder']} expires={r['expires_at']} fence={r['fence']}")
    conn.close()


# ---------------------------------------------------------------- render


def cmd_render(a):
    """Markdown is a rendered export, generated from the DB, never edited.
    This is what keeps humans and git-diff-based review workflows working."""
    conn = Conn(port=a.port).connect()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    total = q(conn, "SELECT COUNT(*) n FROM bc")[0]["n"]
    per_ss = q(conn, """SELECT s.ss_id, s.name, COUNT(b.bc_id) n
                        FROM subsystem s LEFT JOIN bc b ON b.ss_id=s.ss_id
                        GROUP BY s.ss_id, s.name ORDER BY s.ss_id""")
    lines = [
        "---", "document_type: bc-index",
        "generated: true  # DO NOT EDIT - rendered by `fa render`",
        f"total_bcs: {total}", "---", "",
        "# BC-INDEX", "",
        f"Total BCs: {total}", "",
        "| Subsystem | Name | Count |", "|---|---|---|",
    ]
    for r in per_ss:
        lines.append(f"| {r['ss_id']} | {r['name']} | {r['n']} |")
    lines += [f"| **Total** | | **{total}** |", "", "| BC | Subsystem | Capability | Title |", "|---|---|---|---|"]
    for r in q(conn, "SELECT bc_id, ss_id, capability, title FROM bc ORDER BY bc_id"):
        t = str(r["title"]).replace("|", "\\|")[:120]
        lines.append(f"| {r['bc_id']} | {r['ss_id']} | {r['capability'] or 'TBD'} | {t} |")

    (out / "BC-INDEX.md").write_text("\n".join(lines) + "\n")
    print(f"rendered {out/'BC-INDEX.md'}  (total_bcs={total}, {len(per_ss)} subsystems)")
    conn.close()


# ---------------------------------------------------------------- main


def main():
    p = argparse.ArgumentParser(prog="fa", description="the only interface to factory artifacts")
    p.add_argument("--port", type=int, default=int(os.environ.get("FA_PORT", 3308)))
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init").set_defaults(fn=cmd_init)

    s = sub.add_parser("import"); s.add_argument("factory"); s.set_defaults(fn=cmd_import)
    s = sub.add_parser("count"); s.add_argument("--by-subsystem", action="store_true"); s.set_defaults(fn=cmd_count)
    s = sub.add_parser("get"); s.add_argument("id"); s.set_defaults(fn=cmd_get)
    s = sub.add_parser("history"); s.add_argument("id"); s.add_argument("--limit", type=int, default=10); s.set_defaults(fn=cmd_history)
    sub.add_parser("validate").set_defaults(fn=cmd_validate)

    s = sub.add_parser("lock")
    s.add_argument("action", choices=["acquire", "release", "status"])
    s.add_argument("--holder", default=os.environ.get("USER", "unknown"))
    s.add_argument("--ttl", type=int, default=2700)
    s.set_defaults(fn=cmd_lock)

    s = sub.add_parser("render"); s.add_argument("--out", default="rendered"); s.set_defaults(fn=cmd_render)

    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
