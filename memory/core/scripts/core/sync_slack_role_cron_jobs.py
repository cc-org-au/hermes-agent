#!/usr/bin/env python3
"""Create per-Slack-channel daily status cron jobs from messaging.role_routing (chief profile).

Only one profile per **physical host** should have ``messaging.slack_role_cron_leader: true`` and
Slack role jobs for a given Slack workspace; use disjoint channel maps (and
``prune_slack_cron_for_non_leader.py`` on duplicate profiles). Operator Mac vs VPS droplet = split
ownership, not the same ``slack:C…`` targets twice.

- Skips channels already covered by an existing job with the same deliver target.
- Stagger minutes starting at base (default 10:05 Sydney wall time via cron minute/hour fields).
- Prompts enforce material-change-only delivery, strict silent envelopes, and forbid
  cross-channel duplication.

Usage:
  HERMES_HOME=~/.hermes/profiles/chief-orchestrator \\
    ./venv/bin/python memory/core/scripts/core/sync_slack_role_cron_jobs.py [--apply]

Each job prompt ends with ``--<hop> --<role-slug>`` where *role-slug* is the reporting role for that
specific message (for example ``--droplet --engineering-director``). Hop is ``--operator`` or
``--droplet``: ``auto`` uses ``--droplet`` when ``HERMES_HOME`` is ``…/profiles/*-droplet``, else
``--operator``. Override with ``messaging.role_routing.slack.hermes_hop`` or
``HERMES_SLACK_ROLE_HERMES_HOP``.

Without --apply, prints planned jobs only.
"""
from __future__ import annotations

import argparse
import os
import sys
import uuid
from pathlib import Path

def _repo_root() -> Path:
    p = Path(__file__).resolve()
    for anc in [p.parent, *p.parents]:
        if (anc / "cron" / "jobs.py").is_file():
            return anc
    return p.parents[4]


sys.path.insert(0, str(_repo_root()))


def _effective_slack_role_channels(home: Path, cfg: dict) -> dict:
    """Same merge as ``load_gateway_config``: config.yaml + messaging_role_routing overlay."""
    base_rr = (cfg.get("messaging") or {}).get("role_routing") or {}
    if not isinstance(base_rr, dict):
        base_rr = {}
    from hermes_constants import resolve_workspace_operations_dir
    from gateway.config import _extract_role_routing_overlay_doc, _merge_role_routing_overlay

    overlay_path = resolve_workspace_operations_dir(home) / "messaging_role_routing.yaml"
    if not overlay_path.is_file():
        merged_rr = base_rr
    else:
        doc = _load_yaml(overlay_path) or {}
        ov_rr = _extract_role_routing_overlay_doc(doc) if isinstance(doc, dict) else None
        if isinstance(ov_rr, dict) and ov_rr:
            merged_rr = _merge_role_routing_overlay(dict(base_rr), dict(ov_rr))
        else:
            merged_rr = base_rr
    slack = (merged_rr.get("slack") or {}).get("channels") or {}
    return slack if isinstance(slack, dict) else {}


def _load_yaml(path: Path):
    import yaml

    if not path.is_file():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


EXECUTIVE_BRIEFING_CHANNEL_SLUGS = frozenset(
    {
        "executive-team-briefings",
        "executive-briefing-lead",
    }
)

EXECUTIVE_BRIEFING_ROLES: tuple[str, ...] = (
    "project-lead-agentic-company",
    "engineering-director",
    "it-security-director",
    "operations-director",
    "product-director",
)

DISABLED_SINGLE_CHANNEL_SLUGS = frozenset(
    {
        "project-lead-agentic-company",
    }
)


