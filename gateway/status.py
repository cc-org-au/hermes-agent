"""
Gateway runtime status helpers.

Provides PID-file based detection of whether the gateway daemon is running,
used by send_message's check_fn to gate availability in the CLI.

The PID file lives at ``{HERMES_HOME}/gateway.pid``.  HERMES_HOME defaults to
``~/.hermes`` but can be overridden via the environment variable.  This means
separate HERMES_HOME directories naturally get separate PID files — a property
that will be useful when we add named profiles (multiple agents running
concurrently under distinct configurations).
"""

import hashlib
import json
import logging
import os
import re
import signal
import sys
from datetime import datetime, timezone
from pathlib import Path
from hermes_constants import get_hermes_home
from typing import Any, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

_GATEWAY_KIND = "hermes-gateway"
_RUNTIME_STATUS_FILE = "gateway_state.json"
_LOCKS_DIRNAME = "gateway-locks"


def _get_pid_path() -> Path:
    """Return the path to the gateway PID file, respecting HERMES_HOME."""
    home = get_hermes_home()
    return home / "gateway.pid"


def _get_runtime_status_path() -> Path:
    """Return the persisted runtime health/status file path."""
    return _get_pid_path().with_name(_RUNTIME_STATUS_FILE)


def _get_lock_dir() -> Path:
    """Return the machine-local directory for token-scoped gateway locks."""
    override = os.getenv("HERMES_GATEWAY_LOCK_DIR")
    if override:
        return Path(override)
    state_home = Path(os.getenv("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    return state_home / "hermes" / _LOCKS_DIRNAME


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _scope_hash(identity: str) -> str:
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]


def _get_scope_lock_path(scope: str, identity: str) -> Path:
    return _get_lock_dir() / f"{scope}-{_scope_hash(identity)}.lock"


def _get_process_start_time(pid: int) -> Optional[int]:
    """Return the kernel start time for a process when available."""
    stat_path = Path(f"/proc/{pid}/stat")
    try:
        # Field 22 in /proc/<pid>/stat is process start time (clock ticks).
        return int(stat_path.read_text().split()[21])
    except (FileNotFoundError, IndexError, PermissionError, ValueError, OSError):
        return None


def _read_process_cmdline(pid: int) -> Optional[str]:
    """Return the process command line as a space-separated string."""
    cmdline_path = Path(f"/proc/{pid}/cmdline")
    try:
        raw = cmdline_path.read_bytes()
    except (FileNotFoundError, PermissionError, OSError):
        return None

    if not raw:
        return None
    return raw.replace(b"\x00", b" ").decode("utf-8", errors="ignore").strip()


def _looks_like_gateway_process(pid: int) -> bool:
    """Return True when the live PID still looks like the Hermes gateway."""
    cmdline = _read_process_cmdline(pid)
    if not cmdline:
        return False

    patterns = (
        "hermes_cli.main gateway",
        "hermes_cli/main.py gateway",
        "hermes gateway",
        "gateway/run.py",
    )
    return any(pattern in cmdline for pattern in patterns)


def _record_looks_like_gateway(record: dict[str, Any]) -> bool:
    """Validate gateway identity from PID-file metadata when cmdline is unavailable."""
    if record.get("kind") != _GATEWAY_KIND:
        return False

    argv = record.get("argv")
    if not isinstance(argv, list) or not argv:
        return False

    cmdline = " ".join(str(part) for part in argv)
    patterns = (
        "hermes_cli.main gateway",
        "hermes_cli/main.py gateway",
        "hermes gateway",
        "gateway/run.py",
    )
    return any(pattern in cmdline for pattern in patterns)


def _build_pid_record() -> dict:
    return {
        "pid": os.getpid(),
        "kind": _GATEWAY_KIND,
        "argv": list(sys.argv),
        "start_time": _get_process_start_time(os.getpid()),
    }


def _build_runtime_status_record() -> dict[str, Any]:
    payload = _build_pid_record()
    payload.update({
        "gateway_state": "starting",
        "exit_reason": None,
        "platforms": {},
        "updated_at": _utc_now_iso(),
    })
    return payload


def _read_json_file(path: Path) -> Optional[dict[str, Any]]:
    if not path.exists():
        return None
    try:
        raw = path.read_text().strip()
    except OSError:
        return None
    if not raw:
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _write_json_file(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload))


