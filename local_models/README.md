# Local model weights (Hugging Face Hub)

Downloaded checkpoints live under `hub/` (gitignored). Tracked files: `manifest.yaml`, this README.

## Manifest (default)

`MiniMaxAI/MiniMax-M2.5` and `openai/gpt-oss-120b` — together roughly **~400 GiB** LFS; `manifest.yaml` sets `budget_gb: 420` so both can be planned in one run. Adjust `budget_gb` if your disk differs.

## Free-fallback routing (Gemini → local hub ids)

Default **`free_model_routing.kimi_router`** uses **`router_provider: gemini`** and **`router_model: gemma-4-31b-it`** (Google AI) to pick **one** hub id per turn from the tier list (`MiniMaxAI/MiniMax-M2.5`, `openai/gpt-oss-120b`). Inference runs against **`HERMES_LOCAL_INFERENCE_BASE_URL`** when those ids appear in `hub/state.json`.

Requires **`GEMINI_API_KEY`** or **`GOOGLE_API_KEY`** for routing; local serving uses your vLLM/TGI base URL (no HF token needed for routing when using the Gemini router).

## Gated HF repos

If you add a gated model to `manifest.yaml`, set **`HF_TOKEN`** and accept the license on the model page.

## Download (resume + max parallelism)

From the repo root (use the project venv if you have one):

```bash
pip install 'huggingface_hub>=0.26' hf_transfer pyyaml
export HF_HUB_ENABLE_HF_TRANSFER=1
python scripts/local_models/download_models.py --max-workers 64
```

`max_workers` is also read from `manifest.yaml` (default **32**); pass **`--max-workers 64`** (or higher if your Hub client supports it) for maximum parallel shard downloads. **`--no-sync-droplet`** skips the post-step rsync.

After **all** repos in the plan finish without errors, the script **verifies** each snapshot (`config.json` + weights/index), then runs **`scripts/local_models/sync_to_droplet.sh`** automatically (unless `--no-sync-droplet`).

- **Resume**: `snapshot_download` resumes partial files; safe to stop and re-run.
- **Logs**: `logs/download.log`, `logs/failures.jsonl`, `hub/state.json`.

## Manual sync to droplet

```bash
./scripts/local_models/sync_to_droplet.sh
```

Uses the same `~/.env/.env` SSH variables as `scripts/core/droplet_run.sh`. Syncs **`local_models/hub/`** → `/home/hermesuser/hermes-agent/local_models/hub/` (not `~/.hermes`).

## Local OpenAI-compatible server

Point vLLM/TGI at the downloaded dirs with **`--served-model-name`** equal to the hub id (`MiniMaxAI/MiniMax-M2.5`, `openai/gpt-oss-120b`). Then:

```bash
export HERMES_LOCAL_INFERENCE_BASE_URL=http://127.0.0.1:8000/v1
```

Optional: `HERMES_LOCAL_MODEL_STATE` to override the path to `state.json`.
