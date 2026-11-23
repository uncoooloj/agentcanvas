"""Workspace-confined source previews and Git evidence for Studio."""

from __future__ import annotations

import os
import re
import stat
import subprocess
import tempfile
from pathlib import Path, PureWindowsPath

_GIT_TIMEOUT = 3
_PATCH_LIMIT = 40 * 1024
_PREVIEW_LIMIT = 8 * 1024 * 1024
_PATH_LIST_LIMIT = 1024 * 1024
_SHA = re.compile(r"[a-f0-9]{40}(?:[a-f0-9]{24})?")
_LANGUAGES = {
    ".py": "python", ".js": "javascript", ".jsx": "jsx", ".ts": "typescript", ".tsx": "tsx",
    ".go": "go", ".rs": "rust", ".rb": "ruby", ".php": "php", ".java": "java",
    ".kt": "kotlin", ".swift": "swift", ".dart": "dart", ".json": "json", ".toml": "toml",
    ".yml": "yaml", ".yaml": "yaml", ".html": "html", ".css": "css", ".md": "markdown",
    ".sh": "bash", ".sql": "sql",
}


_INTERNAL_PATH_COMPONENTS = frozenset({".agentcanvas", ".git"})


def _resolve_workspace_path(root: Path, rel_path: str, *, reject_internal: bool) -> Path:
    if not isinstance(rel_path, str) or not rel_path or "\x00" in rel_path:
        raise ValueError("PATH_OUTSIDE_WORKSPACE")
    path = Path(rel_path)
    windows = PureWindowsPath(rel_path)
    # Workspaces can be on case-insensitive filesystems.
    if reject_internal and any(
        parts and parts[0].casefold() in _INTERNAL_PATH_COMPONENTS for parts in (path.parts, windows.parts)
    ):
        raise ValueError("INTERNAL_PATH_FORBIDDEN")
    if path.is_absolute() or windows.drive or windows.root or ".." in windows.parts or ".." in path.parts:
        raise ValueError("PATH_OUTSIDE_WORKSPACE")
    try:
        root = Path(root).resolve()
        candidate = (root / path).resolve()
        relative = candidate.relative_to(root)
    except (OSError, RuntimeError, ValueError) as exc:
        raise ValueError("PATH_OUTSIDE_WORKSPACE") from exc
    if reject_internal and relative.parts and relative.parts[0].casefold() in _INTERNAL_PATH_COMPONENTS:
        raise ValueError("INTERNAL_PATH_FORBIDDEN")
    try:
        current = root
        for component in path.parts:
            current /= component
            if current.is_symlink():
                raise ValueError("PATH_OUTSIDE_WORKSPACE")
    except OSError as exc:
        raise ValueError("PATH_OUTSIDE_WORKSPACE") from exc
    return candidate


def resolve_workspace_path(root: Path, rel_path: str) -> Path:
    """Resolve a confined path for trusted AgentCanvas state access."""
    return _resolve_workspace_path(root, rel_path, reject_internal=False)


def safe_resolve_workspace_file(root: Path, rel_path: str) -> Path:
    """Resolve a source path, rejecting traversal, internal paths, and symlinks."""
    return _resolve_workspace_path(root, rel_path, reject_internal=True)


def _git(root: Path, *args: str, limit: int | None = None, diff_exit: bool = False) -> bytes | None:
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env.update(
        GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull, GIT_OPTIONAL_LOCKS="0",
        GIT_TERMINAL_PROMPT="0", GIT_ATTR_NOSYSTEM="1", GIT_NO_LAZY_FETCH="1", LC_ALL="C",
    )
    command = [
        "git", "--no-pager", "-c", "core.fsmonitor=false", "-c", "core.quotePath=false",
        "-c", "diff.ignoreSubmodules=all",
    ]
    try:
        if args[0] in {"diff", "status"}:
            # Even when textconv and external diff are disabled, Git can run a
            # repository-configured clean filter while hashing working files.
            configured = subprocess.run(
                [*command, "config", "--null", "--name-only", "--get-regexp",
                 r"^filter\..*\.(clean|process|required)$"],
                cwd=root, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, timeout=_GIT_TIMEOUT, check=False,
            )
            if configured.returncode not in {0, 1}:
                return None
            for setting in configured.stdout.split(b"\0"):
                if setting:
                    suffix = "false" if setting.endswith(b".required") else ""
                    command.extend(["-c", os.fsdecode(setting) + "=" + suffix])
        command.extend(args)
        if limit is None:
            result = subprocess.run(
                command, cwd=root, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, timeout=_GIT_TIMEOUT, check=False,
            )
            return result.stdout if result.returncode == 0 else None
        # Spool potentially large patches without retaining all of them in memory.
        with tempfile.TemporaryFile() as output:
            result = subprocess.run(
                command, cwd=root, env=env, stdin=subprocess.DEVNULL, stdout=output,
                stderr=subprocess.DEVNULL, timeout=_GIT_TIMEOUT, check=False,
            )
            if result.returncode != 0 and not (diff_exit and result.returncode == 1):
                return None
            output.seek(0)
            return output.read(limit + 1)
    except (OSError, subprocess.TimeoutExpired):
        return None


