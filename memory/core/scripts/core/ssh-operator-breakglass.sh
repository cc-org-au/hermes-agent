#!/usr/bin/env bash
# SSH to operator mini using a break-glass private key (no sshd from= on that pubkey line).
#
# Host/user/port default from the same ~/.env/.env keys as ssh_operator.sh (MACMINI_SSH_*),
# plus optional MACMINI_SSH_LAN_IP for same-LAN fallback when Tailscale is wedged after a
# Wi‑Fi change (Screen Sharing still works via 192.168.x.x but TS SSH times out).
#
# Try order (deduped): when **MACMINI_SSH_LAN_IP** is set and **MACMINI_SSH_TRY_LAN_FIRST** is unset (env + file),
# **LAN first** (same default as **ssh_operator.sh**). Otherwise Tailscale (**MACMINI_SSH_HOST**) then LAN unless
# **MACMINI_SSH_TRY_LAN_FIRST=1** is set explicitly. Set **MACMINI_SSH_TRY_LAN_FIRST=0** in **~/.env/.env** for Tailscale-first.
# With two targets: first hop uses **HERMES_OPERATOR_SSH_PRIMARY_CONNECT_TIMEOUT** (default **8**);
# last hop uses **HERMES_OPERATOR_SSH_CONNECT_TIMEOUT** (default **20** here). **HERMES_OPERATOR_SSH_VERBOSE_TRY=1**
# prints every attempt (default: only fallback).
# On the mini, run once (sudo): memory/core/scripts/core/operator_mini_add_lan_listenaddress_sshd.sh
# so sshd actually listens on that LAN IP (Hermes default is loopback + TS only).
#
# Key resolution (first hit wins):
#   1) OPERATOR_BREAKGLASS_KEY=file
#   2) $PWD / script dir: id_ed25519, operator_breakglass, breakglass_ed25519, .operator_key, operator_key
#   3) $HOME/.env/.breakglass as FILE or dir with those key names
#
# Optional: OPERATOR_BREAKGLASS_USE_TAILSCALE_SSH=1 uses `tailscale ssh` (port 22 on peer
# unless your tailnet maps otherwise).
#
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${HERMES_OPERATOR_ENV:-${HERMES_DROPLET_ENV:-${HOME}/.env/.env}}"

_ef_host=""
_ef_port=""
_ef_user=""
_ef_lan=""
_ef_try_lan_first=""
_try_lan_key_seen_in_file=0
if [[ -f "$ENV_FILE" ]]; then
  while IFS= read -r line || [[ -n "$line" ]]; do
    [[ -z "$line" || "$line" =~ ^[[:space:]]*# ]] && continue
    key="${line%%=*}"
    val="${line#*=}"
    if [[ "$key" == export* ]]; then
      key="${key#export}"
      key="${key##[[:space:]]}"
      key="${key%%[[:space:]]}"
    fi
    if [[ "$val" =~ ^\"(.*)\"$ ]]; then
      val="${BASH_REMATCH[1]}"
    fi
    case "$key" in
      MACMINI_SSH_HOST) _ef_host="${val}" ;;
      SSH_IP_OPERATOR)
        [[ "$val" != *"@"* ]] && _ef_host="${val}"
        ;;
      MACMINI_SSH_PORT) _ef_port="${val}" ;;
      MACMINI_SSH_USER) _ef_user="${val}" ;;
      MACMINI_SSH_LAN_IP) _ef_lan="${val}" ;;
      MACMINI_SSH_TRY_LAN_FIRST)
        _ef_try_lan_first="${val}"
        _try_lan_key_seen_in_file=1
        ;;
    esac
  done <"$ENV_FILE"
fi

HOST="${OPERATOR_TAILSCALE_HOST:-${MACMINI_SSH_HOST:-${_ef_host:-100.67.17.9}}}"
PORT="${OPERATOR_SSH_PORT:-${MACMINI_SSH_PORT:-${_ef_port:-52822}}}"
USER_NAME="${OPERATOR_SSH_USER:-${MACMINI_SSH_USER:-${_ef_user:-operator}}}"
LAN_IP="${MACMINI_SSH_LAN_IP:-${_ef_lan:-}}"

if [[ -n "${LAN_IP}" && "${LAN_IP}" != "${HOST}" && "${_try_lan_key_seen_in_file}" -eq 0 && -z "${MACMINI_SSH_TRY_LAN_FIRST+x}" ]]; then
  MACMINI_SSH_TRY_LAN_FIRST=1
fi

