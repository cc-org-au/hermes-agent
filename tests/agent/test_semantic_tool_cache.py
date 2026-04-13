"""Semantic tool result cache (SQLite, profile-local)."""

from __future__ import annotations

import json

import pytest

from agent.semantic_tool_cache import (
    clear_semantic_tool_cache_for_tests,
    configure_semantic_tool_cache,
    lookup,
    store,
)


def test_semantic_cache_hit_miss(tmp_path, monkeypatch):
    home = tmp_path / ".hermes"
    home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(home))
    clear_semantic_tool_cache_for_tests()
    configure_semantic_tool_cache(
        {
            "enabled": True,
            "ttl_seconds": 3600,
            "sqlite_relpath": "semantic_tool_cache.sqlite",
            "allow_tools": ["read_file"],
            "host_role_env_precedence": ["HERMES_CLI_INSTANCE_LABEL"],
        }
    )
    monkeypatch.setenv("HERMES_CLI_INSTANCE_LABEL", "test-role")

    assert lookup("read_file", {"path": "/x"}) is None
    store("read_file", {"path": "/x"}, json.dumps({"ok": True}))
    hit = lookup("read_file", {"path": "/x"})
    assert hit is not None
    assert json.loads(hit) == {"ok": True}

    configure_semantic_tool_cache({"enabled": True, "allow_tools": []})
    assert lookup("read_file", {"path": "/x"}) is None
