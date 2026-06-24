import json
import tempfile
import unittest
from pathlib import Path
from urllib.parse import urlparse

from agentcanvas.server import make_handler


def _write(root: Path, relative_path: str, content: str) -> None:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class _FakeHandler:
    def __init__(self, handler_cls):
        self.handler_cls = handler_cls
        self.response = None

    def authorized(self, _parsed):
        return True

    def write_json(self, payload, status=200):
        self.response = {"status": status, "payload": payload}

    def request_session_id(self, *args, **kwargs):
        return self.handler_cls.request_session_id(self, *args, **kwargs)

    def request_demo_mode(self, *args, **kwargs):
        return self.handler_cls.request_demo_mode(self, *args, **kwargs)


class ServerContextTests(unittest.TestCase):
    def test_demo_context_uses_workspace_name(self):
        with tempfile.TemporaryDirectory() as temp_root:
            workspace = Path(temp_root) / "agentcanvas-demo"
            workspace.mkdir()
            handler_cls = make_handler(
                workspace,
                token="token",
                assistant_id="generic",
                assistant_name="No agent connected",
                demo_mode=True,
                session_id="agent-session-1",
            )
            fake = _FakeHandler(handler_cls)

            handler_cls.handle_api_get(fake, urlparse("/api/context?token=token"))

            self.assertEqual(fake.response["status"], 200)
            context = fake.response["payload"]["context"]
            self.assertEqual(context["mode"], "demo")
            self.assertTrue(context["isDemo"])
            self.assertEqual(context["demoFixture"], "agentcanvas-demo")
            self.assertEqual(context["assistant"], "No agent connected")
            self.assertEqual(context["sessionId"], "agent-session-1")

    def test_landing_context_is_not_demo_until_requested(self):
        with tempfile.TemporaryDirectory() as temp_root:
            workspace = Path(temp_root) / "agentcanvas-demo"
            workspace.mkdir()
            handler_cls = make_handler(
                workspace,
                token="token",
                assistant_id="generic",
                assistant_name="No agent connected",
                landing_mode=True,
            )
            fake = _FakeHandler(handler_cls)

            handler_cls.handle_api_get(fake, urlparse("/api/context?token=token"))

            context = fake.response["payload"]["context"]
            self.assertEqual(context["mode"], "landing")
            self.assertFalse(context["isDemo"])
            self.assertIsNone(context["demoFixture"])
            self.assertEqual(context["workspacePath"], "")

            handler_cls.handle_api_get(fake, urlparse("/api/context?token=token&demo=1"))

            context = fake.response["payload"]["context"]
            self.assertEqual(context["mode"], "demo")
            self.assertTrue(context["isDemo"])
            self.assertEqual(context["demoFixture"], "agentcanvas-demo")
            self.assertEqual(context["workspacePath"], str(workspace))

    def test_query_session_id_overrides_server_session_id(self):
        with tempfile.TemporaryDirectory() as temp_root:
            workspace = Path(temp_root) / "workspace"
            workspace.mkdir()
            handler_cls = make_handler(
                workspace,
                token="token",
                assistant_id="codex",
                assistant_name="Codex",
                session_id="server-session",
            )
            fake = _FakeHandler(handler_cls)

            handler_cls.handle_api_get(
                fake,
                urlparse("/api/context?token=token&sessionId=query-session"),
            )

            context = fake.response["payload"]["context"]
            self.assertEqual(context["mode"], "workspace")
            self.assertFalse(context["isDemo"])
            self.assertIsNone(context["demoFixture"])
            self.assertEqual(context["workspacePath"], str(workspace))
            self.assertEqual(context["sessionId"], "query-session")

    def test_context_includes_learning_program_workspace_profile(self):
        with tempfile.TemporaryDirectory() as temp_root:
            workspace = Path(temp_root) / "robotics-adventure"
            workspace.mkdir()
            _write(
                workspace,
                "README.md",
                (
                    "# Robotics Adventure\n\n"
                    "A curriculum project with lessons, modules, and student labs.\n"
                ),
            )
            _write(workspace, "lessons/lesson-1.md", "# Lesson 1\n")
            handler_cls = make_handler(
                workspace,
                token="token",
                assistant_id="codex",
                assistant_name="Codex",
            )
            fake = _FakeHandler(handler_cls)

            handler_cls.handle_api_get(fake, urlparse("/api/context?token=token"))

            context = fake.response["payload"]["context"]
            profile = context["workspaceProfile"]
            self.assertEqual("learning_program", context["workspaceKind"])
            self.assertEqual("learning_program", profile["kind"])
            self.assertEqual("project", context["productLanguage"]["singular"])
            self.assertEqual("lesson", profile["product_language"]["entry_noun"])


if __name__ == "__main__":
    unittest.main()
