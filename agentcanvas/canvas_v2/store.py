"""Small v2 canvas store/write protocol.

This module intentionally keeps Phase 0 narrow: it owns optimistic writes and
basic graph integrity while fuller validation/migration modules are still
being built.
"""

from __future__ import annotations

import json
import uuid
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional, Set, Tuple

from agentcanvas.ir import (
    STATE_DIR_NAME,
    canvas_ir_path,
    ensure_state_dirs,
    now_utc,
    resolve_workspace,
)

CANVAS_V2_SCHEMA = "agentcanvas.canvas.v2"
KNOWN_NODE_KINDS = {
    "When",
    "Do",
    "Decision",
    "Loop",
    "Parallel",
    "Join",
    "Wait",
    "SubFlow",
    "End",
}
KNOWN_EDGE_KINDS = {
    "normal",
    "branch",
    "loop_body",
    "loop_back",
    "loop_exit",
    "parallel",
    "error",
    "async",
}
OPEN_PENDING_STATUSES = {"pending", "sent", "in_progress", "needs_input", "blocked"}


class CanvasStoreError(ValueError):
    """Structured store error suitable for CLI/API recovery."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        revision: Optional[int] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.revision = revision
        self.details = details or {}

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "ok": False,
            "error": {
                "code": self.code,
                "message": self.message,
            },
        }
        if self.revision is not None:
            payload["revision"] = self.revision
            payload["error"]["revision"] = self.revision
        if self.details:
            payload["error"]["details"] = self.details
        return payload


def load_canvas_document(workspace: str | Path) -> Dict[str, Any]:
    """Load the current v2 canvas, or return an empty revision-0 document."""

    root = resolve_workspace(workspace)
    path = canvas_ir_path(root)
    if not path.exists():
        return _empty_document()

    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise CanvasStoreError("INVALID_CANVAS", "canvas.ir.json must be a JSON object")
    if payload.get("schema") != CANVAS_V2_SCHEMA:
        from .migration import detect_v1_canvas

        if detect_v1_canvas(payload):
            raise CanvasStoreError(
                "MIGRATION_REQUIRED",
                "canvas.ir.json is a legacy AgentCanvas canvas; migrate it before applying v2 operations",
                details={
                    "schema": payload.get("schema"),
                    "suggested_command": "agentcanvas canvas migrate --workspace <workspace> --apply",
                },
            )
        raise CanvasStoreError(
            "UNSUPPORTED_CANVAS_SCHEMA",
            "canvas.ir.json must be agentcanvas.canvas.v2 for canvas apply",
            details={"schema": payload.get("schema")},
        )
    return _normalize_document(payload)


def apply_operation_batch(
    workspace: str | Path,
    batch: Mapping[str, Any],
    *,
    base_revision: Optional[int] = None,
    authored_by: Optional[str] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Apply a v2 operation batch atomically and return a structured result."""

    if not isinstance(batch, Mapping):
        raise CanvasStoreError("INVALID_BATCH", "operation batch must be a JSON object")

    root = resolve_workspace(workspace)
    current = load_canvas_document(root)
    current_revision = _revision(current)
    expected_revision = _coalesce_base_revision(base_revision, batch)
    if expected_revision != current_revision:
        raise CanvasStoreError(
            "REVISION_CONFLICT",
            "base_revision does not match the current canvas revision",
            revision=current_revision,
            details={
                "base_revision": expected_revision,
                "current_revision": current_revision,
                "changed_since": _changed_since_summary(current, expected_revision),
            },
        )

    operations = batch.get("operations")
    if not isinstance(operations, list):
        raise CanvasStoreError("INVALID_BATCH", "operations must be a list")

    writer = authored_by or _optional_string(batch.get("authored_by")) or "agentcanvas-cli"
    allow_rewrite = batch.get("allow_rewrite")
    if allow_rewrite is not None and not isinstance(allow_rewrite, Mapping):
        raise CanvasStoreError("INVALID_BATCH", "allow_rewrite must be null or an object")

    updated = deepcopy(current)
    _apply_operations(updated, operations)
    _validate_referenced_deletes(root, operations, allow_rewrite=allow_rewrite)
    _validate_document(updated)

    next_revision = current_revision + 1
    updated["revision"] = next_revision
    updated["authored_by"] = writer
    updated["updated_at"] = now_utc()

    # TODO(canvas-v2): replace this minimal guard with the full layered churn
    # guard and pending tombstone transaction from the v2 spec.
    if not dry_run:
        _write_revision(root, current, updated)
    return {
        "ok": True,
        "dry_run": bool(dry_run),
        "revision": next_revision,
        "base_revision": current_revision,
        "path": str(canvas_ir_path(root)),
    }


