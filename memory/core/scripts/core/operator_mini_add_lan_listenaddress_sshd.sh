#!/usr/bin/env bash
# Manual one-shot: delegates to operator_mini_refresh_lan_listenaddress.sh (same args).
# Prefer installing the automatic refresh LaunchDaemon once — see
# operator_mini_install_lan_listenaddress_watch.sh
#
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec bash "$DIR/operator_mini_refresh_lan_listenaddress.sh" "$@"
