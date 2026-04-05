#!/usr/bin/env bash
#
# Gateway + messaging watchdog (optional external supervisor)
# ============================================================
#
# Purpose
# -------
# Keep the Hermes messaging gateway and at least one platform adapter connected.
# The check uses `hermes gateway watchdog-check`, which verifies:
#
#   1. Gateway process uptime — a valid `gateway.pid` points to a live Hermes
#      gateway process (detects crashes with stale `gateway_state.json`).
#   2. Runtime state — `gateway_state.json` has `gateway_state=running`.
#   3. Messaging channel uptime — at least one row under `platforms` has
#      `state=connected` (e.g. Slack/Telegram up while WhatsApp reconnects).
#
# Intentionally, this does *not* require every platform to be connected, so
# one flaky bridge does not force restarts that tear down healthy adapters.
#
# Recovery loop
# -------------
# When unhealthy:
#   1. Backoff (exponential, capped) + jitter.
#   2. Prefer `systemctl --user restart hermes-gateway-<profile>.service` when
#      the unit exists (aligned with `hermes gateway install` for that profile).
#   3. Else: `venv/bin/python -m hermes_cli.main … gateway run --replace` in the
#      background (legacy / no systemd).
#   4. If still unhealthy: `hermes doctor --fix` (logs to gateway-watchdog.log),
#      then restart again (systemd or replace).
#   5. Rate-limit: after too many attempts in a window, cooldown before retrying.
#
# Environment (optional)
# ----------------------
#   HERMES_HOME                    — explicit profile/instance directory (highest priority)
#   HERMES_PROFILE_BASE            — default ~/.hermes; used with HERMES_WATCHDOG_PROFILE
#   HERMES_WATCHDOG_PROFILE        — named profile under profiles/<name> (optional)
#   HERMES_AGENT_DIR               — repo root with venv (default ~/hermes-agent)
#   WATCHDOG_PREFER_SYSTEMD        — 1 = try systemctl --user restart first (default 1)
#   WATCHDOG_INTERVAL_SECONDS      — healthy poll interval (default 60)
#   WATCHDOG_MAX_BACKOFF_SECONDS    — max delay between recovery tries (default 600)
#   WATCHDOG_JITTER_MAX_SECONDS    — random extra delay 0..N (default 20)
#   WATCHDOG_ATTEMPT_WINDOW_SECONDS — rolling window for attempt cap (default 1800)
#   WATCHDOG_MAX_ATTEMPTS_IN_WINDOW — max recovery tries per window (default 4)
#   WATCHDOG_COOLDOWN_SECONDS      — sleep after hitting attempt cap (default 900)
#   WATCHDOG_RESTART_WAIT_SECONDS  — wait after restart before re-check (default 20)
#   WATCHDOG_POST_DOCTOR_WAIT_SECONDS — wait after doctor+restart (default 25)
#
# Profile resolution (when HERMES_HOME is unset)
# ----------------------------------------------
#   1. If HERMES_WATCHDOG_PROFILE is set → HERMES_HOME=$HERMES_PROFILE_BASE/profiles/<name>
#   2. Else if $HERMES_PROFILE_BASE/profiles/chief-orchestrator exists → use it (VPS / orchestrator)
#   3. Else → HERMES_HOME=$HERMES_PROFILE_BASE
#
# Install
# -------
# Copy to ~/.hermes/bin/gateway-watchdog.sh, chmod +x, run under systemd,
# tmux, or cron with the same user/env as the gateway (HERMES_HOME + venv).
#
# Docs: website/docs/user-guide/messaging/gateway-watchdog.md

set -euo pipefail

_PROFILE_BASE="${HERMES_PROFILE_BASE:-$HOME/.hermes}"
_PROFILES_ROOT="${_PROFILE_BASE}/profiles"

if [[ -n "${HERMES_HOME:-}" ]]; then
  :
elif [[ -n "${HERMES_WATCHDOG_PROFILE:-}" ]]; then
  HERMES_HOME="${_PROFILE_BASE}/profiles/${HERMES_WATCHDOG_PROFILE}"
elif [[ -d "${_PROFILE_BASE}/profiles/chief-orchestrator" ]]; then
  HERMES_HOME="${_PROFILE_BASE}/profiles/chief-orchestrator"
