import importlib.util
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "verify_release.py"


def load_verifier():
    spec = importlib.util.spec_from_file_location("verify_release", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ReleaseVerifierTests(unittest.TestCase):
    def test_missing_frontend_dependencies_get_clear_install_message(self):
        verifier = load_verifier()

        with tempfile.TemporaryDirectory() as temp_root:
            frontend = Path(temp_root) / "frontend"
            frontend.mkdir()
            (frontend / "package.json").write_text("{}", encoding="utf-8")

            with self.assertRaises(verifier.VerificationError) as raised:
                verifier.require_frontend_build_tools(frontend)

        message = str(raised.exception)
        self.assertIn("dependencies are missing", message)
        self.assertIn("npm install --prefix frontend", message)

    def test_frontend_build_tools_are_optional_without_frontend_package(self):
        verifier = load_verifier()

        with tempfile.TemporaryDirectory() as temp_root:
            self.assertIsNone(verifier.require_frontend_build_tools(Path(temp_root)))

    def test_frontend_env_points_build_output_at_temporary_directory(self):
        verifier = load_verifier()

        with tempfile.TemporaryDirectory() as temp_root:
            output_dir = Path(temp_root) / "web-build"
            env = verifier.frontend_env(output_dir, "/agentcanvas/")

        self.assertEqual(env["AGENTCANVAS_VITE_OUT_DIR"], str(output_dir))
        self.assertEqual(env["AGENTCANVAS_VITE_BASE"], "/agentcanvas/")

    def test_run_step_reports_missing_commands_in_plain_language(self):
        verifier = load_verifier()

        with patch("subprocess.run", side_effect=FileNotFoundError), redirect_stdout(
            StringIO()
        ):
            with self.assertRaises(verifier.VerificationError) as raised:
                verifier.run_step("Missing command", ["missing-tool"], PROJECT_ROOT)

        self.assertIn("could not start", str(raised.exception))
        self.assertIn("missing-tool", str(raised.exception))

    def test_run_step_can_map_exit_code_to_clear_message(self):
        verifier = load_verifier()

        completed = subprocess.CompletedProcess(["blocked-tool"], 2)
        with patch("subprocess.run", return_value=completed), redirect_stdout(StringIO()):
            with self.assertRaises(verifier.VerificationError) as raised:
                verifier.run_step(
                    "Blocked command",
                    ["blocked-tool"],
                    PROJECT_ROOT,
                    returncode_messages={2: "localhost permission blocked"},
                )

        self.assertEqual(str(raised.exception), "localhost permission blocked")

    def test_runtime_smoke_argument_defaults_to_enabled(self):
        verifier = load_verifier()

        args = verifier.build_parser().parse_args([])

        self.assertFalse(args.skip_runtime_smoke)

    def test_runtime_smoke_argument_can_be_skipped(self):
        verifier = load_verifier()

        args = verifier.build_parser().parse_args(["--skip-runtime-smoke"])

        self.assertTrue(args.skip_runtime_smoke)

    def test_python_checks_run_runtime_smoke_after_cli_by_default(self):
        verifier = load_verifier()
        labels = []

        def fake_run_step(label, *args, **kwargs):
            labels.append(label)

        with patch.object(verifier, "run_step", side_effect=fake_run_step):
            verifier.run_python_checks()

        self.assertEqual(
            labels,
            [
                "Python unit tests",
                "AgentCanvas CLI smoke test",
                "AgentCanvas runtime API smoke test",
            ],
        )

    def test_python_checks_can_skip_runtime_smoke(self):
        verifier = load_verifier()
        labels = []

        def fake_run_step(label, *args, **kwargs):
            labels.append(label)

        with patch.object(verifier, "run_step", side_effect=fake_run_step), redirect_stdout(
            StringIO()
        ):
            verifier.run_python_checks(skip_runtime_smoke=True)

        self.assertEqual(labels, ["Python unit tests", "AgentCanvas CLI smoke test"])


if __name__ == "__main__":
    unittest.main()
