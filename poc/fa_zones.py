#!/usr/bin/env python3
"""Zone resolution for `fa` — the part that must stay invisible.

Design rule: **an agent never names a zone.** It says `fa get HS-001` and fa works out
which database that lives in, whether this role may see it, and what to say if not.

On disk:

    <project>/
    ├── .factory-db/            # everything fa owns
    │   ├── fa.yaml             # ONE config file
    │   ├── open/               # a Dolt database (trust zone)
    │   └── walled/             # a Dolt database (trust zone)
    └── .factory/               # rendered markdown (generated, committed)

Zones MUST be separate directories, and fa MUST invoke dolt with cwd set to a single
zone. Passing `--data-dir` over the parent exposes siblings and allows cross-database
queries (measured: test_asymmetry A2).

Honest scope: fa's role check is ERGONOMICS — a clear refusal instead of a confusing
failure. The actual boundary is the agent's tool profile / filesystem permissions
denying the walled directory, exactly as it denies `.factory/specs/` today. An agent
with unrestricted shell access can bypass fa; that is equally true of the current
path-exclusion design, so this is parity, not a regression.
"""
from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------- config

# The whole zone map. Adding an artifact type is one line here.
DEFAULT_CONFIG = """\
version: 1
default_zone: open
zones:
  open:
    artifacts: [bc, vp, story, epic, task, adr, wave, phase, state, template, lease,
                capability, domain_invariant, nfr, fr, subsystem, instance]
  walled:
    artifacts: [holdout_scenario, adversary_finding, evaluation]
    visible_to: [orchestrator, holdout-evaluator, adversary, state-manager]
"""

# id prefix -> artifact type. This is what lets `fa get HS-001` route itself.
ID_PATTERNS: list[tuple[str, str]] = [
    (r"^BC-\d+\.\d+\.\d+", "bc"),
    (r"^VP-\d+", "vp"),
    (r"^S-[\d.]+", "story"),
    (r"^E-\d+", "epic"),
    (r"^ADR-\d+", "adr"),
    (r"^CAP-\d+", "capability"),
    (r"^DI-\d+", "domain_invariant"),
    (r"^NFR-[A-Z]+-\d+", "nfr"),
    (r"^FR-\d+", "fr"),
    (r"^SS-\d+", "subsystem"),
    (r"^HS-\d+", "holdout_scenario"),
    (r"^ADV-", "adversary_finding"),
    (r"^EVAL-", "evaluation"),
]


class ZoneError(RuntimeError):
    """Base for zone problems. All carry an actionable message."""


class UnknownArtifact(ZoneError):
    pass


class NotVisible(ZoneError):
    """The role may not see this zone. Deliberately says WHICH zone and WHY."""


@dataclass
class Zone:
    name: str
    path: Path
    artifacts: list[str] = field(default_factory=list)
    visible_to: list[str] | None = None          # None = visible to everyone

    def allows(self, role: str) -> bool:
        return self.visible_to is None or role in self.visible_to


def _parse_config(text: str) -> dict:
    """Tiny YAML subset: enough for this config, no dependency.

    Bracketed lists are JOINED onto one logical line FIRST. Parsing line-by-line while
    a `[...]` list is still open swallows the next zone's header as a continuation.
    """
    joined: list[str] = []
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if joined and joined[-1].count("[") > joined[-1].count("]"):
            joined[-1] += " " + raw.strip()
        else:
            joined.append(raw.rstrip())

    out: dict = {"zones": {}}
    cur: str | None = None
    for line in joined:
        indent = len(line) - len(line.lstrip())
        m = re.match(r"^(\w[\w-]*):\s*(.*)$", line.strip())
        if not m:
            continue
        key, val = m.group(1), m.group(2).strip()
        if indent == 0:
            cur = "zones" if key == "zones" else None
            if key != "zones":
                out[key] = val
        elif indent == 2 and cur is not None:
            out["zones"].setdefault(key, {})
            cur = key
        elif indent >= 4 and cur and cur in out["zones"]:
            if val.startswith("["):
                out["zones"][cur][key] = [
                    x.strip() for x in val.strip("[]").split(",") if x.strip()]
            else:
                out["zones"][cur][key] = val
    return out


