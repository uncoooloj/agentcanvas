"""Local HTTP server for the AgentCanvas browser app."""

from __future__ import annotations

import json
import mimetypes
import secrets
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import parse_qs, unquote, urlparse

from .indexer import index_workspace
from .ir import list_pending, load_ir, resolve_workspace, state_paths, write_pending_change


def run_server(
    workspace: str | Path,
    host: str = "127.0.0.1",
    port: int = 8765,
    token: Optional[str] = None,
) -> None:
    root = resolve_workspace(workspace)
    token = token or secrets.token_urlsafe(24)
    ensure_ir(root)
    handler_class = make_handler(root, token)
    httpd = ThreadingHTTPServer((host, port), handler_class)
    actual_host, actual_port = httpd.server_address[:2]
    display_host = "127.0.0.1" if actual_host in {"0.0.0.0", "::"} else actual_host
    url = f"http://{display_host}:{actual_port}/?token={token}"

    print(f"AgentCanvas serving {root}", flush=True)
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


def make_handler(workspace: Path, token: str):
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

            if parsed.path == "/api/pending":
                self.write_json({"ok": True, "pending": list_pending(workspace)})
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
                self.write_json({"ok": True, "graph": graph, "summary": graph["summary"]})
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
                    pending = write_pending_change(workspace, payload, graph)
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
