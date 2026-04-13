"""SQLite-backed cache for idempotent, read-only tool results (profile-local)."""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import threading
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_cfg: Dict[str, Any] = {
    "enabled": False,
    "ttl_seconds": 3600,
    "sqlite_relpath": "semantic_tool_cache.sqlite",
    "allow_tools": [],
    "host_role_env_precedence": [
        "HERMES_CLI_INSTANCE_LABEL",
        "HERMES_GATEWAY_LOCK_INSTANCE",
    ],
}


def configure_semantic_tool_cache(merged: Dict[str, Any]) -> None:
    """Replace process-local cache policy (merged canon + config overlay)."""
    global _cfg
    with _lock:
        _cfg = {**_cfg, **merged}


def _host_role() -> str:
    prec = _cfg.get("host_role_env_precedence") or []
    import os

    for key in prec:
        v = (os.environ.get(key) or "").strip()
        if v:
            return v[:128]
    plat = (os.environ.get("HERMES_SESSION_SOURCE") or os.environ.get("HERMES_PLATFORM") or "").strip()
    return plat[:128] or "default"


def _normalize_args(args: Dict[str, Any]) -> str:
    try:
        return json.dumps(args, sort_keys=True, ensure_ascii=False, default=str)
    except TypeError:
        return json.dumps(str(args), ensure_ascii=False)


def _cache_key(tool_name: str, args: Dict[str, Any], hermes_home: str) -> str:
    payload = f"{tool_name}\0{_host_role()}\0{hermes_home}\0{_normalize_args(args)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _db_path() -> "Any":
    from hermes_constants import get_hermes_home

    rel = str(_cfg.get("sqlite_relpath") or "semantic_tool_cache.sqlite").strip()
    if not rel or ".." in rel.replace("\\", "/"):
        rel = "semantic_tool_cache.sqlite"
    return get_hermes_home() / rel


def _connect() -> sqlite3.Connection:
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=30.0)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS cache (k TEXT PRIMARY KEY, v TEXT NOT NULL, exp REAL NOT NULL)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cache_exp ON cache(exp)")
    return conn


def _prune_expired(conn: sqlite3.Connection) -> None:
    now = time.time()
    conn.execute("DELETE FROM cache WHERE exp <= ?", (now,))


def lookup(tool_name: str, args: Dict[str, Any]) -> Optional[str]:
    if not _cfg.get("enabled"):
        return None
    allow: List[str] = _cfg.get("allow_tools") or []
    if tool_name not in allow:
        return None
    from hermes_constants import get_hermes_home

    key = _cache_key(tool_name, args, str(get_hermes_home()))
    try:
        with _lock:
            conn = _connect()
            try:
                _prune_expired(conn)
                row = conn.execute("SELECT v, exp FROM cache WHERE k = ?", (key,)).fetchone()
                if not row:
                    return None
                _v, exp = row
                if float(exp) <= time.time():
                    conn.execute("DELETE FROM cache WHERE k = ?", (key,))
                    conn.commit()
                    return None
                return str(_v)
            finally:
                conn.close()
    except Exception as e:
        logger.debug("semantic_tool_cache lookup failed: %s", e)
        return None


def store(tool_name: str, args: Dict[str, Any], result: str) -> None:
    if not _cfg.get("enabled"):
        return
    allow: List[str] = _cfg.get("allow_tools") or []
    if tool_name not in allow:
        return
    from hermes_constants import get_hermes_home

    ttl = int(_cfg.get("ttl_seconds") or 3600)
    key = _cache_key(tool_name, args, str(get_hermes_home()))
    exp = time.time() + float(max(60, ttl))
    try:
        with _lock:
            conn = _connect()
            try:
                conn.execute(
                    "INSERT OR REPLACE INTO cache(k, v, exp) VALUES (?,?,?)",
                    (key, result, exp),
                )
                conn.commit()
            finally:
                conn.close()
    except Exception as e:
        logger.debug("semantic_tool_cache store failed: %s", e)


def clear_semantic_tool_cache_for_tests() -> None:
    """Remove DB file (tests only)."""
    from pathlib import Path

    p = _db_path()
    try:
        if Path(p).exists():
            Path(p).unlink()
    except OSError:
        pass
