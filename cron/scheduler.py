"""
Cron job scheduler - executes due jobs.

Provides tick() which checks for due jobs and runs them. The gateway
calls this every 60 seconds from a background thread.

Uses a file-based lock (~/.hermes/cron/.tick.lock) so only one tick
runs at a time if multiple processes overlap.

Delivery filtering, headlines, and platform send live in cron.delivery.
Prompt assembly lives in cron.job_prompt.
"""

from __future__ import annotations

import logging
import os
import sys
import traceback
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import fcntl
except ImportError:
    fcntl = None
    try:
        import msvcrt
    except ImportError:
        msvcrt = None

from hermes_constants import get_hermes_home
from hermes_time import now as _hermes_now

from cron.delivery import (
    SILENT_MARKER,
    cron_delivery_dedupe_enabled,
    cron_strict_delivery_envelope,
    deliver_cron_result,
    delivery_content_fingerprint,
    format_cron_delivery_with_headline,
    read_cron_limits,
    resolve_delivery_target,
    resolve_origin,
    sanitize_cron_deliver_content,
)
from cron.job_prompt import build_cron_job_prompt
from cron.jobs import advance_next_run, get_due_jobs, mark_job_run, save_job_output
from cron.state_gate import fingerprint_for_state_skip_gate, should_skip_llm_for_unchanged_state

logger = logging.getLogger(__name__)

# Test / monkeypatch compatibility (historical names on this module)
_cron_delivery_dedupe_enabled = cron_delivery_dedupe_enabled
_delivery_content_fingerprint = delivery_content_fingerprint
_cron_read_limits = read_cron_limits
_deliver_result = deliver_cron_result
_resolve_origin = resolve_origin
_resolve_delivery_target = resolve_delivery_target
_build_job_prompt = build_cron_job_prompt

_hermes_home = get_hermes_home()
_LOCK_DIR = _hermes_home / "cron"
_LOCK_FILE = _LOCK_DIR / ".tick.lock"


