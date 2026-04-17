#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import importlib.util


ROOT_ANCHORS = [
    "AGENTS.md",
    "MEMORY.md",
    "USER.md",
    "ATTENTION.md",
    "INDEX.md",
    "COMPASS.md",
    "STATE.md",
    "TOOLS.md",
    "SKILLS.md",
    "BOOTSTRAP.md",
    "SOUL.md",
    "README.md",
]

LEGACY_TOP_DIRS = [
    "actors",
    "core",
    "governance",
    "knowledge",
    "runtime",
    "skills",
]


@dataclass(frozen=True)
class MappingRow:
    old_path: str
    new_path: str
    layer: str
    residency: str  # always-loaded | selective | archived
    note: str


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _list_files(root: Path) -> list[str]:
    if not root.exists():
        return []
    out: list[str] = []
    for p in sorted(root.rglob("*")):
        if p.is_file():
            out.append(str(p.resolve()))
    return out


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _safe_move(src: Path, dst: Path) -> None:
    _ensure_dir(dst.parent)
    if not src.exists():
        return
    if dst.exists():
        raise RuntimeError(f"Refusing to overwrite existing path: {dst}")
    shutil.move(str(src), str(dst))


def _safe_copytree(src: Path, dst: Path) -> None:
    if not src.exists():
        return
    if dst.exists():
        return
    _ensure_dir(dst.parent)
    shutil.copytree(src, dst, dirs_exist_ok=False)


def _safe_copy2(src: Path, dst: Path) -> None:
    if not src.exists():
        return
    if dst.exists():
        return
    _ensure_dir(dst.parent)
    shutil.copy2(src, dst)


def _write_text(path: Path, content: str) -> None:
    _ensure_dir(path.parent)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def _append_infra(
    infra_path: Path,
    *,
    pre_inventory: list[str],
    post_inventory: list[str],
    mappings: list[MappingRow],
    stamp: str,
) -> None:
    mapping_lines = [
        "| old path | new path | layer | residency | note |",
        "|---|---|---|---|---|",
    ]
    for row in mappings:
        mapping_lines.append(
            f"| `{row.old_path}` | `{row.new_path}` | `{row.layer}` | `{row.residency}` | {row.note} |"
        )

    body = f"""# Cortical Lattice Memory — Infrastructure

> Generated/updated by `migrate_workspace_memory_to_cortical_lattice.py` at `{stamp}` (UTC).

## A) Current system inventory (pre-migration; absolute paths)

```text
{chr(10).join(pre_inventory)}
```

## B) New system inventory (post-migration; absolute paths)

```text
{chr(10).join(post_inventory)}
```

## C) File-to-layer mapping (path → new path)

{chr(10).join(mapping_lines)}

## D) Hermes wiring map (what is loaded by default vs selectively)

- **Always-loaded root anchors** (small): `AGENTS.md`, `MEMORY.md`, `USER.md`, `ATTENTION.md`, `INDEX.md` under `HERMES_HOME/workspace/memory/`
- **Optional root extras** (env `HERMES_WORKSPACE_MEMORY_EXTRAS`): `STATE.md`, `TOOLS.md`, `SKILLS.md`, `BOOTSTRAP.md`
- **Identity**: `SOUL.md` prefers `HERMES_HOME/workspace/memory/SOUL.md`
- **Deep map** (on-demand): `INFRASTRUCTURE.md`

Runtime code pointers:
- `agent/prompt_builder.py` — loads workspace memory anchors
- `run_agent.py` — retrieval + writeback orchestration (Cortical Lattice integration)
- `tools/memory_tool.py` — built-in persistent `memories/{{MEMORY,USER}}.md` (compact)
- `hermes_cli/config.py` — feature flags / config for memory compiler/planner

## E) Diagrams

### System flow (ASCII)

```text
+----------------------+           +--------------------------------------+
| constitution/        |           | retrieval_planner + memory_compiler   |
| (pinned, stable)     |<--------->| (per-turn, selective, prompt-efficient)|
+----------+-----------+           +-------------------+------------------+
           |                                               |
           | always-loaded                                  | emits ephemeral pack
           v                                               v
+----------------------+                          +----------------------+
| root anchors         |                          | working-memory/      |
| AGENTS/MEMORY/USER   |                          | typed pages +        |
| ATTENTION/INDEX      |                          | context-pack mirror  |
+----------------------+                          +----------+-----------+
                                                          |
                                                          | writeback + promotion candidates
                                                          v
     +-------------------+   +-------------------+   +-------------------+
     | episodic-ledger/  |   | semantic-graph/   |   | hazard-memory/    |
     | traces, episodes  |   | entities/relations|   | anti-patterns     |
     +---------+---------+   +---------+---------+   +---------+---------+
               |                       |                       |
               v                       v                       v
          +----+-----------------------+-----------------------+----+
          | case-memory/  <-->  skill-atlas/  <-->  doctrine/       |
          +--------------------------------------------------------+

Observability feedstock (optional):
- LangSmith traces → observability/ + episodic-ledger/
```

### File mapping (ASCII)

```text
Before (legacy workspace/memory root)
  AGENTS.md, MEMORY.md, USER.md, ATTENTION.md, INDEX.md, ...
  actors/ core/ governance/ knowledge/ runtime/ skills/

After (Cortical Lattice workspace/memory root)
  Root anchors (small): AGENTS.md, MEMORY.md, USER.md, ATTENTION.md, INDEX.md, ...
  Layers: constitution/ working-memory/ episodic-ledger/ semantic-graph/ case-memory/
          skill-atlas/ reflective-doctrine/ prospective-memory/ hazard-memory/
          social-role-memory/ observability/ indexes/ bootstrap/
  Archive: legacy-archive/pre-cortical-{stamp}/ (full pre-migration snapshot)
```
"""

    _write_text(infra_path, body)


