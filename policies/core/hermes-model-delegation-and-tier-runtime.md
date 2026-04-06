<!-- policy-read-order-nav:top -->
> **Governance read order** — step 14 of 61 in the canonical `policies/` sequence (layer map & tables: [`README.md`](../README.md)).
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

---

## Provider fallback chain (OpenRouter limits → direct Gemini / Gemma)

**Goal:** When OpenRouter returns **rate limits**, **402-style billing**, or **403 “key limit / credits”** style errors, optionally switch the running agent to a **direct** provider (e.g. **Google Gemini API** with **Gemma**) without requiring a manual model change, then **probe the primary** when configured.

### Policy alignment

- Stays within **Priority 5 — Provider safety**: fallback is for **documented** account/key limits and rate limits, not for evading fair-use rules across parallel “spray” (see `token-model-tool-and-channel-governance-policy.md` §6).
- Prefer **one primary path** (OpenRouter) with a **single** configured fallback chain, not ad-hoc multi-provider duplication per request.

### Configuration (profile `config.yaml`)

- **`fallback_model`** — single dict, or **`fallback_model`** as a **list** (`fallback_providers`) for an ordered chain.
- Hermes-only keys on each entry (stripped before router resolution):
  - **`only_rate_limit: true`** — activate this entry only for **quota-style** failures (rate limit, 402, OpenRouter key/credit limit messages, specific 403 bodies). Do **not** rely on generic non-retryable 403 without the quota classifier.
  - **`restore_health_check: true`** — after fallback, periodically **ping** the primary before restoring (optional **`health_check_message`**).
- **`provider` + `model`** on each entry — must resolve via `agent/auxiliary_client.resolve_provider_client` (e.g. `provider: gemini`, `model: gemma-4-31b-it`, **`GEMINI_API_KEY`** in profile `.env`).

See **`scripts/templates/chief-orchestrator-profile.example.yaml`** and inline comments on **`fallback_model`**.

### Code map (must stay consistent when reimplementing)

| Behavior | Location |
|----------|-----------|
| Quota / billing / key-limit classification | `run_agent.py` — `AIAgent._quota_style_api_failure()` (includes OpenRouter **403** + “key limit”, “settings/keys”, etc.; infers **402/403/429** from message text when `status_code` is missing on the exception) |
| Eager fallback on classified errors | `run_agent.py` — retry loop: if classified and fallback chain non-empty, **`_try_activate_fallback(triggered_by_rate_limit=True)`** unless the **credential pool** may still recover — pool blocks **only** **`status_code == 429`**, not 402/403 (rotating pooled keys does not fix account key caps) |
| Non-retryable 4xx path | Same loop: **`_try_activate_fallback(triggered_by_rate_limit=is_rate_limited)`** so **`only_rate_limit`** fallbacks still activate after quota-style errors that hit the client-error branch |
| Fallback activation / chain advance | `run_agent.py` — `_try_activate_fallback()`, `_fallback_entry_for_resolve()` |
| Primary health probe | `run_agent.py` — `_probe_primary_healthy()` |
| Tests | `tests/test_provider_fallback.py` (`TestQuotaStyleApiFailure`, `TestOnlyRateLimitFallback`, etc.) |

### Verification

1. Configure **`fallback_model`** with **`only_rate_limit: true`** and a working direct provider key.
2. Induce an OpenRouter **key limit** or **402** (or use a test double): agent should log **quota / fallback** and continue on the fallback model.
3. Run **`pytest tests/test_provider_fallback.py`**.

---

## Gemma / Gemini `<thought>` tags in assistant text

Some models (notably **Gemma** via the **Google API**) emit **`<thought>…</thought>`** (or similar) **inside** `message.content` instead of separate reasoning fields.

### Expected Hermes behavior

- **User-visible** assistant text and **conversation history** **`content`** must **not** include raw `<thought>` XML; inner text may be captured as **`reasoning`** when extracted.
- **Streaming (CLI):** treat `<thought>` like other reasoning tags — **suppress** from the response panel by default; if the operator enables **`/reasoning`**, stream inner text into the **dim reasoning** box (see `cli.py` **`_stream_delta`** **`_OPEN_TAGS` / `_CLOSE_TAGS`**).
- **Resume / history display:** strip common reasoning tags in **`_strip_reasoning`** when showing past turns.

### Code map

| Area | Module |
|------|--------|
| Strip paired blocks + orphan tags | `run_agent.py` — `_strip_think_blocks()`, `_has_content_after_think_block()` |
| Extract inline reasoning | `run_agent.py` — `_extract_reasoning()`, `_build_assistant_message()` (stores **stripped** `content`, preserves **`reasoning`**) |
| Stream filter | `cli.py` — `_stream_delta`, `_strip_reasoning` |
| Auxiliary extraction | `agent/auxiliary_client.py` — `extract_content_or_reasoning()` |
| Tests | `tests/test_run_agent.py` — `TestStripThinkBlocks` (e.g. `test_thought_block_removed`) |

---

## Activation sequence (policy pack)

Phased activation places **token governance policy + Hermes runtime YAML** in **Sessions 1–2** so enforcement is active **before** the full runtime-activation audit (**Session 3**). See `policies/core/deployment-handoff.md` § Session-by-session prompt order and `scripts/templates/activation_sessions_cumulative_cover_2_20.txt`.

## Prompt caching invariant

Do not change toolsets or rewrite past system context mid-conversation; tier/model selection per **new** user message is fine. See `AGENTS.md` (prompt caching).

<!-- policy-read-order-nav:bottom -->
> **Next step:** continue to [core/governance/role-prompts/implement-token-model-and-tool-and-channel-governance-prompt.md](governance/role-prompts/implement-token-model-and-tool-and-channel-governance-prompt.md) after this file is fully read and applied. Do not skip ahead unless a human operator explicitly directs a narrower scope.
<!-- policy-read-order-nav:bottom-end -->
