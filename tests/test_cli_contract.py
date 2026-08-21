import json
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_APP = PROJECT_ROOT / "examples" / "sample-js-app"


def _agentcanvas_env():
    env = os.environ.copy()
    pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        str(PROJECT_ROOT)
        if not pythonpath
        else str(PROJECT_ROOT) + os.pathsep + pythonpath
    )
    return env


def _json_strings(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield str(key)
            yield from _json_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _json_strings(item)
    elif value is not None:
        yield str(value)


def _prompt_path(path: Path) -> str:
    return str(path).replace("\\", "/")


class AgentCanvasCliContractTests(unittest.TestCase):
    maxDiff = None

    def _copy_sample_workspace(self, temp_root):
        workspace = Path(temp_root) / "sample-js-app"
        shutil.copytree(SAMPLE_APP, workspace, ignore=shutil.ignore_patterns(".agentcanvas"))
        return workspace

    def _run_agentcanvas(self, *args, cwd):
        return subprocess.run(
            [sys.executable, "-m", "agentcanvas", *args],
            cwd=cwd,
            env=_agentcanvas_env(),
            text=True,
            capture_output=True,
            timeout=15,
        )

    def _skip_if_cli_scaffold(self, completed):
        combined = completed.stdout + completed.stderr
        if "AgentCanvas scaffold is ready" in combined:
            self.skipTest("agentcanvas CLI command implementation is still scaffolded")

    def test_sample_js_app_has_indexer_signals(self):
        expected_paths = [
            "src/routes/cart.js",
            "src/routes/checkout.js",
            "src/actions/add-to-cart.js",
            "src/actions/apply-discount.js",
            "src/actions/submit-order.js",
            "tests/checkout.integration.test.js",
            "checkout.test.js",
        ]

        for relative_path in expected_paths:
            with self.subTest(path=relative_path):
                self.assertTrue((SAMPLE_APP / relative_path).is_file())

    def test_start_without_workspace_can_use_demo_workspace_for_launch_or_demo(self):
        from agentcanvas.cli import selected_workspace
        from agentcanvas.demo import demo_fixture, demo_workspace

        args = SimpleNamespace(workspace=None, path=None, demo=False)

        self.assertEqual(selected_workspace(args), ".")
        selected = Path(selected_workspace(args, demo_default=True))
        self.assertEqual(selected.name, demo_fixture().name)
        self.assertTrue(selected.is_dir())
        self.assertNotEqual(selected, demo_fixture())
        self.assertTrue((selected / ".agentcanvas-demo").is_file())

        copied = demo_workspace()
        self.assertEqual(copied.name, demo_fixture().name)
        self.assertTrue(copied.is_dir())

    def test_start_command_passes_launch_mode_to_server(self):
        from agentcanvas.cli import main
        from agentcanvas.demo import demo_fixture

        with tempfile.TemporaryDirectory() as temp_root:
            workspace = Path(temp_root) / "real-workspace"
            workspace.mkdir()
            cases = [
                (["start", "--port", "0"], True, False, None),
                (["start", "--demo", "--port", "0"], False, True, None),
                (["start", str(workspace), "--port", "0"], False, False, workspace),
                (
                    ["start", "--workspace", str(workspace), "--port", "0"],
                    False,
                    False,
                    workspace,
                ),
            ]

            for argv, landing_mode, demo_mode, expected_workspace in cases:
                with self.subTest(argv=argv):
                    with patch("agentcanvas.cli.run_server") as run_server:
                        self.assertEqual(main(argv), 0)

                    run_server.assert_called_once()
                    _, kwargs = run_server.call_args
                    self.assertEqual(kwargs["landing_mode"], landing_mode)
                    self.assertEqual(kwargs["demo_mode"], demo_mode)
                    self.assertEqual(kwargs["port"], 0)
                    self.assertEqual(kwargs["host"], "127.0.0.1")

                    selected = Path(kwargs["workspace"])
                    if expected_workspace is None:
                        self.assertEqual(selected.name, demo_fixture().name)
                        self.assertTrue((selected / ".agentcanvas-demo").is_file())
                    else:
                        self.assertEqual(selected, expected_workspace)

    def test_start_command_accepts_supervised_token_from_env(self):
        from agentcanvas.cli import main

        with tempfile.TemporaryDirectory() as temp_root:
            workspace = Path(temp_root) / "real-workspace"
            workspace.mkdir()
            with patch.dict(
                os.environ,
                {
                    "AGENTCANVAS_SERVER_TOKEN": "supervised-token",
                    "AGENTCANVAS_SUPERVISED": "1",
                },
            ):
                with patch("agentcanvas.cli.run_server") as run_server:
                    self.assertEqual(main(["start", str(workspace), "--port", "0"]), 0)

            _, kwargs = run_server.call_args
            self.assertEqual(kwargs["token"], "supervised-token")
            self.assertTrue(kwargs["supervised"])

    def test_start_non_loopback_host_requires_explicit_allow_flag(self):
        from agentcanvas.cli import main

        with tempfile.TemporaryDirectory() as temp_root:
            workspace = Path(temp_root) / "real-workspace"
            workspace.mkdir()

            with patch("agentcanvas.cli.run_server") as run_server:
                stderr = io.StringIO()
                with redirect_stderr(stderr):
                    self.assertEqual(main(["start", str(workspace), "--host", "0.0.0.0", "--port", "0"]), 1)
            run_server.assert_not_called()
            self.assertIn("--allow-remote-host", stderr.getvalue())

            with patch("agentcanvas.cli.run_server") as run_server:
                stderr = io.StringIO()
                with redirect_stderr(stderr):
                    self.assertEqual(
                        main(
                            [
                                "start",
                                str(workspace),
                                "--host",
                                "0.0.0.0",
                                "--allow-remote-host",
                                "--port",
                                "0",
                            ]
                        ),
                        0,
                    )
            _, kwargs = run_server.call_args
            self.assertEqual(kwargs["host"], "0.0.0.0")
            self.assertIn("exposes the local canvas server", stderr.getvalue())

    def test_up_command_prints_stable_json_launch_payload(self):
        from agentcanvas.cli import main

        with tempfile.TemporaryDirectory() as temp_root:
            workspace = Path(temp_root) / "real-workspace"
            workspace.mkdir()
            payload = {
                "ok": True,
                "url": "http://127.0.0.1:8765/?token=secret",
                "port": 8765,
                "token": "secret",
                "pid": 123,
                "already_running": False,
            }
            stdout = io.StringIO()
            with patch("agentcanvas.cli.ensure_server_up", return_value=payload) as ensure_up:
                with redirect_stdout(stdout):
                    self.assertEqual(main(["up", str(workspace), "--json", "--session-id", "session-1"]), 0)
            result = json.loads(stdout.getvalue())
            self.assertEqual(result["url"], payload["url"])
            self.assertNotIn("token", result)
            self.assertEqual(stdout.getvalue().count("secret"), 1)
            self.assertFalse(result["already_running"])
            ensure_up.assert_called_once()
            _, kwargs = ensure_up.call_args
            self.assertEqual(kwargs["session_id"], "session-1")
            self.assertFalse(kwargs["open_browser"])

    def test_up_command_refuses_non_loopback_host(self):
        from agentcanvas.cli import main

        with tempfile.TemporaryDirectory() as temp_root:
            workspace = Path(temp_root) / "real-workspace"
            workspace.mkdir()
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                self.assertEqual(
                    main(["up", str(workspace), "--host", "0.0.0.0", "--json"]),
                    1,
                )

            payload = json.loads(stdout.getvalue())
            self.assertFalse(payload["ok"])
            self.assertEqual(payload["error"]["code"], "NON_LOOPBACK_HOST")
            self.assertEqual(payload["error"]["details"]["host"], "0.0.0.0")

    def test_up_stop_uses_launch_record(self):
        from agentcanvas.cli import main

        with tempfile.TemporaryDirectory() as temp_root:
            workspace = Path(temp_root) / "real-workspace"
            workspace.mkdir()
            with patch("agentcanvas.cli.stop_server", return_value={"ok": True, "stopped": True, "pid": 123}) as stop:
                with patch("builtins.print"):
                    self.assertEqual(main(["up", str(workspace), "--stop"]), 0)
            stop.assert_called_once()
            self.assertEqual(stop.call_args.args[0], workspace.resolve())

    def test_index_command_writes_workflow_ir_for_sample_app(self):
        with tempfile.TemporaryDirectory() as temp_root:
            workspace = self._copy_sample_workspace(temp_root)

            completed = self._run_agentcanvas("index", str(workspace), cwd=temp_root)
            self._skip_if_cli_scaffold(completed)

            self.assertEqual(
                completed.returncode,
                0,
                completed.stdout + completed.stderr,
            )

            ir_path = workspace / ".agentcanvas" / "workflow.ir.json"
            self.assertTrue(ir_path.is_file(), f"missing {ir_path}")

            with ir_path.open(encoding="utf-8") as handle:
                workflow_ir = json.load(handle)

            self.assertIn("source_facts", workflow_ir)
            self.assertGreater(workflow_ir["summary"].get("language_facts", 0), 0)
            self.assertIn(
                "javascript-typescript",
                workflow_ir["summary"].get("language_modules", []),
            )
            self.assertEqual(
                workflow_ir["projection_contract"]["primary_mode"],
                "llm-assisted",
            )
            self.assertEqual(
                workflow_ir["projection_contract"]["language_module_role"]["purpose"],
                "grounding_chunking_provenance",
            )

            discovered = "\n".join(_json_strings(workflow_ir))
            for expected_fragment in [
                "src/routes/checkout.js",
                "src/actions/submit-order.js",
                "tests/checkout.integration.test.js",
            ]:
                with self.subTest(fragment=expected_fragment):
                    self.assertIn(expected_fragment, discovered)

    def test_pending_command_lists_pending_change_requests(self):
        with tempfile.TemporaryDirectory() as temp_root:
            workspace = self._copy_sample_workspace(temp_root)
            pending_dir = workspace / ".agentcanvas" / "pending"
            pending_dir.mkdir(parents=True, exist_ok=True)
            (pending_dir / "raise-checkout-empty-state.md").write_text(
                "# Raise Checkout Empty State\n\nAdd copy for empty carts.\n",
                encoding="utf-8",
            )
            (pending_dir / "raise-checkout-empty-state.json").write_text(
                json.dumps(
                    {
                        "id": "raise-checkout-empty-state",
                        "title": "Raise checkout empty state",
                        "target": "src/routes/checkout.js",
                        "status": "pending",
                        "created_at": "2026-06-19T00:00:00Z",
                        "workspace": str(workspace),
                        "sessionId": "session-1",
                        "change": {
                            "journeyId": "flow:checkout",
                            "targetStep": "n:checkout:empty-cart",
                        },
                    }
                ),
                encoding="utf-8",
            )
            (pending_dir / "other-session.json").write_text(
                json.dumps(
                    {
                        "id": "other-session",
                        "title": "Other session",
                        "status": "pending",
                        "created_at": "2026-06-19T00:00:01Z",
                        "workspace": str(workspace),
                        "sessionId": "session-2",
                        "change": {"journeyId": "flow:other"},
                    }
                ),
                encoding="utf-8",
            )

            completed = self._run_agentcanvas("pending", str(workspace), cwd=temp_root)
            self._skip_if_cli_scaffold(completed)

            self.assertEqual(
                completed.returncode,
                0,
                completed.stdout + completed.stderr,
            )
            self.assertIn("raise-checkout-empty-state.md", completed.stdout)
            self.assertIn("raise-checkout-empty-state.json", completed.stdout)
            self.assertIn("other-session", completed.stdout)

            session_result = self._run_agentcanvas(
                "pending",
                str(workspace),
                "--session-id",
                "session-1",
                cwd=temp_root,
            )
            self.assertEqual(
                session_result.returncode,
                0,
                session_result.stdout + session_result.stderr,
            )
            self.assertIn("raise-checkout-empty-state", session_result.stdout)
            self.assertNotIn("other-session", session_result.stdout)

            wrong_session_status = self._run_agentcanvas(
                "status",
                "raise-checkout-empty-state",
                str(workspace),
                "--status",
                "sent",
                "--session-id",
                "session-2",
                cwd=temp_root,
            )
            self.assertEqual(wrong_session_status.returncode, 1)

            status_result = self._run_agentcanvas(
                "status",
                "raise-checkout-empty-state",
                str(workspace),
                "--status",
                "in_progress",
                "--note",
                "Working on it.",
                "--actor",
                "codex-session-1",
                "--session-id",
                "session-1",
                cwd=temp_root,
            )
            self.assertEqual(
                status_result.returncode,
                0,
                status_result.stdout + status_result.stderr,
            )
            with (pending_dir / "raise-checkout-empty-state.json").open(encoding="utf-8") as handle:
                updated = json.load(handle)
            self.assertEqual(updated["status"], "in_progress")
            self.assertEqual(updated["note"], "Working on it.")
            self.assertEqual(updated["history"][-1]["actor"], "codex-session-1")
            self.assertEqual(
                updated["refs"],
                [
                    {"kind": "flow", "id": "flow:checkout", "source": "change.journeyId"},
                    {
                        "kind": "node",
                        "id": "n:checkout:empty-cart",
                        "flow": "flow:checkout",
                        "source": "change.targetStep",
                    },
                ],
            )
            self.assertEqual(updated["orphaned_refs"], [])

            implemented_result = self._run_agentcanvas(
                "status",
                "raise-checkout-empty-state",
                str(workspace),
                "--status",
                "implemented",
                "--note",
                "Implemented.",
                "--session-id",
                "session-1",
                cwd=temp_root,
            )
            self.assertEqual(
                implemented_result.returncode,
                0,
                implemented_result.stdout + implemented_result.stderr,
            )
            verified_result = self._run_agentcanvas(
                "status",
                "raise-checkout-empty-state",
                str(workspace),
                "--status",
                "verified",
                "--note",
                "Verified.",
                "--actor",
                "codex-session-1",
                "--session-id",
                "session-1",
                "--evidence-check",
                "npm test",
                "--evidence-result",
                "passed",
                "--evidence-at",
                "2026-07-06T00:00:00Z",
                cwd=temp_root,
            )
            self.assertEqual(
                verified_result.returncode,
                0,
                verified_result.stdout + verified_result.stderr,
            )
            with (pending_dir / "raise-checkout-empty-state.json").open(encoding="utf-8") as handle:
                verified = json.load(handle)
            self.assertEqual(verified["status"], "verified")
            self.assertEqual(
                verified["verification"],
                {
                    "actor": "codex-session-1",
                    "at": "2026-07-06T00:00:00Z",
                    "check": "npm test",
                    "result": "passed",
                },
            )

    def test_reply_command_appends_pending_conversation(self):
        from agentcanvas.ir import write_pending_change

        with tempfile.TemporaryDirectory() as temp_root:
            workspace = self._copy_sample_workspace(temp_root)
            pending = write_pending_change(
                workspace,
                {
                    "title": "Clarify checkout copy",
                    "summary": "Make checkout copy clearer.",
                    "journeyId": "flow:checkout",
                },
                session_id="session-1",
            )

            question = self._run_agentcanvas(
                "reply",
                pending["id"],
                str(workspace),
                "--question",
                "Should this include email receipts too?",
                "--session-id",
                "session-1",
                cwd=temp_root,
            )
            self.assertEqual(question.returncode, 0, question.stdout + question.stderr)
            self.assertIn("Added question", question.stdout)
            self.assertIn("needs_input", question.stdout)

            answer = self._run_agentcanvas(
                "reply",
                pending["id"],
                str(workspace),
                "--answer",
                "Checkout screen only.",
                "--session-id",
                "session-1",
                cwd=temp_root,
            )
            self.assertEqual(answer.returncode, 0, answer.stdout + answer.stderr)
            self.assertIn("Added answer", answer.stdout)
            self.assertIn("in_progress", answer.stdout)

            wrong_session = self._run_agentcanvas(
                "reply",
                pending["id"],
                str(workspace),
                "--note",
                "Wrong session should not write.",
                "--session-id",
                "session-2",
                cwd=temp_root,
            )
            self.assertEqual(wrong_session.returncode, 1)

            conversation_path = (
                workspace
                / ".agentcanvas"
                / "pending"
                / f"{pending['id']}.conversation.jsonl"
            )
            lines = conversation_path.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(lines), 2)
            turns = [json.loads(line) for line in lines]
            self.assertEqual([turn["kind"] for turn in turns], ["question", "answer"])

    def test_health_command_reports_missing_map_files_without_writing_state(self):
        with tempfile.TemporaryDirectory() as temp_root:
            workspace = Path(temp_root) / "empty-workspace"
            workspace.mkdir()

            completed = self._run_agentcanvas("health", str(workspace), cwd=temp_root)
            self._skip_if_cli_scaffold(completed)

            self.assertEqual(
                completed.returncode,
                0,
                completed.stdout + completed.stderr,
            )
            self.assertIn("Map is not ready yet", completed.stdout)
            self.assertIn(
                "Workflow evidence (workflow IR): missing from .agentcanvas/workflow.ir.json.",
                completed.stdout,
            )
            self.assertIn(
                "Canvas map (canvas IR): missing from .agentcanvas/canvas.ir.json.",
                completed.stdout,
            )
            self.assertIn(".agentcanvas/pending", completed.stdout)
            self.assertFalse((workspace / ".agentcanvas").exists())

    def test_health_command_reports_readable_stale_canvas(self):
        with tempfile.TemporaryDirectory() as temp_root:
            workspace = Path(temp_root) / "mapped-workspace"
            state_dir = workspace / ".agentcanvas"
            state_dir.mkdir(parents=True)
            workflow_path = state_dir / "workflow.ir.json"
            canvas_path = state_dir / "canvas.ir.json"
            workflow_path.write_text(
                json.dumps({"schema": "agentcanvas.workflow.v1"}),
                encoding="utf-8",
            )
            canvas_path.write_text(
                json.dumps({"schema": "agentcanvas.behavior_canvas_response.v1"}),
                encoding="utf-8",
            )
            os.utime(canvas_path, (1000, 1000))
            os.utime(workflow_path, (2000, 2000))

            completed = self._run_agentcanvas("health", str(workspace), cwd=temp_root)
            self._skip_if_cli_scaffold(completed)

            self.assertEqual(
                completed.returncode,
                0,
                completed.stdout + completed.stderr,
            )
            self.assertIn(
                "Canvas map (canvas IR): found and readable at .agentcanvas/canvas.ir.json.",
                completed.stdout,
            )
            self.assertIn(
                "Freshness: canvas map is older than the workflow evidence.",
                completed.stdout,
            )

    def test_prompt_command_prints_copyable_agent_instruction_without_writing_state(self):
        with tempfile.TemporaryDirectory() as temp_root:
            workspace = Path(temp_root) / "workspace-to-map"
            workspace.mkdir()

            completed = self._run_agentcanvas("prompt", str(workspace), cwd=temp_root)
            self._skip_if_cli_scaffold(completed)

            self.assertEqual(
                completed.returncode,
                0,
                completed.stdout + completed.stderr,
            )
            self.assertIn("Copy this to the AI coding agent", completed.stdout)
            self.assertIn("Calling agent: the calling coding agent.", completed.stdout)
            self.assertIn(_prompt_path(workspace.resolve()), completed.stdout)
            self.assertIn(
                _prompt_path(workspace.resolve() / ".agentcanvas" / "canvas.ir.json"),
                completed.stdout,
            )
            self.assertIn("`.agentcanvas/canvas.ir.json`", completed.stdout)
            self.assertIn("pip install use-agentcanvas", completed.stdout)
            self.assertNotRegex(completed.stdout, r"pip install\s+agentcanvas\b")
            self.assertNotIn("agentcanvas start", completed.stdout)
            self.assertIn("uvx --from use-agentcanvas agentcanvas setup --agent auto", completed.stdout)
            self.assertIn("agentcanvas up --workspace", completed.stdout)
            self.assertIn("--json", completed.stdout)
            self.assertIn("agentcanvas health --workspace", completed.stdout)
            self.assertIn("plain English", completed.stdout)
            self.assertIn("ask clarifying questions", completed.stdout)
            for agent_name in ["Codex", "Claude", "Cursor", "Antigravity"]:
                self.assertNotIn(agent_name, completed.stdout)
            self.assertFalse((workspace / ".agentcanvas").exists())

    def test_prompt_command_renders_requested_agent_label(self):
        with tempfile.TemporaryDirectory() as temp_root:
            workspace = Path(temp_root) / "workspace-to-map"
            workspace.mkdir()

            completed = self._run_agentcanvas(
                "prompt",
                str(workspace),
                "--agent",
                "Claude Code",
                cwd=temp_root,
            )
            self._skip_if_cli_scaffold(completed)

            self.assertEqual(
                completed.returncode,
                0,
                completed.stdout + completed.stderr,
            )
            self.assertIn("Copy this to Claude Code:", completed.stdout)
            self.assertIn("Calling agent: Claude Code.", completed.stdout)
            self.assertIn("AgentCanvas is agent-agnostic", completed.stdout)
            self.assertIn("agentcanvas setup --agent claude-code", completed.stdout)
            self.assertIn("agentcanvas up --workspace", completed.stdout)
            self.assertNotIn("Codex", completed.stdout)
            self.assertNotIn("Cursor", completed.stdout)
            self.assertNotIn("agentcanvas start", completed.stdout)
            self.assertFalse((workspace / ".agentcanvas").exists())

    def test_pending_handoff_markdown_includes_canvas_map_instruction(self):
        from agentcanvas.ir import write_pending_change

        with tempfile.TemporaryDirectory() as temp_root:
            workspace = self._copy_sample_workspace(temp_root)

            pending = write_pending_change(
                workspace,
                {
                    "title": "Refresh the checkout map",
                    "summary": "Map the checkout journey for the canvas.",
                },
            )

            markdown = Path(pending["markdown_path"]).read_text(encoding="utf-8")
            self.assertIn(_prompt_path(workspace.resolve()), markdown)
            self.assertIn(
                _prompt_path(workspace.resolve() / ".agentcanvas" / "canvas.ir.json"),
                markdown,
            )
            self.assertIn("`.agentcanvas/canvas.ir.json`", markdown)
            self.assertIn("pip install use-agentcanvas", markdown)
            self.assertNotRegex(markdown, r"pip install\s+agentcanvas\b")
            self.assertNotIn("agentcanvas start", markdown)
            self.assertIn("uvx --from use-agentcanvas agentcanvas setup --agent auto", markdown)
            self.assertIn("agentcanvas up --workspace", markdown)
            self.assertIn("ask clarifying questions", markdown)
            for agent_name in ["Codex", "Claude", "Cursor", "Antigravity"]:
                self.assertNotIn(agent_name, markdown)

    def test_apply_query_materializes_llm_canvas_query(self):
        with tempfile.TemporaryDirectory() as temp_root:
            workspace = self._copy_sample_workspace(temp_root)

            index_result = self._run_agentcanvas("index", str(workspace), cwd=temp_root)
            self._skip_if_cli_scaffold(index_result)
            self.assertEqual(
                index_result.returncode,
                0,
                index_result.stdout + index_result.stderr,
            )

            with (workspace / ".agentcanvas" / "workflow.ir.json").open(encoding="utf-8") as handle:
                workflow_ir = json.load(handle)
            fact_id = workflow_ir["source_facts"]["facts"][0]["id"]
            query_path = Path(temp_root) / "canvas-query.json"
            query_path.write_text(
                json.dumps(
                    {
                        "schema": "agentcanvas.canvas_query.v1",
                        "version": "0.1.0",
                        "mode": "llm-assisted",
                        "operations": [
                            {
                                "op": "upsert_node",
                                "node": {
                                    "id": "when:checkout",
                                    "type": "route",
                                    "label": "Someone starts checkout",
                                },
                                "fact_ids": [fact_id],
                            },
                            {
                                "op": "upsert_node",
                                "node": {
                                    "id": "do:submit-order",
                                    "type": "action",
                                    "label": "Submit the order",
                                },
                                "fact_ids": [fact_id],
                            },
                            {
                                "op": "upsert_edge",
                                "edge": {
                                    "source": "when:checkout",
                                    "target": "do:submit-order",
                                    "kind": "then",
                                },
                                "fact_ids": [fact_id],
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )

            completed = self._run_agentcanvas(
                "apply-query",
                str(workspace),
                "--query",
                str(query_path),
                cwd=temp_root,
            )
            self.assertEqual(
                completed.returncode,
                0,
                completed.stdout + completed.stderr,
            )

            with (workspace / ".agentcanvas" / "workflow.ir.json").open(encoding="utf-8") as handle:
                workflow_ir = json.load(handle)
            with (workspace / ".agentcanvas" / "canvas.ir.json").open(encoding="utf-8") as handle:
                canvas_ir = json.load(handle)

            self.assertIn("source_facts", workflow_ir)
            self.assertEqual(canvas_ir["schema"], "agentcanvas.canvas.v2")
            self.assertEqual(canvas_ir["revision"], 1)
            self.assertEqual(canvas_ir["authored_by"], "apply-query")
            self.assertEqual(canvas_ir["app"]["name"], "Sample js app")
            self.assertEqual(len(canvas_ir["flows"]), 1)
            flow = canvas_ir["flows"][0]
            self.assertTrue(flow["entry_node"].startswith("agent:when-checkout"))
            self.assertEqual(
                [node["title"] for node in flow["nodes"]],
                ["Someone starts checkout", "Submit the order"],
            )
            self.assertFalse((workspace / ".agentcanvas" / "history" / "canvas.pre-v2.json").exists())
            self.assertTrue((workspace / ".agentcanvas" / "history" / "canvas.0.json").is_file())


if __name__ == "__main__":
    unittest.main()
