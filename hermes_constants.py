"""Shared constants for Hermes Agent.

Import-safe module with no dependencies — can be imported from anywhere
without risk of circular imports.
"""

import os
from contextlib import contextmanager
from contextvars import ContextVar, Token
from pathlib import Path
from typing import Any, Iterator, Optional

# Per-task override (e.g. gateway @profile) — must not replace os.environ globally.
_HERMES_HOME_OVERRIDE: ContextVar[Optional[str]] = ContextVar(
    "hermes_home_override",
    default=None,
)


def _sanitized_hermes_home_env() -> Optional[str]:
    """Return HERMES_HOME from the environment if it is a sane path string.

    Rejects poisoned values (e.g. ``unittest.mock`` string reps accidentally set on
    ``os.environ``), which would otherwise create ``<MagicMock ...>`` directories.
    """
    raw = os.getenv("HERMES_HOME")
    if raw is None:
        return None
    s = str(raw).strip()
    if not s or s.startswith("<") or "MagicMock" in s:
        return None
    return s


def get_hermes_home() -> Path:
    """Return the Hermes home directory (default: ~/.hermes).

    Reads HERMES_HOME env var, falls back to ~/.hermes.
    This is the single source of truth — all other copies should import this.
    """
    _ctx = _HERMES_HOME_OVERRIDE.get()
    if _ctx:
        return Path(_ctx).expanduser()
    s = _sanitized_hermes_home_env()
    if s:
        return Path(s).expanduser()
    return Path(Path.home() / ".hermes").expanduser()


def set_hermes_home_override(path: Path) -> Token:
    """Bind ``get_hermes_home()`` to *path* for the current task (ContextVar).

    Call :func:`reset_hermes_home_override` with the returned token when done.
    Used by the messaging gateway for one-turn @profile routing without mutating
    ``os.environ`` process-wide.
    """
    return _HERMES_HOME_OVERRIDE.set(str(path.expanduser().resolve()))


def reset_hermes_home_override(token: Token) -> None:
    """Reset a prior :func:`set_hermes_home_override` binding."""
    _HERMES_HOME_OVERRIDE.reset(token)


@contextmanager
def hermes_home_override(path: Path) -> Iterator[None]:
    """Context manager for a temporary ``get_hermes_home()`` override."""
    tok = set_hermes_home_override(path)
    try:
        yield
    finally:
        reset_hermes_home_override(tok)


def safe_hermes_home_directory(value: Any) -> Optional[str]:
    """If *value* is a real existing directory path, return its resolved string; else None.

    Use before ``load_hermes_dotenv(hermes_home=…)`` or temporarily setting
    ``HERMES_HOME`` from ``parent_agent._delegate_launch_hermes_home``. Rejects
    ``MagicMock`` / non-string / non-directory values so tests cannot create bogus
    path components under the repo.
    """
    if value is None:
        return None
    try:
        from unittest.mock import MagicMock, Mock, NonCallableMagicMock, NonCallableMock

        if isinstance(value, (MagicMock, Mock, NonCallableMagicMock, NonCallableMock)):
            return None
    except Exception:
        pass
    if not isinstance(value, (str, os.PathLike)):
        return None
    try:
        s = os.fspath(value).strip()
    except Exception:
        return None
    if not s or s.startswith("<") or "MagicMock" in s:
        return None
    try:
        p = Path(s).expanduser()
        if p.is_dir():
            return str(p.resolve())
    except OSError:
        return None
    return None


def get_optional_skills_dir(default: Path | None = None) -> Path:
    """Return the optional-skills directory, honoring package-manager wrappers.

    Packaged installs may ship ``optional-skills`` outside the Python package
    tree and expose it via ``HERMES_OPTIONAL_SKILLS``.
    """
    override = os.getenv("HERMES_OPTIONAL_SKILLS", "").strip()
    if override:
        return Path(override)
    if default is not None:
        return default
    return get_hermes_home() / "optional-skills"


