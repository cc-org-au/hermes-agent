---
name: zep
description: Zep Cloud temporal memory + knowledge graph tools (host-scoped API keys).
---

# Zep (Hermes integration)

Zep provides temporal semantics and a knowledge graph across sessions.

## Required env

- `ZEP_API_KEY_OPERATOR` (operator) or `ZEP_API_KEY_DROPLET` (droplet)
- Optional: `ZEP_DEFAULT_USER_ID` (default `hermes-default`)

## Available commands (tools)

### Graph search / facts

- `zep_knowledge_search(query, user_id?, limit?)`
- `zep_user_ensure(user_id?)`

### Session memory (threads)

- `zep_session_create(session_id, user_id?)`
- `zep_session_add(session_id, user_id?, messages=[{role, role_type, content}])`
- `zep_memory_get(session_id)`

## Suggested workflow

- Ensure user once (`zep_user_ensure`).
- For each Hermes chat thread, pick a stable `session_id` and store messages via `zep_session_add`.
- Retrieve context via `zep_memory_get` when needed, and use `zep_knowledge_search` for facts.

## References

- Zep quickstart: `https://help.getzep.com/v2/quickstart`
- Zep overview: `https://help.getzep.com/overview`
