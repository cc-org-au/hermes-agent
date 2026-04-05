<!-- policy-read-order-nav:top -->
> **Governance read order** — step 14 of 60 in the canonical `policies/` sequence (layer map & tables: [`README.md`](../README.md)).
> **Before this file:** read [core/governance/standards/token-model-tool-and-channel-governance-policy.md](governance/standards/token-model-tool-and-channel-governance-policy.md) and everything earlier in that sequence. **Do not** interpret this document as authoritative until those prerequisites are satisfied.
> **This file:** safe to apply only after the prerequisite above (if any) is complete.
<!-- policy-read-order-nav:top-end -->

# Hermes model delegation, tier routing, and token governance (implementation map)

This note is for **operators and engineers** who need to **reproduce or extend** Hermes cost controls: per-turn tier selection, runtime YAML caps, subagent delegation limits, and optional consultant (router / challenger / chief) deliberation. Canonical product policy remains `policies/core/governance/standards/token-model-tool-and-channel-governance-policy.md`.

## What gets enforced

| Concern | Mechanism |
|--------|-----------|
| Blocked premium models | `blocked_model_substrings` in runtime YAML → downgrade to `blocked_fallback_tier` or `default_model` |
| Main model tier per prompt | `model.default: tier:dynamic` (or fixed `tier:D`) in profile `config.yaml`; resolved each user turn via `agent/tier_model_routing.py` |
| Auxiliary / delegation models | Same `tier:X` or `tier:dynamic` in `config.yaml` under `auxiliary.*`, `compression.*`, `delegation.model`; resolved per call when dynamic |
| Max turns / delegate iterations | `max_agent_turns`, `delegation_max_iterations` in runtime YAML → `AIAgent` and `tools/delegate_tool.py` |
| Optional context stripping | `skip_context_files` in runtime YAML (discouraged for governance activation) |
| Consultant path (E/F, escalation) | `consultant_routing` in runtime YAML + `agent/consultant_routing.py`; logs `workspace/operations/consultant_deliberations.jsonl` |

## On-disk contract

1. **Profile** — `HERMES_HOME` (e.g. `~/.hermes/profiles/chief-orchestrator/`) holds `config.yaml` and `.env`.
2. **Runtime governance file** — `HERMES_HOME/workspace/operations/hermes_token_governance.runtime.yaml` (copy from repo `scripts/templates/hermes_token_governance.runtime.example.yaml`). Loaded when `enabled: true` and not disabled by env.
3. **Registers** — Workspace registries under `WORKSPACE/operations/` (e.g. `MODEL_ROUTING_REGISTRY.md`) are **policy artifacts**; Hermes does not parse them for routing unless a future feature does—the **YAML + config** drive behavior.

## Code map (reimplementation checklist)

| Area | Primary modules | Role |
|------|-----------------|------|
| Load + apply YAML | `agent/token_governance_runtime.py` | `apply_token_governance_runtime()`, `apply_per_turn_tier_model()`, `resolve_tier_strings_in_config()`; consultant hooks; `_emit_status(..., "token_governance")` |
| Tier heuristics | `agent/tier_model_routing.py` | `select_tier_for_message`, `tier:dynamic`, length bands, `chief` vs `dynamic` default routing |
| Consultant pipeline | `agent/consultant_routing.py` | Router LLM, challenger, chief; `governance_activation_signal()`; optional `governance_activation_deliberation_floor` (opt-in only) |
| Agent loop | `run_agent.py` | `AIAgent.__init__` applies runtime; per-turn tier before each user message; `_emit_status` for lifecycle + governance lines |
| Delegation | `tools/delegate_tool.py` | Honors `_token_governance_delegation_max` and dynamic delegation model when configured |
| Config loading | `hermes_cli/config.py` | `DEFAULT_CONFIG` / `load_config` merge; `auxiliary.consultant_router` (and challenger/chief) defaults |
| Gateway visibility | `gateway/run.py` | Status callback prefixes governance lines for Telegram/Slack/WhatsApp when enabled in config |

## Configuration keys (typical)

**Profile `config.yaml` (placeholders, not raw slugs where tiering is desired):**

- `model.default: tier:dynamic` or `tier:D`
- `compression.summary_model`, `auxiliary.*.model`, `delegation.model` — same pattern
- `auxiliary.consultant_router.model` (and challenger/chief) — cheap / strong models for internal consultant steps

**Runtime YAML (`hermes_token_governance.runtime.yaml`):**

- `enabled`, `tier_models` (A–F → OpenRouter or provider slugs), `chief_default_tier`, `blocked_fallback_tier`, `blocked_model_substrings`
- `max_agent_turns`, `delegation_max_iterations`
- `dynamic_tier_routing`, `default_routing_tier` (`chief` | `dynamic`), optional length keys for dynamic fallback
- `consultant_routing.enabled`, `tiers_requiring_deliberation`, optional `governance_activation_deliberation_floor`

## Environment overrides

- `HERMES_TOKEN_GOVERNANCE_DISABLE=1` — skip runtime YAML application
- `HERMES_GOVERNANCE_ALLOW_PREMIUM=1` — allow models that would otherwise be blocklisted (use sparingly)
- `HERMES_CONSULTANT_ROUTING_DISABLE=1` — disable consultant pipeline

## Tests

- `tests/agent/test_token_governance_runtime.py`
- `tests/agent/test_tier_model_routing.py`
- `tests/agent/test_consultant_routing.py`
- `tests/tools/test_delegate.py` (delegation cap interaction)
- Auxiliary client tests may need `pytest -n0` if flaky under xdist

## Activation sequence (policy pack)

Phased activation places **token governance policy + Hermes runtime YAML** in **Sessions 1–2** so enforcement is active **before** the full runtime-activation audit (**Session 3**). See `policies/core/deployment-handoff.md` § Session-by-session prompt order and `scripts/templates/activation_sessions_cumulative_cover_2_20.txt`.

## Prompt caching invariant

Do not change toolsets or rewrite past system context mid-conversation; tier/model selection per **new** user message is fine. See `AGENTS.md` (prompt caching).

<!-- policy-read-order-nav:bottom -->
> **Next step:** continue to [core/governance/role-prompts/implement-token-model-and-tool-and-channel-governance-prompt.md](governance/role-prompts/implement-token-model-and-tool-and-channel-governance-prompt.md) after this file is fully read and applied. Do not skip ahead unless a human operator explicitly directs a narrower scope.
<!-- policy-read-order-nav:bottom-end -->
