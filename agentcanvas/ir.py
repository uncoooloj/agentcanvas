"""Workflow IR and pending-change helpers for AgentCanvas."""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

SCHEMA = "agentcanvas.workflow.v1"
IR_FILENAME = "workflow.ir.json"
CANVAS_IR_FILENAME = "canvas.ir.json"
STATE_DIR_NAME = ".agentcanvas"
PENDING_DIR_NAME = "pending"
CANVAS_MAP_HANDOFF_SCHEMA = "agentcanvas.canvas_map_handoff.v1"
MAP_HEALTH_SCHEMA = "agentcanvas.map_health.v1"
PENDING_STATUSES = {
    "pending",
    "sent",
    "in_progress",
    "done",
    "needs_input",
    "blocked",
}


def now_utc() -> str:
    """Return a compact UTC timestamp that is easy to read in generated files."""

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def resolve_workspace(workspace: str | Path) -> Path:
    return Path(workspace).expanduser().resolve()


def state_paths(workspace: str | Path) -> Tuple[Path, Path, Path]:
    root = resolve_workspace(workspace)
    state_dir = root / STATE_DIR_NAME
    return state_dir, state_dir / IR_FILENAME, state_dir / PENDING_DIR_NAME


def canvas_ir_path(workspace: str | Path) -> Path:
    root = resolve_workspace(workspace)
    return root / STATE_DIR_NAME / CANVAS_IR_FILENAME


def ensure_state_dirs(workspace: str | Path) -> Tuple[Path, Path, Path]:
    state_dir, ir_path, pending_dir = state_paths(workspace)
    state_dir.mkdir(parents=True, exist_ok=True)
    pending_dir.mkdir(parents=True, exist_ok=True)
    return state_dir, ir_path, pending_dir


def atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        tmp_path.write_text(content, encoding="utf-8")
        tmp_path.replace(path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    atomic_write_text(path, text)


def save_ir(workspace: str | Path, workflow_ir: Dict[str, Any]) -> Path:
    _, ir_path, _ = ensure_state_dirs(workspace)
    atomic_write_json(ir_path, workflow_ir)
    return ir_path


def save_canvas_ir(workspace: str | Path, canvas_ir: Dict[str, Any]) -> Path:
    ensure_state_dirs(workspace)
    path = canvas_ir_path(workspace)
    atomic_write_json(path, canvas_ir)
    return path


def load_ir(workspace: str | Path) -> Dict[str, Any]:
    _, ir_path, _ = state_paths(workspace)
    with ir_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_canvas_ir(workspace: str | Path) -> Dict[str, Any]:
    path = canvas_ir_path(workspace)
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def build_canvas_map_instruction(workspace: str | Path) -> str:
    """Return copyable instructions for authoring a missing canvas map."""

    root = resolve_workspace(workspace)
    relative_output = f"{STATE_DIR_NAME}/{CANVAS_IR_FILENAME}"
    output_path = canvas_ir_path(root)
    return (
        f"Read the workspace at {root}. If there is no readable canvas map, "
        "refresh or author the AgentCanvas behavior map from the current "
        f"workspace evidence and write the output to {output_path} "
        f"(`{relative_output}`). Describe user-visible behavior in plain "
        "English, keep the map grounded in the files you inspected, and ask "
        "clarifying questions before executing any user-requested edits when "
        "scope, expected behavior, or missing details are unclear."
    )


def canvas_map_handoff(workspace: str | Path) -> Dict[str, Any]:
    """Return canvas-map readability plus the instruction needed to repair it."""

    root = resolve_workspace(workspace)
    output_path = canvas_ir_path(root)
    readable = False
    reason = None
    try:
        payload = load_canvas_ir(root)
    except FileNotFoundError:
        reason = "missing"
    except json.JSONDecodeError:
        reason = "invalid_json"
    except OSError:
        reason = "unreadable"
    else:
        readable = isinstance(payload, dict)
        if not readable:
            reason = "invalid_shape"

    return {
        "schema": CANVAS_MAP_HANDOFF_SCHEMA,
        "readable": readable,
        "needsAuthoring": not readable,
        "reason": reason,
        "workspacePath": str(root),
        "outputPath": str(output_path),
        "relativeOutputPath": f"{STATE_DIR_NAME}/{CANVAS_IR_FILENAME}",
        "instruction": None if readable else build_canvas_map_instruction(root),
    }


def map_health(workspace: str | Path) -> Dict[str, Any]:
    """Return a read-only health summary for the workflow and canvas map files."""

    root = resolve_workspace(workspace)
    state_dir, workflow_path, pending_dir = state_paths(root)
    canvas_path = canvas_ir_path(root)

    workflow_exists = workflow_path.is_file()
    canvas_exists = canvas_path.is_file()
    canvas_readable = False
    canvas_reason = "missing" if not canvas_exists else None
    canvas_error = None
    if canvas_exists:
        try:
            with canvas_path.open("r", encoding="utf-8") as handle:
                canvas_payload = json.load(handle)
        except json.JSONDecodeError as exc:
            canvas_reason = "invalid_json"
            canvas_error = str(exc)
        except OSError as exc:
            canvas_reason = "unreadable"
            canvas_error = str(exc)
        else:
            canvas_readable = isinstance(canvas_payload, dict)
            if not canvas_readable:
                canvas_reason = "invalid_shape"

    stale = None
    freshness_status = "unknown"
    freshness_reason = None
    if workflow_exists and canvas_exists:
        try:
            workflow_mtime = workflow_path.stat().st_mtime
            canvas_mtime = canvas_path.stat().st_mtime
        except OSError as exc:
            freshness_reason = f"Could not compare file times: {exc}"
        else:
            stale = canvas_mtime < workflow_mtime
            freshness_status = "stale" if stale else "fresh"
    elif not workflow_exists:
        freshness_reason = "Workflow evidence is missing."
    else:
        freshness_reason = "Canvas map is missing."

    pending_exists = pending_dir.is_dir()
    pending_readable = pending_exists
    pending_error = None
    pending_file_count = 0
    pending_change_count = 0
    if pending_exists:
        try:
            pending_file_count = sum(1 for path in pending_dir.iterdir() if path.is_file())
            pending_change_count = len(list_pending(root))
        except OSError as exc:
            pending_readable = False
            pending_error = str(exc)

    status = "ready"
    if not workflow_exists:
        status = "missing_workflow_ir"
    elif not canvas_exists:
        status = "missing_canvas_ir"
    elif not canvas_readable:
        status = "unreadable_canvas_ir"
    elif stale:
        status = "stale_canvas_ir"

    health: Dict[str, Any] = {
        "schema": MAP_HEALTH_SCHEMA,
        "workspacePath": str(root),
        "stateDir": {
            "path": str(state_dir),
            "relativePath": STATE_DIR_NAME,
            "exists": state_dir.is_dir(),
        },
        "workflowIr": {
            "path": str(workflow_path),
            "relativePath": f"{STATE_DIR_NAME}/{IR_FILENAME}",
            "exists": workflow_exists,
        },
        "canvasIr": {
            "path": str(canvas_path),
            "relativePath": f"{STATE_DIR_NAME}/{CANVAS_IR_FILENAME}",
            "exists": canvas_exists,
            "readable": canvas_readable,
            "reason": canvas_reason,
            "error": canvas_error,
        },
        "freshness": {
            "status": freshness_status,
            "stale": stale,
            "reason": freshness_reason,
        },
        "pendingFiles": {
            "path": str(pending_dir),
            "relativePath": f"{STATE_DIR_NAME}/{PENDING_DIR_NAME}",
            "exists": pending_exists,
            "readable": pending_readable,
            "fileCount": pending_file_count,
            "changeCount": pending_change_count,
            "error": pending_error,
        },
        "status": status,
        "ready": status == "ready",
    }
    health["summary"] = map_health_summary_lines(health)
    return health


def map_health_summary_lines(health: Dict[str, Any]) -> List[str]:
    """Return the user-facing health summary in plain English."""

    workflow = health["workflowIr"]
    canvas = health["canvasIr"]
    freshness = health["freshness"]
    pending = health["pendingFiles"]

    if health["ready"]:
        lead = (
            "Map is ready: the workflow evidence and canvas map are present, "
            "the canvas is readable, and it matches the latest workflow evidence."
        )
    elif health["status"] == "missing_workflow_ir":
        lead = "Map is not ready yet: workflow evidence has not been created."
    elif health["status"] == "missing_canvas_ir":
        lead = "Map is not ready yet: the canvas map has not been created."
    elif health["status"] == "unreadable_canvas_ir":
        lead = "Map needs attention: the canvas map file exists, but AgentCanvas cannot read it."
    elif health["status"] == "stale_canvas_ir":
        lead = "Map needs attention: the canvas map is older than the workflow evidence."
    else:
        lead = "Map health could not be fully checked."

    lines = [lead]
    if workflow["exists"]:
        lines.append(
            f"Workflow evidence (workflow IR): found at {workflow['relativePath']}."
        )
    else:
        lines.append(
            f"Workflow evidence (workflow IR): missing from {workflow['relativePath']}."
        )

    if canvas["exists"] and canvas["readable"]:
        lines.append(f"Canvas map (canvas IR): found and readable at {canvas['relativePath']}.")
    elif canvas["exists"]:
        reason = _plain_health_reason(canvas.get("reason"))
        lines.append(
            f"Canvas map (canvas IR): found at {canvas['relativePath']}, but it is {reason}."
        )
    else:
        lines.append(f"Canvas map (canvas IR): missing from {canvas['relativePath']}.")

    if freshness["stale"] is True:
        lines.append("Freshness: canvas map is older than the workflow evidence.")
    elif freshness["stale"] is False:
        lines.append("Freshness: canvas map is current with the workflow evidence.")
    else:
        lines.append(f"Freshness: not checked yet because {freshness['reason']}")

    pending_location = f"{pending['relativePath']} ({pending['path']})"
    if pending["exists"] and pending["readable"]:
        lines.append(
            "Pending request files: "
            f"use {pending_location}; {pending['changeCount']} change request(s), "
            f"{pending['fileCount']} file(s)."
        )
    elif pending["exists"]:
        lines.append(
            f"Pending request files: {pending_location} exists, but AgentCanvas cannot read it."
        )
    else:
        lines.append(
            f"Pending request files: they will live in {pending_location} when requests exist."
        )
    return lines


def format_map_health(health: Dict[str, Any]) -> str:
    lines = [f"AgentCanvas map health for {health['workspacePath']}"]
    lines.extend(f"- {line}" for line in health["summary"])
    return "\n".join(lines)


def _plain_health_reason(reason: Any) -> str:
    return {
        "invalid_json": "not valid JSON",
        "invalid_shape": "not a JSON object",
        "unreadable": "not readable",
        "missing": "missing",
    }.get(reason, "not readable")


def summarize_ir(workflow_ir: Dict[str, Any]) -> Dict[str, Any]:
    summary = dict(workflow_ir.get("summary") or {})
    summary.setdefault("nodes", len(workflow_ir.get("nodes") or []))
    summary.setdefault("edges", len(workflow_ir.get("edges") or []))
    summary.setdefault("components", len(workflow_ir.get("components") or []))
    return summary


def slugify(value: str, fallback: str = "canvas-change") -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return slug[:64] or fallback


def list_pending(workspace: str | Path) -> List[Dict[str, Any]]:
    _, _, pending_dir = state_paths(workspace)
    if not pending_dir.exists():
        return []

    items: List[Dict[str, Any]] = []
    for json_path in sorted(pending_dir.glob("*.json")):
        try:
            with json_path.open("r", encoding="utf-8") as handle:
                item = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            item = {
                "id": json_path.stem,
                "title": json_path.stem,
                "status": "unreadable",
                "error": str(exc),
            }

        md_path = json_path.with_suffix(".md")
        item.setdefault("id", json_path.stem)
        item.setdefault("title", item["id"])
        item.setdefault("status", "pending")
        item["json_path"] = str(json_path)
        item["markdown_path"] = str(md_path) if md_path.exists() else None
        items.append(item)

    return sorted(items, key=lambda item: item.get("created_at", ""), reverse=True)


def _first_text(values: Iterable[Any], fallback: str) -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return fallback


def _markdown_for_pending(record: Dict[str, Any]) -> str:
    summary = _first_text(
        [
            record.get("summary"),
            (record.get("change") or {}).get("summary")
            if isinstance(record.get("change"), dict)
            else None,
        ],
        "Review the canvas edit JSON below and decide how to apply it.",
    )
    change_json = json.dumps(record.get("change") or {}, indent=2, sort_keys=True)

    lines = [
        f"# {record['title']}",
        "",
        f"- ID: {record['id']}",
        f"- Created: {record.get('created_at') or record.get('updated_at') or 'unknown time'}",
        f"- Workspace: {record.get('workspace') or 'unknown workspace'}",
        f"- Status: {record['status']}",
        "- Source: AgentCanvas local canvas",
        "",
        "## Summary",
        "",
        summary,
        "",
        "## Requested Canvas Edit",
        "",
        "```json",
        change_json,
        "```",
        "",
        "## Agent Handoff",
        "",
        "Read the current workspace state before acting. If anything about the "
        "request is unclear, ask the user a focused clarification question before "
        "moving into execution.",
        "",
        "If this is a canvas-authoring request, update "
        "`.agentcanvas/canvas.ir.json` so the browser reflects the new map. "
        "The map instruction is:",
        "",
        build_canvas_map_instruction(record.get("workspace") or "."),
        "",
        "Do not re-index after a canvas-only edit.",
        "",
        "If the user explicitly asked for a source-code implementation, patch the "
        "app code, run the relevant checks, then re-index so the evidence file "
        "matches the implementation.",
        "",
        "If you are already running while the user edits AgentCanvas, poll for "
        "ready requests with:",
        "",
        "```bash",
        f"agentcanvas pending --workspace {json.dumps(record.get('workspace') or '.')}",
        "```",
        "",
        "When you start this request, update its status:",
        "",
        "```bash",
        f"agentcanvas status --workspace {json.dumps(record.get('workspace') or '.')} {json.dumps(record['id'])} --status in_progress",
        "```",
        "",
        "If you need the user, mark it clearly:",
        "",
        "```bash",
        f"agentcanvas status --workspace {json.dumps(record.get('workspace') or '.')} {json.dumps(record['id'])} --status needs_input --note \"What I need from you...\"",
        "```",
        "",
        "When finished, mark it done. Only run `agentcanvas index` first if you "
        "changed source code:",
        "",
        "```bash",
        f"# Source-code changes only: agentcanvas index --workspace {json.dumps(record.get('workspace') or '.')}",
        f"agentcanvas status --workspace {json.dumps(record.get('workspace') or '.')} {json.dumps(record['id'])} --status done --note \"Implemented and verified.\"",
        "```",
        "",
    ]
    return "\n".join(lines)


def write_pending_change(
    workspace: str | Path,
    change: Dict[str, Any],
    workflow_ir: Dict[str, Any] | None = None,
    session_id: str | None = None,
) -> Dict[str, Any]:
    if not isinstance(change, dict):
        raise ValueError("change payload must be a JSON object")

    root = resolve_workspace(workspace)
    _, _, pending_dir = ensure_state_dirs(root)
    created_at = now_utc()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    title = _first_text(
        [change.get("title"), change.get("name"), change.get("summary")],
        "Canvas change request",
    )
    pending_id = f"{stamp}-{slugify(title)}-{uuid.uuid4().hex[:8]}"
    json_path = pending_dir / f"{pending_id}.json"
    markdown_path = pending_dir / f"{pending_id}.md"

    graph_snapshot = None
    if workflow_ir:
        graph_snapshot = {
            "schema": workflow_ir.get("schema"),
            "generated_at": workflow_ir.get("generated_at"),
            "summary": summarize_ir(workflow_ir),
        }

    record: Dict[str, Any] = {
        "id": pending_id,
        "title": title,
        "summary": _first_text([change.get("summary")], ""),
        "status": "pending",
        "created_at": created_at,
        "workspace": str(root),
        "source": "agentcanvas",
        "kind": "graph_edit",
        "change": change,
        "graph": graph_snapshot,
    }
    if session_id:
        record["sessionId"] = session_id

    atomic_write_json(json_path, record)
    atomic_write_text(markdown_path, _markdown_for_pending(record))

    return {
        **record,
        "json_path": str(json_path),
        "markdown_path": str(markdown_path),
    }


def update_pending_status(
    workspace: str | Path,
    pending_id: str,
    status: str,
    note: str | None = None,
) -> Dict[str, Any]:
    if status not in PENDING_STATUSES:
        allowed = ", ".join(sorted(PENDING_STATUSES))
        raise ValueError(f"status must be one of: {allowed}")

    _, _, pending_dir = state_paths(workspace)
    json_path = pending_dir / f"{pending_id}.json"
    if not json_path.exists():
        matches = sorted(pending_dir.glob(f"*{pending_id}*.json"))
        if len(matches) == 1:
            json_path = matches[0]
        else:
            raise FileNotFoundError(f"pending request not found: {pending_id}")

    with json_path.open("r", encoding="utf-8") as handle:
        record = json.load(handle)

    updated_at = now_utc()
    history = list(record.get("status_history") or [])
    history.append(
        {
            "status": status,
            "updated_at": updated_at,
            **({"note": note} if note else {}),
        }
    )
    record["status"] = status
    record["updated_at"] = updated_at
    record["status_history"] = history
    if note:
        record["note"] = note

    atomic_write_json(json_path, record)
    markdown_path = json_path.with_suffix(".md")
    if markdown_path.exists():
        atomic_write_text(markdown_path, _markdown_for_pending(record))

    return {
        **record,
        "json_path": str(json_path),
        "markdown_path": str(markdown_path) if markdown_path.exists() else None,
    }
