"""Shared lightweight source-fact extraction for MVP language modules."""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Iterable, List, Optional, Pattern, Sequence, Set


FACT_SCHEMA = "agentcanvas.source_facts.v1"
MAX_FILE_BYTES = 1_000_000
HTTP_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS", "TRACE", "CONNECT", "ANY", "ALL"}


class PatternSpec:
    def __init__(
        self,
        pattern: str,
        *,
        flags: int = re.MULTILINE,
        kind: str = "",
        default_path: Optional[str] = None,
    ) -> None:
        self.pattern = re.compile(pattern, flags)
        self.kind = kind
        self.default_path = default_path


class LightweightLanguageSpec:
    def __init__(
        self,
        *,
        language: str,
        parser_name: str,
        source_extensions: Iterable[str],
        import_patterns: Sequence[PatternSpec],
        symbol_patterns: Sequence[PatternSpec],
        route_patterns: Sequence[PatternSpec],
        call_patterns: Sequence[PatternSpec] = (),
        branch_aliases: Optional[Dict[str, str]] = None,
        line_comment: Optional[str | Sequence[str]] = None,
        block_comment: Optional[tuple[str, str]] = None,
    ) -> None:
        self.language = language
        self.parser_name = parser_name
        self.source_extensions = {ext.lower() for ext in source_extensions}
        self.import_patterns = tuple(import_patterns)
        self.symbol_patterns = tuple(symbol_patterns)
        self.route_patterns = tuple(route_patterns)
        self.call_patterns = tuple(call_patterns)
        self.branch_aliases = branch_aliases or {}
        self.line_comment = line_comment
        if isinstance(line_comment, str):
            self.line_comments = (line_comment,)
        else:
            self.line_comments = tuple(line_comment or ())
        self.block_comment = block_comment


def parse_workspace(
    root: str | Path,
    *,
    spec: LightweightLanguageSpec,
    paths: Optional[Sequence[str | Path]] = None,
) -> Dict[str, Any]:
    workspace = Path(root)
    selected = [Path(path) for path in paths] if paths else _discover(workspace, spec)
    bundle = _empty_bundle(spec)
    for path in selected:
        merge_bundle(bundle, extract_file(path, spec=spec, workspace_root=workspace))
    bundle["summary"] = _summary(bundle["facts"])
    return bundle


def extract_file(
    path: str | Path,
    *,
    spec: LightweightLanguageSpec,
    workspace_root: str | Path | None = None,
) -> Dict[str, Any]:
    file_path = Path(path)
    display_path = _display_path(file_path, workspace_root)
    try:
        if file_path.stat().st_size > MAX_FILE_BYTES:
            return _read_error_bundle(spec, display_path, "file too large")
        source = file_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return _read_error_bundle(spec, display_path, str(exc))
    return extract_source_facts(display_path, source, spec=spec)


def extract_source_facts(
    path: str | Path,
    source: str,
    *,
    spec: LightweightLanguageSpec,
) -> Dict[str, Any]:
    display_path = PurePosixPath(str(path)).as_posix()
    code = _mask_comments(source, spec)
    structural_code = _mask_strings(code)
    facts: List[Dict[str, Any]] = [
        {
            "id": _stable_id("file", display_path, 1, display_path),
            "type": "file",
            "kind": "source",
            "language": spec.language,
            "path": display_path,
            "file": display_path,
            "readable": True,
            "line_count": len(source.splitlines()),
            "source_ref": {"path": display_path, "line": 1},
        }
    ]
    facts.extend(_extract_imports(code, display_path, spec))
    facts.extend(_extract_symbols(structural_code, display_path, spec))
    facts.extend(_extract_routes(code, display_path, spec))
    facts.extend(_extract_branches(structural_code, display_path, spec))
    facts.extend(_extract_calls(structural_code, display_path, spec))
    return {
        "schema": FACT_SCHEMA,
        "language": spec.language,
        "parser": {
            "name": spec.parser_name,
            "version": "0.1.0",
            "strategy": "regex",
        },
        "path": display_path,
        "facts": facts,
        "summary": _summary(facts),
        "errors": [],
    }


def merge_bundle(target: Dict[str, Any], source: Dict[str, Any]) -> None:
    target["facts"].extend(source.get("facts") or [])
    target.setdefault("errors", []).extend(source.get("errors") or [])


