#!/usr/bin/env python3
"""Populate the full spec relationship graph from the live corpus.

Two rules that make this a real test rather than a demo:

1. Node universes come from AUTHORITATIVE DEFINITION SOURCES only (the catalog /
   registry that declares each ID), never from grep-over-everything. If the
   universe were built from all mentions, every reference would trivially
   resolve and the integrity check would prove nothing.

2. Every edge that a FOREIGN KEY rejects is RECORDED AS A FINDING, not dropped.
   The rejections are the output.

Usage: graph_import.py <path-to-.factory>
"""
from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path

import pymysql

PORT = 3308
DB = "factory_artifacts"


def conn(autocommit=True):
    return pymysql.connect(host="127.0.0.1", port=PORT, user="root", database=DB,
                           autocommit=autocommit, cursorclass=pymysql.cursors.DictCursor)


def ex(c, sql, args=None):
    with c.cursor() as cur:
        cur.execute(sql, args or ())
        return cur.rowcount


def rows(c, sql, args=None):
    with c.cursor() as cur:
        cur.execute(sql, args or ())
        return cur.fetchall()


# ------------------------------------------------------------ frontmatter

FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.S)


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Handles scalars, inline lists (`k: [a, b]`) and block lists (`k:\\n  - a`).

    The first POC pass skipped any line starting with whitespace or '-', which
    silently discarded EVERY list-valued edge in the corpus. That bug is the
    reason the trace table came back empty.
    """
    m = FM_RE.match(text)
    if not m:
        return {}, text
    out: dict[str, object] = {}
    cur_key: str | None = None

    # Join multi-line inline lists first. The corpus wraps long ones, e.g.
    #   blocks: ["S-8.11", "S-8.12",
    #            "S-8.18", ...]
    # Reading only the first physical line truncates the list mid-element.
    joined: list[str] = []
    for raw in m.group(1).splitlines():
        if joined and joined[-1].count("[") > joined[-1].count("]"):
            joined[-1] += " " + raw.strip()
        else:
            joined.append(raw)

    for raw in joined:
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        # continuation of a block list
        if re.match(r"^\s+-\s+", raw):
            if cur_key is not None:
                out.setdefault(cur_key, [])
                if isinstance(out[cur_key], list):
                    out[cur_key].append(raw.split("-", 1)[1].strip().strip("\"'"))
            continue
        if raw.startswith((" ", "\t")):
            continue  # nested mapping we do not need
        if ":" not in raw:
            continue
        k, _, v = raw.partition(":")
        k, v = k.strip(), v.strip()
        # Strip trailing YAML comments: `verification_properties: []  # [process-gap] ...`
        if "#" in v:
            v = re.sub(r"\s+#.*$", "", v).strip()
        cur_key = k
        if v.startswith("[") and v.endswith("]"):
            inner = v[1:-1].strip()
            out[k] = [x.strip().strip("\"'") for x in inner.split(",") if x.strip()] if inner else []
        elif v == "":
            out[k] = []          # a block list may follow
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


def scalar(v) -> str | None:
    if isinstance(v, list):
        return v[0] if len(v) == 1 else None
    s = (str(v).strip() if v is not None else "")
    return None if s in ("", "null", "none", "None", "[]") else s


# ------------------------------------------------------------ node universes


def load_universes(root: Path) -> dict[str, dict[str, str]]:
    """Each universe: id -> name, from that ID class's declaring document."""
    U: dict[str, dict[str, str]] = {k: {} for k in
                                    ("cap", "di", "nfr", "fr", "adr", "epic")}

    def headings(path: Path, pat: str) -> dict[str, str]:
        got = {}
        if not path.exists():
            return got
        for ln in path.read_text(errors="replace").splitlines():
            s = ln.strip()
            # The corpus declares IDs in three shapes; all are authoritative.
            #   1. heading:   ### NFR-PERF-001: ...
            #   2. bold line: **CAP-001 \u2014 ...**       (domain-spec style)
            #   3. table row: | FR-037 | ... |
            # NOTE: the bold form must NOT be anchored to end-of-line \u2014 the corpus
            # appends an amendment suffix after the closing '**', e.g.
            #   **DI-019 \u2014 ASYNC_DRAIN_WINDOW_MS = 100** _(v1.5 \u2014 amended ...)_
            # Anchoring here silently lost DI-017 and DI-019 from the universe.
            for rx in (rf"^#+\s+({pat})[:\s\u2014-]*(.*)$",
                       rf"^\*\*({pat})\s*[\u2014:-]*\s*(.*?)\*\*",
                       rf"^\|\s*\*{{0,2}}({pat})\*{{0,2}}\s*\|(.*)$"):
                m = re.match(rx, s)
                if m:
                    got.setdefault(m.group(1), m.group(2).split("|")[0].strip()[:400])
                    break
        return got

    ds = root / "specs/domain-spec"
    U["cap"] = headings(ds / "capabilities.md", r"CAP-\d+")
    U["di"] = headings(ds / "invariants.md", r"DI-\d+")

    prd = root / "specs/prd.md"
    U["fr"] = headings(prd, r"FR-\d+")
    # NFRs: the authoritative registry is the phase-0 catalog (NOT under specs/),
    # unioned with the handful declared in the PRD table.
    U["nfr"] = headings(root / "phase-0-ingestion/pass-4-nfr-catalog.md", r"NFR-[A-Z]+-\d+")
    for k, v in headings(prd, r"NFR-[A-Z]+-\d+").items():
        U["nfr"].setdefault(k, v)

    for f in (root / "specs/architecture").glob("*.md"):
        U["adr"].update(headings(f, r"ADR-\d+"))

    for f in (root / "stories/epics").glob("E-*.md"):
        m = re.match(r"^(E-\d+)", f.name)
        if m:
            U["epic"][m.group(1)] = f.stem[len(m.group(1)) + 1:].replace("-", " ")[:400]
    return U


