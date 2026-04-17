---
name: langsmith
description: LangSmith observability validation + tracing hints for Hermes (uses host-scoped API keys).
---

# LangSmith (Hermes integration)

Hermes uses LangSmith for **observability/tracing**, not as the primary durable memory store.

## Available commands (tools)

- `langsmith_workspace_info`
  - Validates the host-scoped key and returns account/workspace info.
  - This call is designed to avoid endpoints that may be forbidden under some key scopes.

## Tracing setup

To send traces from LangChain/LangGraph components, you generally enable tracing via environment:

- `LANGSMITH_API_KEY_OPERATOR` or `LANGSMITH_API_KEY_DROPLET`
- Optional tracing flags (used by LangChain/LangGraph ecosystems):
  - `LANGCHAIN_TRACING_V2=true`
  - `LANGSMITH_TRACING=true`

## References

- LangSmith docs: `https://docs.langchain.com/langsmith/home`
