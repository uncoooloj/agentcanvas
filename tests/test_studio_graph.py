"""Focused contract tests for the v3 studio graph store."""

from __future__ import annotations

import json
import tempfile
import threading
import unittest
from pathlib import Path

from agentcanvas.graph import (
    AnnotationsStore,
    StudioRevisionConflict,
    build_demo_studio_document,
    load_studio_document,
    save_studio_document,
    studio_output_schema,
    validate_studio_document,
)


class StudioGraphTests(unittest.TestCase):
    def test_demo_is_a_valid_complete_document_and_schema_is_strict(self) -> None:
        document = build_demo_studio_document()
        self.assertEqual(validate_studio_document(document), document)

        def check_schema(schema):
            if schema.get("type") == "object":
                self.assertFalse(schema["additionalProperties"])
                self.assertEqual(set(schema["required"]), set(schema["properties"]))
                for child in schema["properties"].values():
                    check_schema(child)
            if "items" in schema:
                check_schema(schema["items"])
            for child in schema.get("anyOf", []):
                check_schema(child)

        for kind in ("map", "diff", "plan", "build"):
            check_schema(studio_output_schema(kind))
        self.assertEqual(set(studio_output_schema("plan")["properties"]), {
            "status", "question", "plan_summary", "document",
        })
        self.assertIn("verification_summary", studio_output_schema("build")["properties"])

    def test_save_load_and_legacy_adaptation(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            document, has_flows = load_studio_document(root)
            self.assertFalse(has_flows)
            saved = save_studio_document(root, document)
            self.assertEqual(1, saved["revision"])
            loaded, has_flows = load_studio_document(root)
            self.assertFalse(has_flows)
            self.assertEqual(1, loaded["revision"])

            (root / ".agentcanvas" / "studio.json").unlink()
            legacy = {
                "schema": "agentcanvas.canvas.v2",
                "flows": [{
                    "id": "checkout",
                    "title": "Checkout",
                    "nodes": [{"id": "start", "kind": "When", "title": "Start"}, {"id": "end", "kind": "End", "title": "End"}],
                    "edges": [{"id": "go", "source": "start", "target": "end", "kind": "normal"}],
                }],
            }
            (root / ".agentcanvas" / "canvas.ir.json").write_text(json.dumps(legacy), encoding="utf-8")
            adapted, has_flows = load_studio_document(root)
            self.assertTrue(has_flows)
            self.assertEqual("checkout", adapted["flows"][0]["id"])
            self.assertEqual("go", adapted["flows"][0]["edges"][0]["id"])

    def test_concurrent_saves_allocate_distinct_revisions(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source, _ = load_studio_document(root)
            revisions: list[int] = []
            failures: list[BaseException] = []
            guard = threading.Lock()

            def save() -> None:
                try:
                    result = save_studio_document(root, source)
                    with guard:
                        revisions.append(result["revision"])
                except BaseException as exc:  # test captures thread failures
                    with guard:
                        failures.append(exc)

            threads = [threading.Thread(target=save) for _ in range(8)]
            for thread in threads: thread.start()
            for thread in threads: thread.join()
            self.assertEqual([], failures)
            self.assertEqual(list(range(1, 9)), sorted(revisions))

    def test_save_rejects_an_outdated_expected_revision(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            original, _ = load_studio_document(root)
            newer = save_studio_document(root, {**original, "summary": "Newer canvas"}, expected_revision=0)
            with self.assertRaisesRegex(StudioRevisionConflict, "^REVISION_CONFLICT$"):
                save_studio_document(root, original, expected_revision=0)
            self.assertEqual(load_studio_document(root)[0], newer)
            (root / ".agentcanvas" / "studio.json").write_text("invalid JSON", encoding="utf-8")
            with self.assertRaises(StudioRevisionConflict):
                save_studio_document(root, original, expected_revision=0)
            self.assertEqual(save_studio_document(root, original)["revision"], 1)

    def test_annotations_crud_and_workspace_confinement(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            store = AnnotationsStore(root)
            record = store.create(target_type="node", target_id="n1", text="Investigate")
            self.assertEqual("unknown", record["author"])
            self.assertTrue(store.update(record["id"], resolved=True)["resolved"])
            store.delete(record["id"])
            self.assertEqual([], store.load())
            with self.assertRaises(LookupError):
                store.delete(record["id"])

        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            outside = root / "outside"
            outside.mkdir()
            (root / ".agentcanvas").symlink_to(outside, target_is_directory=True)
            with self.assertRaises(ValueError):
                load_studio_document(root)

    def test_rejects_dangling_references(self) -> None:
        document = build_demo_studio_document()
        document["flows"][0]["nodes"][0]["component_id"] = "missing"
        with self.assertRaises(ValueError):
            validate_studio_document(document)

    def test_native_legacy_branches_and_evidence_survive_invalid_studio_fallback(self):
        fixture = Path(__file__).parent / "fixtures" / "canvas_v2" / "photo_upload_combined.json"
        legacy = json.loads(fixture.read_text(encoding="utf-8"))
        legacy["flows"][0]["nodes"][0]["evidence_refs"] = ["fact:upload"]
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            state = root / ".agentcanvas"
            state.mkdir()
            invalid = build_demo_studio_document()
            invalid["mode"] = []
            (state / "studio.json").write_text(json.dumps(invalid), encoding="utf-8")
            (state / "canvas.ir.json").write_text(json.dumps(legacy), encoding="utf-8")
            facts = {"source_facts": {"facts": [{
                "id": "fact:upload", "subject": "choosePhotos",
                "provenance": [{"location": {"path": "src/upload.js", "line": 20, "end_line": 25}}],
            }]}}
            (state / "workflow.ir.json").write_text(json.dumps(facts), encoding="utf-8")
            doc, mapped = load_studio_document(root)

        self.assertTrue(mapped)
        self.assertEqual({edge["id"] for edge in doc["flows"][0]["edges"]},
                         {edge["id"] for edge in legacy["flows"][0]["edges"]})
        self.assertEqual(doc["flows"][0]["nodes"][0]["code_refs"], [
            {"path": "src/upload.js", "line": 20, "end_line": 25, "symbol": "choosePhotos"},
        ])

    def test_empty_legacy_and_invalid_document_paths(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            state = root / ".agentcanvas"
            state.mkdir()
            (state / "canvas.ir.json").write_text('{"schema":"agentcanvas.canvas.v2","flows":[]}', encoding="utf-8")
            _, mapped = load_studio_document(root)
            self.assertFalse(mapped)
        for invalid_path in ("../file.py", "/file.py", r"C:\file.py", ""):
            with self.subTest(invalid_path=invalid_path), self.assertRaises(ValueError):
                document = build_demo_studio_document()
                document["flows"][0]["nodes"][0]["code_refs"][0]["path"] = invalid_path
                validate_studio_document(document)

    def test_existing_display_wrapper_is_adapted(self):
        from agentcanvas.core.behavior_canvas import build_behavior_canvas
        from agentcanvas.indexer import index_workspace

        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "app.py").write_text(
                "from flask import Flask\napp = Flask(__name__)\n"
                "@app.get('/orders')\ndef orders():\n    return 'ok'\n", encoding="utf-8",
            )
            wrapper = build_behavior_canvas(index_workspace(root), workspace=root)
            (root / ".agentcanvas" / "canvas.ir.json").write_text(json.dumps(wrapper), encoding="utf-8")
            document, mapped = load_studio_document(root)
        self.assertTrue(wrapper["canvas"]["journeys"])
        self.assertTrue(mapped)
        self.assertEqual(len(document["flows"]), len(wrapper["canvas"]["journeys"]))


if __name__ == "__main__":
    unittest.main()
