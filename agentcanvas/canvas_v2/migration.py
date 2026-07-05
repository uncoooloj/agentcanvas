"""Migration helpers for legacy AgentCanvas display canvases.

This module is intentionally stdlib-only and side-effect free. File reads,
history writes, and server integration happen in later Phase 0 work; the
helpers here only classify and transform JSON-like dictionaries.
"""

from __future__ import annotations

from datetime import datetime
import copy
import re
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


CANVAS_V1_SCHEMA = "agentcanvas.canvas.v1"
BEHAVIOR_WRAPPER_SCHEMA = "agentcanvas.behavior_canvas_response.v1"
DISPLAY_CANVAS_SCHEMA = "agentcanvas.behavior_canvas.v1"
CANVAS_V2_SCHEMA = "agentcanvas.canvas.v2"

_UNWRAP_KEYS = ("canvas", "canvas_model", "canvasModel", "model")
_ID_RE = re.compile(r"[^a-zA-Z0-9_.:/-]+")


def detect_v1_canvas(payload: Any) -> bool:
    """Return True when *payload* is one of the v1 canvas shapes in the wild."""

    unwrapped, _wrapper = _unwrap_v1_payload(payload)
    return _looks_like_v1_canvas(unwrapped)


def migrate_canvas_v1_to_v2(
    payload: Mapping[str, Any],
    authored_by: str = "migration",
    updated_at: Optional[str] = None,
) -> Dict[str, Any]:
    """Convert a v1 canvas payload into an ``agentcanvas.canvas.v2`` document."""

    source, wrapper_metadata = _unwrap_v1_payload(payload)
    if not _looks_like_v1_canvas(source):
        raise ValueError("payload is not a recognized AgentCanvas v1 canvas")

    source = _dict(source)
    metadata = _top_level_metadata(source, wrapper_metadata)
    flows = []
    for index, journey in enumerate(_list(source.get("journeys"))):
        if not isinstance(journey, Mapping):
            continue
        flows.append(_migrate_journey(journey, index))

    return {
        "schema": CANVAS_V2_SCHEMA,
        "revision": 1,
        "authored_by": authored_by,
        "updated_at": updated_at or _utc_now(),
        "evidence": {},
        "app": {
            "name": _app_name(source),
            "summary": _string(source.get("summary") or source.get("description")),
            "is_demo": bool(source.get("isDemo") or source.get("is_demo")),
        },
        "flows": flows,
        "metadata": metadata,
    }


def _migrate_journey(journey: Mapping[str, Any], index: int) -> Dict[str, Any]:
    title = _string(journey.get("title")) or "Workspace flow"
    flow_id = _string(journey.get("id")) or "flow:%s" % _slug(title, "flow")
    flow_slug = _slug(flow_id, "flow")
    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []
    used_ids = set()
    context = {
        "flow_id": flow_id,
        "flow_slug": flow_slug,
        "nodes": nodes,
        "edges": edges,
        "used_ids": used_ids,
    }

    if isinstance(journey.get("steps"), list):
        first_id, _leaves = _append_typed_steps(_list(journey.get("steps")), context)
    else:
        first_id, _leaves = _append_display_nodes(_list(journey.get("nodes")), context)

    metadata = _metadata_from_extra(
        journey,
        {
            "id",
            "title",
            "summary",
            "entry",
            "steps",
            "nodes",
            "entry_refs",
            "provenance",
            "confidence",
            "metadata",
            "lastEditedAt",
        },
    )
    if isinstance(journey.get("metadata"), Mapping):
        metadata.update(copy.deepcopy(_dict(journey.get("metadata"))))
    if journey.get("lastEditedAt") is not None:
        metadata.setdefault("lastEditedAt", copy.deepcopy(journey.get("lastEditedAt")))

    entry_refs = _strings(journey.get("entry_refs"))
    evidence_refs = _strings(journey.get("refs")) + entry_refs

    return _clean(
        {
            "id": flow_id,
            "title": title,
            "summary": _string(journey.get("summary")),
            "altitude": "flow",
            "entry_node": first_id,
            "nodes": nodes,
            "edges": edges,
            "lanes": [],
            "tags": [],
            "evidence_refs": _dedupe(evidence_refs),
            "confidence": _confidence(journey.get("confidence")),
            "metadata": metadata,
        }
    )


def _append_display_nodes(
    items: Sequence[Any],
    context: Mapping[str, Any],
) -> Tuple[Optional[str], List[str]]:
    return _append_sequence(items, context, _migrate_display_node)


