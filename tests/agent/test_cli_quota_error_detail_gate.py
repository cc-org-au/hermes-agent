"""CLI-persisted suppression of repeated quota-class API error vprint blocks."""

from __future__ import annotations

from cli import HermesCLI


def test_cli_quota_error_detail_resets_when_session_id_changes():
    cli = HermesCLI.__new__(HermesCLI)
    cli.session_id = "sess-a"
    cli._cli_quota_error_detail_session_id = None
    cli._cli_quota_error_detail_emitted = False

    cli._sync_cli_quota_error_detail_session()
    assert cli._cli_quota_error_detail_session_id == "sess-a"
    assert cli._cli_quota_error_detail_emitted is False

    cli._cli_quota_error_detail_mark_shown()
    assert cli._cli_quota_error_detail_emitted is True
    assert cli._cli_quota_error_detail_should_suppress() is True

    cli._sync_cli_quota_error_detail_session()
    assert cli._cli_quota_error_detail_emitted is True

    cli.session_id = "sess-b"
    cli._sync_cli_quota_error_detail_session()
    assert cli._cli_quota_error_detail_session_id == "sess-b"
    assert cli._cli_quota_error_detail_emitted is False
    assert cli._cli_quota_error_detail_should_suppress() is False
    assert cli._cli_suppress_quota_repeat_notices is False
    assert cli._cli_blacklist_announced_providers == set()

    cli._cli_quota_ux_episode_completed()
    assert cli._cli_suppress_quota_repeat_notices is True
    assert cli._cli_quota_user_notice_should_suppress() is True
    cli._cli_provider_blacklist_mark_announced("custom")
    assert cli._cli_provider_blacklist_should_suppress("custom") is True