def _empty_bundle(spec: LightweightLanguageSpec) -> Dict[str, Any]:
    return {
        "schema": FACT_SCHEMA,
        "language": spec.language,
        "parser": {
            "name": spec.parser_name,
            "version": "0.1.0",
            "strategy": "regex",
        },
        "facts": [],
        "summary": {"total": 0, "by_type": {}},
        "errors": [],
    }


def _discover(root: Path, spec: LightweightLanguageSpec) -> List[Path]:
    paths = []
    skip = {".agentcanvas", ".git", ".hg", ".svn", ".venv", "__pycache__", "build", "dist", "node_modules", "target"}
    for dirpath, dirnames, filenames in root.walk() if hasattr(root, "walk") else _walk(root):
        dirnames[:] = [dirname for dirname in dirnames if dirname not in skip and not dirname.startswith(".")]
        for filename in filenames:
            path = Path(dirpath) / filename
            if path.suffix.lower() in spec.source_extensions:
                paths.append(path)
    return sorted(paths)


def _walk(root: Path):
    import os

    yield from os.walk(root)


def _display_path(path: Path, workspace_root: str | Path | None) -> str:
    try:
        if workspace_root is not None:
            return PurePosixPath(path.resolve().relative_to(Path(workspace_root).resolve())).as_posix()
    except (OSError, ValueError):
        pass
    return PurePosixPath(str(path)).as_posix()


def _read_error_bundle(spec: LightweightLanguageSpec, path: str, message: str) -> Dict[str, Any]:
    fact = {
        "id": _stable_id("read_error", path, 1, message),
        "type": "read_error",
        "kind": "read_error",
        "language": spec.language,
        "message": message,
        "file": path,
        "path": path,
        "source_ref": {"path": path, "line": 1},
    }
    return {
        "schema": FACT_SCHEMA,
        "language": spec.language,
        "parser": {"name": spec.parser_name, "version": "0.1.0", "strategy": "regex"},
        "path": path,
        "facts": [fact],
        "summary": _summary([fact]),
        "errors": [fact],
    }


def _extract_imports(code: str, path: str, spec: LightweightLanguageSpec) -> List[Dict[str, Any]]:
    facts = []
    seen: Set[tuple[str, int]] = set()
    for pattern in spec.import_patterns:
        for match in pattern.pattern.finditer(code):
            raw_specifier = _group(match, "specifier", "name", "package")
            if not raw_specifier:
                continue
            line = _line_number(code, match.start())
            for specifier in _expand_import_specifiers(raw_specifier):
                key = (specifier, line)
                if key in seen:
                    continue
                seen.add(key)
                facts.append(
                    {
                        "id": _stable_id("import", path, line, specifier),
                        "type": "import",
                        "kind": pattern.kind or "import",
                        "language": spec.language,
                        "specifier": specifier,
                        "file": path,
                        "source_ref": {"path": path, "line": line},
                    }
                )
    return facts


def _extract_symbols(code: str, path: str, spec: LightweightLanguageSpec) -> List[Dict[str, Any]]:
    facts = []
    seen: Set[tuple[str, str, int]] = set()
    for pattern in spec.symbol_patterns:
        for match in pattern.pattern.finditer(code):
            name = _group(match, "name", "symbol")
            if not name:
                continue
            kind = _group(match, "kind") or pattern.kind or "symbol"
            line = _line_number(code, match.start())
            key = (kind, name, line)
            if key in seen:
                continue
            seen.add(key)
            facts.append(
                {
                    "id": _stable_id("symbol", path, line, kind, name),
                    "type": "symbol",
                    "kind": kind,
                    "symbol_kind": kind,
                    "language": spec.language,
                    "name": name,
                    "qualified_name": name,
                    "file": path,
                    "source_ref": {"path": path, "line": line},
                }
            )
    return facts


