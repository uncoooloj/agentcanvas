import copy
import unittest

from agentcanvas.canvas_v2 import detect_v1_canvas, flatten_canvas_v2, migrate_canvas_v1_to_v2


class CanvasV2MigrationTests(unittest.TestCase):
    def test_detects_real_v1_shapes(self):
        display = _display_canvas()
        typed = _typed_canvas()

        self.assertTrue(detect_v1_canvas(typed))
        self.assertTrue(detect_v1_canvas({"canvas": display}))
        self.assertTrue(detect_v1_canvas(display))
        self.assertTrue(detect_v1_canvas({"canvas_model": typed}))
        self.assertTrue(detect_v1_canvas({"canvasModel": display}))
        self.assertTrue(detect_v1_canvas({"model": display}))
        self.assertTrue(detect_v1_canvas(_behavior_wrapper(display)))
        self.assertFalse(detect_v1_canvas({"schema": "agentcanvas.canvas.v2", "flows": []}))

    def test_migrates_display_branch_nodes_to_decisions_recursively(self):
        v2 = migrate_canvas_v1_to_v2(_display_canvas(), updated_at="2026-07-05T12:00:00Z")

        self.assertEqual(v2["schema"], "agentcanvas.canvas.v2")
        self.assertEqual(v2["app"]["name"], "Checkout")
        self.assertFalse(v2["app"]["is_demo"])

        flow = v2["flows"][0]
        self.assertEqual(flow["id"], "checkout-flow")
        self.assertEqual(flow["entry_node"], "start")
        node_by_id = {node["id"]: node for node in flow["nodes"]}

        self.assertEqual(node_by_id["start"]["kind"], "When")
        self.assertEqual(node_by_id["stock-check"]["kind"], "Decision")
        self.assertEqual(node_by_id["vip-check"]["kind"], "Decision")
        self.assertEqual(node_by_id["reserve-stock"]["kind"], "Do")
        self.assertEqual(node_by_id["reserve-stock"]["metadata"]["tech"]["nodeId"], "call:reserve")
        self.assertEqual(node_by_id["reserve-stock"]["evidence_refs"], ["call:reserve"])

        branch_edges = [edge for edge in flow["edges"] if edge["kind"] == "branch"]
        self.assertEqual(
            sorted((edge["source"], edge["target"], edge["label"]) for edge in branch_edges),
            [
                ("stock-check", "backorder", "Otherwise"),
                ("stock-check", "reserve-stock", "Item is in stock"),
                ("vip-check", "manual-review", "Otherwise"),
                ("vip-check", "ship-free", "Customer is VIP"),
            ],
        )
        self.assertEqual(node_by_id["stock-check"]["metadata"]["source"]["kind"], "manual")

    def test_migrates_behavior_wrapper_metadata_and_is_idempotent_except_updated_at(self):
        wrapped = _behavior_wrapper(_display_canvas())

        first = migrate_canvas_v1_to_v2(wrapped, updated_at="one")
        second = migrate_canvas_v1_to_v2(wrapped, updated_at="two")
        first_without_time = copy.deepcopy(first)
        second_without_time = copy.deepcopy(second)
        first_without_time.pop("updated_at")
        second_without_time.pop("updated_at")

        self.assertEqual(first_without_time, second_without_time)
        self.assertEqual(first["metadata"]["legacy_wrapper"]["mapping"]["mode"], "agent-authored")
        self.assertEqual(first["metadata"]["legacy_wrapper"]["schema"], "agentcanvas.behavior_canvas_response.v1")

    def test_migrates_typed_if_elseif_else_chain_to_one_decision(self):
        v2 = migrate_canvas_v1_to_v2(_typed_canvas(), updated_at="2026-07-05T12:00:00Z")
        flow = v2["flows"][0]

        decision_nodes = [node for node in flow["nodes"] if node["kind"] == "Decision"]
        self.assertEqual([node["id"] for node in decision_nodes], ["eligible"])
        branch_edges = [edge for edge in flow["edges"] if edge["source"] == "eligible" and edge["kind"] == "branch"]
        self.assertEqual(
            sorted((edge["target"], edge["label"], edge.get("is_default")) for edge in branch_edges),
            [
                ("manual", "Else", True),
                ("notify", "Account is new", False),
                ("upgrade", "Account is trusted", False),
            ],
        )
        legacy_ids = sorted(edge["metadata"]["legacy_step"]["id"] for edge in branch_edges)
        self.assertEqual(legacy_ids, ["eligible", "fallback", "trusted"])

    def test_flattens_v2_back_to_current_display_wrapper(self):
        v2 = migrate_canvas_v1_to_v2(_display_canvas(), updated_at="2026-07-05T12:00:00Z")

        display = flatten_canvas_v2(v2)

        self.assertEqual(display["appName"], "Checkout")
        self.assertEqual(display["isDemo"], False)
        journey = display["journeys"][0]
        self.assertEqual(journey["id"], "checkout-flow")
        self.assertEqual([node["kind"] for node in journey["nodes"]], ["step", "branch"])
        self.assertEqual(journey["nodes"][0]["role"], "when")

        branch = journey["nodes"][1]
        self.assertEqual(branch["id"], "stock-check")
        self.assertEqual(branch["condition"], "Item is in stock")
        self.assertEqual(branch["then"][0]["text"], "Reserve stock")
        nested = branch["then"][1]
        self.assertEqual(nested["kind"], "branch")
        self.assertEqual(nested["condition"], "Customer is VIP")
        self.assertEqual([node["text"] for node in nested["then"]], ["Ship for free"])
        self.assertEqual([node["text"] for node in branch["otherwise"]], ["Create backorder"])


