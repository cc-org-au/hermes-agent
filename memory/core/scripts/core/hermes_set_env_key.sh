#!/usr/bin/env bash
# Set or replace one line in Hermes ~/.env (or profile .env): KEY=value
# Removes every existing line matching ^KEY=, then appends a single new line.
#
# Usage:
#   ./scripts/core/hermes_set_env_key.sh SLACK_BOT_TOKEN 'xoxb-...'
#   ./scripts/core/hermes_set_env_key.sh --profile chief-orchestrator SLACK_BOT_TOKEN 'xoxb-...'
#   ./scripts/core/hermes_set_env_key.sh --file /path/to/.env MY_KEY 'my value'
#   printf '%s' 'secret' | ./scripts/core/hermes_set_env_key.sh MY_KEY
#
set -euo pipefail

PROFILE=""
ENV_TARGET=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile|-p)
      PROFILE="${2:?--profile requires a name}"
      shift 2
      ;;
    --file|-f)
      ENV_TARGET="${2:?--file requires a path}"
      shift 2
      ;;
    -h|--help)
      sed -n '1,12p' "$0" | tail -n +2
      exit 0
      ;;
    -*)
      echo "hermes_set_env_key.sh: unknown option $1 (try --help)" >&2
      exit 1
      ;;
    *)
      break
      ;;
  esac
done

if [[ $# -lt 1 ]]; then
  echo "usage: hermes_set_env_key.sh [options] KEY [VALUE]" >&2
  exit 1
fi

KEY_RAW="$1"
shift

if [[ ! "$KEY_RAW" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
  echo "hermes_set_env_key.sh: invalid KEY (use letters, digits, underscore only)" >&2
  exit 1
fi

if [[ $# -ge 1 ]]; then
  VALUE="$*"
elif [[ ! -t 0 ]]; then
  VALUE="$(cat)"
else
  echo "hermes_set_env_key.sh: missing VALUE (pass as arg or stdin)" >&2
  exit 1
fi

if [[ -n "$ENV_TARGET" ]]; then
  :
elif [[ -n "$PROFILE" ]]; then
  ENV_TARGET="${HOME}/.hermes/profiles/${PROFILE}/.env"
else
  ENV_TARGET="${HOME}/.hermes/.env"
fi

_parent="$(dirname "$ENV_TARGET")"
mkdir -p "$_parent"
touch "$ENV_TARGET"

_tmp="$(mktemp "${TMPDIR:-/tmp}/hermes_set_env.XXXXXX")"
chmod 600 "$_tmp"
trap 'rm -f "$_tmp"' EXIT

grep -v "^${KEY_RAW}=" "$ENV_TARGET" > "$_tmp" || true
printf '%s=%s\n' "$KEY_RAW" "$VALUE" >> "$_tmp"
chmod 600 "$_tmp"
mv "$_tmp" "$ENV_TARGET"
trap - EXIT
echo "hermes_set_env_key.sh: set ${KEY_RAW}=… in $ENV_TARGET" >&2
