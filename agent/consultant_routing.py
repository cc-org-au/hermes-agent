"""Chief-orchestrator consultant routing (policy-aligned, no human operator approval).

Implements a hybrid of deterministic tier heuristics + optional cheap-router LLM, with
internal challenger + Chief deliberation for tiers that require it. Deliberation is logged
to ``workspace/operations/consultant_deliberations.jsonl`` — not injected into the user
dialogue (only a short status line may appear).

Disable entirely with ``HERMES_CONSULTANT_ROUTING_DISABLE=1``.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

ENV_DISABLE = "HERMES_CONSULTANT_ROUTING_DISABLE"

# Substrings typical of multi-step activation / org-governance session prompts (case-insensitive).
_DEFAULT_GOV_ACTIVATION_KW = (
    "activation protocol",
    "handoff",
    "verification",
    "org_registry",
    "org_chart",
    "policy_root",
    "rem-",
    "session ",  # "Session 7"
    "governance",
    "deployment order",
    "sub-agents",
    "sub_agents",
    "role-prompts",
    "executable",
    "outstanding tasks",
)


def governance_activation_signal(user_message: str, cr: Dict[str, Any]) -> bool:
    """True when the user text looks like a long activation / governance session brief."""
    t = (user_message or "").strip()
    try:
        min_c = int(cr.get("governance_activation_min_chars") or 1600)
    except (TypeError, ValueError):
        min_c = 1600
    try:
        min_h = int(cr.get("governance_activation_min_hits") or 3)
    except (TypeError, ValueError):
        min_h = 3
    if len(t) < min_c:
        return False
    low = t.lower()
    kws = cr.get("governance_activation_keywords")
    if isinstance(kws, str):
        kws = [kws]
    if not isinstance(kws, list) or not kws:
        kws = _DEFAULT_GOV_ACTIVATION_KW
    hits = sum(1 for k in kws if str(k).lower() in low)
    return hits >= min_h


def _cr_cfg(gov: Dict[str, Any]) -> Dict[str, Any]:
    raw = gov.get("consultant_routing")
    return raw if isinstance(raw, dict) else {}


def consultant_routing_enabled(gov: Optional[Dict[str, Any]]) -> bool:
    if os.environ.get(ENV_DISABLE, "").strip().lower() in ("1", "true", "yes"):
        return False
    if not gov or not gov.get("enabled", False):
        return False
    cr = _cr_cfg(gov)
    return bool(cr.get("enabled"))


def _deliberations_log_path() -> Any:
    from hermes_constants import get_hermes_home

    p = get_hermes_home() / "workspace" / "operations" / "consultant_deliberations.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _append_deliberation_record(record: Dict[str, Any]) -> None:
    try:
        path = _deliberations_log_path()
        line = json.dumps(record, ensure_ascii=False) + "\n"
        with open(path, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        logger.debug("consultant deliberation log failed", exc_info=True)


def _extract_json_object(text: str) -> Optional[Dict[str, Any]]:
    if not text or not text.strip():
        return None
    text = text.strip()
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        return None
    try:
        out = json.loads(m.group(0))
        return out if isinstance(out, dict) else None
    except json.JSONDecodeError:
        return None


def _normalize_tier_letter(ch: str, tier_models: Dict[str, str]) -> Optional[str]:
    u = str(ch or "").strip().upper()
    if len(u) == 1 and u in tier_models:
        return u
    return None


def _tier_order() -> List[str]:
    return ["A", "B", "C", "D", "E", "F"]


def _max_tier(a: str, b: str) -> str:
    """Higher cost / later letter in A–F."""
    order = _tier_order()
    ia = order.index(a) if a in order else 0
    ib = order.index(b) if b in order else 0
    return a if ia >= ib else b


def _min_tier_cost(a: str, b: str) -> str:
    """Lower cost / earlier letter in A–F."""
    order = _tier_order()
    ia = order.index(a) if a in order else 0
    ib = order.index(b) if b in order else 0
    return a if ia <= ib else b


def _call_aux_task(
    task: str,
    system: str,
    user: str,
    max_tokens: int = 512,
    *,
    agent: Any = None,
) -> str:
    from agent.auxiliary_client import call_llm, extract_content_or_reasoning

    msgs = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    # Session override takes highest priority (user chose a specific router via /models router).
    override = getattr(agent, "_router_session_override", None) if agent is not None else None
    if isinstance(override, dict):
        prov = str(override.get("provider") or "").strip()
        mod = str(override.get("model") or "").strip()
        bu = str(override.get("base_url") or "").strip()
        ak = str(override.get("api_key") or "").strip()
        if prov and mod:
            if prov == "custom" and bu:
                from agent.openai_native_runtime import native_openai_api_key

                ak = ak or native_openai_api_key()
                resp = call_llm(
                    task=None,
                    provider="custom",
                    model=mod,
                    base_url=bu,
                    api_key=ak or None,
                    messages=msgs,
                    temperature=0.2,
                    max_tokens=max_tokens,
                )
                return extract_content_or_reasoning(resp) or ""
            resp = call_llm(
                task=None,
                provider=prov,
                model=mod,
                messages=msgs,
                temperature=0.2,
                max_tokens=max_tokens,
            )
            return extract_content_or_reasoning(resp) or ""

    # For routing/classification tasks: prefer GPT-5.4 via native OpenAI.
    # This gives genuinely dynamic, non-static routing decisions rather than
    # always falling back to the same Gemini model. Challenger/chief tasks also
    # benefit from GPT-5.4's nuanced judgment.
    _ROUTING_TASKS = ("consultant_router", "consultant_challenger", "consultant_chief",
                      "profile_router")
    if task in _ROUTING_TASKS:
        try:
            from agent.openai_native_runtime import native_openai_runtime_tuple
            _rt = native_openai_runtime_tuple()
            bt, ak = _rt if _rt else (None, None)
            if bt and ak:
                resp = call_llm(
                    task=None,
                    provider="custom",
                    model="gpt-5.4",
                    base_url=bt,
                    api_key=ak,
                    messages=msgs,
                    temperature=0.2,
                    max_tokens=max_tokens,
                )
                result = extract_content_or_reasoning(resp) or ""
                if result:
                    logger.debug("_call_aux_task: used GPT-5.4 for task=%s", task)
                    return result
        except Exception as exc:
            logger.debug("_call_aux_task: GPT-5.4 routing failed for %s, falling back: %s", task, exc)

    resp = call_llm(
        task,
        messages=msgs,
        temperature=0.2,
        max_tokens=max_tokens,
    )
    return extract_content_or_reasoning(resp) or ""


_PUSHBACK_PHRASES = (
    "that's not what i asked",
    "that's not what i said",
    "that's not what i want",
    "you didn't",
    "you ignored",
    "still not",
    "still wrong",
    "still incorrect",
    "still not right",
    "again wrong",
    "no, you",
    "no that's wrong",
    "no that is wrong",
    "not right",
    "not correct",
    "incorrect",
    "wrong again",
    "try again",
    "do it again",
    "redo this",
    "do it properly",
    "do it correctly",
    "that missed",
    "you missed",
    "you failed",
    "this is wrong",
    "this is not",
    "this isn't",
    "still haven't",
    "still not done",
    "not what i meant",
    "doesn't work",
    "doesn't do what",
    "fix it",
    "please fix",
    "please redo",
    "please try again",
    "still broken",
    "not working",
)


def is_pushback_message(text: str) -> bool:
    """Return True when the user message looks like explicit dissatisfaction / pushback."""
    if not text:
        return False
    low = text.strip().lower()
    # Very short emphatic openers
    first_50 = low[:50]
    if first_50.startswith(("no,", "no.", "wrong.", "wrong,", "nope", "incorrect")):
        return True
    return any(p in low for p in _PUSHBACK_PHRASES)


def resolve_consultant_tier(
    user_message: str,
    gov_cfg: Dict[str, Any],
    deterministic_tier: str,
    tier_models: Dict[str, str],
    *,
    agent: Any = None,
    pushback_signal: bool = False,
    retry_count: int = 0,
) -> Tuple[str, Dict[str, Any]]:
    """Return (final_tier_letter, audit dict) after optional router + deliberation.

    Args:
        pushback_signal: True when the user explicitly pushed back on the previous response.
        retry_count: Number of times this task has already been attempted at the same tier.
    """
    cr = _cr_cfg(gov_cfg)
    mode = str(cr.get("mode") or "hybrid").strip().lower()
    audit: Dict[str, Any] = {
        "deterministic_tier": deterministic_tier,
        "mode": mode,
        "deliberation": None,
        "router": None,
        "pushback_signal": pushback_signal,
        "retry_count": retry_count,
    }

    # Hard-escalate on push-back or repeated failure: skip LLM routing, go straight to E.
    if (pushback_signal or retry_count >= 3) and deterministic_tier not in ("E", "F"):
        forced = "E"
        audit["forced_escalation"] = (
            "pushback" if pushback_signal else f"retry_count={retry_count}"
        )
        logger.info(
            "consultant_routing: hard-escalating to %s (%s)", forced, audit["forced_escalation"]
        )
        deterministic_tier = forced

    if mode == "deterministic":
        return deterministic_tier, audit

    skip_tiers = cr.get("skip_router_when_tier_in")
    if isinstance(skip_tiers, str):
        skip_tiers = [skip_tiers]
    if not isinstance(skip_tiers, list):
        skip_tiers = []
    skip_tiers_u = {str(x).strip().upper() for x in skip_tiers if x}
    if deterministic_tier in skip_tiers_u:
        audit["skipped_router"] = "deterministic_tier_in_skip_list"
        return deterministic_tier, audit

    tiers_delib = cr.get("tiers_requiring_deliberation") or ["E", "F", "G"]
    if isinstance(tiers_delib, str):
        tiers_delib = [tiers_delib]
    tiers_delib_u = {str(x).strip().upper() for x in tiers_delib if x}

    router_task = str(cr.get("router_task") or "consultant_router").strip()
    challenger_task = str(cr.get("challenger_task") or "consultant_challenger").strip()
    chief_task = str(cr.get("chief_task") or "consultant_chief").strip()

    gov_sig = governance_activation_signal(user_message, cr)
    audit["governance_activation_signal"] = gov_sig

    pushback = audit.get("pushback_signal", False)
    retry_count = int(audit.get("retry_count") or 0)

    # --- LLM router (hybrid / llm) ---
    if mode in ("hybrid", "llm"):
        pushback_hint = ""
        if pushback:
            pushback_hint = (
                "\n\n[ESCALATION SIGNAL] The user has explicitly pushed back on the previous "
                "response — they indicated it did not meet their requirements. This is a strong "
                "signal to escalate to E or F. Set request_consultant_escalation=true and "
                "recommend at least tier E unless the task is trivially simple."
            )
        retry_hint = ""
        if retry_count >= 2:
            retry_hint = (
                f"\n\n[RETRY LOOP SIGNAL] This task has failed or been rejected {retry_count} times. "
                "The current tier is clearly insufficient. Escalate: recommend E or F and set "
                "request_consultant_escalation=true."
            )
        sys_router = (
            "You are an intelligent routing advisor for a multi-tier AI organization. "
            "Tiers A–G all have API costs — NONE are free. Match tier strictly to genuine task complexity.\n"
            "- Tier A: one-liners, trivial ack/lookup, pure formatting (low-cost Gemini via direct Google API)\n"
            "- Tier B: short/simple tasks, renames, single-file edits (low-cost Gemini via direct Google API)\n"
            "- Tier C: multi-step reasoning, moderate analysis, batch ops (low-cost Gemini Pro via direct Google API)\n"
            "- Tier D: complex tasks, most consultations, writing, planning, debugging (claude-sonnet-4.6)\n"
            "- Tier E: hardest non-coding reasoning, ambiguous multi-domain problems (gpt-5.4)\n"
            "- Tier F: deep engineering, architecture, refactors, complex code generation (gpt-5.3-codex)\n"
            "- Tier G: RARE — Claude Opus 4.6 consultant; only when the router believes Opus can route "
            "better/cheaper/more comprehensively than the OpenAI router, or for the absolute hardest "
            "multi-domain problems. Single-turn only. Always requires deliberation+approval.\n\n"
            "COST PRIORITY: Always prefer direct API sources (Google Gemini API, OpenAI API, Anthropic API) "
            "over OpenRouter. OpenRouter is ALWAYS paid even for models that are free via their native API. "
            "gemma-4-31b-it via direct Gemini API = free; via OpenRouter = paid.\n"
            "ROUTING BIAS: Use A/B/C for the bulk of routine/menial work (lowest API cost). "
            "Optimize for the lowest cost that delivers the performance the task requires. "
            "Only escalate to D for genuinely complex tasks. Only escalate to E/F for the hardest tasks "
            "or after repeated failures. Tier G is reserved for extraordinary cases.\n"
            "CONSULTANT ESCALATION: When the task genuinely warrants D/E/F/G, set request_consultant_escalation=true "
            "and the deliberation system (challenger + chief review) will run an agentic discussion before approving. "
            "Do NOT suppress escalation — the deliberation system is the gatekeeping mechanism.\n"
            "IMPORTANT: Set request_consultant_escalation=true whenever you recommend E, F, or G. "
            "For coding/engineering tasks that warrant consultant escalation, prefer F over E."
        )
        hint = ""
        if gov_sig:
            hint = (
                "\n\n[CLASSIFIER] This message matches org activation/governance session heuristics "
                "(long structured brief with handoff, registry, or remediation-style tasks). "
                "These sessions almost always benefit from E or F. Recommend E or F and set "
                "request_consultant_escalation=true unless the task is genuinely trivial."
            )
        user_router = (
            f"Deterministic baseline tier (from heuristics): {deterministic_tier}\n\n"
            f"User message:\n---\n{(user_message or '')[:12000]}\n---\n\n"
            f"{hint}{pushback_hint}{retry_hint}"
            "Reply with ONLY a JSON object, no markdown fences:\n"
            '{"recommended_tier":"B"|"C"|"D"|"E"|"F"|"G", '
            '"request_consultant_escalation": true or false, '
            '"rationale": "one short sentence"}\n'
            "Rules: set request_consultant_escalation=true whenever recommended_tier is E, F, or G. "
            "Actively recommend E/F for complex multi-step, architectural, security-sensitive, "
            "or previously-failed tasks."
        )
        # --- Unified routing engine (GPT-5.4 primary, Gemini Flash fallback) ---
        # Attempt routing_engine.route_prompt first for unified tier + free_model_brief.
        # Only use its result when it actually got an LLM response (parsed=True).
        # Otherwise fall through to the legacy _call_aux_task path.
        rec = None
        esc = False
        free_model_brief = None
        coding_task_hint = False
        _used_routing_engine = False
        try:
            from agent.routing_engine import route_prompt as _route_prompt

            _conv = getattr(agent, "_conversation_history_for_routing", None)
            _route = _route_prompt(
                user_message,
                available_profiles=None,
                conversation_messages=_conv,
                fallback_tier=deterministic_tier,
            )
            if _route.audit.get("parsed"):
                rec = _normalize_tier_letter(_route.tier, tier_models)
                esc = _route.tier in ("E", "F", "G")
                free_model_brief = _route.free_model_brief
                coding_task_hint = _route.coding_task
                audit["router"] = {
                    "raw_excerpt": (_route.audit.get("raw_excerpt") or "")[:500],
                    "recommended_tier": rec,
                    "request_consultant_escalation": esc,
                    "rationale": "routing_engine unified decision",
                    "free_model_brief": free_model_brief,
                    "coding_task": coding_task_hint,
                    "background_task": _route.background_task,
                    "profile_suggestion": _route.profile,
                }
                _used_routing_engine = True
        except Exception as _re_err:
            logger.debug("routing_engine import/call failed: %s", _re_err)

        if not _used_routing_engine:
            # Legacy fallback: _call_aux_task (also used by tests that mock it)
            try:
                raw_r = _call_aux_task(
                    router_task, sys_router, user_router, max_tokens=400, agent=agent
                )
                parsed = _extract_json_object(raw_r) or {}
                rec = _normalize_tier_letter(str(parsed.get("recommended_tier") or ""), tier_models)
                esc = bool(parsed.get("request_consultant_escalation"))
                audit["router"] = {
                    "raw_excerpt": raw_r[:2000],
                    "recommended_tier": rec,
                    "request_consultant_escalation": esc,
                    "rationale": str(parsed.get("rationale") or "")[:500],
                }
            except Exception as e:
                logger.info("consultant router LLM failed; using deterministic tier: %s", e)
                audit["router"] = {"error": str(e)}
                return deterministic_tier, audit

        if rec is None:
            return deterministic_tier, audit

        # coding_task hint: prefer tier F (gpt-5.3-codex) over E when escalating to consultant.
        if coding_task_hint and rec == "E" and "F" in tier_models:
            logger.debug("routing_engine: coding_task hint — upgrading E → F (gpt-5.3-codex)")
            rec = "F"
            esc = True
            if isinstance(audit.get("router"), dict):
                audit["router"]["recommended_tier"] = rec
                audit["router"]["coding_task_upgrade"] = True

        if mode == "llm":
            # Router may downgrade below deterministic or upgrade; still subject to deliberation gates.
            merged = rec
        else:
            # Hybrid: do not serve a cheaper tier than deterministic heuristics (stability).
            merged = _max_tier(deterministic_tier, rec)

        # Optional opt-in: raise merged tier floor when governance signal fires (forces deliberation).
        floor_raw = cr.get("governance_activation_deliberation_floor")
        if gov_sig and floor_raw not in (None, "", False):
            fl = _normalize_tier_letter(str(floor_raw), tier_models)
            if fl:
                before = merged
                merged = _max_tier(merged, fl)
                if merged != before:
                    audit["governance_deliberation_floor"] = fl

        need_delib = merged in tiers_delib_u or esc
        # When the live model is openrouter/auto, require deliberation for upper tiers
        # so expensive consultant-class routes are explicitly approved by challenger+chief.
        _agent_model = str(getattr(agent, "model", "") or "").strip().lower() if agent is not None else ""
        if _agent_model == "openrouter/auto" and merged in ("D", "E", "F", "G"):
            need_delib = True
            audit["auto_router_deliberation_guard"] = True

        if "openrouter" in _agent_model and merged == "G":
            need_delib = True
            audit["openrouter_consultant_deliberation_guard"] = True

        max_sess = cr.get("max_deliberations_per_session")
        if need_delib and max_sess is not None and agent is not None:
            try:
                cap_n = int(max_sess)
                cur = int(getattr(agent, "_consultant_deliberation_count", 0) or 0)
                if cap_n >= 0 and cur >= cap_n:
                    cap_letter = str(cr.get("cap_tier_when_deliberation_exhausted") or "D").strip().upper()
                    if len(cap_letter) == 1 and cap_letter in tier_models:
                        merged = _min_tier_cost(merged, cap_letter)
                    need_delib = False
                    audit["deliberation_session_cap"] = cap_n
            except (TypeError, ValueError):
                pass

        if not need_delib:
            audit["final_without_deliberation"] = merged
            return merged, audit

        # --- Internal challenger + Chief (not shown in main chat) ---
        session = getattr(agent, "session_id", None) or ""
        turn_id = str(uuid.uuid4())[:12]
        excerpt = (user_message or "")[:4000]

        sys_ch = (
            "You challenge routing decisions to prevent unnecessary spend. "
            "Be concise. Reply JSON only."
        )
        user_ch = (
            f"Router recommended tier {merged} for this request. Rationale: "
            f"{audit['router'].get('rationale', '')}\n\n"
            f"Request excerpt:\n{excerpt}\n\n"
            '{"challenge":"...", "max_reasonable_tier":"B"|"C"|"D"|"E"|"F"|"G"}'
        )
        try:
            raw_ch = _call_aux_task(
                challenger_task, sys_ch, user_ch, max_tokens=350, agent=agent
            )
            ch_p = _extract_json_object(raw_ch) or {}
        except Exception as e:
            ch_p = {"challenge": f"(challenger failed: {e})", "max_reasonable_tier": "D"}
        max_rt = _normalize_tier_letter(str(ch_p.get("max_reasonable_tier") or "D"), tier_models)
        if max_rt is None:
            max_rt = "D"

        sys_chef = (
            "You are the Chief Orchestrator. You alone approve use of premium consultant tiers "
            "(E/F/G) after internal challenge. Operators are not asked for approval. "
            "Approve consultant-class tiers only when the request truly requires them. "
            "Tier G (Claude Opus 4.6) is the most expensive — approve ONLY for extraordinary "
            "tasks and only for a single turn. Reply JSON only."
        )
        user_chef = (
            f"Deterministic baseline: {deterministic_tier}. Router tier: {merged}. "
            f"Router rationale: {audit['router'].get('rationale', '')}\n"
            f"Challenger: {ch_p.get('challenge', '')}\n"
            f"Challenger max_reasonable_tier: {max_rt}\n\n"
            f"Full request:\n{excerpt}\n\n"
            '{"approved_consultant_tier": true|false, "final_tier": "B"|"C"|"D"|"E"|"F"|"G", '
            '"decision_summary": "one line"}\n'
            "Tier G (Claude Opus 4.6) is single-turn only and the most expensive option — "
            "approve only for extraordinary multi-domain problems where Opus specifically "
            "adds value over GPT-5.4/Codex. "
            "If approved_consultant_tier is false, set final_tier to at most the challenger "
            "max_reasonable_tier (or lower)."
        )
        try:
            raw_cf = _call_aux_task(
                chief_task, sys_chef, user_chef, max_tokens=400, agent=agent
            )
            cf_p = _extract_json_object(raw_cf) or {}
        except Exception as e:
            logger.info("consultant chief deliberation failed; capping at D: %s", e)
            audit["deliberation"] = {"error": str(e), "fallback": "D"}
            cap = "D"
            final = _normalize_tier_letter(cap, tier_models) or deterministic_tier
            if final in tier_models:
                return final, audit
            return deterministic_tier, audit

        approved = bool(cf_p.get("approved_consultant_tier"))
        fin = _normalize_tier_letter(str(cf_p.get("final_tier") or ""), tier_models)
        if fin is None:
            fin = deterministic_tier

        if approved:
            if fin not in tier_models:
                fin = merged if merged in tier_models else deterministic_tier
            if fin == "G" and agent is not None:
                setattr(agent, "_opus_single_turn_active", True)
                opus_max = 2
                try:
                    opus_max = int(cr.get("opus_max_per_session") or 2)
                except (TypeError, ValueError):
                    pass
                opus_cnt = int(getattr(agent, "_opus_escalation_count", 0) or 0)
                if opus_cnt >= opus_max:
                    fin = "F" if "F" in tier_models else deterministic_tier
                    audit["opus_session_cap_hit"] = True
                else:
                    setattr(agent, "_opus_escalation_count", opus_cnt + 1)
        else:
            # Cap at challenger's max_reasonable_tier (chief denied premium consultant use).
            fin = _normalize_tier_letter(str(cf_p.get("final_tier") or max_rt), tier_models) or max_rt
            fin = _min_tier_cost(fin, max_rt)

        audit["deliberation"] = {
            "turn_id": turn_id,
            "session_id": session,
            "challenger": ch_p,
            "chief_raw_excerpt": raw_cf[:2000],
            "chief": cf_p,
            "approved_consultant_tier": approved,
        }

        _append_deliberation_record(
            {
                "ts": time.time(),
                "turn_id": turn_id,
                "session_id": session,
                "deterministic_tier": deterministic_tier,
                "router": audit.get("router"),
                "deliberation": audit["deliberation"],
                "final_tier": fin,
            }
        )

        try:
            cnt = getattr(agent, "_consultant_deliberation_count", 0) or 0
            setattr(agent, "_consultant_deliberation_count", int(cnt) + 1)
        except Exception:
            pass

        return fin, audit

    return deterministic_tier, audit


def format_status_line(audit: Dict[str, Any], final_tier: str, final_model: str) -> str:
    """Single-line user-visible summary (optional)."""
    if not audit.get("deliberation"):
        if audit.get("router") and audit.get("final_without_deliberation"):
            return (
                f"Consultant routing: router → Tier {audit['final_without_deliberation']} → {final_model}"
            )
        return ""
    d = audit.get("deliberation") or {}
    summ = ""
    if isinstance(d.get("chief"), dict):
        summ = str(d["chief"].get("decision_summary") or "")[:160]
    base = f"Chief deliberation: Tier {final_tier} → {final_model}"
    if summ:
        return f"{base} ({summ})"
    return base
