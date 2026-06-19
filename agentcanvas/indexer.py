"""Workspace indexing for AgentCanvas."""

from __future__ import annotations

import json
import os
import re
import subprocess
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from .core import (
    annotate_bundle_with_surfaces,
    app_surface_for_path,
    detect_app_surfaces,
    enrich_app_surfaces,
)
from .ir import SCHEMA, now_utc, resolve_workspace, save_ir, summarize_ir
from .languages import (
    dart_lang,
    go_lang,
    js_ts,
    kotlin_lang,
    php_lang,
    python_lang,
    ruby_lang,
    swift_lang,
)
from .projection import SOURCE_FACTS_SCHEMA, build_projection_contract, facts_from_workflow_ir

PYTHON_SOURCE_EXTENSIONS = {".py"}
LANGUAGE_MODULES = [
    ("go", go_lang.SOURCE_EXTENSIONS, go_lang.parse_workspace),
    ("php-laravel", php_lang.SOURCE_EXTENSIONS, php_lang.parse_workspace),
    ("ruby-rails", ruby_lang.SOURCE_EXTENSIONS, ruby_lang.parse_workspace),
    ("dart-flutter", dart_lang.SOURCE_EXTENSIONS, dart_lang.parse_workspace),
    ("swift", swift_lang.SOURCE_EXTENSIONS, swift_lang.parse_workspace),
    ("kotlin", kotlin_lang.SOURCE_EXTENSIONS, kotlin_lang.parse_workspace),
]
SOURCE_EXTENSIONS = (
    set(js_ts.SOURCE_EXTENSIONS)
    | PYTHON_SOURCE_EXTENSIONS
    | set().union(*(set(extensions) for _, extensions, _ in LANGUAGE_MODULES))
)
IMPORT_EXTENSIONS = [
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".mjs",
    ".cjs",
    ".json",
    ".go",
    ".php",
    ".rb",
    ".dart",
    ".swift",
    ".kt",
    ".kts",
]
SKIP_DIRS = {
    ".agentcanvas",
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "__pycache__",
    "build",
    "coverage",
    "dist",
    "node_modules",
    "out",
    "target",
    ".next",
    ".turbo",
    ".cache",
}
MAX_INDEXED_FILES = 3000
MAX_FILE_BYTES = 1_000_000
MAX_SOURCE_FACTS = 500

IMPORT_RE = re.compile(
    r"""
    (?:\bimport\s+(?:[^'"()]+?\s+from\s*)?["']([^"']+)["'])
    |(?:\bexport\s+[^"']*?\s+from\s+["']([^"']+)["'])
    |(?:\brequire\(\s*["']([^"']+)["']\s*\))
    |(?:\bimport\(\s*["']([^"']+)["']\s*\))
    """,
    re.VERBOSE,
)
EXPORT_DECL_RE = re.compile(
    r"\bexport\s+(?:default\s+)?(?:async\s+)?"
    r"(function|class|const|let|var|type|interface|enum)\s+([A-Za-z_$][\w$]*)"
)
EXPORT_NAMED_RE = re.compile(r"\bexport\s*\{([^}]+)\}")
EXPORT_DEFAULT_RE = re.compile(
    r"\bexport\s+default\s+(?:async\s+)?(?:function|class)?\s*([A-Za-z_$][\w$]*)?"
)
CJS_EXPORT_RE = re.compile(r"\b(?:module\.)?exports\.([A-Za-z_$][\w$]*)\s*=")
ROUTE_CALL_RE = re.compile(
    r"\b(?:app|router)\.(get|post|put|patch|delete|del|all|use)\s*"
    r"\(\s*[`'\"]([^`'\"]+)[`'\"]",
    re.IGNORECASE,
)
GENERIC_ROUTE_RE = re.compile(
    r"\broute\s*\(\s*[`'\"]([^`'\"]+)[`'\"]", re.IGNORECASE
)


def index_workspace(workspace: str | Path) -> Dict[str, Any]:
    """Build and persist the workflow IR for a workspace."""

    root = resolve_workspace(workspace)
    workflow_ir = build_workflow_ir(root)
    save_ir(root, workflow_ir)
    return workflow_ir