def _append_typed_steps(
    items: Sequence[Any],
    context: Mapping[str, Any],
) -> Tuple[Optional[str], List[str]]:
    first_id = None
    previous_leaves: List[str] = []
    index = 0

    while index < len(items):
        item = items[index]
        if not isinstance(item, Mapping):
            index += 1
            continue
        kind = _canvas_step_kind(item.get("kind"))
        if kind == "If":
            chain = [item]
            index += 1
            while index < len(items) and isinstance(items[index], Mapping):
                next_kind = _canvas_step_kind(items[index].get("kind"))
                if next_kind not in {"ElseIf", "Else"}:
                    break
                chain.append(items[index])
                index += 1
                if next_kind == "Else":
                    break
            item_first, item_leaves = _migrate_typed_decision_chain(chain, context)
        elif kind in {"ElseIf", "Else"}:
            index += 1
            continue
        else:
            item_first, item_leaves = _migrate_typed_step(item, context)
            index += 1

        if not item_first:
            continue
        if first_id is None:
            first_id = item_first
        for previous in previous_leaves:
            _add_edge(context, previous, item_first, "normal", None)
        previous_leaves = item_leaves or [item_first]

    return first_id, previous_leaves


def _append_sequence(
    items: Sequence[Any],
    context: Mapping[str, Any],
    migrate_one: Any,
) -> Tuple[Optional[str], List[str]]:
    first_id = None
    previous_leaves: List[str] = []

    for item in items:
        if not isinstance(item, Mapping):
            continue
        item_first, item_leaves = migrate_one(item, context)
        if not item_first:
            continue
        if first_id is None:
            first_id = item_first
        for previous in previous_leaves:
            _add_edge(context, previous, item_first, "normal", None)
        previous_leaves = item_leaves or [item_first]

    return first_id, previous_leaves


def _migrate_display_node(
    node: Mapping[str, Any],
    context: Mapping[str, Any],
) -> Tuple[Optional[str], List[str]]:
    if node.get("kind") == "branch":
        return _migrate_display_branch(node, context)

    role = _string(node.get("role")).lower()
    kind = "When" if role == "when" else "Do"
    return _add_node_from_legacy(context, node, kind, _string(node.get("text") or node.get("label")), child_keys=set())


def _migrate_display_branch(
    node: Mapping[str, Any],
    context: Mapping[str, Any],
) -> Tuple[Optional[str], List[str]]:
    condition = _string(node.get("condition") or node.get("text") or node.get("label")) or "mapped condition"
    decision_id, _leaves = _add_node_from_legacy(
        context,
        node,
        "Decision",
        condition,
        child_keys={"then", "otherwise"},
    )
    if not decision_id:
        return None, []

    branch_specs = [
        (condition or "Yes", _list(node.get("then")), False),
        ("Otherwise", _list(node.get("otherwise")), True),
    ]
    leaves: List[str] = []
    for label, children, is_default in branch_specs:
        child_first, child_leaves = _append_display_nodes(children, context)
        if not child_first:
            child_first, child_leaves = _synthetic_end(context, decision_id, label)
        _add_edge(context, decision_id, child_first, "branch", label, is_default=is_default)
        leaves.extend(child_leaves or [child_first])
    return decision_id, _dedupe(leaves)


def _migrate_typed_step(
    step: Mapping[str, Any],
    context: Mapping[str, Any],
) -> Tuple[Optional[str], List[str]]:
    kind = _canvas_step_kind(step.get("kind"))
    if kind in {"If", "ElseIf", "Else"}:
        return _migrate_typed_decision(step, context)
    return _add_node_from_legacy(
        context,
        step,
        kind if kind in {"When", "Do"} else "Do",
        _string(step.get("text") or step.get("label")),
        child_keys={"steps"},
    )


def _migrate_typed_decision(
    step: Mapping[str, Any],
    context: Mapping[str, Any],
) -> Tuple[Optional[str], List[str]]:
    return _migrate_typed_decision_chain([step], context)


def _migrate_typed_decision_chain(
    chain: Sequence[Mapping[str, Any]],
    context: Mapping[str, Any],
) -> Tuple[Optional[str], List[str]]:
    if not chain:
        return None, []
    head = chain[0]
    condition = _condition_text(head)
    decision_id, _leaves = _add_node_from_legacy(context, head, "Decision", condition, child_keys={"steps"})
    if not decision_id:
        return None, []

    leaves: List[str] = []
    for step in chain:
        kind = _canvas_step_kind(step.get("kind"))
        label = "Else" if kind == "Else" else _condition_text(step)
        child_first, child_leaves = _append_typed_steps(_list(step.get("steps")), context)
        if not child_first:
            child_first, child_leaves = _synthetic_end(context, decision_id, label)
        _add_edge(
            context,
            decision_id,
            child_first,
            "branch",
            label,
            is_default=kind == "Else",
            metadata=_legacy_branch_metadata(step),
        )
        leaves.extend(child_leaves or [child_first])
    return decision_id, _dedupe(leaves)


