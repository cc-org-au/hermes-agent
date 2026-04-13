#!/usr/bin/env bash
# Run on the Mac mini with administrative sudo (policies/core/security-first-setup.md Step 12A).
#
# macOS socket-activated sshd ignores Port/ListenAddress in sshd_config. This script:
#   1) Assumes /etc/ssh/sshd_config.d/200-hermes-tailscale-only.conf already pins 52822 + TS IP + key-only
#      (see macmini_apply_sshd_tailscale_only.sh).
#   2) Installs LaunchDaemon org.hermes.tailscale.sshd — /usr/sbin/sshd -D so those binds take effect.
#   3) Installs PF anchor org.hermes to drop inbound TCP 22 (while launchd may still hold the socket).
#
# Idempotent. Use **macmini_operator_ssh_guard.sh** for snapshot + timed rollback around changes.
#
set -euo pipefail

PLIST=/Library/LaunchDaemons/org.hermes.tailscale.sshd.plist
ANCHOR=/etc/pf.anchors/org.hermes

if [[ "$(id -u)" != "0" ]]; then
  echo "error: run with sudo" >&2
  exit 1
fi

umask 022
cat >"$PLIST" <<'PL'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>org.hermes.tailscale.sshd</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/sbin/sshd</string>
    <string>-D</string>
    <string>-f</string>
    <string>/etc/ssh/sshd_config</string>
    <string>-o</string>
    <string>PidFile=/var/run/sshd_hermes.pid</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardErrorPath</key>
  <string>/var/log/hermes-tailscale-sshd.log</string>
  <key>StandardOutPath</key>
  <string>/var/log/hermes-tailscale-sshd.log</string>
</dict>
</plist>
PL
chmod 644 "$PLIST"

cat >"$ANCHOR" <<'AN'
# org.hermes — Screen Sharing (VNC) from tailnet + LAN; block inbound SSH on :22; mgmt SSH 52822.
# Tailscale IPv4: 100.64.0.0/10 (RFC 6598). LAN: operator Screen Sharing at vnc://192.168.1.198/
# (allow clients from 192.168.1.0/24 — change CIDR if your subnet differs). Port 5900 = VNC.
# ARD may use 3283 — add a pass line if needed. Do not use 0.0.0.0/0 for VNC here.
pass in quick inet proto tcp from 100.64.0.0/10 to any port 5900 flags S/SA keep state
pass in quick inet proto tcp from 192.168.1.0/24 to any port 5900 flags S/SA keep state
block drop in quick inet proto tcp to any port 22
block drop in quick inet6 proto tcp to any port 22
AN
chmod 644 "$ANCHOR"

if ! grep -q 'anchor "org.hermes"' /etc/pf.conf; then
  cat >>/etc/pf.conf <<'PC'

# Hermes Mac mini — see /etc/pf.anchors/org.hermes
anchor "org.hermes"
load anchor "org.hermes" from "/etc/pf.anchors/org.hermes"
PC
fi

plutil -lint "$PLIST" >/dev/null
pfctl -vnf "$ANCHOR" >/dev/null
launchctl bootout system "$PLIST" 2>/dev/null || true
launchctl bootstrap system "$PLIST"
sleep 2
pfctl -f /etc/pf.conf
echo "ok: launchd org.hermes.tailscale.sshd + pf reload; verify: ssh -p 52822 user@<tailscale-ip>"
