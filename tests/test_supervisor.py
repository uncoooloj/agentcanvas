import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from agentcanvas.server import server_heartbeat_path, token_hint
from agentcanvas.supervisor import (
    api_url,
    heartbeat_is_fresh,
    launch_record_path,
    launch_url,
    prepend_pythonpath,
    pid_is_alive,
    stop_server,
    validate_loopback_host,
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

    def test_validate_launch_record_requires_fresh_matching_heartbeat_when_workspace_is_known(self):
        with tempfile.TemporaryDirectory() as temp_root:
            workspace = Path(temp_root) / "workspace"
            workspace.mkdir()
            record = {
                "pid": os.getpid(),
                "host": "127.0.0.1",
                "port": 8787,
                "token": "secret-token",
                "session_id": "session-1",
            }
            heartbeat = {
                "schema": "agentcanvas.server_heartbeat.v1",
                "pid": os.getpid(),
                "host": "127.0.0.1",
                "port": 8787,
                "workspace": str(workspace.resolve()),
                "updated_at": "2026-01-01T00:00:00Z",
                "last_seen": "2026-01-01T00:00:00Z",
                "token_hint": token_hint("secret-token"),
            }
            heartbeat_path = server_heartbeat_path(workspace)
            heartbeat_path.parent.mkdir(parents=True, exist_ok=True)
            heartbeat_path.write_text(json.dumps(heartbeat), encoding="utf-8")

            with patch("agentcanvas.supervisor.urllib.request.urlopen", return_value=_FakeResponse()):
                live = validate_launch_record(record, workspace=workspace)

            self.assertIsNotNone(live)
            heartbeat["token_hint"] = token_hint("wrong-token")
            heartbeat_path.write_text(json.dumps(heartbeat), encoding="utf-8")

            with patch("agentcanvas.supervisor.urllib.request.urlopen", return_value=_FakeResponse()):
                self.assertIsNone(validate_launch_record(record, workspace=workspace))

    def test_heartbeat_freshness_rejects_stale_files(self):
        with tempfile.TemporaryDirectory() as temp_root:
            workspace = Path(temp_root) / "workspace"
            workspace.mkdir()
            record = {
                "pid": os.getpid(),
                "host": "127.0.0.1",
                "port": 8787,
                "token": "secret-token",
            }
            heartbeat_path = server_heartbeat_path(workspace)
            heartbeat_path.parent.mkdir(parents=True, exist_ok=True)
            heartbeat_path.write_text(
                json.dumps(
                    {
                        "schema": "agentcanvas.server_heartbeat.v1",
                        "pid": os.getpid(),
                        "host": "127.0.0.1",
                        "port": 8787,
                        "workspace": str(workspace.resolve()),
                        "token_hint": token_hint("secret-token"),
                    }
                ),
                encoding="utf-8",
            )
            stale_time = time.time() - 120
            os.utime(heartbeat_path, (stale_time, stale_time))

            self.assertFalse(heartbeat_is_fresh(workspace, record, max_age_seconds=45))

    def test_validate_launch_record_rejects_dead_pid(self):
        record = {
            "pid": 99999999,
            "host": "127.0.0.1",
            "port": 8787,
            "token": "secret-token",
        }

        self.assertIsNone(validate_launch_record(record))

    def test_pid_is_alive_treats_windows_invalid_parameter_as_dead(self):
        error = OSError("invalid parameter")
        error.winerror = 87

        with patch("agentcanvas.supervisor.os.kill", side_effect=error):
            self.assertFalse(pid_is_alive(99999999))

    def test_validate_loopback_host_rejects_public_bind(self):
        validate_loopback_host("127.0.0.1")
        validate_loopback_host("localhost")
        with self.assertRaisesRegex(Exception, "loopback"):
            validate_loopback_host("0.0.0.0")

    def test_stop_server_keeps_launch_record_when_process_does_not_stop(self):
        with tempfile.TemporaryDirectory() as temp_root:
            workspace = Path(temp_root) / "workspace"
            workspace.mkdir()
            record = {
                "schema": "agentcanvas.launch.v1",
                "pid": os.getpid(),
                "host": "127.0.0.1",
                "port": 8765,
                "token": "secret-token",
                "url": launch_url("127.0.0.1", 8765, "secret-token"),
            }
            path = write_launch_record(workspace, record)

            with patch("agentcanvas.supervisor.terminate_pid", return_value=False):
                result = stop_server(workspace)

            self.assertFalse(result["ok"])
            self.assertFalse(result["stopped"])
            self.assertTrue(path.exists())

    def test_stop_server_removes_launch_record_and_heartbeat_when_stopped(self):
        with tempfile.TemporaryDirectory() as temp_root:
            workspace = Path(temp_root) / "workspace"
            workspace.mkdir()
            record = {
                "schema": "agentcanvas.launch.v1",
                "pid": os.getpid(),
                "host": "127.0.0.1",
                "port": 8765,
                "token": "secret-token",
                "url": launch_url("127.0.0.1", 8765, "secret-token"),
            }
            launch_path = write_launch_record(workspace, record)
            heartbeat_path = server_heartbeat_path(workspace)
            heartbeat_path.parent.mkdir(parents=True, exist_ok=True)
            heartbeat_path.write_text("{}", encoding="utf-8")

            with patch("agentcanvas.supervisor.terminate_pid", return_value=True):
                result = stop_server(workspace)

            self.assertTrue(result["ok"])
            self.assertTrue(result["stopped"])
            self.assertFalse(launch_path.exists())
            self.assertFalse(heartbeat_path.exists())

    def test_prepend_pythonpath_keeps_local_checkout_importable(self):
        self.assertEqual(prepend_pythonpath("/repo", None), "/repo")
        self.assertEqual(prepend_pythonpath("/repo", "/other"), "/repo" + os.pathsep + "/other")
        self.assertEqual(prepend_pythonpath("/repo", "/repo" + os.pathsep + "/other"), "/repo" + os.pathsep + "/other")


if __name__ == "__main__":
    unittest.main()
