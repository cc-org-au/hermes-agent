#!/usr/bin/env python3
"""
Delegate Tool -- Subagent Architecture

Spawns child AIAgent instances with isolated context, restricted toolsets,
and their own terminal sessions. Supports single-task and batch (parallel)
modes. The parent blocks until all children complete.

Each child gets:
  - A fresh conversation (no parent history)
  - Its own task_id (own terminal session, file ops cache)
  - A restricted toolset (configurable, with blocked tools always stripped)
  - A focused system prompt built from the delegated goal + context

The parent's context only sees the delegation call and the summary result,
never the child's intermediate tool calls or reasoning.
"""

import json
import logging
logger = logging.getLogger(__name__)
import os
import threading
import time
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional

# Serialize delegate_task when switching HERMES_HOME for a child profile (process-global env).
_HERMES_PROFILE_DELEGATE_LOCK = threading.RLock()


# Tools that children must never have access to
DELEGATE_BLOCKED_TOOLS = frozenset([
    "delegate_task",   # no recursive delegation
    "hand_off_to_profile",
    "sync_org_automation",  # org-wide writes; parent/orchestrator only
    "clarify",         # no user interaction
    "memory",          # no writes to shared MEMORY.md
    "send_message",    # no cross-platform side effects
    "slack_channel_admin",
    "telegram_forum_topic",
    "execute_code",    # children should reason step-by-step, not write scripts
])

MAX_CONCURRENT_CHILDREN = 3
MAX_DEPTH = 2  # parent (0) -> child (1) -> grandchild rejected (2)
DEFAULT_MAX_ITERATIONS = 50
DEFAULT_TOOLSETS = ["terminal", "file", "web"]


def check_delegate_requirements() -> bool:
    """Delegation has no external requirements -- always available."""
    return True


def _build_child_system_prompt(goal: str, context: Optional[str] = None) -> str:
    """Build a focused system prompt for a child agent."""
    parts = [
        "You are a focused subagent working on a specific delegated task.",
        "",
        f"YOUR TASK:\n{goal}",
    ]
    if context and context.strip():
        parts.append(f"\nCONTEXT:\n{context}")
    parts.append(
        "\nComplete this task using the tools available to you. "
        "When finished, provide a clear, concise summary of:\n"
        "- What you did\n"
        "- What you found or accomplished\n"
        "- Any files you created or modified\n"
        "- Any issues encountered\n\n"
        "Be thorough but concise -- your response is returned to the "
        "parent agent as a summary.\n\n"
        "CRITICAL: You must NEVER simulate, stub, fake, or mock any action. "
        "Do NOT write scripts that pretend to perform tasks (e.g. writing fake "
        "check-in messages, simulating API calls, creating dummy status files). "
        "Use real tools (delegate_task, terminal, etc.) to perform actual operations. "
        "If you cannot do something for real, state what is blocked and why — "
        "never produce a fake result."
    )
    return "\n".join(parts)


@contextmanager
def _hermes_profile_env(profile_name: Optional[str]):
    """Temporarily set HERMES_HOME to profiles/<profile_name> for child construction + run."""
    name = (profile_name or "").strip()
    if not name:
        yield
        return
    from hermes_cli.profiles import get_profile_dir, profile_exists, validate_profile_name

    validate_profile_name(name)
    if not profile_exists(name):
        raise ValueError(
            f"hermes_profile {name!r} does not exist. Create it first "
            f"(e.g. scripts/core/bootstrap_org_agent_profiles.py) or use an existing profile name."
        )
    target = str(get_profile_dir(name))
    with _HERMES_PROFILE_DELEGATE_LOCK:
        old = os.environ.get("HERMES_HOME")
        try:
            os.environ["HERMES_HOME"] = target
            yield
        finally:
            if old is None:
                os.environ.pop("HERMES_HOME", None)
            else:
                os.environ["HERMES_HOME"] = old


def _strip_blocked_tools(toolsets: List[str]) -> List[str]:
    """Remove toolsets that contain only blocked tools."""
    blocked_toolset_names = {
        "delegation", "clarify", "memory", "code_execution",
    }
    return [t for t in toolsets if t not in blocked_toolset_names]


def _build_child_progress_callback(task_index: int, parent_agent, task_count: int = 1) -> Optional[callable]:
    """Build a callback that relays child agent tool calls to the parent display.

    Two display paths:
      CLI:     prints tree-view lines above the parent's delegation spinner
      Gateway: batches tool names and relays to parent's progress callback

    Returns None if no display mechanism is available, in which case the
    child agent runs with no progress callback (identical to current behavior).
    """
    spinner = getattr(parent_agent, '_delegate_spinner', None)
    parent_cb = getattr(parent_agent, 'tool_progress_callback', None)

    if not spinner and not parent_cb:
        return None  # No display → no callback → zero behavior change

    # Show 1-indexed prefix only in batch mode (multiple tasks)
    prefix = f"[{task_index + 1}] " if task_count > 1 else ""

    # Gateway: batch tool names, flush periodically
    _BATCH_SIZE = 5
    _batch: List[str] = []

    def _callback(tool_name: str, preview: str = None):
        # Special "_thinking" event: model produced text content (reasoning)
        if tool_name == "_thinking":
            if spinner:
                short = (preview[:55] + "...") if preview and len(preview) > 55 else (preview or "")
                try:
                    spinner.print_above(f" {prefix}├─ 💭 \"{short}\"")
                except Exception as e:
                    logger.debug("Spinner print_above failed: %s", e)
            # Don't relay thinking to gateway (too noisy for chat)
            return

        # Regular tool call event
        if spinner:
            short = (preview[:35] + "...") if preview and len(preview) > 35 else (preview or "")
            from agent.display import get_tool_emoji
            emoji = get_tool_emoji(tool_name)
            line = f" {prefix}├─ {emoji} {tool_name}"
            if short:
                line += f"  \"{short}\""
            try:
                spinner.print_above(line)
            except Exception as e:
                logger.debug("Spinner print_above failed: %s", e)

        if parent_cb:
            _batch.append(tool_name)
            if len(_batch) >= _BATCH_SIZE:
                summary = ", ".join(_batch)
                try:
                    parent_cb("subagent_progress", f"🔀 {prefix}{summary}")
                except Exception as e:
                    logger.debug("Parent callback failed: %s", e)
                _batch.clear()

    def _flush():
        """Flush remaining batched tool names to gateway on completion."""
        if parent_cb and _batch:
            summary = ", ".join(_batch)
            try:
                parent_cb("subagent_progress", f"🔀 {prefix}{summary}")
            except Exception as e:
                logger.debug("Parent callback flush failed: %s", e)
            _batch.clear()

    _callback._flush = _flush
    return _callback


