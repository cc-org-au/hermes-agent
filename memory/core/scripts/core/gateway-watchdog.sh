#!/usr/bin/env bash
# External gateway health supervisor for production VPS / always-on messaging.
#
# This loop invokes Hermes CLI + one lightweight Python call to
# ``gateway.status.dedupe_gateway_processes_for_current_home`` each interval so
# duplicate ``gateway run`` PIDs (token fights / flapping) are cleared **before**
# ``watchdog-check``. Recovery still uses systemctl or ``gateway run --replace`` only —
# no extra pkill/kill beyond that dedupe + systemd.
#
# Recovery prefers the platform service manager: ``launchctl kickstart`` for the
# gateway LaunchAgent on macOS, ``systemctl --user restart`` for
# ``hermes-gateway-*.service`` on Linux, else ``hermes gateway run --replace``.
#
# Environment (all optional; see website/docs/user-guide/messaging/gateway-watchdog.md):
#   HERMES_HOME, HERMES_PROFILE_BASE, HERMES_WATCHDOG_PROFILE, HERMES_AGENT_DIR
#   WATCHDOG_INTERVAL_SECONDS (default 60)
#   WATCHDOG_PREFER_SYSTEMD (default 1)
#   WATCHDOG_SINGLE_INSTANCE_LOCK (default 1) — flock on $HERMES_HOME/gateway-watchdog.lock
#   WATCHDOG_MAX_BACKOFF_SECONDS (default 600), WATCHDOG_JITTER_MAX_SECONDS (default 20)
#   HERMES_GATEWAY_WATCHDOG_ENFORCE_SINGLE — passed through to watchdog-check (default on in Python)
#   WATCHDOG_DEDUPE_EACH_TICK (default 1) — run Python singleton dedupe every loop (before health check)
#   WATCHDOG_REQUIRE_ALL_PLATFORMS — default 1: export HERMES_GATEWAY_WATCHDOG_REQUIRE_ALL_PLATFORMS=1
#     unless that var is already set (strict: every configured platform must be connected). Set 0 for ≥1-connected.

set -euo pipefail

HERMES_AGENT_DIR="${HERMES_AGENT_DIR:-${HERMES_AGENT_REPO:-$HOME/hermes-agent}}"
PY="${HERMES_AGENT_DIR}/venv/bin/python"
if [[ ! -x "$PY" ]]; then
  echo "gateway-watchdog: missing venv python at $PY (set HERMES_AGENT_DIR)" >&2
  exit 1
fi

HERMES_PROFILE_BASE="${HERMES_PROFILE_BASE:-$HOME/.hermes}"
if [[ -z "${HERMES_HOME:-}" ]]; then
  if [[ -n "${HERMES_WATCHDOG_PROFILE:-}" ]]; then
    export HERMES_HOME="${HERMES_PROFILE_BASE}/profiles/${HERMES_WATCHDOG_PROFILE}"
  elif [[ -d "${HERMES_PROFILE_BASE}/profiles/chief-orchestrator" ]]; then
    export HERMES_HOME="${HERMES_PROFILE_BASE}/profiles/chief-orchestrator"
  else
    export HERMES_HOME="${HERMES_PROFILE_BASE}"
  fi
fi
export HERMES_HOME

HERMES_HOME="$(readlink -f "$HERMES_HOME" 2>/dev/null || echo "$HERMES_HOME")"
export HERMES_HOME

# Strict watchdog health: every configured messaging platform must be `connected`, so a
# dropped WhatsApp/Telegram/Slack adapter fails `watchdog-check` and triggers recovery.
# The stock shell watchdog defaults to strict. Set WATCHDOG_REQUIRE_ALL_PLATFORMS=0 for
# the legacy ≥1-connected mode, or set HERMES_GATEWAY_WATCHDOG_REQUIRE_ALL_PLATFORMS
# yourself (this block does not override an already-exported HERMES_* value).
if [[ -z "${HERMES_GATEWAY_WATCHDOG_REQUIRE_ALL_PLATFORMS+x}" ]]; then
  : "${WATCHDOG_REQUIRE_ALL_PLATFORMS:=1}"
  if [[ "$WATCHDOG_REQUIRE_ALL_PLATFORMS" == "1" ]]; then
    export HERMES_GATEWAY_WATCHDOG_REQUIRE_ALL_PLATFORMS=1
  elif [[ "$WATCHDOG_REQUIRE_ALL_PLATFORMS" == "0" ]]; then
    export HERMES_GATEWAY_WATCHDOG_REQUIRE_ALL_PLATFORMS=0
  fi
