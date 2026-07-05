"""Portable workspace-scoped write lock for AgentCanvas state files."""

from __future__ import annotations

import errno
import json
import os
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional


STATE_DIR_NAME = ".agentcanvas"
WORKSPACE_LOCK_FILENAME = "workspace.lock"
WORKSPACE_LOCK_BREAKS_FILENAME = "workspace-lock.breaks.jsonl"
DEFAULT_LOCK_LEASE_SECONDS = 30.0
DEFAULT_LOCK_TIMEOUT_SECONDS = 10.0
_POLL_INITIAL_SECONDS = 0.01
_POLL_MAX_SECONDS = 0.10
_thread_state = threading.local()


class WorkspaceLockBusy(ValueError):
    """Raised when the workspace write lock cannot be acquired in time."""

    code = "WORKSPACE_BUSY"

    def __init__(
        self,
        message: str,
        *,
        writer: str,
        lock_path: Path,
        timeout_seconds: float,
        holder: Optional[Mapping[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.writer = writer
        self.lock_path = lock_path
        self.timeout_seconds = timeout_seconds
        self.holder = dict(holder or {})
        self.details = {
            "writer": writer,
            "lock_path": str(lock_path),
            "timeout_seconds": timeout_seconds,
            "retryable": True,
            "holder": self.holder,
            "repair_hint": "Another AgentCanvas writer is updating this workspace; retry the request shortly.",
        }


class WorkspaceWriteLock:
    """Exclusive lock implemented with ``O_CREAT|O_EXCL`` lock-file creation."""

    def __init__(
        self,
        workspace: str | Path,
        *,
        writer: str,
        timeout: Optional[float] = None,
        lease_seconds: float = DEFAULT_LOCK_LEASE_SECONDS,
    ) -> None:
        self.root = Path(workspace).expanduser().resolve()
        self.writer = writer
        self.timeout = DEFAULT_LOCK_TIMEOUT_SECONDS if timeout is None else float(timeout)
        self.lease_seconds = float(lease_seconds)
        self.nonce = uuid.uuid4().hex
        self.lock_path = workspace_lock_path(self.root)
        self.break_events: List[Dict[str, Any]] = []
        self._physical_lock = False

    def __enter__(self) -> "WorkspaceWriteLock":
        held = _held_lock_counts()
        root_key = str(self.root)
        if held.get(root_key, 0) > 0:
            held[root_key] += 1
            self.break_events = _lock_break_events().setdefault(root_key, [])
            return self

        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + max(0.0, self.timeout)
        poll_seconds = _POLL_INITIAL_SECONDS
        last_holder: Optional[Dict[str, Any]] = None
        while True:
            try:
                self._create_lock_file()
            except FileExistsError:
                holder = _read_json_object(self.lock_path)
                last_holder = holder if isinstance(holder, dict) else None
                if is_stale_process_claim(
                    holder,
                    lease_seconds=self.lease_seconds,
                    path=self.lock_path,
                ):
                    event = self._break_stale_lock(holder)
                    self.break_events.append(event)
                    _record_lock_break(self.root, event)
                    continue
                if time.monotonic() >= deadline:
                    raise WorkspaceLockBusy(
                        "workspace is busy with another AgentCanvas writer",
                        writer=self.writer,
                        lock_path=self.lock_path,
                        timeout_seconds=self.timeout,
                        holder=last_holder,
                    )
                time.sleep(min(poll_seconds, max(0.0, deadline - time.monotonic())))
                poll_seconds = min(_POLL_MAX_SECONDS, poll_seconds * 1.5)
                continue

            self._physical_lock = True
            held[root_key] = 1
            _lock_break_events()[root_key] = self.break_events
            return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        held = _held_lock_counts()
        root_key = str(self.root)
        depth = held.get(root_key, 0)
        if depth > 1:
            held[root_key] = depth - 1
            return
        held.pop(root_key, None)
        _lock_break_events().pop(root_key, None)
        if self._physical_lock:
            self._release_lock_file()

    def _create_lock_file(self) -> None:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        fd = os.open(str(self.lock_path), flags, 0o644)
        try:
            payload = {
                "schema": "agentcanvas.workspace_lock.v1",
                "pid": os.getpid(),
                "acquired_at": now_utc(),
                "acquired_at_epoch": time.time(),
                "writer": self.writer,
                "nonce": self.nonce,
            }
            os.write(fd, (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8"))
        finally:
            os.close(fd)

    def _break_stale_lock(self, holder: Any) -> Dict[str, Any]:
        event = {
            "schema": "agentcanvas.workspace_lock_break.v1",
            "at": now_utc(),
            "at_epoch": time.time(),
            "breaker_pid": os.getpid(),
            "breaker_writer": self.writer,
            "lock_path": str(self.lock_path),
            "stale_holder": holder if isinstance(holder, Mapping) else None,
        }
        try:
            self.lock_path.unlink()
        except FileNotFoundError:
            pass
        return event

    def _release_lock_file(self) -> None:
        holder = _read_json_object(self.lock_path)
        if not isinstance(holder, Mapping):
            return
        if holder.get("pid") != os.getpid() or holder.get("nonce") != self.nonce:
            return
        try:
            self.lock_path.unlink()
        except FileNotFoundError:
            pass


def workspace_write_lock(
    workspace: str | Path,
    *,
    writer: str,
    timeout: Optional[float] = None,
    lease_seconds: float = DEFAULT_LOCK_LEASE_SECONDS,
) -> WorkspaceWriteLock:
    if timeout is None:
        timeout = _env_float("AGENTCANVAS_LOCK_TIMEOUT_SECONDS", DEFAULT_LOCK_TIMEOUT_SECONDS)
    lease_seconds = _env_float("AGENTCANVAS_LOCK_LEASE_SECONDS", lease_seconds)
    return WorkspaceWriteLock(
        workspace,
        writer=writer,
        timeout=timeout,
        lease_seconds=lease_seconds,
    )


WorkspaceBusyError = WorkspaceLockBusy


def workspace_lock(
    workspace: str | Path,
    *,
    writer: str = "agentcanvas",
    timeout_seconds: Optional[float] = None,
    lease_seconds: Optional[float] = None,
    poll_seconds: float = _POLL_INITIAL_SECONDS,
) -> WorkspaceWriteLock:
    del poll_seconds
    return workspace_write_lock(
        workspace,
        writer=writer,
        timeout=timeout_seconds,
        lease_seconds=DEFAULT_LOCK_LEASE_SECONDS if lease_seconds is None else lease_seconds,
    )


def pid_is_dead(value: Any) -> bool:
    try:
        pid = int(value)
    except (TypeError, ValueError):
        return True
    return not process_is_alive(pid)


def workspace_lock_path(workspace: str | Path) -> Path:
    root = Path(workspace).expanduser().resolve()
    return root / STATE_DIR_NAME / WORKSPACE_LOCK_FILENAME


def workspace_lock_held(workspace: str | Path) -> bool:
    root = Path(workspace).expanduser().resolve()
    return _held_lock_counts().get(str(root), 0) > 0


def current_lock_break_events(workspace: str | Path) -> List[Dict[str, Any]]:
    root = Path(workspace).expanduser().resolve()
    events = _lock_break_events().get(str(root), [])
    return [dict(event) for event in events]


def is_stale_process_claim(
    claim: Any,
    *,
    lease_seconds: float = DEFAULT_LOCK_LEASE_SECONDS,
    path: Optional[Path] = None,
    now_epoch: Optional[float] = None,
) -> bool:
    now_value = time.time() if now_epoch is None else float(now_epoch)
    acquired_epoch = _claim_epoch(claim)
    if acquired_epoch is None and path is not None:
        try:
            acquired_epoch = path.stat().st_mtime
        except OSError:
            acquired_epoch = None
    if acquired_epoch is None or now_value - acquired_epoch <= lease_seconds:
        return False
    pid = _claim_pid(claim)
    if pid is None:
        return True
    return not process_is_alive(pid)


def process_is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if pid == os.getpid():
        return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError as exc:
        return exc.errno != errno.ESRCH
    return True


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _record_lock_break(root: Path, event: Mapping[str, Any]) -> None:
    history_dir = root / STATE_DIR_NAME / "history"
    history_dir.mkdir(parents=True, exist_ok=True)
    path = history_dir / WORKSPACE_LOCK_BREAKS_FILENAME
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(dict(event), sort_keys=True) + "\n")


def _claim_epoch(claim: Any) -> Optional[float]:
    if not isinstance(claim, Mapping):
        return None
    for key in ("acquired_at_epoch", "started_at_epoch", "created_at_epoch"):
        value = claim.get(key)
        if isinstance(value, (int, float)):
            return float(value)
    for key in ("acquired_at", "started_at", "created_at"):
        value = claim.get(key)
        if isinstance(value, str):
            parsed = _parse_iso_epoch(value)
            if parsed is not None:
                return parsed
    return None


def _claim_pid(claim: Any) -> Optional[int]:
    if not isinstance(claim, Mapping):
        return None
    try:
        return int(claim.get("pid"))
    except (TypeError, ValueError):
        return None


def _parse_iso_epoch(value: str) -> Optional[float]:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _env_float(name: str, fallback: float) -> float:
    raw = os.environ.get(name)
    if raw:
        try:
            return float(raw)
        except ValueError:
            pass
    return float(fallback)


def _read_json_object(path: Path) -> Optional[Dict[str, Any]]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _held_lock_counts() -> Dict[str, int]:
    held = getattr(_thread_state, "held_counts", None)
    if held is None:
        held = {}
        _thread_state.held_counts = held
    return held


def _lock_break_events() -> Dict[str, List[Dict[str, Any]]]:
    events = getattr(_thread_state, "break_events", None)
    if events is None:
        events = {}
        _thread_state.break_events = events
    return events
