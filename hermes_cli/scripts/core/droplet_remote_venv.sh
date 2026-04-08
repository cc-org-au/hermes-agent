#!/usr/bin/env bash
# shellcheck shell=bash
# Shared helpers: on the VPS, cd to the Hermes checkout and source venv/bin/activate before
# running operator commands. Sourced by ssh_droplet.sh, ssh_droplet_user.sh,
# ssh_droplet_hermesuser_direct.sh — do not run directly.
#
# Workstation ~/.env/.env (optional):
#   HERMES_DROPLET_REPO=/home/hermesuser/hermes-agent   # default if unset
#   HERMES_DROPLET_VENV_USER=hermesuser                 # sudo-user must match for ssh_droplet wrap

_droplet_repo() {
  printf '%s' "${HERMES_DROPLET_REPO:-/home/hermesuser/hermes-agent}"
}

_droplet_venv_user_matches() {
  [[ "${1:-}" == "${HERMES_DROPLET_VENV_USER:-hermesuser}" ]]
}

# Shell snippet: cd repo, activate venv if present (trailing space).
_droplet_remote_venv_prefix() {
  local repo="$1"
  local rq
  rq=$(printf '%q' "$repo")
  printf 'cd %s 2>/dev/null || true; [ -f %s/venv/bin/activate ] && . %s/venv/bin/activate; ' "$rq" "$rq" "$rq"
}

# Prefix a remote bash -lc command body with venv activation.
_droplet_wrap_cmd_with_venv() {
  local user_cmd="$1"
  local pre
  pre=$(_droplet_remote_venv_prefix "$(_droplet_repo)")
  printf '%s%s' "$pre" "$user_cmd"
}