# ------------------------------------------------------------ import


def main():
    root = Path(sys.argv[1]).expanduser()
    c = conn()

    # schema extension (idempotent: ALTER fails if column exists)
    ddl = (Path(__file__).parent / "graph.sql").read_text()
    ddl = "\n".join(re.sub(r"--.*$", "", l) for l in ddl.splitlines())
    for stmt in [s.strip() for s in ddl.split(";") if s.strip()]:
        try:
            ex(c, stmt)
        except pymysql.err.Error as e:
            if "already exists" not in str(e) and "duplicate column" not in str(e).lower():
                print(f"  ddl note: {str(e)[:90]}")

    # Deterministic re-run: clear edge tables so counts and findings reflect THIS
    # import, not an accumulation across runs.
    for t in ("vp_bc", "vp_di", "vp_nfr", "vp_subsystem", "story_bc", "story_vp",
              "story_fr", "story_subsystem", "story_dep", "bc_trace"):
        try:
            ex(c, f"DELETE FROM {t}")
        except pymysql.err.Error:
            pass

    U = load_universes(root)
    for tbl, key, uni in (("capability", "cap_id", "cap"), ("domain_invariant", "di_id", "di"),
                          ("nfr", "nfr_id", "nfr"), ("fr", "fr_id", "fr"),
                          ("adr", "adr_id", "adr"), ("epic", "epic_id", "epic")):
        col = "title" if tbl in ("adr", "epic") else "name"
        for i, nm in U[uni].items():
            ex(c, f"INSERT IGNORE INTO {tbl} ({key}, {col}) VALUES (%s,%s)", (i, nm))
    print("node universes: " + ", ".join(f"{k}={len(v)}" for k, v in U.items()))

    findings: dict[str, list[str]] = defaultdict(list)
    counts: dict[str, int] = defaultdict(int)

    def ids(raw_values, pat: str, field: str) -> list[str]:
        """Coerce an ID-typed field to IDs, recording TYPE violations.

        The corpus writes things like `subsystems: ["SS-04 (Plugin Ecosystem)"]` —
        an ID with prose glued on. That is a schema violation in its own right,
        distinct from a dangling reference, so report it as such instead of
        letting it surface as an opaque column-width error.
        """
        out = []
        for rv in raw_values:
            m = re.search(pat, str(rv))
            if not m:
                findings[f"{field} value is not an id"].append(f"{str(rv)[:60]}")
                continue
            if m.group(0) != str(rv).strip():
                findings[f"{field} holds an id plus prose"].append(f"{str(rv)[:60]}")
            out.append(m.group(0))
        return out

    def edge(table, cols, vals, label):
        """Insert an edge; a FK rejection is a FINDING, not a silent drop.

        MUST NOT use INSERT IGNORE: IGNORE downgrades FK violations to warnings,
        which would make every dangling reference silently vanish and this whole
        check report a false clean. Duplicates are handled explicitly instead.
        """
        ph = ",".join(["%s"] * len(vals))
        try:
            ex(c, f"INSERT INTO {table} ({','.join(cols)}) VALUES ({ph})", vals)
            counts[table] += 1
        except pymysql.err.Error as e:
            code = e.args[0]
            if code in (1062, 1022):                     # duplicate row: benign re-run
                counts[table] += 0
            elif code in (1452, 1216, 1217, 1451):        # FK violation -> the finding
                findings[label].append(f"{vals[0]} -> {vals[1]}")
            else:
                findings[label + " (other)"].append(f"{vals} :: {str(e)[:60]}")

    # ---- BC attributes (lifecycle + self-referential replacement)
    for f in (root / "specs/behavioral-contracts").rglob("BC-*.md"):
        if f.name == "BC-INDEX.md":
            continue
        m = re.match(r"^(BC-\d+\.\d+\.\d+)", f.name)
        if not m:
            continue
        fm, _ = parse_frontmatter(f.read_text(errors="replace"))
        # `replacement` is declared as a BC pointer. Enforce the TYPE: anything
        # that is not a BC id is a schema violation, recorded rather than coerced.
        repl = scalar(fm.get("replacement"))
        if repl is not None and not re.fullmatch(r"BC-\d+\.\d+\.\d+", repl):
            findings["bc.replacement holds prose, not a BC id"].append(
                f"{m.group(1)} -> {repl[:60]}…")
            repl = None
        # Refresh capability from frontmatter too, so this import is the single
        # authority for the column (and cannot inherit stale test writes).
        cap = scalar(fm.get("capability"))
        cap = cap if cap and re.fullmatch(r"CAP-\d+", cap) else None
        ex(c, """UPDATE bc SET lifecycle_status=%s, status=%s, replacement=%s, capability=%s
                 WHERE bc_id=%s""",
           (scalar(fm.get("lifecycle_status")), scalar(fm.get("status")),
            repl, cap, m.group(1)))

    # ---- VP attributes + edges (bcs / domain_invariants / nfrs)
    for f in sorted((root / "specs/verification-properties").glob("VP-*.md")):
        m = re.match(r"^(VP-\d+)", f.name)
        if not m:
            continue
        vp = m.group(1)
        fm, _ = parse_frontmatter(f.read_text(errors="replace"))
        # `scope` is declared scalar but the corpus also uses "SS-01, SS-03".
        # Model it as the M:N edge it actually is; flag the multi-valued ones.
        scopes = [s.strip() for s in re.split(r"[,\s]+", " ".join(as_list(fm.get("scope"))))
                  if re.fullmatch(r"SS-\d+", s.strip())]
        if len(scopes) > 1:
            findings["VP.scope is multi-valued in a scalar-declared field"].append(
                f"{vp} -> {','.join(scopes)}")
        ex(c, """UPDATE vp SET scope=%s, source_bc=%s, proof_method=%s,
                               feasibility=%s, module=%s, vp_type=%s WHERE vp_id=%s""",
           (scopes[0] if len(scopes) == 1 else None, scalar(fm.get("source_bc")),
            scalar(fm.get("proof_method")), scalar(fm.get("feasibility")),
            scalar(fm.get("module")), scalar(fm.get("type")), vp))
        for ss in scopes:
            edge("vp_subsystem", ("vp_id", "ss_id"), (vp, ss), "VP.scope -> missing SS")
        for bc in ids(as_list(fm.get("bcs")), r"BC-\d+\.\d+\.\d+", "VP.bcs"):
            edge("vp_bc", ("vp_id", "bc_id"), (vp, bc), "VP.bcs -> missing BC")
        for sbc in ids(as_list(fm.get("source_bc")), r"BC-\d+\.\d+\.\d+", "VP.source_bc"):
            edge("vp_bc", ("vp_id", "bc_id"), (vp, sbc), "VP.source_bc -> missing BC")
        for di in ids(as_list(fm.get("domain_invariants")), r"DI-\d+", "VP.domain_invariants"):
            edge("vp_di", ("vp_id", "di_id"), (vp, di), "VP.domain_invariants -> missing DI")
        for nf in ids(as_list(fm.get("nfrs")), r"NFR-[A-Z]+-\d+", "VP.nfrs"):
            edge("vp_nfr", ("vp_id", "nfr_id"), (vp, nf), "VP.nfrs -> missing NFR")

    # ---- STORY attributes + edges
    story_dep_raw: list[tuple[str, str, str]] = []
    for f in sorted((root / "stories").glob("S-*.md")):
        m = re.match(r"^(S-[\d.]+?)-", f.name) or re.match(r"^(S-[\d.]+)", f.name)
        if not m:
            continue
        fm, _ = parse_frontmatter(f.read_text(errors="replace"))
        sid = scalar(fm.get("story_id")) or m.group(1).rstrip(".")
        if not rows(c, "SELECT 1 FROM story WHERE story_id=%s", (sid,)):
            continue  # story row absent (id form differs); counted below
        ex(c, "UPDATE story SET epic_id=%s, priority=%s, points=%s, cycle=%s WHERE story_id=%s",
           (scalar(fm.get("epic_id")), scalar(fm.get("priority")),
            scalar(fm.get("points")), scalar(fm.get("cycle")), sid))
        for bc in ids(as_list(fm.get("behavioral_contracts")), r"BC-\d+\.\d+\.\d+",
                      "story.behavioral_contracts"):
            edge("story_bc", ("story_id", "bc_id"), (sid, bc), "story.behavioral_contracts -> missing BC")
        for vp in ids(as_list(fm.get("verification_properties")), r"VP-\d+",
                      "story.verification_properties"):
            edge("story_vp", ("story_id", "vp_id"), (sid, vp), "story.verification_properties -> missing VP")
        for fr in ids(as_list(fm.get("functional_requirements")), r"FR-[A-Z0-9-]*\d+",
                      "story.functional_requirements"):
            edge("story_fr", ("story_id", "fr_id"), (sid, fr), "story.functional_requirements -> missing FR")
        for ss in ids(as_list(fm.get("subsystems")), r"SS-\d+", "story.subsystems"):
            edge("story_subsystem", ("story_id", "ss_id"), (sid, ss), "story.subsystems -> missing SS")
        # depends_on / blocks are story-typed. A non-story id here (the corpus has
        # epic ids in these fields) is a type violation, reported by ids().
        for d in ids(as_list(fm.get("depends_on")), r"S-[\d.]+", "story.depends_on"):
            story_dep_raw.append((sid, d, "depends_on"))
        for b in ids(as_list(fm.get("blocks")), r"S-[\d.]+", "story.blocks"):
            story_dep_raw.append((sid, b, "blocks"))

    for sid, other, kind in story_dep_raw:
        edge("story_dep", ("story_id", "dep_id", "kind"), (sid, other, kind),
             f"story.{kind} -> missing story")

    # epic_id is an FK-shaped reference; validate it as one.
    for r in rows(c, """SELECT s.story_id, s.epic_id FROM story s
                        LEFT JOIN epic e ON e.epic_id = s.epic_id
                        WHERE s.epic_id IS NOT NULL AND e.epic_id IS NULL"""):
        findings["story.epic_id -> missing epic"].append(f"{r['story_id']} -> {r['epic_id']}")

    for r in rows(c, """SELECT b.bc_id, b.capability FROM bc b
                        LEFT JOIN capability c ON c.cap_id = b.capability
                        WHERE b.capability IS NOT NULL AND c.cap_id IS NULL"""):
        findings["bc.capability -> missing CAP"].append(f"{r['bc_id']} -> {r['capability']}")

    for r in rows(c, """SELECT b.bc_id, b.replacement FROM bc b
                        LEFT JOIN bc r2 ON r2.bc_id = b.replacement
                        WHERE b.replacement IS NOT NULL AND r2.bc_id IS NULL"""):
        findings["bc.replacement -> missing BC"].append(f"{r['bc_id']} -> {r['replacement']}")

    try:
        ex(c, "CALL DOLT_COMMIT('-Am','graph: populate full spec relationship graph')")
    except pymysql.err.Error as e:
        if "nothing to commit" not in str(e):
            raise
        print("(no changes since last import — idempotent re-run)")

    print("\nedges loaded:")
    for t in sorted(counts):
        print(f"  {t:20} {counts[t]}")
    print("\nreferential findings (edges the FK refused / dangling scalar refs):")
    if not findings:
        print("  none")
    total = 0
    for label in sorted(findings):
        v = findings[label]
        total += len(v)
        print(f"  {len(v):5}  {label}")
        for s in sorted(set(v))[:4]:
            print(f"         e.g. {s}")
    print(f"\n  TOTAL dangling references: {total}")
    c.close()


if __name__ == "__main__":
    main()