def _apply_operations(document: Dict[str, Any], operations: Iterable[Any]) -> None:
    flows = _flow_map(document)
    for index, operation in enumerate(operations):
        if not isinstance(operation, Mapping):
            raise CanvasStoreError("INVALID_OPERATION", _op_message(index, "must be an object"))
        op = operation.get("op")
        if op == "set_app":
            app = operation.get("app")
            if not isinstance(app, Mapping):
                raise CanvasStoreError("INVALID_OPERATION", _op_message(index, "app must be an object"))
            document["app"] = _clean_dict(app)
        elif op == "upsert_flow":
            flow = operation.get("flow")
            if not isinstance(flow, Mapping):
                raise CanvasStoreError("INVALID_OPERATION", _op_message(index, "flow must be an object"))
            normalized = _normalize_flow(flow, existing=flows.get(flow.get("id")))
            flows[normalized["id"]] = normalized
        elif op == "upsert_node":
            flow = _operation_flow(operation, flows, index)
            node = operation.get("node")
            if not isinstance(node, Mapping):
                raise CanvasStoreError("INVALID_OPERATION", _op_message(index, "node must be an object"))
            _upsert_item(flow, "nodes", _clean_dict(node), index)
        elif op == "upsert_edge":
            flow = _operation_flow(operation, flows, index)
            edge = operation.get("edge")
            if not isinstance(edge, Mapping):
                raise CanvasStoreError("INVALID_OPERATION", _op_message(index, "edge must be an object"))
            _upsert_item(flow, "edges", _clean_dict(edge), index)
        elif op == "delete_node":
            flow = _operation_flow(operation, flows, index)
            target = _required_string(operation.get("target"), index, "target")
            flow["nodes"] = [node for node in flow.get("nodes", []) if node.get("id") != target]
            flow["edges"] = [
                edge
                for edge in flow.get("edges", [])
                if edge.get("source") != target and edge.get("target") != target
            ]
            if flow.get("entry_node") == target:
                flow.pop("entry_node", None)
        elif op == "delete_edge":
            flow = _operation_flow(operation, flows, index)
            target = _required_string(operation.get("target"), index, "target")
            flow["edges"] = [edge for edge in flow.get("edges", []) if edge.get("id") != target]
        else:
            raise CanvasStoreError(
                "UNSUPPORTED_OPERATION",
                _op_message(index, "op is not supported"),
                details={"op": op},
            )

    document["flows"] = list(flows.values())


def _validate_document(document: Mapping[str, Any]) -> None:
    if document.get("schema") != CANVAS_V2_SCHEMA:
        raise CanvasStoreError("INVALID_CANVAS", "schema must be agentcanvas.canvas.v2")
    if not isinstance(document.get("app"), Mapping):
        raise CanvasStoreError("INVALID_CANVAS", "app must be an object")
    flows = document.get("flows")
    if not isinstance(flows, list):
        raise CanvasStoreError("INVALID_CANVAS", "flows must be a list")

    flow_ids: Set[str] = set()
    for flow in flows:
        if not isinstance(flow, Mapping):
            raise CanvasStoreError("INVALID_FLOW", "each flow must be an object")
        flow_id = _non_empty(flow.get("id"))
        if not flow_id:
            raise CanvasStoreError("INVALID_FLOW", "flow.id must be a non-empty string")
        if flow_id in flow_ids:
            raise CanvasStoreError("DUPLICATE_ID", "duplicate flow id", details={"id": flow_id})
        flow_ids.add(flow_id)

    for flow in flows:
        _validate_flow(flow, flow_ids)