def _read_pid_record() -> Optional[dict]:
    pid_path = _get_pid_path()
    if not pid_path.exists():
        return None

    raw = pid_path.read_text().strip()
    if not raw:
        return None

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        try:
            return {"pid": int(raw)}
        except ValueError:
            return None

    if isinstance(payload, int):
        return {"pid": payload}
    if isinstance(payload, dict):
        return payload
    return None


def write_pid_file() -> None:
    """Write the current process PID and metadata to the gateway PID file."""
    _write_json_file(_get_pid_path(), _build_pid_record())


def write_runtime_status(
    *,
    gateway_state: Optional[str] = None,
    exit_reason: Optional[str] = None,
    platform: Optional[str] = None,
    platform_state: Optional[str] = None,
    error_code: Optional[str] = None,
    error_message: Optional[str] = None,
) -> None:
    """Persist gateway runtime health information for diagnostics/status."""
    path = _get_runtime_status_path()
    payload = _read_json_file(path) or _build_runtime_status_record()
    payload.setdefault("platforms", {})
    payload.setdefault("kind", _GATEWAY_KIND)
    payload["pid"] = os.getpid()
    payload["start_time"] = _get_process_start_time(os.getpid())
    payload["updated_at"] = _utc_now_iso()

    if gateway_state is not None:
        payload["gateway_state"] = gateway_state
    if exit_reason is not None:
        payload["exit_reason"] = exit_reason

    if platform is not None:
        platform_payload = payload["platforms"].get(platform, {})
        if platform_state is not None:
            platform_payload["state"] = platform_state
        if error_code is not None:
            platform_payload["error_code"] = error_code
        if error_message is not None:
            platform_payload["error_message"] = error_message
        platform_payload["updated_at"] = _utc_now_iso()
        payload["platforms"][platform] = platform_payload

    _write_json_file(path, payload)


def read_runtime_status() -> Optional[dict[str, Any]]:
    """Read the persisted gateway runtime health/status information."""
    return _read_json_file(_get_runtime_status_path())


def _env_watchdog_require_all_platforms() -> Optional[bool]:
    """Return True/False from env, or None to fall through to gateway config."""
    raw = (os.environ.get("HERMES_GATEWAY_WATCHDOG_REQUIRE_ALL_PLATFORMS") or "").strip().lower()
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off"):
        return False
    return None


def _config_watchdog_require_all_platforms() -> bool:
    try:
        from gateway.config import load_gateway_config

        cfg = load_gateway_config()
        val = (cfg.messaging or {}).get("watchdog_require_all_platforms")
        if val is None:
            return False
        if isinstance(val, str):
            return val.strip().lower() in ("1", "true", "yes", "on")
        return bool(val)
    except Exception:
        logger.debug("watchdog_require_all_platforms: load_gateway_config failed", exc_info=True)
        return False


def _resolve_watchdog_require_all_platforms(explicit: Optional[bool]) -> bool:
    if explicit is not None:
        return bool(explicit)
    env_v = _env_watchdog_require_all_platforms()
    if env_v is not None:
        return env_v
    return _config_watchdog_require_all_platforms()


def _env_watchdog_enforce_singleton() -> bool:
    """Default True: ``watchdog-check`` may SIGTERM duplicate gateways for this HERMES_HOME.

    Disable with ``HERMES_GATEWAY_WATCHDOG_ENFORCE_SINGLE=0`` or legacy
    ``WATCHDOG_ENFORCE_SINGLE_GATEWAY=0``.
    """
    specific = (os.environ.get("HERMES_GATEWAY_WATCHDOG_ENFORCE_SINGLE") or "").strip().lower()
    if specific:
        return specific not in ("0", "false", "no", "off")
    legacy = (os.environ.get("WATCHDOG_ENFORCE_SINGLE_GATEWAY") or "").strip().lower()
    if legacy:
        return legacy not in ("0", "false", "no", "off")
    return True


def _read_hermes_home_from_pid_environ(pid: int) -> Optional[str]:
    """Return HERMES_HOME from ``/proc/<pid>/environ`` when available (Linux)."""
    path = Path(f"/proc/{pid}/environ")
    if not path.exists():
        return None
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    for part in raw.split(b"\0"):
        if part.startswith(b"HERMES_HOME="):
            return part.split(b"=", 1)[1].decode("utf-8", errors="surrogateescape")
    return None


