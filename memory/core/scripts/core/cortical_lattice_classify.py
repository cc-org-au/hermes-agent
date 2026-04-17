"""Content-aware refinement for Cortical Lattice memory classification.

Used by ``semantic_integrate_cortical_lattice_memory.py`` after path-based rules.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ClassifyResult:
    layer: str
    dest: Path
    role: str
    note: str = ""


# YAML frontmatter keys that override destination layer (first match wins).
_FM_KEYS = (
    "memory_layer",
    "cortical_layer",
    "hermes_memory_layer",
    "lattice_layer",
)

# Normalize user-facing labels to internal layer directory names under workspace/memory/.
_LAYER_ALIASES: dict[str, str] = {
    "hazard": "hazard-memory",
    "hazard-memory": "hazard-memory",
    "prospective": "prospective-memory",
    "prospective-memory": "prospective-memory",
    "episodic": "episodic-ledger",
    "episodic-ledger": "episodic-ledger",
    "ledger": "episodic-ledger",
    "doctrine": "reflective-doctrine",
    "reflective-doctrine": "reflective-doctrine",
    "governance": "reflective-doctrine",
    "semantic": "semantic-graph",
    "semantic-graph": "semantic-graph",
    "knowledge": "semantic-graph",
    "working": "working-memory",
    "working-memory": "working-memory",
    "social": "social-role-memory",
    "social-role": "social-role-memory",
    "social-role-memory": "social-role-memory",
    "persona": "social-role-memory",
    "case": "case-memory",
    "case-memory": "case-memory",
    "observability": "observability",
    "bootstrap": "bootstrap",
    "skill": "skill-atlas",
    "skill-atlas": "skill-atlas",
    "constitution": "constitution",
}


def _extract_yaml_frontmatter(text: str) -> str | None:
    t = text.lstrip("\ufeff")
    if not t.startswith("---"):
        return None
    end = t.find("\n---", 3)
    if end == -1:
        return None
    return t[3:end]


def _parse_frontmatter_layer(text: str) -> str | None:
    """Return normalized internal layer name from frontmatter, or None."""
    block = _extract_yaml_frontmatter(text)
    if not block:
        return None
    for line in block.splitlines():
        if ":" not in line or line.strip().startswith("#"):
            continue
        key, _, val = line.partition(":")
        key = key.strip().lower()
        if key not in _FM_KEYS:
            continue
        val = val.strip().strip('"').strip("'")
        if not val:
            continue
        norm = val.lower().replace(" ", "-").replace("_", "-")
        return _LAYER_ALIASES.get(norm, norm)
    return None


def _safe_rel_tail(rel: Path) -> Path:
    parts = [p for p in rel.parts if p not in ("", ".", "..")]
    return Path(*parts) if parts else Path("document.md")


_KNOWN_LAYERS = frozenset(
    {
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
        "bootstrap",
        "indexes",
    }
)


def classify_from_frontmatter(
    mem_root: Path,
    *,
    rel: Path,
    body: str,
    base: ClassifyResult,
) -> ClassifyResult | None:
    """If frontmatter declares a layer, re-home under ``<layer>/imports/<relpath>``."""
    raw = _parse_frontmatter_layer(body)
    if not raw:
        return None
    layer = _LAYER_ALIASES.get(raw, raw)
    if layer not in _KNOWN_LAYERS:
        return None
    tail = _safe_rel_tail(rel)
    dest = mem_root / layer / "imports" / tail
    return ClassifyResult(
        layer,
        dest,
        "content-frontmatter",
        f"Frontmatter memory layer override (was path role `{base.role}`).",
    )


# (keywords tuple, target layer, role note)
_KEYWORD_RULES: tuple[tuple[tuple[str, ...], str, str], ...] = (
    (
        ("incident register", "security remediation", "failure mode", "do not retry", "dangerous command"),
        "hazard-memory",
        "content-keyword-hazard",
    ),
    (
        ("open action", "deadline", "follow-up required", "escalation queue", "pending remediation"),
        "prospective-memory",
        "content-keyword-prospective",
    ),
    (
        ("changelog", "what changed", "state transition", "dated entry"),
        "episodic-ledger",
        "content-keyword-episodic",
    ),
    (
        ("playbook", "runbook", "procedure", "step 1", "verification steps"),
        "skill-atlas",
        "content-keyword-skillish",
    ),
    (
        ("stable truth", "invariant", "definition", "concept:", "domain model"),
        "semantic-graph",
        "content-keyword-semantic",
    ),
)


def classify_from_keywords_misc_only(
    mem_root: Path,
    *,
    rel: Path,
    body: str,
    base: ClassifyResult,
) -> ClassifyResult | None:
    """Re-classify ``misc`` / misc-import paths using lightweight keyword signals."""
    if base.role != "misc":
        return None
    sample = body[:24000].lower()
    if len(sample) < 80:
        return None
    best: tuple[int, str, str] = (0, "", "")
    for kws, layer, role in _KEYWORD_RULES:
        score = sum(1 for k in kws if k in sample)
        if score > best[0]:
            best = (score, layer, role)
    if best[0] < 2:
        return None
    _, layer, role = best
    tail = _safe_rel_tail(rel)
    dest = mem_root / layer / "content-autoclass" / tail
    return ClassifyResult(layer, dest, role, "Keyword heuristic (misc-import only); review if wrong.")


def refine_classification(
    mem_root: Path,
    source_root: Path,
    path: Path,
    body: str,
    base: ClassifyResult,
) -> ClassifyResult:
    """Apply frontmatter override, then keyword override for misc."""
    try:
        rel = path.relative_to(source_root).as_posix()
    except ValueError:
        rel = path.name
    rel_path = Path(rel)

    fm = classify_from_frontmatter(mem_root, rel=rel_path, body=body, base=base)
    if fm is not None:
        return fm

    kw = classify_from_keywords_misc_only(mem_root, rel=rel_path, body=body, base=base)
    if kw is not None:
        return kw

    return base


def first_markdown_heading(body: str) -> str:
    for line in body.splitlines():
        s = line.strip()
        if s.startswith("#"):
            return re.sub(r"^#+\s*", "", s).strip() or "Untitled"
    return "Untitled"


def first_paragraph_excerpt(body: str, max_len: int = 280) -> str:
    text = body.strip()
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            text = text[end + 4 :].lstrip()
    buf: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            if buf:
                break
            continue
        if line.startswith("#"):
            continue
        buf.append(line)
        if sum(len(x) for x in buf) > max_len:
            break
    out = " ".join(buf).strip()
    if len(out) > max_len:
        return out[: max_len - 3].rstrip() + "..."
    return out or "Hermes workspace procedure (see body)."
