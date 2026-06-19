"""Projection contracts for turning reliable facts into canvas operations."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import PurePosixPath
from typing import Any, Dict, Iterable, List, Optional

from agentcanvas.ir import SCHEMA as WORKFLOW_IR_SCHEMA

SOURCE_FACTS_SCHEMA = "agentcanvas.source_facts.v1"
CANVAS_QUERY_SCHEMA = "agentcanvas.canvas_query.v1"
PROJECTION_CONTRACT_SCHEMA = "agentcanvas.projection_contract.v1"


SOURCE_FACTS_JSON_SCHEMA: Dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://agentcanvas.local/schemas/source-facts-v1.json",
    "title": "AgentCanvas Source Facts",
    "type": "object",
    "additionalProperties": False,
    "required": ["schema", "version", "repo", "facts"],
    "properties": {
        "schema": {"const": SOURCE_FACTS_SCHEMA},
        "version": {"type": "string"},
        "repo": {"type": "object"},
        "facts": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": True,
                "required": ["id", "kind", "subject", "summary", "attributes"],
                "properties": {
                    "id": {"type": "string"},
                    "kind": {"type": "string"},
                    "subject": {"type": "string"},
                    "summary": {"type": "string"},
                    "attributes": {"type": "object"},
                    "evidence": {
                        "type": "array",
                        "items": {"type": "object"},
                    },
                    "confidence": {
                        "type": "number",
                        "minimum": 0,
                        "maximum": 1,
                    },
                },
            },
        },
        "warnings": {"type": "array", "items": {"type": "string"}},
    },
}


CANVAS_QUERY_JSON_SCHEMA: Dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://agentcanvas.local/schemas/canvas-query-v1.json",
    "title": "AgentCanvas Canvas Query",
    "type": "object",
    "additionalProperties": False,
    "required": ["schema", "version", "mode", "operations"],
    "properties": {
        "schema": {"const": CANVAS_QUERY_SCHEMA},
        "version": {"type": "string"},
        "mode": {"enum": ["heuristic", "llm-assisted"]},
        "intent": {
            "type": "string",
            "description": "Short human-readable projection goal.",
        },
        "operations": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["op"],
                "properties": {
                    "op": {
                        "enum": [
                            "upsert_node",
                            "upsert_edge",
                            "delete_node",
                            "delete_edge",
                            "annotate",
                        ]
                    },
                    "node": {"$ref": "#/$defs/node"},
                    "edge": {"$ref": "#/$defs/edge"},
                    "target": {"type": "string"},
                    "annotation": {"type": "object"},
                    "fact_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "confidence": {
                        "type": "number",
                        "minimum": 0,
                        "maximum": 1,
                    },
                    "rationale": {"type": "string"},
                },
            },
        },
        "warnings": {"type": "array", "items": {"type": "string"}},
    },
    "$defs": {
        "node": {
            "type": "object",
            "additionalProperties": True,
            "required": ["id", "type", "label"],
            "properties": {
                "id": {"type": "string"},
                "type": {"type": "string"},
                "label": {"type": "string"},
                "path": {"type": "string"},
                "data": {"type": "object"},
            },
        },
        "edge": {
            "type": "object",
            "additionalProperties": True,
            "required": ["source", "target", "kind"],
            "properties": {
                "id": {"type": "string"},
                "source": {"type": "string"},
                "target": {"type": "string"},
                "kind": {"type": "string"},
                "label": {"type": "string"},
                "data": {"type": "object"},
            },
        },
    },
}


PROJECTION_CONTRACT_JSON_SCHEMA: Dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://agentcanvas.local/schemas/projection-contract-v1.json",
    "title": "AgentCanvas Projection Contract",
    "type": "object",
    "additionalProperties": False,
    "required": [
        "schema",
        "version",
        "primary_mode",
        "fallback_mode",
        "language_module_role",
        "source_facts",
        "response_schema",
        "instructions",
    ],
    "properties": {
        "schema": {"const": PROJECTION_CONTRACT_SCHEMA},
        "version": {"type": "string"},
        "primary_mode": {"const": "llm-assisted"},
        "fallback_mode": {"const": "heuristic"},
        "language_module_role": {
            "type": "object",
            "required": ["purpose", "description"],
            "properties": {
                "purpose": {"const": "grounding_chunking_provenance"},
                "description": {"type": "string"},
            },
        },
        "source_facts": SOURCE_FACTS_JSON_SCHEMA,
        "response_schema": {"type": "object"},
        "instructions": {"type": "array", "items": {"type": "string"}},
    },
}


SYSTEM_PROMPT = """You project grounded repository facts into AgentCanvas canvas query JSON.

