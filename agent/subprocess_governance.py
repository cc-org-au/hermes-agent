"""Subprocess and subagent governance policy.

Enforces that all background tasks and delegated subagents use only truly free
(zero API cost) models. Any API-cost model requires explicit operator approval
before a subprocess or background task can run.

TRULY FREE models (zero API cost — local inference only):
  - Gemma-4 on Gemini API (``gemma-4-31b-it``) and matching local slugs; alternate ``gemma4`` spellings
  - Any model served via HERMES_LOCAL_INFERENCE_BASE_URL (self-hosted)

LOW-COST models (Gemini API — small but non-zero cost per call):
  - google/gemini-2.5-flash, google/gemini-2.5-flash-lite, google/gemini-2.5-pro
  → These are NOT free. They require operator approval for subprocess use.

MID/HIGH COST (always require explicit approval for subprocess use):
  - anthropic/claude-sonnet-4-6 (tier D)
  - gpt-5.4 (tier E)
  - gpt-5.3-codex (tier F)
  - Any other OpenRouter/OpenAI model

Policy rules:
1. Background/subprocess tasks MUST use only genuinely free local models.
2. Gemini API models (low-cost) ALSO require approval for subprocess use.
3. Any non-free model requires EXPLICIT real-time operator approval via callback.
4. Subprocesses have a hard max duration of SUBPROCESS_MAX_SECONDS (default 300 / 5 min).
5. The launching agent is responsible for monitoring and must terminate on completion or timeout.
6. On completion the launching agent notifies the chief and operator with a concise summary.

The chief orchestrator must be consulted (via the normal agentic approval flow in
consultant_routing) before any paid model is used for a subprocess.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Policy constants
# ---------------------------------------------------------------------------

SUBPROCESS_MAX_SECONDS: int = 300  # 5 minutes hard limit

# Substrings that identify models treated as free for subprocess policy (see classify_model_cost).
_FREE_LOCAL_MODEL_SUBSTRINGS: tuple[str, ...] = (
    "gemma-4-31b-it",
    "gemma4",
    "local/",       # catch-all for self-hosted slugs prefixed with "local/"
)

# Substrings identifying models that cost money via API (not free).
_PAID_API_MODEL_SUBSTRINGS: tuple[str, ...] = (
    "gemini",       # Gemini API is paid
    "claude",
    "gpt",
    "openai",
    "anthropic",
    "mistral",
    "cohere",
    "openrouter",
)


# ---------------------------------------------------------------------------
# Classification helpers
# ---------------------------------------------------------------------------

def _has_local_inference_url() -> bool:
    """True when a local inference server is configured."""
    return bool(os.environ.get("HERMES_LOCAL_INFERENCE_BASE_URL", "").strip())


def classify_model_cost(model_id: str, *, provider: str = "", base_url: str = "") -> str:
    """Return 'free', 'low_cost', or 'paid' for a given model ID.

    'free'     = zero API cost (direct Gemini API for gemma-4-31b-it, or local inference).
    'low_cost' = Gemini API calls (gemini-* models) — small cost, NOT free.
    'paid'     = mid/high-cost API model, or ANY model routed through OpenRouter.

    The *provider* and *base_url* parameters allow distinguishing the same model
    name served via different backends.  ``gemma-4-31b-it`` via direct Gemini API
    is free; the same model via OpenRouter is paid (OpenRouter charges for every
    model it proxies).
    """
    from agent.tier_model_routing import canonical_gemma_model_id

    mid = canonical_gemma_model_id((model_id or "").strip()).lower()
    prov = (provider or "").strip().lower()
    burl = (base_url or "").strip().lower()

    _is_openrouter = (
        "openrouter" in prov
        or "openrouter" in burl
        or "openrouter.ai" in burl
    )

    # OpenRouter charges for every model — never free, always at least low_cost
    if _is_openrouter:
        if any(s in mid for s in _FREE_LOCAL_MODEL_SUBSTRINGS):
            return "low_cost"
        return "paid"

    # Local inference base URL makes any model effectively free
    if _has_local_inference_url():
        return "free"
    # Free models by slug (direct Gemini API or local)
    if any(s in mid for s in _FREE_LOCAL_MODEL_SUBSTRINGS):
        return "free"
    # Gemini API: low-cost but not free
    if "gemini" in mid or mid.startswith("google/gemini"):
        return "low_cost"
    # Any other known paid provider
    if any(s in mid for s in _PAID_API_MODEL_SUBSTRINGS):
        return "paid"
    # Unknown model — assume paid to be safe
    return "paid"


def is_free_subprocess_model(model_id: str) -> bool:
    """True only if the model is genuinely zero-cost (local)."""
    return classify_model_cost(model_id) == "free"


def default_free_subprocess_model_id() -> str:
    """Model id used when auto-falling back from a blocked paid subprocess model.

    Reads ``free_model_routing.gemini_native_tier_models[0]`` from config when present,
    else ``gemma-4-31b-it`` (Gemma-4 on Gemini API — classified as *free* for subprocess policy).
    """
    try:
        from hermes_cli.config import load_config

        cfg = load_config()
        fmr = (cfg or {}).get("free_model_routing") or {}
        gn = fmr.get("gemini_native_tier_models") or []
        if isinstance(gn, list) and gn:
            mid = str(gn[0]).strip()
            if mid:
                return mid
    except Exception:
        pass
    return "gemma-4-31b-it"


def requires_operator_approval(model_id: str) -> bool:
    """True for any model that isn't genuinely free (i.e., has API costs)."""
    return not is_free_subprocess_model(model_id)


