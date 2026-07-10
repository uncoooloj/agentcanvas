import json
import tempfile
import unittest
from pathlib import Path

from agentcanvas.ir import append_pending_conversation, update_pending_status, write_pending_change
from agentcanvas.lifecycle import (
    LifecycleError,
    PENDING,
    PENDING_STATUSES,
    PendingStatus,
    REF_PROTECTING,
    TERMINAL,
    allowed_next_statuses,
    is_ref_protecting,
    transition_record,
    validate_status,
)


class LifecycleTests(unittest.TestCase):
    maxDiff = None

    def test_phase1_status_categories_match_ref_protection_contract(self):
        self.assertEqual(
            REF_PROTECTING,
            {"pending", "sent", "in_progress", "implemented", "needs_input", "blocked"},
        )
        self.assertEqual(TERMINAL, {"verified", "done", "cancelled", "rejected"})
        self.assertTrue(is_ref_protecting("implemented"))
        self.assertTrue(is_ref_protecting("blocked"))
        self.assertFalse(is_ref_protecting("verified"))
        self.assertFalse(is_ref_protecting("cancelled"))

    def test_pending_status_enum_derives_string_exports(self):
        self.assertEqual(PendingStatus.PENDING.value, "pending")
        self.assertEqual(PendingStatus.VERIFIED.value, "verified")
        self.assertEqual({status.value for status in PendingStatus}, PENDING_STATUSES)
        self.assertIs(type(PENDING), str)
        self.assertTrue(all(type(status) is str for status in PENDING_STATUSES))
        self.assertEqual(validate_status(PendingStatus.IMPLEMENTED), "implemented")

    def test_transition_table_returns_allowed_next_states(self):
        self.assertEqual(
            allowed_next_statuses("implemented"),
            {"in_progress", "verified", "blocked", "cancelled", "rejected"},
        )
        blocked_record = {"status": "blocked", "blocked_from": "in_progress"}
        self.assertEqual(allowed_next_statuses("blocked", blocked_record), {"in_progress", "cancelled", "rejected"})
        self.assertEqual(
            allowed_next_statuses(PendingStatus.IMPLEMENTED),
            {"in_progress", "verified", "blocked", "cancelled", "rejected"},
        )

    def test_illegal_transition_reports_allowed_states(self):
        with self.assertRaises(LifecycleError) as raised:
            transition_record(
                {"status": "pending"},
                "verified",
                at="2026-07-06T00:00:00Z",
                enforce_transitions=True,
            )

        self.assertEqual(raised.exception.status, "verified")
        self.assertEqual(raised.exception.allowed, {"sent", "needs_input", "blocked", "cancelled", "rejected"})

    def test_verified_requires_evidence(self):
        with self.assertRaises(LifecycleError):
            transition_record(
                {"status": "implemented"},
                "verified",
                at="2026-07-06T00:00:00Z",
            )

        updated = transition_record(
            {"status": "implemented"},
            "verified",
            at="2026-07-06T00:00:00Z",
            evidence={"actor": "codex", "at": "2026-07-06T00:00:00Z", "check": "unit tests", "result": "passed"},
        )
        self.assertEqual(updated["status"], "verified")
        self.assertEqual(updated["verification"]["check"], "unit tests")
        self.assertEqual(updated["history"][-1]["to"], "verified")

    def test_transition_record_accepts_enum_but_returns_strings(self):
        updated = transition_record(
            {"status": PendingStatus.IMPLEMENTED},
            PendingStatus.VERIFIED,
            at="2026-07-06T00:00:00Z",
            evidence={"actor": "codex", "at": "2026-07-06T00:00:00Z", "check": "unit tests", "result": "passed"},
        )

        self.assertEqual(updated["status"], "verified")
        self.assertIs(type(updated["status"]), str)
        self.assertEqual(updated["history"][-1]["from"], "implemented")
        self.assertEqual(updated["history"][-1]["to"], "verified")
        self.assertEqual(updated["status_history"][-1]["status"], "verified")

    def test_update_pending_status_writes_history_and_requires_verified_evidence(self):
        with tempfile.TemporaryDirectory() as temp_root:
            workspace = Path(temp_root) / "workspace"
            pending_dir = workspace / ".agentcanvas" / "pending"
            pending_dir.mkdir(parents=True)
            pending_path = pending_dir / "change.json"
            pending_path.write_text(
                json.dumps({"id": "change", "title": "Change", "status": "implemented", "change": {}}),
                encoding="utf-8",
            )

            with self.assertRaises(LifecycleError):
                update_pending_status(workspace, "change", "verified")

            updated = update_pending_status(
                workspace,
                "change",
                "verified",
                evidence={
                    "actor": "codex",
                    "at": "2026-07-06T00:00:00Z",
                    "check": "release verifier",
                    "result": "passed",
                },
            )

            self.assertEqual(updated["status"], "verified")
            self.assertEqual(updated["history"][-1]["to"], "verified")
            self.assertEqual(updated["status_history"][-1]["status"], "verified")

    def test_answer_must_follow_question_and_does_not_write_on_failure(self):
        with tempfile.TemporaryDirectory() as temp_root:
            workspace = Path(temp_root) / "workspace"
            pending = write_pending_change(workspace, {"title": "Answer", "summary": "Answer"})

            with self.assertRaises(ValueError):
                append_pending_conversation(
                    workspace,
                    pending["id"],
                    role="user",
                    kind="answer",
                    text="Too early",
                )

            conversation_path = Path(pending["json_path"]).with_suffix(".conversation.jsonl")
            self.assertFalse(conversation_path.exists())


if __name__ == "__main__":
    unittest.main()
