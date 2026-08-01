#!/usr/bin/env python3
"""Validate the artifact type registry AGAINST the three live corpora.

A registry nobody ran against real data is a wish list. This is the gate that makes it a
schema. Two halves:

  PART 1  COMPLETENESS OF THE REGISTRY ITSELF
          Every document_type value observed in any corpus must be dispositioned exactly
          once: canonical | alias | gap | retired. A value with no disposition is a hole
          in the standard, reported as such. Also checks the registry's internal
          consistency: alias targets exist, enum references exist, no type is both
          canonical and aliased-away, shape/authority are legal values.

  PART 2  CONFORMANCE OF THE CORPORA TO THE REGISTRY
          For every file, resolve its type through the alias map, then check the declared
          required fields, enum membership and section schema. Emits findings in the same
          shape `fa validate` uses so they can be baselined and ratcheted.

Read-only. Touches nothing outside this directory.

Exit codes: 0 registry is internally consistent and complete · 1 registry has holes or
defects · 2 the script itself failed. Never collapse 1 and 2.
"""
import os, re, sys, json, collections

try:
    import yaml
except ImportError:
    print("FATAL need pyyaml: python3 -m pip install pyyaml", file=sys.stderr); sys.exit(2)

HERE = os.path.dirname(os.path.abspath(__file__))
CORPORA = ("vsdd-factory", "prism", "rivetry")
DT = re.compile(r'^document_type:\s*["\']?([^"\'\s#]+)')
KEY = re.compile(r'^([A-Za-z_][A-Za-z0-9_.-]*):\s*(.*)$')
H = re.compile(r'^(#{2,6})\s+(.*)')
FENCE = re.compile(r'^\s*(```|~~~)')


def load():
    RD = os.path.join(os.path.dirname(HERE), "fa", "registry")   # ONE canonical location:
    # the YAML is embedded into the fa binary from there, so there is no second copy to drift.
    reg = yaml.safe_load(open(os.path.join(RD, "artifact-type-registry.yaml")))
    enums = yaml.safe_load(open(os.path.join(RD, "enums.yaml")))
    al = yaml.safe_load(open(os.path.join(RD, "aliases.yaml")))
    return reg, enums, al


def fm_body(txt):
    L = txt.splitlines(keepends=True)
    if not L or L[0].strip() != "---":
        return None, txt
    for i in range(1, len(L)):
        if L[i].strip() in ("---", "..."):
            return L[1:i], "".join(L[i + 1:])
    return None, txt


def sections(body):
    """Fence-aware ordinal section partition. Returns [(depth, heading, text)].
    Verified byte-exact: ''.join(text for _,_,text in ...) == body."""
    out, cur, head, depth, infence = [], [], None, 0, False
    for line in body.splitlines(keepends=True):
        if FENCE.match(line):
            infence = not infence
            cur.append(line); continue
        m = H.match(line) if not infence else None
        if m:
            if cur or head is not None:
                out.append((depth, head, "".join(cur)))
            head, depth, cur = m.group(2).strip(), len(m.group(1)), [line]
        else:
            cur.append(line)
    if cur or head is not None:
        out.append((depth, head, "".join(cur)))
    return out


