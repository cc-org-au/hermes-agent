"""
Cron job scheduler - executes due jobs.

Provides tick() which checks for due jobs and runs them. The gateway
calls this every 60 seconds from a background thread.

Uses a file-based lock (~/.hermes/cron/.tick.lock) so only one tick
runs at a time if multiple processes overlap.
"""

import asyncio
import hashlib
import json
import logging
import os
import re
import sys
import traceback

# fcntl is Unix-only; on Windows use msvcrt for file locking
try:
    import fcntl
except ImportError:
    fcntl = None
    try:
        import msvcrt
    except ImportError:
        msvcrt = None
from pathlib import Path
from hermes_constants import get_hermes_home
from hermes_cli.config import load_config
from typing import Optional

from hermes_time import now as _hermes_now

logger = logging.getLogger(__name__)

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from cron.jobs import get_due_jobs, mark_job_run, save_job_output, advance_next_run

# Sentinel: when a cron agent has nothing new to report, it can start its
# response with this marker to suppress delivery.  Output is still saved
# locally for audit.
SILENT_MARKER = "[SILENT]"

# Lines / fragments that change every run but do not change the underlying status.
_RE_DEDUPE_UPDATED_LINE = re.compile(r"^\s*updated\s*:", re.I)
_RE_DEDUPE_AS_OF_PAREN = re.compile(r"\s*\(\s*as\s+of\s+[^)]+\)", re.I)
_RE_DEDUPE_AS_OF_TAIL = re.compile(r"\s+as\s+of\s+.+$", re.I)
_RE_DEDUPE_ISO_TIMESTAMP = re.compile(
    r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2})?(\.\d+)?([+-]\d{2}:\d{2}|Z|AEST|AEDT|UTC)?"
)


def _normalize_for_delivery_dedupe(text: str) -> str:
    """Collapse cron/agent output so timestamp-only edits map to the same fingerprint."""
    lines_out: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if _RE_DEDUPE_UPDATED_LINE.match(line):
            continue
        line = _RE_DEDUPE_AS_OF_PAREN.sub("", line)
        line = _RE_DEDUPE_AS_OF_TAIL.sub("", line)
        line = _RE_DEDUPE_ISO_TIMESTAMP.sub(" ", line)
        line = re.sub(
            r"\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}(?::\d{2})?\s*(?:AEST|AEDT|UTC|GMT)\b",
            " ",
            line,
            flags=re.I,
        )
        line = re.sub(r"\s+", " ", line).strip()
        if line:
            lines_out.append(line.lower())
    joined = " ".join(lines_out)
    return re.sub(r"\s+", " ", joined).strip()


def _delivery_content_fingerprint(content: str) -> str:
    normalized = _normalize_for_delivery_dedupe(content)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _cron_delivery_dedupe_enabled() -> bool:
    try:
        cfg = load_config()
        return bool(cfg.get("cron", {}).get("delivery_dedupe", True))
    except Exception:
        return True


def _cron_read_limits() -> tuple[int, int]:
    """Return (delivery_max_chars, max_agent_turns) with safe bounds."""
    try:
        c = load_config().get("cron") or {}
        mx = int(c.get("delivery_max_chars", 600))
        mt = int(c.get("max_agent_turns", 12))
        return max(200, min(4000, mx)), max(3, min(90, mt))
    except Exception:
        return 600, 12


_RE_BRACKET_INTERNAL_NOTE = re.compile(r"\[internal note\s*:[^\]]*\]", re.I)
_RE_BRACKET_CONTEXT = re.compile(r"\[CONTEXT\s*:[^\]]*\]", re.I | re.DOTALL)
_RE_BRACKET_CONCLUSION = re.compile(r"\[CONCLUSION\s*:[^\]]*\]", re.I | re.DOTALL)
_RE_SHOWN_RESPONSE = re.compile(r"\[SHOWN RESPONSE\]\s*", re.I)

_ALERT_HINTS = re.compile(
    r"\b(gateway|whatsapp|telegram|slack|alert|sev\s*[012]|sev\d|down|recovered|reconnected|"
    r"connected|bridge|systemd|resolved|outstanding|intervention|fatal|error|"
    r"ok\s+all_connected|start-limit|degraded|watchdog|cron|platforms?)\b",
    re.I,
)

