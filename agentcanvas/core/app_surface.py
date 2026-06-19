"""App-surface detection for monorepo workspaces.

An app surface is the deployable or user-facing boundary a source path belongs
to: mobile app, web app, backend service, or a less-specific package. The
detector is intentionally manifest-first so it can distinguish similarly named
flows such as mobile/web/backend signup paths in a monorepo.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from .model import normalize_id_segment, normalize_path

SUPPORTED_MANIFESTS = {
    "package.json",
    "pubspec.yaml",
    "go.mod",
    "composer.json",
    "Gemfile",
    "pyproject.toml",
    "requirements.txt",
    "Cargo.toml",
}

SOURCE_HINT_EXTENSIONS = {
    ".cjs",
    ".dart",
    ".go",
    ".js",
    ".jsx",
    ".kt",
    ".kts",
    ".mjs",
    ".php",
    ".py",
    ".rb",
    ".swift",
    ".ts",
    ".tsx",
}

WEB_DEPENDENCIES = {
    "@angular/core": "angular",
    "@remix-run/react": "remix",
    "@sveltejs/kit": "sveltekit",
    "astro": "astro",
    "next": "next",
    "react": "react",
    "react-dom": "react",
    "svelte": "svelte",
    "vite": "vite",
    "vue": "vue",
}
MOBILE_DEPENDENCIES = {
    "expo": "expo",
    "react-native": "react-native",
    "@react-native-community/cli": "react-native",
}
NODE_BACKEND_DEPENDENCIES = {
    "@nestjs/core": "nestjs",
    "express": "express",
    "fastify": "fastify",
    "hapi": "hapi",
    "koa": "koa",
}
GO_FRAMEWORKS = {
    "github.com/gin-gonic/gin": "gin",
    "github.com/go-chi/chi": "chi",
    "github.com/gofiber/fiber": "fiber",
    "github.com/labstack/echo": "echo",
}
COMPOSER_FRAMEWORKS = {
    "laravel/framework": "laravel",
    "symfony/framework-bundle": "symfony",
}
GEM_FRAMEWORKS = {
    "rails": "rails",
    "sinatra": "sinatra",
}

TYPE_PRIORITY = {"mobile": 4, "web": 3, "backend": 2, "package": 1}


class _SurfaceAccumulator:
    def __init__(self, root: str) -> None:
        self.root = root
        self.manifest_paths: set[str] = set()
        self.type_scores: Counter[str] = Counter()
        self.frameworks: set[str] = set()
        self.languages: set[str] = set()
        self.signals: set[str] = set()

    def add(self, signal: Mapping[str, Any]) -> None:
        self.manifest_paths.add(str(signal["path"]))
        for app_type, score in (signal.get("type_scores") or {}).items():
            self.type_scores[str(app_type)] += int(score)
        self.frameworks.update(str(item) for item in signal.get("frameworks") or [])
        self.languages.update(str(item) for item in signal.get("languages") or [])
        self.signals.update(str(item) for item in signal.get("signals") or [])


def detect_app_surfaces(root: str | Path, files: Sequence[str | Path]) -> List[Dict[str, Any]]:
    """Infer app surfaces from workspace manifests and path conventions.

    The return value is a list of JSON-serializable dictionaries with stable
    `id`, `type`, `root`, manifest, and entry-hint fields.
    """

    workspace = Path(root)
    rel_paths = sorted(_relative_paths(workspace, files))
    rel_path_set = set(rel_paths)
    by_root: Dict[str, _SurfaceAccumulator] = {}

    for rel in rel_paths:
        name = PurePosixPath(rel).name
        if name not in SUPPORTED_MANIFESTS:
            continue

        path = workspace / rel
        signal = _classify_manifest(path, rel)
        if not signal:
            continue

        manifest_root = normalize_path(str(PurePosixPath(rel).parent))
        accumulator = by_root.setdefault(manifest_root, _SurfaceAccumulator(manifest_root))
        accumulator.add(signal)

    surfaces = [_surface_from_accumulator(item, rel_path_set) for item in by_root.values()]
    _assign_surface_ids(surfaces)
    return sorted(surfaces, key=lambda item: (item["root"], item["id"]))


def app_surface_for_path(
    path: str | Path,
    app_surfaces: Sequence[Mapping[str, Any]],
) -> Optional[Mapping[str, Any]]:
    """Return the most specific app surface containing `path`, if any."""

    rel = normalize_path(str(path))
    best: Optional[Mapping[str, Any]] = None
    best_depth = -1
    for surface in app_surfaces:
        root = normalize_path(str(surface.get("root") or "."))
        if not _path_is_under_root(rel, root):
            continue
        depth = 0 if root == "." else len(PurePosixPath(root).parts)
        if depth > best_depth:
            best = surface
            best_depth = depth
    return best


def app_surface_id_for_path(
    path: str | Path,
    app_surfaces: Sequence[Mapping[str, Any]],
) -> Optional[str]:
    surface = app_surface_for_path(path, app_surfaces)
    return str(surface["id"]) if surface else None


def enrich_app_surfaces(
    app_surfaces: Sequence[Mapping[str, Any]],
    file_infos: Sequence[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    """Add source/test counts and route hints to detected app surfaces."""

    enriched = [_copy_surface(surface) for surface in app_surfaces]
    by_id = {surface["id"]: surface for surface in enriched}
    for surface in enriched:
        surface["source_files"] = 0
        surface["test_files"] = 0
        surface["route_count"] = 0

    for info in file_infos:
        path = str(info.get("path") or "")
        surface_id = info.get("app_surface_id") or app_surface_id_for_path(path, enriched)
        if not surface_id or surface_id not in by_id:
            continue

        surface = by_id[str(surface_id)]
        surface["source_files"] += 1
        if info.get("is_test"):
            surface["test_files"] += 1

        for route in info.get("routes") or []:
            if not isinstance(route, Mapping):
                continue
            route_path = route.get("path")
            route_file = str(route.get("file") or path)
            if not route_path:
                continue
            method = str(route.get("method") or "ANY")
            detail = f"{method} {route_path}"
            if _append_hint(
                surface,
                {
                    "kind": "route",
                    "path": route_file,
                    "detail": detail,
                    "source": "route-extraction",
                },
            ):
                surface["route_count"] += 1

    return enriched


def annotate_bundle_with_surfaces(
    bundle: Dict[str, Any],
    app_surfaces: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    """Annotate raw language facts with app-surface metadata in place."""

    if not app_surfaces:
        return bundle

    for fact in bundle.get("facts") or []:
        if not isinstance(fact, dict):
            continue
        source_path = _fact_source_path(fact)
        if not source_path:
            continue
        surface = app_surface_for_path(source_path, app_surfaces)
        if not surface:
            continue
        fact.setdefault("app_surface_id", surface.get("id"))
        fact.setdefault("app_surface_type", surface.get("type"))
        fact.setdefault("app_surface_root", surface.get("root"))
    return bundle


def _surface_from_accumulator(
    accumulator: _SurfaceAccumulator,
    rel_path_set: set[str],
) -> Dict[str, Any]:
    app_type = _dominant_type(accumulator.type_scores)
    name = _surface_name(accumulator.root)
    signals = sorted(accumulator.signals)
    surface: Dict[str, Any] = {
        "id": "",
        "name": name,
        "type": app_type,
        "root": accumulator.root,
        "manifest_paths": sorted(accumulator.manifest_paths),
        "frameworks": sorted(accumulator.frameworks),
        "languages": sorted(accumulator.languages),
        "entry_hints": _entry_hints(accumulator.root, app_type, rel_path_set),
        "confidence": {
            "score": _confidence_score(accumulator.type_scores),
            "signals": signals,
        },
    }
    return surface


def _assign_surface_ids(surfaces: List[Dict[str, Any]]) -> None:
    base_ids = [f"app:{normalize_id_segment(surface['name'], 'root')}" for surface in surfaces]
    duplicate_ids = {item for item in base_ids if base_ids.count(item) > 1}
    for surface, base_id in zip(surfaces, base_ids):
        if base_id in duplicate_ids:
            surface["id"] = f"app:{normalize_id_segment(surface['root'], 'root')}"
        else:
            surface["id"] = base_id


def _classify_manifest(path: Path, rel: str) -> Optional[Dict[str, Any]]:
    name = PurePosixPath(rel).name
    text = _safe_read_text(path)
    root = normalize_path(str(PurePosixPath(rel).parent))
    root_score = _path_type_score(root)

    if name == "pubspec.yaml":
        frameworks = ["flutter"] if _contains_any(text, ["flutter:", "sdk: flutter"]) else ["dart"]
        return _manifest_signal(
            rel,
            {"mobile": 4},
            frameworks=frameworks,
            languages=["dart"],
            signals=["manifest:pubspec.yaml"],
        )

    if name == "go.mod":
        frameworks = [framework for module, framework in GO_FRAMEWORKS.items() if module in text]
        return _manifest_signal(
            rel,
            {"backend": 4},
            frameworks=frameworks or ["go"],
            languages=["go"],
            signals=["manifest:go.mod"],
        )

    if name == "composer.json":
        package_json = _load_json(text)
        require = _json_dependency_names(package_json, ("require", "require-dev"))
        frameworks = sorted({framework for package, framework in COMPOSER_FRAMEWORKS.items() if package in require})
        return _manifest_signal(
            rel,
            {"backend": 4},
            frameworks=frameworks or ["composer"],
            languages=["php"],
            signals=["manifest:composer.json"],
        )

    if name == "Gemfile":
        frameworks = sorted({framework for gem, framework in GEM_FRAMEWORKS.items() if _gem_declared(text, gem)})
        return _manifest_signal(
            rel,
            {"backend": 4},
            frameworks=frameworks or ["ruby"],
            languages=["ruby"],
            signals=["manifest:Gemfile"],
        )

    if name == "pyproject.toml":
        scores = Counter(root_score)
        if scores:
            scores["backend"] += 1
        elif _contains_any(text, ["fastapi", "django", "flask", "starlette"]):
            scores["backend"] += 3
        if not scores:
            return None
        return _manifest_signal(
            rel,
            scores,
            frameworks=_python_frameworks(text),
            languages=["python"],
            signals=["manifest:pyproject.toml"],
        )

    if name == "requirements.txt":
        if not (_contains_any(text, ["fastapi", "django", "flask", "starlette"]) or root_score):
            return None
        scores = Counter(root_score)
        scores["backend"] += 2
        return _manifest_signal(
            rel,
            scores,
            frameworks=_python_frameworks(text),
            languages=["python"],
            signals=["manifest:requirements.txt"],
        )

    if name == "Cargo.toml":
        scores = Counter(root_score)
        if scores:
            scores["backend"] += 1
        elif _contains_any(text, ["actix-web", "axum", "rocket", "warp"]):
            scores["backend"] += 3
        if not scores:
            return None
        return _manifest_signal(
            rel,
            scores,
            frameworks=_rust_frameworks(text),
            languages=["rust"],
            signals=["manifest:Cargo.toml"],
        )

    if name == "package.json":
        package_json = _load_json(text)
        if not package_json:
            return None
        return _classify_package_json(rel, package_json, root_score)

    return None


def _classify_package_json(
    rel: str,
    package_json: Mapping[str, Any],
    root_score: Counter[str],
) -> Optional[Dict[str, Any]]:
    deps = _json_dependency_names(package_json, ("dependencies", "devDependencies", "peerDependencies"))
    scripts = package_json.get("scripts") if isinstance(package_json.get("scripts"), Mapping) else {}
    script_text = " ".join(str(value).lower() for value in scripts.values())
    scores = Counter(root_score)
    frameworks: set[str] = set()
    signals = ["manifest:package.json"]

    for package, framework in MOBILE_DEPENDENCIES.items():
        if package in deps:
            scores["mobile"] += 4
            frameworks.add(framework)

    for package, framework in WEB_DEPENDENCIES.items():
        if package in deps:
            scores["web"] += 3
            frameworks.add(framework)

    for package, framework in NODE_BACKEND_DEPENDENCIES.items():
        if package in deps:
            scores["backend"] += 3
            frameworks.add(framework)

    if re.search(r"\b(next|vite|webpack|remix|astro|svelte-kit)\b", script_text):
        scores["web"] += 2
        if "next" in script_text:
            frameworks.add("next")
        if "vite" in script_text:
            frameworks.add("vite")

    if re.search(r"\b(node|tsx|ts-node|nest|fastify)\b", script_text):
        scores["backend"] += 1

    if not scores:
        if package_json.get("workspaces"):
            return None
        return _manifest_signal(
            rel,
            {"package": 1},
            frameworks=[],
            languages=["javascript-typescript"],
            signals=signals,
        )

    return _manifest_signal(
        rel,
        scores,
        frameworks=sorted(frameworks),
        languages=["javascript-typescript"],
        signals=signals,
    )


def _manifest_signal(
    rel: str,
    type_scores: Mapping[str, int],
    *,
    frameworks: Iterable[str],
    languages: Iterable[str],
    signals: Iterable[str],
) -> Dict[str, Any]:
    return {
        "path": rel,
        "type_scores": {key: int(value) for key, value in type_scores.items()},
        "frameworks": sorted(set(frameworks)),
        "languages": sorted(set(languages)),
        "signals": sorted(set(signals)),
    }


def _dominant_type(scores: Counter[str]) -> str:
    if not scores:
        return "package"
    return sorted(
        scores.items(),
        key=lambda item: (item[1], TYPE_PRIORITY.get(item[0], 0), item[0]),
        reverse=True,
    )[0][0]


def _confidence_score(scores: Counter[str]) -> float:
    if not scores:
        return 0.4
    total = sum(scores.values())
    winner = scores[_dominant_type(scores)]
    score = 0.55 + min(0.4, winner / max(total, 1) * 0.4)
    if winner >= 4:
        score += 0.05
    return round(min(score, 0.99), 2)


def _path_type_score(root: str) -> Counter[str]:
    parts = {part.lower() for part in PurePosixPath(root).parts}
    scores: Counter[str] = Counter()
    if parts.intersection({"mobile", "ios", "android", "flutter"}):
        scores["mobile"] += 2
    if parts.intersection({"client", "frontend", "site", "web", "www"}):
        scores["web"] += 2
    if parts.intersection({"api", "backend", "server", "service", "services", "worker"}):
        scores["backend"] += 2
    return scores


def _entry_hints(root: str, app_type: str, rel_path_set: set[str]) -> List[Dict[str, str]]:
    hints: List[Tuple[int, Dict[str, str]]] = []
    for rel in sorted(rel_path_set):
        if not _path_is_under_root(rel, root):
            continue
        path = PurePosixPath(rel)
        if path.name in SUPPORTED_MANIFESTS or path.suffix.lower() not in SOURCE_HINT_EXTENSIONS:
            continue
        relative_parts = PurePosixPath(_strip_root(rel, root)).parts
        hint = _entry_hint_for_path(rel, relative_parts, app_type)
        if not hint:
            continue
        priority = _hint_priority(rel, hint)
        hints.append((priority, hint))

    deduped: List[Dict[str, str]] = []
    seen: set[Tuple[str, str, str]] = set()
    for _, hint in sorted(hints, key=lambda item: (item[0], item[1]["path"], item[1]["kind"])):
        key = (hint["kind"], hint["path"], hint.get("detail", ""))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(hint)
        if len(deduped) >= 25:
            break
    return deduped


def _entry_hint_for_path(
    rel: str,
    relative_parts: Tuple[str, ...],
    app_type: str,
) -> Optional[Dict[str, str]]:
    lowered = rel.lower()
    part_set = {part.lower() for part in relative_parts}
    name = PurePosixPath(rel).name.lower()

    if app_type == "mobile":
        if relative_parts == ("lib", "main.dart") or name in {"main.dart", "app.dart"}:
            return {"kind": "mobile-entry", "path": rel, "detail": "Flutter/Dart app entry"}
        if part_set.intersection({"features", "flows", "pages", "routes", "screens", "views"}) or "signup" in lowered:
            return {"kind": "mobile-screen", "path": rel, "detail": _human_flow_detail(rel)}
        return None

    if app_type == "web":
        if name in {"main.tsx", "main.jsx", "app.tsx", "app.jsx", "index.tsx", "index.jsx"}:
            return {"kind": "web-entry", "path": rel, "detail": "browser app entry"}
        route = _web_route_from_parts(relative_parts)
        if route:
            return {"kind": "web-route", "path": rel, "detail": route}
        if "signup" in lowered:
            return {"kind": "web-route", "path": rel, "detail": _human_flow_detail(rel)}
        return None

    if app_type == "backend":
        if name in {"main.go", "server.go", "app.go", "index.js", "server.js", "main.py"}:
            return {"kind": "backend-entry", "path": rel, "detail": "service entry"}
        if part_set.intersection({"controllers", "handlers", "routes", "router", "views"}) or "signup" in lowered:
            return {"kind": "backend-handler", "path": rel, "detail": _human_flow_detail(rel)}
        return None

    if "signup" in lowered:
        return {"kind": "flow", "path": rel, "detail": _human_flow_detail(rel)}
    return None


def _hint_priority(rel: str, hint: Mapping[str, str]) -> int:
    kind = hint.get("kind") or ""
    if kind.endswith("entry"):
        return 0
    if "signup" in rel.lower():
        return 1
    if "route" in kind or "handler" in kind:
        return 2
    return 5


def _web_route_from_parts(relative_parts: Tuple[str, ...]) -> Optional[str]:
    parts = list(relative_parts)
    if parts[:2] == ["src", "app"]:
        route_parts = parts[2:]
        if route_parts and PurePosixPath(route_parts[-1]).stem in {"page", "route"}:
            return _route_detail(route_parts[:-1])
    if parts[:2] == ["src", "pages"]:
        return _route_detail(parts[2:])
    if parts and parts[0] in {"app", "pages"}:
        route_parts = parts[1:]
        if parts[0] == "app" and route_parts and PurePosixPath(route_parts[-1]).stem not in {"page", "route"}:
            return None
        return _route_detail(route_parts[:-1] if parts[0] == "app" else route_parts)
    if parts and parts[0] == "routes":
        return _route_detail(parts[1:])
    return None


def _route_detail(route_parts: Sequence[str]) -> str:
    cleaned = []
    for part in route_parts:
        stem = PurePosixPath(part).stem
        if not stem or (stem.startswith("(") and stem.endswith(")")):
            continue
        if stem == "index":
            continue
        if stem.startswith("[...") and stem.endswith("]"):
            cleaned.append(f"*{stem[4:-1]}")
        elif stem.startswith("[") and stem.endswith("]"):
            cleaned.append(f":{stem[1:-1]}")
        else:
            cleaned.append(stem)
    return "/" + "/".join(cleaned)


def _human_flow_detail(rel: str) -> str:
    lowered = rel.lower()
    if "signup" in lowered or "sign-up" in lowered or "sign_up" in lowered:
        return "signup flow"
    if "login" in lowered or "sign-in" in lowered or "signin" in lowered:
        return "login flow"
    return "entry hint"


def _append_hint(surface: Dict[str, Any], hint: Dict[str, str]) -> bool:
    hints = surface.setdefault("entry_hints", [])
    key = (hint.get("kind"), hint.get("path"), hint.get("detail"))
    for existing in hints:
        if (
            existing.get("kind"),
            existing.get("path"),
            existing.get("detail"),
        ) == key:
            return False
    hints.append(hint)
    if len(hints) > 25:
        del hints[25:]
    return True


def _fact_source_path(fact: Mapping[str, Any]) -> Optional[str]:
    for key in ("source_ref", "provenance"):
        ref = fact.get(key)
        if isinstance(ref, Mapping) and isinstance(ref.get("path"), str):
            return str(ref["path"])
    for key in ("file", "source", "path"):
        value = fact.get(key)
        if isinstance(value, str) and value and not value.startswith("/"):
            return value
    return None


def _copy_surface(surface: Mapping[str, Any]) -> Dict[str, Any]:
    copied: Dict[str, Any] = {}
    for key, value in surface.items():
        if isinstance(value, list):
            copied[key] = [dict(item) if isinstance(item, Mapping) else item for item in value]
        elif isinstance(value, dict):
            copied[key] = dict(value)
        else:
            copied[key] = value
    return copied


def _path_is_under_root(path: str, root: str) -> bool:
    rel = normalize_path(path)
    surface_root = normalize_path(root)
    if surface_root == ".":
        return not rel.startswith("../")
    return rel == surface_root or rel.startswith(f"{surface_root}/")


def _strip_root(path: str, root: str) -> str:
    rel = normalize_path(path)
    surface_root = normalize_path(root)
    if surface_root == ".":
        return rel
    if rel == surface_root:
        return "."
    prefix = f"{surface_root}/"
    return rel[len(prefix) :] if rel.startswith(prefix) else rel


def _surface_name(root: str) -> str:
    if root == ".":
        return "root"
    parts = PurePosixPath(root).parts
    return parts[-1] if parts else "root"


def _relative_paths(root: Path, files: Sequence[str | Path]) -> List[str]:
    rels = []
    resolved_root = root.resolve()
    for raw_path in files:
        path = Path(raw_path)
        try:
            if path.is_absolute():
                rel = path.resolve().relative_to(resolved_root)
            else:
                rel = path
        except (OSError, ValueError):
            continue
        rels.append(normalize_path(str(rel)))
    return rels


def _safe_read_text(path: Path) -> str:
    try:
        if path.stat().st_size > 1_000_000:
            return ""
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _load_json(text: str) -> Dict[str, Any]:
    try:
        value = json.loads(text or "{}")
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _json_dependency_names(package_json: Mapping[str, Any], sections: Sequence[str]) -> set[str]:
    names: set[str] = set()
    for section in sections:
        value = package_json.get(section)
        if isinstance(value, Mapping):
            names.update(str(key) for key in value.keys())
    return names


def _contains_any(text: str, needles: Iterable[str]) -> bool:
    lowered = text.lower()
    return any(needle.lower() in lowered for needle in needles)


def _gem_declared(text: str, gem: str) -> bool:
    return re.search(rf"\bgem\s+['\"]{re.escape(gem)}['\"]", text) is not None


def _python_frameworks(text: str) -> List[str]:
    frameworks = []
    for name in ["django", "fastapi", "flask", "starlette"]:
        if name in text.lower():
            frameworks.append(name)
    return frameworks or ["python"]


def _rust_frameworks(text: str) -> List[str]:
    frameworks = []
    for name in ["actix-web", "axum", "rocket", "warp"]:
        if name in text.lower():
            frameworks.append(name)
    return frameworks or ["rust"]
