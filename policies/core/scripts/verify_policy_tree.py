#!/usr/bin/env python3
"""Verify required folders, anchor files, and (strict) activation cues in core/governance/standards/*.md."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from _paths import POLICIES_ROOT, REPO_ROOT

CORE = POLICIES_ROOT / "core"

REQUIRED_DIRS = [
    CORE,
    CORE / "runtime",
    CORE / "runtime" / "agent",
    CORE / "governance",
    CORE / "governance" / "standards",
    CORE / "governance" / "role-prompts",
    CORE / "governance" / "generated",
    CORE / "governance" / "generated" / "by_role",
    CORE / "scripts",
]

REQUIRED_FILES = [
    POLICIES_ROOT / "README.md",
    CORE / "governance" / "artifacts-and-archival-memory.md",
    CORE / "security-first-setup.md",
    CORE / "unified-deployment-and-security.md",
    CORE / "deployment-handoff.md",
    CORE / "agentic-company-deployment-pack.md",
    CORE / "pipeline-runbook.md",
    CORE / "governance" / "standards" / "canonical-ai-agent-security-policy.md",
    CORE / "security-prompts.md",
    CORE / "runtime" / "agent" / "AGENTS.md",
    CORE / "governance" / "generated" / "README.md",
    CORE / "governance" / "generated" / "by_role" / "README.md",
]

ACTIVATION_MARKERS = (
    "## Activation prompt (role reminder)",
    "## Activation prompt",
)


def verify_activation_cues(strict: bool) -> list[str]:
    """Ensure each standards policy links its prompt (prevents empty/stub policies passing)."""
    if not strict:
        return []
    std = CORE / "governance" / "standards"
    if not std.is_dir():
        return [f"missing directory: {std.relative_to(REPO_ROOT)}"]
    errors: list[str] = []
    for path in sorted(std.glob("*.md")):
        if path.name.startswith("._"):
            continue  # AppleDouble sidecar files must not masquerade as policies
        text = path.read_text(encoding="utf-8")
        if not any(m in text for m in ACTIVATION_MARKERS):
            errors.append(
                f"standards policy missing activation cue: {path.relative_to(REPO_ROOT)} "
                f"(expected heading like '{ACTIVATION_MARKERS[0]}')",
            )
    return errors


def verify_tree(strict_activation: bool = True) -> tuple[int, list[str]]:
    missing: list[str] = []
    for d in REQUIRED_DIRS:
        if not d.is_dir():
            missing.append(f"missing dir: {d.relative_to(REPO_ROOT)}")
    for f in REQUIRED_FILES:
        if not f.is_file():
            missing.append(f"missing file: {f.relative_to(REPO_ROOT)}")
    missing.extend(verify_activation_cues(strict_activation))
    if missing:
        return 1, missing
    return 0, []


def main() -> int:
    ap = argparse.ArgumentParser(description="Verify agentic company policy tree layout and activation cues.")
    ap.add_argument(
        "--no-strict",
        action="store_true",
        help="Skip activation-cue checks on policies/core/governance/standards/*.md (not recommended for deployment).",
    )
    args = ap.parse_args()
    code, errs = verify_tree(strict_activation=not args.no_strict)
    if code != 0:
        print("verify_policy_tree: FAILED", file=sys.stderr)
        for m in errs:
            print(" ", m, file=sys.stderr)
        return 1
    print("verify_policy_tree: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
