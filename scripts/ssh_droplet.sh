#!/usr/bin/env bash
# SSH to the droplet using an encrypted private key.
#
# Expects a shell-env file (default: ~/.env/.env) with at least:
#   SSH_PORT, SSH_USER, SSH_TAILSCALE_IP (or SSH_IP)
# and a private key at ~/.env/.ssh_key unless SSH_KEY_FILE is set.
# Optional: SSH_SUDO_PASSWORD (required for --sudo-user when not using workstation `hermes … droplet`;
# see HERMES_DROPLET_WORKSTATION_CLI in this file).
#
# SSH key passphrase — default: entered interactively (or via /dev/tty). ssh-agent and inherited
# SSH_ASKPASS are stripped unless you opt in below.
#
# Opt-in automation (CI / headless): add a line HERMES_DROPLET_ALLOW_ENV_PASSPHRASE=1 to the SAME
# env file as SSH_PASSPHRASE (shell-export alone cannot enable this — avoids accidental bypass).
# The script uses a short-lived SSH_ASKPASS helper (never exports SSH_PASSPHRASE to ssh).
# Non-interactive use without that opt-in fails unless HERMES_DROPLET_INTERACTIVE=1.
#
# Usage:
#   ./scripts/ssh_droplet.sh
#   ./scripts/ssh_droplet.sh 'hostname'
#   ./scripts/ssh_droplet.sh --sudo-user hermesuser 'cd ~/hermes-agent && git pull'
#
# Sudo for workstation `hermes … droplet` (HERMES_DROPLET_WORKSTATION_CLI=1 + --sudo-user):
#   ON  (default): remote runs `sudo -k; sudo -u <runtime> bash -lc …` (password on VPS TTY).
#   OFF: remote runs `bash -lc …` as SSH_USER (no sudo). Use for headless git pull, etc., when
#        SSH_USER is already the account that should own the work, or you accept running as admin.
#   Toggle per invocation:
#     HERMES_DROPLET_REQUIRE_SUDO=0 ./scripts/ssh_droplet.sh 'cd ~/hermes-agent && git pull'
#     AGENT_DROPLET_REQUIRE_SUDO=1 hermes tui droplet   # with repo scripts/ on PATH (see .envrc)
#   Or prefix flags (before --sudo-user / remote command):
#     ./scripts/ssh_droplet.sh --droplet-no-sudo '…'
#     ./scripts/ssh_droplet.sh --droplet-require-sudo --sudo-user hermesuser '…'
#   Optional line in the same env file as SSH_*: HERMES_DROPLET_REQUIRE_SUDO=0 (default for scripts).
#
# Automation (AI / CI): ./scripts/droplet_run.sh 'remote command' — sudo off for that process only;
# `hermes … droplet` still uses sudo on by default (agent-droplet does not inherit parent REQUIRE_SUDO).
#
# Remote side of "<cli> … droplet" (workstation): scripts/hermes → scripts/agent-droplet.
# See policies/core/unified-deployment-and-security.md (Step 15).

set -euo pipefail

_drop_cleanup() {
  [[ -n "${_DROPLET_PASSFILE:-}" && -f "$_DROPLET_PASSFILE" ]] && rm -f "$_DROPLET_PASSFILE"
  [[ -n "${_DROPLET_ASKPASS_SCRIPT:-}" && -f "$_DROPLET_ASKPASS_SCRIPT" ]] && rm -f "$_DROPLET_ASKPASS_SCRIPT"
}
trap _drop_cleanup EXIT

ENV_FILE="${HERMES_DROPLET_ENV:-${HOME}/.env/.env}"
KEY_FILE="${SSH_KEY_FILE:-${HOME}/.env/.ssh_key}"
_DROPLET_KEY_PASS=""
_ALLOW_ENV_PASS_FROM_FILE=0
_RAW_SSH_PASSPHRASE=""

if [[ ! -f "$ENV_FILE" ]]; then
  echo "ssh_droplet.sh: missing env file ${ENV_FILE} (set HERMES_DROPLET_ENV)" >&2
  exit 1
fi
if [[ ! -f "$KEY_FILE" ]]; then
  echo "ssh_droplet.sh: missing key ${KEY_FILE} (set SSH_KEY_FILE)" >&2
  exit 1
fi