else
  HERMES_HOME="$_PROFILE_BASE"
fi
export HERMES_HOME

AGENT_DIR="${HERMES_AGENT_DIR:-$HOME/hermes-agent}"
PY="${AGENT_DIR}/venv/bin/python"
if [[ ! -x "$PY" ]]; then
  echo "gateway-watchdog: missing venv python at ${PY} (set HERMES_AGENT_DIR)" >&2
  exit 1
fi

# -p <name> when HERMES_HOME is under profiles/<name> (matches agent-droplet / gateway install)
HERMES_CLI=( "$PY" -m hermes_cli.main )
if [[ "$HERMES_HOME" == "${_PROFILES_ROOT}/"* ]]; then
  _WATCHDOG_PN="${HERMES_HOME#"${_PROFILES_ROOT}/"}"
  _WATCHDOG_PN="${_WATCHDOG_PN%%/*}"
  if [[ -n "$_WATCHDOG_PN" ]]; then
    HERMES_CLI+=( -p "$_WATCHDOG_PN" )
  fi
fi

hermes_gateway_service_name() {
  if [[ "$HERMES_HOME" == "$_PROFILE_BASE" ]]; then
    echo "hermes-gateway"
    return 0
  fi
  if [[ "$HERMES_HOME" == "${_PROFILES_ROOT}/"* ]]; then
    local name="${HERMES_HOME#"${_PROFILES_ROOT}/"}"
    name="${name%%/*}"
    if [[ -n "$name" ]]; then
      echo "hermes-gateway-${name}"
      return 0
    fi
  fi
  echo ""
}

LOG_DIR="$HERMES_HOME/logs"
LOG_FILE="$LOG_DIR/gateway-watchdog.log"
STATE_FILE="$HERMES_HOME/gateway_state.json"

CHECK_INTERVAL="${WATCHDOG_INTERVAL_SECONDS:-60}"
MAX_BACKOFF="${WATCHDOG_MAX_BACKOFF_SECONDS:-600}"
JITTER_MAX="${WATCHDOG_JITTER_MAX_SECONDS:-20}"
ATTEMPT_WINDOW="${WATCHDOG_ATTEMPT_WINDOW_SECONDS:-1800}"
MAX_ATTEMPTS="${WATCHDOG_MAX_ATTEMPTS_IN_WINDOW:-4}"
COOLDOWN_SECONDS="${WATCHDOG_COOLDOWN_SECONDS:-900}"
RESTART_WAIT="${WATCHDOG_RESTART_WAIT_SECONDS:-20}"
POST_DOCTOR_WAIT="${WATCHDOG_POST_DOCTOR_WAIT_SECONDS:-25}"
PREFER_SYSTEMD="${WATCHDOG_PREFER_SYSTEMD:-1}"

mkdir -p "$LOG_DIR"
# Tighten log perms when possible (REM-005 / audit); ignore if not owner.
touch "$LOG_FILE" 2>/dev/null || true
chmod 600 "$LOG_FILE" 2>/dev/null || true
declare -a ATTEMPTS=()

log() {
  printf '%s [watchdog] %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$*" >> "$LOG_FILE"
}

now_epoch() {
  date +%s
}

rand_between_zero_and() {
  local max="$1"
  if (( max <= 0 )); then
    echo 0
  else
    echo $((RANDOM % (max + 1)))
  fi
}

prune_attempts() {
  local now cutoff
  now=$(now_epoch)
  cutoff=$((now - ATTEMPT_WINDOW))
  local kept=()
  local ts
  for ts in "${ATTEMPTS[@]:-}"; do
    if (( ts >= cutoff )); then
      kept+=("$ts")
    fi
  done
  ATTEMPTS=("${kept[@]:-}")
}

attempt_count() {
  prune_attempts
  echo "${#ATTEMPTS[@]}"
}

record_attempt() {
  ATTEMPTS+=("$(now_epoch)")
}

check_health() {
  local out
  if out=$(cd "$AGENT_DIR" && HERMES_HOME="$HERMES_HOME" "${HERMES_CLI[@]}" gateway watchdog-check 2>&1); then
    HEALTH_REASON="$out"
    return 0
  fi
  HEALTH_REASON="$out"
  return 1
}

