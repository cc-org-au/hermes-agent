"""strip_messaging_env_from_hermes_home.py behavior."""

from pathlib import Path


def test_messaging_secrets_vs_allowlists() -> None:
    """Tokens stripped; allowlist / channel ID vars kept."""
    import importlib.util

    root = Path(__file__).resolve().parents[2]
    path = root / "scripts" / "core" / "strip_messaging_env_from_hermes_home.py"
    spec = importlib.util.spec_from_file_location("strip_messaging_env", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)

    secrets = mod._messaging_secret_key_names()
    assert "TELEGRAM_BOT_TOKEN" in secrets
    assert "SLACK_APP_TOKEN" in secrets
    assert "TELEGRAM_ALLOWED_USERS" not in secrets
    assert "SLACK_ALLOWED_CHANNELS" not in secrets
    assert "API_SERVER_KEY" not in secrets


def test_strip_script_compiles() -> None:
    import py_compile

    root = Path(__file__).resolve().parents[2]
    path = root / "scripts" / "core" / "strip_messaging_env_from_hermes_home.py"
    assert path.is_file(), f"missing {path}"
    py_compile.compile(str(path), doraise=True)