_COT_LINE_PREFIXES = (
    "based on ",
    "ased on ",  # truncated model output still reads as chain-of-thought
    "given that ",
    "therefore,",
    "therefore ",
    "the current state indicates",
    "the current state shows",
    "the current escalation",
    "since there",
    "since the ",
    "according to",
    "i will ",
    "i'll ",
    "i cannot ",
    "i'm sorry",
    "would you like",
    "the previous state",
    "the last known",
    "the last stored",
    "the status json",
    "there are no ",
    "there is no ",
    "no new ",
    "no change ",
    "recent web search",
    "proceeding with",
    "following the",
    "hard requirement",
    "as per the",
    "summary:",
    "analysis:",
    "final response",
    "conclusion:",
    "if you would like",
    "unable to confirm",
    "cannot confirm",
    "given the lack of",
    "without real-time",
    "overall effective state",
    "appropriate action is",
    "nothing new to report",
)


_RE_SILENT_BRACKET = re.compile(r"\[\s*\.?\s*silent\s*\]", re.I)

_HALLUCINATION_SNIPPETS = (
    "alert audio",
    "audio message",
    "generated an alert",
    "i have generated",
    "text-to-speech",
    "voice note",
)


def _normalize_silent_brackets(text: str) -> str:
    """Fullwidth brackets from some models break [SILENT] detection."""
    return text.replace("\u3010", "[").replace("\u3011", "]").replace("［", "[").replace("］", "]")


def _strip_hallucination_sentences(text: str) -> str:
    """Remove sentences that claim audio/TTS/alerts the gateway did not send."""
    if not text or not any(sn in text.lower() for sn in _HALLUCINATION_SNIPPETS):
        return text
    chunks = re.split(r"(?<=[.!?])\s+", text.strip())
    kept: list[str] = []
    for ch in chunks:
        lowc = ch.lower()
        if any(sn in lowc for sn in _HALLUCINATION_SNIPPETS):
            continue
        t = ch.strip()
        if t:
            kept.append(t)
    return " ".join(kept).strip()


def _cron_vague_operational_claim_only(body: str) -> bool:
    """
    True when text is only hand-wavy 'everything is up' copy with no check output
    (watchdog, connected=, gateway_state, etc.) — not worth a WhatsApp ping.
    """
    low = body.lower()
    if not any(w in low for w in ("recovered", "restored", "reconnected", "operational", "is now up")):
        return False
    evidence = (
        "watchdog",
        "all_connected",
        "gateway_state",
        "gateway.pid",
        "connected:",
        "platforms:",
        "telegram",
        "slack",
        "systemctl",
        "start-limit",
        "json",
        "`",
    )
    if any(sig in low for sig in evidence):
        return False
    if "all platforms" in low or "now up" in low or "fully operational" in low:
        return True
    return False


def _cron_prose_announces_silent(low: str) -> bool:
    """Model wrote [SILENT] inside a paragraph instead of alone — never deliver that."""
    if not _RE_SILENT_BRACKET.search(low):
        return False
    if any(
        p in low
        for p in (
            "will respond",
            "respond with",
            "return exactly",
            "output exactly",
            "comply with",
            "comply to",
            "avoid redundant",
            "avoid duplicate",
            "no change since",
            "no change in",
            "has been no change",
            "unchanged",
            "nothing new",
            "nothing to report",
            "therefore, i will",
            "therefore i will",
            "accordingly, i will",
            "appropriate response is",
            "finalize this response",
            "protocol and avoid",
        )
    ):
        return True
    # Long reasoning that only exists to justify [SILENT]
    if len(low) > 120 and "resolved" in low and "no new" in low:
        return True
    return False


