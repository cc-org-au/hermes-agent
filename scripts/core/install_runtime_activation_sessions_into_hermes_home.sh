#!/usr/bin/env bash
#
# Copy phased activation session prompts into HERMES_HOME so file tools resolve them
# without relying on the git checkout path.
#
#   HERMES_HOME=/path/to/profile bash scripts/core/install_runtime_activation_sessions_into_hermes_home.sh
#
# Source: ${HERMES_AGENT_DIR}/runtime-activation-sessions/*.md (repo checkout on the host).
# Target: ${HERMES_HOME}/sessions/runtime-activation-sessions/
#
# With --patch-governance (default): idempotently extend workspace/operations/runtime_governance.runtime.yaml
# so injected context points at sessions/runtime-activation-sessions/.

set -euo pipefail

PATCH_GOV=1
if [[ "${1:-}" == "--no-patch-governance" ]]; then
  PATCH_GOV=0
fi

AGENT_DIR="${HERMES_AGENT_DIR:-${HOME}/hermes-agent}"
SRC="${AGENT_DIR}/runtime-activation-sessions"
DST_ROOT="${HERMES_HOME:?Set HERMES_HOME}/sessions/runtime-activation-sessions"

if [[ ! -d "$SRC" ]]; then
  echo "install_runtime_activation_sessions: missing source dir ${SRC} (set HERMES_AGENT_DIR?)" >&2
  exit 1
fi

mkdir -p "$DST_ROOT"
shopt -s nullglob
mds=( "${SRC}"/*.md )
if [[ ${#mds[@]} -eq 0 ]]; then
  echo "install_runtime_activation_sessions: no *.md under ${SRC}" >&2
  exit 1
fi
cp -f "${mds[@]}" "$DST_ROOT/"
echo "install_runtime_activation_sessions: copied ${#mds[@]} files -> ${DST_ROOT}"

if [[ "$PATCH_GOV" -eq 1 ]]; then
  GOV="${HERMES_HOME}/workspace/operations/runtime_governance.runtime.yaml"
  if [[ -f "$GOV" ]]; then
    python3 - "$GOV" <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
if "sessions/runtime-activation-sessions" in text:
    print("install_runtime_activation_sessions: governance yaml already references sessions/runtime-activation-sessions")
    sys.exit(0)

needle = '  - "WORKSPACE/operations/hermes_token_governance.runtime.yaml"\n'
insert_ro = needle + (
    '  - "sessions/runtime-activation-sessions/session-init-token-model-tool-channel-governance-policy.md"\n'
)
if needle not in text:
    print("install_runtime_activation_sessions: could not find read_order anchor in", path, file=sys.stderr)
    sys.exit(1)
text = text.replace(needle, insert_ro, 1)

d_needle = (
    '  - "Use delegate_task with hermes_profile when work must run under another isolated profile."\n'
)
d_extra = d_needle + (
    '  - "Phased activation session prompts live under sessions/runtime-activation-sessions/ '
    '(session-1- through session-20-*.md); read the file that matches activation_session above."\n'
)
if d_needle not in text:
    print("install_runtime_activation_sessions: could not find concise_directives anchor in", path, file=sys.stderr)
    sys.exit(1)
text = text.replace(d_needle, d_extra, 1)

path.write_text(text, encoding="utf-8")
print("install_runtime_activation_sessions: patched", path)
PY
  else
    echo "install_runtime_activation_sessions: no ${GOV} — skip governance patch"
  fi
fi
