import json
import tempfile
import unittest
from pathlib import Path

from scripts.run_dogfood_attempt import build_manifest, read_generated_at, write_json, write_text
from scripts.verify_dogfood_proof import validate_manifest


class DogfoodAttemptRunnerTests(unittest.TestCase):
    def test_build_manifest_writes_replayable_proof(self):
        with tempfile.TemporaryDirectory() as temp_root:
            root = Path(temp_root)
            workspace = root / "workspace"
            workspace.mkdir()
            (workspace / "src").mkdir()
            (workspace / "src" / "app.py").write_text("print('hello')\n", encoding="utf-8")
            pending_root = workspace / ".agentcanvas" / "pending"
            pending_root.mkdir(parents=True)
            pending_id = "dogfood-attempt"
            (pending_root / f"{pending_id}.md").write_text("# Dogfood attempt\n", encoding="utf-8")
            write_json(
                pending_root / f"{pending_id}.json",
                {"id": pending_id, "status": "verified"},
            )
            write_text(
                pending_root / f"{pending_id}.conversation.jsonl",
                json.dumps({"role": "assistant", "content": "Question?"}) + "\n",
            )
            verification_path = root / "proof" / "verification.txt"
            write_text(verification_path, "result=passed\n")

            manifest = build_manifest(
                agent_id="codex",
                agent_name="Codex",
                workspace=workspace,
                workspace_type="local-project",
                workspace_description="Test workspace.",
                pending_id=pending_id,
                pending_status="verified",
                permission_prompt_count=1,
                verification_command="scripts/run_dogfood_attempt.py",
                verification_path=verification_path,
                workflow_before="before",
                workflow_after="after",
            )
            manifest_path = root / "proof" / "proof.json"
            write_json(manifest_path, manifest)

            result = validate_manifest(manifest_path)

        self.assertTrue(result["ok"])
        self.assertEqual(result["agent"], "codex")
        self.assertEqual(result["pending_request"], pending_id)

    def test_read_generated_at_handles_missing_ir(self):
        with tempfile.TemporaryDirectory() as temp_root:
            self.assertEqual(read_generated_at(Path(temp_root)), "not-indexed")


if __name__ == "__main__":
    unittest.main()