def _validate_flow(flow: Mapping[str, Any], flow_ids: Set[str]) -> None:
    flow_id = str(flow["id"])
    nodes = flow.get("nodes")
    edges = flow.get("edges")
    if not isinstance(nodes, list):
        raise CanvasStoreError("INVALID_FLOW", "flow.nodes must be a list", details={"flow": flow_id})
    if not isinstance(edges, list):
        raise CanvasStoreError("INVALID_FLOW", "flow.edges must be a list", details={"flow": flow_id})

    node_ids: Set[str] = set()
    for node in nodes:
        if not isinstance(node, Mapping):
            raise CanvasStoreError("INVALID_NODE", "each node must be an object", details={"flow": flow_id})
        node_id = _non_empty(node.get("id"))
        if not node_id:
            raise CanvasStoreError("INVALID_NODE", "node.id must be a non-empty string", details={"flow": flow_id})
        if node_id in node_ids:
            raise CanvasStoreError("DUPLICATE_ID", "duplicate node id", details={"flow": flow_id, "id": node_id})
        node_ids.add(node_id)
        if node.get("kind") not in KNOWN_NODE_KINDS:
            raise CanvasStoreError("UNKNOWN_NODE_KIND", "node.kind is not supported", details={"flow": flow_id, "node": node_id, "kind": node.get("kind")})
        if not _non_empty(node.get("title")):
            raise CanvasStoreError("INVALID_NODE", "node.title must be a non-empty string", details={"flow": flow_id, "node": node_id})
        if node.get("kind") == "SubFlow" and node.get("flow_ref") not in flow_ids:
            raise CanvasStoreError("DANGLING_FLOW_REF", "SubFlow.flow_ref must point at an existing flow", details={"flow": flow_id, "node": node_id, "flow_ref": node.get("flow_ref")})

    entry_node = flow.get("entry_node")
    if entry_node is not None and entry_node not in node_ids:
        raise CanvasStoreError("DANGLING_ENTRY_NODE", "entry_node must point at a node in the flow", details={"flow": flow_id, "entry_node": entry_node})

    edge_ids: Set[str] = set()
    for edge in edges:
        if not isinstance(edge, Mapping):
            raise CanvasStoreError("INVALID_EDGE", "each edge must be an object", details={"flow": flow_id})
        edge_id = _non_empty(edge.get("id"))
        if not edge_id:
            raise CanvasStoreError("EDGE_ID_REQUIRED", "edge.id is required", details={"flow": flow_id})
        if edge_id in edge_ids:
            raise CanvasStoreError("DUPLICATE_ID", "duplicate edge id", details={"flow": flow_id, "id": edge_id})
        edge_ids.add(edge_id)
        if edge.get("kind") not in KNOWN_EDGE_KINDS:
            raise CanvasStoreError("UNKNOWN_EDGE_KIND", "edge.kind is not supported", details={"flow": flow_id, "edge": edge_id, "kind": edge.get("kind")})
        source = edge.get("source")
        target = edge.get("target")
        if source not in node_ids or target not in node_ids:
            raise CanvasStoreError(
                "DANGLING_EDGE_ENDPOINT",
                "edge endpoints must point at active nodes in the same flow",
                details={"flow": flow_id, "edge": edge_id, "source": source, "target": target},
            )


def _validate_referenced_deletes(
    workspace: Path,
    operations: Iterable[Any],
    *,
    allow_rewrite: Optional[Mapping[str, Any]],
) -> None:
    if allow_rewrite:
        return

    deleted: Set[Tuple[str, str]] = set()
    for operation in operations:
        if not isinstance(operation, Mapping):
            continue
        if operation.get("op") == "delete_node":
            target = operation.get("target")
            if isinstance(target, str):
                deleted.add(("node", target))
        elif operation.get("op") == "delete_edge":
            target = operation.get("target")
            if isinstance(target, str):
                deleted.add(("edge", target))
    if not deleted:
        return

    references = _open_pending_refs(workspace)
    blocked = sorted(
        {"%s:%s" % (kind, item_id) for kind, item_id in deleted if (kind, item_id) in references}
    )
    if blocked:
        raise CanvasStoreError(
            "REFERENCED_ID_REMOVED",
            "operation removes ids referenced by open pending requests",
            details={"ids": blocked},
        )


