---
name: letta
description: Letta pinned memory blocks + archival memory tools via Letta Cloud (host-scoped API keys).
---

# Letta (Hermes integration)

Letta’s key advantage is **always-visible pinned memory blocks** plus a large archival history.

## Required env

- `LETTA_API_KEY_OPERATOR` (operator) or `LETTA_API_KEY_DROPLET` (droplet)

Hermes caches a default Letta agent id at:

- `${HERMES_HOME}/runtime/letta_default_agent_id.txt`

## Available commands (tools)

- `letta_agent_ensure` — ensure the default Letta agent exists
- `letta_memory_turn(message, agent_id?)` — send a message to the Letta agent
- `letta_memory_blocks(agent_id?)` — read pinned blocks
- `letta_block_update(block_label, value, agent_id?)` — update a pinned block

## References

- Letta Python SDK: `https://docs.letta.com/api/python/`
