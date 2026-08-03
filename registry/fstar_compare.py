#!/usr/bin/env python3
"""#671's phase-1 exit criterion: can `datum` reproduce the known F-* findings?

THE QUESTION. `datum` parses FRONTMATTER ONLY. #671 insists the real drift lives in BODY PROSE
(ADR-NNN section cites, BC version cells copied into story tables). Whoever is right decides
whether the type registry needs prose-reference link types BEFORE 24 projects migrate onto it.
So: take the findings the adversary actually reported and classify each by WHAT A PARSER WOULD
HAVE TO SEE to catch it.

⚠ EXTRACTION RULE — v2, AND WHY v1 WAS WRONG.
v1 recognised only the inline `SEV-NNN: statement` form and ran on 8 docs/cycle. It found
ELEVEN findings, all from ONE file, and would have supported a confident verdict off 0.3% of
the data. That is the fourth instance in this spike of a parser silently losing input, so the
rule is stated in full and the per-form counts are printed:

  Population: every document in vsdd-factory's cycles/ tree whose document_type is one of the
  12 spellings that alias to adversarial-review (390 documents, 7 cycles). `--recent N` also
  reports the top-N-passes-per-cycle subset, since #671 says "recent adversarial passes".

  A FINDING is any of THREE forms, all counted:
    heading    `### <ID> — <statement>`            (2,370 candidates corpus-wide)
    table-row  `| <ID> | <SEV> | <location> | <description> |`   (956)
    inline     `**<SEV>-<NNN>: <statement>**` + following `- Key: value` bullets  (22)
  where <ID> matches (CRIT|CRITICAL|HIGH|MED|MEDIUM|LOW|NIT|NITPICK|OBS|F|CV|SEC|PG)<tag>.
  Lines that look like a finding but yield no statement are counted as MALFORMED and reported,
  never dropped.

CLASSIFICATION. Keyword rules over statement + location + description, first match wins.
Every rule's hit count is printed and samples are dumped, so it is auditable rather than
asserted. Six classes — class F was added after reading the data, because a large share of
adversarial findings are SEMANTIC judgements about spec completeness that no parser of any
kind can reach, and folding those into "process" would have overstated what prose extraction
buys.
  A REGISTRY-ELIMINATES  derived-data staleness; impossible once the artifact is derived
  B FRONTMATTER-REACHABLE datum today, or with a declared field/enum/link
  C PROSE-REFERENCE       needs body-prose extraction — #671's territory
  D EXTERNAL-STATE        needs a fact from outside .factory (PR state, SHA, CI, source)
  E PROCESS-UNREACHABLE   about how a gate was RUN, not about data
  F SEMANTIC-JUDGEMENT    requires understanding the spec's meaning, not its structure

Read-only. Exit 0 always; this is a measurement, not a gate.
"""
import os, re, sys, json, collections

ROOT = os.path.expanduser("~/Dev/vsdd-factory/.factory")
HERE = os.path.dirname(os.path.abspath(__file__))
RECENT = int(os.environ.get("FSTAR_RECENT", "8"))

IDPAT = r'(?:CRIT|CRITICAL|HIGH|MED|MEDIUM|LOW|NIT|NITPICK|OBS|F|CV|SEC|PG)[A-Z0-9]*[-–][A-Za-z0-9.\-]+'
H_FIND = re.compile(rf'^#{{3,5}}\s+\**({IDPAT})\**\s*[—–\-:|]?\s*(.*)$')
T_FIND = re.compile(rf'^\|\s*\**({IDPAT})\**\s*\|(.+)$')
I_FIND = re.compile(rf'^\**((?:CRIT|CRITICAL|HIGH|MED|MEDIUM|LOW|NIT|NITPICK|OBS|F)-\d+)\**\s*(?:\([^)]*\))?\s*:\s*(.+?)\**$')
ATTR = re.compile(r'^\s*[-*]\s*([A-Z][A-Za-z /]+):\s*(.*)$')
DT = re.compile(r'^document_type:\s*["\']?([^"\'\s#]+)')
PASSN = re.compile(r'^pass:\s*["\']?(\d+)')
SEVWORD = re.compile(r'^(CRIT|CRITICAL|HIGH|MED|MEDIUM|LOW|NIT|NITPICK|OBS)', re.I)

