#!/usr/bin/env python3
"""probe_field_mass.py — measure the REAL field mass of the field-per-row (EAV) model.

The L1-L2 design stores every declared field of every artifact as one `artifact_field`
row, and asserts "field mass is order 10^5 rows per corpus". That is the denominator of
the pivot cost and it has never been measured. This measures it, from the actual corpora.

What it counts, per corpus:
  - files, and files carrying frontmatter at all
  - SCALAR keys              -> 1 artifact_field row each
  - LIST keys and their item counts -> one row PER ITEM (the model's `ord` column)
  - the resulting artifact_field row total, and rows-per-artifact distribution
  - value lengths, against the model's VARCHAR(2000) v_text ceiling

Rules this obeys, all earned in this repo:
  - print PER-FORM counts; report malformed; never drop silently
  - a value too long for the declared column is a FINDING, not a truncation
  - READ-ONLY over every corpus
"""
import os
import sys
import json
from collections import Counter

CORPORA = {
    "vsdd-factory": os.path.expanduser("~/Dev/vsdd-factory/.factory"),
    "prism": os.path.expanduser("~/Dev/prism/.factory"),
    "rivetry": os.path.expanduser("~/Dev/rivetry/.factory"),
}

# The model's declared ceiling for a scalar text value.
V_TEXT_MAX = 2000


def parse_frontmatter(text):
    """Return (keys, malformed_reason). Deliberately tolerant at the INGEST boundary
    (V-J), but it reports every form it could not read rather than skipping it."""
    if not text.startswith("---"):
        return None, "no-frontmatter"
    end = text.find("\n---", 3)
    if end < 0:
        return None, "unterminated-frontmatter"
    block = text[3:end]

    keys = {}           # key -> list of scalar values (len 1 for a scalar)
    cur_list_key = None
    for raw in block.split("\n"):
        line = raw.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        stripped = line.lstrip()
        indent = len(line) - len(stripped)

        # a YAML block-sequence item under the previous key
        if stripped.startswith("- "):
            if cur_list_key is not None:
                keys.setdefault(cur_list_key, []).append(stripped[2:].strip())
            continue

        if ":" not in stripped:
            continue
        # nested mapping keys are counted as their own fields (the model is flat)
        k, _, v = stripped.partition(":")
        k = k.strip()
        v = v.strip()
        if not k:
            continue
        if indent > 0:
            # a nested key becomes a dotted field name in a flat model
            k = "*nested*." + k
        if v == "":
            cur_list_key = k
            keys.setdefault(k, [])
            continue
        cur_list_key = None
        # an inline flow sequence [a, b, c] is a list
        if v.startswith("[") and v.endswith("]"):
            inner = v[1:-1].strip()
            items = [x.strip() for x in inner.split(",") if x.strip()] if inner else []
            keys[k] = items
        else:
            keys[k] = [v]
    return keys, None


def walk(root):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d != ".git"]
        for fn in filenames:
            if fn.endswith((".md", ".markdown")):
                yield os.path.join(dirpath, fn)


