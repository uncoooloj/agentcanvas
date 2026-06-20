"""Local HTTP server for the AgentCanvas browser app."""

from __future__ import annotations

import json
import mimetypes
import os
import secrets
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from urllib.parse import parse_qs, unquote, urlencode, urlparse

from .indexer import index_workspace
from .ir import (
    canvas_ir_path,
    list_pending,
    load_canvas_ir,
    load_ir,
    resolve_workspace,
    save_canvas_ir,
    state_paths,
    update_pending_status,
    write_pending_change,
)
from .core.behavior_canvas import build_behavior_canvas


# Known coding-agent platforms that may launch AgentCanvas, with human labels.
_ASSISTANTS = {
    "claude-code": "Claude Code",
    "codex": "Codex",
    "cursor": "Cursor",
    "antigravity": "Antigravity",
    "generic": "Your assistant",
}


def resolve_assistant(agent: Optional[str]) -> Tuple[str, str]:
    """Return (id, display_name) for the coding agent invoking AgentCanvas.

    Prefers an explicit --agent value, then env hints, else a neutral default.
    """
    if agent:
        key = agent.strip().lower().replace(" ", "-")
        return key, _ASSISTANTS.get(key, agent)
    env = os.environ
    if env.get("CLAUDECODE") or env.get("CLAUDE_CODE") or "CLAUDE_CODE_ENTRYPOINT" in env:
        return "claude-code", _ASSISTANTS["claude-code"]
    if any(k.startswith("CODEX_") for k in env) or env.get("CODEX"):
        return "codex", _ASSISTANTS["codex"]
    if any(k.startswith("CURSOR") for k in env):
        return "cursor", _ASSISTANTS["cursor"]
    return "generic", _ASSISTANTS["generic"]


def run_server(
    workspace: str | Path,
    host: str = "127.0.0.1",
    port: int = 8765,
    token: Optional[str] = None,
    agent: Optional[str] = None,
    demo_mode: bool = False,
    landing_mode: bool = False,
    session_id: Optional[str] = None,
) -> None:
    root = resolve_workspace(workspace)
    token = token or secrets.token_urlsafe(24)
    assistant_id, assistant_name = resolve_assistant(agent)
    if demo_mode and assistant_id == "generic":
        assistant_name = "No agent connected"
    ensure_ir(root)
    handler_class = make_handler(
        root,
        token,
        assistant_id,
        assistant_name,
        demo_mode,
        landing_mode=landing_mode,
        session_id=session_id,
    )
    httpd = ThreadingHTTPServer((host, port), handler_class)
    actual_host, actual_port = httpd.server_address[:2]
    display_host = "127.0.0.1" if actual_host in {"0.0.0.0", "::"} else actual_host
    query = {"token": token}
    if session_id:
        query["sessionId"] = session_id
    url = f"http://{display_host}:{actual_port}/?{urlencode(query)}"

    if landing_mode:
        prefix = "AgentCanvas launch page serving"
    elif demo_mode:
        prefix = "AgentCanvas demo mode serving"
    else:
        prefix = "AgentCanvas serving"
    print(f"{prefix} {root}", flush=True)
    print(f"Open {url}", flush=True)
    print("Press Ctrl-C to stop.", flush=True)

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nAgentCanvas stopped.", flush=True)
    finally:
        httpd.server_close()


def ensure_ir(workspace: Path) -> None:
    _, ir_path, _ = state_paths(workspace)
    if not ir_path.exists():
        index_workspace(workspace)


def load_or_build_canvas(workspace: Path, *, refresh: bool = False) -> Dict[str, Any]:
    if not refresh:
        try:
            if canvas_cache_is_fresh(workspace):
                return load_canvas_ir(workspace)
        except FileNotFoundError:
            pass
    try:
        graph = load_ir(workspace)
    except FileNotFoundError:
        graph = index_workspace(workspace)
    canvas = build_behavior_canvas(graph, workspace=workspace)
    save_canvas_ir(workspace, canvas)
    return canvas


