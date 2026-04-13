"""
Messaging delivery for cron: sanitize model output, headlines, dedupe fingerprints, send.

Keeps `scheduler.py` focused on when jobs run; all “what we send / how we filter” lives here.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import re
import unicodedata
from typing import Optional

from hermes_cli.config import load_config

from cron.delivery_envelope import cron_strict_delivery_envelope, try_parse_cron_delivery_envelope

logger = logging.getLogger(__name__)

SILENT_MARKER = "[SILENT]"

_RE_DEDUPE_UPDATED_LINE = re.compile(r"^\s*updated\s*:", re.I)
_RE_DEDUPE_AS_OF_PAREN = re.compile(r"\s*\(\s*as\s+of\s+[^)]+\)", re.I)
_RE_DEDUPE_AS_OF_TAIL = re.compile(r"\s+as\s+of\s+.+$", re.I)
_RE_DEDUPE_ISO_TIMESTAMP = re.compile(
    r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2})?(\.\d+)?([+-]\d{2}:\d{2}|Z|AEST|AEDT|UTC)?"
)


def normalize_for_delivery_dedupe(text: str) -> str:
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


def delivery_content_fingerprint(content: str) -> str:
    normalized = normalize_for_delivery_dedupe(content)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def cron_delivery_dedupe_enabled() -> bool:
    raw = os.environ.get("HERMES_CRON_DELIVERY_DEDUPE", "").strip().lower()
    if raw in ("0", "false", "no", "off"):
        return False
    try:
        cfg = load_config()
        return bool(cfg.get("cron", {}).get("delivery_dedupe", True))
    except Exception:
        return True


def read_cron_limits() -> tuple[int, int]:
    """Return (delivery_max_chars, max_agent_turns) with safe bounds.

    ``delivery_max_chars`` upper bound matches Slack's large ``text`` posts (~40k);
    Hermes defaults lower in config to avoid spam — raise in ``cron.delivery_max_chars`` when needed.
    """
    try:
        c = load_config().get("cron") or {}
        mx = int(c.get("delivery_max_chars", 12000))
        mt = int(c.get("max_agent_turns", 12))
        return max(200, min(36000, mx)), max(3, min(90, mt))
    except Exception:
        return 12000, 12


_RE_BRACKET_INTERNAL_NOTE = re.compile(r"\[internal note\s*:[^\]]*\]", re.I)
_RE_BRACKET_CONTEXT = re.compile(r"\[CONTEXT\s*:[^\]]*\]", re.I | re.DOTALL)
_RE_BRACKET_CONCLUSION = re.compile(r"\[CONCLUSION\s*:[^\]]*\]", re.I | re.DOTALL)
_RE_SHOWN_RESPONSE = re.compile(r"\[SHOWN RESPONSE\]\s*", re.I)

_ALERT_HINTS = re.compile(
    r"\b(gateway|whatsapp|telegram|slack|sev\s*[012]|sev\d|down|recovered|reconnected|"
    r"connected|bridge|systemd|resolved|outstanding|intervention|fatal|error|"
    r"ok\s+all_connected|start-limit|degraded|watchdog|cron|platforms?)\b"
    r"|\balert\s*[:\-]",
    re.I,
)

_COT_LINE_PREFIXES = (
    "based on ",
    "ased on ",
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
    "the current gateway state",
)

_RE_SILENT_BRACKET = re.compile(
    r"[\[〔【［]\s*\.?\s*silent\s*[\]〕】］]",
    re.I,
)
# Models invent "[Silently no change…]" instead of the literal token [SILENT].
_RE_SILENTLY_BRACKET = re.compile(r"[\[〔【（(]\s*silently\b", re.I)

_HALLUCINATION_SNIPPETS = (
    "alert audio",
    "audio message",
    "generated an alert",
    "i have generated",
    "text-to-speech",
    "voice note",
)


def _normalize_silent_brackets(text: str) -> str:
    t = text
    for a, b in (
        ("\u3010", "["),
        ("\u3011", "]"),
        ("［", "["),
        ("］", "]"),
        ("\uff3b", "["),
        ("\uff3d", "]"),
        ("〔", "["),
        ("〕", "]"),
        ("【", "["),
        ("】", "]"),
    ):
        t = t.replace(a, b)
    return t


def _inner_has_unicode_letter(inner: str) -> bool:
    return any(unicodedata.category(ch).startswith("L") for ch in inner)


def _bracketed_foreign_script_silent_marker(text: str) -> bool:
    """
    Treat transliterated [SILENT] in non-Latin scripts as silent (e.g. Devanagari [एसआईएलेंट]).
    Short bracket-only body, no ASCII letter runs, but contains Unicode letters.
    """
    s = _normalize_silent_brackets(str(text).strip())
    m = re.fullmatch(r"\[([^\]]{2,120})\]", s)
    if not m:
        return False
    inner = m.group(1).strip()
    if re.search(r"[a-zA-Z]{2,}", inner):
        return False
    return _inner_has_unicode_letter(inner)


def _strip_hallucination_sentences(text: str) -> str:
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


def _vague_operational_claim_only(body: str) -> bool:
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
        "systemctl",
        "start-limit",
        "`",
    )
    if any(sig in low for sig in evidence):
        return False
    if "all platforms" in low or "now up" in low or "fully operational" in low:
        return True
    return False


_CRON_META_FLUFF_RES = (
    re.compile(r"\bi[' ]?m\s+sending\b", re.I),
    re.compile(r"\bi\s+am\s+sending\b", re.I),
    re.compile(r"\bhere\s+is\s+(another\s+)?(message|update)\b", re.I),
    re.compile(r"\b(this|that)\s+message\s+(is\s+)?(to\s+)?(tell|say|inform)\b", re.I),
    re.compile(r"\bsending\s+(you\s+)?(a\s+)?(message|update)\b", re.I),
    re.compile(r"\bnothing\s+to\s+(update|tell|report|say)\b", re.I),
    re.compile(r"\bnothing\s+has\s+changed\b", re.I),
    re.compile(r"\bnothing\s+new\s+to\s+report\b", re.I),
    re.compile(r"\bnothing\s+to\s+report\b", re.I),
    re.compile(r"\bno\s+changes?\s+(to\s+)?report\b", re.I),
    re.compile(r"\bno\s+changes?\s+since\b", re.I),
    re.compile(r"\bthere\s+is\s+nothing\s+to\s+", re.I),
    re.compile(r"\bthere\s+(has\s+)?been\s+no\s+change\b", re.I),
    re.compile(r"\bthere\s+are\s+no\s+new\s+(updates?|issues?|incidents?)\b", re.I),
    re.compile(r"\bjust\s+(wanted\s+)?to\s+(let\s+you\s+know|inform\s+you)\b", re.I),
    re.compile(r"\btelling\s+you\s+that\s+there\s+(is|are)\s+no\b", re.I),
    re.compile(r"\bto\s+inform\s+you\s+that\b", re.I),
    re.compile(r"\bi\s+will\s+(now\s+)?(send|respond|reply|output|provide)\b", re.I),
    re.compile(r"\bas\s+an\s+ai\b", re.I),
    re.compile(r"\bfor\s+transparency\b", re.I),
    re.compile(r"\bhope\s+this\s+(helps|message)\b", re.I),
    re.compile(r"\bsaying\s+nothing\s+has\s+changed\b", re.I),
    re.compile(r"\bmessage\s+(to\s+)?(tell|say)\s+you\b", re.I),
    re.compile(r"\bno\s+alert\s+is\s+necessary\b", re.I),
    re.compile(r"\bno\s+change\s+in\s+(the\s+)?(state|status)\b", re.I),
    re.compile(r"\bwith\s+no\s+change\s+in\s+(the\s+)?(state|status)\b", re.I),
)

_CRON_INFO_SIGNAL_RES = (
    re.compile(r"\d{3,}"),
    re.compile(r"\b(sev\s*[012]|sev\d)\b", re.I),
    re.compile(
        r"\b(all_connected|gateway_state|gateway\.pid|watchdog|start-limit|start limit)\b",
        re.I,
    ),
    re.compile(r"\d{4}-\d{2}-\d{2}"),
    re.compile(r"=\s*[\w@.,:+-]+"),
    re.compile(r"\b(telegram|slack|whatsapp)\s*[=:]"),
    re.compile(r"[:]\s*(fatal|down|up|ok|connected|disconnected)\b", re.I),
    re.compile(r"/[\w./~-]{4,}\b"),
    re.compile(r"\b(error|errno|exception|traceback|timeout|failed)\b", re.I),
    re.compile(
        r"\b(fatal|degraded|recovered|resolved|outstanding|intervention|escalat)\w*\b",
        re.I,
    ),
    re.compile(r"^\s*[-*•]\s+\S", re.M),
)


def _meta_fluff_hits(body: str) -> int:
    return sum(1 for rx in _CRON_META_FLUFF_RES if rx.search(body))


def _informative_signal_hits(body: str) -> int:
    return sum(1 for rx in _CRON_INFO_SIGNAL_RES if rx.search(body))


def _announces_remain_silent(low: str) -> bool:
    if not re.search(
        r"\b(will\s+remain\s+silent|remains?\s+silent|staying\s+silent|stay\s+silent|"
        r"remain\s+silent|the\s+system\s+remains\s+silent|i\s+will\s+remain\s+silent|"
        r"i\s+am\s+remaining\s+silent|i\s+will\s+stay\s+silent)\b",
        low,
    ):
        return False
    if re.search(
        r"\b(degraded|fatal|disconnected|unstable|traceback|exception:|errno\s+|http\s*5\d\d)\b",
        low,
        re.I,
    ):
        return False
    return _informative_signal_hits(low) <= 1


def _suppress_meta_fluff(body: str) -> bool:
    if not (body or "").strip():
        return True
    low = body.lower()
    wc = len(body.split())
    meta = _meta_fluff_hits(body)
    info = _informative_signal_hits(body)
    first_person = len(re.findall(r"\b(i'(?:m|ve)|i\s+will|i\s+am|i\s+have|i\s+cannot)\b", low))

    if meta >= 1 and info == 0:
        return True
    if meta >= 2:
        return True
    if wc >= 26 and info == 0:
        return True
    if wc >= 16 and info <= 1 and meta >= 1:
        return True
    if wc >= 18 and first_person >= 2 and info <= 1:
        return True
    return False


def _silent_stand_in_prose(low: str) -> bool:
    """[Silently …], (silently …), bare 'Silently no change…]', etc."""
    if _RE_SILENTLY_BRACKET.search(low):
        return True
    if re.search(r"\bsilently\s+no\s+(change|update|alert)\b", low):
        return True
    # Missing '[' (model typo): "Silently no change and no alert sent]"
    if re.search(r"^\s*silently\s+no\s+change\b", low, re.M):
        return True
    if re.search(r"\bsilently\b[^\n\[]{0,120}\]", low):
        return True
    return False


_CRON_STRUCTURED_EVIDENCE_MARKERS = (
    "all_connected",
    "watchdog-check",
    "watchdog:",
    "watchdog ",
    "gateway_state",
    "gateway.pid",
    "connected:",
    "ok all_connected",
    "start-limit",
    "start limit",
)


def _cron_response_has_structured_evidence(low: str) -> bool:
    """Watchdog-style lines worth delivering; prose like 'WhatsApp is down' alone is not."""
    if any(m in low for m in _CRON_STRUCTURED_EVIDENCE_MARKERS):
        return True
    if re.search(r"\b(sev\s*[012]|sev\d)\b", low):
        return True
    if re.search(r"\b(telegram|slack|whatsapp)\s*[=:]", low):
        return True
    if re.search(r"[:]\s*(fatal|down|up|ok|connected|disconnected)\b", low):
        return True
    return False


def _cron_narrative_no_evidence_suppresses(low: str) -> bool:
    """
    Same-state / 'silent' / web-search essay without tool output — never message this.
    Droplet cron jobs were burning tokens delivering this repeatedly.
    """
    fluff_markers = (
        "remains silent",
        "system remains silent",
        "as per the rules",
        "no transition",
        "not resended",
        "not been resended",
        "unchanged state",
        "consistent with the previous",
        "state has not transitioned",
        "have not changed",
        "no alert has been",
        "web search",
        "support documentation",
        "i will not resend",
        "will not resend",
        "last sent message",
        "message hash",
        "availability resources",
    )
    if not any(m in low for m in fluff_markers):
        return False
    if _cron_response_has_structured_evidence(low):
        return False
    return True


def _line_exempt_from_cot_strip(line: str) -> bool:
    """Do not drop lines that carry [SILENT] / silent compliance (often start with 'I will ')."""
    ln = _normalize_silent_brackets(line.strip())
    if _bracketed_foreign_script_silent_marker(ln):
        return True
    low = ln.lower()
    if _RE_SILENT_BRACKET.search(low):
        return True
    if _RE_SILENTLY_BRACKET.search(low):
        return True
    if _silent_stand_in_prose(low):
        return True
    if _response_means_silent(ln):
        return True
    return False


def _prose_announces_silent(low: str) -> bool:
    if not _RE_SILENT_BRACKET.search(low):
        return False
    if any(
        p in low
        for p in (
            "will respond",
            "respond with",
            "return exactly",
            "i will return",
            "will return exactly",
            "will return ",
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
    if len(low) > 120 and "resolved" in low and "no new" in low:
        return True
    return False


def _response_means_silent(text: str) -> bool:
    if not text or not str(text).strip():
        return True
    s = _normalize_silent_brackets(str(text).strip())
    if _bracketed_foreign_script_silent_marker(s):
        return True
    low = s.lower()
    if _silent_stand_in_prose(low):
        return True
    if _cron_narrative_no_evidence_suppresses(low):
        return True
    if _announces_remain_silent(low):
        return True
    if _prose_announces_silent(low):
        return True
    first = s.lstrip()
    if re.match(r"^\[\.?silent\]", first, re.I):
        return True
    lines = [ln.strip() for ln in s.splitlines() if ln.strip()]
    if not lines:
        return True
    last = lines[-1]
    if _bracketed_foreign_script_silent_marker(last):
        return True
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
    if _line_exempt_from_cot_strip(line):
        return False
    low = line.lower().strip()
    if len(low) < 30:
        return False
    return any(low.startswith(p) for p in _COT_LINE_PREFIXES)


def _pick_delivery_paragraph(body: str, max_chars: int) -> str:
    chunks = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
    # Model often ends with "… I will respond with [SILENT]." in the last paragraph.
    # Never prefer an earlier alert-looking paragraph over that conclusion.
    if len(chunks) >= 2 and _response_means_silent(chunks[-1]):
        return ""
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
    # Keep the start of the chosen paragraph (bullets, evidence) when over budget — do not
    # replace with only the last few lines, which hid the headline under a small max_chars.
    if len(joined) > max_chars:
        joined = joined[: max_chars - 1].rstrip() + "…"
    joined = joined.strip()
    if _cron_narrative_no_evidence_suppresses(joined.lower()):
        return ""
    return joined


def sanitize_cron_deliver_content(
    raw: str, max_chars: int, *, strict_delivery_envelope: bool = False
) -> tuple[str, bool]:
    """
    Turn a model final_response into messaging-safe text.

    If the response ends with ###HERMES_CRON_DELIVERY_JSON … ###END_HERMES_CRON_DELIVERY_JSON,
    only the JSON ``lines`` are delivered (deterministic). Earlier prose is ignored.

    Returns:
        (text_to_send, skip_delivery) — skip_delivery True means do not notify the user.
    """
    raw = _normalize_silent_brackets(str(raw or "").strip())
    env = try_parse_cron_delivery_envelope(raw, max_chars, strict=strict_delivery_envelope)
    if env is not None:
        return env
    if _response_means_silent(raw):
        return "", True
    s = raw.strip()
    s = _strip_hallucination_sentences(s)
    if not s.strip():
        return "", True
    if _response_means_silent(s):
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
    if _response_means_silent(body):
        return "", True

    if len(body) <= 220 and body.count("\n") <= 2:
        out = body if len(body) <= max_chars else body[: max_chars - 1].rstrip() + "…"
        if _vague_operational_claim_only(out):
            return "", True
        if _suppress_meta_fluff(out):
            return "", True
        if _cron_narrative_no_evidence_suppresses(out.lower()):
            return "", True
        return out, False

    out = _pick_delivery_paragraph(body, max_chars)
    if not out.strip():
        return "", True
    if not _ALERT_HINTS.search(out) and len(out) > 120:
        return "", True
    if _vague_operational_claim_only(out):
        return "", True
    if _suppress_meta_fluff(out):
        return "", True
    if _cron_narrative_no_evidence_suppresses(out.lower()):
        return "", True
    return out, False


def _severity_suffix(body: str, success: bool) -> str:
    if not success:
        return "Run failed"
    low = body.lower()
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


def _headline_line(job: dict, body: str, success: bool) -> str:
    custom = str(job.get("deliver_summary") or job.get("delivery_summary") or "").strip()
    raw = str(job.get("name") or job.get("id") or "Scheduled job").strip()
    topic = re.sub(r"[-_]+", " ", raw).strip().title()
    if len(topic) > 44:
        topic = topic[:41].rstrip() + "…"
    if custom:
        if success:
            return custom[:120]
        return f"{custom[:72]} — Run failed"[:120]
    suffix = _severity_suffix(body, success)
    return f"{topic} — {suffix}"


def format_cron_delivery_with_headline(job: dict, body: str, *, success: bool) -> str:
    body = (body or "").strip()
    if not body:
        return body
    headline = _headline_line(job, body, success).strip()
    if body.startswith(headline):
        return body
    first_line = body.splitlines()[0].strip() if body else ""
    if first_line == headline:
        return body
    return f"{headline}\n{body}"


def resolve_origin(job: dict) -> Optional[dict]:
    origin = job.get("origin")
    if not origin:
        return None
    platform = origin.get("platform")
    chat_id = origin.get("chat_id")
    if platform and chat_id:
        return origin
    return None


def resolve_delivery_target(job: dict) -> Optional[dict]:
    deliver = job.get("deliver", "local")
    origin = resolve_origin(job)

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
        if ":" in rest:
            chat_id, thread_id = rest.split(":", 1)
        else:
            chat_id, thread_id = rest, None

        try:
            from gateway.channel_directory import resolve_channel_name

            target = chat_id
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


def deliver_cron_result(job: dict, content: str) -> bool:
    """
    Deliver job output to the configured target.

    Returns True if a message was sent successfully; False if skipped, misconfigured, or failed.
    """
    target = resolve_delivery_target(job)
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

    coro = _send_to_platform(platform, pconfig, chat_id, delivery_content, thread_id=thread_id)
    try:
        result = asyncio.run(coro)
    except RuntimeError:
        coro.close()
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(
                asyncio.run,
                _send_to_platform(platform, pconfig, chat_id, delivery_content, thread_id=thread_id),
            )
            result = future.result(timeout=30)
    except Exception as e:
        logger.error("Job '%s': delivery to %s:%s failed: %s", job["id"], platform_name, chat_id, e)
        return False

    if result and result.get("error"):
        logger.error("Job '%s': delivery error: %s", job["id"], result["error"])
        return False
    logger.info("Job '%s': delivered to %s:%s", job["id"], platform_name, chat_id)
    return True
