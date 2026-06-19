"""JavaScript and TypeScript source fact extraction.

This module is intentionally dependency-light for the MVP. It emits a flat,
language-neutral source-fact bundle that a shared mapper can turn into graph
nodes and edges. The public API is parser-oriented so a stronger AST-backed
implementation can replace the regex internals later without changing callers.
"""

from __future__ import annotations

import os
import re
from bisect import bisect_right
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

SOURCE_EXTENSIONS = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}
IMPORT_EXTENSIONS = [".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".json"]
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
MAX_FILE_BYTES = 1_000_000

FACT_SCHEMA = "agentcanvas.source_facts.v1"
PARSER_NAME = "js-ts-regex-mvp"
PARSER_VERSION = "0.1.0"

IDENTIFIER = r"[A-Za-z_$][\w$]*"
HTTP_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}

IMPORT_RE = re.compile(
    rf"""
    (?P<static>\bimport\s+(?P<body>[^;]*?)\s+from\s*(?P<quote>["'])(?P<specifier>[^"']+)(?P=quote))
    |(?P<side>\bimport\s*(?P<side_quote>["'])(?P<side_specifier>[^"']+)(?P=side_quote))
    |(?P<reexport>\bexport\s+(?P<reexport_body>[^;]*?)\s+from\s*(?P<reexport_quote>["'])(?P<reexport_specifier>[^"']+)(?P=reexport_quote))
    |(?P<require>\brequire\(\s*(?P<require_quote>["'])(?P<require_specifier>[^"']+)(?P=require_quote)\s*\))
    |(?P<dynamic>\bimport\(\s*(?P<dynamic_quote>["'])(?P<dynamic_specifier>[^"']+)(?P=dynamic_quote)\s*\))
    """,
    re.VERBOSE | re.MULTILINE | re.DOTALL,
)
DECL_RE = re.compile(
    rf"""
    (?P<export>\bexport\s+(?P<default>default\s+)?)?
    (?P<async>async\s+)?
    (?P<kind>function|class|const|let|var|type|interface|enum)
    (?:\s+(?P<name>{IDENTIFIER}))?
    """,
    re.VERBOSE | re.MULTILINE,
)
EXPORT_NAMED_RE = re.compile(
    r"\bexport\s*\{(?P<body>[^}]+)\}\s*(?:from\s*(?P<quote>[\"'])(?P<specifier>[^\"']+)(?P=quote))?",
    re.MULTILINE | re.DOTALL,
)
EXPORT_STAR_RE = re.compile(
    r"\bexport\s+\*\s*(?:as\s+(?P<name>[A-Za-z_$][\w$]*)\s*)?from\s*(?P<quote>[\"'])(?P<specifier>[^\"']+)(?P=quote)",
    re.MULTILINE,
)
EXPORT_DEFAULT_RE = re.compile(
    rf"\bexport\s+default\s+(?!(?:async\s+)?(?:function|class)\b)(?P<name>{IDENTIFIER})?",
    re.MULTILINE,
)
CJS_EXPORT_RE = re.compile(rf"\b(?:module\.)?exports\.(?P<name>{IDENTIFIER})\s*=")
CJS_OBJECT_EXPORT_RE = re.compile(
    r"\bmodule\.exports\s*=\s*\{(?P<body>[^}]+)\}", re.MULTILINE | re.DOTALL
)
ROUTE_CALL_RE = re.compile(
    rf"""
    \b(?P<receiver>{IDENTIFIER}(?:\.{IDENTIFIER})*)\s*\.\s*
    (?P<method>get|post|put|patch|delete|del|all|use|route)\s*
    \(\s*(?P<quote>["'`])(?P<path>[^"'`]+)(?P=quote)(?P<tail>[^)]*)
    """,
    re.VERBOSE | re.IGNORECASE | re.MULTILINE | re.DOTALL,
)
GENERIC_ROUTE_RE = re.compile(
    r"\broute\s*\(\s*(?P<quote>[\"'`])(?P<path>[^\"'`]+)(?P=quote)",
    re.IGNORECASE,
)
ROUTE_OBJECT_RE = re.compile(
    r"\{(?P<body>[^{}]*(?:method|path)\s*:\s*[^{}]*)\}", re.MULTILINE | re.DOTALL
)
PROPERTY_RE = re.compile(
    r"(?P<key>method|path|handler)\s*:\s*(?P<quote>[\"'`])(?P<value>[^\"'`]+)(?P=quote)",
    re.IGNORECASE,
)
IF_RE = re.compile(r"\bif\b")
ELSE_RE = re.compile(r"\belse\b")
SWITCH_RE = re.compile(r"\bswitch\b")
CASE_RE = re.compile(r"\bcase\s+(?P<condition>[^:]+):|\bdefault\s*:")


