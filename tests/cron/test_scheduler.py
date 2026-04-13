"""Tests for cron/scheduler.py — origin resolution, delivery routing, and error logging."""

import json
import logging
import os
import sys
import types
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

# run_agent imports ``fire`` at module level; CI/slim venv may omit it.
if "fire" not in sys.modules:
    sys.modules["fire"] = types.ModuleType("fire")

from cron.scheduler import (
    _resolve_origin,
    _resolve_delivery_target,
    _deliver_result,
    run_job,
    SILENT_MARKER,
    _build_job_prompt,
    _delivery_content_fingerprint,
    sanitize_cron_deliver_content,
    format_cron_delivery_with_headline,
    _cron_read_limits,
)


def _expected_tick_deliver_fingerprint(job: dict, raw_body: str, *, success: bool = True) -> str:
    """Fingerprint after the same sanitize + headline path as tick()."""
    max_chars, _ = _cron_read_limits()
    sanitized, skip = sanitize_cron_deliver_content(raw_body, max_chars)
    assert not skip
    final = format_cron_delivery_with_headline(job, sanitized, success=success)
    return _delivery_content_fingerprint(final)


class TestResolveOrigin:
    def test_full_origin(self):
        job = {
            "origin": {
                "platform": "telegram",
                "chat_id": "123456",
                "chat_name": "Test Chat",
                "thread_id": "42",
            }
        }
        result = _resolve_origin(job)
        assert isinstance(result, dict)
        assert result == job["origin"]
        assert result["platform"] == "telegram"
        assert result["chat_id"] == "123456"
        assert result["chat_name"] == "Test Chat"
        assert result["thread_id"] == "42"

    def test_no_origin(self):
        assert _resolve_origin({}) is None
        assert _resolve_origin({"origin": None}) is None

    def test_missing_platform(self):
        job = {"origin": {"chat_id": "123"}}
        assert _resolve_origin(job) is None

    def test_missing_chat_id(self):
        job = {"origin": {"platform": "telegram"}}
        assert _resolve_origin(job) is None

    def test_empty_origin(self):
        job = {"origin": {}}
        assert _resolve_origin(job) is None