def _cron_response_means_silent(text: str) -> bool:
    """True when the model clearly intends no user-visible delivery."""
    if not text or not str(text).strip():
        return True
    s = _normalize_silent_brackets(str(text).strip())
    low = s.lower()
    if _cron_prose_announces_silent(low):
        return True
    first = s.lstrip()
    if re.match(r"^\[\.?silent\]", first, re.I):
        return True
    lines = [ln.strip() for ln in s.splitlines() if ln.strip()]
    if not lines:
        return True
    last = lines[-1]
    if re.match(r"^[\s\.]*\[\.?silent\]", last, re.I):
        return True
    if len(last) < 220 and _RE_SILENT_BRACKET.search(last):
        return True
    tail = low[-520:]
    if "[silent]" in tail and any(
        p in tail
        for p in (
            "respond with",
            "respond exactly",
            "return exactly",
            "output exactly",
            "will now ",
            "appropriate response is",
            "[silent].",
            "finalize this response",
            "accordingly,",
        )
    ):
        return True
    one = re.sub(r"\s+", " ", low)
    if "[silent]" in one and "nothing new" in one and len(s) > 60:
        return True
    return False


def _is_cot_line(line: str) -> bool:
    low = line.lower().strip()
    if len(low) < 30:
        return False
    return any(low.startswith(p) for p in _COT_LINE_PREFIXES)


def _pick_delivery_paragraph(body: str, max_chars: int) -> str:
    chunks = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
    candidate = ""
    for chunk in reversed(chunks):
        if _ALERT_HINTS.search(chunk):
            candidate = chunk
            break
    if not candidate and chunks:
        candidate = chunks[-1]
    elif not candidate:
        candidate = body
    lines = [ln.strip() for ln in candidate.splitlines() if ln.strip()]
    if not lines:
        return ""
    joined = "\n".join(lines)
    if len(joined) > max_chars:
        tail = lines[-min(6, len(lines)) :]
        joined = "\n".join(tail)
    if len(joined) > max_chars:
        joined = joined[: max_chars - 1].rstrip() + "…"
    return joined.strip()


def sanitize_cron_deliver_content(raw: str, max_chars: int) -> tuple[str, bool]:
    """
    Turn a model final_response into messaging-safe text.

    Returns:
        (text_to_send, skip_delivery) — skip_delivery True means do not notify the user.
    """
    raw = _normalize_silent_brackets(str(raw or "").strip())
    if _cron_response_means_silent(raw):
        return "", True
    s = raw.strip()
    s = _strip_hallucination_sentences(s)
    if not s.strip():
        return "", True
    if _cron_response_means_silent(s):
        return "", True
    s = _RE_BRACKET_INTERNAL_NOTE.sub("", s)
    s = _RE_BRACKET_CONTEXT.sub("", s)
    s = _RE_BRACKET_CONCLUSION.sub("", s)
    s = _RE_SHOWN_RESPONSE.sub("", s)
    s = s.strip()

    kept: list[str] = []
    for ln in s.splitlines():
        lns = ln.strip()
        if not lns:
            continue
        if _is_cot_line(lns):
            continue
        kept.append(lns)

    body = "\n".join(kept).strip()
    if not body:
        return "", True

    # Short, already-compact replies (tests + simple summaries)
    if len(body) <= 220 and body.count("\n") <= 2:
        out = body if len(body) <= max_chars else body[: max_chars - 1].rstrip() + "…"
        if _cron_vague_operational_claim_only(out):
            return "", True
        return out, False

    out = _pick_delivery_paragraph(body, max_chars)
    if not out.strip():
        return "", True
    if not _ALERT_HINTS.search(out) and len(out) > 120:
        return "", True
    if _cron_vague_operational_claim_only(out):
        return "", True
    return out, False


def _cron_severity_suffix(body: str, success: bool) -> str:
    """Compact status phrase inferred from delivery body (no extra LLM call)."""
    if not success:
        return "Run failed"
    low = body.lower()
    # Critical / needs action now
    if any(
        p in low
        for p in (
            "gateway down",
            "no platforms",
            "telegram: fatal",
            "slack: fatal",
            "fatal",
            "start-limit",
            "start limit",
            "bridge disconnected",
            "not connected",
            "⚠️ cron job",
        )
    ):
        return "Action needed"
    if re.search(r"\bsev\s*0\b", low) or re.search(r"\bsev\s*1\b", low):
        return "Action needed"
    if re.search(r"\bdown\b", low) and "recovered" not in low and "restored" not in low:
        return "Action needed"
    # Elevated attention
    if any(
        p in low
        for p in (
            "sev2",
            "sev 2",
            "degraded",
            "outstanding",
            "intervention",
            "warning",
            "attention required",
        )
    ):
        return "Review suggested"
    # Healthy / cleared (before generic "alert" heuristic)
    if any(
        p in low
        for p in (
            "recovered",
            "resolved",
            "cleared",
            "reconnected",
            "restored",
            "healthy",
            "all_connected",
            "connectivity restored",
            "gateway recovered",
            "platforms: whatsapp",
            "ok all_connected",
            "status ok",
            "all clear",
        )
    ):
        return "Nominal"
    if re.search(r"\balert\b", low) and "false alert" not in low:
        return "Review suggested"
    return "Update"


