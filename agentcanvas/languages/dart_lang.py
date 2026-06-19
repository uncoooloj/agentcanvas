"""Dart and Flutter source fact extraction for AgentCanvas."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

from .lightweight import LightweightLanguageSpec, PatternSpec, extract_file as _extract_file
from .lightweight import extract_source_facts as _extract_source_facts
from .lightweight import parse_workspace as _parse_workspace

LANGUAGE = "dart-flutter"
SOURCE_EXTENSIONS = {".dart"}

SPEC = LightweightLanguageSpec(
    language=LANGUAGE,
    parser_name="dart-flutter-regex-mvp",
    source_extensions=SOURCE_EXTENSIONS,
    line_comment="//",
    block_comment=("/*", "*/"),
    import_patterns=[
        PatternSpec(r"\bimport\s+['\"](?P<specifier>[^'\"]+)['\"]"),
        PatternSpec(r"\bexport\s+['\"](?P<specifier>[^'\"]+)['\"]", kind="export-import"),
        PatternSpec(r"\bpart\s+['\"](?P<specifier>[^'\"]+)['\"]", kind="part"),
    ],
    symbol_patterns=[
        PatternSpec(r"\b(?P<kind>extension\s+type|class|mixin|enum|extension)\s+(?P<name>[A-Za-z_]\w*)"),
        PatternSpec(
            r"^\s*(?:(?:abstract|external|static)\s+)*(?!(?:const|final|var)\b)(?:[A-Za-z_]\w*(?:<[^;\n{}]+>)?\??|void)\s+(?P<name>[A-Za-z_]\w*)\s*\(",
            kind="function",
        ),
    ],
    route_patterns=[
        PatternSpec(
            r"\b(?:GoRoute|TypedGoRoute(?:<[^>]+>)?)\s*\(.*?path\s*:\s*['\"](?P<path>[^'\"]+)['\"]",
            kind="flutter-go-route",
            flags=re.MULTILINE | re.DOTALL,
        ),
        PatternSpec(r"['\"](?P<path>/[^'\"]+)['\"]\s*:\s*\([^)]*\)\s*=>", kind="flutter-named-route"),
        PatternSpec(
            r"\bNavigator\.(?:pushNamed|pushReplacementNamed|popAndPushNamed|restorablePushNamed|restorablePushReplacementNamed)\s*\([^,]+,\s*['\"](?P<path>[^'\"]+)['\"]",
            kind="flutter-navigation",
        ),
        PatternSpec(
            r"\bNavigator\.of\([^)]*\)\.(?:pushNamed|pushReplacementNamed|popAndPushNamed|restorablePushNamed|restorablePushReplacementNamed)\s*\(\s*['\"](?P<path>[^'\"]+)['\"]",
            kind="flutter-navigation",
        ),
    ],
    call_patterns=[PatternSpec(r"\b(?P<function>[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)\s*\(")],
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
