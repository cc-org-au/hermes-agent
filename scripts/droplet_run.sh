#!/usr/bin/env bash
# Run a one-off remote shell command on the droplet as SSH_USER, without the workstation
# `sudo -u <runtime>` step (HERMES_DROPLET_REQUIRE_SUDO=0 for this process only).
#
# AI assistants / CI: use this for git pull, smoke checks, etc. Parent shell is unchanged;
# interactive `hermes … droplet` still defaults to sudo on (see scripts/agent-droplet).
#
# Usage:
#   ./scripts/droplet_run.sh 'cd ~/hermes-agent && git status'
#   ./scripts/droplet_run.sh --droplet-require-sudo --sudo-user hermesuser 'whoami'   # rare
#
# Same credentials as scripts/ssh_droplet.sh (~/.env/.env). HERMES_DROPLET_INTERACTIVE=1
# keeps the IDE TTY gate satisfied; SSH key rules follow ssh_droplet.sh.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
exec env HERMES_DROPLET_REQUIRE_SUDO=0 HERMES_DROPLET_INTERACTIVE=1 \
  bash "$ROOT/ssh_droplet.sh" "$@"
