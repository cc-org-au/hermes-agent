"""
Text helpers for /paperclip slash commands and autoresearch repo path resolution.

Upstream paperclip: https://github.com/cc-org-au/paperclip

Repo roots are optional: ``integrations.paperclip.repo`` / ``integrations.autoresearch.repo``
in config.yaml, or ``HERMES_PAPERCLIP_REPO`` / ``HERMES_AUTORESEARCH_REPO``.
"""

from __future__ import annotations

import os
from typing import Any, Mapping, Optional

PAPERCLIP_REPO_URL = "https://github.com/cc-org-au/paperclip"


def _cfg_dict(config: Any) -> Mapping[str, Any]:
    if isinstance(config, dict):
        return config
    return {}


def resolve_paperclip_repo(config: Optional[Mapping[str, Any]] = None) -> str:
    raw = (os.getenv("HERMES_PAPERCLIP_REPO") or "").strip()
    if raw:
        return os.path.expanduser(raw)
    ig = _cfg_dict(config).get("integrations") or {}
    pc = ig.get("paperclip") if isinstance(ig, dict) else None
    if isinstance(pc, dict):
        raw = (pc.get("repo") or "").strip()
    else:
        raw = ""
    return os.path.expanduser(raw) if raw else ""


def resolve_autoresearch_repo(config: Optional[Mapping[str, Any]] = None) -> str:
    raw = (os.getenv("HERMES_AUTORESEARCH_REPO") or "").strip()
    if raw:
        return os.path.expanduser(raw)
    ig = _cfg_dict(config).get("integrations") or {}
    ar = ig.get("autoresearch") if isinstance(ig, dict) else None
    if isinstance(ar, dict):
        raw = (ar.get("repo") or "").strip()
    else:
        raw = ""
    return os.path.expanduser(raw) if raw else ""


def _first_topic(cmd_line: str, canonical: str) -> str:
    parts = (cmd_line or "").strip().split()
    if len(parts) < 2:
        return "help"
    return (parts[1] or "help").lower()


def _repo_hint(path: str, name: str) -> str:
    if not path:
        return (
            f"No local clone path set. Add `integrations.{name}.repo` in config.yaml "
            f"or set `HERMES_{name.upper()}_REPO` to the cloned repository root."
        )
    exists = os.path.isdir(path)
    return (
        f"Configured repo: `{path}` {'(directory found)' if exists else '(path not found on this machine)'}"
    )


def format_paperclip_message(cmd_line: str, config: Optional[Mapping[str, Any]] = None) -> str:
    """Return help text for ``/paperclip [help|onboard|configure|dev]``."""
    topic = _first_topic(cmd_line, "paperclip")
    repo = resolve_paperclip_repo(config)
    hint = _repo_hint(repo, "paperclip")

    if topic in ("help", "h", "?"):
        return "\n".join(
            [
                "**Paperclip** — open-source orchestration for agent teams (company-scale goals, budgets, heartbeats).",
                f"Upstream: {PAPERCLIP_REPO_URL}",
                "",
                "**Subcommands**",
                "• `/paperclip onboard` — zero-install quickstart via npm",
                "• `/paperclip configure` — edit Paperclip settings",
                "• `/paperclip dev` — run from a git clone (API + UI)",
                "",
                hint,
                "",
                "Docs: README “Quickstart”, `doc/DEVELOPING.md` in the repo.",
            ]
        )

    if topic == "onboard":
        lines = [
            "**Paperclip — onboard (quickstart)**",
            "",
            "From any directory (Node.js 20+, pnpm 9.15+ recommended):",
            "```",
            "npx paperclipai onboard --yes",
            "```",
            "Rerunning `onboard` keeps existing config; use `npx paperclipai configure` to edit.",
            "",
            "Default API: `http://localhost:3100` (embedded Postgres; no separate DB setup).",
            "",
            hint,
        ]
        return "\n".join(lines)

    if topic in ("configure", "config"):
        return "\n".join(
            [
                "**Paperclip — configure**",
                "",
                "```",
                "npx paperclipai configure",
                "```",
                "",
                hint,
            ]
        )

    if topic in ("dev", "clone", "run"):
        lines = [
            "**Paperclip — develop from source**",
            "",
            "```",
            f"git clone {PAPERCLIP_REPO_URL}",
            "cd paperclip",
            "pnpm install",
            "pnpm dev              # API + UI (watch)",
            "# or: pnpm dev:server  # API only",
            "```",
            "",
            "See repo `package.json` and `doc/DEVELOPING.md` for `pnpm build`, `pnpm test:run`, DB tasks.",
            "",
            hint,
        ]
        if repo:
            lines.extend(["", f"If your clone is at `{repo}`, run the same commands inside that directory."])
        return "\n".join(lines)

    return (
        f"Unknown topic `{topic}`. Use: `/paperclip help|onboard|configure|dev`\n\n"
        + format_paperclip_message("/paperclip help", config)
    )
