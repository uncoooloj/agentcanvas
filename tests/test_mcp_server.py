import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from agentcanvas.ir import (
    ConversationRole,
    ConversationTurnKind,
    append_pending_conversation,
    save_ir,
    write_pending_change,
)
from agentcanvas.lifecycle import (
    IN_PROGRESS,
    NEEDS_INPUT,
    SENT,
)
from agentcanvas.mcp_server import (
    DEFAULT_EVIDENCE_MAX_BYTES,
    DEFAULT_EVIDENCE_MAX_ITEMS,
    apply_canvas,
    ask_user,
    get_answers,
    get_canvas,
    get_evidence,
    get_request,
    get_workspace_status,
    list_requests,
    record_sync,
    update_request,
    validate_canvas,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _agentcanvas_env():
    env = os.environ.copy()
    pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        str(PROJECT_ROOT)
        if not pythonpath
        else str(PROJECT_ROOT) + os.pathsep + pythonpath
    )
    return env


class McpServerContractTests(unittest.TestCase):
    maxDiff = None

    def test_mcp_evidence_defaults_match_phase_1_contract(self):
        self.assertEqual(DEFAULT_EVIDENCE_MAX_ITEMS, 100)
        self.assertEqual(DEFAULT_EVIDENCE_MAX_BYTES, 48 * 1024)

    def _workspace(self, temp_root):
        workspace = Path(temp_root) / "workspace"
        workspace.mkdir()
        return workspace

    def _workflow_ir(self):
        return {
            "schema": "agentcanvas.workflow.v1",
            "generated_at": "2026-07-06T00:00:00Z",
            "summary": {"language_facts": 2},
            "source_facts": {
                "facts": [
                    {
                        "id": "route:checkout",
                        "kind": "route",
                        "path": "src/routes/checkout.js",
                        "line": 12,
                        "title": "Checkout route",
                    },
                    {
                        "id": "action:submit-order",
                        "kind": "action",
                        "path": "src/actions/submit-order.js",
                        "line": 7,
                        "title": "Submit an order",
                    },
                ],
            },
            "nodes": [
                {
                    "id": "node:checkout",
                    "path": "src/routes/checkout.js",
                    "line": 12,
                    "label": "Checkout screen",
                }
            ],
        }

    def _initial_operations(self):
        return [
            {
                "op": "set_app",
                "app": {
                    "name": "Shop",
                    "summary": "People check out.",
                    "is_demo": False,
                },
            },
            {
                "op": "upsert_flow",
                "flow": {
                    "id": "flow:checkout",
                    "title": "Checkout",
                    "summary": "How an order gets placed.",
                    "entry_node": "n:checkout:start",
                },
            },
            {
                "op": "upsert_node",
                "flow": "flow:checkout",
                "node": {
                    "id": "n:checkout:start",
                    "kind": "When",
                    "title": "Someone starts checkout",
                    "evidence_refs": ["route:checkout"],
                },
            },
            {
                "op": "upsert_node",
                "flow": "flow:checkout",
                "node": {
                    "id": "n:checkout:submit",
                    "kind": "Do",
                    "title": "Submit the order",
                    "evidence_refs": ["action:submit-order"],
                },
            },
            {
                "op": "upsert_edge",
                "flow": "flow:checkout",
                "edge": {
                    "id": "e:checkout:start:submit",
                    "kind": "normal",
                    "source": "n:checkout:start",
                    "target": "n:checkout:submit",
                },
            },
        ]

    def test_mcp_cli_without_optional_sdk_has_clear_failure_contract(self):
        with tempfile.TemporaryDirectory() as temp_root:
            workspace = self._workspace(temp_root)

            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agentcanvas",
                    "mcp",
                    "--workspace",
                    str(workspace),
                ],
                cwd=temp_root,
                env=_agentcanvas_env(),
                text=True,
                capture_output=True,
                timeout=15,
            )

            self.assertEqual(completed.returncode, 3, completed.stdout + completed.stderr)
            self.assertEqual(completed.stdout, "")
            self.assertIn("use-agentcanvas[mcp]", completed.stderr)
            self.assertIn("agentcanvas mcp", completed.stderr)

    def test_mcp_handlers_apply_canvas_report_status_and_page_evidence(self):
        with tempfile.TemporaryDirectory() as temp_root:
            workspace = self._workspace(temp_root)
            save_ir(workspace, self._workflow_ir())

            result = apply_canvas(
                self._initial_operations(),
                0,
                workspace=str(workspace),
                authored_by="mcp-test",
            )
            self.assertEqual(result["revision"], 1)

            status = get_workspace_status(str(workspace))
            self.assertTrue(status["ok"])
            self.assertEqual(status["canvas"]["revision"], 1)
            self.assertEqual(status["canvas"]["flow_count"], 1)
            self.assertEqual(status["pending"]["count"], 0)
            self.assertEqual(status["canvas"]["evidence"]["status"], "fresh")

            canvas = get_canvas(str(workspace), flow_id="flow:checkout")
            self.assertEqual(canvas["revision"], 1)
            self.assertEqual(canvas["canvas_v2"]["flows"][0]["id"], "flow:checkout")
            self.assertEqual(canvas["validation"]["warnings"], [])

            validation = validate_canvas(workspace=str(workspace), mode="strict")
            self.assertTrue(validation["ok"])

            evidence = get_evidence(str(workspace), max_items=1)
            self.assertTrue(evidence["ok"])
            self.assertEqual(len(evidence["items"]), 1)
            self.assertIsNotNone(evidence["next_cursor"])

            filtered = get_evidence(str(workspace), query="submit")
            self.assertTrue(filtered["ok"])
            self.assertEqual(len(filtered["items"]), 1)
            self.assertIn("submit-order.js", json.dumps(filtered["items"][0]))

            sync = record_sync(str(workspace), git_head="abc123")
            self.assertEqual(sync["evidence"]["git_head"], "abc123")
            self.assertIn("workflow_sha256", sync["evidence"])

    def test_mcp_pending_lifecycle_questions_and_answers(self):
        with tempfile.TemporaryDirectory() as temp_root:
            workspace = self._workspace(temp_root)
            pending = write_pending_change(
                workspace,
                {
                    "changeId": "change-1",
                    "title": "Make checkout clearer",
                    "summary": "Clarify the checkout submit step.",
                    "journeyId": "flow:checkout",
                    "targetNodeId": "n:checkout:submit",
                },
                session_id="session-1",
            )

            listed = list_requests(str(workspace), session_id="session-1")
            self.assertEqual(listed["count"], 1)
            self.assertEqual(listed["requests"][0]["id"], pending["id"])
            self.assertNotIn("change", listed["requests"][0])

            sent = update_request(
                pending["id"],
                SENT,
                workspace=str(workspace),
                note="Sent to the current agent.",
            )
            self.assertEqual(sent["request"]["status"], SENT)
            in_progress = update_request(pending["id"], IN_PROGRESS, workspace=str(workspace))
            self.assertEqual(in_progress["request"]["status"], IN_PROGRESS)

            asked = ask_user(
                pending["id"],
                "Should this change affect email receipts too?",
                workspace=str(workspace),
            )
            self.assertEqual(asked["request"]["status"], NEEDS_INPUT)
            self.assertEqual(asked["request"]["conversation"][-1]["kind"], "question")

            detail = get_request(pending["id"], workspace=str(workspace))
            self.assertEqual(detail["request"]["conversation_summary"]["turns"], 1)

            append_pending_conversation(
                workspace,
                pending["id"],
                role=ConversationRole.USER.value,
                kind=ConversationTurnKind.ANSWER.value,
                text="Checkout screen only.",
                actor="test-user",
            )

            answers = get_answers(pending["id"], workspace=str(workspace))
            self.assertEqual(len(answers["answers"]), 1)
            self.assertEqual(answers["answers"][0]["text"], "Checkout screen only.")
            self.assertEqual(answers["answers"][0]["request_id"], pending["id"])


if __name__ == "__main__":
    unittest.main()
