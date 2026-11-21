"""Exercise Studio routes through the HTTP handler and the CLI launch path."""

import errno
import http.client
import io
import json
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from contextlib import contextmanager, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from http.server import ThreadingHTTPServer

from agentcanvas.cli import build_parser, main
from agentcanvas.graph import build_demo_studio_document
from agentcanvas.runner import RunManager
from agentcanvas.server import initialize_studio_server, make_handler
from agentcanvas.supervisor import ensure_server_up, launch_url


TOKEN = "studio-local-token"
AUTH = {"X-AgentCanvas-Token": TOKEN}
COPY_RUNNER = {"preferred": "copy", "available": ["copy"]}


class StudioServerTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        (self.root / "pyproject.toml").write_text('[project]\nname = "sample"\n', encoding="utf-8")
        (self.root / "app.py").write_text("def greet():\n    return 'hello'\n", encoding="utf-8")
        patcher = patch("agentcanvas.runner.detect_runners", return_value=COPY_RUNNER)
        patcher.start()
        self.addCleanup(patcher.stop)
        handler = make_handler(self.root, TOKEN, "generic", "Your assistant")
        self.thread = None
        try:
            self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        except PermissionError as exc:
            if exc.errno not in {errno.EPERM, errno.EACCES}:
                raise
            # Restricted hosts can still exercise real HTTP over a connected socket.
            self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler, bind_and_activate=False)
        else:
            self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        initialize_studio_server(self.httpd, self.root, None)
        self.addCleanup(self.close_server)
        if self.thread:
            self.thread.start()

    def close_server(self):
        self.httpd.studio_stop.set()
        self.httpd.event_bus.publish("server.stopping", {})
        self.httpd.run_manager.shutdown()
        if self.thread:
            self.httpd.shutdown()
            self.thread.join(timeout=2)
        self.httpd.server_close()

    @contextmanager
    def connection(self):
        host, port = self.httpd.server_address
        client = http.client.HTTPConnection(host, port, timeout=3)
        if self.thread is None:
            client_sock, server_sock = socket.socketpair()
            client_sock.settimeout(3)
            client.sock = client_sock
            self.httpd.process_request(server_sock, ("127.0.0.1", 12345))
        try:
            yield client
        finally:
            client.close()

    def request(self, method, path, body=None, headers=None):
        headers = dict(AUTH if headers is None else headers)
        if body is not None:
            body = json.dumps(body)
            headers["Content-Type"] = "application/json"
        with self.connection() as client:
            client.request(method, path, body, headers)
            with client.getresponse() as response:
                return response.status, json.loads(response.read())

    def test_studio_is_immediately_available_without_legacy_index(self):
        status, payload = self.request("GET", "/api/studio?diffBase=main..HEAD")
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertFalse(payload["has_mapped_canvas"])
        self.assertEqual(payload["document"]["schema"], "agentcanvas.studio.v3")
        self.assertEqual(payload["document"]["workspace"], str(self.root))
        self.assertTrue(payload["document"]["components"])
        self.assertEqual(payload["document"]["flows"], [])
        self.assertEqual(payload["runners"], {"preferred": "copy", "available": []})
        self.assertEqual(payload["stale_node_ids"], [])
        self.assertEqual(payload["mode"], "workspace")
        self.assertEqual(payload["studio_mode"], "diff")
        self.assertEqual(payload["diff_base"], "main..HEAD")
        self.assertFalse((self.root / ".agentcanvas" / "workflow.ir.json").exists())

        status, payload = self.request("GET", "/api/studio?demo=true")
        self.assertEqual(status, 200)
        self.assertTrue(payload["has_mapped_canvas"])
        self.assertGreaterEqual(len(payload["document"]["components"]), 5)

    def test_legacy_context_canvas_and_pending_remain_available(self):
        status, payload = self.request("GET", "/api/context")
        self.assertEqual(status, 200)
        self.assertEqual(payload["context"]["workspacePath"], str(self.root))
        self.assertEqual(self.request("GET", "/api/pending"), (200, {"ok": True, "pending": []}))
        status, payload = self.request("GET", "/api/canvas")
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertTrue((self.root / ".agentcanvas" / "workflow.ir.json").exists())

    def test_tokens_are_required_and_non_loopback_origin_is_rejected(self):
        for method, path in [
            ("GET", "/api/studio"),
            ("GET", "/api/events"),
            ("GET", "/api/file-slice"),
            ("GET", "/api/file-diff"),
            ("POST", "/api/annotations"),
            ("PATCH", "/api/annotations/some-id"),
            ("DELETE", "/api/annotations/some-id"),
            ("POST", "/api/runs"),
            ("GET", "/api/runs/some-id"),
            ("POST", "/api/runs/some-id/answer"),
            ("POST", "/api/runs/some-id/cancel"),
            ("POST", "/api/runs/some-id/discard"),
        ]:
            with self.subTest(method=method, path=path):
                status, payload = self.request(method, path, headers={})
                self.assertEqual(status, 401)
                self.assertEqual(payload["error"]["code"], "token_invalid")
        status, _ = self.request("GET", "/api/studio?token=%C3%A9", headers={})
        self.assertEqual(status, 401)
        status, _ = self.request("GET", f"/api/studio?token={TOKEN}", headers={})
        self.assertEqual(status, 200)
        status, _ = self.request("GET", "/api/studio", headers={**AUTH, "Origin": "https://example.com"})
        self.assertEqual(status, 403)
        with self.connection() as client:
            client.request("OPTIONS", "/api/annotations", headers={"Origin": "http://localhost:3000"})
            with client.getresponse() as response:
                self.assertEqual(response.status, 204)
                self.assertEqual(response.getheader("Access-Control-Allow-Origin"), "http://localhost:3000")
                self.assertIn("PATCH", response.getheader("Access-Control-Allow-Methods"))

    def test_remote_opt_in_allows_only_matching_remote_origin(self):
        self.httpd.RequestHandlerClass = make_handler(
            self.root, TOKEN, "generic", "Your assistant", allow_remote_origin=True,
        )
        headers = {**AUTH, "Host": "studio.example.test:8765"}
        status, _ = self.request("GET", "/api/studio", headers={
            **headers, "Origin": "http://studio.example.test:8765",
        })
        self.assertEqual(status, 200)
        status, _ = self.request("GET", "/api/studio", headers={
            **headers, "Origin": "https://unrelated.example.test",
        })
        self.assertEqual(status, 403)

    def test_source_slice_and_confined_diff_routes(self):
        status, payload = self.request("GET", "/api/file-slice?path=app.py&line=2&context=0")
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["highlight_line"], 2)
        self.assertEqual(payload["lines"], [{"number": 2, "text": "    return 'hello'"}])
        status, payload = self.request("GET", "/api/file-slice?path=../app.py")
        self.assertEqual(status, 400)
        self.assertEqual(payload["error"], "PATH_OUTSIDE_WORKSPACE")
        status, payload = self.request("GET", "/api/file-diff?path=../app.py")
        self.assertEqual(status, 400)
        self.assertEqual(payload["error"], "PATH_OUTSIDE_WORKSPACE")
        status, payload = self.request("GET", "/api/file-slice?path=missing.py")
        self.assertEqual(status, 404)
        self.assertEqual(payload["error"], "FILE_NOT_FOUND")
        (self.root / "binary").write_bytes(b"\0binary")
        status, payload = self.request("GET", "/api/file-slice?path=binary")
        self.assertEqual(status, 422)
        self.assertEqual(payload["error"], "BINARY_FILE")

    def test_file_diff_reports_worktree_edits(self):
        def git(*args):
            subprocess.run(["git", "-C", str(self.root), *args], check=True, capture_output=True, timeout=5)

        git("init", "-q")
        git("add", "app.py")
        git(
            "-c", "user.name=Studio Test", "-c", "user.email=studio@example.test",
            "-c", "core.hooksPath=/dev/null", "commit", "--no-gpg-sign", "-qm", "Initial",
        )
        (self.root / "app.py").write_text("def greet():\n    return 'updated'\n", encoding="utf-8")
        status, payload = self.request("GET", "/api/file-diff?path=app.py&base=HEAD")
        self.assertEqual(status, 200)
        self.assertTrue(payload["has_diff"])
        self.assertEqual(payload["additions"], 1)
        self.assertEqual(payload["deletions"], 1)

    def test_annotation_crud(self):
        status, payload = self.request("POST", "/api/annotations", {
            "target_type": "node",
            "target_id": "node:checkout",
            "flow_id": "flow:checkout",
            "text": "Check the retry behavior",
            "author": "Dev",
        })
        self.assertEqual(status, 200)
        annotation = payload["annotation"]
        path = "/api/annotations/" + annotation["id"]

        status, payload = self.request("PATCH", path, {"resolved": True})
        self.assertEqual(status, 200)
        self.assertTrue(payload["annotation"]["resolved"])
        _, payload = self.request("GET", "/api/studio")
        self.assertEqual(len(payload["annotations"]), 1)
        self.assertEqual(self.request("DELETE", path), (200, {"ok": True}))
        self.assertEqual(self.request("DELETE", path)[0], 404)
        _, payload = self.request("GET", "/api/studio")
        self.assertEqual(payload["annotations"], [])

    def test_run_create_and_lookup(self):
        status, payload = self.request("POST", "/api/runs?diffBase=main..HEAD", {
            "kind": "diff", "runner": "copy", "prompt": "Show me the checkout path",
        })
        self.assertEqual(status, 200)
        run = payload["run"]
        self.assertEqual(run["runner"], "copy")
        self.assertEqual(run["diff_base"], "main..HEAD")
        path = "/api/runs/" + run["id"]
        status, payload = self.request("GET", path)
        self.assertEqual(status, 200)
        self.assertEqual(payload["run"]["id"], run["id"])
        self.assertEqual(self.request("GET", "/api/runs/nonexistent")[0], 404)
        self.assertEqual(self.request("POST", "/api/runs", {"kind": "unknown"})[0], 400)

    def test_run_action_routes_dispatch_to_manager(self):
        manager = self.httpd.run_manager
        run = {"id": "plan-1", "kind": "plan"}
        for action, method, body in [
            ("answer", "answer_run", {"answer": "Keep the retry"}),
            ("answer", "answer_run", {"approve": True}),
            ("cancel", "cancel_run", None),
            ("discard", "discard_run", None),
        ]:
            with self.subTest(action=action, body=body), patch.object(manager, method, return_value=run) as call:
                status, payload = self.request("POST", f"/api/runs/{run['id']}/{action}", body)
                self.assertEqual(status, 200)
                self.assertEqual(payload["run"], run)
                call.assert_called_once_with(run["id"], **(body or {}))

        path = f"/api/runs/{run['id']}/answer"
        with patch.object(manager, "get_run", return_value={"status": "awaiting_approval"}), patch.object(
            manager, "answer_run", return_value=run
        ) as answer:
            self.assertEqual(self.request("POST", path, {"answer": "approve"})[0], 200)
            answer.assert_called_once_with(run["id"], approve=True)

    def test_sse_streams_annotation_write_after_initial_ping(self):
        with self.connection() as client:
            client.request("GET", f"/api/events?token={TOKEN}")
            with client.getresponse() as response:
                self.assertEqual(response.status, 200)
                self.assertEqual(response.getheader("Content-Type"), "text/event-stream")
                self.assertEqual(response.getheader("Cache-Control"), "no-cache")
                self.assertEqual(response.getheader("Connection"), "keep-alive")
                self.assertEqual(response.getheader("X-Accel-Buffering"), "no")
                self.assertEqual(response.fp.readline(), b": ping\n")
                self.assertEqual(response.fp.readline(), b"\n")

                status, payload = self.request("POST", "/api/annotations", {
                    "target_type": "node", "target_id": "node:checkout", "text": "Pay once",
                })
                self.assertEqual(status, 200)
                self.assertEqual(response.fp.readline(), b"event: annotations.updated\n")
                data = response.fp.readline().removeprefix(b"data: ")
                self.assertEqual(json.loads(data)["annotation"], payload["annotation"])
                self.assertEqual(response.fp.readline(), b"\n")

    def test_map_run_streams_progress_and_persists_the_canvas(self):
        document = build_demo_studio_document()
        document.update(workspace=str(self.root), workspace_name=self.root.name, mode="map", diff_base=None)
        turns = [
            {"type": "thread.started", "thread_id": "fake-local-thread"},
            {"type": "item.completed", "item": {"type": "agent_message", "text": json.dumps(document)}},
            {"type": "turn.completed"},
        ]
        script = "\n".join(f"print({json.dumps(turn)!r}, flush=True)" for turn in turns)

        def fake_runner(_command, **kwargs):
            read_stdin = "import sys\nsys.stdin.read()\n" if kwargs.get("stdin") == subprocess.PIPE else ""
            return subprocess.Popen([sys.executable, "-u", "-c", read_stdin + script], **kwargs)

        self.httpd.run_manager.shutdown()
        self.httpd.run_manager = RunManager(self.root, self.httpd.event_bus, command_factory=fake_runner)
        with patch("agentcanvas.runner.detect_runners", return_value={"preferred": "codex", "available": ["codex"]}):
            with self.connection() as client:
                client.request("GET", f"/api/events?token={TOKEN}")
                with client.getresponse() as response:
                    self.assertEqual(response.fp.readline(), b": ping\n")
                    self.assertEqual(response.fp.readline(), b"\n")
                    status, payload = self.request("POST", "/api/runs", {"kind": "map"})
                    self.assertEqual(status, 200)
                    run_id = payload["run"]["id"]
                    seen = {}
                    for _ in range(15):
                        event = response.fp.readline().decode("utf-8").strip().removeprefix("event: ")
                        data = json.loads(response.fp.readline().removeprefix(b"data: "))
                        self.assertEqual(response.fp.readline(), b"\n")
                        seen[event] = data
                        if event == "studio.updated":
                            break
                    self.assertEqual(seen["run.log"]["run_id"], run_id)
                    self.assertTrue(seen["run.log"]["entry"]["message"])
                    self.assertEqual(seen["run.updated"]["run"]["status"], "completed")
                    self.assertTrue(seen["studio.updated"]["has_mapped_canvas"])
        status, payload = self.request("GET", "/api/studio")
        self.assertEqual(status, 200)
        self.assertTrue(payload["has_mapped_canvas"])
        self.assertEqual(payload["document"]["flows"], document["flows"])
        self.assertIsNone(payload["active_run"])
        self.assertEqual(payload["recent_runs"][0]["id"], run_id)
        self.assertEqual(payload["runners"]["available"][0]["id"], "codex")


