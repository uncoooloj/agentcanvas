"""Swift and SwiftUI source fact extraction for AgentCanvas."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

from .lightweight import LightweightLanguageSpec, PatternSpec, extract_file as _extract_file
from .lightweight import extract_source_facts as _extract_source_facts
from .lightweight import parse_workspace as _parse_workspace

LANGUAGE = "swift"
SOURCE_EXTENSIONS = {".swift"}

SPEC = LightweightLanguageSpec(
    language=LANGUAGE,
    parser_name="swift-regex-mvp",
    source_extensions=SOURCE_EXTENSIONS,
    line_comment="//",
    block_comment=("/*", "*/"),
    import_patterns=[PatternSpec(r"(?:@testable\s+)?\bimport\s+(?P<specifier>[A-Za-z_]\w*)")],
    symbol_patterns=[
        PatternSpec(r"\b(?P<kind>class|struct|enum|protocol|actor|extension)\s+(?P<name>[A-Za-z_]\w*)"),
        PatternSpec(r"\bfunc\s+(?P<name>[A-Za-z_]\w*)\s*\(", kind="function"),
    ],
    route_patterns=[
        PatternSpec(
            r"\bNavigationLink\s*\(.*?destination\s*:\s*(?P<handler>[A-Za-z_]\w*)",
            kind="swiftui-navigation",
            flags=re.MULTILINE | re.DOTALL,
        ),
        PatternSpec(
            r"\.navigationDestination\s*\(\s*for\s*:\s*(?P<path>[A-Za-z_]\w*)\.self",
            kind="swiftui-navigation-destination",
        ),
        PatternSpec(r"\bstruct\s+(?P<path>[A-Za-z_]\w*(?:View|Screen))\s*:\s*View", kind="swiftui-screen"),
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
