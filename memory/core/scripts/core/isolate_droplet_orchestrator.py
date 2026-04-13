#!/usr/bin/env python3
"""Mark a cloned orchestrator profile as the isolated VPS instance (no Slack cron / no Slack gateway).

Run on the **droplet** after:

  hermes profile create chief-orchestrator-droplet --clone-all --clone-from chief-orchestrator --no-alias

Then:

  HERMES_HOME=~/.hermes/profiles/chief-orchestrator-droplet \\
    ./venv/bin/python scripts/core/isolate_droplet_orchestrator.py

This script:
- Removes cron jobs that deliver to Slack (duplicate of Mac/operator messaging leader).
- Sets ``platforms.slack.enabled: false`` in config.yaml (gateway still runs Telegram/WhatsApp if configured).
- Sets ``messaging.slack_role_cron_leader: false`` so ``sync_slack_role_cron_jobs.py --apply`` is a no-op here.
- Appends ``HERMES_GATEWAY_LOCK_INSTANCE`` / ``HERMES_CLI_INSTANCE_LABEL`` to ``.env`` when missing.
- Forces **OpenAI primary mode (OPM) off** in ``config.yaml`` and token-governance runtime YAML, and appends
  ``HERMES_OPENAI_PRIMARY_MODE=0`` so config/runtime cannot re-enable OPM until you remove the env line.
- If ``model.provider: gemini`` but ``model.default`` looks like an OpenRouter slug, rewrites ``model.default``
  to a native Gemini id (fixes HTTP 404 ``models/openai/...`` on generativelanguage).

The **operator** Mac should keep profile ``chief-orchestrator`` and set
``messaging.slack_role_cron_leader: true`` (default when key absent = leader).

If this VPS uses a **separate Slack app** (different tokens) and a **separate workspace**
channel map, re-enable Slack check-ins with ``restore_slack_role_checkins.py`` (see that script).
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def _load_yaml(path: Path) -> dict:
    import yaml

    if not path.is_file():
        return {}
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    return doc if isinstance(doc, dict) else {}


def _save_yaml(path: Path, data: dict) -> None:
    import yaml

    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")


def _strip_slack_cron_jobs(home: Path) -> int:
    os.environ["HERMES_HOME"] = str(home)
    from cron.jobs import load_jobs, save_jobs

    jobs = load_jobs()
    removed = 0
    kept = []
    for j in jobs:
        deliver = str(j.get("deliver") or "")
        name = str(j.get("name") or "")
        if deliver.startswith("slack:") or name.startswith("daily-slack-role-status-"):
            removed += 1
            print(f"remove cron job: {name or j.get('id')} ({deliver})")
            continue
        kept.append(j)
    if removed:
        save_jobs(kept)
    else:
        print("no Slack-target cron jobs to remove")
    return removed


def apply_routing_defaults_to_config(cfg: dict) -> None:
    """Mutate *cfg* in memory: OPM off; native Gemini model id if provider is gemini."""
    opm = cfg.setdefault("openai_primary_mode", {})
    if not isinstance(opm, dict):
        opm = {}
        cfg["openai_primary_mode"] = opm
    opm["enabled"] = False

    mdl = cfg.get("model")
    if isinstance(mdl, dict):
        prov = str(mdl.get("provider") or "").strip().lower()
        if prov == "gemini":
            from agent.tier_model_routing import coerce_model_id_for_native_gemini_api

            cur = str(mdl.get("default") or mdl.get("model") or "").strip()
            fixed = coerce_model_id_for_native_gemini_api(cur, full_config=cfg)
            if fixed != cur:
                print(f"fix model.default for gemini: {cur!r} -> {fixed!r}")
                mdl["default"] = fixed


def apply_profile_normal_routing_defaults(home: Path) -> None:
    """OPM off, Gemini slug fix, token-governance OPM off, ``HERMES_OPENAI_PRIMARY_MODE=0`` in ``.env``.

    Use on any profile (e.g. ``chief-orchestrator-droplet``) without Slack/cron isolation.
    """
    cfg_path = home / "config.yaml"
    if not cfg_path.is_file():
        print(f"warning: missing {cfg_path}", file=sys.stderr)
    else:
        cfg = _load_yaml(cfg_path)
        apply_routing_defaults_to_config(cfg)
        _save_yaml(cfg_path, cfg)
        print(f"patched {cfg_path} (openai_primary_mode.enabled=false + gemini model guard)")
    _patch_token_governance_runtime(home)
    _append_opm_disable_env(home)
    print("done — restart gateway: hermes -p <profile> gateway restart --sync")


def _append_opm_disable_env(home: Path) -> None:
    """Append ``HERMES_OPENAI_PRIMARY_MODE=0`` when missing (env wins over YAML for OPM)."""
    env_path = home / ".env"
    if not env_path.is_file():
        print(f"warning: missing {env_path} — add HERMES_OPENAI_PRIMARY_MODE=0 manually", file=sys.stderr)
        return
    text = env_path.read_text(encoding="utf-8", errors="replace")
    keys_present = set()
    for line in text.splitlines():
        m = re.match(r'^[ \t]*(?:export[ \t]+)?([A-Za-z_][A-Za-z0-9_]*)=', line)
        if m:
            keys_present.add(m.group(1))
    key, val = "HERMES_OPENAI_PRIMARY_MODE", "0"
    if key in keys_present:
        print(f"keep existing {key}")
        return
    with open(env_path, "a", encoding="utf-8") as f:
        if text and not text.endswith("\n"):
            f.write("\n")
        f.write(f"{key}={val}\n")
    print(f"appended {key}={val}")


def _patch_config(home: Path) -> None:
    cfg_path = home / "config.yaml"
    cfg = _load_yaml(cfg_path)
    apply_routing_defaults_to_config(cfg)

    plat = cfg.setdefault("platforms", {})
    if not isinstance(plat, dict):
        plat = {}
        cfg["platforms"] = plat
    slack = plat.setdefault("slack", {})
    if not isinstance(slack, dict):
        slack = {}
        plat["slack"] = slack
    slack["enabled"] = False

    msg = cfg.setdefault("messaging", {})
    if not isinstance(msg, dict):
        msg = {}
        cfg["messaging"] = msg
    msg["slack_role_cron_leader"] = False
    # Strict “all platforms connected” is unrealistic when this host intentionally
    # disables Slack and may share Telegram/WhatsApp tokens with the operator gateway.
    msg["watchdog_require_all_platforms"] = False

    _save_yaml(cfg_path, cfg)
    print(
        f"patched {cfg_path} (openai_primary_mode.enabled=false, gemini model guard if applicable, "
        "platforms.slack.enabled=false, messaging.slack_role_cron_leader=false, "
        "messaging.watchdog_require_all_platforms=false)"
    )


_ENV_LINES = [
    ('HERMES_OPENAI_PRIMARY_MODE', '0'),
    ('HERMES_GATEWAY_LOCK_INSTANCE', 'droplet'),
    ('HERMES_CLI_INSTANCE_LABEL', 'droplet'),
]


def _patch_token_governance_runtime(home: Path) -> None:
    path = home / "workspace/memory/runtime/operations/hermes_token_governance.runtime.yaml"
    if not path.is_file():
        print(f"skip token governance patch (missing {path})")
        return
    doc = _load_yaml(path)
    if not doc:
        doc = {}
    opm = doc.setdefault("openai_primary_mode", {})
    if not isinstance(opm, dict):
        opm = {}
        doc["openai_primary_mode"] = opm
    opm["enabled"] = False
    _save_yaml(path, doc)
    print(f"patched {path} (openai_primary_mode.enabled=false)")


def _append_env(home: Path) -> None:
    env_path = home / ".env"
    if not env_path.is_file():
        print(f"warning: missing {env_path} — create manually", file=sys.stderr)
        return
    text = env_path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    keys_present = set()
    for line in lines:
        m = re.match(r'^[ \t]*(?:export[ \t]+)?([A-Za-z_][A-Za-z0-9_]*)=', line)
        if m:
            keys_present.add(m.group(1))
    added = 0
    with open(env_path, "a", encoding="utf-8") as f:
        for key, val in _ENV_LINES:
            if key in keys_present:
                print(f"keep existing {key}")
                continue
            if added == 0 and text and not text.endswith("\n"):
                f.write("\n")
            f.write(f"{key}={val}\n")
            print(f"appended {key}={val}")
            added += 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--home",
        metavar="PATH",
        help="Profile directory (default: HERMES_HOME)",
    )
    args = parser.parse_args()
    hh = (args.home or os.environ.get("HERMES_HOME") or "").strip()
    if not hh:
        print("Set HERMES_HOME or pass --home", file=sys.stderr)
        return 2
    home = Path(hh).expanduser()
    if not home.is_dir():
        print(f"Not a directory: {home}", file=sys.stderr)
        return 2

    _strip_slack_cron_jobs(home)
    _patch_config(home)
    _patch_token_governance_runtime(home)
    _append_env(home)
    print("done — restart gateway for this profile: hermes -p <profile> gateway restart --sync")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