def _text(raw: bytes) -> str:
    return raw.decode("utf-8", errors="replace")


def _bounded_text(raw: bytes, limit: int) -> str:
    return _text(raw[:limit]).encode("utf-8")[:limit].decode("utf-8", errors="ignore")


def _has_git_marker(root: Path) -> bool:
    return any((folder / ".git").exists() for folder in (root, *root.parents))


def _workspace_prefix(root: Path) -> str | None:
    output = _git(root, "rev-parse", "--show-toplevel")
    if output is None:
        return None
    try:
        worktree = Path(os.fsdecode(output.removesuffix(b"\n"))).resolve()
        relative = root.resolve().relative_to(worktree)
    except (OSError, RuntimeError, ValueError):
        return None
    return relative.as_posix() + "/" if relative.parts else ""


def _status_entries(root: Path, prefix: str) -> dict[str, str] | None:
    raw = _git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all", "--no-renames",
               "--ignore-submodules=all", "--", ".", limit=_PATH_LIST_LIMIT)
    if raw is None or len(raw) > _PATH_LIST_LIMIT:
        return None
    entries = {}
    for record in raw.split(b"\0"):
        if len(record) < 4:
            continue
        path = os.fsdecode(record[3:])
        if not path.startswith(prefix):
            continue
        relative = path[len(prefix):]
        if relative and relative.split("/", 1)[0] != ".agentcanvas":
            entries[relative] = _text(record[:2])
    return entries


def get_git_status(root: Path) -> dict:
    prefix = _workspace_prefix(root)
    if prefix is None:
        empty = {"branch": None, "head": None, "dirty": False, "changed_files": []}
        return {**empty, "error": "GIT_STATUS_UNAVAILABLE"} if _has_git_marker(root) else empty
    branch = _git(root, "symbolic-ref", "--quiet", "--short", "HEAD")
    head = _git(root, "rev-parse", "--verify", "HEAD")
    changed = _status_entries(root, prefix)
    status = {
        "branch": _text(branch).rstrip("\n") if branch else None,
        "head": _text(head).rstrip("\n") if head else None,
        "dirty": bool(changed),
        "changed_files": sorted(changed or {}),
    }
    if changed is None:
        status["error"] = "GIT_STATUS_UNAVAILABLE"
    return status


def _resolve_ref(root: Path, ref: str) -> str | None:
    if not ref or ref.startswith("-") or "\x00" in ref or len(ref) > 1024:
        return None
    output = _git(root, "rev-parse", "--verify", "--quiet", "--end-of-options", ref + "^{commit}")
    revision = _text(output).strip() if output else ""
    return revision if _SHA.fullmatch(revision) else None


def _resolve_base(root: Path, base: str | None) -> str | None:
    if base and ".." in base:
        separator = "..." if "..." in base else ".."
        before, after = base.split(separator, 1)
        left = _resolve_ref(root, before or "HEAD")
        right = _resolve_ref(root, after or "HEAD")
        return left + separator + right if left and right else None
    if base:
        return _resolve_ref(root, base)
    head = _resolve_ref(root, "HEAD")
    if head:
        return head
    # Git recognizes its empty tree object even before the first commit.
    empty = _git(root, "hash-object", "-t", "tree", "--stdin")
    return _text(empty).strip() if empty else None


