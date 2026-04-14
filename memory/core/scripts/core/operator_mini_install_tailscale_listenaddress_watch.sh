#!/usr/bin/env bash
# Install a system LaunchDaemon on the operator mini that every 60 seconds (and at boot)
# refreshes the Tailscale ListenAddress for Hermes sshd :52822 when the mini's 100.x changes.
#
# Usage (on mini, from repo, with sudo):
#   cd ~/hermes-agent
#   sudo bash memory/core/scripts/core/operator_mini_install_tailscale_listenaddress_watch.sh
#
set -euo pipefail

if [[ "$(id -u)" != "0" ]]; then
  echo "Run with sudo." >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIBEXEC="/usr/local/libexec/hermes"
PLIST_SRC="${SCRIPT_DIR}/org.hermes.tailscale-ssh-listen-refresh.plist"
PLIST_DST="/Library/LaunchDaemons/org.hermes.tailscale-ssh-listen-refresh.plist"

install -d -m 755 "$LIBEXEC"
install -m 755 "${SCRIPT_DIR}/operator_mini_refresh_tailscale_listenaddress.sh" "${LIBEXEC}/"
cp -f "$PLIST_SRC" "$PLIST_DST"
chmod 644 "$PLIST_DST"
plutil -lint "$PLIST_DST" >/dev/null

launchctl bootout system "$PLIST_DST" 2>/dev/null || true
launchctl bootstrap system "$PLIST_DST"
launchctl enable system/org.hermes.tailscale-ssh-listen-refresh
launchctl kickstart -k system/org.hermes.tailscale-ssh-listen-refresh

echo "Installed ${PLIST_DST} + ${LIBEXEC}/operator_mini_refresh_tailscale_listenaddress.sh"
echo "Interval: 60s (reinstall this script after pulling repo to refresh the plist if it changed)."
echo "Logs: /var/log/hermes-tailscale-ssh-refresh.log"
echo "Uninstall: sudo launchctl bootout system $PLIST_DST && sudo rm -f $PLIST_DST ${LIBEXEC}/operator_mini_refresh_tailscale_listenaddress.sh"

