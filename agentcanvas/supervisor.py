"""Detached local server supervisor for `agentcanvas up`."""

from __future__ import annotations

import json
import errno
import os
import secrets
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlencode

from . import __version__
from .ir import ensure_state_dirs, now_utc, resolve_workspace
from .server import server_heartbeat_path, token_hint


LAUNCH_RECORD_FILENAME = "launch.json"
SERVER_LOG_FILENAME = "server.log"
SUPERVISED_ENV = "AGENTCANVAS_SUPERVISED"
TOKEN_ENV = "AGENTCANVAS_SERVER_TOKEN"
READY_TIMEOUT_SECONDS = 15.0
HEARTBEAT_REUSE_MAX_AGE_SECONDS = 45.0
STOP_TIMEOUT_SECONDS = 5.0
LOOPBACK_HOSTS = {"127.0.0.1", "localhost"}


class SupervisorError(RuntimeError):
    def __init__(self, code: str, message: str, *, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": False,
            "error": {
                "code": self.code,
                "message": self.message,
                "details": self.details,
            },
        }


def launch_record_path(workspace: str | Path) -> Path:
    state_dir, _ir_path, _pending_dir = ensure_state_dirs(resolve_workspace(workspace))
    return state_dir / LAUNCH_RECORD_FILENAME


def server_log_path(workspace: str | Path) -> Path:
    state_dir, _ir_path, _pending_dir = ensure_state_dirs(resolve_workspace(workspace))
    return state_dir / SERVER_LOG_FILENAME


def ensure_server_up(
    workspace: str | Path,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    port_end: int = 8865,
    agent: Optional[str] = None,
    session_id: Optional[str] = None,
    open_browser: bool = False,
) -> Dict[str, Any]:
    validate_loopback_host(host)
    root = resolve_workspace(workspace)
    record = read_launch_record(root)
    live = validate_launch_record(record, workspace=root) if record else None
    if live:
        result = {
            **live,
            "ok": True,
            "already_running": True,
        }
        if open_browser:
            webbrowser.open(result["url"])
        return result

    if record:
        remove_launch_record(root)

    selected_port = choose_port(host, port, port_end)
    token = secrets.token_urlsafe(24)
    child = spawn_server(
        root,
        host=host,
        port=selected_port,
        token=token,
        agent=agent,
        session_id=session_id,
    )
    url = launch_url(host, selected_port, token, session_id=session_id)
    record = {
        "schema": "agentcanvas.launch.v1",
        "pid": child.pid,
        "host": host,
        "port": selected_port,
        "token": token,
        "url": url,
        "started_at": now_utc(),
        "version": __version__,
        "session_id": session_id,
        "agent": agent,
        "workspace": str(root),
    }

    try:
        wait_until_ready(record, workspace=root, timeout_seconds=READY_TIMEOUT_SECONDS)
    except SupervisorError as exc:
        terminate_pid(child.pid)
        raise SupervisorError(
            exc.code,
            exc.message,
            details={
                **exc.details,
                "log": tail_server_log(root),
            },
        )

    write_launch_record(root, record)
    result = {
        **record,
        "ok": True,
        "already_running": False,
    }
    if open_browser:
        webbrowser.open(url)
    return result


def stop_server(workspace: str | Path) -> Dict[str, Any]:
    root = resolve_workspace(workspace)
    record = read_launch_record(root)
    if not record:
        return {"ok": True, "stopped": False, "reason": "not_running"}
    pid = int(record.get("pid") or 0)
    stopped = terminate_pid(pid, wait_seconds=STOP_TIMEOUT_SECONDS) if pid else False
    if stopped:
        remove_launch_record(root)
        remove_server_heartbeat(root)
        return {"ok": True, "stopped": True, "pid": pid}
    return {"ok": False, "stopped": False, "pid": pid, "reason": "still_running"}


