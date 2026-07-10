"""Workflow IR and pending-change helpers for AgentCanvas."""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from agentcanvas.bootstrap import render_bootstrap_prompt
from agentcanvas.lifecycle import (
    DONE,
    IMPLEMENTED,
    IN_PROGRESS,
    NEEDS_INPUT,
    PENDING,
    PENDING_STATUSES,
    VERIFIED,
    transition_record,
)
from agentcanvas.workspace_lock import WorkspaceLockBusy, workspace_write_lock

SCHEMA = "agentcanvas.workflow.v1"
IR_FILENAME = "workflow.ir.json"
CANVAS_IR_FILENAME = "canvas.ir.json"
CANVAS_V2_SCHEMA = "agentcanvas.canvas.v2"
STATE_DIR_NAME = ".agentcanvas"
PENDING_DIR_NAME = "pending"
CONVERSATION_SUFFIX = ".conversation.jsonl"
CANVAS_MAP_HANDOFF_SCHEMA = "agentcanvas.canvas_map_handoff.v1"
MAP_HEALTH_SCHEMA = "agentcanvas.map_health.v1"


class PendingFileStatus(str, Enum):
    UNREADABLE = "unreadable"


class PendingRecordSource(str, Enum):
    AGENTCANVAS = "agentcanvas"


class PendingRecordKind(str, Enum):
    GRAPH_EDIT = "graph_edit"


class ConversationRole(str, Enum):
    AGENT = "agent"
    USER = "user"


class ConversationTurnKind(str, Enum):
    QUESTION = "question"
    ANSWER = "answer"
    NOTE = "note"


class MapFreshnessStatus(str, Enum):
    UNKNOWN = "unknown"
    STALE = "stale"
    FRESH = "fresh"


class MapHealthStatus(str, Enum):
    READY = "ready"
    MISSING_WORKFLOW_IR = "missing_workflow_ir"
    MISSING_CANVAS_IR = "missing_canvas_ir"
    UNREADABLE_CANVAS_IR = "unreadable_canvas_ir"
    STALE_CANVAS_IR = "stale_canvas_ir"
    UNKNOWN_CANVAS_FRESHNESS = "unknown_canvas_freshness"


class MapHealthReason(str, Enum):
    MISSING = "missing"
    INVALID_JSON = "invalid_json"
    INVALID_SHAPE = "invalid_shape"
    UNREADABLE = "unreadable"


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
    root = resolve_workspace(workspace)
    ensure_state_dirs(root)
    path = canvas_ir_path(root)
    try:
        with workspace_write_lock(root, writer="save-canvas-ir"):
            atomic_write_json(path, canvas_ir)
    except WorkspaceLockBusy as exc:
        raise ValueError(str(exc))
    return path


def load_ir(workspace: str | Path) -> Dict[str, Any]:
    _, ir_path, _ = state_paths(workspace)
    with ir_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_canvas_ir(workspace: str | Path) -> Dict[str, Any]:
    path = canvas_ir_path(workspace)
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def build_bootstrap_prompt(workspace: str | Path, *, agent: str | None = None) -> str:
    """Return copyable AgentCanvas bootstrap instructions."""

    root = resolve_workspace(workspace)
    return render_bootstrap_prompt(
        workspace=root,
        agent_label=agent,
        workflow_relative_path=f"{STATE_DIR_NAME}/{IR_FILENAME}",
        canvas_relative_path=f"{STATE_DIR_NAME}/{CANVAS_IR_FILENAME}",
        canvas_path=canvas_ir_path(root),
    )


def build_canvas_map_instruction(workspace: str | Path) -> str:
    """Return compatibility copy for missing-canvas handoffs."""

    return build_bootstrap_prompt(workspace)


