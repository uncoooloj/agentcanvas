import json
import tempfile
import unittest
from pathlib import Path

from scripts.verify_dogfood_proof import (
    DogfoodProofError,
    stable_directory_sha256,
    validate_manifest,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
VALID_MANIFEST = PROJECT_ROOT / "tests" / "fixtures" / "dogfood-proof" / "manifest.valid.json"


class DogfoodProofManifestTests(unittest.TestCase):
    def test_valid_manifest_is_replayable(self):
        result = validate_manifest(VALID_MANIFEST)

        self.assertTrue(result["ok"])
        self.assertEqual(result["agent"], "codex")
        self.assertEqual(result["pending_request"], "dogfood-proof-change")
        self.assertEqual(result["checklist_items"], 3)

    def test_manifest_fixture_hash_matches_sample_workspace(self):
        manifest = json.loads(VALID_MANIFEST.read_text(encoding="utf-8"))

        self.assertEqual(
            manifest["workspace"]["fixture_sha256"],
            stable_directory_sha256(PROJECT_ROOT / manifest["workspace"]["fixture_path"]),
        )

    def test_fixture_hash_ignores_runtime_and_vcs_artifacts(self):
        with tempfile.TemporaryDirectory() as temp_root:
            root = Path(temp_root)
            (root / "app").mkdir()
            (root / "app" / "main.py").write_text("print('stable')\n", encoding="utf-8")
            before = stable_directory_sha256(root)

            for relative_path in [
                ".agentcanvas/workflow.ir.json",
                ".git/HEAD",
                ".pytest_cache/README.md",
                "__pycache__/main.cpython-39.pyc",
                "docs/private/release-matrix.local.json",
                "node_modules/example/package.json",
                "dist/build.txt",
            ]:
                path = root / relative_path
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("volatile\n", encoding="utf-8")

            self.assertEqual(before, stable_directory_sha256(root))

    def test_manifest_rejects_stale_fixture_hash(self):
        with tempfile.TemporaryDirectory() as temp_root:
            manifest_path = Path(temp_root) / "manifest.json"
            manifest = json.loads(VALID_MANIFEST.read_text(encoding="utf-8"))
            manifest["workspace"]["fixture_sha256"] = "0" * 64
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            with self.assertRaises(DogfoodProofError) as raised:
                validate_manifest(manifest_path)

        self.assertIn("fixture_sha256 mismatch", str(raised.exception))

    def test_manifest_rejects_invalid_conversation_jsonl(self):
        with tempfile.TemporaryDirectory() as temp_root:
            temp = Path(temp_root)
            bad_jsonl = temp / "bad.conversation.jsonl"
            bad_jsonl.write_text("{not-json}\n", encoding="utf-8")
            manifest = json.loads(VALID_MANIFEST.read_text(encoding="utf-8"))
            manifest["pending_request"]["conversation_jsonl_path"] = str(bad_jsonl)
            manifest_path = temp / "manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            with self.assertRaises(DogfoodProofError) as raised:
                validate_manifest(manifest_path)

        self.assertIn("is not valid JSON", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
