#!/usr/bin/env bash
# Append lines to Hermes secrets file (~/.hermes/.env or a profile .env).
# Intended for the droplet (run as hermesuser); safe to use on any host.
#
# Usage:
#   ./scripts/core/hermes_append_env.sh 'SLACK_BOT_TOKEN=xoxb-...'
#   ./scripts/core/hermes_append_env.sh --profile chief-orchestrator 'SLACK_BOT_TOKEN=xoxb-...'
#   ./scripts/core/hermes_append_env.sh --file /home/hermesuser/.hermes/.env 'KEY=value'
#   printf '%s\n' 'FOO=bar' | ./scripts/core/hermes_append_env.sh
#
# Options:
#   --profile NAME   Target ~/.hermes/profiles/NAME/.env (overrides default top-level .env)
#   --file PATH      Exact file to append to (overrides --profile and default)
#   --dry-run        Print what would be appended; do not write
#
set -euo pipefail

PROFILE=""
ENV_TARGET=""
DRY_RUN=0

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
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    -h|--help)
      sed -n '1,20p' "$0" | tail -n +2
      exit 0
      ;;
    --)
      shift
      break
      ;;
    -*)
      echo "hermes_append_env.sh: unknown option $1 (try --help)" >&2
      exit 1
      ;;
    *)
      break
      ;;
  esac
done

if [[ -n "$ENV_TARGET" ]]; then
  :
elif [[ -n "$PROFILE" ]]; then
  ENV_TARGET="${HOME}/.hermes/profiles/${PROFILE}/.env"
else
  ENV_TARGET="${HOME}/.hermes/.env"
fi

_ts="$(date -u +'%Y-%m-%dT%H:%M:%SZ')"

_collect_payload() {
  if [[ $# -gt 0 ]]; then
    printf '%s\n' "$@"
  else
    cat
  fi
}

_payload="$(_collect_payload "$@")"
# Drop trailing blank lines for display/dry-run only; we still append a single blank before block
if [[ -z "${_payload//[$'\t\n\r ']/}" ]]; then
  echo "hermes_append_env.sh: nothing to append (pass 'KEY=value' args or stdin)" >&2
  exit 1
fi

_block=$(
  printf '\n# --- hermes_append_env.sh %s ---\n' "$_ts"
  printf '%s\n' "$_payload"
)

if [[ "$DRY_RUN" -eq 1 ]]; then
  printf '%s' "$_block"
  printf '\n[dry-run] target: %s\n' "$ENV_TARGET" >&2
  exit 0
fi

_parent="$(dirname "$ENV_TARGET")"
mkdir -p "$_parent"
touch "$ENV_TARGET"
printf '%s' "$_block" >> "$ENV_TARGET"
chmod 600 "$ENV_TARGET"
echo "hermes_append_env.sh: appended to $ENV_TARGET" >&2
