#!/bin/bash
# Run **on the Mac mini with sudo** (copy this script + operator_ssh_gate_remote.sh to the mini first).
# Installs the gate to /usr/local/libexec/hermes/ and prints the sshd **Match** block to add manually.
#
#   sudo ./install_operator_ssh_gate_remote.sh
#
# Then merge the printed **Match User** lines into /etc/ssh/sshd_config (or drop-in under sshd_config.d),
# validate: sudo sshd -t
# Restart Remote Login / sshd (macOS): System Settings → General → Sharing → Remote Login off/on,
# or: sudo launchctl kickstart -k system/com.openssh.sshd  (exact label may vary by OS version)
#
# **operator** must be allowed to **sudo** (e.g. Admin): sudo dseditgroup -o edit -a operator -t user admin
#
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST="${OPERATOR_SSH_GATE_INSTALL_DIR:-/usr/local/libexec/hermes}"
GATE_SRC="${HERE}/operator_ssh_gate_remote.sh"
GATE_DST="${DEST}/operator_ssh_gate_remote.sh"

if [[ "$(id -u)" != "0" ]]; then
  echo "Run with sudo: sudo $0" >&2
  exit 1
fi
if [[ ! -f "$GATE_SRC" ]]; then
  echo "Missing ${GATE_SRC}" >&2
  exit 1
fi
install -d -m 0755 "$DEST"
install -m 0755 "$GATE_SRC" "$GATE_DST"
echo "Installed: $GATE_DST"
echo ""
echo "Add this block to /etc/ssh/sshd_config (or a file under /etc/ssh/sshd_config.d/), then sshd -t && restart sshd:"
echo ""
cat <<EOF
Match User operator
    ForceCommand ${GATE_DST}
EOF
echo ""
echo "Use a second authorized_keys entry (separate key) without ForceCommand for automation, with from=\"<tailscale-ip>/32\" if possible."