def build_workflow_ir(workspace: str | Path) -> Dict[str, Any]:
    root = resolve_workspace(workspace)
    discovered, truncated = discover_files(root)
    package_info = collect_package_info(root, discovered)
    git = collect_git_info(root)
    app_surfaces = detect_app_surfaces(root, discovered)

    source_paths = [path for path in discovered if is_source_file(path)]
    source_set = {to_posix(path.relative_to(root)) for path in source_paths}
    file_infos = [
        analyze_source_file(root, path, source_set, app_surfaces)
        for path in source_paths
    ]
    app_surfaces = enrich_app_surfaces(app_surfaces, file_infos)

    tests = [info for info in file_infos if info["is_test"]]
    routes = [route for info in file_infos for route in info["routes"]]
    exports = [export for info in file_infos for export in info["exports"]]
    import_count = sum(len(info["imports"]) for info in file_infos)
    changed_files = git.get("changed_files", [])
    changed_path_set = {item["path"] for item in changed_files}

    components = build_components(file_infos, changed_path_set)
    focus = build_focus_metadata(
        file_infos=file_infos,
        changed_paths=changed_path_set,
        components=components,
        package_info=package_info,
        git=git,
    )
    nodes, edges = build_graph(
        file_infos=file_infos,
        app_surfaces=app_surfaces,
        components=components,
        package_info=package_info,
    )

    workflow_ir: Dict[str, Any] = {
        "schema": SCHEMA,
        "version": "0.1.0",
        "generated_at": now_utc(),
        "workspace": {
            "root": str(root),
            "name": root.name,
        },
        "summary": {
            "files_seen": len(discovered),
            "source_files": len(file_infos),
            "test_files": len(tests),
            "imports": import_count,
            "exports": len(exports),
            "routes": len(routes),
            "app_surfaces": len(app_surfaces),
            "components": len(components),
            "changed_files": len(changed_path_set),
            "truncated": truncated,
        },
        "package": package_info,
        "git": git,
        "focus": focus,
        "app_surfaces": app_surfaces,
        "components": components,
        "nodes": nodes,
        "edges": edges,
    }
    workflow_ir["summary"].update(
        {
            "nodes": len(nodes),
            "edges": len(edges),
        }
    )
    source_facts = build_source_facts(root, source_paths, workflow_ir)
    workflow_ir["source_facts"] = source_facts
    workflow_ir["summary"]["language_facts"] = len(source_facts.get("facts") or [])
    workflow_ir["summary"]["language_modules"] = sorted(
        {
            fact.get("attributes", {}).get("language")
            for fact in source_facts.get("facts") or []
            if fact.get("attributes", {}).get("language")
        }
    )
    workflow_ir["projection_contract"] = build_projection_contract(
        source_facts,
        projection_repo_summary(workflow_ir),
        max_facts=200,
    )
    return workflow_ir


def discover_files(root: Path) -> Tuple[List[Path], bool]:
    files: List[Path] = []
    truncated = False

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            dirname
            for dirname in dirnames
            if should_descend_into(dirname)
        ]

        for filename in filenames:
            path = Path(dirpath) / filename
            files.append(path)
            if len(files) >= MAX_INDEXED_FILES:
                return sorted(files), True

    return sorted(files), truncated


def should_descend_into(dirname: str) -> bool:
    if dirname in SKIP_DIRS:
        return False
    if dirname.startswith(".") and dirname not in {".github"}:
        return False
    return True


def is_source_file(path: Path) -> bool:
    return path.suffix.lower() in SOURCE_EXTENSIONS


def to_posix(path: Path | PurePosixPath | str) -> str:
    return PurePosixPath(str(path)).as_posix()