class StudioLaunchTests(unittest.TestCase):
    def test_up_shorthand_and_existing_commands(self):
        parser = build_parser()
        self.assertEqual(parser.parse_args(["."]).command, "up")
        self.assertEqual(parser.parse_args(["up", "."]).path, ".")
        self.assertEqual(parser.parse_args(["status", "pending-1", "--status", "done"]).command, "status")
        self.assertEqual(parser.parse_args(["init", "--agent", "auto"]).command, "setup")
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(parser.parse_args([directory, "--json"]).path, directory)

    def test_diff_cli_parses_both_working_tree_and_explicit_range(self):
        self.assertEqual(build_parser().parse_args(["diff"]).range, "")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            output = io.StringIO()
            with patch("agentcanvas.cli.ensure_server_up", return_value={"url": "url"}) as up, redirect_stdout(output):
                self.assertEqual(main([
                    "diff", "main..HEAD", "--workspace", directory, "--port", "0", "--json", "--no-open",
                ]), 0)
            self.assertEqual(up.call_args.args, (root,))
            self.assertEqual(up.call_args.kwargs["diff_base"], "main..HEAD")
            self.assertEqual(up.call_args.kwargs["port"], 0)
            self.assertFalse(up.call_args.kwargs["open_browser"])
            self.assertEqual(json.loads(output.getvalue())["url"], "url")

    def test_supervisor_scopes_new_and_reused_launch_urls(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            url = launch_url("127.0.0.1", 8787, TOKEN)
            record = {"url": url, "pid": 12345, "host": "127.0.0.1", "port": 8787, "token": TOKEN}
            with patch("agentcanvas.supervisor.read_launch_record", return_value=record), patch(
                "agentcanvas.supervisor.validate_launch_record", return_value=record
            ), patch("agentcanvas.supervisor.webbrowser.open") as browser:
                result = ensure_server_up(root, diff_base="feature/foo..HEAD", open_browser=True)
            self.assertTrue(result["already_running"])
            browser.assert_called_once_with(result["url"])
            self.assertEqual(parse_qs(urlparse(result["url"]).query), {
                "token": [TOKEN], "tab": ["diff"], "diffBase": ["feature/foo..HEAD"],
            })
            self.assertEqual(record["url"], url)

            with patch("agentcanvas.supervisor.read_launch_record", return_value=None), patch(
                "agentcanvas.supervisor.choose_port", return_value=8787
            ), patch(
                "agentcanvas.supervisor.spawn_server", return_value=SimpleNamespace(pid=12345)
            ) as spawn, patch("agentcanvas.supervisor.wait_until_ready"):
                result = ensure_server_up(root, diff_base="")
            self.assertFalse(result["already_running"])
            self.assertEqual(spawn.call_args.kwargs["diff_base"], "")
            params = parse_qs(urlparse(result["url"]).query, keep_blank_values=True)
            self.assertEqual(params["tab"], ["diff"])
            self.assertEqual(params["diffBase"], [""])


if __name__ == "__main__":
    unittest.main()
