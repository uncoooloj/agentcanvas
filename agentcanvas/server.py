"""Local HTTP server for the AgentCanvas browser app."""

from __future__ import annotations

from copy import deepcopy
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
    canvas_map_handoff,
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
from .core.behavior_canvas import (
    build_behavior_canvas,
    canvas_source_metadata,
)
from .core.workspace_profile import infer_workspace_profile


# Known coding-agent platforms that may launch AgentCanvas, with human labels.
_ASSISTANTS = {
    "claude-code": "Claude Code",
    "codex": "Codex",
    "cursor": "Cursor",
    "antigravity": "Antigravity",
    "generic": "Your assistant",
}
DEMO_MARKER_FILENAME = ".agentcanvas-demo"


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


def load_or_build_canvas(
    workspace: Path,
    *,
    refresh: bool = False,
    demo_mode: bool = False,
    demo_fallback: bool = False,
) -> Dict[str, Any]:
    demo_content = demo_mode or demo_fallback or is_demo_workspace(workspace)
    if not refresh:
        try:
            canvas = load_canvas_ir(workspace)
            if is_agent_authored_canvas(canvas):
                return with_workspace_profile(
                    workspace,
                    with_runtime_source_status(
                        preserve_agent_authored_canvas(workspace, canvas),
                        demo_content=demo_content,
                        demo_fallback=demo_fallback,
                    ),
                )
            if canvas_cache_is_fresh(workspace):
                return with_workspace_profile(
                    workspace,
                    with_runtime_source_status(
                        canvas,
                        demo_content=demo_content,
                        demo_fallback=demo_fallback,
                    ),
                )
        except FileNotFoundError:
            pass
    try:
        graph = load_ir(workspace)
    except FileNotFoundError:
        graph = index_workspace(workspace)
    canvas = build_behavior_canvas(graph, workspace=workspace, is_demo=demo_content)
    canvas = with_runtime_source_status(
        canvas,
        demo_content=demo_content,
        demo_fallback=demo_fallback,
    )
    save_canvas_ir(workspace, canvas)
    return with_workspace_profile(workspace, canvas)


def is_agent_authored_canvas(canvas: Dict[str, Any]) -> bool:
    mapping = canvas.get("mapping") if isinstance(canvas.get("mapping"), dict) else {}
    if mapping.get("mode") == "agent-authored":
        return True
    source = mapping.get("source") if isinstance(mapping.get("source"), dict) else {}
    if source.get("kind") == "agent-authored":
        return True
    body = canvas.get("canvas") if isinstance(canvas.get("canvas"), dict) else canvas
    metadata = body.get("metadata") if isinstance(body.get("metadata"), dict) else {}
    source = metadata.get("source") if isinstance(metadata.get("source"), dict) else {}
    if source.get("kind") == "agent-authored":
        return True
    projection = metadata.get("projection") if isinstance(metadata.get("projection"), dict) else {}
    if projection.get("mode") == "agent-authored":
        return True
    return False


def preserve_agent_authored_canvas(workspace: Path, canvas: Dict[str, Any]) -> Dict[str, Any]:
    if canvas_cache_is_fresh(workspace):
        return canvas
    warning = (
        "Workspace evidence was refreshed after this agent-authored canvas. "
        "AgentCanvas kept the canvas file; ask the connected agent to refresh the map if behavior changed."
    )
    return with_runtime_source_status(
        with_canvas_warning(canvas, warning),
        stale=True,
        stale_reason=warning,
    )


def with_canvas_warning(canvas: Dict[str, Any], warning: str) -> Dict[str, Any]:
    next_canvas = deepcopy(canvas)
    mapping = next_canvas.setdefault("mapping", {})
    if isinstance(mapping, dict):
        warnings = mapping.setdefault("warnings", [])
        if isinstance(warnings, list) and warning not in warnings:
            warnings.append(warning)
    body = next_canvas.get("canvas") if isinstance(next_canvas.get("canvas"), dict) else next_canvas
    metadata = body.setdefault("metadata", {})
    if isinstance(metadata, dict):
        projection = metadata.setdefault("projection", {})
        if isinstance(projection, dict):
            warnings = projection.setdefault("warnings", [])
            if isinstance(warnings, list) and warning not in warnings:
                warnings.append(warning)
    return next_canvas