def _build_child_agent(
    task_index: int,
    goal: str,
    context: Optional[str],
    toolsets: Optional[List[str]],
    model: Optional[str],
    max_iterations: int,
    parent_agent,
    # Credential overrides from delegation config (provider:model resolution)
    override_provider: Optional[str] = None,
    override_base_url: Optional[str] = None,
    override_api_key: Optional[str] = None,
    override_api_mode: Optional[str] = None,
):
    """
    Build a child AIAgent on the main thread (thread-safe construction).
    Returns the constructed child agent without running it.

    When override_* params are set (from delegation config), the child uses
    those credentials instead of inheriting from the parent.  This enables
    routing subagents to a different provider:model pair (e.g. cheap/fast
    model on OpenRouter while the parent runs on Nous Portal).
    """
    from run_agent import AIAgent

    # When no explicit toolsets given, inherit from parent's enabled toolsets
    # so disabled tools (e.g. web) don't leak to subagents.
    parent_toolsets = set(getattr(parent_agent, "enabled_toolsets", None) or DEFAULT_TOOLSETS)
    if toolsets:
        # Intersect with parent — subagent must not gain tools the parent lacks
        child_toolsets = _strip_blocked_tools([t for t in toolsets if t in parent_toolsets])
    elif parent_agent and getattr(parent_agent, "enabled_toolsets", None):
        child_toolsets = _strip_blocked_tools(parent_agent.enabled_toolsets)
    else:
        child_toolsets = _strip_blocked_tools(DEFAULT_TOOLSETS)

    child_prompt = _build_child_system_prompt(goal, context)
    # Extract parent's API key so subagents inherit auth (e.g. Nous Portal).
    parent_api_key = getattr(parent_agent, "api_key", None)
    if (not parent_api_key) and hasattr(parent_agent, "_client_kwargs"):
        parent_api_key = parent_agent._client_kwargs.get("api_key")

    # Build progress callback to relay tool calls to parent display
    child_progress_cb = _build_child_progress_callback(task_index, parent_agent)

    # Each subagent gets its own iteration budget capped at max_iterations
    # (configurable via delegation.max_iterations, default 50).  This means
    # total iterations across parent + subagents can exceed the parent's
    # max_iterations.  The user controls the per-subagent cap in config.yaml.

    # Resolve effective credentials: config override > parent inherit
    effective_model = model or parent_agent.model
    effective_provider = override_provider or getattr(parent_agent, "provider", None)
    effective_base_url = override_base_url or parent_agent.base_url
    effective_api_key = override_api_key or parent_api_key
    effective_api_mode = override_api_mode or getattr(parent_agent, "api_mode", None)
    effective_acp_command = getattr(parent_agent, "acp_command", None)
    effective_acp_args = list(getattr(parent_agent, "acp_args", []) or [])

    child = AIAgent(
        base_url=effective_base_url,
        api_key=effective_api_key,
        model=effective_model,
        provider=effective_provider,
        api_mode=effective_api_mode,
        acp_command=effective_acp_command,
        acp_args=effective_acp_args,
        max_iterations=max_iterations,
        max_tokens=getattr(parent_agent, "max_tokens", None),
        reasoning_config=getattr(parent_agent, "reasoning_config", None),
        prefill_messages=getattr(parent_agent, "prefill_messages", None),
        enabled_toolsets=child_toolsets,
        quiet_mode=True,
        ephemeral_system_prompt=child_prompt,
        log_prefix=f"[subagent-{task_index}]",
        platform=parent_agent.platform,
        skip_context_files=True,
        skip_memory=True,
        clarify_callback=None,
        session_db=getattr(parent_agent, '_session_db', None),
        providers_allowed=parent_agent.providers_allowed,
        providers_ignored=parent_agent.providers_ignored,
        providers_order=parent_agent.providers_order,
        provider_sort=parent_agent.provider_sort,
        tool_progress_callback=child_progress_cb,
        iteration_budget=None,  # fresh budget per subagent
    )
    # Set delegation depth so children can't spawn grandchildren
    child._delegate_depth = getattr(parent_agent, '_delegate_depth', 0) + 1

    # Stash build params so subprocess governance can rebuild with a free model if blocked
    child._delegate_meta = {
        "task_index": task_index,
        "goal": goal,
        "context": context,
        "toolsets": toolsets,
        "max_iterations": max_iterations,
        "override_provider": override_provider,
        "override_base_url": override_base_url,
        "override_api_key": override_api_key,
        "override_api_mode": override_api_mode,
    }

    # Register child for interrupt propagation
    if hasattr(parent_agent, '_active_children'):
        lock = getattr(parent_agent, '_active_children_lock', None)
        if lock:
            with lock:
                parent_agent._active_children.append(child)
        else:
            parent_agent._active_children.append(child)

    return child

