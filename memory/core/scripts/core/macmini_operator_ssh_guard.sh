#!/usr/bin/env bash
# Hermes — Mac mini SSH hardening with timed rollback (policies/core/security-first-setup.md Step 12A).
#
# Run on the **operator Mac mini** with sudo. Snapshots /etc state, arms a timer that restores the
# snapshot unless you **cancel**. Use while screensharing or with a local console session open.
#
# Network model (already enforced by the apply scripts):
# - SSH listens on **127.0.0.1** and **current Tailscale IPv4** only — not on LAN interfaces.
# - Your **workstation** keeps access when you change Wi‑Fi/Ethernet/hotspot because it uses the
#   **Tailscale overlay** (stable 100.x per machine), not the workstation’s ephemeral LAN IP.
#
# Typical sequence:
#   sudo bash ./macmini_operator_ssh_guard.sh begin 600
#   sudo bash ./macmini_operator_ssh_guard.sh apply
#   # from laptop: ssh -p 52822 operator@<tailscale-ip>
#   sudo bash ./macmini_operator_ssh_guard.sh cancel
#
# If login fails, wait for auto-restore or: sudo bash ./macmini_operator_ssh_guard.sh restore-now
#
set -euo pipefail

ROLLBACK_ROOT="/var/root/hermes-operator-ssh-rollback"
ARMED_PID_FILE="$ROLLBACK_ROOT/armed.pid"
ACTIVE_SNAP_FILE="$ROLLBACK_ROOT/active_snap"
LOG_FILE="/var/log/hermes-operator-ssh-guard.log"

F200="/etc/ssh/sshd_config.d/200-hermes-tailscale-only.conf"
PLIST="/Library/LaunchDaemons/org.hermes.tailscale.sshd.plist"
ANCHOR="/etc/pf.anchors/org.hermes"
PFC="/etc/pf.conf"

SELF="${BASH_SOURCE[0]}"
[[ -f "$SELF" ]] || SELF="$(command -v macmini_operator_ssh_guard.sh 2>/dev/null || true)"
SCRIPT_DIR="$(cd "$(dirname "$SELF")" && pwd)"
SELF_ABS="$SCRIPT_DIR/$(basename "$SELF")"

_log() {
  local msg="[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"
  echo "$msg" | tee -a "$LOG_FILE" >&2
}

_require_root() {
  if [[ "$(id -u)" != "0" ]]; then
    echo "error: run with sudo (this script mutates /etc and LaunchDaemons)." >&2
    exit 1
  fi
}

_snapshot() {
  local snap="$1"
  mkdir -p "$snap"
  if [[ -f "$F200" ]]; then echo yes >"$snap/has_200"; cp -a "$F200" "$snap/200-hermes-tailscale-only.conf"; else echo no >"$snap/has_200"; fi
  if [[ -f "$PLIST" ]]; then echo yes >"$snap/has_plist"; cp -a "$PLIST" "$snap/org.hermes.tailscale.sshd.plist"; else echo no >"$snap/has_plist"; fi
  if [[ -f "$ANCHOR" ]]; then echo yes >"$snap/has_anchor"; cp -a "$ANCHOR" "$snap/org.hermes.anchor"; else echo no >"$snap/has_anchor"; fi
  cp -a "$PFC" "$snap/pf.conf"
  _log "snapshot saved -> $snap"
}