def canvas_cache_is_fresh(workspace: Path) -> bool:
    _, ir_path, _ = state_paths(workspace)
    path = canvas_ir_path(workspace)
    if not path.exists():
        return False
    if not ir_path.exists():
        return True
    return path.stat().st_mtime >= ir_path.stat().st_mtime


def is_demo_workspace(workspace: Path) -> bool:
    return (workspace / DEMO_MARKER_FILENAME).exists()


def canvas_runtime_source(
    workspace: Path,
    *,
    demo_mode: bool = False,
    landing_mode: bool = False,
    request_demo_mode: bool = False,
) -> Dict[str, Any]:
    demo_fallback = landing_mode and not request_demo_mode and is_demo_workspace(workspace)
    demo_content = demo_mode or request_demo_mode or demo_fallback or is_demo_workspace(workspace)
    if demo_fallback:
        kind = "demo-fallback"
        status = "demo_fallback"
        reason = "launch_page_without_workspace"
    elif demo_content:
        kind = "demo"
        status = "demo"
        reason = "requested_demo_workspace" if (demo_mode or request_demo_mode) else "demo_workspace"
    else:
        kind = "workspace"
        status = "workspace"
        reason = None
    return {
        "kind": kind,
        "status": status,
        "demoContent": demo_content,
        "demoFallback": demo_fallback,
        "demoFixture": workspace.name if demo_content else None,
        "reason": reason,
    }


