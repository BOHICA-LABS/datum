#!/usr/bin/env python3
"""PROBE for STORY 4: would `adversarial-finding` AS ROWS reproduce the counts the prose asserts?

Story 4's exit criterion is that `finding_count`, `severity_distribution` and
`total_findings` become DERIVED and agree with the prose they replace. That is only testable
if the extraction is first measured against the claims, per document, with the per-form
counts printed — the extractor in this repo has silently lost input four separate times, so
"it found some findings" is not evidence of anything.

Reuses fstar_compare.py's extraction rules deliberately: a second, subtly different
extractor would be one more thing to drift.

Read-only. Exit 0 always; this is a measurement, not a gate.
"""
import os, re, sys, collections, importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("fc", os.path.join(HERE, "fstar_compare.py"))
fc = importlib.util.module_from_spec(spec)
sys.argv = ["probe_findings"]          # keep fstar_compare's own CLI out of this
_stdout = sys.stdout
sys.stdout = open(os.devnull, "w")      # it prints its own report on import-run
try:
    spec.loader.exec_module(fc)
except SystemExit:
    pass
finally:
    sys.stdout.close()
    sys.stdout = _stdout

ROOT = fc.ROOT

# ── THE FIFTH SILENTLY-LOST INPUT, and the most pointed one ───────────────────
#
# fc.IDPAT requires a finding id to START with a severity or category word
# (CRIT|HIGH|MED|LOW|NIT|OBS|F|CV|SEC|PG). It therefore misses `ADV-S8P1-P01-HIGH-001` —
# which is EXACTLY the convention the adversarial-finding TEMPLATE declares
# (`finding_id: "ADV-<CYCLE>-P[N]-[SEV]-NNN"`), and which adv-s8.00-p1.md documents in its own
# `## Finding ID Convention` section. The one id form the extractor did not know is the
# declared standard, because the extractor was built from observed prose.
#
# fstar_compare.py is deliberately NOT edited: research/FSTAR-COMPARISON.md quotes its numbers
# (2,138 candidate lines, 87% precision) and they stand as measured. This is a SUPERSET, and
# the delta is reported below so the undercount is visible rather than silently corrected.
ADV_ID = r'ADV-[A-Za-z0-9]+-P\d+[A-Za-z0-9]*-(?:CRIT|CRITICAL|HIGH|MED|MEDIUM|LOW|NIT|NITPICK|OBS)-\d+'
# A SIXTH convention: `### P2-001 [MED] <statement>` — a pass-prefixed id with no severity or
# category word at all, and the severity in a BRACKET. adv-e8-p2.md claims findings_total: 7
# and defines exactly P2-001..P2-007, so the claim was right and the extractor saw none of them.
#
# Six id conventions across one corpus is not a parser problem to solve once; it is the
# ARGUMENT FOR STORY 4. With findings as rows the convention is declared once and enforced,
# instead of being discovered one form at a time by a regex that fails silently in between.
PASS_ID = r'P\d+[A-Za-z]?-\d+'
IDPAT2 = rf'(?:{ADV_ID}|{fc.IDPAT}|{PASS_ID})' 
fc.H_FIND = re.compile(rf'^#{{3,6}}\s+\**({IDPAT2})\**\s*[\u2014\u2013\-:|]?\s*(.*)$')
fc.T_FIND = re.compile(rf'^\|\s*\**({IDPAT2})\**\s*\|(.+)$')
# ── OWNERSHIP: a review MENTIONS findings it does not OWN ─────────────────────
#
# A pass-2 review has two parts: `## Part A — Fix Verification (Pass-1 Closure Audit)`, which
# re-states PASS-1's findings to audit their fixes, and `## Part B — New Findings`, which is
# what this pass introduces. `findings_total` counts Part B ONLY. Counting every mention gave
# 21 rows against a claimed 9 on adv-s8.08-p2.
#
# Same class as the shadow stage's scope predicate: a derived count needs a declared SCOPE or
# it counts mentions. Here the scope is structural — the section the finding sits under.
MENTION_SEC = re.compile(
    r'(fix[- ]verification|closure audit|prior[- ]pass|previous[- ]pass|pass-\d+ closure'
    r'|carried[- ]forward|re-?verification|resolution status|already (closed|resolved))', re.I)
