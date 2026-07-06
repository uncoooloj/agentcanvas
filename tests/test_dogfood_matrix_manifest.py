import json
import tempfile
import unittest
from pathlib import Path

from scripts.verify_dogfood_matrix import DogfoodMatrixError, validate_matrix


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PARTIAL_MATRIX = PROJECT_ROOT / "tests" / "fixtures" / "dogfood-matrix" / "matrix.partial.json"
VALID_PROOF = "tests/fixtures/dogfood-proof/manifest.valid.json"


class DogfoodMatrixManifestTests(unittest.TestCase):
    def test_partial_matrix_validates_shape_without_claiming_release_gate(self):
        result = validate_matrix(PARTIAL_MATRIX)

        self.assertTrue(result["ok"])
        self.assertFalse(result["complete"])
        self.assertEqual(result["run_count"], 1)
        self.assertEqual(result["proof_count"], 1)
        self.assertEqual(result["required_pair_count"], 12)
        self.assertEqual(len(result["missing"]), 12)

    def test_partial_matrix_fails_gate_mode(self):
        with self.assertRaises(DogfoodMatrixError) as raised:
            validate_matrix(PARTIAL_MATRIX, gate=True)

        self.assertIn("dogfood matrix gate is incomplete", str(raised.exception))

    def test_complete_matrix_requires_two_consecutive_clean_attempts_per_pair(self):
        with tempfile.TemporaryDirectory() as temp_root:
            matrix_path = Path(temp_root) / "matrix.json"
            matrix_path.write_text(json.dumps(_complete_matrix()), encoding="utf-8")

            result = validate_matrix(matrix_path, gate=True)

        self.assertTrue(result["complete"])
        self.assertEqual(result["required_pair_count"], 4)
        self.assertEqual(result["run_count"], 8)
        self.assertEqual(result["missing"], [])

    def test_non_consecutive_clean_attempts_do_not_satisfy_gate(self):
        matrix = _complete_matrix()
        matrix["runs"] = [
            {
                "agent_id": "codex",
                "workspace_id": "agentcanvas",
                "attempt": 1,
                "status": "clean",
                "loop": "full_loop",
                "runbook_id": "phase4-full-loop-v1",
                "permission_prompt_count": 1,
                "triage_class": "none",
            },
            {
                "agent_id": "codex",
                "workspace_id": "agentcanvas",
                "attempt": 3,
                "status": "clean",
                "loop": "full_loop",
                "runbook_id": "phase4-full-loop-v1",
                "permission_prompt_count": 1,
                "triage_class": "none",
            },
        ]

        with tempfile.TemporaryDirectory() as temp_root:
            matrix_path = Path(temp_root) / "matrix.json"
            matrix_path.write_text(json.dumps(matrix), encoding="utf-8")

            result = validate_matrix(matrix_path)

        self.assertFalse(result["complete"])
        codex_agentcanvas = next(
            missing
            for missing in result["missing"]
            if missing["agent_id"] == "codex" and missing["workspace_id"] == "agentcanvas"
        )
        self.assertEqual(codex_agentcanvas["clean_attempts"], [1, 3])

    def test_run_rejects_unknown_agent(self):
        matrix = _complete_matrix()
        matrix["runs"][0]["agent_id"] = "unknown"

        with tempfile.TemporaryDirectory() as temp_root:
            matrix_path = Path(temp_root) / "matrix.json"
            matrix_path.write_text(json.dumps(matrix), encoding="utf-8")

            with self.assertRaises(DogfoodMatrixError) as raised:
                validate_matrix(matrix_path)

        self.assertIn("agent_id is unknown", str(raised.exception))

    def test_run_rejects_mismatched_proof_agent(self):
        matrix = _complete_matrix()
        matrix["runs"][0]["agent_id"] = "claude-code"
        matrix["runs"][0]["proof_manifest_path"] = VALID_PROOF

        with tempfile.TemporaryDirectory() as temp_root:
            matrix_path = Path(temp_root) / "matrix.json"
            matrix_path.write_text(json.dumps(matrix), encoding="utf-8")

            with self.assertRaises(DogfoodMatrixError) as raised:
                validate_matrix(matrix_path)

        self.assertIn("proof agent mismatch", str(raised.exception))


def _complete_matrix():
    agents = [
        {"id": "codex", "name": "Codex", "public_claim": True},
        {"id": "claude-code", "name": "Claude Code", "public_claim": True},
    ]
    workspaces = [
        {"id": "agentcanvas", "name": "AgentCanvas", "type": "agentcanvas", "gate": True},
        {"id": "nextjs-vibe", "name": "Vibe-coded Next.js app", "type": "nextjs", "gate": True},
    ]
    runs = []
    for agent in agents:
        for workspace in workspaces:
            for attempt in (1, 2):
                runs.append(
                    {
                        "agent_id": agent["id"],
                        "workspace_id": workspace["id"],
                        "attempt": attempt,
                        "status": "clean",
                        "loop": "full_loop",
                        "runbook_id": "phase4-full-loop-v1",
                        "permission_prompt_count": 1,
                        "triage_class": "none",
                    }
                )
    return {
        "schema": "agentcanvas.dogfood_matrix.v1",
        "agents": agents,
        "workspaces": workspaces,
        "runs": runs,
    }


if __name__ == "__main__":
    unittest.main()