def _add_node_from_legacy(
    context: Mapping[str, Any],
    legacy: Mapping[str, Any],
    kind: str,
    title: str,
    child_keys: Iterable[str],
) -> Tuple[Optional[str], List[str]]:
    title = title or _string(legacy.get("condition")) or kind
    node_id = _string(legacy.get("id")) or _new_node_id(context, title)
    node_id = _unique(node_id, context["used_ids"])

    refs = []
    refs.extend(_strings(legacy.get("refs")))
    tech = legacy.get("tech") if isinstance(legacy.get("tech"), Mapping) else {}
    refs.extend(_strings(tech.get("refs") if isinstance(tech, Mapping) else None))

    metadata = _metadata_from_extra(
        legacy,
        {
            "id",
            "kind",
            "role",
            "text",
            "label",
            "condition",
            "steps",
            "then",
            "otherwise",
            "refs",
            "provenance",
            "confidence",
            "metadata",
            "detail",
            "tech",
        }.union(set(child_keys)),
    )
    if isinstance(legacy.get("metadata"), Mapping):
        metadata.update(copy.deepcopy(_dict(legacy.get("metadata"))))
    if legacy.get("uncertain") is not None:
        metadata["uncertain"] = bool(legacy.get("uncertain"))
    if isinstance(tech, Mapping) and tech:
        metadata["tech"] = copy.deepcopy(_dict(tech))
    if legacy.get("condition") is not None and kind == "Decision":
        metadata.setdefault("condition", copy.deepcopy(legacy.get("condition")))
    if legacy.get("provenance") is not None:
        metadata.setdefault("provenance", copy.deepcopy(legacy.get("provenance")))

    node = _clean(
        {
            "id": node_id,
            "kind": kind,
            "title": title,
            "detail": _string(legacy.get("detail")),
            "evidence_refs": _dedupe(refs),
            "confidence": _confidence(legacy.get("confidence")),
            "status": "inferred" if legacy.get("uncertain") else "verified",
            "flow_ref": None,
            "metadata": metadata,
        }
    )
    context["nodes"].append(node)
    return node_id, [node_id]


def _synthetic_end(
    context: Mapping[str, Any],
    source_id: str,
    label: str,
) -> Tuple[str, List[str]]:
    title = label or "End"
    node_id = _unique(
        "n:%s:%s-end" % (context["flow_slug"], _slug("%s-%s" % (source_id, title), "branch")),
        context["used_ids"],
    )
    context["nodes"].append(
        {
            "id": node_id,
            "kind": "End",
            "title": title,
            "status": "inferred",
            "metadata": {"synthetic": True},
        }
    )
    return node_id, [node_id]


def _add_edge(
    context: Mapping[str, Any],
    source: str,
    target: str,
    kind: str,
    label: Optional[str],
    is_default: bool = False,
    metadata: Optional[Mapping[str, Any]] = None,
) -> None:
    edge_id = _unique(
        "e:%s:%s:%s" % (context["flow_slug"], _slug(source, "source"), _slug(label or target, "target")),
        context["used_ids"],
    )
    context["edges"].append(
        _clean(
            {
                "id": edge_id,
                "source": source,
                "target": target,
                "kind": kind,
                "label": label,
                "is_default": bool(is_default) if kind == "branch" else None,
                "evidence_refs": [],
                "metadata": copy.deepcopy(_dict(metadata)),
            }
        )
    )


def _legacy_branch_metadata(step: Mapping[str, Any]) -> Dict[str, Any]:
    legacy = _metadata_from_extra(step, {"steps"})
    return {"legacy_step": legacy} if legacy else {}


