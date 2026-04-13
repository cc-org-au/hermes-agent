#!/usr/bin/env bash
# Install a system LaunchDaemon on the operator mini that every 5 minutes (and at boot)
# refreshes the LAN ListenAddress for Hermes sshd :52822 when en0/en1 DHCP changes.
#
# You still need Tailscale or LAN reachability for *initial* setup (Screen Sharing, or first SSH).
# After this is installed, you do NOT need to re-run the LAN script manually when the mini’s
# LAN IP changes on the *same* network.
#
# What this does NOT fix: laptop and mini on different networks with Tailscale down everywhere —
# that requires physical access (crash cart), someone on-site, or fixing Tailscale from a device
# that can still reach the mini.
#
# Usage (on mini, from repo, with sudo):
#   cd ~/hermes-agent
#   sudo bash memory/core/scripts/core/operator_mini_install_lan_listenaddress_watch.sh
#
set -euo pipefail

if [[ "$(id -u)" != "0" ]]; then
  echo "Run with sudo." >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIBEXEC="/usr/local/libexec/hermes"
PLIST_SRC="${SCRIPT_DIR}/org.hermes.lan-ssh-listen-refresh.plist"
PLIST_DST="/Library/LaunchDaemons/org.hermes.lan-ssh-listen-refresh.plist"

install -d -m 755 "$LIBEXEC"
install -m 755 "${SCRIPT_DIR}/operator_mini_refresh_lan_listenaddress.sh" "${LIBEXEC}/"
cp -f "$PLIST_SRC" "$PLIST_DST"
chmod 644 "$PLIST_DST"
plutil -lint "$PLIST_DST" >/dev/null

launchctl bootout system "$PLIST_DST" 2>/dev/null || true
launchctl bootstrap system "$PLIST_DST"
launchctl enable system/org.hermes.lan-ssh-listen-refresh
launchctl kickstart -k system/org.hermes.lan-ssh-listen-refresh

echo "Installed ${PLIST_DST} + ${LIBEXEC}/operator_mini_refresh_lan_listenaddress.sh"
echo "Logs: /var/log/hermes-lan-ssh-refresh.log"
echo "Uninstall: sudo launchctl bootout system $PLIST_DST && sudo rm -f $PLIST_DST ${LIBEXEC}/operator_mini_refresh_lan_listenaddress.sh"
