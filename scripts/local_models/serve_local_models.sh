#!/usr/bin/env bash
# Serve locally-downloaded models via an OpenAI-compatible vLLM HTTP server.
#
# Usage:
#   ./scripts/local_models/serve_local_models.sh [--model <hub_id>] [--port <N>] [--gpu-memory-util <0-1>]
#
# Default model: Qwen/QwQ-32B (from local_models/hub/Qwen__QwQ-32B)
# Default port:  8000
#
# Requirements:
#   pip install vllm  (already included if using hermes venv)
#
# Hermes config:
#   Set in your profile .env:
#     HERMES_LOCAL_INFERENCE_BASE_URL=http://localhost:8000
#     HERMES_LOCAL_INFERENCE_API_KEY=dummy-local   # optional
#
# The served model is identified by its HuggingFace hub id (e.g. Qwen/QwQ-32B).
# vLLM exposes it at POST /v1/chat/completions with model="Qwen/QwQ-32B".
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HUB_DIR="$REPO_ROOT/local_models/hub"
STATE_JSON="$HUB_DIR/state.json"

# ── Defaults ──────────────────────────────────────────────────────────────────
MODEL_HUB_ID="${HERMES_SERVE_MODEL:-Qwen/QwQ-32B}"
PORT="${HERMES_SERVE_PORT:-8000}"
GPU_UTIL="${HERMES_SERVE_GPU_UTIL:-0.90}"
MAX_MODEL_LEN="${HERMES_SERVE_MAX_MODEL_LEN:-}"  # empty = vLLM default

# ── Parse flags ───────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --model)         MODEL_HUB_ID="$2"; shift 2 ;;
    --port)          PORT="$2"; shift 2 ;;
    --gpu-memory-util) GPU_UTIL="$2"; shift 2 ;;
    --max-model-len) MAX_MODEL_LEN="$2"; shift 2 ;;
    *) echo "Unknown arg: $1" >&2; exit 1 ;;
  esac
done

# ── Resolve local model path from state.json ──────────────────────────────────
MODEL_PATH=""
if [[ -f "$STATE_JSON" ]]; then
  # Extract path for MODEL_HUB_ID from state.json using python (no jq dep).
  MODEL_PATH="$(python3 - <<PYEOF
import json, sys
with open("$STATE_JSON") as f:
    s = json.load(f)
repos = s.get("repos", {})
entry = repos.get("$MODEL_HUB_ID")
if entry and entry.get("path"):
    print(entry["path"])
PYEOF
  )"
fi

if [[ -z "$MODEL_PATH" || ! -d "$MODEL_PATH" ]]; then
  # Fall back: derive path from hub id (slash → __)
  DERIVED="${MODEL_HUB_ID//\//__}"
  if [[ -d "$HUB_DIR/$DERIVED" ]]; then
    MODEL_PATH="$HUB_DIR/$DERIVED"
  fi
fi

if [[ -z "$MODEL_PATH" || ! -d "$MODEL_PATH" ]]; then
  echo "ERROR: Model not found locally for hub id '$MODEL_HUB_ID'." >&2
  echo "  Expected path: $HUB_DIR/${MODEL_HUB_ID//\//__}" >&2
  echo "  Run: python scripts/local_models/download_models.py --skip-size-check --max-workers 2" >&2
  exit 1
fi

echo "==> Serving $MODEL_HUB_ID"
echo "    Model path : $MODEL_PATH"
echo "    Port       : $PORT"
echo ""

# ── Activate venv if available ────────────────────────────────────────────────
if [[ -f "$REPO_ROOT/venv/bin/activate" ]]; then
  # shellcheck source=/dev/null
  source "$REPO_ROOT/venv/bin/activate"
fi

# ── Build vLLM command ────────────────────────────────────────────────────────
VLLM_CMD=(
  python -m vllm.entrypoints.openai.api_server
  --model "$MODEL_PATH"
  --served-model-name "$MODEL_HUB_ID"
  --port "$PORT"
  --trust-remote-code
  --gpu-memory-utilization "$GPU_UTIL"
)

if [[ -n "$MAX_MODEL_LEN" ]]; then
  VLLM_CMD+=(--max-model-len "$MAX_MODEL_LEN")
fi

# CPU-only fallback when no GPU detected
if ! python3 -c "import torch; assert torch.cuda.is_available()" 2>/dev/null; then
  echo "No CUDA GPU detected — adding --device cpu (inference will be slow)."
  VLLM_CMD+=(--device cpu)
fi

echo "Running: ${VLLM_CMD[*]}"
echo ""
exec "${VLLM_CMD[@]}"