class TestResolveDeliveryTarget:
    def test_origin_delivery_preserves_thread_id(self):
        job = {
            "deliver": "origin",
            "origin": {
                "platform": "telegram",
                "chat_id": "-1001",
                "thread_id": "17585",
            },
        }

        assert _resolve_delivery_target(job) == {
            "platform": "telegram",
            "chat_id": "-1001",
            "thread_id": "17585",
        }

    def test_explicit_telegram_topic_target_with_thread_id(self):
        """deliver: 'telegram:chat_id:thread_id' parses correctly."""
        job = {
            "deliver": "telegram:-1003724596514:17",
        }
        assert _resolve_delivery_target(job) == {
            "platform": "telegram",
            "chat_id": "-1003724596514",
            "thread_id": "17",
        }

    def test_explicit_telegram_chat_id_without_thread_id(self):
        """deliver: 'telegram:chat_id' sets thread_id to None."""
        job = {
            "deliver": "telegram:-1003724596514",
        }
        assert _resolve_delivery_target(job) == {
            "platform": "telegram",
            "chat_id": "-1003724596514",
            "thread_id": None,
        }

    def test_human_friendly_label_resolved_via_channel_directory(self):
        """deliver: 'whatsapp:Alice (dm)' resolves to the real JID."""
        job = {"deliver": "whatsapp:Alice (dm)"}
        with patch(
            "gateway.channel_directory.resolve_channel_name",
            return_value="12345678901234@lid",
        ):
            result = _resolve_delivery_target(job)
        assert result == {
            "platform": "whatsapp",
            "chat_id": "12345678901234@lid",
            "thread_id": None,
        }

    def test_human_friendly_label_without_suffix_resolved(self):
        """deliver: 'telegram:My Group' resolves without display suffix."""
        job = {"deliver": "telegram:My Group"}
        with patch(
            "gateway.channel_directory.resolve_channel_name",
            return_value="-1009999",
        ):
            result = _resolve_delivery_target(job)
        assert result == {
            "platform": "telegram",
            "chat_id": "-1009999",
            "thread_id": None,
        }

    def test_raw_id_not_mangled_when_directory_returns_none(self):
        """deliver: 'whatsapp:12345@lid' passes through when directory has no match."""
        job = {"deliver": "whatsapp:12345@lid"}
        with patch(
            "gateway.channel_directory.resolve_channel_name",
            return_value=None,
        ):
            result = _resolve_delivery_target(job)
        assert result == {
            "platform": "whatsapp",
            "chat_id": "12345@lid",
            "thread_id": None,
        }

    def test_bare_platform_uses_matching_origin_chat(self):
        job = {
            "deliver": "telegram",
            "origin": {
                "platform": "telegram",
                "chat_id": "-1001",
                "thread_id": "17585",
            },
        }

        assert _resolve_delivery_target(job) == {
            "platform": "telegram",
            "chat_id": "-1001",
            "thread_id": "17585",
        }

    def test_bare_platform_falls_back_to_home_channel(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_HOME_CHANNEL", "-2002")
        job = {
            "deliver": "telegram",
            "origin": {
                "platform": "discord",
                "chat_id": "abc",
            },
        }

        assert _resolve_delivery_target(job) == {
            "platform": "telegram",
            "chat_id": "-2002",
            "thread_id": None,
        }


class TestDeliverResultWrapping:
    """Verify that cron deliveries are wrapped with header/footer and no longer mirrored."""

    def test_delivery_wraps_content_with_header_and_footer(self):
        """Delivered content should include task name header and agent-invisible note."""
        from gateway.config import Platform

        pconfig = MagicMock()
        pconfig.enabled = True
        mock_cfg = MagicMock()
        mock_cfg.platforms = {Platform.TELEGRAM: pconfig}

        with patch("gateway.config.load_gateway_config", return_value=mock_cfg), \
             patch("tools.send_message_tool._send_to_platform", new=AsyncMock(return_value={"success": True})) as send_mock:
            job = {
                "id": "test-job",
                "name": "daily-report",
                "deliver": "origin",
                "origin": {"platform": "telegram", "chat_id": "123"},
            }
            _deliver_result(job, "Here is today's summary.")

        send_mock.assert_called_once()
        sent_content = send_mock.call_args.kwargs.get("content") or send_mock.call_args[0][-1]
        assert "Cronjob Response: daily-report" in sent_content
        assert "-------------" in sent_content
        assert "Here is today's summary." in sent_content
        assert "The agent cannot see this message" in sent_content

    def test_delivery_uses_job_id_when_no_name(self):
        """When a job has no name, the wrapper should fall back to job id."""
        from gateway.config import Platform

        pconfig = MagicMock()
        pconfig.enabled = True
        mock_cfg = MagicMock()
        mock_cfg.platforms = {Platform.TELEGRAM: pconfig}

        with patch("gateway.config.load_gateway_config", return_value=mock_cfg), \
             patch("tools.send_message_tool._send_to_platform", new=AsyncMock(return_value={"success": True})) as send_mock:
            job = {
                "id": "abc-123",
                "deliver": "origin",
                "origin": {"platform": "telegram", "chat_id": "123"},
            }
            _deliver_result(job, "Output.")

        sent_content = send_mock.call_args.kwargs.get("content") or send_mock.call_args[0][-1]
        assert "Cronjob Response: abc-123" in sent_content

    def test_delivery_skips_wrapping_when_config_disabled(self):
        """When cron.wrap_response is false, deliver raw content without header/footer."""
        from gateway.config import Platform

        pconfig = MagicMock()
        pconfig.enabled = True
        mock_cfg = MagicMock()
        mock_cfg.platforms = {Platform.TELEGRAM: pconfig}

        with patch("gateway.config.load_gateway_config", return_value=mock_cfg), \
             patch("tools.send_message_tool._send_to_platform", new=AsyncMock(return_value={"success": True})) as send_mock, \
             patch("cron.delivery.load_config", return_value={"cron": {"wrap_response": False}}):
            job = {
                "id": "test-job",
                "name": "daily-report",
                "deliver": "origin",
                "origin": {"platform": "telegram", "chat_id": "123"},
            }
            _deliver_result(job, "Clean output only.")

        send_mock.assert_called_once()
        sent_content = send_mock.call_args.kwargs.get("content") or send_mock.call_args[0][-1]
        assert sent_content == "Clean output only."
        assert "Cronjob Response" not in sent_content
        assert "The agent cannot see" not in sent_content

    def test_no_mirror_to_session_call(self):
        """Cron deliveries should NOT mirror into the gateway session."""
        from gateway.config import Platform

        pconfig = MagicMock()
        pconfig.enabled = True
        mock_cfg = MagicMock()
        mock_cfg.platforms = {Platform.TELEGRAM: pconfig}

        with patch("gateway.config.load_gateway_config", return_value=mock_cfg), \
             patch("tools.send_message_tool._send_to_platform", new=AsyncMock(return_value={"success": True})), \
             patch("gateway.mirror.mirror_to_session") as mirror_mock:
            job = {
                "id": "test-job",
                "deliver": "origin",
                "origin": {"platform": "telegram", "chat_id": "123"},
            }
            _deliver_result(job, "Hello!")

        mirror_mock.assert_not_called()

    def test_origin_delivery_preserves_thread_id(self):
        """Origin delivery should forward thread_id to the send helper."""
        from gateway.config import Platform

        pconfig = MagicMock()
        pconfig.enabled = True
        mock_cfg = MagicMock()
        mock_cfg.platforms = {Platform.TELEGRAM: pconfig}

        job = {
            "id": "test-job",
            "name": "topic-job",
            "deliver": "origin",
            "origin": {
                "platform": "telegram",
                "chat_id": "-1001",
                "thread_id": "17585",
            },
        }

        with patch("gateway.config.load_gateway_config", return_value=mock_cfg), \
             patch("tools.send_message_tool._send_to_platform", new=AsyncMock(return_value={"success": True})) as send_mock:
            _deliver_result(job, "hello")

        send_mock.assert_called_once()
        assert send_mock.call_args.kwargs["thread_id"] == "17585"


class TestRunJobSessionPersistence:
    def test_run_job_passes_session_db_and_cron_platform(self, tmp_path):
        job = {
            "id": "test-job",
            "name": "test",
            "prompt": "hello",
        }
        fake_db = MagicMock()

        with patch("cron.scheduler._hermes_home", tmp_path), \
             patch("cron.scheduler._resolve_origin", return_value=None), \
             patch("cron.delivery.load_config", return_value={"cron": {"max_agent_turns": 12, "delivery_max_chars": 600}}), \
             patch("dotenv.load_dotenv"), \
             patch("hermes_state.SessionDB", return_value=fake_db), \
             patch(
                 "hermes_cli.runtime_provider.resolve_runtime_provider",
                 return_value={
                     "api_key": "test-key",
                     "base_url": "https://example.invalid/v1",
                     "provider": "openrouter",
                     "api_mode": "chat_completions",
                 },
             ), \
             patch("run_agent.AIAgent") as mock_agent_cls:
            mock_agent = MagicMock()
            mock_agent.run_conversation.return_value = {"final_response": "ok"}
            mock_agent_cls.return_value = mock_agent

            success, output, final_response, error = run_job(job)

        assert success is True
        assert error is None
        assert final_response == "ok"
        assert "ok" in output

        kwargs = mock_agent_cls.call_args.kwargs
        assert kwargs["session_db"] is fake_db
        assert kwargs["platform"] == "cron"
        assert kwargs["session_id"].startswith("cron_test-job_")
        assert kwargs.get("max_iterations") == 12
        for _ts in ("web", "browser", "cronjob", "messaging"):
            assert _ts in (kwargs.get("disabled_toolsets") or [])
        fake_db.end_session.assert_called_once()
        call_args = fake_db.end_session.call_args
        assert call_args[0][0].startswith("cron_test-job_")
        assert call_args[0][1] == "cron_complete"
        fake_db.close.assert_called_once()

    def test_run_job_empty_response_returns_empty_not_placeholder(self, tmp_path):
        """Empty final_response should stay empty for delivery logic (issue #2234).
        
        The placeholder '(No response generated)' should only appear in the
        output log, not in the returned final_response that's used for delivery.
        """
        job = {
            "id": "silent-job",
            "name": "silent test",
            "prompt": "do work via tools only",
        }
        fake_db = MagicMock()

        with patch("cron.scheduler._hermes_home", tmp_path), \
             patch("cron.scheduler._resolve_origin", return_value=None), \
             patch("dotenv.load_dotenv"), \
             patch("hermes_state.SessionDB", return_value=fake_db), \
             patch(
                 "hermes_cli.runtime_provider.resolve_runtime_provider",
                 return_value={
                     "api_key": "test-key",
                     "base_url": "https://example.invalid/v1",
                     "provider": "openrouter",
                     "api_mode": "chat_completions",
                 },
             ), \
             patch("run_agent.AIAgent") as mock_agent_cls:
            mock_agent = MagicMock()
            # Agent did work via tools but returned no text
            mock_agent.run_conversation.return_value = {"final_response": ""}
            mock_agent_cls.return_value = mock_agent

            success, output, final_response, error = run_job(job)

        assert success is True
        assert error is None
        # final_response should be empty for delivery logic to skip
        assert final_response == ""
        # But the output log should show the placeholder
        assert "(No response generated)" in output

    def test_slack_role_job_disables_mutating_toolsets(self, tmp_path):
        job = {
            "id": "role-job",
            "name": "daily-slack-role-status-risk-and-insights-director-C123",
            "prompt": "hello",
        }
        fake_db = MagicMock()

        with patch("cron.scheduler._hermes_home", tmp_path), \
             patch("cron.scheduler._resolve_origin", return_value=None), \
             patch("dotenv.load_dotenv"), \
             patch("hermes_state.SessionDB", return_value=fake_db), \
             patch(
                 "hermes_cli.runtime_provider.resolve_runtime_provider",
                 return_value={
                     "api_key": "test-key",
                     "base_url": "https://example.invalid/v1",
                     "provider": "openrouter",
                     "api_mode": "chat_completions",
                 },
             ), \
             patch("run_agent.AIAgent") as mock_agent_cls:
            mock_agent = MagicMock()
            mock_agent.run_conversation.return_value = {"final_response": "ok"}
            mock_agent_cls.return_value = mock_agent

            success, output, final_response, error = run_job(job)

        assert success is True
        assert error is None
        assert final_response == "ok"
        disabled = set(mock_agent_cls.call_args.kwargs.get("disabled_toolsets") or [])
        for toolset in (
            "terminal",
            "file",
            "delegation",
            "code_execution",
            "memory",
            "session_search",
            "skills",
            "hermes_core",
            "todo",
        ):
            assert toolset in disabled

    def test_run_job_sets_auto_delivery_env_from_dotenv_home_channel(self, tmp_path, monkeypatch):
        job = {
            "id": "test-job",
            "name": "test",
            "prompt": "hello",
            "deliver": "telegram",
        }
        fake_db = MagicMock()
        seen = {}

        (tmp_path / ".env").write_text("TELEGRAM_HOME_CHANNEL=-2002\n")
        monkeypatch.delenv("TELEGRAM_HOME_CHANNEL", raising=False)
        monkeypatch.delenv("HERMES_CRON_AUTO_DELIVER_PLATFORM", raising=False)
        monkeypatch.delenv("HERMES_CRON_AUTO_DELIVER_CHAT_ID", raising=False)
        monkeypatch.delenv("HERMES_CRON_AUTO_DELIVER_THREAD_ID", raising=False)

        class FakeAgent:
            def __init__(self, *args, **kwargs):
                pass

            def run_conversation(self, *args, **kwargs):
                seen["platform"] = os.getenv("HERMES_CRON_AUTO_DELIVER_PLATFORM")
                seen["chat_id"] = os.getenv("HERMES_CRON_AUTO_DELIVER_CHAT_ID")
                seen["thread_id"] = os.getenv("HERMES_CRON_AUTO_DELIVER_THREAD_ID")
                return {"final_response": "ok"}

        with patch("cron.scheduler._hermes_home", tmp_path), \
             patch("hermes_state.SessionDB", return_value=fake_db), \
             patch(
                 "hermes_cli.runtime_provider.resolve_runtime_provider",
                 return_value={
                     "api_key": "***",
                     "base_url": "https://example.invalid/v1",
                     "provider": "openrouter",
                     "api_mode": "chat_completions",
                 },
             ), \
             patch("run_agent.AIAgent", FakeAgent):
            success, output, final_response, error = run_job(job)

        assert success is True
        assert error is None
        assert final_response == "ok"
        assert "ok" in output
        assert seen == {
            "platform": "telegram",
            "chat_id": "-2002",
            "thread_id": None,
        }
        assert os.getenv("HERMES_CRON_AUTO_DELIVER_PLATFORM") is None
        assert os.getenv("HERMES_CRON_AUTO_DELIVER_CHAT_ID") is None
        assert os.getenv("HERMES_CRON_AUTO_DELIVER_THREAD_ID") is None
        fake_db.close.assert_called_once()


class TestRunJobConfigLogging:
    """Verify that config.yaml parse failures are logged, not silently swallowed."""

    def test_bad_config_yaml_is_logged(self, caplog, tmp_path):
        """When config.yaml is malformed, a warning should be logged."""
        bad_yaml = tmp_path / "config.yaml"
        bad_yaml.write_text("invalid: yaml: [[[bad")

        job = {
            "id": "test-job",
            "name": "test",
            "prompt": "hello",
        }

        with patch("cron.scheduler._hermes_home", tmp_path), \
             patch("cron.scheduler._resolve_origin", return_value=None), \
             patch("dotenv.load_dotenv"), \
             patch("run_agent.AIAgent") as mock_agent_cls:
            mock_agent = MagicMock()
            mock_agent.run_conversation.return_value = {"final_response": "ok"}
            mock_agent_cls.return_value = mock_agent

            with caplog.at_level(logging.WARNING, logger="cron.scheduler"):
                run_job(job)

        assert any("failed to load config.yaml" in r.message for r in caplog.records), \
            f"Expected 'failed to load config.yaml' warning in logs, got: {[r.message for r in caplog.records]}"

    def test_bad_prefill_messages_is_logged(self, caplog, tmp_path):
        """When the prefill messages file contains invalid JSON, a warning should be logged."""
        # Valid config.yaml that points to a bad prefill file
        config_yaml = tmp_path / "config.yaml"
        config_yaml.write_text("prefill_messages_file: prefill.json\n")

        bad_prefill = tmp_path / "prefill.json"
        bad_prefill.write_text("{not valid json!!!")

        job = {
            "id": "test-job",
            "name": "test",
            "prompt": "hello",
        }

        with patch("cron.scheduler._hermes_home", tmp_path), \
             patch("cron.scheduler._resolve_origin", return_value=None), \
             patch("dotenv.load_dotenv"), \
             patch("run_agent.AIAgent") as mock_agent_cls:
            mock_agent = MagicMock()
            mock_agent.run_conversation.return_value = {"final_response": "ok"}
            mock_agent_cls.return_value = mock_agent

            with caplog.at_level(logging.WARNING, logger="cron.scheduler"):
                run_job(job)

        assert any("failed to parse prefill messages" in r.message for r in caplog.records), \
            f"Expected 'failed to parse prefill messages' warning in logs, got: {[r.message for r in caplog.records]}"


class TestRunJobPerJobOverrides:
    def test_job_level_model_provider_and_base_url_overrides_are_used(self, tmp_path):
        config_yaml = tmp_path / "config.yaml"
        config_yaml.write_text(
            "model:\n"
            "  default: gpt-5.4\n"
            "  provider: openai-codex\n"
            "  base_url: https://chatgpt.com/backend-api/codex\n"
        )

        job = {
            "id": "briefing-job",
            "name": "briefing",
            "prompt": "hello",
            "model": "perplexity/sonar-pro",
            "provider": "custom",
            "base_url": "http://127.0.0.1:4000/v1",
        }

        fake_db = MagicMock()
        fake_runtime = {
            "provider": "openrouter",
            "api_mode": "chat_completions",
            "base_url": "http://127.0.0.1:4000/v1",
            "api_key": "***",
        }

        with patch("cron.scheduler._hermes_home", tmp_path), \
             patch("cron.scheduler._resolve_origin", return_value=None), \
             patch("dotenv.load_dotenv"), \
             patch("hermes_state.SessionDB", return_value=fake_db), \
             patch("hermes_cli.runtime_provider.resolve_runtime_provider", return_value=fake_runtime) as runtime_mock, \
             patch("run_agent.AIAgent") as mock_agent_cls:
            mock_agent = MagicMock()
            mock_agent.run_conversation.return_value = {"final_response": "ok"}
            mock_agent_cls.return_value = mock_agent

            success, output, final_response, error = run_job(job)

        assert success is True
        assert error is None
        assert final_response == "ok"
        assert "ok" in output
        runtime_mock.assert_called_once_with(
            requested="custom",
            explicit_base_url="http://127.0.0.1:4000/v1",
        )
        assert mock_agent_cls.call_args.kwargs["model"] == "perplexity/sonar-pro"
        fake_db.close.assert_called_once()


class TestRunJobSkillBacked:
    def test_run_job_loads_skill_and_disables_recursive_cron_tools(self, tmp_path):
        job = {
            "id": "skill-job",
            "name": "skill test",
            "prompt": "Check the feeds and summarize anything new.",
            "skill": "blogwatcher",
        }

        fake_db = MagicMock()

        with patch("cron.scheduler._hermes_home", tmp_path), \
             patch("cron.scheduler._resolve_origin", return_value=None), \
             patch("dotenv.load_dotenv"), \
             patch("hermes_state.SessionDB", return_value=fake_db), \
             patch(
                 "hermes_cli.runtime_provider.resolve_runtime_provider",
                 return_value={
                     "api_key": "***",
                     "base_url": "https://example.invalid/v1",
                     "provider": "openrouter",
                     "api_mode": "chat_completions",
                 },
             ), \
             patch("tools.skills_tool.skill_view", return_value=json.dumps({"success": True, "content": "# Blogwatcher\nFollow this skill."})), \
             patch("run_agent.AIAgent") as mock_agent_cls:
            mock_agent = MagicMock()
            mock_agent.run_conversation.return_value = {"final_response": "ok"}
            mock_agent_cls.return_value = mock_agent

            success, output, final_response, error = run_job(job)

        assert success is True
        assert error is None
        assert final_response == "ok"

        kwargs = mock_agent_cls.call_args.kwargs
        assert "cronjob" in (kwargs["disabled_toolsets"] or [])

        prompt_arg = mock_agent.run_conversation.call_args.args[0]
        assert "blogwatcher" in prompt_arg
        assert "Follow this skill" in prompt_arg
        assert "Check the feeds and summarize anything new." in prompt_arg

    def test_run_job_loads_multiple_skills_in_order(self, tmp_path):
        job = {
            "id": "multi-skill-job",
            "name": "multi skill test",
            "prompt": "Combine the results.",
            "skills": ["blogwatcher", "find-nearby"],
        }

        fake_db = MagicMock()

        def _skill_view(name):
            return json.dumps({"success": True, "content": f"# {name}\nInstructions for {name}."})

        with patch("cron.scheduler._hermes_home", tmp_path), \
             patch("cron.scheduler._resolve_origin", return_value=None), \
             patch("dotenv.load_dotenv"), \
             patch("hermes_state.SessionDB", return_value=fake_db), \
             patch(
                 "hermes_cli.runtime_provider.resolve_runtime_provider",
                 return_value={
                     "api_key": "***",
                     "base_url": "https://example.invalid/v1",
                     "provider": "openrouter",
                     "api_mode": "chat_completions",
                 },
             ), \
             patch("tools.skills_tool.skill_view", side_effect=_skill_view) as skill_view_mock, \
             patch("run_agent.AIAgent") as mock_agent_cls:
            mock_agent = MagicMock()
            mock_agent.run_conversation.return_value = {"final_response": "ok"}
            mock_agent_cls.return_value = mock_agent

            success, output, final_response, error = run_job(job)

        assert success is True
        assert error is None
        assert final_response == "ok"
        assert skill_view_mock.call_count == 2
        assert [call.args[0] for call in skill_view_mock.call_args_list] == ["blogwatcher", "find-nearby"]

        prompt_arg = mock_agent.run_conversation.call_args.args[0]
        assert prompt_arg.index("blogwatcher") < prompt_arg.index("find-nearby")
        assert "Instructions for blogwatcher." in prompt_arg
        assert "Instructions for find-nearby." in prompt_arg
        assert "Combine the results." in prompt_arg


class TestDeliveryDedupeNormalization:
    """Stable fingerprints across volatile timestamps in cron agent output."""

    def test_updated_line_stripped(self):
        a = "Open SEV2: 3 active\nUpdated: 2026-04-13 10:19:20.041296+10:00"
        b = "Open SEV2: 3 active\nUpdated: 2026-04-14 08:00:00+10:00"
        assert _delivery_content_fingerprint(a) == _delivery_content_fingerprint(b)

    def test_as_of_clause_stripped(self):
        a = "Escalations cleared: 0\nNo pending (as of 2026-04-13 12:11 AEST)."
        b = "Escalations cleared: 0\nNo pending (as of 2026-04-14 09:00 AEST)."
        assert _delivery_content_fingerprint(a) == _delivery_content_fingerprint(b)

    def test_meaningful_change_changes_fingerprint(self):
        a = "Open SEV2: 3 active"
        b = "Open SEV2: 4 active"
        assert _delivery_content_fingerprint(a) != _delivery_content_fingerprint(b)


class TestTickDeliveryDedupe:
    """Skip messaging when normalized body matches last successful delivery."""

    def test_skips_when_fingerprint_matches_previous(self):
        body_a = "Status ok\nUpdated: 2026-04-10T10:00:00+10:00"
        body_b = "Status ok\nUpdated: 2026-04-11T11:00:00+10:00"
        job = {
            "id": "dedupe-job",
            "name": "dedupe",
            "deliver": "origin",
            "origin": {"platform": "telegram", "chat_id": "1"},
        }
        fp = _expected_tick_deliver_fingerprint(job, body_a)
        job["last_deliver_fingerprint"] = fp
        mark_mock = MagicMock()
        deliver_mock = MagicMock(return_value=True)
        with patch("cron.scheduler.get_due_jobs", return_value=[job]), \
             patch("cron.scheduler.advance_next_run"), \
             patch("cron.scheduler.run_job", return_value=(True, "# o", body_b, None)), \
             patch("cron.scheduler.save_job_output", return_value="/tmp/x"), \
             patch("cron.scheduler._deliver_result", deliver_mock), \
             patch("cron.scheduler.mark_job_run", mark_mock):
            from cron.scheduler import tick

            tick(verbose=False)

        deliver_mock.assert_not_called()
        mark_mock.assert_called_once_with(
            "dedupe-job",
            True,
            None,
            deliver_fingerprint_update=None,
            state_gate_fingerprint_update=None,
        )

    def test_delivers_when_no_prior_fingerprint(self):
        job = {
            "id": "dedupe-job-2",
            "name": "dedupe",
            "deliver": "origin",
            "origin": {"platform": "telegram", "chat_id": "1"},
        }
        mark_mock = MagicMock()
        deliver_mock = MagicMock(return_value=True)
        body = "New alert\nUpdated: 2026-04-10T10:00:00+10:00"
        fp = _expected_tick_deliver_fingerprint(job, body)
        with patch("cron.scheduler.get_due_jobs", return_value=[job]), \
             patch("cron.scheduler.advance_next_run"), \
             patch("cron.scheduler.run_job", return_value=(True, "# o", body, None)), \
             patch("cron.scheduler.save_job_output", return_value="/tmp/x"), \
             patch("cron.scheduler._deliver_result", deliver_mock), \
             patch("cron.scheduler.mark_job_run", mark_mock):
            from cron.scheduler import tick

            tick(verbose=False)

        deliver_mock.assert_called_once()
        assert mark_mock.call_args.kwargs.get("deliver_fingerprint_update") == fp


class TestSilentDelivery:
    """Verify that [SILENT] responses suppress delivery while still saving output."""

    def _make_job(self):
        return {
            "id": "monitor-job",
            "name": "monitor",
            "deliver": "origin",
            "origin": {"platform": "telegram", "chat_id": "123"},
        }

    def test_normal_response_delivers(self):
        with patch("cron.scheduler.get_due_jobs", return_value=[self._make_job()]), \
             patch("cron.scheduler.run_job", return_value=(True, "# output", "Results here", None)), \
             patch("cron.scheduler.save_job_output", return_value="/tmp/out.md"), \
             patch("cron.scheduler._deliver_result") as deliver_mock, \
             patch("cron.scheduler.mark_job_run"):
            from cron.scheduler import tick
            tick(verbose=False)
        deliver_mock.assert_called_once()

    def test_silent_response_suppresses_delivery(self, caplog):
        with patch("cron.scheduler.get_due_jobs", return_value=[self._make_job()]), \
             patch("cron.scheduler.run_job", return_value=(True, "# output", "[SILENT]", None)), \
             patch("cron.scheduler.save_job_output", return_value="/tmp/out.md"), \
             patch("cron.scheduler._deliver_result") as deliver_mock, \
             patch("cron.scheduler.mark_job_run"):
            from cron.scheduler import tick
            with caplog.at_level(logging.INFO, logger="cron.scheduler"):
                tick(verbose=False)
        deliver_mock.assert_not_called()
        assert any(SILENT_MARKER in r.message for r in caplog.records)

    def test_silent_with_note_suppresses_delivery(self):
        with patch("cron.scheduler.get_due_jobs", return_value=[self._make_job()]), \
             patch("cron.scheduler.run_job", return_value=(True, "# output", "[SILENT] No changes detected", None)), \
             patch("cron.scheduler.save_job_output", return_value="/tmp/out.md"), \
             patch("cron.scheduler._deliver_result") as deliver_mock, \
             patch("cron.scheduler.mark_job_run"):
            from cron.scheduler import tick
            tick(verbose=False)
        deliver_mock.assert_not_called()

    def test_silent_is_case_insensitive(self):
        with patch("cron.scheduler.get_due_jobs", return_value=[self._make_job()]), \
             patch("cron.scheduler.run_job", return_value=(True, "# output", "[silent] nothing new", None)), \
             patch("cron.scheduler.save_job_output", return_value="/tmp/out.md"), \
             patch("cron.scheduler._deliver_result") as deliver_mock, \
             patch("cron.scheduler.mark_job_run"):
            from cron.scheduler import tick
            tick(verbose=False)
        deliver_mock.assert_not_called()

    def test_failed_job_always_delivers(self):
        """Failed jobs deliver regardless of [SILENT] in output."""
        with patch("cron.scheduler.get_due_jobs", return_value=[self._make_job()]), \
             patch("cron.scheduler.run_job", return_value=(False, "# output", "", "some error")), \
             patch("cron.scheduler.save_job_output", return_value="/tmp/out.md"), \
             patch("cron.scheduler._deliver_result") as deliver_mock, \
             patch("cron.scheduler.mark_job_run"):
            from cron.scheduler import tick
            tick(verbose=False)
        deliver_mock.assert_called_once()

    def test_output_saved_even_when_delivery_suppressed(self):
        with patch("cron.scheduler.get_due_jobs", return_value=[self._make_job()]), \
             patch("cron.scheduler.run_job", return_value=(True, "# full output", "[SILENT]", None)), \
             patch("cron.scheduler.save_job_output") as save_mock, \
             patch("cron.scheduler._deliver_result") as deliver_mock, \
             patch("cron.scheduler.mark_job_run"):
            save_mock.return_value = "/tmp/out.md"
            from cron.scheduler import tick
            tick(verbose=False)
        save_mock.assert_called_once_with("monitor-job", "# full output")
        deliver_mock.assert_not_called()


class TestCronDeliveryHeadline:
    """First line summarizes job + inferred status before detail body."""

    def test_auto_headline_from_job_name_and_body(self):
        job = {"id": "x", "name": "gateway-watchdog-status"}
        body = "ok all_connected=whatsapp,telegram,slack"
        out = format_cron_delivery_with_headline(job, body, success=True)
        lines = out.splitlines()
        assert lines[0] == "Gateway Watchdog Status — Nominal"
        assert "ok all_connected" in out

    def test_custom_deliver_summary_override(self):
        job = {"id": "x", "name": "ignored", "deliver_summary": "Custom Prefix — OK"}
        body = "Details here."
        out = format_cron_delivery_with_headline(job, body, success=True)
        assert out.startswith("Custom Prefix — OK\n")

    def test_failed_run_headline(self):
        job = {"id": "x", "name": "nightly", "deliver_summary": "Nightly"}
        body = "TimeoutError: …"
        out = format_cron_delivery_with_headline(job, body, success=False)
        assert out.startswith("Nightly — Run failed\n")


class TestSanitizeCronDeliverContent:
    """Strip chain-of-thought; keep short operational lines."""

    def test_long_reasoning_with_alert_tail_keeps_tail(self):
        raw = (
            "Based on the current state file, no change was detected.\n\n"
            "WhatsApp gateway recovered\nConnected: whatsapp, telegram, slack"
        )
        body, skip = sanitize_cron_deliver_content(raw, 600)
        assert skip is False
        assert "Based on" not in body
        assert "WhatsApp gateway recovered" in body

    def test_silent_intent_paragraph_suppresses(self):
        raw = (
            "The gateway was down. Since nothing changed I will respond with [SILENT]."
        )
        _body, skip = sanitize_cron_deliver_content(raw, 600)
        assert skip is True

    def test_escalation_resolved_prose_with_silent_suppresses(self):
        """Models often paste paragraphs ending in 'respond with [SILENT]' — never deliver."""
        raw = (
            "Based on the current state file and recent logs, there has been no change in the "
            "escalation status since the last report. The previous status was \"resolved,\" and "
            "no new critical issues or severity changes have occurred. Therefore, I will respond "
            "with [SILENT] to comply with the protocol and avoid redundant messaging."
        )
        _body, skip = sanitize_cron_deliver_content(raw, 600)
        assert skip is True

    def test_truncated_based_on_filtered_as_cot(self):
        raw = (
            "ased on the current state file, nothing changed. Therefore, I will respond with [SILENT]."
        )
        _body, skip = sanitize_cron_deliver_content(raw, 600)
        assert skip is True

    def test_audio_hallucination_stripped_then_vague_recovery_suppresses(self):
        raw = (
            "The WhatsApp gateway connectivity has recovered and is now UP, with all platforms "
            "operational. I have generated an alert audio message for this event."
        )
        _body, skip = sanitize_cron_deliver_content(raw, 600)
        assert skip is True

    def test_recovery_with_watchdog_evidence_delivers(self):
        raw = "WhatsApp gateway recovered. watchdog-check: ok all_connected=whatsapp,telegram,slack"
        body, skip = sanitize_cron_deliver_content(raw, 600)
        assert skip is False
        assert "all_connected" in body

    def test_exact_silent_suppresses(self):
        _body, skip = sanitize_cron_deliver_content("[SILENT]", 600)
        assert skip is True

    def test_devanagari_transliterated_silent_suppresses(self):
        """Models sometimes spell SILENT in non-Latin scripts instead of ASCII [SILENT]."""
        _body, skip = sanitize_cron_deliver_content("[एसआईएलेंट]", 600)
        assert skip is True

    def test_meta_fluff_sending_message_nothing_to_update_suppresses(self):
        raw = (
            "I am sending a message to tell you there is nothing to update at this time."
        )
        _body, skip = sanitize_cron_deliver_content(raw, 600)
        assert skip is True

    def test_meta_fluff_another_message_nothing_changed_suppresses(self):
        raw = "Here is another message saying nothing has changed since the last check."
        _body, skip = sanitize_cron_deliver_content(raw, 600)
        assert skip is True

    def test_return_exactly_silent_suppresses(self):
        raw = (
            "The current state indicates no change in escalation status since the last run. "
            "Therefore, I will return exactly [SILENT]."
        )
        _body, skip = sanitize_cron_deliver_content(raw, 600)
        assert skip is True

    def test_system_remains_silent_prose_suppresses(self):
        raw = (
            "The gateway platforms are all connected (whatsapp, telegram, slack) with "
            "no change in state since the last check. No alert is necessary, "
            "and the system remains silent."
        )
        _body, skip = sanitize_cron_deliver_content(raw, 600)
        assert skip is True

    def test_degraded_bullet_alert_delivers(self):
        raw = (
            "• The current state indicates the WhatsApp gateway is degraded — disconnected.\n"
            "• A transition event has been detected.\n"
            "• Alert: WhatsApp gateway: Degraded — unstable."
        )
        body, skip = sanitize_cron_deliver_content(raw, 600)
        assert skip is False
        assert "degraded" in body.lower()

    def test_silently_bracket_stand_in_suppresses(self):
        raw = "[Silently no change and no alert sent]"
        _body, skip = sanitize_cron_deliver_content(raw, 600)
        assert skip is True

    def test_slop_then_respond_with_silent_suppresses_entirely(self):
        raw = (
            "The current state indicates that the WhatsApp gateway is down, with no active "
            "platform connections. Web search confirms ongoing issues.\n\n"
            "Given the unchanged state and the previous alert about the down status, "
            "I will not resend a message. The state has not transitioned, so "
            "I will respond with [SILENT]."
        )
        _body, skip = sanitize_cron_deliver_content(raw, 600)
        assert skip is True

    def test_delivery_envelope_only_lines_delivered(self):
        raw = (
            "Internal reasoning and web search fluff here.\n\n"
            "###HERMES_CRON_DELIVERY_JSON\n"
            '{"silent": false, "lines": ["ok all_connected=whatsapp", "gateway_state=running"]}\n'
            "###END_HERMES_CRON_DELIVERY_JSON\n"
        )
        body, skip = sanitize_cron_deliver_content(raw, 600)
        assert skip is False
        assert body == "ok all_connected=whatsapp\ngateway_state=running"
        assert "reasoning" not in body

    def test_delivery_envelope_silent_skips(self):
        raw = (
            "Narrative\n###HERMES_CRON_DELIVERY_JSON\n"
            '{"silent": true}\n'
            "###END_HERMES_CRON_DELIVERY_JSON"
        )
        _body, skip = sanitize_cron_deliver_content(raw, 600)
        assert skip is True

    def test_delivery_envelope_json_in_code_fence(self):
        raw = (
            "###HERMES_CRON_DELIVERY_JSON\n"
            "```json\n"
            '{"silent": false, "lines": ["line a"]}\n'
            "```\n"
            "###END_HERMES_CRON_DELIVERY_JSON"
        )
        body, skip = sanitize_cron_deliver_content(raw, 600)
        assert skip is False
        assert body == "line a"

    def test_strict_delivery_envelope_missing_block_suppresses(self):
        raw = "Only prose, no envelope."
        _body, skip = sanitize_cron_deliver_content(raw, 600, strict_delivery_envelope=True)
        assert skip is True

    def test_strict_delivery_envelope_invalid_json_suppresses(self):
        raw = "###HERMES_CRON_DELIVERY_JSON\nnot json\n###END_HERMES_CRON_DELIVERY_JSON"
        _body, skip = sanitize_cron_deliver_content(raw, 600, strict_delivery_envelope=True)
        assert skip is True

    def test_bare_silently_no_change_bracket_typo_suppresses(self):
        raw = "Silently no change and no alert sent]"
        _body, skip = sanitize_cron_deliver_content(raw, 600)
        assert skip is True

    def test_web_search_essay_remains_silent_no_evidence_suppresses(self):
        raw = (
            "The current state indicates that the WhatsApp gateway is down, with no active "
            "platform connections, and a recent hash for the last sent message. Web search "
            "and availability resources confirm ongoing issues.\n\n"
            "Given the unchanged state, I will not resend a message. "
            "I will respond with [SILENT]."
        )
        _body, skip = sanitize_cron_deliver_content(raw, 600)
        assert skip is True

    def test_gateway_state_remains_silent_no_watchdog_suppresses(self):
        raw = (
            "The current gateway state indicates that WhatsApp is down, with no active "
            "platform connections, consistent with the previous state. "
            "No alert has been resended since there is no transition. "
            "The system remains silent as per the rules."
        )
        _body, skip = sanitize_cron_deliver_content(raw, 600)
        assert skip is True

    def test_web_search_with_real_watchdog_still_delivers(self):
        raw = (
            "Web search says outages happen.\n"
            "watchdog-check: ok all_connected=whatsapp,telegram\n"
            "The system remains silent otherwise."
        )
        body, skip = sanitize_cron_deliver_content(raw, 600)
        assert skip is False
        assert "all_connected" in body

    def test_strict_envelope_env_overrides_config(self, monkeypatch):
        monkeypatch.setenv("HERMES_CRON_STRICT_DELIVERY_ENVELOPE", "1")
        with patch(
            "cron.delivery_envelope.load_config",
            return_value={"cron": {"strict_delivery_envelope": False}},
        ):
            from cron.delivery_envelope import cron_strict_delivery_envelope

            assert cron_strict_delivery_envelope() is True


class TestBuildJobPromptSilentHint:
    """Verify _build_job_prompt always injects deterministic JSON envelope guidance."""

    def test_hint_always_present(self):
        job = {"prompt": "Check for updates"}
        result = _build_job_prompt(job)
        assert "HERMES_CRON_DELIVERY_JSON" in result
        assert '"silent"' in result
        assert "Check for updates" in result

    def test_hint_present_even_without_prompt(self):
        job = {"prompt": ""}
        result = _build_job_prompt(job)
        assert "HERMES_CRON_DELIVERY_JSON" in result


class TestBuildJobPromptMissingSkill:
    """Verify that a missing skill logs a warning and does not crash the job."""

    def _missing_skill_view(self, name: str) -> str:
        return json.dumps({"success": False, "error": f"Skill '{name}' not found."})

    def test_missing_skill_does_not_raise(self):
        """Job should run even when a referenced skill is not installed."""
        with patch("tools.skills_tool.skill_view", side_effect=self._missing_skill_view):
            result = _build_job_prompt({"skills": ["ghost-skill"], "prompt": "do something"})
        # prompt is preserved even though skill was skipped
        assert "do something" in result

    def test_missing_skill_injects_user_notice_into_prompt(self):
        """A system notice about the missing skill is injected into the prompt."""
        with patch("tools.skills_tool.skill_view", side_effect=self._missing_skill_view):
            result = _build_job_prompt({"skills": ["ghost-skill"], "prompt": "do something"})
        assert "ghost-skill" in result
        assert "not found" in result.lower() or "skipped" in result.lower()

    def test_missing_skill_logs_warning(self, caplog):
        """A warning is logged when a skill cannot be found."""
        with caplog.at_level(logging.WARNING, logger="cron.job_prompt"):
            with patch("tools.skills_tool.skill_view", side_effect=self._missing_skill_view):
                _build_job_prompt({"name": "My Job", "skills": ["ghost-skill"], "prompt": "do something"})
        assert any("ghost-skill" in record.message for record in caplog.records)

    def test_valid_skill_loaded_alongside_missing(self):
        """A valid skill is still loaded when another skill in the list is missing."""

        def _mixed_skill_view(name: str) -> str:
            if name == "real-skill":
                return json.dumps({"success": True, "content": "Real skill content."})
            return json.dumps({"success": False, "error": f"Skill '{name}' not found."})

        with patch("tools.skills_tool.skill_view", side_effect=_mixed_skill_view):
            result = _build_job_prompt({"skills": ["ghost-skill", "real-skill"], "prompt": "go"})
        assert "Real skill content." in result
        assert "go" in result


class TestTickStateSkipGate:
    """Pre-LLM state fingerprint skips provider when semantic state is unchanged."""

    def test_skips_run_job_when_state_unchanged(self, tmp_path):
        def fake_skip(job):
            return True, "samefp"

        with patch("cron.scheduler.get_due_jobs", return_value=[{"id": "g1", "name": "g"}]), \
             patch("cron.scheduler.advance_next_run"), \
             patch("cron.scheduler.should_skip_llm_for_unchanged_state", side_effect=fake_skip), \
             patch("cron.scheduler.run_job") as run_mock, \
             patch("cron.scheduler.mark_job_run") as mark_mock, \
             patch("cron.scheduler.save_job_output"):
            from cron.scheduler import tick

            tick(verbose=False)

        run_mock.assert_not_called()
        mark_mock.assert_called_once()
        assert mark_mock.call_args.args[0] == "g1"
        assert mark_mock.call_args.kwargs.get("skip_repeat_increment") is True

    def test_runs_job_when_state_changed(self, tmp_path):
        with patch("cron.scheduler.get_due_jobs", return_value=[{"id": "g2", "name": "g"}]), \
             patch("cron.scheduler.advance_next_run"), \
             patch("cron.scheduler.should_skip_llm_for_unchanged_state", return_value=(False, "fp")), \
             patch("cron.scheduler.run_job", return_value=(True, "o", "r", None)), \
             patch("cron.scheduler.save_job_output", return_value=tmp_path / "o.md"), \
             patch("cron.scheduler.mark_job_run") as mark_mock, \
             patch("cron.scheduler._deliver_result"), \
             patch("cron.scheduler.fingerprint_for_state_skip_gate", return_value=None):
            from cron.scheduler import tick

            tick(verbose=False)

        mark_mock.assert_called_once()
        assert not mark_mock.call_args.kwargs.get("skip_repeat_increment")


class TestTickAdvanceBeforeRun:
    """Verify that tick() calls advance_next_run before run_job for crash safety."""

    def test_advance_called_before_run_job(self, tmp_path):
        """advance_next_run must be called before run_job to prevent crash-loop re-fires."""
        call_order = []

        def fake_advance(job_id):
            call_order.append(("advance", job_id))
            return True

        def fake_run_job(job):
            call_order.append(("run", job["id"]))
            return True, "output", "response", None

        fake_job = {
            "id": "test-advance",
            "name": "test",
            "prompt": "hello",
            "enabled": True,
            "schedule": {"kind": "cron", "expr": "15 6 * * *"},
        }

        with patch("cron.scheduler.get_due_jobs", return_value=[fake_job]), \
             patch("cron.scheduler.advance_next_run", side_effect=fake_advance) as adv_mock, \
             patch("cron.scheduler.run_job", side_effect=fake_run_job), \
             patch("cron.scheduler.save_job_output", return_value=tmp_path / "out.md"), \
             patch("cron.scheduler.mark_job_run"), \
             patch("cron.scheduler._deliver_result"):
            from cron.scheduler import tick
            executed = tick(verbose=False)

        assert executed == 1
        adv_mock.assert_called_once_with("test-advance")
        # advance must happen before run
        assert call_order == [("advance", "test-advance"), ("run", "test-advance")]


def test_read_cron_limits_default_and_upper_cap():
    from cron.delivery import read_cron_limits

    with patch("cron.delivery.load_config", return_value={"cron": {}}):
        mx, _ = read_cron_limits()
        assert mx == 12000
    with patch(
        "cron.delivery.load_config",
        return_value={"cron": {"delivery_max_chars": 999_999}},
    ):
        mx, _ = read_cron_limits()
        assert mx == 36000