# ── PART 1 ────────────────────────────────────────────────────────────────────
def part1(reg, enums, al, observed):
    findings = []
    canon = set(reg.get("types") or {})
    gaps = set(reg.get("gap_types") or {})
    retired_t = set(reg.get("retired_types") or {})
    aliases = al.get("aliases") or {}
    retired_a = set(al.get("retired") or {})
    unresolved = set(al.get("unresolved") or {})

    print("=" * 78)
    print("PART 1  REGISTRY COMPLETENESS AND INTERNAL CONSISTENCY")
    print("=" * 78)
    print(f"canonical types  : {len(canon)}")
    print(f"gap types        : {len(gaps)}  (real concepts with no template yet)")
    print(f"retired types    : {len(retired_t)}")
    print(f"alias entries    : {len(aliases)}")
    print(f"observed values  : {len(observed)}  (distinct document_type across 3 corpora)")

    # 1a every observed value dispositioned
    holes = []
    for v in sorted(observed):
        n = sum(observed[v].values())
        if v in canon or v in gaps or v in aliases or v in retired_a or v in retired_t or v in unresolved:
            continue
        holes.append((v, n))
    if holes:
        for v, n in sorted(holes, key=lambda x: -x[1]):
            findings.append(("registry-hole", f"observed value '{v}' ({n} files) has NO disposition"))
    print(f"\n[1a] observed values with no disposition : {len(holes)}"
          f"   {'OK' if not holes else 'HOLES -> see findings'}")

    # 1b alias targets must resolve
    bad = []
    for a, spec in aliases.items():
        tgt = (spec or {}).get("canonical")
        if tgt is None:
            continue          # explicit retired_with_field disposition
        if tgt not in canon and tgt not in gaps:
            bad.append((a, tgt))
    for a, tgt in bad:
        findings.append(("alias-target-missing", f"alias '{a}' -> '{tgt}' which is not a declared type"))
    print(f"[1b] alias targets that do not resolve   : {len(bad)}   {'OK' if not bad else 'BROKEN'}")

    # 1c a value must not be both canonical and aliased away from itself
    selfalias = [a for a, s in aliases.items()
                 if (s or {}).get("canonical") and s["canonical"] != a and a in canon]
    for a in selfalias:
        findings.append(("alias-shadows-canonical",
                         f"'{a}' is a declared canonical type AND aliased to '{aliases[a]['canonical']}'"))
    print(f"[1c] aliases shadowing a canonical type  : {len(selfalias)}   {'OK' if not selfalias else 'CONFLICT'}")

    # 1d enum references must exist
    ename = set(enums["enums"])
    miss = []
    for t, spec in list((reg.get("types") or {}).items()) + list((reg.get("gap_types") or {}).items()):
        for field, en in ((spec or {}).get("enums") or {}).items():
            if en and en not in ename:
                miss.append((t, field, en))
    for t, f, e in miss:
        findings.append(("enum-missing", f"type '{t}' field '{f}' references undeclared enum '{e}'"))
    print(f"[1d] undeclared enum references          : {len(miss)}   {'OK' if not miss else 'BROKEN'}")

    # 1e shape / authority / policy / severity must be legal
    legal_shape = set(enums["enums"]["shape"]["values"])
    legal_auth = set(enums["enums"]["authority"]["values"])
    legal_sev = set(enums["enums"]["gate_severity"]["values"])
    legal_enf = set(enums["enums"]["enforcement_level"]["values"])
    legal_pol = set(reg["section_policies"])
    illegal = []
    for t, spec in list((reg.get("types") or {}).items()) + list((reg.get("gap_types") or {}).items()):
        s = spec or {}
        for fld, legal in (("shape", legal_shape), ("authority", legal_auth),
                           ("gate_severity", legal_sev), ("enforcement_level", legal_enf),
                           ("section_policy", legal_pol)):
            v = s.get(fld)
            if v is not None and v not in legal:
                illegal.append((t, fld, v))
    for t, f, v in illegal:
        findings.append(("illegal-value", f"type '{t}' has {f}='{v}', not a declared value"))
    print(f"[1e] illegal shape/authority/policy vals : {len(illegal)}   {'OK' if not illegal else 'BROKEN'}")

    # 1f link_types targets must be types, a declared universe, or `any_artifact`
    universes = {"capability", "domain_invariant", "nfr", "fr", "subsystem", "module", "any_artifact"}
    linkbad = []
    for ln, spec in reg["link_types"].items():
        if ln == "rules":
            continue
        for tgt in (spec or {}).get("targets", []):
            if tgt not in canon and tgt not in gaps and tgt not in universes:
                linkbad.append((ln, tgt))
    for ln, tgt in linkbad:
        findings.append(("link-target-missing", f"link_type '{ln}' targets '{tgt}' which is neither a type nor a declared universe"))
    print(f"[1f] link targets that do not resolve    : {len(linkbad)}   {'OK' if not linkbad else 'BROKEN'}")

    # 1g every type must declare a key
    nokey = [t for t, s in (reg.get("types") or {}).items() if not (s or {}).get("key")]
    for t in nokey:
        findings.append(("no-key", f"type '{t}' declares no key — identity is undefined"))
    print(f"[1g] types with no declared key          : {len(nokey)}   {'OK' if not nokey else 'BROKEN'}")

    # 1h the two-namespace defect, quantified — THREE kinds, not one boolean.
    # Collapsing them into one flag overstated the disagreement as 17; only
    # name_disagreement is a namespace defect. See namespace_reconciliation.
    kinds = collections.defaultdict(list)
    allrows = {**(reg.get("types") or {}), **(reg.get("gap_types") or {})}
    for t, sp in allrows.items():
        st = (sp or {}).get("namespace_status")
        if st:
            kinds[st].append(t)
    print(f"\n[1h] NAMESPACE RECONCILIATION (story 1)")
    for k, label in (("name_disagreement", "two names for one concept  <- THE defect"),
                     ("path_missing", "template declares it, path registry does not"),
                     ("template_missing", "path registry declares it, no template does -> story 2")):
        print(f"       {k:18s} {len(kinds[k]):3d}   {label}")
        for t in sorted(kinds[k]):
            print(f"           - {t}")
    nr = reg.get("namespace_reconciliation") or {}
    declared = {d["document_type"] for d in (nr.get("name_disagreements") or [])}
    flagged = set(kinds["name_disagreement"])
    if declared != flagged:
        findings.append(("namespace-undeclared",
                         f"name_disagreement flags {sorted(flagged)} but namespace_reconciliation "
                         f"declares {sorted(declared)} — every disagreement needs a resolution"))
    for d in (nr.get("name_disagreements") or []):
        if d.get("winner") != d.get("document_type"):
            findings.append(("namespace-resolution",
                             f"{d['document_type']}: resolution_rule says the document_type name wins, "
                             f"but winner is {d.get('winner')!r}"))
    # every path_registry_only entry must have a disposition
    for e in (nr.get("path_registry_only") or []):
        if not e.get("disposition"):
            findings.append(("namespace-undisposed",
                             f"path-registry-only artifact_type {e.get('artifact_type')!r} has no disposition"))
    # exit criterion, checked rather than aspirational
    if kinds["name_disagreement"]:
        print(f"       EXIT CRITERION NOT MET: {len(kinds['name_disagreement'])} name disagreement(s) "
              f"remain — {nr.get('exit_criterion','')}")
    else:
        print(f"       EXIT CRITERION MET: zero name disagreements")

    # 1i mass accounting: is every observed FILE covered?
    tot = sum(sum(c.values()) for c in observed.values())
    cov = collections.Counter()
    for v, c in observed.items():
        n = sum(c.values())
        if v in canon:      cov["canonical"] += n
        elif v in aliases:  cov["aliased"] += n
        elif v in gaps:     cov["gap"] += n
        elif v in retired_a or v in retired_t: cov["retired"] += n
        elif v in unresolved: cov["unresolved"] += n
        else:               cov["UNDISPOSITIONED"] += n
    print(f"\n[1i] FILE MASS ACCOUNTING  (total typed files: {tot})")
    for k in ("canonical", "aliased", "gap", "retired", "unresolved", "UNDISPOSITIONED"):
        if cov[k]:
            print(f"       {k:16s} {cov[k]:5d}  {cov[k]*100.0/tot:5.1f}%")
    return findings


