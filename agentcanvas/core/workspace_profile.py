"""Workspace-level product language inference for AgentCanvas."""

from __future__ import annotations

import os
import re
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from .model import normalize_path

WORKSPACE_PROFILE_SCHEMA = "agentcanvas.workspace_profile.v1"

_KIND_LABELS = {
    "app": "App",
    "tool_product": "Tool/product",
    "learning_program": "Learning program/project",
    "library_package": "Library/package",
    "api_backend": "API/backend",
    "monorepo_mixed": "Monorepo/mixed",
}

_PRODUCT_LANGUAGE = {
    "app": {
        "singular": "app",
        "plural": "apps",
        "workspace_noun": "app",
        "entry_noun": "flow",
    },
    "tool_product": {
        "singular": "tool",
        "plural": "tools",
        "workspace_noun": "product",
        "entry_noun": "workflow",
    },
    "learning_program": {
        "singular": "project",
        "plural": "projects",
        "workspace_noun": "learning program",
        "entry_noun": "lesson",
    },
    "library_package": {
        "singular": "package",
        "plural": "packages",
        "workspace_noun": "library",
        "entry_noun": "API",
    },
    "api_backend": {
        "singular": "service",
        "plural": "services",
        "workspace_noun": "API/backend",
        "entry_noun": "endpoint",
    },
    "monorepo_mixed": {
        "singular": "workspace",
        "plural": "workspaces",
        "workspace_noun": "monorepo",
        "entry_noun": "surface",
    },
}

_KIND_PRIORITY = {
    "learning_program": 6,
    "tool_product": 5,
    "monorepo_mixed": 4,
    "api_backend": 3,
    "app": 2,
    "library_package": 1,
}