def _resolve_free_fallback_runtime(child: Any, parent_agent: Any) -> Optional[Dict[str, Any]]:
    """HTTP stack for rerunning a subprocess with the free model (gemma-4-31b-it).

    Always resolves Gemini API credentials first — gemma-4-31b-it is a Google
    model and must never be sent to OpenAI, OpenRouter, or other non-Gemini
    endpoints.  Falls back to parent/child credentials ONLY if they point to a
    Gemini-compatible endpoint.
    """
    # Always prefer explicit Gemini resolution — correct provider for gemma
    try:
        from hermes_cli.runtime_provider import resolve_runtime_provider

        rt = resolve_runtime_provider(requested="gemini")
        if rt and (rt.get("api_key") or "").strip():
            return rt
    except Exception:
        pass

    # Only fall back to agent credentials if they point to a Gemini endpoint
    def _from_agent_if_gemini(agent: Any) -> Optional[Dict[str, Any]]:
        if agent is None:
            return None
        prov = (getattr(agent, "provider", None) or "").strip().lower()
        bu = (getattr(agent, "base_url", None) or "").strip().lower()
        if prov == "gemini" or "generativelanguage.googleapis.com" in bu:
            ak = (getattr(agent, "api_key", None) or "").strip()
            if not ak and hasattr(agent, "_client_kwargs"):
                ck = getattr(agent, "_client_kwargs", None) or {}
                if isinstance(ck, dict):
                    ak = (ck.get("api_key") or "").strip()
            if ak:
                return {
                    "provider": "gemini",
                    "base_url": (getattr(agent, "base_url", None) or "").strip().rstrip("/"),
                    "api_key": ak,
                    "api_mode": "chat_completions",
                }
        return None

    for ag in (child, parent_agent):
        rt = _from_agent_if_gemini(ag)
        if rt:
            return rt
    return None


