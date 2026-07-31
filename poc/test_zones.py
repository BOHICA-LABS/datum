#!/usr/bin/env python3
"""Zone UX: is the boundary real, and is it invisible to the user?

Two things must both hold, or the design fails:
  REAL      — a walled zone must actually be unreachable
  INVISIBLE — nobody ever types a zone name; `fa get HS-001` just works

  Z1  `fa init` creates every zone from one config file
  Z2  routing: id -> artifact type -> zone, with no zone named by the caller
  Z3  a role without access gets a CLEAN, actionable refusal (not a crash)
  Z4  a permitted role reads the same id transparently
  Z5  filesystem permissions genuinely bound access (chmod 000)
  Z6  HONEST LIMIT: an unrestricted shell bypasses fa -- same as today's design
  Z7  cross-zone work for a permitted role stays one command
  Z8  adding a new artifact type is a one-line config change
  Z9  error messages name the fix, not the internals

Run: .venv/bin/python -u poc/test_zones.py
"""
from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from fa_zones import NotVisible, Store, UnknownArtifact, ZoneError  # noqa: E402

ROOT = Path(__file__).parent / "zn" / ".factory-db"
RESULTS: list[tuple[str, bool, str]] = []


def check(name, ok, detail=""):
    RESULTS.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}")
    for ln in (detail or "").splitlines():
        print(f"        {ln}")


def setup():
    print("--- setup: fa init")
    if ROOT.parent.exists():
        shutil.rmtree(ROOT.parent)
    s = Store.open(ROOT, role="orchestrator")
    made = s.init()
    s.sql("open", "CREATE TABLE bc (bc_id VARCHAR(24) PRIMARY KEY, title TEXT NOT NULL)")
    s.sql("open", "INSERT INTO bc VALUES ('BC-1.01.001','a public contract')")
    s.sql("walled", "CREATE TABLE holdout_scenario (hs_id VARCHAR(16) PRIMARY KEY, "
                    "expectation TEXT NOT NULL)")
    s.sql("walled", "INSERT INTO holdout_scenario VALUES ('HS-001','SECRET-EXPECTATION')")
    for z in ("open", "walled"):
        d = ROOT / z
        subprocess.run(["dolt", "add", "-A"], cwd=d, capture_output=True)
        subprocess.run(["dolt", "commit", "-m", "seed"], cwd=d, capture_output=True)
    print(f"    zones created: {made}\n")
    return s


# ---------------------------------------------------------------- tests


def z1_init(s):
    cfg = (ROOT / "fa.yaml").exists()
    dbs = {z: (ROOT / z / ".dolt").exists() for z in ("open", "walled")}
    check("Z1 `fa init` creates every zone from one config file",
          cfg and all(dbs.values()),
          f"{ROOT.name}/fa.yaml exists = {cfg}\ninitialized: {dbs}\n"
          "=> one command, and the layout is discoverable: .factory-db/{fa.yaml,open,walled}")


def z2_routing_no_zone_names(s):
    """The caller passes an ID. fa figures out the rest."""
    cases = {}
    for aid in ("BC-1.01.001", "VP-007", "S-1.04", "HS-001", "ADR-019", "NFR-SEC-001"):
        cases[aid] = (s.artifact_type(aid), s.zone_for_type(s.artifact_type(aid)).name)
    ok = (cases["BC-1.01.001"] == ("bc", "open")
          and cases["HS-001"] == ("holdout_scenario", "walled")
          and cases["NFR-SEC-001"] == ("nfr", "open"))
    check("Z2 routing: id -> type -> zone, caller never names a zone",
          ok,
          "\n".join(f"  {a:14} -> type={t:18} zone={z}" for a, (t, z) in cases.items())
          + "\n=> `fa get HS-001` and `fa get BC-1.01.001` are the same command shape;\n"
            "   the zone split is an implementation detail the user never sees")