REVIEW_TYPES = {
    "adversarial-review", "adversary-review", "adversarial-review-pass", "adversary-pass",
    "adversary-pass-report", "adversarial-review-report", "adversarial-pass-report",
    "local-adversary-review", "per-story-adversary-review", "adversary-report",
    "pr-adversary-pass-report", "adversarial-review-rejected",
}

RULES = [
    ("E", "gate-invocation",       r'literal[- ]shell|invoked via|pseudocode|interpretation layer|self-appl|narrative interpretation|captured stdout|attested as'),
    ("E", "codified-no-gate",      r'no runtime gate|codified.{0,20}without.{0,20}runtime|enforcement does not|no (?:corresponding )?(?:WASM )?hook|lint(?:-\d+)? (?:missing|absent)|no lint'),
    ("A", "index-body-table",      r'body[- ](?:table|row)|INDEX(?:\.md)? body|upstream[- ]index|index body|body table row'),
    ("A", "derived-count",         r'count(?:s)? (?:disagree|stale|mismatch|drift|prose says)|total_bcs|stated count|Total BCs|story_count|actual (?:is|count)|says \d+.{0,20}actual'),
    ("A", "index-registration",    r'not (?:registered|listed|enumerated) in (?:STORY-)?(?:BC-)?(?:VP-)?(?:ARCH-)?INDEX|INDEX.{0,30}does not (?:include|list)|missing (?:from )?(?:the )?index'),
    ("A", "index-stale",           r'(?:INDEX|STORY-INDEX|BC-INDEX|VP-INDEX|ARCH-INDEX).{0,60}stale|stale narrative'),
    ("C", "version-cite",          r'4-index|four-index|version cite|cites .{0,12}v\d|\b(?:BC|VP|STORY|ARCH) v\d|version cell|version_cite|v\d\.\d+.{0,30}(?:stale|drift)'),
    ("D", "pr-merge-state",        r'MERGED PR|merged PR|PR #\d+|at merge time|develop_sha|post-merge|commit [0-9a-f]{7}|SHA'),
    ("D", "external-artifact",     r'\bCI\b|workflow|test suite|cargo|\.rs\b|\.sh\b|\.py\b|source file|implementation (?:file|code)|codebase'),
    ("B", "frontmatter-field",     r'frontmatter|lifecycle_status|status: draft|status draft|traces_to|input-hash|document_type|frontmatter lacks|missing (?:the )?field|empty (?:array|list)'),
    ("B", "link-integrity",        r'dangling|does not exist|never written|missing (?:BC|VP|story|ADR|epic)\b|unresolved (?:ref|id)|nonexistent'),
    ("C", "prose-section-ref",     r'§|ADR-\d+ (?:Decision|section)|::|anchor|body (?:prose|text)|Precedence Ladder|EC-\d+|Postcondition|Precondition'),
    ("C", "prose-numeric-claim",   r'~\d|approximat|literal wc|line[- ]growth|banner literal|line \d+ states'),
    ("F", "not-enumerated",        r'not enumerated|not covered|uncovered|undescribed|undocumented|missing sibling|not bound|unstated|not (?:disclosed|specified)|no (?:mention|description)'),
    ("F", "semantic-quality",      r'grammar|awkward|terminology|wording|ambiguous|misleading|unclear|inconsistent (?:with|terminology)|naming|readab'),
    ("F", "spec-completeness",     r'edge case|variant|fallback path|should (?:also )?(?:describe|specify|cover)|incomplete|gap in|does not (?:describe|specify|account)'),
]
NAMES = {
    "A": "REGISTRY-ELIMINATES   derived data; impossible once the artifact is derived",
    "B": "FRONTMATTER-REACHABLE  datum today, or with a declared field/enum/link",
    "C": "PROSE-REFERENCE        needs body-prose extraction (#671's claim)",
    "D": "EXTERNAL-STATE         needs a fact from outside .factory",
    "E": "PROCESS-UNREACHABLE    about how a gate was RUN, not about data",
    "F": "SEMANTIC-JUDGEMENT     requires understanding meaning, not structure",
    "?": "UNMATCHED              no rule fired — reported, never assumed benign",
}


