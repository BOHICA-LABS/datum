#!/usr/bin/env python3
"""PROBE for STORY 12: what do prose references actually look like, and what does each RULE cost?

Story 12 is worth 21.8% +/-8.7 of the adversary's findings, and its own declared rules warn
that getting them wrong "manufactures false findings". So the order is the same as story 7's
and story 4's: measure the classes and the per-rule impact FIRST, then write the resolver.

The number that matters most is NOT how many references exist. It is how many raw candidates
each rule ELIMINATES — because a resolver without those rules would report every one of them
as a finding, confidently and wrongly.

Read-only. Exit 0 always; this is a measurement, not a gate.
"""
import os, re, sys, collections

ROOT = os.path.expanduser(sys.argv[1] if len(sys.argv) > 1 else "~/Dev/vsdd-factory/.factory")

# The kinds, VERBATIM from artifact-type-registry.yaml prose_ref_kinds. Copied as patterns
# rather than re-invented: this probe measures the DECLARED standard, not a parallel one.
KINDS = {
    "ac":       (r'AC-\d+',                  "file"),
    "ec":       (r'EC-\d+',                  "file"),
    "pc":       (r'PC-?\d+',                 "file"),
    "t_task":   (r'T-\d+',                   "file"),
    "finding":  (r'F-[A-Za-z0-9]+-\d+',      "cycle"),
    "decision": (r'D-\d+',                   "cycle"),
    "lesson":   (r'L-[A-Za-z0-9]*-?\d+',     "cycle"),
    "policy":   (r'POL(?:ICY)?[- ]\d+',      "project"),
    "section":  (r'§[^,;)\s][^,;)]*',        "file"),
}
# Anchored with \b on BOTH sides plus a guard against a preceding [A-Za-z-]. The registry's
# declared patterns are unanchored; measured consequence below.
KIND_RE = {k: re.compile(r'(?<![A-Za-z0-9-])(?:' + p + r')(?![A-Za-z0-9])') for k, (p, _) in KINDS.items()}
KIND_RE_RAW = {k: re.compile(p) for k, (p, _) in KINDS.items()}   # the DECLARED pattern, as-is

# An OWNER is a top-level artifact id. A cross-document citation of a sub-artifact id must
# name one, or it is `unresolvable` — never `dangling` (prose_ref_rules
# report-unresolvable-separately).
OWNER_RE = re.compile(r'\b(?:BC-\d+\.\d+\.\d+|VP-\d+|S-\d+\.\d+[A-Za-z0-9.\-]*|E-\d+|ADR-\d+|SS-\d+)\b')

# The declared pattern requires a per|see|against preposition. Measured against three looser
# forms, because a cite the checker cannot see is a cite it cannot judge, and pin_policy is
# the whole reason this kind exists.
VERSION_CITE = re.compile(r'(?:per|see|against)\s+([A-Z][A-Z-]*(?:-INDEX)?(?:\.md)?)\s+v(\d+\.\d+)')
VERSION_CITE_LOOSE = re.compile(r'\b([A-Z][A-Z-]{2,}(?:-INDEX)?(?:\.md)?)\s+v(\d+\.\d+)')

FENCE = re.compile(r'^\s*(```|~~~)')

GENERIC_ID = re.compile(r'\b[A-Z][A-Z]{0,5}(?:-[A-Za-z0-9.]+){1,3}\b')
TOPLEVEL = re.compile(r'(?:BC-\d+\.\d+\.\d+|VP-\d+|S-\d+\.\d+[A-Za-z0-9.\-]*|E-\d+|ADR-\d+'
                      r'|SS-\d+|CAP-\d+|DI-\d+|NFR-[A-Za-z0-9.\-]+|FR-[A-Za-z0-9.\-]+)')


def fm_body(txt):
    L = txt.splitlines(keepends=True)
    if not L or L[0].strip() != "---":
        return None, txt
    for i in range(1, len(L)):
        if L[i].strip() in ("---", "..."):
            return L[1:i], "".join(L[i + 1:])
    return None, txt


def doc_type(block):
    if not block:
        return ""
    for line in block:
        m = re.match(r'^document_type:\s*["\']?([^"\'\s#]+)', line)
        if m:
            return m.group(1)
    return ""