def canvas_map_handoff(workspace: str | Path) -> Dict[str, Any]:
    """Return canvas-map readability plus the instruction needed to repair it."""

    root = resolve_workspace(workspace)
    output_path = canvas_ir_path(root)
    readable = False
    reason = None
    try:
        payload = load_canvas_ir(root)
    except FileNotFoundError:
        reason = MapHealthReason.MISSING.value
    except json.JSONDecodeError:
        reason = MapHealthReason.INVALID_JSON.value
    except OSError:
        reason = MapHealthReason.UNREADABLE.value
    else:
        readable = isinstance(payload, dict)
        if not readable:
            reason = MapHealthReason.INVALID_SHAPE.value

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
    canvas_payload: Optional[Dict[str, Any]] = None
    canvas_reason = MapHealthReason.MISSING.value if not canvas_exists else None
    canvas_error = None
    if canvas_exists:
        try:
            with canvas_path.open("r", encoding="utf-8") as handle:
                raw_canvas_payload = json.load(handle)
        except json.JSONDecodeError as exc:
            canvas_reason = MapHealthReason.INVALID_JSON.value
            canvas_error = str(exc)
        except OSError as exc:
            canvas_reason = MapHealthReason.UNREADABLE.value
            canvas_error = str(exc)
        else:
            canvas_readable = isinstance(raw_canvas_payload, dict)
            if not canvas_readable:
                canvas_reason = MapHealthReason.INVALID_SHAPE.value
            else:
                canvas_payload = raw_canvas_payload

    stale = None
    freshness_status = MapFreshnessStatus.UNKNOWN.value
    freshness_reason = None
    evidence_status = None
    if workflow_exists and canvas_exists:
        if isinstance(canvas_payload, dict) and canvas_payload.get("schema") == CANVAS_V2_SCHEMA:
            try:
                from agentcanvas.canvas_v2.evidence import compare_canvas_with_current_workflow_evidence

                evidence_status = compare_canvas_with_current_workflow_evidence(canvas_payload, root)
            except (OSError, ValueError) as exc:
                freshness_reason = f"Could not compare workflow evidence: {exc}"
            else:
                stale = evidence_status.get("stale")
                status_value = evidence_status.get("status")
                freshness_status = status_value if isinstance(status_value, str) else MapFreshnessStatus.UNKNOWN.value
                reasons = evidence_status.get("reasons")
                if isinstance(reasons, list) and reasons:
                    freshness_reason = "; ".join(str(reason) for reason in reasons)
        else:
            try:
                workflow_mtime = workflow_path.stat().st_mtime
                canvas_mtime = canvas_path.stat().st_mtime
            except OSError as exc:
                freshness_reason = f"Could not compare file times: {exc}"
            else:
                stale = canvas_mtime < workflow_mtime
                freshness_status = MapFreshnessStatus.STALE.value if stale else MapFreshnessStatus.FRESH.value
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

    status = MapHealthStatus.READY.value
    if not workflow_exists:
        status = MapHealthStatus.MISSING_WORKFLOW_IR.value
    elif not canvas_exists:
        status = MapHealthStatus.MISSING_CANVAS_IR.value
    elif not canvas_readable:
        status = MapHealthStatus.UNREADABLE_CANVAS_IR.value
    elif stale:
        status = MapHealthStatus.STALE_CANVAS_IR.value
    elif stale is None:
        status = MapHealthStatus.UNKNOWN_CANVAS_FRESHNESS.value

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
            "evidence": evidence_status,
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
        "ready": status == MapHealthStatus.READY.value,
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
    elif health["status"] == MapHealthStatus.MISSING_WORKFLOW_IR.value:
        lead = "Map is not ready yet: workflow evidence has not been created."
    elif health["status"] == MapHealthStatus.MISSING_CANVAS_IR.value:
        lead = "Map is not ready yet: the canvas map has not been created."
    elif health["status"] == MapHealthStatus.UNREADABLE_CANVAS_IR.value:
        lead = "Map needs attention: the canvas map file exists, but AgentCanvas cannot read it."
    elif health["status"] == MapHealthStatus.STALE_CANVAS_IR.value:
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
        MapHealthReason.INVALID_JSON.value: "not valid JSON",
        MapHealthReason.INVALID_SHAPE.value: "not a JSON object",
        MapHealthReason.UNREADABLE.value: "not readable",
        MapHealthReason.MISSING.value: "missing",
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


