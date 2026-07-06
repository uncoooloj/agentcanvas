import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from urllib.parse import urlparse

from agentcanvas.server import (
    build_server_heartbeat,
    make_handler,
    server_heartbeat_enabled,
    token_hint,
    write_server_heartbeat,
)


def _read_json(path: Path):
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


class _FakePostHandler:
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


class _FakeGetHandler:
    def __init__(self, handler_cls):
        self.handler_cls = handler_cls
        self.response = None

    def authorized(self, _parsed):
        return True

    def write_json(self, payload, status=200):
        self.response = {"status": int(status), "payload": payload}


class ServerCanvasV2ApiTests(unittest.TestCase):
    maxDiff = None

    def _workspace(self, temp_root):
        workspace = Path(temp_root) / "workspace"
        workspace.mkdir()
        return workspace

    def _initial_batch(self):
        return {
            "base_revision": 0,
            "authored_by": "server-test",
            "operations": [
                {
                    "op": "set_app",
                    "app": {
                        "name": "Photo Share",
                        "summary": "People upload and share photos.",
                        "is_demo": False,
                    },
                },
                {
                    "op": "upsert_flow",
                    "flow": {
                        "id": "flow:upload",
                        "title": "Upload photo",
                        "summary": "How a photo gets uploaded.",
                        "entry_node": "n:upload:start",
                    },
                },
                {
                    "op": "upsert_node",
                    "flow": "flow:upload",
                    "node": {
                        "id": "n:upload:start",
                        "kind": "When",
                        "title": "Choose a photo",
                    },
                },
            ],
        }

    def test_canvas_apply_accepts_v2_operation_batch(self):
        with tempfile.TemporaryDirectory() as temp_root:
            workspace = self._workspace(temp_root)
            handler_cls = make_handler(
                workspace,
                token="token",
                assistant_id="codex",
                assistant_name="Codex",
            )
            fake = _FakePostHandler(handler_cls, self._initial_batch())

            handler_cls.handle_api_post(fake, urlparse("/api/canvas/apply?token=token"))

            self.assertEqual(fake.response["status"], 200)
            payload = fake.response["payload"]
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["base_revision"], 0)
            self.assertEqual(payload["revision"], 1)
            canvas = _read_json(workspace / ".agentcanvas" / "canvas.ir.json")
            self.assertEqual(canvas["revision"], 1)
            self.assertEqual(canvas["authored_by"], "server-test")
            self.assertEqual(canvas["app"]["name"], "Photo Share")

    def test_canvas_apply_defaults_author_to_assistant(self):
        with tempfile.TemporaryDirectory() as temp_root:
            workspace = self._workspace(temp_root)
            batch = self._initial_batch()
            batch.pop("authored_by")
            handler_cls = make_handler(
                workspace,
                token="token",
                assistant_id="codex",
                assistant_name="Codex",
            )
            fake = _FakePostHandler(handler_cls, batch)

            handler_cls.handle_api_post(fake, urlparse("/api/canvas/apply?token=token"))

            self.assertEqual(fake.response["status"], 200)
            canvas = _read_json(workspace / ".agentcanvas" / "canvas.ir.json")
            self.assertEqual(canvas["authored_by"], "codex")

    def test_canvas_apply_returns_revision_conflict_envelope(self):
        with tempfile.TemporaryDirectory() as temp_root:
            workspace = self._workspace(temp_root)
            handler_cls = make_handler(
                workspace,
                token="token",
                assistant_id="codex",
                assistant_name="Codex",
            )
            handler_cls.handle_api_post(
                _FakePostHandler(handler_cls, self._initial_batch()),
                urlparse("/api/canvas/apply?token=token"),
            )
            stale = self._initial_batch()

            fake = _FakePostHandler(handler_cls, stale)
            handler_cls.handle_api_post(fake, urlparse("/api/canvas/apply?token=token"))

            self.assertEqual(fake.response["status"], 409)
            payload = fake.response["payload"]
            self.assertFalse(payload["ok"])
            self.assertEqual(payload["error"]["code"], "REVISION_CONFLICT")
            self.assertEqual(payload["revision"], 1)
            self.assertEqual(
                payload["error"]["details"]["changed_since"]["flow_ids"],
                ["flow:upload"],
            )

    def test_canvas_history_lists_store_snapshots(self):
        with tempfile.TemporaryDirectory() as temp_root:
            workspace = self._workspace(temp_root)
            handler_cls = make_handler(
                workspace,
                token="token",
                assistant_id="codex",
                assistant_name="Codex",
            )
            handler_cls.handle_api_post(
                _FakePostHandler(handler_cls, self._initial_batch()),
                urlparse("/api/canvas/apply?token=token"),
            )
            handler_cls.handle_api_post(
                _FakePostHandler(
                    handler_cls,
                    {
                        "base_revision": 1,
                        "operations": [
                            {
                                "op": "set_app",
                                "app": {"name": "Photo Share 2"},
                            }
                        ],
                    },
                ),
                urlparse("/api/canvas/apply?token=token"),
            )
            fake = _FakeGetHandler(handler_cls)

            handler_cls.handle_api_get(fake, urlparse("/api/canvas/history?token=token"))

            self.assertEqual(fake.response["status"], 200)
            payload = fake.response["payload"]
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["current_revision"], 2)
            self.assertEqual(
                [entry["revision"] for entry in payload["history"]],
                [1, 0],
            )

    def test_canvas_validate_returns_authoring_warnings(self):
        with tempfile.TemporaryDirectory() as temp_root:
            workspace = self._workspace(temp_root)
            handler_cls = make_handler(
                workspace,
                token="token",
                assistant_id="codex",
                assistant_name="Codex",
            )
            handler_cls.handle_api_post(
                _FakePostHandler(handler_cls, self._initial_batch()),
                urlparse("/api/canvas/apply?token=token"),
            )
            fake = _FakeGetHandler(handler_cls)

            handler_cls.handle_api_get(fake, urlparse("/api/canvas/validate?token=token&mode=authoring"))

            self.assertEqual(fake.response["status"], 200)
            payload = fake.response["payload"]
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["mode"], "authoring")
            self.assertEqual(payload["revision"], 1)
            self.assertEqual(payload["flow_count"], 1)
            warning_codes = {warning["code"] for warning in payload["warnings"]}
            self.assertIn("EVIDENCE_REFS_MISSING", warning_codes)

    def test_canvas_validate_returns_strict_error_envelope(self):
        with tempfile.TemporaryDirectory() as temp_root:
            workspace = self._workspace(temp_root)
            handler_cls = make_handler(
                workspace,
                token="token",
                assistant_id="codex",
                assistant_name="Codex",
            )
            handler_cls.handle_api_post(
                _FakePostHandler(handler_cls, self._initial_batch()),
                urlparse("/api/canvas/apply?token=token"),
            )
            handler_cls.handle_api_post(
                _FakePostHandler(
                    handler_cls,
                    {
                        "base_revision": 1,
                        "operations": [
                            {
                                "op": "upsert_node",
                                "flow": "flow:upload",
                                "node": {
                                    "id": "n:upload:orphan",
                                    "kind": "Do",
                                    "title": "Unreachable work",
                                },
                            }
                        ],
                    },
                ),
                urlparse("/api/canvas/apply?token=token"),
            )
            fake = _FakeGetHandler(handler_cls)

            handler_cls.handle_api_get(fake, urlparse("/api/canvas/validate?token=token&mode=strict"))

            self.assertEqual(fake.response["status"], 400)
            payload = fake.response["payload"]
            self.assertFalse(payload["ok"])
            self.assertEqual(payload["error"]["code"], "UNREACHABLE_NODE")
            self.assertIn("repair_hint", payload["error"])

    def test_canvas_restore_restores_snapshot_as_new_revision(self):
        with tempfile.TemporaryDirectory() as temp_root:
            workspace = self._workspace(temp_root)
            handler_cls = make_handler(
                workspace,
                token="token",
                assistant_id="codex",
                assistant_name="Codex",
            )
            handler_cls.handle_api_post(
                _FakePostHandler(handler_cls, self._initial_batch()),
                urlparse("/api/canvas/apply?token=token"),
            )
            handler_cls.handle_api_post(
                _FakePostHandler(
                    handler_cls,
                    {
                        "base_revision": 1,
                        "operations": [
                            {
                                "op": "set_app",
                                "app": {"name": "Photo Share 2"},
                            }
                        ],
                    },
                ),
                urlparse("/api/canvas/apply?token=token"),
            )
            fake = _FakePostHandler(
                handler_cls,
                {"revision": 1, "base_revision": 2, "authored_by": "server-restore-test"},
            )

            handler_cls.handle_api_post(fake, urlparse("/api/canvas/restore?token=token"))

            self.assertEqual(fake.response["status"], 200)
            payload = fake.response["payload"]
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["revision"], 3)
            self.assertEqual(payload["restored_revision"], 1)
            canvas = _read_json(workspace / ".agentcanvas" / "canvas.ir.json")
            self.assertEqual(canvas["revision"], 3)
            self.assertEqual(canvas["app"]["name"], "Photo Share")
            self.assertEqual(canvas["authored_by"], "server-restore-test")

    def test_server_heartbeat_writes_real_workspace_metadata_without_token_leak(self):
        with tempfile.TemporaryDirectory() as temp_root:
            workspace = self._workspace(temp_root)
            path = write_server_heartbeat(
                workspace,
                host="127.0.0.1",
                port=8765,
                token="super-secret-token",
                session_id="session-1",
                agent="codex",
                agent_name="Codex",
            )

            self.assertEqual(
                path,
                workspace.resolve() / ".agentcanvas" / "server.heartbeat.json",
            )
            payload = _read_json(path)
            self.assertEqual(payload["schema"], "agentcanvas.server_heartbeat.v1")
            self.assertEqual(payload["pid"], os.getpid())
            self.assertEqual(payload["host"], "127.0.0.1")
            self.assertEqual(payload["port"], 8765)
            self.assertEqual(payload["workspace"], str(workspace.resolve()))
            self.assertEqual(payload["session_id"], "session-1")
            self.assertEqual(payload["agent"], "codex")
            self.assertEqual(payload["agent_name"], "Codex")
            self.assertEqual(payload["updated_at"], payload["last_seen"])
            self.assertEqual(payload["token_hint"], token_hint("super-secret-token"))
            self.assertNotIn("super-secret-token", json.dumps(payload))

    def test_heartbeat_is_not_enabled_for_landing_or_demo_modes(self):
        self.assertTrue(server_heartbeat_enabled(demo_mode=False, landing_mode=False))
        self.assertFalse(server_heartbeat_enabled(demo_mode=True, landing_mode=False))
        self.assertFalse(server_heartbeat_enabled(demo_mode=False, landing_mode=True))

    def test_build_server_heartbeat_omits_optional_fields_when_unavailable(self):
        with tempfile.TemporaryDirectory() as temp_root:
            workspace = self._workspace(temp_root)

            payload = build_server_heartbeat(
                workspace,
                host="127.0.0.1",
                port=8765,
                token="secret",
            )

            self.assertNotIn("session_id", payload)
            self.assertNotIn("agent", payload)
            self.assertNotIn("agent_name", payload)


if __name__ == "__main__":
    unittest.main()
