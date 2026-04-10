#!/usr/bin/env bash
# Run on the Mac mini (e.g. over SSH): git pull, Homebrew **python@3.12** if **brew** exists,
# **operator_bootstrap_venv.sh**, then **pip install -e ".[messaging]"** (fallback: **-e .**).
#
#   ./scripts/core/operator_remote_install.sh
#
set -euo pipefail
REPO="${HERMES_OPERATOR_REPO:-$HOME/hermes-agent}"
cd "$REPO"

git pull --ff-only origin main || true

export PATH="/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin:$PATH"
if command -v brew >/dev/null 2>&1; then
  export HOMEBREW_NO_AUTO_UPDATE=1
  export NONINTERACTIVE=1
  if ! brew list python@3.12 &>/dev/null; then
    brew install python@3.12 || echo "operator_remote_install.sh: brew install python@3.12 failed (permissions? run as admin or chown Homebrew prefix). Continuing if python3.12 exists on PATH." >&2
  fi
fi
export PATH="/opt/homebrew/opt/python@3.12/bin:/usr/local/opt/python@3.12/bin:$PATH"

if ./scripts/core/operator_bootstrap_venv.sh; then
  :
else
  echo "operator_remote_install.sh: no system Python >=3.11; installing **uv** and creating venv with downloaded Python 3.12…" >&2
  export PATH="${HOME}/.local/bin:${PATH}"
  if ! command -v uv >/dev/null 2>&1; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
  fi
  export PATH="${HOME}/.local/bin:${PATH}"
  command -v uv >/dev/null || {
    echo "operator_remote_install.sh: uv not available after install" >&2
    exit 1
  }
  rm -rf venv
  # uv's default venv has no pip unless --seed (flag only; no trailing "pip" arg).
  uv venv venv --python 3.12 --seed
  ./venv/bin/python -m pip install -U pip
fi

if ! ./venv/bin/pip install -q -e ".[messaging]"; then
  ./venv/bin/pip install -q -e "."
fi

echo "--- hermes doctor (first lines) ---"
./venv/bin/python -m hermes_cli.main doctor 2>&1 | head -50 || true
echo "--- done ---"
REPO_ABS="$(pwd)"
cat <<EOF

=== Hermes is not on PATH until you activate the venv ===
  cd "$REPO_ABS"
  source venv/bin/activate
  hermes setup
  hermes doctor --fix

Or use the venv binary directly (no activate):
  "$REPO_ABS/venv/bin/hermes" setup
  "$REPO_ABS/venv/bin/python" -m hermes_cli.main doctor --fix

Optional (persistent): append venv to PATH in ~/.zprofile
  echo "export PATH=\"$REPO_ABS/venv/bin:\$PATH\"" >> ~/.zprofile
EOF