def _run_single_child(
    task_index: int,
    goal: str,
    child=None,
    parent_agent=None,
    *,
    _subprocess_task_id: Optional[str] = None,
    _free_fallback_depth: int = 0,
    **_kwargs,
) -> Dict[str, Any]:
    """
    Run a pre-built child agent. Called from within a thread.
    Returns a structured result dict.

    Subprocess governance is applied here:
    - Checks model cost class before running.
    - Requires operator approval for any non-free (paid) model.
    - Enforces max duration (SUBPROCESS_MAX_SECONDS = 5 min).
    - Notifies parent agent on completion.
    """
    child_start = time.monotonic()
    child_model = getattr(child, "model", None) or ""
    task_id = _subprocess_task_id or f"delegate-{task_index}-{int(child_start)}"

    # ── Subprocess governance: enforce free-model-only policy ──────────────
    try:
        from agent.subprocess_governance import (
            SUBPROCESS_MAX_SECONDS,
            default_free_subprocess_model_id,
            enforce_subprocess_model_policy,
            is_free_subprocess_model,
            notify_completion,
        )
        _gov_approved, _gov_reason = enforce_subprocess_model_policy(
            child_model,
            goal,
            task_id,
            parent_agent=parent_agent,
        )
        if not _gov_approved:
            # Auto-fallback: rerun with configured free model (gemma-4-31b-it on Gemini API)
            # instead of blocking and forcing the parent to deliberate / ask for approval.
            if (
                _free_fallback_depth < 1
                and str(_gov_reason).startswith("denied_paid_model")
                and child is not None
                and parent_agent is not None
            ):
                fb_model = default_free_subprocess_model_id()
                if (
                    fb_model
                    and is_free_subprocess_model(fb_model)
                    and fb_model.strip().lower() != (child_model or "").strip().lower()
                ):
                    try:
                        rt = _resolve_free_fallback_runtime(child, parent_agent)
                        if rt and (rt.get("api_key") or "").strip():
                            _emit_fb = getattr(parent_agent, "_emit_status", None)
                            if callable(_emit_fb):
                                _emit_fb(
                                    f"↪ Subprocess: paid model {child_model!r} not allowed for "
                                    f"delegation — switching to free model {fb_model!r} and continuing.",
                                    "subprocess_governance",
                                )
                            # Drop blocked child from interrupt list; replacement re-registers
                            if hasattr(parent_agent, "_active_children") and child in getattr(
                                parent_agent, "_active_children", []
                            ):
                                try:
                                    parent_agent._active_children.remove(child)
                                except ValueError:
                                    pass
                            meta = getattr(child, "_delegate_meta", None) or {}
                            _mi = int(meta.get("max_iterations") or 50)
                            new_child = _build_child_agent(
                                task_index=int(meta.get("task_index", task_index)),
                                goal=str(meta.get("goal", goal)),
                                context=meta.get("context"),
                                toolsets=meta.get("toolsets"),
                                model=fb_model,
                                max_iterations=_mi,
                                parent_agent=parent_agent,
                                override_provider=rt.get("provider"),
                                override_base_url=rt.get("base_url"),
                                override_api_key=rt.get("api_key"),
                                override_api_mode=rt.get("api_mode"),
                            )
                            new_child._delegate_saved_tool_names = getattr(
                                child, "_delegate_saved_tool_names", None
                            )
                            return _run_single_child(
                                task_index,
                                str(meta.get("goal", goal)),
                                new_child,
                                parent_agent,
                                _subprocess_task_id=f"{task_id}-free-fallback",
                                _free_fallback_depth=_free_fallback_depth + 1,
                            )
                    except Exception as _fb_err:
                        logger.warning(
                            "delegate_tool: free-model auto-fallback failed: %s", _fb_err
                        )
            blocked_msg = (
                f"Subprocess blocked by governance policy: model {child_model!r} "
                f"requires operator approval for background/subprocess use. "
                f"Only free local models (gemma-4-31b-it or local inference) are permitted without approval. "
                f"Reason: {_gov_reason}"
            )
            logger.warning("delegate_tool: %s", blocked_msg)
            _emit = getattr(parent_agent, "_emit_status", None) if parent_agent else None
            if callable(_emit):
                _emit(f"⛔ {blocked_msg}", "subprocess_governance")
            return {
                "task_index": task_index,
                "goal": goal[:80],
                "status": "blocked",
                "summary": blocked_msg,
                "duration": 0,
                "api_calls": 0,
                "exit_reason": "subprocess_governance_blocked",
            }
        _gov_max_s = SUBPROCESS_MAX_SECONDS
    except Exception as _gov_err:
        logger.debug("subprocess_governance import/check failed: %s", _gov_err)
        _gov_approved = True  # fail-open if governance module is unavailable
        _gov_max_s = 300

    if parent_agent is not None and child is not None:
        _dcb = getattr(parent_agent, "on_delegate_child_model", None)
        if callable(_dcb):
            try:
                _dcb(child_model if isinstance(child_model, str) else str(child_model or ""))
            except Exception:
                logger.debug("on_delegate_child_model callback failed", exc_info=True)

    # Get the progress callback from the child agent
    child_progress_cb = getattr(child, 'tool_progress_callback', None)

    # Restore parent tool names using the value saved before child construction
    # mutated the global. This is the correct parent toolset, not the child's.
    import model_tools
    _saved_tool_names = getattr(child, "_delegate_saved_tool_names",
                                list(model_tools._last_resolved_tool_names))

    # ── Delegation context review & model gating ─────────────────────────
    try:
        from agent.delegation_review import gate_delegate_model, review_delegation_context

        _gated_model, _gate_reason = gate_delegate_model(
            child_model, getattr(parent_agent, "model", "") if parent_agent else "",
        )
        if _gated_model != child_model:
            _emit = getattr(parent_agent, "_emit_status", None) if parent_agent else None
            if callable(_emit):
                _emit(f"[Delegate] {_gate_reason}", "delegation_review")
            logger.info("delegation gating: %s", _gate_reason)

        _review = review_delegation_context(goal, _kwargs.get("context"), child_model)
        if _review.get("improved_context"):
            _extra = _review["improved_context"]
            goal = f"{goal}\n\nAdditional guidance: {_extra}"
            _emit = getattr(parent_agent, "_emit_status", None) if parent_agent else None
            if callable(_emit):
                _emit(f"[Delegate] Context enriched: {_extra[:60]}", "delegation_review")
    except Exception as _dr_err:
        logger.debug("delegation review skipped: %s", _dr_err)

    _emit = getattr(parent_agent, "_emit_status", None) if parent_agent else None
    _cost_cls = "unknown"
    try:
        from agent.subprocess_governance import classify_model_cost
        _cost_cls = classify_model_cost(child_model)
    except Exception:
        pass
    if callable(_emit):
        _emit(
            f"[Delegate] Task: {goal[:60]} -> {child_model} ({_cost_cls})",
            "delegation",
        )

    try:
        # ── Delegation watchdog: periodic heartbeat + forced wrap-up ───────
        _watchdog_stop = threading.Event()
        _HEARTBEAT_SEC = 60.0
        _FORCE_WRAPUP_SEC = float(_gov_max_s) - 30.0  # 30s before hard timeout
        _watchdog_emit = getattr(parent_agent, "_emit_status", None) if parent_agent else None
        _child_model_short = (child_model or "").rsplit("/", 1)[-1][:20]

        def _delegation_watchdog():
            _start = time.monotonic()
            _wrapup_sent = False
            while not _watchdog_stop.wait(timeout=_HEARTBEAT_SEC):
                elapsed = time.monotonic() - _start
                if callable(_watchdog_emit):
                    _iter_count = getattr(child, "_api_call_count", "?")
                    _watchdog_emit(
                        f"[Delegate] Subagent active — {int(elapsed)}s, "
                        f"iteration {_iter_count} ({_child_model_short})",
                        "delegation_heartbeat",
                    )
                if (
                    not _wrapup_sent
                    and _FORCE_WRAPUP_SEC > 0
                    and (time.monotonic() - _start) > _FORCE_WRAPUP_SEC
                ):
                    _wrapup_sent = True
                    if callable(_watchdog_emit):
                        _watchdog_emit(
                            f"[Delegate] Subagent approaching time limit "
                            f"({int(elapsed)}s/{_gov_max_s}s) — requesting wrap-up",
                            "delegation_heartbeat",
                        )
                    try:
                        child.request_interrupt()
                    except Exception:
                        pass

        _watchdog_thread = threading.Thread(
            target=_delegation_watchdog, daemon=True, name=f"delegate-watchdog-{task_id}"
        )
        _watchdog_thread.start()

        result = child.run_conversation(user_message=goal)

        _watchdog_stop.set()
        _watchdog_thread.join(timeout=2.0)

        # Flush any remaining batched progress to gateway
        if child_progress_cb and hasattr(child_progress_cb, '_flush'):
            try:
                child_progress_cb._flush()
            except Exception as e:
                logger.debug("Progress callback flush failed: %s", e)

        duration = round(time.monotonic() - child_start, 2)

        # ── Subprocess timeout check ────────────────────────────────────────
        if _gov_approved and duration > _gov_max_s:
            logger.warning(
                "delegate_tool: subprocess task_id=%s exceeded %ds limit (took %.1fs) — "
                "flagging as timed_out",
                task_id, _gov_max_s, duration,
            )
            _emit = getattr(parent_agent, "_emit_status", None) if parent_agent else None
            if callable(_emit):
                _emit(
                    f"⏱️ Subprocess {task_id} exceeded {_gov_max_s}s time limit (took {duration:.1f}s)",
                    "subprocess_governance",
                )
            try:
                from agent.subprocess_governance import update_subprocess
                update_subprocess(task_id, "timed_out")
            except Exception:
                pass

        summary = result.get("final_response") or ""
        completed = result.get("completed", False)
        interrupted = result.get("interrupted", False)
        api_calls = result.get("api_calls", 0)

        if interrupted:
            status = "interrupted"
        elif summary:
            # A summary means the subagent produced usable output.
            # exit_reason ("completed" vs "max_iterations") already
            # tells the parent *how* the task ended.
            status = "completed"
        else:
            status = "failed"

        # Build tool trace from conversation messages (already in memory).
        # Uses tool_call_id to correctly pair parallel tool calls with results.
        tool_trace: list[Dict[str, Any]] = []
        trace_by_id: Dict[str, Dict[str, Any]] = {}
        messages = result.get("messages") or []
        if isinstance(messages, list):
            for msg in messages:
                if not isinstance(msg, dict):
                    continue
                if msg.get("role") == "assistant":
                    for tc in (msg.get("tool_calls") or []):
                        fn = tc.get("function", {})
                        entry_t = {
                            "tool": fn.get("name", "unknown"),
                            "args_bytes": len(fn.get("arguments", "")),
                        }
                        tool_trace.append(entry_t)
                        tc_id = tc.get("id")
                        if tc_id:
                            trace_by_id[tc_id] = entry_t
                elif msg.get("role") == "tool":
                    content = msg.get("content", "")
                    is_error = bool(
                        content and "error" in content[:80].lower()
                    )
                    result_meta = {
                        "result_bytes": len(content),
                        "status": "error" if is_error else "ok",
                    }
                    # Match by tool_call_id for parallel calls
                    tc_id = msg.get("tool_call_id")
                    target = trace_by_id.get(tc_id) if tc_id else None
                    if target is not None:
                        target.update(result_meta)
                    elif tool_trace:
                        # Fallback for messages without tool_call_id
                        tool_trace[-1].update(result_meta)

        # Determine exit reason
        if interrupted:
            exit_reason = "interrupted"
        elif completed:
            exit_reason = "completed"
        else:
            exit_reason = "max_iterations"

        # Extract token counts (safe for mock objects)
        _input_tokens = getattr(child, "session_prompt_tokens", 0)
        _output_tokens = getattr(child, "session_completion_tokens", 0)
        _model = getattr(child, "model", None)

        entry: Dict[str, Any] = {
            "task_index": task_index,
            "status": status,
            "summary": summary,
            "api_calls": api_calls,
            "duration_seconds": duration,
            "model": _model if isinstance(_model, str) else None,
            "exit_reason": exit_reason,
            "tokens": {
                "input": _input_tokens if isinstance(_input_tokens, (int, float)) else 0,
                "output": _output_tokens if isinstance(_output_tokens, (int, float)) else 0,
            },
            "tool_trace": tool_trace,
        }
        if status == "failed":
            entry["error"] = result.get("error", "Subagent did not produce a response.")

        # ── Subprocess completion notification ─────────────────────────────
        if _gov_approved:
            try:
                from agent.subprocess_governance import notify_completion
                _notif_summary = (
                    f"Subprocess {task_id}: {status} in {duration:.1f}s "
                    f"({api_calls} API calls). "
                    + (summary[:200] if summary else "No output.")
                )
                notify_completion(task_id, _notif_summary, parent_agent=parent_agent)
            except Exception:
                logger.debug("subprocess completion notify failed", exc_info=True)

        return entry

    except Exception as exc:
        duration = round(time.monotonic() - child_start, 2)
        logging.exception(f"[subagent-{task_index}] failed")
        # Notify governance of error
        if _gov_approved:
            try:
                from agent.subprocess_governance import update_subprocess
                update_subprocess(task_id, "completed", result_summary=f"error: {exc}")
            except Exception:
                pass
        return {
            "task_index": task_index,
            "status": "error",
            "summary": None,
            "error": str(exc),
            "api_calls": 0,
            "duration_seconds": duration,
        }

    finally:
        # Stop the delegation watchdog thread
        try:
            _watchdog_stop.set()
        except Exception:
            pass

        # Restore the parent's tool names so the process-global is correct
        # for any subsequent execute_code calls or other consumers.
        import model_tools

        saved_tool_names = getattr(child, "_delegate_saved_tool_names", None)
        if isinstance(saved_tool_names, list):
            model_tools._last_resolved_tool_names = list(saved_tool_names)

        # Unregister child from interrupt propagation
        if hasattr(parent_agent, '_active_children'):
            try:
                lock = getattr(parent_agent, '_active_children_lock', None)
                if lock:
                    with lock:
                        parent_agent._active_children.remove(child)
                else:
                    parent_agent._active_children.remove(child)
            except (ValueError, UnboundLocalError) as e:
                logger.debug("Could not remove child from active_children: %s", e)