def _cron_headline_line(job: dict, body: str, success: bool) -> str:
    """Single-line preview: job topic + inferred status (or per-job override)."""
    custom = str(job.get("deliver_summary") or job.get("delivery_summary") or "").strip()
    raw = str(job.get("name") or job.get("id") or "Scheduled job").strip()
    topic = re.sub(r"[-_]+", " ", raw).strip().title()
    if len(topic) > 44:
        topic = topic[:41].rstrip() + "…"
    if custom:
        if success:
            return custom[:120]
        return f"{custom[:72]} — Run failed"[:120]
    suffix = _cron_severity_suffix(body, success)
    return f"{topic} — {suffix}"


def format_cron_delivery_with_headline(job: dict, body: str, *, success: bool) -> str:
    """Prefix messaging delivery with one short status line (no extra LLM)."""
    body = (body or "").strip()
    if not body:
        return body
    headline = _cron_headline_line(job, body, success).strip()
    if body.startswith(headline):
        return body
    first_line = body.splitlines()[0].strip() if body else ""
    if first_line == headline:
        return body
    return f"{headline}\n{body}"


# Resolve Hermes home directory (respects HERMES_HOME override)
_hermes_home = get_hermes_home()

# File-based lock prevents concurrent ticks from gateway + daemon + systemd timer
_LOCK_DIR = _hermes_home / "cron"
_LOCK_FILE = _LOCK_DIR / ".tick.lock"


def _resolve_origin(job: dict) -> Optional[dict]:
    """Extract origin info from a job, preserving any extra routing metadata."""
    origin = job.get("origin")
    if not origin:
        return None
    platform = origin.get("platform")
    chat_id = origin.get("chat_id")
    if platform and chat_id:
        return origin
    return None


def _resolve_delivery_target(job: dict) -> Optional[dict]:
    """Resolve the concrete auto-delivery target for a cron job, if any."""
    deliver = job.get("deliver", "local")
    origin = _resolve_origin(job)

    if deliver == "local":
        return None

    if deliver == "origin":
        if not origin:
            return None
        return {
            "platform": origin["platform"],
            "chat_id": str(origin["chat_id"]),
            "thread_id": origin.get("thread_id"),
        }

    if ":" in deliver:
        platform_name, rest = deliver.split(":", 1)
        # Check for thread_id suffix (e.g. "telegram:-1003724596514:17")
        if ":" in rest:
            chat_id, thread_id = rest.split(":", 1)
        else:
            chat_id, thread_id = rest, None

        # Resolve human-friendly labels like "Alice (dm)" to real IDs.
        # send_message(action="list") shows labels with display suffixes
        # that aren't valid platform IDs (e.g. WhatsApp JIDs).
        try:
            from gateway.channel_directory import resolve_channel_name
            target = chat_id
            # Strip display suffix like " (dm)" or " (group)"
            if target.endswith(")") and " (" in target:
                target = target.rsplit(" (", 1)[0].strip()
            resolved = resolve_channel_name(platform_name.lower(), target)
            if resolved:
                chat_id = resolved
        except Exception:
            pass

        return {
            "platform": platform_name,
            "chat_id": chat_id,
            "thread_id": thread_id,
        }

    platform_name = deliver
    if origin and origin.get("platform") == platform_name:
        return {
            "platform": platform_name,
            "chat_id": str(origin["chat_id"]),
            "thread_id": origin.get("thread_id"),
        }

    chat_id = os.getenv(f"{platform_name.upper()}_HOME_CHANNEL", "")
    if not chat_id:
        return None

    return {
        "platform": platform_name,
        "chat_id": chat_id,
        "thread_id": None,
    }


