import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from agentcanvas.canvas_v2 import (
    CANVAS_V2_SCHEMA,
    CanvasStoreError,
    apply_operation_batch,
    list_canvas_history,
    load_canvas_document,
    restore_canvas_revision,
)
import agentcanvas.canvas_v2.store as canvas_store


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

    def _five_node_batch(self):
        batch = self._initial_batch()
        batch["operations"].extend(
            [
                {
                    "op": "upsert_node",
                    "flow": "flow:upload",
                    "node": {
                        "id": "n:upload:resize",
                        "kind": "Do",
                        "title": "Resize the photo",
                    },
                },
                {
                    "op": "upsert_node",
                    "flow": "flow:upload",
                    "node": {
                        "id": "n:upload:scan",
                        "kind": "Do",
                        "title": "Scan the photo",
                    },
                },
                {
                    "op": "upsert_node",
                    "flow": "flow:upload",
                    "node": {
                        "id": "n:upload:notify",
                        "kind": "Do",
                        "title": "Notify the person",
                    },
                },
                {
                    "op": "upsert_edge",
                    "flow": "flow:upload",
                    "edge": {
                        "id": "e:upload:save:resize",
                        "source": "n:upload:save",
                        "target": "n:upload:resize",
                        "kind": "normal",
                    },
                },
                {
                    "op": "upsert_edge",
                    "flow": "flow:upload",
                    "edge": {
                        "id": "e:upload:resize:scan",
                        "source": "n:upload:resize",
                        "target": "n:upload:scan",
                        "kind": "normal",
                    },
                },
                {
                    "op": "upsert_edge",
                    "flow": "flow:upload",
                    "edge": {
                        "id": "e:upload:scan:notify",
                        "source": "n:upload:scan",
                        "target": "n:upload:notify",
                        "kind": "normal",
                    },
                },
            ]
        )
        return batch

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

    def test_rejects_invalid_evidence_refs(self):
        with tempfile.TemporaryDirectory() as temp_root:
            workspace = self._workspace(temp_root)
            batch = self._initial_batch()
            batch["operations"][2]["node"]["evidence_refs"] = ["src/upload.ts:12", ""]

            with self.assertRaises(CanvasStoreError) as raised:
                apply_operation_batch(workspace, batch)

            self.assertEqual(raised.exception.code, "INVALID_EVIDENCE_REF")
            self.assertEqual(raised.exception.details["node"], "n:upload:start")
            self.assertFalse((workspace / ".agentcanvas" / "canvas.ir.json").exists())

    def test_rejects_unknown_node_status(self):
        with tempfile.TemporaryDirectory() as temp_root:
            workspace = self._workspace(temp_root)
            batch = self._initial_batch()
            batch["operations"][2]["node"]["status"] = "guessed"

            with self.assertRaises(CanvasStoreError) as raised:
                apply_operation_batch(workspace, batch)

            self.assertEqual(raised.exception.code, "UNKNOWN_STATUS")
            self.assertEqual(raised.exception.details["status"], "guessed")
            self.assertFalse((workspace / ".agentcanvas" / "canvas.ir.json").exists())

    def test_rejects_invalid_confidence_shape(self):
        with tempfile.TemporaryDirectory() as temp_root:
            workspace = self._workspace(temp_root)
            batch = self._initial_batch()
            batch["operations"][1]["flow"]["confidence"] = {"level": "certain"}

            with self.assertRaises(CanvasStoreError) as raised:
                apply_operation_batch(workspace, batch)

            self.assertEqual(raised.exception.code, "INVALID_CONFIDENCE")
            self.assertEqual(raised.exception.details["level"], "certain")
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

    def test_churn_guard_allows_small_deletes_below_count_floor(self):
        with tempfile.TemporaryDirectory() as temp_root:
            workspace = self._workspace(temp_root)
            apply_operation_batch(workspace, self._initial_batch())

            result = apply_operation_batch(
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

            self.assertEqual(result["revision"], 2)

    def test_churn_guard_rejects_large_flow_rewrite_without_allow_rewrite(self):
        with tempfile.TemporaryDirectory() as temp_root:
            workspace = self._workspace(temp_root)
            apply_operation_batch(workspace, self._five_node_batch())

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
                            },
                            {
                                "op": "delete_node",
                                "flow": "flow:upload",
                                "target": "n:upload:resize",
                            },
                            {
                                "op": "delete_node",
                                "flow": "flow:upload",
                                "target": "n:upload:scan",
                            },
                            {
                                "op": "delete_node",
                                "flow": "flow:upload",
                                "target": "n:upload:notify",
                            },
                        ],
                    },
                )

            self.assertEqual(raised.exception.code, "ID_CHURN")
            envelope = raised.exception.to_dict()
            self.assertEqual(envelope["error"]["details"]["scope"], "flow")
            self.assertEqual(envelope["error"]["details"]["flow"], "flow:upload")
            self.assertEqual(
                envelope["error"]["details"]["vanished_ids"],
                [
                    "n:upload:notify",
                    "n:upload:resize",
                    "n:upload:save",
                    "n:upload:scan",
                ],
            )
            self.assertTrue(envelope["error"]["repair_hint"])

    def test_churn_guard_rejects_document_sweep_without_allow_rewrite(self):
        with tempfile.TemporaryDirectory() as temp_root:
            workspace = self._workspace(temp_root)
            apply_operation_batch(
                workspace,
                {
                    "base_revision": 0,
                    "operations": [
                        {"op": "set_app", "app": {"name": "Two flow app"}},
                        {
                            "op": "upsert_flow",
                            "flow": {
                                "id": "flow:first",
                                "title": "First flow",
                                "entry_node": "n:first:start",
                            },
                        },
                        {
                            "op": "upsert_flow",
                            "flow": {
                                "id": "flow:second",
                                "title": "Second flow",
                                "entry_node": "n:second:start",
                            },
                        },
                        *[
                            {
                                "op": "upsert_node",
                                "flow": flow,
                                "node": {"id": node_id, "kind": "Do", "title": node_id},
                            }
                            for flow, node_id in [
                                ("flow:first", "n:first:start"),
                                ("flow:first", "n:first:middle"),
                                ("flow:first", "n:first:end"),
                                ("flow:second", "n:second:start"),
                                ("flow:second", "n:second:middle"),
                                ("flow:second", "n:second:end"),
                            ]
                        ],
                    ],
                },
            )

            with self.assertRaises(CanvasStoreError) as raised:
                apply_operation_batch(
                    workspace,
                    {
                        "base_revision": 1,
                        "operations": [
                            {
                                "op": "delete_node",
                                "flow": "flow:first",
                                "target": "n:first:middle",
                            },
                            {
                                "op": "delete_node",
                                "flow": "flow:first",
                                "target": "n:first:end",
                            },
                            {
                                "op": "delete_node",
                                "flow": "flow:second",
                                "target": "n:second:middle",
                            },
                        ],
                    },
                )

            self.assertEqual(raised.exception.code, "ID_CHURN")
            self.assertEqual(raised.exception.details["scope"], "document")
            self.assertEqual(raised.exception.details["vanished_count"], 3)

    def test_allow_rewrite_records_reason_and_tombstones_open_pending_refs(self):
        with tempfile.TemporaryDirectory() as temp_root:
            workspace = self._workspace(temp_root)
            apply_operation_batch(workspace, self._five_node_batch())
            pending_dir = workspace / ".agentcanvas" / "pending"
            pending_dir.mkdir(parents=True, exist_ok=True)
            pending_path = pending_dir / "change.json"
            pending_path.write_text(
                json.dumps(
                    {
                        "id": "change",
                        "status": "pending",
                        "change": {
                            "journeyId": "flow:upload",
                            "targetNodeId": "n:upload:save",
                        },
                    }
                ),
                encoding="utf-8",
            )

            result = apply_operation_batch(
                workspace,
                {
                    "base_revision": 1,
                    "allow_rewrite": {"reason": "Replacing this flow with a clearer map."},
                    "operations": [
                        {
                            "op": "delete_flow",
                            "target": "flow:upload",
                        }
                    ],
                },
                authored_by="codex-rewrite-test",
            )

            self.assertEqual(result["revision"], 2)
            canvas = _read_json(workspace / ".agentcanvas" / "canvas.ir.json")
            self.assertEqual(canvas["flows"], [])
            self.assertEqual(
                canvas["metadata"]["last_allow_rewrite"]["reason"],
                "Replacing this flow with a clearer map.",
            )
            history = list_canvas_history(workspace)
            self.assertEqual(
                history["current"]["allow_rewrite_reason"],
                "Replacing this flow with a clearer map.",
            )
            self.assertEqual(history["current"]["op_summary"]["deleted_flow_count"], 1)
            pending = _read_json(pending_path)
            self.assertEqual(pending["refs"], [])
            self.assertEqual(
                {(ref["kind"], ref["id"]) for ref in pending["orphaned_refs"]},
                {("flow", "flow:upload"), ("node", "n:upload:save")},
            )

    def test_allow_rewrite_crash_recovery_restores_canvas_and_pending_refs(self):
        with tempfile.TemporaryDirectory() as temp_root:
            workspace = self._workspace(temp_root)
            apply_operation_batch(workspace, self._five_node_batch())
            original_canvas = _read_json(workspace / ".agentcanvas" / "canvas.ir.json")
            pending_dir = workspace / ".agentcanvas" / "pending"
            pending_dir.mkdir(parents=True, exist_ok=True)
            pending_path = pending_dir / "change.json"
            pending_path.write_text(
                json.dumps(
                    {
                        "id": "change",
                        "status": "pending",
                        "change": {
                            "journeyId": "flow:upload",
                            "targetNodeId": "n:upload:save",
                        },
                    }
                ),
                encoding="utf-8",
            )
            original_pending = _read_json(pending_path)
            original_flag = canvas_store.CRASH_AFTER_CANVAS_REPLACE_FOR_TESTS
            canvas_store.CRASH_AFTER_CANVAS_REPLACE_FOR_TESTS = True
            try:
                with self.assertRaises(RuntimeError):
                    apply_operation_batch(
                        workspace,
                        {
                            "base_revision": 1,
                            "allow_rewrite": {"reason": "Simulated rewrite crash."},
                            "operations": [
                                {
                                    "op": "delete_flow",
                                    "target": "flow:upload",
                                }
                            ],
                        },
                    )
            finally:
                canvas_store.CRASH_AFTER_CANVAS_REPLACE_FOR_TESTS = original_flag

            txn_paths = list((workspace / ".agentcanvas" / "history").glob("canvas.txn.*.json"))
            self.assertEqual(len(txn_paths), 1)
            txn_payload = _read_json(txn_paths[0])
            txn_payload["pid"] = 999999
            txn_payload["started_at_epoch"] = 0
            txn_paths[0].write_text(json.dumps(txn_payload), encoding="utf-8")

            recovered = load_canvas_document(workspace)

            self.assertEqual(recovered, original_canvas)
            self.assertEqual(_read_json(pending_path), original_pending)
            self.assertFalse((workspace / ".agentcanvas" / "history" / "canvas.1.json").exists())
            self.assertEqual(list((workspace / ".agentcanvas" / "history").glob("canvas.txn.*.json")), [])

    def test_history_lists_snapshots_and_restore_writes_new_revision(self):
        with tempfile.TemporaryDirectory() as temp_root:
            workspace = self._workspace(temp_root)
            apply_operation_batch(workspace, self._initial_batch())
            apply_operation_batch(
                workspace,
                {
                    "base_revision": 1,
                    "operations": [
                        {
                            "op": "set_app",
                            "app": {"name": "Photo Share 2"},
                        }
                    ],
                },
            )
            apply_operation_batch(
                workspace,
                {
                    "base_revision": 2,
                    "operations": [
                        {
                            "op": "set_app",
                            "app": {"name": "Photo Share 3"},
                        }
                    ],
                },
            )

            history = list_canvas_history(workspace)
            self.assertEqual(history["current_revision"], 3)
            self.assertEqual(
                [entry["revision"] for entry in history["history"]],
                [2, 1, 0],
            )
            self.assertEqual(history["current"]["flow_summary"]["count"], 1)
            self.assertEqual(history["current"]["flow_summary"]["titles"], ["Upload photo"])

            restored = restore_canvas_revision(
                workspace,
                1,
                base_revision=3,
                authored_by="codex-restore-test",
            )

            self.assertEqual(restored["revision"], 4)
            canvas = _read_json(workspace / ".agentcanvas" / "canvas.ir.json")
            self.assertEqual(canvas["revision"], 4)
            self.assertEqual(canvas["app"]["name"], "Photo Share")
            self.assertEqual(canvas["metadata"]["restored_from_revision"], 1)

    def test_cli_canvas_history_and_restore(self):
        with tempfile.TemporaryDirectory() as temp_root:
            workspace = self._workspace(temp_root)
            apply_operation_batch(workspace, self._initial_batch())
            apply_operation_batch(
                workspace,
                {
                    "base_revision": 1,
                    "operations": [
                        {
                            "op": "set_app",
                            "app": {"name": "Photo Share 2"},
                        }
                    ],
                },
            )

            history = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agentcanvas",
                    "canvas",
                    "history",
                    "--workspace",
                    str(workspace),
                ],
                cwd=temp_root,
                env=_agentcanvas_env(),
                text=True,
                capture_output=True,
                timeout=15,
            )

            self.assertEqual(history.returncode, 0, history.stdout + history.stderr)
            history_payload = json.loads(history.stdout)
            self.assertEqual(history_payload["current_revision"], 2)
            self.assertEqual(
                [entry["revision"] for entry in history_payload["history"]],
                [1, 0],
            )

            restore = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agentcanvas",
                    "canvas",
                    "restore",
                    "--workspace",
                    str(workspace),
                    "--revision",
                    "1",
                    "--base-revision",
                    "2",
                    "--authored-by",
                    "cli-restore-test",
                ],
                cwd=temp_root,
                env=_agentcanvas_env(),
                text=True,
                capture_output=True,
                timeout=15,
            )

            self.assertEqual(restore.returncode, 0, restore.stdout + restore.stderr)
            restore_payload = json.loads(restore.stdout)
            self.assertEqual(restore_payload["revision"], 3)
            canvas = _read_json(workspace / ".agentcanvas" / "canvas.ir.json")
            self.assertEqual(canvas["app"]["name"], "Photo Share")
            self.assertEqual(canvas["authored_by"], "cli-restore-test")

    def test_history_retention_prunes_oldest_snapshots_by_count(self):
        with tempfile.TemporaryDirectory() as temp_root:
            workspace = self._workspace(temp_root)
            original_limit = canvas_store.HISTORY_MAX_REVISIONS
            canvas_store.HISTORY_MAX_REVISIONS = 2
            try:
                apply_operation_batch(workspace, self._initial_batch())
                for revision in range(1, 5):
                    apply_operation_batch(
                        workspace,
                        {
                            "base_revision": revision,
                            "operations": [
                                {
                                    "op": "set_app",
                                    "app": {"name": "Photo Share %s" % revision},
                                }
                            ],
                        },
                    )
            finally:
                canvas_store.HISTORY_MAX_REVISIONS = original_limit

            history_files = sorted(
                path.name
                for path in (workspace / ".agentcanvas" / "history").glob("canvas.*.json")
                if path.name not in {"canvas.head.json", "canvas.pre-v2.json"}
            )
            self.assertEqual(history_files, ["canvas.3.json", "canvas.4.json"])

    def test_history_retention_prunes_snapshots_by_age(self):
        with tempfile.TemporaryDirectory() as temp_root:
            workspace = self._workspace(temp_root)
            apply_operation_batch(workspace, self._initial_batch())
            old_snapshot = workspace / ".agentcanvas" / "history" / "canvas.0.json"
            os.utime(old_snapshot, (0, 0))

            apply_operation_batch(
                workspace,
                {
                    "base_revision": 1,
                    "operations": [
                        {
                            "op": "set_app",
                            "app": {"name": "Photo Share 2"},
                        }
                    ],
                },
            )

            self.assertFalse(old_snapshot.exists())
            self.assertTrue((workspace / ".agentcanvas" / "history" / "canvas.1.json").exists())

    def test_history_retention_prunes_snapshots_by_size(self):
        with tempfile.TemporaryDirectory() as temp_root:
            workspace = self._workspace(temp_root)
            original_limit = canvas_store.HISTORY_MAX_BYTES
            canvas_store.HISTORY_MAX_BYTES = 1
            try:
                apply_operation_batch(workspace, self._initial_batch())
            finally:
                canvas_store.HISTORY_MAX_BYTES = original_limit

            history_files = [
                path
                for path in (workspace / ".agentcanvas" / "history").glob("canvas.*.json")
                if path.name not in {"canvas.head.json", "canvas.pre-v2.json", "canvas.txn.json"}
            ]
            self.assertEqual(history_files, [])

    def test_manual_edit_reconciliation_snapshots_previous_and_bumps_revision(self):
        with tempfile.TemporaryDirectory() as temp_root:
            workspace = self._workspace(temp_root)
            apply_operation_batch(workspace, self._initial_batch())
            canvas_path = workspace / ".agentcanvas" / "canvas.ir.json"
            manually_edited = _read_json(canvas_path)
            manually_edited["app"]["name"] = "Manually renamed"
            canvas_path.write_text(json.dumps(manually_edited), encoding="utf-8")

            reconciled = load_canvas_document(workspace)

            self.assertEqual(reconciled["revision"], 2)
            self.assertEqual(reconciled["authored_by"], "manual-edit")
            self.assertEqual(reconciled["app"]["name"], "Manually renamed")
            self.assertEqual(
                _read_json(workspace / ".agentcanvas" / "history" / "canvas.1.json")["app"]["name"],
                "Photo Share",
            )


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