def delegate_task(
    goal: Optional[str] = None,
    context: Optional[str] = None,
    toolsets: Optional[List[str]] = None,
    tasks: Optional[List[Dict[str, Any]]] = None,
    max_iterations: Optional[int] = None,
    hermes_profile: Optional[str] = None,
    parent_agent=None,
) -> str:
    """
    Spawn one or more child agents to handle delegated tasks.

    Supports two modes:
      - Single: provide goal (+ optional context, toolsets)
      - Batch:  provide tasks array [{goal, context, toolsets}, ...]

    Returns JSON with results array, one entry per task.
    """
    if parent_agent is None:
        return json.dumps({"error": "delegate_task requires a parent agent context."})

    # Depth limit
    depth = getattr(parent_agent, '_delegate_depth', 0)
    if depth >= MAX_DEPTH:
        return json.dumps({
            "error": (
                f"Delegation depth limit reached ({MAX_DEPTH}). "
                "Subagents cannot spawn further subagents."
            )
        })

    # Load config
    cfg = _load_config()
    default_max_iter = cfg.get("max_iterations", DEFAULT_MAX_ITERATIONS)
    effective_max_iter = max_iterations or default_max_iter
    tg_cap = getattr(parent_agent, "_token_governance_delegation_max", None)
    if tg_cap is not None:
        try:
            tg_i = int(tg_cap)
            if tg_i > 0:
                effective_max_iter = min(effective_max_iter, tg_i)
        except (TypeError, ValueError):
            pass

    # Subprocess governance: cap iterations for subprocesses to max_iterations_for_subprocess.
    # This prevents runaway subagents from making excessive API calls.
    # The cap is loaded from the token governance YAML; fallback is 15.
    try:
        from agent.token_governance_runtime import load_runtime_config as _load_tg
        _tg = _load_tg()
        _subproc_cap = None
        if _tg:
            _sg = _tg.get("subprocess_governance") or {}
            _subproc_cap = _sg.get("max_iterations_for_subprocess")
        if _subproc_cap is not None:
            _sp_cap_i = int(_subproc_cap)
            if _sp_cap_i > 0:
                effective_max_iter = min(effective_max_iter, _sp_cap_i)
    except Exception:
        pass

    from agent.tier_model_routing import is_tier_dynamic

    per_task_dynamic = is_tier_dynamic(str(cfg.get("model") or ""))

    # Normalize to task list
    if tasks and isinstance(tasks, list):
        task_list = tasks[:MAX_CONCURRENT_CHILDREN]
    elif goal and isinstance(goal, str) and goal.strip():
        task_list = [{"goal": goal, "context": context, "toolsets": toolsets}]
    else:
        return json.dumps({"error": "Provide either 'goal' (single task) or 'tasks' (batch)."})

    if not task_list:
        return json.dumps({"error": "No tasks provided."})

    # Validate each task has a goal
    for i, task in enumerate(task_list):
        if not task.get("goal", "").strip():
            return json.dumps({"error": f"Task {i} is missing a 'goal'."})

    hp = (hermes_profile or "").strip() or None
    if hp and len(task_list) != 1:
        return json.dumps({
            "error": (
                "hermes_profile is only supported for a single delegated task. "
                "Use goal (and optional context/toolsets), not a multi-item tasks[] array, "
                "because profile-scoped children temporarily set process-wide HERMES_HOME."
            )
        })

    overall_start = time.monotonic()
    results: List[Dict[str, Any]] = []
    children: List[tuple] = []

    n_tasks = len(task_list)
    task_labels = [t["goal"][:40] for t in task_list]

    import model_tools as _model_tools
    _parent_tool_names = list(_model_tools._last_resolved_tool_names)

    if hp:
        t = task_list[0]
        prompt_for = (
            f"{t.get('goal') or ''}\n{t.get('context') or ''}"
            if per_task_dynamic
            else ""
        )
        try:
            creds = _resolve_delegation_credentials(cfg, parent_agent, prompt_for)
        except ValueError as exc:
            return json.dumps({"error": str(exc)})
        try:
            with _hermes_profile_env(hp):
                child = _build_child_agent(
                    task_index=0, goal=t["goal"], context=t.get("context"),
                    toolsets=t.get("toolsets") or toolsets, model=creds["model"],
                    max_iterations=effective_max_iter, parent_agent=parent_agent,
                    override_provider=creds["provider"], override_base_url=creds["base_url"],
                    override_api_key=creds["api_key"],
                    override_api_mode=creds["api_mode"],
                )
                child._delegate_saved_tool_names = _parent_tool_names
                children = [(0, t, child)]
                result = _run_single_child(0, t["goal"], child, parent_agent)
        finally:
            _model_tools._last_resolved_tool_names = _parent_tool_names
        results = [result]
    else:
        try:
            for i, t in enumerate(task_list):
                prompt_for = (
                    f"{t.get('goal') or ''}\n{t.get('context') or ''}"
                    if per_task_dynamic
                    else ""
                )
                try:
                    creds = _resolve_delegation_credentials(cfg, parent_agent, prompt_for)
                except ValueError as exc:
                    return json.dumps({"error": str(exc)})
                child = _build_child_agent(
                    task_index=i, goal=t["goal"], context=t.get("context"),
                    toolsets=t.get("toolsets") or toolsets, model=creds["model"],
                    max_iterations=effective_max_iter, parent_agent=parent_agent,
                    override_provider=creds["provider"], override_base_url=creds["base_url"],
                    override_api_key=creds["api_key"],
                    override_api_mode=creds["api_mode"],
                )
                child._delegate_saved_tool_names = _parent_tool_names
                children.append((i, t, child))
        finally:
            _model_tools._last_resolved_tool_names = _parent_tool_names

        if n_tasks == 1:
            _i, _t, child = children[0]
            result = _run_single_child(0, _t["goal"], child, parent_agent)
            results.append(result)
        else:
            completed_count = 0
            spinner_ref = getattr(parent_agent, '_delegate_spinner', None)

            with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_CHILDREN) as executor:
                futures = {}
                for i, t, child in children:
                    future = executor.submit(
                        _run_single_child,
                        task_index=i,
                        goal=t["goal"],
                        child=child,
                        parent_agent=parent_agent,
                    )
                    futures[future] = i

                for future in as_completed(futures):
                    try:
                        entry = future.result()
                    except Exception as exc:
                        idx = futures[future]
                        entry = {
                            "task_index": idx,
                            "status": "error",
                            "summary": None,
                            "error": str(exc),
                            "api_calls": 0,
                            "duration_seconds": 0,
                        }
                    results.append(entry)
                    completed_count += 1

                    idx = entry["task_index"]
                    label = task_labels[idx] if idx < len(task_labels) else f"Task {idx}"
                    dur = entry.get("duration_seconds", 0)
                    status = entry.get("status", "?")
                    icon = "✓" if status == "completed" else "✗"
                    remaining = n_tasks - completed_count
                    completion_line = f"{icon} [{idx+1}/{n_tasks}] {label}  ({dur}s)"
                    if spinner_ref:
                        try:
                            spinner_ref.print_above(completion_line)
                        except Exception:
                            print(f"  {completion_line}")
                    else:
                        print(f"  {completion_line}")

                    if spinner_ref and remaining > 0:
                        try:
                            spinner_ref.update_text(
                                f"🔀 {remaining} task{'s' if remaining != 1 else ''} remaining"
                            )
                        except Exception as e:
                            logger.debug("Spinner update_text failed: %s", e)

            results.sort(key=lambda r: r["task_index"])

    if parent_agent and hasattr(parent_agent, '_memory_manager') and parent_agent._memory_manager:
        for entry in results:
            try:
                idx = entry["task_index"]
                _task_goal = (
                    task_list[idx]["goal"] if idx < len(task_list) else ""
                )
                ch = children[idx][2] if idx < len(children) else None
                parent_agent._memory_manager.on_delegation(
                    task=_task_goal,
                    result=entry.get("summary", "") or "",
                    child_session_id=getattr(ch, "session_id", "") if ch is not None else "",
                )
            except Exception:
                pass

    total_duration = round(time.monotonic() - overall_start, 2)

    if hp:
        try:
            from hermes_cli.profiles import record_profile_usage

            record_profile_usage(hp, kind="delegate")
        except Exception:
            pass

    return json.dumps({
        "results": results,
        "total_duration_seconds": total_duration,
    }, ensure_ascii=False)


