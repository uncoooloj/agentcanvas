import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.parse import urlparse

from agentcanvas.server import make_handler


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


class _FakeHandler:
    def __init__(self, handler_cls):
        self.handler_cls = handler_cls
        self.response = None
        self.body = {}

    def authorized(self, _parsed):
        return True

    def write_json(self, payload, status=200):
        self.response = {"status": status, "payload": payload}

    def read_json_body(self):
        return self.body

    def request_session_id(self, *args, **kwargs):
        return self.handler_cls.request_session_id(self, *args, **kwargs)

    def request_demo_mode(self, *args, **kwargs):
        return self.handler_cls.request_demo_mode(self, *args, **kwargs)


class ProgressTests(unittest.TestCase):
    maxDiff = None

    def _run_agentcanvas(self, *args, cwd):
        return subprocess.run(
            [sys.executable, "-m", "agentcanvas", *args],
            cwd=cwd,
            env=_agentcanvas_env(),
            text=True,
            capture_output=True,
            timeout=15,
        )

    def test_progress_command_writes_durable_progress_json(self):
        with tempfile.TemporaryDirectory() as temp_root:
            workspace = Path(temp_root) / "workspace"
            workspace.mkdir()

            completed = self._run_agentcanvas(
                "progress",
                str(workspace),
                "--stage",
                "mapping_flows",
                "--message",
                "Mapped checkout flows",
                "--current",
                "2",
                "--total",
                "5",
                cwd=temp_root,
            )

            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            stdout = json.loads(completed.stdout)
            self.assertTrue(stdout["ok"])
            progress = stdout["progress"]
            self.assertTrue(progress["exists"])
            self.assertTrue(progress["readable"])
            self.assertEqual("mapping_flows", progress["stage"])
            self.assertEqual(2, progress["current"])
            self.assertEqual(5, progress["total"])

            progress_path = workspace / ".agentcanvas" / "progress.json"
            self.assertTrue(progress_path.is_file())
            with progress_path.open(encoding="utf-8") as handle:
                durable = json.load(handle)
            self.assertEqual("agentcanvas.progress.v1", durable["schema"])
            self.assertEqual("Mapped checkout flows", durable["message"])
            self.assertRegex(durable["updated_at"], r"^\d{4}-\d{2}-\d{2}T")

    def test_progress_command_rejects_invalid_range_without_writing(self):
        with tempfile.TemporaryDirectory() as temp_root:
            workspace = Path(temp_root) / "workspace"
            workspace.mkdir()

            completed = self._run_agentcanvas(
                "progress",
                str(workspace),
                "--stage",
                "indexing",
                "--message",
                "Indexing files",
                "--current",
                "7",
                "--total",
                "3",
                cwd=temp_root,
            )

            self.assertEqual(completed.returncode, 1)
            payload = json.loads(completed.stderr)
            self.assertFalse(payload["ok"])
            self.assertEqual("INVALID_PROGRESS_RANGE", payload["error"]["code"])
            self.assertFalse((workspace / ".agentcanvas" / "progress.json").exists())

    def test_progress_command_rejects_invalid_stage_with_structured_error(self):
        with tempfile.TemporaryDirectory() as temp_root:
            workspace = Path(temp_root) / "workspace"
            workspace.mkdir()

            completed = self._run_agentcanvas(
                "progress",
                str(workspace),
                "--stage",
                "thinking",
                "--message",
                "Thinking about the map",
                cwd=temp_root,
            )

            self.assertEqual(completed.returncode, 1)
            payload = json.loads(completed.stderr)
            self.assertFalse(payload["ok"])
            self.assertEqual("INVALID_PROGRESS_STAGE", payload["error"]["code"])
            self.assertEqual(
                ["indexing", "surveying", "mapping_flows", "done"],
                payload["error"]["details"]["allowed"],
            )

    def test_progress_command_rejects_non_numeric_count_with_structured_error(self):
        with tempfile.TemporaryDirectory() as temp_root:
            workspace = Path(temp_root) / "workspace"
            workspace.mkdir()

            completed = self._run_agentcanvas(
                "progress",
                str(workspace),
                "--stage",
                "surveying",
                "--message",
                "Surveying routes",
                "--current",
                "many",
                cwd=temp_root,
            )

            self.assertEqual(completed.returncode, 1)
            payload = json.loads(completed.stderr)
            self.assertFalse(payload["ok"])
            self.assertEqual("INVALID_PROGRESS_COUNT", payload["error"]["code"])
            self.assertEqual("current", payload["error"]["details"]["field"])

    def test_progress_api_returns_missing_progress_shape(self):
        with tempfile.TemporaryDirectory() as temp_root:
            workspace = Path(temp_root) / "workspace"
            workspace.mkdir()
            handler_cls = make_handler(
                workspace,
                token="token",
                assistant_id="codex",
                assistant_name="Codex",
            )
            fake = _FakeHandler(handler_cls)

            handler_cls.handle_api_get(fake, urlparse("/api/progress?token=token"))

            self.assertEqual(fake.response["status"], 200)
            payload = fake.response["payload"]
            self.assertTrue(payload["ok"])
            progress = payload["progress"]
            self.assertFalse(progress["exists"])
            self.assertFalse(progress["readable"])
            self.assertIsNone(progress["progress"])
            self.assertEqual(".agentcanvas/progress.json", progress["relativePath"])
            self.assertIn("No progress", progress["notice"])

    def test_progress_api_writes_durable_progress(self):
        with tempfile.TemporaryDirectory() as temp_root:
            workspace = Path(temp_root) / "workspace"
            workspace.mkdir()
            handler_cls = make_handler(
                workspace,
                token="token",
                assistant_id="codex",
                assistant_name="Codex",
            )
            fake = _FakeHandler(handler_cls)
            fake.body = {
                "stage": "mapping_flows",
                "message": "Drafting checkout and returns",
                "current": 2,
                "total": 3,
            }

            handler_cls.handle_api_post(fake, urlparse("/api/progress?token=token"))

            self.assertEqual(fake.response["status"], 200)
            progress = fake.response["payload"]["progress"]
            self.assertTrue(progress["exists"])
            self.assertEqual("mapping_flows", progress["stage"])
            self.assertEqual("Drafting checkout and returns", progress["message"])
            self.assertEqual(2, progress["current"])
            durable_path = workspace / ".agentcanvas" / "progress.json"
            self.assertTrue(durable_path.is_file())

    def test_progress_api_rejects_invalid_progress(self):
        with tempfile.TemporaryDirectory() as temp_root:
            workspace = Path(temp_root) / "workspace"
            workspace.mkdir()
            handler_cls = make_handler(
                workspace,
                token="token",
                assistant_id="codex",
                assistant_name="Codex",
            )
            fake = _FakeHandler(handler_cls)
            fake.body = {"stage": "thinking", "message": "Thinking"}

            handler_cls.handle_api_post(fake, urlparse("/api/progress?token=token"))

            self.assertEqual(fake.response["status"], 400)
            self.assertFalse(fake.response["payload"]["ok"])
            self.assertEqual("INVALID_PROGRESS_STAGE", fake.response["payload"]["error"]["code"])
            self.assertFalse((workspace / ".agentcanvas" / "progress.json").exists())

    def test_progress_api_and_context_include_progress(self):
        with tempfile.TemporaryDirectory() as temp_root:
            workspace = Path(temp_root) / "workspace"
            state_dir = workspace / ".agentcanvas"
            state_dir.mkdir(parents=True)
            (state_dir / "canvas.ir.json").write_text(
                json.dumps({"schema": "agentcanvas.behavior_canvas_response.v1"}),
                encoding="utf-8",
            )
            (state_dir / "progress.json").write_text(
                json.dumps(
                    {
                        "schema": "agentcanvas.progress.v1",
                        "stage": "surveying",
                        "message": "Reviewing routes",
                        "current": 1,
                        "total": 4,
                        "updated_at": "2026-07-06T12:00:00Z",
                    }
                ),
                encoding="utf-8",
            )
            handler_cls = make_handler(
                workspace,
                token="token",
                assistant_id="codex",
                assistant_name="Codex",
            )
            fake = _FakeHandler(handler_cls)

            handler_cls.handle_api_get(fake, urlparse("/api/progress?token=token"))

            self.assertEqual(fake.response["status"], 200)
            progress = fake.response["payload"]["progress"]
            self.assertTrue(progress["exists"])
            self.assertTrue(progress["readable"])
            self.assertEqual("surveying", progress["stage"])
            self.assertEqual("Reviewing routes", progress["message"])
            self.assertEqual(1, progress["current"])
            self.assertEqual(4, progress["total"])

            handler_cls.handle_api_get(fake, urlparse("/api/context?token=token"))

            context_progress = fake.response["payload"]["context"]["progress"]
            self.assertTrue(context_progress["exists"])
            self.assertEqual("surveying", context_progress["stage"])
            self.assertEqual("2026-07-06T12:00:00Z", context_progress["updated_at"])


if __name__ == "__main__":
    unittest.main()
