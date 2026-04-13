# File inventory — routing and cost

| Area | Path |
|------|------|
| Routing canon (repo) | `agent/dynamic_routing_canon.yaml` |
| Routing canon (overlay) | `${HERMES_HOME}/routing_canon.yaml` |
| Canon loader / helpers | `agent/routing_canon.py` |
| Routing trace helper | `agent/routing_trace.py` |
| OpenRouter free resolver | `agent/openrouter_free_router.py` |
| Semantic cache | `agent/semantic_tool_cache.py` |
| Provider catalog (generated) | `agent/provider_model_routing_catalog.json` |
| Catalog generator | `scripts/generate_provider_model_routing_catalog.py` |
| Catalog Python helper | `agent/provider_model_routing_catalog.py` |
| Context compressor | `agent/context_compressor.py` |
| Agent loop / API kwargs | `run_agent.py` |
| Tool definitions / dispatch | `model_tools.py`, `tools/registry.py` |
| CLI model validation / menus | `hermes_cli/models.py`, `hermes_cli/model_switch.py` |
| Slash commands (`/compress`, `/compact` alias) | `hermes_cli/commands.py` |
| User config defaults / migration | `hermes_cli/config.py` |
| Gateway message path + hygiene compression | `gateway/run.py` |
| Token governance runtime (tiers, overlays) | `${HERMES_HOME}/workspace/memory/runtime/operations/hermes_token_governance.runtime.yaml` (template under `memory/runtime/operations/`) |
| Crossref tests | `tests/agent/test_routing_canon_catalog_crossref.py` |
| OpenRouter free tests | `tests/test_openrouter_free_router.py` |
| Lazy tools tests | `tests/test_lazy_tool_loading.py` |
| Semantic cache tests | `tests/agent/test_semantic_tool_cache.py` |
| Cost caps / concise tests | `tests/test_cost_caps_concise.py` |