# ---------------------------------------------------------------------------
# Subprocess registry
# ---------------------------------------------------------------------------

@dataclass
class SubprocessRecord:
    task_id: str
    model_id: str
    goal: str
    start_time: float = field(default_factory=time.monotonic)
    status: str = "running"          # running | completed | terminated | timed_out
    result_summary: Optional[str] = None
    approved_by_operator: bool = False


_registry_lock = threading.Lock()
_SUBPROCESS_REGISTRY: Dict[str, SubprocessRecord] = {}


def register_subprocess(task_id: str, model_id: str, goal: str,
                        approved: bool = False) -> SubprocessRecord:
    rec = SubprocessRecord(
        task_id=task_id,
        model_id=model_id,
        goal=goal[:200],
        approved_by_operator=approved,
    )
    with _registry_lock:
        _SUBPROCESS_REGISTRY[task_id] = rec
    logger.info(
        "subprocess_governance: registered task_id=%s model=%s approved=%s",
        task_id, model_id, approved,
    )
    return rec


def update_subprocess(task_id: str, status: str,
                      result_summary: Optional[str] = None) -> None:
    with _registry_lock:
        rec = _SUBPROCESS_REGISTRY.get(task_id)
    if rec:
        rec.status = status
        if result_summary is not None:
            rec.result_summary = result_summary
    logger.info("subprocess_governance: task_id=%s → %s", task_id, status)


def get_active_subprocesses() -> List[SubprocessRecord]:
    with _registry_lock:
        return [r for r in _SUBPROCESS_REGISTRY.values() if r.status == "running"]


def prune_stale_subprocesses(max_age_seconds: int = SUBPROCESS_MAX_SECONDS) -> List[SubprocessRecord]:
    """Mark timed-out subprocesses and return the list of pruned records."""
    pruned: List[SubprocessRecord] = []
    now = time.monotonic()
    with _registry_lock:
        for rec in _SUBPROCESS_REGISTRY.values():
            if rec.status == "running" and (now - rec.start_time) > max_age_seconds:
                rec.status = "timed_out"
                pruned.append(rec)
    for rec in pruned:
        logger.warning(
            "subprocess_governance: task_id=%s timed out after %.0fs — marking terminated",
            rec.task_id, max_age_seconds,
        )
    return pruned


# ---------------------------------------------------------------------------
# Approval flow
# ---------------------------------------------------------------------------

