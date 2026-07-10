import unittest
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class AgentCanvasImportTests(unittest.TestCase):
    def test_import_agentcanvas(self):
        import agentcanvas

        self.assertEqual(agentcanvas.__version__, "0.1.2")

    def test_cli_reports_release_version(self):
        completed = subprocess.run(
            [sys.executable, "-m", "agentcanvas", "--version"],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            check=True,
        )

        self.assertEqual(completed.stdout.strip(), "agentcanvas 0.1.2")


if __name__ == "__main__":
    unittest.main()