def read_launch_record(workspace: str | Path) -> Optional[Dict[str, Any]]:
    path = launch_record_path(workspace)
    if not path.exists():
        return None
    try:
        with path.open(encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def write_launch_record(workspace: str | Path, record: Dict[str, Any]) -> Path:
    path = launch_record_path(workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    data = json.dumps(record, indent=2, sort_keys=True) + "\n"
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(data)
        tmp.replace(path)
        try:
            path.chmod(0o600)
        except OSError:
            pass
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
    return path


def remove_launch_record(workspace: str | Path) -> None:
    path = launch_record_path(workspace)
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def remove_server_heartbeat(workspace: str | Path) -> None:
    path = server_heartbeat_path(workspace)
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def validate_launch_record(
    record: Optional[Dict[str, Any]],
    *,
    workspace: str | Path | None = None,
) -> Optional[Dict[str, Any]]:
    if not record:
        return None
    pid = int(record.get("pid") or 0)
    port = int(record.get("port") or 0)
    token = record.get("token")
    host = str(record.get("host") or "127.0.0.1")
    if not pid or not port or not isinstance(token, str) or not token:
        return None
    if not is_loopback_host(host):
        return None
    if not pid_is_alive(pid):
        return None
    if workspace is not None and not heartbeat_is_fresh(workspace, record):
        return None
    url = str(record.get("url") or launch_url(host, port, token, session_id=record.get("session_id")))
    health_url = api_url(host, port, "/api/health", token, session_id=record.get("session_id"))
    try:
        with urllib.request.urlopen(health_url, timeout=2) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or not payload.get("ok"):
        return None
    return {
        "pid": pid,
        "host": host,
        "port": port,
        "token": token,
        "url": url,
        "session_id": record.get("session_id"),
        "agent": record.get("agent"),
        "version": record.get("version"),
    }


def wait_until_ready(record: Dict[str, Any], *, workspace: str | Path, timeout_seconds: float) -> None:
    deadline = time.time() + timeout_seconds
    last_error = "server did not respond"
    while time.time() < deadline:
        live = validate_launch_record(record, workspace=workspace)
        if live:
            return
        last_error = "health check or heartbeat did not pass yet"
        time.sleep(0.2)
    raise SupervisorError("READY_TIMEOUT", "AgentCanvas server did not become ready in time", details={"last_error": last_error})


def spawn_server(
    workspace: Path,
    *,
    host: str,
    port: int,
    token: str,
    agent: Optional[str],
    session_id: Optional[str],
) -> subprocess.Popen:
    log_path = server_log_path(workspace)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    args = [
        sys.executable,
        "-m",
        "agentcanvas",
        "start",
        str(workspace),
        "--host",
        host,
        "--port",
        str(port),
    ]
    if agent:
        args.extend(["--agent", agent])
    if session_id:
        args.extend(["--session-id", session_id])
    env = os.environ.copy()
    env[TOKEN_ENV] = token
    env[SUPERVISED_ENV] = "1"
    env["PYTHONPATH"] = prepend_pythonpath(str(Path(__file__).resolve().parents[1]), env.get("PYTHONPATH"))
    stdout = log_path.open("ab")
    kwargs: Dict[str, Any] = {
        "cwd": str(workspace),
        "env": env,
        "stdout": stdout,
        "stderr": subprocess.STDOUT,
    }
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        kwargs["start_new_session"] = True
    try:
        return subprocess.Popen(args, **kwargs)
    finally:
        stdout.close()


def choose_port(host: str, start: int, end: int) -> int:
    validate_loopback_host(host)
    if start == 0:
        return free_port(host)
    for port in range(int(start), int(end) + 1):
        if port_is_free(host, port):
            return port
    raise SupervisorError("PORT_BUSY", "No free port was found for AgentCanvas", details={"host": host, "start": start, "end": end})


def free_port(host: str) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


def port_is_free(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((host, int(port)))
        except OSError:
            return False
    return True


def pid_is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError as exc:
        return getattr(exc, "errno", None) not in {errno.ESRCH, errno.EINVAL}
    return True


def terminate_pid(pid: int, *, wait_seconds: float = 0) -> bool:
    if not pid_is_alive(pid):
        return True
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return False
    deadline = time.time() + max(0.0, wait_seconds)
    while time.time() < deadline:
        if not pid_is_alive(pid):
            return True
        time.sleep(0.1)
    if wait_seconds <= 0:
        return True
    return not pid_is_alive(pid)


def is_loopback_host(host: str) -> bool:
    return host.strip().lower() in LOOPBACK_HOSTS


def validate_loopback_host(host: str) -> None:
    if is_loopback_host(host):
        return
    raise SupervisorError(
        "NON_LOOPBACK_HOST",
        "agentcanvas up only binds to loopback hosts",
        details={"host": host, "allowed_hosts": sorted(LOOPBACK_HOSTS)},
    )


def heartbeat_is_fresh(
    workspace: str | Path,
    record: Dict[str, Any],
    *,
    max_age_seconds: float = HEARTBEAT_REUSE_MAX_AGE_SECONDS,
) -> bool:
    path = server_heartbeat_path(workspace)
    if not path.is_file():
        return False
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        age_seconds = max(0.0, time.time() - path.stat().st_mtime)
    except (OSError, ValueError):
        return False
    if age_seconds > max_age_seconds:
        return False
    if not isinstance(payload, dict):
        return False
    expected = {
        "schema": "agentcanvas.server_heartbeat.v1",
        "pid": int(record.get("pid") or 0),
        "port": int(record.get("port") or 0),
        "workspace": str(resolve_workspace(workspace)),
        "token_hint": token_hint(str(record.get("token") or "")),
    }
    if str(payload.get("schema")) != expected["schema"]:
        return False
    if int(payload.get("pid") or 0) != expected["pid"]:
        return False
    if int(payload.get("port") or 0) != expected["port"]:
        return False
    if str(payload.get("workspace") or "") != expected["workspace"]:
        return False
    if str(payload.get("token_hint") or "") != expected["token_hint"]:
        return False
    return True


def launch_url(host: str, port: int, token: str, *, session_id: Optional[str] = None) -> str:
    query = {"token": token}
    if session_id:
        query["sessionId"] = session_id
    return f"http://{host}:{int(port)}/?{urlencode(query)}"


def api_url(host: str, port: int, path: str, token: str, *, session_id: Optional[str] = None) -> str:
    query = {"token": token}
    if session_id:
        query["sessionId"] = session_id
    return f"http://{host}:{int(port)}{path}?{urlencode(query)}"


def tail_server_log(workspace: str | Path, *, lines: int = 20) -> str:
    path = server_log_path(workspace)
    if not path.exists():
        return ""
    try:
        content = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    return "\n".join(content[-lines:])


def prepend_pythonpath(path: str, existing: Optional[str]) -> str:
    if not existing:
        return path
    parts = existing.split(os.pathsep)
    if path in parts:
        return existing
    return path + os.pathsep + existing