def safe_read_text(path: Path) -> Optional[str]:
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            return None
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def build_source_facts(
    root: Path,
    source_paths: Sequence[Path],
    workflow_ir: Dict[str, Any],
) -> Dict[str, Any]:
    """Build an LLM-ready source-facts bundle from language modules plus IR facts."""

    repo = projection_repo_summary(workflow_ir)
    facts: List[Dict[str, Any]] = []
    warnings: List[str] = []

    js_paths = [
        path
        for path in source_paths
        if path.suffix.lower() in js_ts.SOURCE_EXTENSIONS
    ]
    if js_paths:
        try:
            js_bundle = js_ts.parse_workspace(root, paths=js_paths)
            annotate_bundle_with_surfaces(js_bundle, workflow_ir.get("app_surfaces") or [])
            facts.extend(canonical_language_facts(js_bundle, "javascript-typescript"))
        except Exception as exc:  # pragma: no cover - defensive, keeps indexing useful.
            warnings.append(f"JS/TS language module failed: {type(exc).__name__}: {exc}")

    python_paths = [
        path
        for path in source_paths
        if path.suffix.lower() in PYTHON_SOURCE_EXTENSIONS
    ]
    for path in python_paths:
        rel = to_posix(path.relative_to(root))
        text = safe_read_text(path)
        if text is None:
            warnings.append(f"Python source file was not readable: {rel}")
            facts.append(
                canonical_language_fact(
                    {
                        "id": f"read_error:{rel}",
                        "type": "read_error",
                        "kind": "read_error",
                        "language": "python",
                        "file": rel,
                        "path": rel,
                        "readable": False,
                        "provenance": {"path": rel, "line": 1},
                    },
                    "python",
                    len(facts),
                )
            )
            continue
        try:
            py_bundle = python_lang.extract_source_facts(rel, source=text)
            annotate_bundle_with_surfaces(py_bundle, workflow_ir.get("app_surfaces") or [])
            facts.extend(canonical_language_facts(py_bundle, "python"))
        except Exception as exc:  # pragma: no cover - defensive, keeps indexing useful.
            warnings.append(f"Python language module failed for {rel}: {type(exc).__name__}: {exc}")

    for language, extensions, parser in LANGUAGE_MODULES:
        language_paths = [
            path
            for path in source_paths
            if path.suffix.lower() in extensions
        ]
        if not language_paths:
            continue
        try:
            bundle = parser(root, paths=language_paths)
            annotate_bundle_with_surfaces(bundle, workflow_ir.get("app_surfaces") or [])
            facts.extend(canonical_language_facts(bundle, language))
        except Exception as exc:  # pragma: no cover - defensive, keeps indexing useful.
            warnings.append(f"{language} language module failed: {type(exc).__name__}: {exc}")

    base_bundle = facts_from_workflow_ir(
        workflow_ir,
        repo,
        max_facts=150,
    )
    facts.extend(base_bundle.get("facts") or [])

    if len(facts) > MAX_SOURCE_FACTS:
        warnings.append(
            f"Source facts truncated from {len(facts)} to {MAX_SOURCE_FACTS} facts."
        )
        facts = facts[:MAX_SOURCE_FACTS]

    return {
        "schema": SOURCE_FACTS_SCHEMA,
        "version": "0.1.0",
        "repo": repo,
        "facts": facts,
        "warnings": warnings,
    }


def canonical_language_facts(
    bundle: Dict[str, Any],
    default_language: str,
) -> List[Dict[str, Any]]:
    language = str(bundle.get("language") or bundle.get("language_family") or default_language)
    return [
        canonical_language_fact(raw, language, index)
        for index, raw in enumerate(bundle.get("facts") or [])
        if isinstance(raw, dict)
    ]


def canonical_language_fact(
    raw: Dict[str, Any],
    language: str,
    index: int,
) -> Dict[str, Any]:
    raw_type = str(raw.get("type") or raw.get("kind") or "fact")
    raw_kind = str(raw.get("kind") or raw_type)
    raw_id = str(raw.get("id") or f"{raw_type}:{index}")
    subject = language_fact_subject(raw)
    summary = language_fact_summary(raw, language, raw_type, raw_kind, subject)
    attributes = compact_language_attributes(raw)
    attributes["language"] = language
    attributes["fact_type"] = raw_type

    return {
        "id": f"language:{language}:{raw_id}",
        "kind": f"language_{raw_type}",
        "subject": subject,
        "summary": summary,
        "attributes": attributes,
        "evidence": language_fact_evidence(raw),
        "confidence": language_fact_confidence(raw_type),
    }


def language_fact_subject(raw: Dict[str, Any]) -> str:
    if raw.get("type") == "route" and raw.get("path"):
        method = raw.get("method")
        return f"{method} {raw['path']}" if method else str(raw["path"])
    if raw.get("qualified_name"):
        return str(raw["qualified_name"])
    if raw.get("name"):
        return str(raw["name"])
    if raw.get("function"):
        return str(raw["function"])
    if raw.get("specifier"):
        return str(raw["specifier"])
    if raw.get("file"):
        return str(raw["file"])
    if raw.get("path"):
        return str(raw["path"])
    return str(raw.get("id") or "source fact")


