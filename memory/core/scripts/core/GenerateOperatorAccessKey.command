#!/bin/bash
# Double-click in Finder (macOS). Right-click → Open the first time if Gatekeeper blocks.
# Runs the collaborator helper: generate key, prompts, optional SSH login.
cd "$(dirname "$0")"
exec bash ./generate_operator_collaborator_key.sh "$@"
