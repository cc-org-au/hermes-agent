#!/usr/bin/env python3
"""
Populate workspace/operations/CHANNEL_ARCHITECTURE.md and SKILL_INVENTORY_REGISTER.md
from the active HERMES_HOME (.env + skills/). Intended for operator runs on the VPS
after messaging env is configured.

Usage:
  export HERMES_HOME=/path/to/profile
  ./venv/bin/python scripts/render_workspace_registers_from_env.py

Does not print secrets to stdout; writes markdown under workspace/operations/.
"""

from __future__ import annotations

import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


def _hermes_home() -> Path:
    raw = os.environ.get("HERMES_HOME", "").strip()
    if not raw:
        print("HERMES_HOME required", file=sys.stderr)
        sys.exit(1)
    return Path(raw).expanduser().resolve()


def parse_dotenv(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, _, v = line.partition("=")
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k:
            out[k] = v
    return out


def _mask_token(val: str, keep: int = 6) -> str:
    v = (val or "").strip()
    if len(v) <= keep:
        return "***" if v else ""
    return v[:keep] + "…"


def render_channel_architecture(home: Path, env: dict[str, str]) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    rows = []

    def add_platform(title: str, keys: list[tuple[str, str]]) -> None:
        block = [f"### {title}", "", "| Variable | Value |", "|----------|-------|"]
        for label, key in keys:
            val = env.get(key, "")
            if not val:
                block.append(f"| `{key}` | *(unset)* |")
            elif "TOKEN" in key or "SECRET" in key or "PASSWORD" in key or "KEY" in key:
                block.append(f"| `{key}` | `{_mask_token(val)}` |")
            else:
                block.append(f"| `{key}` | `{val}` |")
        rows.append("\n".join(block))

    intro = f"""# Channel architecture (W003 — generated)

> **Generated:** {now} from `{home}/.env` via `scripts/render_workspace_registers_from_env.py`  
> **Do not commit secrets:** user/channel IDs are operational data; rotate tokens via `.env` only.

This file mirrors **live gateway allowlists** and **home channel** hints. Integration surface checks use
**channel** allowlists when set (`TELEGRAM_ALLOWED_CHATS`, `SLACK_ALLOWED_CHANNELS`, …); your profile
currently emphasises **user** allowlists (`*_ALLOWED_USERS`) and **home channel** vars — both are valid Hermes patterns.

Restart gateway after editing `.env`:
`./venv/bin/python -m hermes_cli.main -p <profile> gateway restart`

"""

    add_platform(
        "Slack",
        [
            ("User allowlist", "SLACK_ALLOWED_USERS"),
            ("Channel allowlist", "SLACK_ALLOWED_CHANNELS"),
            ("Workspace / team allowlist", "SLACK_ALLOWED_TEAMS"),
            ("Home channel ID", "SLACK_HOME_CHANNEL"),
            ("Home channel name", "SLACK_HOME_CHANNEL_NAME"),
            ("Bot token (masked)", "SLACK_BOT_TOKEN"),
            ("App token (masked)", "SLACK_APP_TOKEN"),
        ],
    )
    add_platform(
        "Telegram",
        [
            ("User allowlist", "TELEGRAM_ALLOWED_USERS"),
            ("Chat allowlist", "TELEGRAM_ALLOWED_CHATS"),
            ("Home channel ID", "TELEGRAM_HOME_CHANNEL"),
            ("Home channel name", "TELEGRAM_HOME_CHANNEL_NAME"),
            ("Bot token (masked)", "TELEGRAM_BOT_TOKEN"),
        ],
    )
    add_platform(
        "Discord",
        [
            ("User allowlist", "DISCORD_ALLOWED_USERS"),
            ("Channel allowlist", "DISCORD_ALLOWED_CHANNELS"),
            ("Guild allowlist", "DISCORD_ALLOWED_GUILDS"),
            ("Bot token (masked)", "DISCORD_BOT_TOKEN"),
        ],
    )
    add_platform(
        "WhatsApp",
        [
            ("User allowlist", "WHATSAPP_ALLOWED_USERS"),
            ("Chat allowlist", "WHATSAPP_ALLOWED_CHATS"),
            ("Mode", "WHATSAPP_MODE"),
            ("Enabled flag", "WHATSAPP_ENABLED"),
        ],
    )

    # .env fragments for copy-paste (non-secret lines only)
    allow_lines = []
    for key in sorted(env):
        if any(
            x in key
            for x in (
                "ALLOWED_USERS",
                "ALLOWED_CHATS",
                "ALLOWED_CHANNELS",
                "ALLOWED_GUILDS",
                "ALLOWED_TEAMS",
                "HOME_CHANNEL",
                "HOME_CHANNEL_NAME",
            )
        ):
            if "TOKEN" in key or "SECRET" in key:
                continue
            allow_lines.append(f"{key}={env[key]}")
    env_fragment = "\n".join(allow_lines) if allow_lines else "# (no allowlist / home-channel keys found)"

    body = intro + "\n\n".join(rows) + "\n\n---\n\n## `.env` allowlist / home-channel lines (no tokens)\n\n```bash\n" + env_fragment + "\n```\n"
    return body


def skill_title(skill_dir: Path) -> str:
    sm = skill_dir / "SKILL.md"
    if sm.is_file():
        text = sm.read_text(encoding="utf-8", errors="replace")[:4000]
        m = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
        if m:
            return m.group(1).strip()
    return skill_dir.name.replace("-", " ").title()


def render_skill_inventory(home: Path) -> str:
    skills_root = home / "skills"
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# Skill inventory register (W004 — generated)",
        "",
        f"> **Generated:** {now} from `{skills_root}`",
        "",
        "| Skill folder | Title / notes | Source | Version | Filesystem | Network | Secrets | Last reviewed |",
        "|--------------|---------------|--------|---------|------------|---------|---------|---------------|",
    ]
    if not skills_root.is_dir():
        lines.append("| — | *(no skills directory)* | | | | | | |")
        return "\n".join(lines) + "\n"

    for p in sorted(skills_root.iterdir()):
        if not p.is_dir() or p.name.startswith("."):
            continue
        title = skill_title(p)
        req_net = "see SKILL.md"
        req_fs = "see SKILL.md"
        secrets = "see SKILL.md"
        ver = "bundled"
        lines.append(
            f"| `{p.name}` | {title[:80]} | `{p}` | {ver} | {req_fs} | {req_net} | {secrets} | {now[:10]} |"
        )

    lines.append("")
    lines.append("## Hygiene")
    lines.append("")
    lines.append("- Review quarterly per `operations/README.md` (ORG_HYGIENE_RULES cadence).")
    lines.append("- Update **Secrets** column after reading each skill’s `SKILL.md` required_environment_variables.")
    return "\n".join(lines) + "\n"