def fm_body(txt):
    L = txt.splitlines(keepends=True)
    if not L or L[0].strip() != "---":
        return None, txt
    for i in range(1, len(L)):
        if L[i].strip() in ("---", "..."):
            return L[1:i], "".join(L[i + 1:])
    return None, txt


def collect():
    docs = []
    for dp, dn, fs in os.walk(os.path.join(ROOT, "cycles")):
        dn[:] = [d for d in dn if d != ".git"]
        for f in fs:
            if not f.endswith(".md"):
                continue
            p = os.path.join(dp, f)
            try: txt = open(p, encoding="utf-8", errors="replace").read()
            except OSError: continue
            block, body = fm_body(txt)
            if block is None:
                continue
            dt = pw = cyc = None
            for line in block:
                m = DT.match(line)
                if m and dt is None: dt = m.group(1)
                m2 = PASSN.match(line)
                if m2 and pw is None: pw = int(m2.group(1))
                if line.startswith("cycle:") and cyc is None:
                    cyc = line.split(":", 1)[1].strip().strip('"\'')
            if dt in REVIEW_TYPES:
                docs.append({"path": os.path.relpath(p, ROOT), "type": dt, "pass": pw,
                             "cycle": cyc or os.path.basename(dp), "body": body})
    return docs


def findings_in(doc):
    """Three forms. Returns (findings, malformed_count)."""
    out, malformed = [], 0
    lines = doc["body"].splitlines()
    pending = None
    for idx, raw in enumerate(lines):
        s = raw.strip()
        m = H_FIND.match(s)
        if m:
            if pending: out.append(pending)
            stmt = m.group(2).strip()
            # a heading with no statement: take the next non-blank line as the statement
            if not stmt:
                for j in range(idx + 1, min(idx + 4, len(lines))):
                    if lines[j].strip():
                        stmt = lines[j].strip(); break
            if not stmt:
                malformed += 1; pending = None; continue
            pending = {"form": "heading", "id": m.group(1), "statement": stmt, "attrs": {}}
            continue
        m = T_FIND.match(s)
        if m:
            if pending: out.append(pending); pending = None
            cells = [c.strip().strip('*') for c in m.group(2).split("|")]
            cells = [c for c in cells if c != ""]
            if not cells:
                malformed += 1; continue
            sev = cells[0] if cells and SEVWORD.match(cells[0]) else ""
            rest = cells[1:] if sev else cells
            loc = rest[0] if rest else ""
            desc = " ".join(rest[1:]) if len(rest) > 1 else ""
            if not (loc or desc):
                malformed += 1; continue
            out.append({"form": "table-row", "id": m.group(1), "sev": sev,
                        "statement": desc or loc, "attrs": {"Location": loc, "Defect": desc}})
            continue
        m = I_FIND.match(s)
        if m:
            if pending: out.append(pending)
            pending = {"form": "inline", "id": m.group(1), "statement": m.group(2).strip(), "attrs": {}}
            continue
        if pending is not None:
            a = ATTR.match(raw)
            if a:
                pending["attrs"][a.group(1).strip()] = a.group(2).strip()
            elif s.startswith("#"):
                out.append(pending); pending = None
    if pending: out.append(pending)
    for f in out:
        f.setdefault("sev", "")
        if not f["sev"]:
            mm = SEVWORD.match(f["id"])
            f["sev"] = mm.group(1).upper() if mm else "?"
        f["doc"] = doc["path"]; f["cycle"] = doc["cycle"]; f["pass"] = doc["pass"]
    return out, malformed


def classify(f):
    text = " ".join([f["statement"], f["attrs"].get("Location", ""),
                     f["attrs"].get("Defect", ""), f["attrs"].get("Recommended fix", "")])
    for cls, name, rx in RULES:
        if re.search(rx, text, re.I):
            return cls, name
    return "?", "unmatched"


