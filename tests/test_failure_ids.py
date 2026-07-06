import tempfile
import unittest
from pathlib import Path
from urllib.parse import urlparse

from agentcanvas.failure_ids import FAILURE_REPAIR_HINTS, FailureId, failure_payload
from agentcanvas.ir import build_bootstrap_prompt
from agentcanvas.server import make_handler


class _FakeHandler:
    def __init__(self, handler_cls):
        self.handler_cls = handler_cls
        self.response = None
        self.headers = {}

    def write_json(self, payload, status=200):
        self.response = {"status": int(status), "payload": payload}

    def authorized(self, *args, **kwargs):
        return self.handler_cls.authorized(self, *args, **kwargs)


class FailureIdTests(unittest.TestCase):
    def test_failure_payload_uses_machine_readable_code_and_hint(self):
        payload = failure_payload(FailureId.TOKEN_INVALID, "missing or invalid token")

        self.assertFalse(payload["ok"])
        self.assertEqual("token_invalid", payload["error"]["code"])
        self.assertIn("fresh URL", payload["error"]["hint"])

    def test_bootstrap_prompt_has_self_heal_clause_for_every_failure_id(self):
        with tempfile.TemporaryDirectory() as temp_root:
            workspace = Path(temp_root) / "workspace"
            workspace.mkdir()

            prompt = build_bootstrap_prompt(workspace)

        for failure_id in FailureId:
            self.assertIn(failure_id.value, prompt)
            hint_word = FAILURE_REPAIR_HINTS[failure_id].split()[0].lower()
            self.assertIn(hint_word, prompt.lower())

    def test_unauthorized_api_response_carries_token_invalid_failure_id(self):
        with tempfile.TemporaryDirectory() as temp_root:
            workspace = Path(temp_root) / "workspace"
            workspace.mkdir()
            handler_cls = make_handler(
                workspace,
                token="secret-token",
                assistant_id="codex",
                assistant_name="Codex",
            )
            fake = _FakeHandler(handler_cls)

            handler_cls.handle_api_get(fake, urlparse("/api/context?token=wrong-token"))

            self.assertEqual(401, fake.response["status"])
            error = fake.response["payload"]["error"]
            self.assertEqual("token_invalid", error["code"])
            self.assertIn("agentcanvas up --json", error["hint"])


if __name__ == "__main__":
    unittest.main()
