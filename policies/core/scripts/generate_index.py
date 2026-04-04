#!/usr/bin/env python3
"""Regenerate policies/INDEX.md — list all markdown files under policies/.

After a successful write, run ``apply_read_order_navigation.py`` (or ``start_pipeline.py``)
so INDEX.md regains top/bottom read-order navigation blocks.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from _paths import POLICIES_ROOT, REPO_ROOT

INDEX = POLICIES_ROOT / "INDEX.md"


def run_generate_index() -> tuple[int, str | None]:
    try:
        md_files = sorted(
            (p for p in POLICIES_ROOT.rglob("*.md") if not p.name.startswith("._")),
            key=lambda p: str(p.relative_to(POLICIES_ROOT)).lower(),
        )
        lines = [
            "# Policies — file index (generated)",
            "",
            "Regenerate with: `python policies/core/scripts/generate_index.py` or `python policies/core/scripts/start_pipeline.py`",
            "",
            "Paths are relative to the repository root.",
            "",
        ]
        count = 0
        for p in md_files:
            if p.name == "INDEX.md" and p.parent == POLICIES_ROOT:
                continue
            rel = p.relative_to(REPO_ROOT)
            lines.append(f"- `{rel}`")
            count += 1
        lines.append(f"- `{INDEX.relative_to(REPO_ROOT)}` (this file)")
        lines.append("")
        INDEX.write_text("\n".join(lines), encoding="utf-8")
        msg = f"Wrote {INDEX.relative_to(REPO_ROOT)} ({count} policy-tree markdown files)"
        return 0, msg
    except OSError as e:
        return 1, str(e)


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate policies/INDEX.md")
    ap.add_argument("--dry-run", action="store_true", help="Print count only; do not write INDEX.md")
    args = ap.parse_args()
    if args.dry_run:
        md_files = [
            p
            for p in POLICIES_ROOT.rglob("*.md")
            if not p.name.startswith("._")
            and not (p.name == "INDEX.md" and p.parent == POLICIES_ROOT)
        ]
        print(f"generate_index: dry-run — would index {len(md_files)} files")
        return 0
    code, msg = run_generate_index()
    if code != 0:
        print(f"generate_index: FAILED: {msg}", file=sys.stderr)
        return 1
    print(msg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
