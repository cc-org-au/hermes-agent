#!/usr/bin/env bash
# Operator mini — collaborator SSH helper (macOS/Linux).
# - Generates ~/.ssh/operator_access_<label>_ed25519 and suggests an authorized_keys line
#   using this machine's Tailscale IPv4 /32 in from= (key useless from another tailnet node).
# - Same script: login after admin has added the line (connect via Tailscale IP).
#
# macOS: double-click GenerateOperatorAccessKey.command in this folder.
#
# Usage:
#   bash generate_operator_collaborator_key.sh              # interactive
#   bash generate_operator_collaborator_key.sh "Alice"      # generate only (no prompts)
#   bash generate_operator_collaborator_key.sh --login      # SSH using saved config
#
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "${SCRIPT_DIR}/operator_access_common.sh"

DEFAULT_HOST="${HERMES_OPERATOR_TAILSCALE_HOST:-100.67.17.9}"
DEFAULT_PORT="${HERMES_OPERATOR_SSH_PORT:-52822}"
DEFAULT_USER="${HERMES_OPERATOR_SSH_USER:-operator}"

_prompt_yn() {
  local msg="$1" r
  read -r -p "$msg [y/N]: " r || true
  r="$(echo "$r" | tr '[:upper:]' '[:lower:]')"
  [[ "$r" == "y" || "$r" == "yes" ]]
}

_do_login() {
  _operator_load_config || {
    echo "No saved config at $HERMES_OP_ACCESS_CONFIG — run without --login to generate a key first." >&2
    exit 1
  }
  local key
  key="$(_operator_key_paths "$HERMES_OPERATOR_ACCESS_SAFE")"
  if [[ ! -f "$key" ]]; then
    echo "Missing private key: $key" >&2
    exit 1
  fi
  echo "SSH → ${HERMES_OPERATOR_ACCESS_USER}@${HERMES_OPERATOR_ACCESS_HOST}:${HERMES_OPERATOR_ACCESS_PORT} (Tailscale — required for from= to match)"
  _operator_ssh_login "$key" "${HERMES_OPERATOR_ACCESS_HOST:-$DEFAULT_HOST}" "${HERMES_OPERATOR_ACCESS_PORT:-$DEFAULT_PORT}" "${HERMES_OPERATOR_ACCESS_USER:-$DEFAULT_USER}" "$@"
}

_generate_only() {
  local name="$1"
  local safe host port user ts from_line auth_line out pub
  safe="$(_operator_safe_label "$name")"
  out="$(_operator_key_paths "$safe")"
  mkdir -p "${HOME}/.ssh"
  chmod 700 "${HOME}/.ssh"
  if [[ -f "$out" ]]; then
    echo "Key already exists: $out" >&2
    exit 1
  fi
  read -r -p "Operator mini Tailscale IP or MagicDNS name [${DEFAULT_HOST}]: " host || true
  host="${host:-$DEFAULT_HOST}"
  port="$DEFAULT_PORT"
  user="$DEFAULT_USER"

  ssh-keygen -t ed25519 -f "$out" -N "" -C "operator-access-${safe}" </dev/null
  chmod 600 "$out"
  pub="$(cat "${out}.pub")"

  ts="$(_operator_ts_ip4)"
  if [[ -n "$ts" ]]; then
    from_line="${ts}/32"
    auth_line="from=\"${from_line}\" ${pub}"
    echo ""
    echo "Tailscale detected on this Mac — admin should use this EXACT one-line authorized_keys entry:"
  else
    from_line=""
    auth_line="$pub"
    echo ""
    echo "Tailscale CLI not found or not logged in — no from= hint. Send admin the pubkey line only;"
    echo "admin may set from= to your Tailscale /32 after you run 'tailscale ip -4', or leave unrestricted."
  fi
  echo ""
  echo "---- send to admin (one line) ----"
  echo "$auth_line"
  echo "---- end ----"
  echo ""
  echo "Your Tailscale IP for from= (if admin asks): ${ts:-'(not detected)'}"

  _operator_save_config "$safe" "$host" "$port" "$user" "$from_line"

  if command -v pbcopy >/dev/null 2>&1; then
    printf '%s' "$auth_line" | pbcopy
    echo "(Copied to clipboard on macOS.)"
  fi
  echo "Private key (never send): $out"
}