def main():
    grand = Counter()
    per_corpus = {}
    rows_per_artifact_all = []
    overlong = []

    for name, root in CORPORA.items():
        if not os.path.isdir(root):
            print(f"SKIP {name}: {root} not present", file=sys.stderr)
            continue
        c = Counter()
        rows_per_artifact = []
        key_freq = Counter()
        list_key_freq = Counter()
        malformed = Counter()

        for path in walk(root):
            c["files"] += 1
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as fh:
                    text = fh.read()
            except OSError as e:
                malformed[f"unreadable:{e.errno}"] += 1
                continue

            keys, bad = parse_frontmatter(text)
            if keys is None:
                malformed[bad] += 1
                c["files_no_frontmatter"] += 1
                # a blob-with-path artifact: 0 field rows, still 1 artifact row
                rows_per_artifact.append(0)
                continue

            c["files_with_frontmatter"] += 1
            n_rows = 0
            for k, vals in keys.items():
                key_freq[k] += 1
                if len(vals) == 0:
                    # a declared-but-empty key still occupies one row (empty value)
                    c["keys_empty"] += 1
                    n_rows += 1
                elif len(vals) == 1:
                    c["keys_scalar"] += 1
                    n_rows += 1
                else:
                    c["keys_list"] += 1
                    list_key_freq[k] += 1
                    c["list_items"] += len(vals)
                    n_rows += len(vals)
                for v in vals:
                    if len(v) > V_TEXT_MAX:
                        overlong.append((name, os.path.relpath(path, root), k, len(v)))
            c["artifact_field_rows"] += n_rows
            rows_per_artifact.append(n_rows)

        c["distinct_field_names"] = len(key_freq)
        per_corpus[name] = (c, rows_per_artifact, key_freq, list_key_freq, malformed)
        rows_per_artifact_all.extend(rows_per_artifact)
        for k, v in c.items():
            grand[k] += v

    # ---- report -------------------------------------------------------------
    print("=" * 78)
    print("FIELD MASS OF THE FIELD-PER-ROW (EAV) MODEL — measured, per corpus")
    print("=" * 78)
    hdr = f"{'corpus':<15}{'files':>8}{'w/ fm':>8}{'no fm':>7}{'scalar':>9}{'list':>7}{'items':>8}{'FIELD ROWS':>12}{'names':>7}"
    print(hdr)
    for name, (c, _rpa, _kf, _lkf, _mal) in per_corpus.items():
        print(f"{name:<15}{c['files']:>8}{c['files_with_frontmatter']:>8}"
              f"{c['files_no_frontmatter']:>7}{c['keys_scalar']:>9}{c['keys_list']:>7}"
              f"{c['list_items']:>8}{c['artifact_field_rows']:>12}{c['distinct_field_names']:>7}")
    print("-" * 78)
    print(f"{'TOTAL':<15}{grand['files']:>8}{grand['files_with_frontmatter']:>8}"
          f"{grand['files_no_frontmatter']:>7}{grand['keys_scalar']:>9}{grand['keys_list']:>7}"
          f"{grand['list_items']:>8}{grand['artifact_field_rows']:>12}")

    rows_per_artifact_all.sort()
    n = len(rows_per_artifact_all)
    if n:
        def pct(p):
            return rows_per_artifact_all[min(n - 1, int(n * p))]
        print()
        print("rows-per-artifact distribution (the pivot's fan-in):")
        print(f"  min {rows_per_artifact_all[0]} · p50 {pct(.50)} · p90 {pct(.90)} "
              f"· p99 {pct(.99)} · p99.9 {pct(.999)} · MAX {rows_per_artifact_all[-1]}")
        print(f"  mean {grand['artifact_field_rows']/n:.1f} field rows per artifact")

    print()
    print(f"artifact rows      : {grand['files']:,}")
    print(f"artifact_field rows: {grand['artifact_field_rows']:,}")
    print(f"design's claim     : 'order 10^5 rows per corpus'")
    largest = max((c['artifact_field_rows'] for c, *_ in per_corpus.values()), default=0)
    print(f"largest corpus     : {largest:,} field rows -> "
          f"order 10^{len(str(largest))-1}")

    print()
    if overlong:
        print(f"⚠ {len(overlong)} VALUE(S) EXCEED v_text VARCHAR({V_TEXT_MAX}) — "
              f"the model would REFUSE or truncate these:")
        for corpus, rel, k, ln in sorted(overlong, key=lambda x: -x[3])[:10]:
            print(f"    {ln:>7} chars  {corpus:<14} {k:<28} {rel}")
        if len(overlong) > 10:
            print(f"    … and {len(overlong)-10} more")
    else:
        print(f"✓ no frontmatter value exceeds v_text VARCHAR({V_TEXT_MAX})")

    print()
    print("malformed / unparseable forms (reported, never dropped):")
    for name, (_c, _rpa, _kf, _lkf, mal) in per_corpus.items():
        if mal:
            forms = ", ".join(f"{k} {v}" for k, v in mal.most_common())
            print(f"  {name:<15} {forms}")

    print()
    print("top LIST-valued field names (these are the rows-per-artifact multiplier):")
    combined = Counter()
    for _n, (_c, _rpa, _kf, lkf, _m) in per_corpus.items():
        combined.update(lkf)
    for k, v in combined.most_common(12):
        print(f"  {v:>6}  {k}")

    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "field_mass.json")
    with open(out, "w") as fh:
        json.dump({
            "per_corpus": {k: dict(v[0]) for k, v in per_corpus.items()},
            "grand": dict(grand),
            "rows_per_artifact_percentiles": {
                "p50": pct(.50) if n else None,
                "p90": pct(.90) if n else None,
                "p99": pct(.99) if n else None,
                "max": rows_per_artifact_all[-1] if n else None,
            },
            "overlong_values": len(overlong),
        }, fh, indent=2, sort_keys=True)
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
