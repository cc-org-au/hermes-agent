"""Optional LLM-based routing of user prompts to named Hermes profiles (CLI).

When ``agent.profile_router.enabled`` is true, the CLI may delegate a user turn
to another profile via ``delegate_task(hermes_profile=...)`` *before* the main
``run_conversation`` loop, so the specialist profile's config/toolsets apply.

This is **off by default** (extra latency + cost; chief/orchestrator stays in control).
Does not mutate sticky ``active_profile`` — only per-turn delegation.

Automatic profile creation and ORG_REGISTRY edits are handled by
``hermes workspace org-automation apply`` / ``sync_org_automation`` (see
``hermes_cli.org_automation``), not by this router. Destructive lifecycle
actions stay out of scope; use ``hermes profile lifecycle-audit`` (advisory).
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Last HF / routing model id used for JSON profile classification (for CLI status bar + logs).
_LAST_ROUTER_MODEL_ID: Optional[str] = None
_LAST_ROUTER_STAGE: str = ""


def clear_profile_router_telemetry() -> None:
    global _LAST_ROUTER_MODEL_ID, _LAST_ROUTER_STAGE
    _LAST_ROUTER_MODEL_ID = None
    _LAST_ROUTER_STAGE = ""


def get_profile_router_telemetry() -> Tuple[Optional[str], str]:
    return _LAST_ROUTER_MODEL_ID, _LAST_ROUTER_STAGE


def _set_router_telemetry(stage: str, model_id: Optional[str] = None) -> None:
    global _LAST_ROUTER_MODEL_ID, _LAST_ROUTER_STAGE
    _LAST_ROUTER_STAGE = stage
    if model_id is not None:
        _LAST_ROUTER_MODEL_ID = model_id


class RouterDelegateParentStub:
    """Minimal ``parent_agent`` for ``delegate_task`` when skipping chief ``AIAgent`` init."""

    __slots__ = (
        "_delegate_depth",
        "enabled_toolsets",
        "model",
        "provider",
        "base_url",
        "api_key",
        "api_mode",
        "acp_command",
        "acp_args",
        "max_tokens",
        "reasoning_config",
        "prefill_messages",
        "platform",
        "session_db",
        "providers_allowed",
        "providers_ignored",
        "providers_order",
        "provider_sort",
        "tool_progress_callback",
        "_active_children",
        "_active_children_lock",
        "_token_governance_delegation_max",
        "on_delegate_child_model",
    )

    def __init__(
        self,
        *,
        enabled_toolsets: List[str],
        model: str,
        runtime: Dict[str, Any],
        platform: str,
        session_db: Any = None,
        reasoning_config: Any = None,
        providers_allowed: Any = None,
        providers_ignored: Any = None,
        providers_order: Any = None,
        provider_sort: Any = None,
        tool_progress_callback: Any = None,
        prefill_messages: Any = None,
        on_delegate_child_model: Optional[Callable[[str], None]] = None,
    ) -> None:
        self._delegate_depth = 0
        self.enabled_toolsets = list(enabled_toolsets or [])
        self.model = model
        self.provider = runtime.get("provider")
        self.base_url = runtime.get("base_url")
        self.api_key = runtime.get("api_key")
        self.api_mode = runtime.get("api_mode")
        self.acp_command = runtime.get("command")
        self.acp_args = list(runtime.get("args") or [])
        self.max_tokens = None
        self.reasoning_config = reasoning_config
        self.prefill_messages = prefill_messages
        self.platform = platform
        self.session_db = session_db
        self.providers_allowed = providers_allowed
        self.providers_ignored = providers_ignored
        self.providers_order = providers_order
        self.provider_sort = provider_sort
        self.tool_progress_callback = tool_progress_callback
        self._active_children: List[Any] = []
        self._active_children_lock = threading.Lock()
        self._token_governance_delegation_max = None
        self.on_delegate_child_model = on_delegate_child_model


def build_router_delegate_parent_stub(
    *,
    enabled_toolsets: List[str],
    model: str,
    runtime: Dict[str, Any],
    platform: str,
    session_db: Any = None,
    reasoning_config: Any = None,
    providers_allowed: Any = None,
    providers_ignored: Any = None,
    providers_order: Any = None,
    provider_sort: Any = None,
    tool_progress_callback: Any = None,
    prefill_messages: Any = None,
    on_delegate_child_model: Optional[Callable[[str], None]] = None,
) -> RouterDelegateParentStub:
    """Build a lightweight parent for profile-router delegation without constructing ``AIAgent``."""
    return RouterDelegateParentStub(
        enabled_toolsets=enabled_toolsets,
        model=model,
        runtime=runtime if isinstance(runtime, dict) else {},
        platform=platform,
        session_db=session_db,
        reasoning_config=reasoning_config,
        providers_allowed=providers_allowed,
        providers_ignored=providers_ignored,
        providers_order=providers_order,
        provider_sort=provider_sort,
        tool_progress_callback=tool_progress_callback,
        prefill_messages=prefill_messages,
        on_delegate_child_model=on_delegate_child_model,
    )


def build_router_delegate_parent_stub_for_cli(
    cli: Any,
    *,
    turn_route: Dict[str, Any],
    on_delegate_child_model: Optional[Callable[[str], None]] = None,
) -> RouterDelegateParentStub:
    """Build a stub from ``HermesCLI`` + ``_resolve_turn_agent_config`` output."""
    rt = turn_route.get("runtime") if isinstance(turn_route, dict) else None
    if not isinstance(rt, dict):
        rt = {}
    return build_router_delegate_parent_stub(
        enabled_toolsets=list(getattr(cli, "enabled_toolsets", None) or []),
        model=str(turn_route.get("model") or getattr(cli, "model", "") or ""),
        runtime=rt,
        platform="cli",
        session_db=getattr(cli, "_session_db", None),
        reasoning_config=getattr(cli, "reasoning_config", None),
        providers_allowed=getattr(cli, "_providers_only", None),
        providers_ignored=getattr(cli, "_providers_ignore", None),
        providers_order=getattr(cli, "_providers_order", None),
        provider_sort=getattr(cli, "_provider_sort", None),
        tool_progress_callback=getattr(cli, "_on_tool_progress", None),
        prefill_messages=getattr(cli, "prefill_messages", None),
        on_delegate_child_model=on_delegate_child_model,
    )


def _profiles_root() -> Path:
    return Path.home() / ".hermes" / "profiles"


def list_routable_profile_names() -> List[str]:
    """Return sorted directory names under ~/.hermes/profiles (kebab-case slugs)."""
    root = _profiles_root()
    if not root.is_dir():
        return []
    names = [
        p.name
        for p in root.iterdir()
        if p.is_dir() and not p.name.startswith(".")
    ]
    return sorted(names)


def _keyword_route_project_lead(
    user_message: str,
    candidates: List[str],
    *,
    current_profile: str,
    skip_current: bool,
    threshold: float,
) -> Optional[Tuple[str, float, str]]:
    """Fast path: project / product lead status asks → ``ag-pl-*`` / ``fd-product`` (no HF call)."""
    low = (user_message or "").strip().lower()
    if len(low) < 12:
        return None

    lead_q = (
        "project lead" in low
        or ("project" in low and "lead" in low)
        or ("status update" in low and "lead" in low)
        or "from the lead" in low
        or ("lead" in low and "status" in low and "project" in low)
    )
    if not lead_q:
        return None

    scored: List[Tuple[int, str]] = []
    for slug in candidates:
        s = slug.lower()
        score = 0
        if "agentic-company" in low and "agentic-company" in s:
            score += 120
        if s.startswith("ag-pl-") or "-pl-" in s or "project-lead" in s:
            score += 60
        if s == "fd-product" and ("product" in low or "lead" in low):
            score += 35
        if score > 0:
            scored.append((score, slug))
    if not scored:
        return None
    scored.sort(key=lambda x: (-x[0], x[1]))
    best = scored[0][1]
    if skip_current and best == current_profile:
        return None, 0.0, "keyword target is current profile"
    conf = max(float(threshold), 0.78)
    return best, conf, "keyword project-lead routing"


def _keyword_route_profile(
    user_message: str,
    candidates: List[str],
    *,
    current_profile: str,
    skip_current: bool,
    threshold: float,
) -> Optional[Tuple[str, float, str]]:
    """Fast path: route obvious security/compliance questions without an LLM (no OpenRouter cost).

    Used when auxiliary APIs are exhausted or to avoid latency; still respects
    ``only_when_current_profiles`` / filters via *candidates*.
    """
    low = (user_message or "").strip().lower()
    if len(low) < 10:
        return None

    security_q = any(
        k in low
        for k in (
            "security posture",
            "security audit",
            "security review",
            "security status",
            "threat model",
            "vulnerability assessment",
            "compliance posture",
            "preflight security",
        )
    ) or (
        "security" in low
        and any(w in low for w in ("posture", "today", "status", "review", "audit", "risk", "threat"))
    )
    if not security_q:
        return None

    # Require an unambiguous specialist slug — avoid grabbing generic ``sec-bot``-style
    # names where "sec" is just a token (those stay on the LLM router).
    scored: List[Tuple[int, str]] = []
    for slug in candidates:
        s = slug.lower()
        strong = (
            "security" in s
            or "preflight" in s
            or "compliance" in s
            or "infosec" in s
            or "ag-sec" in s
            or s.startswith("sec-ops")
            or "sec-guard" in s
        )
        if strong:
            scored.append((50 + len(s), slug))
    if not scored:
        return None
    scored.sort(key=lambda x: -x[0])
    best = scored[0][1]
    if skip_current and best == current_profile:
        return None, 0.0, "keyword target is current profile"
    conf = max(float(threshold), 0.78)
    return best, conf, "keyword security routing"


def _parse_router_json(text: str) -> Optional[Dict[str, Any]]:
    if not text or not text.strip():
        return None
    raw = text.strip()
    # Strip markdown fences
    raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.I)
    raw = re.sub(r"\s*```\s*$", "", raw)
    try:
        obj = json.loads(raw)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{[^{}]*\}", raw, re.DOTALL)
    if m:
        try:
            obj = json.loads(m.group(0))
            return obj if isinstance(obj, dict) else None
        except json.JSONDecodeError:
            return None
    return None


def _user_text_from_messages(messages: List[Dict[str, Any]]) -> str:
    for m in reversed(messages):
        if m.get("role") == "user":
            return str(m.get("content") or "")
    return ""


def _call_profile_router_llm(
    messages: List[Dict[str, Any]],
    router_cfg: Dict[str, Any],
) -> Any:
    """Run the profile-router JSON classifier via tier routing.

    Order (when ``use_free_model_routing`` is true, the default):

    1. Optional pinned ``router_provider``/``router_model`` if both are set to
       ``huggingface`` + a hub id (tried first; on failure, continue).
    2. ``free_model_routing`` — router picks one hub id from *tiers* (top-level or legacy ``kimi_router.tiers``)
       (``router_provider: gemini`` + ``gemma-4-31b-it``, or legacy HF router API), then that
       hub model runs the JSON classification (local OpenAI base if configured).

    Credentials: ``GEMINI_API_KEY`` / ``GOOGLE_API_KEY`` for ``gemini`` router; HF token for
    ``huggingface`` router; pinned HF hub calls still need an HF token.
    """
    from agent.auxiliary_client import call_llm

    use_free = router_cfg.get("use_free_model_routing", True)
    explicit_p = (router_cfg.get("router_provider") or "").strip().lower()
    explicit_m = (router_cfg.get("router_model") or "").strip()

    kwargs = dict(
        task=None,
        messages=messages,
        temperature=0.1,
        max_tokens=256,
    )

    if not use_free:
        if explicit_p and explicit_m:
            return call_llm(provider=explicit_p, model=explicit_m, **kwargs)
        raise RuntimeError(
            "profile_router: with use_free_model_routing=false, set router_provider and router_model",
        )

    tok = (
        os.environ.get("HF_TOKEN")
        or os.environ.get("HUGGING_FACE_HUB_TOKEN")
        or os.environ.get("HUGGINGFACE_API_KEY")
        or ""
    ).strip()
    base = (os.environ.get("HF_BASE_URL", "").strip() or "https://router.huggingface.co/v1").rstrip("/")

    from hermes_cli.config import load_config

    from agent.free_model_routing import (
        fallback_free_routed_model_id,
        gemini_native_tier_model_set,
        normalize_kimi_tiers,
        raw_free_model_routing_tiers,
    )
    from agent.hf_fallback_router import resolve_gemini_routed_model, resolve_hf_routed_model

    cfg = load_config()
    fmr = (cfg.get("free_model_routing") or {}) if isinstance(cfg, dict) else {}
    if not (isinstance(fmr, dict) and fmr.get("enabled")):
        fmr = {}

    user_text = _user_text_from_messages(messages)

    if explicit_p == "huggingface" and explicit_m:
        if not tok:
            raise RuntimeError(
                "Profile router: pinned huggingface router_model requires HF_TOKEN, "
                "HUGGING_FACE_HUB_TOKEN, or HUGGINGFACE_API_KEY.",
            )
        try:
            _set_router_telemetry("hf_inference_pinned", explicit_m)
            logger.info("profile_router: HF inference (pinned) model=%s", explicit_m)
            return call_llm(provider="huggingface", model=explicit_m, **kwargs)
        except Exception as exc:
            logger.warning(
                "profile_router: pinned router_model failed, using free_model_routing chain: %s",
                exc,
            )

    # Profile classification uses the Gemini router model directly — never HF Inference Providers.
    # HF Inference Providers credits are often depleted; profile routing only needs a lightweight
    # classification call, which Gemma-4 on Gemini API handles cleanly.
    kr = fmr.get("kimi_router") if isinstance(fmr.get("kimi_router"), dict) else {}
    router_model = str(kr.get("router_model") or "").strip()
    router_prov = str(kr.get("router_provider") or "gemini").strip().lower()

    if router_prov == "gemini" and router_model:
        gem = (
            os.environ.get("GEMINI_API_KEY")
            or os.environ.get("GOOGLE_API_KEY")
            or ""
        ).strip()
        if gem:
            _set_router_telemetry("gemini_direct", router_model)
            logger.info("profile_router: Gemini direct classification model=%s", router_model)
            return call_llm(provider="gemini", model=router_model, **kwargs)
        logger.warning(
            "profile_router: router_provider=gemini but no GEMINI_API_KEY/GOOGLE_API_KEY found"
        )

    # Fallback: try a local inference base URL if configured, else raise.
    local_base = os.environ.get("HERMES_LOCAL_INFERENCE_BASE_URL", "").strip()
    if router_model and local_base:
        _set_router_telemetry("local_inference", router_model)
        logger.info("profile_router: local inference model=%s base=%s", router_model, local_base)
        return call_llm(provider="openai", model=router_model, base_url=local_base, **kwargs)

    raise RuntimeError(
        "profile_router: set free_model_routing.kimi_router.router_provider=gemini and "
        "router_model=gemma-4-31b-it (or another Gemini-compatible model), and ensure "
        "GEMINI_API_KEY is set. HF Inference Providers are not used for profile classification.",
    )


def classify_profile_for_prompt(
    user_message: str,
    *,
    candidates: List[str],
    current_profile: str,
    router_cfg: Dict[str, Any],
) -> Tuple[Optional[str], float, str]:
    """Call auxiliary LLM; return (target_profile or None, confidence, reason)."""
    clear_profile_router_telemetry()
    if not candidates:
        return None, 0.0, "no profiles"
    threshold = float(router_cfg.get("confidence_threshold") or 0.72)
    min_chars = int(router_cfg.get("min_message_chars") or 12)
    if len((user_message or "").strip()) < min_chars:
        return None, 0.0, "message too short"

    exclude = set(router_cfg.get("exclude_profiles") or [])
    allow_only = router_cfg.get("allow_only_profiles") or []
    if allow_only:
        candidates = [c for c in candidates if c in allow_only]
    candidates = [c for c in candidates if c not in exclude]
    if not candidates:
        return None, 0.0, "no candidates after filters"

    only_from = router_cfg.get("only_when_current_profiles") or []
    if only_from and current_profile not in only_from:
        return None, 0.0, "current profile not in only_when_current_profiles"

    skip_current = router_cfg.get("exclude_current_profile", True)
    if skip_current and current_profile in candidates and current_profile != "default":
        # Still allow routing *to* another profile when current is chief; remove self from targets only if same name chosen later
        pass

    kw_pl = _keyword_route_project_lead(
        user_message,
        candidates,
        current_profile=current_profile,
        skip_current=skip_current,
        threshold=threshold,
    )
    if kw_pl and kw_pl[0]:
        _set_router_telemetry("keyword_heuristic", "keyword")
        return kw_pl[0], kw_pl[1], kw_pl[2]

    kw = _keyword_route_profile(
        user_message,
        candidates,
        current_profile=current_profile,
        skip_current=skip_current,
        threshold=threshold,
    )
    if kw and kw[0]:
        _set_router_telemetry("keyword_heuristic", "keyword")
        return kw[0], kw[1], kw[2]

    system = (
        "You route user turns to Hermes profile slugs (each profile is an isolated agent runtime). "
        "Reply with ONLY valid JSON, no markdown.\n"
        'Schema: {"profile": "<exact slug from list or null>", "confidence": number 0-1, "reason": "brief"}\n'
        "When the user's request clearly fits a specialist (infer from slug words: security, legal, "
        "hr, finance, infra, director, product, compliance, preflight, audit, etc.), choose that slug "
        "with confidence 0.7–1.0.\n"
        "Use profile null with confidence below 0.5 when the orchestrator should answer or no slug fits.\n"
        "Never invent slugs; profile must be exactly one of the listed names or null."
    )
    user = (
        f"Current session profile: {current_profile!r}\n"
        f"Available profile slugs: {', '.join(candidates)}\n\n"
        f"User message:\n{user_message.strip()[:8000]}"
    )

    from agent.auxiliary_client import extract_content_or_reasoning

    _messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    text: Optional[str] = None
    try:
        resp = _call_profile_router_llm(_messages, router_cfg)
        text = extract_content_or_reasoning(resp)
    except Exception as exc:
        logger.warning("profile_router LLM call failed: %s", exc)
        return None, 0.0, f"router error: {exc}"

    if not (text and str(text).strip()):
        return None, 0.0, "empty router model output"

    data = _parse_router_json(text)
    if not data:
        logger.debug("profile_router: unparseable response: %s", text[:200])
        return None, 0.0, "unparseable router output"

    name = data.get("profile")
    if name is not None and not isinstance(name, str):
        name = None
    if name is not None:
        name = name.strip()
        if name == "" or name.lower() == "null":
            name = None

    try:
        conf = float(data.get("confidence", 0))
    except (TypeError, ValueError):
        conf = 0.0
    reason = str(data.get("reason") or "").strip()[:500]

    if name is None or conf < threshold:
        return None, conf, reason or "below threshold"

    if name not in candidates:
        logger.info("profile_router: model chose unknown profile %r", name)
        return None, conf, "unknown profile slug"

    if skip_current and name == current_profile:
        return None, conf, "target is current profile"

    return name, conf, reason


def route_and_delegate_if_configured(
    *,
    user_message: str,
    parent_agent: Any,
    agent_config: Dict[str, Any],
    current_profile: str,
    precomputed: Optional[Tuple[Optional[str], float, str]] = None,
) -> Optional[str]:
    """If routing applies, run delegate_task and return markdown for the user; else None.

    Pass *precomputed* from an earlier ``classify_profile_for_prompt`` call to avoid a
    second classification (and to allow a lightweight ``RouterDelegateParentStub``).
    """
    router_cfg = agent_config if isinstance(agent_config, dict) else {}
    if not router_cfg.get("enabled"):
        return None

    if precomputed is not None:
        target, conf, reason = precomputed
    else:
        candidates = list_routable_profile_names()
        target, conf, reason = classify_profile_for_prompt(
            user_message,
            candidates=candidates,
            current_profile=current_profile,
            router_cfg=router_cfg,
        )
    if not target:
        return None

    from tools.delegate_tool import delegate_task

    payload = delegate_task(
        goal=user_message.strip(),
        context=(
            f"Routed automatically from profile {current_profile!r} "
            f"(router confidence {conf:.2f}). Reason: {reason}"
        ),
        hermes_profile=target,
        parent_agent=parent_agent,
    )
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return None
    if isinstance(data, dict) and data.get("error"):
        logger.warning("profile_router delegate failed: %s", data.get("error"))
        return None

    # Format a concise reply for the CLI (delegate returns JSON with results[])
    results = data.get("results")
    body = payload
    if isinstance(results, list) and results:
        first = results[0]
        if isinstance(first, dict):
            body = first.get("summary") or first.get("response") or json.dumps(first, indent=2)[:12000]
    header = f"_Delegated to profile `{target}` (router confidence {conf:.2f})_\n\n"
    return header + (body if isinstance(body, str) else str(body))