fi

LOG_DIR="${HERMES_HOME}/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="${LOG_DIR}/gateway-watchdog.log"
touch "$LOG_FILE" 2>/dev/null || true
if [[ -O "$LOG_FILE" ]] 2>/dev/null; then
  chmod 600 "$LOG_FILE" 2>/dev/null || true
fi

LOCK_FILE="${HERMES_HOME}/gateway-watchdog.lock"
WATCHDOG_SINGLE_INSTANCE_LOCK="${WATCHDOG_SINGLE_INSTANCE_LOCK:-1}"
if [[ "$WATCHDOG_SINGLE_INSTANCE_LOCK" != "0" ]]; then
  if command -v flock >/dev/null 2>&1; then
    exec 9>>"$LOCK_FILE"
    if ! flock -n 9; then
      echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) gateway-watchdog: another instance holds $LOCK_FILE — exiting" | tee -a "$LOG_FILE"
      exit 0
    fi
  else
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) gateway-watchdog: warning: flock not found — single-instance lock skipped" | tee -a "$LOG_FILE"
  fi
fi

log() {
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) gateway-watchdog: $*" | tee -a "$LOG_FILE"
}

hermes_cli() {
  HERMES_HOME="$HERMES_HOME" HERMES_PROFILE_BASE="${HERMES_PROFILE_BASE:-$HOME/.hermes}" \
    "$PY" -m hermes_cli.main "$@"
}

# Same logic as the first phase of ``hermes gateway watchdog-check`` — terminate extra
# gateway daemons for this HERMES_HOME (keeps gateway.pid / newest PID).
dedupe_gateway_strays() {
  if [[ "${WATCHDOG_DEDUPE_EACH_TICK:-1}" == "0" ]]; then
    return 0
  fi
  (
    cd "$HERMES_AGENT_DIR" 2>/dev/null || exit 0
    HERMES_HOME="$HERMES_HOME" HERMES_PROFILE_BASE="${HERMES_PROFILE_BASE:-$HOME/.hermes}" \
      "$PY" -c "from gateway.status import dedupe_gateway_processes_for_current_home as _d; _d()" 2>/dev/null || true
  )
}

# Maps current HERMES_HOME to systemd user unit name prefix (hermes-gateway or hermes-gateway-<profile>).
service_unit_name() {
  local def="${HERMES_PROFILE_BASE:-$HOME/.hermes}"
  local def_r home_r profroot
  def_r=$(readlink -f "$def" 2>/dev/null || echo "$def")
  home_r=$(readlink -f "$HERMES_HOME" 2>/dev/null || echo "$HERMES_HOME")
  if [[ "$home_r" == "$def_r" ]]; then
    echo "hermes-gateway"
    return
  fi
  profroot="${def_r}/profiles"
  if [[ "$home_r" == "$profroot"/* ]]; then
    echo "hermes-gateway-${home_r##*/}"
    return
  fi
  echo ""
}

_ensure_systemd_user_bus() {
  local uid
  uid="$(id -u)"
  export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$uid}"
  if [[ -S "${XDG_RUNTIME_DIR}/bus" ]]; then
    export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=${XDG_RUNTIME_DIR}/bus}"
  fi
}

launchd_gateway_label() {
  "$PY" -c "from hermes_cli.gateway import get_launchd_label; print(get_launchd_label())" 2>/dev/null || echo ""
}

try_launchd_gateway_restart() {
  [[ "$(uname -s)" == "Darwin" ]] || return 1
  local label uid plist
  label="$(launchd_gateway_label)"
  [[ -n "$label" ]] || return 1
  plist="${HOME}/Library/LaunchAgents/${label}.plist"
  if [[ ! -f "$plist" ]]; then
    return 1
  fi
  uid="$(id -u)"
  log "recovery: launchctl kickstart gui/${uid}/${label}"
  if ! launchctl kickstart -k "gui/${uid}/${label}" 2>/dev/null; then
    log "recovery: launchctl kickstart failed (exit $?)"
    return 1
  fi
  sleep 5
  return 0
}