def language_fact_summary(
    raw: Dict[str, Any],
    language: str,
    raw_type: str,
    raw_kind: str,
    subject: str,
) -> str:
    file_path = raw.get("file") or raw.get("path")
    line = raw.get("line")
    location = ""
    if file_path:
        location = f" in {file_path}"
        if line:
            location += f":{line}"

    if raw_type == "route":
        method = raw.get("method")
        return f"{language} route {method + ' ' if method else ''}{subject}{location}"
    if raw_type == "branch":
        condition = raw.get("condition") or subject
        return f"{language} {raw_kind} branch {condition}{location}"
    if raw_type == "call":
        return f"{language} call {subject}{location}"
    if raw_type == "symbol":
        return f"{language} {raw_kind} {subject}{location}"
    if raw_type == "import":
        return f"{language} import {subject}{location}"
    return f"{language} {raw_type} {subject}{location}"


def language_fact_evidence(raw: Dict[str, Any]) -> List[Dict[str, Any]]:
    evidence: List[Dict[str, Any]] = []
    for key in ["source_ref", "provenance"]:
        ref = raw.get(key)
        if isinstance(ref, dict):
            item: Dict[str, Any] = {}
            if ref.get("path"):
                item["path"] = to_posix(str(ref["path"]))
            if ref.get("line"):
                item["line"] = ref["line"]
            if ref.get("column"):
                item["column"] = ref["column"]
            if item:
                evidence.append(item)
                return evidence

    file_path = raw.get("file") or raw.get("path")
    if isinstance(file_path, str) and file_path:
        item = {"path": to_posix(file_path)}
        if raw.get("line"):
            item["line"] = raw["line"]
        evidence.append(item)
    return evidence


def language_fact_confidence(raw_type: str) -> float:
    if raw_type in {"file", "import", "symbol", "export", "route"}:
        return 0.9
    if raw_type in {"branch", "call"}:
        return 0.75
    if raw_type.endswith("error"):
        return 1.0
    return 0.65


def compact_language_attributes(raw: Dict[str, Any]) -> Dict[str, Any]:
    skip = {"id", "source_ref", "provenance"}
    return {
        key: json_safe(value)
        for key, value in raw.items()
        if key not in skip and value is not None
    }


def json_safe(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        return {
            str(key): json_safe(item)
            for key, item in list(value.items())[:20]
        }
    if isinstance(value, (list, tuple, set)):
        return [json_safe(item) for item in list(value)[:20]]
    return str(value)


def projection_repo_summary(workflow_ir: Dict[str, Any]) -> Dict[str, Any]:
    workspace = workflow_ir.get("workspace") or {}
    return {
        "name": workspace.get("name"),
        "root": workspace.get("root"),
        "summary": workflow_ir.get("summary") or {},
        "package": workflow_ir.get("package") or {},
        "git": workflow_ir.get("git") or {},
        "focus": workflow_ir.get("focus") or {},
        "app_surfaces": workflow_ir.get("app_surfaces") or [],
    }


def app_surface_metadata(surface: Mapping[str, Any]) -> Dict[str, Any]:
    surface_id = surface.get("id")
    surface_type = surface.get("type")
    surface_root = surface.get("root")
    return {
        "app_surface_id": surface_id,
        "app_surface_type": surface_type,
        "app_surface_root": surface_root,
        "app_surface": surface_id,
        "surface_root": surface_root,
        "surface_kind": surface_type,
        "surface_platform": surface.get("platform"),
    }


def collect_package_info(root: Path, files: Sequence[Path]) -> Dict[str, Any]:
    manifests = []
    merged_scripts: Dict[str, str] = {}

    for path in files:
        if path.name != "package.json":
            continue
        text = safe_read_text(path)
        if text is None:
            continue
        try:
            package_json = json.loads(text)
        except json.JSONDecodeError:
            continue

        rel = to_posix(path.relative_to(root))
        scripts = package_json.get("scripts") or {}
        if not isinstance(scripts, dict):
            scripts = {}

        manifests.append(
            {
                "path": rel,
                "name": package_json.get("name"),
                "private": package_json.get("private"),
                "scripts": scripts,
                "dependencies": sorted((package_json.get("dependencies") or {}).keys()),
                "devDependencies": sorted(
                    (package_json.get("devDependencies") or {}).keys()
                ),
            }
        )
        for name, command in scripts.items():
            merged_scripts.setdefault(name, command)

    lockfiles = []
    for filename, manager in [
        ("pnpm-lock.yaml", "pnpm"),
        ("yarn.lock", "yarn"),
        ("package-lock.json", "npm"),
        ("bun.lockb", "bun"),
        ("bun.lock", "bun"),
    ]:
        if (root / filename).exists():
            lockfiles.append({"path": filename, "manager": manager})

    manager = lockfiles[0]["manager"] if lockfiles else "npm"
    return {
        "manager": manager,
        "lockfiles": lockfiles,
        "manifests": manifests,
        "scripts": merged_scripts,
    }


def collect_git_info(root: Path) -> Dict[str, Any]:
    base: Dict[str, Any] = {
        "available": False,
        "root": None,
        "branch": None,
        "changed_files": [],
        "error": None,
    }
    try:
        git_root = run_git(root, ["rev-parse", "--show-toplevel"]).strip()
    except (OSError, subprocess.SubprocessError) as exc:
        base["error"] = str(exc)
        return base

    if not git_root:
        base["error"] = "git repository not found"
        return base

    base["available"] = True
    base["root"] = git_root
    try:
        base["branch"] = run_git(root, ["branch", "--show-current"]).strip() or None
    except (OSError, subprocess.SubprocessError):
        base["branch"] = None

    changed: Dict[str, Dict[str, str]] = {}
    for item in parse_git_diff_name_status(root):
        changed[item["path"]] = item
    for item in parse_git_status(root):
        changed[item["path"]] = item

    base["changed_files"] = sorted(changed.values(), key=lambda item: item["path"])
    return base


def run_git(root: Path, args: Sequence[str]) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=str(root),
        capture_output=True,
        check=False,
        text=True,
        timeout=4,
    )
    if result.returncode != 0:
        raise subprocess.SubprocessError(result.stderr.strip() or "git failed")
    return result.stdout


