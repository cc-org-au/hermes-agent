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
LIBEXEC=/usr/local/libexec/hermes
WRAPPER="${LIBEXEC}/hermes_sshd_wait_tailscale_exec.sh"

if [[ "$(id -u)" != "0" ]]; then
  echo "error: run with sudo" >&2
  exit 1
fi

umask 022
install -d -m 755 "$LIBEXEC"
cat >"$WRAPPER" <<'WRAP'
#!/usr/bin/env bash
# LaunchDaemon helper: sshd's ListenAddress includes the Tailscale IPv4. At cold boot,
# org.hermes.tailscale.sshd often starts before Tailscale assigns 100.x, so bind fails and
# remote SSH times out until a manual kickstart. Wait for tailscale ip -4, then exec sshd.
set -uo pipefail
LOG=/var/log/hermes-tailscale-sshd.log
MAX_WAIT_SEC=120
STEP=2
elapsed=0
while [[ "$elapsed" -lt "$MAX_WAIT_SEC" ]]; do
  TS=""
  if [[ -x /Applications/Tailscale.app/Contents/MacOS/tailscale ]]; then
    TS="$(/Applications/Tailscale.app/Contents/MacOS/tailscale ip -4 2>/dev/null | head -1 | tr -d '[:space:]')" || TS=""
  elif command -v tailscale >/dev/null 2>&1; then
    TS="$(tailscale ip -4 2>/dev/null | head -1 | tr -d '[:space:]')" || TS=""
  fi
  if [[ -n "$TS" ]]; then
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) hermes_sshd_wait: tailscale IPv4 ready (${TS}), starting sshd" >>"$LOG"
    exec /usr/sbin/sshd -D -f /etc/ssh/sshd_config -o PidFile=/var/run/sshd_hermes.pid
  fi
  sleep "$STEP"
  elapsed=$((elapsed + STEP))
done
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) hermes_sshd_wait: timeout after ${MAX_WAIT_SEC}s; starting sshd anyway (Tailscale may still be down)" >>"$LOG"
exec /usr/sbin/sshd -D -f /etc/ssh/sshd_config -o PidFile=/var/run/sshd_hermes.pid
WRAP
chmod 755 "$WRAPPER"

cat >"$PLIST" <<'PL'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>org.hermes.tailscale.sshd</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/local/libexec/hermes/hermes_sshd_wait_tailscale_exec.sh</string>
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
# org.hermes — block inbound SSH on port 22; management SSH uses 52822 (Tailscale + loopback).
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
echo "ok: ${WRAPPER} + launchd org.hermes.tailscale.sshd + pf reload; verify: ssh -p 52822 user@<tailscale-ip>"
