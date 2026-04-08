#!/usr/bin/env bash
# Run a one-off remote shell command on the droplet as SSH_USER, without the workstation
# `sudo -u <runtime>` step (HERMES_DROPLET_REQUIRE_SUDO=0 for this process only).
#
# AI assistants / CI — sudo off by default (this wrapper):
#   Use plain `./scripts/core/droplet_run.sh '…'` for work as SSH_USER (e.g. hermesadmin) without
#   interactive sudo. That avoids TTY/password hangs in Cursor when you do not need hermesuser.
# When you must run as hermesuser (paths under /home/hermesuser, git as that user), use
#   ./scripts/core/droplet_run.sh --droplet-require-sudo --sudo-user hermesuser '…'
#   Remote commands as hermesuser are prefixed with cd + venv activate (see droplet_remote_venv.sh
#   and policies Step 15 — Remote venv).
#   Non-interactive sudo requires SSH_SUDO_PASSWORD in the same ~/.env/.env as SSH_* (see
#   ssh_droplet.sh). Do not edit ~/.env/.env to “turn sudo off globally”; this wrapper already
#   limits REQUIRE_SUDO=0 to this process — interactive `hermes … droplet` stays sudo-on by default.
#
# Usage:
#   ./scripts/core/droplet_run.sh 'cd ~/hermes-agent && git status'
#   ./scripts/core/droplet_run.sh --droplet-require-sudo --sudo-user hermesuser 'whoami'   # rare
#
# Restart a profile-scoped gateway over SSH (sets DBUS/XDG like Hermes does — avoid raw systemctl --user):
#   ./scripts/core/droplet_run.sh --droplet-require-sudo --sudo-user hermesuser \
#     'cd ~/hermes-agent && ./venv/bin/python -m hermes_cli.main -p chief-orchestrator gateway restart'
#
# Replace local ~/.hermes with /home/hermesuser/.hermes from the VPS (binary-safe ssh -T; backs up first):
#   ./scripts/core/droplet_pull_hermes_home.sh
# Push local ~/.hermes to the VPS (backs up remote .hermes first; see script for gateway restart):
#   ./scripts/core/droplet_push_hermes_home.sh
# Append secrets on the VPS as hermesuser (after git pull so the script exists in ~/hermes-agent):
#   ./scripts/core/droplet_run.sh --droplet-require-sudo --sudo-user hermesuser \
#     'bash ~/hermes-agent/scripts/core/hermes_append_env.sh KEY=value'
# Replace one key in ~/.hermes/.env (removes old KEY= lines, writes one new line):
#   bash ~/hermes-agent/scripts/core/hermes_set_env_key.sh KEY 'value'
#
# Same credentials as scripts/core/ssh_droplet.sh (~/.env/.env). HERMES_DROPLET_INTERACTIVE=1
# keeps the IDE TTY gate satisfied; SSH key rules follow ssh_droplet.sh.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
exec env HERMES_DROPLET_REQUIRE_SUDO=0 HERMES_DROPLET_INTERACTIVE=1 \
  bash "$ROOT/ssh_droplet.sh" "$@"
