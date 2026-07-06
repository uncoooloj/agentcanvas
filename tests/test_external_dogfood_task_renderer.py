import argparse
import tempfile
import unittest
from pathlib import Path

from scripts.render_external_dogfood_task import render_task, main


class ExternalDogfoodTaskRendererTests(unittest.TestCase):
    def test_rendered_task_uses_environment_token_placeholder(self):
        text = render_task(
            argparse.Namespace(
                agent_id="claude-code",
                agent_name="Claude Code",
                workspace_id="fastapi-service",
                attempt=1,
                workspace="/tmp/fixture",
                session_id="claude-fastapi-1",
                journey_id="route:post--signup-app-main.py",
                target_node_id="route:post--signup-app-main.py:1:do",
                proof_dir="/tmp/proof",
                private_docs_dir="docs/private",
                private_note_path="docs/private/dogfood-claude.md",
                matrix_path="docs/private/release-matrix.local.json",
                question="Should I preserve fixture behavior?",
                answer="Yes. Preserve fixture behavior.",
                workspace_verification_command="python3.9 -m py_compile app/main.py",
            )
        )

        self.assertIn("X-AgentCanvas-Token: $AGENTCANVAS_TOKEN", text)
        self.assertIn("$AGENTCANVAS_BASE_URL", text)
        self.assertIn("Do not print, save, or summarize `$AGENTCANVAS_TOKEN`.", text)
        self.assertNotIn("?token=", text)
        self.assertNotIn("<live-token>", text)

    def test_main_writes_output_file(self):
        with tempfile.TemporaryDirectory() as temp_root:
            output = Path(temp_root) / "task.md"

            exit_code = main(
                [
                    "--agent-id",
                    "claude-code",
                    "--agent-name",
                    "Claude Code",
                    "--workspace-id",
                    "fastapi-service",
                    "--attempt",
                    "1",
                    "--workspace",
                    "/tmp/fixture",
                    "--session-id",
                    "claude-fastapi-1",
                    "--journey-id",
                    "route:post--signup-app-main.py",
                    "--target-node-id",
                    "route:post--signup-app-main.py:1:do",
                    "--proof-dir",
                    "/tmp/proof",
                    "--private-note-path",
                    "docs/private/dogfood-claude.md",
                    "--workspace-verification-command",
                    "python3.9 -m py_compile app/main.py",
                    "--output",
                    str(output),
                ]
            )

            self.assertEqual(exit_code, 0)
            self.assertIn("Claude Code fastapi-service Dogfood Task", output.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
