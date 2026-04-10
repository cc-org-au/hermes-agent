#!/usr/bin/env bash
# shellcheck shell=bash
# Prefix remote bash commands: cd to Hermes checkout on the Mac mini, activate venv.
# Sourced by ssh_operator.sh — do not run directly.
#
# On the remote shell, HERMES_OPERATOR_REPO may be exported by ssh_operator.sh; otherwise
# default is $HOME/hermes-agent.

_operator_wrap_cmd_with_venv() {
  local user_cmd="$1"
  local pre
  pre='repo="${HERMES_OPERATOR_REPO:-$HOME/hermes-agent}"; cd "$repo" 2>/dev/null || exit 1; '
  pre+='[ -f "$repo/venv/bin/activate" ] && . "$repo/venv/bin/activate"; '
  pre+='export VIRTUAL_ENV="$repo/venv"; export PATH="${VIRTUAL_ENV}/bin:${PATH}"; '
  printf '%s%s' "$pre" "$user_cmd"
}

_operator_interactive_shell_cmd() {
  _operator_wrap_cmd_with_venv "exec bash -l"
}
