#!/usr/bin/env python3
"""PROBE: how closely does each authored index COLUMN already agree with its source records?

Run BEFORE building the shadow differ (story 7). The point is to learn which columns are
shadowable as-is, which need a declared normalisation rule, and which are prose that a
differ would only manufacture noise from. Designing the rules first and measuring after is
how a differ ends up with rules tuned to make its own numbers look clean.

Read-only. Reports raw agreement per column plus the disagreement SHAPES, not a verdict.

usage: python3 registry/probe_indexes.py [corpus-root]
"""
import os, re, sys, json, collections

ROOT = os.path.expanduser(sys.argv[1] if len(sys.argv) > 1 else "~/Dev/vsdd-factory/.factory")

FENCE = re.compile(r'^\s*(```|~~~)')
HEAD = re.compile(r'^(#{1,6})\s+(.*)')


def fm_body(txt):
    L = txt.splitlines(keepends=True)
    if not L or L[0].strip() != "---":
        return {}, txt
    for i in range(1, len(L)):
        if L[i].strip() in ("---", "..."):
            fm = {}
            for line in L[1:i]:
                m = re.match(r'^([A-Za-z_][A-Za-z0-9_.-]*):\s*(.*)$', line)
                if m:
                    fm.setdefault(m.group(1), re.sub(r'\s+#.*$', '', m.group(2)).strip().strip('"\''))
            return fm, "".join(L[i + 1:])
    return {}, txt


def split_cells(s):
    """Split a table row on UNESCAPED pipes only.

    Measured: 5 BC-INDEX rows carry a literal `\\|` inside a cell, and splitting on every
    pipe truncated those cells to fragments like `value_len\\` — which then read as a
    Capability disagreement. A splitter that loses input is the recurring defect class in
    this spike, so this is the rule, not a special case.
    """
    out, cur, i = [], [], 0
    body = s.strip()
    if body.startswith("|"):
        body = body[1:]
    if body.endswith("|"):
        body = body[:-1]
    while i < len(body):
        ch = body[i]
        if ch == "\\" and i + 1 < len(body):
            cur.append(body[i + 1]); i += 2; continue
        if ch == "|":
            out.append("".join(cur).strip()); cur = []; i += 1; continue
        cur.append(ch); i += 1
    out.append("".join(cur).strip())
    return out


# The H1 of a record document repeats its own id; the index cell carries the bare title.
# Without this rule the differ reports EVERY row as a Title disagreement — measured 2,145
# false findings across the three indexes on the first probe run.
ID_PREFIX = re.compile(
    r'^\s*(?:Behavioral Contract\s+|Verification Property\s+|Story\s+)?'
    r'(?:BC-\d+\.\d+\.\d+|VP-\d+|S-\d+\.\d+[A-Za-z0-9.-]*|E-\d+)\s*[:—-]\s*')


def strip_id_prefix(s):
    return ID_PREFIX.sub("", s).strip()


# A status/points cell often carries the enum token plus a bracketed annotation:
# `merged [superseded by ADR-015]`. The token is derivable; the annotation is prose that
# no store column holds, so it is compared on the token and the annotation is reported as
# its own class rather than silently accepted or silently flagged.
ANNOT = re.compile(r'^([^\[(]+?)\s*[\[(].*[\])]\s*$')


def split_annotation(s):
    m = ANNOT.match(s)
    return (m.group(1).strip(), s[len(m.group(1)):].strip()) if m else (s, "")


def tables(body):
    """Fence-aware markdown tables, each carrying the heading it sits under.

    Keyed on the table's OWN header row, because column sets vary WITHIN one document:
    STORY-INDEX's E-0 table has 7 columns and its E-1 table has 8.
    """
    out, cur, heading, in_fence = [], None, "", False
    for ln, raw in enumerate(body.splitlines(), 1):
        if FENCE.match(raw):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = HEAD.match(raw)
        if m:
            heading = m.group(2).strip()
            cur = None
            continue
        s = raw.strip()
        if s.startswith("|") and s.endswith("|") and s.count("|") >= 2:
            cells = split_cells(s)
            if cur is None:
                cur = {"heading": heading, "header": cells, "rows": [], "line": ln}
                out.append(cur)
            elif all(re.fullmatch(r':?-{2,}:?', c) for c in cells if c):
                pass                        # the separator row
            else:
                cur["rows"].append({"cells": cells, "line": ln})
        else:
            cur = None
    return out


