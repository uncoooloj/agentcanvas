import re
import unittest
from pathlib import Path

from agentcanvas.canvas_v2.store import KNOWN_EDGE_KINDS, KNOWN_NODE_KINDS, KNOWN_STATUSES
from agentcanvas.lifecycle import PendingStatus


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_TYPES = PROJECT_ROOT / "frontend" / "src" / "lib" / "types.ts"


def ts_enum_values(name):
    source = FRONTEND_TYPES.read_text(encoding="utf-8")
    match = re.search(rf"export enum {re.escape(name)} \{{(?P<body>.*?)\n\}}", source, re.DOTALL)
    if not match:
        raise AssertionError(f"TypeScript enum {name} was not found in {FRONTEND_TYPES}")
    return set(re.findall(r'"([^"]+)"', match.group("body")))


class EnumContractTests(unittest.TestCase):
    def test_pending_status_values_match_frontend_contract(self):
        backend = {status.value for status in PendingStatus}

        self.assertEqual(backend, ts_enum_values("PendingStatus"))

    def test_canvas_v2_status_values_match_frontend_contract(self):
        self.assertEqual(KNOWN_STATUSES, ts_enum_values("CanvasV2Status"))

    def test_canvas_v2_node_kind_values_match_frontend_contract(self):
        self.assertEqual(KNOWN_NODE_KINDS, ts_enum_values("CanvasV2NodeKind"))

    def test_canvas_v2_edge_kind_values_match_frontend_contract(self):
        self.assertEqual(KNOWN_EDGE_KINDS, ts_enum_values("CanvasV2EdgeKind"))


if __name__ == "__main__":
    unittest.main()
