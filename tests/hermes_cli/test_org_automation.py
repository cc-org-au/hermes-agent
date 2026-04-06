"""Tests for hermes_cli.org_automation."""

from pathlib import Path
from unittest.mock import patch

import yaml

from hermes_cli.org_automation import (
    _render_sync_block,
    _replace_or_append_block,
    sync_org_markdown_files,
)


def test_render_sync_block_includes_rows(tmp_path):
    manifest = {
        "profiles": [
            {"name": "role-a", "ag_id": "ag-1", "role_prompt": "prompts/a.md"},
        ]
    }
    mp = tmp_path / "m.yaml"
    mp.write_text(yaml.safe_dump(manifest), encoding="utf-8")
    block = _render_sync_block(manifest, mp)
    assert "HERMES_ORG_MANIFEST_SYNC:BEGIN" in block
    assert "`role-a`" in block
    assert "ag-1" in block


def test_replace_block_roundtrip(tmp_path):
    path = tmp_path / "ORG_REGISTRY.md"
    path.write_text("intro\n\n<!-- HERMES_ORG_MANIFEST_SYNC:BEGIN -->\nold\n<!-- HERMES_ORG_MANIFEST_SYNC:END -->\n\nfooter\n")
    new_block = "<!-- HERMES_ORG_MANIFEST_SYNC:BEGIN -->\nnew\n<!-- HERMES_ORG_MANIFEST_SYNC:END -->\n"
    _replace_or_append_block(path, new_block)
    body = path.read_text(encoding="utf-8")
    assert "new" in body
    assert "old" not in body
    assert "footer" in body


def test_sync_org_markdown_files_writes_ops(tmp_path):
    home = tmp_path / ".hermes"
    manifest = {"profiles": [{"name": "x", "ag_id": "", "role_prompt": "p.md"}]}
    mp = tmp_path / "manifest.yaml"
    mp.write_text(yaml.safe_dump(manifest), encoding="utf-8")

    with patch.dict("os.environ", {"HERMES_HOME": str(home)}, clear=False):
        sync_org_markdown_files(manifest, manifest_path=mp, dry_run=False)

    for name in ("ORG_REGISTRY.md", "ORG_CHART.md"):
        p = home / "workspace" / "operations" / name
        assert p.is_file()
        t = p.read_text(encoding="utf-8")
        assert "HERMES_ORG_MANIFEST_SYNC:BEGIN" in t
        assert "`x`" in t
