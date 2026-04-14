#!/usr/bin/env bash
# Run ON the operator Mac mini (e.g. via Screen Sharing → Terminal) when:
#   tailscale ping <mini-ts-ip> works from your laptop but
#   ssh -p 52822 … times out (TCP never connects).
#
# Typical causes:
#   - /etc/ssh/sshd_config.d/200-hermes-tailscale-only.conf ListenAddress ≠ current `tailscale ip -4`
#   - org.hermes.tailscale.sshd LaunchDaemon not running (sshd not listening on :52822 on TS IP)
#   - macOS Application Firewall blocking inbound sshd on 52822
#
# Usage (on mini — one command per line; do not paste "cd … # comment" as one broken line):
#   cd "$HOME/hermes-agent" && bash memory/core/scripts/core/operator_mini_ssh_tcp_diagnostic.sh
#   (If scripts/core is a symlink to memory/..., scripts/core/... also works.)
#
# If that directory does not exist, find the clone:
#   find "$HOME" -maxdepth 5 -type d -name hermes-agent 2>/dev/null
#
# No git clone at all — download and run (read URL first if you prefer):
#   curl -fsSL https://raw.githubusercontent.com/cc-org-au/hermes-agent/main/memory/core/scripts/core/operator_mini_ssh_tcp_diagnostic.sh | bash
#
set -euo pipefail

echo "=== date ==="
date

echo ""
echo "=== tailscale ip -4 (must match ListenAddress in 200-hermes-tailscale-only.conf) ==="
if [[ -x /Applications/Tailscale.app/Contents/MacOS/tailscale ]]; then
  /Applications/Tailscale.app/Contents/MacOS/tailscale ip -4 2>/dev/null || true
elif command -v tailscale >/dev/null 2>&1; then
  tailscale ip -4 2>/dev/null || true
else
  echo "(tailscale CLI not found)"
fi

echo ""
echo "=== sshd drop-in (Port / ListenAddress) ==="
if [[ -f /etc/ssh/sshd_config.d/200-hermes-tailscale-only.conf ]]; then
  grep -E '^(Port|ListenAddress|AllowUsers)\b' /etc/ssh/sshd_config.d/200-hermes-tailscale-only.conf 2>/dev/null || cat /etc/ssh/sshd_config.d/200-hermes-tailscale-only.conf
else
  echo "MISSING: /etc/ssh/sshd_config.d/200-hermes-tailscale-only.conf (Hermes hardening not applied?)"
fi

echo ""
echo "=== LISTEN sockets on 52822 (need sshd on 127.0.0.1 and Tailscale IP) ==="
echo "    (If empty, re-run entire script as: sudo bash $0)"
if command -v lsof >/dev/null 2>&1; then
  if lsof -nP -iTCP:52822 -sTCP:LISTEN 2>/dev/null | grep -q .; then
    lsof -nP -iTCP:52822 -sTCP:LISTEN
  elif sudo -n true 2>/dev/null; then
    sudo lsof -nP -iTCP:52822 -sTCP:LISTEN 2>/dev/null || echo "(nothing listening on 52822)"
  else
    sudo lsof -nP -iTCP:52822 -sTCP:LISTEN 2>/dev/null || echo "(need sudo password — or nothing is listening)"
  fi
else
  echo "lsof not found"
fi

echo ""
echo "=== LaunchDaemon org.hermes.tailscale.sshd (Hermes sshd -D) ==="
launchctl print system/org.hermes.tailscale.sshd 2>&1 | head -25 || echo "(not loaded — sshd may not bind custom Port/ListenAddress)"

echo ""
echo "=== LaunchDaemon org.hermes.tailscale-ssh-listen-refresh (TS ListenAddress auto-refresh) ==="
launchctl print system/org.hermes.tailscale-ssh-listen-refresh 2>&1 | head -25 || echo "(not loaded — install with operator_mini_install_tailscale_listenaddress_watch.sh)"

echo ""
echo "=== socketfilterfw global (Application Firewall) ==="
FW="/usr/libexec/ApplicationFirewall/socketfilterfw"
"$FW" --getglobalstate 2>/dev/null || true
if [[ -x "$FW" ]]; then
  echo "=== sshd blocked by app firewall? (1 = blocked) ==="
  "$FW" --getappblocked /usr/sbin/sshd 2>/dev/null || true
fi

echo ""
echo "=== FIX HINTS ==="
echo "1) If ListenAddress TS IP ≠ tailscale ip -4: re-run macmini_apply_sshd_tailscale_only.sh (see repo) or edit drop-in to match, then kickstart sshd."
echo "2) If nothing listens on 52822: sudo launchctl bootstrap system /Library/LaunchDaemons/org.hermes.tailscale.sshd.plist"
echo "   If TS IP changes frequently: sudo bash memory/core/scripts/core/operator_mini_install_tailscale_listenaddress_watch.sh"
echo "3) Firewall enabled + TCP timeout from laptop: run (from repo on mini):"
echo "     sudo bash memory/core/scripts/core/operator_mini_fix_sshd_incoming_firewall.sh"
echo "   Or System Settings → Network → Firewall → Options → allow incoming for sshd."
echo "4) After reboot, SSH dead until kickstart: Hermes sshd bound before Tailscale had 100.x."
echo "     Re-apply: sudo bash memory/core/scripts/core/macmini_sshd_tailscale_launchd_pf.sh"
echo "     (installs wait-for-Tailscale wrapper). Then: sudo launchctl kickstart -k system/org.hermes.tailscale.sshd"