def _infer_hermes_hop_tag(_home: Path, cfg: dict) -> str:
    """Return ``--droplet`` or ``--operator`` for the Hermes CLI hop (trailing argv token).

    ``auto``: ``--droplet`` when ``HERMES_HOME`` resolves to ``…/profiles/<name>`` with
    ``<name>`` ending in ``-droplet`` (e.g. VPS orchestrator clone); else ``--operator``.
    Config / env override.
    """
    env = os.environ.get("HERMES_SLACK_ROLE_HERMES_HOP", "").strip().lower()
    if env in ("droplet", "operator"):
        return f"--{env}"
    inst = os.environ.get("HERMES_GATEWAY_LOCK_INSTANCE", "").strip().lower()
    if inst in ("droplet", "operator"):
        return f"--{inst}"
    label = os.environ.get("HERMES_CLI_INSTANCE_LABEL", "").strip().lower()
    if label in ("droplet", "operator"):
        return f"--{label}"
    msg = cfg.get("messaging") or {}
    if isinstance(msg, dict):
        rr = msg.get("role_routing") or {}
        if isinstance(rr, dict):
            slack = rr.get("slack") or {}
            if isinstance(slack, dict):
                hop = slack.get("hermes_hop")
                if isinstance(hop, str):
                    h = hop.strip().lower()
                    if h in ("droplet", "operator"):
                        return f"--{h}"
    try:
        r = _home.expanduser().resolve()
        if r.parent.name == "profiles" and r.name.endswith("-droplet"):
            return "--droplet"
    except OSError:
        pass
    return "--operator"


def _legacy_chief_tag_hop(chief_tag: str | None) -> str | None:
    """If ``--chief-tag`` was ``--operator --chief-orchestrator``, return ``--operator`` only."""
    if not chief_tag or not str(chief_tag).strip():
        return None
    for tok in str(chief_tag).split():
        if tok in ("--droplet", "--operator"):
            return tok
    return None


def _resolve_hermes_hop_tag(
    *,
    hermes_hop: str,
    chief_tag: str | None,
    home: Path,
    cfg: dict,
) -> str:
    if hermes_hop in ("droplet", "operator"):
        return f"--{hermes_hop}"
    legacy = _legacy_chief_tag_hop(chief_tag)
    if legacy is not None:
        return legacy
    return _infer_hermes_hop_tag(home, cfg)


def _expand_role_slugs(role_slug: str) -> tuple[str, ...]:
    slug = str(role_slug).strip()
    if slug in EXECUTIVE_BRIEFING_CHANNEL_SLUGS:
        return EXECUTIVE_BRIEFING_ROLES
    return (slug,)


def _role_slug_from_job_name(name: str, channel_id: str) -> str | None:
    prefix = "daily-slack-role-status-"
    suffix = f"-{channel_id}"
    if not name.startswith(prefix) or not name.endswith(suffix):
        return None
    middle = name[len(prefix):-len(suffix)]
    return middle.strip() or None


def _refresh_role_slug_for_job(job: dict, channel_slug: str, channel_id: str) -> str | None:
    expanded = _expand_role_slugs(channel_slug)
    if len(expanded) == 1:
        return expanded[0]
    parsed = _role_slug_from_job_name(str(job.get("name", "")), channel_id)
    if parsed in expanded:
        return parsed
    return None


def _should_skip_channel_slug(channel_slug: str) -> bool:
    slug = str(channel_slug).strip()
    return slug in DISABLED_SINGLE_CHANNEL_SLUGS


