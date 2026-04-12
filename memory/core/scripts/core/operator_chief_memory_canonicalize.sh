#!/usr/bin/env bash
# One-off / repeatable: canonicalize chief-orchestrator memory + policies layout (operator Mac or droplet VPS).
# Examples:
#   ./operator_chief_memory_canonicalize.sh
#   HERMES_CANONICAL_HOST_LABEL=droplet ./operator_chief_memory_canonicalize.sh
#   ./droplet_chief_memory_canonicalize.sh
#
# Does not print secret contents. Idempotent-ish: safe to re-run (merges with rsync backups).
set -euo pipefail

HERMES_CANONICAL_HOST_LABEL="${HERMES_CANONICAL_HOST_LABEL:-operator}"

PROFILE="${HERMES_PROFILE_HOME:-$HOME/.hermes/profiles/chief-orchestrator}"
WS="$PROFILE/workspace"
MK="$WS/memory"
PERSONA="$MK/actors/persona"
REF="$MK/knowledge/references"
PROJ="$MK/knowledge/projects"
HERMES_REPO="${HERMES_AGENT_REPO:-$HOME/hermes-agent}"

ts="$(date +%Y%m%dT%H%M%SZ)"

mkdir -p "$PROJ" "$REF" "$PERSONA"

# --- 1) Merge profile/memory/knowledge/projects → workspace/memory/knowledge/projects
if [[ -d "$PROFILE/memory/knowledge/projects" ]]; then
  if compgen -G "$PROFILE/memory/knowledge/projects/*" >/dev/null 2>&1; then
    rsync -avb --suffix=".merged-${ts}" "$PROFILE/memory/knowledge/projects/" "$PROJ/"
  fi
  rm -rf "$PROFILE/memory/knowledge/projects"
fi
mkdir -p "$PROFILE/memory/knowledge"
cat > "$PROFILE/memory/knowledge/README_CANONICAL_REDIRECT.md" << 'EOF'
# Deprecated path

Project knowledge and profile-scoped memory files **do not** live under `profiles/<profile>/memory/` anymore.

**Canonical project knowledge:** `workspace/memory/knowledge/projects/`  
**Canonical workspace memory root:** `workspace/memory/`

Do not add new files under `profiles/chief-orchestrator/memory/` except this redirect notice.
EOF

# --- 2) Consolidate profiles/.../memories/MEMORY.md + USER.md into workspace memory
MEM_DIR="$PROFILE/memories"
mkdir -p "$MEM_DIR"
ARCH="$MEM_DIR/_archived_${ts}"
if [[ -f "$MEM_DIR/MEMORY.md" || -f "$MEM_DIR/USER.md" ]]; then
  mkdir -p "$ARCH"
  [[ -f "$MEM_DIR/MEMORY.md" ]] && mv "$MEM_DIR/MEMORY.md" "$ARCH/"
  [[ -f "$MEM_DIR/USER.md" ]] && mv "$MEM_DIR/USER.md" "$ARCH/"
  [[ -f "$MEM_DIR/MEMORY.md.lock" ]] && mv "$MEM_DIR/MEMORY.md.lock" "$ARCH/" 2>/dev/null || true
  [[ -f "$MEM_DIR/USER.md.lock" ]] && mv "$MEM_DIR/USER.md.lock" "$ARCH/" 2>/dev/null || true
fi

# Build merged reference memory (from archived Mem0 policy text)
if [[ -f "$ARCH/MEMORY.md" ]]; then
  {
    echo "# Consolidated durable memory policy (${HERMES_CANONICAL_HOST_LABEL})"
    echo ""
    echo "> Migrated from \`profiles/chief-orchestrator/memories/MEMORY.md\` on ${ts}."
    echo ""
    cat "$ARCH/MEMORY.md"
  } > "$REF/memory.md"
elif [[ ! -f "$REF/memory.md" ]]; then
  echo "# memory.md — ${HERMES_CANONICAL_HOST_LABEL} durable notes (no legacy MEMORY.md to merge)." > "$REF/memory.md"
fi

