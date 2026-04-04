#!/usr/bin/env python3
"""
Insert or refresh top/bottom read-order navigation blocks in every policies/*.md file.

Canonical sequence is defined in READ_ORDER_SEQUENCE — single source of truth.
The human-readable layer map and step tables live in `policies/README.md`.
Run from repo root:  python policies/core/scripts/apply_read_order_navigation.py

Idempotent: strips prior <!-- policy-read-order-nav:* --> regions before re-inserting.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from _paths import POLICIES_ROOT, REPO_ROOT

# Single linear order: `core/` holds runbooks, launch, runtime, governance, and scripts (see policies/README.md).
READ_ORDER_SEQUENCE: tuple[str, ...] = (
    "core/security-first-setup.md",
    "core/firewall-exceptions-workflow.md",
    "core/unified-deployment-and-security.md",
    "core/deployment-handoff.md",
    "core/gateway-watchdog.md",
    "core/README.md",
    "core/agentic-company-deployment-pack.md",
    "core/global-agentic-company-deployment-policy.md",
    "README.md",
    "core/pipeline-runbook.md",
    "core/security-prompts.md",
    "core/chief-orchestrator-directive.md",
    "core/runtime/agent/BOOTSTRAP.md",
    "core/runtime/agent/AGENTS.md",
    "core/runtime/agent/IDENTITY.md",
    "core/runtime/agent/USER.md",
    "core/runtime/agent/SOUL.md",
    "core/runtime/agent/MEMORY.md",
    "core/runtime/agent/ORCHESTRATOR.md",
    "core/runtime/agent/SECURITY.md",
    "core/runtime/agent/RATE_LIMIT_POLICY.md",
    "core/runtime/agent/TOOLS.md",
    "core/runtime/agent/HEARTBEAT.md",
    "core/runtime/agent/README.md",
    "core/governance/standards/canonical-ai-agent-security-policy.md",
    "core/governance/standards/org-mapper-hr-policy.md",
    "core/governance/role-prompts/org-mapper-hr-controller.md",
    "core/governance/standards/functional-director-policy-template.md",
    "core/governance/role-prompts/functional-director-template.md",
    "core/governance/standards/project-lead-policy-template.md",
    "core/governance/role-prompts/project-lead-template.md",
    "core/governance/standards/supervisor-policy-template.md",
    "core/governance/role-prompts/supervisor-template.md",
    "core/governance/standards/worker-specialist-policy-template.md",
    "core/governance/role-prompts/worker-specialist-template.md",
    "core/governance/standards/board-of-directors-review-policy.md",
    "core/governance/role-prompts/board-of-directors-review.md",
    "core/governance/standards/task-state-and-evidence-policy.md",
    "core/governance/role-prompts/task-state-evidence-enforcer.md",
    "core/governance/standards/channel-architecture-policy.md",
    "core/governance/role-prompts/future-channel-architecture-planner.md",
    "core/governance/standards/client-deployment-policy.md",
    "core/governance/role-prompts/client-intake-deployment-template.md",
    "core/governance/standards/agent-lifecycle-org-hygiene-policy.md",
    "core/governance/role-prompts/agent-lifecycle-org-hygiene-controller.md",
    "core/governance/standards/agentic-company-template.md",
    "core/governance/role-prompts/markdown-playbook-generator.md",
    "core/governance/role-prompts/minimal-default-deployment-order.md",
    "core/governance/artifacts-and-archival-memory.md",
    "core/governance/generated/README.md",
    "core/governance/generated/by_role/README.md",
    "core/governance/generated/by_role/_TEMPLATE/README.md",
    "core/governance/generated/by_role/examples/README.md",
    "core/governance/generated/playbooks/slack-department-project-task-routing.md",
    "core/scripts/README.md",
    "INDEX.md",
)

_TOP_START = "<!-- policy-read-order-nav:top -->"
_TOP_END = "<!-- policy-read-order-nav:top-end -->"
_BOTTOM_START = "<!-- policy-read-order-nav:bottom -->"
_BOTTOM_END = "<!-- policy-read-order-nav:bottom-end -->"

_RE_TOP = re.compile(
    rf"{re.escape(_TOP_START)}.*?{re.escape(_TOP_END)}\s*",
    re.DOTALL,
)
_RE_BOTTOM = re.compile(
    rf"\s*{re.escape(_BOTTOM_START)}.*?{re.escape(_BOTTOM_END)}\s*",
    re.DOTALL,
)


def _rel_link(from_path: Path, to_path: Path) -> str:
    """POSIX relpath from the directory containing ``from_path`` to ``to_path``."""
    return os.path.relpath(to_path, from_path.parent).replace("\\", "/")


def _strip_nav(s: str) -> str:
    s = _RE_TOP.sub("", s)
    s = _RE_BOTTOM.sub("", s)
    return s.strip()


def _top_block(
    step: int,
    total: int,
    prev_rel: str | None,
    prev_label: str,
    read_order_rel: str,
) -> str:
    lines = [
        _TOP_START,
        "> **Governance read order** — step "
        f"{step} of {total} in the canonical `policies/` sequence (layer map & tables: [`README.md`]({read_order_rel})).",
    ]
    if prev_rel is None:
        lines.append(
            "> **Before this file:** none — this is the **first** document in the sequence. Do not treat later policy files as valid context until this one is understood."
        )
    else:
        lines.append(
            f"> **Before this file:** read [{prev_label}]({prev_rel}) and everything earlier in that sequence. **Do not** interpret this document as authoritative until those prerequisites are satisfied."
        )
    lines.append(
        "> **This file:** safe to apply only after the prerequisite above (if any) is complete."
    )
    lines.append(_TOP_END)
    return "\n".join(lines) + "\n\n"


def _bottom_block(
    step: int,
    total: int,
    next_rel: str | None,
    next_label: str,
    from_path: Path,
) -> str:
    lines = [_BOTTOM_START]
    if next_rel is None:
        ops_link = _rel_link(from_path, REPO_ROOT / "operations")
        ro_link = _rel_link(from_path, POLICIES_ROOT / "README.md")
        lines.append(
            "> **Next step:** end of the canonical `policies/*.md` sequence for this repository snapshot. "
            f"Use operational registers under [`operations/`]({ops_link}) and "
            f"[`README.md`]({ro_link}) (generated output & operations) for runtime memory and project trees."
        )
    else:
        lines.append(
            f"> **Next step:** continue to [{next_label}]({next_rel}) after this file is fully read and applied. "
            "Do not skip ahead unless a human operator explicitly directs a narrower scope."
        )
    lines.append(_BOTTOM_END)
    return "\n\n" + "\n".join(lines) + "\n"


def apply_to_file(rel: str, sequence: list[str], total: int) -> str | None:
    path = POLICIES_ROOT / rel
    if not path.is_file():
        return f"missing: {rel}"
    step = sequence.index(rel) + 1
    prev_rel_s: str | None = None
    prev_label = ""
    if step > 1:
        prev = sequence[step - 2]
        prev_label = prev  # full path under policies/ (disambiguates README.md, etc.)
        prev_rel_s = _rel_link(path, POLICIES_ROOT / prev)
    next_rel_s: str | None = None
    next_label = ""
    if step < total:
        nxt = sequence[step]
        next_label = nxt
        next_rel_s = _rel_link(path, POLICIES_ROOT / nxt)

    body = _strip_nav(path.read_text(encoding="utf-8"))
    read_order_rel = _rel_link(path, POLICIES_ROOT / "README.md")
    top = _top_block(step, total, prev_rel_s, prev_label, read_order_rel)
    bottom = _bottom_block(step, total, next_rel_s, next_label, path)
    path.write_text(top + body + bottom, encoding="utf-8")
    return None


def main() -> int:
    md_files = sorted(
        (
            p.relative_to(POLICIES_ROOT).as_posix()
            for p in POLICIES_ROOT.rglob("*.md")
            if not p.name.startswith("._")
        ),
        key=lambda s: s.lower(),
    )
    seq = list(READ_ORDER_SEQUENCE)
    if set(seq) != set(md_files):
        missing = sorted(set(md_files) - set(seq))
        extra = sorted(set(seq) - set(md_files))
        print("apply_read_order_navigation: SEQUENCE mismatch", file=sys.stderr)
        if missing:
            print("  missing from SEQUENCE:", missing, file=sys.stderr)
        if extra:
            print("  extra in SEQUENCE:", extra, file=sys.stderr)
        return 1
    if len(seq) != len(md_files):
        print("apply_read_order_navigation: duplicate entries in SEQUENCE", file=sys.stderr)
        return 1

    total = len(seq)
    errs: list[str] = []
    for rel in seq:
        err = apply_to_file(rel, seq, total)
        if err:
            errs.append(err)
    if errs:
        for e in errs:
            print(e, file=sys.stderr)
        return 1
    print(f"apply_read_order_navigation: OK — {total} files updated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
