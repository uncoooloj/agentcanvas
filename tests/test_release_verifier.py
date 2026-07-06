import importlib.util
import json
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

    def test_readme_documents_phase4_security_truths(self):
        readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("## Security And Privacy", readme)
        self.assertIn("agentcanvas up` refuses non-loopback hosts", readme)
        self.assertIn("--allow-remote-host", readme)
        self.assertIn("Heartbeat files\nstore only a token hint", readme)
        self.assertIn("runtime smoke logs redact launch tokens", readme)
        self.assertIn("AgentCanvas ships with no telemetry", readme)
        self.assertIn("MCP tools can read and update AgentCanvas state", readme)
        self.assertNotIn("**MCP**: planned", readme)

    def test_public_docs_describe_pending_conversation_logs(self):
        paths = [
            PROJECT_ROOT / "README.md",
            PROJECT_ROOT / "docs" / "adapters.md",
            PROJECT_ROOT / "docs" / "publishing.md",
        ]

        for path in paths:
            with self.subTest(path=path.name):
                self.assertIn(
                    ".agentcanvas/pending/*.conversation.jsonl",
                    path.read_text(encoding="utf-8"),
                )

    def test_phase5_issue_templates_exist(self):
        template_dir = PROJECT_ROOT / ".github" / "ISSUE_TEMPLATE"

        expected = {
            "bug.yml": ("Bug report", "bug"),
            "dogfood.yml": ("Dogfood run", "dogfood"),
            "agent-compat.yml": ("Agent compatibility", "agent-compat"),
        }
        for filename, (name, label) in expected.items():
            with self.subTest(filename=filename):
                source = (template_dir / filename).read_text(encoding="utf-8")
                self.assertIn("name: %s" % name, source)
                self.assertIn("- %s" % label, source)
                self.assertIn("body:", source)

    def test_frontend_node_version_is_pinned_to_ci_runtime(self):
        workflow = (PROJECT_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        package = json.loads((PROJECT_ROOT / "frontend" / "package.json").read_text(encoding="utf-8"))
        lockfile = json.loads((PROJECT_ROOT / "frontend" / "package-lock.json").read_text(encoding="utf-8"))
        node_version = (PROJECT_ROOT / ".node-version").read_text(encoding="utf-8").strip()

        self.assertEqual(node_version, "22.13.0")
        self.assertIn('NODE_VERSION: "22.13.0"', workflow)
        self.assertEqual(package["engines"]["node"], ">=22.13.0 <23")
        self.assertEqual(lockfile["packages"][""]["engines"]["node"], ">=22.13.0 <23")

    def test_cloudflare_config_matches_frontend_agentcanvas_contract(self):
        verifier = load_verifier()

        with redirect_stdout(StringIO()):
            verifier.verify_cloudflare_config()

    def test_packaged_web_asset_freshness_allows_generated_whitespace_only(self):
        verifier = load_verifier()

        with tempfile.TemporaryDirectory() as temp_root:
            root = Path(temp_root)
            build = root / "build"
            packaged = root / "packaged"
            (build / "assets").mkdir(parents=True)
            (packaged / "assets").mkdir(parents=True)
            (build / "index.html").write_text("<script></script>   \n\n", encoding="utf-8")
            (packaged / "index.html").write_text("<script></script>\n", encoding="utf-8")
            (build / "assets" / "app.js").write_text("console.log('ok')  \n", encoding="utf-8")
            (packaged / "assets" / "app.js").write_text("console.log('ok')\n", encoding="utf-8")
            (build / "favicon.ico").write_bytes(b"icon")
            (packaged / "favicon.ico").write_bytes(b"icon")

            with patch.object(verifier, "PACKAGED_WEB_DIR", packaged), redirect_stdout(StringIO()):
                verifier.verify_packaged_web_assets(build)

    def test_packaged_web_asset_freshness_rejects_stale_committed_assets(self):
        verifier = load_verifier()

        with tempfile.TemporaryDirectory() as temp_root:
            root = Path(temp_root)
            build = root / "build"
            packaged = root / "packaged"
            build.mkdir()
            packaged.mkdir()
            (build / "index.html").write_text("fresh\n", encoding="utf-8")
            (packaged / "index.html").write_text("stale\n", encoding="utf-8")

            with patch.object(verifier, "PACKAGED_WEB_DIR", packaged), redirect_stdout(StringIO()):
                with self.assertRaises(verifier.VerificationError) as raised:
                    verifier.verify_packaged_web_assets(build)

        self.assertIn("assets are stale", str(raised.exception))

    def test_run_step_reports_missing_commands_in_plain_language(self):
        verifier = load_verifier()

        with patch("subprocess.run", side_effect=FileNotFoundError), redirect_stdout(
            StringIO()
        ):
            with self.assertRaises(verifier.VerificationError) as raised:
                verifier.run_step("Missing command", ["missing-tool"], PROJECT_ROOT)

        self.assertIn("could not start", str(raised.exception))
        self.assertIn("missing-tool", str(raised.exception))

    def test_verifier_rejects_unsupported_python_with_clear_message(self):
        verifier = load_verifier()

        with self.assertRaises(verifier.VerificationError) as raised:
            verifier.require_supported_python((3, 7, 17))

        message = str(raised.exception)
        self.assertIn("Python 3.9 or newer", message)
        self.assertIn("python3.9 scripts/verify_release.py", message)

    def test_verifier_accepts_declared_python_floor(self):
        verifier = load_verifier()

        verifier.require_supported_python((3, 9, 0))

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
                "Dogfood proof manifest",
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

        self.assertEqual(labels, ["Python unit tests", "AgentCanvas CLI smoke test", "Dogfood proof manifest"])


if __name__ == "__main__":
    unittest.main()
