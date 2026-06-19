"""Go source fact extraction for AgentCanvas."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

from .lightweight import LightweightLanguageSpec, PatternSpec, extract_file as _extract_file
from .lightweight import extract_source_facts as _extract_source_facts
from .lightweight import parse_workspace as _parse_workspace

LANGUAGE = "go"
SOURCE_EXTENSIONS = {".go"}

SPEC = LightweightLanguageSpec(
    language=LANGUAGE,
    parser_name="go-regex-mvp",
    source_extensions=SOURCE_EXTENSIONS,
    line_comment="//",
    block_comment=("/*", "*/"),
    import_patterns=[
        PatternSpec(
            r'^\s*import\s+(?:(?:[A-Za-z_]\w*|[._])\s+)?'
            r'["`](?P<specifier>[^"`]+)["`]',
            flags=re.MULTILINE,
        ),
        PatternSpec(
            r'^\s*(?:(?:[A-Za-z_]\w*|[._])\s+)?'
            r'["`](?P<specifier>[^"`]+)["`]\s*(?://.*)?$',
            flags=re.MULTILINE,
            kind="import-block",
        ),
    ],
    symbol_patterns=[
        PatternSpec(r"\bfunc\s+(?:\([^)]+\)\s*)?(?P<name>[A-Za-z_]\w*)\s*\(", kind="function"),
        PatternSpec(r"\btype\s+(?P<name>[A-Za-z_]\w*)\s+(?P<kind>struct|interface|func)"),
    ],
    route_patterns=[
        PatternSpec(
            r"\b(?P<receiver>[A-Za-z_]\w*)\.HandleFunc\s*\(\s*"
            r"[\"`](?P<path>[^\"`]+)[\"`]\s*,\s*"
            r"(?P<handler>[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)?)\s*\)"
            r"\.Methods\s*\(\s*[\"`](?P<method>GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)[\"`]",
            kind="gorilla-route",
            flags=re.MULTILINE | re.DOTALL,
        ),
        PatternSpec(
            r"\b(?P<receiver>[A-Za-z_]\w*)\."
            r"(?P<method>GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS|Get|Post|Put|Patch|Delete|Head|Options)"
            r"\s*\(\s*[\"`](?P<path>[^\"`]+)[\"`]\s*"
            r"(?:,\s*(?P<handler>[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)?))?",
            kind="handler-call",
        ),
        PatternSpec(
            r"\b(?P<receiver>[A-Za-z_]\w*)\.(?:HandleFunc|Handle)\s*\(\s*"
            r"[\"`](?P<path>[^\"`]+)[\"`]\s*"
            r"(?:,\s*(?P<handler>[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)?))?"
            r"\s*\)(?!\s*\.Methods)",
            kind="handler-call",
        ),
        PatternSpec(
            r"\bhttp\.HandleFunc\s*\(\s*[\"`](?P<path>[^\"`]+)[\"`]\s*,\s*"
            r"(?P<handler>[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)?)\s*\)",
            kind="http-handlefunc",
        ),
    ],
    call_patterns=[PatternSpec(r"\b(?P<function>[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)?)\s*\(")],
    branch_aliases={"else if": "else-if"},
)


def parse_workspace(root: str | Path, paths: Optional[Sequence[str | Path]] = None) -> Dict[str, Any]:
    return _parse_workspace(root, spec=SPEC, paths=paths)


def extract_source_facts(path: str | Path, source: Optional[str] = None) -> Dict[str, Any]:
    if source is None:
        return extract_file(path)
    return _extract_source_facts(path, source, spec=SPEC)


def extract_file(path: str | Path) -> Dict[str, Any]:
    return _extract_file(path, spec=SPEC)
