"""Async Mem0 Platform dispatch for ``mem0_async_invoke``.

Runs ``AsyncMemoryClient`` inside ``async with`` per call (proper ``aclose``).
Validation mirrors sync tools (confirms, Hermes entity scope, webhook project guard).
"""

from __future__ import annotations

import json
from typing import Any, Dict


async def mem0_async_dispatch(
    provider: Any,
    client: Any,
    operation: str,
    arguments: Dict[str, Any],
) -> Any:
    """Execute one async Mem0 client or ``client.project`` operation."""
    from plugins.memory.mem0 import (
        _DELETE_ALL_CONFIRM,
        _DELETE_PROJECT_CONFIRM,
        _MEM0_ADD_API_VERSION,
        _RESET_ACCOUNT_CONFIRM,
        _mem0_search_filters,
    )

    op = (operation or "").strip().lower().replace("-", "_")
    a = dict(arguments or {})

    if op in ("chat",):
        raise ValueError(
            "AsyncMemoryClient.chat is not implemented in mem0ai. "
            "Use search, add, get_all, or other operations."
        )

    if op in ("list_entities",):
        op = "users"

    uid_scope = provider._user_id
    aid_scope = provider._agent_id

    def _eff_oid() -> str:
        return (getattr(client, "org_id", None) or provider._org_id or "").strip()

    def _eff_pid() -> str:
        return (getattr(client, "project_id", None) or provider._project_id or "").strip()

    def _need_org_project() -> None:
        if not _eff_oid() or not _eff_pid():
            raise ValueError(
                "org_id and project_id required (mem0.json / env or from Mem0 ping)."
            )

    def _need_org() -> None:
        if not _eff_oid():
            raise ValueError("org_id required (mem0.json / MEM0_ORG_ID or from Mem0 ping).")

    def _webhook_pid_ok(pid: str) -> None:
        p = (pid or "").strip()
        if not p:
            raise ValueError("project_id required")
        cfg = _eff_pid()
        if cfg and p != cfg:
            raise ValueError(f"project_id must match active Mem0 project ({cfg!r}).")

    def _filters() -> dict:
        return _mem0_search_filters(uid_scope)

    if op == "add":
        msgs = a.get("messages")
        content = (a.get("content") or "").strip()
        infer = bool(a.get("infer", True))
        if msgs is not None:
            if not isinstance(msgs, list) or not msgs:
                raise ValueError("messages must be a non-empty list")
            inp: Any = msgs
        elif content:
            inp = content
        else:
            raise ValueError("Provide content or messages")
        return await client.add(
            inp,
            user_id=uid_scope,
            agent_id=aid_scope,
            infer=infer,
            version=_MEM0_ADD_API_VERSION,
        )

    if op == "get":
        mid = (a.get("memory_id") or "").strip()
        if not mid:
            raise ValueError("memory_id required")
        return await client.get(mid)

    if op == "get_all":
        filters = a.get("filters") or _filters()
        page = int(a.get("page") or 1)
        ps = min(max(int(a.get("page_size") or 50), 1), 100)
        return await client.get_all(filters=filters, page=page, page_size=ps)

    if op == "search":
        query = (a.get("query") or "").strip()
        if not query:
            raise ValueError("query required")
        rerank = bool(a.get("rerank", False))
        top_k = min(int(a.get("top_k") or 10), 50)
        kw_search = bool(getattr(provider, "_keyword_search", False))
        return await client.search(
            query,
            filters=_filters(),
            rerank=rerank,
            top_k=top_k,
            keyword_search=kw_search,
        )

    if op == "update":
        mid = (a.get("memory_id") or "").strip()
        if not mid:
            raise ValueError("memory_id required")
        text = a.get("text")
        metadata = a.get("metadata")
        if isinstance(metadata, str) and metadata.strip():
            try:
                metadata = json.loads(metadata)
            except json.JSONDecodeError:
                raise ValueError("metadata must be JSON object or object") from None
        ts = a.get("timestamp")
        if text is None and metadata is None and ts is None:
            raise ValueError("Provide at least one of text, metadata, timestamp")
        return await client.update(
            mid,
            text=text,
            metadata=metadata if isinstance(metadata, dict) else None,
            timestamp=ts,
        )

    if op == "delete":
        mid = (a.get("memory_id") or "").strip()
        if not mid:
            raise ValueError("memory_id required")
        return await client.delete(mid)

    if op == "delete_all":
        if (a.get("confirm") or "").strip() != _DELETE_ALL_CONFIRM:
            raise ValueError(
                "Refused: set confirm to the exact string "
                f"{_DELETE_ALL_CONFIRM!r} (deletes all memories for this user_id)."
            )
        return await client.delete_all(user_id=uid_scope)

    if op == "history":
        mid = (a.get("memory_id") or "").strip()
        if not mid:
            raise ValueError("memory_id required")
        return await client.history(mid)

    if op == "users":
        return await client.users()

    if op == "delete_users":
        u = (a.get("user_id") or "").strip()
        ag = (a.get("agent_id") or "").strip()
        app_id = (a.get("app_id") or "").strip()
        run_id = (a.get("run_id") or "").strip()
        if app_id or run_id:
            raise ValueError("app_id/run_id not allowed from Hermes; use user_id or agent_id.")
        if u and u != uid_scope:
            raise ValueError(f"user_id must match configured user ({uid_scope!r}).")
        if ag and ag != aid_scope:
            raise ValueError(f"agent_id must match configured agent ({aid_scope!r}).")
        if not u and not ag:
            raise ValueError("Provide user_id or agent_id matching Hermes Mem0 scope.")
        if u:
            return await client.delete_users(user_id=u)
        return await client.delete_users(agent_id=ag)

    if op == "reset":
        if (a.get("confirm") or "").strip() != _RESET_ACCOUNT_CONFIRM:
            raise ValueError(f"confirm must be exactly {_RESET_ACCOUNT_CONFIRM!r}")
        return await client.reset()

    if op == "batch_update":
        mems = a.get("memories")
        if not isinstance(mems, list) or not mems:
            raise ValueError("memories must be a non-empty list")
        for i, m in enumerate(mems):
            if not isinstance(m, dict) or not m.get("memory_id"):
                raise ValueError(f"memories[{i}] needs memory_id")
        return await client.batch_update(mems)

    if op == "batch_delete":
        ids = a.get("memory_ids")
        if not isinstance(ids, list) or not ids:
            raise ValueError("memory_ids must be a non-empty list")
        payload = [{"memory_id": str(x)} for x in ids if x]
        if len(payload) != len(ids):
            raise ValueError("memory_ids must be non-empty strings")
        return await client.batch_delete(payload)

    if op == "create_memory_export":
        schema = a.get("schema")
        if not isinstance(schema, str) or not schema.strip():
            raise ValueError("schema must be a non-empty string")
        u = (a.get("user_id") or "").strip() or uid_scope
        return await client.create_memory_export(schema, user_id=u)

    if op == "get_memory_export":
        filters = a.get("filters")
        if filters is None:
            filters = {}
        if not isinstance(filters, dict):
            raise ValueError("filters must be an object")
        body = dict(filters)
        if "user_id" not in body:
            body["user_id"] = uid_scope
        return await client.get_memory_export(**body)

    if op in ("get_memory_export_summary", "get_summary"):
        filters = a.get("filters")
        if filters is not None and not isinstance(filters, dict):
            raise ValueError("filters must be an object or omitted")
        return await client.get_summary(filters if isinstance(filters, dict) else None)

    if op in ("legacy_get_project", "get_project"):
        _need_org_project()
        fields = a.get("fields")
        fl = fields if isinstance(fields, list) else None
        return await client.get_project(fields=fl)

    if op in ("legacy_update_project", "update_project"):
        _need_org_project()
        keys = (
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
        kw = {k: a[k] for k in keys if k in a}
        if not kw:
            raise ValueError("Provide at least one legacy project field to update")
        return await client.update_project(**kw)

    if op == "get_webhooks":
        pid = str(a.get("project_id") or "")
        _webhook_pid_ok(pid)
        return await client.get_webhooks(pid.strip())

    if op == "create_webhook":
        pid = str(a.get("project_id") or "")
        _webhook_pid_ok(pid)
        url = (a.get("url") or "").strip()
        name = (a.get("name") or "").strip()
        ev = a.get("event_types")
        if not url or not name:
            raise ValueError("url and name required")
        if not isinstance(ev, list) or not ev:
            raise ValueError("event_types must be a non-empty array")
        return await client.create_webhook(url, name, pid.strip(), ev)

    if op == "update_webhook":
        wid = a.get("webhook_id")
        if wid is None:
            raise ValueError("webhook_id required")
        try:
            w_int = int(wid)
        except (TypeError, ValueError):
            raise ValueError("webhook_id must be an integer") from None
        et = a.get("event_types")
        return await client.update_webhook(
            w_int,
            name=a.get("name"),
            url=a.get("url"),
            event_types=et if isinstance(et, list) else None,
        )

    if op == "delete_webhook":
        wid = a.get("webhook_id")
        if wid is None:
            raise ValueError("webhook_id required")
        try:
            w_int = int(wid)
        except (TypeError, ValueError):
            raise ValueError("webhook_id must be an integer") from None
        return await client.delete_webhook(w_int)

    if op == "feedback":
        mid = (a.get("memory_id") or "").strip()
        fb = (a.get("feedback") or "").strip()
        if not mid or not fb:
            raise ValueError("memory_id and feedback required")
        return await client.feedback(mid, feedback=fb, feedback_reason=a.get("feedback_reason"))

    # --- client.project (AsyncProject) ---
    if op == "project_get":
        _need_org_project()
        fields = a.get("fields")
        fl = fields if isinstance(fields, list) else None
        return await client.project.get(fields=fl)

    if op == "project_update":
        _need_org_project()
        keys = (
            "custom_instructions",
            "custom_categories",
            "retrieval_criteria",
            "enable_graph",
            "multilingual",
        )
        kw = {k: a[k] for k in keys if k in a}
        if not kw:
            raise ValueError("Provide at least one project field to update")
        return await client.project.update(**kw)

    if op == "project_create":
        _need_org()
        name = (a.get("name") or "").strip()
        if not name:
            raise ValueError("name required")
        return await client.project.create(name, description=a.get("description"))

    if op == "project_delete":
        _need_org_project()
        if (a.get("confirm") or "").strip() != _DELETE_PROJECT_CONFIRM:
            raise ValueError(f"confirm must be exactly {_DELETE_PROJECT_CONFIRM!r}")
        return await client.project.delete()

    if op in ("project_members", "project_get_members"):
        _need_org_project()
        return await client.project.get_members()

    if op in ("project_member_add", "project_add_member"):
        _need_org_project()
        email = (a.get("email") or "").strip()
        if not email:
            raise ValueError("email required")
        role = (a.get("role") or "READER").strip().upper()
        return await client.project.add_member(email, role=role)

    if op in ("project_member_update", "project_update_member"):
        _need_org_project()
        email = (a.get("email") or "").strip()
        role = (a.get("role") or "").strip().upper()
        if not email or not role:
            raise ValueError("email and role required")
        return await client.project.update_member(email, role)

    if op in ("project_member_remove", "project_remove_member"):
        _need_org_project()
        email = (a.get("email") or "").strip()
        if not email:
            raise ValueError("email required")
        return await client.project.remove_member(email)

    raise ValueError(
        f"Unknown async operation {operation!r}. See mem0_async_invoke description for names."
    )