def _extract_routes(code: str, path: str, spec: LightweightLanguageSpec) -> List[Dict[str, Any]]:
    facts = []
    seen: Set[tuple[str, str, int]] = set()
    for pattern in spec.route_patterns:
        for match in pattern.pattern.finditer(code):
            handler = _group(match, "handler", "action", "name")
            if not handler:
                handler = _handler_from_tail(_raw_group(match, "tail", "target"))
            handler = _normalize_handler(handler)
            route_path = _group(match, "path", "route") or pattern.default_path or handler
            if not route_path:
                continue
            method = _normalize_route_method(_group(match, "method"))
            line = _line_number(code, match.start())
            key = (method or "", route_path, line)
            if key in seen:
                continue
            seen.add(key)
            fact = {
                "id": _stable_id("route", path, line, method or "ROUTE", route_path),
                "type": "route",
                "kind": pattern.kind or "route",
                "route_kind": pattern.kind or "route",
                "language": spec.language,
                "method": method,
                "path": route_path,
                "file": path,
                "source_ref": {"path": path, "line": line},
            }
            if handler:
                fact["handler"] = handler
            facts.append(fact)
    return facts


def _extract_branches(code: str, path: str, spec: LightweightLanguageSpec) -> List[Dict[str, Any]]:
    branch_re = re.compile(
        r"\b(?P<kind>else\s+if|elseif|elsif|elif|if|else|switch|when|case|default)\b",
        re.MULTILINE,
    )
    facts = []
    for match in branch_re.finditer(code):
        raw_kind = " ".join(match.group("kind").lower().split())
        kind = spec.branch_aliases.get(raw_kind, raw_kind.replace(" ", "-"))
        condition = _branch_condition_after(code, match.end(), kind)
        line = _line_number(code, match.start())
        facts.append(
            {
                "id": _stable_id("branch", path, line, kind, condition or kind),
                "type": "branch",
                "kind": kind,
                "branch_kind": kind,
                "language": spec.language,
                "condition": condition,
                "file": path,
                "source_ref": {"path": path, "line": line},
            }
        )
    return facts


def _extract_calls(code: str, path: str, spec: LightweightLanguageSpec) -> List[Dict[str, Any]]:
    facts = []
    seen: Set[tuple[str, int]] = set()
    keywords = {
        "catch",
        "case",
        "class",
        "default",
        "def",
        "do",
        "else",
        "elseif",
        "elsif",
        "end",
        "enum",
        "extension",
        "for",
        "foreach",
        "fun",
        "func",
        "function",
        "if",
        "import",
        "interface",
        "module",
        "namespace",
        "object",
        "package",
        "protocol",
        "return",
        "struct",
        "switch",
        "when",
        "while",
        "use",
    }
    for pattern in spec.call_patterns:
        for match in pattern.pattern.finditer(code):
            function = _group(match, "function", "name")
            if not function or function in keywords or _looks_like_declaration_call(code, match.start(), function):
                continue
            line = _line_number(code, match.start())
            key = (function, line)
            if key in seen:
                continue
            seen.add(key)
            facts.append(
                {
                    "id": _stable_id("call", path, line, function),
                    "type": "call",
                    "kind": pattern.kind or "call",
                    "language": spec.language,
                    "function": function,
                    "file": path,
                    "source_ref": {"path": path, "line": line},
                }
            )
    return facts[:200]


def _mask_comments(source: str, spec: LightweightLanguageSpec) -> str:
    if not spec.line_comments and not spec.block_comment:
        return source

    chars = list(source)
    line_comments = sorted(spec.line_comments, key=len, reverse=True)
    block_start, block_end = spec.block_comment or (None, None)
    index = 0
    string_quote: Optional[str] = None
    triple_string = False

    while index < len(source):
        if string_quote:
            if triple_string and source.startswith(string_quote * 3, index):
                index += 3
                string_quote = None
                triple_string = False
                continue
            if not triple_string and source[index] == "\\":
                index += 2
                continue
            if not triple_string and source[index] == string_quote:
                index += 1
                string_quote = None
                continue
            index += 1
            continue

        if block_start and block_end and source.startswith(block_start, index):
            end = source.find(block_end, index + len(block_start))
            stop = len(source) if end == -1 else end + len(block_end)
            _mask_range(chars, source, index, stop)
            index = stop
            continue

        matched_line_comment = next(
            (token for token in line_comments if source.startswith(token, index)),
            None,
        )
        if matched_line_comment:
            stop = source.find("\n", index)
            if stop == -1:
                stop = len(source)
            _mask_range(chars, source, index, stop)
            index = stop
            continue

        if source[index] in {"'", '"', "`"}:
            string_quote = source[index]
            if source.startswith(string_quote * 3, index):
                triple_string = True
                index += 3
            else:
                triple_string = False
                index += 1
            continue

        index += 1

    return "".join(chars)


