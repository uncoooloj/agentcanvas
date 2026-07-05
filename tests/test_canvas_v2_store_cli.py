import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from agentcanvas.canvas_v2 import CANVAS_V2_SCHEMA, CanvasStoreError, apply_operation_batch


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _agentcanvas_env():
    env = os.environ.copy()
    pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        str(PROJECT_ROOT)
        if not pythonpath
        else str(PROJECT_ROOT) + os.pathsep + pythonpath
    )
    return env


def _read_json(path):
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


class CanvasV2StoreCliTests(unittest.TestCase):
    maxDiff = None

    def _workspace(self, temp_root):
        workspace = Path(temp_root) / "workspace"
        workspace.mkdir()
        return workspace

    def _initial_batch(self):
        return {
            "base_revision": 0,
            "authored_by": "codex-test",
            "operations": [
                {
                    "op": "set_app",
                    "app": {
                        "name": "Photo Share",
                        "summary": "People upload and share photos.",
                        "is_demo": False,
                    },
                },
                {
                    "op": "upsert_flow",
                    "flow": {
                        "id": "flow:upload",
                        "title": "Upload photo",
                        "summary": "How a photo gets uploaded.",
                        "entry_node": "n:upload:start",
                    },
                },
                {
                    "op": "upsert_node",
                    "flow": "flow:upload",
                    "node": {
                        "id": "n:upload:start",
                        "kind": "When",
                        "title": "Choose a photo",
                    },
                },
                {
                    "op": "upsert_node",
                    "flow": "flow:upload",
                    "node": {
                        "id": "n:upload:save",
                        "kind": "Do",
                        "title": "Save the photo",
                    },
                },
                {
                    "op": "upsert_edge",
                    "flow": "flow:upload",
                    "edge": {
                        "id": "e:upload:start:save",
                        "source": "n:upload:start",
                        "target": "n:upload:save",
                        "kind": "normal",
                    },
                },
            ],
        }

    def test_apply_initializes_v2_canvas_and_history(self):
        with tempfile.TemporaryDirectory() as temp_root:
            workspace = self._workspace(temp_root)

            result = apply_operation_batch(workspace, self._initial_batch())

            self.assertTrue(result["ok"])
            self.assertEqual(result["revision"], 1)
            canvas_path = workspace / ".agentcanvas" / "canvas.ir.json"
            canvas = _read_json(canvas_path)
            self.assertEqual(canvas["schema"], CANVAS_V2_SCHEMA)
            self.assertEqual(canvas["revision"], 1)
            self.assertEqual(canvas["authored_by"], "codex-test")
            self.assertEqual(canvas["app"]["name"], "Photo Share")
            self.assertEqual(canvas["flows"][0]["nodes"][1]["id"], "n:upload:save")

            history = _read_json(workspace / ".agentcanvas" / "history" / "canvas.0.json")
            self.assertEqual(history["schema"], CANVAS_V2_SCHEMA)
            self.assertEqual(history["revision"], 0)

    def test_revision_conflict_is_structured_and_does_not_write(self):
        with tempfile.TemporaryDirectory() as temp_root:
            workspace = self._workspace(temp_root)
            apply_operation_batch(workspace, self._initial_batch())

            with self.assertRaises(CanvasStoreError) as raised:
                apply_operation_batch(
                    workspace,
                    {
                        "base_revision": 0,
                        "operations": [
                            {
                                "op": "set_app",
                                "app": {"name": "Stale"},
                            }
                        ],
                    },
                )

            error = raised.exception.to_dict()
            self.assertEqual(error["error"]["code"], "REVISION_CONFLICT")
            self.assertEqual(error["revision"], 1)
            self.assertEqual(
                error["error"]["details"]["changed_since"]["flow_ids"],
                ["flow:upload"],
            )
            canvas = _read_json(workspace / ".agentcanvas" / "canvas.ir.json")
            self.assertEqual(canvas["app"]["name"], "Photo Share")

    def test_rejects_edges_without_explicit_id(self):
        with tempfile.TemporaryDirectory() as temp_root:
            workspace = self._workspace(temp_root)
            batch = self._initial_batch()
            batch["operations"][-1]["edge"].pop("id")

            with self.assertRaises(CanvasStoreError) as raised:
                apply_operation_batch(workspace, batch)

            self.assertEqual(raised.exception.code, "EDGE_ID_REQUIRED")
            self.assertFalse((workspace / ".agentcanvas" / "canvas.ir.json").exists())

    def test_delete_operations_increment_revision_and_snapshot_previous(self):
        with tempfile.TemporaryDirectory() as temp_root:
            workspace = self._workspace(temp_root)
            apply_operation_batch(workspace, self._initial_batch())

            result = apply_operation_batch(
                workspace,
                {
                    "base_revision": 1,
                    "operations": [
                        {
                            "op": "delete_edge",
                            "flow": "flow:upload",
                            "target": "e:upload:start:save",
                        },
                        {
                            "op": "delete_node",
                            "flow": "flow:upload",
                            "target": "n:upload:save",
                        },
                    ],
                },
                authored_by="codex-delete-test",
            )

            self.assertEqual(result["revision"], 2)
            canvas = _read_json(workspace / ".agentcanvas" / "canvas.ir.json")
            self.assertEqual(canvas["authored_by"], "codex-delete-test")
            self.assertEqual(canvas["revision"], 2)
            self.assertEqual(
                [node["id"] for node in canvas["flows"][0]["nodes"]],
                ["n:upload:start"],
            )
            self.assertEqual(canvas["flows"][0]["edges"], [])
            history = _read_json(workspace / ".agentcanvas" / "history" / "canvas.1.json")
            self.assertEqual(history["revision"], 1)
            self.assertEqual(len(history["flows"][0]["edges"]), 1)

    def test_cli_canvas_apply_writes_canvas(self):
        with tempfile.TemporaryDirectory() as temp_root:
            workspace = self._workspace(temp_root)
            input_path = Path(temp_root) / "ops.json"
            input_path.write_text(json.dumps(self._initial_batch()), encoding="utf-8")

            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agentcanvas",
                    "canvas",
                    "apply",
                    "--workspace",
                    str(workspace),
                    "--base-revision",
                    "0",
                    "--input",
                    str(input_path),
                ],
                cwd=temp_root,
                env=_agentcanvas_env(),
                text=True,
                capture_output=True,
                timeout=15,
            )

            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            output = json.loads(completed.stdout)
            self.assertEqual(output["revision"], 1)
            canvas = _read_json(workspace / ".agentcanvas" / "canvas.ir.json")
            self.assertEqual(canvas["schema"], CANVAS_V2_SCHEMA)

    def test_open_pending_reference_blocks_delete(self):
        with tempfile.TemporaryDirectory() as temp_root:
            workspace = self._workspace(temp_root)
            apply_operation_batch(workspace, self._initial_batch())
            pending_dir = workspace / ".agentcanvas" / "pending"
            pending_dir.mkdir(parents=True, exist_ok=True)
            (pending_dir / "change.json").write_text(
                json.dumps(
                    {
                        "id": "change",
                        "status": "pending",
                        "refs": [
                            {
                                "kind": "node",
                                "id": "n:upload:save",
                                "flow": "flow:upload",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaises(CanvasStoreError) as raised:
                apply_operation_batch(
                    workspace,
                    {
                        "base_revision": 1,
                        "operations": [
                            {
                                "op": "delete_node",
                                "flow": "flow:upload",
                                "target": "n:upload:save",
                            }
                        ],
                    },
                )

            self.assertEqual(raised.exception.code, "REFERENCED_ID_REMOVED")