_restore_internal() {
  local snap="${1:?snap dir}"
  _require_root
  mkdir -p "$ROLLBACK_ROOT"
  [[ -d "$snap" ]] || { _log "restore: missing snap $snap"; exit 1; }

  _log "RESTORE starting from $snap"

  launchctl bootout system "$PLIST" 2>/dev/null || true
  sleep 1

  if [[ "$(cat "$snap/has_200")" == yes ]]; then
    cp -a "$snap/200-hermes-tailscale-only.conf" "$F200"
    chmod 644 "$F200"
  else
    rm -f "$F200"
  fi

  if [[ "$(cat "$snap/has_plist")" == yes ]]; then
    cp -a "$snap/org.hermes.tailscale.sshd.plist" "$PLIST"
    chmod 644 "$PLIST"
  else
    rm -f "$PLIST"
  fi

  if [[ "$(cat "$snap/has_anchor")" == yes ]]; then
    cp -a "$snap/org.hermes.anchor" "$ANCHOR"
    chmod 644 "$ANCHOR"
  else
    rm -f "$ANCHOR"
  fi

  cp -a "$snap/pf.conf" "$PFC"
  chmod 644 "$PFC" 2>/dev/null || true

  if /usr/sbin/sshd -t 2>/dev/null; then
    :
  else
    _log "warning: sshd -t failed after restore; check $F200 and main sshd_config"
  fi

  pfctl -f /etc/pf.conf 2>/dev/null || _log "warning: pfctl -f failed"

  if [[ "$(cat "$snap/has_plist")" == yes ]]; then
    plutil -lint "$PLIST" >/dev/null 2>&1 || true
    launchctl bootstrap system "$PLIST" 2>/dev/null || true
    sleep 2
  fi

  launchctl kickstart -k system/com.openssh.sshd 2>/dev/null || _log "warning: kickstart com.openssh.sshd failed"

  rm -f "$ARMED_PID_FILE" "$ACTIVE_SNAP_FILE"
  _log "RESTORE complete"
}

_cmd_begin() {
  _require_root
  local secs="${1:-300}"
  mkdir -p "$ROLLBACK_ROOT"
  touch "$LOG_FILE" 2>/dev/null || true

  if [[ -f "$ARMED_PID_FILE" ]]; then
    local old
    old="$(cat "$ARMED_PID_FILE" 2>/dev/null || true)"
    if [[ -n "$old" ]] && kill -0 "$old" 2>/dev/null; then
      echo "error: rollback already armed (pid $old). Run: sudo $SELF_ABS cancel" >&2
      exit 1
    fi
  fi

  local id="snap-$(date -u +%Y%m%d-%H%M%S)"
  local snap="$ROLLBACK_ROOT/$id"
  _snapshot "$snap"
  echo "$snap" >"$ACTIVE_SNAP_FILE"

  # nohup + disconnected stdin: rollback still runs after non-interactive SSH exits (no SIGHUP kill).
  export HERMES_GUARD_SELF="$SELF_ABS" HERMES_GUARD_SNAP="$snap" HERMES_GUARD_LOG="$LOG_FILE" HERMES_GUARD_SECS="$secs"
  nohup bash -c 'sleep "$HERMES_GUARD_SECS"; exec bash "$HERMES_GUARD_SELF" _restore_internal "$HERMES_GUARD_SNAP" >>"$HERMES_GUARD_LOG" 2>&1' \
    </dev/null >/dev/null 2>&1 &
  local pid=$!
  unset HERMES_GUARD_SELF HERMES_GUARD_SNAP HERMES_GUARD_LOG HERMES_GUARD_SECS
  echo "$pid" >"$ARMED_PID_FILE"
  _log "begin: armed automatic restore in ${secs}s (pid $pid) snap=$snap"
  echo ""
  echo "Timed rollback armed: ${secs}s"
  echo "  Active snapshot: $snap"
  echo "  If SSH still works after your change:  sudo $SELF_ABS cancel"
  echo "  Restore immediately (no wait):        sudo $SELF_ABS restore-now"
  echo "  Then from laptop verify:             ssh -p 52822 operator@<tailscale-ip>"
}

_cmd_cancel() {
  _require_root
  if [[ ! -f "$ARMED_PID_FILE" ]]; then
    echo "no armed rollback (missing $ARMED_PID_FILE)" >&2
    exit 0
  fi
  local pid
  pid="$(cat "$ARMED_PID_FILE")"
  if kill -0 "$pid" 2>/dev/null; then
    kill "$pid" 2>/dev/null || true
    _log "cancel: killed rollback timer pid $pid"
    echo "Cancelled rollback timer (pid $pid)."
  else
    echo "rollback timer (pid $pid) already exited."
  fi
  rm -f "$ARMED_PID_FILE"
  if [[ -f "$ACTIVE_SNAP_FILE" ]]; then
    echo "Snapshot kept at: $(cat "$ACTIVE_SNAP_FILE") (for manual restore-now if needed)"
  fi
}

