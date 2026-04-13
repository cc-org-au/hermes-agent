#!/usr/bin/env bash
# Run ON the operator Mac mini with sudo when:
#   - Hermes org.hermes.tailscale.sshd is running
#   - ListenAddress matches tailscale ip -4
#   - But remote SSH to :52822 times out AND Application Firewall is enabled
#
# Allows /usr/sbin/sshd to accept incoming connections, then restarts Hermes sshd
# so it re-binds after Tailscale is up.
#
# Usage:
#   cd ~/hermes-agent
#   sudo bash memory/core/scripts/core/operator_mini_fix_sshd_incoming_firewall.sh
#
set -euo pipefail

SSHD="/usr/sbin/sshd"
FW="/usr/libexec/ApplicationFirewall/socketfilterfw"

if [[ "$(id -u)" != "0" ]]; then
  echo "Run as root: sudo bash $0" >&2
  exit 1
fi

echo "=== Before: firewall global + sshd blocked? ==="
"$FW" --getglobalstate || true
"$FW" --getappblocked "$SSHD" 2>/dev/null || true

echo ""
echo "=== Register sshd and allow incoming (Application Firewall) ==="
"$FW" --add "$SSHD" 2>/dev/null || true
"$FW" --unblockapp "$SSHD" 2>/dev/null || true

echo "=== After: sshd blocked? (should be no / 0) ==="
"$FW" --getappblocked "$SSHD" 2>/dev/null || true

echo ""
echo "=== Restart Hermes tailscale sshd ==="
launchctl kickstart -k system/org.hermes.tailscale.sshd
sleep 2

echo ""
echo "=== LISTEN on 52822 (need *:52822 or 100.67.x.x:52822 and 127.0.0.1:52822) ==="
lsof -nP -iTCP:52822 -sTCP:LISTEN || {
  echo "Still nothing listening. Tail hermes sshd log:" >&2
  tail -30 /var/log/hermes-tailscale-sshd.log 2>/dev/null || true
  exit 1
}

echo ""
echo "OK. From your laptop: ssh -4 -p 52822 operator@<tailscale-ip>"
echo "If it still times out, check System Settings → Network → Firewall → Options for sshd."
