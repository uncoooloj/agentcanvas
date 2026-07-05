"""Command line interface for AgentCanvas."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from . import __version__
from .demo import demo_workspace
from .indexer import format_index_summary, index_workspace
from .ir import (
    PENDING_STATUSES,
    atomic_write_json,
    build_canvas_map_instruction,
    canvas_ir_path,
    ensure_state_dirs,
    format_map_health,
    list_pending,
    load_ir,
    load_canvas_ir,
    map_health,
    now_utc,
    resolve_workspace,
    save_canvas_ir,
    state_paths,
    update_pending_status,
)
from .core import build_agent_authored_canvas
from .canvas_v2 import (
    CANVAS_V2_SCHEMA,
    CanvasStoreError,
    apply_operation_batch,
    detect_v1_canvas,
    migrate_canvas_v1_to_v2,
    validate_canvas_v2,
)
from .projection import ProjectionValidationError, materialize_canvas_model
from .server import run_server


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

    pending_parser = subparsers.add_parser("pending", help="list pending change requests")
    pending_parser.add_argument("path", nargs="?", help="workspace path to inspect")
    pending_parser.add_argument("--workspace", help="workspace path to inspect")
    pending_parser.set_defaults(func=cmd_pending)

    health_parser = subparsers.add_parser(
        "health",
        help="check whether the workspace map files are ready",
    )
    health_parser.add_argument("path", nargs="?", help="workspace path to inspect")
    health_parser.add_argument("--workspace", help="workspace path to inspect")
    health_parser.set_defaults(func=cmd_health)

    prompt_parser = subparsers.add_parser(
        "prompt",
        help="print the copyable instruction for your coding agent",
    )
    prompt_parser.add_argument("path", nargs="?", help="workspace path to map")
    prompt_parser.add_argument("--workspace", help="workspace path to map")
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
    status_parser.set_defaults(func=cmd_status)

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

    return parser


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
    run_server(
        workspace=Path(selected_workspace(args, demo_default=landing_mode or demo_mode)),
        host=args.host,
        port=args.port,
        agent=getattr(args, "agent", None),
        demo_mode=demo_mode,
        landing_mode=landing_mode,
        session_id=getattr(args, "session_id", None),
    )
    return 0


def cmd_pending(args: argparse.Namespace) -> int:
    workspace = resolve_workspace(selected_workspace(args))
    pending = list_pending(workspace)
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
        print(f"- {item.get('id')} [{item.get('status', 'pending')}] {title} ({created}){suffix}")
    return 0


def cmd_health(args: argparse.Namespace) -> int:
    workspace = resolve_workspace(selected_workspace(args))
    print(format_map_health(map_health(workspace)))
    return 0


def cmd_prompt(args: argparse.Namespace) -> int:
    workspace = resolve_workspace(selected_workspace(args))
    print("Copy this to the AI coding agent working in this project:")
    print()
    print(build_canvas_map_instruction(workspace))
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    workspace = resolve_workspace(selected_workspace(args))
    try:
        item = update_pending_status(
            workspace,
            args.pending_id,
            args.status,
            note=getattr(args, "note", None),
        )
    except (FileNotFoundError, ValueError) as exc:
        print(f"Could not update pending request: {exc}")
        return 1

    print(f"Updated {item['id']} to {item['status']}")
    if item.get("note"):
        print(item["note"])
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

    if args.dry_run:
        print("Canvas query is valid.")
        flow_count = len((canvas_ir.get("canvas") or {}).get("journeys") or [])
        print(f"Display canvas flows: {flow_count}")
        return 0

    path = save_canvas_ir(workspace, canvas_ir)
    print(f"Applied canvas query to {path}")
    print(f"Workflow evidence remains in {ir_path}")
    flow_count = len((canvas_ir.get("canvas") or {}).get("journeys") or [])
    print(f"Display canvas flows: {flow_count}")
    return 0


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
        state_dir, _ir_path, _pending_dir = ensure_state_dirs(workspace)
        history_dir = state_dir / "history"
        history_dir.mkdir(parents=True, exist_ok=True)
        history_path = history_dir / "canvas.pre-v2.json"
        atomic_write_json(history_path, current)
        save_canvas_ir(workspace, migrated)
        result["history_path"] = str(history_path)

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
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