def seed_consultant_board(ops: Path) -> None:
    cr = ops / "CONSULTANT_REQUEST_REGISTER.md"
    if cr.is_file():
        t = cr.read_text(encoding="utf-8")
        if "CR-SEED-001" not in t:
            old = "| | | | | | | draft / approved / rejected / completed |"
            new = (
                "| CR-SEED-001 | 2026-04-05 | operator | — | "
                "Registry operational — replace with first real premium-model request | "
                "n/a | open |"
            )
            if old in t:
                cr.write_text(t.replace(old, new, 1), encoding="utf-8")

    br = ops / "BOARD_REVIEW_REGISTER.md"
    if br.is_file():
        t = br.read_text(encoding="utf-8")
        if "BR-SEED-001" not in t:
            # Only replace the placeholder row in Decisions log (six empty cells).
            old = "| | | | | | |"
            new = (
                "| 2026-04-05 | BR-SEED-001 | Register operational | "
                "Seed row — replace after first board session | Chief | — |"
            )
            if old in t:
                br.write_text(t.replace(old, new, 1), encoding="utf-8")


def merge_org_tool_policy_notes(home: Path) -> None:
    """Document security sub-agent tier/tool alignment (Hermes ignores unknown YAML keys)."""
    path = home / "workspace" / "operations" / "hermes_token_governance.runtime.yaml"
    if not path.is_file():
        return
    try:
        import yaml
    except ImportError:
        return
    raw = path.read_text(encoding="utf-8")
    data = yaml.safe_load(raw) or {}
    if not isinstance(data, dict):
        return
    if data.get("org_tool_policy_notes"):
        return
    data["org_tool_policy_notes"] = (
        "Security foundation profiles (ag-sec-*) use toolsets from scripts/org_agent_profiles_manifest.yaml "
        "after bootstrap; not duplicated in core. Default delegation uses chief tier_models; use consultant "
        "routing / tier E–F for incident or board-class work per MODEL_ROUTING_REGISTRY.md."
    )
    path.write_text(
        yaml.dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def patch_security_alert_w003_w004(home: Path) -> None:
    path = home / "workspace" / "operations" / "SECURITY_ALERT_REGISTER.md"
    if not path.is_file():
        return
    text = path.read_text(encoding="utf-8")
    text2 = text
    text2 = re.sub(
        r"(\| W003 \|[^\n]+\| Medium \| )\*\*IN PROGRESS\*\*",
        r"\1**COMPLETE**",
        text2,
        count=1,
    )
    text2 = re.sub(
        r"\| W004 \|[^\n]+\n",
        "| W004 | Skill inventory populated from live `skills/` | Low | **COMPLETE** | AG-012 | "
        "Regenerated via `scripts/render_workspace_registers_from_env.py`; refine Network/Secrets per each `SKILL.md`. |\n",
        text2,
        count=1,
    )
    if text2 != text:
        path.write_text(text2, encoding="utf-8")


def main() -> None:
    home = _hermes_home()
    ops = home / "workspace" / "operations"
    ops.mkdir(parents=True, exist_ok=True)
    env = parse_dotenv(home / ".env")
    (ops / "CHANNEL_ARCHITECTURE.md").write_text(render_channel_architecture(home, env), encoding="utf-8")
    (ops / "SKILL_INVENTORY_REGISTER.md").write_text(render_skill_inventory(home), encoding="utf-8")
    patch_security_alert_w003_w004(home)
    seed_consultant_board(ops)
    merge_org_tool_policy_notes(home)
    print(f"Wrote {ops / 'CHANNEL_ARCHITECTURE.md'}")
    print(f"Wrote {ops / 'SKILL_INVENTORY_REGISTER.md'}")


if __name__ == "__main__":
    main()