def hand_off_to_profile(
    profile_name: str,
    user_request: str,
    context_summary: str = "",
    parent_agent=None,
) -> str:
    """Model-facing alias: run a single delegated task under another Hermes profile.

    Same isolation as ``delegate_task`` with ``hermes_profile`` — use when the
    current role should pass work to a specialist profile without asking the
    operator to switch ``active_profile``.
    """
    pn = (profile_name or "").strip()
    if not pn:
        return json.dumps({"error": "profile_name is required"})
    ur = (user_request or "").strip()
    if not ur:
        return json.dumps({"error": "user_request is required"})
    return delegate_task(
        goal=ur,
        context=(context_summary or "").strip(),
        hermes_profile=pn,
        parent_agent=parent_agent,
    )


def _resolve_delegation_credentials(
    cfg: dict,
    parent_agent,
    prompt_for_tier: str = "",
) -> dict:
    """Resolve credentials for subagent delegation.

    If ``delegation.base_url`` is configured, subagents use that direct
    OpenAI-compatible endpoint. Otherwise, if ``delegation.provider`` is
    configured, the full credential bundle (base_url, api_key, api_mode,
    provider) is resolved via the runtime provider system — the same path used
    by CLI/gateway startup. This lets subagents run on a completely different
    provider:model pair.

    If neither base_url nor provider is configured, returns None values so the
    child inherits everything from the parent agent.

    When ``delegation.model`` is ``tier:dynamic``, the concrete model is chosen
    per call from governance ``tier_models`` using the same heuristics as the
    main agent (pass *prompt_for_tier* with goal + context for batch tasks).

    Raises ValueError with a user-friendly message on credential failure.
    """
    configured_model = str(cfg.get("model") or "").strip() or None
    if configured_model:
        from agent.tier_model_routing import is_tier_dynamic, resolve_tier_dynamic_model

        if is_tier_dynamic(configured_model):
            rm = resolve_tier_dynamic_model(prompt_for_tier, None)
            if rm:
                configured_model = rm
    configured_provider = str(cfg.get("provider") or "").strip() or None
    configured_base_url = str(cfg.get("base_url") or "").strip() or None
    configured_api_key = str(cfg.get("api_key") or "").strip() or None

    # Gemma routing hard rule:
    # If Gemma is selected for delegation and no explicit provider/base_url was
    # requested, prefer direct Gemini API first. OpenRouter is a paid last resort.
    _cmid = (configured_model or "").strip().lower()
    _is_gemma = _cmid in ("gemma-4-31b-it", "gemma-4") or _cmid.endswith("/gemma-4-31b-it")
    if _is_gemma and not configured_provider and not configured_base_url:
        from agent.tier_model_routing import canonical_gemma_model_id
        from hermes_cli.runtime_provider import resolve_runtime_provider

        configured_model = canonical_gemma_model_id(configured_model)
        # First try direct Google Gemini API.
        try:
            rt = resolve_runtime_provider(requested="gemini")
            if (rt.get("api_key") or "").strip():
                return {
                    "model": configured_model,
                    "provider": rt.get("provider"),
                    "base_url": rt.get("base_url"),
                    "api_key": rt.get("api_key"),
                    "api_mode": rt.get("api_mode"),
                    "command": rt.get("command"),
                    "args": list(rt.get("args") or []),
                }
        except Exception:
            pass
        # Only if Gemini is unavailable, fall back to OpenRouter.
        try:
            rt = resolve_runtime_provider(requested="openrouter")
            if (rt.get("api_key") or "").strip():
                _or_model = configured_model
                if "/" not in _or_model:
                    _or_model = f"google/{_or_model}"
                return {
                    "model": _or_model,
                    "provider": rt.get("provider"),
                    "base_url": rt.get("base_url"),
                    "api_key": rt.get("api_key"),
                    "api_mode": rt.get("api_mode"),
                    "command": rt.get("command"),
                    "args": list(rt.get("args") or []),
                }
        except Exception:
            pass

    if configured_base_url:
        api_key = (
            configured_api_key
            or os.getenv("OPENAI_API_KEY", "").strip()
        )
        if not api_key:
            raise ValueError(
                "Delegation base_url is configured but no API key was found. "
                "Set delegation.api_key or OPENAI_API_KEY."
            )

        base_lower = configured_base_url.lower()
        provider = "custom"
        api_mode = "chat_completions"
        if "chatgpt.com/backend-api/codex" in base_lower:
            provider = "openai-codex"
            api_mode = "codex_responses"
        elif "api.anthropic.com" in base_lower:
            provider = "anthropic"
            api_mode = "anthropic_messages"

        return {
            "model": configured_model,
            "provider": provider,
            "base_url": configured_base_url,
            "api_key": api_key,
            "api_mode": api_mode,
        }

    if not configured_provider:
        # No provider override — child inherits everything from parent
        return {
            "model": configured_model,
            "provider": None,
            "base_url": None,
            "api_key": None,
            "api_mode": None,
        }

    # Provider is configured — resolve full credentials
    try:
        from hermes_cli.runtime_provider import resolve_runtime_provider
        runtime = resolve_runtime_provider(requested=configured_provider)
    except Exception as exc:
        raise ValueError(
            f"Cannot resolve delegation provider '{configured_provider}': {exc}. "
            f"Check that the provider is configured (API key set, valid provider name), "
            f"or set delegation.base_url/delegation.api_key for a direct endpoint. "
            f"Available providers: openrouter, nous, zai, kimi-coding, minimax."
        ) from exc

    api_key = runtime.get("api_key", "")
    if not api_key:
        raise ValueError(
            f"Delegation provider '{configured_provider}' resolved but has no API key. "
            f"Set the appropriate environment variable or run 'hermes login'."
        )

    return {
        "model": configured_model,
        "provider": runtime.get("provider"),
        "base_url": runtime.get("base_url"),
        "api_key": api_key,
        "api_mode": runtime.get("api_mode"),
        "command": runtime.get("command"),
        "args": list(runtime.get("args") or []),
    }


