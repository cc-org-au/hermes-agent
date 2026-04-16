#!/usr/bin/env bash
# Shared logic for operator SSH collaborator onboarding (sourced by .command / .sh).
# Collaborator keys normally connect to the mini using its Tailscale IP
# (HERMES_OPERATOR_ACCESS_HOST). A generator may optionally store a sshd from="CIDR"
# restriction, but unrestricted pubkeys are also supported for "grant once" access.

HERMES_OP_ACCESS_CONFIG="${HOME}/.ssh/.hermes_operator_access_env"

_operator_ts_ip4() {
  local ip=""
  if [[ -x /Applications/Tailscale.app/Contents/MacOS/tailscale ]]; then
    ip="$(/Applications/Tailscale.app/Contents/MacOS/tailscale ip -4 2>/dev/null | head -1 | tr -d '[:space:]')"
  fi
  if [[ -z "$ip" ]] && command -v tailscale >/dev/null 2>&1; then
    ip="$(tailscale ip -4 2>/dev/null | head -1 | tr -d '[:space:]')"
  fi
  printf '%s' "$ip"
}

_operator_safe_label() {
  local n="${1:-collaborator}"
  echo "${n//[^a-zA-Z0-9._-]/_}"
}

_operator_key_paths() {
  local safe="$1"
  echo "${HOME}/.ssh/operator_access_${safe}_ed25519"
}

_operator_save_config() {
  local safe="$1" host="$2" port="$3" user="$4" from_cidr="$5"
  mkdir -p "${HOME}/.ssh"
  chmod 700 "${HOME}/.ssh"
  umask 077
  {
    echo "HERMES_OPERATOR_ACCESS_SAFE=$safe"
    echo "HERMES_OPERATOR_ACCESS_HOST=$host"
    echo "HERMES_OPERATOR_ACCESS_PORT=$port"
    echo "HERMES_OPERATOR_ACCESS_USER=$user"
    echo "HERMES_OPERATOR_ACCESS_FROM=$from_cidr"
  } >"$HERMES_OP_ACCESS_CONFIG"
  chmod 600 "$HERMES_OP_ACCESS_CONFIG"
}

_operator_load_config() {
  [[ -f "$HERMES_OP_ACCESS_CONFIG" ]] || return 1
  # shellcheck source=/dev/null
  source "$HERMES_OP_ACCESS_CONFIG"
}

_operator_ssh_login() {
  local key="$1" host="${2:-100.67.17.9}" port="${3:-52822}" user="${4:-operator}"
  shift 4 || true
  exec ssh -o IdentitiesOnly=yes -o IdentityAgent=none -i "$key" -p "$port" "$user@$host" "$@"
}
