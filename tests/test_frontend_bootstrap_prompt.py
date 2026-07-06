import json
import re
import unittest
from pathlib import Path

from agentcanvas.bootstrap import build_landing_bootstrap_prompt


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

    def test_landing_page_does_not_inline_a_stale_agent_prompt(self):
        landing = LANDING_PAGE.read_text(encoding="utf-8")

        self.assertIn("LANDING_BOOTSTRAP_PROMPT", landing)
        self.assertNotIn("const AGENT_PROMPT", landing)
        self.assertNotIn("agentcanvas start --workspace", landing)


if __name__ == "__main__":
    unittest.main()
