"""Pending-request reference normalization helpers.

Phase 0 keeps these helpers side-effect free by default. Callers can normalize
one pending record in memory, migrate pending JSON files in place, list open
references, or tombstone references that point at deleted canvas ids.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from agentcanvas.ir import STATE_DIR_NAME, atomic_write_json, now_utc, resolve_workspace


OPEN_PENDING_STATUSES = {"pending", "sent", "in_progress", "needs_input", "blocked"}

_FLOW_KEYS = {
    "flow",
    "flowId",
    "flow_id",
    "journey",
    "journeyId",
    "journey_id",
    "targetFlow",
    "targetFlowId",
    "target_flow_id",
    "targetJourney",
    "targetJourneyId",
    "target_journey_id",
}
_NODE_KEYS = {
    "node",
    "nodeId",
    "node_id",
    "step",
    "stepId",
    "step_id",
    "target",
    "targetNode",
    "targetNodeId",
    "target_node_id",
    "targetStep",
    "targetStepId",
    "target_step_id",
}
_FLOW_COLLECTION_KEYS = {"flows", "journeys"}
_NODE_COLLECTION_KEYS = {"nodes", "steps"}


def normalize_pending_record(record: Mapping[str, Any]) -> Dict[str, Any]:
    """Return *record* with normalized ``refs`` and ``orphaned_refs`` lists.

    Existing normalized refs are preserved and de-duplicated. Missing refs are
    inferred from common legacy fields inside ``change`` such as ``journeyId``,
    ``targetNodeId``, ``targetStep``, ``flowId``, and nested node/flow ids.
    """

    normalized = copy.deepcopy(dict(record))
    orphaned_refs = _dedupe_refs(_normalized_refs(normalized.get("orphaned_refs")))
    orphaned_keys = {
        (ref.get("kind"), ref.get("id"))
        for ref in orphaned_refs
        if isinstance(ref.get("kind"), str) and isinstance(ref.get("id"), str)
    }
    refs = _normalized_refs(normalized.get("refs"))
    refs.extend(_refs_from_change(normalized.get("change")))
    normalized["refs"] = [
        ref
        for ref in _dedupe_refs(refs)
        if (ref.get("kind"), ref.get("id")) not in orphaned_keys
    ]
    normalized["orphaned_refs"] = orphaned_refs
    return normalized


def migrate_pending_refs(workspace: str | Path, *, write: bool = True) -> List[Dict[str, Any]]:
    """Normalize every pending JSON file under *workspace*.

    When ``write`` is true, changed files are written atomically. The returned
    records include ``json_path`` for the file that was read.
    """

    pending_dir = _pending_dir(workspace)
    if not pending_dir.is_dir():
        return []

    migrated = []
    for json_path in sorted(pending_dir.glob("*.json")):
        record = _read_json_object(json_path)
        if record is None:
            continue
        normalized = normalize_pending_record(record)
        normalized["json_path"] = str(json_path)
        migrated.append(normalized)
        comparable = dict(normalized)
        comparable.pop("json_path", None)
        if write and comparable != record:
            atomic_write_json(json_path, comparable)
    return migrated


def list_open_referenced_ids(workspace: str | Path) -> Set[Tuple[str, str]]:
    """Return ``(kind, id)`` pairs referenced by open pending requests."""

    references = set()
    for record in migrate_pending_refs(workspace, write=False):
        if record.get("status", "pending") not in OPEN_PENDING_STATUSES:
            continue
        for ref in record.get("refs") or []:
            if not isinstance(ref, Mapping):
                continue
            kind = ref.get("kind")
            item_id = ref.get("id")
            if isinstance(kind, str) and isinstance(item_id, str):
                references.add((kind, item_id))
    return references


def tombstone_deleted_refs(
    workspace: str | Path,
    *,
    deleted_nodes: Iterable[str] = (),
    deleted_flows: Iterable[str] = (),
    timestamp: Optional[str] = None,
    write: bool = True,
) -> List[Dict[str, Any]]:
    """Move refs for deleted nodes/flows into ``orphaned_refs``.

    Only open pending requests are modified. Tombstoned refs are removed from
    ``refs`` and copied to ``orphaned_refs`` with ``orphaned_at``. When
    ``write`` is false, changed records are returned with ``json_path`` but not
    persisted; callers can include them in a larger transaction.
    """

    deleted = set()
    for item_id in deleted_nodes:
        if item_id:
            deleted.add(("node", str(item_id)))
    for item_id in deleted_flows:
        if item_id:
            deleted.add(("flow", str(item_id)))
    if not deleted:
        return migrate_pending_refs(workspace, write=False)

    pending_dir = _pending_dir(workspace)
    if not pending_dir.is_dir():
        return []

    orphaned_at = timestamp or now_utc()
    updated_records = []
    for json_path in sorted(pending_dir.glob("*.json")):
        record = _read_json_object(json_path)
        if record is None:
            continue
        normalized = normalize_pending_record(record)
        if normalized.get("status", "pending") not in OPEN_PENDING_STATUSES:
            normalized["json_path"] = str(json_path)
            updated_records.append(normalized)
            continue

        active_refs = []
        orphaned_refs = list(normalized.get("orphaned_refs") or [])
        changed = False
        for ref in normalized.get("refs") or []:
            key = (ref.get("kind"), ref.get("id")) if isinstance(ref, Mapping) else (None, None)
            if key in deleted:
                orphaned = dict(ref)
                orphaned["orphaned_at"] = orphaned_at
                orphaned_refs.append(orphaned)
                changed = True
            else:
                active_refs.append(ref)

        if changed and write:
            normalized["refs"] = _dedupe_refs(active_refs)
            normalized["orphaned_refs"] = _dedupe_refs(orphaned_refs)
            atomic_write_json(json_path, normalized)
        elif changed:
            normalized["refs"] = _dedupe_refs(active_refs)
            normalized["orphaned_refs"] = _dedupe_refs(orphaned_refs)
        normalized["json_path"] = str(json_path)
        updated_records.append(normalized)
    return updated_records


def _refs_from_change(change: Any) -> List[Dict[str, Any]]:
    refs = []
    if not isinstance(change, Mapping):
        return refs

    flow_id = _first_string_for_keys(change, _FLOW_KEYS)
    for key, value in _walk_mapping(change):
        if key in _FLOW_KEYS and isinstance(value, str) and value:
            refs.append(_ref("flow", value, source="change.%s" % key))
            flow_id = flow_id or value
        elif key in _FLOW_KEYS and isinstance(value, Mapping):
            item_id = _mapping_id(value)
            if item_id:
                refs.append(_ref("flow", item_id, source="change.%s.id" % key))
                flow_id = flow_id or item_id
        elif key in _FLOW_COLLECTION_KEYS and isinstance(value, list):
            for item_id in _mapping_ids(value):
                refs.append(_ref("flow", item_id, source="change.%s.id" % key))
                flow_id = flow_id or item_id
        elif key in _NODE_KEYS and isinstance(value, str) and value:
            refs.append(_ref("node", value, flow=flow_id, source="change.%s" % key))
        elif key in _NODE_KEYS and isinstance(value, Mapping):
            item_id = _mapping_id(value)
            if item_id:
                refs.append(_ref("node", item_id, flow=flow_id, source="change.%s.id" % key))
        elif key in _NODE_COLLECTION_KEYS and isinstance(value, list):
            for item_id in _mapping_ids(value):
                refs.append(_ref("node", item_id, flow=flow_id, source="change.%s.id" % key))
    return refs


def _normalized_refs(value: Any) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        return []
    refs = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        kind = item.get("kind")
        item_id = item.get("id")
        if not isinstance(kind, str) or not isinstance(item_id, str) or not item_id:
            continue
        ref = {"kind": kind, "id": item_id}
        flow = item.get("flow")
        if isinstance(flow, str) and flow:
            ref["flow"] = flow
        source = item.get("source")
        if isinstance(source, str) and source:
            ref["source"] = source
        orphaned_at = item.get("orphaned_at")
        if isinstance(orphaned_at, str) and orphaned_at:
            ref["orphaned_at"] = orphaned_at
        refs.append(ref)
    return refs


def _dedupe_refs(refs: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    deduped = []
    seen = set()
    for ref in refs:
        if not isinstance(ref, Mapping):
            continue
        kind = ref.get("kind")
        item_id = ref.get("id")
        if not isinstance(kind, str) or not isinstance(item_id, str) or not item_id:
            continue
        key = (
            kind,
            item_id,
            ref.get("flow") if isinstance(ref.get("flow"), str) else None,
            ref.get("orphaned_at") if isinstance(ref.get("orphaned_at"), str) else None,
        )
        if key in seen:
            continue
        seen.add(key)
        clean = {"kind": kind, "id": item_id}
        for optional_key in ("flow", "source", "orphaned_at"):
            optional_value = ref.get(optional_key)
            if isinstance(optional_value, str) and optional_value:
                clean[optional_key] = optional_value
        deduped.append(clean)
    return deduped


def _ref(kind: str, item_id: str, *, flow: Optional[str] = None, source: str) -> Dict[str, Any]:
    ref = {"kind": kind, "id": item_id, "source": source}
    if flow:
        ref["flow"] = flow
    return ref


def _first_string_for_keys(value: Mapping[str, Any], keys: Set[str]) -> Optional[str]:
    for key, item in _walk_mapping(value):
        if key in keys and isinstance(item, str) and item:
            return item
        if key in keys and isinstance(item, Mapping):
            item_id = _mapping_id(item)
            if item_id:
                return item_id
    return None


def _mapping_ids(values: Iterable[Any]) -> Iterable[str]:
    for value in values:
        item_id = _mapping_id(value)
        if item_id:
            yield item_id


def _mapping_id(value: Any) -> Optional[str]:
    if not isinstance(value, Mapping):
        return None
    item_id = value.get("id")
    return item_id if isinstance(item_id, str) and item_id else None


def _walk_mapping(value: Any) -> Iterable[Tuple[str, Any]]:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if isinstance(key, str):
                yield key, item
            if isinstance(item, (Mapping, list)):
                for nested in _walk_mapping(item):
                    yield nested
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, (Mapping, list)):
                for nested in _walk_mapping(item):
                    yield nested


def _read_json_object(path: Path) -> Optional[Dict[str, Any]]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def _pending_dir(workspace: str | Path) -> Path:
    return resolve_workspace(workspace) / STATE_DIR_NAME / "pending"