def _open_pending_refs(workspace: Path) -> Set[Tuple[str, str]]:
    pending_dir = workspace / STATE_DIR_NAME / "pending"
    references: Set[Tuple[str, str]] = set()
    if not pending_dir.is_dir():
        return references
    for path in pending_dir.glob("*.json"):
        try:
            with path.open("r", encoding="utf-8") as handle:
                item = json.load(handle)
        except (OSError, ValueError):
            continue
        if not isinstance(item, Mapping):
            continue
        if item.get("status", "pending") not in OPEN_PENDING_STATUSES:
            continue
        refs = item.get("refs")
        if not isinstance(refs, list):
            continue
        for ref in refs:
            if not isinstance(ref, Mapping):
                continue
            kind = ref.get("kind")
            item_id = ref.get("id")
            if isinstance(kind, str) and isinstance(item_id, str):
                references.add((kind, item_id))
    return references


def _write_revision(root: Path, previous: Dict[str, Any], updated: Dict[str, Any]) -> None:
    ensure_state_dirs(root)
    history_dir = root / STATE_DIR_NAME / "history"
    history_dir.mkdir(parents=True, exist_ok=True)
    history_path = history_dir / ("canvas.%s.json" % _revision(previous))
    canvas_path = canvas_ir_path(root)
    tmp_history = history_path.with_name(".%s.%s.tmp" % (history_path.name, uuid.uuid4().hex))
    tmp_canvas = canvas_path.with_name(".%s.%s.tmp" % (canvas_path.name, uuid.uuid4().hex))
    try:
        tmp_history.write_text(json.dumps(previous, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp_canvas.write_text(json.dumps(updated, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp_history.replace(history_path)
        tmp_canvas.replace(canvas_path)
    finally:
        if tmp_history.exists():
            tmp_history.unlink()
        if tmp_canvas.exists():
            tmp_canvas.unlink()


def _empty_document() -> Dict[str, Any]:
    return {
        "schema": CANVAS_V2_SCHEMA,
        "revision": 0,
        "authored_by": "agentcanvas",
        "updated_at": None,
        "evidence": {},
        "app": {
            "name": "",
            "summary": "",
            "is_demo": False,
        },
        "flows": [],
        "metadata": {},
    }


def _normalize_document(payload: Mapping[str, Any]) -> Dict[str, Any]:
    document = _empty_document()
    document.update(_clean_dict(payload))
    document["revision"] = _revision(document)
    document["app"] = _clean_dict(document.get("app") if isinstance(document.get("app"), Mapping) else {})
    flows = document.get("flows")
    document["flows"] = [
        _normalize_flow(flow)
        for flow in flows
        if isinstance(flow, Mapping)
    ] if isinstance(flows, list) else []
    if not isinstance(document.get("metadata"), Mapping):
        document["metadata"] = {}
    if not isinstance(document.get("evidence"), Mapping):
        document["evidence"] = {}
    return document


def _normalize_flow(
    flow: Mapping[str, Any],
    *,
    existing: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    flow_id = _non_empty(flow.get("id"))
    if not flow_id:
        raise CanvasStoreError("INVALID_FLOW", "flow.id must be a non-empty string")
    normalized = _clean_dict(existing) if isinstance(existing, Mapping) else {}
    normalized.update(_clean_dict(flow))
    normalized["id"] = flow_id
    normalized.setdefault("title", flow_id)
    normalized.setdefault("summary", "")
    normalized.setdefault("altitude", "flow")
    normalized.setdefault("nodes", [])
    normalized.setdefault("edges", [])
    normalized.setdefault("lanes", [])
    normalized.setdefault("tags", [])
    normalized.setdefault("evidence_refs", [])
    normalized.setdefault("confidence", {})
    normalized.setdefault("metadata", {})
    if not isinstance(normalized.get("nodes"), list):
        normalized["nodes"] = []
    if not isinstance(normalized.get("edges"), list):
        normalized["edges"] = []
    return normalized


def _flow_map(document: Mapping[str, Any]) -> Dict[str, Dict[str, Any]]:
    flows: Dict[str, Dict[str, Any]] = {}
    for flow in document.get("flows") or []:
        if isinstance(flow, Mapping) and isinstance(flow.get("id"), str):
            flows[flow["id"]] = _normalize_flow(flow)
    return flows


def _operation_flow(
    operation: Mapping[str, Any],
    flows: Mapping[str, Dict[str, Any]],
    index: int,
) -> Dict[str, Any]:
    flow_id = _required_string(operation.get("flow"), index, "flow")
    flow = flows.get(flow_id)
    if flow is None:
        raise CanvasStoreError(
            "UNKNOWN_FLOW",
            _op_message(index, "flow does not exist"),
            details={"flow": flow_id},
        )
    return flow


def _upsert_item(flow: Dict[str, Any], key: str, item: Dict[str, Any], index: int) -> None:
    if key == "edges" and not _non_empty(item.get("id")):
        raise CanvasStoreError("EDGE_ID_REQUIRED", _op_message(index, "edge.id is required"))
    item_id = _required_string(item.get("id"), index, "%s.id" % key[:-1])
    items = flow.setdefault(key, [])
    replaced = False
    for item_index, current in enumerate(items):
        if isinstance(current, Mapping) and current.get("id") == item_id:
            items[item_index] = item
            replaced = True
            break
    if not replaced:
        items.append(item)


def _coalesce_base_revision(base_revision: Optional[int], batch: Mapping[str, Any]) -> int:
    batch_revision = batch.get("base_revision")
    if base_revision is not None and batch_revision is not None:
        try:
            input_revision = int(batch_revision)
        except (TypeError, ValueError):
            raise CanvasStoreError("INVALID_BATCH", "base_revision must be an integer")
        if input_revision != int(base_revision):
            raise CanvasStoreError(
                "INVALID_BATCH",
                "CLI base_revision does not match input base_revision",
                details={"base_revision": base_revision, "input_base_revision": batch_revision},
            )
        return int(base_revision)
    if base_revision is not None:
        return int(base_revision)
    if batch_revision is None:
        raise CanvasStoreError(
            "INVALID_BATCH",
            "base_revision is required",
        )
    try:
        return int(batch_revision)
    except (TypeError, ValueError):
        raise CanvasStoreError("INVALID_BATCH", "base_revision must be an integer")


def _changed_since_summary(current: Mapping[str, Any], base_revision: int) -> Dict[str, Any]:
    flow_ids = [
        flow.get("id")
        for flow in current.get("flows", [])
        if isinstance(flow, Mapping) and isinstance(flow.get("id"), str)
    ]
    return {
        "from_revision": base_revision,
        "to_revision": _revision(current),
        "flow_ids": flow_ids,
        "operation_count": max(0, _revision(current) - base_revision),
    }


def _revision(document: Mapping[str, Any]) -> int:
    try:
        return int(document.get("revision", 0))
    except (TypeError, ValueError):
        return 0


def _required_string(value: Any, index: int, key: str) -> str:
    text = _non_empty(value)
    if not text:
        raise CanvasStoreError("INVALID_OPERATION", _op_message(index, "%s must be a non-empty string" % key))
    return text


def _optional_string(value: Any) -> Optional[str]:
    return value if isinstance(value, str) and value else None


def _non_empty(value: Any) -> Optional[str]:
    return value if isinstance(value, str) and value else None


def _op_message(index: int, message: str) -> str:
    return "operations[%s] %s" % (index, message)


def _clean_dict(value: Mapping[str, Any]) -> Dict[str, Any]:
    return dict(value)
