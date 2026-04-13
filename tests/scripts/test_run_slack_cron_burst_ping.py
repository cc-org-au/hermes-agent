"""--ping mode on run_slack_cron_burst_now (Slack delivery smoke, no LLM)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

REPO = Path(__file__).resolve().parents[2]
BURST = REPO / "memory" / "core" / "scripts" / "core" / "run_slack_cron_burst_now.py"


def _load_main():
    spec = importlib.util.spec_from_file_location("run_slack_cron_burst_now", BURST)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod.main


@pytest.fixture
def burst_main():
    return _load_main()


def test_ping_delivers_once_per_slack_job(
    burst_main,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    home = tmp_path / ".hermes"
    (home / "cron").mkdir(parents=True)
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.chdir(REPO)
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))

    jobs = [
        {"id": "a1", "name": "daily-a", "deliver": "slack:C111"},
        {"id": "b2", "name": "daily-b", "deliver": "slack:C222"},
    ]
    with patch("cron.jobs.load_jobs", return_value=jobs):
        with patch("cron.delivery.deliver_cron_result", return_value=True) as send:
            monkeypatch.setattr(sys, "argv", ["x", "--ping", "hello test"])
            assert burst_main() == 0
            assert send.call_count == 2
            send.assert_any_call(jobs[0], "hello test")
            send.assert_any_call(jobs[1], "hello test")
