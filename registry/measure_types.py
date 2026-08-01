#!/usr/bin/env python3
"""Measure canonical (template-declared) vs ACTUAL document_type usage across corpora.

Extraction rules, stated because every count depends on them:
  - canonical set: `^document_type:` lines in plugins/vsdd-factory/templates/**, value
    stripped of quotes/whitespace. One value per template file (3 files share
    architecture-section, 3 share adversary-prompt-template).
  - actual usage: `^document_type:` in the FIRST frontmatter block only (between the
    first `---` and the next `---`) of every *.md/*.yaml under .factory/. Files with no
    frontmatter are counted separately as `<none>`, never as a type.
  - a value is CANONICAL iff it is byte-identical to a template-declared value.
"""
import os, re, sys, json, collections

TPL = os.path.expanduser("~/Dev/vsdd-factory/plugins/vsdd-factory/templates")
CORPORA = {p: os.path.expanduser(f"~/Dev/{p}/.factory") for p in ("vsdd-factory","prism","rivetry")}
DT = re.compile(r'^document_type:\s*["\']?([^"\'\s#]+)')

def canonical():
    out = collections.defaultdict(list)
    for root,_,files in os.walk(TPL):
        for f in files:
            p = os.path.join(root,f)
            try: txt = open(p, encoding="utf-8", errors="replace").read()
            except OSError: continue
            for line in txt.splitlines():
                m = DT.match(line)
                if m:
                    out[m.group(1)].append(os.path.relpath(p, TPL)); break
    return dict(out)

def frontmatter(txt):
    """Return the first frontmatter block, or None. Requires --- as the FIRST line."""
    lines = txt.splitlines()
    if not lines or lines[0].strip() != "---": return None
    for i in range(1, len(lines)):
        if lines[i].strip() in ("---","..."): return lines[1:i]
    return None

def scan(root):
    hits = collections.defaultdict(list)   # type -> [relpath]
    nofm, nodt, total = [], [], 0
    for dirpath,dirs,files in os.walk(root):
        dirs[:] = [d for d in dirs if d != ".git"]
        for f in files:
            if not f.endswith((".md",".yaml",".yml")): continue
            p = os.path.join(dirpath,f); total += 1
            try: txt = open(p, encoding="utf-8", errors="replace").read()
            except OSError: continue
            fm = frontmatter(txt)
            rel = os.path.relpath(p, root)
            if fm is None: nofm.append(rel); continue
            for line in fm:
                m = DT.match(line)
                if m: hits[m.group(1)].append(rel); break
            else: nodt.append(rel)
    return hits, nofm, nodt, total

def norm(v):
    """Aggressive normalisation used ONLY to PROPOSE alias links for human review."""
    s = v.lower().replace("_","-")
    s = re.sub(r'^(vsdd-plugin-|pr-level-|per-story-|local-|cycle-|wave-)','',s)
    s = re.sub(r'-(report|record|doc|document|file|note|notes|summary|manifest)$','',s)
    s = s.replace("adversary","adversarial")
    s = re.sub(r'-(pass|passes)$','',s)
    s = re.sub(r'(matrices)$','matrix',s)
    s = re.sub(r'e?s$','',s) if s.endswith(("ies",)) else s
    return s

if __name__ == "__main__":
    can = canonical()
    print(f"CANONICAL: {len(can)} distinct document_type values from {len({f for v in can.values() for f in v})} template files")
    # dedup clusters INSIDE the canonical set
    byn = collections.defaultdict(list)
    for v in can: byn[norm(v)].append(v)
    print("\n--- canonical-set internal collisions (the standard's own drift) ---")
    for n,vs in sorted(byn.items()):
        if len(vs) > 1: print(f"  {n:34s} <- {sorted(vs)}")

    data = {"canonical": {k: sorted(v) for k,v in can.items()}, "corpora": {}}
    for name, root in CORPORA.items():
        if not os.path.isdir(root): print(f"MISSING {root}"); continue
        hits, nofm, nodt, total = scan(root)
        used = sum(len(v) for v in hits.values())
        ok  = {k:v for k,v in hits.items() if k in can}
        bad = {k:v for k,v in hits.items() if k not in can}
        okn, badn = sum(len(v) for v in ok.values()), sum(len(v) for v in bad.values())
        print(f"\n===== {name}: {total} md/yaml files")
        print(f"  with document_type   : {used} ({used*100//max(total,1)}%)   distinct={len(hits)}")
        print(f"  no frontmatter       : {len(nofm)}")
        print(f"  frontmatter, no dtype: {len(nodt)}")
        print(f"  CANONICAL values     : {len(ok)} distinct / {okn} files ({okn*100//max(used,1)}% of typed files)")
        print(f"  NON-canonical values : {len(bad)} distinct / {badn} files ({badn*100//max(used,1)}%)")
        data["corpora"][name] = {
            "total_files": total, "typed": used, "no_frontmatter": len(nofm),
            "fm_no_dtype": len(nodt),
            "canonical": {k: len(v) for k,v in sorted(ok.items())},
            "noncanonical": {k: len(v) for k,v in sorted(bad.items(), key=lambda kv:-len(kv[1]))},
            "noncanonical_examples": {k: sorted(v)[:3] for k,v in bad.items()},
        }
    json.dump(data, open(os.path.join(os.path.dirname(os.path.abspath(__file__)),"types_measured.json"),"w"), indent=1)
    print("\nwrote registry/types_measured.json")
