"""Mem0 plugin config: file + env merge."""

import json
from pathlib import Path

import pytest


def test_load_config_merges_mem0_api_key_from_env(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setenv("MEM0_API_KEY", "env-secret-key")
    monkeypatch.setenv("MEM0_USER_ID", "from-env-user")
    cfg_path = tmp_path / "mem0.json"
    cfg_path.write_text(
        json.dumps({"user_id": "file-user", "agent_id": "a1", "rerank": False}),
        encoding="utf-8",
    )
    from plugins.memory.mem0 import _load_config

    out = _load_config()
    assert out["api_key"] == "env-secret-key"
    assert out["user_id"] == "file-user"
    assert out["agent_id"] == "a1"
    assert out["rerank"] is False
