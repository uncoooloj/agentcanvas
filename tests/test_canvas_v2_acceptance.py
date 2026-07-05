import json
import tempfile
import unittest
from pathlib import Path

from agentcanvas.canvas_v2 import load_canvas_document, validate_canvas_v2


FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "canvas_v2"
NODE_KINDS = {
    "When",
    "Do",
    "Decision",
    "Loop",
    "Parallel",
    "Join",
    "Wait",
    "SubFlow",
    "End",
}


def _load_fixture(name):
    with (FIXTURE_DIR / name).open(encoding="utf-8") as handle:
        return json.load(handle)


class CanvasV2AcceptanceTests(unittest.TestCase):
    maxDiff = None

    def test_strict_validation_accepts_fixture_covering_every_node_kind(self):
        fixture = _load_fixture("all_node_kinds.json")

        result = validate_canvas_v2(fixture, mode="strict")

        kinds = {
            node["kind"]
            for flow in fixture["flows"]
            for node in flow["nodes"]
        }
        self.assertEqual(kinds, NODE_KINDS)
        self.assertEqual(result["mode"], "strict")
        self.assertEqual(result["flow_count"], 2)
        self.assertEqual(result["node_count"], 14)

    def test_photo_upload_fixture_round_trips_after_normalize_validate_and_serialize(self):
        fixture = _load_fixture("photo_upload_combined.json")
        flow = fixture["flows"][0]

        node_by_id = {node["id"]: node for node in flow["nodes"]}
        self.assertEqual(node_by_id["n:upload:loop"]["kind"], "Loop")
        self.assertEqual(node_by_id["n:upload:check"]["kind"], "Decision")
        self.assertEqual(node_by_id["n:upload:parallel"]["kind"], "Parallel")
        self.assertEqual(node_by_id["n:upload:join"]["kind"], "Join")
        self.assertEqual(node_by_id["n:upload:failed"]["kind"], "End")

        warning_path = next(edge for edge in flow["edges"] if edge["id"] == "e:upload:check:warn")
        self.assertEqual(warning_path["target"], "n:upload:warn")
        failure_edges = [
            edge
            for edge in flow["edges"]
            if edge["kind"] == "error" and edge["target"] == "n:upload:failed"
        ]
        self.assertEqual(
            sorted(edge["id"] for edge in failure_edges),
            ["e:upload:check:failed", "e:upload:store-original:failed"],
        )

        with tempfile.TemporaryDirectory() as temp_root:
            workspace = Path(temp_root) / "workspace"
            state_dir = workspace / ".agentcanvas"
            state_dir.mkdir(parents=True)
            (state_dir / "canvas.ir.json").write_text(json.dumps(fixture), encoding="utf-8")

            normalized = load_canvas_document(workspace)
            result = validate_canvas_v2(normalized, mode="strict")
            serialized = json.loads(json.dumps(normalized, sort_keys=True))

        self.assertTrue(result["ok"])
        self.assertEqual(serialized, fixture)


if __name__ == "__main__":
    unittest.main()