def run_job(job: dict) -> tuple[bool, str, str, Optional[str]]:
    """
    Execute a single cron job.

    Returns:
        Tuple of (success, full_output_doc, final_response, error_message)
    """
    from run_agent import AIAgent

    _session_db = None
    try:
        from hermes_state import SessionDB

        _session_db = SessionDB()
    except Exception as e:
        logger.debug("Job '%s': SQLite session store not available: %s", job.get("id", "?"), e)

    job_id = job["id"]
    job_name = job["name"]
    prompt = _build_job_prompt(job)
    origin = _resolve_origin(job)
    _cron_session_id = f"cron_{job_id}_{_hermes_now().strftime('%Y%m%d_%H%M%S')}"

    logger.info("Running job '%s' (ID: %s)", job_name, job_id)
    logger.info("Prompt: %s", prompt[:100])

    if origin:
        os.environ["HERMES_SESSION_PLATFORM"] = origin["platform"]
        os.environ["HERMES_SESSION_CHAT_ID"] = str(origin["chat_id"])
        if origin.get("chat_name"):
            os.environ["HERMES_SESSION_CHAT_NAME"] = origin["chat_name"]

    try:
        from dotenv import load_dotenv

        try:
            load_dotenv(str(_hermes_home / ".env"), override=True, encoding="utf-8")
        except UnicodeDecodeError:
            load_dotenv(str(_hermes_home / ".env"), override=True, encoding="latin-1")

        delivery_target = _resolve_delivery_target(job)
        if delivery_target:
            os.environ["HERMES_CRON_AUTO_DELIVER_PLATFORM"] = delivery_target["platform"]
            os.environ["HERMES_CRON_AUTO_DELIVER_CHAT_ID"] = str(delivery_target["chat_id"])
            if delivery_target.get("thread_id") is not None:
                os.environ["HERMES_CRON_AUTO_DELIVER_THREAD_ID"] = str(delivery_target["thread_id"])

        model = job.get("model") or os.getenv("HERMES_MODEL") or ""

        _cfg = {}
        try:
            import yaml

            _cfg_path = str(_hermes_home / "config.yaml")
            if os.path.exists(_cfg_path):
                with open(_cfg_path) as _f:
                    _cfg = yaml.safe_load(_f) or {}
                _model_cfg = _cfg.get("model", {})
                if not job.get("model"):
                    _cron_m = str((_cfg.get("cron") or {}).get("default_model") or "").strip()
                    if _cron_m:
                        model = _cron_m
                    elif isinstance(_model_cfg, str):
                        model = _model_cfg
                    elif isinstance(_model_cfg, dict):
                        model = _model_cfg.get("default", model)
        except Exception as e:
            logger.warning("Job '%s': failed to load config.yaml, using defaults: %s", job_id, e)

        from hermes_constants import OPENROUTER_FREE_SYNTHETIC, parse_reasoning_effort

        if not str(model or "").strip():
            model = OPENROUTER_FREE_SYNTHETIC

        effort = os.getenv("HERMES_REASONING_EFFORT", "")
        if not effort:
            effort = str(_cfg.get("agent", {}).get("reasoning_effort", "")).strip()
        reasoning_config = parse_reasoning_effort(effort)

        prefill_messages = None
        prefill_file = os.getenv("HERMES_PREFILL_MESSAGES_FILE", "") or _cfg.get("prefill_messages_file", "")
        if prefill_file:
            import json as _json

            pfpath = Path(prefill_file).expanduser()
            if not pfpath.is_absolute():
                pfpath = _hermes_home / pfpath
            if pfpath.exists():
                try:
                    with open(pfpath, "r", encoding="utf-8") as _pf:
                        prefill_messages = _json.load(_pf)
                    if not isinstance(prefill_messages, list):
                        prefill_messages = None
                except Exception as e:
                    logger.warning("Job '%s': failed to parse prefill messages file '%s': %s", job_id, pfpath, e)
                    prefill_messages = None

        _, cron_turn_cap = _cron_read_limits()
        global_max = _cfg.get("agent", {}).get("max_turns") or _cfg.get("max_turns") or 90
        try:
            global_max = int(global_max)
        except (TypeError, ValueError):
            global_max = 90
        max_iterations = min(global_max, cron_turn_cap)

        pr = _cfg.get("provider_routing", {})
        smart_routing = _cfg.get("smart_model_routing", {}) or {}

        from hermes_cli.runtime_provider import format_runtime_provider_error, resolve_runtime_provider

        try:
            _req_prov = job.get("provider") or os.getenv("HERMES_INFERENCE_PROVIDER")
            if not (str(_req_prov or "").strip()) and not job.get("provider"):
                _cp = str((_cfg.get("cron") or {}).get("default_provider") or "").strip()
                if _cp:
                    _req_prov = _cp
            if not str(_req_prov or "").strip() and str(model or "").strip() == OPENROUTER_FREE_SYNTHETIC:
                _req_prov = "openrouter"
            runtime_kwargs = {"requested": _req_prov}
            if job.get("base_url"):
                runtime_kwargs["explicit_base_url"] = job.get("base_url")
            runtime = resolve_runtime_provider(**runtime_kwargs)
        except Exception as exc:
            message = format_runtime_provider_error(exc)
            raise RuntimeError(message) from exc

        from agent.smart_model_routing import resolve_turn_route

        turn_route = resolve_turn_route(
            prompt,
            smart_routing,
            {
                "model": model,
                "api_key": runtime.get("api_key"),
                "base_url": runtime.get("base_url"),
                "provider": runtime.get("provider"),
                "api_mode": runtime.get("api_mode"),
                "command": runtime.get("command"),
                "args": list(runtime.get("args") or []),
            },
        )

        disabled_toolsets = [
            "cronjob",
            "messaging",
            "clarify",
            "web",
            "search",
            "browser",
            "moa",
            "rl",
            "image_gen",
            "vision",
        ]
        if str(job_name).startswith("daily-slack-role-status-"):
            # Slack role check-ins should generate a concise status report, not perform repo /
            # service maintenance or mutate profile state while composing the message.
            disabled_toolsets.extend(
                [
                    "terminal",
                    "file",
                    "delegation",
                    "code_execution",
                    "memory",
                    "session_search",
                    "skills",
                    "tts",
                    "homeassistant",
                ]
            )

        agent = AIAgent(
            model=turn_route["model"],
            api_key=turn_route["runtime"].get("api_key"),
            base_url=turn_route["runtime"].get("base_url"),
            provider=turn_route["runtime"].get("provider"),
            api_mode=turn_route["runtime"].get("api_mode"),
            acp_command=turn_route["runtime"].get("command"),
            acp_args=turn_route["runtime"].get("args"),
            max_iterations=max_iterations,
            reasoning_config=reasoning_config,
            prefill_messages=prefill_messages,
            providers_allowed=pr.get("only"),
            providers_ignored=pr.get("ignore"),
            providers_order=pr.get("order"),
            provider_sort=pr.get("sort"),
            disabled_toolsets=disabled_toolsets,
            quiet_mode=True,
            skip_memory=True,
            platform="cron",
            session_id=_cron_session_id,
            session_db=_session_db,
        )

        result = agent.run_conversation(prompt)

        final_response = result.get("final_response", "") or ""
        logged_response = final_response if final_response else "(No response generated)"

        output = f"""# Cron Job: {job_name}

**Job ID:** {job_id}
**Run Time:** {_hermes_now().strftime('%Y-%m-%d %H:%M:%S')}
**Schedule:** {job.get('schedule_display', 'N/A')}

## Prompt

{prompt}

## Response

{logged_response}
"""

        logger.info("Job '%s' completed successfully", job_name)
        return True, output, final_response, None

    except Exception as e:
        error_msg = f"{type(e).__name__}: {str(e)}"
        logger.error("Job '%s' failed: %s", job_name, error_msg)

        output = f"""# Cron Job: {job_name} (FAILED)

**Job ID:** {job_id}
**Run Time:** {_hermes_now().strftime('%Y-%m-%d %H:%M:%S')}
**Schedule:** {job.get('schedule_display', 'N/A')}

## Prompt

{prompt}

## Error

```
{error_msg}

{traceback.format_exc()}
```
"""
        return False, output, "", error_msg

    finally:
        for key in (
            "HERMES_SESSION_PLATFORM",
            "HERMES_SESSION_CHAT_ID",
            "HERMES_SESSION_CHAT_NAME",
            "HERMES_CRON_AUTO_DELIVER_PLATFORM",
            "HERMES_CRON_AUTO_DELIVER_CHAT_ID",
            "HERMES_CRON_AUTO_DELIVER_THREAD_ID",
        ):
            os.environ.pop(key, None)
        if _session_db:
            try:
                _session_db.end_session(_cron_session_id, "cron_complete")
            except (Exception, KeyboardInterrupt) as e:
                logger.debug("Job '%s': failed to end session: %s", job_id, e)
            try:
                _session_db.close()
            except (Exception, KeyboardInterrupt) as e:
                logger.debug("Job '%s': failed to close SQLite session store: %s", job_id, e)


