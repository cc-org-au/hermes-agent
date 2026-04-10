#!/usr/bin/env bash
# Run on the Mac mini inside the hermes-agent checkout (or set HERMES_OPERATOR_REPO).
# Hermes requires Python >= 3.11; macOS /usr/bin/python3 is often 3.9 — install Homebrew python@3.12 first.
#
#   brew install python@3.12
#   # Apple Silicon: PATH often includes /opt/homebrew/opt/python@3.12/bin
#   ./scripts/core/operator_bootstrap_venv.sh
#
set -euo pipefail
_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="${HERMES_OPERATOR_REPO:-}"
if [[ -z "$REPO" ]]; then
  REPO="$_SCRIPT_DIR"
  while [[ "$REPO" != / ]]; do
    if [[ -f "$REPO/pyproject.toml" ]]; then
      break
    fi
    REPO="$(dirname "$REPO")"
  done
  if [[ ! -f "$REPO/pyproject.toml" ]]; then
    echo "operator_bootstrap_venv.sh: could not find repo root (pyproject.toml)." >&2
    exit 1
  fi
fi
cd "$REPO"

_pick_python() {
  local try cand
  for try in python3.13 python3.12 python3.11; do
    cand="$(command -v "$try" 2>/dev/null || true)"
    if [[ -n "$cand" ]] && "$cand" -c 'import sys; assert sys.version_info[:2] >= (3, 11)' 2>/dev/null; then
      printf '%s' "$cand"
      return 0
    fi
  done
  local prefix v
  for prefix in /opt/homebrew /usr/local; do
    for v in 3.13 3.12 3.11; do
      cand="${prefix}/opt/python@${v}/bin/python3"
      if [[ -x "$cand" ]] && "$cand" -c 'import sys; assert sys.version_info[:2] >= (3, 11)' 2>/dev/null; then
        printf '%s' "$cand"
        return 0
      fi
    done
  done
  # python.org macOS installer (no Homebrew)
  local fw
  for fw in /Library/Frameworks/Python.framework/Versions/*; do
    [[ -d "$fw" ]] || continue
    cand="${fw}/bin/python3"
    if [[ -x "$cand" ]] && "$cand" -c 'import sys; assert sys.version_info[:2] >= (3, 11)' 2>/dev/null; then
      printf '%s' "$cand"
      return 0
    fi
  done
  return 1
}

PY="$(_pick_python || true)"
if [[ -z "$PY" ]]; then
  cat >&2 <<'EOF'
operator_bootstrap_venv.sh: No Python >= 3.11 found (Hermes requires >= 3.11 per pyproject.toml).

Install Homebrew Python, then re-run this script:

  brew install python@3.12
  echo 'export PATH="/opt/homebrew/opt/python@3.12/bin:$PATH"' >> ~/.zprofile   # Apple Silicon
  # Intel Mac: use /usr/local/opt/python@3.12/bin instead

Or install from https://www.python.org/downloads/ (adds **/Library/Frameworks/.../python3**).

Or run **./scripts/core/operator_remote_install.sh** on the mini — it can fall back to **uv** (downloads Python; no sudo).
EOF
  exit 1
fi

echo "Using: $PY ($("$PY" --version 2>&1))"
if [[ -d venv ]]; then
  echo "Removing existing venv/ (was built with a different interpreter)."
  rm -rf venv
fi
"$PY" -m venv venv
./venv/bin/pip install -U pip
./venv/bin/pip install -e .
echo ""
echo "OK. Examples:"
echo "  source venv/bin/activate"
echo "  hermes setup              # interactive; needs a real TTY"
echo "  ./venv/bin/hermes doctor  # or full path without activate"
