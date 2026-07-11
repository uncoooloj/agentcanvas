"""Durable, local proof that an AgentCanvas-capable agent is available."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional

from .ir import atomic_write_json, now_utc, resolve_workspace, state_paths


AGENT_PRESENCE_SCHEMA = "agentcanvas.agent_presence.v1"
AGENT_PRESENCE_FILENAME = "agent.presence.json"
AGENT_PRESENCE_FRESH_SECONDS = 90


class AgentPresenceState(str, Enum):
    CONNECTED = "connected"
    NOT_CONNECTED = "not_connected"
    STALE = "stale"
    UNREADABLE = "unreadable"
    SESSION_MISMATCH = "session_mismatch"


class AgentPresenceError(ValueError):
    """Raised when local agent-presence state is invalid."""


def agent_presence_path(workspace: str | Path) -> Path:
    state_dir, _ir_path, _pending_dir = state_paths(workspace)
    return state_dir / AGENT_PRESENCE_FILENAME


def record_agent_presence(
    workspace: str | Path,
    *,
    agent: str,
    agent_name: Optional[str] = None,
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    agent_value = _required_text(agent, "agent")
    payload: Dict[str, Any] = {
        "schema": AGENT_PRESENCE_SCHEMA,
        "agent": agent_value,
        "updated_at": now_utc(),
    }
    if agent_name and agent_name.strip():
        payload["agent_name"] = agent_name.strip()
    if session_id and session_id.strip():
        payload["session_id"] = session_id.strip()
    atomic_write_json(agent_presence_path(workspace), payload)
    return payload


def agent_presence_status(
    workspace: str | Path,
    *,
    session_id: Optional[str] = None,
    fresh_seconds: int = AGENT_PRESENCE_FRESH_SECONDS,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    root = resolve_workspace(workspace)
    path = agent_presence_path(root)
    base = {"path": str(path), "exists": path.exists(), "readable": False, "connected": False}
    if not path.exists():
        return {**base, "state": AgentPresenceState.NOT_CONNECTED.value}

    try:
        payload = _load_agent_presence(path)
    except (OSError, ValueError) as exc:
        return {
            **base,
            "state": AgentPresenceState.UNREADABLE.value,
            "error": str(exc),
        }

    expected_session = _optional_text(session_id)
    recorded_session = _optional_text(payload.get("session_id"))
    if expected_session and recorded_session and expected_session != recorded_session:
        return {
            **base,
            "readable": True,
            "state": AgentPresenceState.SESSION_MISMATCH.value,
            **_public_fields(payload),
        }

    updated_at = _parse_timestamp(payload["updated_at"])
    reference = now or datetime.now(timezone.utc)
    if (reference - updated_at).total_seconds() > fresh_seconds:
        return {
            **base,
            "readable": True,
            "state": AgentPresenceState.STALE.value,
            **_public_fields(payload),
        }
    return {
        **base,
        "readable": True,
        "connected": True,
        "state": AgentPresenceState.CONNECTED.value,
        **_public_fields(payload),
    }


def _load_agent_presence(path: Path) -> Dict[str, Any]:
    import json

    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise AgentPresenceError("agent presence must contain a JSON object")
    if payload.get("schema") != AGENT_PRESENCE_SCHEMA:
        raise AgentPresenceError("agent presence has an unsupported schema")
    _required_text(payload.get("agent"), "agent")
    _parse_timestamp(payload.get("updated_at"))
    return payload


def _public_fields(payload: Dict[str, Any]) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "agent": payload["agent"],
        "updatedAt": payload["updated_at"],
    }
    if _optional_text(payload.get("agent_name")):
        result["agentName"] = payload["agent_name"].strip()
    if _optional_text(payload.get("session_id")):
        result["sessionId"] = payload["session_id"].strip()
    return result


def _required_text(value: Any, field: str) -> str:
    text = _optional_text(value)
    if not text:
        raise AgentPresenceError(f"{field} must be a non-empty string")
    return text


def _optional_text(value: Any) -> Optional[str]:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _parse_timestamp(value: Any) -> datetime:
    text = _required_text(value, "updated_at")
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError as exc:
        raise AgentPresenceError("updated_at must be an ISO-8601 timestamp") from exc
