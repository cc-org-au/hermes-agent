#!/usr/bin/env bash
# Run ON the operator Mac mini as root. Ensures /etc/ssh/sshd_config.d/200-hermes-tailscale-only.conf
# tracks the *current* Tailscale IPv4 and reloads Hermes sshd when it changes.
#
# Why: the 200-hermes-tailscale-only.conf file pins a literal ListenAddress <tailscale-ip>. That IP
# can change after network changes / Tailscale restart; sshd then binds the wrong interface, causing
# remote SSH to 100.x:52822 to time out even though Tailscale is up.
#
# Safe to run periodically: only rewrites the conf when the TS IP actually changes.
#
set -euo pipefail

if [[ "$(id -u)" != "0" ]]; then
  echo "Run with sudo." >&2
  exit 1
fi

CONF="/etc/ssh/sshd_config.d/200-hermes-tailscale-only.conf"
HERMES_SSHD_LABEL="system/org.hermes.tailscale.sshd"

_ts_ip4() {
  local ip=""
  if [[ -x /Applications/Tailscale.app/Contents/MacOS/tailscale ]]; then
    ip="$(/Applications/Tailscale.app/Contents/MacOS/tailscale ip -4 2>/dev/null | head -1 | tr -d '[:space:]')"
  elif command -v tailscale >/dev/null 2>&1; then
    ip="$(tailscale ip -4 2>/dev/null | head -1 | tr -d '[:space:]')"
  fi
  printf '%s' "$ip"
}

_existing_ts_listen() {
  [[ -f "$CONF" ]] || return 1
  # Prefer the non-loopback ListenAddress entry (127.0.0.1 is always present).
  awk '
    /^[[:space:]]*ListenAddress[[:space:]]+/ {
      if ($2 != "127.0.0.1") { print $2; exit }
    }
  ' "$CONF" 2>/dev/null || true
}

_reload_hermes_sshd() {
  if ! /usr/sbin/sshd -t; then
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) sshd -t failed — fix config before SSH will listen" >&2
    return 1
  fi
  launchctl kickstart -k "$HERMES_SSHD_LABEL" 2>/dev/null || launchctl kickstart -k system/com.openssh.sshd 2>/dev/null || true
}

TS_IP="$(_ts_ip4)"
if [[ -z "$TS_IP" ]]; then
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) no tailscale ip -4 available (tailscale down?) — leaving ${CONF} unchanged" >&2
  exit 0
fi

existing="$(_existing_ts_listen || true)"
if [[ "$existing" == "$TS_IP" && -n "$existing" ]]; then
  exit 0
fi

if [[ ! -f "$CONF" ]]; then
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) missing ${CONF} — run macmini_apply_sshd_tailscale_only.sh first" >&2
  exit 1
fi

tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT

umask 022
awk -v ts="$TS_IP" '
  BEGIN { replaced=0 }
  /^[[:space:]]*ListenAddress[[:space:]]+/ {
    if ($2 != "127.0.0.1" && replaced==0) {
      print "ListenAddress " ts
      replaced=1
      next
    }
  }
  { print }
  END {
    if (replaced==0) {
      print "ListenAddress " ts
    }
  }
' "$CONF" >"$tmp"

if cmp -s "$tmp" "$CONF"; then
  exit 0
fi

cp -f "$tmp" "$CONF"
chmod 644 "$CONF"
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) updated ${CONF} -> ListenAddress ${TS_IP}" >&2
_reload_hermes_sshd
exit 0

