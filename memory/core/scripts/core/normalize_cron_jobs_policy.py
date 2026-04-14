#!/usr/bin/env python3
"""Normalize cron configs/jobs to the repo-wide messaging policy."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable

import yaml

OPENROUTER_FREE_MODEL = "openrouter/free"
OPENROUTER_PROVIDER = "openrouter"


def _resolve_hermes_root(active_home: Path) -> Path:
    active_home = active_home.expanduser().resolve()
    if active_home.name == ".hermes":
        return active_home
    if active_home.parent.name == "profiles":
        return active_home.parent.parent
    return active_home


def iter_target_homes(active_home: Path, *, all_profiles: bool) -> list[Path]:
    active_home = active_home.expanduser().resolve()
    if not all_profiles:
        return [active_home]

    root = _resolve_hermes_root(active_home)
    homes: list[Path] = []
    seen: set[Path] = set()

    def _add(path: Path) -> None:
        path = path.expanduser().resolve()
        if path in seen or not path.exists() or not path.is_dir():
            return
        seen.add(path)
        homes.append(path)

    _add(root)
    profiles_dir = root / "profiles"
    if profiles_dir.is_dir():
        for child in sorted(profiles_dir.iterdir()):
            if child.is_dir():
                _add(child)
    _add(active_home)
    return homes


def _read_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def _write_yaml(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _read_jobs(path: Path) -> tuple[object, list[dict]]:
    if not path.exists():
        return [], []
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data, data
    if isinstance(data, dict) and isinstance(data.get("jobs"), list):
        return data, data["jobs"]
    return data, []


def _write_jobs(path: Path, original_payload: object, jobs: Iterable[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    job_rows = list(jobs)
    if isinstance(original_payload, dict):
        payload = dict(original_payload)
        payload["jobs"] = job_rows
    else:
        payload = job_rows
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def normalize_home(home: Path, *, apply: bool) -> dict[str, int | bool | str]:
    home = home.expanduser().resolve()
    config_path = home / "config.yaml"
    jobs_path = home / "cron" / "jobs.json"

    cfg = _read_yaml(config_path)
    cron_cfg = cfg.get("cron") if isinstance(cfg.get("cron"), dict) else {}
    cfg_changed = False
    if cron_cfg.get("default_model") != OPENROUTER_FREE_MODEL:
        cron_cfg["default_model"] = OPENROUTER_FREE_MODEL
        cfg_changed = True
    if cron_cfg.get("default_provider") != OPENROUTER_PROVIDER:
        cron_cfg["default_provider"] = OPENROUTER_PROVIDER
        cfg_changed = True
    if cron_cfg.get("strict_delivery_envelope") is not True:
        cron_cfg["strict_delivery_envelope"] = True
        cfg_changed = True
    if cfg_changed:
        cfg["cron"] = cron_cfg
        if apply:
            _write_yaml(config_path, cfg)

    original_jobs_payload, jobs = _read_jobs(jobs_path)
    jobs_changed = False
    updated_jobs = 0
    for job in jobs:
        if not isinstance(job, dict):
            continue
        job_changed = False
        if job.get("model") != OPENROUTER_FREE_MODEL:
            job["model"] = OPENROUTER_FREE_MODEL
            job_changed = True
        if job.get("provider") != OPENROUTER_PROVIDER:
            job["provider"] = OPENROUTER_PROVIDER
            job_changed = True
        if job.get("strict_delivery_envelope") is not True:
            job["strict_delivery_envelope"] = True
            job_changed = True
        if job.get("base_url") not in (None, ""):
            job["base_url"] = None
            job_changed = True
        if job_changed:
            updated_jobs += 1
            jobs_changed = True

    if jobs_changed and apply:
        _write_jobs(jobs_path, original_jobs_payload, jobs)

    return {
        "home": str(home),
        "config_changed": cfg_changed,
        "jobs_changed": jobs_changed,
        "job_count": len(jobs),
        "updated_jobs": updated_jobs,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--home",
        default=str(Path.home() / ".hermes"),
        help="Active Hermes home or profile path to normalize from.",
    )
    parser.add_argument(
        "--only-active-home",
        action="store_true",
        help="Only normalize the selected --home instead of the full .hermes + profiles tree.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write the normalized config/jobs back to disk.",
    )
    args = parser.parse_args(argv)

    homes = iter_target_homes(Path(args.home), all_profiles=not args.only_active_home)
    for home in homes:
        result = normalize_home(home, apply=args.apply)
        print(
            json.dumps(
                {
                    "home": result["home"],
                    "config_changed": result["config_changed"],
                    "jobs_changed": result["jobs_changed"],
                    "job_count": result["job_count"],
                    "updated_jobs": result["updated_jobs"],
                    "applied": bool(args.apply),
                },
                sort_keys=True,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
