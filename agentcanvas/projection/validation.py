"""Validation and materialization for AgentCanvas projection output."""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set

from agentcanvas.ir import SCHEMA as WORKFLOW_IR_SCHEMA
from agentcanvas.ir import now_utc, summarize_ir

from .contracts import CANVAS_QUERY_SCHEMA, SOURCE_FACTS_SCHEMA


class ProjectionValidationError(ValueError):
    """Raised when projection JSON cannot be accepted as canvas language."""


VISIBLE_TITLE_MAX_CHARS = 80
VISIBLE_STEPS_PER_JOURNEY_MAX = 8

_JARGON_RE = re.compile(
    r"\b(?:CI|AST|handler|middleware|module|linter|protocol)\b",
    flags=re.IGNORECASE,
)
_SNAKE_CASE_RE = re.compile(r"\b[a-z][a-z0-9]*_[a-z0-9_]*\b")
_ABSOLUTE_PATH_PREFIXES = (
    "/Users/",
    "/home/",
    "/private/",
    "/tmp/",
    "/var/",
    "~/",
)
_WINDOWS_PATH_RE = re.compile(r"^[A-Za-z]:[\\/]")
_FILE_EXTENSION_RE = re.compile(r"\.[A-Za-z0-9]{1,8}$")
_VISIBLE_TEXT_KEYS = (
    "text",
    "label",
    "title",
    "name",
    "entry",
    "summary",
    "condition",
)
_TITLE_LIKE_KEYS = ("title", "label", "name")


