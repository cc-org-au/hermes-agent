#!/usr/bin/env bash
# Operator mini — collaborator SSH helper (macOS/Linux).
# - Generates ~/.ssh/operator_access_<label>_ed25519 and prints the public key directly in the terminal.
# - Default: plain pubkey (no from= restriction) so admin adds it once and it keeps working
#   even if either side changes networks or Tailscale IPs.
# - Optional: --restrict-from-current-tailscale-ip adds from="<your current tailscale ip>/32".
# - Saved SSH target defaults to the known operator mini Tailscale host + port from env/defaults.
#
# macOS: double-click GenerateOperatorAccessKey.command in this folder.
#
# Usage:
#   bash generate_operator_collaborator_key.sh
#       Interactive menu: SSH now, set up authentication, show saved key, exit.
#   bash generate_operator_collaborator_key.sh "Alice"
#       Generate a new key for label Alice (plain pubkey by default).
#   bash generate_operator_collaborator_key.sh --restrict-from-current-tailscale-ip "Alice"
#       Generate a new key restricted to your current Tailscale IP (/32).
#   bash generate_operator_collaborator_key.sh --login
#       SSH into operator using saved config + private key.
#
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HELPER="${SCRIPT_DIR}/operator_access_common.sh"
if [[ -f "$HELPER" ]]; then
  # shellcheck source=/dev/null
  source "$HELPER"
else
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
fi

DEFAULT_HOST="${HERMES_OPERATOR_TAILSCALE_HOST:-100.67.17.9}"
DEFAULT_PORT="${HERMES_OPERATOR_SSH_PORT:-52822}"
DEFAULT_USER="${HERMES_OPERATOR_SSH_USER:-operator}"

_prompt_yn() {
  local msg="$1" r
  read -r -p "$msg [y/N]: " r || true
  r="$(echo "$r" | tr '[:upper:]' '[:lower:]')"
  [[ "$r" == "y" || "$r" == "yes" ]]
}

_build_auth_line() {
  local pub="$1" from_line="${2:-}"
  if [[ -n "$from_line" ]]; then
    printf 'from="%s" %s' "$from_line" "$pub"
  else
    printf '%s' "$pub"
  fi
}

