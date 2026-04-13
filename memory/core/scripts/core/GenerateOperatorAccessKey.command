#!/bin/bash
# Double-click this file in Finder (macOS). Terminal opens, creates a keypair under ~/.ssh/,
# copies your PUBLIC key to the clipboard, and shows a short dialog.
# First run: if macOS blocks it, right-click → Open (Gatekeeper).
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v ssh-keygen >/dev/null 2>&1; then
  osascript -e 'display dialog "ssh-keygen not found. Install Xcode CLT or use Terminal from a full macOS install." buttons {"OK"} default button 1 with icon stop'
  exit 1
fi

NAME="$(osascript -e 'display dialog "Label for this key (e.g. your name):" default answer "collaborator" buttons {"Cancel", "OK"} default button "OK"' -e 'text returned of result' 2>/dev/null || true)"
NAME="${NAME:-collaborator}"
SAFE="${NAME//[^a-zA-Z0-9._-]/_}"
OUT="${HOME}/.ssh/operator_access_${SAFE}_ed25519"

mkdir -p "${HOME}/.ssh"
chmod 700 "${HOME}/.ssh"

if [[ -f "$OUT" ]]; then
  osascript -e "display dialog \"A key already exists at:\\n${OUT}\\n\\nDelete it first or pick another label.\" buttons {\"OK\"} default button 1 with icon stop"
  exit 1
fi

/usr/bin/ssh-keygen -t ed25519 -f "$OUT" -N "" -C "operator-access-${SAFE}" </dev/null
chmod 600 "$OUT"
/usr/bin/pbcopy <"${OUT}.pub"

osascript <<OSA
display dialog "Done. Your PUBLIC key (one line, starts with ssh-ed25519) is on the clipboard — paste it to the admin.

Private key stays on this Mac only:
${OUT}

Connect later with:
ssh -i \\"${OUT}\\" -o IdentitiesOnly=yes -p 52822 operator@<TAILSCALE_IP>" buttons {"OK"} default button "OK"
OSA

echo ""
echo "=== Public key (also in clipboard) ==="
cat "${OUT}.pub"
echo ""
read -r -p "Press Enter to close this window…" _
