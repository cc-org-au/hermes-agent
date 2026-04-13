"""Tests for workspace runtime governance prompt injection."""

from __future__ import annotations

import pytest
import yaml


def test_load_runtime_governance_prompt_disabled(tmp_path, monkeypatch):
    from agent import runtime_governance_prompt as rgp

    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    ops = tmp_path / "workspace" / "memory" / "runtime" / "operations"
    ops.mkdir(parents=True)
    p = ops / "runtime_governance.runtime.yaml"
    p.write_text(yaml.safe_dump({"enabled": False, "summary": "x"}), encoding="utf-8")
    assert rgp.load_runtime_governance_prompt() == ""


def test_load_runtime_governance_prompt_content(tmp_path, monkeypatch):
    from agent import runtime_governance_prompt as rgp

    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    ops = tmp_path / "workspace" / "memory" / "runtime" / "operations"
    ops.mkdir(parents=True)
    doc = {
        "enabled": True,
        "activation_session": 4,
        "active_role_slug": "security_governor",
        "summary": "Stay inside policy.",
        "concise_directives": ["Do A", "Do B"],
        "read_order_paths": ["POLICY_ROOT/core/security-prompts.md"],
    }
    (ops / "runtime_governance.runtime.yaml").write_text(
        yaml.safe_dump(doc), encoding="utf-8"
    )
    out = rgp.load_runtime_governance_prompt()
    assert "Activation session" in out or "activation" in out.lower()
    assert "security_governor" in out
    assert "Do A" in out
    assert "security-prompts.md" in out