def main() -> int:
    ap = argparse.ArgumentParser(description="Migrate $HERMES_HOME/workspace/memory to Cortical Lattice Memory (non-destructive; archives legacy tree).")
    ap.add_argument("--hermes-home", required=True, help="Profile HERMES_HOME (e.g. ~/.hermes/profiles/chief-orchestrator).")
    ap.add_argument("--no-copy", action="store_true", help="Archive legacy tree but do not copy curated subsets into new layers.")
    ap.add_argument("--stamp", default="", help="Override UTC stamp (testing).")
    args = ap.parse_args()

    hermes_home = Path(args.hermes_home).expanduser().resolve()
    mem_root = hermes_home / "workspace" / "memory"
    if not mem_root.exists():
        raise SystemExit(f"missing workspace/memory: {mem_root}")

    stamp = args.stamp.strip() or _utc_stamp()

    already_migrated = (mem_root / "CORTICAL_LATTICE_MEMORY.md").is_file()

    # --- Pre-inventory (exact absolute paths)
    pre_inventory = []
    pre_inventory.extend(_list_files(mem_root))
    pre_inventory.extend(_list_files(hermes_home / "memories"))
    pre_inventory.extend(_list_files(hermes_home / "sessions"))
    pre_inventory.extend(_list_files(hermes_home / "runtime"))
    pre_inventory = sorted(dict.fromkeys(pre_inventory))

    # --- Determine legacy archive root
    legacy_archive_dir = mem_root / "legacy-archive"
    _ensure_dir(legacy_archive_dir)

    def _latest_pre_cortical() -> Path | None:
        try:
            cands = [p for p in legacy_archive_dir.glob("pre-cortical-*") if p.is_dir()]
            if not cands:
                return None
            return sorted(cands, key=lambda p: p.name)[-1]
        except Exception:
            return None

    archive_root: Path
    if already_migrated:
        # Idempotent rerun: do NOT move/overwrite current cortex tree.
        # Use the most recent archive as the legacy source for wiring/mapping.
        _latest = _latest_pre_cortical()
        archive_root = _latest or (legacy_archive_dir / f"pre-cortical-{stamp}")
        _ensure_dir(archive_root)
    else:
        archive_root = legacy_archive_dir / f"pre-cortical-{stamp}"
        _ensure_dir(archive_root)

    mappings: list[MappingRow] = []

    if not already_migrated:
        # Move legacy top-level dirs into archive (if present)
        for d in LEGACY_TOP_DIRS:
            src = mem_root / d
            if src.exists():
                dst = archive_root / d
                _safe_move(src, dst)
                mappings.append(
                    MappingRow(
                        old_path=str(src),
                        new_path=str(dst),
                        layer="legacy-archive",
                        residency="archived",
                        note="Archived whole legacy subtree before creating Cortical layers.",
                    )
                )

        # Move existing root anchors into archive (if present)
        for name in ROOT_ANCHORS:
            src = mem_root / name
            if src.exists():
                dst = archive_root / "root-anchors" / name
                _safe_move(src, dst)
                mappings.append(
                    MappingRow(
                        old_path=str(src),
                        new_path=str(dst),
                        layer="legacy-archive",
                        residency="archived",
                        note="Archived prior root anchor before replacing with Cortical stub.",
                    )
                )

    # Ensure scaffold exists by importing the scaffold script from the repo if available.
    # We load the known scaffolder script that ships next to this file.
    scaffold_path = Path(__file__).resolve().parent / "scaffold_cortical_lattice_memory_tree.py"
    if scaffold_path.is_file():
        spec = importlib.util.spec_from_file_location("_cortical_scaffold", scaffold_path)
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            # Ensure dataclasses (and similar) can resolve cls.__module__ via sys.modules.
            sys.modules[spec.name] = mod
            spec.loader.exec_module(mod)  # type: ignore[union-attr]
            try:
                mod.scaffold(mem_root)  # type: ignore[attr-defined]
            except Exception as e:
                raise SystemExit(f"scaffold failed: {e}")
    for layer in [
        "constitution",
        "working-memory",
        "episodic-ledger",
        "semantic-graph",
        "case-memory",
        "skill-atlas",
        "reflective-doctrine",
        "prospective-memory",
        "hazard-memory",
        "social-role-memory",
        "observability",
        "indexes",
        "bootstrap",
        "legacy-archive",
    ]:
        _ensure_dir(mem_root / layer)

    # Minimal bridge note for humans/agents finding the archive.
    _write_text(
        mem_root / "indexes" / "legacy-bridges.md",
        f"""# legacy-bridges

Legacy workspace memory content was archived at:

- `{archive_root}`

Use `INFRASTRUCTURE.md` for the authoritative pre/post inventories and mapping table.
""",
    )

    # Curated copy-back from archived legacy tree into new layers (non-destructive to archive)
    if not args.no_copy:
        legacy = archive_root

        def _map_copy(old: Path, new: Path, layer: str, note: str) -> None:
            mappings.append(
                MappingRow(
                    old_path=str(old),
                    new_path=str(new),
                    layer=layer,
                    residency="selective",
                    note=note,
                )
            )

        # Working memory: runtime/state/*
        src = legacy / "runtime" / "state"
        dst = mem_root / "working-memory" / "_legacy_runtime_state"
        _safe_copytree(src, dst)
        if src.exists():
            _map_copy(src, dst, "working-memory", "Legacy working-state mirror (runtime/state) for selective reference.")
        if (legacy / "runtime" / "state" / "current-focus.md").exists():
            src_cf = legacy / "runtime" / "state" / "current-focus.md"
            dst_cf = mem_root / "working-memory" / "_legacy_current-focus.md"
            _safe_copy2(src_cf, dst_cf)
            mappings.append(
                MappingRow(
                    old_path=str(src_cf),
                    new_path=str(dst_cf),
                    layer="working-memory",
                    residency="selective",
                    note="Seed working memory from legacy runtime/state (kept as legacy mirror until normalized).",
                )
            )

        # Skill atlas: runtime/tasks/procedures and workspace skills
        src = legacy / "runtime" / "tasks" / "procedures"
        dst = mem_root / "skill-atlas" / "references" / "legacy-procedures"
        _safe_copytree(src, dst)
        if src.exists():
            _map_copy(src, dst, "skill-atlas", "Legacy procedures mirror (runtime/tasks/procedures) for future promotion into skills.")

        src = legacy / "skills"
        dst = mem_root / "skill-atlas" / "legacy-workspace-skills"
        _safe_copytree(src, dst)
        if src.exists():
            _map_copy(src, dst, "skill-atlas", "Legacy workspace skills mirror (pre-migration workspace/memory/skills).")

        # Observability / episodic: sessions and runtime/logs are outside workspace/memory;
        # we mirror pointers only (infra inventory captures them as canonical evidence).

        # Social/role: actors/persona
        src = legacy / "actors" / "persona"
        dst = mem_root / "social-role-memory" / "persona" / "legacy-persona"
        _safe_copytree(src, dst)
        if src.exists():
            _map_copy(src, dst, "social-role-memory", "Legacy persona mirror (actors/persona).")

        # Semantic graph mirrors: knowledge/*
        src = legacy / "knowledge"
        dst = mem_root / "semantic-graph" / "graph-mirror" / "legacy-knowledge"
        _safe_copytree(src, dst)
        if src.exists():
            _map_copy(src, dst, "semantic-graph", "Legacy knowledge mirror for semantic graph scaffolding and future Zep sync.")

        # Doctrine: governance/*
        src = legacy / "governance"
        dst = mem_root / "reflective-doctrine" / "legacy-governance"
        _safe_copytree(src, dst)
        if src.exists():
            _map_copy(src, dst, "reflective-doctrine", "Legacy governance/doctrine mirror (pre-migration governance subtree).")

        # Bootstrap: runtime/tasks/templates
        src = legacy / "runtime" / "tasks" / "templates"
        dst = mem_root / "bootstrap" / "templates" / "legacy-templates"
        _safe_copytree(src, dst)
        if src.exists():
            _map_copy(src, dst, "bootstrap", "Legacy templates mirror (runtime/tasks/templates).")

        # Core: canonical paths doc, etc.
        src = legacy / "core"
        dst = mem_root / "indexes" / "legacy-core"
        _safe_copytree(src, dst)
        if src.exists():
            _map_copy(src, dst, "indexes", "Legacy core/index material mirror (pre-migration core subtree).")

    # Write/refresh INFRASTRUCTURE.md after the archive + copyback
    infra_path = mem_root / "INFRASTRUCTURE.md"

    post_inventory = []
    post_inventory.extend(_list_files(mem_root))
    post_inventory.extend(_list_files(hermes_home / "memories"))
    post_inventory.extend(_list_files(hermes_home / "sessions"))
    post_inventory.extend(_list_files(hermes_home / "runtime"))
    post_inventory = sorted(dict.fromkeys(post_inventory))

    _append_infra(
        infra_path,
        pre_inventory=pre_inventory,
        post_inventory=post_inventory,
        mappings=mappings,
        stamp=stamp,
    )

    # Emit a small machine-readable receipt for automation
    receipt = {
        "ok": True,
        "stamp": stamp,
        "hermes_home": str(hermes_home),
        "memory_root": str(mem_root),
        "archive_root": str(archive_root),
        "mappings_count": len(mappings),
        "pre_inventory_files": len(pre_inventory),
        "post_inventory_files": len(post_inventory),
    }
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

