---
name: langmem
description: Use LangMem-style lifecycle memory tools (durable SQLite store per Hermes profile).
---

# LangMem (Hermes integration)

Hermes exposes LangMem as tool calls under the `memory_cloud` toolset.

## What it’s for

- **Lifecycle thinking**: treat semantic / episodic / procedural memory differently.
- **Hot-path writes**: record small durable memories explicitly.
- **Quick search**: retrieve prior memories when needed.

## Persistence

This integration uses a **durable SQLite store** at:

- `${HERMES_HOME}/runtime/langmem.sqlite3`

So it persists across sessions and restarts on both operator and droplet.

## Available commands (tools)

- `langmem_semantic_memory`
  - `action=search` with `query`, optional `limit`
  - `action=create` with `content`
  - `action=update` with `memory_id` + `content`
  - `action=delete` with `memory_id`

## How to use alongside Mem0

- Use **Mem0** for **semantic recall + rerank + filtering** (cloud durable memory).
- Use **LangMem** for **small durable lifecycle notes** (durable local store) and for explicitly managed “procedural” reminders.

## References

- LangMem docs: `https://langchain-ai.github.io/langmem/`