# ── PART 2 ────────────────────────────────────────────────────────────────────
def part2(reg, enums, al):
    aliases = al.get("aliases") or {}
    retired_a = set(al.get("retired") or {})
    types = dict(reg.get("types") or {})
    types.update(reg.get("gap_types") or {})
    spine_req = list(reg["defaults"]["required"])
    shape_over = reg["defaults"].get("shape_overrides") or {}
    forbidden = set(reg["defaults"]["forbidden"])
    retired_fields = {"input-hash"}

    print("\n" + "=" * 78)
    print("PART 2  CORPUS CONFORMANCE — the findings a gate would emit on day one")
    print("=" * 78)

    findings = collections.Counter()
    migration_items = collections.Counter()
    per_corpus = collections.defaultdict(collections.Counter)
    sect_mismatch = 0
    checked = 0
    examples = collections.defaultdict(list)

    for corp in CORPORA:
        root = os.path.expanduser(f"~/Dev/{corp}/.factory")
        if not os.path.isdir(root):
            print(f"  SKIP {corp} (not present)"); continue
        for dp, dn, fs in os.walk(root):
            dn[:] = [d for d in dn if d != ".git"]
            for f in fs:
                if not f.endswith((".md", ".yaml", ".yml")):
                    continue
                p = os.path.join(dp, f)
                try:
                    txt = open(p, encoding="utf-8", errors="replace").read()
                except OSError:
                    continue
                block, body = fm_body(txt)
                if block is None:
                    continue
                # Parse keys AND block-style list continuations. Without the
                # continuation handling, `behavioral_contracts:\n  - BC-x` reads as an
                # empty value and the field is wrongly reported missing — which is exactly
                # what the Go/Python parity diff caught on 7 link fields.
                fields, order = {}, []
                for line in block:
                    m = KEY.match(line)
                    if m:
                        # strip trailing YAML comments: the corpus writes
                        # `verification_properties: []  # [process-gap] ...`, and without
                        # this the value reads as non-empty. Found by a Go/Python parity
                        # diff that was off by exactly ONE file.
                        v = re.sub(r'\s+#.*$', '', m.group(2)).strip().strip('"\'')
                        fields.setdefault(m.group(1), v)
                        order.append(m.group(1))
                    elif order and re.match(r'^\s+-\s*\S', line):
                        k = order[-1]
                        if fields.get(k, "") == "":
                            fields[k] = "[block-list]"
                dt = fields.get("document_type")
                if not dt:
                    continue
                rel = os.path.relpath(p, root)

                # resolve through the alias map
                resolved, applied = dt, {}
                if dt in retired_a:
                    findings["type-retired"] += 1; per_corpus[corp]["type-retired"] += 1
                    examples["type-retired"].append(f"{corp}:{rel} ({dt})")
                    continue
                if dt in aliases and (aliases[dt] or {}).get("canonical"):
                    resolved = aliases[dt]["canonical"]
                    applied = (aliases[dt] or {}).get("set") or {}
                    findings["type-alias-applied"] += 1; per_corpus[corp]["type-alias-applied"] += 1
                if resolved not in types:
                    findings["type-unknown"] += 1; per_corpus[corp]["type-unknown"] += 1
                    examples["type-unknown"].append(f"{corp}:{rel} ({dt})")
                    continue

                spec = types[resolved] or {}
                checked += 1

                # required fields = spine (or the shape's override) + delta
                shape = spec.get("shape")
                base = (shape_over.get(shape) or {}).get("required", spine_req)
                req = list(base) + list(spec.get("required+") or [])
                # a key whose only source today is the filename is a ONE-TIME MIGRATION
                # item, not a per-file authoring defect (see defaults.key_source_note)
                if spec.get("key_source") == "filename":
                    req = [x for x in req if x not in set(spec.get("key") or [])]
                    migration_items[resolved] += 1
                for r in req:
                    if r in ("version", "timestamp"):
                        continue                       # derived on write, not authored
                    if r in applied:
                        continue                       # the alias supplies it
                    # three states: absent / present-but-empty / present
                    if r not in fields:
                        findings[f"missing-required:{r}"] += 1
                        per_corpus[corp]["missing-required"] += 1
                        if len(examples[f"missing-required:{r}"]) < 2:
                            examples[f"missing-required:{r}"].append(f"{corp}:{rel} ({resolved})")
                    elif fields[r] in ("", "[]", "{}", "null", "~"):
                        findings[f"empty-required:{r}"] += 1
                        per_corpus[corp]["empty-required"] += 1

                # forbidden / retired fields
                for bad in forbidden | retired_fields:
                    if bad in fields:
                        findings[f"retired-field:{bad}"] += 1
                        per_corpus[corp]["retired-field"] += 1

                # enum membership
                for field, ename in (spec.get("enums") or {}).items():
                    if field not in fields or not ename:
                        continue
                    e = enums["enums"].get(ename) or {}
                    vals = set(e.get("values") or {})
                    migf = set(e.get("migrated_from") or {})
                    v = fields[field]
                    if e.get("closed") is False or e.get("open_extension"):
                        continue
                    if v in vals:
                        continue
                    if v in migf:
                        findings[f"enum-migratable:{field}"] += 1
                        per_corpus[corp]["enum-migratable"] += 1
                    else:
                        findings[f"enum-illegal:{field}"] += 1
                        per_corpus[corp]["enum-illegal"] += 1
                        if len(examples[f"enum-illegal:{field}"]) < 3:
                            examples[f"enum-illegal:{field}"].append(f"{corp}:{rel} {field}={v!r}")

                # section schema
                declared = spec.get("sections") or []
                policy = spec.get("section_policy", "free")
                if declared and policy in ("required_ordered", "required_unordered", "expected"):
                    have = {h for _, h, _ in sections(body) if h}
                    for s in declared:
                        if s not in have:
                            findings[f"missing-section:{resolved}"] += 1
                            per_corpus[corp]["missing-section"] += 1
                            break

                # D-A invariant: the section partition must be byte-exact
                if f.endswith(".md"):
                    if "".join(t for _, _, t in sections(body)) != body:
                        sect_mismatch += 1
                        findings["section-partition-lossy"] += 1

    print(f"\nfiles type-resolved and checked: {checked}")
    print(f"\nD-A INVARIANT  concat(sections) == body : "
          f"{'HOLDS on every file' if sect_mismatch == 0 else f'VIOLATED on {sect_mismatch} files'}")

    if migration_items:
        print("\n--- ONE-TIME MIGRATION items (key lives only in the filename today) ---")
        for k, n in migration_items.most_common():
            print(f"  {n:6d}  {k}: materialise the key into the record on import")
    print("\n--- findings by class (this is the day-one baseline, not a failure) ---")
    for k, n in findings.most_common(28):
        print(f"  {n:6d}  {k}")
        for ex in examples.get(k, [])[:2]:
            print(f"          e.g. {ex}")
    print(f"\ntotal findings: {sum(findings.values())}")
    print("\n--- per corpus ---")
    for c in CORPORA:
        if per_corpus[c]:
            tot = sum(per_corpus[c].values())
            top = ", ".join(f"{k} {v}" for k, v in per_corpus[c].most_common(5))
            print(f"  {c:14s} {tot:6d}   {top}")
    return findings


def main():
    reg, enums, al = load()
    obs_path = os.path.join(HERE, "types_measured.json")
    if not os.path.exists(obs_path):
        print("FATAL run measure_types.py first", file=sys.stderr); sys.exit(2)
    meas = json.load(open(obs_path))
    observed = collections.defaultdict(dict)
    for corp, d in meas["corpora"].items():
        for v, n in list(d["canonical"].items()) + list(d["noncanonical"].items()):
            observed[v][corp] = n

    f1 = part1(reg, enums, al, observed)
    f2 = part2(reg, enums, al)

    print("\n" + "=" * 78)
    if f1:
        print(f"REGISTRY DEFECTS: {len(f1)}")
        for cls, msg in f1[:40]:
            print(f"  [{cls}] {msg}")
        if len(f1) > 40:
            print(f"  ... and {len(f1)-40} more")
        print("=" * 78)
        sys.exit(1)
    print("REGISTRY OK — complete over every observed value, internally consistent.")
    print(f"Corpus conformance findings (the ratchet's starting baseline): {sum(f2.values())}")
    print("=" * 78)
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:
        import traceback; traceback.print_exc()
        print(f"FATAL {e}", file=sys.stderr); sys.exit(2)