def mask_code(line):
    """Blank out backtick spans and markdown link TARGETS, preserving offsets.

    RULE exclude-code-spans. Offsets are preserved rather than the text removed so that a
    match position still means what it meant — a rule that shifts offsets while filtering is
    how a checker reports the wrong location for a real finding.
    """
    out = list(line)
    # backtick spans (single or double)
    for m in re.finditer(r'`{1,2}[^`]*`{1,2}', line):
        for i in range(m.start(), m.end()):
            out[i] = " "
    # link targets: keep the TEXT, blank the (target)
    for m in re.finditer(r'\]\(([^)]*)\)', line):
        for i in range(m.start(), m.end()):
            out[i] = " "
    return "".join(out)


def strip_fences(lines):
    """Return (masked_lines, n_lines_inside_fences)."""
    out, in_fence, fenced = [], False, 0
    for ln in lines:
        if FENCE.match(ln):
            in_fence = not in_fence
            out.append("")
            fenced += 1
            continue
        if in_fence:
            out.append("")
            fenced += 1
            continue
        out.append(ln)
    return out, fenced


# A DEFINITION of a sub-artifact id: a heading, a table-row first cell, or a bold label.
def definitions(kind, lines):
    pat = KINDS[kind][0]
    defs = set()
    for ln in lines:
        for m in (re.match(r'^#{1,6}\s+\**(' + pat + r')\b', ln),
                  re.match(r'^\|\s*\**(' + pat + r')\**\s*\|', ln),
                  re.match(r'^\s*[-*]?\s*\*\*(' + pat + r')\**[:.]', ln)):
            if m:
                defs.add(m.group(1))
    return defs


def scope_key(kind, rel):
    """The resolution scope declared for this kind: file | cycle | project.

    LOAD-BEARING, and my first cut got it wrong. Resolving `decision`, `finding` and `lesson`
    (scope: cycle) and `policy` (scope: project) only against the CITING FILE reported 52.8%
    of all candidates as unresolvable — 38,568 of them. That would have been the false finding
    set the rule report-unresolvable-separately exists to prevent, produced by ignoring the
    `scope` field the registry declares for exactly this purpose.
    """
    sc = KINDS[kind][1]
    if sc == "file":
        return rel
    if sc == "cycle":
        parts = rel.split(os.sep)
        return parts[1] if len(parts) > 1 and parts[0] == "cycles" else "(no-cycle)"
    return ""


def collect_definitions():
    """PASS 1: every sub-artifact id DEFINED anywhere, indexed by (kind, scope-key)."""
    idx = collections.defaultdict(set)
    for dp, dn, fs in os.walk(ROOT):
        dn[:] = [d for d in dn if d != ".git"]
        for fn in fs:
            if not fn.endswith(".md"):
                continue
            path = os.path.join(dp, fn)
            rel = os.path.relpath(path, ROOT)
            try:
                txt = open(path, encoding="utf-8", errors="replace").read()
            except OSError:
                continue
            block, body = fm_body(txt)
            if block is None:
                continue
            lines = body.splitlines()
            for kind in KINDS:
                for d in definitions(kind, lines):
                    idx[(kind, scope_key(kind, rel))].add(d)
                    idx[(kind, "__any__")].add(d)
    return idx