def firstH1(body):
    for raw in body.splitlines():
        m = re.match(r'^#\s+(.*)', raw)
        if m:
            return m.group(1).strip()
    return ""


def delink(s):
    return re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', s).strip()


def norm(s):
    return re.sub(r'\s+', ' ', delink(s).replace("**", "")).strip()


# ── load the records ─────────────────────────────────────────────────────────
bcs = {}
for dp, dn, fs in os.walk(os.path.join(ROOT, "specs", "behavioral-contracts")):
    dn[:] = [d for d in dn if d != ".git"]
    for f in fs:
        m = re.fullmatch(r'(BC-\d+\.\d+\.\d+)\.md', f)
        if not m:
            continue
        fm, body = fm_body(open(os.path.join(dp, f), encoding="utf-8", errors="replace").read())
        bcs[m.group(1)] = {"fm": fm, "h1": firstH1(body)}

vps = {}
for dp, dn, fs in os.walk(os.path.join(ROOT, "specs", "verification-properties")):
    dn[:] = [d for d in dn if d != ".git"]
    for f in fs:
        m = re.fullmatch(r'(VP-\d+)\.md', f)
        if not m:
            continue
        fm, body = fm_body(open(os.path.join(dp, f), encoding="utf-8", errors="replace").read())
        vps[m.group(1)] = {"fm": fm, "h1": firstH1(body)}

stories = {}
for dp, dn, fs in os.walk(os.path.join(ROOT, "stories")):
    dn[:] = [d for d in dn if d != ".git"]
    for f in fs:
        m = re.match(r'(S-\d+\.\d+[A-Za-z0-9.-]*?)[-.]', f)
        if not f.endswith(".md") or not m:
            continue
        fm, body = fm_body(open(os.path.join(dp, f), encoding="utf-8", errors="replace").read())
        sid = fm.get("story_id") or m.group(1).rstrip(".")
        stories.setdefault(sid, {"fm": fm, "h1": firstH1(body), "file": f})

print(f"records loaded: bc={len(bcs)} vp={len(vps)} story={len(stories)}\n")


TITLE_COLS = {"Title"}
# The annotation rule applies ONLY to enum-ish columns. Applied to Title it TRUNCATED
# `Registry rejects unknown entry fields (typo guard)` to its first clause and then reported
# the truncation as a disagreement — 252 self-inflicted BC findings and 40 story ones. A
# normalisation rule aimed at the wrong column manufactures exactly what it was added to
# prevent, so its scope is declared rather than global.
ENUM_COLS = {"Status", "Type", "Proof Method", "Scope", "Epic", "Points", "Priority",
             "Capability", "Domain Invariant"}
# Backticks are markup, not content: VP-069..071 title cells drop the code span the record's
# H1 carries. Same discipline story 12 needs for code spans, applied to cell text.
def strip_markup(s):
    return s.replace("`", "").strip()