OWNED_SEC = re.compile(r'(new findings|fresh[- ]context|findings \(this pass\)|part b)', re.I)

BRACKET_SEV = re.compile(r'^\s*\[?\**(CRIT|CRITICAL|HIGH|MED|MEDIUM|LOW|NIT|NITPICK|OBS)\**\]?', re.I)

ADV_SEV = re.compile(r'^ADV-[A-Za-z0-9]+-P\d+[A-Za-z0-9]*-([A-Za-z]+)-\d+$')

# The claim forms, measured: finding_count (123 docs), findings_total (35), findings: 1H/3M/2L
# (4), severity_distribution (2), total_findings (1).
CLAIM_INT = re.compile(r'^(finding_count|findings_total|total_findings|observations):\s*["\']?(\d+)')
CLAIM_DIST = re.compile(r'^(findings|severity_distribution):\s*["\']?([0-9]+[CHMLNO][A-Za-z0-9/+ ]*)')
DIST_TOK = re.compile(r'(\d+)\s*([A-Za-z]+)')

# Severity spellings -> the canonical bucket. Measured from the corpus rather than invented:
# the same review set writes CRIT and CRITICAL, MED and MEDIUM, NIT and NITPICK.
SEV = {"crit": "CRIT", "critical": "CRIT", "c": "CRIT",
       "high": "HIGH", "h": "HIGH",
       "med": "MED", "medium": "MED", "m": "MED",
       "low": "LOW", "l": "LOW",
       "nit": "NIT", "nitpick": "NIT", "n": "NIT",
       "obs": "OBS", "o": "OBS", "observation": "OBS"}


def canon_sev(s):
    return SEV.get(s.strip().lower(), "")


BOLD_SEV = re.compile(r'\*\*Severity:?\*\*:?\s*\**\s*([A-Za-z]+)')
SEC_SEV = re.compile(r'^#{2,4}\s+\**(CRIT|CRITICAL|HIGH|MED|MEDIUM|LOW|NIT|NITPICK|OBS)\b', re.I)

SEV_SOURCES = collections.Counter()


def sev_of(f):
    """Severity through five ORDERED sources; records which one resolved it.

    Order matters: an explicit per-finding statement outranks the section it sits under,
    and the id prefix is LAST because IDPAT admits F/CV/SEC/PG, which are categories and
    not severities at all.
    """
    for k in ("Severity", "severity", "Sev"):
        if k in f.get("attrs", {}):
            c = canon_sev(re.split(r'[^A-Za-z]', f["attrs"][k].strip(), 1)[0])
            if c:
                SEV_SOURCES["attr-bullet"] += 1; return c
    mb2 = BRACKET_SEV.match(f.get("statement") or "")
    if mb2:
        c = canon_sev(mb2.group(1))
        if c:
            SEV_SOURCES["bracket-in-statement"] += 1; return c
    if f.get("bold_sev"):
        c = canon_sev(f["bold_sev"])
        if c:
            SEV_SOURCES["bold-line"] += 1; return c
    if f.get("table_sev"):
        c = canon_sev(f["table_sev"])
        if c:
            SEV_SOURCES["table-column"] += 1; return c
    ma = ADV_SEV.match(f["id"])
    if ma:
        c = canon_sev(ma.group(1))
        if c:
            SEV_SOURCES["id-embedded-ADV"] += 1; return c
    m = re.match(r'^([A-Za-z]+)', f["id"])
    if m:
        c = canon_sev(m.group(1))
        if c:
            SEV_SOURCES["id-prefix"] += 1; return c
    if f.get("section_sev"):
        c = canon_sev(f["section_sev"])
        if c:
            SEV_SOURCES["section-heading"] += 1; return c
    SEV_SOURCES["(unresolved)"] += 1
    return ""


def parse_dist(s):
    """`1H/3M/2L` or `0C+4H+3M+1L+1N` -> {'HIGH': 1, ...}. Unknown tokens are REPORTED."""
    out, unknown = collections.Counter(), []
    for n, word in DIST_TOK.findall(s):
        c = canon_sev(word)
        if c:
            out[c] += int(n)
        else:
            unknown.append(word)
    return out, unknown


