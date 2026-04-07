"""Optional local OpenAI-compatible server for HF hub model ids (vLLM / TGI / llama.cpp server).

Auto-start behaviour (macOS / Apple Silicon only):
  When ``HERMES_LOCAL_INFERENCE_BASE_URL`` is set and a locally-downloaded model is found,
  ``ensure_local_inference_server_running()`` checks if the server is reachable.
  If not, it starts ``mlx_lm.server`` as a subprocess and waits up to
  ``HERMES_LOCAL_INFERENCE_START_TIMEOUT`` seconds (default 60) for it to become ready.
  The subprocess is stored in the module-level ``_server_proc`` and stays alive for the
  duration of the Python process.

Server reachability:
  ``is_local_inference_server_alive()`` does a 1-second GET /v1/models; callers use
  this before routing to avoid 3 × retry noise when the server is simply not running.
"""

from __future__ import annotations

import json
import logging
import os
import platform
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# Subprocess handle for the auto-started server (module-level singleton).
_server_proc: Optional[subprocess.Popen] = None  # type: ignore[type-arg]


def _default_state_path() -> Path:
    # agent/local_inference.py -> repo root
    return Path(__file__).resolve().parent.parent / "local_models" / "hub" / "state.json"


def load_local_hub_state() -> Optional[Dict[str, Any]]:
    p = os.environ.get("HERMES_LOCAL_MODEL_STATE", "").strip()
    path = Path(p) if p else _default_state_path()
    if not path.is_file():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        return raw if isinstance(raw, dict) else None
    except Exception as exc:
        logger.debug("local_inference: could not read %s: %s", path, exc)
        return None


def downloaded_hub_repo_ids() -> Optional[set[str]]:
    """Return hub ids marked downloaded in ``state.json``, or None if state is unknown.

    Distinguishes between:
    - ``None`` — state.json is missing or unreadable (caller should not filter)
    - ``set()`` — state.json exists but nothing is marked downloaded (caller should filter everything out)
    - ``{ids}`` — the set of downloaded hub ids
    """
    state = load_local_hub_state()
    if state is None:
        return None  # file missing → don't filter
    raw = state.get("downloaded") or state.get("repos") or []
    if isinstance(raw, dict):
        ids = [str(k).strip() for k in raw if str(k).strip()]
    elif isinstance(raw, list):
        ids = [str(x).strip() for x in raw if str(x).strip()]
    else:
        return set()  # state.json present but malformed → treat as empty
    return set(ids)  # may be empty set() when downloaded=[]


def filter_hub_model_ids_by_local_state(
    model_ids: list[str],
    *,
    enabled: bool = True,
) -> list[str]:
    """Drop tier hub ids that are not present in local ``state.json`` when enabled.

    - state.json missing (``have is None``) → return *model_ids* unchanged (unknown state)
    - state.json present but empty (``have == set()``) → return ``[]`` (nothing downloaded)
    - state.json has ids → return only the intersection with *model_ids*
      (if intersection is empty, return ``[]`` — respect the explicit empty state)
    """
    if not enabled or not model_ids:
        return list(model_ids)
    have = downloaded_hub_repo_ids()
    if have is None:
        # state.json missing — don't filter (unknown state, avoid breaking things)
        return list(model_ids)
    # state.json present: filter strictly to what is downloaded (may be empty)
    return [m.strip() for m in model_ids if m and str(m).strip() in have]


def _resolve_served_model_path(hub_id: str, state: dict) -> str:
    """Return the best local path to use as the ``model`` field in API calls.

    Prefers a 4-bit quantized variant (``<path>-mlx-4bit``) when present,
    then the original BF16 path from state.json, then the hub id unchanged.
    """
    repos = state.get("repos") or {}
    entry = repos.get(hub_id) if isinstance(repos, dict) else None
    base_path: Optional[str] = None
    if isinstance(entry, dict):
        base_path = (entry.get("path") or "").strip() or None

    if not base_path:
        derived = hub_id.replace("/", "__")
        candidate = Path(__file__).resolve().parent.parent / "local_models" / "hub" / derived
        if candidate.is_dir():
            base_path = str(candidate)

    if base_path:
        quant_path = base_path + "-mlx-4bit"
        if Path(quant_path).is_dir():
            return quant_path
        if Path(base_path).is_dir():
            return base_path

    return hub_id


# ── Server reachability ────────────────────────────────────────────────────────

def _base_url_from_env() -> str:
    b = os.environ.get("HERMES_LOCAL_INFERENCE_BASE_URL", "").strip()
    if not b:
        return ""
    b = b.rstrip("/")
    if not b.endswith("/v1"):
        b = f"{b}/v1"
    return b


def is_local_inference_server_alive(timeout: float = 1.2) -> bool:
    """Return True if the local inference HTTP server responds within *timeout* seconds."""
    import urllib.error
    import urllib.request

    base = _base_url_from_env()
    if not base:
        return False
    url = base.rstrip("/v1").rstrip("/") + "/v1/models"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310
            return resp.status == 200
    except Exception:
        return False