def _gateway_profile_cli_token() -> Optional[str]:
    """Profile name used with ``-p`` for the current HERMES_HOME, or None for default ``~/.hermes``."""
    home = get_hermes_home().resolve()
    default = (Path.home() / ".hermes").resolve()
    if home == default:
        return None
    profiles_root = (default / "profiles").resolve()
    try:
        rel = home.relative_to(profiles_root)
        if len(rel.parts) == 1 and re.match(r"^[a-z0-9][a-z0-9_-]{0,63}$", rel.parts[0]):
            return rel.parts[0]
    except ValueError:
        pass
    return None


def _pid_belongs_to_this_hermes_home(pid: int, home: Path) -> bool:
    """True when ``pid`` is a gateway process for ``home`` (env or ``-p`` argv)."""
    resolved = home.resolve()
    envh = _read_hermes_home_from_pid_environ(pid)
    if envh:
        try:
            return Path(envh).resolve() == resolved
        except OSError:
            return False
    cmd = _read_process_cmdline(pid) or ""
    tok = _gateway_profile_cli_token()
    if tok is None:
        m = re.search(r"(?:^|\s)-p(?:=|\s+)(\S+)", cmd)
        if m:
            prof = m.group(1).strip("\"'")
            if prof:
                return False
        return True
    return bool(re.search(rf"(?:^|\s)-p(?:=|\s+){re.escape(tok)}(?:\s|$)", cmd))


def _pick_newest_gateway_pid(pids: list[int]) -> Optional[int]:
    """Among gateway PIDs, prefer the one with the greatest kernel start time (newest)."""
    if not pids:
        return None
    if len(pids) == 1:
        return pids[0]
    scored: list[tuple[int, int]] = []
    for p in pids:
        st = _get_process_start_time(p)
        if st is not None:
            scored.append((st, p))
    if scored:
        return max(scored, key=lambda t: t[0])[1]
    return pids[-1]


def _looks_like_long_running_gateway_process(pid: int) -> bool:
    """Exclude ephemeral ``gateway <subcommand>`` CLIs from daemon dedupe."""
    cmd = (_read_process_cmdline(pid) or "").lower()
    if "watchdog-check" in cmd or "audit-singleton" in cmd:
        return False
    for bad in (
        " gateway install",
        " gateway uninstall",
        " gateway setup",
        " gateway stop",
    ):
        if bad in cmd:
            return False
    return True


def dedupe_gateway_processes_for_current_home() -> Tuple[int, str]:
    """Terminate duplicate Hermes gateway processes for the current ``HERMES_HOME``.

    Keeps the PID registered in ``gateway.pid`` when it is still live and matches
    this home; otherwise keeps the **newest** matching process (by ``/proc`` start
    time on Linux) and sends ``SIGTERM`` to older strays.

    Returns:
        ``(kill_count, detail_string)`` — ``kill_count`` is the number of SIGTERM
        signals sent (best-effort).
    """
    try:
        from hermes_cli.gateway import find_gateway_pids
    except Exception:
        logger.debug("dedupe_gateway_processes: find_gateway_pids unavailable", exc_info=True)
        return 0, "skip_import"

    home = get_hermes_home()
    raw = find_gateway_pids()
    candidates = [
        p
        for p in raw
        if _looks_like_long_running_gateway_process(p) and _pid_belongs_to_this_hermes_home(p, home)
    ]
    if len(candidates) <= 1:
        return 0, "singleton"

    canonical = get_running_pid()
    if canonical is not None and canonical in candidates:
        keeper = canonical
    elif canonical is not None and canonical not in candidates:
        logger.debug(
            "dedupe_gateway_processes: gateway.pid pid=%s not in filtered candidates %s; skip",
            canonical,
            candidates,
        )
        return 0, "canonical_mismatch_skip"
    else:
        keeper = _pick_newest_gateway_pid(candidates)
        if keeper is None:
            return 0, "no_keeper"

    killed = 0
    detail_parts: list[str] = []
    for pid in candidates:
        if pid == keeper:
            continue
        try:
            os.kill(pid, signal.SIGTERM)
            killed += 1
            detail_parts.append(str(pid))
        except (ProcessLookupError, PermissionError):
            pass
    if not detail_parts:
        return 0, "singleton"
    return killed, f"terminated_pids={','.join(detail_parts)} keeper={keeper}"