def report(label, findings, malformed, forms):
    tot = len(findings)
    print(f"\n{'='*78}\n{label}: {tot} findings\n{'='*78}")
    print("by form   : " + " · ".join(f"{k} {v}" for k, v in forms.most_common()))
    print(f"malformed : {malformed} (reported, not dropped)")
    print("severity  : " + " · ".join(f"{k} {v}" for k, v in
                                      collections.Counter(f["sev"] for f in findings).most_common(8)))
    cls_c = collections.Counter(); rule_c = collections.Counter()
    samples = collections.defaultdict(list)
    for f in findings:
        c, r = classify(f)
        f["class"], f["rule"] = c, r
        cls_c[c] += 1; rule_c[(c, r)] += 1
        if len(samples[c]) < 3:
            samples[c].append(f)
    print()
    for c in "ABCDEF?":
        n = cls_c[c]
        if not n: continue
        print(f"{c}  {n:5d}  {n*100.0/tot:5.1f}%   {NAMES[c]}")
        for (cc, rn), rnum in rule_c.most_common():
            if cc == c:
                print(f"          {rnum:5d}  rule '{rn}'")
    print(f"\n--- samples for hand-verification ---")
    for c in "ABCDEF?":
        for f in samples[c]:
            print(f"  [{c}/{f['rule']}] {f['id']} ({f['form']}) {f['statement'][:120]}")
    return cls_c, samples


def main():
    docs = collect()
    if not docs:
        print("FATAL no adversarial-review documents found", file=sys.stderr); sys.exit(2)
    print(f"review documents: {len(docs)} across {len({d['cycle'] for d in docs})} cycles")

    allf, mal, forms = [], 0, collections.Counter()
    for d in docs:
        fs, m = findings_in(d)
        allf += fs; mal += m
        for f in fs: forms[f["form"]] += 1

    by_cycle = collections.defaultdict(list)
    for d in docs: by_cycle[d["cycle"]].append(d)
    recent_paths = set()
    for c, ds in by_cycle.items():
        ds.sort(key=lambda x: (x["pass"] is None, x["pass"] or 0), reverse=True)
        recent_paths |= {d["path"] for d in ds[:RECENT]}
    recentf = [f for f in allf if f["doc"] in recent_paths]
    rforms = collections.Counter(f["form"] for f in recentf)

    cls_all, _ = report("FULL POPULATION (all review documents)", allf, mal, forms)
    cls_rec, _ = report(f"RECENT PASSES ONLY (top {RECENT}/cycle, {len(recent_paths)} docs)",
                        recentf, 0, rforms)

    print(f"\n{'='*78}\nVERDICT — derived from the numbers above, not pre-written\n{'='*78}")
    for label, cc in (("full population", cls_all), ("recent passes", cls_rec)):
        t = sum(cc.values())
        if not t: continue
        addressable = cc["A"] + cc["B"]
        print(f"\n{label} (n={t}):")
        print(f"  registry+datum as designed already covers : {addressable:5d}  {addressable*100.0/t:5.1f}%"
              f"   (A {cc['A']} derived-data + B {cc['B']} frontmatter)")
        print(f"  REQUIRES prose extraction (#671)       : {cc['C']:5d}  {cc['C']*100.0/t:5.1f}%")
        print(f"  out of reach of ANY parser             : {cc['E']+cc['F']:5d}  "
              f"{(cc['E']+cc['F'])*100.0/t:5.1f}%   (E {cc['E']} process + F {cc['F']} semantic)")
        print(f"  needs external state                   : {cc['D']:5d}  {cc['D']*100.0/t:5.1f}%")
        if cc["?"]:
            print(f"  UNMATCHED, needs a human read          : {cc['?']:5d}  {cc['?']*100.0/t:5.1f}%")

    json.dump([{k: v for k, v in f.items() if k != "body"} for f in allf],
              open(os.path.join(HERE, "fstar_findings.json"), "w"), indent=1)
    print(f"\nwrote registry/fstar_findings.json ({len(allf)} findings)")


if __name__ == "__main__":
    main()
