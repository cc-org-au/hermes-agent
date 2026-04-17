#!/usr/bin/env python3
"""Promote ``skill-atlas/procedures/**/*.md`` into Cursor-style ``SKILL.md`` skill bundles.

Writes ``skill-atlas/promoted-skills/<slug>/SKILL.md`` with YAML frontmatter plus the
procedure body and a provenance link. Idempotent: skips if SKILL.md already exists
unless ``--force``.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from cortical_lattice_classify import first_markdown_heading, first_paragraph_excerpt  # noqa: E402


def _slug(name: str) -> str:
    s = name.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-") or "procedure"


def _yaml_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def promote(mem_root: Path, *, force: bool = False, dry_run: bool = False) -> dict[str, str | int]:
    proc_root = mem_root / "skill-atlas" / "procedures"
    out_root = mem_root / "skill-atlas" / "promoted-skills"
    if not proc_root.is_dir():
        return {"ok": True, "written": 0, "note": "no procedures tree"}

    written = 0
    for md in sorted(proc_root.rglob("*.md")):
        rel = md.relative_to(proc_root)
        slug = _slug(rel.with_suffix("").as_posix().replace("/", "-"))
        dest_dir = out_root / slug
        dest = dest_dir / "SKILL.md"
        if dest.exists() and not force:
            continue
        body = md.read_text(encoding="utf-8", errors="replace")
        title = first_markdown_heading(body)
        desc = first_paragraph_excerpt(body, max_len=320)
        front = (
            "---\n"
            f'name: {_yaml_escape(slug)}\n'
            f'description: "{_yaml_escape(desc)}"\n'
            "---\n\n"
        )
        block = (
            f"# {title}\n\n"
            f"**Source procedure:** `{md.relative_to(mem_root)}`\n\n"
            "---\n\n"
            f"{body.strip()}\n"
        )
        content = front + block
        if not dry_run:
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest.write_text(content.rstrip() + "\n", encoding="utf-8")
        written += 1

    return {"ok": True, "written": written, "out_root": str(out_root)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Promote procedures to SKILL.md skill bundles.")
    ap.add_argument("--hermes-home", required=True, help="Profile HERMES_HOME (…/profiles/<name>)")
    ap.add_argument("--force", action="store_true", help="Overwrite existing SKILL.md files.")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    hermes = Path(args.hermes_home).expanduser().resolve()
    mem_root = hermes / "workspace" / "memory"
    if not mem_root.is_dir():
        print(f"missing {mem_root}", file=sys.stderr)
        return 2

    r = promote(mem_root, force=args.force, dry_run=args.dry_run)
    print(r)
    return 0 if r.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
