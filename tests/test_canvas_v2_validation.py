import unittest

from agentcanvas.canvas_v2 import CanvasStoreError, validate_canvas_v2


class CanvasV2ValidationTests(unittest.TestCase):
    def test_authoring_mode_allows_empty_canvas(self):
        result = validate_canvas_v2(
            {
                "schema": "agentcanvas.canvas.v2",
                "app": {},
                "flows": [],
            }
        )

        self.assertEqual(result["mode"], "authoring")
        self.assertEqual(result["flow_count"], 0)

    def test_strict_mode_requires_a_complete_reachable_flow(self):
        with self.assertRaises(CanvasStoreError) as raised:
            validate_canvas_v2(
                {
                    "schema": "agentcanvas.canvas.v2",
                    "app": {},
                    "flows": [
                        {
                            "id": "flow:signup",
                            "title": "Signup",
                            "nodes": [
                                {"id": "n:start", "kind": "When", "title": "Someone signs up"},
                                {"id": "n:create", "kind": "Do", "title": "Create the account"},
                            ],
                            "edges": [],
                        }
                    ],
                },
                mode="strict",
            )

        self.assertEqual(raised.exception.code, "ENTRY_NODE_REQUIRED")

    def test_strict_mode_reports_unreachable_nodes(self):
        with self.assertRaises(CanvasStoreError) as raised:
            validate_canvas_v2(
                {
                    "schema": "agentcanvas.canvas.v2",
                    "app": {},
                    "flows": [
                        {
                            "id": "flow:signup",
                            "title": "Signup",
                            "entry_node": "n:start",
                            "nodes": [
                                {"id": "n:start", "kind": "When", "title": "Someone signs up"},
                                {"id": "n:create", "kind": "Do", "title": "Create the account"},
                            ],
                            "edges": [],
                        }
                    ],
                },
                mode="strict",
            )

        self.assertEqual(raised.exception.code, "UNREACHABLE_NODE")
        self.assertEqual(raised.exception.details["nodes"], ["n:create"])

    def test_strict_mode_accepts_reachable_flow(self):
        result = validate_canvas_v2(
            {
                "schema": "agentcanvas.canvas.v2",
                "app": {},
                "flows": [
                    {
                        "id": "flow:signup",
                        "title": "Signup",
                        "entry_node": "n:start",
                        "nodes": [
                            {"id": "n:start", "kind": "When", "title": "Someone signs up"},
                            {"id": "n:create", "kind": "Do", "title": "Create the account"},
                        ],
                        "edges": [
                            {
                                "id": "e:start:create",
                                "source": "n:start",
                                "target": "n:create",
                                "kind": "normal",
                            }
                        ],
                    }
                ],
            },
            mode="strict",
        )

        self.assertEqual(result["mode"], "strict")
        self.assertEqual(result["node_count"], 2)


if __name__ == "__main__":
    unittest.main()
