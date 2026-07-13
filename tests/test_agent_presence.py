import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from agentcanvas.agent_presence import (
    AGENT_PRESENCE_SCHEMA,
    AgentPresenceState,
    agent_presence_path,
    agent_presence_status,
    record_agent_presence,
)


class AgentPresenceTests(unittest.TestCase):
    def test_presence_is_fresh_only_for_the_matching_session(self):
        with tempfile.TemporaryDirectory() as temp_root:
            workspace = Path(temp_root) / "workspace"
            workspace.mkdir()

            record_agent_presence(
                workspace,
                agent="codex",
                agent_name="Codex",
                session_id="session-123",
            )

            matching = agent_presence_status(workspace, session_id="session-123")
            mismatched = agent_presence_status(workspace, session_id="another-session")

            self.assertTrue(matching["connected"])
            self.assertEqual(AgentPresenceState.CONNECTED.value, matching["state"])
            self.assertFalse(mismatched["connected"])
            self.assertEqual(AgentPresenceState.SESSION_MISMATCH.value, mismatched["state"])

    def test_presence_expires_without_a_fresh_heartbeat(self):
        with tempfile.TemporaryDirectory() as temp_root:
            workspace = Path(temp_root) / "workspace"
            workspace.mkdir()
            path = agent_presence_path(workspace)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(
                    {
                        "schema": AGENT_PRESENCE_SCHEMA,
                        "agent": "codex",
                        "updated_at": "2026-07-11T00:00:00Z",
                    }
                ),
                encoding="utf-8",
            )

            status = agent_presence_status(
                workspace,
                fresh_seconds=60,
                now=datetime(2026, 7, 11, tzinfo=timezone.utc) + timedelta(seconds=61),
            )

            self.assertFalse(status["connected"])
            self.assertEqual(AgentPresenceState.STALE.value, status["state"])
