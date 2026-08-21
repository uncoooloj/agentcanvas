"""Durable progress state for AgentCanvas workspace mapping."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from .ir import STATE_DIR_NAME, atomic_write_json, now_utc, resolve_workspace, state_paths

PROGRESS_SCHEMA = "agentcanvas.progress.v1"
PROGRESS_FILENAME = "progress.json"
PROGRESS_STAGES = ("indexing", "surveying", "mapping_flows", "done")


class ProgressError(ValueError):
    """Structured progress validation or read error."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": False,
            "error": {
                "code": self.code,
                "message": self.message,
                "details": self.details,
            },
        }


def progress_path(workspace: str | Path) -> Path:
    state_dir, _ir_path, _pending_dir = state_paths(workspace)
    return state_dir / PROGRESS_FILENAME


def progress_relative_path() -> str:
    return f"{STATE_DIR_NAME}/{PROGRESS_FILENAME}"


def build_progress_payload(
    *,
    stage: Any,
    message: Any,
    current: Any = None,
    total: Any = None,
    updated_at: Optional[str] = None,
) -> Dict[str, Any]:
    stage_value = validate_stage(stage)
    message_value = validate_message(message)
    current_value = validate_count(current, "current")
    total_value = validate_count(total, "total")
    if (
        current_value is not None
        and total_value is not None
        and current_value > total_value
    ):
        raise ProgressError(
            "INVALID_PROGRESS_RANGE",
            "current cannot be greater than total",
            details={"current": current_value, "total": total_value},
        )

    timestamp = updated_at or now_utc()
    if not isinstance(timestamp, str) or not timestamp.strip():
        raise ProgressError(
            "INVALID_PROGRESS_TIMESTAMP",
            "updated_at must be a non-empty string",
            details={"updated_at": timestamp},
        )

    payload: Dict[str, Any] = {
        "schema": PROGRESS_SCHEMA,
        "stage": stage_value,
        "message": message_value,
        "updated_at": timestamp.strip(),
    }
    if current_value is not None:
        payload["current"] = current_value
    if total_value is not None:
        payload["total"] = total_value
    return payload


def validate_stage(stage: Any) -> str:
    if not isinstance(stage, str) or not stage.strip():
        raise ProgressError(
            "INVALID_PROGRESS_STAGE",
            "stage must be one of: " + ", ".join(PROGRESS_STAGES),
            details={"stage": stage, "allowed": list(PROGRESS_STAGES)},
        )
    stage_value = stage.strip()
    if stage_value not in PROGRESS_STAGES:
        raise ProgressError(
            "INVALID_PROGRESS_STAGE",
            "stage must be one of: " + ", ".join(PROGRESS_STAGES),
            details={"stage": stage_value, "allowed": list(PROGRESS_STAGES)},
        )
    return stage_value


def validate_message(message: Any) -> str:
    if not isinstance(message, str) or not message.strip():
        raise ProgressError(
            "INVALID_PROGRESS_MESSAGE",
            "message must be a non-empty string",
            details={"message": message},
        )
    return message.strip()


def validate_count(value: Any, field: str) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool):
        raise invalid_count_error(value, field)
    if isinstance(value, int):
        count = value
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            raise invalid_count_error(value, field)
        try:
            count = int(text, 10)
        except ValueError as exc:
            raise invalid_count_error(value, field) from exc
    else:
        raise invalid_count_error(value, field)

    if count < 0:
        raise invalid_count_error(value, field)
    return count


def invalid_count_error(value: Any, field: str) -> ProgressError:
    return ProgressError(
        "INVALID_PROGRESS_COUNT",
        f"{field} must be a non-negative integer",
        details={"field": field, "value": value},
    )


def write_progress(
    workspace: str | Path,
    *,
    stage: Any,
    message: Any,
    current: Any = None,
    total: Any = None,
) -> Dict[str, Any]:
    root = resolve_workspace(workspace)
    payload = build_progress_payload(
        stage=stage,
        message=message,
        current=current,
        total=total,
    )
    atomic_write_json(progress_path(root), payload)
    return payload


def load_progress(workspace: str | Path) -> Dict[str, Any]:
    path = progress_path(workspace)
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except FileNotFoundError:
        raise
    except json.JSONDecodeError as exc:
        raise ProgressError(
            "INVALID_PROGRESS_JSON",
            "progress.json must be valid JSON",
            details={"path": str(path), "reason": str(exc)},
        ) from exc
    except OSError as exc:
        raise ProgressError(
            "PROGRESS_NOT_READABLE",
            "progress.json could not be read",
            details={"path": str(path), "reason": str(exc)},
        ) from exc

    if not isinstance(payload, dict):
        raise ProgressError(
            "INVALID_PROGRESS_FILE",
            "progress.json must contain a JSON object",
            details={"path": str(path)},
        )
    if payload.get("schema") != PROGRESS_SCHEMA:
        raise ProgressError(
            "INVALID_PROGRESS_SCHEMA",
            "progress.json has an unsupported schema",
            details={"path": str(path), "schema": payload.get("schema")},
        )
    if "updated_at" not in payload:
        raise ProgressError(
            "INVALID_PROGRESS_TIMESTAMP",
            "progress.json must include updated_at",
            details={"path": str(path)},
        )
    return build_progress_payload(
        stage=payload.get("stage"),
        message=payload.get("message"),
        current=payload.get("current"),
        total=payload.get("total"),
        updated_at=payload.get("updated_at"),
    )


def progress_status(workspace: str | Path) -> Dict[str, Any]:
    root = resolve_workspace(workspace)
    path = progress_path(root)
    base = progress_status_base(root)
    if not path.exists():
        return {
            **base,
            "exists": False,
            "readable": False,
            "progress": None,
            "notice": "No progress has been written yet.",
        }

    payload = load_progress(root)
    return {
        **base,
        "exists": True,
        "readable": True,
        "progress": payload,
        **payload,
    }


def safe_progress_status(workspace: str | Path) -> Dict[str, Any]:
    try:
        return progress_status(workspace)
    except ProgressError as exc:
        root = resolve_workspace(workspace)
        return {
            **progress_status_base(root),
            "exists": progress_path(root).exists(),
            "readable": False,
            "progress": None,
            "error": exc.to_dict()["error"],
        }


def progress_status_base(workspace: str | Path) -> Dict[str, Any]:
    root = resolve_workspace(workspace)
    path = progress_path(root)
    return {
        "schema": PROGRESS_SCHEMA,
        "path": str(path),
        "relativePath": progress_relative_path(),
    }
