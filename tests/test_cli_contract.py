import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
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


class AgentCanvasCliContractTests(unittest.TestCase):
    maxDiff = None

    def _copy_sample_workspace(self, temp_root):
        workspace = Path(temp_root) / "sample-js-app"
        shutil.copytree(SAMPLE_APP, workspace)
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
                        "change": {},
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

            status_result = self._run_agentcanvas(
                "status",
                "raise-checkout-empty-state",
                str(workspace),
                "--status",
                "in_progress",
                "--note",
                "Working on it.",
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
            self.assertIn(str(workspace.resolve()), markdown)
            self.assertIn(
                str(workspace.resolve() / ".agentcanvas" / "canvas.ir.json"),
                markdown,
            )
            self.assertIn("`.agentcanvas/canvas.ir.json`", markdown)
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
            self.assertEqual(canvas_ir["schema"], "agentcanvas.behavior_canvas_response.v1")
            self.assertEqual(canvas_ir["mapping"]["mode"], "agent-authored")
            self.assertEqual(canvas_ir["mapping"]["flowCount"], 1)
            journey = canvas_ir["canvas"]["journeys"][0]
            self.assertEqual(journey["entry"], "Someone starts checkout")
            self.assertEqual(
                [node["text"] for node in journey["nodes"]],
                ["Someone starts checkout", "Submit the order"],
            )


if __name__ == "__main__":
    unittest.main()
