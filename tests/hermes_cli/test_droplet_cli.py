"""Tests for ``hermes droplet`` (VPS hop) argv handling and profile name guardrails."""

import pytest


def test_resolve_agent_droplet_script_exists():
    from hermes_cli.main import _resolve_agent_droplet_script

    p = _resolve_agent_droplet_script()
    assert p is not None and p.is_file()
    assert p.name == "agent-droplet"


def test_rewrite_mistaken_profile_droplet_argv():
    from hermes_cli.main import _rewrite_mistaken_profile_droplet_argv

    assert _rewrite_mistaken_profile_droplet_argv(["-p", "droplet"]) == ["droplet"]
    assert _rewrite_mistaken_profile_droplet_argv(["--profile", "Droplet"]) == ["droplet"]
    assert _rewrite_mistaken_profile_droplet_argv(["--profile=droplet"]) == ["droplet"]
    assert _rewrite_mistaken_profile_droplet_argv(["-p", "droplet", "tui"]) == ["tui", "droplet"]
    assert _rewrite_mistaken_profile_droplet_argv(["chat"]) is None
    assert _rewrite_mistaken_profile_droplet_argv(["-p", "chief-orchestrator", "tui"]) is None


def test_strip_trailing_droplet_hop_argv():
    from hermes_cli.main import _strip_trailing_droplet_hop_argv

    assert _strip_trailing_droplet_hop_argv(["droplet"]) == []
    assert _strip_trailing_droplet_hop_argv(["chat", "droplet"]) == ["chat"]
    assert _strip_trailing_droplet_hop_argv(["-p", "droplet"]) is None
    assert _strip_trailing_droplet_hop_argv(["--profile", "droplet"]) is None
    assert _strip_trailing_droplet_hop_argv(["profile", "list"]) is None
    assert _strip_trailing_droplet_hop_argv([]) is None


def test_resolve_agent_operator_script_exists():
    from hermes_cli.main import _resolve_agent_operator_script

    p = _resolve_agent_operator_script()
    assert p is not None and p.is_file()
    assert p.name == "agent-operator"


def test_strip_trailing_operator_hop_argv():
    from hermes_cli.main import _strip_trailing_operator_hop_argv

    assert _strip_trailing_operator_hop_argv(["operator"]) == []
    assert _strip_trailing_operator_hop_argv(["chat", "operator"]) == ["chat"]
    assert _strip_trailing_operator_hop_argv(["-p", "operator"]) is None
    assert _strip_trailing_operator_hop_argv(["--profile", "operator"]) is None
    assert _strip_trailing_operator_hop_argv(["profile", "list"]) is None
    assert _strip_trailing_operator_hop_argv([]) is None


def test_validate_profile_name_rejects_droplet():
    from hermes_cli.profiles import validate_profile_name

    with pytest.raises(ValueError, match="SSH"):
        validate_profile_name("droplet")
    with pytest.raises(ValueError, match="SSH"):
        validate_profile_name("Droplet")


def test_resolve_profile_env_droplet_rejected_at_validate(tmp_path, monkeypatch):
    from hermes_cli.profiles import resolve_profile_env

    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    with pytest.raises(ValueError, match="SSH"):
        resolve_profile_env("droplet")
