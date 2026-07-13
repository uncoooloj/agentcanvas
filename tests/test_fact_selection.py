import unittest

from agentcanvas.core.facts import prioritize_facts
from agentcanvas.projection.contracts import SOURCE_FACTS_SCHEMA, build_projection_prompt, normalize_fact_bundle


def _fact(fact_id, kind, **extra):
    fact = {
        "id": fact_id,
        "kind": kind,
        "subject": fact_id,
        "summary": fact_id,
        "attributes": {},
        "evidence": [{"path": f"src/{fact_id}.py", "line": 1}],
    }
    fact.update(extra)
    return fact


class FactSelectionTests(unittest.TestCase):
    def test_prioritization_is_deterministic_and_keeps_entrypoint_link_and_endpoint(self):
        facts = [
            _fact("ordinary-z", "file"),
            _fact("node:src/entry.py", "canvas_node", evidence=[{"path": "src/entry.py"}]),
            _fact(
                "edge:entry-to-handler",
                "canvas_edge",
                attributes={
                    "edge": {
                        "source": "src/entry.py",
                        "target": "src/handler.py",
                        "kind": "calls",
                    }
                },
                evidence=[],
            ),
            _fact("route:/checkout", "language_route", attributes={"fact_type": "route"}),
            _fact("ordinary-a", "file"),
            _fact("node:src/handler.py", "canvas_node", evidence=[{"path": "src/handler.py"}]),
        ]

        selected, metadata = prioritize_facts(list(reversed(facts)), 4)
        selected_again, metadata_again = prioritize_facts(facts, 4)

        self.assertEqual([fact["id"] for fact in selected], [fact["id"] for fact in selected_again])
        self.assertEqual(
            {"route:/checkout", "edge:entry-to-handler", "node:src/entry.py", "node:src/handler.py"},
            {fact["id"] for fact in selected},
        )
        self.assertEqual(metadata["total_facts"], 6)
        self.assertEqual(metadata["included_facts"], 4)
        self.assertEqual(metadata["omitted_facts"], 2)
        self.assertFalse(metadata["complete"])
        self.assertEqual(metadata, metadata_again)

    def test_contract_carries_forward_upstream_omissions(self):
        source = {
            "schema": SOURCE_FACTS_SCHEMA,
            "version": "0.1.0",
            "repo": {},
            "facts": [_fact("route:/checkout", "language_route"), _fact("file:a", "file")],
            "fact_selection": {
                "strategy": "priority-v1",
                "max_facts": 2,
                "chunk_index": 0,
                "chunk_count": 2,
                "total_facts": 5,
                "included_facts": 2,
                "omitted_facts": 3,
                "complete": False,
                "omitted_by_kind": {"file": 3},
                "omitted_fact_ids": ["file:omitted"],
                "omitted_fact_ids_truncated": False,
            },
        }

        bundle = normalize_fact_bundle(source, max_facts=1)

        self.assertEqual(bundle["fact_selection"]["total_facts"], 5)
        self.assertEqual(bundle["fact_selection"]["included_facts"], 1)
        self.assertEqual(bundle["fact_selection"]["omitted_facts"], 4)
        self.assertFalse(bundle["fact_selection"]["complete"])
        self.assertIn("file:omitted", bundle["fact_selection"]["omitted_fact_ids"])

    def test_prompt_surfaces_incomplete_fact_selection(self):
        source = {
            "schema": SOURCE_FACTS_SCHEMA,
            "version": "0.1.0",
            "repo": {},
            "facts": [_fact("route:/checkout", "language_route"), _fact("file:a", "file")],
        }

        prompt = build_projection_prompt(source, max_facts=1)
        prompt_text = prompt["messages"][1]["content"]

        self.assertIn("Fact selection and completeness", prompt_text)
        self.assertIn('"complete": false', prompt_text)
        self.assertIn("fact_selection", " ".join(prompt["instructions"]))


if __name__ == "__main__":
    unittest.main()