def parse_git_diff_name_status(root: Path) -> List[Dict[str, str]]:
    try:
        output = run_git(root, ["diff", "--name-status", "HEAD", "--"])
    except (OSError, subprocess.SubprocessError):
        return []

    items = []
    for line in output.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        status, path = parts[0], parts[-1]
        items.append({"path": to_posix(path), "status": status, "source": "git diff"})
    return items


def parse_git_status(root: Path) -> List[Dict[str, str]]:
    try:
        output = run_git(root, ["status", "--porcelain"])
    except (OSError, subprocess.SubprocessError):
        return []

    items = []
    for line in output.splitlines():
        if len(line) < 4:
            continue
        status = line[:2].strip() or "modified"
        path = line[3:]
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        items.append({"path": to_posix(path), "status": status, "source": "git status"})
    return items


def analyze_source_file(
    root: Path,
    path: Path,
    source_set: set[str],
    app_surfaces: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    rel = to_posix(path.relative_to(root))
    text = safe_read_text(path)
    imports = extract_imports(text or "", rel)
    for imported in imports:
        imported["resolved_path"] = resolve_import(root, rel, imported["specifier"], source_set)
    routes = extract_routes(text or "", rel)
    surface = app_surface_for_path(rel, app_surfaces)
    surface_meta = app_surface_metadata(surface) if surface else {}
    if surface:
        for route in routes:
            route.update(surface_meta)

    info = {
        "path": rel,
        "kind": classify_source_file(rel),
        "is_test": is_test_path(rel),
        "imports": imports,
        "exports": extract_exports(text or "", rel),
        "routes": routes,
        "component": component_key(rel),
        "readable": text is not None,
    }
    if surface:
        info.update(surface_meta)
    return info


def classify_source_file(rel: str) -> str:
    lowered = rel.lower()
    if is_test_path(rel):
        return "test"
    if "/api/" in f"/{lowered}" or lowered.startswith("api/"):
        return "api"
    if any(part in lowered.split("/") for part in ["routes", "pages", "app"]):
        return "route"
    return "source"


def is_test_path(rel: str) -> bool:
    lowered = rel.lower()
    name = PurePosixPath(lowered).name
    return (
        ".test." in name
        or ".spec." in name
        or lowered.startswith("test/")
        or lowered.startswith("tests/")
        or "/test/" in lowered
        or "/tests/" in lowered
        or "/__tests__/" in lowered
    )


def extract_imports(text: str, rel: str) -> List[Dict[str, Any]]:
    imports = []
    for match in IMPORT_RE.finditer(text):
        specifier = next(group for group in match.groups() if group)
        kind = "local" if specifier.startswith(".") else "package"
        imports.append(
            {
                "specifier": specifier,
                "kind": kind,
                "line": line_number(text, match.start()),
                "source": rel,
            }
        )
    return imports


def extract_exports(text: str, rel: str) -> List[Dict[str, Any]]:
    exports: Dict[Tuple[str, str], Dict[str, Any]] = {}

    for match in EXPORT_DECL_RE.finditer(text):
        export_kind, name = match.groups()
        exports[(name, export_kind)] = {
            "name": name,
            "kind": export_kind,
            "path": rel,
            "line": line_number(text, match.start()),
        }

    for match in EXPORT_NAMED_RE.finditer(text):
        for raw_name in match.group(1).split(","):
            name = raw_name.strip().split(" as ", 1)[-1].strip()
            if not name or name == "default":
                continue
            exports[(name, "named")] = {
                "name": name,
                "kind": "named",
                "path": rel,
                "line": line_number(text, match.start()),
            }

    for match in EXPORT_DEFAULT_RE.finditer(text):
        name = match.group(1) or "default"
        exports[(name, "default")] = {
            "name": name,
            "kind": "default",
            "path": rel,
            "line": line_number(text, match.start()),
        }

    for match in CJS_EXPORT_RE.finditer(text):
        name = match.group(1)
        exports[(name, "commonjs")] = {
            "name": name,
            "kind": "commonjs",
            "path": rel,
            "line": line_number(text, match.start()),
        }

    return sorted(exports.values(), key=lambda item: (item["line"], item["name"]))


def extract_routes(text: str, rel: str) -> List[Dict[str, Any]]:
    routes: Dict[Tuple[str, str], Dict[str, Any]] = {}
    file_route = route_from_path(rel)
    if file_route:
        routes[(file_route, "file")] = {
            "path": file_route,
            "method": None,
            "source": "file",
            "file": rel,
            "line": None,
        }

    for match in ROUTE_CALL_RE.finditer(text):
        method = match.group(1).upper()
        if method == "DEL":
            method = "DELETE"
        route = match.group(2)
        routes[(route, method)] = {
            "path": route,
            "method": method,
            "source": "handler",
            "file": rel,
            "line": line_number(text, match.start()),
        }

    for match in GENERIC_ROUTE_RE.finditer(text):
        route = match.group(1)
        routes[(route, "route")] = {
            "path": route,
            "method": None,
            "source": "route-call",
            "file": rel,
            "line": line_number(text, match.start()),
        }

    return sorted(routes.values(), key=lambda item: (item["path"], item.get("method") or ""))


def route_from_path(rel: str) -> Optional[str]:
    path = PurePosixPath(rel)
    parts = list(path.with_suffix("").parts)
    if parts and parts[0] == "src":
        parts = parts[1:]
    if not parts:
        return None

    root = parts[0]
    route_parts: List[str]
    if root == "app":
        route_parts = parts[1:]
        if route_parts and route_parts[-1] in {"page", "route"}:
            route_parts = route_parts[:-1]
        else:
            return None
    elif root == "pages":
        route_parts = parts[1:]
        if route_parts and route_parts[-1] in {"_app", "_document"}:
            return None
    elif root in {"routes", "api"}:
        route_parts = parts[1:] if root == "routes" else parts
    else:
        return None

    cleaned = [
        normalise_route_segment(part)
        for part in route_parts
        if part and not (part.startswith("(") and part.endswith(")"))
    ]
    if cleaned and cleaned[-1] == "index":
        cleaned = cleaned[:-1]
    route = "/" + "/".join(cleaned)
    return route if route != "/" or root in {"pages", "app", "routes"} else route


def normalise_route_segment(part: str) -> str:
    if part.startswith("[[...") and part.endswith("]]"):
        return f"*{part[5:-2]}?"
    if part.startswith("[...") and part.endswith("]"):
        return f"*{part[4:-1]}"
    if part.startswith("[") and part.endswith("]"):
        return f":{part[1:-1]}"
    return part


def line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def resolve_import(
    root: Path,
    rel: str,
    specifier: str,
    source_set: set[str],
) -> Optional[str]:
    if not specifier.startswith("."):
        return None

    base = (root / rel).parent / specifier
    candidates: List[Path] = [base]
    candidates.extend(base.with_suffix(ext) for ext in IMPORT_EXTENSIONS)
    candidates.extend(base / f"index{ext}" for ext in IMPORT_EXTENSIONS)

    for candidate in candidates:
        try:
            rel_candidate = to_posix(candidate.resolve().relative_to(root))
        except (OSError, ValueError):
            continue
        if rel_candidate in source_set:
            return rel_candidate
    return None


def component_key(rel: str) -> str:
    parts = rel.split("/")
    if not parts:
        return "project"
    if parts[0] in {"apps", "packages"} and len(parts) > 1:
        return f"{parts[0]}/{parts[1]}"
    if parts[0] == "src" and len(parts) > 1 and parts[1] in {
        "app",
        "api",
        "components",
        "features",
        "lib",
        "pages",
        "routes",
        "server",
        "services",
        "ui",
    }:
        return f"src/{parts[1]}"
    if parts[0] in {"app", "api", "components", "lib", "pages", "routes", "server", "src"}:
        return parts[0]
    if is_test_path(rel):
        return "tests"
    return parts[0] if len(parts) > 1 else "project"


def build_components(
    file_infos: Sequence[Dict[str, Any]],
    changed_paths: set[str],
) -> List[Dict[str, Any]]:
    groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for info in file_infos:
        groups[info["component"]].append(info)

    components = []
    for key, infos in sorted(groups.items()):
        paths = sorted(info["path"] for info in infos)
        changed = sorted(path for path in paths if path in changed_paths)
        kind_counts = Counter(info["kind"] for info in infos)
        components.append(
            {
                "id": f"component:{key}",
                "name": key,
                "kind": "component",
                "paths": paths[:50],
                "file_count": len(infos),
                "test_files": sum(1 for info in infos if info["is_test"]),
                "routes": sum(len(info["routes"]) for info in infos),
                "exports": sum(len(info["exports"]) for info in infos),
                "changed_files": changed,
                "dominant_file_kind": kind_counts.most_common(1)[0][0],
                "app_surfaces": sorted(
                    {
                        info["app_surface"]
                        for info in infos
                        if info.get("app_surface")
                    }
                ),
            }
        )
    return components


def build_focus_metadata(
    *,
    file_infos: Sequence[Dict[str, Any]],
    changed_paths: set[str],
    components: Sequence[Dict[str, Any]],
    package_info: Dict[str, Any],
    git: Dict[str, Any],
) -> Dict[str, Any]:
    test_paths = [info["path"] for info in file_infos if info["is_test"]]
    related_tests = related_tests_for_changes(file_infos, changed_paths)
    touched_components = [
        component["id"]
        for component in components
        if set(component["changed_files"])
    ]
    scripts = package_info.get("scripts") or {}
    relevant_scripts = {
        name: command
        for name, command in scripts.items()
        if any(word in name.lower() for word in ["build", "check", "dev", "lint", "test"])
    }

    hints = []
    if git.get("available"):
        if changed_paths:
            hints.append("Prioritize files currently changed in git.")
        else:
            hints.append("Git is available but no changed files were detected.")
    else:
        hints.append("Git metadata is unavailable for this workspace.")
    if related_tests:
        hints.append("Related tests were inferred from changed file names and paths.")
    elif test_paths:
        hints.append("Tests exist, but no changed-file-specific test was inferred.")

    return {
        "changed_files": sorted(changed_paths),
        "components": touched_components,
        "related_tests": related_tests,
        "available_test_files": sorted(test_paths)[:25],
        "relevant_scripts": relevant_scripts,
        "hints": hints,
    }


def related_tests_for_changes(
    file_infos: Sequence[Dict[str, Any]],
    changed_paths: set[str],
) -> List[str]:
    if not changed_paths:
        return []

    tests = [info["path"] for info in file_infos if info["is_test"]]
    source_stems = {
        PurePosixPath(path).stem.split(".", 1)[0]
        for path in changed_paths
        if path
    }
    related = []
    for test_path in tests:
        test_parts = set(PurePosixPath(test_path).parts)
        test_stem = PurePosixPath(test_path).stem.split(".", 1)[0]
        if test_stem in source_stems:
            related.append(test_path)
            continue
        for changed in changed_paths:
            changed_parts = set(PurePosixPath(changed).parts[:-1])
            if changed_parts and changed_parts.intersection(test_parts):
                related.append(test_path)
                break
    return sorted(set(related))


def build_graph(
    *,
    file_infos: Sequence[Dict[str, Any]],
    app_surfaces: Sequence[Dict[str, Any]],
    components: Sequence[Dict[str, Any]],
    package_info: Dict[str, Any],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []
    node_ids: set[str] = set()
    edge_ids: set[str] = set()

    def add_node(node: Dict[str, Any]) -> None:
        if node["id"] not in node_ids:
            node_ids.add(node["id"])
            nodes.append(node)

    def add_edge(source: str, target: str, kind: str, **extra: Any) -> None:
        edge_id = f"{source}->{kind}->{target}"
        if edge_id in edge_ids:
            return
        edge_ids.add(edge_id)
        edge = {"id": edge_id, "source": source, "target": target, "kind": kind}
        edge.update(extra)
        edges.append(edge)

    for surface in app_surfaces:
        add_node(
            {
                "id": surface["id"],
                "type": "app_surface",
                "label": surface["name"],
                "path": None if surface["root"] == "." else surface["root"],
                "data": surface,
            }
        )

    for component in components:
        add_node(
            {
                "id": component["id"],
                "type": "component",
                "label": component["name"],
                "data": component,
            }
        )
        for app_surface in component.get("app_surfaces") or []:
            add_edge(app_surface, component["id"], "contains")

    for info in file_infos:
        file_id = file_node_id(info["path"])
        add_node(
            {
                "id": file_id,
                "type": "file",
                "label": PurePosixPath(info["path"]).name,
                "path": info["path"],
                "data": {
                    "kind": info["kind"],
                    "component": info["component"],
                    "is_test": info["is_test"],
                    "imports": info["imports"],
                    "exports": info["exports"],
                    "routes": info["routes"],
                    "readable": info["readable"],
                    "app_surface_id": info.get("app_surface_id"),
                    "app_surface_type": info.get("app_surface_type"),
                    "app_surface_root": info.get("app_surface_root"),
                    "app_surface": info.get("app_surface"),
                    "surface_root": info.get("surface_root"),
                    "surface_kind": info.get("surface_kind"),
                    "surface_platform": info.get("surface_platform"),
                },
            }
        )
        add_edge(f"component:{info['component']}", file_id, "contains")

        for imported in info["imports"]:
            if imported.get("resolved_path"):
                add_edge(file_id, file_node_id(imported["resolved_path"]), "imports")

        for exported in info["exports"]:
            export_id = export_node_id(exported)
            add_node(
                {
                    "id": export_id,
                    "type": "export",
                    "label": exported["name"],
                    "path": exported["path"],
                    "data": exported,
                }
            )
            add_edge(file_id, export_id, "declares")

        for route in info["routes"]:
            route_id = route_node_id(route)
            add_node(
                {
                    "id": route_id,
                    "type": "route",
                    "label": route["path"],
                    "path": route["file"],
                    "data": route,
                }
            )
            add_edge(file_id, route_id, "serves")

    for name, command in sorted((package_info.get("scripts") or {}).items()):
        script_id = f"script:{name}"
        add_node(
            {
                "id": script_id,
                "type": "script",
                "label": name,
                "data": {
                    "name": name,
                    "command": command,
                    "manager": package_info.get("manager"),
                },
            }
        )

    test_infos = [info for info in file_infos if info["is_test"]]
    source_infos = [info for info in file_infos if not info["is_test"]]
    for test in test_infos:
        test_stem = PurePosixPath(test["path"]).stem.split(".", 1)[0]
        for source in source_infos:
            source_stem = PurePosixPath(source["path"]).stem
            if source_stem == test_stem:
                add_edge(file_node_id(test["path"]), file_node_id(source["path"]), "tests")

    return nodes, edges


def file_node_id(path: str) -> str:
    return f"file:{path}"


def export_node_id(exported: Dict[str, Any]) -> str:
    return f"export:{exported['path']}:{exported['name']}:{exported['kind']}"


def route_node_id(route: Dict[str, Any]) -> str:
    method = route.get("method") or "ANY"
    return f"route:{route['file']}:{method}:{route['path']}"


def format_index_summary(workflow_ir: Dict[str, Any]) -> str:
    summary = summarize_ir(workflow_ir)
    return (
        f"{summary.get('source_files', 0)} source files, "
        f"{summary.get('test_files', 0)} tests, "
        f"{summary.get('routes', 0)} routes, "
        f"{summary.get('components', 0)} components, "
        f"{summary.get('changed_files', 0)} changed files"
    )