def _mask_strings(source: str) -> str:
    chars = list(source)
    index = 0
    string_quote: Optional[str] = None
    string_start = 0
    triple_string = False

    while index < len(source):
        if string_quote:
            if triple_string and source.startswith(string_quote * 3, index):
                _mask_range(chars, source, string_start, index + 3)
                index += 3
                string_quote = None
                triple_string = False
                continue
            if not triple_string and source[index] == "\\":
                index += 2
                continue
            if not triple_string and source[index] == string_quote:
                _mask_range(chars, source, string_start, index + 1)
                index += 1
                string_quote = None
                continue
            index += 1
            continue

        if source[index] in {"'", '"', "`"}:
            string_quote = source[index]
            string_start = index
            if source.startswith(string_quote * 3, index):
                triple_string = True
                index += 3
            else:
                triple_string = False
                index += 1
            continue

        index += 1

    if string_quote:
        _mask_range(chars, source, string_start, len(source))
    return "".join(chars)


def _expand_import_specifiers(specifier: str) -> List[str]:
    cleaned = re.sub(r"^(?:function|const)\s+", "", specifier.strip(), flags=re.IGNORECASE)
    if "{" in cleaned and "}" in cleaned:
        prefix, remainder = cleaned.split("{", 1)
        body, _ = remainder.split("}", 1)
        expanded = []
        for item in body.split(","):
            name = re.sub(r"\s+as\s+[A-Za-z_]\w*$", "", item.strip(), flags=re.IGNORECASE)
            if name:
                expanded.append(prefix + name)
        return expanded

    cleaned = re.sub(r"\s+as\s+[A-Za-z_]\w*$", "", cleaned, flags=re.IGNORECASE)
    return [cleaned] if cleaned else []


def _handler_from_tail(tail: Optional[str]) -> Optional[str]:
    if not tail:
        return None
    text = tail.strip()
    if text.startswith(","):
        text = text[1:].strip()
    if re.match(r"function\s*\(", text):
        return "closure"

    array_handler = re.search(
        r"\[\s*(?P<controller>[A-Za-z_\\][A-Za-z0-9_\\]*(?:::class)?)\s*,\s*['\"](?P<action>[^'\"]+)['\"]\s*\]",
        text,
    )
    if array_handler:
        controller = _remove_suffix(array_handler.group("controller"), "::class")
        return f"{controller}@{array_handler.group('action')}"

    rails_to = re.search(r"\bto:\s*['\"](?P<handler>[^'\"]+)['\"]", text)
    if rails_to:
        return rails_to.group("handler")

    string_handler = re.search(
        r"['\"](?P<handler>[A-Za-z_\\][A-Za-z0-9_\\]*(?:@|#)[A-Za-z_]\w*[!?=]?)['\"]",
        text,
    )
    if string_handler:
        return string_handler.group("handler")

    direct_handler = re.match(
        r"(?P<handler>[A-Za-z_\\][A-Za-z0-9_\\.\\]*(?:::[A-Za-z_]\w*)?)",
        text,
    )
    if direct_handler:
        return direct_handler.group("handler")
    return None


def _normalize_handler(handler: Optional[str]) -> Optional[str]:
    if not handler:
        return None
    value = handler.strip().strip(",").strip().strip('"\'`')
    if value.endswith("::class"):
        value = _remove_suffix(value, "::class")
    return value or None


def _remove_suffix(value: str, suffix: str) -> str:
    if suffix and value.endswith(suffix):
        return value[: -len(suffix)]
    return value


def _normalize_route_method(method: Optional[str]) -> Optional[str]:
    if not method:
        return None
    normalized = method.upper()
    if normalized == "DEL":
        return "DELETE"
    if normalized in HTTP_METHODS:
        return normalized
    return None