def body_of(text):
    block, body = fc.fm_body(text)
    return body if block is not None else text


def dedupe(found):
    """ONE ROW PER (document, finding_id) — the composite natural key the
    adversarial-finding template already declares.

    Load-bearing, not tidiness: a review states a finding as a `### HIGH-P34-001:` heading AND
    repeats it in a closure/summary table, so counting LINES THAT MENTION a finding gave
    EXACTLY 2x the asserted distribution on pass-34 (2H/6M/4L against a claimed 1H/3M/2L).
    Counting mentions is not counting findings — the same lesson as "counting files is not
    counting artifacts", one level down.

    The heading form wins over the table row: it is where the statement and the
    `**Severity:**` line live.
    """
    best, order, dupes = {}, [], 0
    rank = {"heading": 0, "inline": 1, "table-row": 2}
    for f in found:
        k = f["id"]
        if k not in best:
            best[k] = f; order.append(k)
        else:
            dupes += 1
            if rank.get(f["form"], 9) < rank.get(best[k]["form"], 9):
                merged = dict(f)
                for src in ("bold_sev", "table_sev", "section_sev", "attrs"):
                    if not merged.get(src) and best[k].get(src):
                        merged[src] = best[k][src]
                best[k] = merged
            else:
                for src in ("bold_sev", "table_sev", "section_sev"):
                    if not best[k].get(src) and f.get(src):
                        best[k][src] = f[src]
    return [best[k] for k in order], dupes


def enrich(found, body):
    """Attach the bold `**Severity:** X` line, the enclosing severity section heading, and the
    table Severity cell — the three sources fc.findings_in does not itself record."""
    lines = body.splitlines()
    sec = ""
    top = ""
    id_line = {}
    for i, ln in enumerate(lines):
        if re.match(r'^#{1,2}\s+', ln):
            top = ln
        m = SEC_SEV.match(ln)
        if m:
            sec = m.group(1)
        for f in found:
            if f["id"] in ln and i not in id_line.values():
                id_line.setdefault(f["id"], i)
        for f in found:
            defining = re.match(r'^#{3,6}\s+\**' + re.escape(f["id"]), ln) is not None
            if defining and f.get("_defined_top") is None:
                f["_defined_top"] = top
            if f.get("_sec") is None and f["id"] in ln:
                f["_sec"] = sec
                f["_top"] = top
    for f in found:
        f["section_sev"] = f.get("_sec") or ""
        t = f.get("_defined_top") or f.get("_top") or ""
        # Default OWNED: most reviews have no Part A/B split at all, and defaulting to
        # "mentioned" would silently drop their findings — the failure mode this whole
        # exercise keeps re-learning.
        f["owned"] = not (MENTION_SEC.search(t) and not OWNED_SEC.search(t))
        i = id_line.get(f["id"])
        if i is not None:
            window = "\n".join(lines[i:i + 8])
            mb = BOLD_SEV.search(window)
            if mb:
                f["bold_sev"] = mb.group(1)
        if f["form"] == "table-row":
            for cell in (f.get("rest") or f.get("statement") or "").split("|"):
                c = canon_sev(cell.strip().strip("*"))
                if c:
                    f["table_sev"] = cell.strip().strip("*"); break


