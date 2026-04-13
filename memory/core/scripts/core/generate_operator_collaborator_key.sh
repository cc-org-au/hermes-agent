#!/usr/bin/env bash
# Send this script to someone who needs SSH access to your operator Mac mini.
# They run it locally; it creates a dedicated keypair and prints ONLY the public key
# for you to append to operator's ~/.ssh/authorized_keys (optionally with from="..." ).
#
# macOS: double-click **GenerateOperatorAccessKey.command** instead (same folder) — no Terminal commands.
#
# Usage:
#   bash generate_operator_collaborator_key.sh "Alice Dev"
#
set -euo pipefail
NAME="${1:-collaborator}"
SAFE="${NAME//[^a-zA-Z0-9._-]/_}"
OUT="${HOME}/.ssh/operator_access_${SAFE}_ed25519"
mkdir -p "${HOME}/.ssh"
chmod 700 "${HOME}/.ssh"
if [[ -f "$OUT" ]]; then
  echo "Refusing to overwrite existing: $OUT" >&2
  echo "Remove it first or pick a different name." >&2
  exit 1
fi
ssh-keygen -t ed25519 -f "$OUT" -C "operator-access-${SAFE}"
chmod 600 "$OUT"
echo ""
echo "=== Send ONLY the line below to the admin (public key) ==="
cat "${OUT}.pub"
echo "=== end ==="
echo ""
echo "Private key (keep secret, never email): $OUT"
echo "They will add your pubkey to authorized_keys; you connect with:"
echo "  ssh -i \"$OUT\" -o IdentitiesOnly=yes -p 52822 operator@<TAILSCALE_IP>"