def _role_prompt(
    role_slug: str,
    channel_id: str,
    *,
    hermes_hop_tag: str,
    executive_briefing: bool = False,
) -> str:
    if executive_briefing:
        intro = (
            f"Use Australia/Sydney (Hermes timezone). Run once per day at the scheduled wall time.\n\n"
            f"You are generating the **Slack-only executive-briefings update** for role `{role_slug}` "
            f"in channel `{channel_id}`.\n"
            f"This channel must receive a **separate post per relevant executive role**; do not synthesize "
            f"a combined executive-team summary."
        )
    else:
        intro = (
            f"Use Australia/Sydney (Hermes timezone). Run once per day at the scheduled wall time.\n\n"
            f"You are generating the **Slack-only daily status** for role `{role_slug}` in channel `{channel_id}`."
        )
    return f"""{intro}

**Hard rules**
- If there is **no material change** in reportable work, risks, staffing, ownership, or decisions since the last delivered update for this role/channel, use the exact JSON envelope with `{{"silent": true}}`.
- Slack is **never** a human-operator intervention channel. Do **not** ask the human operator to do anything here.
- Attempt autonomous resolution first using available internal tools, delegation, subprocesses, and free OpenRouter models before mentioning a blocker.
- Only report blockers that remain after autonomous action, and phrase them as current internal blockers rather than a human request.
- **Never** paste or paraphrase content meant for WhatsApp connectivity alerts, Telegram project topics, other Slack channels, or the chief DM summary.
- Each channel must add **unique** information for this role remit; do not broadcast the same narrative to multiple channels.

**Content** (only when not silent)
- Align with published policies under `HERMES_HOME/policies/` relevant to `{role_slug}` when applicable (do not paste large policy text).
- Return **Slack-ready final copy only**. Do **not** include tool traces, command transcripts, internal plans, or chain-of-thought.
- Follow the JSON delivery envelope from the system prompt **exactly** with these exact markers and no spaces:
  `###HERMES_CRON_DELIVERY_JSON`
  `###END_HERMES_CRON_DELIVERY_JSON`
- Put the upward summary into the JSON `lines` array using one string per field, in this exact order:
  `objective: ...`
  `current status: ...`
  `evidence: ...`
  `blocker: ...`
  `next action: ...`
  `requested decision, if any: ...`
  `memory recommendation: keep active|archive|close`
- Add the final line in the JSON `lines` array exactly: `{hermes_hop_tag} --{role_slug}`
- Do **not** write any text after `###END_HERMES_CRON_DELIVERY_JSON`.
- Never output literal `[SILENT]`.
- If you cannot produce grounded, role-relevant lines for this channel, return `{{"silent": true}}` in the exact envelope instead of guessing.

**Blockers, failures, and remediation**
- Use at most a **small** amount of local inspection to ground the summary.
- Only attempt remediation when the blocker is directly about this channel's deliverability or the current host's status signal for this role (for example Slack `is_archived`, missing allowlist entry, gateway platform disconnected, stale cron state).
- Do **not** run unrelated maintenance, package upgrades, setup wizards, or broad repo changes just to compose a report.
- When you fix something, state **what broke**, **what you changed**, and **verification** in the status lines. If a matter truly still needs human judgment after exhausting internal options, keep Slack non-escalatory and route that judgment need internally to the WhatsApp escalation service instead.

**Closing**
Return **only** the policy-formatted report lines via the JSON envelope. The final line must be exactly `{hermes_hop_tag} --{role_slug}` on its own line."""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Write jobs.json")
    parser.add_argument(
        "--refresh-prompts",
        action="store_true",
        help="With --apply: rewrite prompts on existing slack:* role jobs whose channel is in the merged map.",
    )
    parser.add_argument("--base-hour", type=int, default=10, help="Local hour for first stagger (default 10)")
    parser.add_argument(
        "--base-minute",
        type=int,
        default=10,
        help="First minute slot (default 10 — after chief 10:05 summary / lead 10:01 on typical layouts)",
    )
    parser.add_argument("--stagger", type=int, default=2, help="Minutes between channels (default 2)")
    parser.add_argument(
        "--hermes-hop",
        choices=("auto", "droplet", "operator"),
        default="auto",
        help="Closing-line CLI hop before profile dirname (default auto: *-droplet profiles → --droplet)",
    )
    parser.add_argument(
        "--chief-tag",
        default=None,
        metavar="STRING",
        help="Deprecated: use --hermes-hop. If set, first --operator/--droplet token is used; "
        "e.g. '--operator --chief-orchestrator' becomes '--operator'.",
    )
    args = parser.parse_args()

    hh = os.environ.get("HERMES_HOME", "").strip()
    if not hh:
        print("Set HERMES_HOME to the profile directory (e.g. ~/.hermes/profiles/chief-orchestrator).", file=sys.stderr)
        return 2
    home = Path(hh).expanduser()
    cfg = _load_yaml(home / "config.yaml")
    try:
        from hermes_cli.env_loader import load_hermes_dotenv

        load_hermes_dotenv(hermes_home=home)
    except Exception:
        pass
    _msg = cfg.get("messaging") or {}
    if isinstance(_msg, dict) and _msg.get("slack_role_cron_leader") is False:
        print(
            "messaging.slack_role_cron_leader is false — this host does not run Slack role cron sync; skip.",
            file=sys.stderr,
        )
        return 0
    slack = _effective_slack_role_channels(home, cfg)
    if not slack:
        print(
            "No Slack role channels after merge (config.yaml + workspace/.../messaging_role_routing.yaml) — nothing to do",
            file=sys.stderr,
        )
        return 1

    os.environ["HERMES_HOME"] = str(home)
    from cron.jobs import compute_next_run, load_jobs, save_jobs

    jobs = load_jobs()
    cron_cfg = cfg.get("cron") if isinstance(cfg.get("cron"), dict) else {}
    cron_default_model = str(cron_cfg.get("default_model") or "").strip() or None
    cron_default_provider = str(cron_cfg.get("default_provider") or "").strip() or None
    hermes_hop_tag = _resolve_hermes_hop_tag(
        hermes_hop=args.hermes_hop,
        chief_tag=args.chief_tag,
        home=home,
        cfg=cfg,
    )
    if args.refresh_prompts and args.apply:
        updated = 0
        for j in jobs:
            deliver = str(j.get("deliver", ""))
            if not deliver.startswith("slack:"):
                continue
            rest = deliver.split(":", 1)[1]
            cid = rest.split(":", 1)[0].strip()
            slug = slack.get(cid)
            if not slug or str(slug).strip() == "chief_orchestrator":
                continue
            if _should_skip_channel_slug(str(slug).strip()):
                continue
            slug = _refresh_role_slug_for_job(j, str(slug).strip(), cid)
            if not slug:
                continue
            j["prompt"] = _role_prompt(
                slug,
                cid,
                hermes_hop_tag=hermes_hop_tag,
                executive_briefing=slug in EXECUTIVE_BRIEFING_ROLES and str(slack.get(cid)).strip() in EXECUTIVE_BRIEFING_CHANNEL_SLUGS,
            )
            j["strict_delivery_envelope"] = True
            j["model"] = cron_default_model
            j["provider"] = cron_default_provider
            updated += 1
        if updated:
            print(f"refreshed prompts on {updated} existing job(s)", file=sys.stderr)

    existing_names = {str(j.get("name", "")) for j in jobs}

    minute = args.base_minute
    planned = []
    for channel_id, role_slug in sorted(slack.items(), key=lambda x: x[1]):
        cid = str(channel_id).strip()
        slug = str(role_slug).strip()
        if slug == "chief_orchestrator":
            print(f"skip chief_orchestrator channel {cid} (dedicated chief summary / operator DM jobs cover orchestration)")
            continue
        if _should_skip_channel_slug(slug):
            print(f"skip {slug} channel {cid} (handled by non-Slack status path)")
            continue
        deliver = f"slack:{cid}"
        expanded_roles = _expand_role_slugs(slug)
        for expanded_role in expanded_roles:
            name = f"daily-slack-role-status-{expanded_role}-{cid}"
            if name in existing_names:
                print(f"skip (exists): {name}")
                continue
            expr = f"{minute} {args.base_hour} * * *"
            minute += args.stagger
            prompt = _role_prompt(
                expanded_role,
                cid,
                hermes_hop_tag=hermes_hop_tag,
                executive_briefing=slug in EXECUTIVE_BRIEFING_CHANNEL_SLUGS,
            )
            job = {
                "id": uuid.uuid4().hex[:12],
                "name": name,
                "prompt": prompt,
                "strict_delivery_envelope": True,
                "skills": [],
                "skill": None,
                "model": cron_default_model,
                "provider": cron_default_provider,
                "base_url": None,
                "schedule": {"kind": "cron", "expr": expr, "display": expr},
                "schedule_display": expr,
                "repeat": {"times": 999999, "completed": 0},
                "enabled": True,
                "state": "scheduled",
                "paused_at": None,
                "paused_reason": None,
                "created_at": __import__("datetime").datetime.now().astimezone().isoformat(),
                "next_run_at": compute_next_run({"kind": "cron", "expr": expr}),
                "last_run_at": None,
                "last_status": None,
                "last_error": None,
                "deliver": deliver,
                "origin": None,
            }
            planned.append(job)
            print(f"plan: {name} {expr} -> {deliver}")

    if not args.apply:
        if args.refresh_prompts:
            print("--refresh-prompts requires --apply", file=sys.stderr)
            return 2
        print("\nDry run. Pass --apply to append to cron/jobs.json")
        return 0

    jobs.extend(planned)
    save_jobs(jobs)
    print(f"Wrote {len(planned)} job(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
