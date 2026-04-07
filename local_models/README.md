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

## Hosted inference for very large open models (MiniMax, gpt-oss, …)

Those checkpoints are **too large** for Hugging Face’s free serverless GPU slots and for most “free API” tiers. Practical options:

1. **Hugging Face Inference Providers** (OpenAI-compatible via `HF_TOKEN`): small monthly credits on free accounts, then pay-as-you-go; pick **models that are actually offered** on a provider (see [Inference Providers pricing](https://huggingface.co/docs/inference-providers/pricing)). Hermes already uses **`provider: huggingface`** with **`HF_TOKEN`** / **`HUGGINGFACE_API_KEY`** for routing and fallbacks (`free_model_routing`, `hf_router`).
2. **Google AI (Gemma)** — free tier limits; Hermes can use **`router_provider: gemini`** in `free_model_routing.kimi_router` with **`GEMINI_API_KEY`** / **`GOOGLE_API_KEY`** for tier picking (not the same weights as MiniMax/gpt-oss, but zero local disk).
3. **Swap tier lists** in `config.yaml` `free_model_routing.kimi_router.tiers` to **smaller hub ids** that your chosen provider actually serves (e.g. community Qwen/Llama instruct variants), instead of `MiniMaxAI/MiniMax-M2.5` / `openai/gpt-oss-120b`.

There is no durable **100% free** API that runs **those exact** multi‑100 GiB weights at scale; the sustainable pattern is **smaller hosted models** + credits, or **self‑host** where you have RAM/VRAM.

## Local OpenAI-compatible server

Point vLLM/TGI at a downloaded tree; **`--served-model-name`** should match the hub id (e.g. `Qwen/QwQ-32B`). Then:

```bash
export HERMES_LOCAL_INFERENCE_BASE_URL=http://127.0.0.1:8000/v1
```

Optional: `HERMES_LOCAL_MODEL_STATE` to override the path to `state.json`.
