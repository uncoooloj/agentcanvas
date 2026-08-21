"""Shared failure IDs and repair hints for AgentCanvas onboarding."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, Optional


class FailureId(str, Enum):
    UV_MISSING = "uv_missing"
    INSTALL_FAILED = "install_failed"
    PORT_BUSY = "port_busy"
    TOKEN_INVALID = "token_invalid"
    SERVER_NOT_RUNNING = "server_not_running"
    AGENT_STALLED = "agent_stalled"
    WORKSPACE_UNINDEXED = "workspace_unindexed"
    CANVAS_INVALID = "canvas_invalid"


FAILURE_REPAIR_HINTS: Dict[FailureId, str] = {
    FailureId.UV_MISSING: "Install uv, or use the pip fallback for use-agentcanvas.",
    FailureId.INSTALL_FAILED: "Retry the install with the package named use-agentcanvas and inspect the package-manager error.",
    FailureId.PORT_BUSY: "Rerun agentcanvas up with a wider --port-end or stop the old server.",
    FailureId.TOKEN_INVALID: "Rerun agentcanvas up --json and open the fresh URL it returns.",
    FailureId.SERVER_NOT_RUNNING: "Run agentcanvas up --json for this workspace and use the returned local URL.",
    FailureId.AGENT_STALLED: "Check .agentcanvas/progress.json and ask the agent to resume mapping from the latest progress stage.",
    FailureId.WORKSPACE_UNINDEXED: "Run agentcanvas index --workspace <path> and refresh the canvas.",
    FailureId.CANVAS_INVALID: "Ask the agent to validate the canvas and repair it through agentcanvas canvas apply.",
}


def failure_payload(
    failure_id: FailureId,
    message: str,
    *,
    details: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Return the structured error envelope used by HTTP and CLI surfaces."""

    return {
        "ok": False,
        "error": {
            "code": failure_id.value,
            "message": message,
            "hint": FAILURE_REPAIR_HINTS[failure_id],
            "details": details or {},
        },
    }
