"""Public validation helpers for AgentCanvas canvas v2 documents."""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Set

from .store import CanvasStoreError, _validate_document

VALIDATION_MODES = {"authoring", "strict"}

REPAIR_HINTS = {
    "INVALID_VALIDATION_MODE": "Use mode='authoring' while drafting or mode='strict' before publishing.",
    "INVALID_CANVAS": "Provide a canvas object with schema 'agentcanvas.canvas.v2', an app object, and a flows list.",
    "INVALID_FLOW": "Make every flow an object with a non-empty id plus nodes and edges lists.",
    "DUPLICATE_ID": "Give each flow, node, and edge id a unique stable value within its scope.",
    "INVALID_NODE": "Make every node an object with non-empty id, kind, and title fields.",
    "UNKNOWN_NODE_KIND": "Use a supported node kind: When, Do, Decision, Loop, Parallel, Join, Wait, SubFlow, or End.",
    "DANGLING_FLOW_REF": "Point SubFlow.flow_ref at an existing flow id in this canvas.",
    "DANGLING_ENTRY_NODE": "Set flow.entry_node to the id of a node in the same flow.",
    "EDGE_ID_REQUIRED": "Add a stable non-empty id to the edge.",
    "INVALID_EDGE": "Make every edge an object with id, kind, source, and target fields.",
    "UNKNOWN_EDGE_KIND": "Use a supported edge kind: normal, branch, loop_body, loop_back, loop_exit, parallel, error, or async.",
    "DANGLING_EDGE_ENDPOINT": "Point edge.source and edge.target at existing nodes in the same flow.",
    "EMPTY_CANVAS": "Add at least one flow before running strict validation.",
    "ENTRY_NODE_REQUIRED": "Set flow.entry_node to the first node that should run in each non-empty flow.",
    "UNREACHABLE_NODE": "Connect every node from flow.entry_node or remove nodes that are not part of the flow.",
    "DECISION_BRANCHES_REQUIRED": "Add at least two outgoing branch-style edges from the Decision node.",
    "LOOP_EXIT_REQUIRED": "Add both a loop_body edge and a loop_exit edge from the Loop node.",
    "PARALLEL_BRANCHES_REQUIRED": "Add at least two outgoing parallel edges from the Parallel node.",
    "JOIN_INPUTS_REQUIRED": "Connect at least two incoming paths into the Join node.",
    "END_HAS_OUTGOING_EDGE": "Remove outgoing edges from End nodes or change the node kind if the flow continues.",
}


