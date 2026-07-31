#!/usr/bin/env python3
"""Build ONE fixture of the live corpus in three interchangeable forms, so the
embedded driver and the `dolt sql` CLI can be timed on IDENTICAL work.

  fixture.jsonl   records, FK-safe order   -> the embedded Go harness reads this
  corpus.sql      batched multi-row INSERTs -> `dolt sql -f` (invariant 6 shape)
  stmts.sql       one INSERT per statement  -> per-invocation CLI sampling

Parsing is lifted from poc/fa.py + poc/graph_import.py so the fixture is the same
records those suites imported. Edges are kept only when BOTH endpoints resolve,
so the fixture never depends on FK violations to load.

Usage: python poc/corpus_fixture.py <factory-root> <out-dir>
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.S)
BC_ID_RE = re.compile(r"^(BC-\d+\.\d+\.\d+)")
VP_ID_RE = re.compile(r"^(VP-\d+)")


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Scalars + inline lists + block lists (graph_import.py's parser)."""
    m = FM_RE.match(text)
    if not m:
        return {}, text
    out: dict[str, object] = {}
    cur_key: str | None = None
    joined: list[str] = []
    for raw in m.group(1).splitlines():
        if joined and joined[-1].count("[") > joined[-1].count("]"):
            joined[-1] += " " + raw.strip()
        else:
            joined.append(raw)
    for raw in joined:
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if re.match(r"^\s+-\s+", raw):
            if cur_key is not None:
                out.setdefault(cur_key, [])
                if isinstance(out[cur_key], list):
                    out[cur_key].append(raw.split("-", 1)[1].strip().strip("\"'"))
            continue
        if raw.startswith((" ", "\t")) or ":" not in raw:
            continue
        k, _, v = raw.partition(":")
        k, v = k.strip(), v.strip()
        if "#" in v:
            v = re.sub(r"\s+#.*$", "", v).strip()
        cur_key = k
        if v.startswith("[") and v.endswith("]"):
            inner = v[1:-1].strip()
            out[k] = [x.strip().strip("\"'") for x in inner.split(",") if x.strip()] if inner else []
        elif v == "":
            out[k] = []
        else:
            out[k] = v.strip("\"'")
    return out, text[m.end():]


def as_list(v) -> list[str]:
    if v is None:
        return []
    if isinstance(v, list):
        return [str(x) for x in v if str(x).strip()]
    s = str(v).strip()
    return [] if s in ("", "[]", "null", "none", "None") else [s]


def first_h1(body: str) -> str:
    for ln in body.splitlines():
        if ln.startswith("# "):
            return ln[2:].strip()
    return ""


def build(root: Path) -> list[dict]:
    recs: list[dict] = []

    # --- subsystems (authoritative BC-S prefixes from ARCH-INDEX)
    ss_rows: dict[str, tuple[int, str]] = {}
    arch = root / "specs/architecture/ARCH-INDEX.md"
    if arch.exists():
        for ln in arch.read_text(errors="replace").splitlines():
            m = re.match(r"\|\s*(SS-\d+)\s*\|\s*([^|]+?)\s*\|\s*BC-(\d+)\s*\|", ln)
            if m:
                ss_rows[m.group(1)] = (int(m.group(3)), m.group(2).strip())
    for d in sorted((root / "specs/behavioral-contracts").glob("ss-*")):
        ss_id = "SS-" + d.name.split("-")[1]
        ss_rows.setdefault(ss_id, (int(d.name.split("-")[1]), ss_id))
    for ss_id, (pfx, name) in sorted(ss_rows.items()):
        recs.append({"t": "ss", "id": ss_id, "prefix": pfx, "title": name[:200]})

    # --- VPs (bc_trace FKs point at them)
    vp_ids: set[str] = set()
    vp_bcs: dict[str, list[str]] = {}
    for f in sorted((root / "specs/verification-properties").glob("VP-*.md")):
        m = VP_ID_RE.match(f.name)
        if not m:
            continue
        fm, body = parse_frontmatter(f.read_text(errors="replace"))
        vp_id = m.group(1)
        vp_ids.add(vp_id)
        vp_bcs[vp_id] = [x for x in as_list(fm.get("bcs")) if BC_ID_RE.match(x)]
        recs.append({"t": "vp", "id": vp_id, "title": first_h1(body)[:1000] or vp_id,
                     "body": body, "ver": str(fm.get("version", "v1.0"))[:16]})

    # --- BCs (subsystem from FRONTMATTER, not the directory)
    bc_ids: set[str] = set()
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
            continue
        cap = str(fm.get("capability", "")).strip()
        cap = cap if re.match(r"^CAP-\d+$", cap) else ""
        bc_ids.add(bc_id)
        recs.append({"t": "bc", "id": bc_id, "ss": ss,
                     "title": first_h1(body)[:1000] or bc_id, "body": body,
                     "cap": cap, "ver": str(fm.get("version", "v1.0"))[:16]})

    # --- stories
    story_bcs: dict[str, list[str]] = {}
    for f in sorted((root / "stories").rglob("S-*.md")):
        m = re.match(r"^(S-[\d.]+)", f.name)
        if not m:
            continue
        sid = m.group(1).rstrip(".")
        fm, body = parse_frontmatter(f.read_text(errors="replace"))
        try:
            wave = int(str(fm.get("wave")))
        except (TypeError, ValueError):
            wave = None
        story_bcs[sid] = [x for x in as_list(fm.get("behavioral_contracts")) if BC_ID_RE.match(x)]
        recs.append({"t": "story", "id": sid, "title": first_h1(body)[:1000] or sid,
                     "status": str(fm.get("status", "pending"))[:24], "wave": wave,
                     "body": body})

    # --- edges: BOTH endpoints must resolve (no FK violations in the fixture)
    seen: set[tuple] = set()
    for vp_id, bcs in vp_bcs.items():
        for bc in bcs:
            if bc in bc_ids and ("t", vp_id, bc) not in seen:
                seen.add(("t", vp_id, bc))
                recs.append({"t": "trace", "id": bc, "id2": vp_id})
    for sid, bcs in story_bcs.items():
        for bc in bcs:
            if bc in bc_ids and ("s", sid, bc) not in seen:
                seen.add(("s", sid, bc))
                recs.append({"t": "sbc", "id": sid, "id2": bc})
    return recs


def esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace("'", "\\'")


def lit(v) -> str:
    if v is None or v == "":
        return "NULL"
    if isinstance(v, int):
        return str(v)
    return "'" + esc(str(v)) + "'"


def sql_for(r: dict) -> str:
    t = r["t"]
    if t == "ss":
        return ("INSERT IGNORE INTO subsystem (ss_id, bc_prefix, name) VALUES ("
                f"{lit(r['id'])},{r['prefix']},{lit(r['title'])});")
    if t == "vp":
        return ("INSERT IGNORE INTO vp (vp_id, title, body, version) VALUES ("
                f"{lit(r['id'])},{lit(r['title'])},{lit(r['body'])},{lit(r['ver'])});")
    if t == "bc":
        return ("INSERT IGNORE INTO bc (bc_id, ss_id, title, body, capability, version) VALUES ("
                f"{lit(r['id'])},{lit(r['ss'])},{lit(r['title'])},{lit(r['body'])},"
                f"{lit(r.get('cap'))},{lit(r['ver'])});")
    if t == "story":
        w = r.get("wave")
        return ("INSERT IGNORE INTO story (story_id, title, status, wave, body) VALUES ("
                f"{lit(r['id'])},{lit(r['title'])},{lit(r['status'])},"
                f"{'NULL' if w is None else w},{lit(r['body'])});")
    if t == "trace":
        return f"INSERT IGNORE INTO bc_trace (bc_id, vp_id) VALUES ({lit(r['id'])},{lit(r['id2'])});"
    if t == "sbc":
        return f"INSERT IGNORE INTO story_bc (story_id, bc_id) VALUES ({lit(r['id'])},{lit(r['id2'])});"
    raise ValueError(t)


def write_all(recs: list[dict], out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "fixture.jsonl", "w") as fh:
        for r in recs:
            fh.write(json.dumps({
                "t": r["t"], "id": r.get("id", ""), "id2": r.get("id2", ""),
                "ss": r.get("ss", ""), "title": r.get("title", ""),
                "body": r.get("body", ""), "cap": r.get("cap", ""),
                "ver": r.get("ver", ""), "status": r.get("status", ""),
                "wave": r.get("wave"), "prefix": r.get("prefix", 0),
            }) + "\n")
    stmts = [sql_for(r) for r in recs]
    with open(out / "stmts.sql", "w") as fh:
        fh.write("\n".join(stmts) + "\n")
    # batched form: same rows, multi-statement file (one invocation)
    with open(out / "corpus.sql", "w") as fh:
        fh.write("\n".join(stmts) + "\n")
    counts: dict[str, int] = {}
    for r in recs:
        counts[r["t"]] = counts.get(r["t"], 0) + 1
    return counts


def main():
    root = Path(sys.argv[1]).expanduser()
    out = Path(sys.argv[2])
    recs = build(root)
    counts = write_all(recs, out)
    print(json.dumps({"records": len(recs), "counts": counts,
                      "jsonl_mb": round((out / "fixture.jsonl").stat().st_size / 1e6, 1),
                      "sql_mb": round((out / "corpus.sql").stat().st_size / 1e6, 1)}))


if __name__ == "__main__":
    main()