@dataclass
class Store:
    """The one object `fa` holds. Everything else routes through it."""
    root: Path
    role: str = "orchestrator"
    zones: dict[str, Zone] = field(default_factory=dict)
    default_zone: str = "open"

    @classmethod
    def open(cls, root: str | Path | None = None, role: str | None = None) -> "Store":
        root = Path(root or os.environ.get("FA_ROOT", ".factory-db")).resolve()
        role = role or os.environ.get("FA_ROLE", "orchestrator")
        cfg_path = root / "fa.yaml"
        cfg = _parse_config(cfg_path.read_text() if cfg_path.exists() else DEFAULT_CONFIG)
        zones = {}
        for name, spec in cfg.get("zones", {}).items():
            zones[name] = Zone(name=name, path=root / name,
                               artifacts=spec.get("artifacts", []),
                               visible_to=spec.get("visible_to"))
        return cls(root=root, role=role, zones=zones,
                   default_zone=cfg.get("default_zone", "open"))

    # ---------------------------------------------------------- routing

    def artifact_type(self, artifact_id: str) -> str:
        for pat, kind in ID_PATTERNS:
            if re.match(pat, artifact_id):
                return kind
        raise UnknownArtifact(
            f"'{artifact_id}' does not match any known artifact id pattern. "
            f"Known prefixes: BC- VP- S- E- ADR- CAP- DI- NFR- FR- SS- HS- ADV- EVAL-")

    def zone_for_type(self, kind: str) -> Zone:
        for z in self.zones.values():
            if kind in z.artifacts:
                return z
        raise UnknownArtifact(
            f"artifact type '{kind}' is not assigned to a zone in fa.yaml")

    def zone_for(self, artifact_id: str) -> Zone:
        """The whole point: id in, zone out. The caller never names a zone."""
        z = self.zone_for_type(self.artifact_type(artifact_id))
        if not z.allows(self.role):
            raise NotVisible(
                f"'{artifact_id}' lives in the '{z.name}' zone, which role "
                f"'{self.role}' may not read. This is an information-asymmetry wall, "
                f"not an error — see fa.yaml zones.{z.name}.visible_to")
        if not z.path.exists():
            raise ZoneError(f"zone '{z.name}' is not initialized at {z.path} "
                            f"— run `fa init`")
        return z

    def readable_zones(self) -> list[str]:
        return sorted(n for n, z in self.zones.items() if z.allows(self.role))

    # ---------------------------------------------------------- execution

    def sql(self, artifact_id_or_zone: str, stmt: str, timeout: int = 300):
        """Run SQL in the zone that owns this artifact.

        cwd is ALWAYS a single zone directory. Never pass --data-dir over the parent:
        that exposes sibling zones and permits cross-database queries (A2).
        """
        if artifact_id_or_zone in self.zones:
            z = self.zones[artifact_id_or_zone]
            if not z.allows(self.role):
                raise NotVisible(f"role '{self.role}' may not read zone '{z.name}'")
        else:
            z = self.zone_for(artifact_id_or_zone)
        return subprocess.run(["dolt", "sql", "-q", stmt, "-r", "csv"],
                              cwd=z.path, capture_output=True, text=True, timeout=timeout)

    def rows(self, artifact_id_or_zone: str, stmt: str) -> list[dict]:
        r = self.sql(artifact_id_or_zone, stmt)
        lines = [l for l in (r.stdout or "").strip().splitlines() if l.strip()]
        if len(lines) < 2:
            return []
        hdr = lines[0].split(",")
        return [dict(zip(hdr, l.split(","))) for l in lines[1:]]

    def init(self):
        """`fa init` — create every zone. One command, no zone names required."""
        self.root.mkdir(parents=True, exist_ok=True)
        cfg = self.root / "fa.yaml"
        if not cfg.exists():
            cfg.write_text(DEFAULT_CONFIG)
        made = []
        for z in self.zones.values():
            if not (z.path / ".dolt").exists():
                z.path.mkdir(parents=True, exist_ok=True)
                subprocess.run(["dolt", "init", "--name", "fa", "--email", "fa@local"],
                               cwd=z.path, capture_output=True, text=True)
                made.append(z.name)
        return made
