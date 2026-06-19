import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


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


if __name__ == "__main__":
    unittest.main()