def list_pending(
    workspace: str | Path,
    *,
    summary: bool = False,
    status: Optional[str] = None,
    session_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    _, _, pending_dir = state_paths(workspace)
    if not pending_dir.exists():
        return []

    items: List[Dict[str, Any]] = []
    for json_path in sorted(pending_dir.glob("*.json")):
        item = _read_pending_file(json_path)
        if status and item.get("status") != status:
            continue
        if session_id and not _pending_matches_session(item, session_id):
            continue
        if summary:
            item = pending_summary(item)
        items.append(item)

    return sorted(items, key=lambda item: item.get("created_at", ""), reverse=True)


def get_pending_request(
    workspace: str | Path,
    pending_id: str,
    *,
    since: Optional[str] = None,
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    _, _, pending_dir = state_paths(workspace)
    json_path = _resolve_pending_json_path(pending_dir, pending_id)
    item = _read_pending_file(json_path)
    if session_id and not _pending_matches_session(item, session_id):
        raise FileNotFoundError(f"pending request not found for session: {pending_id}")
    item["conversation"] = read_pending_conversation(json_path, since=since)
    return item


def pending_summary(item: Dict[str, Any]) -> Dict[str, Any]:
    summary_keys = [
        "id",
        "title",
        "summary",
        "status",
        "note",
        "error",
        "workspace",
        "sessionId",
        "session_id",
        "changeId",
        "change_id",
        "clientChangeId",
        "created_at",
        "updated_at",
        "json_path",
        "markdown_path",
        "refs",
        "orphaned_refs",
        "status_history",
        "conversation_summary",
    ]
    summary = {key: item[key] for key in summary_keys if key in item}
    if isinstance(summary.get("status_history"), list):
        summary["status_history"] = summary["status_history"][-20:]
    else:
        summary["status_history"] = [
            {
                "status": item.get("status", PENDING),
                "updated_at": item.get("updated_at") or item.get("created_at"),
                "note": item.get("note"),
            }
        ]
    if "changeId" not in summary and isinstance(item.get("change"), dict):
        change = item["change"]
        for key in ("changeId", "clientChangeId", "change_id"):
            if isinstance(change.get(key), str):
                summary["changeId"] = change[key]
                break
    summary.setdefault("id", item.get("id"))
    summary.setdefault("title", item.get("title") or item.get("id"))
    summary.setdefault("status", item.get("status", PENDING))
    return summary


def _pending_record_for_write(record: Dict[str, Any]) -> Dict[str, Any]:
    clean = dict(record)
    clean.pop("json_path", None)
    clean.pop("markdown_path", None)
    clean.pop("conversation", None)
    return clean


def _pending_matches_session(item: Dict[str, Any], session_id: str) -> bool:
    # Prefer the canonical key when both spellings are present so a stale alias
    # cannot broaden access to another session.
    owner = item.get("sessionId")
    if owner is None:
        owner = item.get("session_id")
    return owner == session_id


def _resolve_pending_json_path(pending_dir: Path, pending_id: str) -> Path:
    json_path = pending_dir / f"{pending_id}.json"
    if json_path.exists():
        return json_path
    matches = sorted(pending_dir.glob(f"*{pending_id}*.json"))
    if len(matches) == 1:
        return matches[0]
    raise FileNotFoundError(f"pending request not found: {pending_id}")


def _read_pending_file(json_path: Path) -> Dict[str, Any]:
    try:
        with json_path.open("r", encoding="utf-8") as handle:
            item = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        item = {
            "id": json_path.stem,
            "title": json_path.stem,
            "status": PendingFileStatus.UNREADABLE.value,
            "error": str(exc),
        }

    md_path = json_path.with_suffix(".md")
    if isinstance(item, dict):
        from agentcanvas.canvas_v2.pending_refs import normalize_pending_record

        item = normalize_pending_record(item)
    else:
        item = {
            "id": json_path.stem,
            "title": json_path.stem,
            "status": PendingFileStatus.UNREADABLE.value,
        }
    item.setdefault("id", json_path.stem)
    item.setdefault("title", item["id"])
    item.setdefault("status", PENDING)
    item["json_path"] = str(json_path)
    item["markdown_path"] = str(md_path) if md_path.exists() else None
    item["conversation_summary"] = _conversation_summary(conversation_path_for_json(json_path))
    return item


def conversation_path_for_json(json_path: Path) -> Path:
    return json_path.with_suffix(CONVERSATION_SUFFIX)


def read_pending_conversation(
    json_path: Path,
    *,
    since: Optional[str] = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    return _read_conversation_file(conversation_path_for_json(json_path), since=since, limit=limit)


def _read_conversation_file(
    path: Path,
    *,
    since: Optional[str] = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    turns: List[Dict[str, Any]] = []
    seen_since = since is None
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    turn = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(turn, dict):
                    continue
                if not seen_since:
                    if since in {str(turn.get("id")), str(turn.get("at"))}:
                        seen_since = True
                    continue
                turns.append(turn)
    except OSError:
        return []
    return turns[-max(1, int(limit)) :]


def _conversation_summary(path: Path) -> Dict[str, Any]:
    turns = _read_conversation_file(path, limit=1000000)
    unanswered = None
    for turn in reversed(turns):
        if (
            turn.get("role") == ConversationRole.USER.value
            and turn.get("kind") == ConversationTurnKind.ANSWER.value
        ):
            break
        if (
            turn.get("role") == ConversationRole.AGENT.value
            and turn.get("kind") == ConversationTurnKind.QUESTION.value
        ):
            unanswered = {
                "id": turn.get("id"),
                "text": turn.get("text"),
                "at": turn.get("at"),
            }
            break
    last = turns[-1] if turns else {}
    return {
        "turns": len(turns),
        "last_role": last.get("role"),
        "last_kind": last.get("kind"),
        "last_at": last.get("at"),
        "unanswered_question": unanswered,
    }


def _first_text(values: Iterable[Any], fallback: str) -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return fallback


def _markdown_for_pending(
    record: Dict[str, Any],
    conversation: Optional[List[Dict[str, Any]]] = None,
) -> str:
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
        "If this is a canvas-authoring request, do not hand-edit "
        "`.agentcanvas/canvas.ir.json`. Apply a canvas v2 operation batch with "
        "`agentcanvas canvas apply --base-revision <revision> --input <ops.json>` "
        "so revision checks, history, and pending refs stay intact. The map "
        "instruction is:",
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
        f"agentcanvas status --workspace {json.dumps(record.get('workspace') or '.')} {json.dumps(record['id'])} --status {IN_PROGRESS}",
        "```",
        "",
        "If you need the user, mark it clearly:",
        "",
        "```bash",
        f"agentcanvas status --workspace {json.dumps(record.get('workspace') or '.')} {json.dumps(record['id'])} --status {NEEDS_INPUT} --note \"What I need from you...\"",
        "```",
        "",
        "When finished, mark it implemented, then verified with evidence, then "
        "done. Only run `agentcanvas index` first if you changed source code:",
        "",
        "```bash",
        f"# Source-code changes only: agentcanvas index --workspace {json.dumps(record.get('workspace') or '.')}",
        f"agentcanvas status --workspace {json.dumps(record.get('workspace') or '.')} {json.dumps(record['id'])} --status {IMPLEMENTED} --note \"Implemented.\"",
        f"agentcanvas status --workspace {json.dumps(record.get('workspace') or '.')} {json.dumps(record['id'])} --status {VERIFIED} --note \"Verified.\" --evidence-check \"<command or smoke test>\" --evidence-result \"passed\" --evidence-actor \"<agent name>\"",
        f"agentcanvas status --workspace {json.dumps(record.get('workspace') or '.')} {json.dumps(record['id'])} --status {DONE} --note \"Done.\"",
        "```",
        "",
    ]
    conversation = conversation or []
    if conversation:
        lines.extend(["## Conversation", ""])
        for turn in conversation[-10:]:
            role = turn.get("role", ConversationRole.AGENT.value)
            kind = turn.get("kind", ConversationTurnKind.NOTE.value)
            text = str(turn.get("text") or "").strip()
            at = turn.get("at") or "unknown time"
            lines.extend([f"- **{role} {kind}** ({at}): {text}", ""])
    return "\n".join(lines)


def append_pending_conversation(
    workspace: str | Path,
    pending_id: str,
    *,
    role: str,
    kind: str,
    text: str,
    actor: str = "agentcanvas",
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    try:
        role = ConversationRole(str(role).strip().lower()).value
    except ValueError:
        raise ValueError("conversation role must be agent or user")
    try:
        kind = ConversationTurnKind(str(kind).strip().lower()).value
    except ValueError:
        raise ValueError("conversation kind must be question, answer, or note")
    if not isinstance(text, str) or not text.strip():
        raise ValueError("conversation text is required")

    root = resolve_workspace(workspace)
    with workspace_write_lock(root, writer="pending-conversation"):
        _, _, pending_dir = state_paths(root)
        json_path = _resolve_pending_json_path(pending_dir, pending_id)
        record = _read_pending_file(json_path)
        if session_id and not _pending_matches_session(record, session_id):
            raise FileNotFoundError(f"pending request not found for session: {pending_id}")
        turn = {
            "id": uuid.uuid4().hex,
            "at": now_utc(),
            "role": role,
            "kind": kind,
            "text": text.strip(),
        }
        conversation_path = conversation_path_for_json(json_path)
        conversation_path.parent.mkdir(parents=True, exist_ok=True)

        if (
            role == ConversationRole.AGENT.value
            and kind == ConversationTurnKind.QUESTION.value
        ):
            record = transition_record(
                record,
                NEEDS_INPUT,
                at=turn["at"],
                actor=actor,
                note=text.strip(),
                enforce_transitions=True,
            )
        elif (
            role == ConversationRole.USER.value
            and kind == ConversationTurnKind.ANSWER.value
        ):
            if record.get("status") != NEEDS_INPUT:
                raise ValueError("answers require a pending request in needs_input status")
            record = transition_record(
                record,
                IN_PROGRESS,
                at=turn["at"],
                actor=actor,
                note="User answered in AgentCanvas.",
                enforce_transitions=True,
            )

        with conversation_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(turn, sort_keys=True) + "\n")

        conversation = read_pending_conversation(json_path, limit=1000000)
        record["conversation_summary"] = _conversation_summary(conversation_path)
        from agentcanvas.canvas_v2.pending_refs import normalize_pending_record

        record = normalize_pending_record(record)
        record["conversation_summary"] = _conversation_summary(conversation_path)
        atomic_write_json(json_path, _pending_record_for_write(record))
        markdown_path = json_path.with_suffix(".md")
        if markdown_path.exists():
            atomic_write_text(markdown_path, _markdown_for_pending(record, conversation))

    return {
        **record,
        "json_path": str(json_path),
        "markdown_path": str(markdown_path) if markdown_path.exists() else None,
        "conversation": conversation,
    }


def write_pending_change(
    workspace: str | Path,
    change: Dict[str, Any],
    workflow_ir: Dict[str, Any] | None = None,
    session_id: str | None = None,
) -> Dict[str, Any]:
    if not isinstance(change, dict):
        raise ValueError("change payload must be a JSON object")

    root = resolve_workspace(workspace)
    with workspace_write_lock(root, writer="pending-create"):
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
            "status": PENDING,
            "created_at": created_at,
            "workspace": str(root),
            "source": PendingRecordSource.AGENTCANVAS.value,
            "kind": PendingRecordKind.GRAPH_EDIT.value,
            "change": change,
            "graph": graph_snapshot,
        }
        for key in ("changeId", "clientChangeId", "change_id"):
            if isinstance(change.get(key), str):
                record[key] = change[key]
        if session_id:
            record["sessionId"] = session_id
        from agentcanvas.canvas_v2.pending_refs import normalize_pending_record

        record = normalize_pending_record(record)
        record["conversation_summary"] = _conversation_summary(conversation_path_for_json(json_path))

        atomic_write_json(json_path, _pending_record_for_write(record))
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
    *,
    actor: str = "agentcanvas",
    evidence: Dict[str, Any] | None = None,
    enforce_transitions: bool = False,
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    if status not in PENDING_STATUSES:
        allowed = ", ".join(sorted(PENDING_STATUSES))
        raise ValueError(f"status must be one of: {allowed}")

    root = resolve_workspace(workspace)
    with workspace_write_lock(root, writer="pending-status"):
        _, _, pending_dir = state_paths(root)
        json_path = pending_dir / f"{pending_id}.json"
        if not json_path.exists():
            matches = sorted(pending_dir.glob(f"*{pending_id}*.json"))
            if len(matches) == 1:
                json_path = matches[0]
            else:
                raise FileNotFoundError(f"pending request not found: {pending_id}")

        with json_path.open("r", encoding="utf-8") as handle:
            record = json.load(handle)
        if session_id and not _pending_matches_session(record, session_id):
            raise FileNotFoundError(f"pending request not found for session: {pending_id}")

        record = transition_record(
            record,
            status,
            at=now_utc(),
            actor=actor,
            note=note,
            evidence=evidence,
            enforce_transitions=enforce_transitions,
        )
        from agentcanvas.canvas_v2.pending_refs import normalize_pending_record

        record = normalize_pending_record(record)

        atomic_write_json(json_path, _pending_record_for_write(record))
        markdown_path = json_path.with_suffix(".md")
        if markdown_path.exists():
            atomic_write_text(markdown_path, _markdown_for_pending(record, read_pending_conversation(json_path)))

    return {
        **record,
        "json_path": str(json_path),
        "markdown_path": str(markdown_path) if markdown_path.exists() else None,
    }