def _load_config() -> dict:
    """Load delegation config from CLI_CONFIG or persistent config.

    Checks the runtime config (cli.py CLI_CONFIG) first, then falls back
    to the persistent config (hermes_cli/config.py load_config()) so that
    ``delegation.model`` / ``delegation.provider`` are picked up regardless
    of the entry point (CLI, gateway, cron).
    """
    try:
        from cli import CLI_CONFIG
        cfg = CLI_CONFIG.get("delegation", {})
        if cfg:
            return cfg
    except Exception:
        pass
    try:
        from hermes_cli.config import load_config
        full = load_config()
        return full.get("delegation", {})
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# OpenAI Function-Calling Schema
# ---------------------------------------------------------------------------

DELEGATE_TASK_SCHEMA = {
    "name": "delegate_task",
    "description": (
        "Spawn one or more subagents to work on tasks in isolated contexts. "
        "Each subagent gets its own conversation, terminal session, and toolset. "
        "Only the final summary is returned -- intermediate tool results "
        "never enter your context window.\n\n"
        "TWO MODES (one of 'goal' or 'tasks' is required):\n"
        "1. Single task: provide 'goal' (+ optional context, toolsets)\n"
        "2. Batch (parallel): provide 'tasks' array with up to 3 items. "
        "All run concurrently and results are returned together.\n\n"
        "WHEN TO USE delegate_task:\n"
        "- Reasoning-heavy subtasks (debugging, code review, research synthesis)\n"
        "- Tasks that would flood your context with intermediate data\n"
        "- Parallel independent workstreams (research A and B simultaneously)\n\n"
        "WHEN NOT TO USE (use these instead):\n"
        "- Mechanical multi-step work with no reasoning needed -> use execute_code\n"
        "- Single tool call -> just call the tool directly\n"
        "- Tasks needing user interaction -> subagents cannot use clarify\n\n"
        "IMPORTANT:\n"
        "- Subagents have NO memory of your conversation. Pass all relevant "
        "info (file paths, error messages, constraints) via the 'context' field.\n"
        "- Subagents CANNOT call: delegate_task, clarify, memory, send_message, "
        "slack_channel_admin, telegram_forum_topic, execute_code.\n"
        "- Each subagent gets its own terminal session (separate working directory and state).\n"
        "- Optional hermes_profile: run the subagent under that named Hermes profile's "
        "HERMES_HOME (toolsets, keys, gateway state isolated). Single-task only; "
        "create profiles with scripts/core/bootstrap_org_agent_profiles.py.\n"
        "- Prefer ``hand_off_to_profile`` when explicitly handing off to another role profile "
        "(same mechanics as hermes_profile delegation).\n"
        "- Results are always returned as an array, one entry per task."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "goal": {
                "type": "string",
                "description": (
                    "What the subagent should accomplish. Be specific and "
                    "self-contained -- the subagent knows nothing about your "
                    "conversation history."
                ),
            },
            "context": {
                "type": "string",
                "description": (
                    "Background information the subagent needs: file paths, "
                    "error messages, project structure, constraints. The more "
                    "specific you are, the better the subagent performs."
                ),
            },
            "toolsets": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Toolsets to enable for this subagent. "
                    "Default: inherits your enabled toolsets. "
                    "Common patterns: ['terminal', 'file'] for code work, "
                    "['web'] for research, ['terminal', 'file', 'web'] for "
                    "full-stack tasks."
                ),
            },
            "tasks": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "goal": {"type": "string", "description": "Task goal"},
                        "context": {"type": "string", "description": "Task-specific context"},
                        "toolsets": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Toolsets for this specific task",
                        },
                    },
                    "required": ["goal"],
                },
                "maxItems": 3,
                "description": (
                    "Batch mode: up to 3 tasks to run in parallel. Each gets "
                    "its own subagent with isolated context and terminal session. "
                    "When provided, top-level goal/context/toolsets are ignored."
                ),
            },
            "max_iterations": {
                "type": "integer",
                "description": (
                    "Max tool-calling turns per subagent (default: 50). "
                    "Only set lower for simple tasks."
                ),
            },
            "hermes_profile": {
                "type": "string",
                "description": (
                    "Named Hermes profile (under ~/.hermes/profiles/<name>) whose HERMES_HOME "
                    "the subagent uses for config, tool availability, and filesystem scope. "
                    "Must be omitted when using batch tasks[] with more than one item."
                ),
            },
        },
        "required": [],
    },
}


