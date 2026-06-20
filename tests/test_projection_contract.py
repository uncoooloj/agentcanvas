import json
import unittest

from agentcanvas.ir import SCHEMA as WORKFLOW_IR_SCHEMA
from agentcanvas.projection import (
    CANVAS_QUERY_SCHEMA,
    PROJECTION_CONTRACT_SCHEMA,
    SOURCE_FACTS_SCHEMA,
    build_projection_contract,
    build_projection_prompt,
    facts_from_workflow_ir,
    heuristic_project,
    materialize_canvas_model,
    validate_canvas_query,
)
from agentcanvas.projection.sample import SAMPLE_SOURCE_FACTS, build_sample_projection


class ProjectionContractTests(unittest.TestCase):
    maxDiff = None

    def test_projection_contract_prefers_llm_assisted_grounded_projection(self):
        contract = build_projection_contract(SAMPLE_SOURCE_FACTS)

        self.assertEqual(contract["schema"], PROJECTION_CONTRACT_SCHEMA)
        self.assertEqual(contract["primary_mode"], "llm-assisted")
        self.assertEqual(contract["fallback_mode"], "heuristic")
        self.assertEqual(
            contract["language_module_role"]["purpose"],
            "grounding_chunking_provenance",
        )
        self.assertIn(
            "Treat LLM-assisted projection as the primary path.",
            contract["instructions"],
        )
        instructions = "\n".join(contract["instructions"])
        self.assertIn("source_facts", instructions)
        self.assertIn("repo app_surfaces", instructions)
        self.assertIn("ask concise clarifying questions", instructions)
        self.assertIn("When, Do, If, ElseIf, and Else", instructions)
        self.assertIn("Do not create top-level journeys from raw file inventories", instructions)
        self.assertIn("Progressive mapping is acceptable", instructions)

    def test_projection_prompt_is_provider_and_agent_agnostic(self):
        prompt = build_projection_prompt(SAMPLE_SOURCE_FACTS)
        prompt_text = json.dumps(prompt)

        self.assertEqual(prompt["source_facts"]["schema"], SOURCE_FACTS_SCHEMA)
        response_schema_name = prompt["response_schema"]["properties"]["schema"]["const"]
        self.assertEqual(response_schema_name, CANVAS_QUERY_SCHEMA)
        self.assertIn("grounding, chunking, and provenance providers", prompt_text)
        self.assertIn("When, Do, If, ElseIf, and Else", prompt_text)
        self.assertIn("app_surfaces", prompt_text)
        self.assertIn("raw file invent", prompt_text)
        self.assertNotIn("Codex", prompt_text)
        self.assertNotIn("Claude", prompt_text)
        self.assertNotIn("Cursor", prompt_text)
        self.assertNotIn("Antigravity", prompt_text)

    def test_sample_facts_prompt_and_canvas_model_validate(self):
        sample = build_sample_projection()
        canvas_model = sample["canvas_model"]

        self.assertEqual(sample["source_facts"]["schema"], SOURCE_FACTS_SCHEMA)
        self.assertEqual(
            sample["prompt_contract"]["schema"],
            "agentcanvas.llm_projection_prompt.v1",
        )
        self.assertEqual(sample["llm_canvas_query"]["mode"], "llm-assisted")
        self.assertEqual(canvas_model["schema"], WORKFLOW_IR_SCHEMA)
        self.assertEqual(canvas_model["summary"]["nodes"], 3)
        self.assertEqual(canvas_model["summary"]["edges"], 2)
        checkout_node = next(
            node for node in canvas_model["nodes"] if node["id"] == "flow:checkout"
        )
        self.assertEqual(
            ["fact:file:src/checkout.js"],
            checkout_node["data"]["projection"]["fact_ids"],
        )
        self.assertEqual(
            "Checkout",
            checkout_node["data"]["journey"]["title"],
        )
        self.assertEqual(
            ["When", "Do"],
            [
                step["kind"]
                for step in checkout_node["data"]["journey"]["steps"]
            ],
        )

    def test_heuristic_projection_materializes_existing_canvas_facts(self):
        workflow_ir = {
            "schema": WORKFLOW_IR_SCHEMA,
            "version": "0.1.0",
            "workspace": {"root": "/tmp/example", "name": "example"},
            "summary": {},
            "package": {},
            "git": {},
            "focus": {},
            "components": [],
            "nodes": [
                {
                    "id": "file:src/a.js",
                    "type": "file",
                    "label": "a.js",
                    "path": "src/a.js",
                    "data": {},
                },
                {
                    "id": "file:src/b.js",
                    "type": "file",
                    "label": "b.js",
                    "path": "src/b.js",
                    "data": {},
                },
            ],
            "edges": [
                {
                    "id": "file:src/a.js->imports->file:src/b.js",
                    "source": "file:src/a.js",
                    "target": "file:src/b.js",
                    "kind": "imports",
                }
            ],
        }
        source_facts = facts_from_workflow_ir(workflow_ir)
        query = heuristic_project(source_facts)
        model = materialize_canvas_model(
            query,
            source_facts["repo"],
            source_facts=source_facts,
        )

        self.assertEqual(query["mode"], "heuristic")
        self.assertEqual(model["summary"]["nodes"], 2)
        self.assertEqual(model["summary"]["edges"], 1)

    def test_workflow_facts_include_app_surfaces_for_monorepos(self):
        workflow_ir = {
            "schema": WORKFLOW_IR_SCHEMA,
            "version": "0.1.0",
            "workspace": {"root": "/tmp/example", "name": "example"},
            "summary": {"app_surfaces": 2},
            "package": {},
            "git": {},
            "focus": {},
            "app_surfaces": [
                {
                    "id": "surface:apps:mobile",
                    "root": "apps/mobile",
                    "name": "mobile",
                    "kind": "mobile",
                    "platform": "flutter",
                    "manifest_paths": ["apps/mobile/pubspec.yaml"],
                    "languages": ["dart-flutter"],
                    "entrypoints": [{"kind": "route", "path": "/signup"}],
                    "confidence": 0.8,
                },
                {
                    "id": "surface:services:api",
                    "root": "services/api",
                    "name": "api",
                    "kind": "backend",
                    "platform": "server",
                    "manifest_paths": ["services/api/go.mod"],
                    "languages": ["go"],
                    "entrypoints": [{"kind": "route", "path": "/signup", "method": "POST"}],
                    "confidence": 0.8,
                },
            ],
            "components": [],
            "nodes": [],
            "edges": [],
        }

        source_facts = facts_from_workflow_ir(workflow_ir)
        surface_facts = [
            fact for fact in source_facts["facts"] if fact["kind"] == "app_surface"
        ]

        self.assertEqual(len(surface_facts), 2)
        self.assertEqual(
            source_facts["repo"]["app_surfaces"],
            workflow_ir["app_surfaces"],
        )
        instructions = " ".join(build_projection_contract(source_facts)["instructions"])
        self.assertIn("group behavior by human journey first", instructions)

    def test_canvas_query_rejects_unknown_fact_ids(self):
        query = {
            "schema": CANVAS_QUERY_SCHEMA,
            "version": "0.1.0",
            "mode": "llm-assisted",
            "operations": [
                {
                    "op": "upsert_node",
                    "node": {
                        "id": "route:/ghost",
                        "type": "route",
                        "label": "Ghost route",
                    },
                    "fact_ids": ["fact:not-present"],
                    "confidence": 0.5,
                    "rationale": "Unsupported.",
                }
            ],
            "warnings": [],
        }

        errors = validate_canvas_query(query, SAMPLE_SOURCE_FACTS)

        self.assertTrue(any("unknown id fact:not-present" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
