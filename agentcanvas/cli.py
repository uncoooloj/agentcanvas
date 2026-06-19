"""Command line interface for AgentCanvas."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from . import __version__
from .indexer import format_index_summary, index_workspace
from .ir import list_pending, resolve_workspace, state_paths
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
    start_parser.set_defaults(func=cmd_start)

    pending_parser = subparsers.add_parser("pending", help="list pending change requests")
    pending_parser.add_argument("path", nargs="?", help="workspace path to inspect")
    pending_parser.add_argument("--workspace", help="workspace path to inspect")
    pending_parser.set_defaults(func=cmd_pending)

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
    run_server(
        workspace=Path(selected_workspace(args)),
        host=args.host,
        port=args.port,
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


def selected_workspace(args: argparse.Namespace) -> str:
    return args.workspace or args.path or "."


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)