# Merge USER into persona user.md
if [[ -f "$ARCH/USER.md" ]]; then
  {
    echo "# User profile (${HERMES_CANONICAL_HOST_LABEL})"
    echo ""
    echo "> Consolidated from \`profiles/chief-orchestrator/memories/USER.md\` + template on ${ts}."
    echo ""
    cat "$PERSONA/user.md"
    echo ""
    echo "## Preferences (from memories/USER.md)"
    echo ""
    cat "$ARCH/USER.md"
  } > "$PERSONA/user.md.tmp"
  mv "$PERSONA/user.md.tmp" "$PERSONA/user.md"
fi

cat > "$MEM_DIR/README_CANONICAL_REDIRECT.md" << 'EOF'
# Deprecated: `profiles/chief-orchestrator/memories/`

Previous `MEMORY.md` / `USER.md` were merged into:

- `workspace/memory/knowledge/references/memory.md` — durable policy / Mem0-oriented notes  
- `workspace/memory/actors/persona/user.md` — user preferences and profile  

Do not add new files here. Use `workspace/memory/` only.
EOF

# --- 3) SOUL: merge workspace/SOUL.md into canonical persona/soul.md
if [[ -f "$WS/SOUL.md" && ! -L "$WS/SOUL.md" ]]; then
  mkdir -p "$ARCH"
  _soul_ws="$(cat "$WS/SOUL.md")"
  {
    echo "# Soul (canonical)"
    echo ""
    echo "> Consolidated from \`workspace/SOUL.md\` + template on ${ts}."
    echo ""
    cat "$PERSONA/soul.md"
    echo ""
    echo "## From workspace/SOUL.md"
    echo ""
    printf '%s\n' "$_soul_ws"
  } > "$PERSONA/soul.md.tmp"
  mv "$PERSONA/soul.md.tmp" "$PERSONA/soul.md"
  mv "$WS/SOUL.md" "$ARCH/workspace_SOUL.md.archived-${ts}"
fi
ln -sf "$PERSONA/soul.md" "$WS/SOUL.md"
ln -sf "$WS/SOUL.md" "$PROFILE/SOUL.md"

# --- 4) Policies from git checkout (run git pull separately if needed)
if [[ -d "$HERMES_REPO/policies" ]]; then
  mkdir -p "$PROFILE/policies"
  rsync -av --delete "$HERMES_REPO/policies/" "$PROFILE/policies/"
fi

# --- 5) Canonical paths doc for agents
mkdir -p "$MK/core"
cat > "$MK/core/CANONICAL_PATHS_AND_SOURCES.md" << EOF
# Canonical paths (chief-orchestrator, ${HERMES_CANONICAL_HOST_LABEL})

**Host label:** \`${HERMES_CANONICAL_HOST_LABEL}\` — use \`~\` as the runtime user’s home (\`hermesuser\` on the droplet, \`operator\` on the Mac mini).

**Highest priority — use these only for new content:**

| Purpose | Path |
|--------|------|
| Workspace memory root | \`~/.hermes/profiles/chief-orchestrator/workspace/memory/\` |
| Project knowledge (e.g. agentic-company) | \`~/.hermes/profiles/chief-orchestrator/workspace/memory/knowledge/projects/\` |
| Durable reference notes (incl. former memories/MEMORY.md) | \`~/.hermes/profiles/chief-orchestrator/workspace/memory/knowledge/references/memory.md\` |
| User preferences / persona | \`~/.hermes/profiles/chief-orchestrator/workspace/memory/actors/persona/user.md\` |
| Soul / voice | \`~/.hermes/profiles/chief-orchestrator/workspace/memory/actors/persona/soul.md\` |
| Repo policies (synced copy) | \`~/.hermes/profiles/chief-orchestrator/policies/\` ← mirrors \`hermes-agent/policies/\` |

**Do not use for new files:**

- \`profiles/chief-orchestrator/memory/\` (except README redirect)
- \`profiles/chief-orchestrator/memories/\` (deprecated; see README there)

**Policies:** Treat \`~/hermes-agent/policies/\` on disk (and the profile copy above) as the canonical policy tree for Hermes; prefer it over ad-hoc policy docs elsewhere.

**Mem0:** Continue to follow the durable policy text in \`knowledge/references/memory.md\` for sync/deletion rules.
EOF

echo "chief_memory_canonicalize: host=${HERMES_CANONICAL_HOST_LABEL} PROFILE=$PROFILE"