_normalize_source_restriction() {
  local source="$1"
  source="${source#"${source%%[![:space:]]*}"}"
  source="${source%"${source##*[![:space:]]}"}"
  if [[ -z "$source" ]]; then
    printf ''
  elif [[ "$source" == */* ]]; then
    printf '%s' "$source"
  else
    printf '%s/32' "$source"
  fi
}

_resolve_from_line() {
  local mode="$1" ts="$2" entered=""
  case "$mode" in
    no-from)
      printf ''
      ;;
    restrict)
      if [[ -n "$ts" ]]; then
        read -r -p "What is your Tailscale IP [${ts}]: " entered || true
        entered="${entered:-$ts}"
      else
        read -r -p "What is your Tailscale IP? (leave blank for no restriction): " entered || true
      fi
      _normalize_source_restriction "$entered"
      ;;
    *)
      echo "internal error: unknown from-mode '$mode'" >&2
      exit 1
      ;;
  esac
}

_print_key_material() {
  local pub="$1" auth_line="$2"
  echo ""
  echo "==== Your public key ===="
  echo "$pub"
  echo "==== end public key ===="
  echo ""
  if [[ "$auth_line" == "$pub" ]]; then
    echo "Send the public key line above to the admin for operator's authorized_keys."
  else
    echo "==== Send this line to the admin (authorized_keys) ===="
    echo "$auth_line"
    echo "==== end admin line ===="
  fi
  echo ""
}

_print_auth_line_summary() {
  local ts="$1" from_line="$2"
  if [[ -n "$from_line" ]]; then
    echo "This key is restricted to source ${from_line}."
  else
    echo "This key has no from= restriction, so the admin only needs to add it once."
  fi
  echo "Operator host is preset to ${DEFAULT_USER}@${DEFAULT_HOST}:${DEFAULT_PORT}."
  echo "Your current Tailscale IP (if admin asks): ${ts:-'(not detected)'}"
}

_print_login_command() {
  local key="$1" host="${2:-$DEFAULT_HOST}" port="${3:-$DEFAULT_PORT}" user="${4:-$DEFAULT_USER}"
  local qkey qtarget
  qkey="$(printf '%q' "$key")"
  qtarget="$(printf '%q' "${user}@${host}")"
  echo "After the admin adds your key, run this exact SSH command to log into the mini:"
  echo "  ssh -o IdentitiesOnly=yes -o IdentityAgent=none -i ${qkey} -p ${port} ${qtarget}"
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
  if [[ -n "${HERMES_OPERATOR_ACCESS_FROM:-}" ]]; then
    echo "SSH → ${HERMES_OPERATOR_ACCESS_USER}@${HERMES_OPERATOR_ACCESS_HOST}:${HERMES_OPERATOR_ACCESS_PORT} (source IP must match from=${HERMES_OPERATOR_ACCESS_FROM})"
  else
    echo "SSH → ${HERMES_OPERATOR_ACCESS_USER}@${HERMES_OPERATOR_ACCESS_HOST}:${HERMES_OPERATOR_ACCESS_PORT} (no from= restriction on this key)"
  fi
  _print_login_command "$key" "${HERMES_OPERATOR_ACCESS_HOST:-$DEFAULT_HOST}" "${HERMES_OPERATOR_ACCESS_PORT:-$DEFAULT_PORT}" "${HERMES_OPERATOR_ACCESS_USER:-$DEFAULT_USER}"
  _operator_ssh_login "$key" "${HERMES_OPERATOR_ACCESS_HOST:-$DEFAULT_HOST}" "${HERMES_OPERATOR_ACCESS_PORT:-$DEFAULT_PORT}" "${HERMES_OPERATOR_ACCESS_USER:-$DEFAULT_USER}" "$@"
}

_generate_key_material() {
  local safe="$1" from_mode="$2"
  local out pub ts from_line auth_line
  out="$(_operator_key_paths "$safe")"
  mkdir -p "${HOME}/.ssh"
  chmod 700 "${HOME}/.ssh"
  if [[ -f "$out" ]]; then
    echo "Key already exists: $out" >&2
    return 1
  fi

  ssh-keygen -q -t ed25519 -f "$out" -N "" -C "operator-access-${safe}" </dev/null
  chmod 600 "$out"
  pub="$(cat "${out}.pub")"
  ts="$(_operator_ts_ip4)"
  from_line="$(_resolve_from_line "$from_mode" "$ts")"
  auth_line="$(_build_auth_line "$pub" "$from_line")"

  _operator_save_config "$safe" "$DEFAULT_HOST" "$DEFAULT_PORT" "$DEFAULT_USER" "$from_line"

  _print_key_material "$pub" "$auth_line"
  _print_auth_line_summary "$ts" "$from_line"
  if command -v pbcopy >/dev/null 2>&1; then
    printf '%s' "$auth_line" | pbcopy
    echo "(Copied the admin line to clipboard on macOS.)"
  fi
  echo "Private key (never send): $out"
  _print_login_command "$out"
}

_show_saved_key_material() {
  _operator_load_config || {
    echo "No saved config at $HERMES_OP_ACCESS_CONFIG — set up authentication first." >&2
    return 1
  }
  local key pub auth_line
  key="$(_operator_key_paths "$HERMES_OPERATOR_ACCESS_SAFE")"
  if [[ ! -f "${key}.pub" ]]; then
    echo "Missing public key: ${key}.pub" >&2
    return 1
  fi
  pub="$(cat "${key}.pub")"
  auth_line="$(_build_auth_line "$pub" "${HERMES_OPERATOR_ACCESS_FROM:-}")"
  _print_key_material "$pub" "$auth_line"
  _print_auth_line_summary "$(_operator_ts_ip4)" "${HERMES_OPERATOR_ACCESS_FROM:-}"
  if command -v pbcopy >/dev/null 2>&1; then
    printf '%s' "$auth_line" | pbcopy
    echo "(Copied the admin line to clipboard on macOS.)"
  fi
  echo "Private key: $key"
  _print_login_command "$key" "${HERMES_OPERATOR_ACCESS_HOST:-$DEFAULT_HOST}" "${HERMES_OPERATOR_ACCESS_PORT:-$DEFAULT_PORT}" "${HERMES_OPERATOR_ACCESS_USER:-$DEFAULT_USER}"
}

_setup_new_authentication() {
  local from_mode="$1"
  local name safe out
  while :; do
    read -r -p "Label for this key (e.g. your name) [collaborator]: " name || true
    name="${name:-collaborator}"
    safe="$(_operator_safe_label "$name")"
    out="$(_operator_key_paths "$safe")"
    if [[ -f "$out" ]]; then
      echo "A key already exists at $out. Choose another label or use 'SSH into operator' instead." >&2
    else
      break
    fi
  done

  _generate_key_material "$safe" "$from_mode" || exit 1

  if _prompt_yn "Has the admin added that line to operator's authorized_keys?"; then
    if _prompt_yn "Would you like to SSH into operator now?"; then
      _do_login
    fi
  fi
  echo "Later, run:  bash \"$0\" --login"
}

_generate_only() {
  local name="$1" from_mode="$2"
  local safe
  safe="$(_operator_safe_label "$name")"
  _generate_key_material "$safe" "$from_mode"
}

_interactive() {
  local from_mode="$1"
  local saved_key=""
  if _operator_load_config 2>/dev/null; then
    saved_key="$(_operator_key_paths "$HERMES_OPERATOR_ACCESS_SAFE")"
  fi

  echo "Would you like to:"
  echo "  1) SSH into operator"
  echo "  2) Set up authentication to SSH into operator"
  if [[ -n "$saved_key" && -f "$saved_key" ]]; then
    echo "  3) Show your public key / admin line again"
    echo "  4) Exit"
    read -r -p "Choose [1-4]: " choice || true
    case "$choice" in
      1) _do_login ;;
      2) _setup_new_authentication "$from_mode" ;;
      3) _show_saved_key_material ;;
      *) exit 0 ;;
    esac
  else
    echo "  3) Exit"
    read -r -p "Choose [1-3]: " choice || true
    case "$choice" in
      1)
        echo "No saved operator key yet, so we'll set up authentication first."
        _setup_new_authentication "$from_mode"
        ;;
      2) _setup_new_authentication "$from_mode" ;;
      *) exit 0 ;;
    esac
  fi
}

main() {
  local from_mode="no-from"
  local label=""

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --login | -l)
        shift || true
        _do_login "$@"
        return
        ;;
      --no-from | --unrestricted)
        from_mode="no-from"
        shift
        ;;
      --restrict-from-current-tailscale-ip | --restrict)
        from_mode="restrict"
        shift
        ;;
      -h | --help)
        sed -n '1,18p' "$0"
        return
        ;;
      --)
        shift
        break
        ;;
      "")
        shift
        ;;
      *)
        label="$1"
        shift
        break
        ;;
    esac
  done

  if [[ $# -gt 0 ]]; then
    echo "Usage: bash $0 [--no-from|--restrict-from-current-tailscale-ip] [label]" >&2
    echo "   or: bash $0 --login [ssh-args...]" >&2
    exit 1
  fi

  if [[ -n "$label" ]]; then
    _generate_only "$label" "$from_mode"
  else
    _interactive "$from_mode"
  fi
}

main "$@"
