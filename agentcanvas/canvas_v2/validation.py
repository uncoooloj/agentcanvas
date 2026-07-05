"""Public validation helpers for AgentCanvas canvas v2 documents."""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Set

from .store import CanvasStoreError, _validate_document

VALIDATION_MODES = {"authoring", "strict"}


def validate_canvas_v2(document: Mapping[str, Any], *, mode: str = "authoring") -> Dict[str, Any]:
    """Validate a canvas v2 document and return a compact summary.

    ``authoring`` mode checks the graph contract while allowing unfinished
    canvases. ``strict`` mode adds checks that are useful before publishing or
    using a canvas as a complete source of truth.
    """

    if mode not in VALIDATION_MODES:
        raise CanvasStoreError(
            "INVALID_VALIDATION_MODE",
            "validation mode must be authoring or strict",
            details={"mode": mode},
        )
    if not isinstance(document, Mapping):
        raise CanvasStoreError("INVALID_CANVAS", "canvas document must be an object")

    _validate_document(document)
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
    }


def _validate_strict(document: Mapping[str, Any]) -> None:
    flows = document.get("flows") or []
    if not flows:
        raise CanvasStoreError("EMPTY_CANVAS", "strict validation requires at least one flow")

    for flow in flows:
        flow_id = str(flow.get("id"))
        nodes = flow.get("nodes") or []
        edges = flow.get("edges") or []
        node_ids = {node.get("id") for node in nodes if isinstance(node, Mapping)}
        if nodes and not flow.get("entry_node"):
            raise CanvasStoreError(
                "ENTRY_NODE_REQUIRED",
                "strict validation requires entry_node for each non-empty flow",
                details={"flow": flow_id},
            )
        entry_node = flow.get("entry_node")
        if entry_node and nodes:
            reachable = _reachable_nodes(str(entry_node), edges)
            unreachable = sorted(str(node_id) for node_id in node_ids if node_id not in reachable)
            if unreachable:
                raise CanvasStoreError(
                    "UNREACHABLE_NODE",
                    "strict validation requires every node to be reachable from entry_node",
                    details={"flow": flow_id, "nodes": unreachable},
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
