# Local model weights (Hugging Face Hub)

Downloaded checkpoints live under `hub/` (gitignored). Tracked files: `manifest.yaml`, this README.

## Current manifest

**`Qwen/QwQ-32B`** (~61 GiB) — fits smaller disks and the default **90 GiB** budget in `manifest.yaml`. Raise `budget_gb` if you add more repos.

## Download (resume + max parallelism)

From repo root (venv recommended):

```bash
pip install 'huggingface_hub>=0.26' hf_transfer pyyaml
export HF_HUB_ENABLE_HF_TRANSFER=1
python scripts/local_models/download_models.py --max-workers 64 --no-sync-droplet
```

`max_workers` is also read from `manifest.yaml` (default **64**). **`--no-sync-droplet`** skips rsync (use `./scripts/local_models/sync_to_droplet.sh` or the parallel script when ready).

Logs: `logs/download.log`, `logs/failures.jsonl`, `hub/state.json`.

## Hosted vs local routing (very large checkpoints)

Multi‑100 GiB weights are **too large** for Hugging Face’s free serverless GPU slots and for most “free API” tiers. Practical options:

1. **Google AI (Gemma-4 router)** — Hermes defaults to **`router_provider: gemini`** + **`gemma-4-31b-it`** under **`free_model_routing.kimi_router`**, with tier targets in **`free_model_routing.tiers`**, using **`GEMINI_API_KEY`** / **`GOOGLE_API_KEY`** (default: **`gemma-4-31b-it`** on Gemini API and **`Qwen/QwQ-32B`** when that hub id is downloaded and **`HERMES_LOCAL_INFERENCE_BASE_URL`** is set). Top-level **`gemini_native_tier_models`** marks API ids that are not HF hub repos.
2. **Legacy HF router API** — set **`router_provider: huggingface`** and a **`router_model`** served at `router.huggingface.co` if you still use that path; **`HF_TOKEN`** is required for that hop.
3. **Hugging Face Inference Providers** — optional paid/credit hosted models (see [Inference Providers pricing](https://huggingface.co/docs/inference-providers/pricing)); not part of Hermes default `free_model_routing` anymore.

There is no durable **100% free** API that runs **those exact** largest weights at scale; the sustainable pattern is **tier routing to what you host locally** (`HERMES_LOCAL_INFERENCE_BASE_URL` + `hub/state.json`), smaller hosted models, or credits.

## Local OpenAI-compatible server

Point vLLM/TGI at a downloaded tree; **`--served-model-name`** should match the hub id (e.g. `Qwen/QwQ-32B`). Then:

```bash
export HERMES_LOCAL_INFERENCE_BASE_URL=http://127.0.0.1:8000/v1
```

Optional: `HERMES_LOCAL_MODEL_STATE` to override the path to `state.json`.
