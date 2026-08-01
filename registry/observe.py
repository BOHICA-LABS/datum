#!/usr/bin/env python3
"""Observe, per document_type, the ACTUAL frontmatter key usage + id shapes + paths
across vsdd-factory, prism and rivetry. Feeds the registry's required-vs-optional split.

Rules (stated because every number depends on them):
  - first frontmatter block only; `---` must be line 1.
  - a key is REQUIRED-candidate iff present in >=95% of that type's files in EVERY corpus
    that has >=3 files of the type. Below that it is optional. <3 files = no evidence.
  - id shape is the regex family of the file basename, not of any field.
"""
import os, re, json, collections

CORPORA = ("vsdd-factory","prism","rivetry")
DT = re.compile(r'^document_type:\s*["\']?([^"\'\s#]+)')
KEY = re.compile(r'^([A-Za-z_][A-Za-z0-9_.-]*):')
H = re.compile(r'^(#{2,6})\s+(.*)')
FENCE = re.compile(r'^\s*(```|~~~)')

def fm_and_body(txt):
    L = txt.splitlines(keepends=True)
    if not L or L[0].strip() != "---": return None, txt
    for i in range(1, len(L)):
        if L[i].strip() in ("---","..."): return L[1:i], "".join(L[i+1:])
    return None, txt

def headings(body):
    out=[]; inf=False
    for line in body.splitlines():
        if FENCE.match(line): inf = not inf; continue
        if inf: continue
        m=H.match(line)
        if m: out.append((len(m.group(1)), m.group(2).strip()))
    return out

def idshape(name):
    s = re.sub(r'\d+','N',name)
    return s

def main():
    per = collections.defaultdict(lambda: {
        "corpora": collections.Counter(), "keys": collections.Counter(),
        "n": 0, "dirs": collections.Counter(), "basename_shapes": collections.Counter(),
        "h2": collections.Counter(), "values": collections.defaultdict(collections.Counter),
        "per_corpus_n": collections.Counter(), "per_corpus_keys": collections.defaultdict(collections.Counter),
    })
    ENUMISH = ("status","level","phase","producer","verdict","convergence","severity",
               "gate_result","lifecycle_status","priority","shape","authority")
    for c in CORPORA:
        root = os.path.expanduser(f"~/Dev/{c}/.factory")
        if not os.path.isdir(root): continue
        for dp,dn,fs in os.walk(root):
            dn[:] = [d for d in dn if d != ".git"]
            for f in fs:
                if not f.endswith((".md",".yaml",".yml")): continue
                p = os.path.join(dp,f)
                try: txt = open(p,encoding="utf-8",errors="replace").read()
                except OSError: continue
                block, body = fm_and_body(txt)
                if block is None: continue
                dt = None; keys = []
                for line in block:
                    m = KEY.match(line)
                    if m: keys.append(m.group(1))
                    m2 = DT.match(line)
                    if m2 and dt is None: dt = m2.group(1)
                if not dt: continue
                d = per[dt]
                d["n"] += 1; d["corpora"][c] += 1; d["per_corpus_n"][c] += 1
                for k in set(keys):
                    d["keys"][k] += 1; d["per_corpus_keys"][c][k] += 1
                rel = os.path.relpath(p, root)
                d["dirs"][os.path.dirname(rel).split("/")[0] or "."] += 1
                d["basename_shapes"][idshape(f)] += 1
                for depth,h in headings(body):
                    if depth == 2: d["h2"][h] += 1
                for line in block:
                    for e in ENUMISH:
                        m3 = re.match(rf'^{e}:\s*(\S.*)$', line)
                        if m3:
                            v = m3.group(1).strip().strip('"\'')
                            if len(v) <= 48 and len(v.split()) <= 3:
                                d["values"][e][v] += 1
    out = {}
    for dt,d in per.items():
        req = []
        opt = []
        evidence_corpora = [c for c in CORPORA if d["per_corpus_n"][c] >= 3]
        for k,n in d["keys"].items():
            if evidence_corpora:
                allc = all(d["per_corpus_keys"][c][k] >= 0.95*d["per_corpus_n"][c] for c in evidence_corpora)
                (req if allc else opt).append(k)
            else:
                opt.append(k)
        out[dt] = {
            "n": d["n"], "by_corpus": dict(d["corpora"]),
            "required_observed": sorted(req), "optional_observed": sorted(opt),
            "top_dirs": dict(d["dirs"].most_common(4)),
            "basename_shapes": dict(d["basename_shapes"].most_common(4)),
            "top_h2": [h for h,_ in d["h2"].most_common(12)],
            "enums": {k: dict(v.most_common(14)) for k,v in d["values"].items() if v},
            "evidence_corpora": evidence_corpora,
        }
    json.dump(out, open("registry/types_observed.json","w"), indent=1, sort_keys=True)
    print(f"observed {len(out)} document_type values across {len(CORPORA)} corpora")
    print(f"types with >=3 files in >=1 corpus (usable field evidence): "
          f"{sum(1 for v in out.values() if v['evidence_corpora'])}")

if __name__ == "__main__": main()