# ── Auto-start (macOS / Apple Silicon only) ───────────────────────────────────

def _find_mlx_lm_executable() -> Optional[str]:
    """Return the path to the mlx_lm server entrypoint in the current venv, or None."""
    # Prefer the venv that contains this file
    repo_root = Path(__file__).resolve().parent.parent
    for candidate in (
        repo_root / "venv" / "bin" / "python",
        Path(sys.executable),
    ):
        if candidate.is_file():
            try:
                result = subprocess.run(
                    [str(candidate), "-c", "import mlx_lm; print('ok')"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    return str(candidate)
            except Exception:
                pass
    return None


def ensure_local_inference_server_running(
    hub_id: str = "Qwen/QwQ-32B",
    *,
    port: Optional[int] = None,
    start_timeout: int = 90,
    quiet: bool = False,
) -> bool:
    """Ensure the local inference server is running; auto-start it on macOS if not.

    Returns True if the server is (or becomes) reachable, False otherwise.
    On non-macOS platforms the function only checks reachability and never starts.
    """
    global _server_proc

    # Resolve port from env or default
    base_url = os.environ.get("HERMES_LOCAL_INFERENCE_BASE_URL", "").strip()
    if not base_url:
        return False

    if port is None:
        try:
            from urllib.parse import urlparse
            parsed = urlparse(base_url)
            port = parsed.port or 8000
        except Exception:
            port = 8000

    # Already alive?
    if is_local_inference_server_alive():
        return True

    # Dead subprocess → clean up
    if _server_proc is not None and _server_proc.poll() is not None:
        _server_proc = None

    # Only auto-start on macOS with mlx_lm
    if platform.system() != "Darwin":
        return False

    python_bin = _find_mlx_lm_executable()
    if python_bin is None:
        logger.warning("local_inference: mlx_lm not found — cannot auto-start server. pip install mlx-lm")
        return False

    # Find the model path
    state = load_local_hub_state()
    if not state:
        return False
    downloaded = state.get("downloaded") or list((state.get("repos") or {}).keys())
    if hub_id not in downloaded:
        return False
    model_path = _resolve_served_model_path(hub_id, state)
    if not Path(model_path).is_dir() and model_path == hub_id:
        return False

    log_path = Path(model_path).parent / "qwen_server.log"

    if not quiet:
        print(
            f"\n🤖  Starting local Qwen inference server (port {port})…"
            f"\n    Model: {Path(model_path).name}"
            f"\n    Log:   {log_path}"
            f"\n    This stays running for the duration of your Hermes session.\n",
            flush=True,
        )

    env = os.environ.copy()
    env["HF_HUB_OFFLINE"] = "1"
    env["TRANSFORMERS_OFFLINE"] = "1"

    try:
        log_fh = open(log_path, "a")  # noqa: WPS515
        _server_proc = subprocess.Popen(
            [python_bin, "-m", "mlx_lm", "server",
             "--model", model_path,
             "--host", "0.0.0.0",
             "--port", str(port)],
            stdout=log_fh,
            stderr=log_fh,
            env=env,
            start_new_session=True,
        )
    except Exception as exc:
        logger.warning("local_inference: failed to start server: %s", exc)
        return False

    # Wait for it to become responsive
    deadline = time.monotonic() + start_timeout
    while time.monotonic() < deadline:
        if _server_proc.poll() is not None:
            logger.warning("local_inference: server process exited early")
            return False
        if is_local_inference_server_alive():
            if not quiet:
                print("    ✓ Local inference server ready.\n", flush=True)
            return True
        time.sleep(1.5)

    logger.warning("local_inference: server did not become ready within %ds", start_timeout)
    return False


# ── Override helper ────────────────────────────────────────────────────────────

def local_inference_override_for_hub_model(fb_model: str) -> Optional[Tuple[str, str, str]]:
    """If ``HERMES_LOCAL_INFERENCE_BASE_URL`` is set and *fb_model* is in download state,
    return ``(base_url, api_key, served_model_name)``.

    *served_model_name* is the local filesystem path to pass as the ``model``
    field in OpenAI-compatible API calls (avoids the server re-downloading the
    hub model).  Prefers the 4-bit quantized variant when present.
    """
    base = os.environ.get("HERMES_LOCAL_INFERENCE_BASE_URL", "").strip()
    if not base:
        return None
    mid = (fb_model or "").strip()
    if not mid:
        return None
    state = load_local_hub_state()
    if not state:
        return None
    downloaded = state.get("downloaded") or state.get("repos") or []
    if isinstance(downloaded, dict):
        downloaded = list(downloaded.keys())
    if not isinstance(downloaded, list):
        return None
    if mid not in downloaded:
        return None
    b = base.rstrip("/")
    if not b.endswith("/v1"):
        b = f"{b}/v1"
    key = os.environ.get("HERMES_LOCAL_INFERENCE_API_KEY", "dummy-local").strip() or "dummy-local"
    served_name = _resolve_served_model_path(mid, state)
    return b, key, served_name
