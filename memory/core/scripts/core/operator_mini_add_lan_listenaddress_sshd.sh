#!/usr/bin/env bash
# Run ON the operator Mac mini with sudo when Screen Sharing (LAN) works but SSH to the
# Tailscale IP fails (e.g. laptop Tailscale wedged after Wi‑Fi change). Hermes sshd only
# listens on 127.0.0.1 + Tailscale by default — this adds one extra ListenAddress on your
# LAN IP so key-only SSH on port 52822 works from the same subnet.
#
# Security: same sshd_config (key-only, AllowUsers). Prefer locking Wi‑Fi to trusted LAN;
# optional PF rules can further restrict 52822 to RFC1918 (see macmini_sshd_tailscale_launchd_pf.sh).
#
# Usage:
#   sudo bash operator_mini_add_lan_listenaddress_sshd.sh           # auto: en0 then en1
#   sudo bash operator_mini_add_lan_listenaddress_sshd.sh 192.168.1.61
#
set -euo pipefail

if [[ "$(id -u)" != "0" ]]; then
  echo "Run with sudo." >&2
  exit 1
fi

LAN_IP="${1:-}"
if [[ -z "$LAN_IP" ]]; then
  for _if in en0 en1; do
    LAN_IP="$(ipconfig getifaddr "$_if" 2>/dev/null || true)"
    [[ -n "$LAN_IP" ]] && break
  done
fi

if [[ -z "$LAN_IP" ]]; then
  echo "Could not determine LAN IPv4. Pass it: sudo bash $0 192.168.1.61" >&2
  exit 1
fi

DROP="/etc/ssh/sshd_config.d/201-hermes-lan-ssh.conf"
umask 022
{
  echo "# Hermes: LAN fallback for sshd (Port / AllowUsers / auth come from 200-hermes-tailscale-only.conf)"
  echo "ListenAddress ${LAN_IP}"
} >"$DROP"
chmod 644 "$DROP"
echo "Wrote $DROP (ListenAddress $LAN_IP)"

if ! /usr/sbin/sshd -t; then
  echo "sshd -t failed; remove $DROP if needed." >&2
  exit 1
fi

launchctl kickstart -k system/org.hermes.tailscale.sshd
sleep 2
echo "Restarted org.hermes.tailscale.sshd. Check: sudo lsof -nP -iTCP:52822 -sTCP:LISTEN"
lsof -nP -iTCP:52822 -sTCP:LISTEN 2>/dev/null | grep -E '52822|LISTEN' || true
