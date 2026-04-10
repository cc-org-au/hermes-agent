#!/usr/bin/env bash
# Apply on the Mac mini as root (sudo). Aligns with policies/core/security-first-setup.md (Step 12A)
# and unified-deployment-and-security.md (admin-plane: private overlay, key-only, explicit auth methods).
#
# - Binds sshd to loopback + Tailscale IPv4 only (no LAN-wide SSH).
# - Non-default Port (default 52822).
# - AuthenticationMethods publickey; password / kbd-interactive SSH auth off; root SSH off.
# - AllowUsers: set MACMINI_SSH_ALLOW_USERS="user1 user2" before sudo if defaults are wrong.
#
# Prerequisites: Tailscale up; Remote Login enabled; pubkey already in each AllowUsers account.
#
# Usage on mini:
#   sudo MACMINI_SSH_ALLOW_USERS="operator hurizexian20562" ./macmini_apply_sshd_tailscale_only.sh [PORT]
#
# macOS socket-activated sshd ignores Port/ListenAddress; also run **macmini_sshd_tailscale_launchd_pf.sh**
# (as root) so sshd -D binds 52822 and PF drops inbound :22. On-host: /usr/local/share/hermes/mac-mini-ssh-network.txt
#
set -euo pipefail

PORT="${1:-52822}"
TS_IP="${MACMINI_TAILSCALE_IP4:-}"
if [[ -z "$TS_IP" ]]; then
  if [[ -x /Applications/Tailscale.app/Contents/MacOS/tailscale ]]; then
    TS_IP="$(/Applications/Tailscale.app/Contents/MacOS/tailscale ip -4 2>/dev/null | head -1 | tr -d '[:space:]')"
  elif command -v tailscale >/dev/null 2>&1; then
    TS_IP="$(tailscale ip -4 2>/dev/null | head -1 | tr -d '[:space:]')"
  fi
fi
[[ -n "$TS_IP" ]] || {
  echo "error: no Tailscale IPv4; set MACMINI_TAILSCALE_IP4=... or run tailscale up." >&2
  exit 1
}

ALLOW_USERS="${MACMINI_SSH_ALLOW_USERS:-operator hurizexian20562}"
CONF="/etc/ssh/sshd_config.d/200-hermes-tailscale-only.conf"

if [[ "$(id -u)" != "0" ]]; then
  echo "error: run with sudo" >&2
  exit 1
fi

umask 022
cat >"$CONF" <<EOF
# Hermes policy: SSH only on loopback + Tailscale; key-only; explicit AuthenticationMethods.
Port ${PORT}
ListenAddress 127.0.0.1
ListenAddress ${TS_IP}
AuthenticationMethods publickey
PubkeyAuthentication yes
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin no
AllowUsers ${ALLOW_USERS}
EOF
chmod 644 "$CONF"

if ! /usr/sbin/sshd -t; then
  echo "error: sshd -t failed; not restarting." >&2
  exit 1
fi

if launchctl kickstart -k system/com.openssh.sshd 2>/dev/null; then
  echo "sshd reloaded via launchctl kickstart."
else
  echo "warning: kickstart failed; toggle Remote Login in System Settings." >&2
fi

echo "Wrote ${CONF}"
echo "Listen: 127.0.0.1:${PORT} and ${TS_IP}:${PORT} | AllowUsers: ${ALLOW_USERS}"
