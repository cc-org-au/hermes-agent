"""Hash manifest for policies/ to detect edits between pipeline runs."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from _paths import MANIFEST_PATH, POLICIES_ROOT, STATE_DIR

SKIP_PARTS = frozenset({".pipeline_state", "__pycache__", ".git"})
TEXT_SUFFIXES = {".md", ".py"}


def _iter_tracked_files() -> list[Path]:
    files: list[Path] = []
    for root in (POLICIES_ROOT,):
        for p in root.rglob("*"):
            if not p.is_file():
                continue
            if p.name.startswith("._"):
                continue
            rel = p.relative_to(POLICIES_ROOT)
            if any(part in SKIP_PARTS for part in rel.parts):
                continue
            if p.suffix not in TEXT_SUFFIXES:
                continue
            files.append(p)
    files.sort(key=lambda x: str(x).lower())
    return files


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def compute_manifest() -> dict[str, str]:
    """relative path (posix) -> sha256."""
    out: dict[str, str] = {}
    for p in _iter_tracked_files():
        rel = p.relative_to(POLICIES_ROOT).as_posix()
        out[rel] = file_hash(p)
    return out


def load_saved_manifest() -> dict[str, str] | None:
    if not MANIFEST_PATH.is_file():
        return None
    try:
        data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict) and "files" in data:
            raw = data["files"]
            if isinstance(raw, dict):
                return {str(k): str(v) for k, v in raw.items()}
    except (OSError, json.JSONDecodeError, TypeError):
        return None
    return None


def manifest_changed(current: dict[str, str], saved: dict[str, str] | None) -> bool:
    if saved is None:
        return True
    if set(current.keys()) != set(saved.keys()):
        return True
    for k, v in current.items():
        if saved.get(k) != v:
            return True
    return False


def diff_manifest(current: dict[str, str], saved: dict[str, str] | None) -> list[str]:
    """Human-readable diff lines."""
    lines: list[str] = []
    if saved is None:
        lines.append("(no saved manifest — treating as full refresh)")
        return lines
    all_keys = sorted(set(current) | set(saved))
    for k in all_keys:
        a, b = current.get(k), saved.get(k)
        if k not in saved:
            lines.append(f"+ {k}")
        elif k not in current:
            lines.append(f"- {k}")
        elif a != b:
            lines.append(f"M {k}")
    if not lines:
        lines.append("(no file changes)")
    return lines


def write_manifest(current: dict[str, str]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    payload = {"version": 1, "files": current}
    MANIFEST_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def describe_manifest() -> str:
    m = compute_manifest()
    return f"{len(m)} tracked files under policies/"

