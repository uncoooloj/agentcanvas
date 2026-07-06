import json
import tempfile
import unittest
from pathlib import Path

from agentcanvas.canvas_v2.pending_refs import (
    list_open_referenced_ids,
    migrate_pending_refs,
    normalize_pending_record,
    tombstone_deleted_refs,
)


class CanvasV2PendingRefsTests(unittest.TestCase):
    maxDiff = None

    def test_normalizes_refs_from_legacy_change_fields(self):
        record = {
            "id": "change-1",
            "status": "pending",
            "refs": [{"kind": "node", "id": "n:existing", "flow": "flow:checkout"}],
            "change": {
                "journeyId": "flow:checkout",
                "targetNodeId": "n:payment",
                "targetStep": "n:review",
                "operations": [
                    {"flowId": "flow:returns"},
                    {"nodeId": "n:return-label"},
                    {"targetStep": {"id": "n:return-confirm"}},
                    {"flows": [{"id": "flow:support"}]},
                    {"nodes": [{"id": "n:support-ticket"}]},
                ],
            },
        }

        normalized = normalize_pending_record(record)

        self.assertEqual(normalized["orphaned_refs"], [])
        refs = {(ref["kind"], ref["id"], ref.get("flow")) for ref in normalized["refs"]}
        self.assertEqual(
            refs,
            {
                ("node", "n:existing", "flow:checkout"),
                ("flow", "flow:checkout", None),
                ("node", "n:payment", "flow:checkout"),
                ("node", "n:review", "flow:checkout"),
                ("flow", "flow:returns", None),
                ("node", "n:return-label", "flow:checkout"),
                ("node", "n:return-confirm", "flow:checkout"),
                ("flow", "flow:support", None),
                ("node", "n:support-ticket", "flow:checkout"),
            },
        )

    def test_migrates_pending_json_files_in_place(self):
        with tempfile.TemporaryDirectory() as temp_root:
            workspace = Path(temp_root) / "workspace"
            pending_dir = workspace / ".agentcanvas" / "pending"
            pending_dir.mkdir(parents=True)
            pending_path = pending_dir / "change.json"
            pending_path.write_text(
                json.dumps(
                    {
                        "id": "change",
                        "status": "pending",
                        "change": {
                            "journeyId": "flow:signup",
                            "targetStep": "n:add-email",
                        },
                    }
                ),
                encoding="utf-8",
            )

            migrated = migrate_pending_refs(workspace)

            self.assertEqual(len(migrated), 1)
            written = _read_json(pending_path)
            self.assertEqual(
                written["refs"],
                [
                    {"kind": "flow", "id": "flow:signup", "source": "change.journeyId"},
                    {
                        "kind": "node",
                        "id": "n:add-email",
                        "flow": "flow:signup",
                        "source": "change.targetStep",
                    },
                ],
            )
            self.assertEqual(written["orphaned_refs"], [])

    def test_lists_only_open_referenced_ids(self):
        with tempfile.TemporaryDirectory() as temp_root:
            workspace = Path(temp_root) / "workspace"
            pending_dir = workspace / ".agentcanvas" / "pending"
            pending_dir.mkdir(parents=True)
            (pending_dir / "open.json").write_text(
                json.dumps(
                    {
                        "id": "open",
                        "status": "in_progress",
                        "change": {"journeyId": "flow:signup", "targetNodeId": "n:email"},
                    }
                ),
                encoding="utf-8",
            )
            (pending_dir / "done.json").write_text(
                json.dumps(
                    {
                        "id": "done",
                        "status": "done",
                        "change": {"journeyId": "flow:closed", "targetNodeId": "n:closed"},
                    }
                ),
                encoding="utf-8",
            )

            refs = list_open_referenced_ids(workspace)

            self.assertEqual(refs, {("flow", "flow:signup"), ("node", "n:email")})

    def test_lists_null_status_as_pending_reference(self):
        with tempfile.TemporaryDirectory() as temp_root:
            workspace = Path(temp_root) / "workspace"
            pending_dir = workspace / ".agentcanvas" / "pending"
            pending_dir.mkdir(parents=True)
            (pending_dir / "legacy-null-status.json").write_text(
                json.dumps(
                    {
                        "id": "legacy-null-status",
                        "status": None,
                        "refs": [{"kind": "node", "id": "n:legacy", "flow": "flow:signup"}],
                    }
                ),
                encoding="utf-8",
            )

            refs = list_open_referenced_ids(workspace)

            self.assertEqual(refs, {("node", "n:legacy")})

    def test_tombstones_deleted_node_and_flow_refs(self):
        with tempfile.TemporaryDirectory() as temp_root:
            workspace = Path(temp_root) / "workspace"
            pending_dir = workspace / ".agentcanvas" / "pending"
            pending_dir.mkdir(parents=True)
            pending_path = pending_dir / "change.json"
            pending_path.write_text(
                json.dumps(
                    {
                        "id": "change",
                        "status": "pending",
                        "change": {
                            "journeyId": "flow:checkout",
                            "targetNodeId": "n:payment",
                            "targetStep": "n:review",
                        },
                    }
                ),
                encoding="utf-8",
            )

            tombstone_deleted_refs(
                workspace,
                deleted_nodes=["n:payment"],
                deleted_flows=["flow:checkout"],
                timestamp="2026-07-05T12:00:00Z",
            )

            written = _read_json(pending_path)
            self.assertEqual(
                written["refs"],
                [
                    {
                        "kind": "node",
                        "id": "n:review",
                        "flow": "flow:checkout",
                        "source": "change.targetStep",
                    }
                ],
            )
            self.assertEqual(
                written["orphaned_refs"],
                [
                    {
                        "kind": "flow",
                        "id": "flow:checkout",
                        "source": "change.journeyId",
                        "orphaned_at": "2026-07-05T12:00:00Z",
                    },
                    {
                        "kind": "node",
                        "id": "n:payment",
                        "flow": "flow:checkout",
                        "source": "change.targetNodeId",
                        "orphaned_at": "2026-07-05T12:00:00Z",
                    },
                ],
            )
            self.assertEqual(list_open_referenced_ids(workspace), {("node", "n:review")})


def _read_json(path):
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


if __name__ == "__main__":
    unittest.main()
