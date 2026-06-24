import importlib.util
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


if __name__ == "__main__":
    unittest.main()
