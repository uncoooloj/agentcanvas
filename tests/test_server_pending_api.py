import io
import json
import tempfile
import unittest
from pathlib import Path
from urllib.parse import urlparse

from agentcanvas.ir import (
    ConversationRole,
    ConversationTurnKind,
    append_pending_conversation,
    update_pending_status,
    write_pending_change,
)
from agentcanvas.lifecycle import IN_PROGRESS, NEEDS_INPUT, VERIFIED
from agentcanvas.server import make_handler


class _FakeHandler:
    def __init__(self, handler_cls, payload=None):
        self.handler_cls = handler_cls
        self.response = None
        body = b"" if payload is None else json.dumps(payload).encode("utf-8")
        self.rfile = io.BytesIO(body)
        self.headers = {"Content-Length": str(len(body))}

    def authorized(self, _parsed):
        return True

    def write_json(self, payload, status=200):
        self.response = {"status": int(status), "payload": payload}

    def read_json_body(self):
        return self.handler_cls.read_json_body(self)

    def pending_request_id(self, path):
        return self.handler_cls.pending_request_id(self, path)

    def pending_answer_id(self, path):
        return self.handler_cls.pending_answer_id(self, path)

    def request_session_id(self, parsed, payload=None):
        return self.handler_cls.request_session_id(self, parsed, payload)


