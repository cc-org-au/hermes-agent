#!/usr/bin/env python3
"""Download Hugging Face hub models for local_models/manifest.yaml with budget + resume.

Requires: pip install 'huggingface_hub>=0.26' hf_transfer pyyaml
Env: HF_HUB_ENABLE_HF_TRANSFER=1 (recommended) for fast parallel shard downloads.

Safe to interrupt and re-run; snapshot_download resumes incomplete files.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LOCAL = REPO_ROOT / "local_models"
HUB = LOCAL / "hub"
LOG_DIR = LOCAL / "logs"
FAILURES = LOG_DIR / "failures.jsonl"
SKIPPED = LOG_DIR / "skipped_budget.json"
STATE = HUB / "state.json"


def _load_existing_repos() -> dict[str, dict]:
    if not STATE.is_file():
        return {}
    try:
        old = json.loads(STATE.read_text(encoding="utf-8"))
        r = old.get("repos") or {}
        return dict(r) if isinstance(r, dict) else {}
    except Exception:
        return {}


def _write_state(
    downloaded: dict[str, dict],
    *,
    budget_bytes: int,
    max_workers: int,
) -> None:
    payload = {
        "downloaded": sorted(downloaded.keys()),
        "repos": downloaded,
        "budget_bytes": budget_bytes,
        "max_workers": max_workers,
        "updated": datetime.now(timezone.utc).isoformat(),
    }
    STATE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(STATE)


def _verify_repo_snapshot(dest: Path) -> bool:
    """True if the snapshot looks complete (config + weight shards or index)."""
    if not dest.is_dir():
        return False
    if not (dest / "config.json").is_file():
        return False
    if (dest / "model.safetensors.index.json").is_file():
        return True
    for p in dest.glob("*.safetensors"):
        if p.is_file() and p.stat().st_size > 1_000_000:
            return True
    for p in dest.glob("*.gguf"):
        if p.is_file() and p.stat().st_size > 1_000_000:
            return True
    for name in ("pytorch_model.bin", "pytorch_model.bin.index.json"):
        if (dest / name).is_file() and (dest / name).stat().st_size > 1_000_000:
            return True
    return False


def _run_sync_to_droplet() -> None:
    sync_sh = REPO_ROOT / "scripts" / "local_models" / "sync_to_droplet.sh"
    if not sync_sh.is_file():
        print(f"sync: missing {sync_sh}", flush=True)
        raise FileNotFoundError(str(sync_sh))
    print(f"\n>>> Running {sync_sh}", flush=True)
    subprocess.run(
        ["/bin/bash", str(sync_sh)],
        cwd=str(REPO_ROOT),
        check=True,
        env=os.environ.copy(),
    )


def _ensure_hf() -> None:
    try:
        import huggingface_hub  # noqa: F401
    except ImportError:
        print("Install: pip install 'huggingface_hub>=0.26' hf_transfer", file=sys.stderr)
        sys.exit(1)


def _bytes_for_repo(api, repo_id: str) -> int | None:
    from huggingface_hub import HfApi

    if not isinstance(api, HfApi):
        api = HfApi()
    try:
        info = api.repo_info(repo_id, repo_type="model", files_metadata=True)
    except Exception as exc:
        print(f"[size] {repo_id}: failed ({exc})", flush=True)
        return None
    total = 0
    for s in info.siblings or []:
        sz = getattr(s, "size", None)
        if isinstance(sz, int) and sz > 0:
            total += sz
    return total if total > 0 else None


def _greedy_pack(
    items: list[tuple[str, int, int]],
    budget: int,
) -> tuple[list[tuple[str, int, int]], list[tuple[str, int, int]]]:
    """items: (repo_id, size_bytes, priority). Lower priority first. Returns (chosen, skipped)."""
    # Sort: priority asc, then size asc
    items = sorted(items, key=lambda x: (x[2], x[1]))
    chosen: list[tuple[str, int, int]] = []
    skipped: list[tuple[str, int, int]] = []
    used = 0
    for repo_id, size, pri in items:
        if size < 0:
            skipped.append((repo_id, size, pri))
            continue
        if used + size <= budget:
            chosen.append((repo_id, size, pri))
            used += size
        else:
            skipped.append((repo_id, size, pri))
    return chosen, skipped


def main() -> int:
    _ensure_hf()
    os.environ.setdefault("HF_HUB_ENABLE_HF_TRANSFER", "1")

    ap = argparse.ArgumentParser(description="Download HF models under local_models/hub/")
    ap.add_argument("--budget-gb", type=float, default=200.0)
    ap.add_argument("--max-workers", type=int, default=32)
    ap.add_argument("--manifest", type=Path, default=LOCAL / "manifest.yaml")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument(
        "--no-sync-droplet",
        action="store_true",
        help="Do not rsync local_models/hub to the droplet after successful verified downloads.",
    )
    args = ap.parse_args()

    import yaml
    from huggingface_hub import HfApi, snapshot_download

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    HUB.mkdir(parents=True, exist_ok=True)

    raw = yaml.safe_load(args.manifest.read_text(encoding="utf-8")) or {}
    budget_bytes = int(float(raw.get("budget_gb", args.budget_gb)) * (1024**3))
    max_workers = int(raw.get("max_workers", args.max_workers))
    repos_cfg = raw.get("repos") or []

    api = HfApi()
    items: list[tuple[str, int, int]] = []
    for i, row in enumerate(repos_cfg):
        if isinstance(row, str):
            rid, pri = row, 100 + i
        elif isinstance(row, dict):
            rid = str(row.get("id") or "").strip()
            pri = int(row.get("priority", 100 + i))
        else:
            continue
        if not rid:
            continue
        sz = _bytes_for_repo(api, rid)
        if sz is None:
            items.append((rid, -1, pri))
        else:
            items.append((rid, sz, pri))

    known = [(a, b, c) for a, b, c in items if b >= 0]
    unknown = [(a, b, c) for a, b, c in items if b < 0]
    chosen, skipped_budget = _greedy_pack(known, budget_bytes)
    skipped: list[tuple[str, int, int]] = list(skipped_budget) + list(unknown)

    SKIPPED.write_text(
        json.dumps(
            {
                "budget_bytes": budget_bytes,
                "skipped": [{"id": a, "bytes": b, "priority": c} for a, b, c in skipped],
                "ts": datetime.now(timezone.utc).isoformat(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    print(
        f"Budget {budget_bytes / (1024**3):.2f} GiB — plan {len(chosen)} repo(s), "
        f"skip {len(skipped)} (see {SKIPPED})",
        flush=True,
    )

    if args.dry_run:
        for rid, sz, _ in chosen:
            print(f"  would download {rid} (~{sz / (1024**3):.2f} GiB)", flush=True)
        return 0

    downloaded: dict[str, dict] = _load_existing_repos()
    failures: list[dict] = []

    for rid, sz, _ in chosen:
        slug = rid.replace("/", "__")
        dest = HUB / slug
        dest.mkdir(parents=True, exist_ok=True)
        t0 = time.time()
        print(f"\n>>> {rid} -> {dest} (max_workers={max_workers})", flush=True)
        try:
            snapshot_download(
                repo_id=rid,
                local_dir=str(dest),
                max_workers=max_workers,
            )
            downloaded[rid] = {"path": str(dest), "bytes_approx": sz, "seconds": round(time.time() - t0, 2)}
            print(f"    OK in {downloaded[rid]['seconds']}s", flush=True)
            _write_state(downloaded, budget_bytes=budget_bytes, max_workers=max_workers)
        except Exception as exc:
            rec = {
                "repo": rid,
                "error": str(exc),
                "traceback": traceback.format_exc(),
                "ts": datetime.now(timezone.utc).isoformat(),
            }
            failures.append(rec)
            with open(FAILURES, "a", encoding="utf-8") as ff:
                ff.write(json.dumps(rec) + "\n")
            print(f"    FAIL: {exc}", flush=True)

    _write_state(downloaded, budget_bytes=budget_bytes, max_workers=max_workers)
    print(f"\nFinal state: {STATE}", flush=True)
    if failures:
        print(f"WARNING: {len(failures)} failure(s) appended to {FAILURES}", flush=True)
        return 2

    # Verify each planned repo path, then optional droplet sync
    verify_ok = True
    for rid, sz, _ in chosen:
        slug = rid.replace("/", "__")
        dest = HUB / slug
        if not _verify_repo_snapshot(dest):
            print(f"VERIFY FAIL: {rid} at {dest} — expected config + weight shards", flush=True)
            verify_ok = False
    if not verify_ok:
        print("Verification failed — skipping droplet sync.", flush=True)
        return 3

    if not args.no_sync_droplet and chosen:
        try:
            _run_sync_to_droplet()
        except subprocess.CalledProcessError as exc:
            print(f"sync_to_droplet failed (exit {exc.returncode})", flush=True)
            return 4
        except OSError as exc:
            print(f"sync_to_droplet failed: {exc}", flush=True)
            return 4

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
