"""OpenRouter slugs in routing canon must exist in provider_model_routing_catalog.json."""

from __future__ import annotations

import json
from pathlib import Path

import yaml


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _collect_openrouter_slugs_from_canon(data: dict) -> set[str]:
    out: set[str] = set()
    sec = data.get("openrouter_step_up_escalation")
    if isinstance(sec, dict):
        for key in ("chat_models", "codex_models"):
            raw = sec.get(key)
            if isinstance(raw, list):
                for item in raw:
                    if isinstance(item, str) and item.strip():
                        out.add(item.strip())
    sec = data.get("opm_cross_provider_quota_failover")
    if isinstance(sec, dict):
        for key in ("openrouter_chat_models", "openrouter_codex_models"):
            raw = sec.get(key)
            if isinstance(raw, list):
                for item in raw:
                    if isinstance(item, str) and item.strip():
                        out.add(item.strip())
    sec = data.get("openrouter_free_router")
    if isinstance(sec, dict):
        raw = sec.get("candidate_slugs")
        if isinstance(raw, list):
            for item in raw:
                if isinstance(item, str) and item.strip():
                    out.add(item.strip())
    return out


def test_canon_openrouter_slugs_are_in_catalog():
    root = _repo_root()
    canon_path = root / "agent" / "dynamic_routing_canon.yaml"
    catalog_path = root / "agent" / "provider_model_routing_catalog.json"
    canon = yaml.safe_load(canon_path.read_text(encoding="utf-8"))
    assert isinstance(canon, dict)
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    or_models = catalog.get("providers", {}).get("openrouter", {}).get("models", [])
    ids = {m["id"] for m in or_models if isinstance(m, dict) and m.get("id")}

    missing = _collect_openrouter_slugs_from_canon(canon) - ids
    assert not missing, f"Canon OpenRouter slugs missing from catalog: {sorted(missing)}"
