import re
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOTS = [
    PROJECT_ROOT / "agentcanvas",
    PROJECT_ROOT / "frontend" / "src",
]
SOURCE_EXTENSIONS = {".py", ".ts", ".tsx", ".js", ".jsx"}
DISALLOWED_TELEMETRY_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"\bposthog\b",
        r"\bsegment\.io\b",
        r"(@sentry/|\bsentry\b)",
        r"\bamplitude\b",
        r"\bmixpanel\b",
        r"\bplausible\b",
        r"\bgoogle-analytics\b",
        r"\bgoogletagmanager\b",
        r"\bgtag\s*\(",
        r"\bdataLayer\b",
        r"\bnavigator\.sendBeacon\b",
        r"\bnew\s+XMLHttpRequest\b",
        r"\bnew\s+WebSocket\b",
    ]
]
FETCH_CALL_RE = re.compile(r"\bfetch\((?P<target>[^)\n]+)")


class NoTelemetryTests(unittest.TestCase):
    def test_source_has_no_telemetry_vendor_or_browser_reporting_code(self):
        offenders = []
        for path in _source_files():
            text = path.read_text(encoding="utf-8")
            for pattern in DISALLOWED_TELEMETRY_PATTERNS:
                if pattern.search(text):
                    offenders.append(
                        f"{path.relative_to(PROJECT_ROOT)} matches {pattern.pattern}"
                    )

        self.assertEqual(offenders, [])

    def test_frontend_network_calls_go_through_local_api_helper(self):
        offenders = []
        for path in (PROJECT_ROOT / "frontend" / "src").rglob("*"):
            if path.suffix not in {".ts", ".tsx"}:
                continue
            text = path.read_text(encoding="utf-8")
            for match in FETCH_CALL_RE.finditer(text):
                target = match.group("target").strip()
                if target not in {
                    "url(path",
                    "url(\"/api/reindex\"",
                    "url(\"/api/reindex?includeGraph=1\"",
                    "url(\"/api/changes\"",
                    "u.toString(",
                }:
                    offenders.append(f"{path.relative_to(PROJECT_ROOT)} uses fetch({target}")

        self.assertEqual(offenders, [])


def _source_files():
    for root in SOURCE_ROOTS:
        for path in root.rglob("*"):
            if path.is_file() and path.suffix in SOURCE_EXTENSIONS:
                if "web" not in path.relative_to(root).parts:
                    yield path


if __name__ == "__main__":
    unittest.main()
