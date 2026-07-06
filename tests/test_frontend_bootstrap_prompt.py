import json
import re
import unittest
from pathlib import Path, PureWindowsPath

from agentcanvas.bootstrap import (
    LANDING_AGENT_LABEL,
    build_bootstrap_permission_prompts,
    build_landing_bootstrap_prompt,
    render_bootstrap_prompt,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_PROMPT = PROJECT_ROOT / "frontend" / "src" / "lib" / "landingBootstrapPrompt.ts"
LANDING_PAGE = PROJECT_ROOT / "frontend" / "src" / "components" / "LandingPage.tsx"


class FrontendBootstrapPromptTests(unittest.TestCase):
    def test_landing_prompt_is_generated_from_shared_bootstrap_template(self):
        source = FRONTEND_PROMPT.read_text(encoding="utf-8")

        prompt_match = re.search(r"LANDING_BOOTSTRAP_PROMPT = (\".*\")", source)
        self.assertIsNotNone(prompt_match)
        generated_prompt = json.loads(prompt_match.group(1))

        self.assertEqual(build_landing_bootstrap_prompt(), generated_prompt)
        self.assertIn(
            'LANDING_BOOTSTRAP_PROMPT_SOURCE = "agentcanvas/templates/bootstrap_prompt.md"',
            source,
        )

    def test_bootstrap_prompt_normalizes_windows_paths_for_shared_output(self):
        prompt = render_bootstrap_prompt(
            workspace=PureWindowsPath("your-project"),
            agent_label=LANDING_AGENT_LABEL,
            workflow_relative_path=".agentcanvas/workflow.ir.json",
            canvas_relative_path=".agentcanvas/canvas.ir.json",
            canvas_path=PureWindowsPath("your-project/.agentcanvas/canvas.ir.json"),
        )

        self.assertNotIn("\\", prompt)
        self.assertIn("agentcanvas up --workspace your-project --agent auto --json", prompt)
        self.assertIn("your-project/.agentcanvas/canvas.ir.json", prompt)

    def test_landing_permission_prompt_metadata_matches_shared_budget(self):
        source = FRONTEND_PROMPT.read_text(encoding="utf-8")

        prompts_match = re.search(r"LANDING_BOOTSTRAP_PERMISSION_PROMPTS = (\[.*\])", source)
        self.assertIsNotNone(prompts_match)
        prompts = json.loads(prompts_match.group(1))

        self.assertEqual(build_bootstrap_permission_prompts(), prompts)
        self.assertLessEqual(len(prompts), 3)
        self.assertEqual(["Install", "Run", "Connect"], [prompt["label"] for prompt in prompts])

    def test_landing_page_does_not_inline_a_stale_agent_prompt(self):
        landing = LANDING_PAGE.read_text(encoding="utf-8")

        self.assertIn("LANDING_BOOTSTRAP_PROMPT", landing)
        self.assertIn("LANDING_BOOTSTRAP_PERMISSION_PROMPTS.map", landing)
        self.assertNotIn("const AGENT_PROMPT", landing)
        self.assertNotIn("agentcanvas start --workspace", landing)


if __name__ == "__main__":
    unittest.main()
