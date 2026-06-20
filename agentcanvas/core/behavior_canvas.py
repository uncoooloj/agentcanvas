"""Deterministic behavior-canvas projection from workflow IR.

The workflow IR is intentionally code-shaped. This module produces the
human-facing canvas shape that the browser can render without treating files,
exports, or components as sequential product behavior.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

BEHAVIOR_CANVAS_SCHEMA = "agentcanvas.behavior_canvas.v1"
BEHAVIOR_CANVAS_WRAPPER_SCHEMA = "agentcanvas.behavior_canvas_response.v1"
CANVAS_MAPPING_SCHEMA = "agentcanvas.canvas_mapping.v1"
MAX_JOURNEYS = 50
MAX_REFS = 8
SOURCE_SUFFIXES = {".cjs", ".js", ".jsx", ".mjs", ".py", ".ts", ".tsx"}
FIXTURE_PARTS = {
    "__tests__",
    "demo_project",
    "demo_projects",
    "examples",
    "fixture",
    "fixtures",
    "test",
    "tests",
}
API_METHOD_BY_FUNCTION = {
    "do_GET": "GET",
    "handle_api_get": "GET",
    "do_POST": "POST",
    "handle_api_post": "POST",
}
SCRIPT_NAMES_OF_INTEREST = {
    "agentcanvas:index",
    "build",
    "build:agentcanvas",
    "check",
    "dev",
    "lint",
    "preview",
    "start",
    "test",
    "typecheck",
}


@dataclass
class _Step:
    id: str
    role: str
    text: str
    refs: Tuple[str, ...] = ()
    detail: Optional[str] = None
    uncertain: bool = False

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "kind": "step",
            "id": self.id,
            "role": self.role,
            "text": self.text,
        }
        if self.detail:
            payload["detail"] = self.detail
        if self.uncertain:
            payload["uncertain"] = True
        refs = _dedupe(self.refs)[:MAX_REFS]
        if refs:
            payload["tech"] = {"refs": refs}
        return payload


@dataclass
class _Journey:
    id: str
    title: str
    summary: str
    entry: str
    sort_key: Tuple[int, str]
    nodes: List[_Step] = field(default_factory=list)
    refs: Tuple[str, ...] = ()
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "id": self.id,
            "title": self.title,
            "summary": self.summary,
            "entry": self.entry,
            "nodes": [node.to_dict() for node in self.nodes],
        }
        refs = _dedupe(self.refs)[:MAX_REFS]
        if refs:
            payload["tech"] = {"refs": refs}
        if self.metadata:
            payload["metadata"] = self.metadata
        return payload


@dataclass(frozen=True)
class _ApiEndpoint:
    method: str
    path: str
    source_path: str
    line: int


@dataclass(frozen=True)
class _CliCommand:
    name: str
    help: str
    source_path: str
    line: int


def workflow_ir_to_behavior_canvas(
    workflow_ir: Mapping[str, Any],
    *,
    workspace: Optional[str | Path] = None,
    is_demo: bool = False,
) -> Dict[str, Any]:
    """Return a frontend AppModel-like canvas from raw workflow IR."""

    workspace_info = workflow_ir.get("workspace") if isinstance(workflow_ir.get("workspace"), Mapping) else {}
    workspace_name = str(workspace_info.get("name") or "Your app")
    workspace_root = Path(workspace) if workspace is not None else _workspace_root(workflow_ir)
    components = [item for item in workflow_ir.get("components") or [] if isinstance(item, Mapping)]
    component_index = _component_index(components)

    journeys: Dict[str, _Journey] = {}

    def add(journey: _Journey) -> None:
        if not journey.nodes or journey.id in journeys:
            return
        journeys[journey.id] = journey

    for journey in _cli_journeys(workflow_ir, workspace_root):
        add(journey)
    for journey in _api_journeys(workflow_ir, workspace_root):
        add(journey)
    for journey in _route_journeys(workflow_ir, component_index):
        add(journey)
    for journey in _source_fact_route_journeys(workflow_ir):
        add(journey)
    for journey in _app_surface_journeys(workflow_ir, have_cli=any(item.id.startswith("cli:") for item in journeys.values())):
        add(journey)
    for journey in _script_journeys(workflow_ir):
        add(journey)

    ordered = sorted(journeys.values(), key=lambda item: item.sort_key)[:MAX_JOURNEYS]
    if not ordered:
        ordered = [_fallback_journey(workflow_ir, components)]

    return {
        "schema": BEHAVIOR_CANVAS_SCHEMA,
        "version": "0.1.0",
        "appName": _human_title(workspace_name),
        "journeys": [journey.to_dict() for journey in ordered],
        "isDemo": bool(is_demo),
        "thin": len(ordered) <= 2,
        "metadata": {
            "source_schema": workflow_ir.get("schema"),
            "generated_at": workflow_ir.get("generated_at"),
            "summary": workflow_ir.get("summary") or {},
            "app_surfaces": _public_app_surfaces(workflow_ir),
            "components": _public_components(components),
            "projection": {
                "mode": "deterministic",
                "warnings": _projection_warnings(workflow_ir, len(journeys), len(ordered)),
            },
        },
    }


def build_behavior_canvas(
    workflow_ir: Mapping[str, Any],
    *,
    workspace: Optional[str | Path] = None,
    is_demo: bool = False,
) -> Dict[str, Any]:
    """Build the persisted API response for ``/api/canvas``."""

    canvas = workflow_ir_to_behavior_canvas(
        workflow_ir,
        workspace=workspace,
        is_demo=is_demo,
    )
    warnings = (
        (canvas.get("metadata") or {})
        .get("projection", {})
        .get("warnings", [])
    )
    return {
        "schema": BEHAVIOR_CANVAS_WRAPPER_SCHEMA,
        "version": "0.1.0",
        "canvas": canvas,
        "mapping": {
            "schema": CANVAS_MAPPING_SCHEMA,
            "status": "ready",
            "mode": "deterministic",
            "primaryMode": "llm-assisted",
            "flowCount": len(canvas.get("journeys") or []),
            "warnings": warnings,
            "stages": [
                {
                    "id": "index",
                    "label": "Indexed workspace",
                    "status": "done",
                },
                {
                    "id": "entrypoints",
                    "label": "Found runtime entrypoints",
                    "status": "done" if canvas.get("journeys") else "error",
                },
                {
                    "id": "canvas",
                    "label": "Built behavior canvas",
                    "status": "ready",
                },
            ],
        },
    }


def build_agent_authored_canvas(
    canvas_model: Mapping[str, Any],
    *,
    workspace: Optional[str | Path] = None,
    canvas_query: Optional[Mapping[str, Any]] = None,
    is_demo: bool = False,
) -> Dict[str, Any]:
    """Build the persisted API response from an agent-authored canvas model.

    ``canvas_model`` is the validated graph shape produced by ``apply-query``.
    This converts that graph into the human-facing behavior canvas without
    treating the graph as fresh index evidence.
    """

    canvas = _agent_authored_behavior_canvas(
        canvas_model,
        workspace=workspace,
        canvas_query=canvas_query,
        is_demo=is_demo,
    )
    warnings = (
        (canvas.get("metadata") or {})
        .get("projection", {})
        .get("warnings", [])
    )
    return {
        "schema": BEHAVIOR_CANVAS_WRAPPER_SCHEMA,
        "version": "0.1.0",
        "canvas": canvas,
        "mapping": {
            "schema": CANVAS_MAPPING_SCHEMA,
            "status": "ready",
            "mode": "agent-authored",
            "primaryMode": "agent-authored",
            "flowCount": len(canvas.get("journeys") or []),
            "warnings": warnings,
            "stages": [
                {
                    "id": "evidence",
                    "label": "Read workspace evidence",
                    "status": "done",
                },
                {
                    "id": "agent-map",
                    "label": "Agent wrote behavior canvas",
                    "status": "done",
                },
                {
                    "id": "canvas",
                    "label": "Browser canvas ready",
                    "status": "ready",
                },
            ],
        },
    }


def _agent_authored_behavior_canvas(
    canvas_model: Mapping[str, Any],
    *,
    workspace: Optional[str | Path] = None,
    canvas_query: Optional[Mapping[str, Any]] = None,
    is_demo: bool = False,
) -> Dict[str, Any]:
    workspace_info = canvas_model.get("workspace") if isinstance(canvas_model.get("workspace"), Mapping) else {}
    workspace_name = str(
        workspace_info.get("name")
        or (Path(workspace).name if workspace is not None else "")
        or "Your app"
    )
    journeys = _agent_annotation_journeys(canvas_model)
    if not journeys:
        journeys = _agent_graph_journeys(canvas_model)

    ordered = sorted(journeys, key=lambda item: item.sort_key)[:MAX_JOURNEYS]
    projection = canvas_model.get("projection") if isinstance(canvas_model.get("projection"), Mapping) else {}
    query_mode = (
        str(canvas_query.get("mode"))
        if isinstance(canvas_query, Mapping) and canvas_query.get("mode")
        else str(projection.get("mode") or "agent-authored")
    )
    raw_warnings = list(projection.get("warnings") or [])
    if isinstance(canvas_query, Mapping):
        raw_warnings.extend(canvas_query.get("warnings") or [])
    warnings = [str(item) for item in raw_warnings if item]
    if not ordered:
        warnings.append("Agent-authored canvas had no displayable flows.")

    return {
        "schema": BEHAVIOR_CANVAS_SCHEMA,
        "version": "0.1.0",
        "appName": _human_title(workspace_name),
        "journeys": [journey.to_dict() for journey in ordered],
        "isDemo": bool(is_demo),
        "thin": len(ordered) <= 2,
        "metadata": {
            "source_schema": canvas_model.get("schema"),
            "workspace": str(workspace) if workspace is not None else workspace_info.get("root"),
            "generated_at": canvas_model.get("generated_at"),
            "summary": canvas_model.get("summary") or {},
            "projection": {
                "mode": "agent-authored",
                "query_mode": query_mode,
                "warnings": _dedupe(warnings),
            },
        },
    }


def _agent_annotation_journeys(canvas_model: Mapping[str, Any]) -> List[_Journey]:
    journeys: Dict[str, _Journey] = {}
    for node in canvas_model.get("nodes") or []:
        if not isinstance(node, Mapping):
            continue
        data = node.get("data") if isinstance(node.get("data"), Mapping) else {}
        journey_data = data.get("journey") if isinstance(data.get("journey"), Mapping) else None
        if not journey_data:
            continue

        journey_id = str(journey_data.get("id") or node.get("id") or node.get("label") or "agent-flow")
        title = str(journey_data.get("title") or node.get("label") or "Agent-authored flow")
        entry = str(journey_data.get("entry") or title)
        summary = str(journey_data.get("summary") or "Mapped by the connected agent from workspace evidence.")
        raw_steps = journey_data.get("steps") if isinstance(journey_data.get("steps"), list) else []
        refs = _agent_refs(node)
        steps: List[Tuple[str, str, Iterable[str]]] = []
        for index, raw_step in enumerate(raw_steps):
            if not isinstance(raw_step, Mapping):
                continue
            role = _agent_step_role(raw_step, index)
            text = _agent_step_text(raw_step, default=("Someone starts this flow" if index == 0 else "Do the next step"))
            steps.append((role, text, [*refs, *_agent_refs(raw_step)]))
        if not steps:
            steps = [("when", entry, refs), ("do", title, refs)]

        order = journey_data.get("order")
        sort_index = int(order) if isinstance(order, int) else 20
        journeys.setdefault(
            journey_id,
            _journey(
                journey_id=f"agent:{journey_id}",
                title=_sentence(title),
                summary=summary,
                entry=entry,
                sort_key=(sort_index, title.lower()),
                steps=steps,
                refs=refs,
                metadata={"projection": "agent-authored"},
            ),
        )
    return list(journeys.values())


def _agent_graph_journeys(canvas_model: Mapping[str, Any]) -> List[_Journey]:
    nodes = [node for node in canvas_model.get("nodes") or [] if isinstance(node, Mapping)]
    if not nodes:
        return []

    nodes_by_id = {str(node.get("id")): node for node in nodes if node.get("id")}
    outgoing: Dict[str, List[Tuple[str, Mapping[str, Any]]]] = {}
    incoming: set[str] = set()
    for edge in canvas_model.get("edges") or []:
        if not isinstance(edge, Mapping):
            continue
        source = str(edge.get("source") or "")
        target = str(edge.get("target") or "")
        if source not in nodes_by_id or target not in nodes_by_id:
            continue
        outgoing.setdefault(source, []).append((target, edge))
        incoming.add(target)

    for edge_list in outgoing.values():
        edge_list.sort(key=lambda item: (str(item[1].get("kind") or ""), item[0]))

    start_ids = _dedupe(
        [
            str(node.get("id"))
            for node in nodes
            if node.get("id") and (str(node.get("id")) not in incoming or _agent_node_looks_like_start(node))
        ]
    )
    if not start_ids:
        start_ids = [str(nodes[0].get("id"))]

    journeys: List[_Journey] = []
    consumed: set[str] = set()
    for start_id in start_ids:
        if len(journeys) >= MAX_JOURNEYS or start_id in consumed:
            continue
        chain = _walk_agent_graph(start_id, nodes_by_id, outgoing)
        if not chain:
            continue
        consumed.update(str(node.get("id")) for node in chain if node.get("id"))
        journeys.append(_journey_from_agent_chain(chain, len(journeys)))

    return journeys


def _walk_agent_graph(
    start_id: str,
    nodes_by_id: Mapping[str, Mapping[str, Any]],
    outgoing: Mapping[str, List[Tuple[str, Mapping[str, Any]]]],
) -> List[Mapping[str, Any]]:
    chain: List[Mapping[str, Any]] = []
    current = start_id
    seen: set[str] = set()
    while current in nodes_by_id and current not in seen and len(chain) < 12:
        seen.add(current)
        chain.append(nodes_by_id[current])
        next_edges = outgoing.get(current) or []
        if not next_edges:
            break
        current = next_edges[0][0]
    return chain


def _journey_from_agent_chain(chain: Sequence[Mapping[str, Any]], index: int) -> _Journey:
    first = chain[0]
    title = _agent_journey_title(first)
    entry = _agent_step_text(first, default="Someone starts this flow")
    refs = _dedupe(ref for node in chain for ref in _agent_refs(node))
    steps: List[Tuple[str, str, Iterable[str]]] = []
    for step_index, node in enumerate(chain):
        role = _agent_step_role(node, step_index)
        text = _agent_step_text(node, default=("Someone starts this flow" if step_index == 0 else "Do the next step"))
        steps.append((role, text, _agent_refs(node)))

    return _journey(
        journey_id=f"agent:{first.get('id') or title}",
        title=title,
        summary="Mapped by the connected agent from workspace evidence.",
        entry=entry,
        sort_key=(20 + index, title.lower()),
        steps=steps,
        refs=refs,
        metadata={"projection": "agent-authored"},
    )


def _agent_journey_title(node: Mapping[str, Any]) -> str:
    label = _agent_step_text(node, default="Agent-authored flow")
    match = re.match(
        r"^(?:someone|a user|the user)\s+(?:starts|opens|uses|runs|submits|requests|triggers|visits)\s+(.+)$",
        label,
        flags=re.IGNORECASE,
    )
    if match:
        return _human_title(match.group(1))
    return _human_title(label)


def _agent_node_looks_like_start(node: Mapping[str, Any]) -> bool:
    node_type = str(node.get("type") or "").lower()
    node_id = str(node.get("id") or "").lower()
    label = str(node.get("label") or "").lower()
    return (
        node_type in {"command", "entrypoint", "event", "page", "route", "screen", "trigger", "when"}
        or node_id.startswith("when:")
        or label.startswith(("someone ", "a user ", "the user "))
    )


def _agent_step_role(item: Mapping[str, Any], index: int) -> str:
    raw = str(item.get("role") or item.get("kind") or item.get("type") or "").lower()
    if raw in {"when", "trigger", "event", "route", "screen", "page", "command", "entrypoint"}:
        return "when" if index == 0 else "do"
    return "when" if index == 0 else "do"


def _agent_step_text(item: Mapping[str, Any], *, default: str) -> str:
    for key in ("text", "label", "title", "name"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return _sentence(value.strip())
    return default


def _agent_refs(item: Mapping[str, Any]) -> List[str]:
    refs: List[str] = []
    path = item.get("path")
    if isinstance(path, str):
        refs.append(_line_ref(path, item.get("line")))

    data = item.get("data") if isinstance(item.get("data"), Mapping) else {}
    projection = data.get("projection") if isinstance(data.get("projection"), Mapping) else {}
    for fact_id in projection.get("fact_ids") or item.get("fact_ids") or []:
        if isinstance(fact_id, str):
            refs.append(fact_id)

    for key in ("refs", "sources"):
        values = item.get(key)
        if isinstance(values, list):
            refs.extend(str(value) for value in values if value)

    provenance = item.get("provenance")
    if isinstance(provenance, list):
        for entry in provenance:
            if not isinstance(entry, Mapping):
                continue
            location = entry.get("location") if isinstance(entry.get("location"), Mapping) else {}
            entry_path = location.get("path") or entry.get("path")
            if isinstance(entry_path, str):
                refs.append(_line_ref(entry_path, location.get("line") or entry.get("line")))

    return _dedupe(refs)


def _cli_journeys(workflow_ir: Mapping[str, Any], workspace: Optional[Path]) -> List[_Journey]:
    if workspace is None:
        return []

    executables = _python_console_scripts(workflow_ir, workspace)
    if not executables:
        return []

    commands = _find_cli_commands(workflow_ir, workspace)
    if not commands:
        return [
            _journey(
                journey_id=f"cli:{_slug(command)}",
                title=f"`{command}` command",
                summary="Python console script entrypoint.",
                entry=f"Someone runs `{command}`",
                sort_key=(10, command),
                refs=(ref,),
                steps=[
                    ("when", f"Someone runs `{command}`", (ref,)),
                    ("do", f"Run `{target}`", (ref,)),
                ],
            )
            for command, target, ref in executables
        ]

    journeys: List[_Journey] = []
    for executable, _target, script_ref in executables:
        for command in commands:
            full_command = f"{executable} {command.name}"
            ref = _line_ref(command.source_path, command.line)
            journeys.append(
                _journey(
                    journey_id=f"cli:{_slug(full_command)}",
                    title=f"`{full_command}`",
                    summary=command.help or "CLI command entrypoint.",
                    entry=f"Someone runs `{full_command}`",
                    sort_key=(10, full_command),
                    refs=(script_ref, ref),
                    steps=[
                        ("when", f"Someone runs `{full_command}`", (script_ref, ref)),
                        ("do", _cli_action_text(command.name, command.help), (ref,)),
                    ],
                    metadata={"entrypoint": executable, "command": command.name},
                )
            )
    return journeys


def _api_journeys(workflow_ir: Mapping[str, Any], workspace: Optional[Path]) -> List[_Journey]:
    endpoints = _find_api_endpoints(workflow_ir, workspace)
    journeys: List[_Journey] = []
    for endpoint in endpoints:
        ref = _line_ref(endpoint.source_path, endpoint.line)
        title = f"{endpoint.method} {endpoint.path}"
        journeys.append(
            _journey(
                journey_id=f"api:{endpoint.method.lower()}:{_slug(endpoint.path)}",
                title=title,
                summary="Local AgentCanvas HTTP API endpoint.",
                entry=f"A {endpoint.method} request hits {endpoint.path}",
                sort_key=(20, title),
                refs=(ref,),
                steps=[
                    ("when", f"A {endpoint.method} request hits {endpoint.path}", (ref,)),
                    ("do", _api_action_text(endpoint.method, endpoint.path), (ref,)),
                ],
                metadata={"method": endpoint.method, "path": endpoint.path},
            )
        )
    return journeys


def _route_journeys(
    workflow_ir: Mapping[str, Any],
    component_index: Mapping[str, Mapping[str, Any]],
) -> List[_Journey]:
    journeys: List[_Journey] = []
    for node in workflow_ir.get("nodes") or []:
        if not isinstance(node, Mapping) or node.get("type") != "route":
            continue
        data = node.get("data") if isinstance(node.get("data"), Mapping) else {}
        source_path = str(node.get("path") or data.get("file") or "")
        route_path = str(data.get("path") or node.get("label") or "")
        if not route_path or _is_fixture_path(source_path):
            continue
        method = str(data.get("method") or "ANY").upper()
        refs = _dedupe(
            [
                str(node.get("id") or ""),
                _line_ref(source_path, data.get("line")),
                *_component_refs(source_path, component_index),
            ]
        )
        title = f"{method} {route_path}" if method != "ANY" else route_path
        action = "Run the route handler"
        if data.get("source") == "file":
            action = "Render the file-based route"
        journeys.append(
            _journey(
                journey_id=f"route:{method.lower()}:{_slug(route_path)}:{_slug(source_path)}",
                title=title,
                summary="Application route entrypoint.",
                entry=_request_entry(method, route_path),
                sort_key=(30, title),
                refs=tuple(refs),
                steps=[
                    ("when", _request_entry(method, route_path), tuple(refs[:2])),
                    ("do", action, tuple(refs)),
                ],
                metadata={"method": method, "path": route_path, "source": source_path},
            )
        )
    return journeys


def _source_fact_route_journeys(workflow_ir: Mapping[str, Any]) -> List[_Journey]:
    facts = (workflow_ir.get("source_facts") or {}).get("facts") if isinstance(workflow_ir.get("source_facts"), Mapping) else []
    journeys: List[_Journey] = []
    seen: set[Tuple[str, str, str]] = set()
    for fact in facts or []:
        if not isinstance(fact, Mapping):
            continue
        attributes = fact.get("attributes") if isinstance(fact.get("attributes"), Mapping) else {}
        if attributes.get("fact_type") != "route":
            continue
        source_path = _fact_path(fact, attributes)
        if _is_fixture_path(source_path):
            continue
        route_path = str(attributes.get("path") or fact.get("subject") or "")
        if not route_path:
            continue
        methods = _route_methods(attributes)
        method = methods[0] if methods else "ANY"
        key = (method, route_path, source_path)
        if key in seen:
            continue
        seen.add(key)
        refs = _fact_refs(fact, attributes)
        title = f"{method} {route_path}" if method != "ANY" else route_path
        handler = str(attributes.get("handler") or attributes.get("view") or "").strip()
        journeys.append(
            _journey(
                journey_id=f"routefact:{method.lower()}:{_slug(route_path)}:{_slug(source_path)}",
                title=title,
                summary="Language-extracted route entrypoint.",
                entry=_request_entry(method, route_path),
                sort_key=(35, title),
                refs=tuple(refs),
                steps=[
                    ("when", _request_entry(method, route_path), tuple(refs)),
                    ("do", f"Run {handler}" if handler else "Run the route handler", tuple(refs)),
                ],
                metadata={"method": method, "path": route_path, "source": source_path},
            )
        )
    return journeys


def _app_surface_journeys(workflow_ir: Mapping[str, Any], *, have_cli: bool) -> List[_Journey]:
    journeys: List[_Journey] = []
    for surface in workflow_ir.get("app_surfaces") or []:
        if not isinstance(surface, Mapping):
            continue
        root = str(surface.get("root") or ".")
        if _is_fixture_path(root):
            continue
        surface_type = str(surface.get("type") or "package")
        if root == "." and have_cli:
            continue
        refs = _surface_refs(surface)
        name = str(surface.get("name") or root or "app")
        title = _surface_title(name, surface_type)
        entry = _surface_entry(name, surface_type)
        journeys.append(
            _journey(
                journey_id=f"surface:{_slug(str(surface.get('id') or root))}",
                title=title,
                summary=f"{_human_title(surface_type)} app surface.",
                entry=entry,
                sort_key=(40, title),
                refs=tuple(refs),
                steps=[
                    ("when", entry, tuple(refs[:2])),
                    ("do", _surface_action(surface), tuple(refs)),
                ],
                metadata={
                    "app_surface_id": surface.get("id"),
                    "type": surface_type,
                    "root": root,
                },
            )
        )
    return journeys


def _script_journeys(workflow_ir: Mapping[str, Any]) -> List[_Journey]:
    package_info = workflow_ir.get("package") if isinstance(workflow_ir.get("package"), Mapping) else {}
    manifests = package_info.get("manifests") if isinstance(package_info.get("manifests"), list) else []
    manager = str(package_info.get("manager") or "npm")
    journeys: List[_Journey] = []
    for manifest in manifests:
        if not isinstance(manifest, Mapping):
            continue
        manifest_path = str(manifest.get("path") or "")
        if _is_fixture_path(manifest_path):
            continue
        scripts = manifest.get("scripts") if isinstance(manifest.get("scripts"), Mapping) else {}
        package_root = _parent_path(manifest_path)
        package_label = package_root if package_root != "." else str(manifest.get("name") or "workspace")
        for name, command in sorted(scripts.items()):
            if str(name) not in SCRIPT_NAMES_OF_INTEREST and not any(word in str(name).lower() for word in ("build", "check", "dev", "lint", "test")):
                continue
            run_command = f"{manager} run {name}"
            ref = manifest_path
            journeys.append(
                _journey(
                    journey_id=f"script:{_slug(package_label)}:{_slug(str(name))}",
                    title=f"{package_label}: `{run_command}`",
                    summary="Package script entrypoint.",
                    entry=f"Someone runs `{run_command}`",
                    sort_key=(50, f"{package_label}:{name}"),
                    refs=(ref,),
                    steps=[
                        ("when", f"Someone runs `{run_command}` in {package_label}", (ref,)),
                        ("do", f"Execute `{command}`", (ref,)),
                    ],
                    metadata={"package": package_label, "script": name},
                )
            )
    return journeys[:12]


def _fallback_journey(workflow_ir: Mapping[str, Any], components: Sequence[Mapping[str, Any]]) -> _Journey:
    refs = [str(component.get("id") or component.get("name")) for component in components[:MAX_REFS]]
    summary = workflow_ir.get("summary") if isinstance(workflow_ir.get("summary"), Mapping) else {}
    return _journey(
        journey_id="workspace-overview",
        title="Workspace overview",
        summary="No clear runtime entrypoints were detected, so this is a compact project overview.",
        entry="Someone opens the workspace",
        sort_key=(90, "workspace-overview"),
        refs=tuple(refs),
        steps=[
            ("when", "Someone opens the workspace", tuple(refs[:2])),
            (
                "do",
                f"Review {summary.get('source_files', 0)} source files across {summary.get('components', 0)} components",
                tuple(refs),
            ),
        ],
        metadata={"fallback": True},
    )


def _journey(
    *,
    journey_id: str,
    title: str,
    summary: str,
    entry: str,
    sort_key: Tuple[int, str],
    steps: Sequence[Tuple[str, str, Iterable[str]]],
    refs: Iterable[str] = (),
    metadata: Optional[Dict[str, Any]] = None,
) -> _Journey:
    normalized_id = _stable_id(journey_id)
    nodes = [
        _Step(
            id=f"{normalized_id}:{index}:{role}",
            role=role,
            text=text,
            refs=tuple(ref for ref in step_refs if ref),
        )
        for index, (role, text, step_refs) in enumerate(steps)
    ]
    return _Journey(
        id=normalized_id,
        title=title,
        summary=summary,
        entry=entry,
        sort_key=sort_key,
        nodes=nodes,
        refs=tuple(ref for ref in refs if ref),
        metadata=metadata or {},
    )


def _find_api_endpoints(
    workflow_ir: Mapping[str, Any],
    workspace: Optional[Path],
) -> List[_ApiEndpoint]:
    if workspace is None:
        return []
    endpoints: Dict[Tuple[str, str, str, int], _ApiEndpoint] = {}
    for source_path in _source_paths(workflow_ir, suffixes={".py"}):
        if _is_fixture_path(source_path):
            continue
        text = _safe_read(workspace / source_path)
        if not text:
            continue
        try:
            tree = ast.parse(text, filename=source_path)
        except SyntaxError:
            continue
        visitor = _ApiEndpointVisitor(source_path)
        visitor.visit(tree)
        for endpoint in visitor.endpoints:
            endpoints[(endpoint.method, endpoint.path, endpoint.source_path, endpoint.line)] = endpoint
    return sorted(endpoints.values(), key=lambda item: (item.method, item.path, item.source_path, item.line))


class _ApiEndpointVisitor(ast.NodeVisitor):
    def __init__(self, source_path: str) -> None:
        self.source_path = source_path
        self.function_stack: List[str] = []
        self.endpoints: List[_ApiEndpoint] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.function_stack.append(node.name)
        self.generic_visit(node)
        self.function_stack.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.visit_FunctionDef(node)  # type: ignore[arg-type]

    def visit_Compare(self, node: ast.Compare) -> None:
        path = _api_path_from_compare(node)
        method = self._current_method()
        if path and method:
            self.endpoints.append(_ApiEndpoint(method, path, self.source_path, int(getattr(node, "lineno", 1))))
        self.generic_visit(node)

    def _current_method(self) -> Optional[str]:
        for function_name in reversed(self.function_stack):
            method = API_METHOD_BY_FUNCTION.get(function_name)
            if method:
                return method
        return None


def _api_path_from_compare(node: ast.Compare) -> Optional[str]:
    if len(node.ops) != 1 or not isinstance(node.ops[0], ast.Eq) or len(node.comparators) != 1:
        return None
    left_path = _path_attribute_name(node.left)
    right_path = _path_attribute_name(node.comparators[0])
    left_string = _string_constant(node.left)
    right_string = _string_constant(node.comparators[0])
    if left_path and right_string and right_string.startswith("/api/"):
        return right_string
    if right_path and left_string and left_string.startswith("/api/"):
        return left_string
    return None


def _path_attribute_name(node: ast.AST) -> Optional[str]:
    if isinstance(node, ast.Attribute) and node.attr == "path":
        return node.attr
    return None


def _string_constant(node: ast.AST) -> Optional[str]:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Str):
        return node.s
    return None


def _find_cli_commands(
    workflow_ir: Mapping[str, Any],
    workspace: Path,
) -> List[_CliCommand]:
    commands: Dict[str, _CliCommand] = {}
    for source_path in _source_paths(workflow_ir, suffixes={".py"}):
        if _is_fixture_path(source_path):
            continue
        text = _safe_read(workspace / source_path)
        if not text or "add_parser" not in text:
            continue
        try:
            tree = ast.parse(text, filename=source_path)
        except SyntaxError:
            continue
        visitor = _CliCommandVisitor(source_path)
        visitor.visit(tree)
        for command in visitor.commands:
            commands.setdefault(command.name, command)
    return sorted(commands.values(), key=lambda item: item.name)


class _CliCommandVisitor(ast.NodeVisitor):
    def __init__(self, source_path: str) -> None:
        self.source_path = source_path
        self.commands: List[_CliCommand] = []

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Attribute) and node.func.attr == "add_parser" and node.args:
            name = _string_constant(node.args[0])
            if name and not name.startswith("-"):
                help_text = ""
                for keyword in node.keywords:
                    if keyword.arg == "help":
                        help_text = _string_constant(keyword.value) or ""
                        break
                self.commands.append(
                    _CliCommand(
                        name=name,
                        help=help_text,
                        source_path=self.source_path,
                        line=int(getattr(node, "lineno", 1)),
                    )
                )
        self.generic_visit(node)


def _python_console_scripts(
    workflow_ir: Mapping[str, Any],
    workspace: Path,
) -> List[Tuple[str, str, str]]:
    package_info = workflow_ir.get("package") if isinstance(workflow_ir.get("package"), Mapping) else {}
    configured = package_info.get("python_scripts") if isinstance(package_info.get("python_scripts"), list) else []
    scripts: List[Tuple[str, str, str]] = []
    for item in configured:
        if not isinstance(item, Mapping):
            continue
        path = str(item.get("path") or "pyproject.toml")
        for name, target in sorted((item.get("scripts") or {}).items()):
            scripts.append((str(name), str(target), path))
    if scripts:
        return scripts

    pyproject = workspace / "pyproject.toml"
    parsed = parse_pyproject_scripts(_safe_read(pyproject))
    return [(name, target, "pyproject.toml") for name, target in sorted(parsed.items())]


def parse_pyproject_scripts(text: str) -> Dict[str, str]:
    """Parse ``[project.scripts]`` with a small TOML subset."""

    scripts: Dict[str, str] = {}
    in_section = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            in_section = line == "[project.scripts]"
            continue
        if not in_section or "=" not in line:
            continue
        name, raw_value = line.split("=", 1)
        name = name.strip().strip("\"'")
        value = raw_value.split("#", 1)[0].strip().strip("\"'")
        if name and value:
            scripts[name] = value
    return scripts


def _source_paths(
    workflow_ir: Mapping[str, Any],
    *,
    suffixes: Optional[set[str]] = None,
) -> List[str]:
    paths: set[str] = set()
    for node in workflow_ir.get("nodes") or []:
        if not isinstance(node, Mapping) or node.get("type") != "file":
            continue
        path = str(node.get("path") or "")
        if not path:
            continue
        if suffixes and PurePosixPath(path).suffix.lower() not in suffixes:
            continue
        paths.add(path)
    return sorted(paths)


def _public_app_surfaces(workflow_ir: Mapping[str, Any]) -> List[Dict[str, Any]]:
    surfaces = []
    for surface in workflow_ir.get("app_surfaces") or []:
        if not isinstance(surface, Mapping):
            continue
        root = str(surface.get("root") or ".")
        if _is_fixture_path(root):
            continue
        surfaces.append(
            {
                key: surface.get(key)
                for key in ("id", "name", "type", "root", "manifest_paths", "entry_hints", "source_files", "test_files", "route_count")
                if key in surface
            }
        )
    return surfaces


def _public_components(components: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    public = []
    for component in components[:25]:
        raw_paths = [path for path in component.get("paths") or [] if isinstance(path, str)]
        paths = [path for path in raw_paths if not _is_fixture_path(path)]
        if raw_paths and not paths:
            continue
        public.append(
            {
                "id": component.get("id"),
                "name": component.get("name"),
                "file_count": component.get("file_count"),
                "routes": component.get("routes"),
                "exports": component.get("exports"),
                "paths": paths[:10],
            }
        )
    return public


def _component_index(components: Sequence[Mapping[str, Any]]) -> Dict[str, Mapping[str, Any]]:
    index: Dict[str, Mapping[str, Any]] = {}
    for component in components:
        for path in component.get("paths") or []:
            if isinstance(path, str):
                index[path] = component
    return index


def _component_refs(path: str, component_index: Mapping[str, Mapping[str, Any]]) -> List[str]:
    component = component_index.get(path)
    if not component:
        return []
    refs = [str(component.get("id") or "")]
    refs.extend(str(item) for item in component.get("app_surfaces") or [])
    return [ref for ref in refs if ref]


def _surface_refs(surface: Mapping[str, Any]) -> List[str]:
    refs: List[str] = []
    refs.extend(str(path) for path in surface.get("manifest_paths") or [] if path)
    for hint in surface.get("entry_hints") or []:
        if isinstance(hint, Mapping) and hint.get("path"):
            refs.append(str(hint["path"]))
    return _dedupe(refs)


def _fact_refs(fact: Mapping[str, Any], attributes: Mapping[str, Any]) -> List[str]:
    refs = [str(fact.get("id") or "")]
    for evidence in fact.get("evidence") or []:
        if isinstance(evidence, Mapping) and evidence.get("path"):
            refs.append(_line_ref(str(evidence["path"]), evidence.get("line")))
    path = _fact_path(fact, attributes)
    if path:
        refs.append(path)
    return _dedupe(refs)


def _fact_path(fact: Mapping[str, Any], attributes: Mapping[str, Any]) -> str:
    for value in (attributes.get("file"), attributes.get("path")):
        if isinstance(value, str) and value and not value.startswith("/"):
            return value
    for evidence in fact.get("evidence") or []:
        if isinstance(evidence, Mapping) and isinstance(evidence.get("path"), str):
            return str(evidence["path"])
    return ""


def _route_methods(attributes: Mapping[str, Any]) -> List[str]:
    methods = attributes.get("methods")
    if isinstance(methods, str):
        return [methods.upper()]
    if isinstance(methods, Sequence):
        return [str(method).upper() for method in methods if method]
    method = attributes.get("method")
    return [str(method).upper()] if method else []


def _projection_warnings(workflow_ir: Mapping[str, Any], detected_count: int, returned_count: int) -> List[str]:
    warnings = [
        "Starter map built from runtime entrypoints. The calling LLM can refine it into deeper journeys with the projection contract.",
    ]
    summary = workflow_ir.get("summary") if isinstance(workflow_ir.get("summary"), Mapping) else {}
    raw_nodes = int(summary.get("nodes") or 0)
    if raw_nodes and returned_count < raw_nodes:
        warnings.append(
            f"Collapsed {raw_nodes} raw graph nodes into {returned_count} behavior journeys."
        )
    if detected_count > returned_count:
        warnings.append(f"Canvas journeys truncated from {detected_count} to {returned_count}.")
    return warnings


def _api_action_text(method: str, path: str) -> str:
    actions = {
        "/api/canvas": "Return the behavior canvas for the workspace",
        "/api/changes": "Record a pending canvas change request",
        "/api/context": "Return workspace and assistant context",
        "/api/graph": "Return the raw indexed graph for tooling",
        "/api/pending": "List pending canvas change requests",
        "/api/reindex": "Re-index the workspace",
        "/api/status": "Update a pending request status",
    }
    return actions.get(path, f"Handle the {method} API request")


def _cli_action_text(name: str, help_text: str) -> str:
    actions = {
        "apply-query": "Validate and apply a projected canvas query",
        "index": "Index the workspace into workflow data",
        "pending": "List pending canvas change requests",
        "start": "Choose the workspace and start the local canvas server",
        "status": "Update a pending request status",
    }
    return actions.get(name, _sentence(help_text or "Run the command handler"))


def _surface_title(name: str, surface_type: str) -> str:
    label = _human_title(name)
    if surface_type == "web":
        return f"{label} web app"
    if surface_type == "mobile":
        return f"{label} mobile app"
    if surface_type == "backend":
        return f"{label} backend service"
    return f"{label} package"


def _surface_entry(name: str, surface_type: str) -> str:
    label = _human_title(name).lower()
    if surface_type == "web":
        return f"Someone opens the {label} web app"
    if surface_type == "mobile":
        return f"Someone opens the {label} mobile app"
    if surface_type == "backend":
        return f"The {label} backend receives work"
    return f"Someone uses the {label} package"


def _surface_action(surface: Mapping[str, Any]) -> str:
    hints = surface.get("entry_hints") or []
    if hints and isinstance(hints[0], Mapping) and hints[0].get("detail"):
        return f"Use {hints[0]['detail']}"
    surface_type = str(surface.get("type") or "package")
    if surface_type == "web":
        return "Load the browser interface"
    if surface_type == "mobile":
        return "Load the mobile interface"
    if surface_type == "backend":
        return "Run the service entrypoint"
    return "Run the package entrypoint"


def _request_entry(method: str, path: str) -> str:
    if method == "ANY":
        return f"Someone opens {path}"
    return f"A {method} request hits {path}"


def _workspace_root(workflow_ir: Mapping[str, Any]) -> Optional[Path]:
    workspace = workflow_ir.get("workspace")
    if isinstance(workspace, Mapping) and isinstance(workspace.get("root"), str):
        return Path(str(workspace["root"]))
    return None


def _parent_path(path: str) -> str:
    parent = PurePosixPath(path).parent.as_posix()
    return "." if parent in {"", "."} else parent


def _line_ref(path: str, line: Any) -> str:
    if not path:
        return ""
    try:
        line_int = int(line)
    except (TypeError, ValueError):
        line_int = 0
    return f"{path}:{line_int}" if line_int > 0 else path


def _safe_read(path: Path) -> str:
    try:
        if path.stat().st_size > 1_000_000:
            return ""
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _is_fixture_path(path: str) -> bool:
    if not path:
        return False
    parts = {part.lower() for part in PurePosixPath(path).parts}
    return bool(parts.intersection(FIXTURE_PARTS))


def _dedupe(values: Iterable[str]) -> List[str]:
    seen: set[str] = set()
    result = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _stable_id(value: str) -> str:
    head, _, tail = value.partition(":")
    return f"{head}:{_slug(tail or value)}"


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_.:/-]+", "-", str(value).strip().lower()).strip("-")
    cleaned = cleaned.replace("/", "-").replace(":", "-")
    return cleaned[:96] or "item"


def _human_title(value: str) -> str:
    text = re.sub(r"[_:-]+", " ", str(value)).replace("/", " ")
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)
    text = re.sub(r"\s+", " ", text).strip()
    return _sentence(text or "Your app")


def _sentence(value: str) -> str:
    text = str(value).strip()
    return text[:1].upper() + text[1:] if text else text
