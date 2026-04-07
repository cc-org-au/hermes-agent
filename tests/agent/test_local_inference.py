"""local_inference override for HF hub ids served locally."""

import json

import pytest


def test_local_override_when_in_state(tmp_path, monkeypatch):
    from agent import local_inference as li

    hub = tmp_path / "local_models" / "hub"
    hub.mkdir(parents=True)
    (hub / "state.json").write_text(
        json.dumps({"downloaded": ["org/model-a"]}),
        encoding="utf-8",
    )
    monkeypatch.setenv("HERMES_LOCAL_INFERENCE_BASE_URL", "http://127.0.0.1:8000")
    monkeypatch.setenv("HERMES_LOCAL_MODEL_STATE", str(hub / "state.json"))
    monkeypatch.setenv("HERMES_LOCAL_INFERENCE_API_KEY", "x")
    base, key = li.local_inference_override_for_hub_model("org/model-a")
    assert base.endswith("/v1")
    assert key == "x"


def test_no_override_without_env():
    from agent import local_inference as li

    assert li.local_inference_override_for_hub_model("org/model-a") is None


def test_filter_hub_model_ids_keeps_downloaded(tmp_path, monkeypatch):
    from agent import local_inference as li

    hub = tmp_path / "local_models" / "hub"
    hub.mkdir(parents=True)
    (hub / "state.json").write_text(
        json.dumps({"downloaded": ["Qwen/QwQ-32B"]}),
        encoding="utf-8",
    )
    monkeypatch.setenv("HERMES_LOCAL_MODEL_STATE", str(hub / "state.json"))
    out = li.filter_hub_model_ids_by_local_state(
        ["Qwen/QwQ-32B", "google/missing"],
        enabled=True,
    )
    assert out == ["Qwen/QwQ-32B"]


def test_filter_hub_model_ids_no_state_noop(tmp_path, monkeypatch):
    from agent import local_inference as li

    missing = tmp_path / "no_state.json"
    monkeypatch.setenv("HERMES_LOCAL_MODEL_STATE", str(missing))
    raw = ["a", "b"]
    assert li.filter_hub_model_ids_by_local_state(raw, enabled=True) == raw