def request_operator_approval(
    model_id: str,
    goal: str,
    cost_class: str,
    *,
    approval_callback: Optional[Callable[[str], bool]] = None,
    emit_status: Optional[Callable[[str, str], None]] = None,
) -> bool:
    """Request explicit operator approval to use a paid model for a subprocess.

    Returns True if approved, False if denied or no callback is available.
    """
    cost_label = {
        "low_cost": "LOW-COST (Gemini API — not free)",
        "paid": "PAID (mid/high-cost API)",
    }.get(cost_class, "PAID (cost unknown)")

    msg = (
        f"\n⚠️  SUBPROCESS APPROVAL REQUIRED\n"
        f"A background task wants to use a {cost_label} model:\n"
        f"  Model:  {model_id}\n"
        f"  Goal:   {goal[:120]}\n"
        f"\nBackground tasks should only use free local models (gemma-4-31b-it or local inference).\n"
        f"Approve this subprocess to proceed with the paid model? [y/N]: "
    )

    if callable(emit_status):
        try:
            emit_status(
                f"⚠️  Subprocess wants to use paid model {model_id!r} — awaiting operator approval",
                "subprocess_governance",
            )
        except Exception:
            pass

    if callable(approval_callback):
        try:
            return approval_callback(msg)
        except Exception as exc:
            logger.warning("subprocess_governance: approval_callback raised: %s", exc)
            return False

    # No interactive callback — log and deny for safety
    logger.warning(
        "subprocess_governance: DENIED subprocess with paid model %r (no approval callback). "
        "Goal: %s", model_id, goal[:80],
    )
    return False


# ---------------------------------------------------------------------------
# Policy enforcement entry point (called from delegate_tool.py)
# ---------------------------------------------------------------------------

def _is_openai_primary_mode_allowed(model_id: str, parent_agent: Any = None) -> bool:
    """Check if model is allowed by the openai_primary_mode feature flag.

    When enabled, OpenAI models listed in allowed_subprocess_models are
    permitted in subprocesses IF routed directly from OpenAI (not OpenRouter).
    """
    try:
        from hermes_cli.config import load_config
        from agent.token_governance_runtime import load_runtime_config

        cfg = load_config() or {}
        rt = load_runtime_config() or {}

        # Runtime YAML is authoritative for deployment-time governance knobs.
        opm = rt.get("openai_primary_mode") or cfg.get("openai_primary_mode") or {}
        if not opm.get("enabled", False):
            return False

        allowed = opm.get("allowed_subprocess_models") or []

        def _core_model(mid: str) -> str:
            m = (mid or "").strip().lower()
            if m.startswith("openai/"):
                return m.split("/", 1)[1]
            return m

        mid = _core_model(model_id)
        allowed_core = {_core_model(str(a)) for a in allowed if str(a).strip()}
        if mid not in allowed_core:
            return False

        if opm.get("require_direct_openai", True) and parent_agent is not None:
            # Direct-OpenAI requirement applies to the subprocess runtime, not
            # necessarily the current parent runtime. Parent can be on Gemini
            # while child delegates to native api.openai.com.
            from agent.openai_native_runtime import native_openai_runtime_tuple

            if not native_openai_runtime_tuple():
                return False
        return True
    except Exception:
        return False


def enforce_subprocess_model_policy(
    model_id: str,
    goal: str,
    task_id: str,
    *,
    parent_agent: Any = None,
    allow_low_cost: bool = False,
) -> tuple[bool, str]:
    """Check subprocess model policy and request approval if needed.

    Returns (approved: bool, reason: str).
    approved=True → proceed with the subprocess.
    approved=False → block the subprocess.

    Args:
        model_id: Model the subprocess wants to use.
        goal: Human-readable task goal (for approval prompt).
        task_id: Unique task identifier for the registry.
        parent_agent: Launching agent (for approval callback + emit_status).
        allow_low_cost: If True, Gemini API models are pre-approved (not recommended).
    """
    cost_class = classify_model_cost(model_id)

    if cost_class == "free":
        register_subprocess(task_id, model_id, goal, approved=True)
        return True, "free_model"

    # openai_primary_mode: bypass paid-model block for whitelisted OpenAI models
    if _is_openai_primary_mode_allowed(model_id, parent_agent):
        register_subprocess(task_id, model_id, goal, approved=True)
        logger.info(
            "subprocess_governance: openai_primary_mode allows %r for task %s",
            model_id, task_id,
        )
        return True, "openai_primary_mode"

    if cost_class == "low_cost" and allow_low_cost:
        logger.info(
            "subprocess_governance: allow_low_cost=True, permitting Gemini model %r", model_id
        )
        register_subprocess(task_id, model_id, goal, approved=True)
        return True, "low_cost_allowed"

    # Needs approval
    _emit = getattr(parent_agent, "_emit_status", None) if parent_agent else None
    _approval_cb = _get_approval_callback(parent_agent)

    approved = request_operator_approval(
        model_id,
        goal,
        cost_class,
        approval_callback=_approval_cb,
        emit_status=_emit,
    )

    if approved:
        register_subprocess(task_id, model_id, goal, approved=True)
        logger.info(
            "subprocess_governance: operator approved paid model %r for task %s", model_id, task_id
        )
        return True, "operator_approved"

    logger.warning(
        "subprocess_governance: subprocess BLOCKED — paid model %r not approved for task %s",
        model_id, task_id,
    )
    return False, f"denied_paid_model:{model_id}"