def execute_due_cron_job(
    job: dict,
    *,
    verbose: bool = True,
    force_llm: bool = False,
) -> bool:
    """Run a single job through the same pipeline as ``tick()`` (LLM + sanitize + deliver + mark).

    Does **not** take the tick-wide file lock — safe for one-off bursts while the gateway holds
    ``.tick.lock``. When *force_llm* is true, the pre-LLM ``state_skip_gate`` short-circuit is skipped
    so the provider always runs (manual ``run_slack_cron_burst_now`` / operator-requested reports).

    Returns:
        True if the job reached the same completion path as ``tick`` where ``executed`` is incremented
        (LLM path with ``mark_job_run`` at end). False when the state gate skipped the LLM or on
        outer exception (matches ``tick`` accounting).
    """
    job_id = job["id"]
    try:
        advance_next_run(job_id)

        skip_llm, _gate_fp = should_skip_llm_for_unchanged_state(job)
        if skip_llm and not force_llm:
            logger.info(
                "Job '%s': state_skip_gate unchanged — skipping LLM / provider call",
                job_id,
            )
            mark_job_run(job_id, True, None, skip_repeat_increment=True)
            return False

        success, output, final_response, error = run_job(job)

        output_file = save_job_output(job_id, output)
        if verbose:
            logger.info("Output saved to: %s", output_file)

        deliver_content = final_response if success else f"⚠️ Cron job '{job.get('name', job_id)}' failed:\n{error}"
        should_deliver = bool(deliver_content)
        max_chars, _ = _cron_read_limits()
        if should_deliver and success:
            strict_env = job.get("strict_delivery_envelope")
            if strict_env is None:
                strict_env = cron_strict_delivery_envelope()
            sanitized, skip_user = sanitize_cron_deliver_content(
                deliver_content,
                max_chars,
                strict_delivery_envelope=bool(strict_env),
            )
            if skip_user or not (sanitized or "").strip():
                logger.info(
                    "Job '%s': delivery suppressed (envelope / [SILENT] / sanitize)",
                    job_id,
                )
                should_deliver = False
            else:
                deliver_content = sanitized
        elif should_deliver and not success and len(deliver_content) > 2400:
            deliver_content = deliver_content[:2399] + "…"

        if should_deliver and success and deliver_content.strip().upper().startswith(SILENT_MARKER):
            logger.info("Job '%s': agent returned %s — skipping delivery", job_id, SILENT_MARKER)
            should_deliver = False

        if should_deliver:
            deliver_content = format_cron_delivery_with_headline(job, deliver_content, success=success)

        dedupe_on = _cron_delivery_dedupe_enabled()
        fp_new: Optional[str] = None
        if should_deliver:
            fp_new = _delivery_content_fingerprint(deliver_content)
        if (
            should_deliver
            and dedupe_on
            and fp_new
            and job.get("last_deliver_fingerprint")
            and job["last_deliver_fingerprint"] == fp_new
        ):
            logger.info(
                "Job '%s': delivery dedupe — same status as last send, skipping",
                job_id,
            )
            should_deliver = False

        deliver_fingerprint_update: Optional[str] = None
        if should_deliver:
            try:
                if _deliver_result(job, deliver_content) and dedupe_on:
                    deliver_fingerprint_update = fp_new
            except Exception as de:
                logger.error("Delivery failed for job %s: %s", job_id, de)

        state_gate_fp: Optional[str] = None
        if success:
            state_gate_fp = fingerprint_for_state_skip_gate(job)

        mark_job_run(
            job_id,
            success,
            error,
            deliver_fingerprint_update=deliver_fingerprint_update,
            state_gate_fingerprint_update=state_gate_fp,
        )
        return True

    except Exception as e:
        logger.error("Error processing job %s: %s", job_id, e)
        mark_job_run(job_id, False, str(e))
        return False


