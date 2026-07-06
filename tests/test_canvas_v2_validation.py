import unittest

from agentcanvas.canvas_v2 import CanvasStoreError, validate_canvas_v2


class CanvasV2ValidationTests(unittest.TestCase):
    def assertValidationError(self, document, *, mode="authoring", code):
        with self.assertRaises(CanvasStoreError) as raised:
            validate_canvas_v2(document, mode=mode)

        envelope = raised.exception.to_dict()
        self.assertEqual(envelope["error"]["code"], code)
        self.assertIn("repair_hint", envelope["error"])
        self.assertTrue(envelope["error"]["repair_hint"])
        return raised.exception

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
        self.assertEqual(result["warnings"], [])

    def test_authoring_mode_reports_incomplete_and_degraded_warnings(self):
        result = validate_canvas_v2(
            {
                "schema": "agentcanvas.canvas.v2",
                "app": {},
                "flows": [
                    {
                        "id": "flow:draft",
                        "title": "Draft",
                        "nodes": [
                            {
                                "id": "n:draft:start",
                                "kind": "When",
                                "title": "Draft starts",
                                "metadata": {"degraded": True},
                            }
                        ],
                        "edges": [],
                    }
                ],
            }
        )

        warnings_by_code = {warning["code"]: warning for warning in result["warnings"]}
        self.assertIn("ENTRY_NODE_MISSING", warnings_by_code)
        self.assertIn("DEGRADED_NODE", warnings_by_code)
        for warning in result["warnings"]:
            self.assertTrue(warning["repair_hint"])

    def test_authoring_mode_warns_for_incomplete_decision_and_loop_paths(self):
        result = validate_canvas_v2(
            {
                "schema": "agentcanvas.canvas.v2",
                "app": {},
                "flows": [
                    {
                        "id": "flow:draft",
                        "title": "Draft",
                        "entry_node": "n:start",
                        "nodes": [
                            {"id": "n:start", "kind": "When", "title": "Start", "evidence_refs": ["src/app.ts"]},
                            {"id": "n:decision", "kind": "Decision", "title": "Can continue?", "evidence_refs": ["src/app.ts"]},
                            {"id": "n:loop", "kind": "Loop", "title": "Retry work", "evidence_refs": ["src/app.ts"]},
                            {"id": "n:done", "kind": "End", "title": "Done"},
                        ],
                        "edges": [
                            {"id": "e:start:decision", "source": "n:start", "target": "n:decision", "kind": "normal"},
                            {"id": "e:decision:loop", "source": "n:decision", "target": "n:loop", "kind": "branch"},
                            {"id": "e:loop:done", "source": "n:loop", "target": "n:done", "kind": "loop_body"},
                        ],
                    }
                ],
            }
        )

        warnings_by_code = {warning["code"]: warning for warning in result["warnings"]}
        self.assertIn("DECISION_BRANCHES_INCOMPLETE", warnings_by_code)
        self.assertIn("LOOP_EXIT_INCOMPLETE", warnings_by_code)

    def test_invalid_validation_mode_reports_repair_hint(self):
        self.assertValidationError(
            {
                "schema": "agentcanvas.canvas.v2",
                "app": {},
                "flows": [],
            },
            mode="publish",
            code="INVALID_VALIDATION_MODE",
        )

    def test_strict_mode_requires_a_complete_reachable_flow(self):
        self.assertValidationError(
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
            code="ENTRY_NODE_REQUIRED",
        )

    def test_strict_mode_reports_unreachable_nodes(self):
        error = self.assertValidationError(
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
            code="UNREACHABLE_NODE",
        )

        self.assertEqual(error.details["nodes"], ["n:create"])

    def test_store_shape_rejection_is_wrapped_with_repair_hint(self):
        self.assertValidationError(
            {
                "schema": "agentcanvas.canvas.v2",
                "app": {},
                "flows": [
                    {
                        "id": "flow:signup",
                        "title": "Signup",
                        "entry_node": "n:start",
                        "nodes": [
                            {"id": "n:start", "kind": "Mystery", "title": "Someone signs up"},
                        ],
                        "edges": [],
                    }
                ],
            },
            code="UNKNOWN_NODE_KIND",
        )

    def test_strict_mode_rejects_loop_without_exit(self):
        self.assertValidationError(
            {
                "schema": "agentcanvas.canvas.v2",
                "app": {},
                "flows": [
                    {
                        "id": "flow:loop",
                        "title": "Loop",
                        "entry_node": "n:start",
                        "nodes": [
                            {"id": "n:start", "kind": "When", "title": "Start"},
                            {"id": "n:loop", "kind": "Loop", "title": "Retry work"},
                            {"id": "n:do", "kind": "Do", "title": "Do work"},
                        ],
                        "edges": [
                            {"id": "e:start:loop", "source": "n:start", "target": "n:loop", "kind": "normal"},
                            {"id": "e:loop:do", "source": "n:loop", "target": "n:do", "kind": "loop_body"},
                        ],
                    }
                ],
            },
            mode="strict",
            code="LOOP_EXIT_REQUIRED",
        )

    def test_strict_mode_rejects_decision_with_one_branch(self):
        self.assertValidationError(
            {
                "schema": "agentcanvas.canvas.v2",
                "app": {},
                "flows": [
                    {
                        "id": "flow:decision",
                        "title": "Decision",
                        "entry_node": "n:start",
                        "nodes": [
                            {"id": "n:start", "kind": "When", "title": "Start"},
                            {"id": "n:decision", "kind": "Decision", "title": "Can continue?"},
                            {"id": "n:done", "kind": "End", "title": "Done"},
                        ],
                        "edges": [
                            {"id": "e:start:decision", "source": "n:start", "target": "n:decision", "kind": "normal"},
                            {"id": "e:decision:done", "source": "n:decision", "target": "n:done", "kind": "branch"},
                        ],
                    }
                ],
            },
            mode="strict",
            code="DECISION_BRANCHES_REQUIRED",
        )

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
        self.assertEqual(result["warnings"], [])


if __name__ == "__main__":
    unittest.main()