def z3_clean_refusal(s):
    """An implementer asking for a holdout scenario must get a clear refusal."""
    impl = Store.open(ROOT, role="implementer")
    msg, kind = "", None
    try:
        impl.zone_for("HS-001")
    except NotVisible as e:
        msg, kind = str(e), "NotVisible"
    except Exception as e:                                   # noqa: BLE001
        msg, kind = str(e), type(e).__name__
    readable = impl.readable_zones()
    actionable = ("walled" in msg and "implementer" in msg
                  and "visible_to" in msg and "not an error" in msg)
    check("Z3 a role without access gets a clean, actionable refusal",
          kind == "NotVisible" and actionable and readable == ["open"],
          f"raised: {kind}\n  {msg}\n"
          f"implementer's readable zones: {readable}\n"
          "=> the message names the zone, the role, and the config key to look at, and\n"
          "   says the wall is intentional -- so an agent does not 'fix' it by retrying")


def z4_permitted_role_transparent(s):
    ev = Store.open(ROOT, role="holdout-evaluator")
    got = ev.rows("HS-001", "SELECT expectation FROM holdout_scenario WHERE hs_id='HS-001'")
    denied_specs, dmsg = False, ""
    try:
        ev.zone_for("BC-1.01.001")
    except NotVisible as e:
        denied_specs, dmsg = True, str(e)[:70]
    val = got[0]["expectation"] if got else None
    check("Z4 a permitted role reads the walled id with the same command",
          val == "SECRET-EXPECTATION" and not denied_specs,
          f"holdout-evaluator reading HS-001 -> {val!r}\n"
          f"same role reading BC-1.01.001 -> denied={denied_specs} "
          f"{'(' + dmsg + ')' if dmsg else '(allowed: bc is in the open zone)'}\n"
          "NOTE the evaluator IS allowed the open zone here because zone granularity is\n"
          "  per-DIRECTORY, not per-table. Table-level walls need the server+GRANT\n"
          "  option (test_asymmetry A4). State which you need before implementing.")


def z5_filesystem_bounds_access(s):
    """The real boundary. Remove read permission and confirm access is impossible.

    Note: with mode 000 the OS denies the cwd itself, so the dolt process cannot even
    be spawned -- a STRONGER result than dolt failing after start. Permissions are
    restored in a finally block; leaving them clamped broke later tests once.
    """
    walled = ROOT / "walled"
    orig = stat.S_IMODE(walled.stat().st_mode)
    blocked = sibling_blocked = False
    how = ""
    try:
        os.chmod(walled, 0o000)
        try:
            r = subprocess.run(
                ["dolt", "sql", "-q", "SELECT expectation FROM holdout_scenario"],
                cwd=str(walled), capture_output=True, text=True)
            blocked = r.returncode != 0 and "SECRET-EXPECTATION" not in (r.stdout or "")
            how = f"dolt ran but failed (rc={r.returncode})"
        except PermissionError as e:
            blocked = True
            how = f"the OS refused to even spawn the process: {str(e)[:60]}"
        # a sibling zone must not be able to reach in either
        r2 = subprocess.run(["dolt", "sql", "-q",
                             "SELECT expectation FROM walled.holdout_scenario"],
                            cwd=str(ROOT / "open"), capture_output=True, text=True)
        sibling_blocked = "SECRET-EXPECTATION" not in (r2.stdout or "")
    finally:
        os.chmod(walled, orig)
    restored = subprocess.run(
        ["dolt", "sql", "-q", "SELECT expectation FROM holdout_scenario", "-r", "csv"],
        cwd=str(walled), capture_output=True, text=True)
    back = "SECRET-EXPECTATION" in (restored.stdout or "")
    check("Z5 filesystem permissions genuinely bound access",
          blocked and sibling_blocked and back,
          f"with mode 000: blocked={blocked}\n  {how}\n"
          f"from the sibling `open` zone: leaked={not sibling_blocked}\n"
          f"after restoring permissions: readable again={back}\n"
          "=> if agents run as separate OS users, chmod/chown makes the wall\n"
          "   OS-ENFORCED -- strictly stronger than today's harness-level path exclusion,\n"
          "   because the process cannot even start in the walled directory")


