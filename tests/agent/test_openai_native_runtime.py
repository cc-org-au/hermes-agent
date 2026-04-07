"""Tests for agent.openai_native_runtime."""

from agent.openai_native_runtime import (
    native_openai_runtime_tuple,
    resolve_native_openai_chat_base_url,
)


def test_resolve_base_default(monkeypatch):
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    assert resolve_native_openai_chat_base_url() == "https://api.openai.com/v1"


def test_resolve_base_appends_v1_for_openai_host(monkeypatch):
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.openai.com")
    assert resolve_native_openai_chat_base_url() == "https://api.openai.com/v1"


def test_runtime_tuple_none_without_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert native_openai_runtime_tuple() is None


def test_runtime_tuple_with_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    bu, ak = native_openai_runtime_tuple()
    assert ak == "sk-test"
    assert bu == "https://api.openai.com/v1"