AgentCanvas is usually invoked by an LLM or coding agent. Treat LLM-assisted
repo understanding as the core projection path: translate grounded facts into
human-readable flow language that can be shown on the canvas. Language modules
are grounding, chunking, and provenance providers. They improve precision, but
they are not required to be perfect parsers before useful projection can happen.

Use only supplied source facts as evidence. Do not invent routes, files, tests,
services, or relationships that are not supported by fact_ids. If a useful
canvas relationship is uncertain, omit it or add a warning. Output only JSON
matching the response schema.

When the repo summary includes app_surfaces, treat those as app/workspace lanes
inside a human journey. For example, signup in a monorepo is usually one
business journey with mobile, web, and backend surfaces participating through
entrypoints and handoffs. Split into separate top-level journeys only when the
actor, outcome, or business rules truly differ."""


USER_PROMPT_TEMPLATE = """Project these grounded facts into AgentCanvas canvas query language.

Return JSON with schema "{canvas_query_schema}". Use mode "llm-assisted".
Every operation should cite fact_ids. Prefer stable node IDs from facts when
available. Use concise, human-readable labels that explain the repo flow. The
result will be validated before AgentCanvas accepts it.

Repository summary:
{repo_summary}

Source facts:
{source_facts}

Canvas query response schema:
{response_schema}
"""


def build_projection_contract(
    source: Dict[str, Any],
    repo_summary: Optional[Dict[str, Any]] = None,
    *,
    max_facts: int = 200,
) -> Dict[str, Any]:
    """Build the provider-neutral contract a caller can hand to an LLM."""

    fact_bundle = normalize_fact_bundle(source, repo_summary, max_facts=max_facts)
    return {
        "schema": PROJECTION_CONTRACT_SCHEMA,
        "version": "0.1.0",
        "primary_mode": "llm-assisted",
        "fallback_mode": "heuristic",
        "language_module_role": {
            "purpose": "grounding_chunking_provenance",
            "description": (
                "Language modules gather reliable facts, chunks, symbols, paths, "
                "and provenance. They optimize projection quality but are not a "
                "required perfect-parser barrier."
            ),
        },
        "source_facts": fact_bundle,
        "response_schema": deepcopy(CANVAS_QUERY_JSON_SCHEMA),
        "instructions": [
            "Treat LLM-assisted projection as the primary path.",
            "Use language-module facts as grounding evidence, not as a complete parser output.",
            "For monorepos, group behavior by human journey first, then use app_surfaces as lanes or drilldowns.",
            "Represent cross-surface handoffs only when route, call, import, event, or entrypoint facts support them.",
            "Use only source_facts as evidence.",
            "Return JSON only; no Markdown wrapper.",
            "Set mode to llm-assisted.",
            "Cite fact_ids on every operation.",
            "Prefer omission plus warning over unsupported inference.",
        ],
    }


def build_projection_prompt(
    source: Dict[str, Any],
    repo_summary: Optional[Dict[str, Any]] = None,
    *,
    max_facts: int = 200,
) -> Dict[str, Any]:
    """Return messages plus response schema for any LLM/provider wrapper."""

    contract = build_projection_contract(source, repo_summary, max_facts=max_facts)
    fact_bundle = contract["source_facts"]
    user_prompt = USER_PROMPT_TEMPLATE.format(
        canvas_query_schema=CANVAS_QUERY_SCHEMA,
        repo_summary=json.dumps(fact_bundle["repo"], indent=2, sort_keys=True),
        source_facts=json.dumps(fact_bundle["facts"], indent=2, sort_keys=True),
        response_schema=json.dumps(contract["response_schema"], indent=2, sort_keys=True),
    )
    return {
        "schema": "agentcanvas.llm_projection_prompt.v1",
        "version": "0.1.0",
        "primary_mode": contract["primary_mode"],
        "fallback_mode": contract["fallback_mode"],
        "language_module_role": contract["language_module_role"],
        "instructions": contract["instructions"],
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "response_schema": contract["response_schema"],
        "source_facts": fact_bundle,
    }


def normalize_fact_bundle(
    source: Dict[str, Any],
    repo_summary: Optional[Dict[str, Any]] = None,
    *,
    max_facts: int = 200,
) -> Dict[str, Any]:
    """Accept a workflow IR or source-facts bundle and return source_facts.v1."""

    if source.get("schema") == SOURCE_FACTS_SCHEMA:
        bundle = deepcopy(source)
        if repo_summary:
            bundle["repo"] = _merge_repo_summary(bundle.get("repo") or {}, repo_summary)
        bundle["facts"] = _limit_facts(bundle.get("facts") or [], max_facts)
        return bundle

    if source.get("schema") == WORKFLOW_IR_SCHEMA:
        return facts_from_workflow_ir(source, repo_summary, max_facts=max_facts)

    return {
        "schema": SOURCE_FACTS_SCHEMA,
        "version": "0.1.0",
        "repo": repo_summary or {},
        "facts": _limit_facts(source.get("facts") or [], max_facts),
        "warnings": [
            "Source did not declare a known schema; facts were passed through as-is."
        ],
    }


def facts_from_workflow_ir(
    workflow_ir: Dict[str, Any],
    repo_summary: Optional[Dict[str, Any]] = None,
    *,
    max_facts: int = 200,
) -> Dict[str, Any]:
    """Extract a compact, evidence-carrying fact bundle from workflow IR."""

    repo = _repo_summary_from_workflow_ir(workflow_ir)
    if repo_summary:
        repo = _merge_repo_summary(repo, repo_summary)

    facts: List[Dict[str, Any]] = []
    for surface in workflow_ir.get("app_surfaces") or []:
        facts.append(_app_surface_fact(surface))

    for component in workflow_ir.get("components") or []:
        facts.append(_component_fact(component))

    for node in workflow_ir.get("nodes") or []:
        facts.append(_node_fact(node))

    for edge in workflow_ir.get("edges") or []:
        facts.append(_edge_fact(edge))

    return {
        "schema": SOURCE_FACTS_SCHEMA,
        "version": "0.1.0",
        "repo": repo,
        "facts": _limit_facts(facts, max_facts),
        "warnings": [],
    }


def _repo_summary_from_workflow_ir(workflow_ir: Dict[str, Any]) -> Dict[str, Any]:
    workspace = workflow_ir.get("workspace") or {}
    return {
        "name": workspace.get("name"),
        "root": workspace.get("root"),
        "summary": workflow_ir.get("summary") or {},
        "package": workflow_ir.get("package") or {},
        "git": workflow_ir.get("git") or {},
        "focus": workflow_ir.get("focus") or {},
        "app_surfaces": workflow_ir.get("app_surfaces") or [],
    }


def _merge_repo_summary(
    base: Dict[str, Any],
    override: Dict[str, Any],
) -> Dict[str, Any]:
    merged = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            nested = deepcopy(merged[key])
            nested.update(value)
            merged[key] = nested
        else:
            merged[key] = value
    return merged


def _app_surface_fact(surface: Dict[str, Any]) -> Dict[str, Any]:
    surface_id = str(surface.get("id") or surface.get("root") or "surface")
    root = surface.get("root") or "."
    label = surface.get("name") or root
    kind = surface.get("kind") or "app_surface"
    platform = surface.get("platform") or "unknown"
    return {
        "id": f"app_surface:{surface_id}",
        "kind": "app_surface",
        "subject": surface_id,
        "summary": f"{kind} app surface {label} at {root} ({platform})",
        "attributes": _compact_dict(surface),
        "evidence": _path_evidence(
            [root if root != "." else None, *(surface.get("manifest_paths") or [])]
        ),
        "confidence": _confidence_score(surface.get("confidence")),
    }


def _confidence_score(value: Any, default: float = 0.75) -> float:
    if isinstance(value, dict):
        value = value.get("score", default)
    if value is None:
        return default
    try:
        score = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, score))


def _component_fact(component: Dict[str, Any]) -> Dict[str, Any]:
    component_id = str(component.get("id") or component.get("name") or "component")
    return {
        "id": f"component:{component_id}",
        "kind": "component",
        "subject": component_id,
        "summary": f"Component {component.get('name') or component_id}",
        "attributes": _compact_dict(component),
        "evidence": _path_evidence(component.get("paths") or []),
        "confidence": 1.0,
    }


def _node_fact(node: Dict[str, Any]) -> Dict[str, Any]:
    node_id = str(node.get("id") or "")
    label = str(node.get("label") or node_id)
    node_type = str(node.get("type") or "node")
    return {
        "id": f"node:{node_id}",
        "kind": "canvas_node",
        "subject": node_id,
        "summary": f"{node_type} node {label}",
        "attributes": {"node": _compact_node(node)},
        "evidence": _path_evidence([node.get("path")]),
        "confidence": 1.0,
    }


def _edge_fact(edge: Dict[str, Any]) -> Dict[str, Any]:
    edge_id = str(
        edge.get("id")
        or f"{edge.get('source', '')}->{edge.get('kind', '')}->{edge.get('target', '')}"
    )
    return {
        "id": f"edge:{edge_id}",
        "kind": "canvas_edge",
        "subject": edge_id,
        "summary": (
            f"{edge.get('source')} {edge.get('kind', 'relates_to')} "
            f"{edge.get('target')}"
        ),
        "attributes": {"edge": _compact_edge(edge)},
        "evidence": [],
        "confidence": 1.0,
    }


def _compact_node(node: Dict[str, Any]) -> Dict[str, Any]:
    compact = {
        "id": node.get("id"),
        "type": node.get("type"),
        "label": node.get("label"),
    }
    if node.get("path"):
        compact["path"] = node["path"]
    data = node.get("data")
    if isinstance(data, dict):
        compact["data"] = _compact_dict(data)
    return {key: value for key, value in compact.items() if value is not None}


def _compact_edge(edge: Dict[str, Any]) -> Dict[str, Any]:
    compact = {
        "id": edge.get("id"),
        "source": edge.get("source"),
        "target": edge.get("target"),
        "kind": edge.get("kind"),
    }
    if edge.get("label"):
        compact["label"] = edge["label"]
    data = edge.get("data")
    if isinstance(data, dict):
        compact["data"] = _compact_dict(data)
    return {key: value for key, value in compact.items() if value is not None}


def _compact_dict(value: Dict[str, Any], *, max_list_items: int = 12) -> Dict[str, Any]:
    compact: Dict[str, Any] = {}
    for key, item in value.items():
        if isinstance(item, list):
            compact[key] = item[:max_list_items]
        elif isinstance(item, dict):
            compact[key] = _compact_dict(item, max_list_items=max_list_items)
        else:
            compact[key] = item
    return compact


def _path_evidence(paths: Iterable[Any]) -> List[Dict[str, str]]:
    evidence = []
    for path in paths:
        if isinstance(path, str) and path:
            evidence.append({"path": PurePosixPath(path).as_posix()})
    return evidence


def _limit_facts(facts: Iterable[Dict[str, Any]], max_facts: int) -> List[Dict[str, Any]]:
    limited = []
    for fact in facts:
        if not isinstance(fact, dict):
            continue
        limited.append(fact)
        if len(limited) >= max_facts:
            break
    return limited