def runtime_status_watchdog_healthy(
    payload: Optional[dict[str, Any]] = None,
    *,
    require_all_platforms: Optional[bool] = None,
    expected_platforms: Optional[Sequence[str]] = None,
) -> tuple[bool, str]:
    """Return ``(ok, reason)`` for external process watchdogs.

    Default (strict off): healthy when **all** of the following hold:

    1. A live gateway process is registered in ``gateway.pid`` (when reading
       status from disk — callers that pass an explicit ``payload`` dict, e.g.
       unit tests, skip this check).
    2. ``gateway_state`` in ``gateway_state.json`` is ``running``.
    3. **At least one** platform row reports ``state == "connected"``.

    Optional **strict** mode (every configured messaging platform must be
    connected) — enable via either:

    - ``messaging.watchdog_require_all_platforms: true`` in merged gateway
      config (``config.yaml`` / ``gateway.json``), or
    - ``HERMES_GATEWAY_WATCHDOG_REQUIRE_ALL_PLATFORMS=1`` in the environment
      (overrides config when set to a truthy/falsey string).

    In strict mode, expected platforms are ``GatewayConfig.get_connected_platforms()``
    unless tests pass ``expected_platforms=...``. If none are configured,
    health is **ok** (nothing to enforce). Missing status rows or any state
    other than ``connected`` (e.g. ``reconnecting``, ``fatal``) fails the check
    so external watchdogs can restart the gateway and bring every adapter up.
    """
    loaded_from_disk = payload is None
    if loaded_from_disk and _env_watchdog_enforce_singleton():
        try:
            n_killed, detail = dedupe_gateway_processes_for_current_home()
            if n_killed:
                logger.warning(
                    "watchdog singleton enforced: terminated %s duplicate gateway process(es) (%s)",
                    n_killed,
                    detail,
                )
        except Exception:
            logger.debug("watchdog singleton dedupe failed", exc_info=True)
    if loaded_from_disk:
        payload = read_runtime_status()
    if not payload:
        return False, "missing gateway_state.json"
    if loaded_from_disk and get_running_pid() is None:
        return (
            False,
            "gateway process not running (stale or missing gateway.pid)",
        )
    if payload.get("gateway_state") != "running":
        return False, f"gateway_state={payload.get('gateway_state')!r}"
    platforms = payload.get("platforms") or {}
    if not platforms:
        return False, "no platform statuses present"

    require_all = _resolve_watchdog_require_all_platforms(require_all_platforms)
    if require_all:
        if expected_platforms is not None:
            exp = [str(x).strip() for x in expected_platforms if str(x).strip()]
        else:
            try:
                from gateway.config import load_gateway_config

                gc = load_gateway_config()
                exp = [p.value for p in gc.get_connected_platforms()]
            except Exception:
                logger.debug("watchdog expected platforms: load failed", exc_info=True)
                exp = []
        if not exp:
            return True, "ok watchdog_require_all (no messaging platforms configured)"
        missing_status: list[str] = []
        not_connected: list[str] = []
        for name in sorted(exp):
            pdata = platforms.get(name)
            if not isinstance(pdata, dict):
                missing_status.append(name)
                continue
            if pdata.get("state") != "connected":
                not_connected.append(f"{name}={pdata.get('state')!r}")
        if missing_status or not_connected:
            parts: list[str] = []
            if missing_status:
                parts.append(f"missing_status={','.join(missing_status)}")
            if not_connected:
                parts.append(f"not_connected={','.join(not_connected)}")
            return False, f"watchdog_require_all_platforms: {'; '.join(parts)}"
        return True, f"ok all_connected={','.join(exp)}"

    connected = [
        name
        for name, pdata in platforms.items()
        if isinstance(pdata, dict) and pdata.get("state") == "connected"
    ]
    if connected:
        return True, f"ok connected={','.join(sorted(connected))}"
    return False, "no platform reports state=connected"


def remove_pid_file() -> None:
    """Remove the gateway PID file if it exists."""
    try:
        _get_pid_path().unlink(missing_ok=True)
    except Exception:
        pass


