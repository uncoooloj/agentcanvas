#!/usr/bin/env python3
"""Exercise the local pending-request loop against a live AgentCanvas server."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence
from urllib import error, request

import smoke_runtime as runtime


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WORKSPACE = PROJECT_ROOT / "examples" / "sample-js-app"


class PendingLoopError(runtime.SmokeError):
    """The pending-request dogfood loop did not complete."""


def post_json(
    base_url: str,
    path: str,
    token: str,
    payload: Mapping[str, Any],
    timeout_seconds: float,
) -> Dict[str, Any]:
    url = base_url.rstrip("/") + path
    body = json.dumps(payload).encode("utf-8")
    http_request = request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-AgentCanvas-Token": token,
        },
        method="POST",
    )
    try:
        with request.urlopen(http_request, timeout=timeout_seconds) as response:
            data = response.read().decode("utf-8")
    except PermissionError as exc:
        raise runtime.SandboxPermissionError(
            f"Sandbox denied the localhost request to {path}: {exc}. "
            "Rerun with permission to connect to 127.0.0.1."
        )
    except error.URLError as exc:
        reason = getattr(exc, "reason", exc)
        if isinstance(reason, PermissionError) or runtime.looks_like_sandbox_permission_failure(str(reason)):
            raise runtime.SandboxPermissionError(
                f"Sandbox denied the localhost request to {path}: {reason}. "
                "Rerun with permission to connect to 127.0.0.1."
            )
        raise PendingLoopError(f"Could not post {path}: {exc}")

    try:
        result = json.loads(data)
    except json.JSONDecodeError as exc:
        raise PendingLoopError(f"{path} returned invalid JSON: {exc}")
    if not isinstance(result, dict):
        raise PendingLoopError(f"{path} returned a JSON {type(result).__name__}, not an object")
    return result


def require_ok(payload: Mapping[str, Any], label: str) -> None:
    if payload.get("ok") is not True:
        raise PendingLoopError(f"{label} did not return ok=true: {payload}")


def require_pending(payload: Mapping[str, Any], label: str) -> Dict[str, Any]:
    require_ok(payload, label)
    pending = payload.get("pending")
    if not isinstance(pending, dict):
        raise PendingLoopError(f"{label} must return a pending object")
    return pending


def run_cli_reply(workspace: Path, pending_id: str) -> None:
    command = [
        sys.executable,
        "-m",
        "agentcanvas",
        "reply",
        pending_id,
        str(workspace),
        "--actor",
        "codex-smoke",
        "--question",
        "Should this copy mention discounts?",
    ]
    completed = subprocess.run(
        command,
        cwd=str(PROJECT_ROOT),
        env=runtime.project_env(),
        text=True,
        capture_output=True,
        timeout=30,
    )
    if completed.returncode != 0:
        raise PendingLoopError(
            "agentcanvas reply failed with exit code %s\nstdout:\n%s\nstderr:\n%s"
            % (completed.returncode, completed.stdout, completed.stderr)
        )


def assert_status(pending: Mapping[str, Any], expected: str, label: str) -> None:
    status = pending.get("status")
    if status != expected:
        raise PendingLoopError(f"{label} status={status!r}, expected {expected!r}")


def run_pending_loop(args: argparse.Namespace) -> None:
    source_workspace = Path(args.workspace).resolve()
    if not source_workspace.is_dir():
        raise PendingLoopError(f"workspace does not exist: {source_workspace}")

    print("AgentCanvas pending-loop smoke", flush=True)
    print(f"Project root: {PROJECT_ROOT}", flush=True)
    print(f"Workspace fixture: {source_workspace}", flush=True)

    with tempfile.TemporaryDirectory(prefix="agentcanvas-pending-loop-") as temp_root:
        workspace = Path(temp_root) / source_workspace.name
        shutil.copytree(
            str(source_workspace),
            str(workspace),
            ignore=shutil.ignore_patterns(".agentcanvas"),
        )
        print(f"Workspace copy: {workspace} (without cached .agentcanvas)", flush=True)

        server = runtime.start_server(workspace, args.host)
        try:
            launch = runtime.read_until_launch(server, args.timeout)
            print(f"Parsed server URL: {launch.base_url}", flush=True)

            context_payload = runtime.request_json(
                launch.base_url,
                "/api/context",
                launch.token,
                args.timeout,
            )
            runtime.validate_context(context_payload, expected_workspace=workspace.name)

            change_payload = post_json(
                launch.base_url,
                "/api/changes?sessionId=pending-loop",
                launch.token,
                {
                    "changeId": "pending-loop-change",
                    "title": "Clarify checkout empty state",
                    "summary": "Make the checkout empty state easier to understand.",
                    "journeyId": "flow:checkout",
                    "targetNodeId": "n:checkout:empty-cart",
                },
                args.timeout,
            )
            pending = require_pending(change_payload, "POST /api/changes")
            pending_id = str(pending.get("id") or "")
            if not pending_id:
                raise PendingLoopError("POST /api/changes did not return pending.id")
            assert_status(pending, "pending", "new request")
            print(f"POST /api/changes ok: pending={pending_id}", flush=True)

            run_cli_reply(workspace, pending_id)
            detail = require_pending(
                runtime.request_json(
                    launch.base_url,
                    f"/api/pending/{pending_id}?sessionId=pending-loop",
                    launch.token,
                    args.timeout,
                ),
                "GET /api/pending/<id>",
            )
            assert_status(detail, "needs_input", "questioned request")
            summary = runtime.require_mapping(detail.get("conversation_summary"), "conversation_summary")
            if not isinstance(summary.get("unanswered_question"), Mapping):
                raise PendingLoopError("questioned request must expose an unanswered question")
            print("GET /api/pending/<id> ok: status=needs_input", flush=True)

            answered = require_pending(
                post_json(
                    launch.base_url,
                    f"/api/pending/{pending_id}/answer?sessionId=pending-loop",
                    launch.token,
                    {"answer": "No discounts for this copy."},
                    args.timeout,
                ),
                "POST /api/pending/<id>/answer",
            )
            assert_status(answered, "in_progress", "answered request")
            print("POST /api/pending/<id>/answer ok: status=in_progress", flush=True)

            implemented = require_pending(
                post_json(
                    launch.base_url,
                    "/api/status?sessionId=pending-loop",
                    launch.token,
                    {
                        "id": pending_id,
                        "status": "implemented",
                        "note": "Implemented by pending-loop smoke.",
                    },
                    args.timeout,
                ),
                "POST /api/status implemented",
            )
            assert_status(implemented, "implemented", "implemented request")
            print("POST /api/status ok: status=implemented", flush=True)

            verified = require_pending(
                post_json(
                    launch.base_url,
                    "/api/status?sessionId=pending-loop",
                    launch.token,
                    {
                        "id": pending_id,
                        "status": "verified",
                        "note": "Verified by pending-loop smoke.",
                        "evidence": {
                            "actor": "codex-smoke",
                            "at": "2026-07-06T00:00:00Z",
                            "check": "scripts/smoke_pending_loop.py",
                            "result": "passed",
                        },
                    },
                    args.timeout,
                ),
                "POST /api/status",
            )
            assert_status(verified, "verified", "verified request")
            if not isinstance(verified.get("verification"), Mapping):
                raise PendingLoopError("verified request must include verification evidence")
            print("POST /api/status ok: status=verified", flush=True)

            reindex_payload = post_json(
                launch.base_url,
                "/api/reindex",
                launch.token,
                {},
                args.timeout,
            )
            require_ok(reindex_payload, "POST /api/reindex")
            print("POST /api/reindex ok", flush=True)
        finally:
            runtime.stop_server(server)

    print("PASS: pending-loop smoke verified change, Q/A, evidence, and reindex.", flush=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a live local smoke of the AgentCanvas pending-request loop."
    )
    parser.add_argument(
        "workspace",
        nargs="?",
        default=str(DEFAULT_WORKSPACE),
        help="Workspace fixture to copy into a temporary directory before serving.",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind.")
    parser.add_argument("--timeout", type=float, default=runtime.DEFAULT_TIMEOUT_SECONDS)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        run_pending_loop(args)
    except runtime.SandboxPermissionError as exc:
        print(f"\nSANDBOX PERMISSION BLOCKED: {exc}", file=sys.stderr)
        return 2
    except PendingLoopError as exc:
        print(f"\nFAILED: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
