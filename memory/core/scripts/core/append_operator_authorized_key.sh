#!/usr/bin/env bash
# Run on the operator Mac mini as user **operator** (not root).
# Appends one line to ~/.ssh/authorized_keys with optional sshd from="CIDR".
#
# Usage:
#   bash append_operator_authorized_key.sh
#       Interactive: paste pubkey line, then optionally paste from= CIDR (or press Enter for no restriction).
#   bash append_operator_authorized_key.sh 'ssh-ed25519 AAAA...comment'
#       One argument: append a plain unrestricted pubkey line.
#   bash append_operator_authorized_key.sh 'FULL_LINE'
#       One argument: append the exact single line the collaborator script printed (may already include
#       from="100.x.x.x/32" ssh-ed25519 AAAA...).
#   bash append_operator_authorized_key.sh 'ssh-ed25519 AAAA...comment' '100.109.37.89/32'
#       Two arguments: pubkey line only, then CIDR for optional from= restriction (no quotes in CIDR).
#
set -euo pipefail
AUTH="${HOME}/.ssh/authorized_keys"
mkdir -p "${HOME}/.ssh"
chmod 700 "${HOME}/.ssh"
[[ -f "$AUTH" ]] || touch "$AUTH"
chmod 600 "$AUTH"

_key_type_ok() {
  [[ "$1" =~ ssh-ed25519[[:space:]]+AAAA ]] \
    || [[ "$1" =~ ssh-rsa[[:space:]]+AAA ]] \
    || [[ "$1" =~ ecdsa-sha2-nistp(256|384|521)[[:space:]]+AAAA ]] \
    || [[ "$1" =~ sk-ed25519@openssh\.com[[:space:]]+AAAA ]] \
    || [[ "$1" =~ sk-ecdsa-sha2-nistp256@openssh\.com[[:space:]]+AAAA ]]
}

_append_line() {
  local LINE="$1"
  LINE="${LINE#"${LINE%%[![:space:]]*}"}"
  LINE="${LINE%"${LINE##*[![:space:]]}"}"
  if [[ -z "$LINE" ]]; then
    echo "Error: empty line." >&2
    return 1
  fi
  if [[ "$LINE" =~ ^from= ]]; then
    if ! _key_type_ok "$LINE"; then
      echo "Error: from= line must include a valid OpenSSH public key after the restriction." >&2
      return 1
    fi
  elif ! _key_type_ok "$LINE"; then
    echo "Error: line does not look like an OpenSSH public key (or from=\"…\" key …)." >&2
    return 1
  fi
  printf '%s\n' "$LINE" >>"$AUTH"
  chmod 600 "$AUTH"
  echo "Appended one line to $AUTH"
  echo "Preview (last line):"
  tail -1 "$AUTH"
}

if [[ $# -eq 1 ]]; then
  _append_line "$1"
  exit 0
fi

if [[ $# -eq 2 ]]; then
  PUB="$1"
  FROM="$2"
  PUB="${PUB#"${PUB%%[![:space:]]*}"}"
  PUB="${PUB%"${PUB##*[![:space:]]}"}"
  FROM="${FROM#"${FROM%%[![:space:]]*}"}"
  FROM="${FROM%"${FROM##*[![:space:]]}"}"
  if ! _key_type_ok "$PUB"; then
    echo "Error: first argument does not look like a pubkey line." >&2
    exit 1
  fi
  if [[ -n "$FROM" ]]; then
    if [[ "$FROM" =~ [\ \"] ]]; then
      echo "Error: from= value must be a plain CIDR or IP (no spaces/quotes)." >&2
      exit 1
    fi
    _append_line "from=\"${FROM}\" ${PUB}"
  else
    _append_line "$PUB"
  fi
  exit 0
fi

if [[ $# -gt 2 ]]; then
  echo "Usage: $0 [pubkey-line [from-cidr]]" >&2
  exit 1
fi

echo "Paste the collaborator line (full from=\"…\" ssh-ed25519 … if they sent one line), or pubkey only, then Enter:"
read -r PUB
PUB="${PUB#"${PUB%%[![:space:]]*}"}"
PUB="${PUB%"${PUB##*[![:space:]]}"}"

if [[ "$PUB" =~ ^from= ]]; then
  _append_line "$PUB"
  exit 0
fi

echo "Paste from= CIDR only (e.g. 100.109.37.89/32) or Enter for no from= restriction:"
read -r FROM

if ! _key_type_ok "$PUB"; then
  echo "Error: line does not look like an OpenSSH public key." >&2
  exit 1
fi

FROM="${FROM#"${FROM%%[![:space:]]*}"}"
FROM="${FROM%"${FROM##*[![:space:]]}"}"

if [[ -n "$FROM" ]]; then
  if [[ "$FROM" =~ [\ \"] ]]; then
    echo "Error: from= value must be a plain CIDR or IP (no spaces/quotes)." >&2
    exit 1
  fi
  LINE="from=\"${FROM}\" ${PUB}"
else
  LINE="$PUB"
fi

_append_line "$LINE"