def compute_stale_node_ids(root: Path, doc: dict, *, git_status: dict | None = None) -> list[str]:
    if not doc.get("flows"):
        return []
    status = git_status if git_status is not None else get_git_status(root)
    changed = set(status["changed_files"])
    previous, head = doc.get("git_head"), status["head"]
    if isinstance(previous, str) and previous != head and head:
        resolved = _resolve_ref(root, previous)
        if resolved:
            names = _git(root, "diff", "--relative", "--no-renames", "--name-only", "-z",
                         resolved, head, "--", ".", ":(exclude).agentcanvas", limit=_PATH_LIST_LIMIT)
            if names is not None:
                changed.update(os.fsdecode(name) for name in names.rsplit(b"\0", 1)[0].split(b"\0") if name)
    if not changed:
        return []
    return list(dict.fromkeys(
        node["id"]
        for flow in doc["flows"]
        for node in flow["nodes"]
        if any(Path(ref["path"]).as_posix() in changed for ref in node["code_refs"])
    ))


def read_file_slice(root: Path, rel_path: str, line: int | None = None, context: int = 12) -> dict:
    candidate = safe_resolve_workspace_file(root, rel_path)
    if line is not None and (type(line) is not int or line < 1):
        raise ValueError("line must be a positive integer")
    if type(context) is not int or context < 0:
        raise ValueError("context must be a non-negative integer")
    path = Path(rel_path).as_posix()
    try:
        descriptor = os.open(candidate, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
        with os.fdopen(descriptor, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                return {"ok": False, "path": path, "error": "FILE_NOT_FOUND"}
            raw = stream.read(_PREVIEW_LIMIT + 1)
    except (FileNotFoundError, IsADirectoryError, NotADirectoryError):
        return {"ok": False, "path": path, "error": "FILE_NOT_FOUND"}
    except OSError:
        return {"ok": False, "path": path, "error": "FILE_UNREADABLE"}
    if b"\0" in raw:
        return {"ok": False, "path": path, "error": "BINARY_FILE"}
    try:
        content = raw[:_PREVIEW_LIMIT].decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        if len(raw) <= _PREVIEW_LIMIT or exc.start < _PREVIEW_LIMIT - 3:
            return {"ok": False, "path": path, "error": "BINARY_FILE"}
        content = raw[:exc.start].decode("utf-8-sig")
    # splitlines recognizes Unicode formatting characters as line breaks. Source
    # locations use actual newline bytes, including CRLF line endings.
    lines = content.split("\n") if content else []
    if lines and lines[-1] == "":
        lines.pop()
    if line is not None and line > len(lines) and len(raw) > _PREVIEW_LIMIT:
        return {"ok": False, "path": path, "error": "LINE_OUTSIDE_PREVIEW"}
    highlight = min(line, len(lines)) if line is not None and lines else None
    start = max(1, (highlight or 1) - min(context, 59))
    end = min(len(lines), (highlight or 1) + min(context, 60))
    return {
        "ok": True, "path": path, "start_line": start, "end_line": end,
        "highlight_line": highlight,
        "lines": [{"number": number, "text": lines[number - 1].removesuffix("\r")[:4096]}
                  for number in range(start, end + 1)],
        "language": _LANGUAGES.get(candidate.suffix.lower(), "text"),
        "absolute_path": str(candidate),
    }


_DIFF_OPTIONS = ("--no-color", "--no-ext-diff", "--no-textconv", "--no-renames")


def _untracked_patch(root: Path, path: str, limit: int) -> bytes:
    try:
        candidate = safe_resolve_workspace_file(root, path)
    except ValueError:
        return b""
    if not candidate.is_file():
        return b""
    return _git(root, "diff", "--no-index", *_DIFF_OPTIONS, "--", os.devnull, path,
                limit=limit, diff_exit=True) or b""


def _hunks(patch: str) -> list[dict]:
    hunks: list[dict] = []
    for raw_line in patch.split("\n"):
        line = raw_line.removesuffix("\r")
        if line.startswith("@@ "):
            hunks.append({"header": line, "lines": []})
        elif hunks:
            marker = line[:1]
            kind = {"+": "addition", "-": "deletion", " ": "context", "\\": "meta"}.get(marker)
            if kind:
                hunks[-1]["lines"].append({"kind": kind, "text": line})
    return hunks


def get_file_diff(root: Path, rel_path: str, base: str | None = None) -> dict:
    candidate = safe_resolve_workspace_file(root, rel_path)
    path = Path(rel_path).as_posix()
    result = {"ok": True, "path": path, "base": base, "has_diff": False, "hunks": [], "additions": 0, "deletions": 0}
    if candidate.is_dir():
        return {**result, "ok": False, "error": "INVALID_FILE_PATH"}
    if _workspace_prefix(root) is None:
        return {**result, "ok": False, "error": "GIT_DIFF_UNAVAILABLE"} if _has_git_marker(root) else result
    revision = _resolve_base(root, base)
    if revision is None:
        return {**result, "ok": False, "error": "INVALID_DIFF_BASE"}
    pathspec = ":(literal)" + path
    patch = _git(root, "diff", *_DIFF_OPTIONS, "--relative", revision, "--", pathspec, limit=_PATCH_LIMIT)
    if patch is None:
        return {**result, "ok": False, "error": "GIT_DIFF_UNAVAILABLE"}
    numstat = _git(root, "diff", *_DIFF_OPTIONS, "--relative", "--numstat", "-z", revision, "--", pathspec, limit=8192)
    if numstat is None:
        return {**result, "ok": False, "error": "GIT_DIFF_UNAVAILABLE"}
    if numstat:
        records = numstat.rstrip(b"\0").split(b"\0")
        if len(records) != 1 or records[0].split(b"\t", 2)[-1] != os.fsencode(path):
            return {**result, "ok": False, "error": "INVALID_FILE_PATH"}
    if not patch and not (base and ".." in base):
        untracked = _git(root, "ls-files", "--others", "--exclude-standard", "-z", "--", pathspec)
        if untracked:
            patch = _untracked_patch(root, path, _PATCH_LIMIT)
            numstat = _git(root, "diff", "--no-index", *_DIFF_OPTIONS, "--numstat", "-z", "--", os.devnull, path,
                           limit=1024, diff_exit=True)
    if numstat:
        fields = numstat.split(b"\t", 2)
        if len(fields) == 3:
            result["additions"] = int(fields[0]) if fields[0].isdigit() else 0
            result["deletions"] = int(fields[1]) if fields[1].isdigit() else 0
    result.update(has_diff=bool(patch), hunks=_hunks(_bounded_text(patch, _PATCH_LIMIT)))
    return result


def get_workspace_diff_summary(root: Path, diff_base: str | None = None) -> dict:
    result = {"ok": True, "base": diff_base, "stat": "", "patch": "", "truncated": False}
    prefix = _workspace_prefix(root)
    if prefix is None:
        return {**result, "ok": False, "error": "GIT_DIFF_UNAVAILABLE"} if _has_git_marker(root) else result
    revision = _resolve_base(root, diff_base)
    if revision is None:
        return {**result, "ok": False, "error": "INVALID_DIFF_BASE"}
    scope = (revision, "--", ".", ":(exclude).agentcanvas")
    summary = _git(root, "diff", *_DIFF_OPTIONS, "--relative", "--stat", *scope, limit=4096)
    patch = _git(root, "diff", *_DIFF_OPTIONS, "--relative", *scope, limit=_PATCH_LIMIT)
    if summary is None or patch is None:
        return {**result, "ok": False, "error": "GIT_DIFF_UNAVAILABLE"}
    new_paths = []
    if not (diff_base and ".." in diff_base):
        entries = _status_entries(root, prefix)
        if entries is None:
            return {**result, "ok": False, "error": "GIT_STATUS_UNAVAILABLE"}
        new_paths = [path for path, status in entries.items() if status == "??"]
        if new_paths:
            summary = summary + b"\nUntracked files:\n" + "\n".join(new_paths).encode("utf-8", errors="replace")
        for path in new_paths[:20]:
            remaining = _PATCH_LIMIT - len(patch)
            if remaining <= 0:
                break
            patch += _untracked_patch(root, path, remaining)
    result.update(
        stat=_bounded_text(summary, 4096), patch=_bounded_text(patch, _PATCH_LIMIT),
        truncated=len(summary) > 4096 or len(patch) > _PATCH_LIMIT or len(new_paths) > 20,
    )
    return result
