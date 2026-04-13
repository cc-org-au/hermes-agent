#!/usr/bin/env python3
"""Apply normal routing defaults on an existing profile (no Slack/cron changes).

Sets:

- ``openai_primary_mode.enabled: false`` in ``config.yaml``
- ``openai_primary_mode.enabled: false`` in token governance runtime YAML (if present)
- ``HERMES_OPENAI_PRIMARY_MODE=0`` in profile ``.env`` when missing (env forces OPM off)
- If ``model.provider: gemini`` and ``model.default`` is an OpenRouter-style slug, rewrites to a
  native Gemini model id (fixes HTTP 404 on ``generativelanguage.googleapis.com``).

Run on the **droplet** (or any host) after ``git pull``:

  HERMES_HOME=~/.hermes/profiles/chief-orchestrator-droplet \\
    ./venv/bin/python scripts/core/patch_profile_normal_routing_defaults.py

For a **new** cloned droplet profile, prefer ``isolate_droplet_orchestrator.py`` (includes Slack/cron).
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import importlib.util

_iso = ROOT / "scripts" / "core" / "isolate_droplet_orchestrator.py"
_spec = importlib.util.spec_from_file_location("hermes_isolate_droplet", _iso)
if _spec is None or _spec.loader is None:
    raise RuntimeError(f"cannot load {_iso}")
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
apply_profile_normal_routing_defaults = _mod.apply_profile_normal_routing_defaults


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--home",
        metavar="PATH",
        help="Profile directory (default: HERMES_HOME)",
    )
    args = p.parse_args()
    hh = (args.home or os.environ.get("HERMES_HOME") or "").strip()
    if not hh:
        print("Set HERMES_HOME or pass --home", file=sys.stderr)
        return 2
    home = Path(hh).expanduser()
    if not home.is_dir():
        print(f"Not a directory: {home}", file=sys.stderr)
        return 2
    apply_profile_normal_routing_defaults(home)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
