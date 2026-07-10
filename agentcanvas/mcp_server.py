"""MCP bridge for AgentCanvas.

The public functions in this module are intentionally stdlib-only so tests and
agent adapters can use the same contract even when the optional MCP SDK is not
installed. ``run_mcp_server`` is the only place that imports the SDK.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

from .canvas_v2 import (
    CanvasStoreError,
    apply_operation_batch,
    load_canvas_document,
    validate_canvas_v2,
)
from .canvas_v2.evidence import compare_canvas_with_current_workflow_evidence
from .ir import (
    ConversationRole,
    ConversationTurnKind,
    append_pending_conversation,
    canvas_ir_path,
    get_pending_request,
    list_pending,
    load_ir,
    map_health,
    now_utc,
    read_pending_conversation,
    resolve_workspace,
    update_pending_status,
)
from .lifecycle import LifecycleError, PENDING, PENDING_STATUSES, validate_status
from .progress import write_progress, progress_status


MCP_EXTRA_INSTALL_HINT = (
    "MCP support is optional. Install it with: pip install 'use-agentcanvas[mcp]' "
    "or run: uvx --from 'use-agentcanvas[mcp]' agentcanvas mcp"
)
SERVER_HEARTBEAT_FILENAME = "server.heartbeat.json"
HEARTBEAT_FRESH_SECONDS = 45
DEFAULT_EVIDENCE_MAX_ITEMS = 100
DEFAULT_EVIDENCE_MAX_BYTES = 48 * 1024
MAX_EVIDENCE_ITEMS = 200
MAX_EVIDENCE_BYTES = 200_000


def get_workspace_status(workspace: str = ".") -> Dict[str, Any]:
    """Return a compact agent-facing status for the workspace."""

    root = resolve_workspace(workspace)
    health = map_health(root)
    pending = list_pending(root, summary=True)
    status_counts: Dict[str, int] = {status: 0 for status in sorted(PENDING_STATUSES)}
    status_counts["unreadable"] = 0
    for item in pending:
        raw_status = item.get("status", PENDING)
        try:
            status = validate_status(raw_status)
        except LifecycleError:
            status = str(raw_status or PENDING)
        status_counts[status] = status_counts.get(status, 0) + 1

    canvas_summary: Dict[str, Any] = {
        "path": str(canvas_ir_path(root)),
        "exists": canvas_ir_path(root).is_file(),
    }
    try:
        canvas = load_canvas_document(root)
    except CanvasStoreError as exc:
        canvas_summary.update(
            {
                "readable": False,
                "error": exc.to_dict()["error"],
            }
        )
    except (OSError, ValueError) as exc:
        canvas_summary.update({"readable": False, "error": {"message": str(exc)}})
    else:
        flows = canvas.get("flows") or []
        canvas_summary.update(
            {
                "readable": True,
                "schema": canvas.get("schema"),
                "revision": canvas.get("revision", 0),
                "flow_count": len(flows),
                "node_count": sum(len(flow.get("nodes") or []) for flow in flows),
                "edge_count": sum(len(flow.get("edges") or []) for flow in flows),
                "evidence": _evidence_status(root, canvas),
            }
        )

    return {
        "ok": True,
        "workspace": str(root),
        "checked_at": now_utc(),
        "health": health,
        "canvas": canvas_summary,
        "pending": {
            "count": len(pending),
            "status_counts": status_counts,
        },
        "heartbeat": read_server_heartbeat(root),
    }


def get_canvas(workspace: str = ".", flow_id: Optional[str] = None) -> Dict[str, Any]:
    """Return the current v2 canvas document, optionally scoped to one flow."""

    root = resolve_workspace(workspace)
    document = load_canvas_document(root)
    returned = document
    if flow_id:
        flow = _find_flow(document, flow_id)
        returned = dict(document)
        returned["flows"] = [flow] if flow is not None else []
    validation = validate_canvas_v2(returned, mode="authoring")
    return {
        "ok": True,
        "workspace": str(root),
        "revision": document.get("revision", 0),
        "flow_id": flow_id,
        "canvas_v2": returned,
        "validation": validation,
    }


def get_evidence(
    workspace: str = ".",
    query: Optional[str] = None,
    cursor: Optional[int] = None,
    max_items: int = DEFAULT_EVIDENCE_MAX_ITEMS,
    max_bytes: int = DEFAULT_EVIDENCE_MAX_BYTES,
) -> Dict[str, Any]:
    """Return paginated workflow evidence for agents to ground canvas edits."""

    root = resolve_workspace(workspace)
    try:
        workflow_ir = load_ir(root)
    except FileNotFoundError:
        return {
            "ok": False,
            "workspace": str(root),
            "error": {
                "code": "WORKFLOW_IR_MISSING",
                "message": "workflow.ir.json is missing; run agentcanvas index or author a canvas first",
            },
            "items": [],
            "next_cursor": None,
            "truncated": False,
        }

    evidence_items = _workflow_evidence_items(workflow_ir)
    if query:
        needle = query.strip().lower()
        evidence_items = [
            item
            for item in evidence_items
            if needle in json.dumps(item, sort_keys=True).lower()
        ]

    start = max(0, int(cursor or 0))
    item_limit = min(MAX_EVIDENCE_ITEMS, max(1, int(max_items or DEFAULT_EVIDENCE_MAX_ITEMS)))
    byte_limit = min(MAX_EVIDENCE_BYTES, max(1_000, int(max_bytes or DEFAULT_EVIDENCE_MAX_BYTES)))
    selected: List[Dict[str, Any]] = []
    used_bytes = 0
    index = start
    while index < len(evidence_items) and len(selected) < item_limit:
        item = evidence_items[index]
        encoded = json.dumps(item, sort_keys=True, separators=(",", ":")).encode("utf-8")
        if selected and used_bytes + len(encoded) > byte_limit:
            break
        selected.append(item)
        used_bytes += len(encoded)
        index += 1

    return {
        "ok": True,
        "workspace": str(root),
        "generated_at": workflow_ir.get("generated_at"),
        "summary": workflow_ir.get("summary") or {},
        "query": query,
        "cursor": start,
        "items": selected,
        "next_cursor": index if index < len(evidence_items) else None,
        "truncated": index < len(evidence_items),
        "total_candidates": len(evidence_items),
        "byte_count": used_bytes,
    }


def record_progress(
    workspace: str = ".",
    *,
    stage: str,
    message: str,
    current: Optional[int] = None,
    total: Optional[int] = None,
) -> Dict[str, Any]:
    """Write durable mapping progress for the local UI to display."""

    write_progress(workspace, stage=stage, message=message, current=current, total=total)
    return {"ok": True, "progress": progress_status(workspace)}


def apply_canvas(
    operations: List[Mapping[str, Any]],
    base_revision: int,
    *,
    workspace: str = ".",
    allow_rewrite: Optional[Mapping[str, Any]] = None,
    authored_by: str = "agentcanvas-mcp",
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Apply a v2 canvas operation batch through the canonical store."""

    batch: Dict[str, Any] = {
        "base_revision": int(base_revision),
        "authored_by": authored_by,
        "operations": list(operations),
    }
    if allow_rewrite is not None:
        batch["allow_rewrite"] = dict(allow_rewrite)
    return apply_operation_batch(
        workspace,
        batch,
        base_revision=int(base_revision),
        authored_by=authored_by,
        dry_run=dry_run,
    )


