"""strip_messaging_env_from_hermes_home.py behavior (no hermes_cli import cycle in unit)."""

from pathlib import Path


def test_strip_script_compiles() -> None:
    import py_compile

    root = Path(__file__).resolve().parents[2]
    path = root / "scripts" / "core" / "strip_messaging_env_from_hermes_home.py"
    assert path.is_file(), f"missing {path}"
    py_compile.compile(str(path), doraise=True)
