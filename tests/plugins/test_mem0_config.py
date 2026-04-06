"""Mem0 plugin config: file + env merge."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

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


def test_mem0_search_filters_non_empty():
    from plugins.memory.mem0 import _mem0_search_filters

    assert _mem0_search_filters("alice") == {"AND": [{"user_id": "alice"}]}


def test_mem0_profile_uses_v2_filters_on_get_all():
    """v2 list memories requires ``filters`` in the JSON body, not bare user_id."""
    from plugins.memory.mem0 import Mem0MemoryProvider

    prov = Mem0MemoryProvider()
    prov.initialize("sess-1")
    mock_client = MagicMock()
    mock_client.get_all.return_value = {"results": [{"memory": "fact one"}]}
    with patch.object(prov, "_get_client", return_value=mock_client):
        out = json.loads(prov.handle_tool_call("mem0_profile", {}))

    mock_client.get_all.assert_called_once()
    assert mock_client.get_all.call_args.kwargs.get("filters") == {
        "AND": [{"user_id": prov._user_id}],
    }
    assert out["count"] == 1
    assert "fact one" in out["result"]


def test_normalize_memory_rows():
    from plugins.memory.mem0 import _normalize_memory_rows

    assert _normalize_memory_rows(None) == []
    assert _normalize_memory_rows([]) == []
    assert _normalize_memory_rows([{"memory": "a"}]) == [{"memory": "a"}]
    assert _normalize_memory_rows({"results": [{"memory": "b"}]}) == [{"memory": "b"}]
    assert _normalize_memory_rows({"memories": [{"memory": "c"}]}) == [{"memory": "c"}]