# --- Registry ---
from tools.registry import registry

HAND_OFF_PROFILE_SCHEMA = {
    "name": "hand_off_to_profile",
    "description": (
        "Hand off the user's request to another Hermes profile (separate HERMES_HOME). "
        "Use when the task clearly belongs to a different org role (e.g. security review → "
        "security-focused profile). Runs one delegated subagent with that profile's "
        "config and toolsets; returns the specialist's summary to you. "
        "Does not change the operator's sticky profile — same as delegate_task with "
        "hermes_profile. Profile slug must exist under ~/.hermes/profiles/<name>."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "profile_name": {
                "type": "string",
                "description": "Target profile slug (kebab-case), e.g. chief-security-governor",
            },
            "user_request": {
                "type": "string",
                "description": "What the specialist should do (the substantive ask).",
            },
            "context_summary": {
                "type": "string",
                "description": "Optional: constraints, file paths, prior findings for the specialist.",
            },
        },
        "required": ["profile_name", "user_request"],
    },
}


registry.register(
    name="delegate_task",
    toolset="delegation",
    schema=DELEGATE_TASK_SCHEMA,
    handler=lambda args, **kw: delegate_task(
        goal=args.get("goal"),
        context=args.get("context"),
        toolsets=args.get("toolsets"),
        tasks=args.get("tasks"),
        max_iterations=args.get("max_iterations"),
        hermes_profile=args.get("hermes_profile"),
        parent_agent=kw.get("parent_agent")),
    check_fn=check_delegate_requirements,
    emoji="🔀",
)

registry.register(
    name="hand_off_to_profile",
    toolset="delegation",
    schema=HAND_OFF_PROFILE_SCHEMA,
    handler=lambda args, **kw: hand_off_to_profile(
        profile_name=args.get("profile_name", ""),
        user_request=args.get("user_request", ""),
        context_summary=args.get("context_summary", ""),
        parent_agent=kw.get("parent_agent"),
    ),
    check_fn=check_delegate_requirements,
    emoji="🎯",
)