compute_backoff_delay() {
  local attempts delay i jitter
  attempts=$(attempt_count)
  delay="$CHECK_INTERVAL"
  i=1
  while (( i < attempts )); do
    delay=$((delay * 2))
    if (( delay >= MAX_BACKOFF )); then
      delay="$MAX_BACKOFF"
      break
    fi
    i=$((i + 1))
  done
  jitter=$(rand_between_zero_and "$JITTER_MAX")
  echo $((delay + jitter))
}

restart_gateway() {
  local svc unit
  svc="$(hermes_gateway_service_name)"
  unit="${HOME}/.config/systemd/user/${svc}.service"

  if [[ "$PREFER_SYSTEMD" == "1" ]] && [[ -n "$svc" ]] && [[ -f "$unit" ]] && command -v systemctl >/dev/null 2>&1; then
    # Match hermes_cli.gateway._ensure_user_systemd_env — XDG alone is not always enough;
    # without DBUS_SESSION_BUS_ADDRESS, systemctl --user can fail with "No medium found".
    export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
    if [[ -z "${DBUS_SESSION_BUS_ADDRESS:-}" && -S "${XDG_RUNTIME_DIR}/bus" ]]; then
      export DBUS_SESSION_BUS_ADDRESS="unix:path=${XDG_RUNTIME_DIR}/bus"
    fi
    if systemctl --user restart "${svc}.service" >>"$LOG_FILE" 2>&1; then
      log "recovery: systemctl --user restart ${svc}.service"
      return 0
    fi
    log "recovery: systemctl restart failed, falling back to gateway run --replace"
  fi

  (
    cd "$AGENT_DIR"
    HERMES_HOME="$HERMES_HOME" "${HERMES_CLI[@]}" gateway run --replace >>"$LOG_FILE" 2>&1 &
  )
  log "recovery: gateway run --replace (background)"
}

run_doctor_fix() {
  cd "$AGENT_DIR"
  HERMES_HOME="$HERMES_HOME" "${HERMES_CLI[@]}" doctor --fix >>"$LOG_FILE" 2>&1 || true
}

main() {
  local last_state="booting"
  local delay attempts
  log "watchdog started HERMES_HOME=${HERMES_HOME} interval=${CHECK_INTERVAL}s backoff<=${MAX_BACKOFF}s jitter<=${JITTER_MAX}s attempts=${MAX_ATTEMPTS}/${ATTEMPT_WINDOW}s cooldown=${COOLDOWN_SECONDS}s prefer_systemd=${PREFER_SYSTEMD} cli=${HERMES_CLI[*]}"

  while true; do
    if check_health; then
      if [[ "$last_state" != "healthy" ]]; then
        log "health restored (${HEALTH_REASON}); resetting failure counters"
      fi
      last_state="healthy"
      ATTEMPTS=()
      sleep "$CHECK_INTERVAL"
      continue
    fi

    attempts=$(attempt_count)
    if (( attempts >= MAX_ATTEMPTS )); then
      delay=$((COOLDOWN_SECONDS + $(rand_between_zero_and "$JITTER_MAX")))
      log "attempt cap reached (${attempts}/${MAX_ATTEMPTS}) after unhealthy='${HEALTH_REASON}'; entering cooldown ${delay}s"
      last_state="cooldown"
      sleep "$delay"
      continue
    fi

    record_attempt
    attempts=$(attempt_count)
    delay=$(compute_backoff_delay)
    log "unhealthy detected: ${HEALTH_REASON}; recovery attempt ${attempts}/${MAX_ATTEMPTS} in ${delay}s"
    sleep "$delay"

    restart_gateway
    sleep "$RESTART_WAIT"
    if check_health; then
      log "recovered after gateway restart"
      last_state="healthy"
      ATTEMPTS=()
      sleep "$CHECK_INTERVAL"
      continue
    fi

    log "restart did not recover (${HEALTH_REASON}); running doctor --fix"
    run_doctor_fix
    log "doctor --fix finished; restarting gateway again"
    restart_gateway
    sleep "$POST_DOCTOR_WAIT"

    if check_health; then
      log "recovered after doctor+restart"
      last_state="healthy"
      ATTEMPTS=()
    else
      log "still unhealthy after doctor+restart: ${HEALTH_REASON}"
      last_state="degraded"
    fi

    sleep "$CHECK_INTERVAL"
  done
}

main