def tick(verbose: bool = True) -> int:
    """
    Check and run all due jobs.

    Uses a file lock so only one tick runs at a time, even if the gateway's
    in-process ticker and a standalone daemon or manual tick overlap.

    Args:
        verbose: Whether to print status messages

    Returns:
        Number of jobs executed (0 if another tick is already running)
    """
    _LOCK_DIR.mkdir(parents=True, exist_ok=True)

    lock_fd = None
    try:
        lock_fd = open(_LOCK_FILE, "w")
        if fcntl:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        elif msvcrt:
            msvcrt.locking(lock_fd.fileno(), msvcrt.LK_NBLCK, 1)
    except (OSError, IOError):
        logger.debug("Tick skipped — another instance holds the lock")
        if lock_fd is not None:
            lock_fd.close()
        return 0

    try:
        due_jobs = get_due_jobs()

        if verbose and not due_jobs:
            logger.info("%s - No jobs due", _hermes_now().strftime("%H:%M:%S"))
            return 0

        if verbose:
            logger.info("%s - %s job(s) due", _hermes_now().strftime("%H:%M:%S"), len(due_jobs))

        executed = 0
        for job in due_jobs:
            if execute_due_cron_job(job, verbose=verbose, force_llm=False):
                executed += 1

        return executed
    finally:
        if fcntl:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
        elif msvcrt:
            try:
                msvcrt.locking(lock_fd.fileno(), msvcrt.LK_UNLCK, 1)
            except (OSError, IOError):
                pass
        lock_fd.close()


if __name__ == "__main__":
    tick(verbose=True)