def _branch_condition_after(code: str, offset: int, kind: str) -> str:
    if kind in {"else", "default"}:
        return ""
    index = _skip_whitespace(code, offset)
    if index >= len(code):
        return ""
    if code[index] == "(":
        condition, _ = _read_balanced_parentheses(code, index)
        return _clean_branch_condition(condition)
    return _clean_branch_condition(_read_branch_tail(code, index))


def _read_balanced_parentheses(code: str, offset: int) -> tuple[str, int]:
    depth = 0
    index = offset
    start = offset + 1
    string_quote: Optional[str] = None
    while index < len(code):
        char = code[index]
        if string_quote:
            if char == "\\":
                index += 2
                continue
            if char == string_quote:
                string_quote = None
            index += 1
            continue
        if char in {"'", '"', "`"}:
            string_quote = char
            index += 1
            continue
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return code[start:index], index + 1
        index += 1
    return code[start:], len(code)


def _read_branch_tail(code: str, offset: int) -> str:
    index = offset
    string_quote: Optional[str] = None
    while index < len(code):
        char = code[index]
        if string_quote:
            if char == "\\":
                index += 2
                continue
            if char == string_quote:
                string_quote = None
            index += 1
            continue
        if char in {"'", '"', "`"}:
            string_quote = char
            index += 1
            continue
        if (
            char == "\n"
            or char == "{"
            or code.startswith("->", index)
            or (char == ":" and not code.startswith(":=", index))
        ):
            break
        index += 1
    return code[offset:index]


def _clean_branch_condition(condition: str) -> str:
    cleaned = condition.strip().rstrip(":").strip()
    return re.sub(r"\s+(?:then|do)\s*$", "", cleaned)


def _skip_whitespace(code: str, offset: int) -> int:
    index = offset
    while index < len(code) and code[index].isspace():
        index += 1
    return index


def _looks_like_declaration_call(code: str, offset: int, function: str) -> bool:
    line_start = code.rfind("\n", 0, offset) + 1
    line_prefix = code[line_start:offset]
    stripped = line_prefix.strip()
    if stripped in {"await", "return", "throw", "try", "try await", "yield"}:
        return False
    declaration_keyword = re.compile(
        r"\b(?:def|function)\s+(?:[A-Za-z_]\w*\.)?$"
        r"|\bfunc\s+(?:\([^)]+\)\s*)?$"
        r"|\bfun\s+(?:<[^>\n]+>\s*)?(?:(?:[A-Za-z_]\w*(?:<[^>\n]+>)?|\([^)]+\))\.)?$"
    )
    typed_declaration = re.compile(
        r"^\s*(?:@[A-Za-z_]\w*(?:\([^)]*\))?\s*)*"
        r"(?:(?:abstract|async|external|factory|final|internal|mutating|"
        r"nonmutating|open|override|private|public|static|suspend)\s+)*"
        r"[A-Za-z_]\w*(?:<[^>\n]+>)?\??\s+$"
    )
    return bool(declaration_keyword.search(line_prefix) or typed_declaration.match(line_prefix))


def _mask_range(chars: List[str], source: str, start: int, stop: int) -> None:
    for index in range(start, stop):
        chars[index] = "\n" if source[index] == "\n" else " "


def _space_match(match: re.Match[str]) -> str:
    return "".join("\n" if char == "\n" else " " for char in match.group(0))


def _summary(facts: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    facts = list(facts)
    return {"total": len(facts), "by_type": dict(Counter(fact.get("type", "fact") for fact in facts))}


def _line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _group(match: re.Match[str], *names: str) -> Optional[str]:
    groups = match.groupdict()
    for name in names:
        value = groups.get(name)
        if value:
            return value.strip().strip('"\'`')
    return None


def _raw_group(match: re.Match[str], *names: str) -> Optional[str]:
    groups = match.groupdict()
    for name in names:
        value = groups.get(name)
        if value:
            return value
    return None


def _stable_id(kind: str, path: str, line: int, *parts: Any) -> str:
    tail = ":".join(_slug(part) for part in parts if part is not None)
    return f"{kind}:{path}:{line}:{tail or kind}"


def _slug(value: Any) -> str:
    text = str(value).strip().replace("\\", "/")
    text = re.sub(r"\s+", "-", text)
    text = re.sub(r"[^a-zA-Z0-9_.:/{}-]+", "-", text)
    return text.strip("-").lower()[:120] or "item"