_resolve_breakglass_key() {
  local f
  if [[ -n "${OPERATOR_BREAKGLASS_KEY:-}" && -f "${OPERATOR_BREAKGLASS_KEY}" ]]; then
    echo "${OPERATOR_BREAKGLASS_KEY}"
    return 0
  fi
  for f in \
    "${PWD}/id_ed25519" \
    "${PWD}/operator_breakglass" \
    "${PWD}/breakglass_ed25519" \
    "${PWD}/.operator_key" \
    "${PWD}/operator_key" \
    "${SCRIPT_DIR}/id_ed25519" \
    "${SCRIPT_DIR}/operator_breakglass" \
    "${SCRIPT_DIR}/breakglass_ed25519" \
    "${SCRIPT_DIR}/.operator_key" \
    "${SCRIPT_DIR}/operator_key"; do
    if [[ -f "$f" && ! "$f" =~ \.pub$ ]]; then
      echo "$f"
      return 0
    fi
  done
  local bg="${HOME}/.env/.breakglass"
  if [[ -f "$bg" ]]; then
    echo "$bg"
    return 0
  fi
  if [[ -d "$bg" ]]; then
    for f in "$bg/id_ed25519" "$bg/operator_breakglass" "$bg/breakglass_ed25519" "$bg/.operator_key" "$bg/operator_key"; do
      if [[ -f "$f" ]]; then
        echo "$f"
        return 0
      fi
    done
  fi
  return 1
}

KEY="$(_resolve_breakglass_key || true)"
if [[ -z "$KEY" ]]; then
  echo "No break-glass private key found." >&2
  echo "Set OPERATOR_BREAKGLASS_KEY, put .operator_key or id_ed25519 beside this script (${SCRIPT_DIR}), in \$PWD, or under ~/.env/.breakglass/." >&2
  exit 1
fi

CTO_FINAL="${HERMES_OPERATOR_SSH_CONNECT_TIMEOUT:-20}"
CTO_QUICK="${HERMES_OPERATOR_SSH_PRIMARY_CONNECT_TIMEOUT:-8}"

_breakglass_ssh_opts() {
  local cto="$1"
  _SSH_BASE=(
    -4
    -o BatchMode=no
    -o IdentitiesOnly=yes
    -o IdentityAgent=none
    -o AddKeysToAgent=no
    -o ControlMaster=no
    -o ControlPath=none
    -o StrictHostKeyChecking=accept-new
    -o ConnectTimeout="$cto"
    -o ServerAliveInterval=10
    -o ServerAliveCountMax=6
    -o TCPKeepAlive=yes
    -o PreferredAuthentications=publickey
    -o PubkeyAuthentication=yes
    -i "$KEY"
    -p "$PORT"
  )
  if [[ "$(uname -s)" == "Darwin" ]]; then
    _SSH_BASE+=(-o UseKeychain=no)
  fi
}

if [[ "${OPERATOR_BREAKGLASS_USE_TAILSCALE_SSH:-0}" == "1" ]] && command -v tailscale >/dev/null 2>&1; then
  exec tailscale ssh "${USER_NAME}@${HOST}" "$@"
fi

_candidate_hosts=()
_add_candidate() {
  local cand="$1"
  [[ -z "$cand" ]] && return
  local x
  for x in "${_candidate_hosts[@]:-}"; do
    [[ "$x" == "$cand" ]] && return
  done
  _candidate_hosts+=("$cand")
}

_try_lan_first=0
case "${MACMINI_SSH_TRY_LAN_FIRST:-${_ef_try_lan_first:-0}}" in 1|true|TRUE|True|yes|YES) _try_lan_first=1 ;; esac
if [[ "$_try_lan_first" == "1" ]]; then
  _add_candidate "$LAN_IP"
  _add_candidate "$HOST"
else
  _add_candidate "$HOST"
  _add_candidate "$LAN_IP"
fi

if [[ "${#_candidate_hosts[@]}" -eq 1 ]]; then
  _breakglass_ssh_opts "$CTO_FINAL"
  exec ssh "${_SSH_BASE[@]}" "${USER_NAME}@${_candidate_hosts[0]}" "$@"
fi

last=255
_n="${#_candidate_hosts[@]}"
for ((_i = 0; _i < _n; _i++)); do
  h="${_candidate_hosts[$_i]}"
  if [[ "$_n" -gt 1 && "$_i" -lt $((_n - 1)) ]]; then
    _breakglass_ssh_opts "$CTO_QUICK"
  else
    _breakglass_ssh_opts "$CTO_FINAL"
  fi
  if [[ "$_i" -gt 0 ]]; then
    echo "[ssh-operator-breakglass] fallback: trying ${USER_NAME}@${h} port ${PORT} ..." >&2
  elif [[ "${HERMES_OPERATOR_SSH_VERBOSE_TRY:-0}" == "1" ]]; then
    echo "[ssh-operator-breakglass] trying ${USER_NAME}@${h} port ${PORT} ..." >&2
  fi
  if ssh "${_SSH_BASE[@]}" "${USER_NAME}@${h}" "$@"; then
    exit 0
  fi
  last=$?
done

echo "[ssh-operator-breakglass] all targets failed (last exit ${last})." >&2
echo "  On this Mac: tailscale status; tailscale down && tailscale up" >&2
echo "  On mini (Screen Sharing): sudo bash ~/hermes-agent/memory/core/scripts/core/operator_mini_fix_sshd_incoming_firewall.sh" >&2
echo "  Same Wi‑Fi as mini but TS broken: set MACMINI_SSH_LAN_IP=<mini-LAN-IP> in ${ENV_FILE}" >&2
echo "    On mini (once): sudo bash ~/hermes-agent/memory/core/scripts/core/operator_mini_install_lan_listenaddress_watch.sh" >&2
echo "    (auto-refreshes LAN ListenAddress every 5m; manual add_lan still works.)" >&2
exit "$last"
