# Routing and cost architecture

## Merged routing canon

1. **Repo defaults:** `hermes-agent/agent/dynamic_routing_canon.yaml` (versioned `version:` field).
2. **Profile overlay (optional):** `${HERMES_HOME}/routing_canon.yaml` deep-merged over the repo file.
3. **Loader:** `agent/routing_canon.py` → `load_merged_routing_canon()` and typed helpers (`load_compression_canon_config`, `load_openrouter_free_router_config`, `load_lazy_tool_loading_config`, `load_semantic_cache_config`, `load_cost_caps_config`, `load_concise_output_config`).

Runtime code should prefer these helpers instead of ad hoc dict scraping.

## Model catalog

- **Generated JSON:** `agent/provider_model_routing_catalog.json` (do not hand-edit).
- **Generator:** `scripts/generate_provider_model_routing_catalog.py` (includes OpenRouter hub rows).
- **Crossref tests:** `tests/agent/test_routing_canon_catalog_crossref.py` ensures OpenRouter slugs referenced from canon lists appear in the catalog.

## `openrouter/free`

- **User-facing id:** `openrouter/free` (synthetic; not a literal OpenRouter model id).
- **Resolution:** Immediately before each OpenAI-compatible API call, when the configured model is `openrouter/free` and the stack targets OpenRouter, Hermes intersects canon `openrouter_free_router.candidate_slugs` with **live** free-tier ids from OpenRouter `/models` (TTL from canon). **Strict:** no paid fallback when this selector is active.
- **CLI /models:** `hermes_cli/models.py` accepts the synthetic id without requiring it to appear in `/models`.
- **Implementation:** `agent/openrouter_free_router.py`.

## Compression

- **Merge rule:** Canon `compression.*` first, then `config.yaml` `compression` overlay (same pattern in `run_agent.py` and gateway session hygiene for the `enabled` flag).
- **Lossy mode:** `agent/context_compressor.py` applies retention when `lossy_mode` is true (e.g. `preserve_last_pairs`).
- **Turn interval:** Every N **user** turns (when `turn_interval > 0`), a compression pass runs at turn start (after preflight threshold logic).

## Lazy tool loading

- **Policy:** `agent_lazy_tool_loading` in merged canon; optional override under `config.yaml` `agent.lazy_tool_loading`.
- **Behavior:** System prompt and `valid_tool_names` reflect the **full** enabled tool surface; the API `tools=` array is a **subset** (core toolsets/tools plus `expand_tool_surface` when `expand_via: meta_tool`). Additional tools can be requested via `expand_tool_surface` or are auto-merged when the model issues a call to a valid but inactive tool name.

## Semantic tool cache

- **Policy:** `agent_semantic_cache` in canon; optional `agent.semantic_cache` in `config.yaml`.
- **Storage:** SQLite under `${HERMES_HOME}` (relative path from config), keyed by tool name, normalized args, Hermes home path, and **host role** from env precedence in canon.
- **Hook:** `model_tools.handle_function_call` (allowlisted tools only; errors not cached).

## Cost caps and concise output

- **Cost caps:** `agent_cost_caps` in canon; optional `agent.cost_caps`. Caps apply to **extractive**-looking short user messages (keyword heuristic) and skip configured consultant tiers.
- **Concise mode:** `agent_concise_output` in canon; optional `agent.concise_output`. Injects an **ephemeral** fragment at API-call time (not merged into the cached system prefix).

## CLI ↔ gateway parity

Model routing and agent construction share `hermes_cli/model_switch.py`, `gateway/run.py` session resolution, and the same merged canon defaults where wired.

## Prompt caching

Ephemeral strings (concise fragment, lazy-tool instruction, plugin `pre_llm_call` context) are appended only in the per-call system message assembly in `run_agent.py`, not inside the long-lived cached system prompt block.
