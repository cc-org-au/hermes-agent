# Memory integration override (completeness)

> **Referenced from:** org activation / memory strategy notes.  
> **Purpose:** Define how **Hermes memory** (`memories/MEMORY.md`, `USER.md`, memory tool) relates to **workspace registers** under `workspace/memory/runtime/operations/`.

## Principles

1. **Registers are durable governance** — `SECURITY_ALERT_REGISTER.md`, `ORG_REGISTRY.md`, `CHANNEL_ARCHITECTURE.md`, etc. are the **source of truth** for structured status. They are **not** replaced by ad-hoc memory entries.
2. **MEMORY.md is curated narrative** — short-lived operator facts, preferences, and “what we learned this week” that help the **next session**; keep entries **bounded** (see memory tool char limits).
3. **No cross-profile leakage** — each profile has its own `HERMES_HOME/memories/`; do not instruct copying MEMORY.md between profiles without redaction review.
4. **Prompt cache stability** — mid-session memory writes do **not** change the frozen system prompt snapshot; critical policy changes belong in **workspace** or **policies/** and a **new session** if the chief must see them in context.

## When to use which

| Need | Use |
|------|-----|
| Alert status, allowlists, formal workflow | `workspace/memory/runtime/operations/*.md` registers |
| Operator preferences, environment quirks | `memories/USER.md` / memory tool |
| Session takeaway bullets | `memories/MEMORY.md` via memory tool |
| Legal / audit trail | Registers + dated files in `workspace/memory/runtime/operations/` |

## Archival

- Long-term narrative archival per `policies/core/governance/artifacts-and-archival-memory.md` when materialized.

## Chief bootstrap

- After large governance updates, append a **single** dated entry to `memories/MEMORY.md` (or use `MEMORY_MD_APPEND_SNIPPET.txt` from repo templates) so the next interactive session picks up the headline facts.
