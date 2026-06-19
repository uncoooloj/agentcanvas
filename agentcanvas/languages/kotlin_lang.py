"""Kotlin, Android, and Ktor source fact extraction for AgentCanvas."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Sequence

from .lightweight import LightweightLanguageSpec, PatternSpec, extract_file as _extract_file
from .lightweight import extract_source_facts as _extract_source_facts
from .lightweight import parse_workspace as _parse_workspace

LANGUAGE = "kotlin"
SOURCE_EXTENSIONS = {".kt", ".kts"}

SPEC = LightweightLanguageSpec(
    language=LANGUAGE,
    parser_name="kotlin-regex-mvp",
    source_extensions=SOURCE_EXTENSIONS,
    line_comment="//",
    block_comment=("/*", "*/"),
    import_patterns=[PatternSpec(r"\bimport\s+(?P<specifier>[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*(?:\.\*)?)(?:\s+as\s+[A-Za-z_]\w*)?")],
    symbol_patterns=[
        PatternSpec(r"\b(?P<kind>data\s+class|sealed\s+(?:class|interface)|value\s+class|enum\s+class|class|object|interface)\s+(?P<name>[A-Za-z_]\w*)"),
        PatternSpec(
            r"\bfun\s+(?:<[^>\n]+>\s*)?(?:(?:[A-Za-z_]\w*(?:<[^>\n]+>)?|\([^)]+\))\.)?(?P<name>[A-Za-z_]\w*)\s*\(",
            kind="function",
        ),
    ],
    route_patterns=[
        PatternSpec(r"@(?P<method>GET|POST|PUT|PATCH|DELETE)\s*\(\s*['\"](?P<path>[^'\"]+)['\"]", kind="retrofit-route"),
        PatternSpec(r"\b(?P<method>get|post|put|patch|delete)\s*\(\s*['\"](?P<path>[^'\"]+)['\"]", kind="ktor-route"),
        PatternSpec(r"\broute\s*\(\s*['\"](?P<path>[^'\"]+)['\"]", kind="ktor-route-scope"),
        PatternSpec(r"\bcomposable\s*\(\s*(?:route\s*=\s*)?['\"](?P<path>[^'\"]+)['\"]", kind="compose-navigation"),
        PatternSpec(r"\bnavigation\s*\([^)]*route\s*=\s*['\"](?P<path>[^'\"]+)['\"]", kind="compose-navigation-graph"),
    ],
    call_patterns=[PatternSpec(r"\b(?P<function>[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)\s*\(")],
    branch_aliases={"else if": "else-if", "when": "switch"},
)


def parse_workspace(root: str | Path, paths: Optional[Sequence[str | Path]] = None) -> Dict[str, Any]:
    return _parse_workspace(root, spec=SPEC, paths=paths)


def extract_source_facts(path: str | Path, source: Optional[str] = None) -> Dict[str, Any]:
    if source is None:
        return extract_file(path)
    return _extract_source_facts(path, source, spec=SPEC)


def extract_file(path: str | Path) -> Dict[str, Any]:
    return _extract_file(path, spec=SPEC)
