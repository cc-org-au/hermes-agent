"""Tests for agent.openai_native_runtime."""

from agent.openai_native_runtime import (
    bare_openai_api_model_id,
    is_native_openai_consultant_model_id,
    native_openai_api_key,
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
    monkeypatch.delenv("OPENAI_API_KEY_DROPLET", raising=False)
    assert native_openai_runtime_tuple() is None


def test_runtime_tuple_with_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY_DROPLET", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    bu, ak = native_openai_runtime_tuple()
    assert ak == "sk-test"
    assert bu == "https://api.openai.com/v1"


def test_droplet_key_preferred_when_both_set(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY_DROPLET", "sk-droplet")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-other")
    assert native_openai_api_key() == "sk-droplet"
    bu, ak = native_openai_runtime_tuple()
    assert ak == "sk-droplet"
    assert bu == "https://api.openai.com/v1"


def test_native_consultant_slug_detection():
    assert is_native_openai_consultant_model_id("openai/gpt-5.4")
    assert is_native_openai_consultant_model_id("gpt-5.3-codex")
    assert not is_native_openai_consultant_model_id("openai/gpt-5.4-mini")
    assert bare_openai_api_model_id("openai/gpt-5.4") == "gpt-5.4"
