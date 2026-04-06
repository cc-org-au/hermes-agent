"""Mem0 memory plugin — MemoryProvider interface.

Server-side LLM fact extraction, semantic search with reranking, and
automatic deduplication via the Mem0 Platform API.

Original PR #2933 by kartik-mem0, adapted to MemoryProvider ABC.

Config via environment variables:
  MEM0_API_KEY       — Mem0 Platform API key (required)
  MEM0_USER_ID       — User identifier (default: hermes-user)
  MEM0_AGENT_ID      — Agent identifier (default: hermes)

Or via $HERMES_HOME/mem0.json.

Optional for org/project APIs, webhooks, and ``client.project``: ``org_id``, ``project_id``
(env: ``MEM0_ORG_ID``, ``MEM0_PROJECT_ID``).
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

# Required exact strings for destructive Mem0 operations.
_DELETE_ALL_CONFIRM = "YES_DELETE_ALL_MY_MEM0_MEMORIES"
_RESET_ACCOUNT_CONFIRM = "YES_RESET_ENTIRE_MEM0_ACCOUNT"
_DELETE_PROJECT_CONFIRM = "YES_DELETE_MEM0_PROJECT"

# Request body field for MemoryClient.add (SDK still POSTs to /v1/memories/).
_MEM0_ADD_API_VERSION = "v2"


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
        "org_id": os.environ.get("MEM0_ORG_ID", ""),
        "project_id": os.environ.get("MEM0_PROJECT_ID", ""),
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
                if not (merged.get("org_id") or "").strip():
                    merged["org_id"] = defaults["org_id"]
                if not (merged.get("project_id") or "").strip():
                    merged["project_id"] = defaults["project_id"]
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
        "project context. Fast, no reranking. Use at conversation start. "
        "Uses Mem0 v2 list (POST /v2/memories/) with filters scoped to the "
        "configured Mem0 user_id — do not reimplement this with raw HTTP."
    ),
    "parameters": {"type": "object", "properties": {}, "required": []},
}

SEARCH_SCHEMA = {
    "name": "mem0_search",
    "description": (
        "Search memories by meaning (Mem0 v2 search API). Returns relevant facts ranked "
        "by similarity. Filters are applied automatically for the configured user scope. "
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
        "Uses the same Mem0 add path as mem0_add_memory (SDK POST /v1/memories/) with "
        "infer=false; Hermes supplies user_id and agent_id from mem0.json — do not call "
        "Mem0 REST manually."
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
        "Add memory via Mem0 Platform (official mem0ai SDK: POST /v1/memories/, not v2 list). "
        "Sends text or conversation messages; with infer=true Mem0 runs server-side extraction "
        "and deduplication. Hermes always passes user_id and agent_id from mem0.json — you "
        "only provide content/messages/infer. For a single verbatim fact use mem0_conclude. "
        "Do not use curl or POST /v2/memories/ to add; v2 is for listing/search with filters."
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
        "List memories with v2 filters and pagination (POST /v2/memories/). Hermes injects "
        "the required filter scope (user_id). If you see errors about filters requiring "
        "user_id/agent_id/app_id/run_id, you likely bypassed this tool with a raw v2 request."
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

RESET_ACCOUNT_SCHEMA = {
    "name": "mem0_reset_account",
    "description": (
        "Nuclear: MemoryClient.reset() — deletes all entities and memories for the API key. "
        f"confirm must be exactly {_RESET_ACCOUNT_CONFIRM!r}."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "confirm": {"type": "string"},
        },
        "required": ["confirm"],
    },
}

CREATE_EXPORT_SCHEMA = {
    "name": "mem0_create_memory_export",
    "description": "Start a structured memory export (JSON schema string + optional filters).",
    "parameters": {
        "type": "object",
        "properties": {
            "schema": {
                "type": "string",
                "description": "JSON schema string for export shape.",
            },
            "user_id": {
                "type": "string",
                "description": "Optional; defaults to configured Mem0 user_id.",
            },
        },
        "required": ["schema"],
    },
}

GET_EXPORT_SCHEMA = {
    "name": "mem0_get_memory_export",
    "description": "Retrieve export payload (POST /v1/exports/get/). Optional filters.",
    "parameters": {
        "type": "object",
        "properties": {
            "filters": {
                "type": "object",
                "description": "Optional filter object; user_id defaults to configured user if omitted.",
            },
        },
        "required": [],
    },
}

EXPORT_SUMMARY_SCHEMA = {
    "name": "mem0_get_memory_export_summary",
    "description": "Summary/status for a memory export (MemoryClient.get_summary).",
    "parameters": {
        "type": "object",
        "properties": {
            "filters": {"type": "object", "description": "Optional filters dict."},
        },
        "required": [],
    },
}

GET_WEBHOOKS_SCHEMA = {
    "name": "mem0_get_webhooks",
    "description": "List webhooks for a Mem0 project_id (must match configured project when set).",
    "parameters": {
        "type": "object",
        "properties": {
            "project_id": {"type": "string"},
        },
        "required": ["project_id"],
    },
}

CREATE_WEBHOOK_SCHEMA = {
    "name": "mem0_create_webhook",
    "description": "Create a Mem0 project webhook.",
    "parameters": {
        "type": "object",
        "properties": {
            "project_id": {"type": "string"},
            "url": {"type": "string"},
            "name": {"type": "string"},
            "event_types": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Event type strings per Mem0 API.",
            },
        },
        "required": ["project_id", "url", "name", "event_types"],
    },
}

UPDATE_WEBHOOK_SCHEMA = {
    "name": "mem0_update_webhook",
    "description": "Update webhook by numeric id.",
    "parameters": {
        "type": "object",
        "properties": {
            "webhook_id": {"type": "integer"},
            "name": {"type": "string"},
            "url": {"type": "string"},
            "event_types": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["webhook_id"],
    },
}

DELETE_WEBHOOK_SCHEMA = {
    "name": "mem0_delete_webhook",
    "description": "Delete webhook by numeric id.",
    "parameters": {
        "type": "object",
        "properties": {"webhook_id": {"type": "integer"}},
        "required": ["webhook_id"],
    },
}

PROJECT_GET_SCHEMA = {
    "name": "mem0_project_get",
    "description": "Get current Mem0 project settings (client.project.get). Requires org_id+project_id in mem0.json.",
    "parameters": {
        "type": "object",
        "properties": {
            "fields": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional field names to return.",
            },
        },
        "required": [],
    },
}

PROJECT_UPDATE_SCHEMA = {
    "name": "mem0_project_update",
    "description": "Update project via client.project.update (instructions, categories, graph, etc.).",
    "parameters": {
        "type": "object",
        "properties": {
            "custom_instructions": {"type": "string"},
            "custom_categories": {"type": "array", "items": {"type": "string"}},
            "retrieval_criteria": {"type": "array", "items": {"type": "object"}},
            "enable_graph": {"type": "boolean"},
            "multilingual": {"type": "boolean"},
        },
        "required": [],
    },
}

PROJECT_CREATE_SCHEMA = {
    "name": "mem0_project_create",
    "description": "Create a new project under the configured org (client.project.create).",
    "parameters": {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "description": {"type": "string"},
        },
        "required": ["name"],
    },
}

PROJECT_DELETE_SCHEMA = {
    "name": "mem0_project_delete",
    "description": (
        "Delete the configured Mem0 project. "
        f"confirm must be {_DELETE_PROJECT_CONFIRM!r}."
    ),
    "parameters": {
        "type": "object",
        "properties": {"confirm": {"type": "string"}},
        "required": ["confirm"],
    },
}

PROJECT_MEMBERS_SCHEMA = {
    "name": "mem0_project_members",
    "description": "List members of the current Mem0 project.",
    "parameters": {"type": "object", "properties": {}, "required": []},
}

PROJECT_MEMBER_ADD_SCHEMA = {
    "name": "mem0_project_member_add",
    "description": "Add a project member by email.",
    "parameters": {
        "type": "object",
        "properties": {
            "email": {"type": "string"},
            "role": {
                "type": "string",
                "description": "Default READER if omitted.",
            },
        },
        "required": ["email"],
    },
}

PROJECT_MEMBER_UPDATE_SCHEMA = {
    "name": "mem0_project_member_update",
    "description": "Change a project member's role.",
    "parameters": {
        "type": "object",
        "properties": {
            "email": {"type": "string"},
            "role": {"type": "string"},
        },
        "required": ["email", "role"],
    },
}

PROJECT_MEMBER_REMOVE_SCHEMA = {
    "name": "mem0_project_member_remove",
    "description": "Remove a project member by email.",
    "parameters": {
        "type": "object",
        "properties": {"email": {"type": "string"}},
        "required": ["email"],
    },
}

LEGACY_PROJECT_GET_SCHEMA = {
    "name": "mem0_legacy_project_get",
    "description": (
        "Deprecated MemoryClient.get_project — use mem0_project_get when possible. "
        "Requires org_id and project_id on the client."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "fields": {"type": "array", "items": {"type": "string"}},
        },
        "required": [],
    },
}

LEGACY_PROJECT_UPDATE_SCHEMA = {
    "name": "mem0_legacy_project_update",
    "description": (
        "Deprecated MemoryClient.update_project with extended fields "
        "(version, inclusion_prompt, memory_depth, …). Requires org_id+project_id."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "custom_instructions": {"type": "string"},
            "custom_categories": {"type": "array", "items": {"type": "string"}},
            "retrieval_criteria": {"type": "array", "items": {"type": "object"}},
            "enable_graph": {"type": "boolean"},
            "version": {"type": "string"},
            "inclusion_prompt": {"type": "string"},
            "exclusion_prompt": {"type": "string"},
            "memory_depth": {"type": "string"},
            "usecase_setting": {"type": "string"},
            "multilingual": {"type": "boolean"},
        },
        "required": [],
    },
}

CHAT_STUB_SCHEMA = {
    "name": "mem0_chat",
    "description": (
        "MemoryClient.chat is not implemented in the Mem0 SDK. Calling returns an error "
        "explaining to use other mem0_* tools."
    ),
    "parameters": {"type": "object", "properties": {}, "required": []},
}

MEM0_ASYNC_INVOKE_SCHEMA = {
    "name": "mem0_async_invoke",
    "description": (
        "Run one Mem0 Platform call via AsyncMemoryClient (async HTTP, fresh client per call). "
        "Pass operation (snake_case) and arguments object — same fields as the matching sync mem0_* tool. "
        "Operations: add, get, get_all, search, update, delete, delete_all, history, users, "
        "list_entities (alias users), delete_users, reset, batch_update, batch_delete, "
        "create_memory_export, get_memory_export, get_summary, get_webhooks, create_webhook, "
        "update_webhook, delete_webhook, get_project, legacy_get_project, update_project, "
        "legacy_update_project, project_get, project_update, project_create, project_delete, "
        "project_members, project_get_members, project_member_add, project_add_member, "
        "project_member_update, project_update_member, project_member_remove, project_remove_member. "
        "Same confirm strings as sync for delete_all, reset, project_delete. "
        "chat is not supported (returns error). "
        "Operation add uses the SDK add path (v1 /v1/memories/); get_all/search use v2 with filters."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "description": "Async Mem0 operation name (snake_case), e.g. search, add, project_get.",
            },
            "arguments": {
                "type": "object",
                "description": "Parameters for that operation (object). Omit or {} if none.",
            },
        },
        "required": ["operation"],
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
    RESET_ACCOUNT_SCHEMA,
    CREATE_EXPORT_SCHEMA,
    GET_EXPORT_SCHEMA,
    EXPORT_SUMMARY_SCHEMA,
    GET_WEBHOOKS_SCHEMA,
    CREATE_WEBHOOK_SCHEMA,
    UPDATE_WEBHOOK_SCHEMA,
    DELETE_WEBHOOK_SCHEMA,
    PROJECT_GET_SCHEMA,
    PROJECT_UPDATE_SCHEMA,
    PROJECT_CREATE_SCHEMA,
    PROJECT_DELETE_SCHEMA,
    PROJECT_MEMBERS_SCHEMA,
    PROJECT_MEMBER_ADD_SCHEMA,
    PROJECT_MEMBER_UPDATE_SCHEMA,
    PROJECT_MEMBER_REMOVE_SCHEMA,
    LEGACY_PROJECT_GET_SCHEMA,
    LEGACY_PROJECT_UPDATE_SCHEMA,
    CHAT_STUB_SCHEMA,
    MEM0_ASYNC_INVOKE_SCHEMA,
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
        self._org_id = ""
        self._project_id = ""
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
            {"key": "org_id", "description": "Mem0 organization id (project/webhook APIs)", "env_var": "MEM0_ORG_ID"},
            {"key": "project_id", "description": "Mem0 project id (project/webhook APIs)", "env_var": "MEM0_PROJECT_ID"},
            {"key": "rerank", "description": "Enable reranking for recall", "default": "true", "choices": ["true", "false"]},
        ]

    def _get_client(self):
        """Thread-safe client accessor with lazy initialization."""
        with self._client_lock:
            if self._client is not None:
                return self._client
            try:
                from mem0 import MemoryClient

                kw: Dict[str, Any] = {"api_key": self._api_key}
                if self._org_id:
                    kw["org_id"] = self._org_id
                if self._project_id:
                    kw["project_id"] = self._project_id
                self._client = MemoryClient(**kw)
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
        self._org_id = (self._config.get("org_id") or "").strip()
        self._project_id = (self._config.get("project_id") or "").strip()
        self._rerank = self._config.get("rerank", True)
        self._keyword_search = self._config.get("keyword_search", False)

    def system_prompt_block(self) -> str:
        _names = ", ".join(s["name"] for s in MEM0_ALL_TOOL_SCHEMAS)
        _scope = f"user_id={self._user_id}, agent_id={self._agent_id}"
        if self._org_id and self._project_id:
            _scope += f", org_id={self._org_id}, project_id={self._project_id}"
        if not (self._api_key or "").strip():
            return (
                "# Mem0 Memory (Platform API)\n"
                "**Not connected:** `memory.provider` is mem0 but no API key was loaded. "
                "Set `MEM0_API_KEY` in the active profile `.env` or `api_key` in "
                "`mem0.json` under HERMES_HOME. The mem0_* tool names are still valid; "
                "each call will return this error until the key is present.\n"
                f"Tool names: {_names}."
            )
        return (
            "# Mem0 Memory (Platform API)\n"
            f"Active. {_scope}.\n"
            f"Tools: {_names}.\n"
            "## How to use (read this)\n"
            "- Use **only** these `mem0_*` tools (official mem0ai SDK). Do **not** call Mem0 with "
            "`curl`, browser, or guessed URLs.\n"
            "- **Add** facts: `mem0_add_memory` (content or messages; optional infer) or "
            "`mem0_conclude` (verbatim, infer off). The SDK uses **POST /v1/memories/** with "
            "`user_id` and `agent_id` taken from the Active line above — you do **not** set them "
            "in tool args unless a tool explicitly allows overrides.\n"
            "- **List / search**: `mem0_profile`, `mem0_get_memories`, `mem0_search` use Mem0 **v2** "
            "list/search and supply **filters** automatically. The error "
            "`One of the filters: app_id, user_id, agent_id, run_id is required` means a **v2** "
            "request was sent **without** that scope (often from raw **POST /v2/memories/**). "
            "Fix: use the tools above, not manual REST.\n"
            "- **Hermes profile** name (e.g. chief-orchestrator) is **not** the Mem0 `user_id` "
            "unless you set `user_id` that way in `mem0.json`.\n"
            "Includes export/summary, webhooks, project APIs, reset, mem0_async_invoke, "
            "mem0_chat (stub).\n"
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
        if self._is_breaker_open() or not (self._api_key or "").strip():
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
        if self._is_breaker_open() or not (self._api_key or "").strip():
            return

        def _sync():
            try:
                client = self._get_client()
                messages = [
                    {"role": "user", "content": user_content},
                    {"role": "assistant", "content": assistant_content},
                ]
                client.add(
                    messages,
                    user_id=self._user_id,
                    agent_id=self._agent_id,
                    version=_MEM0_ADD_API_VERSION,
                )
                self._record_success()
            except Exception as e:
                self._record_failure()
                logger.warning("Mem0 sync failed: %s", e)

        # Wait for any previous sync before starting a new one
        if self._sync_thread and self._sync_thread.is_alive():
            self._sync_thread.join(timeout=5.0)

        self._sync_thread = threading.Thread(target=_sync, daemon=True, name="mem0-sync")
        self._sync_thread.start()

    def _effective_org_id(self, client: Any) -> str:
        return (getattr(client, "org_id", None) or self._org_id or "").strip()

    def _effective_project_id(self, client: Any) -> str:
        return (getattr(client, "project_id", None) or self._project_id or "").strip()

    def _require_org_project_json(self, client: Any) -> str | None:
        if not self._effective_org_id(client) or not self._effective_project_id(client):
            return json.dumps({
                "error": (
                    "org_id and project_id are required (mem0.json / MEM0_ORG_ID / "
                    "MEM0_PROJECT_ID, or as returned by Mem0 after API key validation)."
                ),
            })
        return None

    def _require_org_json(self, client: Any) -> str | None:
        if not self._effective_org_id(client):
            return json.dumps(
                {
                    "error": (
                        "org_id required (mem0.json / MEM0_ORG_ID, or from Mem0 after "
                        "API key validation)."
                    ),
                }
            )
        return None

    def _webhook_project_guard(self, client: Any, project_id: str) -> str | None:
        pid = (project_id or "").strip()
        if not pid:
            return json.dumps({"error": "project_id required"})
        cfg_pid = self._effective_project_id(client)
        if cfg_pid and pid != cfg_pid:
            return json.dumps({
                "error": f"project_id must match active Mem0 project ({cfg_pid!r}).",
            })
        return None

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        return list(MEM0_ALL_TOOL_SCHEMAS)

    def _asyncio_run_mem0(self, coro):
        """Run async Mem0 client code from sync handle_tool_call (thread if loop already running)."""
        import asyncio
        import concurrent.futures

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            return ex.submit(asyncio.run, coro).result(timeout=600)

    def _handle_mem0_async_invoke(self, args: dict) -> str:
        from plugins.memory.mem0.async_dispatch import mem0_async_dispatch

        op = (args.get("operation") or "").strip().lower().replace("-", "_")
        raw = args.get("arguments")
        a = raw if isinstance(raw, dict) else {}

        if op == "chat":
            return json.dumps(
                {
                    "error": (
                        "MemoryClient.chat / AsyncMemoryClient.chat is not implemented in the mem0ai SDK. "
                        "Use mem0_search, mem0_add_memory, or mem0_async_invoke with search/add/get_all, etc."
                    )
                }
            )

        if not (self._api_key or "").strip():
            return json.dumps(
                {
                    "error": (
                        "Mem0 API key is not configured. Set MEM0_API_KEY in the Hermes profile "
                        "`.env` (or top-level `~/.hermes/.env`) or add `api_key` to `mem0.json` "
                        "under HERMES_HOME, then restart the gateway if needed."
                    )
                }
            )

        async def _runner():
            from mem0 import AsyncMemoryClient

            kw: Dict[str, Any] = {"api_key": self._api_key}
            if self._org_id:
                kw["org_id"] = self._org_id
            if self._project_id:
                kw["project_id"] = self._project_id
            async with AsyncMemoryClient(**kw) as acl:
                return await mem0_async_dispatch(self, acl, op, a)

        try:
            raw_out = self._asyncio_run_mem0(_runner())
        except ImportError:
            return json.dumps(
                {"error": "mem0 package not installed. Run: pip install mem0ai"}
            )
        except ValueError as e:
            return json.dumps({"error": str(e)})
        except Exception as e:
            self._record_failure()
            return json.dumps({"error": f"mem0_async_invoke failed: {e}"})
        self._record_success()
        return _json_response(raw_out)

    def handle_tool_call(self, tool_name: str, args: dict, **kwargs) -> str:
        if self._is_breaker_open():
            return json.dumps({
                "error": "Mem0 API temporarily unavailable (multiple consecutive failures). Will retry automatically."
            })

        # Async invoke first: operation "chat" is a stub and does not need an API key.
        if tool_name == "mem0_async_invoke":
            return self._handle_mem0_async_invoke(args)

        if not (self._api_key or "").strip():
            return json.dumps(
                {
                    "error": (
                        "Mem0 API key is not configured. Set MEM0_API_KEY in the Hermes profile "
                        "`.env` (or top-level `~/.hermes/.env`) or add `api_key` to `mem0.json` "
                        "under HERMES_HOME, then restart the gateway if needed."
                    )
                }
            )

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
                    version=_MEM0_ADD_API_VERSION,
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
                    version=_MEM0_ADD_API_VERSION,
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

        elif tool_name == "mem0_reset_account":
            if (args.get("confirm") or "").strip() != _RESET_ACCOUNT_CONFIRM:
                return json.dumps(
                    {"error": f"confirm must be exactly {_RESET_ACCOUNT_CONFIRM!r}"}
                )
            try:
                raw = client.reset()
                self._record_success()
                return _json_response(raw)
            except Exception as e:
                self._record_failure()
                return json.dumps({"error": f"reset_account failed: {e}"})

        elif tool_name == "mem0_create_memory_export":
            schema = args.get("schema")
            if not isinstance(schema, str) or not schema.strip():
                return json.dumps({"error": "schema must be a non-empty string (JSON schema text)"})
            uid = (args.get("user_id") or "").strip() or self._user_id
            try:
                raw = client.create_memory_export(schema, user_id=uid)
                self._record_success()
                return _json_response(raw)
            except Exception as e:
                self._record_failure()
                return json.dumps({"error": f"create_memory_export failed: {e}"})

        elif tool_name == "mem0_get_memory_export":
            filters = args.get("filters")
            if filters is None:
                filters = {}
            if not isinstance(filters, dict):
                return json.dumps({"error": "filters must be an object"})
            body = dict(filters)
            if "user_id" not in body:
                body["user_id"] = self._user_id
            try:
                raw = client.get_memory_export(**body)
                self._record_success()
                return _json_response(raw)
            except Exception as e:
                self._record_failure()
                return json.dumps({"error": f"get_memory_export failed: {e}"})

        elif tool_name == "mem0_get_memory_export_summary":
            filters = args.get("filters")
            if filters is not None and not isinstance(filters, dict):
                return json.dumps({"error": "filters must be an object or omitted"})
            try:
                raw = client.get_summary(
                    filters if isinstance(filters, dict) else None
                )
                self._record_success()
                return _json_response(raw)
            except Exception as e:
                self._record_failure()
                return json.dumps({"error": f"get_memory_export_summary failed: {e}"})

        elif tool_name == "mem0_get_webhooks":
            pid = args.get("project_id", "")
            wg = self._webhook_project_guard(client, str(pid))
            if wg:
                return wg
            try:
                raw = client.get_webhooks(str(pid).strip())
                self._record_success()
                return _json_response(raw)
            except Exception as e:
                self._record_failure()
                return json.dumps({"error": f"get_webhooks failed: {e}"})

        elif tool_name == "mem0_create_webhook":
            pid = str(args.get("project_id") or "")
            wg = self._webhook_project_guard(client, pid)
            if wg:
                return wg
            url = (args.get("url") or "").strip()
            name = (args.get("name") or "").strip()
            ev = args.get("event_types")
            if not url or not name:
                return json.dumps({"error": "url and name required"})
            if not isinstance(ev, list) or not ev:
                return json.dumps({"error": "event_types must be a non-empty array"})
            try:
                raw = client.create_webhook(url, name, pid.strip(), ev)
                self._record_success()
                return _json_response(raw)
            except Exception as e:
                self._record_failure()
                return json.dumps({"error": f"create_webhook failed: {e}"})

        elif tool_name == "mem0_update_webhook":
            wid = args.get("webhook_id")
            if wid is None:
                return json.dumps({"error": "webhook_id required"})
            try:
                w_int = int(wid)
            except (TypeError, ValueError):
                return json.dumps({"error": "webhook_id must be an integer"})
            et = args.get("event_types")
            try:
                raw = client.update_webhook(
                    w_int,
                    name=args.get("name"),
                    url=args.get("url"),
                    event_types=et if isinstance(et, list) else None,
                )
                self._record_success()
                return _json_response(raw)
            except Exception as e:
                self._record_failure()
                return json.dumps({"error": f"update_webhook failed: {e}"})

        elif tool_name == "mem0_delete_webhook":
            wid = args.get("webhook_id")
            if wid is None:
                return json.dumps({"error": "webhook_id required"})
            try:
                w_int = int(wid)
            except (TypeError, ValueError):
                return json.dumps({"error": "webhook_id must be an integer"})
            try:
                raw = client.delete_webhook(w_int)
                self._record_success()
                return _json_response(raw)
            except Exception as e:
                self._record_failure()
                return json.dumps({"error": f"delete_webhook failed: {e}"})

        elif tool_name == "mem0_project_get":
            err = self._require_org_project_json(client)
            if err:
                return err
            fields = args.get("fields")
            flist = fields if isinstance(fields, list) else None
            try:
                raw = client.project.get(fields=flist)
                self._record_success()
                return _json_response(raw)
            except Exception as e:
                self._record_failure()
                return json.dumps({"error": f"project_get failed: {e}"})

        elif tool_name == "mem0_project_update":
            err = self._require_org_project_json(client)
            if err:
                return err
            keys = (
                "custom_instructions",
                "custom_categories",
                "retrieval_criteria",
                "enable_graph",
                "multilingual",
            )
            kw = {k: args[k] for k in keys if k in args}
            if not kw:
                return json.dumps({"error": "Provide at least one field to update"})
            try:
                raw = client.project.update(**kw)
                self._record_success()
                return _json_response(raw)
            except Exception as e:
                self._record_failure()
                return json.dumps({"error": f"project_update failed: {e}"})

        elif tool_name == "mem0_project_create":
            err = self._require_org_json(client)
            if err:
                return err
            name = (args.get("name") or "").strip()
            if not name:
                return json.dumps({"error": "name required"})
            try:
                raw = client.project.create(name, description=args.get("description"))
                self._record_success()
                return _json_response(raw)
            except Exception as e:
                self._record_failure()
                return json.dumps({"error": f"project_create failed: {e}"})

        elif tool_name == "mem0_project_delete":
            err = self._require_org_project_json(client)
            if err:
                return err
            if (args.get("confirm") or "").strip() != _DELETE_PROJECT_CONFIRM:
                return json.dumps(
                    {"error": f"confirm must be exactly {_DELETE_PROJECT_CONFIRM!r}"}
                )
            try:
                raw = client.project.delete()
                self._record_success()
                return _json_response(raw)
            except Exception as e:
                self._record_failure()
                return json.dumps({"error": f"project_delete failed: {e}"})

        elif tool_name == "mem0_project_members":
            err = self._require_org_project_json(client)
            if err:
                return err
            try:
                raw = client.project.get_members()
                self._record_success()
                return _json_response(raw)
            except Exception as e:
                self._record_failure()
                return json.dumps({"error": f"project_members failed: {e}"})

        elif tool_name == "mem0_project_member_add":
            err = self._require_org_project_json(client)
            if err:
                return err
            email = (args.get("email") or "").strip()
            if not email:
                return json.dumps({"error": "email required"})
            role = (args.get("role") or "READER").strip().upper()
            try:
                raw = client.project.add_member(email, role=role)
                self._record_success()
                return _json_response(raw)
            except Exception as e:
                self._record_failure()
                return json.dumps({"error": f"project_member_add failed: {e}"})

        elif tool_name == "mem0_project_member_update":
            err = self._require_org_project_json(client)
            if err:
                return err
            email = (args.get("email") or "").strip()
            role = (args.get("role") or "").strip().upper()
            if not email or not role:
                return json.dumps({"error": "email and role required"})
            try:
                raw = client.project.update_member(email, role)
                self._record_success()
                return _json_response(raw)
            except Exception as e:
                self._record_failure()
                return json.dumps({"error": f"project_member_update failed: {e}"})

        elif tool_name == "mem0_project_member_remove":
            err = self._require_org_project_json(client)
            if err:
                return err
            email = (args.get("email") or "").strip()
            if not email:
                return json.dumps({"error": "email required"})
            try:
                raw = client.project.remove_member(email)
                self._record_success()
                return _json_response(raw)
            except Exception as e:
                self._record_failure()
                return json.dumps({"error": f"project_member_remove failed: {e}"})

        elif tool_name == "mem0_legacy_project_get":
            err = self._require_org_project_json(client)
            if err:
                return err
            fields = args.get("fields")
            flist = fields if isinstance(fields, list) else None
            try:
                raw = client.get_project(fields=flist)
                self._record_success()
                return _json_response(raw)
            except Exception as e:
                self._record_failure()
                return json.dumps({"error": f"legacy_project_get failed: {e}"})

        elif tool_name == "mem0_legacy_project_update":
            err = self._require_org_project_json(client)
            if err:
                return err
            legacy_keys = (
                "custom_instructions",
                "custom_categories",
                "retrieval_criteria",
                "enable_graph",
                "version",
                "inclusion_prompt",
                "exclusion_prompt",
                "memory_depth",
                "usecase_setting",
                "multilingual",
            )
            kw = {k: args[k] for k in legacy_keys if k in args}
            if not kw:
                return json.dumps({"error": "Provide at least one legacy field to update"})
            try:
                raw = client.update_project(**kw)
                self._record_success()
                return _json_response(raw)
            except Exception as e:
                self._record_failure()
                return json.dumps({"error": f"legacy_project_update failed: {e}"})

        elif tool_name == "mem0_chat":
            return json.dumps(
                {
                    "error": (
                        "MemoryClient.chat is not implemented in the mem0ai SDK. "
                        "Use mem0_search, mem0_add_memory, mem0_get_memory, etc."
                    )
                }
            )

        return json.dumps(
            {
                "error": (
                    f"Unrecognized Mem0 tool name {tool_name!r}. "
                    "Use the exact names from the tool list (e.g. mem0_list_entities, "
                    "mem0_delete_entities, mem0_get_memories, mem0_profile)."
                )
            }
        )

    def shutdown(self) -> None:
        for t in (self._prefetch_thread, self._sync_thread):
            if t and t.is_alive():
                t.join(timeout=5.0)
        with self._client_lock:
            self._client = None


def register(ctx) -> None:
    """Register Mem0 as a memory provider plugin."""
    ctx.register_memory_provider(Mem0MemoryProvider())
