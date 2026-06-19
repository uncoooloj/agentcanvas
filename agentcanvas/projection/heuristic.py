"""Deterministic offline fallback from facts to canvas query operations."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List

from .contracts import CANVAS_QUERY_SCHEMA, normalize_fact_bundle


def heuristic_project(
    source: Dict[str, Any],
    repo_summary: Dict[str, Any] | None = None,
    *,
    max_facts: int = 200,
) -> Dict[str, Any]:
    """Project facts into canvas query JSON without calling an LLM.

    This fallback intentionally avoids inference. It only emits nodes and edges
    that are already present as reliable facts, preserving the evidence trail
    through fact_ids. LLM-assisted projection remains the primary product path.
    """

    fact_bundle = normalize_fact_bundle(source, repo_summary, max_facts=max_facts)
    operations: List[Dict[str, Any]] = []
    warnings: List[str] = []

    for fact in fact_bundle.get("facts") or []:
        attributes = fact.get("attributes") if isinstance(fact, dict) else None
        if not isinstance(attributes, dict):
            continue

        if fact.get("kind") == "canvas_node" and isinstance(attributes.get("node"), dict):
            node = deepcopy(attributes["node"])
            operations.append(
                {
                    "op": "upsert_node",
                    "node": node,
                    "fact_ids": [fact["id"]],
                    "confidence": _confidence(fact),
                    "rationale": "Preserved node from source facts.",
                }
            )
            continue

        if fact.get("kind") == "canvas_edge" and isinstance(attributes.get("edge"), dict):
            edge = deepcopy(attributes["edge"])
            operations.append(
                {
                    "op": "upsert_edge",
                    "edge": edge,
                    "fact_ids": [fact["id"]],
                    "confidence": _confidence(fact),
                    "rationale": "Preserved edge from source facts.",
                }
            )

    if not operations:
        warnings.append(
            "No canvas_node or canvas_edge facts were available for deterministic projection."
        )

    return {
        "schema": CANVAS_QUERY_SCHEMA,
        "version": "0.1.0",
        "mode": "heuristic",
        "intent": "Deterministically project reliable facts into AgentCanvas.",
        "operations": operations,
        "warnings": warnings,
    }


def _confidence(fact: Dict[str, Any]) -> float:
    value = fact.get("confidence", 1.0)
    if isinstance(value, (int, float)):
        return max(0.0, min(1.0, float(value)))
    return 1.0