try_systemd_restart() {
  local unit base
  base="$(service_unit_name)"
  if [[ -z "$base" ]]; then
    return 1
  fi
  unit="${HOME}/.config/systemd/user/${base}.service"
  if [[ ! -f "$unit" ]]; then
    return 1
  fi
  _ensure_systemd_user_bus
  log "recovery: systemctl --user restart ${base}.service"
  if ! systemctl --user restart "${base}.service"; then
    log "recovery: systemctl restart failed (exit $?)"
    return 1
  fi
  sleep 5
  return 0
}

try_gateway_replace() {
  log "recovery: nohup gateway run --replace (HERMES_HOME=$HERMES_HOME; use when no systemd unit or restart failed)"
  (
    cd "$HERMES_AGENT_DIR" || {
      log "recovery: HERMES_AGENT_DIR missing: $HERMES_AGENT_DIR"
      exit 1
    }
    nohup env HERMES_HOME="$HERMES_HOME" HERMES_PROFILE_BASE="${HERMES_PROFILE_BASE:-$HOME/.hermes}" \
      "$PY" -m hermes_cli.main gateway run --replace >>"${LOG_DIR}/gateway-watchdog-replace.log" 2>&1 &
  )
  sleep 8
}

recover() {
  dedupe_gateway_strays
  if [[ "$(uname -s)" == "Darwin" ]]; then
    if [[ "${WATCHDOG_PREFER_SYSTEMD:-1}" != "0" ]]; then
      if try_launchd_gateway_restart; then
        return 0
      fi
    fi
  elif [[ "${WATCHDOG_PREFER_SYSTEMD:-1}" != "0" ]]; then
    if try_systemd_restart; then
      return 0
    fi
  fi
  try_gateway_replace
}

INTERVAL="${WATCHDOG_INTERVAL_SECONDS:-60}"
MAX_BACKOFF="${WATCHDOG_MAX_BACKOFF_SECONDS:-600}"
JITTER_MAX="${WATCHDOG_JITTER_MAX_SECONDS:-20}"
MAX_ATTEMPTS="${WATCHDOG_MAX_ATTEMPTS_IN_WINDOW:-8}"
WINDOW_SEC="${WATCHDOG_ATTEMPT_WINDOW_SECONDS:-900}"
COOLDOWN="${WATCHDOG_COOLDOWN_SECONDS:-300}"

backoff=60
attempts_in_window=0
window_start="$(date +%s)"

log "starting (HERMES_HOME=$HERMES_HOME HERMES_AGENT_DIR=$HERMES_AGENT_DIR interval=${INTERVAL}s)"

while true; do
  dedupe_gateway_strays
  if chk_out="$(hermes_cli gateway watchdog-check 2>&1)"; then
    log "watchdog-check ok — ${chk_out:-ok}"
    backoff=60
    attempts_in_window=0
    sleep "$INTERVAL"
    continue
  fi

  log "watchdog-check FAILED — ${chk_out:-no detail}"

  now="$(date +%s)"
  if (( now - window_start > WINDOW_SEC )); then
    attempts_in_window=0
    window_start="$now"
  fi
  attempts_in_window=$((attempts_in_window + 1))

  if (( attempts_in_window > MAX_ATTEMPTS )); then
    log "too many recoveries in window — cooldown ${COOLDOWN}s"
    sleep "$COOLDOWN"
    attempts_in_window=0
    window_start="$(date +%s)"
  fi

  recover

  if hermes_cli gateway watchdog-check >/dev/null 2>&1; then
    log "recovered after restart/replace"
    backoff=60
    attempts_in_window=0
    sleep "$INTERVAL"
    continue
  fi

  log "still unhealthy — hermes doctor --fix"
  hermes_cli doctor --fix >>"$LOG_FILE" 2>&1 || true
  sleep 3
  recover

  if ! hermes_cli gateway watchdog-check >/dev/null 2>&1; then
    jitter=$((RANDOM % (JITTER_MAX + 1)))
    sleep_for=$((backoff + jitter))
    if (( sleep_for > MAX_BACKOFF )); then sleep_for=$MAX_BACKOFF; fi
    log "still unhealthy after doctor — backoff ${sleep_for}s (cap ${MAX_BACKOFF}s)"
    sleep "$sleep_for"
    backoff=$((backoff * 2))
    if (( backoff > MAX_BACKOFF )); then backoff=$MAX_BACKOFF; fi
  else
    log "recovered after doctor + restart"
    backoff=60
    attempts_in_window=0
    sleep "$INTERVAL"
  fi
done
