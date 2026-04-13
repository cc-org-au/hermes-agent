#!/usr/bin/env bash
# shellcheck shell=bash
# Shared helpers: on the VPS, cd to the Hermes checkout and source venv/bin/activate before
# running operator commands. Sourced by ssh_droplet.sh, ssh_droplet_user.sh,
# ssh_droplet_hermesuser_direct.sh — do not run directly.
#
# Workstation ~/.env/.env (optional):
#   HERMES_DROPLET_REPO=/home/hermesuser/hermes-agent   # default if unset
#   HERMES_DROPLET_VENV_USER=hermesuser                 # sudo-user must match for ssh_droplet wrap
#
# Optional: HERMES_REMOTE_VENV_QUIET=1 — skip stderr one-liner that confirms venv activation
# (automation that scrapes remote output).

_droplet_repo() {
  printf '%s' "${HERMES_DROPLET_REPO:-/home/hermesuser/hermes-agent}"
}

_droplet_venv_user_matches() {
  [[ "${1:-}" == "${HERMES_DROPLET_VENV_USER:-hermesuser}" ]]
}

# Shell snippet: cd repo, activate venv if present (trailing space).
# Optional $2 = SSH destination label (user@host:path) embedded in export + stderr banner.
_droplet_remote_venv_prefix() {
  local repo="$1"
  local dst="${2:-}"
  local rq
  rq=$(printf '%q' "$repo")
  if [[ -n "$dst" ]]; then
    printf 'export HERMES_DROPLET_SSH_DST=%q; ' "$dst"
  fi
  # Explicit VIRTUAL_ENV/PATH so child processes and tooling match an activated venv
  # (Hermes runs via ./venv/bin/python; this keeps the shell session consistent after sudo).
  printf 'cd %s 2>/dev/null || true; [ -f %s/venv/bin/activate ] && . %s/venv/bin/activate; ' "$rq" "$rq" "$rq"
  local ve="${repo}/venv"
  printf 'export VIRTUAL_ENV=%q; export PATH="${VIRTUAL_ENV}/bin:${PATH}"; ' "$ve"
  # Purple (venv)(venv) + ssh destination — stderr (see HERMES_REMOTE_VENV_QUIET in header).
  printf '%s' 'if [[ "${HERMES_REMOTE_VENV_QUIET:-0}" != "1" ]]; then command -v python >/dev/null 2>&1 && printf "\033[38;5;141m(venv)\033[0m \033[38;5;141m(venv)\033[0m  ssh %s\n    python=%s\n" "${HERMES_DROPLET_SSH_DST:-}" "$(command -v python)" >&2; fi; '
}

# Prefix a remote bash -lc command body with venv activation.
# Optional $2 = SSH label (user@host:path).
_droplet_wrap_cmd_with_venv() {
  local user_cmd="$1"
  local label="${2:-}"
  local pre
  pre=$(_droplet_remote_venv_prefix "$(_droplet_repo)" "$label")
  printf '%s%s' "$pre" "$user_cmd"
}

# After ~/.env/.env is parsed, SSH_KEY_FILE may be set. Order: that path, then defaults.
droplet_resolve_ssh_key_file() {
  local f
  for f in "${SSH_KEY_FILE:-}" "${HOME}/.env/.ssh_key" "${HOME}/.env/.ssh_droplet_key"; do
    if [[ -n "$f" && -f "$f" ]]; then
      printf '%s' "$f"
      return 0
    fi
  done
  return 1
}