def get_hermes_dir(new_subpath: str, old_name: str) -> Path:
    """Resolve a Hermes subdirectory with backward compatibility.

    New installs get the consolidated layout (e.g. ``cache/images``).
    Existing installs that already have the old path (e.g. ``image_cache``)
    keep using it — no migration required.

    Args:
        new_subpath: Preferred path relative to HERMES_HOME (e.g. ``"cache/images"``).
        old_name: Legacy path relative to HERMES_HOME (e.g. ``"image_cache"``).

    Returns:
        Absolute ``Path`` — old location if it exists on disk, otherwise the new one.
    """
    home = get_hermes_home()
    old_path = home / old_name
    if old_path.exists():
        return old_path
    return home / new_subpath


def get_top_level_hermes_policies_dir() -> Path:
    """Top-level policy tree: ``~/.hermes/policies`` (outside any profile).

    Distinct from :func:`get_hermes_home` / ``HERMES_HOME/policies`` when using a
    named profile — operators may symlink this directory to the chief bundle.
    """
    return Path.home() / ".hermes" / "policies"


def resolve_workspace_operations_dir(base_home: Path) -> Path:
    """Resolve the operations directory for an explicit Hermes home (profile root).

    Path: ``<base_home>/workspace/memory/runtime/operations/``.

    Legacy layout ``<base_home>/workspace/operations/`` is still used when it exists
    on disk and the new path does not (migration: run
    ``scripts/core/migrate_workspace_operations_to_memory_runtime.sh``).
    """
    new_p = base_home / "workspace" / "memory" / "runtime" / "operations"
    old_p = base_home / "workspace" / "operations"
    if new_p.exists() or not old_p.exists():
        return new_p
    return old_p


def get_workspace_operations_dir() -> Path:
    """Canonical operational registers and governance YAML under the active profile.

    Same as :func:`resolve_workspace_operations_dir` with :func:`get_hermes_home`.
    """
    return resolve_workspace_operations_dir(get_hermes_home())


def get_workspace_knowledge_projects_dir() -> Path:
    """Canonical project knowledge tree: ``HERMES_HOME/workspace/memory/knowledge/projects/``."""
    return get_hermes_home() / "workspace" / "memory" / "knowledge" / "projects"


def display_hermes_home() -> str:
    """Return a user-friendly display string for the current HERMES_HOME.

    Uses ``~/`` shorthand for readability::

        default:  ``~/.hermes``
        profile:  ``~/.hermes/profiles/coder``
        custom:   ``/opt/hermes-custom``

    Use this in **user-facing** print/log messages instead of hardcoding
    ``~/.hermes``.  For code that needs a real ``Path``, use
    :func:`get_hermes_home` instead.
    """
    home = get_hermes_home()
    try:
        return "~/" + str(home.relative_to(Path.home()))
    except ValueError:
        return str(home)


VALID_REASONING_EFFORTS = ("xhigh", "high", "medium", "low", "minimal")


def parse_reasoning_effort(effort: str) -> dict | None:
    """Parse a reasoning effort level into a config dict.

    Valid levels: "xhigh", "high", "medium", "low", "minimal", "none".
    Returns None when the input is empty or unrecognized (caller uses default).
    Returns {"enabled": False} for "none".
    Returns {"enabled": True, "effort": <level>} for valid effort levels.
    """
    if not effort or not effort.strip():
        return None
    effort = effort.strip().lower()
    if effort == "none":
        return {"enabled": False}
    if effort in VALID_REASONING_EFFORTS:
        return {"enabled": True, "effort": effort}
    return None


OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_MODELS_URL = f"{OPENROUTER_BASE_URL}/models"
OPENROUTER_CHAT_URL = f"{OPENROUTER_BASE_URL}/chat/completions"

AI_GATEWAY_BASE_URL = "https://ai-gateway.vercel.sh/v1"
AI_GATEWAY_MODELS_URL = f"{AI_GATEWAY_BASE_URL}/models"
AI_GATEWAY_CHAT_URL = f"{AI_GATEWAY_BASE_URL}/chat/completions"

NOUS_API_BASE_URL = "https://inference-api.nousresearch.com/v1"
NOUS_API_CHAT_URL = f"{NOUS_API_BASE_URL}/chat/completions"