def parse_workspace(
    root: str | Path,
    paths: Optional[Sequence[str | Path]] = None,
) -> Dict[str, Any]:
    """Extract JS/TS source facts for a workspace root."""

    return JsTsExtractor(root).extract_workspace(paths=paths)


def extract_source_facts(
    path: str | Path,
    source: Optional[str] = None,
) -> Dict[str, Any]:
    """Extract mapper-facing facts from a JS/TS source file or source string."""

    return parse_file(path, text=source)


def extract_file(path: str | Path) -> Dict[str, Any]:
    """Read and extract facts from a JS/TS file."""

    return parse_file(path)


def parse_file(
    path: str | Path,
    *,
    root: str | Path | None = None,
    text: Optional[str] = None,
) -> Dict[str, Any]:
    """Extract JS/TS source facts for one file or supplied text."""

    file_path = Path(path)
    workspace_root = Path(root).expanduser().resolve() if root else file_path.parent
    return JsTsExtractor(workspace_root).extract_path(file_path, text=text)


class JsTsExtractor:
    """Dependency-light JS/TS fact extractor.

    The class boundary is the replacement point for a future AST parser. Public
    methods return the same source-fact bundle shape regardless of internals.
    """

    def __init__(self, root: str | Path):
        self.root = Path(root).expanduser().resolve()

    def extract_workspace(
        self,
        paths: Optional[Sequence[str | Path]] = None,
    ) -> Dict[str, Any]:
        source_paths = self._source_paths(paths)
        source_set = {to_posix(path.relative_to(self.root)) for path in source_paths}
        bundle = empty_bundle(root=self.root)

        for path in source_paths:
            merge_bundle(bundle, self.extract_path(path, source_set=source_set))

        finalize_bundle(bundle)
        return bundle

    def extract_path(
        self,
        path: str | Path,
        *,
        text: Optional[str] = None,
        source_set: Optional[set[str]] = None,
    ) -> Dict[str, Any]:
        file_path = Path(path)
        if not file_path.is_absolute():
            file_path = self.root / file_path

        rel = self._relative_path(file_path)
        readable = True
        if text is None:
            text = safe_read_text(file_path)
            readable = text is not None
        if text is None:
            text = ""

        return self.extract_text(
            rel,
            text,
            readable=readable,
            source_set=source_set or set(),
        )

    def extract_text(
        self,
        rel: str,
        text: str,
        *,
        readable: bool = True,
        source_set: Optional[set[str]] = None,
    ) -> Dict[str, Any]:
        source_set = source_set or set()
        bundle = empty_bundle(root=None)
        bundle["files"].append(file_fact(rel, text, readable=readable))

        comment_masked = mask_source(text, mask_strings=False)
        structural_code = mask_source(text, mask_strings=True)

        imports = extract_imports(text, comment_masked, rel)
        for imported in imports:
            imported["resolved_path"] = resolve_import(
                self.root,
                rel,
                imported["specifier"],
                source_set,
            )

        symbols, exports = extract_symbols_and_exports(
            text,
            structural_code,
            comment_masked,
            rel,
        )
        routes = extract_routes(text, comment_masked, rel, symbols)
        branches = extract_branches(text, structural_code, rel)

        bundle["imports"].extend(imports)
        bundle["symbols"].extend(symbols)
        bundle["exports"].extend(exports)
        bundle["routes"].extend(routes)
        bundle["branches"].extend(branches)
        finalize_bundle(bundle)
        return bundle

    def _source_paths(self, paths: Optional[Sequence[str | Path]]) -> List[Path]:
        if paths is not None:
            candidates = [
                path if isinstance(path, Path) else Path(path)
                for path in paths
            ]
            resolved = [
                path if path.is_absolute() else self.root / path
                for path in candidates
            ]
            return sorted(path.resolve() for path in resolved if is_source_file(path))

        found: List[Path] = []
        for dirpath, dirnames, filenames in os.walk(self.root):
            dirnames[:] = [
                dirname
                for dirname in dirnames
                if should_descend_into(dirname)
            ]
            for filename in filenames:
                path = Path(dirpath) / filename
                if is_source_file(path):
                    found.append(path.resolve())
        return sorted(found)

    def _relative_path(self, file_path: Path) -> str:
        try:
            return to_posix(file_path.resolve().relative_to(self.root))
        except (OSError, ValueError):
            return to_posix(file_path.name)