while IFS= read -r line || [[ -n "$line" ]]; do
  [[ -z "$line" || "$line" =~ ^[[:space:]]*# ]] && continue
  key="${line%%=*}"
  val="${line#*=}"
  case "$key" in
    SSH_PORT|SSH_USER|SSH_TAILSCALE_IP|SSH_IP|SSH_SUDO_PASSWORD) export "${key}=${val}" ;;
    HERMES_DROPLET_REQUIRE_SUDO)
      # Parent (agent-droplet, droplet_run.sh env, user export) wins over the file.
      [[ -n "${HERMES_DROPLET_REQUIRE_SUDO+x}" ]] || export HERMES_DROPLET_REQUIRE_SUDO="${val}"
      ;;
    HERMES_DROPLET_ALLOW_ENV_PASSPHRASE)
      case "$val" in 1|true|TRUE|True|yes|YES) _ALLOW_ENV_PASS_FROM_FILE=1 ;; esac
      ;;
    SSH_PASSPHRASE) _RAW_SSH_PASSPHRASE="${val}" ;;
  esac
done < "$ENV_FILE"

# Workstation `hermes … droplet` sets this: never use SSH_PASSPHRASE / HERMES_DROPLET_ALLOW_ENV_PASSPHRASE
# from the env file — unlock the SSH key interactively (TTY) instead of SSH_ASKPASS.
if [[ "${HERMES_DROPLET_WORKSTATION_CLI:-}" == "1" ]]; then
  _ALLOW_ENV_PASS_FROM_FILE=0
  _RAW_SSH_PASSPHRASE=""
fi

if [[ "$_ALLOW_ENV_PASS_FROM_FILE" == "1" && -n "${_RAW_SSH_PASSPHRASE}" ]]; then
  _DROPLET_KEY_PASS="${_RAW_SSH_PASSPHRASE}"
fi

HOST="${SSH_TAILSCALE_IP:-${SSH_IP:?}}"

# IdentityAgent=none — disable ssh-agent. UseKeychain=no (macOS only) — do not pull key passphrase
# from the login keychain. AddKeysToAgent=no — never add this key to an agent mid-session.
# Do not set PreferredAuthentications=publickey only: some sshd configs require publickey then
# keyboard-interactive (PAM); restricting to publickey leaves auth stuck at "partial success".
# ControlMaster=no / ControlPath=none — never reuse a ControlPersist socket; otherwise a second
# `ssh` can attach without unlocking the key again (looks like "no passphrase").
# -t allocates a TTY so passphrase prompts work when stdin is not a terminal (IDE).
# -tt: force TTY even if stdin is not a terminal (helps sudo passphrase prompts under IDE wrappers).
REMOTE_BASE=(
  ssh -tt -o BatchMode=no -o IdentitiesOnly=yes -o IdentityAgent=none
  -o AddKeysToAgent=no -o ControlMaster=no -o ControlPath=none
  -o StrictHostKeyChecking=accept-new
  -o ConnectTimeout=20 -o ServerAliveInterval=15 -o ServerAliveCountMax=4
  -i "$KEY_FILE" -p "${SSH_PORT:?}"
  "${SSH_USER:?}@${HOST}"
)
if [[ "$(uname -s)" == "Darwin" ]]; then
  REMOTE_BASE+=(-o UseKeychain=no)
fi
REMOTE=("${REMOTE_BASE[@]}")

# Avoid git/less "Press RETURN" when SSH stdin is not a full TTY (IDE / automation).
_DROPLET_REMOTE_PRE='export GIT_PAGER=cat PAGER=cat LESS=FRX; '

unset SSH_PASSPHRASE 2>/dev/null || true
_DROPLET_ENV=(env -u SSH_AUTH_SOCK -u SSH_AUTH_SOCK_PRIVATE -u SSH_ASKPASS -u SSH_ASKPASS_REQUIRE)

if [[ "$_ALLOW_ENV_PASS_FROM_FILE" == "1" ]]; then
  if [[ -z "${_DROPLET_KEY_PASS}" ]]; then
    echo "ssh_droplet.sh: HERMES_DROPLET_ALLOW_ENV_PASSPHRASE=1 in ${ENV_FILE} but SSH_PASSPHRASE is missing or empty" >&2
    exit 1
  fi
  _DROPLET_PASSFILE=$(mktemp)
  _DROPLET_ASKPASS_SCRIPT=$(mktemp)
  chmod 600 "$_DROPLET_PASSFILE"
  printf '%s' "$_DROPLET_KEY_PASS" > "$_DROPLET_PASSFILE"
  printf '%s\n' '#!/bin/sh' "exec cat '$_DROPLET_PASSFILE'" > "$_DROPLET_ASKPASS_SCRIPT"
  chmod 700 "$_DROPLET_ASKPASS_SCRIPT"
  export SSH_ASKPASS="$_DROPLET_ASKPASS_SCRIPT"
  export SSH_ASKPASS_REQUIRE=force
  export DISPLAY="${DISPLAY:-:0}"
  _DROPLET_ENV=(env -u SSH_AUTH_SOCK -u SSH_AUTH_SOCK_PRIVATE)
