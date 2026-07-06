"""Small v2 canvas store/write protocol.

This module intentionally keeps Phase 0 narrow: it owns optimistic writes and
basic graph integrity while fuller validation/migration modules are still
being built.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Set, Tuple

from agentcanvas.ir import (
    STATE_DIR_NAME,
    canvas_ir_path,
    ensure_state_dirs,
    now_utc,
    resolve_workspace,
    state_paths,
)
from agentcanvas.lifecycle import PENDING, is_ref_protecting
from agentcanvas.workspace_lock import (
    DEFAULT_LOCK_LEASE_SECONDS,
    WorkspaceLockBusy,
    is_stale_process_claim,
    workspace_write_lock,
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
KNOWN_STATUSES = {"verified", "inferred", "proposed", "stale"}
KNOWN_CONFIDENCE_LEVELS = {"low", "medium", "high"}
HISTORY_DIR_NAME = "history"
HISTORY_HEAD_FILENAME = "canvas.head.json"
HISTORY_TXN_FILENAME = "canvas.txn.json"
HISTORY_TXN_PREFIX = "canvas.txn."
HISTORY_MAX_REVISIONS = 50
HISTORY_MAX_BYTES = 20 * 1024 * 1024
HISTORY_MAX_AGE_SECONDS = 30 * 24 * 60 * 60
TRANSACTION_STALE_SECONDS = DEFAULT_LOCK_LEASE_SECONDS
CRASH_AFTER_CANVAS_REPLACE_FOR_TESTS = False


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
        repair_hint = self.details.get("repair_hint")
        if isinstance(repair_hint, str) and repair_hint:
            payload["error"]["repair_hint"] = repair_hint
        if self.revision is not None:
            payload["revision"] = self.revision
            payload["error"]["revision"] = self.revision
        if self.details:
            payload["error"]["details"] = self.details
        return payload


def load_canvas_document(workspace: str | Path) -> Dict[str, Any]:
    """Load the current v2 canvas, or return an empty revision-0 document."""

    root = resolve_workspace(workspace)
    try:
        with workspace_write_lock(root, writer="canvas-load"):
            return _load_canvas_document_locked(root, reconcile=True)
    except WorkspaceLockBusy as exc:
        raise _workspace_busy_error(exc)


def _load_canvas_document_locked(root: Path, *, reconcile: bool) -> Dict[str, Any]:
    path = canvas_ir_path(root)
    _recover_incomplete_transaction(root)
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
    return _load_v2_payload(root, payload, reconcile=reconcile)


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
    writer = authored_by or _optional_string(batch.get("authored_by")) or "agentcanvas-cli"
    try:
        with workspace_write_lock(root, writer=writer) as lock:
            return _apply_operation_batch_locked(
                root,
                batch,
                base_revision=base_revision,
                writer=writer,
                dry_run=dry_run,
                broken_locks=_lock_breaks(lock),
            )
    except WorkspaceLockBusy as exc:
        raise _workspace_busy_error(exc)


def _apply_operation_batch_locked(
    root: Path,
    batch: Mapping[str, Any],
    *,
    base_revision: Optional[int],
    writer: str,
    dry_run: bool,
    broken_locks: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    current, legacy_payload = _load_canvas_document_for_apply(
        root,
        writer=writer,
        reconcile=not dry_run,
    )
    current_revision = _revision(current)
    expected_revision = _coalesce_base_revision(base_revision, batch)
    accepted_legacy_base = legacy_payload is not None and expected_revision == 0 and current_revision == 1
    if expected_revision != current_revision and not accepted_legacy_base:
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
    _pause_after_revision_check_for_tests()

    operations = batch.get("operations")
    if not isinstance(operations, list):
        raise CanvasStoreError("INVALID_BATCH", "operations must be a list")

    allow_rewrite = batch.get("allow_rewrite")
    if allow_rewrite is not None and not isinstance(allow_rewrite, Mapping):
        raise CanvasStoreError("INVALID_BATCH", "allow_rewrite must be null or an object")
    allow_rewrite_reason = _allow_rewrite_reason(allow_rewrite)

    updated = deepcopy(current)
    _apply_operations(updated, operations)
    deleted = _deleted_id_summary(current, updated)
    _validate_referenced_deletes(root, deleted, allow_rewrite=allow_rewrite)
    _validate_churn_guard(current, updated, deleted, allow_rewrite=allow_rewrite)
    _validate_document(updated)
    _refresh_evidence_if_available(root, updated)

    next_revision = current_revision + 1
    updated["revision"] = next_revision
    updated["authored_by"] = writer
    updated["updated_at"] = now_utc()
    if allow_rewrite_reason:
        metadata = updated.setdefault("metadata", {})
        if isinstance(metadata, dict):
            metadata["last_allow_rewrite"] = {
                "reason": allow_rewrite_reason,
                "authored_by": writer,
                "at": updated["updated_at"],
            }
    metadata = updated.setdefault("metadata", {})
    if isinstance(metadata, dict):
        metadata["last_operation_summary"] = {
            "operation_count": len(operations),
            "deleted_node_count": len(deleted["nodes"]),
            "deleted_flow_count": len(deleted["flows"]),
            "allow_rewrite": bool(allow_rewrite),
        }

    pending_updates = None
    if not dry_run and allow_rewrite:
        from .pending_refs import tombstone_deleted_refs

        pending_updates = tombstone_deleted_refs(
            root,
            deleted_nodes=deleted["nodes"],
            deleted_flows=deleted["flows"],
            timestamp=updated["updated_at"],
            write=False,
        )

    if not dry_run:
        if legacy_payload is not None:
            _write_legacy_snapshot(root, legacy_payload)
        _write_revision(
            root,
            current,
            updated,
            pending_updates=pending_updates,
            writer=writer,
            broken_locks=broken_locks,
            expected_current=legacy_payload if legacy_payload is not None else current,
        )
    return {
        "ok": True,
        "auto_migrated": legacy_payload is not None,
        "dry_run": bool(dry_run),
        "revision": next_revision,
        "base_revision": current_revision,
        "path": str(canvas_ir_path(root)),
    }


def _load_canvas_document_for_apply(
    root: Path,
    *,
    writer: str,
    reconcile: bool,
) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
    path = canvas_ir_path(root)
    _recover_incomplete_transaction(root)
    if not path.exists():
        return _empty_document(), None

    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise CanvasStoreError("INVALID_CANVAS", "canvas.ir.json must be a JSON object")
    if payload.get("schema") == CANVAS_V2_SCHEMA:
        return _load_v2_payload(root, payload, reconcile=reconcile), None

    from .migration import detect_v1_canvas, migrate_canvas_v1_to_v2

    if detect_v1_canvas(payload):
        migrated = migrate_canvas_v1_to_v2(
            payload,
            authored_by=writer,
            updated_at=now_utc(),
        )
        return _normalize_document(migrated), deepcopy(payload)

    raise CanvasStoreError(
        "UNSUPPORTED_CANVAS_SCHEMA",
        "canvas.ir.json must be agentcanvas.canvas.v2 or a recognized legacy AgentCanvas canvas",
        details={"schema": payload.get("schema")},
    )


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
        elif op == "delete_flow":
            target = _required_string(operation.get("target"), index, "target")
            flows.pop(target, None)
        else:
            raise CanvasStoreError(
                "UNSUPPORTED_OPERATION",
                _op_message(index, "op is not supported"),
                details={"op": op},
            )

    document["flows"] = list(flows.values())


def list_canvas_history(workspace: str | Path) -> Dict[str, Any]:
    """Return available canvas snapshots plus current revision metadata."""

    root = resolve_workspace(workspace)
    try:
        with workspace_write_lock(root, writer="canvas-history"):
            return _list_canvas_history_locked(root)
    except WorkspaceLockBusy as exc:
        raise _workspace_busy_error(exc)


def _list_canvas_history_locked(root: Path) -> Dict[str, Any]:
    current = _load_canvas_document_locked(root, reconcile=True)
    entries = []
    for path in _history_snapshot_paths(root):
        snapshot = _read_json_object(path)
        if not isinstance(snapshot, Mapping):
            continue
        entries.append(_history_entry(path, snapshot))
    entries.sort(key=lambda item: item["revision"], reverse=True)
    return {
        "ok": True,
        "current_revision": _revision(current),
        "current": _history_entry(canvas_ir_path(root), current),
        "history": entries,
    }


def restore_canvas_revision(
    workspace: str | Path,
    revision: int,
    *,
    base_revision: Optional[int] = None,
    authored_by: Optional[str] = None,
) -> Dict[str, Any]:
    """Restore a snapshot as a new canvas revision."""

    root = resolve_workspace(workspace)
    writer = authored_by or "agentcanvas-restore"
    try:
        with workspace_write_lock(root, writer=writer) as lock:
            return _restore_canvas_revision_locked(
                root,
                revision,
                base_revision=base_revision,
                authored_by=writer,
                broken_locks=_lock_breaks(lock),
            )
    except WorkspaceLockBusy as exc:
        raise _workspace_busy_error(exc)


def _restore_canvas_revision_locked(
    root: Path,
    revision: int,
    *,
    base_revision: Optional[int],
    authored_by: str,
    broken_locks: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    current = _load_canvas_document_locked(root, reconcile=True)
    current_revision = _revision(current)
    if base_revision is not None and int(base_revision) != current_revision:
        raise CanvasStoreError(
            "REVISION_CONFLICT",
            "base_revision does not match the current canvas revision",
            revision=current_revision,
            details={
                "base_revision": int(base_revision),
                "current_revision": current_revision,
                "changed_since": _changed_since_summary(current, int(base_revision)),
            },
        )

    try:
        target_revision = int(revision)
    except (TypeError, ValueError):
        raise CanvasStoreError("INVALID_REVISION", "revision must be an integer")

    snapshot = _load_history_snapshot(root, target_revision)
    if snapshot is None:
        raise CanvasStoreError(
            "REVISION_NOT_FOUND",
            "requested canvas history revision was not found",
            details={"revision": target_revision},
        )
    _validate_document(snapshot)

    updated = deepcopy(snapshot)
    updated["revision"] = current_revision + 1
    updated["authored_by"] = authored_by
    updated["updated_at"] = now_utc()
    metadata = updated.setdefault("metadata", {})
    if isinstance(metadata, dict):
        metadata["restored_from_revision"] = target_revision

    _write_revision(root, current, updated, writer=authored_by, broken_locks=broken_locks, expected_current=current)
    return {
        "ok": True,
        "revision": updated["revision"],
        "base_revision": current_revision,
        "restored_revision": target_revision,
        "path": str(canvas_ir_path(root)),
    }


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
    _validate_evidence_refs(flow, "flow", flow_id=flow_id)
    _validate_confidence(flow, "flow", flow_id=flow_id)

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
        _validate_status(node, flow_id=flow_id, node_id=node_id)
        _validate_evidence_refs(node, "node", flow_id=flow_id, node_id=node_id)
        _validate_confidence(node, "node", flow_id=flow_id, node_id=node_id)
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
        _validate_evidence_refs(edge, "edge", flow_id=flow_id, edge_id=edge_id)
        _validate_confidence(edge, "edge", flow_id=flow_id, edge_id=edge_id)
        source = edge.get("source")
        target = edge.get("target")
        if source not in node_ids or target not in node_ids:
            raise CanvasStoreError(
                "DANGLING_EDGE_ENDPOINT",
                "edge endpoints must point at active nodes in the same flow",
                details={"flow": flow_id, "edge": edge_id, "source": source, "target": target},
            )


def _validate_status(node: Mapping[str, Any], *, flow_id: str, node_id: str) -> None:
    status = node.get("status")
    if status is not None and status not in KNOWN_STATUSES:
        raise CanvasStoreError(
            "UNKNOWN_STATUS",
            "node.status is not supported",
            details={"flow": flow_id, "node": node_id, "status": status},
        )


def _validate_evidence_refs(
    item: Mapping[str, Any],
    item_kind: str,
    *,
    flow_id: str,
    node_id: Optional[str] = None,
    edge_id: Optional[str] = None,
) -> None:
    refs = item.get("evidence_refs")
    if refs is None:
        return
    details = _validation_details(flow_id=flow_id, node_id=node_id, edge_id=edge_id)
    if not isinstance(refs, list):
        raise CanvasStoreError(
            "INVALID_EVIDENCE_REFS",
            "%s.evidence_refs must be a list" % item_kind,
            details=details,
        )
    for index, ref in enumerate(refs):
        if not _non_empty(ref):
            ref_details = dict(details)
            ref_details["index"] = index
            raise CanvasStoreError(
                "INVALID_EVIDENCE_REF",
                "%s.evidence_refs entries must be non-empty strings" % item_kind,
                details=ref_details,
            )


def _validate_confidence(
    item: Mapping[str, Any],
    item_kind: str,
    *,
    flow_id: str,
    node_id: Optional[str] = None,
    edge_id: Optional[str] = None,
) -> None:
    confidence = item.get("confidence")
    if confidence is None:
        return
    details = _validation_details(flow_id=flow_id, node_id=node_id, edge_id=edge_id)
    if not isinstance(confidence, Mapping):
        raise CanvasStoreError(
            "INVALID_CONFIDENCE",
            "%s.confidence must be an object" % item_kind,
            details=details,
        )
    level = confidence.get("level")
    if level is not None and level not in KNOWN_CONFIDENCE_LEVELS:
        level_details = dict(details)
        level_details["level"] = level
        raise CanvasStoreError(
            "INVALID_CONFIDENCE",
            "%s.confidence.level is not supported" % item_kind,
            details=level_details,
        )
    reason = confidence.get("reason")
    if reason is not None and not isinstance(reason, str):
        reason_details = dict(details)
        reason_details["field"] = "reason"
        raise CanvasStoreError(
            "INVALID_CONFIDENCE",
            "%s.confidence.reason must be a string" % item_kind,
            details=reason_details,
        )


def _validation_details(
    *,
    flow_id: str,
    node_id: Optional[str] = None,
    edge_id: Optional[str] = None,
) -> Dict[str, Any]:
    details: Dict[str, Any] = {"flow": flow_id}
    if node_id is not None:
        details["node"] = node_id
    if edge_id is not None:
        details["edge"] = edge_id
    return details


def _load_v2_payload(
    root: Path,
    payload: Mapping[str, Any],
    *,
    reconcile: bool,
) -> Dict[str, Any]:
    document = _normalize_document(payload)
    if reconcile:
        return _reconcile_manual_edit(root, document)
    return document


def _validate_referenced_deletes(
    workspace: Path,
    deleted: Mapping[str, Set[str]],
    *,
    allow_rewrite: Optional[Mapping[str, Any]],
) -> None:
    if allow_rewrite:
        return

    deleted_pairs: Set[Tuple[str, str]] = set()
    for node_id in deleted.get("nodes", set()):
        deleted_pairs.add(("node", node_id))
    for flow_id in deleted.get("flows", set()):
        deleted_pairs.add(("flow", flow_id))
    if not deleted_pairs:
        return

    from .pending_refs import list_open_referenced_ids

    references = list_open_referenced_ids(workspace)
    blocked = sorted(
        {
            "%s:%s" % (kind, item_id)
            for kind, item_id in deleted_pairs
            if (kind, item_id) in references
        }
    )
    if blocked:
        raise CanvasStoreError(
            "REFERENCED_ID_REMOVED",
            "operation removes ids referenced by open pending requests",
            details={
                "ids": blocked,
                "repair_hint": "Resolve, cancel, or allow_rewrite the pending change that references these ids before removing them.",
            },
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
        if not is_ref_protecting(item.get("status", PENDING)):
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


def _allow_rewrite_reason(allow_rewrite: Optional[Mapping[str, Any]]) -> Optional[str]:
    if allow_rewrite is None:
        return None
    reason = allow_rewrite.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        raise CanvasStoreError(
            "INVALID_BATCH",
            "allow_rewrite.reason is required when allow_rewrite is provided",
            details={"repair_hint": "Pass allow_rewrite as {\"reason\": \"why the rewrite is intentional\"}."},
        )
    return reason.strip()


def _deleted_id_summary(
    previous: Mapping[str, Any],
    updated: Mapping[str, Any],
) -> Dict[str, Any]:
    before_flows = _flow_node_ids(previous)
    after_flows = _flow_node_ids(updated)
    deleted_flows = set(before_flows) - set(after_flows)
    deleted_nodes: Set[str] = set()
    per_flow: Dict[str, Dict[str, Any]] = {}
    for flow_id, before_nodes in before_flows.items():
        after_nodes = after_flows.get(flow_id, set())
        vanished = set(before_nodes) - set(after_nodes)
        if flow_id in deleted_flows:
            vanished = set(before_nodes)
        if vanished:
            deleted_nodes.update(vanished)
        per_flow[flow_id] = {
            "existing_count": len(before_nodes),
            "vanished_count": len(vanished),
            "vanished_ids": sorted(vanished),
            "flow_deleted": flow_id in deleted_flows,
        }
    total_existing = sum(item["existing_count"] for item in per_flow.values())
    total_vanished = sum(item["vanished_count"] for item in per_flow.values())
    return {
        "nodes": deleted_nodes,
        "flows": deleted_flows,
        "per_flow": per_flow,
        "total_existing": total_existing,
        "total_vanished": total_vanished,
    }


def _flow_node_ids(document: Mapping[str, Any]) -> Dict[str, Set[str]]:
    flows: Dict[str, Set[str]] = {}
    for flow in document.get("flows") or []:
        if not isinstance(flow, Mapping) or not isinstance(flow.get("id"), str):
            continue
        node_ids = {
            node.get("id")
            for node in flow.get("nodes") or []
            if isinstance(node, Mapping) and isinstance(node.get("id"), str)
        }
        flows[flow["id"]] = node_ids
    return flows


def _validate_churn_guard(
    previous: Mapping[str, Any],
    updated: Mapping[str, Any],
    deleted: Mapping[str, Any],
    *,
    allow_rewrite: Optional[Mapping[str, Any]],
) -> None:
    if allow_rewrite:
        return

    for flow_id, stats in sorted((deleted.get("per_flow") or {}).items()):
        existing_count = int(stats.get("existing_count") or 0)
        vanished_count = int(stats.get("vanished_count") or 0)
        ratio = vanished_count / existing_count if existing_count else 0
        if vanished_count >= 3 and ratio > 0.60:
            raise CanvasStoreError(
                "ID_CHURN",
                "operation removes too many existing node ids from one flow",
                revision=_revision(previous),
                details={
                    "scope": "flow",
                    "flow": flow_id,
                    "vanished_count": vanished_count,
                    "existing_count": existing_count,
                    "ratio": ratio,
                    "vanished_ids": stats.get("vanished_ids") or [],
                    "flow_deleted": bool(stats.get("flow_deleted")),
                    "repair_hint": "Preserve existing ids for unchanged behavior, or pass allow_rewrite.reason for an intentional rewrite.",
                },
            )

    total_existing = int(deleted.get("total_existing") or 0)
    total_vanished = int(deleted.get("total_vanished") or 0)
    ratio = total_vanished / total_existing if total_existing else 0
    if total_vanished >= 3 and ratio > 0.40:
        raise CanvasStoreError(
            "ID_CHURN",
            "operation removes too many existing node ids across the canvas",
            revision=_revision(previous),
            details={
                "scope": "document",
                "vanished_count": total_vanished,
                "existing_count": total_existing,
                "ratio": ratio,
                "vanished_ids": sorted(deleted.get("nodes") or []),
                "repair_hint": "Apply smaller focused edits, preserve stable ids, or pass allow_rewrite.reason for an intentional rewrite.",
            },
        )


def _refresh_evidence_if_available(root: Path, document: Dict[str, Any]) -> None:
    _, workflow_path, _ = state_paths(root)
    if not workflow_path.is_file():
        return
    try:
        from .evidence import build_current_workflow_evidence

        document["evidence"] = build_current_workflow_evidence(root)
    except (OSError, ValueError):
        return


def _reconcile_manual_edit(root: Path, document: Dict[str, Any]) -> Dict[str, Any]:
    head = _read_history_head(root)
    if not head:
        return document
    known_sha = head.get("sha256")
    current_sha = _document_sha256(document)
    if known_sha == current_sha:
        return document

    previous = head.get("document")
    if not isinstance(previous, Mapping):
        return document
    previous_document = _normalize_document(previous)
    _validate_document(document)

    reconciled = deepcopy(document)
    reconciled["revision"] = max(_revision(previous_document), _revision(document)) + 1
    reconciled["authored_by"] = "manual-edit"
    reconciled["updated_at"] = now_utc()
    metadata = reconciled.setdefault("metadata", {})
    if isinstance(metadata, dict):
        metadata["manual_edit"] = {
            "detected_from_revision": _revision(previous_document),
            "detected_at": reconciled["updated_at"],
        }
    _write_revision(root, previous_document, reconciled, writer="manual-edit", expected_current=document)
    return reconciled


def _write_revision(
    root: Path,
    previous: Dict[str, Any],
    updated: Dict[str, Any],
    *,
    pending_updates: Optional[List[Dict[str, Any]]] = None,
    writer: str = "agentcanvas",
    broken_locks: Optional[List[Dict[str, Any]]] = None,
    expected_current: Optional[Mapping[str, Any]] = None,
) -> None:
    ensure_state_dirs(root)
    history_dir = root / STATE_DIR_NAME / HISTORY_DIR_NAME
    history_dir.mkdir(parents=True, exist_ok=True)
    history_path = history_dir / ("canvas.%s.json" % _revision(previous))
    head_path = history_dir / HISTORY_HEAD_FILENAME
    txn_path = _transaction_path(history_dir)
    canvas_path = canvas_ir_path(root)
    pending_updates = pending_updates or []
    pending_before = _pending_before_images(pending_updates)
    tmp_history = history_path.with_name(".%s.%s.tmp" % (history_path.name, uuid.uuid4().hex))
    tmp_canvas = canvas_path.with_name(".%s.%s.tmp" % (canvas_path.name, uuid.uuid4().hex))
    tmp_head = head_path.with_name(".%s.%s.tmp" % (head_path.name, uuid.uuid4().hex))
    try:
        _write_transaction_journal(
            txn_path,
            previous=previous,
            pending_before=pending_before,
            history_path=history_path,
            head_path=head_path,
            writer=writer,
            broken_locks=broken_locks or [],
        )
        tmp_history.write_text(json.dumps(previous, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp_canvas.write_text(json.dumps(updated, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp_head.write_text(json.dumps(_history_head(updated), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        _assert_canvas_head_matches(root, expected_current if expected_current is not None else previous)
        tmp_history.replace(history_path)
        tmp_canvas.replace(canvas_path)
        if CRASH_AFTER_CANVAS_REPLACE_FOR_TESTS:
            raise RuntimeError("simulated crash after canvas replace")
        _write_pending_updates(pending_updates)
        tmp_head.replace(head_path)
        _unlink_if_exists(txn_path)
        _prune_history(root)
    finally:
        if tmp_history.exists():
            tmp_history.unlink()
        if tmp_canvas.exists():
            tmp_canvas.unlink()
        if tmp_head.exists():
            tmp_head.unlink()


def _write_transaction_journal(
    txn_path: Path,
    *,
    previous: Mapping[str, Any],
    pending_before: List[Dict[str, Any]],
    history_path: Path,
    head_path: Path,
    writer: str,
    broken_locks: List[Dict[str, Any]],
) -> None:
    payload = {
        "schema": "agentcanvas.canvas_transaction.v1",
        "pid": os.getpid(),
        "writer": writer,
        "nonce": txn_path.name,
        "created_at": now_utc(),
        "started_at_epoch": time.time(),
        "broken_locks": broken_locks,
        "previous_canvas": _normalize_document(previous),
        "pending_before": pending_before,
        "history_before": {
            "path": str(history_path),
            "payload": _read_json_object(history_path),
        },
        "head_before": {
            "path": str(head_path),
            "payload": _read_json_object(head_path),
        },
    }
    tmp_txn = txn_path.with_name(".%s.%s.tmp" % (txn_path.name, uuid.uuid4().hex))
    try:
        tmp_txn.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp_txn.replace(txn_path)
    finally:
        if tmp_txn.exists():
            tmp_txn.unlink()


def _recover_incomplete_transaction(root: Path) -> None:
    for txn_path in _transaction_paths(root):
        _recover_transaction_path(root, txn_path)


def _recover_transaction_path(root: Path, txn_path: Path) -> None:
    txn = _read_json_object(txn_path)
    if not isinstance(txn, Mapping):
        return
    if not _transaction_is_recoverable(txn):
        return
    current_canvas = _read_json_object(canvas_ir_path(root))
    head = _read_history_head(root)
    if (
        isinstance(current_canvas, Mapping)
        and isinstance(head, Mapping)
        and head.get("sha256") == _document_sha256(_normalize_document(current_canvas))
    ):
        _unlink_if_exists(txn_path)
        return
    previous_canvas = txn.get("previous_canvas")
    if isinstance(previous_canvas, Mapping):
        save_path = canvas_ir_path(root)
        tmp_canvas = save_path.with_name(".%s.%s.tmp" % (save_path.name, uuid.uuid4().hex))
        try:
            tmp_canvas.write_text(json.dumps(previous_canvas, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            tmp_canvas.replace(save_path)
        finally:
            if tmp_canvas.exists():
                tmp_canvas.unlink()
    for key in ("history_before", "head_before"):
        item = txn.get(key)
        if not isinstance(item, Mapping):
            continue
        _restore_transaction_file(item)
    for item in txn.get("pending_before") or []:
        if not isinstance(item, Mapping):
            continue
        _restore_transaction_file(item)
    _unlink_if_exists(txn_path)


def _transaction_paths(root: Path) -> List[Path]:
    history_dir = root / STATE_DIR_NAME / HISTORY_DIR_NAME
    if not history_dir.is_dir():
        return []
    paths = []
    legacy = history_dir / HISTORY_TXN_FILENAME
    if legacy.exists():
        paths.append(legacy)
    paths.extend(sorted(history_dir.glob("%s*.json" % HISTORY_TXN_PREFIX)))
    return paths


def _transaction_path(history_dir: Path) -> Path:
    return history_dir / ("%s%s-%s.json" % (HISTORY_TXN_PREFIX, os.getpid(), uuid.uuid4().hex[:10]))


def _transaction_is_recoverable(txn: Mapping[str, Any]) -> bool:
    return is_stale_process_claim(txn, lease_seconds=TRANSACTION_STALE_SECONDS)


def _assert_canvas_head_matches(root: Path, expected_payload: Mapping[str, Any]) -> None:
    current_payload = _read_json_object(canvas_ir_path(root))
    if current_payload is None:
        if _revision(expected_payload) == 0:
            return
        raise CanvasStoreError(
            "REVISION_CONFLICT",
            "canvas changed before AgentCanvas could replace it",
            revision=0,
            details={
                "base_revision": _revision(expected_payload),
                "current_revision": 0,
                "repair_hint": "Refetch the latest canvas revision and retry the operation.",
            },
        )
    if _document_sha256(current_payload) == _document_sha256(expected_payload):
        return
    if not isinstance(current_payload, Mapping) or current_payload.get("schema") != CANVAS_V2_SCHEMA:
        from .migration import detect_v1_canvas

        if _revision(expected_payload) == 1 and isinstance(current_payload, Mapping) and detect_v1_canvas(current_payload):
            return
        raise CanvasStoreError(
            "REVISION_CONFLICT",
            "canvas schema changed before AgentCanvas could replace it",
            revision=0,
            details={
                "schema": current_payload.get("schema") if isinstance(current_payload, Mapping) else None,
                "repair_hint": "Refetch the latest canvas revision and retry the operation.",
            },
        )
    current = _normalize_document(current_payload)
    expected = _normalize_document(expected_payload)
    if _revision(current) == _revision(expected) and _document_sha256(current) == _document_sha256(expected):
        return
    raise CanvasStoreError(
        "REVISION_CONFLICT",
        "canvas changed before AgentCanvas could replace it",
        revision=_revision(current),
        details={
            "base_revision": _revision(expected),
            "current_revision": _revision(current),
            "changed_since": _changed_since_summary(current, _revision(expected)),
            "repair_hint": "Refetch the latest canvas revision and retry the operation.",
        },
    )


def _workspace_busy_error(error: WorkspaceLockBusy) -> CanvasStoreError:
    return CanvasStoreError(
        "WORKSPACE_BUSY",
        "AgentCanvas workspace is busy; another writer is updating local state",
        details={
            "path": str(getattr(error, "path", getattr(error, "lock_path", ""))),
            "writer": getattr(error, "writer", "agentcanvas"),
            "retryable": True,
            "details": getattr(error, "details", {}),
            "repair_hint": "Wait briefly, refetch the latest revision, and retry the operation.",
        },
    )


def _lock_breaks(lock: Any) -> List[Dict[str, Any]]:
    events = getattr(lock, "break_events", None)
    if events is None:
        events = getattr(lock, "broken_locks", [])
    return [dict(event) for event in events if isinstance(event, Mapping)]


def _pause_after_revision_check_for_tests() -> None:
    marker = os.environ.get("AGENTCANVAS_TEST_PAUSE_AFTER_REVISION_CHECK")
    if not marker:
        return
    release = os.environ.get("AGENTCANVAS_TEST_RELEASE_AFTER_REVISION_CHECK")
    timeout = float(os.environ.get("AGENTCANVAS_TEST_PAUSE_TIMEOUT_SECONDS", "10"))
    Path(marker).write_text(str(os.getpid()), encoding="utf-8")
    if not release:
        return
    release_path = Path(release)
    deadline = time.monotonic() + timeout
    while not release_path.exists():
        if time.monotonic() >= deadline:
            raise RuntimeError("timed out waiting for test revision-check release")
        time.sleep(0.01)


def _restore_transaction_file(item: Mapping[str, Any]) -> None:
    path_value = item.get("path")
    payload = item.get("payload")
    if not isinstance(path_value, str):
        return
    path = Path(path_value)
    if payload is None:
        _unlink_if_exists(path)
    elif isinstance(payload, Mapping):
        tmp_path = path.with_name(".%s.%s.tmp" % (path.name, uuid.uuid4().hex))
        try:
            tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            tmp_path.replace(path)
        finally:
            if tmp_path.exists():
                tmp_path.unlink()


def _pending_before_images(pending_updates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    before = []
    for record in pending_updates:
        if not isinstance(record, Mapping):
            continue
        json_path = record.get("json_path")
        if not isinstance(json_path, str):
            continue
        path = Path(json_path)
        before.append({"path": str(path), "payload": _read_json_object(path)})
    return before


def _write_pending_updates(pending_updates: List[Dict[str, Any]]) -> None:
    from agentcanvas.ir import atomic_write_json

    for record in pending_updates:
        if not isinstance(record, Mapping):
            continue
        json_path = record.get("json_path")
        if not isinstance(json_path, str):
            continue
        payload = dict(record)
        payload.pop("json_path", None)
        atomic_write_json(Path(json_path), payload)


def _write_legacy_snapshot(root: Path, payload: Dict[str, Any]) -> None:
    ensure_state_dirs(root)
    history_dir = root / STATE_DIR_NAME / HISTORY_DIR_NAME
    history_dir.mkdir(parents=True, exist_ok=True)
    history_path = history_dir / "canvas.pre-v2.json"
    tmp_history = history_path.with_name(".%s.%s.tmp" % (history_path.name, uuid.uuid4().hex))
    try:
        tmp_history.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp_history.replace(history_path)
    finally:
        if tmp_history.exists():
            tmp_history.unlink()


def _history_head(document: Mapping[str, Any]) -> Dict[str, Any]:
    normalized = _normalize_document(document)
    return {
        "schema": "agentcanvas.canvas_history_head.v1",
        "revision": _revision(normalized),
        "sha256": _document_sha256(normalized),
        "updated_at": normalized.get("updated_at"),
        "authored_by": normalized.get("authored_by"),
        "document": normalized,
    }


def _read_history_head(root: Path) -> Optional[Dict[str, Any]]:
    path = root / STATE_DIR_NAME / HISTORY_DIR_NAME / HISTORY_HEAD_FILENAME
    payload = _read_json_object(path)
    return payload if isinstance(payload, dict) else None


def _history_snapshot_paths(root: Path) -> List[Path]:
    history_dir = root / STATE_DIR_NAME / HISTORY_DIR_NAME
    if not history_dir.is_dir():
        return []
    paths = []
    for path in history_dir.glob("canvas.*.json"):
        if path.name in {HISTORY_HEAD_FILENAME, "canvas.pre-v2.json"}:
            continue
        revision = _revision_from_history_path(path)
        if revision is not None:
            paths.append(path)
    return paths


def _revision_from_history_path(path: Path) -> Optional[int]:
    name = path.name
    if not name.startswith("canvas.") or not name.endswith(".json"):
        return None
    raw = name[len("canvas.") : -len(".json")]
    try:
        return int(raw)
    except ValueError:
        return None


def _load_history_snapshot(root: Path, revision: int) -> Optional[Dict[str, Any]]:
    path = root / STATE_DIR_NAME / HISTORY_DIR_NAME / ("canvas.%s.json" % int(revision))
    payload = _read_json_object(path)
    if not isinstance(payload, Mapping):
        return None
    return _normalize_document(payload)


def _history_entry(path: Path, document: Mapping[str, Any]) -> Dict[str, Any]:
    try:
        size_bytes = path.stat().st_size
    except OSError:
        size_bytes = 0
    metadata = document.get("metadata") if isinstance(document.get("metadata"), Mapping) else {}
    allow_rewrite = metadata.get("last_allow_rewrite") if isinstance(metadata.get("last_allow_rewrite"), Mapping) else {}
    op_summary = metadata.get("last_operation_summary") if isinstance(metadata.get("last_operation_summary"), Mapping) else {}
    flows = document.get("flows") if isinstance(document.get("flows"), list) else []
    flow_titles = []
    for flow in flows:
        if isinstance(flow, Mapping) and isinstance(flow.get("title"), str) and flow.get("title"):
            flow_titles.append(flow["title"])
    return {
        "revision": _revision(document),
        "authored_by": document.get("authored_by"),
        "updated_at": document.get("updated_at"),
        "path": str(path),
        "size_bytes": size_bytes,
        "op_summary": dict(op_summary),
        "allow_rewrite_reason": allow_rewrite.get("reason") if isinstance(allow_rewrite.get("reason"), str) else None,
        "flow_summary": {
            "count": len(flows),
            "titles": flow_titles[:8],
            "truncated": len(flow_titles) > 8,
        },
    }


def _prune_history(root: Path) -> None:
    paths = _history_snapshot_paths(root)
    if not paths:
        return

    now = time.time()
    kept = []
    for path in paths:
        try:
            stat = path.stat()
        except OSError:
            continue
        if now - stat.st_mtime > HISTORY_MAX_AGE_SECONDS:
            _unlink_if_exists(path)
            continue
        kept.append(path)

    kept.sort(key=lambda item: _revision_from_history_path(item) or -1, reverse=True)
    for path in kept[HISTORY_MAX_REVISIONS:]:
        _unlink_if_exists(path)
    kept = [path for path in kept[:HISTORY_MAX_REVISIONS] if path.exists()]

    def total_bytes(items: List[Path]) -> int:
        total = 0
        for item in items:
            try:
                total += item.stat().st_size
            except OSError:
                pass
        return total

    while kept and total_bytes(kept) > HISTORY_MAX_BYTES:
        oldest = kept.pop()
        _unlink_if_exists(oldest)


def _unlink_if_exists(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def _document_bytes(document: Mapping[str, Any]) -> bytes:
    return json.dumps(document, indent=2, sort_keys=True).encode("utf-8")


def _document_sha256(document: Mapping[str, Any]) -> str:
    return hashlib.sha256(_document_bytes(document)).hexdigest()


def _read_json_object(path: Path) -> Optional[Dict[str, Any]]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


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