def empty_bundle(root: Optional[Path]) -> Dict[str, Any]:
    return {
        "schema": FACT_SCHEMA,
        "language": "javascript-typescript",
        "language_family": "javascript-typescript",
        "parser": {
            "name": PARSER_NAME,
            "version": PARSER_VERSION,
            "strategy": "regex",
            "capabilities": [
                "files",
                "imports",
                "symbols",
                "exports",
                "routes",
                "branches",
                "source_refs",
            ],
        },
        "root": str(root) if root else None,
        "files": [],
        "symbols": [],
        "exports": [],
        "imports": [],
        "routes": [],
        "branches": [],
        "diagnostics": [],
        "facts": [],
        "summary": {
            "total": 0,
            "by_type": {},
            "by_kind": {},
        },
    }


def merge_bundle(target: Dict[str, Any], source: Dict[str, Any]) -> None:
    for key in ["files", "symbols", "exports", "imports", "routes", "branches", "diagnostics"]:
        target[key].extend(source.get(key) or [])


def finalize_bundle(bundle: Dict[str, Any]) -> None:
    facts: List[Dict[str, Any]] = []
    for key in ["files", "imports", "symbols", "exports", "routes", "branches", "diagnostics"]:
        facts.extend(bundle.get(key) or [])
    bundle["facts"] = facts
    bundle["summary"] = summary_for_facts(facts)


