"""Tests for gateway messaging role routing."""

from __future__ import annotations

import pytest
import yaml

from gateway.config import Platform
from gateway.messaging_role import (
    append_token_model_disclosure_line,
    build_messaging_role_ephemeral,
    intersect_toolsets_with_messaging_role,
    load_role_allowed_toolsets,
    resolve_messaging_disclosure_label,
    resolve_messaging_role_slug,
)
from gateway.session import SessionSource


def test_resolve_thread_over_channel(tmp_path):
    cfg = {
        "enabled": True,
        "default_role": "chief_orchestrator",
        "slack": {
            "channels": {"C111": "channel_role"},
            "threads": {"174.999": "thread_role"},
        },
    }
    src = SessionSource(
        platform=Platform.SLACK,
        chat_id="C111",
        chat_type="channel",
        thread_id="174.999",
    )
    assert resolve_messaging_role_slug(src, cfg, hermes_home=tmp_path) == "thread_role"


def test_resolve_default(tmp_path):
    cfg = {"enabled": True, "default_role": "chief_orchestrator"}
    src = SessionSource(
        platform=Platform.TELEGRAM,
        chat_id="999",
        chat_type="group",
    )
    assert resolve_messaging_role_slug(src, cfg, hermes_home=tmp_path) == "chief_orchestrator"


def test_build_ephemeral_with_assignments(tmp_path):
    cfg = {"enabled": True, "default_role": "r1"}
    ops = tmp_path / "workspace" / "memory" / "runtime" / "operations"
    ops.mkdir(parents=True)
    doc = {
        "roles": {
            "r1": {
                "display_name": "Role One",
                "policy_reads": ["WORKSPACE/AGENTS.md"],
                "hermes_profile_for_delegation": "r1-profile",
            }
        }
    }
    (ops / "role_assignments.yaml").write_text(yaml.safe_dump(doc), encoding="utf-8")
    src = SessionSource(platform=Platform.SLACK, chat_id="C1", chat_type="channel")
    block = build_messaging_role_ephemeral(src, cfg, hermes_home=tmp_path)
    assert "r1" in block
    assert "AGENTS.md" in block
    assert "delegate_task" in block or "hermes_profile" in block
    assert "token-model" in block or "§14" in block


def test_append_token_model_disclosure_line():
    t = append_token_model_disclosure_line("Hello", "Chief Orchestrator")
    assert t.endswith("--Chief Orchestrator")
    assert append_token_model_disclosure_line(t, "Chief Orchestrator") == t


def test_resolve_messaging_disclosure_label(tmp_path):
    ops = tmp_path / "workspace" / "memory" / "runtime" / "operations"
    ops.mkdir(parents=True)
    doc = {
        "roles": {
            "chief_orchestrator": {"display_name": "Chief Orchestrator"},
        },
    }
    (ops / "role_assignments.yaml").write_text(yaml.safe_dump(doc), encoding="utf-8")
    cfg = {"enabled": True, "default_role": "chief_orchestrator"}
    src = SessionSource(platform=Platform.TELEGRAM, chat_id="1", chat_type="private")
    messaging = {"role_routing": cfg}
    label = resolve_messaging_disclosure_label(src, messaging, hermes_home=tmp_path)
    assert label == "Chief Orchestrator"


def test_intersect_toolsets_with_messaging_role(tmp_path):
    ops = tmp_path / "workspace" / "memory" / "runtime" / "operations"
    ops.mkdir(parents=True)
    doc = {
        "roles": {
            "r1": {"allowed_toolsets": ["terminal", "file"]},
        },
    }
    (ops / "role_assignments.yaml").write_text(yaml.safe_dump(doc), encoding="utf-8")
    src = SessionSource(platform=Platform.SLACK, chat_id="C1", chat_type="channel")
    rr = {"enabled": True, "default_role": "r1", "slack": {"channels": {"C1": "r1"}}}
    uc = {"messaging": {"role_routing": rr}}
    out = intersect_toolsets_with_messaging_role(
        ["terminal", "file", "web"], src, uc, hermes_home=tmp_path
    )
    assert out == ["file", "terminal"]


def test_load_role_allowed_toolsets(tmp_path):
    ops = tmp_path / "workspace" / "memory" / "runtime" / "operations"
    ops.mkdir(parents=True)
    doc = {
        "roles": {
            "fd-engineering": {"allowed_toolsets": ["terminal", "file", "web"]},
            "no_cap": {"display_name": "X"},
        },
    }
    (ops / "role_assignments.yaml").write_text(yaml.safe_dump(doc), encoding="utf-8")
    assert load_role_allowed_toolsets("fd-engineering", hermes_home=tmp_path) == [
        "terminal",
        "file",
        "web",
    ]
    assert load_role_allowed_toolsets("no_cap", hermes_home=tmp_path) is None
    assert load_role_allowed_toolsets(None, hermes_home=tmp_path) is None