fi

# Workstation `hermes … droplet`: never use SSH_ASKPASS (force TTY / pinentry for encrypted keys).
if [[ "${HERMES_DROPLET_WORKSTATION_CLI:-}" == "1" ]]; then
  unset SSH_ASKPASS
  export SSH_ASKPASS_REQUIRE=never
  _DROPLET_ENV=(env -u SSH_AUTH_SOCK -u SSH_AUTH_SOCK_PRIVATE -u SSH_ASKPASS SSH_ASKPASS_REQUIRE=never)
fi

if [[ ! -t 0 && "${HERMES_DROPLET_INTERACTIVE:-}" != "1" && "$_ALLOW_ENV_PASS_FROM_FILE" != "1" ]]; then
  echo "ssh_droplet.sh: droplet SSH requires an interactive terminal (or set HERMES_DROPLET_INTERACTIVE=1 if your client exposes /dev/tty for the key passphrase)." >&2
  exit 1
fi

# Optional leading flags override HERMES_DROPLET_REQUIRE_SUDO for this process only (after env file).
while [[ "${1:-}" == "--droplet-no-sudo" || "${1:-}" == "--droplet-require-sudo" ]]; do
  if [[ "$1" == "--droplet-no-sudo" ]]; then
    export HERMES_DROPLET_REQUIRE_SUDO=0
  else
    export HERMES_DROPLET_REQUIRE_SUDO=1
  fi
  shift
done

_drop_sudo_on() {
  case "${HERMES_DROPLET_REQUIRE_SUDO:-1}" in
    0|false|FALSE|no|NO|off|OFF) return 1 ;;
    *) return 0 ;;
  esac
}

if [[ "${1:-}" == "--sudo-user" ]]; then
  shift
  SUDO_U="${1:?--sudo-user requires a username}"
  shift
  INNER=$(printf '%q' "$*")
  # Workstation `hermes … droplet`: sudo on by default (`sudo -k; sudo -u …`). Turn off with
  # HERMES_DROPLET_REQUIRE_SUDO=0 or --droplet-no-sudo when you need a non-interactive remote step.
  if [[ "${HERMES_DROPLET_WORKSTATION_CLI:-}" == "1" ]]; then
    if _drop_sudo_on; then
      exec "${_DROPLET_ENV[@]}" "${REMOTE[@]}" "${_DROPLET_REMOTE_PRE}sudo -k; sudo -u ${SUDO_U} -H bash -lc ${INNER}"
    fi
    if [[ "${SSH_USER}" != "${SUDO_U}" ]]; then
      echo "ssh_droplet.sh: warning: sudo disabled (HERMES_DROPLET_REQUIRE_SUDO=0) but SSH_USER (${SSH_USER}) != runtime (${SUDO_U}); command runs as ${SSH_USER}" >&2
    fi
    exec "${_DROPLET_ENV[@]}" "${REMOTE[@]}" "${_DROPLET_REMOTE_PRE}bash -lc ${INNER}"
  fi
  # Automation / direct ssh_droplet: skip sudo when already the target account.
  if [[ "${SSH_USER}" == "${SUDO_U}" ]]; then
    exec "${_DROPLET_ENV[@]}" "${REMOTE[@]}" "${_DROPLET_REMOTE_PRE}bash -lc ${INNER}"
  fi
  [[ -n "${SSH_SUDO_PASSWORD:-}" ]] || {
    echo "ssh_droplet.sh: SSH_SUDO_PASSWORD not set in ${ENV_FILE}" >&2
    exit 1
  }
  PW_B64=$(printf '%s' "$SSH_SUDO_PASSWORD" | base64 | tr -d '\n')
  exec "${_DROPLET_ENV[@]}" "${REMOTE[@]}" "${_DROPLET_REMOTE_PRE}printf '%s' '${PW_B64}' | base64 -d | sudo -S -u ${SUDO_U} -H bash -lc ${INNER}"
fi

if [[ $# -eq 0 ]]; then
  exec "${_DROPLET_ENV[@]}" "${REMOTE[@]}"
fi
# One ssh(1) remote argument: run through bash -lc so exports + operators are parsed reliably.
_RIN=$(printf '%q' "$*")
exec "${_DROPLET_ENV[@]}" "${REMOTE[@]}" "${_DROPLET_REMOTE_PRE}bash -lc ${_RIN}"
