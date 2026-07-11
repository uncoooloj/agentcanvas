"""Command line interface for AgentCanvas."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Sequence

from . import __version__
from .adapters import (
    AGENT_UNDETECTED_EXIT,
    AdapterSetupError,
    SUPPORTED_AGENTS,
    setup_adapter,
)
from .demo import demo_workspace
from .indexer import format_index_summary, index_workspace
from .ir import (
    ConversationRole,
    ConversationTurnKind,
    append_pending_conversation,
    build_bootstrap_prompt,
    canvas_ir_path,
    format_map_health,
    list_pending,
    load_ir,
    load_canvas_ir,
    map_health,
    now_utc,
    resolve_workspace,
    state_paths,
    update_pending_status,
)
from .lifecycle import PENDING, PENDING_STATUSES
from .core import build_agent_authored_canvas
from .canvas_v2 import (
    CANVAS_V2_SCHEMA,
    CanvasStoreError,
    apply_operation_batch,
    detect_v1_canvas,
    list_canvas_history,
    migrate_canvas_v1_to_v2,
    restore_canvas_revision,
    validate_canvas_v2,
    write_migrated_canvas_document,
)
from .projection import ProjectionValidationError, materialize_canvas_model
from .progress import ProgressError, write_progress, progress_status
from .server import run_server
from .supervisor import SupervisorError, ensure_server_up, is_loopback_host, stop_server


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agentcanvas",
        description="Index a workspace and serve a local agent workflow canvas.",
    )
    parser.add_argument("--version", action="version", version=f"agentcanvas {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    index_parser = subparsers.add_parser("index", help="index a workspace into workflow IR")
    index_parser.add_argument("path", nargs="?", help="workspace path to index")
    index_parser.add_argument("--workspace", help="workspace path to index")
    index_parser.set_defaults(func=cmd_index)

    start_parser = subparsers.add_parser("start", help="start the local canvas server")
    start_parser.add_argument("path", nargs="?", help="workspace path to serve")
    start_parser.add_argument("--workspace", help="workspace path to serve")
    start_parser.add_argument("--host", default="127.0.0.1", help="host to bind")
    start_parser.add_argument(
        "--allow-remote-host",
        action="store_true",
        help="allow start --host to bind a non-loopback interface; prints a warning",
    )
    start_parser.add_argument("--port", default=8765, type=int, help="port to bind; 0 picks a free port")
    start_parser.add_argument(
        "--agent",
        help="coding agent invoking AgentCanvas (claude-code, codex, cursor, antigravity)",
    )
    start_parser.add_argument(
        "--session-id",
        help="optional launching agent session id to bind browser requests and pending changes",
    )
    start_parser.add_argument(
        "--demo",
        action="store_true",
        help="open the bundled demo project instead of the launch page",
    )
    start_parser.set_defaults(func=cmd_start)

    up_parser = subparsers.add_parser("up", help="start or reuse a background AgentCanvas server")
    up_parser.add_argument("path", nargs="?", help="workspace path to serve")
    up_parser.add_argument("--workspace", help="workspace path to serve")
    up_parser.add_argument("--host", default="127.0.0.1", help="host to bind")
    up_parser.add_argument("--port", default=8765, type=int, help="first port to try")
    up_parser.add_argument("--port-end", default=8865, type=int, help="last port to try")
    up_parser.add_argument(
        "--agent",
        help="coding agent invoking AgentCanvas (claude-code, codex, cursor, antigravity)",
    )
    up_parser.add_argument(
        "--session-id",
        help="optional launching agent session id to bind browser requests and pending changes",
    )
    up_parser.add_argument("--json", action="store_true", help="print a stable JSON launch record")
    up_parser.add_argument("--open", action="store_true", help="open the browser after the server is ready")
    up_parser.add_argument("--stop", action="store_true", help="stop the recorded background server")
    up_parser.set_defaults(func=cmd_up)

    pending_parser = subparsers.add_parser("pending", help="list pending change requests")
    pending_parser.add_argument("path", nargs="?", help="workspace path to inspect")
    pending_parser.add_argument("--workspace", help="workspace path to inspect")
    pending_parser.add_argument("--session-id", help="only show requests for this agent session")
    pending_parser.set_defaults(func=cmd_pending)

    health_parser = subparsers.add_parser(
        "health",
        help="check whether the workspace map files are ready",
    )
    health_parser.add_argument("path", nargs="?", help="workspace path to inspect")
    health_parser.add_argument("--workspace", help="workspace path to inspect")
    health_parser.set_defaults(func=cmd_health)

    progress_parser = subparsers.add_parser(
        "progress",
        help="write durable workspace mapping progress",
    )
    progress_parser.add_argument("path", nargs="?", help="workspace path to update")
    progress_parser.add_argument("--workspace", help="workspace path to update")
    progress_parser.add_argument(
        "--stage",
        required=True,
        help="progress stage",
    )
    progress_parser.add_argument("--message", required=True, help="short progress message")
    progress_parser.add_argument("--current", help="current progress count")
    progress_parser.add_argument("--total", help="total progress count")
    progress_parser.set_defaults(func=cmd_progress)

    mcp_parser = subparsers.add_parser("mcp", help="run the AgentCanvas MCP server over stdio")
    mcp_parser.add_argument("path", nargs="?", help="default workspace path for MCP tools")
    mcp_parser.add_argument("--workspace", help="default workspace path for MCP tools")
    mcp_parser.set_defaults(func=cmd_mcp)

    setup_parser = subparsers.add_parser("setup", help="install AgentCanvas instructions for an AI agent")
    add_setup_arguments(setup_parser)
    setup_parser.set_defaults(func=cmd_setup)

    prompt_parser = subparsers.add_parser(
        "prompt",
        help="print the copyable instruction for your coding agent",
    )
    prompt_parser.add_argument("path", nargs="?", help="workspace path to map")
    prompt_parser.add_argument("--workspace", help="workspace path to map")
    prompt_parser.add_argument(
        "--agent",
        help="optional label for the coding agent that should receive the prompt",
    )
    prompt_parser.set_defaults(func=cmd_prompt)

    status_parser = subparsers.add_parser(
        "status",
        help="update a pending AgentCanvas request status",
    )
    status_parser.add_argument("pending_id", help="pending request id or unique id fragment")
    status_parser.add_argument("path", nargs="?", help="workspace path to update")
    status_parser.add_argument("--workspace", help="workspace path to update")
    status_parser.add_argument("--status", required=True, choices=sorted(PENDING_STATUSES))
    status_parser.add_argument("--note", help="short status note for the user")
    status_parser.add_argument(
        "--actor",
        default="agentcanvas-cli",
        help="agent or person making this status update",
    )
    status_parser.add_argument("--session-id", help="only update a request from this agent session")
    status_parser.add_argument("--evidence-check", help="verification check that was run before marking verified")
    status_parser.add_argument("--evidence-result", help="verification result, for example 'passed'")
    status_parser.add_argument("--evidence-actor", default="agentcanvas-cli", help="who performed verification")
    status_parser.add_argument("--evidence-at", help="ISO timestamp for verification; defaults to now")
    status_parser.set_defaults(func=cmd_status)

    reply_parser = subparsers.add_parser(
        "reply",
        help="append a question, answer, or note to a pending request thread",
    )
    reply_parser.add_argument("pending_id", help="pending request id or unique id fragment")
    reply_parser.add_argument("path", nargs="?", help="workspace path to update")
    reply_parser.add_argument("--workspace", help="workspace path to update")
    reply_parser.add_argument("--session-id", help="only reply to a request from this agent session")
    reply_parser.add_argument("--actor", default="agentcanvas-cli", help="actor name for the conversation turn")
    reply_kind = reply_parser.add_mutually_exclusive_group(required=True)
    reply_kind.add_argument("--question", help="ask the user a clarifying question")
    reply_kind.add_argument("--answer", help="record a user answer")
    reply_kind.add_argument("--note", help="add an implementation note")
    reply_parser.set_defaults(func=cmd_reply)

    apply_parser = subparsers.add_parser(
        "apply-query",
        help="validate an agent canvas query and write the display canvas",
    )
    apply_parser.add_argument("path", nargs="?", help="workspace path to update")
    apply_parser.add_argument("--workspace", help="workspace path to update")
    apply_parser.add_argument("--query", required=True, help="canvas query JSON file")
    apply_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="validate and summarize without writing canvas IR",
    )
    apply_parser.set_defaults(func=cmd_apply_query)

    canvas_parser = subparsers.add_parser("canvas", help="work with the v2 canvas store")
    canvas_subparsers = canvas_parser.add_subparsers(dest="canvas_command", required=True)

    canvas_apply_parser = canvas_subparsers.add_parser(
        "apply",
        help="apply a v2 canvas operation batch",
    )
    canvas_apply_parser.add_argument("path", nargs="?", help="workspace path to update")
    canvas_apply_parser.add_argument("--workspace", help="workspace path to update")
    canvas_apply_parser.add_argument("--base-revision", required=True, type=int)
    canvas_apply_parser.add_argument("--input", required=True, help="operation batch JSON file")
    canvas_apply_parser.add_argument("--authored-by", help="agent or human author name")
    canvas_apply_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="validate and summarize without writing canvas IR",
    )
    canvas_apply_parser.set_defaults(func=cmd_canvas_apply)

    canvas_migrate_parser = canvas_subparsers.add_parser(
        "migrate",
        help="migrate a legacy canvas map to the v2 canvas store format",
    )
    canvas_migrate_parser.add_argument("path", nargs="?", help="workspace path to migrate")
    canvas_migrate_parser.add_argument("--workspace", help="workspace path to migrate")
    canvas_migrate_parser.add_argument("--authored-by", help="agent or human author name")
    migrate_mode = canvas_migrate_parser.add_mutually_exclusive_group(required=True)
    migrate_mode.add_argument(
        "--dry-run",
        action="store_true",
        help="validate and summarize without writing canvas IR",
    )
    migrate_mode.add_argument(
        "--apply",
        action="store_true",
        help="write the migrated v2 canvas IR",
    )
    canvas_migrate_parser.set_defaults(func=cmd_canvas_migrate)

    canvas_history_parser = canvas_subparsers.add_parser(
        "history",
        help="list v2 canvas history snapshots",
    )
    canvas_history_parser.add_argument("path", nargs="?", help="workspace path to inspect")
    canvas_history_parser.add_argument("--workspace", help="workspace path to inspect")
    canvas_history_parser.set_defaults(func=cmd_canvas_history)

    canvas_restore_parser = canvas_subparsers.add_parser(
        "restore",
        help="restore a v2 canvas history snapshot as a new revision",
    )
    canvas_restore_parser.add_argument("path", nargs="?", help="workspace path to update")
    canvas_restore_parser.add_argument("--workspace", help="workspace path to update")
    canvas_restore_parser.add_argument("--revision", required=True, type=int, help="history revision to restore")
    canvas_restore_parser.add_argument("--base-revision", type=int, help="expected current revision")
    canvas_restore_parser.add_argument("--authored-by", help="agent or human author name")
    canvas_restore_parser.set_defaults(func=cmd_canvas_restore)

    return parser


def add_setup_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("path", nargs="?", help="workspace path to configure")
    parser.add_argument("--workspace", help="workspace path to configure")
    parser.add_argument(
        "--agent",
        required=True,
        choices=sorted(SUPPORTED_AGENTS),
        help="agent adapter to configure",
    )
    parser.add_argument(
        "--write-codex-config",
        action="store_true",
        help="also write the optional ~/.codex/config.toml MCP snippet for Codex",
    )
    parser.add_argument(
        "--codex-config",
        help="override Codex config path for --write-codex-config",
    )


def cmd_index(args: argparse.Namespace) -> int:
    workspace = resolve_workspace(selected_workspace(args))
    workflow_ir = index_workspace(workspace)
    _, ir_path, _ = state_paths(workspace)
    print(f"Indexed {workspace}")
    print(f"IR: {ir_path}")
    print(format_index_summary(workflow_ir))
    return 0


def cmd_start(args: argparse.Namespace) -> int:
    landing_mode = not args.workspace and not args.path and not args.demo
    demo_mode = bool(args.demo)
    if not is_loopback_host(args.host):
        if not getattr(args, "allow_remote_host", False):
            print(
                "Refusing to bind AgentCanvas to a non-loopback host without --allow-remote-host.",
                file=sys.stderr,
            )
            return 1
        print(
            "Warning: binding AgentCanvas to a non-loopback host exposes the local canvas server to your network.",
            file=sys.stderr,
        )
    run_server(
        workspace=Path(selected_workspace(args, demo_default=landing_mode or demo_mode)),
        host=args.host,
        port=args.port,
        token=os.environ.get("AGENTCANVAS_SERVER_TOKEN"),
        agent=getattr(args, "agent", None),
        demo_mode=demo_mode,
        landing_mode=landing_mode,
        session_id=getattr(args, "session_id", None),
        supervised=bool(os.environ.get("AGENTCANVAS_SUPERVISED")),
    )
    return 0


def cmd_up(args: argparse.Namespace) -> int:
    workspace = resolve_workspace(selected_workspace(args))
    try:
        if args.stop:
            result = stop_server(workspace)
        else:
            result = ensure_server_up(
                workspace,
                host=args.host,
                port=args.port,
                port_end=args.port_end,
                agent=getattr(args, "agent", None),
                session_id=getattr(args, "session_id", None),
                open_browser=bool(getattr(args, "open", False)) and not bool(getattr(args, "json", False)),
            )
    except SupervisorError as exc:
        payload = exc.to_dict()
        if args.json:
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            print(f"AgentCanvas could not start: {exc.message}", file=sys.stderr)
            if exc.details.get("log"):
                print(exc.details["log"], file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(public_launch_payload(result), indent=2, sort_keys=True))
    elif args.stop:
        print("AgentCanvas stopped." if result.get("stopped") else "AgentCanvas was not running.")
    else:
        print(f"Canvas ready: {result['url']}")
    return 0


def public_launch_payload(result: Dict[str, Any]) -> Dict[str, Any]:
    payload = dict(result)
    payload.pop("token", None)
    return payload


def cmd_pending(args: argparse.Namespace) -> int:
    workspace = resolve_workspace(selected_workspace(args))
    pending = list_pending(workspace, session_id=getattr(args, "session_id", None))
    _, _, pending_dir = state_paths(workspace)
    if not pending:
        print(f"No pending change requests in {pending_dir}")
        return 0

    print(f"Pending change requests in {pending_dir}:")
    for item in pending:
        title = item.get("title") or item.get("id")
        created = item.get("created_at", "unknown time")
        markdown = item.get("markdown_path")
        json_path = item.get("json_path")
        paths = ", ".join(
            Path(path).name for path in [markdown, json_path] if isinstance(path, str)
        )
        suffix = f" - {paths}" if paths else ""
        print(f"- {item.get('id')} [{item.get('status', PENDING)}] {title} ({created}){suffix}")
    return 0


def cmd_health(args: argparse.Namespace) -> int:
    workspace = resolve_workspace(selected_workspace(args))
    print(format_map_health(map_health(workspace)))
    return 0


def cmd_progress(args: argparse.Namespace) -> int:
    workspace = resolve_workspace(selected_workspace(args))
    try:
        write_progress(
            workspace,
            stage=args.stage,
            message=args.message,
            current=getattr(args, "current", None),
            total=getattr(args, "total", None),
        )
        result = progress_status(workspace)
    except ProgressError as exc:
        print(json.dumps(exc.to_dict(), indent=2, sort_keys=True), file=sys.stderr)
        return 1

    print(json.dumps({"ok": True, "progress": result}, indent=2, sort_keys=True))
    return 0


def cmd_mcp(args: argparse.Namespace) -> int:
    workspace = str(resolve_workspace(selected_workspace(args)))
    try:
        from .mcp_server import MCP_EXTRA_INSTALL_HINT, run_mcp_server

        return run_mcp_server(default_workspace=workspace)
    except ModuleNotFoundError as exc:
        if exc.name == "mcp":
            from .mcp_server import MCP_EXTRA_INSTALL_HINT

            print(MCP_EXTRA_INSTALL_HINT, file=sys.stderr)
            return 3
        raise


def cmd_setup(args: argparse.Namespace) -> int:
    workspace = resolve_workspace(selected_workspace(args))
    try:
        result = setup_adapter(
            workspace,
            agent=args.agent,
            write_codex_config=bool(getattr(args, "write_codex_config", False)),
            codex_config_path=getattr(args, "codex_config", None),
        )
    except AdapterSetupError as exc:
        print(json.dumps(exc.to_dict(), indent=2, sort_keys=True), file=sys.stderr)
        return AGENT_UNDETECTED_EXIT if exc.code == "AGENT_UNDETECTED" else 1

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def cmd_prompt(args: argparse.Namespace) -> int:
    workspace = resolve_workspace(selected_workspace(args))
    agent = getattr(args, "agent", None)
    if isinstance(agent, str) and agent.strip():
        target = " ".join(agent.split())[:80]
    else:
        target = "the AI coding agent working in this project"
    print(f"Copy this to {target}:")
    print()
    print(build_bootstrap_prompt(workspace, agent=agent))
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    workspace = resolve_workspace(selected_workspace(args))
    try:
        item = update_pending_status(
            workspace,
            args.pending_id,
            args.status,
            note=getattr(args, "note", None),
            actor=getattr(args, "actor", None) or "agentcanvas-cli",
            session_id=getattr(args, "session_id", None),
            evidence=status_evidence_from_args(args),
            enforce_transitions=True,
        )
    except (FileNotFoundError, ValueError) as exc:
        print(f"Could not update pending request: {exc}")
        return 1

    print(f"Updated {item['id']} to {item['status']}")
    if item.get("note"):
        print(item["note"])
    return 0


def status_evidence_from_args(args: argparse.Namespace) -> Dict[str, Any] | None:
    check = getattr(args, "evidence_check", None)
    result = getattr(args, "evidence_result", None)
    if not check and not result:
        return None
    return {
        "actor": getattr(args, "evidence_actor", None) or getattr(args, "actor", None) or "agentcanvas-cli",
        "at": getattr(args, "evidence_at", None) or now_utc(),
        "check": check or "verification",
        "result": result or "passed",
    }


def cmd_reply(args: argparse.Namespace) -> int:
    workspace = resolve_workspace(selected_workspace(args))
    if getattr(args, "question", None):
        role = ConversationRole.AGENT.value
        kind = ConversationTurnKind.QUESTION.value
        text = args.question
    elif getattr(args, "answer", None):
        role = ConversationRole.USER.value
        kind = ConversationTurnKind.ANSWER.value
        text = args.answer
    else:
        role = ConversationRole.AGENT.value
        kind = ConversationTurnKind.NOTE.value
        text = args.note

    try:
        item = append_pending_conversation(
            workspace,
            args.pending_id,
            role=role,
            kind=kind,
            text=text,
            actor=getattr(args, "actor", None) or "agentcanvas-cli",
            session_id=getattr(args, "session_id", None),
        )
    except (FileNotFoundError, ValueError) as exc:
        print(f"Could not append pending reply: {exc}")
        return 1

    print(f"Added {kind} to {item['id']} [{item.get('status', PENDING)}]")
    summary = item.get("conversation_summary") or {}
    unanswered = summary.get("unanswered_question")
    if isinstance(unanswered, dict) and unanswered.get("text"):
        print(f"Needs input: {unanswered['text']}")
    return 0


def cmd_apply_query(args: argparse.Namespace) -> int:
    workspace = resolve_workspace(selected_workspace(args))
    _, ir_path, _ = state_paths(workspace)
    if not ir_path.exists():
        workflow_ir = index_workspace(workspace)
    else:
        workflow_ir = load_ir(workspace)

    with Path(args.query).expanduser().open(encoding="utf-8") as handle:
        canvas_query = json.load(handle)

    repo_summary = (workflow_ir.get("source_facts") or {}).get("repo") or {
        "name": workflow_ir.get("workspace", {}).get("name"),
        "root": workflow_ir.get("workspace", {}).get("root"),
        "summary": workflow_ir.get("summary") or {},
        "package": workflow_ir.get("package") or {},
        "git": workflow_ir.get("git") or {},
        "focus": workflow_ir.get("focus") or {},
    }
    try:
        canvas_model = materialize_canvas_model(
            canvas_query,
            repo_summary,
            source_facts=workflow_ir.get("source_facts"),
        )
    except ProjectionValidationError as exc:
        print(f"Canvas query rejected: {exc}")
        return 1

    canvas_ir = build_agent_authored_canvas(
        canvas_model,
        workspace=workspace,
        canvas_query=canvas_query,
    )
    try:
        canvas_v2 = migrate_canvas_v1_to_v2(
            canvas_ir,
            authored_by="apply-query",
            updated_at=now_utc(),
        )
        batch, base_revision = _operation_batch_from_projected_canvas(
            workspace,
            canvas_v2,
        )
    except (CanvasStoreError, ValueError) as exc:
        print(f"Canvas query could not be converted to canvas v2: {exc}")
        return 1

    if args.dry_run:
        try:
            result = apply_operation_batch(
                workspace,
                batch,
                base_revision=base_revision,
                authored_by="apply-query",
                dry_run=True,
            )
        except CanvasStoreError as exc:
            print(json.dumps(exc.to_dict(), indent=2, sort_keys=True))
            return 1
        print("Canvas query is valid.")
        flow_count = len(canvas_v2.get("flows") or [])
        print(f"Display canvas flows: {flow_count}")
        print(f"Canvas v2 revision would be: {result['revision']}")
        return 0

    try:
        result = apply_operation_batch(
            workspace,
            batch,
            base_revision=base_revision,
            authored_by="apply-query",
        )
    except CanvasStoreError as exc:
        print(json.dumps(exc.to_dict(), indent=2, sort_keys=True))
        return 1

    path = canvas_ir_path(workspace)
    print(f"Applied canvas query to {path}")
    print(f"Workflow evidence remains in {ir_path}")
    flow_count = len(canvas_v2.get("flows") or [])
    print(f"Display canvas flows: {flow_count}")
    print(f"Canvas v2 revision: {result['revision']}")
    return 0


def _operation_batch_from_projected_canvas(
    workspace: Path,
    canvas_v2: dict,
) -> tuple[dict, int]:
    current_payload = None
    current_is_v2 = False
    try:
        current_payload = load_canvas_ir(workspace)
    except FileNotFoundError:
        current_payload = None
    except json.JSONDecodeError as exc:
        raise CanvasStoreError(
            "INVALID_CANVAS_JSON",
            "canvas.ir.json must be valid JSON before apply-query can merge",
            details={"path": str(canvas_ir_path(workspace)), "reason": str(exc)},
        )

    if isinstance(current_payload, dict) and current_payload.get("schema") == CANVAS_V2_SCHEMA:
        current_v2 = current_payload
        current_is_v2 = True
    elif isinstance(current_payload, dict) and detect_v1_canvas(current_payload):
        current_v2 = migrate_canvas_v1_to_v2(
            current_payload,
            authored_by="apply-query-preview",
            updated_at=now_utc(),
        )
    else:
        current_v2 = {"revision": 0, "flows": []}

    current_flow_ids = {
        flow.get("id")
        for flow in current_v2.get("flows") or []
        if isinstance(flow, dict) and isinstance(flow.get("id"), str)
    }
    next_flows = [
        flow
        for flow in canvas_v2.get("flows") or []
        if isinstance(flow, dict) and isinstance(flow.get("id"), str)
    ]
    next_flow_ids = {flow["id"] for flow in next_flows}
    operations = [
        {
            "op": "set_app",
            "app": canvas_v2.get("app") if isinstance(canvas_v2.get("app"), dict) else {},
        }
    ]
    operations.extend({"op": "upsert_flow", "flow": flow} for flow in next_flows)
    operations.extend(
        {"op": "delete_flow", "target": flow_id}
        for flow_id in sorted(current_flow_ids - next_flow_ids)
    )

    base_revision = int(current_v2.get("revision") or 0)
    batch = {
        "base_revision": base_revision,
        "authored_by": "apply-query",
        "operations": operations,
    }
    if not current_is_v2:
        batch["allow_rewrite"] = {
            "reason": "Initial canvas projection from apply-query.",
        }
    return batch, base_revision


def cmd_canvas_apply(args: argparse.Namespace) -> int:
    if args.workspace and args.path:
        error = CanvasStoreError(
            "WORKSPACE_AMBIGUOUS",
            "pass either --workspace or positional path, not both",
            details={"workspace": args.workspace, "path": args.path},
        )
        print(json.dumps(error.to_dict(), indent=2, sort_keys=True))
        return 1
    workspace = resolve_workspace(selected_workspace(args))
    try:
        with Path(args.input).expanduser().open(encoding="utf-8") as handle:
            batch = json.load(handle)
    except OSError as exc:
        error = CanvasStoreError(
            "INPUT_NOT_READABLE",
            "could not read canvas operation input file",
            details={"path": args.input, "reason": str(exc)},
        )
        print(json.dumps(error.to_dict(), indent=2, sort_keys=True))
        return 1
    except ValueError as exc:
        error = CanvasStoreError(
            "INVALID_INPUT_JSON",
            "canvas operation input must be valid JSON",
            details={"path": args.input, "reason": str(exc)},
        )
        print(json.dumps(error.to_dict(), indent=2, sort_keys=True))
        return 1

    try:
        result = apply_operation_batch(
            workspace,
            batch,
            base_revision=args.base_revision,
            authored_by=getattr(args, "authored_by", None),
            dry_run=bool(getattr(args, "dry_run", False)),
        )
    except CanvasStoreError as exc:
        print(json.dumps(exc.to_dict(), indent=2, sort_keys=True))
        return 1

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def cmd_canvas_migrate(args: argparse.Namespace) -> int:
    if args.workspace and args.path:
        error = CanvasStoreError(
            "WORKSPACE_AMBIGUOUS",
            "pass either --workspace or positional path, not both",
            details={"workspace": args.workspace, "path": args.path},
        )
        print(json.dumps(error.to_dict(), indent=2, sort_keys=True))
        return 1

    workspace = resolve_workspace(selected_workspace(args))
    try:
        current = load_canvas_ir(workspace)
    except FileNotFoundError:
        error = CanvasStoreError(
            "CANVAS_NOT_FOUND",
            "canvas.ir.json was not found",
            details={"path": str(canvas_ir_path(workspace))},
        )
        print(json.dumps(error.to_dict(), indent=2, sort_keys=True))
        return 1
    except json.JSONDecodeError as exc:
        error = CanvasStoreError(
            "INVALID_CANVAS_JSON",
            "canvas.ir.json must be valid JSON",
            details={"path": str(canvas_ir_path(workspace)), "reason": str(exc)},
        )
        print(json.dumps(error.to_dict(), indent=2, sort_keys=True))
        return 1

    if isinstance(current, dict) and current.get("schema") == CANVAS_V2_SCHEMA:
        result = {
            "ok": True,
            "dry_run": bool(args.dry_run),
            "already_v2": True,
            "schema": CANVAS_V2_SCHEMA,
            "revision": current.get("revision", 0),
            "path": str(canvas_ir_path(workspace)),
        }
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0

    if not detect_v1_canvas(current):
        error = CanvasStoreError(
            "UNSUPPORTED_CANVAS_SCHEMA",
            "canvas.ir.json is not a recognized legacy AgentCanvas canvas",
            details={
                "schema": current.get("schema") if isinstance(current, dict) else None,
                "path": str(canvas_ir_path(workspace)),
            },
        )
        print(json.dumps(error.to_dict(), indent=2, sort_keys=True))
        return 1

    migrated = migrate_canvas_v1_to_v2(
        current,
        authored_by=getattr(args, "authored_by", None) or "agentcanvas-cli",
        updated_at=now_utc(),
    )
    summary = validate_canvas_v2(migrated)
    result = {
        "ok": True,
        "dry_run": bool(args.dry_run),
        "already_v2": False,
        "schema": CANVAS_V2_SCHEMA,
        "revision": migrated.get("revision", 0),
        "path": str(canvas_ir_path(workspace)),
        "summary": summary,
    }

    if args.apply:
        store_result = write_migrated_canvas_document(
            workspace,
            legacy_payload=current,
            migrated_document=migrated,
            authored_by=getattr(args, "authored_by", None) or "agentcanvas-cli",
        )
        result["revision"] = store_result["revision"]
        result["history_path"] = store_result["history_path"]

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def cmd_canvas_history(args: argparse.Namespace) -> int:
    if args.workspace and args.path:
        error = CanvasStoreError(
            "WORKSPACE_AMBIGUOUS",
            "pass either --workspace or positional path, not both",
            details={"workspace": args.workspace, "path": args.path},
        )
        print(json.dumps(error.to_dict(), indent=2, sort_keys=True))
        return 1
    workspace = resolve_workspace(selected_workspace(args))
    try:
        result = list_canvas_history(workspace)
    except CanvasStoreError as exc:
        print(json.dumps(exc.to_dict(), indent=2, sort_keys=True))
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def cmd_canvas_restore(args: argparse.Namespace) -> int:
    if args.workspace and args.path:
        error = CanvasStoreError(
            "WORKSPACE_AMBIGUOUS",
            "pass either --workspace or positional path, not both",
            details={"workspace": args.workspace, "path": args.path},
        )
        print(json.dumps(error.to_dict(), indent=2, sort_keys=True))
        return 1
    workspace = resolve_workspace(selected_workspace(args))
    try:
        result = restore_canvas_revision(
            workspace,
            args.revision,
            base_revision=getattr(args, "base_revision", None),
            authored_by=getattr(args, "authored_by", None),
        )
    except CanvasStoreError as exc:
        print(json.dumps(exc.to_dict(), indent=2, sort_keys=True))
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def selected_workspace(args: argparse.Namespace, *, demo_default: bool = False) -> str:
    if args.workspace or args.path:
        return args.workspace or args.path
    if demo_default:
        return str(demo_workspace())
    return "."


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    actual_argv: Sequence[str] = sys.argv[1:] if argv is None else argv
    if len(actual_argv) > 0 and actual_argv[0] == "init":
        actual_argv = ("setup", *actual_argv[1:])
    args = parser.parse_args(actual_argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
