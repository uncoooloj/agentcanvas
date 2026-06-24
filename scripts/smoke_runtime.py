#!/usr/bin/env python3
"""Run a live AgentCanvas API smoke check against the sample JS workspace."""

from __future__ import annotations

import argparse
import json
import os
import queue
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import (
    Any,
    Dict,
    Iterable,
    List,
    Mapping,
    NamedTuple,
    Optional,
    Sequence,
    Tuple,
)
from urllib import error, request
from urllib.parse import parse_qs, urlparse


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WORKSPACE = PROJECT_ROOT / "examples" / "sample-js-app"
DEFAULT_TIMEOUT_SECONDS = 20.0
URL_RE = re.compile(r"https?://[^\s]+")


class SmokeError(RuntimeError):
    """The runtime smoke check could not prove the expected behavior."""


class SandboxPermissionError(SmokeError):
    """The local sandbox blocked localhost server or client socket access."""


class LaunchInfo(NamedTuple):
    base_url: str
    token: str


class ServerProcess(NamedTuple):
    process: subprocess.Popen
    output: "queue.Queue[Tuple[str, str]]"


def project_env() -> Dict[str, str]:
    env = os.environ.copy()
    pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        str(PROJECT_ROOT)
        if not pythonpath
        else str(PROJECT_ROOT) + os.pathsep + pythonpath
    )
    return env


def command_text(command: Sequence[object]) -> str:
    return " ".join(str(part) for part in command)


def parse_launch_info(line: str) -> Optional[LaunchInfo]:
    match = URL_RE.search(line)
    if not match:
        return None
    parsed = urlparse(match.group(0))
    token = parse_qs(parsed.query).get("token", [None])[0]
    if not parsed.scheme or not parsed.netloc or not token:
        return None
    return LaunchInfo(base_url=f"{parsed.scheme}://{parsed.netloc}", token=token)


def start_output_reader(
    stream,
    label: str,
    output: "queue.Queue[Tuple[str, str]]",
) -> threading.Thread:
    def read_lines() -> None:
        try:
            for line in iter(stream.readline, ""):
                output.put((label, line.rstrip("\n")))
        finally:
            output.put((label, ""))

    thread = threading.Thread(target=read_lines, daemon=True)
    thread.start()
    return thread


