#!/usr/bin/env bash
# Run on the operator Mac mini as user **operator** (not root).
# Appends one line to ~/.ssh/authorized_keys with optional sshd from="CIDR".
#
# Usage:
#   bash append_operator_authorized_key.sh
# Follow prompts: paste pubkey line, then from= value (e.g. 100.109.37.89/32) or empty.
#
set -euo pipefail
AUTH="${HOME}/.ssh/authorized_keys"
mkdir -p "${HOME}/.ssh"
chmod 700 "${HOME}/.ssh"
[[ -f "$AUTH" ]] || touch "$AUTH"
chmod 600 "$AUTH"

echo "Paste the FULL public key line (starts with ssh-ed25519 …), then Enter:"
read -r PUB
echo "Paste from= CIDR only (e.g. 100.109.37.89/32) or Enter for no from= restriction:"
read -r FROM

PUB="${PUB#"${PUB%%[![:space:]]*}"}"
PUB="${PUB%"${PUB##*[![:space:]]}"}"

if [[ ! "$PUB" =~ ^ssh-(ed25519|rsa|ecdsa|sk-ed25519|sk-ecdsa-sha2-nistp256) ]]; then
  echo "Error: line does not look like an OpenSSH public key." >&2
  exit 1
fi

if [[ -n "$FROM" ]]; then
  if [[ "$FROM" =~ [\ \"] ]]; then
    echo "Error: from= value must be a plain CIDR or IP (no spaces/quotes)." >&2
    exit 1
  fi
  LINE="from=\"${FROM}\" ${PUB}"
else
  LINE="$PUB"
fi

printf '%s\n' "$LINE" >>"$AUTH"
chmod 600 "$AUTH"
echo "Appended one line to $AUTH"
echo "Preview (last line):"
tail -1 "$AUTH"