def _deliver_result(job: dict, content: str) -> bool:
    """
    Deliver job output to the configured target (origin chat, specific platform, etc.).

    Uses the standalone platform send functions from send_message_tool so delivery
    works whether or not the gateway is running.

    Returns:
        True if a message was sent successfully; False if skipped, misconfigured, or failed.
    """
    target = _resolve_delivery_target(job)
    if not target:
        if job.get("deliver", "local") != "local":
            logger.warning(
                "Job '%s' deliver=%s but no concrete delivery target could be resolved",
                job["id"],
                job.get("deliver", "local"),
            )
        return False

    platform_name = target["platform"]
    chat_id = target["chat_id"]
    thread_id = target.get("thread_id")

    from tools.send_message_tool import _send_to_platform
    from gateway.config import load_gateway_config, Platform

    platform_map = {
        "telegram": Platform.TELEGRAM,
        "discord": Platform.DISCORD,
        "slack": Platform.SLACK,
        "whatsapp": Platform.WHATSAPP,
        "signal": Platform.SIGNAL,
        "matrix": Platform.MATRIX,
        "mattermost": Platform.MATTERMOST,
        "homeassistant": Platform.HOMEASSISTANT,
        "dingtalk": Platform.DINGTALK,
        "feishu": Platform.FEISHU,
        "wecom": Platform.WECOM,
        "email": Platform.EMAIL,
        "sms": Platform.SMS,
    }
    platform = platform_map.get(platform_name.lower())
    if not platform:
        logger.warning("Job '%s': unknown platform '%s' for delivery", job["id"], platform_name)
        return False

    try:
        config = load_gateway_config()
    except Exception as e:
        logger.error("Job '%s': failed to load gateway config for delivery: %s", job["id"], e)
        return False

    pconfig = config.platforms.get(platform)
    if not pconfig or not pconfig.enabled:
        logger.warning("Job '%s': platform '%s' not configured/enabled", job["id"], platform_name)
        return False

    # Optionally wrap the content with a header/footer so the user knows this
    # is a cron delivery.  Wrapping is on by default; set cron.wrap_response: false
    # in config.yaml for clean output.
    wrap_response = True
    try:
        user_cfg = load_config()
        wrap_response = user_cfg.get("cron", {}).get("wrap_response", True)
    except Exception:
        pass

    if wrap_response:
        task_name = job.get("name", job["id"])
        delivery_content = (
            f"Cronjob Response: {task_name}\n"
            f"-------------\n\n"
            f"{content}\n\n"
            f"Note: The agent cannot see this message, and therefore cannot respond to it."
        )
    else:
        delivery_content = content

    # Run the async send in a fresh event loop (safe from any thread)
    coro = _send_to_platform(platform, pconfig, chat_id, delivery_content, thread_id=thread_id)
    try:
        result = asyncio.run(coro)
    except RuntimeError:
        # asyncio.run() checks for a running loop before awaiting the coroutine;
        # when it raises, the original coro was never started — close it to
        # prevent "coroutine was never awaited" RuntimeWarning, then retry in a
        # fresh thread that has no running loop.
        coro.close()
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(asyncio.run, _send_to_platform(platform, pconfig, chat_id, delivery_content, thread_id=thread_id))
            result = future.result(timeout=30)
    except Exception as e:
        logger.error("Job '%s': delivery to %s:%s failed: %s", job["id"], platform_name, chat_id, e)
        return False

    if result and result.get("error"):
        logger.error("Job '%s': delivery error: %s", job["id"], result["error"])
        return False
    logger.info("Job '%s': delivered to %s:%s", job["id"], platform_name, chat_id)
    return True


