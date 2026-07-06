import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch


class _FakeHttpServer:
    def __init__(self, server_address, handler_class):
        self.server_address = server_address
        self.handler_class = handler_class
        self.served = False
        self.closed = False

    def serve_forever(self):
        self.served = True

    def server_close(self):
        self.closed = True


class ServerSecurityTests(unittest.TestCase):
    def test_supervised_server_output_omits_tokenized_launch_url(self):
        from agentcanvas.server import run_server

        with tempfile.TemporaryDirectory() as temp_root:
            workspace = Path(temp_root) / "workspace"
            workspace.mkdir()
            stdout = io.StringIO()

            with patch("agentcanvas.server.ensure_ir"), patch(
                "agentcanvas.server.ThreadingHTTPServer",
                _FakeHttpServer,
            ), patch("agentcanvas.server.start_server_heartbeat", return_value=None), redirect_stdout(stdout):
                run_server(
                    workspace,
                    host="127.0.0.1",
                    port=8765,
                    token="super-secret-token",
                    supervised=True,
                )

        output = stdout.getvalue()
        self.assertIn("AgentCanvas serving", output)
        self.assertNotIn("Open http://", output)
        self.assertNotIn("super-secret-token", output)

    def test_interactive_server_prints_tokenized_launch_url_once(self):
        from agentcanvas.server import run_server

        with tempfile.TemporaryDirectory() as temp_root:
            workspace = Path(temp_root) / "workspace"
            workspace.mkdir()
            stdout = io.StringIO()

            with patch("agentcanvas.server.ensure_ir"), patch(
                "agentcanvas.server.ThreadingHTTPServer",
                _FakeHttpServer,
            ), patch("agentcanvas.server.start_server_heartbeat", return_value=None), redirect_stdout(stdout):
                run_server(
                    workspace,
                    host="127.0.0.1",
                    port=8765,
                    token="super-secret-token",
                    supervised=False,
                )

        output = stdout.getvalue()
        self.assertEqual(output.count("super-secret-token"), 1)
        self.assertEqual(output.count("Open http://"), 1)


if __name__ == "__main__":
    unittest.main()
