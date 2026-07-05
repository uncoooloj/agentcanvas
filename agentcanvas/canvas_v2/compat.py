"""Compatibility adapters from canvas v2 graphs to the current display model."""

from __future__ import annotations

import copy
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from .migration import CANVAS_V2_SCHEMA


def flatten_canvas_v2(document: Mapping[str, Any]) -> Dict[str, Any]:
    """Render a v2 document as the v1 display wrapper the current frontend reads."""

    if not isinstance(document, Mapping) or document.get("schema") != CANVAS_V2_SCHEMA:
        raise ValueError("payload is not an agentcanvas.canvas.v2 document")

    app = document.get("app") if isinstance(document.get("app"), Mapping) else {}
    journeys = []
    for index, flow in enumerate(_list(document.get("flows"))):
        if isinstance(flow, Mapping):
            journey = _flatten_flow(flow, index)
            if journey is not None:
                journeys.append(journey)

    return {
        "appName": _string(app.get("name")) or "Workspace",
        "journeys": journeys,
        "isDemo": bool(app.get("is_demo") or app.get("isDemo")),
    }


def _flatten_flow(flow: Mapping[str, Any], index: int) -> Optional[Dict[str, Any]]:
    nodes = [_dict(node) for node in _list(flow.get("nodes")) if isinstance(node, Mapping)]
    if not nodes:
        return None

    nodes_by_id = {_string(node.get("id")): node for node in nodes if _string(node.get("id"))}
    outgoing: Dict[str, List[Dict[str, Any]]] = {}
    incoming: Dict[str, int] = {}
    for edge in _list(flow.get("edges")):
        if not isinstance(edge, Mapping):
            continue
        source = _string(edge.get("source"))
        target = _string(edge.get("target"))
        if source not in nodes_by_id or target not in nodes_by_id:
            continue
        edge_dict = _dict(edge)
        outgoing.setdefault(source, []).append(edge_dict)
        incoming[target] = incoming.get(target, 0) + 1

    for edge_list in outgoing.values():
        edge_list.sort(key=_edge_sort_key)

    start_id = _string(flow.get("entry_node"))
    if start_id not in nodes_by_id:
        start_id = _first_start(nodes, incoming)
    display_nodes = _walk_nodes(start_id, nodes_by_id, outgoing, set(), set()) if start_id else []
    if not display_nodes:
        return None

    first_step = next((node for node in display_nodes if node.get("kind") == "step" and node.get("role") == "when"), None)
    title = _string(flow.get("title")) or "Workspace flow"
    return {
        "id": _string(flow.get("id")) or "flow:%s" % index,
        "title": title,
        "summary": _string(flow.get("summary")) or "Mapped from your workspace.",
        "entry": _string(flow.get("entry")) or _string(first_step.get("text") if first_step else None) or title,
        "nodes": display_nodes,
    }


def _walk_nodes(
    start_id: str,
    nodes_by_id: Mapping[str, Mapping[str, Any]],
    outgoing: Mapping[str, Sequence[Mapping[str, Any]]],
    stop_ids: Set[str],
    seen: Set[str],
) -> List[Dict[str, Any]]:
    current = start_id
    display: List[Dict[str, Any]] = []

    while current and current in nodes_by_id and current not in seen and current not in stop_ids:
        seen.add(current)
        node = nodes_by_id[current]
        converted = _node_to_display(node, nodes_by_id, outgoing, seen)
        if converted is not None:
            display.append(converted)
        normal = _first_edge(outgoing.get(current), {"normal"})
        if normal is None:
            break
        current = _string(normal.get("target"))
    return display


def _node_to_display(
    node: Mapping[str, Any],
    nodes_by_id: Mapping[str, Mapping[str, Any]],
    outgoing: Mapping[str, Sequence[Mapping[str, Any]]],
    seen: Set[str],
) -> Optional[Dict[str, Any]]:
    kind = _string(node.get("kind"))
    metadata = node.get("metadata") if isinstance(node.get("metadata"), Mapping) else {}
    if kind == "End" and metadata.get("synthetic"):
        return None
    if kind == "Decision":
        return _decision_to_branch(node, nodes_by_id, outgoing, seen)

    role = "when" if kind == "When" else "do"
    title = _display_title(node)
    if kind == "Loop":
        title = "Repeat: %s" % title
    elif kind == "Parallel":
        title = "In parallel: %s" % title
    elif kind == "Wait":
        title = "Wait for: %s" % title
    elif kind == "SubFlow":
        title = "Open flow: %s" % title
    elif kind == "Join":
        title = "Join work: %s" % title
    elif kind == "End":
        title = "End: %s" % title

    payload = {
        "kind": "step",
        "id": _string(node.get("id")),
        "role": role,
        "text": title,
        "detail": _string(node.get("detail")),
    }
    _copy_display_metadata(payload, node)
    return _clean(payload)