def summary_for_facts(facts: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    by_type: Dict[str, int] = {}
    by_kind: Dict[str, int] = {}
    for fact in facts:
        fact_type = str(fact.get("type") or "unknown")
        kind = str(fact.get("kind") or "unknown")
        by_type[fact_type] = by_type.get(fact_type, 0) + 1
        by_kind[kind] = by_kind.get(kind, 0) + 1
    return {
        "total": len(facts),
        "by_type": by_type,
        "by_kind": by_kind,
    }


def with_provenance(
    fact: Dict[str, Any],
    rel: str,
    ref: Dict[str, Any],
) -> Dict[str, Any]:
    fact.setdefault("language", language_for_path(rel))
    fact.setdefault("file", rel)
    fact.setdefault("line", ref["line"])
    fact["source_ref"] = ref
    fact["provenance"] = {
        "path": ref["path"],
        "line": ref["line"],
        "column": ref["column"],
        "offset": ref["offset"],
    }
    return fact


def file_fact(rel: str, text: str, *, readable: bool) -> Dict[str, Any]:
    ref = source_ref(text, rel, 0)
    return with_provenance({
        "id": f"file:{rel}",
        "type": "file",
        "kind": "source_file",
        "path": rel,
        "is_test": is_test_path(rel),
        "readable": readable,
        "line_count": text.count("\n") + (1 if text else 0),
    }, rel, ref)


def extract_imports(text: str, code: str, rel: str) -> List[Dict[str, Any]]:
    imports = []
    seen: set[str] = set()
    for match in IMPORT_RE.finditer(code):
        kind, specifier, imported_names = import_match_details(match)
        if not specifier:
            continue
        fact = {
            "id": stable_id("import", rel, specifier, source_ref(text, rel, match.start())["line"], kind),
            "type": "import",
            "kind": kind,
            "import_kind": kind,
            "specifier": specifier,
            "specifier_kind": "local" if specifier.startswith(".") else "package",
            "imported": imported_names,
            "file": rel,
        }
        with_provenance(fact, rel, source_ref(text, rel, match.start()))
        key = fact["id"]
        if key not in seen:
            seen.add(key)
            imports.append(fact)
    return sorted(imports, key=lambda item: source_sort_key(item["source_ref"]))


def import_match_details(match: re.Match[str]) -> Tuple[str, str, List[str]]:
    if match.group("static"):
        return (
            "static",
            match.group("specifier"),
            parse_import_bindings(match.group("body") or ""),
        )
    if match.group("side"):
        return "side-effect", match.group("side_specifier"), []
    if match.group("reexport"):
        return (
            "reexport",
            match.group("reexport_specifier"),
            parse_import_bindings(match.group("reexport_body") or ""),
        )
    if match.group("require"):
        return "commonjs", match.group("require_specifier"), []
    if match.group("dynamic"):
        return "dynamic", match.group("dynamic_specifier"), []
    return "unknown", "", []


def parse_import_bindings(body: str) -> List[str]:
    body = body.strip()
    if not body or body == "type":
        return []

    names: List[str] = []
    body = re.sub(r"^\s*type\s+", "", body)
    namespace = re.search(r"\*\s+as\s+(" + IDENTIFIER + r")", body)
    if namespace:
        names.append(namespace.group(1))

    brace = re.search(r"\{(?P<body>.*)\}", body, re.DOTALL)
    if brace:
        for part in brace.group("body").split(","):
            parsed = parse_export_name(part)
            if parsed:
                names.append(parsed[1])

    default_part = body.split(",", 1)[0].strip()
    if default_part and not default_part.startswith(("{", "*")):
        default_part = re.sub(r"^\s*type\s+", "", default_part)
        if re.fullmatch(IDENTIFIER, default_part):
            names.insert(0, default_part)

    return unique_preserve_order(names)


def extract_symbols_and_exports(
    text: str,
    structural_code: str,
    comment_masked: str,
    rel: str,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    symbols: Dict[str, Dict[str, Any]] = {}
    exports: Dict[str, Dict[str, Any]] = {}

    for match in DECL_RE.finditer(structural_code):
        kind = match.group("kind")
        raw_name = match.group("name")
        if raw_name is None and match.group("export") and match.group("default"):
            raw_name = "default"
        if raw_name is None:
            continue

        depth = brace_depth_at(structural_code, match.start())
        value_kind = infer_value_kind(text, match.end())
        export_kind = None
        if match.group("export"):
            export_kind = "default" if match.group("default") else "named"

        ref = source_ref(text, rel, match.start())
        symbol_id = stable_id("symbol", rel, raw_name, ref["line"], kind)
        symbol_kind = normalise_symbol_kind(kind, value_kind)
        symbols[symbol_id] = {
            "id": symbol_id,
            "type": "symbol",
            "kind": symbol_kind,
            "symbol_kind": symbol_kind,
            "name": raw_name,
            "file": rel,
            "scope": "module" if depth == 0 else "nested",
            "scope_depth": depth,
            "exported": bool(export_kind),
            "export_kind": export_kind,
        }
        with_provenance(symbols[symbol_id], rel, ref)

        if export_kind:
            add_export(
                exports,
                text,
                rel,
                match.start(),
                name=raw_name,
                exported_name="default" if export_kind == "default" else raw_name,
                export_kind=export_kind,
                symbol_id=symbol_id,
            )

    for match in EXPORT_NAMED_RE.finditer(comment_masked):
        specifier = match.group("specifier")
        for part in match.group("body").split(","):
            parsed = parse_export_name(part)
            if not parsed:
                continue
            local_name, exported_name = parsed
            add_export(
                exports,
                text,
                rel,
                match.start(),
                name=local_name,
                exported_name=exported_name,
                export_kind="reexport" if specifier else "named",
                specifier=specifier,
                symbol_id=find_symbol_id(symbols.values(), local_name),
            )

    for match in EXPORT_STAR_RE.finditer(comment_masked):
        name = match.group("name") or "*"
        add_export(
            exports,
            text,
            rel,
            match.start(),
            name=name,
            exported_name=name,
            export_kind="reexport",
            specifier=match.group("specifier"),
            symbol_id=None,
        )

    for match in EXPORT_DEFAULT_RE.finditer(comment_masked):
        name = match.group("name") or "default"
        if any(
            item.get("export_kind") == "default" and item["source_ref"]["line"] == source_ref(text, rel, match.start())["line"]
            for item in exports.values()
        ):
            continue
        add_export(
            exports,
            text,
            rel,
            match.start(),
            name=name,
            exported_name="default",
            export_kind="default",
            symbol_id=find_symbol_id(symbols.values(), name),
        )

    for match in CJS_EXPORT_RE.finditer(comment_masked):
        name = match.group("name")
        ref = source_ref(text, rel, match.start())
        symbol_id = stable_id("symbol", rel, name, ref["line"], "commonjs-export")
        symbols.setdefault(
            symbol_id,
            with_provenance({
                "id": symbol_id,
                "type": "symbol",
                "kind": "commonjs-export",
                "symbol_kind": "commonjs-export",
                "name": name,
                "file": rel,
                "scope": "module",
                "scope_depth": brace_depth_at(structural_code, match.start()),
                "exported": True,
                "export_kind": "commonjs",
            }, rel, ref),
        )
        add_export(
            exports,
            text,
            rel,
            match.start(),
            name=name,
            exported_name=name,
            export_kind="commonjs",
            symbol_id=symbol_id,
        )

    for match in CJS_OBJECT_EXPORT_RE.finditer(comment_masked):
        for part in match.group("body").split(","):
            parsed = parse_export_name(part)
            if not parsed:
                continue
            local_name, exported_name = parsed
            add_export(
                exports,
                text,
                rel,
                match.start(),
                name=local_name,
                exported_name=exported_name,
                export_kind="commonjs",
                symbol_id=find_symbol_id(symbols.values(), local_name),
            )

    return (
        sorted(symbols.values(), key=lambda item: source_sort_key(item["source_ref"])),
        sorted(exports.values(), key=lambda item: source_sort_key(item["source_ref"])),
    )


def add_export(
    exports: Dict[str, Dict[str, Any]],
    text: str,
    rel: str,
    offset: int,
    *,
    name: str,
    exported_name: str,
    export_kind: str,
    symbol_id: Optional[str],
    specifier: Optional[str] = None,
) -> None:
    ref = source_ref(text, rel, offset)
    export_id = stable_id("export", rel, exported_name, ref["line"], export_kind)
    exports[export_id] = {
        "id": export_id,
        "type": "export",
        "kind": export_kind,
        "export_kind": export_kind,
        "name": name,
        "exported_name": exported_name,
        "file": rel,
        "symbol_id": symbol_id,
        "specifier": specifier,
    }
    with_provenance(exports[export_id], rel, ref)


def parse_export_name(raw: str) -> Optional[Tuple[str, str]]:
    raw = raw.strip()
    if not raw:
        return None
    raw = re.sub(r"^\s*type\s+", "", raw)
    if ":" in raw and " as " not in raw:
        local_name, exported_name = [item.strip() for item in raw.split(":", 1)]
    elif re.search(r"\s+as\s+", raw):
        local_name, exported_name = [
            item.strip()
            for item in re.split(r"\s+as\s+", raw, maxsplit=1)
        ]
    else:
        local_name = exported_name = raw
    if not re.fullmatch(IDENTIFIER, local_name) or not re.fullmatch(IDENTIFIER, exported_name):
        return None
    return local_name, exported_name


def find_symbol_id(symbols: Iterable[Dict[str, Any]], name: str) -> Optional[str]:
    for symbol in symbols:
        if symbol.get("name") == name:
            return symbol.get("id")
    return None


def extract_routes(
    text: str,
    code: str,
    rel: str,
    symbols: Sequence[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    routes: Dict[str, Dict[str, Any]] = {}
    file_route = route_from_path(rel)

    if file_route:
        method_symbols = [
            symbol
            for symbol in symbols
            if symbol.get("exported") and symbol.get("name") in HTTP_METHODS
        ]
        if method_symbols:
            for symbol in method_symbols:
                add_route(
                    routes,
                    text,
                    rel,
                    symbol["source_ref"]["offset"],
                    path=file_route,
                    method=symbol["name"],
                    route_kind="file-route-handler",
                    handler=symbol["name"],
                )
        else:
            add_route(
                routes,
                text,
                rel,
                0,
                path=file_route,
                method=None,
                route_kind="file-route",
                handler=None,
            )

    for match in ROUTE_CALL_RE.finditer(code):
        method = match.group("method").upper()
        if method == "DEL":
            method = "DELETE"
        if method in {"USE", "ROUTE"}:
            http_method = None
        elif method == "ALL":
            http_method = "ALL"
        else:
            http_method = method
        add_route(
            routes,
            text,
            rel,
            match.start(),
            path=match.group("path"),
            method=http_method,
            route_kind="handler-call",
            handler=extract_route_handler(match.group("tail") or ""),
            receiver=match.group("receiver"),
        )

    for match in GENERIC_ROUTE_RE.finditer(code):
        add_route(
            routes,
            text,
            rel,
            match.start(),
            path=match.group("path"),
            method=None,
            route_kind="route-call",
            handler=None,
        )

    for match in ROUTE_OBJECT_RE.finditer(code):
        props = {
            prop.group("key").lower(): prop.group("value")
            for prop in PROPERTY_RE.finditer(match.group("body"))
        }
        if "path" not in props:
            continue
        method = props.get("method")
        if method:
            method = method.upper()
        add_route(
            routes,
            text,
            rel,
            match.start(),
            path=props["path"],
            method=method,
            route_kind="route-object",
            handler=props.get("handler"),
        )

    return sorted(routes.values(), key=lambda item: source_sort_key(item["source_ref"]))


def add_route(
    routes: Dict[str, Dict[str, Any]],
    text: str,
    rel: str,
    offset: int,
    *,
    path: str,
    method: Optional[str],
    route_kind: str,
    handler: Optional[str],
    receiver: Optional[str] = None,
) -> None:
    ref = source_ref(text, rel, offset)
    route_id = stable_id("route", rel, method or "ANY", path, ref["line"], route_kind)
    routes[route_id] = {
        "id": route_id,
        "type": "route",
        "kind": route_kind,
        "route_kind": route_kind,
        "path": path,
        "method": method,
        "handler": handler,
        "receiver": receiver,
        "file": rel,
    }
    with_provenance(routes[route_id], rel, ref)


def extract_route_handler(tail: str) -> Optional[str]:
    tail = tail.strip()
    if not tail.startswith(","):
        return None
    tail = tail[1:].strip()
    if not tail:
        return None
    if tail.startswith(("async ", "(", "function")):
        return "<inline>"
    match = re.match(rf"({IDENTIFIER}(?:\.{IDENTIFIER})*)", tail)
    return match.group(1) if match else None


def extract_branches(text: str, code: str, rel: str) -> List[Dict[str, Any]]:
    branches: List[Dict[str, Any]] = []
    seen: set[str] = set()

    for match in IF_RE.finditer(code):
        else_offset = preceding_else_offset(code, match.start())
        kind = "else-if" if else_offset is not None else "if"
        offset = else_offset if else_offset is not None else match.start()
        condition, _ = read_parenthesized(text, code, match.end())
        append_branch(branches, seen, text, rel, offset, kind, condition)

    for match in ELSE_RE.finditer(code):
        next_index = skip_whitespace(code, match.end())
        if code.startswith("if", next_index) and is_word_boundary(code, next_index - 1, next_index + 2):
            continue
        append_branch(branches, seen, text, rel, match.start(), "else", None)

    for match in SWITCH_RE.finditer(code):
        condition, _ = read_parenthesized(text, code, match.end())
        append_branch(branches, seen, text, rel, match.start(), "switch", condition)

    for match in CASE_RE.finditer(code):
        condition = (match.group("condition") or "default").strip()
        append_branch(branches, seen, text, rel, match.start(), "case", condition)

    return sorted(branches, key=lambda item: source_sort_key(item["source_ref"]))


def append_branch(
    branches: List[Dict[str, Any]],
    seen: set[str],
    text: str,
    rel: str,
    offset: int,
    branch_kind: str,
    condition: Optional[str],
) -> None:
    ref = source_ref(text, rel, offset)
    branch_id = stable_id("branch", rel, branch_kind, ref["line"], condition or "")
    if branch_id in seen:
        return
    seen.add(branch_id)
    branches.append(
        with_provenance({
            "id": branch_id,
            "type": "branch",
            "kind": branch_kind,
            "branch_kind": branch_kind,
            "condition": condition,
            "file": rel,
        }, rel, ref)
    )


def route_from_path(rel: str) -> Optional[str]:
    path = PurePosixPath(rel)
    parts = list(path.with_suffix("").parts)
    if parts and parts[0] == "src":
        parts = parts[1:]
    if not parts:
        return None

    root = parts[0]
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
    return "/" + "/".join(cleaned)


def normalise_route_segment(part: str) -> str:
    if part.startswith("[[...") and part.endswith("]]"):
        return f"*{part[5:-2]}?"
    if part.startswith("[...") and part.endswith("]"):
        return f"*{part[4:-1]}"
    if part.startswith("[") and part.endswith("]"):
        return f":{part[1:-1]}"
    return part


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


def mask_source(text: str, *, mask_strings: bool) -> str:
    chars = list(text)
    index = 0
    length = len(chars)
    quote: Optional[str] = None

    while index < length:
        char = chars[index]
        next_char = chars[index + 1] if index + 1 < length else ""

        if quote:
            if char == "\\":
                if mask_strings and char != "\n":
                    chars[index] = " "
                if index + 1 < length:
                    if mask_strings and chars[index + 1] != "\n":
                        chars[index + 1] = " "
                    index += 2
                    continue
            if char == quote:
                if mask_strings:
                    chars[index] = " "
                quote = None
                index += 1
                continue
            if mask_strings and char != "\n":
                chars[index] = " "
            index += 1
            continue

        if char in {"'", '"', "`"}:
            quote = char
            if mask_strings:
                chars[index] = " "
            index += 1
            continue

        if char == "/" and next_char == "/":
            chars[index] = " "
            chars[index + 1] = " "
            index += 2
            while index < length and chars[index] != "\n":
                chars[index] = " "
                index += 1
            continue

        if char == "/" and next_char == "*":
            chars[index] = " "
            chars[index + 1] = " "
            index += 2
            while index < length:
                if chars[index] == "*" and index + 1 < length and chars[index + 1] == "/":
                    chars[index] = " "
                    chars[index + 1] = " "
                    index += 2
                    break
                if chars[index] != "\n":
                    chars[index] = " "
                index += 1
            continue

        index += 1

    return "".join(chars)


def read_parenthesized(
    text: str,
    code: str,
    start: int,
) -> Tuple[Optional[str], Optional[int]]:
    open_index = skip_whitespace(code, start)
    if open_index >= len(code) or code[open_index] != "(":
        return None, None

    depth = 0
    index = open_index
    while index < len(code):
        char = code[index]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return text[open_index + 1:index].strip(), index
        index += 1
    return None, None


def preceding_else_offset(code: str, if_start: int) -> Optional[int]:
    index = if_start - 1
    while index >= 0 and code[index].isspace():
        index -= 1
    end = index + 1
    while index >= 0 and (code[index].isalnum() or code[index] in {"_", "$"}):
        index -= 1
    start = index + 1
    return start if code[start:end] == "else" else None


def skip_whitespace(text: str, index: int) -> int:
    while index < len(text) and text[index].isspace():
        index += 1
    return index


def is_word_boundary(text: str, start: int, end: int) -> bool:
    before = text[start] if 0 <= start < len(text) else " "
    after = text[end] if 0 <= end < len(text) else " "
    return not is_identifier_char(before) and not is_identifier_char(after)


def is_identifier_char(char: str) -> bool:
    return char.isalnum() or char in {"_", "$"}


def brace_depth_at(code: str, offset: int) -> int:
    depth = 0
    for char in code[:offset]:
        if char == "{":
            depth += 1
        elif char == "}" and depth > 0:
            depth -= 1
    return depth


def infer_value_kind(text: str, declaration_end: int) -> Optional[str]:
    lookahead = text[declaration_end:declaration_end + 200]
    if "=>" in lookahead.split("\n", 1)[0]:
        return "arrow-function"
    return None


def normalise_symbol_kind(kind: str, value_kind: Optional[str]) -> str:
    if value_kind and kind in {"const", "let", "var"}:
        return value_kind
    if kind == "var":
        return "variable"
    return kind


def source_ref(text: str, rel: str, offset: int) -> Dict[str, Any]:
    starts = line_starts(text)
    line_index = bisect_right(starts, offset) - 1
    line_start = starts[line_index] if starts else 0
    return {
        "path": rel,
        "line": line_index + 1,
        "column": offset - line_start + 1,
        "offset": offset,
    }


def line_starts(text: str) -> List[int]:
    starts = [0]
    for match in re.finditer("\n", text):
        starts.append(match.end())
    return starts


def source_sort_key(ref: Dict[str, Any]) -> Tuple[int, int, str]:
    return (int(ref.get("line") or 0), int(ref.get("column") or 0), str(ref.get("path") or ""))


def stable_id(prefix: str, *parts: Any) -> str:
    cleaned = [
        re.sub(r"[^A-Za-z0-9_.:/-]+", "-", str(part)).strip("-")
        for part in parts
        if part is not None and str(part) != ""
    ]
    return f"{prefix}:{':'.join(cleaned)}"


def unique_preserve_order(values: Iterable[str]) -> List[str]:
    seen: set[str] = set()
    result = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def safe_read_text(path: Path) -> Optional[str]:
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            return None
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def should_descend_into(dirname: str) -> bool:
    if dirname in SKIP_DIRS:
        return False
    if dirname.startswith(".") and dirname not in {".github"}:
        return False
    return True


def is_source_file(path: Path) -> bool:
    return path.suffix.lower() in SOURCE_EXTENSIONS


def language_for_path(rel: str) -> str:
    suffix = PurePosixPath(rel).suffix.lower()
    if suffix in {".ts", ".tsx"}:
        return "typescript"
    return "javascript"


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


def to_posix(path: Path | PurePosixPath | str) -> str:
    return PurePosixPath(str(path)).as_posix()
