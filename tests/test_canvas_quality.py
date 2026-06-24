import unittest

from agentcanvas.projection import (
    CANVAS_QUERY_SCHEMA,
    materialize_canvas_model,
    validate_canvas_query,
    validate_canvas_query_quality,
    validate_canvas_query_result,
)
from agentcanvas.projection.sample import SAMPLE_LLM_CANVAS_QUERY, SAMPLE_SOURCE_FACTS


class CanvasQualityTests(unittest.TestCase):
    maxDiff = None

    def test_sample_canvas_query_has_no_visible_text_quality_warnings(self):
        result = validate_canvas_query_result(
            SAMPLE_LLM_CANVAS_QUERY,
            SAMPLE_SOURCE_FACTS,
        )

        self.assertEqual([], result["errors"])
        self.assertEqual([], result["warnings"])
        self.assertEqual([], validate_canvas_query_quality(SAMPLE_LLM_CANVAS_QUERY))

    def test_quality_warnings_are_non_blocking_and_materialized(self):
        query = {
            "schema": CANVAS_QUERY_SCHEMA,
            "version": "0.1.0",
            "mode": "llm-assisted",
            "operations": [
                {
                    "op": "upsert_node",
                    "node": {
                        "id": "flow:technical-checkout",
                        "type": "flow",
                        "label": "src/handlers/checkout_handler.py",
                        "data": {
                            "journey": {
                                "title": (
                                    "Review the CI middleware handler module protocol "
                                    "for checkout_account_state_update in src/**/*.py "
                                    "before launch"
                                ),
                                "entry": "CI starts the checkout_handler module.",
                                "summary": "The AST linter checks src/handlers/checkout_handler.py.",
                                "steps": [
                                    {
                                        "kind": "When",
                                        "text": "CI opens src/handlers/checkout_handler.py.",
                                    },
                                    {
                                        "kind": "Do",
                                        "text": "Run the checkout_handler middleware.",
                                    },
                                    {"kind": "Do", "text": "Load module settings."},
                                    {"kind": "Do", "text": "Parse the AST."},
                                    {"kind": "Do", "text": "Check the protocol."},
                                    {"kind": "Do", "text": "Run the linter."},
                                    {"kind": "Do", "text": "Expand src/**/*.py."},
                                    {"kind": "Do", "text": "Update checkout_state."},
                                    {"kind": "Do", "text": "Notify the next handler."},
                                ],
                            },
                        },
                    },
                    "fact_ids": ["fact:file:src/checkout.js"],
                    "confidence": 0.8,
                    "rationale": "Deliberately technical visible text for quality checks.",
                }
            ],
            "warnings": ["Existing author warning."],
        }

        self.assertEqual([], validate_canvas_query(query, SAMPLE_SOURCE_FACTS))

        result = validate_canvas_query_result(query, SAMPLE_SOURCE_FACTS)
        joined_warnings = "\n".join(result["warnings"])

        self.assertEqual([], result["errors"])
        self.assertIn("raw file path", joined_warnings)
        self.assertIn("glob pattern", joined_warnings)
        self.assertIn("implementation token", joined_warnings)
        self.assertIn("technical jargon", joined_warnings)
        self.assertIn("very long", joined_warnings)
        self.assertIn("has 9 visible steps", joined_warnings)

        model = materialize_canvas_model(
            query,
            SAMPLE_SOURCE_FACTS["repo"],
            source_facts=SAMPLE_SOURCE_FACTS,
        )
        materialized_warnings = "\n".join(model["projection"]["warnings"])

        self.assertIn("Existing author warning.", model["projection"]["warnings"])
        self.assertIn("raw file path", materialized_warnings)
        self.assertIn("glob pattern", materialized_warnings)
        self.assertIn("implementation token", materialized_warnings)
        self.assertIn("technical jargon", materialized_warnings)
        self.assertIn("has 9 visible steps", materialized_warnings)


if __name__ == "__main__":
    unittest.main()
