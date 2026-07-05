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

    def test_cli_canvas_apply_dry_run_validates_without_writing(self):
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
                    "--dry-run",
                ],
                cwd=temp_root,
                env=_agentcanvas_env(),
                text=True,
                capture_output=True,
                timeout=15,
            )

            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            output = json.loads(completed.stdout)
            self.assertTrue(output["dry_run"])
            self.assertEqual(output["revision"], 1)
            self.assertFalse((workspace / ".agentcanvas" / "canvas.ir.json").exists())

    def test_cli_canvas_apply_rejects_ambiguous_workspace_selection(self):
        with tempfile.TemporaryDirectory() as temp_root:
            workspace = self._workspace(temp_root)
            other_workspace = Path(temp_root) / "other"
            other_workspace.mkdir()
            input_path = Path(temp_root) / "ops.json"
            input_path.write_text(json.dumps(self._initial_batch()), encoding="utf-8")

            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agentcanvas",
                    "canvas",
                    "apply",
                    str(other_workspace),
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

            self.assertEqual(completed.returncode, 1)
            output = json.loads(completed.stdout)
            self.assertEqual(output["error"]["code"], "WORKSPACE_AMBIGUOUS")

    def test_cli_canvas_apply_reports_unreadable_input_without_traceback(self):
        with tempfile.TemporaryDirectory() as temp_root:
            workspace = self._workspace(temp_root)

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
                    str(Path(temp_root) / "missing.json"),
                ],
                cwd=temp_root,
                env=_agentcanvas_env(),
                text=True,
                capture_output=True,
                timeout=15,
            )

            self.assertEqual(completed.returncode, 1)
            self.assertNotIn("Traceback", completed.stderr + completed.stdout)
            output = json.loads(completed.stdout)
            self.assertEqual(output["error"]["code"], "INPUT_NOT_READABLE")

    def test_cli_canvas_apply_auto_migrates_legacy_canvas(self):
        with tempfile.TemporaryDirectory() as temp_root:
            workspace = self._workspace(temp_root)
            state_dir = workspace / ".agentcanvas"
            state_dir.mkdir()
            canvas_path = state_dir / "canvas.ir.json"
            canvas_path.write_text(
                json.dumps(_legacy_canvas_wrapper()),
                encoding="utf-8",
            )
            input_path = Path(temp_root) / "ops.json"
            input_path.write_text(
                json.dumps(
                    {
                        "base_revision": 0,
                        "operations": [
                            {
                                "op": "set_app",
                                "app": {"name": "Auto migrated app"},
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

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
            self.assertTrue(output["auto_migrated"])
            self.assertEqual(output["base_revision"], 1)
            self.assertEqual(output["revision"], 2)
            canvas = _read_json(canvas_path)
            self.assertEqual(canvas["schema"], CANVAS_V2_SCHEMA)
            self.assertEqual(canvas["app"]["name"], "Auto migrated app")
            self.assertTrue((state_dir / "history" / "canvas.pre-v2.json").is_file())
            self.assertTrue((state_dir / "history" / "canvas.1.json").is_file())

    def test_cli_canvas_apply_dry_run_auto_migration_preserves_legacy_canvas(self):
        with tempfile.TemporaryDirectory() as temp_root:
            workspace = self._workspace(temp_root)
            state_dir = workspace / ".agentcanvas"
            state_dir.mkdir()
            canvas_path = state_dir / "canvas.ir.json"
            canvas_path.write_text(json.dumps(_legacy_canvas_wrapper()), encoding="utf-8")
            input_path = Path(temp_root) / "ops.json"
            input_path.write_text(
                json.dumps(
                    {
                        "base_revision": 0,
                        "operations": [
                            {
                                "op": "set_app",
                                "app": {"name": "Dry run migrated app"},
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

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
                    "--dry-run",
                ],
                cwd=temp_root,
                env=_agentcanvas_env(),
                text=True,
                capture_output=True,
                timeout=15,
            )

            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            output = json.loads(completed.stdout)
            self.assertTrue(output["auto_migrated"])
            self.assertTrue(output["dry_run"])
            self.assertEqual(output["revision"], 2)
            self.assertNotEqual(_read_json(canvas_path)["schema"], CANVAS_V2_SCHEMA)
            self.assertFalse((state_dir / "history" / "canvas.pre-v2.json").exists())
            self.assertFalse((state_dir / "history" / "canvas.1.json").exists())

    def test_cli_canvas_apply_auto_migration_accepts_migrated_base_revision(self):
        with tempfile.TemporaryDirectory() as temp_root:
            workspace = self._workspace(temp_root)
            state_dir = workspace / ".agentcanvas"
            state_dir.mkdir()
            canvas_path = state_dir / "canvas.ir.json"
            canvas_path.write_text(json.dumps(_legacy_canvas_wrapper()), encoding="utf-8")
            input_path = Path(temp_root) / "ops.json"
            input_path.write_text(
                json.dumps(
                    {
                        "base_revision": 1,
                        "operations": [
                            {
                                "op": "set_app",
                                "app": {"name": "Base one migrated app"},
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

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
                    "1",
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
            self.assertTrue(output["auto_migrated"])
            self.assertEqual(output["base_revision"], 1)
            self.assertEqual(output["revision"], 2)
            self.assertEqual(_read_json(canvas_path)["app"]["name"], "Base one migrated app")

    def test_cli_canvas_migrate_dry_run_and_apply_unblock_v2_apply(self):
        with tempfile.TemporaryDirectory() as temp_root:
            workspace = self._workspace(temp_root)
            state_dir = workspace / ".agentcanvas"
            state_dir.mkdir()
            canvas_path = state_dir / "canvas.ir.json"
            canvas_path.write_text(json.dumps(_legacy_canvas_wrapper()), encoding="utf-8")

            dry_run = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agentcanvas",
                    "canvas",
                    "migrate",
                    "--workspace",
                    str(workspace),
                    "--dry-run",
                ],
                cwd=temp_root,
                env=_agentcanvas_env(),
                text=True,
                capture_output=True,
                timeout=15,
            )

            self.assertEqual(dry_run.returncode, 0, dry_run.stdout + dry_run.stderr)
            dry_run_output = json.loads(dry_run.stdout)
            self.assertTrue(dry_run_output["dry_run"])
            self.assertEqual(dry_run_output["schema"], CANVAS_V2_SCHEMA)
            self.assertNotEqual(_read_json(canvas_path)["schema"], CANVAS_V2_SCHEMA)

            migrate = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agentcanvas",
                    "canvas",
                    "migrate",
                    "--workspace",
                    str(workspace),
                    "--apply",
                    "--authored-by",
                    "codex-migration-test",
                ],
                cwd=temp_root,
                env=_agentcanvas_env(),
                text=True,
                capture_output=True,
                timeout=15,
            )

            self.assertEqual(migrate.returncode, 0, migrate.stdout + migrate.stderr)
            migrate_output = json.loads(migrate.stdout)
            self.assertFalse(migrate_output["dry_run"])
            migrated = _read_json(canvas_path)
            self.assertEqual(migrated["schema"], CANVAS_V2_SCHEMA)
            self.assertEqual(migrated["authored_by"], "codex-migration-test")
            self.assertTrue((state_dir / "history" / "canvas.pre-v2.json").is_file())

            ops_path = Path(temp_root) / "ops.json"
            ops_path.write_text(
                json.dumps(
                    {
                        "base_revision": 1,
                        "operations": [
                            {
                                "op": "set_app",
                                "app": {"name": "Migrated app"},
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            apply = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agentcanvas",
                    "canvas",
                    "apply",
                    "--workspace",
                    str(workspace),
                    "--base-revision",
                    "1",
                    "--input",
                    str(ops_path),
                ],
                cwd=temp_root,
                env=_agentcanvas_env(),
                text=True,
                capture_output=True,
                timeout=15,
            )

            self.assertEqual(apply.returncode, 0, apply.stdout + apply.stderr)
            self.assertEqual(json.loads(apply.stdout)["revision"], 2)
            self.assertEqual(_read_json(canvas_path)["app"]["name"], "Migrated app")

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


def _legacy_canvas_wrapper():
    return {
        "schema": "agentcanvas.behavior_canvas_response.v1",
        "version": "0.1.0",
        "canvas": {
            "schema": "agentcanvas.behavior_canvas.v1",
            "appName": "Legacy app",
            "journeys": [
                {
                    "id": "flow:legacy",
                    "title": "Legacy signup",
                    "summary": "A legacy display canvas.",
                    "nodes": [
                        {
                            "kind": "step",
                            "id": "n:start",
                            "role": "when",
                            "text": "Someone starts",
                        },
                        {
                            "kind": "step",
                            "id": "n:finish",
                            "role": "do",
                            "text": "Finish setup",
                        },
                    ],
                }
            ],
        },
        "mapping": {
            "schema": "agentcanvas.canvas_mapping.v1",
            "mode": "agent-authored",
        },
    }