def _decision_to_branch(
    node: Mapping[str, Any],
    nodes_by_id: Mapping[str, Mapping[str, Any]],
    outgoing: Mapping[str, Sequence[Mapping[str, Any]]],
    seen: Set[str],
) -> Dict[str, Any]:
    branch_edges = [edge for edge in outgoing.get(_string(node.get("id")), []) if edge.get("kind") == "branch"]
    branch_edges.sort(key=_edge_sort_key)
    if not branch_edges:
        payload = {
            "kind": "branch",
            "id": _string(node.get("id")),
            "condition": _display_title(node),
            "then": [],
            "otherwise": [],
        }
        _copy_display_metadata(payload, node)
        return payload

    then_nodes = _branch_path(branch_edges[0], nodes_by_id, outgoing, seen)
    if len(branch_edges) == 1:
        otherwise_nodes: List[Dict[str, Any]] = []
    elif len(branch_edges) == 2:
        otherwise_nodes = _branch_path(branch_edges[1], nodes_by_id, outgoing, seen)
    else:
        otherwise_nodes = [_branch_edge_to_display(edge, nodes_by_id, outgoing, seen) for edge in branch_edges[1:]]

    payload = {
        "kind": "branch",
        "id": _string(node.get("id")),
        "condition": _display_title(node),
        "then": then_nodes,
        "otherwise": otherwise_nodes,
    }
    _copy_display_metadata(payload, node)
    return payload


def _branch_edge_to_display(
    edge: Mapping[str, Any],
    nodes_by_id: Mapping[str, Mapping[str, Any]],
    outgoing: Mapping[str, Sequence[Mapping[str, Any]]],
    seen: Set[str],
) -> Dict[str, Any]:
    return {
        "kind": "branch",
        "id": "%s:display" % _string(edge.get("id")),
        "condition": _string(edge.get("label")) or "Otherwise",
        "then": _branch_path(edge, nodes_by_id, outgoing, seen),
        "otherwise": [],
    }


def _branch_path(
    edge: Mapping[str, Any],
    nodes_by_id: Mapping[str, Mapping[str, Any]],
    outgoing: Mapping[str, Sequence[Mapping[str, Any]]],
    seen: Set[str],
) -> List[Dict[str, Any]]:
    target = _string(edge.get("target"))
    if target not in nodes_by_id:
        return []
    return _walk_nodes(target, nodes_by_id, outgoing, set(), set(seen))


def _copy_display_metadata(payload: Dict[str, Any], node: Mapping[str, Any]) -> None:
    metadata = node.get("metadata") if isinstance(node.get("metadata"), Mapping) else {}
    if metadata.get("uncertain") is not None:
        payload["uncertain"] = bool(metadata.get("uncertain"))
    refs = _strings(node.get("evidence_refs"))
    tech = metadata.get("tech") if isinstance(metadata.get("tech"), Mapping) else {}
    if isinstance(tech, Mapping):
        refs.extend(_strings(tech.get("refs")))
    refs = _dedupe(refs)
    if refs:
        tech_payload = {"refs": refs}
        node_id = _string(tech.get("nodeId") if isinstance(tech, Mapping) else None)
        if node_id:
            tech_payload["nodeId"] = node_id
        payload["tech"] = tech_payload


def _display_title(node: Mapping[str, Any]) -> str:
    return _string(node.get("title") or node.get("detail")) or "Mapped step"


def _first_start(nodes: Sequence[Mapping[str, Any]], incoming: Mapping[str, int]) -> str:
    for node in nodes:
        node_id = _string(node.get("id"))
        if node_id and not incoming.get(node_id):
            return node_id
    return _string(nodes[0].get("id"))


def _first_edge(edges: Optional[Sequence[Mapping[str, Any]]], kinds: Iterable[str]) -> Optional[Mapping[str, Any]]:
    if not edges:
        return None
    wanted = set(kinds)
    for edge in edges:
        if edge.get("kind") in wanted:
            return edge
    return None


def _edge_sort_key(edge: Mapping[str, Any]) -> Tuple[int, str, str]:
    if edge.get("is_default"):
        priority = 20
    elif edge.get("kind") == "normal":
        priority = 0
    else:
        priority = 10
    return (priority, _string(edge.get("label")), _string(edge.get("target")))


def _clean(payload: Mapping[str, Any]) -> Dict[str, Any]:
    return {key: value for key, value in payload.items() if value not in (None, "", [], {})}


def _dict(value: Any) -> Dict[str, Any]:
    return copy.deepcopy(dict(value)) if isinstance(value, Mapping) else {}


def _list(value: Any) -> List[Any]:
    return list(value) if isinstance(value, list) else []


def _string(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _strings(value: Any) -> List[str]:
    if not isinstance(value, list) and not isinstance(value, tuple):
        return []
    return [_string(item) for item in value if _string(item)]


def _dedupe(values: Iterable[str]) -> List[str]:
    seen = set()
    out = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out
