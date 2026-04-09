#!/usr/bin/env bash
# Reverse SSH tunnel: VPS connects to 127.0.0.1:REMOTE_PORT on the *server*, traffic is
# forwarded to this Mac's CHIME_HOST:CHIME_PORT (where hermes_turn_chime_server.py listens).
#
# Use when Tailscale cannot reach the Mac directly (sleep, firewall, no inbound) but SSH
# from Mac → VPS works. On the VPS set:
#   HERMES_TURN_DONE_NOTIFY_URL=http://127.0.0.1:REMOTE_PORT/
#
# Usage (from Mac, after starting the chime server on 127.0.0.1:8765):
#   ./scripts/macos/hermes_turn_chime_reverse_tunnel.sh user@vps-host
#
# Defaults: REMOTE_PORT=8765, forwards to 127.0.0.1:8765 on Mac.
set -euo pipefail
REMOTE_PORT="${HERMES_TUNNEL_REMOTE_PORT:-8765}"
CHIME_HOST="${HERMES_TUNNEL_CHIME_HOST:-127.0.0.1}"
CHIME_PORT="${HERMES_TUNNEL_CHIME_PORT:-8765}"
DEST="${1:?usage: $0 user@vps-host}"
exec ssh -N \
  -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=30 \
  -o ServerAliveCountMax=3 \
  -R "${REMOTE_PORT}:${CHIME_HOST}:${CHIME_PORT}" \
  "$DEST"