def probe(name, path, want_header_has, keycol, cols, records, keyfix=lambda x: x):
    """cols maps an index COLUMN NAME -> a function of the record giving the derived value."""
    full = os.path.join(ROOT, path)
    if not os.path.exists(full):
        print(f"!! {name}: {path} ABSENT"); return
    fm, body = fm_body(open(full, encoding="utf-8", errors="replace").read())
    tabs = [t for t in tables(body) if all(h in t["header"] for h in want_header_has)]
    if not tabs:
        print(f"!! {name}: no table with columns {want_header_has} — REPORTED, not skipped")
        return
    nrows = sum(len(t["rows"]) for t in tabs)
    print(f"== {name}  ({path})")
    print(f"   tables matching {want_header_has}: {len(tabs)} · rows {nrows}")
    hdrs = collections.Counter(tuple(t["header"]) for t in tabs)
    if len(hdrs) > 1:
        print(f"   ⚠ {len(hdrs)} DISTINCT header signatures in one document:")
        for h, n in hdrs.most_common():
            print(f"       x{n}  {' | '.join(h)}")
    stats = {c: collections.Counter() for c in cols}
    shapes = {c: collections.Counter() for c in cols}
    examples = {c: [] for c in cols}
    keyed, unknown = 0, 0
    for t in tabs:
        idx = {h: i for i, h in enumerate(t["header"])}
        if keycol not in idx:
            continue
        for r in t["rows"]:
            if len(r["cells"]) <= idx[keycol]:
                continue
            k = keyfix(norm(r["cells"][idx[keycol]]))
            rec = records.get(k)
            if rec is None:
                unknown += 1
                continue
            keyed += 1
            for c, fn in cols.items():
                if c not in idx or len(r["cells"]) <= idx[c]:
                    stats[c]["col-absent"] += 1
                    continue
                authored = norm(r["cells"][idx[c]])
                derived = norm(str(fn(rec) or ""))
                if c in TITLE_COLS:
                    derived = strip_id_prefix(derived)
                authored, derived = strip_markup(authored), strip_markup(derived)
                if c in ENUM_COLS:
                    authored, annot = split_annotation(authored)
                    if annot:
                        stats[c]["authored-carries-annotation"] += 1
                if authored == derived:
                    stats[c]["agree"] += 1
                elif authored.lower() == derived.lower():
                    stats[c]["agree-casefold"] += 1
                    shapes[c]["case only"] += 1
                elif not authored or authored in ("--", "-", "TBD", "n/a", "N/A", "—"):
                    stats[c]["authored-placeholder"] += 1
                    shapes[c][f"placeholder {authored!r} vs {derived!r}"[:70]] += 1
                elif not derived:
                    stats[c]["derived-empty"] += 1
                    shapes[c][f"derived empty, authored {authored!r}"[:70]] += 1
                else:
                    stats[c]["DISAGREE"] += 1
                    if len(examples[c]) < 4:
                        examples[c].append(f"{k}: authored={authored!r} derived={derived!r}")
    print(f"   rows keyed to a record: {keyed} · key not a known record: {unknown}")
    for c in cols:
        tot = sum(stats[c].values()) or 1
        agree = stats[c]["agree"] + stats[c]["agree-casefold"]
        bits = " ".join(f"{k}={v}" for k, v in sorted(stats[c].items()))
        print(f"     {c:<20} {100*agree/tot:5.1f}% agree   {bits}")
        for e in examples[c]:
            print(f"         e.g. {e}")
        for sh, n in shapes[c].most_common(3):
            print(f"         shape x{n}: {sh}")
    print()


probe("BC-INDEX per-BC rows", "specs/behavioral-contracts/BC-INDEX.md",
      ["BC ID", "Title", "Status"], "BC ID",
      {"Title": lambda r: r["h1"],
       "Status": lambda r: r["fm"].get("status", ""),
       "Capability": lambda r: r["fm"].get("capability", "")},
      bcs)

probe("VP-INDEX Full Index", "specs/verification-properties/VP-INDEX.md",
      ["VP ID", "Title"], "VP ID",
      {"Title": lambda r: r["h1"],
       "Type": lambda r: r["fm"].get("type", ""),
       "Proof Method": lambda r: r["fm"].get("proof_method", ""),
       "Scope": lambda r: r["fm"].get("scope", ""),
       "Status": lambda r: r["fm"].get("status", "")},
      vps)

probe("STORY-INDEX per-epic rows", "stories/STORY-INDEX.md",
      ["Story ID", "Status"], "Story ID",
      {"Title": lambda r: r["h1"],
       "Status": lambda r: r["fm"].get("status", ""),
       "Epic": lambda r: r["fm"].get("epic_id", ""),
       "Points": lambda r: r["fm"].get("points", ""),
       "Priority": lambda r: r["fm"].get("priority", "")},
      stories)