class CanvasValidationError(CanvasStoreError):
    """Validation error with a recovery hint in the structured envelope."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        repair_hint: Optional[str] = None,
        revision: Optional[int] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(code, message, revision=revision, details=details)
        self.repair_hint = repair_hint or _repair_hint(code)

    def to_dict(self) -> Dict[str, Any]:
        payload = super().to_dict()
        if self.repair_hint:
            payload["error"]["repair_hint"] = self.repair_hint
        return payload


def validate_canvas_v2(document: Mapping[str, Any], *, mode: str = "authoring") -> Dict[str, Any]:
    """Validate a canvas v2 document and return a compact summary.

    ``authoring`` mode checks the graph contract while allowing unfinished
    canvases. ``strict`` mode adds checks that are useful before publishing or
    using a canvas as a complete source of truth.
    """

    if mode not in VALIDATION_MODES:
        raise _validation_error(
            "INVALID_VALIDATION_MODE",
            "validation mode must be authoring or strict",
            details={"mode": mode},
        )
    if not isinstance(document, Mapping):
        raise _validation_error("INVALID_CANVAS", "canvas document must be an object")

    try:
        _validate_document(document)
    except CanvasStoreError as error:
        raise _from_store_error(error) from error
    if mode == "strict":
        _validate_strict(document)

    flow_count = len(document.get("flows") or [])
    node_count = sum(len(flow.get("nodes") or []) for flow in document.get("flows") or [])
    edge_count = sum(len(flow.get("edges") or []) for flow in document.get("flows") or [])
    return {
        "ok": True,
        "mode": mode,
        "flow_count": flow_count,
        "node_count": node_count,
        "edge_count": edge_count,
        "warnings": _authoring_warnings(document) if mode == "authoring" else [],
    }


def _validate_strict(document: Mapping[str, Any]) -> None:
    flows = document.get("flows") or []
    if not flows:
        raise _validation_error("EMPTY_CANVAS", "strict validation requires at least one flow")

    for flow in flows:
        flow_id = str(flow.get("id"))
        nodes = flow.get("nodes") or []
        edges = flow.get("edges") or []
        node_ids = {node.get("id") for node in nodes if isinstance(node, Mapping)}
        if nodes and not flow.get("entry_node"):
            raise _validation_error(
                "ENTRY_NODE_REQUIRED",
                "strict validation requires entry_node for each non-empty flow",
                details={"flow": flow_id},
            )
        entry_node = flow.get("entry_node")
        if entry_node and nodes:
            reachable = _reachable_nodes(str(entry_node), edges)
            unreachable = sorted(str(node_id) for node_id in node_ids if node_id not in reachable)
            if unreachable:
                raise _validation_error(
                    "UNREACHABLE_NODE",
                    "strict validation requires every node to be reachable from entry_node",
                    details={"flow": flow_id, "nodes": unreachable},
                )
        _validate_kind_contracts(flow_id, nodes, edges)


def _authoring_warnings(document: Mapping[str, Any]) -> List[Dict[str, Any]]:
    warnings: List[Dict[str, Any]] = []
    flows = document.get("flows") or []
    for flow in flows:
        if not isinstance(flow, Mapping):
            continue
        flow_id = str(flow.get("id"))
        nodes = flow.get("nodes") or []
        edges = flow.get("edges") or []
        outgoing: Dict[str, List[Mapping[str, Any]]] = {}
        for edge in edges:
            if not isinstance(edge, Mapping):
                continue
            source = edge.get("source")
            if isinstance(source, str):
                outgoing.setdefault(source, []).append(edge)
        if nodes and not flow.get("entry_node"):
            warnings.append(
                _warning(
                    "ENTRY_NODE_MISSING",
                    "flow has nodes but no entry_node yet",
                    details={"flow": flow_id},
                    repair_hint="Set flow.entry_node when the first runnable node is known.",
                )
            )
        for node in nodes:
            if not isinstance(node, Mapping):
                continue
            metadata = node.get("metadata") if isinstance(node.get("metadata"), Mapping) else {}
            if metadata.get("degraded") or metadata.get("incomplete") or metadata.get("severity") == "warning":
                warnings.append(
                    _warning(
                        "DEGRADED_NODE",
                        "node is marked degraded or incomplete for authoring",
                        details={"flow": flow_id, "node": node.get("id")},
                        repair_hint="Confirm the behavior and remove the degraded or incomplete marker when resolved.",
                    )
                )
            if node.get("kind") != "End" and not node.get("evidence_refs"):
                warnings.append(
                    _warning(
                        "EVIDENCE_REFS_MISSING",
                        "node has no evidence_refs yet",
                        details={"flow": flow_id, "node": node.get("id")},
                        repair_hint="Attach evidence_refs when this node is grounded in source facts, or keep it as an authoring draft.",
                    )
                )
            node_id = str(node.get("id"))
            node_outgoing = outgoing.get(node_id, [])
            if node.get("kind") == "Decision":
                branches = [
                    edge
                    for edge in node_outgoing
                    if edge.get("kind") in {"branch", "error", "loop_back", "loop_exit"}
                ]
                if len(branches) < 2:
                    warnings.append(
                        _warning(
                            "DECISION_BRANCHES_INCOMPLETE",
                            "Decision has fewer than two outgoing branches",
                            details={"flow": flow_id, "node": node_id},
                            repair_hint="Add both the true path and fallback path before treating this flow as complete.",
                        )
                    )
            if node.get("kind") == "Loop":
                has_body = any(edge.get("kind") == "loop_body" for edge in node_outgoing)
                has_exit = any(edge.get("kind") == "loop_exit" for edge in node_outgoing)
                if not has_body or not has_exit:
                    warnings.append(
                        _warning(
                            "LOOP_EXIT_INCOMPLETE",
                            "Loop is missing either its body path or exit path",
                            details={"flow": flow_id, "node": node_id},
                            repair_hint="Add a loop_body path and a loop_exit path so readers can see when the loop stops.",
                        )
                    )
    return warnings


def _validate_kind_contracts(flow_id: str, nodes: List[Any], edges: List[Any]) -> None:
    incoming: Dict[str, List[Mapping[str, Any]]] = {}
    outgoing: Dict[str, List[Mapping[str, Any]]] = {}
    for edge in edges:
        if not isinstance(edge, Mapping):
            continue
        source = edge.get("source")
        target = edge.get("target")
        if isinstance(source, str):
            outgoing.setdefault(source, []).append(edge)
        if isinstance(target, str):
            incoming.setdefault(target, []).append(edge)

    for node in nodes:
        if not isinstance(node, Mapping):
            continue
        node_id = str(node.get("id"))
        kind = node.get("kind")
        node_outgoing = outgoing.get(node_id, [])
        node_incoming = incoming.get(node_id, [])
        if kind == "Decision":
            branches = [
                edge
                for edge in node_outgoing
                if edge.get("kind") in {"branch", "error", "loop_back", "loop_exit"}
            ]
            if len(branches) < 2:
                raise _validation_error(
                    "DECISION_BRANCHES_REQUIRED",
                    "strict validation requires each Decision to have at least two outgoing branches",
                    details={"flow": flow_id, "node": node_id},
                )
        elif kind == "Loop":
            has_body = any(edge.get("kind") == "loop_body" for edge in node_outgoing)
            has_exit = any(edge.get("kind") == "loop_exit" for edge in node_outgoing)
            if not has_body or not has_exit:
                raise _validation_error(
                    "LOOP_EXIT_REQUIRED",
                    "strict validation requires each Loop to have loop_body and loop_exit edges",
                    details={"flow": flow_id, "node": node_id},
                )
        elif kind == "Parallel":
            parallel_edges = [edge for edge in node_outgoing if edge.get("kind") == "parallel"]
            if len(parallel_edges) < 2:
                raise _validation_error(
                    "PARALLEL_BRANCHES_REQUIRED",
                    "strict validation requires each Parallel node to fan out to at least two branches",
                    details={"flow": flow_id, "node": node_id},
                )
        elif kind == "Join":
            if len(node_incoming) < 2:
                raise _validation_error(
                    "JOIN_INPUTS_REQUIRED",
                    "strict validation requires each Join node to merge at least two incoming paths",
                    details={"flow": flow_id, "node": node_id},
                )
        elif kind == "End" and node_outgoing:
            raise _validation_error(
                "END_HAS_OUTGOING_EDGE",
                "strict validation requires End nodes to stop the flow",
                details={"flow": flow_id, "node": node_id},
            )


def _reachable_nodes(entry_node: str, edges: List[Any]) -> Set[str]:
    outgoing: Dict[str, List[str]] = {}
    for edge in edges:
        if not isinstance(edge, Mapping):
            continue
        source = edge.get("source")
        target = edge.get("target")
        if isinstance(source, str) and isinstance(target, str):
            outgoing.setdefault(source, []).append(target)

    seen: Set[str] = set()
    stack = [entry_node]
    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.add(current)
        stack.extend(outgoing.get(current, []))
    return seen


def _validation_error(
    code: str,
    message: str,
    *,
    details: Optional[Dict[str, Any]] = None,
) -> CanvasValidationError:
    return CanvasValidationError(code, message, details=details)


def _from_store_error(error: CanvasStoreError) -> CanvasValidationError:
    return CanvasValidationError(
        error.code,
        error.message,
        revision=error.revision,
        details=dict(error.details),
    )


def _warning(
    code: str,
    message: str,
    *,
    details: Optional[Dict[str, Any]] = None,
    repair_hint: Optional[str] = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "code": code,
        "message": message,
        "repair_hint": repair_hint or _repair_hint(code),
    }
    if details:
        payload["details"] = details
    return payload


def _repair_hint(code: str) -> str:
    return REPAIR_HINTS.get(code, "Fix the canvas_v2 shape reported by this validation error and run validation again.")