_SKIP_DIRS = {
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

_TEXT_CANDIDATE_NAMES = {
    "readme",
    "curriculum",
    "course",
    "lesson",
    "lessons",
    "module",
    "modules",
    "syllabus",
    "tutorial",
    "workshop",
}
_TEXT_SUFFIXES = {".md", ".mdx", ".rst", ".txt", ".toml", ".json", ".yaml", ".yml"}
_MANIFEST_NAMES = {
    "Cargo.toml",
    "Gemfile",
    "composer.json",
    "go.mod",
    "package.json",
    "pubspec.yaml",
    "pyproject.toml",
    "requirements.txt",
}
def infer_workspace_profile(
    workflow_ir: Optional[Mapping[str, Any]] = None,
    *,
    workspace: Optional[str | Path] = None,
    files: Optional[Sequence[str | Path]] = None,
) -> Dict[str, Any]:
    """Infer a user-facing workspace kind from cheap repo evidence."""

    ir = workflow_ir if isinstance(workflow_ir, Mapping) else {}
    workspace_path = Path(workspace) if workspace is not None else _workspace_path_from_ir(ir)
    workspace_name = _workspace_name(ir, workspace_path)
    surfaces = _app_surfaces(ir)
    summary = ir.get("summary") if isinstance(ir.get("summary"), Mapping) else {}
    package = ir.get("package") if isinstance(ir.get("package"), Mapping) else {}
    paths = _known_paths(ir, workspace_path, files)
    text = _read_workspace_text(workspace_path, paths)
    scores: Counter[str] = Counter()
    signals: List[str] = []

    _score_learning_program(scores, signals, workspace_name, paths, text, summary, surfaces)
    _score_tool_product(scores, signals, workspace_name, paths, text, surfaces)
    _score_monorepo(scores, signals, paths, text, surfaces)
    _score_api_backend(scores, signals, summary, surfaces, paths, text)
    _score_app(scores, signals, surfaces, text)
    _score_library_package(scores, signals, paths, text, package, surfaces)

    if not scores:
        fallback = _fallback_kind(paths)
        scores[fallback] = 1
        signals.append(f"fallback:{fallback}")

    kind = _dominant_kind(scores)
    language = dict(_PRODUCT_LANGUAGE[kind])
    return {
        "schema": WORKSPACE_PROFILE_SCHEMA,
        "kind": kind,
        "label": _KIND_LABELS[kind],
        "product_language": language,
        "confidence": {
            "score": _confidence_score(scores, kind),
            "signals": _dedupe(signals)[:20],
        },
    }


def _score_learning_program(
    scores: Counter[str],
    signals: List[str],
    workspace_name: str,
    paths: Sequence[str],
    text: str,
    summary: Mapping[str, Any],
    surfaces: Sequence[Mapping[str, Any]],
) -> None:
    name_text = workspace_name.lower().replace("-", " ")
    path_text = " ".join(paths).lower().replace("-", " ")
    full_text = f"{name_text} {path_text} {text.lower()}"
    learning_words = {
        "assignment",
        "course",
        "curriculum",
        "homework",
        "lab",
        "lesson",
        "module",
        "student",
        "syllabus",
        "teacher",
        "tutorial",
        "workshop",
    }
    if "robotics" in full_text and any(word in full_text for word in {"adventure", "curriculum", "lesson"}):
        scores["learning_program"] += 6
        signals.append("learning:robotics-adventure")
    if any(word in name_text for word in {"curriculum", "course", "lesson", "learning", "tutorial"}):
        scores["learning_program"] += 3
        signals.append("learning:name")
    learning_path_parts = {"lessons", "curriculum", "modules", "worksheets"}
    if any(learning_path_parts.intersection({part.lower() for part in PurePosixPath(path).parts}) for path in paths):
        scores["learning_program"] += 4
        signals.append("learning:path")
    text_hits = sum(1 for word in learning_words if re.search(rf"\b{re.escape(word)}s?\b", full_text))
    if text_hits >= 3:
        scores["learning_program"] += 4
        signals.append("learning:content")

    markdown_count = sum(1 for path in paths if PurePosixPath(path).suffix.lower() in {".md", ".mdx", ".rst"})
    source_files = int(summary.get("source_files") or 0)
    if markdown_count >= 4 and source_files <= max(2, markdown_count // 3) and not surfaces:
        scores["learning_program"] += 2
        signals.append("learning:docs-heavy")


def _score_tool_product(
    scores: Counter[str],
    signals: List[str],
    workspace_name: str,
    paths: Sequence[str],
    text: str,
    surfaces: Sequence[Mapping[str, Any]],
) -> None:
    lowered = f"{workspace_name} {' '.join(paths)} {text}".lower()
    surface_types = {str(surface.get("type") or "") for surface in surfaces}
    if "agentcanvas" in lowered:
        scores["tool_product"] += 6
        signals.append("tool:agentcanvas")
    if "cli" in surface_types:
        scores["tool_product"] += 4
        signals.append("tool:cli-surface")
    if _contains_any(lowered, ["[project.scripts]", "[project.gui-scripts]", "[tool.poetry.scripts]", '"bin"', "'bin'"]):
        scores["tool_product"] += 4
        signals.append("tool:command-entrypoint")
    if _contains_any(lowered, ["developer-tool", "developer tool", "command line", "workflow canvas", "local editable"]):
        scores["tool_product"] += 3
        signals.append("tool:product-copy")
    if "cli" in surface_types and surface_types.intersection({"web", "mobile"}):
        scores["tool_product"] += 2
        signals.append("tool:companion-ui")


def _score_monorepo(
    scores: Counter[str],
    signals: List[str],
    paths: Sequence[str],
    text: str,
    surfaces: Sequence[Mapping[str, Any]],
) -> None:
    if not surfaces:
        return
    surface_types = {str(surface.get("type") or "") for surface in surfaces if surface.get("type")}
    roots = [str(surface.get("root") or ".") for surface in surfaces]
    app_like_types = surface_types.intersection({"backend", "mobile", "web"})
    monorepo_roots = [
        root
        for root in roots
        if PurePosixPath(root).parts[:1] and PurePosixPath(root).parts[0] in {"apps", "packages", "services"}
    ]
    if len(surfaces) >= 3 and len(app_like_types) >= 2:
        scores["monorepo_mixed"] += 5
        signals.append("monorepo:many-surfaces")
    if len(monorepo_roots) >= 2:
        scores["monorepo_mixed"] += 4
        signals.append("monorepo:path-convention")
    if _contains_any(text.lower(), ['"workspaces"', "[workspace]", "pnpm-workspace", "turbo.json"]):
        scores["monorepo_mixed"] += 4
        signals.append("monorepo:workspace-manifest")
    if len(app_like_types) >= 3:
        scores["monorepo_mixed"] += 2
        signals.append("monorepo:mixed-platforms")


def _score_api_backend(
    scores: Counter[str],
    signals: List[str],
    summary: Mapping[str, Any],
    surfaces: Sequence[Mapping[str, Any]],
    paths: Sequence[str],
    text: str,
) -> None:
    routes = int(summary.get("routes") or 0)
    surface_types = {str(surface.get("type") or "") for surface in surfaces if surface.get("type")}
    if routes:
        scores["api_backend"] += min(5, 2 + routes)
        signals.append("backend:routes")
    if surface_types and surface_types.issubset({"backend", "package"}) and "backend" in surface_types:
        scores["api_backend"] += 5
        signals.append("backend:surface")
    path_text = " ".join(paths).lower()
    if _contains_any(path_text, ["/api/", "/server/", "/backend/", "/services/"]):
        scores["api_backend"] += 2
        signals.append("backend:path")
    if _contains_any(text.lower(), ["fastapi", "django", "flask", "express", "nestjs", "gin-gonic", "laravel", "rails"]):
        scores["api_backend"] += 2
        signals.append("backend:framework")


def _score_app(
    scores: Counter[str],
    signals: List[str],
    surfaces: Sequence[Mapping[str, Any]],
    text: str,
) -> None:
    surface_types = {str(surface.get("type") or "") for surface in surfaces if surface.get("type")}
    app_types = surface_types.intersection({"mobile", "web"})
    if app_types and surface_types.issubset({"mobile", "web", "package"}):
        scores["app"] += 5
        signals.append("app:surface")
    elif app_types:
        scores["app"] += 3
        signals.append("app:surface-mixed")
    if _contains_any(text.lower(), ["react", "next", "vite", "flutter", "react-native", "expo"]):
        scores["app"] += 2
        signals.append("app:framework")


def _score_library_package(
    scores: Counter[str],
    signals: List[str],
    paths: Sequence[str],
    text: str,
    package: Mapping[str, Any],
    surfaces: Sequence[Mapping[str, Any]],
) -> None:
    surface_types = {str(surface.get("type") or "") for surface in surfaces if surface.get("type")}
    if surface_types and surface_types.issubset({"package"}):
        scores["library_package"] += 5
        signals.append("package:surface")
    path_text = " ".join(paths).lower()
    if _contains_any(path_text, ["/sdk/", "/lib/", "/library/", "/packages/"]):
        scores["library_package"] += 3
        signals.append("package:path")
    if _contains_any(text.lower(), ["sdk", "library", "package", "client library"]):
        scores["library_package"] += 2
        signals.append("package:copy")
    if package.get("manifests") and not surfaces:
        scores["library_package"] += 2
        signals.append("package:manifest")


def _dominant_kind(scores: Counter[str]) -> str:
    return sorted(
        scores,
        key=lambda kind: (scores[kind], _KIND_PRIORITY.get(kind, 0), kind),
        reverse=True,
    )[0]


def _confidence_score(scores: Counter[str], kind: str) -> float:
    winner = max(0, int(scores.get(kind) or 0))
    runner_up = max([int(value) for key, value in scores.items() if key != kind] or [0])
    score = 0.45 + min(0.35, winner * 0.04) + min(0.15, max(0, winner - runner_up) * 0.03)
    return round(min(0.95, score), 2)


def _fallback_kind(paths: Sequence[str]) -> str:
    if any(PurePosixPath(path).name in _MANIFEST_NAMES for path in paths):
        return "library_package"
    if any(PurePosixPath(path).suffix.lower() in {".md", ".mdx", ".rst"} for path in paths):
        return "learning_program"
    return "tool_product"


def _workspace_name(ir: Mapping[str, Any], workspace_path: Optional[Path]) -> str:
    workspace_info = ir.get("workspace") if isinstance(ir.get("workspace"), Mapping) else {}
    name = workspace_info.get("name")
    if isinstance(name, str) and name.strip():
        return name.strip()
    if workspace_path is not None:
        return workspace_path.name
    return "workspace"


def _workspace_path_from_ir(ir: Mapping[str, Any]) -> Optional[Path]:
    workspace_info = ir.get("workspace") if isinstance(ir.get("workspace"), Mapping) else {}
    root = workspace_info.get("root")
    if isinstance(root, str) and root:
        return Path(root)
    return None


def _app_surfaces(ir: Mapping[str, Any]) -> List[Mapping[str, Any]]:
    return [surface for surface in ir.get("app_surfaces") or [] if isinstance(surface, Mapping)]


def _known_paths(
    ir: Mapping[str, Any],
    workspace: Optional[Path],
    files: Optional[Sequence[str | Path]],
) -> List[str]:
    paths: List[str] = []
    package = ir.get("package") if isinstance(ir.get("package"), Mapping) else {}
    for manifest in package.get("manifests") or []:
        if isinstance(manifest, Mapping) and isinstance(manifest.get("path"), str):
            paths.append(manifest["path"])

    for surface in _app_surfaces(ir):
        root = surface.get("root")
        if isinstance(root, str):
            paths.append(root)
        for manifest_path in surface.get("manifest_paths") or []:
            if isinstance(manifest_path, str):
                paths.append(manifest_path)
        for hint in surface.get("entry_hints") or []:
            if isinstance(hint, Mapping) and isinstance(hint.get("path"), str):
                paths.append(hint["path"])

    source_facts = ir.get("source_facts") if isinstance(ir.get("source_facts"), Mapping) else {}
    for fact in source_facts.get("facts") or []:
        if not isinstance(fact, Mapping):
            continue
        for evidence in fact.get("evidence") or []:
            if isinstance(evidence, Mapping) and isinstance(evidence.get("path"), str):
                paths.append(evidence["path"])

    if files:
        for path in files:
            paths.append(normalize_path(str(path)))

    if workspace is not None and workspace.exists():
        paths.extend(_scan_workspace_paths(workspace))

    return sorted(_dedupe(normalize_path(path) for path in paths if path))


def _scan_workspace_paths(workspace: Path, *, limit: int = 600) -> List[str]:
    paths: List[str] = []
    try:
        root = workspace.resolve()
    except OSError:
        return paths
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [dirname for dirname in dirnames if dirname not in _SKIP_DIRS and not dirname.startswith(".")]
        for filename in filenames:
            path = Path(dirpath) / filename
            try:
                paths.append(normalize_path(str(path.relative_to(root))))
            except ValueError:
                continue
            if len(paths) >= limit:
                return paths
    return paths


def _read_workspace_text(workspace: Optional[Path], paths: Sequence[str], *, max_chars: int = 80_000) -> str:
    if workspace is None or not workspace.exists():
        return ""

    candidates = _text_candidates(paths)
    chunks: List[str] = []
    total = 0
    for rel in candidates:
        path = workspace / rel
        try:
            if not path.is_file() or path.stat().st_size > 300_000:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        remaining = max_chars - total
        if remaining <= 0:
            break
        chunks.append(text[: min(remaining, 20_000)])
        total += len(chunks[-1])
    return "\n".join(chunks)


def _text_candidates(paths: Sequence[str]) -> List[str]:
    candidates: List[str] = []
    for rel in paths:
        path = PurePosixPath(rel)
        suffix = path.suffix.lower()
        stem = path.stem.lower()
        name = path.name
        parts = {part.lower() for part in path.parts}
        if name in _MANIFEST_NAMES:
            candidates.append(rel)
            continue
        if suffix not in _TEXT_SUFFIXES:
            continue
        if stem in _TEXT_CANDIDATE_NAMES or parts.intersection(_TEXT_CANDIDATE_NAMES):
            candidates.append(rel)
            continue
        if len(path.parts) <= 2 and suffix in {".md", ".mdx", ".rst", ".txt"}:
            candidates.append(rel)
    return _dedupe(candidates)[:25]


def _contains_any(text: str, needles: Iterable[str]) -> bool:
    return any(needle in text for needle in needles)


def _dedupe(values: Iterable[str]) -> List[str]:
    seen: set[str] = set()
    result: List[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