_interactive() {
  local safe name out host port user ts from_line auth_line pub

  if _operator_load_config 2>/dev/null; then
    out="$(_operator_key_paths "$HERMES_OPERATOR_ACCESS_SAFE")"
    if [[ -f "$out" ]]; then
      echo "Existing operator access key: $out"
      echo "  1) Log in to operator mini now"
      echo "  2) Show pubkey / admin line again"
      echo "  3) Exit"
      read -r -p "Choose [1-3]: " choice || true
      case "$choice" in
        1) _do_login "$@"; return ;;
        2)
          pub="$(cat "${out}.pub")"
          if [[ -n "${HERMES_OPERATOR_ACCESS_FROM:-}" ]]; then
            auth_line="from=\"${HERMES_OPERATOR_ACCESS_FROM}\" ${pub}"
          else
            auth_line="$pub"
          fi
          echo "$auth_line"
          command -v pbcopy >/dev/null 2>&1 && printf '%s' "$auth_line" | pbcopy && echo "(Copied to clipboard.)"
          return
          ;;
        *) exit 0 ;;
      esac
    fi
  fi

  read -r -p "Label for this key (e.g. your name) [collaborator]: " name || true
  name="${name:-collaborator}"
  safe="$(_operator_safe_label "$name")"
  out="$(_operator_key_paths "$safe")"
  if [[ -f "$out" ]]; then
    echo "Key exists at $out — use option 1 to log in or delete the key to regenerate." >&2
    exit 1
  fi

  read -r -p "Operator mini Tailscale IP or hostname [${DEFAULT_HOST}]: " host || true
  host="${host:-$DEFAULT_HOST}"
  port="$DEFAULT_PORT"
  user="$DEFAULT_USER"

  ssh-keygen -t ed25519 -f "$out" -N "" -C "operator-access-${safe}" </dev/null
  chmod 600 "$out"
  pub="$(cat "${out}.pub")"
  ts="$(_operator_ts_ip4)"
  if [[ -n "$ts" ]]; then
    from_line="${ts}/32"
    auth_line="from=\"${from_line}\" ${pub}"
  else
    from_line=""
    auth_line="$pub"
  fi

  _operator_save_config "$safe" "$host" "$port" "$user" "$from_line"

  echo ""
  echo "==== Send this ONE line to the admin (authorized_keys) ===="
  echo "$auth_line"
  echo "==== end ===="
  echo ""
  if [[ -z "$ts" ]]; then
    echo "Note: Install/log in to Tailscale and re-run this script to get a from= line tied to this Mac."
  else
    echo "This line includes from=${ts}/32 so the key only works from this machine on the tailnet."
  fi
  command -v pbcopy >/dev/null 2>&1 && printf '%s' "$auth_line" | pbcopy && echo "(Copied to clipboard.)"

  if _prompt_yn "Have you sent the line above to the admin?"; then
    if _prompt_yn "Has the admin confirmed it was added to authorized_keys?"; then
      if _prompt_yn "Connect now (SSH)?"; then
        echo "Using Tailscale host ${host} — stay on the tailnet."
        _operator_ssh_login "$out" "$host" "$port" "$user" "$@"
        exit $?
      fi
    fi
  fi
  echo "Later, run:  bash \"$0\" --login"
  echo "Private key: $out"
}

main() {
  case "${1:-}" in
    --login | -l)
      shift || true
      _do_login "$@"
      ;;
    -h | --help)
      sed -n '1,20p' "$0"
      ;;
    "")
      _interactive "$@"
      ;;
    *)
      _generate_only "$1"
      ;;
  esac
}

main "$@"
