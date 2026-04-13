# Reconfiguration runbook — routing and cost

## Finding these files

- **In git:** `memory/knowledge/references/routing/` under the Hermes checkout (see also `memory/knowledge/references/ROUTING_DOCS.md`).
- **On disk:** open paths **from the repo root** (e.g. `~/hermes-agent/memory/knowledge/references/routing/README.md` on the operator Mac). If missing, **`git pull --ff-only`**.
- **Materialized:** optional copy under `${HERMES_HOME}/workspace/memory/knowledge/references/routing/` — operator vs droplet use **different** `HERMES_HOME` paths; do not assume `/home/hermesuser/...` on the Mac.

## Droplet: OPM off + Gemini model 404 (openai/… on generativelanguage)

If the gateway logs **404** for `models/openai/gpt-5.4-nano` with **Provider: gemini**, the profile is using a **default OpenRouter slug** with the **native Gemini API**. Hermes now **coerces** `model.default` at runtime when `model.provider: gemini`; persist a fix with:

```bash
HERMES_HOME=~/.hermes/profiles/chief-orchestrator-droplet \\
  ./venv/bin/python scripts/core/patch_profile_normal_routing_defaults.py
```

That sets **`openai_primary_mode.enabled: false`**, writes **`HERMES_OPENAI_PRIMARY_MODE=0`** into the profile `.env` when missing (env **overrides** YAML for OPM), patches token-governance runtime YAML, and rewrites **`model.default`** for Gemini if needed. Then **`hermes -p chief-orchestrator-droplet gateway restart --sync`**.

## 1. Change routing defaults

1. Edit **`agent/dynamic_routing_canon.yaml`** in the repo **or** add keys to **`${HERMES_HOME}/routing_canon.yaml`** (overlay wins on conflict).
2. Bump **`version:`** in the repo canon when you change shipped defaults.
3. Restart consumers:
   - **CLI:** new processes pick up YAML automatically.
   - **Gateway:** `hermes -p <profile> gateway restart --sync` on the host that runs messaging.
4. Optional: `hermes gateway watchdog-check` after restart.

## 2. Regenerate the provider routing catalog

```bash
# From repo root, venv active
python scripts/generate_provider_model_routing_catalog.py
```

Commit `agent/provider_model_routing_catalog.json` with the script change. Run:

```bash
python -m pytest tests/agent/test_routing_canon_catalog_crossref.py -o addopts=
```

## 3. `openrouter/free`

- Requires **`OPENROUTER_API_KEY`** on the runtime that resolves the model.
- Expand or reorder **`openrouter_free_router.candidate_slugs`** in merged canon if the intersection with live free models is empty.
- Symptom: user-visible error from **`OpenRouterFreeResolutionError`**; logs include resolution stage.

## 4. Profile `config.yaml` overlays

Under **`agent:`**:

- `lazy_tool_loading` — overrides `agent_lazy_tool_loading` behavior.
- `semantic_cache` — overrides `agent_semantic_cache`.
- `cost_caps` — overrides `agent_cost_caps`.
- `concise_output` — overrides `agent_concise_output`.

Under top-level **`compression:`** — overlays canon `compression` (threshold, `turn_interval`, `lossy_mode`, etc.).

## 5. Sync workspace memory docs to a profile

From the repo root (adjust profile path):

```bash
PROFILE="$HOME/.hermes/profiles/chief-orchestrator-operator"
rsync -a --delete \
  memory/knowledge/references/routing/ \
  "$PROFILE/workspace/memory/knowledge/references/routing/"
```

Repeat for **`chief-orchestrator-droplet`** on the VPS (`hermesuser` home).

**Or** from the checkout (same effect + **`ROUTING_DOCS.md`** copied):

```bash
export HERMES_HOME="$HOME/.hermes/profiles/chief-orchestrator-operator"  # or droplet profile on VPS
./scripts/core/sync_routing_memory_docs.sh
```

**From a dev workstation:** `scripts/core/push_routing_memory_docs_operator.sh` (mini) and `scripts/core/push_routing_memory_docs_droplet.sh` (VPS) — see `../ROUTING_DOCS.md`.

## 6. Verification commands

```bash
python -m pytest tests/test_openrouter_free_router.py \
  tests/test_lazy_tool_loading.py \
  tests/agent/test_semantic_tool_cache.py \
  tests/test_cost_caps_concise.py \
  tests/agent/test_routing_canon_catalog_crossref.py -o addopts=
```

Full suite before merge: `python -m pytest tests/ -o addopts=`

## 7. Rollback

- Revert overlay file or git revert repo canon.
- Restore prior `provider_model_routing_catalog.json` if regeneration was wrong.
- Restart gateway.