def _get_approval_callback(agent: Any) -> Optional[Callable[[str], bool]]:
    """Extract an interactive approval callback from the parent agent."""
    if agent is None:
        return None
    # Try the agent's clarify_callback (used for sudo prompts etc.)
    cb = getattr(agent, "clarify_callback", None)
    if callable(cb):
        def _wrap(prompt: str) -> bool:
            try:
                response = cb(prompt)
                if isinstance(response, str):
                    return response.strip().lower() in ("y", "yes", "1", "true", "approve")
                return bool(response)
            except Exception:
                return False
        return _wrap
    return None


# ---------------------------------------------------------------------------
# Completion notification helper
# ---------------------------------------------------------------------------

def notify_completion(
    task_id: str,
    result_summary: str,
    *,
    parent_agent: Any = None,
    emit_status: Optional[Callable[[str, str], None]] = None,
) -> None:
    """Mark subprocess complete and notify chief/operator.

    Should be called by the launching agent when the subprocess finishes.
    """
    update_subprocess(task_id, "completed", result_summary=result_summary[:500])

    notify_msg = (
        f"✅ Subprocess complete — task_id={task_id}\n"
        f"Summary: {result_summary[:300]}"
    )

    _emit = emit_status or (
        getattr(parent_agent, "_emit_status", None) if parent_agent else None
    )
    if callable(_emit):
        try:
            _emit(notify_msg, "subprocess_governance")
        except Exception:
            pass
    else:
        logger.info("subprocess_governance: %s", notify_msg)


# ---------------------------------------------------------------------------
# Context manager for subprocess lifetime tracking
# ---------------------------------------------------------------------------

class SubprocessLifetime:
    """Context manager: registers a subprocess, enforces timeout, notifies on exit.

    Usage:
        with SubprocessLifetime(task_id, model_id, goal, parent_agent=agent) as gov:
            if not gov.approved:
                return  # blocked
            result = run_task(...)
            gov.result_summary = result
    """

    def __init__(
        self,
        task_id: str,
        model_id: str,
        goal: str,
        *,
        parent_agent: Any = None,
        max_seconds: int = SUBPROCESS_MAX_SECONDS,
    ):
        self.task_id = task_id
        self.model_id = model_id
        self.goal = goal
        self.parent_agent = parent_agent
        self.max_seconds = max_seconds
        self.approved = False
        self.result_summary: str = ""
        self._start: float = 0.0

    def __enter__(self) -> "SubprocessLifetime":
        approved, reason = enforce_subprocess_model_policy(
            self.model_id,
            self.goal,
            self.task_id,
            parent_agent=self.parent_agent,
        )
        self.approved = approved
        self._start = time.monotonic()
        if not approved:
            logger.warning(
                "subprocess_governance: entry blocked for task %s (%s)", self.task_id, reason
            )
        return self

    def elapsed(self) -> float:
        return time.monotonic() - self._start

    def check_timeout(self) -> bool:
        """Returns True (and logs) if the subprocess has exceeded its time limit."""
        if self.elapsed() > self.max_seconds:
            update_subprocess(self.task_id, "timed_out")
            _emit = getattr(self.parent_agent, "_emit_status", None) if self.parent_agent else None
            msg = (
                f"⏱️ Subprocess timed out after {self.max_seconds}s — task_id={self.task_id}"
            )
            if callable(_emit):
                _emit(msg, "subprocess_governance")
            else:
                logger.warning("subprocess_governance: %s", msg)
            return True
        return False

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        if self.approved:
            notify_completion(
                self.task_id,
                self.result_summary or ("error: " + str(exc_val) if exc_val else "completed"),
                parent_agent=self.parent_agent,
            )
        return False  # don't suppress exceptions
