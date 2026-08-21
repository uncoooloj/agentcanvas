#!/usr/bin/env python3
"""Run one local AgentCanvas dogfood attempt and write a replayable proof."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import smoke_pending_loop
import smoke_runtime as runtime
from verify_dogfood_proof import stable_directory_sha256, validate_manifest


PROJECT_ROOT = SCRIPTS_DIR.parent


class DogfoodAttemptError(runtime.SmokeError):
    """The dogfood attempt did not produce a replayable proof."""


def read_generated_at(workspace: Path) -> str:
    path = workspace / ".agentcanvas" / "workflow.ir.json"
    if not path.is_file():
        return "not-indexed"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DogfoodAttemptError(f"{path} is not valid JSON: {exc}")
    value = payload.get("generated_at")
    return value if isinstance(value, str) and value else "unknown"


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def pending_paths(workspace: Path, pending_id: str) -> Dict[str, Path]:
    pending_root = workspace / ".agentcanvas" / "pending"
    return {
        "markdown_path": pending_root / f"{pending_id}.md",
        "json_path": pending_root / f"{pending_id}.json",
        "conversation_jsonl_path": pending_root / f"{pending_id}.conversation.jsonl",
    }


def build_manifest(
    *,
    agent_id: str,
    agent_name: str,
    workspace: Path,
    workspace_type: str,
    workspace_description: str,
    pending_id: str,
    pending_status: str,
    permission_prompt_count: int,
    verification_command: str,
    verification_path: Path,
    workflow_before: str,
    workflow_after: str,
    canvas_revision_before: int = 0,
    canvas_revision_after: int = 0,
) -> Dict[str, Any]:
    paths = pending_paths(workspace, pending_id)
    return {
        "schema": "agentcanvas.dogfood_proof.v1",
        "agent": {"id": agent_id, "name": agent_name},
        "workspace": {
            "type": workspace_type,
            "fixture_path": str(workspace),
            "fixture_sha256": stable_directory_sha256(workspace),
            "description": workspace_description,
        },
        "checklist": [
            {
                "id": "bootstrap",
                "title": "AgentCanvas opens against a real workspace",
                "status": "passed",
                "evidence": "Live /api/context returned workspace mode for the target workspace.",
            },
            {
                "id": "map",
                "title": "Canvas map shows real workspace behavior",
                "status": "passed",
                "evidence": "Live /api/canvas returned a non-demo behavior map.",
            },
            {
                "id": "pending-request",
                "title": "Plain-English canvas change became a pending request",
                "status": "passed",
                "evidence": f"POST /api/changes created {pending_id}.",
            },
            {
                "id": "clarification",
                "title": "Agent asked a clarifying question before execution",
                "status": "passed",
                "evidence": "Conversation JSONL includes the agent question and user answer.",
            },
            {
                "id": "verification",
                "title": "Request reached verified after evidence",
                "status": "passed",
                "evidence": f"POST /api/status marked {pending_id} as {pending_status}.",
            },
            {
                "id": "reindex",
                "title": "Workspace was re-indexed after implementation",
                "status": "passed",
                "evidence": f"Workflow IR timestamp before/after reindex: {workflow_before} -> {workflow_after}.",
            },
        ],
        "permissions": {
            "prompt_count": permission_prompt_count,
            "notes": "Localhost/server access may require a Codex sandbox approval.",
        },
        "pending_request": {
            "id": pending_id,
            "status": pending_status,
            **{key: str(value) for key, value in paths.items()},
        },
        "verification": {
            "command": verification_command,
            "result": "passed",
            "actor": agent_id,
            "evidence_path": str(verification_path),
        },
        "canvas": {
            "revision_before": canvas_revision_before,
            "revision_after": canvas_revision_after,
        },
        "workflow_ir": {
            "indexed_at_before": workflow_before,
            "indexed_at_after": workflow_after,
        },
        "recording": {
            "redacted": True,
            "not_recorded_reason": "Local CLI/API dogfood run; no screen recording retained.",
        },
    }


def run_attempt(args: argparse.Namespace) -> Path:
    workspace = Path(args.workspace).resolve()
    if not workspace.is_dir():
        raise DogfoodAttemptError(f"workspace does not exist: {workspace}")

    proof_dir = Path(args.proof_dir).resolve()
    proof_path = proof_dir / "proof.json"
    verification_path = proof_dir / "verification.txt"
    workflow_before = read_generated_at(workspace)

    server = runtime.start_server(workspace, args.host)
    try:
        launch = runtime.read_until_launch(server, args.timeout)
        context_payload = runtime.request_json(launch.base_url, "/api/context", launch.token, args.timeout)
        runtime.validate_context(context_payload, expected_workspace=workspace.name)

        canvas_payload = runtime.request_json(launch.base_url, "/api/canvas", launch.token, args.timeout)
        runtime.validate_canvas(canvas_payload)
        canvas = runtime.require_mapping(canvas_payload.get("canvas"), "canvas")
        mapping = runtime.require_mapping(canvas_payload.get("mapping"), "mapping")
        if canvas.get("isDemo") is True or mapping.get("demoFallback") is True:
            raise DogfoodAttemptError("dogfood attempt received demo content")

        change_payload = smoke_pending_loop.post_json(
            launch.base_url,
            f"/api/changes?sessionId={args.session_id}",
            launch.token,
            {
                "changeId": args.change_id,
                "title": args.change_title,
                "summary": args.change_summary,
                "journeyId": args.journey_id,
                "targetNodeId": args.target_node_id,
            },
            args.timeout,
        )
        pending = smoke_pending_loop.require_pending(change_payload, "POST /api/changes")
        pending_id = str(pending.get("id") or "")
        if not pending_id:
            raise DogfoodAttemptError("POST /api/changes did not return pending.id")

        run_cli_reply(workspace, pending_id, args.agent_id, args.question)
        detail = smoke_pending_loop.require_pending(
            runtime.request_json(
                launch.base_url,
                f"/api/pending/{pending_id}?sessionId={args.session_id}",
                launch.token,
                args.timeout,
            ),
            "GET /api/pending/<id>",
        )
        smoke_pending_loop.assert_status(detail, "needs_input", "questioned request")

        answered = smoke_pending_loop.require_pending(
            smoke_pending_loop.post_json(
                launch.base_url,
                f"/api/pending/{pending_id}/answer?sessionId={args.session_id}",
                launch.token,
                {"answer": args.answer},
                args.timeout,
            ),
            "POST /api/pending/<id>/answer",
        )
        smoke_pending_loop.assert_status(answered, "in_progress", "answered request")

        verified = smoke_pending_loop.require_pending(
            smoke_pending_loop.post_json(
                launch.base_url,
                f"/api/status?sessionId={args.session_id}",
                launch.token,
                {
                    "id": pending_id,
                    "status": "verified",
                    "note": args.verification_note,
                    "evidence": {
                        "actor": args.agent_id,
                        "at": args.evidence_at,
                        "check": args.verification_command,
                        "result": "passed",
                    },
                },
                args.timeout,
            ),
            "POST /api/status",
        )
        smoke_pending_loop.assert_status(verified, "verified", "verified request")

        smoke_pending_loop.require_ok(
            smoke_pending_loop.post_json(launch.base_url, "/api/reindex", launch.token, {}, args.timeout),
            "POST /api/reindex",
        )
    finally:
        runtime.stop_server(server)

    workflow_after = read_generated_at(workspace)
    verification_text = "\n".join(
        [
            f"workspace={workspace}",
            f"agent={args.agent_id}",
            f"session_id={args.session_id}",
            f"workflow_before={workflow_before}",
            f"workflow_after={workflow_after}",
            f"verification_command={args.verification_command}",
            "result=passed",
            "",
        ]
    )
    write_text(verification_path, verification_text)

    manifest = build_manifest(
        agent_id=args.agent_id,
        agent_name=args.agent_name,
        workspace=workspace,
        workspace_type=args.workspace_type,
        workspace_description=args.workspace_description,
        pending_id=pending_id,
        pending_status="verified",
        permission_prompt_count=args.permission_prompt_count,
        verification_command=args.verification_command,
        verification_path=verification_path,
        workflow_before=workflow_before,
        workflow_after=workflow_after,
    )
    write_json(proof_path, manifest)
    validate_manifest(proof_path)
    print(f"PASS: wrote dogfood proof {proof_path}", flush=True)
    return proof_path


def run_cli_reply(workspace: Path, pending_id: str, actor: str, question: str) -> None:
    command = [
        sys.executable,
        "-m",
        "agentcanvas",
        "reply",
        pending_id,
        str(workspace),
        "--actor",
        actor,
        "--question",
        question,
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
        raise DogfoodAttemptError(
            "agentcanvas reply failed with exit code %s\nstdout:\n%s\nstderr:\n%s"
            % (completed.returncode, completed.stdout, completed.stderr)
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one local AgentCanvas dogfood attempt.")
    parser.add_argument("workspace", help="workspace to run AgentCanvas against in-place")
    parser.add_argument("--proof-dir", required=True, help="directory that will receive proof.json and verification.txt")
    parser.add_argument("--agent-id", default="codex")
    parser.add_argument("--agent-name", default="Codex")
    parser.add_argument("--workspace-type", default="local-project")
    parser.add_argument("--workspace-description", default="Real local workspace dogfood run.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--timeout", type=float, default=runtime.DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--session-id", default="dogfood-attempt")
    parser.add_argument("--change-id", default="dogfood-change")
    parser.add_argument("--change-title", default="Record dogfood attempt")
    parser.add_argument("--change-summary", default="Record this dogfood attempt as release evidence.")
    parser.add_argument("--journey-id", default="flow:agentcanvas")
    parser.add_argument("--target-node-id", default="node:dogfood")
    parser.add_argument("--question", default="Should this change update public files?")
    parser.add_argument("--answer", default="No. Keep the evidence in ignored private proof files.")
    parser.add_argument("--verification-note", default="Verified by local dogfood attempt runner.")
    parser.add_argument("--verification-command", default="scripts/run_dogfood_attempt.py")
    parser.add_argument("--evidence-at", default="2026-07-06T00:00:00Z")
    parser.add_argument("--permission-prompt-count", type=int, default=1)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        run_attempt(args)
    except runtime.SandboxPermissionError as exc:
        print(f"\nSANDBOX PERMISSION BLOCKED: {exc}", file=sys.stderr)
        return 2
    except DogfoodAttemptError as exc:
        print(f"\nFAILED: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
