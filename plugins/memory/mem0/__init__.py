"""Mem0 memory plugin — MemoryProvider interface.

Server-side LLM fact extraction, semantic search with reranking, and
automatic deduplication via the Mem0 Platform API.

Original PR #2933 by kartik-mem0, adapted to MemoryProvider ABC.

Config via environment variables:
  MEM0_API_KEY       — Mem0 Platform API key (required)
  MEM0_USER_ID       — User identifier (default: hermes-user)
  MEM0_AGENT_ID      — Agent identifier (default: hermes)

Or via $HERMES_HOME/mem0.json.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, List

from agent.memory_provider import MemoryProvider

logger = logging.getLogger(__name__)

# Circuit breaker: after this many consecutive failures, pause API calls
# for _BREAKER_COOLDOWN_SECS to avoid hammering a down server.
_BREAKER_THRESHOLD = 5
_BREAKER_COOLDOWN_SECS = 120

# Required exact string for mem0_delete_all_memories (destructive).
_DELETE_ALL_CONFIRM = "YES_DELETE_ALL_MY_MEM0_MEMORIES"


def _json_response(data: Any) -> str:
    """Serialize API payloads for tool results."""
    try:
        return json.dumps(data, default=str)
    except TypeError:
        return json.dumps({"result": str(data)})


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def _load_config() -> dict:
    """Load config from $HERMES_HOME/mem0.json merged with env vars.

    File values win when set; env fills missing ``api_key`` / ``user_id`` /
    ``agent_id`` so ``MEM0_API_KEY`` in ``~/.hermes/.env`` still works when
    ``mem0.json`` only contains non-secret options (rerank, etc.).
    """
    from hermes_constants import get_hermes_home
    defaults = {
        "api_key": os.environ.get("MEM0_API_KEY", ""),
        "user_id": os.environ.get("MEM0_USER_ID", "hermes-user"),
        "agent_id": os.environ.get("MEM0_AGENT_ID", "hermes"),
        "rerank": True,
        "keyword_search": False,
    }
    config_path = get_hermes_home() / "mem0.json"
    if config_path.exists():
        try:
            file_cfg = json.loads(config_path.read_text(encoding="utf-8"))
            if isinstance(file_cfg, dict):
                merged = {**defaults, **file_cfg}
                if not (merged.get("api_key") or "").strip():
                    merged["api_key"] = defaults["api_key"]
                if not (merged.get("user_id") or "").strip():
                    merged["user_id"] = defaults["user_id"]
                if not (merged.get("agent_id") or "").strip():
                    merged["agent_id"] = defaults["agent_id"]
                return merged
        except Exception:
            pass

    return defaults


def _mem0_search_filters(user_id: str) -> dict:
    """Build v2 search filters (required by Mem0 API; must be non-empty).

    Scope matches historical plugin behavior: filter by ``user_id`` only
    (``add`` still sends ``agent_id`` for storage metadata).
    """
    uid = (user_id or "").strip() or "hermes-user"
    return {"AND": [{"user_id": uid}]}


def _normalize_memory_rows(response: Any) -> List[dict]:
    """Normalize MemoryClient search/get_all payloads to a list of row dicts."""
    if response is None:
        return []
    if isinstance(response, list):
        return response
    if isinstance(response, dict):
        for key in ("results", "memories"):
            rows = response.get(key)
            if isinstance(rows, list):
                return rows
    return []


# ---------------------------------------------------------------------------
# Tool schemas
# ---------------------------------------------------------------------------

PROFILE_SCHEMA = {
    "name": "mem0_profile",
    "description": (
        "Retrieve all stored memories about the user — preferences, facts, "
        "project context. Fast, no reranking. Use at conversation start."
    ),
    "parameters": {"type": "object", "properties": {}, "required": []},
}

SEARCH_SCHEMA = {
    "name": "mem0_search",
    "description": (
        "Search memories by meaning. Returns relevant facts ranked by similarity. "
        "Set rerank=true for higher accuracy on important queries."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "What to search for."},
            "rerank": {"type": "boolean", "description": "Enable reranking for precision (default: false)."},
            "top_k": {"type": "integer", "description": "Max results (default: 10, max: 50)."},
        },
        "required": ["query"],
    },
}

CONCLUDE_SCHEMA = {
    "name": "mem0_conclude",
    "description": (
        "Store a durable fact about the user. Stored verbatim (no LLM extraction). "
        "Use for explicit preferences, corrections, or decisions."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "conclusion": {"type": "string", "description": "The fact to store."},
        },
        "required": ["conclusion"],
    },
}

# Additional tools aligned with Mem0 Platform MCP (https://docs.mem0.ai/platform/mem0-mcp)
# and Python MemoryClient (mem0ai).

ADD_MEMORY_SCHEMA = {
    "name": "mem0_add_memory",
    "description": (
        "Add memory via Mem0 Platform (same as MCP add_memory). Sends text or "
        "conversation messages; with infer=true Mem0 runs server-side extraction "
        "and deduplication. Use mem0_conclude instead for a single verbatim fact."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "content": {
                "type": "string",
                "description": "Plain text to store (converted to a user message). Ignored if messages is set.",
            },
            "messages": {
                "type": "array",
                "description": "OpenAI-style messages [{role, content}, ...]. Overrides content when set.",
                "items": {
                    "type": "object",
                    "properties": {
                        "role": {"type": "string"},
                        "content": {"type": "string"},
                    },
                },
            },
            "infer": {
                "type": "boolean",
                "description": "If true (default), Mem0 extracts/merges facts. If false, raw add like conclude.",
            },
        },
        "required": [],
    },
}

GET_MEMORIES_SCHEMA = {
    "name": "mem0_get_memories",
    "description": (
        "List memories with v2 filters and pagination (MCP get_memories). Scoped to "
        "the configured Mem0 user. Use for large profiles; prefer mem0_profile for a quick full dump."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "page": {"type": "integer", "description": "Page number (default 1)."},
            "page_size": {
                "type": "integer",
                "description": "Page size (default 50, max 100).",
            },
        },
        "required": [],
    },
}

GET_MEMORY_SCHEMA = {
    "name": "mem0_get_memory",
    "description": "Fetch one memory by id (MCP get_memory).",
    "parameters": {
        "type": "object",
        "properties": {
            "memory_id": {"type": "string", "description": "Mem0 memory id."},
        },
        "required": ["memory_id"],
    },
}

UPDATE_MEMORY_SCHEMA = {
    "name": "mem0_update_memory",
    "description": "Update a memory's text, metadata, and/or timestamp (MCP update_memory).",
    "parameters": {
        "type": "object",
        "properties": {
            "memory_id": {"type": "string"},
            "text": {"type": "string", "description": "New memory text."},
            "metadata": {
                "type": "object",
                "description": "Metadata object to merge/replace per API.",
            },
            "timestamp": {
                "type": "string",
                "description": "ISO 8601 or Unix epoch string for memory time.",
            },
        },
        "required": ["memory_id"],
    },
}

DELETE_MEMORY_SCHEMA = {
    "name": "mem0_delete_memory",
    "description": "Delete a single memory by id (MCP delete_memory).",
    "parameters": {
        "type": "object",
        "properties": {
            "memory_id": {"type": "string"},
        },
        "required": ["memory_id"],
    },
}

DELETE_ALL_MEMORIES_SCHEMA = {
    "name": "mem0_delete_all_memories",
    "description": (
        "Bulk-delete all memories for the configured Mem0 user_id only (MCP delete_all_memories). "
        "Requires confirm exactly: YES_DELETE_ALL_MY_MEM0_MEMORIES"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "confirm": {
                "type": "string",
                "description": "Must be the exact phrase YES_DELETE_ALL_MY_MEM0_MEMORIES",
            },
        },
        "required": ["confirm"],
    },
}

LIST_ENTITIES_SCHEMA = {
    "name": "mem0_list_entities",
    "description": (
        "List users, agents, apps, and runs that have memories (MCP list_entities). "
        "Read-only."
    ),
    "parameters": {"type": "object", "properties": {}, "required": []},
}

DELETE_ENTITIES_SCHEMA = {
    "name": "mem0_delete_entities",
    "description": (
        "Delete one entity and its memories (MCP delete_entities). Only the configured "
        "Hermes mem0 user_id or agent_id may be deleted (safety)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "user_id": {"type": "string", "description": "Must match the active Mem0 user_id."},
            "agent_id": {"type": "string", "description": "Must match the active Mem0 agent_id."},
            "app_id": {"type": "string"},
            "run_id": {"type": "string"},
        },
        "required": [],
    },
}

MEMORY_HISTORY_SCHEMA = {
    "name": "mem0_memory_history",
    "description": "Return edit history for a memory id (MemoryClient.history).",
    "parameters": {
        "type": "object",
        "properties": {
            "memory_id": {"type": "string"},
        },
        "required": ["memory_id"],
    },
}

FEEDBACK_SCHEMA = {
    "name": "mem0_feedback",
    "description": (
        "Send quality feedback for a memory (POSITIVE, NEGATIVE, VERY_NEGATIVE). "
        "See Mem0 feedback mechanism docs."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "memory_id": {"type": "string"},
            "feedback": {
                "type": "string",
                "description": "One of: POSITIVE, NEGATIVE, VERY_NEGATIVE",
            },
            "feedback_reason": {"type": "string", "description": "Optional explanation."},
        },
        "required": ["memory_id", "feedback"],
    },
}

BATCH_UPDATE_SCHEMA = {
    "name": "mem0_batch_update_memories",
    "description": "Batch-update memories (memory_id + optional text/metadata each).",
    "parameters": {
        "type": "object",
        "properties": {
            "memories": {
                "type": "array",
                "items": {"type": "object"},
                "description": "List of {memory_id, text?, metadata?}",
            },
        },
        "required": ["memories"],
    },
}

BATCH_DELETE_SCHEMA = {
    "name": "mem0_batch_delete_memories",
    "description": "Batch-delete by memory ids.",
    "parameters": {
        "type": "object",
        "properties": {
            "memory_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Mem0 memory ids to delete.",
            },
        },
        "required": ["memory_ids"],
    },
}

MEM0_ALL_TOOL_SCHEMAS: List[Dict[str, Any]] = [
    PROFILE_SCHEMA,
    SEARCH_SCHEMA,
    CONCLUDE_SCHEMA,
    ADD_MEMORY_SCHEMA,
    GET_MEMORIES_SCHEMA,
    GET_MEMORY_SCHEMA,
    UPDATE_MEMORY_SCHEMA,
    DELETE_MEMORY_SCHEMA,
    DELETE_ALL_MEMORIES_SCHEMA,
    LIST_ENTITIES_SCHEMA,
    DELETE_ENTITIES_SCHEMA,
    MEMORY_HISTORY_SCHEMA,
    FEEDBACK_SCHEMA,
    BATCH_UPDATE_SCHEMA,
    BATCH_DELETE_SCHEMA,
]


# ---------------------------------------------------------------------------
# MemoryProvider implementation
# ---------------------------------------------------------------------------

class Mem0MemoryProvider(MemoryProvider):
    """Mem0 Platform memory with server-side extraction and semantic search."""

    def __init__(self):
        self._config = None
        self._client = None
        self._client_lock = threading.Lock()
        self._api_key = ""
        self._user_id = "hermes-user"
        self._agent_id = "hermes"
        self._rerank = True
        self._keyword_search = False
        self._prefetch_result = ""
        self._prefetch_lock = threading.Lock()
        self._prefetch_thread = None
        self._sync_thread = None
        # Circuit breaker state
        self._consecutive_failures = 0
        self._breaker_open_until = 0.0

    @property
    def name(self) -> str:
        return "mem0"

    def is_available(self) -> bool:
        cfg = _load_config()
        return bool(cfg.get("api_key"))

    def save_config(self, values, hermes_home):
        """Write config to $HERMES_HOME/mem0.json."""
        import json
        from pathlib import Path
        config_path = Path(hermes_home) / "mem0.json"
        existing = {}
        if config_path.exists():
            try:
                existing = json.loads(config_path.read_text())
            except Exception:
                pass
        existing.update(values)
        config_path.write_text(json.dumps(existing, indent=2))

    def get_config_schema(self):
        return [
            {"key": "api_key", "description": "Mem0 Platform API key", "secret": True, "required": True, "env_var": "MEM0_API_KEY", "url": "https://app.mem0.ai"},
            {"key": "user_id", "description": "User identifier", "default": "hermes-user"},
            {"key": "agent_id", "description": "Agent identifier", "default": "hermes"},
            {"key": "rerank", "description": "Enable reranking for recall", "default": "true", "choices": ["true", "false"]},
        ]

    def _get_client(self):
        """Thread-safe client accessor with lazy initialization."""
        with self._client_lock:
            if self._client is not None:
                return self._client
            try:
                from mem0 import MemoryClient
                self._client = MemoryClient(api_key=self._api_key)
                return self._client
            except ImportError:
                raise RuntimeError("mem0 package not installed. Run: pip install mem0ai")

    def _is_breaker_open(self) -> bool:
        """Return True if the circuit breaker is tripped (too many failures)."""
        if self._consecutive_failures < _BREAKER_THRESHOLD:
            return False
        if time.monotonic() >= self._breaker_open_until:
            # Cooldown expired — reset and allow a retry
            self._consecutive_failures = 0
            return False
        return True

    def _record_success(self):
        self._consecutive_failures = 0

    def _record_failure(self):
        self._consecutive_failures += 1
        if self._consecutive_failures >= _BREAKER_THRESHOLD:
            self._breaker_open_until = time.monotonic() + _BREAKER_COOLDOWN_SECS
            logger.warning(
                "Mem0 circuit breaker tripped after %d consecutive failures. "
                "Pausing API calls for %ds.",
                self._consecutive_failures, _BREAKER_COOLDOWN_SECS,
            )

    def initialize(self, session_id: str, **kwargs) -> None:
        self._config = _load_config()
        self._api_key = self._config.get("api_key", "")
        self._user_id = self._config.get("user_id", "hermes-user")
        self._agent_id = self._config.get("agent_id", "hermes")
        self._rerank = self._config.get("rerank", True)
        self._keyword_search = self._config.get("keyword_search", False)

    def system_prompt_block(self) -> str:
        _names = ", ".join(s["name"] for s in MEM0_ALL_TOOL_SCHEMAS)
        return (
            "# Mem0 Memory (Platform API)\n"
            f"Active. user_id={self._user_id}, agent_id={self._agent_id}.\n"
            f"Tools: {_names}.\n"
            "Parity with Mem0 MCP: add/list/get/update/delete memories, list/delete "
            "entities, history, feedback, batch update/delete. "
            "mem0_conclude stores one verbatim fact (infer off); mem0_add_memory uses "
            "Mem0 extraction when infer is true (default).\n"
            "If a result JSON has \"error\", the Mem0 API rejected the call—check "
            "credentials, quota, filters, or parameters—not \"missing tools\"."
        )

    def prefetch(self, query: str, *, session_id: str = "") -> str:
        if self._prefetch_thread and self._prefetch_thread.is_alive():
            self._prefetch_thread.join(timeout=3.0)
        with self._prefetch_lock:
            result = self._prefetch_result
            self._prefetch_result = ""
        if not result:
            return ""
        return f"## Mem0 Memory\n{result}"

    def queue_prefetch(self, query: str, *, session_id: str = "") -> None:
        if self._is_breaker_open():
            return

        def _run():
            try:
                client = self._get_client()
                raw = client.search(
                    query,
                    filters=_mem0_search_filters(self._user_id),
                    rerank=self._rerank,
                    top_k=5,
                    keyword_search=self._keyword_search,
                )
                rows = _normalize_memory_rows(raw)
                if rows:
                    lines = [r.get("memory", "") for r in rows if r.get("memory")]
                    with self._prefetch_lock:
                        self._prefetch_result = "\n".join(f"- {l}" for l in lines)
                self._record_success()
            except Exception as e:
                self._record_failure()
                logger.debug("Mem0 prefetch failed: %s", e)

        self._prefetch_thread = threading.Thread(target=_run, daemon=True, name="mem0-prefetch")
        self._prefetch_thread.start()

    def sync_turn(self, user_content: str, assistant_content: str, *, session_id: str = "") -> None:
        """Send the turn to Mem0 for server-side fact extraction (non-blocking)."""
        if self._is_breaker_open():
            return

        def _sync():
            try:
                client = self._get_client()
                messages = [
                    {"role": "user", "content": user_content},
                    {"role": "assistant", "content": assistant_content},
                ]
                client.add(messages, user_id=self._user_id, agent_id=self._agent_id)
                self._record_success()
            except Exception as e:
                self._record_failure()
                logger.warning("Mem0 sync failed: %s", e)

        # Wait for any previous sync before starting a new one
        if self._sync_thread and self._sync_thread.is_alive():
            self._sync_thread.join(timeout=5.0)

        self._sync_thread = threading.Thread(target=_sync, daemon=True, name="mem0-sync")
        self._sync_thread.start()

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        return list(MEM0_ALL_TOOL_SCHEMAS)

    def handle_tool_call(self, tool_name: str, args: dict, **kwargs) -> str:
        if self._is_breaker_open():
            return json.dumps({
                "error": "Mem0 API temporarily unavailable (multiple consecutive failures). Will retry automatically."
            })

        try:
            client = self._get_client()
        except Exception as e:
            return json.dumps({"error": str(e)})

        if tool_name == "mem0_profile":
            try:
                # v2 POST /v2/memories/ requires a top-level ``filters`` object
                # (not bare user_id). Same shape as mem0_search.
                raw = client.get_all(filters=_mem0_search_filters(self._user_id))
                self._record_success()
                memories = _normalize_memory_rows(raw)
                if not memories:
                    return json.dumps({"result": "No memories stored yet."})
                lines = [m.get("memory", "") for m in memories if m.get("memory")]
                return json.dumps({"result": "\n".join(lines), "count": len(lines)})
            except Exception as e:
                self._record_failure()
                return json.dumps({"error": f"Failed to fetch profile: {e}"})

        elif tool_name == "mem0_search":
            query = args.get("query", "")
            if not query:
                return json.dumps({"error": "Missing required parameter: query"})
            rerank = args.get("rerank", False)
            top_k = min(int(args.get("top_k", 10)), 50)
            try:
                raw = client.search(
                    query,
                    filters=_mem0_search_filters(self._user_id),
                    rerank=rerank,
                    top_k=top_k,
                    keyword_search=self._keyword_search,
                )
                self._record_success()
                rows = _normalize_memory_rows(raw)
                if not rows:
                    return json.dumps({"result": "No relevant memories found."})
                items = [
                    {"memory": r.get("memory", ""), "score": r.get("score", 0)}
                    for r in rows
                ]
                return json.dumps({"results": items, "count": len(items)})
            except Exception as e:
                self._record_failure()
                return json.dumps({"error": f"Search failed: {e}"})

        elif tool_name == "mem0_conclude":
            conclusion = args.get("conclusion", "")
            if not conclusion:
                return json.dumps({"error": "Missing required parameter: conclusion"})
            try:
                client.add(
                    [{"role": "user", "content": conclusion}],
                    user_id=self._user_id,
                    agent_id=self._agent_id,
                    infer=False,
                )
                self._record_success()
                return json.dumps({"result": "Fact stored."})
            except Exception as e:
                self._record_failure()
                return json.dumps({"error": f"Failed to store: {e}"})

        elif tool_name == "mem0_add_memory":
            msgs = args.get("messages")
            content = (args.get("content") or "").strip()
            infer = bool(args.get("infer", True))
            if msgs is not None:
                if not isinstance(msgs, list) or not msgs:
                    return json.dumps({"error": "messages must be a non-empty list"})
                messages_input: Any = msgs
            elif content:
                messages_input = content
            else:
                return json.dumps({"error": "Provide content or messages"})
            try:
                raw = client.add(
                    messages_input,
                    user_id=self._user_id,
                    agent_id=self._agent_id,
                    infer=infer,
                )
                self._record_success()
                return _json_response(raw)
            except Exception as e:
                self._record_failure()
                return json.dumps({"error": f"add_memory failed: {e}"})

        elif tool_name == "mem0_get_memories":
            page = int(args.get("page") or 1)
            page_size = min(max(int(args.get("page_size") or 50), 1), 100)
            try:
                raw = client.get_all(
                    filters=_mem0_search_filters(self._user_id),
                    page=page,
                    page_size=page_size,
                )
                self._record_success()
                return _json_response(raw)
            except Exception as e:
                self._record_failure()
                return json.dumps({"error": f"get_memories failed: {e}"})

        elif tool_name == "mem0_get_memory":
            mid = (args.get("memory_id") or "").strip()
            if not mid:
                return json.dumps({"error": "memory_id required"})
            try:
                raw = client.get(mid)
                self._record_success()
                return _json_response(raw)
            except Exception as e:
                self._record_failure()
                return json.dumps({"error": f"get_memory failed: {e}"})

        elif tool_name == "mem0_update_memory":
            mid = (args.get("memory_id") or "").strip()
            if not mid:
                return json.dumps({"error": "memory_id required"})
            text = args.get("text")
            metadata = args.get("metadata")
            if isinstance(metadata, str) and metadata.strip():
                try:
                    metadata = json.loads(metadata)
                except json.JSONDecodeError:
                    return json.dumps({"error": "metadata must be JSON object or object"})
            timestamp = args.get("timestamp")
            if text is None and metadata is None and timestamp is None:
                return json.dumps(
                    {"error": "Provide at least one of text, metadata, timestamp"}
                )
            try:
                raw = client.update(
                    mid,
                    text=text,
                    metadata=metadata if isinstance(metadata, dict) else None,
                    timestamp=timestamp,
                )
                self._record_success()
                return _json_response(raw)
            except Exception as e:
                self._record_failure()
                return json.dumps({"error": f"update_memory failed: {e}"})

        elif tool_name == "mem0_delete_memory":
            mid = (args.get("memory_id") or "").strip()
            if not mid:
                return json.dumps({"error": "memory_id required"})
            try:
                raw = client.delete(mid)
                self._record_success()
                return _json_response(raw)
            except Exception as e:
                self._record_failure()
                return json.dumps({"error": f"delete_memory failed: {e}"})

        elif tool_name == "mem0_delete_all_memories":
            if (args.get("confirm") or "").strip() != _DELETE_ALL_CONFIRM:
                return json.dumps(
                    {
                        "error": "Refused: set confirm to the exact string "
                        f"{_DELETE_ALL_CONFIRM!r} (deletes all memories for this user_id)."
                    }
                )
            try:
                raw = client.delete_all(user_id=self._user_id)
                self._record_success()
                return _json_response(raw)
            except Exception as e:
                self._record_failure()
                return json.dumps({"error": f"delete_all_memories failed: {e}"})

        elif tool_name == "mem0_list_entities":
            try:
                raw = client.users()
                self._record_success()
                return _json_response(raw)
            except Exception as e:
                self._record_failure()
                return json.dumps({"error": f"list_entities failed: {e}"})

        elif tool_name == "mem0_delete_entities":
            uid = (args.get("user_id") or "").strip()
            aid = (args.get("agent_id") or "").strip()
            app_id = (args.get("app_id") or "").strip()
            run_id = (args.get("run_id") or "").strip()
            if app_id or run_id:
                return json.dumps(
                    {"error": "Deleting app_id/run_id from Hermes is disabled; use user_id or agent_id."}
                )
            if uid and uid != self._user_id:
                return json.dumps(
                    {"error": f"user_id must match configured Mem0 user ({self._user_id!r})."}
                )
            if aid and aid != self._agent_id:
                return json.dumps(
                    {"error": f"agent_id must match configured Mem0 agent ({self._agent_id!r})."}
                )
            if not uid and not aid:
                return json.dumps(
                    {"error": "Provide user_id or agent_id matching this Hermes Mem0 scope."}
                )
            try:
                if uid:
                    raw = client.delete_users(user_id=uid)
                else:
                    raw = client.delete_users(agent_id=aid)
                self._record_success()
                return _json_response(raw)
            except Exception as e:
                self._record_failure()
                return json.dumps({"error": f"delete_entities failed: {e}"})

        elif tool_name == "mem0_memory_history":
            mid = (args.get("memory_id") or "").strip()
            if not mid:
                return json.dumps({"error": "memory_id required"})
            try:
                raw = client.history(mid)
                self._record_success()
                return _json_response(raw)
            except Exception as e:
                self._record_failure()
                return json.dumps({"error": f"memory_history failed: {e}"})

        elif tool_name == "mem0_feedback":
            mid = (args.get("memory_id") or "").strip()
            fb = (args.get("feedback") or "").strip()
            reason = args.get("feedback_reason")
            if not mid or not fb:
                return json.dumps({"error": "memory_id and feedback required"})
            try:
                raw = client.feedback(
                    mid, feedback=fb, feedback_reason=reason
                )
                self._record_success()
                return _json_response(raw)
            except Exception as e:
                self._record_failure()
                return json.dumps({"error": f"feedback failed: {e}"})

        elif tool_name == "mem0_batch_update_memories":
            memories = args.get("memories")
            if not isinstance(memories, list) or not memories:
                return json.dumps({"error": "memories must be a non-empty list"})
            for i, m in enumerate(memories):
                if not isinstance(m, dict) or not m.get("memory_id"):
                    return json.dumps(
                        {"error": f"memories[{i}] must be an object with memory_id"}
                    )
            try:
                raw = client.batch_update(memories)
                self._record_success()
                return _json_response(raw)
            except Exception as e:
                self._record_failure()
                return json.dumps({"error": f"batch_update failed: {e}"})

        elif tool_name == "mem0_batch_delete_memories":
            ids = args.get("memory_ids")
            if not isinstance(ids, list) or not ids:
                return json.dumps({"error": "memory_ids must be a non-empty list"})
            payload = [{"memory_id": str(x)} for x in ids if x]
            if len(payload) != len(ids):
                return json.dumps({"error": "memory_ids must be non-empty strings"})
            try:
                raw = client.batch_delete(payload)
                self._record_success()
                return _json_response(raw)
            except Exception as e:
                self._record_failure()
                return json.dumps({"error": f"batch_delete failed: {e}"})

        return json.dumps({"error": f"Unknown tool: {tool_name}"})

    def shutdown(self) -> None:
        for t in (self._prefetch_thread, self._sync_thread):
            if t and t.is_alive():
                t.join(timeout=5.0)
        with self._client_lock:
            self._client = None


def register(ctx) -> None:
    """Register Mem0 as a memory provider plugin."""
    ctx.register_memory_provider(Mem0MemoryProvider())
