import tempfile
import unittest
from pathlib import Path

from agentcanvas.indexer import discover_files


def _write(root: Path, relative_path: str, content: str = "") -> None:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class AgentCanvasIgnoreTests(unittest.TestCase):
    def test_discover_files_respects_agentcanvasignore(self):
        with tempfile.TemporaryDirectory() as temp_root:
            root = Path(temp_root)
            _write(root, ".agentcanvasignore", "demo_projects/\nagentcanvas/web/\n*.tmp\n")
            _write(root, "agentcanvas/indexer.py", "print('keep')\n")
            _write(root, "agentcanvas/web/assets/index.js", "print('built')\n")
            _write(root, "demo_projects/shop/package.json", "{}\n")
            _write(root, "notes.tmp", "ignore me\n")

            files, truncated = discover_files(root)
            rels = {path.relative_to(root).as_posix() for path in files}

            self.assertFalse(truncated)
            self.assertEqual({"agentcanvas/indexer.py", ".agentcanvasignore"}, rels)


if __name__ == "__main__":
    unittest.main()