def main():
    defidx = collect_definitions()
    docs = 0
    raw = collections.Counter()          # every textual candidate, before ANY rule
    in_code = collections.Counter()      # eliminated by exclude-code-spans
    is_definition = collections.Counter()  # the defining occurrence, not a reference
    resolved_local = collections.Counter()
    resolved_scope = collections.Counter()
    owner_stated = collections.Counter()
    unresolvable = collections.Counter()
    dangling = collections.Counter()
    fenced_lines = 0
    version_cites = 0
    version_cites_loose = 0
    undeclared = collections.Counter()
    undeclared_total = [0]
    over_match = collections.Counter()
    per_type = collections.Counter()
    examples = collections.defaultdict(list)

    for dp, dn, fs in os.walk(ROOT):
        dn[:] = [d for d in dn if d != ".git"]
        for fn in fs:
            if not fn.endswith(".md"):
                continue
            path = os.path.join(dp, fn)
            rel = os.path.relpath(path, ROOT)
            try:
                txt = open(path, encoding="utf-8", errors="replace").read()
            except OSError:
                continue
            block, body = fm_body(txt)
            if block is None:
                continue
            docs += 1
            per_type[doc_type(block)] += 1

            lines = body.splitlines()
            nofence, nf = strip_fences(lines)
            fenced_lines += nf
            masked = [mask_code(ln) for ln in nofence]

            joined = "\n".join(masked)
            version_cites += len(VERSION_CITE.findall(joined))
            version_cites_loose += len(VERSION_CITE_LOOSE.findall(joined))
            # (c) UNDECLARED reference forms: id-shaped tokens that match NO declared kind and
            # are not top-level artifact ids. If this is large, the 73k denominator is
            # incomplete and every share computed from it is wrong.
            for m in GENERIC_ID.finditer(joined):
                tok = m.group(0)
                if TOPLEVEL.fullmatch(tok):
                    continue
                if any(r.fullmatch(tok) for r in KIND_RE.values()):
                    continue
                undeclared[re.sub(r'\d+', 'N', tok)] += 1
                undeclared_total[0] += 1
            for kind in KINDS:
                defs = definitions(kind, lines)
                rx = KIND_RE[kind]
                for i, (orig, mask) in enumerate(zip(nofence, masked)):
                    # RAW: every candidate in the UNMASKED line, so the rule's cost is visible
                    for m in rx.finditer(orig):
                        raw[kind] += 1
                    # what the DECLARED (unanchored) pattern would have matched, vs anchored
                    over_match[kind] += (len(list(KIND_RE_RAW[kind].finditer(mask)))
                                         - len(list(rx.finditer(mask))))
                    kept = list(rx.finditer(mask))
                    n_kept = len(kept)
                    n_raw = len(list(rx.finditer(orig)))
                    if n_raw > n_kept:
                        in_code[kind] += n_raw - n_kept
                        if len(examples["code:" + kind]) < 3:
                            examples["code:" + kind].append(f"{rel}:{i+1} {orig.strip()[:90]}")
                    for m in kept:
                        tok = m.group(0).strip()
                        if tok in defs and re.match(r'^(#{1,6}|\||\s*[-*]?\s*\*\*)', mask):
                            is_definition[kind] += 1
                            continue
                        if tok in defs:
                            resolved_local[kind] += 1
                            continue
                        # Resolve at the kind's DECLARED scope before concluding anything.
                        if tok in defidx[(kind, scope_key(kind, rel))]:
                            resolved_scope[kind] += 1
                            continue
                        # Still unresolved at its own scope. Now the rule that decides the
                        # verdict: is the OWNER stated on this line?
                        if OWNER_RE.search(mask):
                            # owner named, id absent at that scope -> a candidate DANGLING ref
                            dangling[kind] += 1
                            if len(examples["dangling:" + kind]) < 3:
                                examples["dangling:" + kind].append(f"{rel}:{i+1} {orig.strip()[:90]}")
                        elif tok in defidx[(kind, "__any__")]:
                            # the id exists SOMEWHERE but this citation never says whose it is
                            unresolvable[kind] += 1
                            if len(examples["unres:" + kind]) < 3:
                                examples["unres:" + kind].append(f"{rel}:{i+1} {orig.strip()[:90]}")
                        else:
                            owner_stated[kind] += 1  # reused column: "no definition anywhere"
                            if len(examples["nodef:" + kind]) < 3:
                                examples["nodef:" + kind].append(f"{rel}:{i+1} {orig.strip()[:90]}")


    print(f"markdown documents with frontmatter : {docs}")
    print(f"lines inside code fences (blanked)  : {fenced_lines}")
    print(f"version-cite (DECLARED per|see|against pattern) : {version_cites}")
    print(f"version-cite (LOOSE `NAME vX.Y` form)           : {version_cites_loose}")
    print(f"over-match by the UNANCHORED declared patterns  : {sum(over_match.values())}"
          f"  {dict(over_match.most_common(4))}")
    print(f"UNDECLARED id-shaped forms in prose             : {undeclared_total[0]}")
    DOCNAME = re.compile(r'^[A-Z0-9-]*-?INDEX(\.md)?$|^(STATE|PRD|ADR|VP|BC|STORY|ARCH|L2)-?(INDEX|MAP)?$')
    PLACEHOLDER = re.compile(r'(TBD|NNN|N\.NN|S\.SS|XXX|YYY)')
    buckets = collections.Counter()
    detail = collections.defaultdict(collections.Counter)
    for tok, n in undeclared.items():
        if DOCNAME.match(tok):
            b = "document/index NAME (an artifact, not a sub-artifact ref)"
        elif PLACEHOLDER.search(tok):
            b = "template PLACEHOLDER (not a reference at all)"
        else:
            b = "a GENUINE reference form the registry does not declare"
        buckets[b] += n
        detail[b][tok] += n
    print("  the census, classified — because id-shaped tokens are NOT all references:")
    for b, n in buckets.most_common():
        print(f"      {n:>6}  {b}")
        top = detail[b].most_common(20)
        for tok, c in top[:8]:
            print(f"             {c:>5}  {tok}")
        covered = sum(c for _, c in top)
        print(f"             ({len(detail[b])} distinct forms; the top 20 cover "
              f"{covered} of {n} = {100*covered/max(n,1):.0f}%)")
        if b.startswith("a GENUINE"):
            # The TAIL decides whether the row-vs-prose recommendation is safe, so it is
            # SAMPLED rather than assumed away. Deterministic stride sample over the ranked
            # tail (no RNG: the sample must be reproducible).
            tail = detail[b].most_common()[20:]
            print(f"             TAIL SAMPLE (every 25th of {len(tail)} tail forms):")
            for tok, c in tail[::25][:26]:
                print(f"                {c:>4}  {tok}")
    print()
    hdr = (f"{'kind':<10} {'raw':>7} {'in-code':>8} {'defs':>7} {'local':>7} {'scope':>7} "
           f"{'UNRESOLV':>9} {'dangling':>9} {'no-def':>7}")
    print(hdr)
    print("-" * len(hdr))
    tot = collections.Counter()
    for k in KINDS:
        print(f"{k:<10} {raw[k]:>7} {in_code[k]:>8} {is_definition[k]:>7} "
              f"{resolved_local[k]:>7} {resolved_scope[k]:>7} {unresolvable[k]:>9} "
              f"{dangling[k]:>9} {owner_stated[k]:>7}")
        for n, c in (("raw", raw[k]), ("in_code", in_code[k]), ("defs", is_definition[k]),
                     ("local", resolved_local[k]), ("scope", resolved_scope[k]),
                     ("unres", unresolvable[k]), ("dangling", dangling[k]),
                     ("nodef", owner_stated[k])):
            tot[n] += c
    print("-" * len(hdr))
    print(f"{'TOTAL':<10} {tot['raw']:>7} {tot['in_code']:>8} {tot['defs']:>7} "
          f"{tot['local']:>7} {tot['scope']:>7} {tot['unres']:>9} {tot['dangling']:>9} "
          f"{tot['nodef']:>7}")
    print()
    print("WHAT EACH RULE COSTS, as a share of raw candidates:")
    r = tot["raw"] or 1
    print(f"  exclude-code-spans eliminates       {tot['in_code']:>7}  ({100*tot['in_code']/r:.1f}%)")
    print(f"  defining occurrences (not refs)     {tot['defs']:>7}  ({100*tot['defs']/r:.1f}%)")
    print(f"  resolve locally in their own file   {tot['local']:>7}  ({100*tot['local']/r:.1f}%)")
    print(f"  resolve at their DECLARED scope     {tot['scope']:>7}  ({100*tot['scope']/r:.1f}%)")
    print(f"  UNRESOLVABLE (owner unstated)       {tot['unres']:>7}  ({100*tot['unres']/r:.1f}%)")
    print(f"  DANGLING (owner named, id absent)   {tot['dangling']:>7}  ({100*tot['dangling']/r:.1f}%)")
    print(f"  no definition anywhere in corpus    {tot['nodef']:>7}  ({100*tot['nodef']/r:.1f}%)")
    print()
    print("⚠ the UNRESOLVABLE column is the one that decides the design: reporting it as")
    print("  `dangling` is how a prose extractor produces a large, confident, WRONG finding set.")
    print()
    for k, v in sorted(examples.items()):
        print(f"  {k}:")
        for e in v:
            print(f"      {e}")


main()