_cmd_restore_now() {
  _require_root
  local snap=""
  if [[ -f "$ACTIVE_SNAP_FILE" ]]; then
    snap="$(cat "$ACTIVE_SNAP_FILE")"
  fi
  if [[ -z "$snap" || ! -d "$snap" ]]; then
    echo "error: no active snapshot; run begin first" >&2
    exit 1
  fi
  _cmd_cancel 2>/dev/null || true
  rm -f "$ARMED_PID_FILE"
  _restore_internal "$snap"
}

_cmd_apply() {
  _require_root
  if [[ ! -f "$ACTIVE_SNAP_FILE" ]]; then
    echo "error: run begin first (need an active snapshot + armed timer)." >&2
    exit 1
  fi
  local allow="${MACMINI_SSH_ALLOW_USERS:-operator}"
  export MACMINI_TAILSCALE_IP4="${MACMINI_TAILSCALE_IP4:-}"
  if [[ -z "${MACMINI_TAILSCALE_IP4:-}" ]]; then
    if [[ -x /Applications/Tailscale.app/Contents/MacOS/tailscale ]]; then
      MACMINI_TAILSCALE_IP4="$(/Applications/Tailscale.app/Contents/MacOS/tailscale ip -4 2>/dev/null | head -1 | tr -d '[:space:]')"
    elif command -v tailscale >/dev/null 2>&1; then
      MACMINI_TAILSCALE_IP4="$(tailscale ip -4 2>/dev/null | head -1 | tr -d '[:space:]')"
    fi
  fi
  [[ -n "${MACMINI_TAILSCALE_IP4:-}" ]] || {
    echo "error: set MACMINI_TAILSCALE_IP4 or ensure tailscale ip -4 works" >&2
    exit 1
  }
  _log "apply: MACMINI_SSH_ALLOW_USERS=$allow TS=$MACMINI_TAILSCALE_IP4"
  MACMINI_SSH_ALLOW_USERS="$allow" bash "$SCRIPT_DIR/macmini_apply_sshd_tailscale_only.sh" "${MACMINI_SSH_PORT:-52822}"
  bash "$SCRIPT_DIR/macmini_sshd_tailscale_launchd_pf.sh"
  _log "apply: finished"
  echo "Apply complete. Verify SSH, then: sudo $SELF_ABS cancel"
}

_cmd_status() {
  _require_root
  echo "log: $LOG_FILE"
  if [[ -f "$ACTIVE_SNAP_FILE" ]]; then
    echo "active snapshot: $(cat "$ACTIVE_SNAP_FILE")"
  else
    echo "active snapshot: (none)"
  fi
  if [[ -f "$ARMED_PID_FILE" ]]; then
    local pid
    pid="$(cat "$ARMED_PID_FILE")"
    if kill -0 "$pid" 2>/dev/null; then
      echo "armed: yes (pid $pid)"
    else
      echo "armed: stale pid file ($pid not running)"
    fi
  else
    echo "armed: no"
  fi
}

_cmd_help() {
  cat <<EOF
Usage (on Mac mini, from repo scripts/core):
  sudo bash macmini_operator_ssh_guard.sh begin [seconds]   default 300; snapshots /etc + arms timer
  sudo bash macmini_operator_ssh_guard.sh apply             runs Hermes tailscale-only SSH stack
  sudo bash macmini_operator_ssh_guard.sh cancel            disarm timer after successful test
  sudo bash macmini_operator_ssh_guard.sh restore-now       restore snapshot immediately
  sudo bash macmini_operator_ssh_guard.sh status

See policies/core/security-first-setup.md Step 12A and policies/core/firewall-exceptions-workflow.md.
EOF
}

main() {
  local cmd="${1:-help}"
  shift || true
  case "$cmd" in
    begin) _cmd_begin "${1:-300}" ;;
    cancel) _cmd_cancel ;;
    apply) _cmd_apply ;;
    restore-now) _cmd_restore_now ;;
    status) _cmd_status ;;
    _restore_internal) _restore_internal "${1:?}" ;;
    help|-h|--help) _cmd_help ;;
    *)
      echo "unknown command: $cmd" >&2
      _cmd_help
      exit 1
      ;;
  esac
}

main "$@"
