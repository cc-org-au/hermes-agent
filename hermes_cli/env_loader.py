"""Helpers for loading Hermes .env files consistently across entrypoints."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


def _load_dotenv_with_fallback(path: Path, *, override: bool) -> None:
    try:
        load_dotenv(dotenv_path=path, override=override, encoding="utf-8")
    except UnicodeDecodeError:
        load_dotenv(dotenv_path=path, override=override, encoding="latin-1")


def load_hermes_dotenv(
    *,
    hermes_home: str | os.PathLike | None = None,
    project_env: str | os.PathLike | None = None,
) -> list[Path]:
    """Load Hermes environment files with user config taking precedence.

    Behavior:
    - ``~/.hermes/.env`` overrides stale shell-exported values when present.
    - **Profile runtimes** (``HERMES_HOME`` is ``…/.hermes/profiles/<name>``): load the
      parent ``~/.hermes/.env`` first so shared keys (e.g. ``HF_TOKEN``, ``GEMINI_API_KEY``)
      apply, then the profile's own ``.env`` with override so profile-specific values win.
    - project ``.env`` acts as a dev fallback and only fills missing values when
      the user env exists.
    - if no user env exists, the project ``.env`` also overrides stale shell vars.
    """
    loaded: list[Path] = []

    home_path = Path(hermes_home or os.getenv("HERMES_HOME", Path.home() / ".hermes")).expanduser()

    # When running under a profile, inherit secrets from the default Hermes home .env
    # before applying the profile-specific file (gateway / CLI / cron use profile HERMES_HOME).
    parts = home_path.parts
    if "profiles" in parts:
        try:
            pi = parts.index("profiles")
            root_hermes = Path(*parts[:pi])
            root_env = root_hermes / ".env"
            prof_env = home_path / ".env"
            if root_env.is_file():
                # If the profile has its own .env, load root first without overriding
                # keys the profile will set; if not, root is the only user env file.
                _load_dotenv_with_fallback(root_env, override=not prof_env.is_file())
                loaded.append(root_env)
        except (ValueError, OSError):
            pass

    user_env = home_path / ".env"
    project_env_path = Path(project_env) if project_env else None

    if user_env.exists():
        _load_dotenv_with_fallback(user_env, override=True)
        loaded.append(user_env)

    if project_env_path and project_env_path.exists():
        _load_dotenv_with_fallback(project_env_path, override=not loaded)
        loaded.append(project_env_path)

    # VPS / split-env: allow OPENAI_API_KEY_DROPLET when OPENAI_API_KEY is unset.
    _droplet_key = os.environ.get("OPENAI_API_KEY_DROPLET", "").strip()
    _openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if _droplet_key and not _openai_key:
        os.environ["OPENAI_API_KEY"] = _droplet_key

    return loaded
