"""PHP and Laravel source fact extraction for AgentCanvas."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

from .lightweight import LightweightLanguageSpec, PatternSpec, extract_file as _extract_file
from .lightweight import extract_source_facts as _extract_source_facts
from .lightweight import parse_workspace as _parse_workspace

LANGUAGE = "php-laravel"
SOURCE_EXTENSIONS = {".php"}

SPEC = LightweightLanguageSpec(
    language=LANGUAGE,
    parser_name="php-laravel-regex-mvp",
    source_extensions=SOURCE_EXTENSIONS,
    line_comment=("//", "#"),
    block_comment=("/*", "*/"),
    import_patterns=[PatternSpec(r"^\s*use\s+(?P<specifier>[^;]+);", flags=re.MULTILINE)],
    symbol_patterns=[
        PatternSpec(r"\b(?P<kind>class|interface|trait|enum)\s+(?P<name>[A-Za-z_]\w*)"),
        PatternSpec(r"\bfunction\s+(?P<name>[A-Za-z_]\w*)\s*\(", kind="function"),
    ],
    route_patterns=[
        PatternSpec(
            r"\bRoute::(?P<method>match)\s*\(\s*\[[^\]]+\]\s*,\s*"
            r"['\"](?P<path>[^'\"]+)['\"](?P<tail>[^;]*)",
            kind="laravel-route",
            flags=re.MULTILINE | re.DOTALL,
        ),
        PatternSpec(
            r"\bRoute::(?P<method>get|post|put|patch|delete|options|any|resource|apiResource)"
            r"\s*\(\s*['\"](?P<path>[^'\"]+)['\"](?P<tail>[^;]*)",
            kind="laravel-route",
            flags=re.MULTILINE | re.DOTALL,
        ),
        PatternSpec(
            r"\$(?:router|app)->(?P<method>get|post|put|patch|delete|options|any)"
            r"\s*\(\s*['\"](?P<path>[^'\"]+)['\"](?P<tail>[^;]*)",
            kind="router-route",
            flags=re.MULTILINE | re.DOTALL,
        ),
    ],
    call_patterns=[
        PatternSpec(
            r"\b(?P<function>[A-Za-z_\\][A-Za-z0-9_\\]*::[A-Za-z_]\w*"
            r"|\$?[A-Za-z_]\w*->[A-Za-z_]\w*|[A-Za-z_]\w*)\s*\("
        )
    ],
    branch_aliases={"elseif": "else-if", "else if": "else-if"},
)


def parse_workspace(root: str | Path, paths: Optional[Sequence[str | Path]] = None) -> Dict[str, Any]:
    return _parse_workspace(root, spec=SPEC, paths=paths)


def extract_source_facts(path: str | Path, source: Optional[str] = None) -> Dict[str, Any]:
    if source is None:
        return extract_file(path)
    return _extract_source_facts(path, source, spec=SPEC)


def extract_file(path: str | Path) -> Dict[str, Any]:
    return _extract_file(path, spec=SPEC)
