#!/usr/bin/env bash
# One-shot on the operator Mac mini (sudo): install the Hermes **LAN SSH listen refresh** daemon.
#
# After **macmini_apply_sshd_tailscale_only.sh**, sshd binds **only** loopback + Tailscale unless
# /etc/ssh/sshd_config.d/201-hermes-lan-ssh.conf lists the current LAN IP. DHCP / Wi‑Fi changes
# can stale that file and break LAN SSH until this job runs.
#
# Security (does not “open up” sshd):
#   - Still **one explicit ListenAddress** per refresh (your current en* IPv4), not 0.0.0.0.
#   - Port / AllowUsers / **publickey-only** stay in **200-hermes-tailscale-only.conf**.
#   - If there is no LAN, the drop-in is **removed** so Tailscale + loopback keep working.
#
# Pair with **stable DHCP reservation** for the mini on your home router so the LAN IP rarely
# changes; Tailscale remains the path when your laptop is off-LAN (hotspot).
#
# Usage:
#   cd ~/hermes-agent
#   sudo bash memory/core/scripts/core/operator_mini_install_ssh_lan_resilience.sh
#
set -euo pipefail

if [[ "$(id -u)" != "0" ]]; then
  echo "Run with sudo." >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec bash "${SCRIPT_DIR}/operator_mini_install_lan_listenaddress_watch.sh"
