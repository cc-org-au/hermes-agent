#!/usr/bin/env bash
# Run ON the operator Mac mini as root. Maintains /etc/ssh/sshd_config.d/201-hermes-lan-ssh.conf
# with ListenAddress = current primary IPv4 (en0 then en1). Restarts Hermes sshd only when the
# address changes — safe to run every few minutes (no spurious kickstart).
#
# Used by: operator_mini_add_lan_listenaddress_sshd.sh (manual) and
#           org.hermes.lan-ssh-listen-refresh LaunchDaemon (automatic).
#
# This does NOT replace Tailscale SSH — it adds a same-subnet escape hatch when TS is wedged.
#
set -euo pipefail

if [[ "$(id -u)" != "0" ]]; then
  echo "Run with sudo." >&2
  exit 1
fi

DROP="/etc/ssh/sshd_config.d/201-hermes-lan-ssh.conf"
LAN_IP="${1:-}"

if [[ -z "$LAN_IP" ]]; then
  for _if in en0 en1; do
    LAN_IP="$(ipconfig getifaddr "$_if" 2>/dev/null || true)"
    [[ -n "$LAN_IP" ]] && break
  done
fi

if [[ -z "$LAN_IP" ]]; then
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) no LAN IPv4 on en0/en1 — leave sshd unchanged" >&2
  exit 0
fi

if [[ -f "$DROP" ]] && grep -qE "^ListenAddress[[:space:]]+${LAN_IP//./\\.}([[:space:]]|$)" "$DROP" 2>/dev/null; then
  exit 0
fi

umask 022
{
  echo "# Hermes: LAN fallback (auto-refreshed). Port / AllowUsers / auth: 200-hermes-tailscale-only.conf"
  echo "ListenAddress ${LAN_IP}"
} >"$DROP"
chmod 644 "$DROP"
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) updated $DROP -> ListenAddress ${LAN_IP}" >&2

if ! /usr/sbin/sshd -t; then
  echo "sshd -t failed after writing $DROP" >&2
  exit 1
fi

launchctl kickstart -k system/org.hermes.tailscale.sshd
exit 0