def _build_job_prompt(job: dict) -> str:
    """Build the effective prompt for a cron job, optionally loading one or more skills first."""
    prompt = job.get("prompt", "")
    skills = job.get("skills")

    # Always prepend [SILENT] guidance so the cron agent can suppress
    # delivery when it has nothing new or noteworthy to report.
    silent_hint = (
        "[SYSTEM: If you have a meaningful status report or findings, "
        "send them — that is the whole point of this job. Only respond "
        "with exactly \"[SILENT]\" (nothing else) when there is genuinely "
        "nothing new to report. [SILENT] suppresses delivery to the user. "
        "Never combine [SILENT] with content — either report your "
        "findings normally, or say [SILENT] and nothing more.]\n\n"
        "[SYSTEM — OUTPUT FORMAT (mandatory): Your final reply must be EITHER "
        "(a) exactly the single line [SILENT] with nothing else, OR (b) at most "
        "four short lines (under 500 characters total) of plain operational "
        "status — no apologies, no \"I will\", no analysis paragraphs, no "
        "markdown essays, no restating instructions. If nothing changed since "
        "the last run, output only [SILENT].]\n\n"
    )
    prompt = silent_hint + prompt
    if skills is None:
        legacy = job.get("skill")
        skills = [legacy] if legacy else []

    skill_names = [str(name).strip() for name in skills if str(name).strip()]
    if not skill_names:
        return prompt

    from tools.skills_tool import skill_view

    parts = []
    skipped: list[str] = []
    for skill_name in skill_names:
        loaded = json.loads(skill_view(skill_name))
        if not loaded.get("success"):
            error = loaded.get("error") or f"Failed to load skill '{skill_name}'"
            logger.warning("Cron job '%s': skill not found, skipping — %s", job.get("name", job.get("id")), error)
            skipped.append(skill_name)
            continue

        content = str(loaded.get("content") or "").strip()
        if parts:
            parts.append("")
        parts.extend(
            [
                f'[SYSTEM: The user has invoked the "{skill_name}" skill, indicating they want you to follow its instructions. The full skill content is loaded below.]',
                "",
                content,
            ]
        )

    if skipped:
        notice = (
            f"[SYSTEM: The following skill(s) were listed for this job but could not be found "
            f"and were skipped: {', '.join(skipped)}. "
            f"Start your response with a brief notice so the user is aware, e.g.: "
            f"'⚠️ Skill(s) not found and skipped: {', '.join(skipped)}']"
        )
        parts.insert(0, notice)

    if prompt:
        parts.extend(["", f"The user has provided the following instruction alongside the skill invocation: {prompt}"])
    return "\n".join(parts)


