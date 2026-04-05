#!/usr/bin/env bash
# Run a one-off remote shell command on the droplet as SSH_USER, without the workstation
# `sudo -u <runtime>` step (HERMES_DROPLET_REQUIRE_SUDO=0 for this process only).
#
# AI assistants / CI — sudo off by default (this wrapper):
#   Use plain `./scripts/droplet_run.sh '…'` for work as SSH_USER (e.g. hermesadmin) without
#   interactive sudo. That avoids TTY/password hangs in Cursor when you do not need hermesuser.
# When you must run as hermesuser (paths under /home/hermesuser, git as that user), use
#   ./scripts/droplet_run.sh --droplet-require-sudo --sudo-user hermesuser '…'
#   Non-interactive sudo requires SSH_SUDO_PASSWORD in the same ~/.env/.env as SSH_* (see
#   ssh_droplet.sh). Do not edit ~/.env/.env to “turn sudo off globally”; this wrapper already
#   limits REQUIRE_SUDO=0 to this process — interactive `hermes … droplet` stays sudo-on by default.
#
# Usage:
#   ./scripts/droplet_run.sh 'cd ~/hermes-agent && git status'
#   ./scripts/droplet_run.sh --droplet-require-sudo --sudo-user hermesuser 'whoami'   # rare
#
# Restart a profile-scoped gateway over SSH (sets DBUS/XDG like Hermes does — avoid raw systemctl --user):
#   ./scripts/droplet_run.sh --droplet-require-sudo --sudo-user hermesuser \
#     'cd ~/hermes-agent && ./venv/bin/python -m hermes_cli.main -p chief-orchestrator gateway restart'
#
# Same credentials as scripts/ssh_droplet.sh (~/.env/.env). HERMES_DROPLET_INTERACTIVE=1
# keeps the IDE TTY gate satisfied; SSH key rules follow ssh_droplet.sh.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
exec env HERMES_DROPLET_REQUIRE_SUDO=0 HERMES_DROPLET_INTERACTIVE=1 \
  bash "$ROOT/ssh_droplet.sh" "$@"