def start_server(workspace: Path, host: str) -> ServerProcess:
    command = [
        sys.executable,
        "-m",
        "agentcanvas",
        "start",
        str(workspace),
        "--host",
        host,
        "--port",
        "0",
        "--agent",
        "codex",
    ]
    print(f"Start command: {command_text(command)}", flush=True)
    try:
        process = subprocess.Popen(
            command,
            cwd=str(PROJECT_ROOT),
            env=project_env(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
    except PermissionError as exc:
        raise SandboxPermissionError(
            "Could not start AgentCanvas because the sandbox denied process or "
            f"socket access: {exc}. Rerun with localhost/server permission."
        )
    except FileNotFoundError as exc:
        raise SmokeError(f"Could not start AgentCanvas: {exc}")

    output: "queue.Queue[Tuple[str, str]]" = queue.Queue()
    if process.stdout is not None:
        start_output_reader(process.stdout, "stdout", output)
    if process.stderr is not None:
        start_output_reader(process.stderr, "stderr", output)
    return ServerProcess(process=process, output=output)


def read_until_launch(server: ServerProcess, timeout_seconds: float) -> LaunchInfo:
    deadline = time.monotonic() + timeout_seconds
    lines: List[Tuple[str, str]] = []
    while time.monotonic() < deadline:
        if server.process.poll() is not None:
            lines.extend(drain_output(server.output))
            text = joined_output(lines)
            if looks_like_sandbox_permission_failure(text):
                raise SandboxPermissionError(
                    "AgentCanvas exited before serving. The output looks like a "
                    "sandbox denied localhost binding. Rerun with permission to "
                    "bind 127.0.0.1, or run this smoke outside the sandbox. "
                    f"Detail: {summarize_permission_failure(text)}"
                )
            raise SmokeError(
                "AgentCanvas exited before printing its launch URL.\n" + text
            )

        try:
            label, line = server.output.get(timeout=0.1)
        except queue.Empty:
            continue
        if line == "":
            continue
        lines.append((label, line))
        if label == "stdout":
            print(f"server {label}: {line}", flush=True)
        launch = parse_launch_info(line)
        if launch is not None:
            return launch

    lines.extend(drain_output(server.output))
    raise SmokeError(
        f"Timed out after {timeout_seconds:g}s waiting for AgentCanvas to print "
        "its launch URL.\n"
        + joined_output(lines)
    )


def drain_output(output: "queue.Queue[Tuple[str, str]]") -> List[Tuple[str, str]]:
    lines: List[Tuple[str, str]] = []
    while True:
        try:
            item = output.get_nowait()
        except queue.Empty:
            return lines
        if item[1] != "":
            lines.append(item)


def joined_output(lines: Iterable[Tuple[str, str]]) -> str:
    text = "\n".join(f"{label}: {line}" for label, line in lines if line)
    return text or "No server output captured."


def stop_server(server: ServerProcess) -> None:
    process = server.process
    if process.poll() is not None:
        return
    process.send_signal(signal.SIGINT)
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def looks_like_sandbox_permission_failure(text: str) -> bool:
    lowered = text.lower()
    return (
        "permissionerror" in lowered
        and "operation not permitted" in lowered
    ) or (
        "errno 1" in lowered
        and "operation not permitted" in lowered
    )


def summarize_permission_failure(text: str) -> str:
    for line in reversed(text.splitlines()):
        if "PermissionError" in line or "Operation not permitted" in line:
            return line.strip()
    return "Permission denied by the local sandbox."


def request_json(base_url: str, path: str, token: str, timeout_seconds: float) -> Dict[str, Any]:
    url = base_url.rstrip("/") + path
    http_request = request.Request(url, headers={"X-AgentCanvas-Token": token})
    try:
        with request.urlopen(http_request, timeout=timeout_seconds) as response:
            data = response.read().decode("utf-8")
    except PermissionError as exc:
        raise SandboxPermissionError(
            f"Sandbox denied the localhost request to {path}: {exc}. "
            "Rerun with permission to connect to 127.0.0.1."
        )
    except error.URLError as exc:
        reason = getattr(exc, "reason", exc)
        if isinstance(reason, PermissionError) or looks_like_sandbox_permission_failure(
            str(reason)
        ):
            raise SandboxPermissionError(
                f"Sandbox denied the localhost request to {path}: {reason}. "
                "Rerun with permission to connect to 127.0.0.1."
            )
        raise SmokeError(f"Could not request {path}: {exc}")
    except TimeoutError as exc:
        raise SmokeError(f"Timed out requesting {path}: {exc}")

    try:
        payload = json.loads(data)
    except json.JSONDecodeError as exc:
        raise SmokeError(f"{path} returned invalid JSON: {exc}")
    if not isinstance(payload, dict):
        raise SmokeError(f"{path} returned a JSON {type(payload).__name__}, not an object")
    return payload


def require_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SmokeError(f"{label} must be an object")
    return value


def validate_context(payload: Mapping[str, Any], expected_workspace: str) -> Mapping[str, Any]:
    if payload.get("ok") is not True:
        raise SmokeError("/api/context did not return ok=true")
    context = require_mapping(payload.get("context"), "/api/context context")
    source = require_mapping(context.get("source"), "/api/context source")
    failures = []
    if context.get("workspace") != expected_workspace:
        failures.append(
            f"workspace={context.get('workspace')!r}, expected {expected_workspace!r}"
        )
    if context.get("mode") != "workspace":
        failures.append(f"mode={context.get('mode')!r}, expected 'workspace'")
    if context.get("isDemo") is not False:
        failures.append(f"isDemo={context.get('isDemo')!r}, expected False")
    if context.get("isDemoContent") is not False:
        failures.append(
            f"isDemoContent={context.get('isDemoContent')!r}, expected False"
        )
    if context.get("demoFallback") is not False:
        failures.append(f"demoFallback={context.get('demoFallback')!r}, expected False")
    if source.get("kind") != "workspace":
        failures.append(f"context.source.kind={source.get('kind')!r}, expected 'workspace'")
    if failures:
        raise SmokeError("/api/context validation failed: " + "; ".join(failures))
    return context


def validate_canvas(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    if payload.get("ok") is not True:
        raise SmokeError("/api/canvas did not return ok=true")
    canvas = require_mapping(payload.get("canvas"), "/api/canvas canvas")
    mapping = require_mapping(payload.get("mapping"), "/api/canvas mapping")
    source = require_mapping(mapping.get("source"), "/api/canvas mapping.source")
    failures = []
    if canvas.get("isDemo") is not False:
        failures.append(f"canvas.isDemo={canvas.get('isDemo')!r}, expected False")
    if mapping.get("demoFallback") is not False:
        failures.append(
            f"mapping.demoFallback={mapping.get('demoFallback')!r}, expected False"
        )
    if source.get("kind") != "heuristic-projection":
        failures.append(
            "mapping.source.kind="
            f"{source.get('kind')!r}, expected 'heuristic-projection'"
        )
    flow_count = mapping.get("flowCount")
    source_flow_count = source.get("flowCount")
    if not isinstance(flow_count, int) or flow_count <= 0:
        failures.append(f"mapping.flowCount={flow_count!r}, expected a positive integer")
    if source_flow_count != flow_count:
        failures.append(
            f"mapping.source.flowCount={source_flow_count!r}, expected {flow_count!r}"
        )
    journeys = canvas.get("journeys")
    if not isinstance(journeys, list) or not journeys:
        failures.append("canvas.journeys must be a non-empty list")
    if failures:
        raise SmokeError("/api/canvas validation failed: " + "; ".join(failures))
    return mapping


def run_smoke(args: argparse.Namespace) -> None:
    source_workspace = Path(args.workspace).resolve()
    if not source_workspace.is_dir():
        raise SmokeError(f"workspace does not exist: {source_workspace}")

    print("AgentCanvas runtime smoke", flush=True)
    print(f"Project root: {PROJECT_ROOT}", flush=True)
    print(f"Workspace fixture: {source_workspace}", flush=True)

    with tempfile.TemporaryDirectory(prefix="agentcanvas-runtime-smoke-") as temp_root:
        workspace = Path(temp_root) / source_workspace.name
        shutil.copytree(
            str(source_workspace),
            str(workspace),
            ignore=shutil.ignore_patterns(".agentcanvas"),
        )
        print(f"Workspace copy: {workspace} (without cached .agentcanvas)", flush=True)

        server = start_server(workspace, args.host)
        try:
            launch = read_until_launch(server, args.timeout)
            print(f"Parsed server URL: {launch.base_url}", flush=True)

            context_payload = request_json(
                launch.base_url,
                "/api/context",
                launch.token,
                args.timeout,
            )
            context = validate_context(context_payload, expected_workspace=workspace.name)
            print(
                "GET /api/context ok: "
                f"mode={context.get('mode')} "
                f"isDemo={context.get('isDemo')} "
                f"source.kind={context.get('source', {}).get('kind')}",
                flush=True,
            )

            canvas_payload = request_json(
                launch.base_url,
                "/api/canvas",
                launch.token,
                args.timeout,
            )
            mapping = validate_canvas(canvas_payload)
            print(
                "GET /api/canvas ok: "
                f"mapping.source.kind={mapping.get('source', {}).get('kind')} "
                f"flowCount={mapping.get('flowCount')} "
                f"displayFlowCount={mapping.get('displayFlowCount')}",
                flush=True,
            )
        finally:
            stop_server(server)

    print("PASS: runtime API smoke verified sample-js-app workspace mode.", flush=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Start AgentCanvas on a random localhost port and verify the "
            "sample workspace /api/context and /api/canvas responses."
        )
    )
    parser.add_argument(
        "workspace",
        nargs="?",
        default=str(DEFAULT_WORKSPACE),
        help="Workspace fixture to copy into a temporary directory before serving.",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to bind. Defaults to 127.0.0.1.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help="Seconds to wait for server launch and each API request.",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        run_smoke(args)
    except SandboxPermissionError as exc:
        print(f"\nSANDBOX PERMISSION BLOCKED: {exc}", file=sys.stderr)
        return 2
    except SmokeError as exc:
        print(f"\nFAILED: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
