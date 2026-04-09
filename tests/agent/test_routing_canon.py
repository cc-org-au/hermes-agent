"""Tests for layered routing_canon loader and TurnRoutingIntent."""

from __future__ import annotations

import pytest
import yaml

from agent.routing_canon import (
    build_turn_routing_intent,
    invalidate_routing_canon_cache,
    load_merged_routing_canon,
    merge_canon_into_consultant_routing,
)


@pytest.fixture
def hermes_home(tmp_path, monkeypatch):
    home = tmp_path / ".hermes"
    home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(home))
    invalidate_routing_canon_cache()
    yield home
    invalidate_routing_canon_cache()


def test_load_merged_includes_repo_defaults(hermes_home):
    m = load_merged_routing_canon(force_reload=True)
    assert int(m.get("version") or 1) >= 1
    assert "consultant_escalation" in m
    assert "openrouter_auto" in m


def test_home_overlay_overrides(hermes_home):
    overlay = {"version": 99, "consultant_escalation": {"router_max_tokens": 123}}
    (hermes_home / "routing_canon.yaml").write_text(yaml.safe_dump(overlay), encoding="utf-8")
    m = load_merged_routing_canon(force_reload=True)
    assert m["version"] == 99
    assert m["consultant_escalation"]["router_max_tokens"] == 123


def test_merge_into_consultant_routing(hermes_home):
    cr = {"enabled": True, "mode": "hybrid"}
    out = merge_canon_into_consultant_routing(cr)
    assert "tiers_requiring_deliberation" in out
    assert isinstance(out.get("openrouter_auto_deliberation_tiers"), list)


def test_build_turn_routing_intent(hermes_home):
    class _Ag:
        _defer_opm_primary_coercion = False
        _skip_per_turn_tier_routing = False
        _opm_suppressed_for_turn = False
        _fallback_activated = False

    ag = _Ag()
    intent = build_turn_routing_intent(ag)
    assert intent.canon_version >= 1
    assert intent.manual_pipeline is False

    ag._defer_opm_primary_coercion = True
    intent2 = build_turn_routing_intent(ag)
    assert intent2.manual_pipeline is True