def main():
    docs = 0
    claim_int_docs = claim_dist_docs = 0
    agree_int = disagree_int = 0
    agree_dist = disagree_dist = 0
    forms = collections.Counter()
    malformed_total = 0
    int_field_used = collections.Counter()
    examples_int, examples_dist = [], []
    unknown_tokens = collections.Counter()
    per_cycle = collections.defaultdict(lambda: {"docs": 0, "rows": 0, "claimed": 0})
    sev_hist = collections.Counter()
    no_claim = 0
    dupe_total = [0]
    mentioned_total = [0]

    for dp, dn, fs in os.walk(os.path.join(ROOT, "cycles")):
        dn[:] = [d for d in dn if d != ".git"]
        for fn in fs:
            if not fn.endswith(".md"):
                continue
            path = os.path.join(dp, fn)
            text = open(path, encoding="utf-8", errors="replace").read()
            m = fc.DT.search(text) or re.search(r'^document_type:\s*["\']?([^"\'\s#]+)', text, re.M)
            dt = m.group(1) if m else ""
            if dt not in fc.REVIEW_TYPES:
                continue
            docs += 1
            rel = os.path.relpath(path, ROOT)
            cycle = rel.split(os.sep)[1] if os.sep in rel else "?"

            body = body_of(text)
            found, malformed = fc.findings_in({"body": body, "path": rel, "cycle": cycle, "pass": None})
            enrich(found, body)
            found, dupes = dedupe(found)
            dupe_total[0] += dupes
            malformed_total += malformed
            for f in found:
                forms[f["form"]] += 1
                sev_hist[sev_of(f) or "(none)"] += 1
            per_cycle[cycle]["docs"] += 1
            per_cycle[cycle]["rows"] += len(found)

            block, _ = fc.fm_body(text)
            fmblock = "".join(block) if block else ""

            owned = [f for f in found if f.get("owned", True)]
            mentioned_total[0] += len(found) - len(owned)
            claimed_any = False
            for line in fmblock.splitlines():
                mi = CLAIM_INT.match(line.strip())
                if mi:
                    claimed_any = True
                    field, n = mi.group(1), int(mi.group(2))
                    int_field_used[field] += 1
                    claim_int_docs += 1
                    per_cycle[cycle]["claimed"] += n
                    if n == len(owned):
                        agree_int += 1
                    else:
                        disagree_int += 1
                        if len(examples_int) < 8:
                            examples_int.append(
                                f"{rel}: {field}={n} owned={len(owned)} (all mentions {len(found)})")
                md = CLAIM_DIST.match(line.strip())
                if md:
                    claimed_any = True
                    claim_dist_docs += 1
                    want, unk = parse_dist(md.group(2))
                    for u in unk:
                        unknown_tokens[u] += 1
                    got = collections.Counter(sev_of(f) for f in owned if sev_of(f))
                    if want == got:
                        agree_dist += 1
                    else:
                        disagree_dist += 1
                        if len(examples_dist) < 8:
                            examples_dist.append(
                                f"{rel}: claims {dict(want)} rows give {dict(got)}")
            if not claimed_any:
                no_claim += 1

    print(f"review documents scanned      : {docs}")
    print(f"extracted finding rows        : {sum(forms.values())}")
    print("  by form                     : " + " · ".join(f"{k} {v}" for k, v in forms.most_common()))
    print(f"  malformed (reported, kept)  : {malformed_total}")
    print(f"  duplicate MENTIONS collapsed : {dupe_total[0]} (one row per (document, finding_id))")
    print(f"  rows MENTIONED not OWNED     : {mentioned_total[0]} (a pass-2 fix-verification section "
          f"re-states pass-1's findings; findings_total counts only what the pass introduces)")
    print("  by severity                 : " + " · ".join(f"{k} {v}" for k, v in sev_hist.most_common()))
    print("  severity RESOLVED VIA        : " + " · ".join(f"{k} {v}" for k, v in SEV_SOURCES.most_common()))
    print()
    print(f"documents asserting an INT count : {claim_int_docs}  "
          f"({' · '.join(f'{k} {v}' for k, v in int_field_used.most_common())})")
    print(f"    agree with the row count     : {agree_int}")
    print(f"    disagree                     : {disagree_int}")
    for e in examples_int:
        print(f"      {e}")
    print()
    print(f"documents asserting a DISTRIBUTION : {claim_dist_docs}")
    print(f"    agree with the rows           : {agree_dist}")
    print(f"    disagree                      : {disagree_dist}")
    for e in examples_dist:
        print(f"      {e}")
    if unknown_tokens:
        print(f"    UNKNOWN severity tokens in claims: {dict(unknown_tokens)}")
    print()
    print(f"review documents asserting NO count at all : {no_claim} of {docs} "
          f"({100*no_claim/max(docs,1):.0f}%) — nothing to compare, and that is the finding")
    print()
    print("per cycle (rows extracted vs summed int claims):")
    for c, d in sorted(per_cycle.items(), key=lambda kv: -kv[1]["rows"]):
        print(f"  {d['rows']:6d} rows  {d['claimed']:6d} claimed  {d['docs']:4d} docs  {c}")


main()
