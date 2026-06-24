import importlib.util
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "smoke_runtime.py"


def load_smoke_runtime():
    spec = importlib.util.spec_from_file_location("smoke_runtime", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RuntimeSmokeTests(unittest.TestCase):
    def test_parse_launch_info_extracts_base_url_and_token(self):
        smoke = load_smoke_runtime()

        launch = smoke.parse_launch_info(
            "Open http://127.0.0.1:54321/?token=abc123&sessionId=session-1"
        )

        self.assertEqual(launch.base_url, "http://127.0.0.1:54321")
        self.assertEqual(launch.token, "abc123")

    def test_parse_launch_info_ignores_lines_without_token(self):
        smoke = load_smoke_runtime()

        self.assertIsNone(smoke.parse_launch_info("AgentCanvas serving workspace"))
        self.assertIsNone(smoke.parse_launch_info("Open http://127.0.0.1:54321/"))

    def test_validate_context_requires_workspace_mode_without_demo_content(self):
        smoke = load_smoke_runtime()

        context = smoke.validate_context(
            {
                "ok": True,
                "context": {
                    "workspace": "sample-js-app",
                    "mode": "workspace",
                    "isDemo": False,
                    "isDemoContent": False,
                    "demoFallback": False,
                    "source": {"kind": "workspace"},
                },
            },
            expected_workspace="sample-js-app",
        )

        self.assertEqual(context["mode"], "workspace")

    def test_validate_context_rejects_demo_fallback(self):
        smoke = load_smoke_runtime()

        with self.assertRaises(smoke.SmokeError) as raised:
            smoke.validate_context(
                {
                    "ok": True,
                    "context": {
                        "workspace": "sample-js-app",
                        "mode": "landing",
                        "isDemo": False,
                        "isDemoContent": True,
                        "demoFallback": True,
                        "source": {"kind": "demo-fallback"},
                    },
                },
                expected_workspace="sample-js-app",
            )

        message = str(raised.exception)
        self.assertIn("mode='landing'", message)
        self.assertIn("demoFallback=True", message)

    def test_validate_canvas_requires_source_kind_and_flow_count(self):
        smoke = load_smoke_runtime()

        mapping = smoke.validate_canvas(
            {
                "ok": True,
                "canvas": {
                    "isDemo": False,
                    "journeys": [{"id": "flow-1"}],
                },
                "mapping": {
                    "demoFallback": False,
                    "flowCount": 1,
                    "displayFlowCount": 1,
                    "source": {
                        "kind": "heuristic-projection",
                        "flowCount": 1,
                    },
                },
            }
        )

        self.assertEqual(mapping["flowCount"], 1)

    def test_validate_canvas_rejects_missing_source_flow_count(self):
        smoke = load_smoke_runtime()

        with self.assertRaises(smoke.SmokeError) as raised:
            smoke.validate_canvas(
                {
                    "ok": True,
                    "canvas": {
                        "isDemo": False,
                        "journeys": [{"id": "flow-1"}],
                    },
                    "mapping": {
                        "demoFallback": False,
                        "flowCount": 1,
                        "source": {"kind": "heuristic-projection"},
                    },
                }
            )

        self.assertIn("mapping.source.flowCount", str(raised.exception))

    def test_sandbox_permission_detection_matches_errno_output(self):
        smoke = load_smoke_runtime()

        self.assertTrue(
            smoke.looks_like_sandbox_permission_failure(
                "PermissionError: [Errno 1] Operation not permitted"
            )
        )
        self.assertFalse(smoke.looks_like_sandbox_permission_failure("address in use"))

    def test_permission_summary_uses_specific_error_line(self):
        smoke = load_smoke_runtime()

        summary = smoke.summarize_permission_failure(
            "\n".join(
                [
                    "Traceback (most recent call last):",
                    "  File \"server.py\", line 90, in run_server",
                    "PermissionError: [Errno 1] Operation not permitted",
                ]
            )
        )

        self.assertEqual(
            summary,
            "PermissionError: [Errno 1] Operation not permitted",
        )

    def test_main_reports_sandbox_permission_without_traceback(self):
        smoke = load_smoke_runtime()
        stderr = StringIO()

        with patch.object(
            smoke,
            "run_smoke",
            side_effect=smoke.SandboxPermissionError("localhost blocked"),
        ), patch("sys.stderr", stderr):
            code = smoke.main([])

        message = stderr.getvalue()
        self.assertEqual(code, 2)
        self.assertIn("SANDBOX PERMISSION BLOCKED", message)
        self.assertIn("localhost blocked", message)
        self.assertNotIn("Traceback", message)


if __name__ == "__main__":
    unittest.main()
