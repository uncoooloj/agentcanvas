import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agentcanvas.supervisor import (
    api_url,
    launch_record_path,
    launch_url,
    prepend_pythonpath,
    validate_launch_record,
    write_launch_record,
)


class _FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps({"ok": True, "health": {"status": "ready"}}).encode("utf-8")


class SupervisorTests(unittest.TestCase):
    def test_launch_record_is_owner_only_and_contains_recoverable_url(self):
        with tempfile.TemporaryDirectory() as temp_root:
            workspace = Path(temp_root) / "workspace"
            workspace.mkdir()
            record = {
                "schema": "agentcanvas.launch.v1",
                "pid": os.getpid(),
                "host": "127.0.0.1",
                "port": 8765,
                "token": "secret-token",
                "url": launch_url("127.0.0.1", 8765, "secret-token", session_id="session-1"),
                "session_id": "session-1",
                "version": "test",
            }

            path = write_launch_record(workspace, record)

            self.assertEqual(path, launch_record_path(workspace))
            written = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(written["token"], "secret-token")
            self.assertIn("sessionId=session-1", written["url"])
            if os.name != "nt":
                self.assertEqual(oct(path.stat().st_mode & 0o777), "0o600")

    def test_validate_launch_record_checks_pid_and_health_with_token(self):
        record = {
            "pid": os.getpid(),
            "host": "127.0.0.1",
            "port": 8787,
            "token": "secret-token",
            "session_id": "session-1",
        }
        expected_url = api_url("127.0.0.1", 8787, "/api/health", "secret-token", session_id="session-1")

        with patch("agentcanvas.supervisor.urllib.request.urlopen", return_value=_FakeResponse()) as urlopen:
            live = validate_launch_record(record)

        self.assertIsNotNone(live)
        self.assertEqual(live["url"], launch_url("127.0.0.1", 8787, "secret-token", session_id="session-1"))
        urlopen.assert_called_once()
        self.assertEqual(urlopen.call_args.args[0], expected_url)

    def test_validate_launch_record_rejects_dead_pid(self):
        record = {
            "pid": 99999999,
            "host": "127.0.0.1",
            "port": 8787,
            "token": "secret-token",
        }

        self.assertIsNone(validate_launch_record(record))

    def test_prepend_pythonpath_keeps_local_checkout_importable(self):
        self.assertEqual(prepend_pythonpath("/repo", None), "/repo")
        self.assertEqual(prepend_pythonpath("/repo", "/other"), "/repo" + os.pathsep + "/other")
        self.assertEqual(prepend_pythonpath("/repo", "/repo" + os.pathsep + "/other"), "/repo" + os.pathsep + "/other")


if __name__ == "__main__":
    unittest.main()