def acquire_scoped_lock(scope: str, identity: str, metadata: Optional[dict[str, Any]] = None) -> tuple[bool, Optional[dict[str, Any]]]:
    """Acquire a machine-local lock keyed by scope + identity.

    Used to prevent multiple local gateways from using the same external identity
    at once (e.g. the same Telegram bot token across different HERMES_HOME dirs).
    """
    lock_path = _get_scope_lock_path(scope, identity)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        **_build_pid_record(),
        "scope": scope,
        "identity_hash": _scope_hash(identity),
        "metadata": metadata or {},
        "updated_at": _utc_now_iso(),
    }

    existing = _read_json_file(lock_path)
    if existing:
        try:
            existing_pid = int(existing["pid"])
        except (KeyError, TypeError, ValueError):
            existing_pid = None

        if existing_pid == os.getpid() and existing.get("start_time") == record.get("start_time"):
            _write_json_file(lock_path, record)
            return True, existing

        stale = existing_pid is None
        if not stale:
            try:
                os.kill(existing_pid, 0)
            except (ProcessLookupError, PermissionError):
                stale = True
            else:
                current_start = _get_process_start_time(existing_pid)
                if (
                    existing.get("start_time") is not None
                    and current_start is not None
                    and current_start != existing.get("start_time")
                ):
                    stale = True
                # Check if process is stopped (Ctrl+Z / SIGTSTP) — stopped
                # processes still respond to os.kill(pid, 0) but are not
                # actually running. Treat them as stale so --replace works.
                if not stale:
                    try:
                        _proc_status = Path(f"/proc/{existing_pid}/status")
                        if _proc_status.exists():
                            for _line in _proc_status.read_text().splitlines():
                                if _line.startswith("State:"):
                                    _state = _line.split()[1]
                                    if _state in ("T", "t"):  # stopped or tracing stop
                                        stale = True
                                    break
                    except (OSError, PermissionError):
                        pass
        if stale:
            try:
                lock_path.unlink(missing_ok=True)
            except OSError:
                pass
        else:
            return False, existing

    try:
        fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return False, _read_json_file(lock_path)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(record, handle)
    except Exception:
        try:
            lock_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    return True, None


def release_scoped_lock(scope: str, identity: str) -> None:
    """Release a previously-acquired scope lock when owned by this process."""
    lock_path = _get_scope_lock_path(scope, identity)
    existing = _read_json_file(lock_path)
    if not existing:
        return
    if existing.get("pid") != os.getpid():
        return
    if existing.get("start_time") != _get_process_start_time(os.getpid()):
        return
    try:
        lock_path.unlink(missing_ok=True)
    except OSError:
        pass


def release_all_scoped_locks() -> int:
    """Remove all scoped lock files in the lock directory.

    Called during --replace to clean up stale locks left by stopped/killed
    gateway processes that did not release their locks gracefully.
    Returns the number of lock files removed.
    """
    lock_dir = _get_lock_dir()
    removed = 0
    if lock_dir.exists():
        for lock_file in lock_dir.glob("*.lock"):
            try:
                lock_file.unlink(missing_ok=True)
                removed += 1
            except OSError:
                pass
    return removed


def get_running_pid() -> Optional[int]:
    """Return the PID of a running gateway instance, or ``None``.

    Checks the PID file and verifies the process is actually alive.
    Cleans up stale PID files automatically.
    """
    record = _read_pid_record()
    if not record:
        remove_pid_file()
        return None

    try:
        pid = int(record["pid"])
    except (KeyError, TypeError, ValueError):
        remove_pid_file()
        return None

    try:
        os.kill(pid, 0)  # signal 0 = existence check, no actual signal sent
    except (ProcessLookupError, PermissionError):
        remove_pid_file()
        return None

    recorded_start = record.get("start_time")
    current_start = _get_process_start_time(pid)
    if recorded_start is not None and current_start is not None and current_start != recorded_start:
        remove_pid_file()
        return None

    if not _looks_like_gateway_process(pid):
        if not _record_looks_like_gateway(record):
            remove_pid_file()
            return None

    return pid


def is_gateway_running() -> bool:
    """Check if the gateway daemon is currently running."""
    return get_running_pid() is not None