def with_runtime_source_status(
    canvas: Dict[str, Any],
    *,
    demo_content: bool = False,
    demo_fallback: bool = False,
    stale: bool = False,
    stale_reason: Optional[str] = None,
) -> Dict[str, Any]:
    next_canvas = deepcopy(canvas)
    body = next_canvas.get("canvas") if isinstance(next_canvas.get("canvas"), dict) else next_canvas
    mapping = next_canvas.setdefault("mapping", {})
    if not isinstance(mapping, dict):
        mapping = {}
        next_canvas["mapping"] = mapping
    metadata = body.setdefault("metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}
        body["metadata"] = metadata

    existing_source = metadata.get("source") if isinstance(metadata.get("source"), dict) else {}
    existing_kind = str(existing_source.get("kind") or mapping.get("mode") or "heuristic-projection")
    if existing_kind == "deterministic":
        existing_kind = "heuristic-projection"
    existing_status = str(mapping.get("status") or existing_source.get("status") or "ready")
    existing_empty = bool(existing_source.get("isEmpty") or mapping.get("empty"))
    existing_stale = bool(existing_source.get("isStale") or mapping.get("stale"))
    effective_stale = stale or existing_stale

    kind = existing_kind
    status = existing_status
    reason = str(existing_source.get("reason")) if existing_source.get("reason") else None
    is_fallback = bool(existing_source.get("isFallback"))
    if demo_fallback:
        kind = "demo-fallback"
        status = "demo_fallback"
        reason = "launch_page_without_workspace"
        is_fallback = True
    elif demo_content and kind not in {"agent-authored", "empty"}:
        kind = "demo"
        status = "demo"
        reason = reason or "demo_workspace"
    if effective_stale:
        status = "stale_cache"
        reason = stale_reason or reason

    source = canvas_source_metadata(
        kind,
        status,
        is_demo_content=demo_content,
        is_fallback=is_fallback,
        is_stale=effective_stale,
        is_empty=existing_empty,
        flow_count=0 if existing_empty else len(body.get("journeys") or []),
        reason=reason,
    )
    metadata["source"] = source
    body["isDemo"] = bool(body.get("isDemo") or demo_content)
    mapping["status"] = status
    mapping["mode"] = kind
    mapping["source"] = source
    mapping["stale"] = effective_stale
    mapping["empty"] = existing_empty
    mapping["demoFallback"] = demo_fallback
    mapping.setdefault("displayFlowCount", len(body.get("journeys") or []))
    if existing_empty:
        mapping["flowCount"] = 0
    projection = metadata.get("projection") if isinstance(metadata.get("projection"), dict) else {}
    if projection:
        projection["source_status"] = status
        projection["source_kind"] = kind
    return next_canvas


def load_workspace_profile(workspace: Path) -> Dict[str, Any]:
    try:
        graph = load_ir(workspace)
    except FileNotFoundError:
        graph = None
    return infer_workspace_profile(graph, workspace=workspace)


def with_workspace_profile(workspace: Path, canvas: Dict[str, Any]) -> Dict[str, Any]:
    body = canvas.get("canvas") if isinstance(canvas.get("canvas"), dict) else canvas
    metadata = body.get("metadata") if isinstance(body.get("metadata"), dict) else {}
    if isinstance(metadata.get("workspace_profile"), dict):
        return canvas

    next_canvas = deepcopy(canvas)
    next_body = (
        next_canvas.get("canvas")
        if isinstance(next_canvas.get("canvas"), dict)
        else next_canvas
    )
    next_body.setdefault("metadata", {})["workspace_profile"] = load_workspace_profile(workspace)
    return next_canvas


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
                request_demo_mode = self.request_demo_mode(parsed)
                source = canvas_runtime_source(
                    workspace,
                    demo_mode=demo_mode,
                    landing_mode=landing_mode,
                    request_demo_mode=request_demo_mode,
                )
                canvas = load_or_build_canvas(
                    workspace,
                    demo_mode=source["demoContent"],
                    demo_fallback=source["demoFallback"],
                )
                self.write_json({"ok": True, **canvas})
                return

            if parsed.path == "/api/pending":
                self.write_json({"ok": True, "pending": list_pending(workspace)})
                return

            if parsed.path == "/api/context":
                request_session_id = self.request_session_id(parsed)
                request_demo_mode = self.request_demo_mode(parsed)
                effective_demo_mode = demo_mode or request_demo_mode
                source = canvas_runtime_source(
                    workspace,
                    demo_mode=demo_mode,
                    landing_mode=landing_mode,
                    request_demo_mode=request_demo_mode,
                )
                workspace_profile = load_workspace_profile(workspace)
                mode = (
                    "landing"
                    if landing_mode and not request_demo_mode
                    else "demo"
                    if effective_demo_mode
                    else "workspace"
                )
                canvas_handoff = canvas_map_handoff(workspace)
                if mode == "landing":
                    canvas_handoff = {
                        **canvas_handoff,
                        "readable": False,
                        "needsAuthoring": False,
                        "reason": "workspace_not_selected",
                        "workspacePath": "",
                        "outputPath": "",
                        "instruction": None,
                    }
                self.write_json(
                    {
                        "ok": True,
                        "context": {
                            "workspace": workspace.name,
                            "workspacePath": "" if mode == "landing" else str(workspace),
                            "workspaceKind": workspace_profile["kind"],
                            "workspaceProfile": workspace_profile,
                            "productLanguage": workspace_profile["product_language"],
                            "assistantId": assistant_id,
                            "assistant": assistant_name,
                            "mode": mode,
                            "isDemo": effective_demo_mode,
                            "isDemoContent": source["demoContent"],
                            "demoFallback": source["demoFallback"],
                            "demoFixture": source["demoFixture"],
                            "source": source,
                            "sessionId": request_session_id,
                            "handoff": {
                                "schema": "agentcanvas.handoff.v1",
                                "canvasMap": canvas_handoff,
                            },
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
                request_demo_mode = self.request_demo_mode(parsed)
                source = canvas_runtime_source(
                    workspace,
                    demo_mode=demo_mode,
                    landing_mode=landing_mode,
                    request_demo_mode=request_demo_mode,
                )
                graph = index_workspace(workspace)
                try:
                    existing_canvas = load_canvas_ir(workspace)
                except FileNotFoundError:
                    existing_canvas = None
                if existing_canvas and is_agent_authored_canvas(existing_canvas):
                    canvas = with_runtime_source_status(
                        preserve_agent_authored_canvas(workspace, existing_canvas),
                        demo_content=source["demoContent"],
                        demo_fallback=source["demoFallback"],
                    )
                else:
                    canvas = build_behavior_canvas(
                        graph,
                        workspace=workspace,
                        is_demo=source["demoContent"],
                    )
                    canvas = with_runtime_source_status(
                        canvas,
                        demo_content=source["demoContent"],
                        demo_fallback=source["demoFallback"],
                    )
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
