#!/usr/bin/env bash
# REM-001 — Restrict SSH management port (e.g. 40227) to Tailscale paths only
# =============================================================================
#
# Problem: sshd on a custom port bound to 0.0.0.0 is reachable from any interface.
# Safer than ListenAddress 127.0.0.1 (which breaks remote admin) is to DROP
# non-Tailscale traffic to that port at the host firewall while leaving sshd
# unchanged.
#
# Prerequisites:
#   - Tailscale installed and interface up (default: tailscale0)
#   - Run as root (sudo) only when applying rules
#   - Keep an active admin session while testing; have rollback ready
#
# Usage:
#   ./scripts/harden_ssh_management_port_tailscale.sh              # dry-run (show rules)
#   sudo REM001_APPLY=1 ./scripts/harden_ssh_management_port_tailscale.sh
#
# Env:
#   REM001_PORT            TCP port (default 40227)
#   REM001_TAILSCALE_IF    Interface name (default tailscale0)
#   REM001_APPLY           Set to 1 to modify iptables (requires root)
#   REM001_SKIP_V6         Set to 1 to skip ip6tables (default apply v6 if present)
#
# Rollback (example — run as root):
#   iptables -D INPUT -p tcp --dport 40227 -s 100.64.0.0/10 -j ACCEPT 2>/dev/null || true
#   iptables -D INPUT -p tcp --dport 40227 -i tailscale0 -j ACCEPT 2>/dev/null || true
#   iptables -D INPUT -p tcp --dport 40227 -j DROP 2>/dev/null || true
#   (repeat for ip6tables if used)
#
# Persistence (Debian/Ubuntu): after verifying SSH over Tailscale still works:
#   sudo apt-get install -y iptables-persistent
#   sudo netfilter-persistent save
#
set -euo pipefail

PORT="${REM001_PORT:-40227}"
TS_IF="${REM001_TAILSCALE_IF:-tailscale0}"
APPLY="${REM001_APPLY:-0}"
SKIP_V6="${REM001_SKIP_V6:-0}"

# Tailscale IPv4 CGNAT carrier-grade space used for mesh IPs
TS_CIDR_V4="100.64.0.0/10"
# Tailscale IPv6 ULA (see https://tailscale.com/kb/1033/ip-and-dns-addresses )
TS_CIDR_V6="fd7a:115c:a1e0::/48"

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "rem-001: missing command: $1" >&2
    exit 1
  }
}

need_cmd iptables

if [[ "$APPLY" != "1" ]]; then
  echo "rem-001: DRY-RUN (set REM001_APPLY=1 as root to apply)"
else
  if [[ "${EUID:-0}" -ne 0 ]]; then
    echo "rem-001: REM001_APPLY=1 requires root (sudo)" >&2
    exit 1
  fi
fi

if ! ip link show "$TS_IF" >/dev/null 2>&1; then
  echo "rem-001: interface '$TS_IF' not found — start Tailscale or set REM001_TAILSCALE_IF" >&2
  exit 1
fi

echo "rem-001: port=$PORT tailscale_if=$TS_IF ts_cidr_v4=$TS_CIDR_V4"

_v4_rules() {
  echo "  iptables -C INPUT -p tcp --dport $PORT -s $TS_CIDR_V4 -j ACCEPT 2>/dev/null \\"
  echo "    || iptables -I INPUT 1 -p tcp --dport $PORT -s $TS_CIDR_V4 -j ACCEPT"
  echo "  iptables -C INPUT -p tcp --dport $PORT -i $TS_IF -j ACCEPT 2>/dev/null \\"
  echo "    || iptables -I INPUT 2 -p tcp --dport $PORT -i $TS_IF -j ACCEPT"
  echo "  iptables -C INPUT -p tcp --dport $PORT -j DROP 2>/dev/null \\"
  echo "    || iptables -A INPUT -p tcp --dport $PORT -j DROP"
}

_v6_rules() {
  if ! command -v ip6tables >/dev/null 2>&1; then
    echo "rem-001: ip6tables not installed; skipping IPv6 (set REM001_SKIP_V6=1 to silence)"
    return 0
  fi
  echo "  ip6tables -C INPUT -p tcp --dport $PORT -s $TS_CIDR_V6 -j ACCEPT 2>/dev/null \\"
  echo "    || ip6tables -I INPUT 1 -p tcp --dport $PORT -s $TS_CIDR_V6 -j ACCEPT"
  echo "  ip6tables -C INPUT -p tcp --dport $PORT -i $TS_IF -j ACCEPT 2>/dev/null \\"
  echo "    || ip6tables -I INPUT 2 -p tcp --dport $PORT -i $TS_IF -j ACCEPT"
  echo "  ip6tables -C INPUT -p tcp --dport $PORT -j DROP 2>/dev/null \\"
  echo "    || ip6tables -A INPUT -p tcp --dport $PORT -j DROP"
}

echo "rem-001: proposed iptables (IPv4):"
_v4_rules

if [[ "$SKIP_V6" != "1" ]]; then
  echo "rem-001: proposed ip6tables (IPv6):"
  _v6_rules
fi

if [[ "$APPLY" != "1" ]]; then
  echo "rem-001: no changes made."
  exit 0
fi

# Apply IPv4 (idempotent: -C checks existence)
if ! iptables -C INPUT -p tcp --dport "$PORT" -s "$TS_CIDR_V4" -j ACCEPT 2>/dev/null; then
  iptables -I INPUT 1 -p tcp --dport "$PORT" -s "$TS_CIDR_V4" -j ACCEPT
  echo "rem-001: inserted ACCEPT $PORT from $TS_CIDR_V4"
fi
if ! iptables -C INPUT -p tcp --dport "$PORT" -i "$TS_IF" -j ACCEPT 2>/dev/null; then
  iptables -I INPUT 2 -p tcp --dport "$PORT" -i "$TS_IF" -j ACCEPT
  echo "rem-001: inserted ACCEPT $PORT on $TS_IF"
fi
if ! iptables -C INPUT -p tcp --dport "$PORT" -j DROP 2>/dev/null; then
  iptables -A INPUT -p tcp --dport "$PORT" -j DROP
  echo "rem-001: appended DROP $PORT (non-Tailscale)"
fi

if [[ "$SKIP_V6" != "1" ]] && command -v ip6tables >/dev/null 2>&1; then
  if ! ip6tables -C INPUT -p tcp --dport "$PORT" -s "$TS_CIDR_V6" -j ACCEPT 2>/dev/null; then
    ip6tables -I INPUT 1 -p tcp --dport "$PORT" -s "$TS_CIDR_V6" -j ACCEPT
    echo "rem-001: ip6tables ACCEPT $PORT from $TS_CIDR_V6"
  fi
  if ! ip6tables -C INPUT -p tcp --dport "$PORT" -i "$TS_IF" -j ACCEPT 2>/dev/null; then
    ip6tables -I INPUT 2 -p tcp --dport "$PORT" -i "$TS_IF" -j ACCEPT
    echo "rem-001: ip6tables ACCEPT $PORT on $TS_IF"
  fi
  if ! ip6tables -C INPUT -p tcp --dport "$PORT" -j DROP 2>/dev/null; then
    ip6tables -A INPUT -p tcp --dport "$PORT" -j DROP
    echo "rem-001: ip6tables DROP $PORT (non-Tailscale)"
  fi
fi

echo "rem-001: applied. Verify a NEW SSH session over Tailscale to port $PORT before closing this shell."
echo "rem-001: persist with: netfilter-persistent save (after apt install iptables-persistent)"