def _display_canvas():
    return {
        "schema": "agentcanvas.behavior_canvas.v1",
        "version": "0.1.0",
        "appName": "Checkout",
        "isDemo": False,
        "metadata": {"source": {"kind": "agent-authored"}},
        "journeys": [
            {
                "id": "checkout-flow",
                "title": "Buying an item",
                "summary": "A customer checks out.",
                "entry": "A customer starts checkout",
                "nodes": [
                    {
                        "kind": "step",
                        "id": "start",
                        "role": "when",
                        "text": "A customer starts checkout",
                    },
                    {
                        "kind": "branch",
                        "id": "stock-check",
                        "condition": "Item is in stock",
                        "metadata": {"source": {"kind": "manual"}},
                        "then": [
                            {
                                "kind": "step",
                                "id": "reserve-stock",
                                "role": "do",
                                "text": "Reserve stock",
                                "detail": "Calls inventory reservation.",
                                "tech": {"nodeId": "call:reserve", "refs": ["call:reserve"]},
                            },
                            {
                                "kind": "branch",
                                "id": "vip-check",
                                "condition": "Customer is VIP",
                                "then": [
                                    {
                                        "kind": "step",
                                        "id": "ship-free",
                                        "role": "do",
                                        "text": "Ship for free",
                                    }
                                ],
                                "otherwise": [
                                    {
                                        "kind": "step",
                                        "id": "manual-review",
                                        "role": "do",
                                        "text": "Ask support to review shipping",
                                    }
                                ],
                            },
                        ],
                        "otherwise": [
                            {
                                "kind": "step",
                                "id": "backorder",
                                "role": "do",
                                "text": "Create backorder",
                                "uncertain": True,
                            }
                        ],
                    },
                ],
            }
        ],
    }


def _typed_canvas():
    return {
        "schema": "agentcanvas.canvas.v1",
        "version": "0.1.0",
        "metadata": {"title": "Accounts"},
        "journeys": [
            {
                "id": "account-flow",
                "title": "Opening an account",
                "steps": [
                    {"id": "account-start", "kind": "When", "text": "Someone opens an account"},
                    {
                        "id": "eligible",
                        "kind": "If",
                        "condition": "Account is new",
                        "steps": [{"id": "notify", "kind": "Do", "text": "Notify the customer"}],
                    },
                    {
                        "id": "trusted",
                        "kind": "ElseIf",
                        "condition": "Account is trusted",
                        "steps": [{"id": "upgrade", "kind": "Do", "text": "Upgrade limits"}],
                    },
                    {
                        "id": "fallback",
                        "kind": "Else",
                        "steps": [{"id": "manual", "kind": "Do", "text": "Send to manual review"}],
                    },
                ],
            }
        ],
    }


def _behavior_wrapper(canvas):
    return {
        "schema": "agentcanvas.behavior_canvas_response.v1",
        "version": "0.1.0",
        "canvas": canvas,
        "mapping": {
            "schema": "agentcanvas.canvas_mapping.v1",
            "mode": "agent-authored",
            "flowCount": 1,
        },
    }


if __name__ == "__main__":
    unittest.main()
