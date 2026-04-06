"""Profile usage + lifecycle audit helpers."""

import json
import time
from pathlib import Path

import pytest


def test_record_and_audit_profile_usage(tmp_path, monkeypatch):
    from hermes_cli import profiles as prof

    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    root = tmp_path / ".hermes" / "profiles"
    root.mkdir(parents=True)
    (root / "idle-one").mkdir()
    (root / "chief-orchestrator").mkdir()

    prof.record_profile_usage("fresh-one", kind="test")
    lines = prof.audit_profile_lifecycle_report(idle_days=1)
    text = "\n".join(lines)
    assert "idle-one" in text or "unknown" in text.lower()
    assert "chief-orchestrator" in text

    usage_path = tmp_path / ".hermes" / ".profile_usage.json"
    assert usage_path.is_file()
    data = json.loads(usage_path.read_text(encoding="utf-8"))
    assert "fresh-one" in data.get("touches", {})


def test_audit_flags_old_touch(tmp_path, monkeypatch):
    from hermes_cli import profiles as prof

    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    root = tmp_path / ".hermes" / "profiles"
    root.mkdir(parents=True)
    (root / "stale-p").mkdir()
    usage_path = tmp_path / ".hermes" / ".profile_usage.json"
    old = int(time.time()) - 200 * 86400
    usage_path.write_text(
        json.dumps({"touches": {"stale-p": old}}),
        encoding="utf-8",
    )
    lines = prof.audit_profile_lifecycle_report(idle_days=90)
    assert any("stale-p" in ln for ln in lines)