def z6_honest_limit(s):
    """State the limit plainly: fa's role check is ergonomics, not security."""
    bypass = subprocess.run(["dolt", "sql", "-q", "SELECT expectation FROM holdout_scenario",
                             "-r", "csv"], cwd=str(ROOT / "walled"),
                            capture_output=True, text=True)
    leaked = "SECRET-EXPECTATION" in (bypass.stdout or "")
    impl = Store.open(ROOT, role="implementer")
    refused = False
    try:
        impl.zone_for("HS-001")
    except NotVisible:
        refused = True
    check("Z6 HONEST LIMIT: an unrestricted shell bypasses fa (parity with today)",
          leaked and refused,
          f"fa refuses the implementer role: {refused}\n"
          f"but raw `dolt sql` in the walled dir still reads it: leaked={leaked}\n"
          "=> fa's role check prevents ACCIDENTS and gives good errors. The ENFORCEMENT\n"
          "   is the agent's tool profile denying the walled path -- exactly as it denies\n"
          "   `.factory/specs/` today. This is parity, not a regression. To make it\n"
          "   stronger than today, use Z5 (OS users + chmod) or A4 (server + GRANT).")


def z7_cross_zone_one_command(s):
    """An orchestrator legitimately spans zones. It must not have to think about it."""
    counts = {}
    for aid, stmt in (("BC-1.01.001", "SELECT COUNT(*) AS c FROM bc"),
                      ("HS-001", "SELECT COUNT(*) AS c FROM holdout_scenario")):
        counts[s.zone_for(aid).name] = s.rows(aid, stmt)[0]["c"]
    check("Z7 a permitted role spans zones without naming them",
          counts.get("open") == "1" and counts.get("walled") == "1",
          f"orchestrator counted per zone (routed automatically): {counts}\n"
          f"readable zones for this role: {s.readable_zones()}\n"
          "=> cost is one extra process spawn per zone touched (~144 ms, SC6); there is\n"
          "   no cross-zone JOIN, which is the price recorded in A6")


def z8_new_artifact_type_is_one_line(s):
    """Extensibility check: adding a type must not require code changes."""
    cfg = ROOT / "fa.yaml"
    before = cfg.read_text()
    cfg.write_text(before.replace(
        "  walled:\n    artifacts: [holdout_scenario, adversary_finding, evaluation]",
        "  walled:\n    artifacts: [holdout_scenario, adversary_finding, evaluation, redteam]"))
    s2 = Store.open(ROOT, role="orchestrator")
    zone = s2.zone_for_type("redteam").name
    cfg.write_text(before)
    check("Z8 adding an artifact type to a zone is a one-line config edit",
          zone == "walled",
          f"added `redteam` to zones.walled.artifacts -> routes to '{zone}'\n"
          "=> no code change. The 46 registry types map onto this with one list entry\n"
          "   each; an id-pattern line is only needed if the type has its own prefix")


def z9_error_messages(s):
    msgs = {}
    try:
        s.artifact_type("WAT-001")
    except UnknownArtifact as e:
        msgs["unknown id"] = str(e)
    s3 = Store.open(ROOT, role="implementer")
    try:
        s3.zone_for("HS-001")
    except NotVisible as e:
        msgs["walled"] = str(e)
    missing = Store.open(ROOT / "nope", role="orchestrator")
    try:
        missing.zone_for("BC-1.01.001")
    except ZoneError as e:
        msgs["uninitialized"] = str(e)
    helpful = (("Known prefixes" in msgs.get("unknown id", ""))
               and ("visible_to" in msgs.get("walled", ""))
               and ("fa init" in msgs.get("uninitialized", "")))
    check("Z9 every error names the fix, not the internals", helpful,
          "\n".join(f"  {k:14} {v[:96]}" for k, v in msgs.items())
          + "\n=> unknown id lists valid prefixes; a wall points at the config key;\n"
            "   an uninitialized store says `fa init`")


def main():
    print("=" * 74)
    print("Zone directories: real boundary, invisible UX")
    print("=" * 74)
    s = setup()
    for t in (z1_init, z2_routing_no_zone_names, z3_clean_refusal,
              z4_permitted_role_transparent, z5_filesystem_bounds_access,
              z6_honest_limit, z7_cross_zone_one_command,
              z8_new_artifact_type_is_one_line, z9_error_messages):
        try:
            t(s)
        except Exception:
            import traceback
            check(f"{t.__name__} (ERROR)", False, traceback.format_exc()[-500:])
        print()
    n = sum(1 for _, ok, _ in RESULTS if ok)
    print("=" * 74)
    print(f"{n}/{len(RESULTS)} passed")
    for nm, ok, _ in RESULTS:
        if not ok:
            print(f"  FAILED: {nm}")
    sys.exit(0 if n == len(RESULTS) else 1)


if __name__ == "__main__":
    main()
