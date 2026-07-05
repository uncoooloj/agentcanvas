import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from agentcanvas.canvas_v2.evidence import (
    EVIDENCE_STATUS_FRESH,
    EVIDENCE_STATUS_POSSIBLY_STALE,
    EVIDENCE_STATUS_STALE,
    build_workflow_evidence,
    build_workflow_evidence_from_path,
    compare_canvas_evidence,
    compare_canvas_with_current_workflow_evidence,
    source_facts_sha256,
)


class CanvasV2EvidenceTests(unittest.TestCase):
    def test_builds_top_level_evidence_from_workflow_bytes(self):
        workflow_ir = {
            "schema": "agentcanvas.workflow.v1",
            "generated_at": "2026-07-05T12:00:00Z",
            "source_facts": _source_facts(),
        }
        workflow_bytes = json.dumps(workflow_ir, indent=2).encode("utf-8")

        evidence = build_workflow_evidence(
            workflow_ir,
            workflow_bytes=workflow_bytes,
            git_head="abc123",
        )

        self.assertEqual(
            sorted(evidence),
            [
                "git_head",
                "source_facts_sha256",
                "workflow_generated_at",
                "workflow_sha256",
            ],
        )
        self.assertEqual(evidence["git_head"], "abc123")
        self.assertEqual(evidence["workflow_generated_at"], "2026-07-05T12:00:00Z")
        self.assertEqual(
            evidence["workflow_sha256"],
            hashlib.sha256(workflow_bytes).hexdigest(),
        )
        self.assertEqual(
            evidence["source_facts_sha256"],
            source_facts_sha256(workflow_ir["source_facts"]),
        )

    def test_hashes_workflow_file_exact_bytes(self):
        with tempfile.TemporaryDirectory() as temp_root:
            workflow_path = Path(temp_root) / ".agentcanvas" / "workflow.ir.json"
            workflow_path.parent.mkdir()
            raw = b'{\n  "generated_at": "one",\n  "source_facts": {"facts": []}\n}\n'
            workflow_path.write_bytes(raw)

            evidence = build_workflow_evidence_from_path(
                workflow_path,
                workspace=temp_root,
            )

        self.assertEqual(evidence["workflow_sha256"], hashlib.sha256(raw).hexdigest())

    def test_source_facts_hash_is_stable_for_fact_order_and_dict_order(self):
        first = {
            "schema": "agentcanvas.source_facts.v1",
            "facts": [
                {"id": "fact:b", "kind": "route", "attributes": {"path": "/b", "method": "GET"}},
                {"kind": "route", "attributes": {"method": "POST", "path": "/a"}, "id": "fact:a"},
            ],
        }
        second = {
            "facts": [
                {"id": "fact:a", "attributes": {"path": "/a", "method": "POST"}, "kind": "route"},
                {"attributes": {"method": "GET", "path": "/b"}, "kind": "route", "id": "fact:b"},
            ],
            "schema": "agentcanvas.source_facts.v1",
        }

        self.assertEqual(source_facts_sha256(first), source_facts_sha256(second))

    def test_compare_reports_fresh_for_exact_match(self):
        evidence = {
            "git_head": "abc123",
            "workflow_generated_at": "2026-07-05T12:00:00Z",
            "workflow_sha256": "workflow",
            "source_facts_sha256": "facts",
        }

        result = compare_canvas_evidence(evidence, dict(evidence))

        self.assertEqual(result["status"], EVIDENCE_STATUS_FRESH)
        self.assertFalse(result["stale"])
        self.assertEqual(result["mismatched_fields"], [])

    def test_compare_reports_stale_for_hash_mismatch(self):
        result = compare_canvas_evidence(
            {
                "git_head": "abc123",
                "workflow_generated_at": "2026-07-05T12:00:00Z",
                "workflow_sha256": "old",
                "source_facts_sha256": "facts",
            },
            {
                "git_head": "abc123",
                "workflow_generated_at": "2026-07-05T12:00:00Z",
                "workflow_sha256": "new",
                "source_facts_sha256": "facts",
            },
        )

        self.assertEqual(result["status"], EVIDENCE_STATUS_STALE)
        self.assertTrue(result["stale"])
        self.assertEqual(result["mismatched_fields"], ["workflow_sha256"])

    def test_compare_reports_possibly_stale_when_evidence_is_incomplete(self):
        result = compare_canvas_evidence(
            {"workflow_sha256": "same"},
            {
                "git_head": "abc123",
                "workflow_generated_at": "2026-07-05T12:00:00Z",
                "workflow_sha256": "same",
                "source_facts_sha256": None,
            },
        )

        self.assertEqual(result["status"], EVIDENCE_STATUS_POSSIBLY_STALE)
        self.assertIsNone(result["stale"])
        self.assertEqual(
            result["unknown_fields"],
            ["git_head", "workflow_generated_at"],
        )

    def test_compare_canvas_document_with_current_workflow_file(self):
        with tempfile.TemporaryDirectory() as temp_root:
            workflow_path = Path(temp_root) / ".agentcanvas" / "workflow.ir.json"
            workflow_path.parent.mkdir()
            workflow_path.write_text(
                json.dumps(
                    {
                        "schema": "agentcanvas.workflow.v1",
                        "generated_at": "2026-07-05T12:00:00Z",
                        "source_facts": _source_facts(),
                    },
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            evidence = build_workflow_evidence_from_path(
                workflow_path,
                workspace=temp_root,
            )
            canvas_document = {"schema": "agentcanvas.canvas.v2", "evidence": evidence}

            result = compare_canvas_with_current_workflow_evidence(
                canvas_document,
                temp_root,
            )

        self.assertEqual(result["status"], EVIDENCE_STATUS_FRESH)


def _source_facts():
    return {
        "schema": "agentcanvas.source_facts.v1",
        "facts": [
            {
                "id": "fact:route",
                "kind": "route",
                "attributes": {"path": "/checkout", "method": "POST"},
            }
        ],
    }


if __name__ == "__main__":
    unittest.main()
