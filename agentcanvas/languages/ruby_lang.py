"""Ruby and Rails source fact extraction for AgentCanvas."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Sequence

from .lightweight import LightweightLanguageSpec, PatternSpec, extract_file as _extract_file
from .lightweight import extract_source_facts as _extract_source_facts
from .lightweight import parse_workspace as _parse_workspace

LANGUAGE = "ruby-rails"
SOURCE_EXTENSIONS = {".rb"}

SPEC = LightweightLanguageSpec(
    language=LANGUAGE,
    parser_name="ruby-rails-regex-mvp",
    source_extensions=SOURCE_EXTENSIONS,
    line_comment="#",
    import_patterns=[
        PatternSpec(r"\brequire(?:_relative)?\s+['\"](?P<specifier>[^'\"]+)['\"]"),
    ],
    symbol_patterns=[
        PatternSpec(r"^\s*(?P<kind>class|module)\s+(?P<name>[A-Z][A-Za-z0-9_:]*)", kind="class"),
        PatternSpec(r"^\s*def\s+(?P<name>(?:self\.|[A-Za-z_]\w*\.)?[A-Za-z_]\w*[!?=]?)", kind="function"),
    ],
    route_patterns=[
        PatternSpec(
            r"^\s*(?P<method>get|post|put|patch|delete)\s+"
            r"['\"](?P<path>[^'\"]+)['\"](?P<tail>[^\n]*)",
            kind="rails-route",
        ),
        PatternSpec(r"^\s*resources\s+:(?P<path>[A-Za-z_]\w*)(?P<tail>[^\n]*)", kind="rails-resource"),
        PatternSpec(r"^\s*resource\s+:(?P<path>[A-Za-z_]\w*)(?P<tail>[^\n]*)", kind="rails-resource"),
        PatternSpec(
            r"^\s*root\s+(?P<handler>['\"][^'\"]+['\"])(?P<tail>[^\n]*)",
            kind="rails-root",
            default_path="/",
        ),
    ],
    call_patterns=[
        PatternSpec(
            r"\b(?P<function>[A-Za-z_]\w*(?:\.[A-Za-z_]\w*[!?=]?)+)\b"
            r"|\b(?P<name>[A-Za-z_]\w*[!?=]?)\s*\("
        )
    ],
    branch_aliases={"elsif": "else-if"},
)


def parse_workspace(root: str | Path, paths: Optional[Sequence[str | Path]] = None) -> Dict[str, Any]:
    return _parse_workspace(root, spec=SPEC, paths=paths)


def extract_source_facts(path: str | Path, source: Optional[str] = None) -> Dict[str, Any]:
    if source is None:
        return extract_file(path)
    return _extract_source_facts(path, source, spec=SPEC)


def extract_file(path: str | Path) -> Dict[str, Any]:
    return _extract_file(path, spec=SPEC)