def validate_canvas(
    document: Optional[Mapping[str, Any]] = None,
    *,
    workspace: str = ".",
    mode: str = "authoring",
) -> Dict[str, Any]:
    """Validate a supplied document or the current workspace canvas."""

    target = document if document is not None else load_canvas_document(workspace)
    return validate_canvas_v2(target, mode=mode)


def list_requests(
    workspace: str = ".",
    status: Optional[str] = None,
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    """List pending requests as bounded summaries."""

    items = list_pending(
        workspace,
        summary=True,
        status=status,
        session_id=session_id,
    )
    return {
        "ok": True,
        "workspace": str(resolve_workspace(workspace)),
        "count": len(items),
        "requests": items,
    }


def get_request(
    request_id: str,
    *,
    workspace: str = ".",
    since: Optional[str] = None,
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Return one pending request with its conversation turns."""

    return {
        "ok": True,
        "workspace": str(resolve_workspace(workspace)),
        "request": get_pending_request(
            workspace,
            request_id,
            since=since,
            session_id=session_id,
        ),
    }


def update_request(
    request_id: str,
    status: str,
    *,
    workspace: str = ".",
    note: Optional[str] = None,
    evidence: Optional[Mapping[str, Any]] = None,
    actor: str = "agentcanvas-mcp",
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Update a pending request status through the shared lifecycle."""

    item = update_pending_status(
        workspace,
        request_id,
        status,
        note=note,
        actor=actor,
        evidence=dict(evidence) if isinstance(evidence, Mapping) else None,
        enforce_transitions=True,
        session_id=session_id,
    )
    return {"ok": True, "workspace": str(resolve_workspace(workspace)), "request": item}


def ask_user(
    request_id: str,
    question: str,
    *,
    workspace: str = ".",
    actor: str = "agentcanvas-mcp",
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Ask the user a clarifying question on a pending request."""

    item = append_pending_conversation(
        workspace,
        request_id,
        role=ConversationRole.AGENT.value,
        kind=ConversationTurnKind.QUESTION.value,
        text=question,
        actor=actor,
        session_id=session_id,
    )
    return {"ok": True, "workspace": str(resolve_workspace(workspace)), "request": item}


def get_answers(
    request_id: Optional[str] = None,
    *,
    workspace: str = ".",
    since: Optional[str] = None,
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Return user answers from one request or all pending request threads."""

    root = resolve_workspace(workspace)
    answers: List[Dict[str, Any]] = []
    if request_id:
        request = get_pending_request(root, request_id, since=since, session_id=session_id)
        answers.extend(_answer_turns(request, request.get("id")))
    else:
        for item in list_pending(root, summary=True, session_id=session_id):
            json_path = item.get("json_path")
            if not isinstance(json_path, str):
                continue
            turns = read_pending_conversation(Path(json_path), since=since)
            answers.extend(
                {
                    "request_id": item.get("id"),
                    **turn,
                }
                for turn in turns
                if _is_user_answer(turn)
            )
    return {"ok": True, "workspace": str(root), "answers": answers}


def record_sync(workspace: str = ".", git_head: Optional[str] = None) -> Dict[str, Any]:
    """Return the current workspace evidence fingerprint for sync bookkeeping."""

    from .canvas_v2.evidence import build_current_workflow_evidence

    evidence = build_current_workflow_evidence(workspace)
    if git_head:
        evidence = dict(evidence)
        evidence["git_head"] = git_head
    return {
        "ok": True,
        "workspace": str(resolve_workspace(workspace)),
        "recorded_at": now_utc(),
        "evidence": evidence,
    }


def read_server_heartbeat(workspace: str = ".") -> Dict[str, Any]:
    """Read server heartbeat metadata when the local web app is running."""

    root = resolve_workspace(workspace)
    path = root / ".agentcanvas" / SERVER_HEARTBEAT_FILENAME
    if not path.is_file():
        return {"exists": False, "path": str(path), "alive": False, "stale": None}
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, ValueError) as exc:
        return {
            "exists": True,
            "path": str(path),
            "alive": False,
            "stale": None,
            "error": str(exc),
        }
    age_seconds = None
    stale = None
    try:
        age_seconds = max(0.0, time.time() - path.stat().st_mtime)
        stale = age_seconds > HEARTBEAT_FRESH_SECONDS
    except OSError:
        pass
    return {
        "exists": True,
        "path": str(path),
        "alive": stale is False,
        "stale": stale,
        "age_seconds": age_seconds,
        "metadata": payload if isinstance(payload, dict) else {},
    }


def run_mcp_server(default_workspace: str = ".") -> int:
    """Run the stdio MCP server. Requires the optional ``mcp`` dependency."""

    try:
        from mcp.server.fastmcp import FastMCP
    except ModuleNotFoundError as exc:
        if exc.name == "mcp":
            raise
        raise

    server = FastMCP("AgentCanvas")

    @server.tool()
    def agentcanvas_workspace_status(workspace: str = default_workspace) -> Dict[str, Any]:
        return get_workspace_status(workspace)

    @server.tool()
    def agentcanvas_get_canvas(
        workspace: str = default_workspace,
        flow_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        return get_canvas(workspace, flow_id=flow_id)

    @server.tool()
    def agentcanvas_get_evidence(
        workspace: str = default_workspace,
        query: Optional[str] = None,
        cursor: Optional[int] = None,
        max_items: int = DEFAULT_EVIDENCE_MAX_ITEMS,
        max_bytes: int = DEFAULT_EVIDENCE_MAX_BYTES,
    ) -> Dict[str, Any]:
        return get_evidence(
            workspace,
            query=query,
            cursor=cursor,
            max_items=max_items,
            max_bytes=max_bytes,
        )

    @server.tool()
    def agentcanvas_record_progress(
        stage: str,
        message: str,
        workspace: str = default_workspace,
        current: Optional[int] = None,
        total: Optional[int] = None,
    ) -> Dict[str, Any]:
        return record_progress(
            workspace,
            stage=stage,
            message=message,
            current=current,
            total=total,
        )

    @server.tool()
    def agentcanvas_apply_canvas(
        operations: List[Dict[str, Any]],
        base_revision: int,
        workspace: str = default_workspace,
        allow_rewrite: Optional[Dict[str, Any]] = None,
        authored_by: str = "agentcanvas-mcp",
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        return apply_canvas(
            operations,
            base_revision,
            workspace=workspace,
            allow_rewrite=allow_rewrite,
            authored_by=authored_by,
            dry_run=dry_run,
        )

    @server.tool()
    def agentcanvas_validate_canvas(
        document: Optional[Dict[str, Any]] = None,
        workspace: str = default_workspace,
        mode: str = "authoring",
    ) -> Dict[str, Any]:
        return validate_canvas(document, workspace=workspace, mode=mode)

    @server.tool()
    def agentcanvas_list_requests(
        workspace: str = default_workspace,
        status: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        return list_requests(workspace, status=status, session_id=session_id)

    @server.tool()
    def agentcanvas_get_request(
        request_id: str,
        workspace: str = default_workspace,
        since: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        return get_request(request_id, workspace=workspace, since=since, session_id=session_id)

    @server.tool()
    def agentcanvas_update_request(
        request_id: str,
        status: str,
        workspace: str = default_workspace,
        note: Optional[str] = None,
        evidence: Optional[Dict[str, Any]] = None,
        actor: str = "agentcanvas-mcp",
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        return update_request(
            request_id,
            status,
            workspace=workspace,
            note=note,
            evidence=evidence,
            actor=actor,
            session_id=session_id,
        )

    @server.tool()
    def agentcanvas_ask_user(
        request_id: str,
        question: str,
        workspace: str = default_workspace,
        actor: str = "agentcanvas-mcp",
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        return ask_user(
            request_id,
            question,
            workspace=workspace,
            actor=actor,
            session_id=session_id,
        )

    @server.tool()
    def agentcanvas_get_answers(
        request_id: Optional[str] = None,
        workspace: str = default_workspace,
        since: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        return get_answers(request_id, workspace=workspace, since=since, session_id=session_id)

    @server.tool()
    def agentcanvas_record_sync(
        workspace: str = default_workspace,
        git_head: Optional[str] = None,
    ) -> Dict[str, Any]:
        return record_sync(workspace, git_head=git_head)

    server.run()
    return 0


def _find_flow(document: Mapping[str, Any], flow_id: str) -> Optional[Dict[str, Any]]:
    for flow in document.get("flows") or []:
        if isinstance(flow, dict) and flow.get("id") == flow_id:
            return flow
    return None


def _evidence_status(root: Path, document: Mapping[str, Any]) -> Dict[str, Any]:
    try:
        return compare_canvas_with_current_workflow_evidence(document, root)
    except (OSError, ValueError):
        return {
            "status": "possibly-stale",
            "stale": None,
            "reasons": ["workflow evidence is missing or unreadable"],
            "mismatched_fields": [],
            "unknown_fields": [],
        }


def _workflow_evidence_items(workflow_ir: Mapping[str, Any]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    source_facts = workflow_ir.get("source_facts")
    if isinstance(source_facts, Mapping):
        facts = source_facts.get("facts")
        if isinstance(facts, list):
            for index, fact in enumerate(facts):
                if isinstance(fact, Mapping):
                    items.append(_evidence_item("fact", index, fact))

    for key in ("components", "nodes", "edges"):
        values = workflow_ir.get(key)
        if isinstance(values, list):
            for index, value in enumerate(values):
                if isinstance(value, Mapping):
                    items.append(_evidence_item(key[:-1], index, value))

    if not items and isinstance(source_facts, Mapping):
        items.append(_evidence_item("source_facts", 0, source_facts))
    return items


def _evidence_item(kind: str, index: int, payload: Mapping[str, Any]) -> Dict[str, Any]:
    path, line = _payload_path_line(payload)
    return {
        "kind": kind,
        "index": index,
        "id": _first_string(
            payload.get("id"),
            payload.get("symbol"),
            payload.get("name"),
            payload.get("path"),
        ),
        "title": _first_string(payload.get("title"), payload.get("label"), payload.get("name")),
        "path": path,
        "line": line,
        "payload": dict(payload),
    }


def _payload_path_line(payload: Mapping[str, Any]) -> Tuple[Optional[str], Optional[int]]:
    for key in ("path", "file", "source_path"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            line = payload.get("line") or payload.get("start_line")
            return value, int(line) if isinstance(line, int) else None
    location = payload.get("location")
    if isinstance(location, Mapping):
        path = location.get("path") or location.get("file")
        line = location.get("line") or location.get("start_line")
        return (
            path if isinstance(path, str) else None,
            int(line) if isinstance(line, int) else None,
        )
    return None, None


def _first_string(*values: Any) -> Optional[str]:
    for value in values:
        if isinstance(value, str) and value:
            return value
    return None


def _is_user_answer(turn: Mapping[str, Any]) -> bool:
    return (
        turn.get("role") == ConversationRole.USER.value
        and turn.get("kind") == ConversationTurnKind.ANSWER.value
    )


def _answer_turns(request: Mapping[str, Any], request_id: Any) -> List[Dict[str, Any]]:
    return [
        {"request_id": request_id, **turn}
        for turn in request.get("conversation") or []
        if isinstance(turn, Mapping) and _is_user_answer(turn)
    ]
