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
#   - Tailscale installed and interface up (default: tailscale0) for apply/dry-run
#   - Run as root (sudo) for apply, rollback, and arm timer
#   - Keep two SSH sessions open over Tailscale while testing
#
# Usage:
#   ./scripts/harden_ssh_management_port_tailscale.sh                    # dry-run
#   sudo REM001_APPLY=1 ./scripts/harden_ssh_management_port_tailscale.sh  # apply + arm timer
#   sudo ./scripts/harden_ssh_management_port_tailscale.sh rollback        # immediate revert
#
# Timed safety rollback (default 180s after apply):
#   - PID written to /tmp/rem001-arm-rollback.pid
#   - Cancel after a successful NEW Tailscale SSH test:
#       sudo kill "$(cat /tmp/rem001-arm-rollback.pid)" && rm -f /tmp/rem001-arm-rollback.pid
#   - Or wait for timer to remove rules automatically
#
# Env:
#   REM001_PORT                 TCP port (default 40227)
#   REM001_TAILSCALE_IF         Interface (default tailscale0)
#   REM001_APPLY                1 = insert rules (requires root)
#   REM001_ROLLBACK             1 = same as `rollback` argument (requires root)
#   REM001_SKIP_V6              1 = skip ip6tables
#   REM001_ROLLBACK_SECONDS     Auto-rollback delay after apply (default 180; 0 = disable arm)
#   REM001_NO_ARM               1 = apply rules but do not start rollback timer
#
# Persistence (after cancel timer + verification):
#   sudo apt-get install -y iptables-persistent && sudo netfilter-persistent save
#
set -euo pipefail

SCRIPT_SELF="${BASH_SOURCE[0]:-$0}"

PORT="${REM001_PORT:-40227}"
TS_IF="${REM001_TAILSCALE_IF:-tailscale0}"
APPLY="${REM001_APPLY:-0}"
SKIP_V6="${REM001_SKIP_V6:-0}"
ROLLBACK_ENV="${REM001_ROLLBACK:-0}"
ROLLBACK_SECS="${REM001_ROLLBACK_SECONDS:-180}"
NO_ARM="${REM001_NO_ARM:-0}"
ARM_PID_FILE="/tmp/rem001-arm-rollback.pid"

# Tailscale IPv4 CGNAT carrier-grade space used for mesh IPs
TS_CIDR_V4="100.64.0.0/10"
# Tailscale IPv6 ULA
TS_CIDR_V6="fd7a:115c:a1e0::/48"

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "rem-001: missing command: $1" >&2
    exit 1
  }
}

require_root() {
  if [[ "${EUID:-0}" -ne 0 ]]; then
    echo "rem-001: this action requires root (sudo)" >&2
    exit 1
  fi
}

# Remove REM-001 rules (idempotent; ignores missing rules; a few passes clear duplicates)
rem001_rollback_rules() {
  need_cmd iptables
  local _pass
  for _pass in 1 2 3; do
    iptables -D INPUT -p tcp --dport "$PORT" -j DROP 2>/dev/null || true
    iptables -D INPUT -p tcp --dport "$PORT" -i "$TS_IF" -j ACCEPT 2>/dev/null || true
    iptables -D INPUT -p tcp --dport "$PORT" -s "$TS_CIDR_V4" -j ACCEPT 2>/dev/null || true
  done

  if [[ "$SKIP_V6" != "1" ]] && command -v ip6tables >/dev/null 2>&1; then
    for _pass in 1 2 3; do
      ip6tables -D INPUT -p tcp --dport "$PORT" -j DROP 2>/dev/null || true
      ip6tables -D INPUT -p tcp --dport "$PORT" -i "$TS_IF" -j ACCEPT 2>/dev/null || true
      ip6tables -D INPUT -p tcp --dport "$PORT" -s "$TS_CIDR_V6" -j ACCEPT 2>/dev/null || true
    done
  fi
  echo "rem-001: rollback complete (port $PORT)"
}

# ----- rollback-only entry (no Tailscale interface check) -----
if [[ "${1:-}" == "rollback" ]] || [[ "$ROLLBACK_ENV" == "1" ]]; then
  require_root
  rem001_rollback_rules
  rm -f "$ARM_PID_FILE"
  exit 0
fi

need_cmd iptables

if [[ "$APPLY" != "1" ]]; then
  echo "rem-001: DRY-RUN (set REM001_APPLY=1 as root to apply)"
else
  require_root
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
  echo "rem-001: immediate revert (after apply): sudo $SCRIPT_SELF rollback"
  exit 0
fi

# Apply IPv4
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

echo "rem-001: applied. Open a NEW SSH session over Tailscale to port $PORT to verify."

# Timed auto-rollback (background)
if [[ "$NO_ARM" != "1" ]] && [[ "$ROLLBACK_SECS" =~ ^[0-9]+$ ]] && [[ "$ROLLBACK_SECS" -gt 0 ]]; then
  # shellcheck disable=SC2090
  export REM001_PORT="$PORT" REM001_TAILSCALE_IF="$TS_IF" REM001_SKIP_V6="$SKIP_V6"
  (
    sleep "$ROLLBACK_SECS"
    echo "rem-001: auto-rollback after ${ROLLBACK_SECS}s (no disarm)" | logger -t rem001 2>/dev/null || true
    REM001_ROLLBACK=1 REM001_PORT="$PORT" REM001_TAILSCALE_IF="$TS_IF" REM001_SKIP_V6="$SKIP_V6" \
      exec bash "$SCRIPT_SELF" rollback
  ) &
  _arm_pid=$!
  echo "$_arm_pid" >"$ARM_PID_FILE"
  echo "rem-001: armed auto-rollback in ${ROLLBACK_SECS}s — PID ${_arm_pid}"
  echo "rem-001: cancel timer after successful test:"
  echo "         sudo kill ${_arm_pid} && rm -f $ARM_PID_FILE"
else
  echo "rem-001: auto-rollback timer disabled (REM001_ROLLBACK_SECONDS=$ROLLBACK_SECS or REM001_NO_ARM=1)"
fi

echo "rem-001: immediate manual revert (any time as root):"
echo "         sudo bash $SCRIPT_SELF rollback"
echo "rem-001: after canceling timer + verification, persist: netfilter-persistent save"
