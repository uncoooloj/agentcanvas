"""Deterministic fact selection metadata shared by indexers and projections."""

from __future__ import annotations

from collections import Counter
from math import ceil
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple


FACT_SELECTION_STRATEGY = "priority-v1"
OMITTED_FACT_IDS_PREVIEW = 100


def prioritize_facts(
    facts: Iterable[Dict[str, Any]],
    max_facts: int,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Select a deterministic, high-signal prefix and describe what was omitted.

    Ranking is intentionally local: it recognizes entrypoints and explicit
    workflow links already present on each fact, but does not traverse the
    repository graph to infer new relationships.
    """

    candidates = [fact for fact in facts if isinstance(fact, dict)]
    limit = max(0, int(max_facts))
    if len(candidates) <= limit:
        return list(candidates), fact_selection_metadata(candidates, candidates, limit)

    ranked = sorted(candidates, key=_fact_sort_key)
    selected = ranked[:limit]
    selected_ids = {str(fact.get("id")) for fact in selected}
    endpoint_ids = {
        endpoint
        for fact in selected
        if _is_workflow_link(fact)
        for endpoint in _link_endpoint_ids(fact)
    }
    if endpoint_ids:
        endpoint_facts = [
            fact
            for fact in ranked
            if not selected_ids.intersection({str(fact.get("id"))})
            and _fact_matches_endpoint(fact, endpoint_ids)
        ]
        replaceable = [
            index
            for index, fact in enumerate(selected)
            if not _is_entrypoint(fact) and not _is_workflow_link(fact)
        ]
        for fact, index in zip(endpoint_facts, reversed(replaceable)):
            selected[index] = fact
        selected = sorted(selected, key=_fact_sort_key)
    return selected, fact_selection_metadata(candidates, selected, limit)


def fact_selection_metadata(
    facts: Sequence[Dict[str, Any]],
    selected: Sequence[Dict[str, Any]],
    max_facts: int,
) -> Dict[str, Any]:
    """Return bounded completeness and chunk metadata for a fact selection."""

    selected_ids = {str(fact.get("id")) for fact in selected}
    omitted = [fact for fact in facts if str(fact.get("id")) not in selected_ids]
    total = len(facts)
    chunk_count = ceil(total / max_facts) if max_facts else (1 if total else 0)
    omitted_ids = sorted({str(fact.get("id")) for fact in omitted if fact.get("id")})

    return {
        "strategy": FACT_SELECTION_STRATEGY,
        "max_facts": max_facts,
        "chunk_index": 0,
        "chunk_count": chunk_count,
        "total_facts": total,
        "included_facts": len(selected),
        "omitted_facts": len(omitted),
        "complete": not omitted,
        "included_by_kind": _counts_by_kind(selected),
        "omitted_by_kind": _counts_by_kind(omitted),
        "omitted_fact_ids": omitted_ids[:OMITTED_FACT_IDS_PREVIEW],
        "omitted_fact_ids_truncated": len(omitted_ids) > OMITTED_FACT_IDS_PREVIEW,
    }


def merge_fact_selection_metadata(
    previous: Mapping[str, Any] | None,
    current: Mapping[str, Any],
) -> Dict[str, Any]:
    """Carry forward omission metadata when an already-bounded bundle is re-chunked."""

    if not isinstance(previous, Mapping) or not previous:
        return dict(current)

    total = max(int(previous.get("total_facts", 0)), int(current.get("total_facts", 0)))
    included = int(current.get("included_facts", 0))
    omitted = max(0, total - included)
    omitted_by_kind = Counter()
    for metadata in (previous, current):
        omitted_by_kind.update(metadata.get("omitted_by_kind") or {})
    omitted_ids = []
    for metadata in (previous, current):
        for fact_id in metadata.get("omitted_fact_ids") or []:
            if fact_id not in omitted_ids:
                omitted_ids.append(fact_id)
    max_facts = int(current.get("max_facts", 0))
    return {
        "strategy": FACT_SELECTION_STRATEGY,
        "max_facts": max_facts,
        "chunk_index": 0,
        "chunk_count": ceil(total / max_facts) if max_facts else (1 if total else 0),
        "total_facts": total,
        "included_facts": included,
        "omitted_facts": omitted,
        "complete": bool(previous.get("complete", True)) and bool(current.get("complete", True)),
        "included_by_kind": current.get("included_by_kind") or {},
        "omitted_by_kind": dict(sorted(omitted_by_kind.items())),
        "omitted_fact_ids": omitted_ids[:OMITTED_FACT_IDS_PREVIEW],
        "omitted_fact_ids_truncated": len(omitted_ids) > OMITTED_FACT_IDS_PREVIEW
        or bool(previous.get("omitted_fact_ids_truncated"))
        or bool(current.get("omitted_fact_ids_truncated")),
    }


def _fact_sort_key(fact: Mapping[str, Any]) -> Tuple[int, str, str, str]:
    return (
        fact_priority(fact),
        str(fact.get("id") or ""),
        str(fact.get("subject") or fact.get("path") or fact.get("file") or ""),
        str(fact.get("summary") or ""),
    )


def fact_priority(fact: Mapping[str, Any]) -> int:
    """Return a stable tier where lower values are more useful to an LLM."""

    if _is_fixture(fact):
        return 50
    if _is_entrypoint(fact):
        return 0
    if _is_workflow_link(fact):
        return 10
    if _has_evidence(fact) or _is_error(fact):
        return 20
    if _is_behavior(fact):
        return 30
    return 40


def _is_entrypoint(fact: Mapping[str, Any]) -> bool:
    kind = _kind(fact)
    attrs = _attributes(fact)
    if kind in {"entrypoint", "route", "app_surface", "canvas_route"} or kind.endswith("_route"):
        return True
    if str(attrs.get("fact_type") or "").lower() == "route":
        return True
    if str(attrs.get("type") or "").lower() in {"route", "entrypoint"}:
        return True
    return any(
        bool(attrs.get(key))
        for key in ("entrypoint", "is_entrypoint", "is_entry_point")
    )


def _is_workflow_link(fact: Mapping[str, Any]) -> bool:
    kind = _kind(fact)
    attrs = _attributes(fact)
    if kind in {"edge", "canvas_edge", "link", "workflow_link"}:
        return True
    if str(attrs.get("fact_type") or "").lower() == "import" and attrs.get("resolved_path"):
        return True
    relation = str(attrs.get("kind") or "").lower()
    if relation in {"imports", "calls", "serves", "depends_on", "handoff", "links"}:
        return True
    return bool(attrs.get("resolved_path")) and kind.endswith("_import")


def _link_endpoint_ids(fact: Mapping[str, Any]) -> set[str]:
    attrs = _attributes(fact)
    edge = attrs.get("edge") if isinstance(attrs.get("edge"), Mapping) else attrs
    return {
        str(edge.get(key))
        for key in ("source", "target", "source_id", "target_id")
        if edge.get(key)
    }


def _fact_matches_endpoint(fact: Mapping[str, Any], endpoint_ids: set[str]) -> bool:
    fact_id = str(fact.get("id") or "")
    aliases = {fact_id}
    if fact_id.startswith("node:"):
        aliases.add(fact_id[len("node:"):])
    return bool(aliases.intersection(endpoint_ids))


def _has_evidence(fact: Mapping[str, Any]) -> bool:
    if fact.get("evidence") or fact.get("source_ref") or fact.get("provenance"):
        return True
    attrs = _attributes(fact)
    return bool(attrs.get("path") or attrs.get("file") or attrs.get("source_ref"))


def _is_error(fact: Mapping[str, Any]) -> bool:
    return _kind(fact).endswith("error") or str(fact.get("type") or "").endswith("error")


def _is_behavior(fact: Mapping[str, Any]) -> bool:
    kind = _kind(fact)
    return kind in {
        "call",
        "branch",
        "event",
        "export",
        "symbol",
        "language_call",
        "language_branch",
        "language_export",
        "language_symbol",
    }


def _is_fixture(fact: Mapping[str, Any]) -> bool:
    attrs = _attributes(fact)
    role = str(fact.get("projection_role") or attrs.get("projection_role") or "").lower()
    if role in {"fixture", "test_fixture"} or attrs.get("is_fixture"):
        return True
    paths = [fact.get("path"), fact.get("file"), attrs.get("path"), attrs.get("file")]
    return any("tests/" in str(path).lower() or "fixtures/" in str(path).lower() for path in paths if path)


def _kind(fact: Mapping[str, Any]) -> str:
    return str(fact.get("kind") or fact.get("type") or "fact").lower().replace("-", "_")


def _attributes(fact: Mapping[str, Any]) -> Mapping[str, Any]:
    value = fact.get("attributes")
    return value if isinstance(value, Mapping) else fact


def _counts_by_kind(facts: Sequence[Mapping[str, Any]]) -> Dict[str, int]:
    return dict(sorted(Counter(_kind(fact) for fact in facts).items()))
