"""Tests for content-aware Cortical Lattice classification helpers."""

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS = _ROOT / "memory" / "core" / "scripts" / "core"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from cortical_lattice_classify import (  # noqa: E402
    ClassifyResult,
    classify_from_frontmatter,
    classify_from_keywords_misc_only,
    refine_classification,
)


@pytest.fixture
def mem_root(tmp_path: Path) -> Path:
    return tmp_path / "memory"


def test_frontmatter_overrides_layer(mem_root: Path) -> None:
    body = "---\nmemory_layer: hazard-memory\n---\n\n# Doc\nincident\n"
    base = ClassifyResult("semantic-graph", mem_root / "semantic-graph" / "misc-import" / "x.md", "misc")
    r = classify_from_frontmatter(mem_root, rel=Path("x.md"), body=body, base=base)
    assert r is not None
    assert r.layer == "hazard-memory"
    assert "imports" in str(r.dest)


def test_keyword_misc_to_hazard(mem_root: Path) -> None:
    body = "\n".join(
        [
            "some misc doc",
            "incident register notes",
            "security remediation required",
            "failure mode analysis",
            "do not retry blindly",
        ]
    )
    base = ClassifyResult("semantic-graph", mem_root / "semantic-graph" / "misc-import" / "z.md", "misc")
    r = classify_from_keywords_misc_only(mem_root, rel=Path("z.md"), body=body, base=base)
    assert r is not None
    assert r.layer == "hazard-memory"
    assert "content-autoclass" in str(r.dest)


def test_refine_prefers_frontmatter_over_keywords(mem_root: Path) -> None:
    body = "---\nmemory_layer: episodic-ledger\n---\n\nincident register " * 5
    base = ClassifyResult("semantic-graph", mem_root / "semantic-graph" / "misc-import" / "a.md", "misc")
    p = mem_root / "src" / "a.md"
    p.parent.mkdir(parents=True)
    p.write_text(body, encoding="utf-8")
    r = refine_classification(mem_root, p.parent, p, body, base)
    assert r.layer == "episodic-ledger"
