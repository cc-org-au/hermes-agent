#!/usr/bin/env bash
# Idempotently ensure HERMES_HOME/workspace/operations/hermes_token_governance.runtime.yaml
# exists with enabled: true and a full consultant_routing block (merged from repo template).
#
# Usage (on the droplet as hermesuser, from repo root):
#   HERMES_HOME=/home/hermesuser/.hermes/profiles/chief-orchestrator \
#     bash memory/core/scripts/core/ensure_chief_token_governance_runtime.sh
#
# Defaults HERMES_HOME to $HOME/.hermes/profiles/chief-orchestrator if unset.
set -euo pipefail
# Script path: memory/core/scripts/core/ → repo root is four levels up.
REPO_ROOT="$(cd "$(dirname "$0")/../../../.." && pwd)"
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes/profiles/chief-orchestrator}"
DST="$HERMES_HOME/workspace/operations/hermes_token_governance.runtime.yaml"
SRC="$REPO_ROOT/memory/runtime/tasks/templates/script-templates/hermes_token_governance.runtime.example.yaml"
if [[ ! -f "$SRC" ]]; then
  echo "missing template: $SRC" >&2
  exit 1
fi
mkdir -p "$(dirname "$DST")"
PY="${HERMES_VENV_PYTHON:-$REPO_ROOT/venv/bin/python}"
if [[ ! -x "$PY" ]]; then
  PY="$(command -v python3)"
fi
if [[ ! -f "$DST" ]]; then
  cp "$SRC" "$DST"
  echo "created $DST"
  exit 0
fi
"$PY" - "$DST" "$SRC" <<'PY'
import sys, pathlib
import yaml

dst, src = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
data = yaml.safe_load(dst.read_text(encoding="utf-8")) or {}
tmpl = yaml.safe_load(src.read_text(encoding="utf-8")) or {}
if not isinstance(data, dict):
    data = {}
if not isinstance(tmpl, dict):
    raise SystemExit("bad template")

data["enabled"] = True
base_cr = tmpl.get("consultant_routing")
if not isinstance(base_cr, dict):
    base_cr = {}
cur_cr = data.get("consultant_routing")
if not isinstance(cur_cr, dict):
    cur_cr = {}
merged = dict(base_cr)
for k, v in cur_cr.items():
    if k == "enabled":
        continue
    merged[k] = v
merged["enabled"] = True
data["consultant_routing"] = merged
dst.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
print("updated", dst)
PY