def validate_canvas_query(
    canvas_query: Dict[str, Any],
    source_facts: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """Return validation errors for canvas query JSON."""

    errors: List[str] = []
    if not isinstance(canvas_query, dict):
        return ["canvas query must be a JSON object"]

    if canvas_query.get("schema") != CANVAS_QUERY_SCHEMA:
        errors.append(f"schema must be {CANVAS_QUERY_SCHEMA}")
    if not isinstance(canvas_query.get("version"), str):
        errors.append("version must be a string")
    if canvas_query.get("mode") not in {"heuristic", "llm-assisted"}:
        errors.append("mode must be heuristic or llm-assisted")

    operations = canvas_query.get("operations")
    if not isinstance(operations, list):
        errors.append("operations must be a list")
        return errors

    fact_ids = _fact_ids(source_facts)
    known_nodes: Set[str] = set()
    deleted_nodes: Set[str] = set()
    edge_ids: Set[str] = set()

    for index, operation in enumerate(operations):
        prefix = f"operations[{index}]"
        if not isinstance(operation, dict):
            errors.append(f"{prefix} must be an object")
            continue

        op = operation.get("op")
        if op not in {"upsert_node", "upsert_edge", "delete_node", "delete_edge", "annotate"}:
            errors.append(f"{prefix}.op is not supported")
            continue

        _validate_operation_facts(prefix, operation, fact_ids, errors)

        if op == "upsert_node":
            node = operation.get("node")
            _validate_node(f"{prefix}.node", node, errors)
            if isinstance(node, dict) and isinstance(node.get("id"), str):
                known_nodes.add(node["id"])
                deleted_nodes.discard(node["id"])
            continue

        if op == "delete_node":
            target = operation.get("target")
            if not isinstance(target, str) or not target:
                errors.append(f"{prefix}.target must be a non-empty node id")
            else:
                deleted_nodes.add(target)
            continue

        if op == "upsert_edge":
            edge = operation.get("edge")
            _validate_edge(f"{prefix}.edge", edge, errors)
            if isinstance(edge, dict):
                edge_id = _edge_id(edge)
                if edge_id in edge_ids:
                    errors.append(f"{prefix}.edge duplicates edge id {edge_id}")
                edge_ids.add(edge_id)
            continue

        if op == "delete_edge":
            target = operation.get("target")
            if not isinstance(target, str) or not target:
                errors.append(f"{prefix}.target must be a non-empty edge id")
            continue

        if op == "annotate":
            target = operation.get("target")
            annotation = operation.get("annotation")
            if not isinstance(target, str) or not target:
                errors.append(f"{prefix}.target must be a non-empty canvas id")
            if not isinstance(annotation, dict):
                errors.append(f"{prefix}.annotation must be an object")

    active_nodes = known_nodes - deleted_nodes
    for index, operation in enumerate(operations):
        if operation.get("op") != "upsert_edge":
            continue
        edge = operation.get("edge")
        if not isinstance(edge, dict):
            continue
        source = edge.get("source")
        target = edge.get("target")
        if source not in active_nodes:
            errors.append(f"operations[{index}].edge.source is not an active node: {source}")
        if target not in active_nodes:
            errors.append(f"operations[{index}].edge.target is not an active node: {target}")

    return errors


def validate_canvas_query_quality(canvas_query: Dict[str, Any]) -> List[str]:
    """Return non-blocking visible-text quality warnings for canvas query JSON."""

    if not isinstance(canvas_query, dict):
        return []

    operations = canvas_query.get("operations")
    if not isinstance(operations, list):
        return []

    warnings: List[str] = []
    for index, operation in enumerate(operations):
        if not isinstance(operation, Mapping):
            continue

        prefix = f"operations[{index}]"
        op = operation.get("op")
        if op == "upsert_node":
            _collect_node_quality_warnings(
                f"{prefix}.node",
                operation.get("node"),
                warnings,
            )
        elif op == "upsert_edge":
            _collect_mapping_text_quality_warnings(
                f"{prefix}.edge",
                operation.get("edge"),
                warnings,
            )
        elif op == "annotate":
            _collect_mapping_text_quality_warnings(
                f"{prefix}.annotation",
                operation.get("annotation"),
                warnings,
            )

    return _dedupe_warnings(warnings)


def validate_canvas_query_result(
    canvas_query: Dict[str, Any],
    source_facts: Optional[Dict[str, Any]] = None,
) -> Dict[str, List[str]]:
    """Return hard validation errors plus non-blocking quality warnings."""

    return {
        "errors": validate_canvas_query(canvas_query, source_facts),
        "warnings": validate_canvas_query_quality(canvas_query),
    }


def validate_canvas_model(canvas_model: Dict[str, Any]) -> List[str]:
    """Return validation errors for a materialized AgentCanvas workflow IR."""

    errors: List[str] = []
    if not isinstance(canvas_model, dict):
        return ["canvas model must be a JSON object"]
    if canvas_model.get("schema") != WORKFLOW_IR_SCHEMA:
        errors.append(f"schema must be {WORKFLOW_IR_SCHEMA}")

    nodes = canvas_model.get("nodes")
    edges = canvas_model.get("edges")
    if not isinstance(nodes, list):
        errors.append("nodes must be a list")
        nodes = []
    if not isinstance(edges, list):
        errors.append("edges must be a list")
        edges = []

    node_ids: Set[str] = set()
    for index, node in enumerate(nodes):
        _validate_node(f"nodes[{index}]", node, errors)
        if isinstance(node, dict) and isinstance(node.get("id"), str):
            if node["id"] in node_ids:
                errors.append(f"nodes[{index}] duplicates node id {node['id']}")
            node_ids.add(node["id"])

    edge_ids: Set[str] = set()
    for index, edge in enumerate(edges):
        _validate_edge(f"edges[{index}]", edge, errors)
        if isinstance(edge, dict):
            edge_id = _edge_id(edge)
            if edge_id in edge_ids:
                errors.append(f"edges[{index}] duplicates edge id {edge_id}")
            edge_ids.add(edge_id)
            if edge.get("source") not in node_ids:
                errors.append(f"edges[{index}].source is not a node: {edge.get('source')}")
            if edge.get("target") not in node_ids:
                errors.append(f"edges[{index}].target is not a node: {edge.get('target')}")

    return errors


def materialize_canvas_model(
    canvas_query: Dict[str, Any],
    repo_summary: Optional[Dict[str, Any]] = None,
    *,
    source_facts: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Apply canvas query operations and return validated workflow IR shape."""

    validation_result = validate_canvas_query_result(canvas_query, source_facts)
    if validation_result["errors"]:
        raise ProjectionValidationError("; ".join(validation_result["errors"]))

    nodes: Dict[str, Dict[str, Any]] = {}
    edges: Dict[str, Dict[str, Any]] = {}
    annotations: Dict[str, List[Dict[str, Any]]] = {}

    for operation in canvas_query["operations"]:
        op = operation["op"]
        if op == "upsert_node":
            node = deepcopy(operation["node"])
            _attach_operation_provenance(node, operation)
            nodes[node["id"]] = node
        elif op == "delete_node":
            target = operation["target"]
            nodes.pop(target, None)
            for edge_id, edge in list(edges.items()):
                if edge.get("source") == target or edge.get("target") == target:
                    edges.pop(edge_id, None)
        elif op == "upsert_edge":
            edge = deepcopy(operation["edge"])
            _attach_operation_provenance(edge, operation)
            edge.setdefault("id", _edge_id(edge))
            edges[edge["id"]] = edge
        elif op == "delete_edge":
            edges.pop(operation["target"], None)
        elif op == "annotate":
            annotations.setdefault(operation["target"], []).append(
                deepcopy(operation["annotation"])
            )

    for target, target_annotations in annotations.items():
        if target in nodes:
            data = nodes[target].setdefault("data", {})
            data.setdefault("annotations", []).extend(target_annotations)
        elif target in edges:
            data = edges[target].setdefault("data", {})
            data.setdefault("annotations", []).extend(target_annotations)

    repo = repo_summary or {}
    workspace = {
        "root": repo.get("root"),
        "name": repo.get("name"),
    }
    model = {
        "schema": WORKFLOW_IR_SCHEMA,
        "version": "0.1.0",
        "generated_at": now_utc(),
        "workspace": workspace,
        "summary": deepcopy(repo.get("summary") or {}),
        "package": deepcopy(repo.get("package") or {}),
        "git": deepcopy(repo.get("git") or {}),
        "focus": deepcopy(repo.get("focus") or {}),
        "components": [],
        "nodes": list(nodes.values()),
        "edges": list(edges.values()),
        "projection": {
            "source_schema": canvas_query.get("schema"),
            "mode": canvas_query.get("mode"),
            "warnings": _dedupe_warnings(
                [
                    *_string_list(canvas_query.get("warnings")),
                    *validation_result["warnings"],
                ]
            ),
        },
    }
    model["summary"].update(summarize_ir(model))

    model_errors = validate_canvas_model(model)
    if model_errors:
        raise ProjectionValidationError("; ".join(model_errors))
    return model


def _validate_operation_facts(
    prefix: str,
    operation: Dict[str, Any],
    known_fact_ids: Set[str],
    errors: List[str],
) -> None:
    fact_ids = operation.get("fact_ids")
    if fact_ids is None:
        errors.append(f"{prefix}.fact_ids is required")
        return
    if not isinstance(fact_ids, list) or not fact_ids:
        errors.append(f"{prefix}.fact_ids must be a non-empty list")
        return
    for fact_id in fact_ids:
        if not isinstance(fact_id, str) or not fact_id:
            errors.append(f"{prefix}.fact_ids contains a non-string id")
        elif known_fact_ids and fact_id not in known_fact_ids:
            errors.append(f"{prefix}.fact_ids contains unknown id {fact_id}")


def _validate_node(prefix: str, node: Any, errors: List[str]) -> None:
    if not isinstance(node, dict):
        errors.append(f"{prefix} must be an object")
        return
    for key in ["id", "type", "label"]:
        if not isinstance(node.get(key), str) or not node.get(key):
            errors.append(f"{prefix}.{key} must be a non-empty string")
    if "path" in node and not isinstance(node["path"], str):
        errors.append(f"{prefix}.path must be a string when present")
    if "data" in node and not isinstance(node["data"], dict):
        errors.append(f"{prefix}.data must be an object when present")


def _validate_edge(prefix: str, edge: Any, errors: List[str]) -> None:
    if not isinstance(edge, dict):
        errors.append(f"{prefix} must be an object")
        return
    for key in ["source", "target", "kind"]:
        if not isinstance(edge.get(key), str) or not edge.get(key):
            errors.append(f"{prefix}.{key} must be a non-empty string")
    if "id" in edge and not isinstance(edge["id"], str):
        errors.append(f"{prefix}.id must be a string when present")
    if "data" in edge and not isinstance(edge["data"], dict):
        errors.append(f"{prefix}.data must be an object when present")


def _edge_id(edge: Dict[str, Any]) -> str:
    value = edge.get("id")
    if isinstance(value, str) and value:
        return value
    return f"{edge.get('source')}->{edge.get('kind')}->{edge.get('target')}"


def _collect_node_quality_warnings(
    prefix: str,
    node: Any,
    warnings: List[str],
) -> None:
    if not isinstance(node, Mapping):
        return

    _collect_mapping_text_quality_warnings(prefix, node, warnings)

    data = node.get("data")
    if not isinstance(data, Mapping):
        return

    journey = data.get("journey")
    if isinstance(journey, Mapping):
        _collect_mapping_text_quality_warnings(
            f"{prefix}.data.journey",
            journey,
            warnings,
        )
        steps = journey.get("steps")
        if isinstance(steps, list):
            visible_steps = _count_visible_steps(steps)
            if visible_steps > VISIBLE_STEPS_PER_JOURNEY_MAX:
                warnings.append(
                    f"{prefix}.data.journey has {visible_steps} visible steps; "
                    f"keep journeys to {VISIBLE_STEPS_PER_JOURNEY_MAX} or fewer steps."
                )
            _collect_steps_quality_warnings(
                f"{prefix}.data.journey.steps",
                steps,
                warnings,
            )

    journey_step = data.get("journey_step")
    if isinstance(journey_step, Mapping):
        _collect_mapping_text_quality_warnings(
            f"{prefix}.data.journey_step",
            journey_step,
            warnings,
        )


def _collect_steps_quality_warnings(
    prefix: str,
    steps: Sequence[Any],
    warnings: List[str],
) -> None:
    for index, step in enumerate(steps):
        if not isinstance(step, Mapping):
            continue

        step_prefix = f"{prefix}[{index}]"
        _collect_mapping_text_quality_warnings(step_prefix, step, warnings)
        nested_steps = step.get("steps")
        if isinstance(nested_steps, list):
            _collect_steps_quality_warnings(
                f"{step_prefix}.steps",
                nested_steps,
                warnings,
            )


def _collect_mapping_text_quality_warnings(
    prefix: str,
    value: Any,
    warnings: List[str],
) -> None:
    if not isinstance(value, Mapping):
        return

    for key in _VISIBLE_TEXT_KEYS:
        raw_text = value.get(key)
        if not isinstance(raw_text, str):
            continue

        location = f"{prefix}.{key}"
        text = raw_text.strip()
        if not text:
            continue

        if key in _TITLE_LIKE_KEYS and len(text) > VISIBLE_TITLE_MAX_CHARS:
            warnings.append(
                f"{location} is very long ({len(text)} characters); "
                f"keep visible titles to {VISIBLE_TITLE_MAX_CHARS} characters or fewer."
            )

        issue_labels = _technical_visible_text_issues(text)
        if issue_labels:
            warnings.append(
                f"{location} may be too technical for visible canvas text "
                f"({', '.join(issue_labels)}): {_excerpt(text)!r}"
            )


def _technical_visible_text_issues(text: str) -> List[str]:
    issues: List[str] = []
    tokens = [_strip_visible_token(token) for token in text.split()]

    if any(_looks_like_file_path(token) for token in tokens):
        issues.append("raw file path")
    if any(_looks_like_glob_pattern(token) for token in tokens):
        issues.append("glob pattern")
    if _SNAKE_CASE_RE.search(text):
        issues.append("implementation token")
    if _JARGON_RE.search(text):
        issues.append("technical jargon")

    return issues


def _strip_visible_token(token: str) -> str:
    return token.strip("`'\".,;:()<>\n\t")


def _looks_like_file_path(token: str) -> bool:
    if not token:
        return False
    if token.startswith(_ABSOLUTE_PATH_PREFIXES) or _WINDOWS_PATH_RE.match(token):
        return True
    if "/" not in token and "\\" not in token:
        return False

    normalized = token.replace("\\", "/")
    if normalized.startswith(("./", "../")):
        return True
    if normalized.startswith("/"):
        return False

    last_segment = normalized.rsplit("/", 1)[-1]
    return bool(_FILE_EXTENSION_RE.search(last_segment))


def _looks_like_glob_pattern(token: str) -> bool:
    if "*" not in token or token in {"*", "**"}:
        return False
    return any(char.isalnum() for char in token)


def _count_visible_steps(steps: Iterable[Any]) -> int:
    count = 0
    for step in steps:
        if not isinstance(step, Mapping):
            continue
        count += 1
        nested_steps = step.get("steps")
        if isinstance(nested_steps, list):
            count += _count_visible_steps(nested_steps)
    return count


def _string_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _dedupe_warnings(warnings: Iterable[str]) -> List[str]:
    deduped: List[str] = []
    seen: Set[str] = set()
    for warning in warnings:
        if warning in seen:
            continue
        deduped.append(warning)
        seen.add(warning)
    return deduped


def _excerpt(text: str, *, max_chars: int = 90) -> str:
    if len(text) <= max_chars:
        return text
    return f"{text[: max_chars - 1].rstrip()}..."


def _attach_operation_provenance(
    item: Dict[str, Any],
    operation: Dict[str, Any],
) -> None:
    data = item.setdefault("data", {})
    if not isinstance(data, dict):
        return

    projection = data.get("projection")
    if not isinstance(projection, dict):
        projection = {}

    fact_ids = operation.get("fact_ids")
    if isinstance(fact_ids, list):
        projection["fact_ids"] = [
            fact_id for fact_id in fact_ids if isinstance(fact_id, str) and fact_id
        ]

    confidence = operation.get("confidence")
    if isinstance(confidence, (int, float)):
        projection["confidence"] = max(0.0, min(1.0, float(confidence)))

    rationale = operation.get("rationale")
    if isinstance(rationale, str) and rationale.strip():
        projection["rationale"] = rationale.strip()

    if projection:
        data["projection"] = projection


def _fact_ids(source_facts: Optional[Dict[str, Any]]) -> Set[str]:
    if not source_facts or source_facts.get("schema") != SOURCE_FACTS_SCHEMA:
        return set()
    ids = set()
    for fact in source_facts.get("facts") or []:
        if isinstance(fact, dict) and isinstance(fact.get("id"), str):
            ids.add(fact["id"])
    return ids