class ServerPendingApiTests(unittest.TestCase):
    maxDiff = None

    def _workspace(self, temp_root):
        workspace = Path(temp_root) / "workspace"
        workspace.mkdir()
        return workspace

    def _handler_cls(self, workspace):
        return make_handler(
            workspace,
            token="token",
            assistant_id="codex",
            assistant_name="Codex",
        )

    def test_pending_list_returns_bounded_summary_without_change_blob(self):
        with tempfile.TemporaryDirectory() as temp_root:
            workspace = self._workspace(temp_root)
            pending = write_pending_change(
                workspace,
                {
                    "changeId": "client-change-1",
                    "title": "Change checkout copy",
                    "summary": "Make the checkout empty state clearer.",
                    "journeyId": "flow:checkout",
                    "targetNodeId": "n:checkout:empty",
                },
                workflow_ir=None,
                session_id="session-1",
            )
            handler_cls = self._handler_cls(workspace)
            fake = _FakeHandler(handler_cls)

            handler_cls.handle_api_get(fake, urlparse("/api/pending?token=token"))

            self.assertEqual(fake.response["status"], 200)
            items = fake.response["payload"]["pending"]
            self.assertEqual(len(items), 1)
            summary = items[0]
            self.assertEqual(summary["id"], pending["id"])
            self.assertEqual(summary["changeId"], "client-change-1")
            self.assertEqual(summary["sessionId"], "session-1")
            self.assertEqual(summary["conversation_summary"]["turns"], 0)
            self.assertIn("refs", summary)
            self.assertIn("status_history", summary)
            self.assertNotIn("change", summary)
            self.assertNotIn("graph", summary)

            update_pending_status(workspace, pending["id"], "in_progress", note="Started work.")
            fake = _FakeHandler(handler_cls)
            handler_cls.handle_api_get(fake, urlparse("/api/pending?token=token"))
            updated = fake.response["payload"]["pending"][0]
            self.assertEqual(updated["status_history"][-1]["status"], "in_progress")
            self.assertEqual(updated["status_history"][-1]["note"], "Started work.")
            self.assertNotIn("change", updated)
            self.assertNotIn("graph", updated)

    def test_pending_detail_and_answer_route_use_conversation_jsonl(self):
        with tempfile.TemporaryDirectory() as temp_root:
            workspace = self._workspace(temp_root)
            pending = write_pending_change(
                workspace,
                {
                    "changeId": "client-change-2",
                    "title": "Change delivery message",
                    "summary": "Text the delivery date after checkout.",
                    "journeyId": "flow:checkout",
                    "targetNodeId": "n:checkout:text",
                },
                workflow_ir=None,
            )
            append_pending_conversation(
                workspace,
                pending["id"],
                role=ConversationRole.AGENT.value,
                kind=ConversationTurnKind.QUESTION.value,
                text="Should this text go to email too?",
                actor="codex",
            )
            handler_cls = self._handler_cls(workspace)
            detail = _FakeHandler(handler_cls)

            handler_cls.handle_api_get(detail, urlparse(f"/api/pending/{pending['id']}?token=token"))

            self.assertEqual(detail.response["status"], 200)
            detail_pending = detail.response["payload"]["pending"]
            self.assertIn("change", detail_pending)
            self.assertEqual(detail_pending["status"], NEEDS_INPUT)
            self.assertEqual(len(detail_pending["conversation"]), 1)
            self.assertEqual(
                detail_pending["conversation_summary"]["unanswered_question"]["text"],
                "Should this text go to email too?",
            )

            answer = _FakeHandler(handler_cls, {"answer": "SMS only for now.", "sessionId": "user-session"})
            handler_cls.handle_api_post(answer, urlparse(f"/api/pending/{pending['id']}/answer?token=token"))

            self.assertEqual(answer.response["status"], 200)
            answered = answer.response["payload"]["pending"]
            self.assertEqual(answered["status"], IN_PROGRESS)
            self.assertEqual(len(answered["conversation"]), 2)
            self.assertIsNone(answered["conversation_summary"]["unanswered_question"])
            conversation_path = workspace / ".agentcanvas" / "pending" / f"{pending['id']}.conversation.jsonl"
            self.assertTrue(conversation_path.is_file())
            self.assertEqual(len(conversation_path.read_text(encoding="utf-8").strip().splitlines()), 2)
            markdown = Path(answered["markdown_path"]).read_text(encoding="utf-8")
            self.assertIn("## Conversation", markdown)
            self.assertIn("SMS only for now.", markdown)

    def test_pending_routes_are_scoped_to_session_id(self):
        with tempfile.TemporaryDirectory() as temp_root:
            workspace = self._workspace(temp_root)
            first = write_pending_change(
                workspace,
                {
                    "changeId": "client-change-session-1",
                    "title": "Session one change",
                    "summary": "Change copy for session one.",
                },
                workflow_ir=None,
                session_id="session-1",
            )
            second = write_pending_change(
                workspace,
                {
                    "changeId": "client-change-session-2",
                    "title": "Session two change",
                    "summary": "Change copy for session two.",
                },
                workflow_ir=None,
                session_id="session-2",
            )
            handler_cls = self._handler_cls(workspace)

            listing = _FakeHandler(handler_cls)
            handler_cls.handle_api_get(listing, urlparse("/api/pending?token=token&sessionId=session-1"))

            self.assertEqual(listing.response["status"], 200)
            self.assertEqual([item["id"] for item in listing.response["payload"]["pending"]], [first["id"]])

            wrong_detail = _FakeHandler(handler_cls)
            handler_cls.handle_api_get(
                wrong_detail,
                urlparse(f"/api/pending/{second['id']}?token=token&sessionId=session-1"),
            )

            self.assertEqual(wrong_detail.response["status"], 404)

            wrong_status = _FakeHandler(
                handler_cls,
                {"id": second["id"], "status": IN_PROGRESS, "sessionId": "session-1"},
            )
            handler_cls.handle_api_post(wrong_status, urlparse("/api/status?token=token"))

            self.assertEqual(wrong_status.response["status"], 400)
            self.assertIn("not found for session", wrong_status.response["payload"]["error"])

    def test_status_route_marks_verified_with_evidence(self):
        with tempfile.TemporaryDirectory() as temp_root:
            workspace = self._workspace(temp_root)
            pending = write_pending_change(
                workspace,
                {
                    "changeId": "client-change-verified",
                    "title": "Verify delivery copy",
                    "summary": "Make sure the change was tested.",
                },
                workflow_ir=None,
                session_id="session-1",
            )
            handler_cls = self._handler_cls(workspace)
            evidence = {
                "actor": "codex",
                "at": "2026-06-19T00:00:00Z",
                "check": "python3.9 -m unittest tests.test_server_pending_api",
                "result": "passed",
            }
            fake = _FakeHandler(
                handler_cls,
                {
                    "id": pending["id"],
                    "status": VERIFIED,
                    "note": "Verified in the API test.",
                    "evidence": evidence,
                    "sessionId": "session-1",
                },
            )

            handler_cls.handle_api_post(fake, urlparse("/api/status?token=token"))

            self.assertEqual(fake.response["status"], 200)
            updated = fake.response["payload"]["pending"]
            self.assertEqual(updated["status"], VERIFIED)
            self.assertEqual(updated["verification"], evidence)
            self.assertEqual(updated["history"][-1]["evidence"], evidence)

    def test_status_route_rejects_verified_without_evidence(self):
        with tempfile.TemporaryDirectory() as temp_root:
            workspace = self._workspace(temp_root)
            pending = write_pending_change(
                workspace,
                {
                    "changeId": "client-change-no-evidence",
                    "title": "Verify without evidence",
                    "summary": "This should fail.",
                },
                workflow_ir=None,
            )
            handler_cls = self._handler_cls(workspace)
            fake = _FakeHandler(handler_cls, {"id": pending["id"], "status": VERIFIED})

            handler_cls.handle_api_post(fake, urlparse("/api/status?token=token"))

            self.assertEqual(fake.response["status"], 400)
            self.assertIn("verified status requires evidence", fake.response["payload"]["error"])


if __name__ == "__main__":
    unittest.main()
