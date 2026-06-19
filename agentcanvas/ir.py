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
STATE_DIR_NAME = ".agentcanvas"
PENDING_DIR_NAME = "pending"


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


def load_ir(workspace: str | Path) -> Dict[str, Any]:
    _, ir_path, _ = state_paths(workspace)
    with ir_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


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
        f"- Created: {record['created_at']}",
        f"- Workspace: {record['workspace']}",
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
        "Apply this request only after checking the current workspace state. "
        "Prefer a small, reviewable change and update this pending item when done.",
        "",
    ]
    return "\n".join(lines)


def write_pending_change(
    workspace: str | Path,
    change: Dict[str, Any],
    workflow_ir: Dict[str, Any] | None = None,
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

    atomic_write_json(json_path, record)
    atomic_write_text(markdown_path, _markdown_for_pending(record))

    return {
        **record,
        "json_path": str(json_path),
        "markdown_path": str(markdown_path),
    }