def canvas_cache_is_fresh(workspace: Path) -> bool:
    _, ir_path, _ = state_paths(workspace)
    path = canvas_ir_path(workspace)
    if not path.exists():
        return False
    if not ir_path.exists():
        return True
    return path.stat().st_mtime >= ir_path.stat().st_mtime


def make_handler(
    workspace: Path,
    token: str,
    assistant_id: str,
    assistant_name: str,
    demo_mode: bool = False,
    landing_mode: bool = False,
    session_id: Optional[str] = None,
):
    web_root = (Path(__file__).resolve().parent / "web").resolve()

    class AgentCanvasHandler(SimpleHTTPRequestHandler):
        server_version = "AgentCanvas/0.1"

        def log_message(self, fmt: str, *args: Any) -> None:
            return

        def do_OPTIONS(self) -> None:
            self.send_response(HTTPStatus.NO_CONTENT)
            self.send_header("Access-Control-Allow-Origin", "http://localhost")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header(
                "Access-Control-Allow-Headers",
                "Authorization, Content-Type, X-AgentCanvas-Token",
            )
            self.end_headers()

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path.startswith("/api/"):
                self.handle_api_get(parsed)
                return
            self.serve_static(parsed.path)

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path.startswith("/api/"):
                self.handle_api_post(parsed)
                return
            self.write_json(
                {"ok": False, "error": "not found"},
                status=HTTPStatus.NOT_FOUND,
            )

        def handle_api_get(self, parsed) -> None:
            if not self.authorized(parsed):
                self.write_json(
                    {"ok": False, "error": "missing or invalid token"},
                    status=HTTPStatus.UNAUTHORIZED,
                )
                return

            if parsed.path == "/api/graph":
                try:
                    graph = load_ir(workspace)
                except FileNotFoundError:
                    graph = index_workspace(workspace)
                self.write_json({"ok": True, "graph": graph})
                return

            if parsed.path == "/api/canvas":
                canvas = load_or_build_canvas(workspace)
                self.write_json({"ok": True, **canvas})
                return

            if parsed.path == "/api/pending":
                self.write_json({"ok": True, "pending": list_pending(workspace)})
                return

            if parsed.path == "/api/context":
                request_session_id = self.request_session_id(parsed)
                request_demo_mode = self.request_demo_mode(parsed)
                effective_demo_mode = demo_mode or request_demo_mode
                mode = (
                    "landing"
                    if landing_mode and not request_demo_mode
                    else "demo"
                    if effective_demo_mode
                    else "workspace"
                )
                self.write_json(
                    {
                        "ok": True,
                        "context": {
                            "workspace": workspace.name,
                            "workspacePath": "" if mode == "landing" else str(workspace),
                            "assistantId": assistant_id,
                            "assistant": assistant_name,
                            "mode": mode,
                            "isDemo": effective_demo_mode,
                            "demoFixture": workspace.name if effective_demo_mode else None,
                            "sessionId": request_session_id,
                        },
                    }
                )
                return

            self.write_json(
                {"ok": False, "error": "not found"},
                status=HTTPStatus.NOT_FOUND,
            )

        def handle_api_post(self, parsed) -> None:
            if not self.authorized(parsed):
                self.write_json(
                    {"ok": False, "error": "missing or invalid token"},
                    status=HTTPStatus.UNAUTHORIZED,
                )
                return

            if parsed.path == "/api/reindex":
                graph = index_workspace(workspace)
                canvas = build_behavior_canvas(graph, workspace=workspace)
                save_canvas_ir(workspace, canvas)
                self.write_json(
                    {
                        "ok": True,
                        "graph": graph,
                        "canvas": canvas.get("canvas"),
                        "mapping": canvas.get("mapping"),
                        "summary": graph["summary"],
                    }
                )
                return

            if parsed.path == "/api/changes":
                payload = self.read_json_body()
                if payload is None:
                    return
                try:
                    graph = load_ir(workspace)
                except FileNotFoundError:
                    graph = index_workspace(workspace)
                try:
                    pending = write_pending_change(
                        workspace,
                        payload,
                        graph,
                        session_id=self.request_session_id(parsed, payload),
                    )
                except ValueError as exc:
                    self.write_json(
                        {"ok": False, "error": str(exc)},
                        status=HTTPStatus.BAD_REQUEST,
                    )
                    return
                self.write_json(
                    {"ok": True, "pending": pending},
                    status=HTTPStatus.CREATED,
                )
                return

            if parsed.path == "/api/status":
                payload = self.read_json_body()
                if payload is None:
                    return
                pending_id = payload.get("id") or payload.get("pendingId")
                status = payload.get("status")
                note = payload.get("note")
                if not isinstance(pending_id, str) or not isinstance(status, str):
                    self.write_json(
                        {"ok": False, "error": "id and status are required"},
                        status=HTTPStatus.BAD_REQUEST,
                    )
                    return
                try:
                    pending = update_pending_status(
                        workspace,
                        pending_id,
                        status,
                        note=note if isinstance(note, str) else None,
                    )
                except (FileNotFoundError, ValueError) as exc:
                    self.write_json(
                        {"ok": False, "error": str(exc)},
                        status=HTTPStatus.BAD_REQUEST,
                    )
                    return
                self.write_json({"ok": True, "pending": pending})
                return

            self.write_json(
                {"ok": False, "error": "not found"},
                status=HTTPStatus.NOT_FOUND,
            )

        def authorized(self, parsed) -> bool:
            query_token = parse_qs(parsed.query).get("token", [None])[0]
            header_token = self.headers.get("X-AgentCanvas-Token")
            auth = self.headers.get("Authorization", "")
            bearer_token = None
            if auth.startswith("Bearer "):
                bearer_token = auth[len("Bearer ") :].strip()
            return token in {query_token, header_token, bearer_token}

        def request_session_id(
            self,
            parsed,
            payload: Optional[Dict[str, Any]] = None,
        ) -> Optional[str]:
            query = parse_qs(parsed.query)
            values = [
                *(query.get("sessionId") or []),
                *(query.get("session_id") or []),
            ]
            if payload:
                for key in ["sessionId", "session_id"]:
                    value = payload.get(key)
                    if isinstance(value, str):
                        values.append(value)
            values.append(session_id)
            for value in values:
                if isinstance(value, str) and value.strip():
                    return value.strip()
            return None

        def request_demo_mode(self, parsed) -> bool:
            value = parse_qs(parsed.query).get("demo", [""])[0]
            return value.lower() in {"1", "true", "yes"}

        def read_json_body(self) -> Optional[Dict[str, Any]]:
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                length = 0

            if length <= 0:
                self.write_json(
                    {"ok": False, "error": "request body must be JSON"},
                    status=HTTPStatus.BAD_REQUEST,
                )
                return None

            try:
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                self.write_json(
                    {"ok": False, "error": "invalid JSON request body"},
                    status=HTTPStatus.BAD_REQUEST,
                )
                return None

            if not isinstance(payload, dict):
                self.write_json(
                    {"ok": False, "error": "request body must be a JSON object"},
                    status=HTTPStatus.BAD_REQUEST,
                )
                return None
            return payload

        def serve_static(self, request_path: str) -> None:
            path = unquote(request_path.split("?", 1)[0])
            if path in {"", "/"}:
                path = "/index.html"
            relative = path.lstrip("/")
            candidate = (web_root / relative).resolve()

            try:
                candidate.relative_to(web_root)
            except ValueError:
                self.send_error(HTTPStatus.NOT_FOUND)
                return

            if not candidate.exists() or not candidate.is_file():
                candidate = web_root / "index.html"

            content_type = mimetypes.guess_type(str(candidate))[0] or "application/octet-stream"
            data = candidate.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def write_json(
            self,
            payload: Dict[str, Any],
            status: HTTPStatus = HTTPStatus.OK,
        ) -> None:
            data = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    return AgentCanvasHandler
