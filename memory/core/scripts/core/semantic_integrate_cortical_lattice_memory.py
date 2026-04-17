#!/usr/bin/env python3
"""Semantic re-integration of pre-Cortical workspace memory into Cortical Lattice layers.

This script treats archived / mirrored legacy trees as *source material* and
redistributes Markdown (and selected companion files) into the active layer
directories under ``HERMES_HOME/workspace/memory/``.

It is intentionally conservative about deletion: by default it does not remove
the pre-cortical archive tree; use ``--prune-legacy-mirrors`` only after review.

Outputs:
- ``workspace/memory/MIGRATION_MAP.md`` — human-readable map
- ``workspace/memory/migration_manifest.jsonl`` — machine-readable one record per file
- Refreshed per-layer ``MANIFEST.md`` stubs that describe *populated* layout

Classification:
- Path-based rules first; then YAML frontmatter (``memory_layer``, ``cortical_layer``, …) and
  keyword heuristics for ``misc-import`` (see ``cortical_lattice_classify.py``).

Root anchors:
- Prior anchor bodies are embedded in full by default (``--root-anchor-max-chars 0``).

Optional:
- ``--promote-procedure-skills`` runs ``promote_procedure_skills.py`` to emit ``SKILL.md`` bundles.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from cortical_lattice_classify import (  # noqa: E402
    ClassifyResult,
    refine_classification,
)


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_text(path: Path, limit: int | None = None) -> str:
    try:
        data = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    if limit is not None:
        return data[:limit]
    return data


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def _append_jsonl(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def _iter_markdown_files(root: Path) -> Iterator[Path]:
    if not root.exists():
        return
    for p in sorted(root.rglob("*")):
        if p.is_file() and p.suffix.lower() in {".md", ".mdc"}:
            yield p


def _strip_prefix(rel: str, prefix: str) -> Path:
    r = rel if not rel.startswith("./") else rel[2:]
    pfx = prefix if prefix.endswith("/") else prefix + "/"
    if r.lower().startswith(pfx.lower()):
        return Path(r[len(pfx) :])
    return Path(r)


def classify_path(mem_root: Path, source_root: Path, path: Path) -> ClassifyResult:
    """Classify primarily by legacy semantic location (path), not filename alone."""
    try:
        rel = path.relative_to(source_root).as_posix()
    except ValueError:
        rel = path.name
    low = rel.lower()
    parts = low.split("/")
    root_name = source_root.name.lower()

    # Mirror: graph-mirror/legacy-knowledge/** may omit the top-level ``knowledge/`` segment
    if root_name == "legacy-knowledge" and not low.startswith("knowledge/"):
        rel = f"knowledge/{rel}"
        low = rel.lower()
        parts = low.split("/")

    # Mirror: legacy-persona/*.md
    if root_name == "legacy-persona":
        return ClassifyResult(
            "social-role-memory",
            mem_root / "social-role-memory" / "persona" / path.name,
            "persona",
            "Persona mirror integrated as active social-role memory (not archived).",
        )

    # Root anchors (captured under root-anchors/)
    if "root-anchors" in parts:
        return ClassifyResult(
            "indexes",
            mem_root / "indexes" / "root-anchors-source" / path.name,
            "root-anchor-source",
            "Original root anchor preserved for merge into live anchors.",
        )

    # Persona / role / orchestration
    if low.startswith("actors/persona/"):
        tail = _strip_prefix(rel, "actors/persona/")
        return ClassifyResult(
            "social-role-memory",
            mem_root / "social-role-memory" / "persona" / tail,
            "persona",
            "Operator/user/soul/tools/heartbeat and related persona material.",
        )
    if low.startswith("actors/registry/"):
        tail = _strip_prefix(rel, "actors/registry/")
        return ClassifyResult(
            "social-role-memory",
            mem_root / "social-role-memory" / "registry" / tail,
            "role-registry",
            "Org / role / project-lead style registers.",
        )
    if low.startswith("actors/orchestration/"):
        tail = _strip_prefix(rel, "actors/orchestration/")
        return ClassifyResult(
            "social-role-memory",
            mem_root / "social-role-memory" / "orchestration" / tail,
            "orchestration",
            "Orchestration playbooks and bridges.",
        )

    # Changelog / dated governance narrative → episodic (still keep doctrine copy via governance path below if needed)
    if "changelog" in low or "governance-changelog" in low:
        tail = Path(rel)
        return ClassifyResult(
            "episodic-ledger",
            mem_root / "episodic-ledger" / "chronology" / tail,
            "governance-chronology",
            "Time-ordered governance / operational narrative (episodic).",
        )

    # Incident / remediation playbooks → case memory (reusable patterns) + hazard overlap handled by filename rules in operations

    # Knowledge → semantic graph (preserve subtree shape under knowledge/)
    if low.startswith("knowledge/"):
        tail = _strip_prefix(rel, "knowledge/")
        return ClassifyResult(
            "semantic-graph",
            mem_root / "semantic-graph" / "knowledge" / tail,
            "semantic-knowledge",
            "Concept / domain / reference / foundation material (stable truths).",
        )

    # Governance → doctrine (preserve full subtree under governance/ for navigability)
    if low.startswith("governance/"):
        tail = _strip_prefix(rel, "governance/")
        return ClassifyResult(
            "reflective-doctrine",
            mem_root / "reflective-doctrine" / "governance" / tail,
            "doctrine-governance",
            "Generalized governance / doctrine (standards, protocols, prompts).",
        )

    # Runtime state → working memory (live)
    if low.startswith("runtime/state/"):
        tail = _strip_prefix(rel, "runtime/state/")
        return ClassifyResult(
            "working-memory",
            mem_root / "working-memory" / "runtime-state" / tail,
            "working-runtime-state",
            "Active / near-active runtime state (focus, baseline, overrides).",
        )

    # Runtime operations (registers, audits, queues) → observability + selective hazard/prospective
    if low.startswith("runtime/operations/"):
        low_name = path.name.lower()
        tail = _strip_prefix(rel, "runtime/operations/")
        if any(k in low_name for k in ("remediation", "incident", "audit", "security", "failure", "hazard")):
            layer = "hazard-memory"
            base = mem_root / "hazard-memory" / "operations"
        elif any(k in low_name for k in ("queue", "pending", "open", "follow", "deadline")):
            layer = "prospective-memory"
            base = mem_root / "prospective-memory" / "operations"
        else:
            layer = "observability"
            base = mem_root / "observability" / "operations"
        return ClassifyResult(layer, base / tail, "runtime-operations", "Operational registers / audits / traces.")

    # Case-like playbooks under runtime (pattern/solution histories)
    if low.startswith("runtime/") and any(k in low for k in ("incident", "remediation", "postmortem", "rca")):
        tail = _strip_prefix(rel, "runtime/")
        return ClassifyResult(
            "case-memory",
            mem_root / "case-memory" / "cases" / tail,
            "case-record",
            "Reusable operational case material derived from runtime narratives.",
        )

    # Procedures → skill atlas (canonical procedures tree)
    if low.startswith("runtime/tasks/procedures/"):
        tail = _strip_prefix(rel, "runtime/tasks/procedures/")
        return ClassifyResult(
            "skill-atlas",
            mem_root / "skill-atlas" / "procedures" / tail,
            "procedure",
            "Repeatable operational procedures (skill promotion candidates).",
        )

    # Templates / scripts / init under runtime/tasks or core/init → bootstrap
    if low.startswith("runtime/tasks/templates/"):
        tail = _strip_prefix(rel, "runtime/tasks/templates/")
        return ClassifyResult(
            "bootstrap",
            mem_root / "bootstrap" / "templates" / tail,
            "bootstrap-template",
            "Templates and reproducible bootstrap artifacts.",
        )
    if low.startswith("core/init/"):
        tail = _strip_prefix(rel, "core/init/")
        return ClassifyResult(
            "bootstrap",
            mem_root / "bootstrap" / "core" / "init" / tail,
            "bootstrap-core",
            "Initialization / pipeline / security-first material from core/init.",
        )

    # core/scripts → bootstrap/scripts (operational reproducibility)
    if low.startswith("core/scripts/"):
        tail = _strip_prefix(rel, "core/scripts/")
        return ClassifyResult(
            "bootstrap",
            mem_root / "bootstrap" / "scripts" / tail,
            "bootstrap-scripts",
            "Policy / operator scripts shipped with memory (executable reproducibility).",
        )

    # Workspace-local skills → skill-atlas/workspace-skills
    if low.startswith("skills/"):
        tail = _strip_prefix(rel, "skills/")
        return ClassifyResult(
            "skill-atlas",
            mem_root / "skill-atlas" / "workspace-skills" / tail,
            "workspace-skill",
            "Hermes workspace skills (pre-migration skills/).",
        )

    # Default: episodic ledger for anything else markdown under runtime or core
    if low.startswith("runtime/") or low.startswith("core/"):
        tail = Path(rel)
        return ClassifyResult(
            "episodic-ledger",
            mem_root / "episodic-ledger" / "imported" / tail,
            "episodic-import",
            "Chronological / narrative operational material (default bucket).",
        )

    # Fallback
    tail = Path(rel)
    return ClassifyResult(
        "semantic-graph",
        mem_root / "semantic-graph" / "misc-import" / tail,
        "misc",
        "Unclassified markdown; placed under semantic misc-import for manual re-triage.",
    )


def _body_effectively_present(existing: str, body: str) -> bool:
    """Avoid merge-append bloat when the same substantive body is already in the destination."""
    b = (body or "").strip()
    if not b:
        return True
    chunk = b[:12000] if len(b) > 12000 else b
    return chunk in existing


def _provenance_header(*, source: Path, role: str, note: str) -> str:
    src = str(source.resolve())
    return (
        f"<!-- cortical-lattice-migrated: {_utc_iso()} -->\n"
        f"<!-- source-path: {src} -->\n"
        f"<!-- semantic-role: {role} -->\n"
        f"<!-- migration-note: {note} -->\n\n"
    )


def _maybe_truncate_section(s: str, max_chars: int) -> str:
    """If ``max_chars`` is 0, return full text; otherwise cap with a visible marker."""
    s = (s or "").strip()
    if max_chars <= 0 or len(s) <= max_chars:
        return s
    return s[:max_chars] + "\n\n[... truncated: use --root-anchor-max-chars 0 for full text ...]\n"


def _merge_root_anchors(mem_root: Path, roots_dir: Path, *, max_chars_per_section: int = 0) -> None:
    """Rebuild live root anchors from archived root-anchors/*.md.

    Default ``max_chars_per_section=0`` embeds prior-anchor bodies **in full** (no lossy excerpting).
    """
    if not roots_dir.is_dir():
        return

    def load(name: str) -> str:
        p = roots_dir / name
        return _read_text(p) if p.is_file() else ""

    def sec(title: str, content: str) -> str:
        return f"## {title}\n\n{_maybe_truncate_section(content, max_chars_per_section)}\n"

    old_agents = load("AGENTS.md")
    old_memory = load("MEMORY.md")
    old_user = load("USER.md")
    old_attention = load("ATTENTION.md")
    old_index = load("INDEX.md")
    old_compass = load("COMPASS.md")
    old_readme = load("README.md")

    ag = f"""# AGENTS.md (workspace/memory)

## Cortical Lattice — live routing

This file was **rebuilt** from the pre-Cortical root anchors (see ``indexes/root-anchors-source/`` for byte-identical copies) and routes the agent through the lattice:

- **Constitution (pinned rules):** ``constitution/CONSTITUTION.md`` + ``constitution/routing.md``
- **Semantic knowledge:** ``semantic-graph/knowledge/`` (concepts, domains, references)
- **Doctrine / governance:** ``reflective-doctrine/governance/``
- **Persona / org memory:** ``social-role-memory/``
- **Working state:** ``working-memory/``
- **Procedures / skills:** ``skill-atlas/procedures/``, ``skill-atlas/promoted-skills/``, ``skill-atlas/workspace-skills/``
- **Episodic imports:** ``episodic-ledger/imported/`` (chronological material pending promotion)
- **Observability / registers:** ``observability/operations/``
- **Migration map:** ``MIGRATION_MAP.md``

{sec("Prior AGENTS.md (full migrated body)", old_agents)}

{sec("Prior MEMORY.md (embedded for routing continuity)", old_memory)}

{sec("Prior USER.md (embedded)", old_user)}
"""
    _write_text(mem_root / "AGENTS.md", ag)

    mem = f"""# MEMORY.md (workspace/memory)

Persistent routing for **what to remember** and **where it lives** after semantic migration.

## Routing rules

- Durable truths / concepts → ``semantic-graph/knowledge/``
- Policies / standards / governance → ``reflective-doctrine/governance/``
- Persona / roles / registers → ``social-role-memory/``
- Live state → ``working-memory/``
- Procedures → ``skill-atlas/procedures/`` and ``skill-atlas/promoted-skills/``
- Failures / anti-patterns → ``hazard-memory/operations/`` (when applicable)
- Open loops / queues → ``prospective-memory/operations/`` (when applicable)

{sec("Prior MEMORY.md (full migrated body)", old_memory)}
"""
    _write_text(mem_root / "MEMORY.md", mem)

    user = f"""# USER.md (workspace/memory)

{sec("Prior USER.md (full migrated body)", old_user)}
"""
    _write_text(mem_root / "USER.md", user)

    att = f"""# ATTENTION.md (workspace/memory)

{sec("Prior ATTENTION.md (full migrated body)", old_attention)}
"""
    _write_text(mem_root / "ATTENTION.md", att)

    idx = f"""# INDEX.md (workspace/memory)

## Lattice index (post semantic migration)

- **Migration map:** ``MIGRATION_MAP.md``
- **Manifest (jsonl):** ``migration_manifest.jsonl``
- **Infrastructure snapshot:** ``INFRASTRUCTURE.md`` (may be large; use selective loading)

{sec("Prior INDEX.md (full migrated body)", old_index)}
"""
    _write_text(mem_root / "INDEX.md", idx)

    comp = f"""# COMPASS.md (workspace/memory)

{sec("Prior COMPASS.md (full migrated body)", old_compass)}
"""
    _write_text(mem_root / "COMPASS.md", comp)

    readme = f"""# README.md (workspace/memory)

{sec("Prior README.md (full migrated body)", old_readme)}
"""
    _write_text(mem_root / "README.md", readme)


def _write_constitution_snippets(mem_root: Path, sources: list[Path]) -> None:
    """Pull high-signal excerpts into constitution/ for always-loaded compilation."""
    const_dir = mem_root / "constitution"
    const_dir.mkdir(parents=True, exist_ok=True)
    pieces: list[str] = []
    for label, rel_hint, max_chars in (
        ("foundation-memory-contract", "foundation-memory-contract", 5000),
        ("enforcement-and-standards", "enforcement-and-standards", 5000),
        ("activation-selection-map", "activation-selection-map", 5000),
        ("role-prompt-injection-rules", "role-prompt-injection", 5000),
    ):
        hit: Path | None = None
        for root in sources:
            if not root.exists():
                continue
            for p in root.rglob("*.md"):
                if rel_hint in str(p).lower():
                    hit = p
                    break
            if hit:
                break
        if not hit:
            continue
        body = _read_text(hit)
        excerpt = body.strip()
        if len(excerpt) > max_chars:
            excerpt = excerpt[:max_chars] + "\n\n[... truncated ...]\n"
        pieces.append(f"## Excerpt: {label}\n\nSource: `{hit}`\n\n{excerpt}")
    routing = mem_root / "constitution" / "routing.md"
    _write_text(
        routing,
        "\n\n".join(
            [
                "# routing.md — condensed high-signal sources",
                "",
                "This file contains **excerpts** migrated from the prior system. Canonical depth remains in semantic + doctrine trees.",
                "",
                *pieces,
            ]
        ),
    )


def _refresh_layer_manifests(mem_root: Path, counts: dict[str, int]) -> None:
    for layer, n in sorted(counts.items(), key=lambda x: x[0]):
        p = mem_root / layer / "MANIFEST.md"
        text = f"""# {layer}/ — MANIFEST (post semantic migration)

This layer was populated by ``semantic_integrate_cortical_lattice_memory.py``.

## Approximate object count

- Markdown files migrated into this layer (including subtrees): **{n}**

## Navigation

- Global map: ``../MIGRATION_MAP.md``
- Per-file manifest: ``../migration_manifest.jsonl``
"""
        _write_text(p, text)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Semantic integration of legacy memory into Cortical Lattice layers.")
    ap.add_argument("--hermes-home", required=True, help="Profile HERMES_HOME")
    ap.add_argument(
        "--repo-memory",
        default="",
        help="Optional extra source tree (e.g. checkout memory/). Used on hosts where archive lacks subtrees.",
    )
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true", help="Overwrite migrated files when re-run.")
    ap.add_argument(
        "--prune-legacy-mirrors",
        action="store_true",
        help="Remove known duplicate mirror dirs under workspace/memory (legacy-knowledge, legacy-governance, _legacy_*).",
    )
    ap.add_argument(
        "--include-legacy-mirrors",
        action="store_true",
        help="Also ingest duplicate mirror trees created by the first-pass migrator (usually unnecessary if archive is complete).",
    )
    ap.add_argument(
        "--root-anchor-max-chars",
        type=int,
        default=0,
        help="Per-section cap when embedding prior root anchors (0 = full text, no truncation).",
    )
    ap.add_argument(
        "--skip-content-refine",
        action="store_true",
        help="Disable YAML frontmatter + keyword refinement (path-only classification).",
    )
    ap.add_argument(
        "--promote-procedure-skills",
        action="store_true",
        help="After migration, emit Cursor-style SKILL.md bundles under skill-atlas/promoted-skills/ from procedures/*.md.",
    )
    args = ap.parse_args(argv)

    hermes_home = Path(args.hermes_home).expanduser().resolve()
    mem_root = hermes_home / "workspace" / "memory"
    if not mem_root.is_dir():
        print(f"missing {mem_root}", file=sys.stderr)
        return 2

    legacy_dir = mem_root / "legacy-archive"
    pre_dirs = sorted([p for p in legacy_dir.glob("pre-cortical-*") if p.is_dir()], key=lambda p: p.name)
    if not pre_dirs:
        print("no legacy-archive/pre-cortical-* found; nothing to integrate", file=sys.stderr)
        return 1
    primary_archive = pre_dirs[-1]

    extra_sources: list[Path] = [primary_archive]
    repo_mem = (args.repo_memory or "").strip()
    if repo_mem:
        p = Path(repo_mem).expanduser().resolve()
        if p.is_dir():
            extra_sources.append(p)

    # Optional: first-pass migrator mirrors (often duplicate the archive subtree)
    if args.include_legacy_mirrors:
        for mirror in (
            mem_root / "semantic-graph" / "graph-mirror" / "legacy-knowledge",
            mem_root / "reflective-doctrine" / "legacy-governance",
            mem_root / "social-role-memory" / "persona" / "legacy-persona",
            mem_root / "skill-atlas" / "references" / "legacy-procedures",
            mem_root / "skill-atlas" / "legacy-workspace-skills",
            mem_root / "bootstrap" / "templates" / "legacy-templates",
            mem_root / "indexes" / "legacy-core",
            mem_root / "working-memory" / "_legacy_runtime_state",
        ):
            if mirror.is_dir():
                extra_sources.append(mirror)

    manifest_path = mem_root / "migration_manifest.jsonl"
    if not args.dry_run:
        # Fresh manifest each run (idempotent re-integration; inspect git history for older receipts if needed).
        manifest_path.write_text("", encoding="utf-8")

    counts: dict[str, int] = {}
    seen_sources: set[str] = set()
    promoted_skills_result: dict | None = None

    for src_root in extra_sources:
        for md in _iter_markdown_files(src_root):
            src_key = str(md.resolve())
            if src_key in seen_sources:
                continue
            seen_sources.add(src_key)

            body = _read_text(md)
            base_cls = classify_path(mem_root, src_root, md)
            cls = base_cls if args.skip_content_refine else refine_classification(mem_root, src_root, md, body, base_cls)
            dest = cls.dest
            header = _provenance_header(source=md, role=cls.role, note=cls.note)
            action = "dry-run"
            if not args.dry_run:
                dest.parent.mkdir(parents=True, exist_ok=True)
                full_new = header + body.lstrip("\n")
                src_marker = f"<!-- source-path: {src_key} -->"
                if dest.exists() and not args.force:
                    old = _read_text(dest)
                    if src_marker in old:
                        action = "skipped-duplicate-source"
                    elif hashlib.sha256(old.encode()).digest() == hashlib.sha256(full_new.encode()).digest():
                        action = "skipped-identical"
                    elif _body_effectively_present(old, body):
                        action = "skipped-duplicate-body"
                    else:
                        _write_text(dest, old.rstrip() + "\n\n---\n\n" + full_new)
                        action = "merged-append"
                else:
                    existed = dest.exists()
                    _write_text(dest, full_new)
                    action = "overwritten" if existed else "created"

            rec = {
                "ts": _utc_iso(),
                "source": str(md),
                "source_root": str(src_root),
                "layer": cls.layer,
                "role": cls.role,
                "dest": str(dest),
                "action": action,
            }
            if not args.dry_run:
                _append_jsonl(manifest_path, rec)

            if args.dry_run or action in (
                "created",
                "merged-append",
                "overwritten",
                "skipped-identical",
                "skipped-duplicate-source",
                "skipped-duplicate-body",
            ):
                counts[cls.layer] = counts.get(cls.layer, 0) + 1

    if not args.dry_run:
        roots = primary_archive / "root-anchors"
        _merge_root_anchors(mem_root, roots, max_chars_per_section=args.root_anchor_max_chars)
        _write_constitution_snippets(mem_root, [primary_archive, mem_root / "semantic-graph" / "knowledge"])
        # Refresh CONSTITUTION.md pointer body if small file exists
        const = mem_root / "constitution" / "CONSTITUTION.md"
        if const.is_file():
            ctext = _read_text(const)
            if "routing.md" not in ctext:
                _write_text(
                    const,
                    ctext.rstrip()
                    + "\n\n## Migrated routing excerpts\n\nSee `constitution/routing.md` (condensed excerpts with provenance).\n",
                )
        _refresh_layer_manifests(mem_root, counts)

        # Migration map markdown
        lines = [
            "# MIGRATION_MAP.md",
            "",
            f"Generated: `{_utc_iso()}`",
            "",
            "## Source roots",
            "",
            f"- Primary archive: `{primary_archive}`",
        ]
        for s in extra_sources[1:]:
            lines.append(f"- Additional source: `{s}`")
        lines += [
            "",
            "## Semantic role → lattice layer (routing)",
            "",
            "| semantic role (header `semantic-role`) | primary layer | canonical destination root |",
            "|---|---|---|",
            "| `root-anchor-source` | indexes | `indexes/root-anchors-source/` |",
            "| `persona` | social-role-memory | `social-role-memory/persona/` |",
            "| `role-registry` | social-role-memory | `social-role-memory/registry/` |",
            "| `orchestration` | social-role-memory | `social-role-memory/orchestration/` |",
            "| `semantic-knowledge` | semantic-graph | `semantic-graph/knowledge/` |",
            "| `doctrine-governance` | reflective-doctrine | `reflective-doctrine/governance/` |",
            "| `governance-chronology` | episodic-ledger | `episodic-ledger/chronology/` |",
            "| `working-runtime-state` | working-memory | `working-memory/runtime-state/` |",
            "| `runtime-operations` | observability / hazard / prospective | `observability/operations/` (default) |",
            "| `procedure` | skill-atlas | `skill-atlas/procedures/` |",
            "| `workspace-skill` | skill-atlas | `skill-atlas/workspace-skills/` |",
            "| `bootstrap-template` | bootstrap | `bootstrap/templates/` |",
            "| `bootstrap-core` | bootstrap | `bootstrap/core/init/` |",
            "| `bootstrap-scripts` | bootstrap | `bootstrap/scripts/` |",
            "| `episodic-import` | episodic-ledger | `episodic-ledger/imported/` |",
            "| `case-record` | case-memory | `case-memory/cases/` |",
            "| `misc` | semantic-graph | `semantic-graph/misc-import/` |",
            "| `content-frontmatter` | (declared in YAML) | `<layer>/imports/` |",
            "| `content-keyword-*` | (heuristic) | `<layer>/content-autoclass/` |",
            "",
            "## Layer population counts (this run)",
            "",
        ]
        for k, v in sorted(counts.items(), key=lambda x: x[0]):
            lines.append(f"- **{k}**: {v} markdown files classified")
        lines += [
            "",
            "## Per-file traceability",
            "",
            "- Machine-readable: `migration_manifest.jsonl` (one JSON object per source file)",
            "",
            "## Canonical policy",
            "",
            "- Old content is **source material**; canonical operational paths are under the Cortical Lattice directories.",
            "- Provenance is embedded in migrated markdown headers and in `migration_manifest.jsonl`.",
            "",
        ]
        _write_text(mem_root / "MIGRATION_MAP.md", "\n".join(lines))

        if args.promote_procedure_skills:
            from promote_procedure_skills import promote as _promote_procedure_skills  # noqa: E402

            promoted_skills_result = _promote_procedure_skills(mem_root, force=args.force, dry_run=False)

        bridge = mem_root / "legacy-archive" / "README-SEMANTIC-MIGRATION.md"
        _write_text(
            bridge,
            "\n".join(
                [
                    "# legacy-archive — bridge",
                    "",
                    "This directory may contain a **pre-cortical snapshot** taken during the first migration.",
                    "",
                    "**Canonical operational memory** now lives in the Cortical Lattice layer directories under `../` (sibling of this folder), not inside this archive.",
                    "",
                    "- Migration map: `../MIGRATION_MAP.md`",
                    "- Per-file manifest: `../migration_manifest.jsonl`",
                    "- Live anchors: `../AGENTS.md`, `../INDEX.md`, `../MEMORY.md`, …",
                    "",
                    "Re-run integration (on the host):",
                    "",
                    "```bash",
                    "python3 memory/core/scripts/core/semantic_integrate_cortical_lattice_memory.py \\",
                    "  --hermes-home \"$HERMES_HOME\"",
                    "# Optional: --promote-procedure-skills  --root-anchor-max-chars 50000",
                    "```",
                    "",
                    f"Primary snapshot used as source: `{primary_archive}`",
                    "",
                ]
            ),
        )

    if args.prune_legacy_mirrors and not args.dry_run:
        for d in (
            mem_root / "semantic-graph" / "graph-mirror" / "legacy-knowledge",
            mem_root / "reflective-doctrine" / "legacy-governance",
            mem_root / "social-role-memory" / "persona" / "legacy-persona",
            mem_root / "skill-atlas" / "references" / "legacy-procedures",
            mem_root / "skill-atlas" / "legacy-workspace-skills",
            mem_root / "bootstrap" / "templates" / "legacy-templates",
            mem_root / "indexes" / "legacy-core",
            mem_root / "working-memory" / "_legacy_runtime_state",
            mem_root / "working-memory" / "_legacy_current-focus.md",
        ):
            try:
                if d.is_dir():
                    shutil.rmtree(d)
                elif d.is_file():
                    d.unlink()
            except OSError:
                pass

    out: dict = {"ok": True, "dry_run": args.dry_run, "counts": counts, "primary_archive": str(primary_archive)}
    if promoted_skills_result is not None:
        out["promoted_skills"] = promoted_skills_result
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