def _unwrap_v1_payload(payload: Any) -> Tuple[Mapping[str, Any], Dict[str, Any]]:
    if not isinstance(payload, Mapping):
        return {}, {}

    root = _dict(payload)
    if root.get("schema") == BEHAVIOR_WRAPPER_SCHEMA and isinstance(root.get("canvas"), Mapping):
        wrapper = _metadata_from_extra(root, {"canvas"})
        if isinstance(root.get("mapping"), Mapping):
            wrapper["mapping"] = copy.deepcopy(_dict(root.get("mapping")))
        return _dict(root.get("canvas")), {"legacy_wrapper": wrapper}

    if _looks_like_v1_canvas(root):
        return root, {}

    for key in _UNWRAP_KEYS:
        value = root.get(key)
        if isinstance(value, Mapping) and _looks_like_v1_canvas(value):
            wrapper = _metadata_from_extra(root, {key})
            wrapper["unwrapped_from"] = key
            return _dict(value), {"legacy_wrapper": wrapper}

    return root, {}


def _looks_like_v1_canvas(payload: Mapping[str, Any]) -> bool:
    if not isinstance(payload, Mapping):
        return False
    journeys = payload.get("journeys")
    if payload.get("schema") == CANVAS_V1_SCHEMA and isinstance(journeys, list):
        return any(isinstance(item, Mapping) and isinstance(item.get("steps"), list) for item in journeys)
    if payload.get("schema") == DISPLAY_CANVAS_SCHEMA and isinstance(journeys, list):
        return True
    if isinstance(journeys, list):
        return any(
            isinstance(item, Mapping)
            and (isinstance(item.get("nodes"), list) or isinstance(item.get("steps"), list))
            for item in journeys
        )
    return False


def _top_level_metadata(source: Mapping[str, Any], wrapper_metadata: Mapping[str, Any]) -> Dict[str, Any]:
    metadata = {}
    if isinstance(source.get("metadata"), Mapping):
        metadata.update(copy.deepcopy(_dict(source.get("metadata"))))
    extras = _metadata_from_extra(
        source,
        {
            "schema",
            "version",
            "appName",
            "app_name",
            "name",
            "title",
            "summary",
            "description",
            "isDemo",
            "is_demo",
            "journeys",
            "metadata",
            "thin",
        },
    )
    if extras:
        metadata["legacy_canvas"] = extras
    metadata.update(copy.deepcopy(_dict(wrapper_metadata)))
    return metadata


def _metadata_from_extra(payload: Mapping[str, Any], known_keys: Iterable[str]) -> Dict[str, Any]:
    known = set(known_keys)
    return {str(key): copy.deepcopy(value) for key, value in payload.items() if key not in known}


def _app_name(source: Mapping[str, Any]) -> str:
    metadata = source.get("metadata") if isinstance(source.get("metadata"), Mapping) else {}
    return (
        _string(source.get("appName"))
        or _string(source.get("app_name"))
        or _string(source.get("name"))
        or _string(source.get("title"))
        or _string(metadata.get("title"))
        or "Workspace"
    )


def _confidence(value: Any) -> Dict[str, str]:
    if isinstance(value, Mapping):
        score = value.get("score")
        reason = _string(value.get("reason") or value.get("rationale"))
    else:
        score = value
        reason = ""
    try:
        numeric = float(score)
    except (TypeError, ValueError):
        numeric = 1.0
    if numeric >= 0.8:
        level = "high"
    elif numeric >= 0.5:
        level = "medium"
    else:
        level = "low"
    return _clean({"level": level, "reason": reason})


def _canvas_step_kind(value: Any) -> str:
    normalized = _string(value or "Do").replace("-", "_").lower()
    aliases = {
        "when": "When",
        "do": "Do",
        "if": "If",
        "else_if": "ElseIf",
        "elseif": "ElseIf",
        "elif": "ElseIf",
        "else": "Else",
    }
    return aliases.get(normalized, "Do")


def _condition_text(step: Mapping[str, Any]) -> str:
    if _canvas_step_kind(step.get("kind")) == "Else":
        return "Else"
    return _string(step.get("condition") or step.get("text") or step.get("label")) or "mapped condition"


def _new_node_id(context: Mapping[str, Any], title: str) -> str:
    return "n:%s:%s" % (context["flow_slug"], _slug(title, "step"))


def _slug(value: Any, fallback: str) -> str:
    cleaned = _ID_RE.sub("-", _string(value).strip()).strip("-").lower()
    return cleaned or fallback


def _unique(value: str, used: set) -> str:
    candidate = value
    suffix = 2
    while candidate in used:
        candidate = "%s-%s" % (value, suffix)
        suffix += 1
    used.add(candidate)
    return candidate


def _clean(payload: Mapping[str, Any]) -> Dict[str, Any]:
    return {key: value for key, value in payload.items() if value not in (None, "", [], {})}


def _dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


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


def _utc_now() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