def run_job(job: dict) -> tuple[bool, str, str, Optional[str]]:
    """
    Execute a single cron job.
    
    Returns:
        Tuple of (success, full_output_doc, final_response, error_message)
    """
    from run_agent import AIAgent
    
    # Initialize SQLite session store so cron job messages are persisted
    # and discoverable via session_search (same pattern as gateway/run.py).
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

    # Inject origin context so the agent's send_message tool knows the chat
    if origin:
        os.environ["HERMES_SESSION_PLATFORM"] = origin["platform"]
        os.environ["HERMES_SESSION_CHAT_ID"] = str(origin["chat_id"])
        if origin.get("chat_name"):
            os.environ["HERMES_SESSION_CHAT_NAME"] = origin["chat_name"]

    try:
        # Re-read .env and config.yaml fresh every run so provider/key
        # changes take effect without a gateway restart.
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

        # Load config.yaml for model, reasoning, prefill, toolsets, provider routing
        _cfg = {}
        try:
            import yaml
            _cfg_path = str(_hermes_home / "config.yaml")
            if os.path.exists(_cfg_path):
                with open(_cfg_path) as _f:
                    _cfg = yaml.safe_load(_f) or {}
                _model_cfg = _cfg.get("model", {})
                if not job.get("model"):
                    if isinstance(_model_cfg, str):
                        model = _model_cfg
                    elif isinstance(_model_cfg, dict):
                        model = _model_cfg.get("default", model)
        except Exception as e:
            logger.warning("Job '%s': failed to load config.yaml, using defaults: %s", job_id, e)

        # Reasoning config from env or config.yaml
        from hermes_constants import parse_reasoning_effort
        effort = os.getenv("HERMES_REASONING_EFFORT", "")
        if not effort:
            effort = str(_cfg.get("agent", {}).get("reasoning_effort", "")).strip()
        reasoning_config = parse_reasoning_effort(effort)

        # Prefill messages from env or config.yaml
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

        # Max iterations — cron jobs use a lower cap than interactive CLI
        _, cron_turn_cap = _cron_read_limits()
        global_max = _cfg.get("agent", {}).get("max_turns") or _cfg.get("max_turns") or 90
        try:
            global_max = int(global_max)
        except (TypeError, ValueError):
            global_max = 90
        max_iterations = min(global_max, cron_turn_cap)

        # Provider routing
        pr = _cfg.get("provider_routing", {})
        smart_routing = _cfg.get("smart_model_routing", {}) or {}

        from hermes_cli.runtime_provider import (
            resolve_runtime_provider,
            format_runtime_provider_error,
        )
        try:
            runtime_kwargs = {
                "requested": job.get("provider") or os.getenv("HERMES_INFERENCE_PROVIDER"),
            }
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
            disabled_toolsets=[
                "cronjob",
                "messaging",
                "clarify",
                # Keep cron monitors cheap: no web/browser/MoA/RL/vision/image tools.
                "web",
                "search",
                "browser",
                "moa",
                "rl",
                "image_gen",
                "vision",
            ],
            quiet_mode=True,
            skip_memory=True,  # Cron system prompts would corrupt user representations
            platform="cron",
            session_id=_cron_session_id,
            session_db=_session_db,
        )
        
        result = agent.run_conversation(prompt)
        
        final_response = result.get("final_response", "") or ""
        # Use a separate variable for log display; keep final_response clean
        # for delivery logic (empty response = no delivery).
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
        # Clean up injected env vars so they don't leak to other jobs
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

    # Cross-platform file locking: fcntl on Unix, msvcrt on Windows
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
            logger.info("%s - No jobs due", _hermes_now().strftime('%H:%M:%S'))
            return 0

        if verbose:
            logger.info("%s - %s job(s) due", _hermes_now().strftime('%H:%M:%S'), len(due_jobs))

        executed = 0
        for job in due_jobs:
            try:
                # For recurring jobs (cron/interval), advance next_run_at to the
                # next future occurrence BEFORE execution.  This way, if the
                # process crashes mid-run, the job won't re-fire on restart.
                # One-shot jobs are left alone so they can retry on restart.
                advance_next_run(job["id"])

                success, output, final_response, error = run_job(job)

                output_file = save_job_output(job["id"], output)
                if verbose:
                    logger.info("Output saved to: %s", output_file)

                # Deliver the final response to the origin/target chat.
                # Sanitize successful replies (strip chain-of-thought; enforce
                # silent / no-news). Output files still contain the full model text.
                deliver_content = final_response if success else f"⚠️ Cron job '{job.get('name', job['id'])}' failed:\n{error}"
                should_deliver = bool(deliver_content)
                max_chars, _ = _cron_read_limits()
                if should_deliver and success:
                    sanitized, skip_user = sanitize_cron_deliver_content(deliver_content, max_chars)
                    if skip_user or not (sanitized or "").strip():
                        logger.info(
                            "Job '%s': delivery suppressed ([SILENT] rules or empty after sanitize)",
                            job["id"],
                        )
                        should_deliver = False
                    else:
                        deliver_content = sanitized
                elif should_deliver and not success and len(deliver_content) > 2400:
                    deliver_content = deliver_content[:2399] + "…"

                if should_deliver and success and deliver_content.strip().upper().startswith(SILENT_MARKER):
                    logger.info("Job '%s': agent returned %s — skipping delivery", job["id"], SILENT_MARKER)
                    should_deliver = False

                if should_deliver:
                    deliver_content = format_cron_delivery_with_headline(
                        job, deliver_content, success=success
                    )

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
                        job["id"],
                    )
                    should_deliver = False

                deliver_fingerprint_update: Optional[str] = None
                if should_deliver:
                    try:
                        if _deliver_result(job, deliver_content) and dedupe_on:
                            deliver_fingerprint_update = fp_new
                    except Exception as de:
                        logger.error("Delivery failed for job %s: %s", job["id"], de)

                mark_job_run(job["id"], success, error, deliver_fingerprint_update=deliver_fingerprint_update)
                executed += 1

            except Exception as e:
                logger.error("Error processing job %s: %s", job['id'], e)
                mark_job_run(job["id"], False, str(e))

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
