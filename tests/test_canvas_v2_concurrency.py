import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from agentcanvas.canvas_v2 import CanvasStoreError, apply_operation_batch, load_canvas_document
from agentcanvas.workspace_lock import workspace_lock_path, workspace_write_lock


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _agentcanvas_env(extra=None):
    env = os.environ.copy()
    pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        str(PROJECT_ROOT)
        if not pythonpath
        else str(PROJECT_ROOT) + os.pathsep + pythonpath
    )
    if extra:
        env.update(extra)
    return env


_APPLY_WORKER = r"""
import json
import sys

from agentcanvas.canvas_v2 import CanvasStoreError, apply_operation_batch

workspace = sys.argv[1]
name = sys.argv[2]
batch = {
    "base_revision": 1,
    "operations": [
        {"op": "set_app", "app": {"name": name, "summary": "Concurrent edit"}}
    ],
}
try:
    result = apply_operation_batch(workspace, batch, authored_by=name)
except CanvasStoreError as exc:
    print(json.dumps(exc.to_dict(), sort_keys=True))
    raise SystemExit(2)
print(json.dumps({"ok": True, "name": name, "revision": result["revision"]}, sort_keys=True))
"""


_LOCK_HOLDER = r"""
import sys
import time
from pathlib import Path

from agentcanvas.workspace_lock import workspace_write_lock

workspace = sys.argv[1]
ready = Path(sys.argv[2])
with workspace_write_lock(workspace, writer="test-holder"):
    ready.write_text("ready", encoding="utf-8")
    time.sleep(0.5)
"""


class CanvasV2ConcurrencyTests(unittest.TestCase):
    maxDiff = None

    def _workspace(self, temp_root):
        workspace = Path(temp_root) / "workspace"
        workspace.mkdir()
        return workspace

    def _initial_batch(self):
        return {
            "base_revision": 0,
            "authored_by": "concurrency-test",
            "operations": [
                {"op": "set_app", "app": {"name": "Photo Share"}},
                {
                    "op": "upsert_flow",
                    "flow": {
                        "id": "flow:upload",
                        "title": "Upload photo",
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
            ],
        }

    def test_interleaved_apply_from_same_base_allows_exactly_one_writer(self):
        for paused_name, competing_name in [
            ("paused-first", "competing-second"),
            ("paused-second", "competing-first"),
        ]:
            with self.subTest(paused=paused_name):
                with tempfile.TemporaryDirectory() as temp_root:
                    workspace = self._workspace(temp_root)
                    apply_operation_batch(workspace, self._initial_batch())
                    marker = Path(temp_root) / "paused.marker"
                    release = Path(temp_root) / "release.marker"
                    paused = subprocess.Popen(
                        [sys.executable, "-c", _APPLY_WORKER, str(workspace), paused_name],
                        cwd=temp_root,
                        env=_agentcanvas_env(
                            {
                                "AGENTCANVAS_TEST_PAUSE_AFTER_REVISION_CHECK": str(marker),
                                "AGENTCANVAS_TEST_RELEASE_AFTER_REVISION_CHECK": str(release),
                            }
                        ),
                        text=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                    )
                    self._wait_for_marker(marker, paused)

                    competing = subprocess.Popen(
                        [sys.executable, "-c", _APPLY_WORKER, str(workspace), competing_name],
                        cwd=temp_root,
                        env=_agentcanvas_env(),
                        text=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                    )
                    time.sleep(0.05)
                    release.write_text("go", encoding="utf-8")

                    paused_out, paused_err = paused.communicate(timeout=10)
                    competing_out, competing_err = competing.communicate(timeout=10)
                    payloads = [
                        self._payload(paused.returncode, paused_out, paused_err),
                        self._payload(competing.returncode, competing_out, competing_err),
                    ]

                    winners = [payload for payload in payloads if payload.get("ok")]
                    losers = [payload for payload in payloads if not payload.get("ok")]
                    self.assertEqual(len(winners), 1, payloads)
                    self.assertEqual(len(losers), 1, payloads)
                    self.assertIn(losers[0]["error"]["code"], {"REVISION_CONFLICT", "WORKSPACE_BUSY"})
                    self.assertEqual(load_canvas_document(workspace)["revision"], 2)
                    self.assertEqual(load_canvas_document(workspace)["app"]["name"], winners[0]["name"])

    def test_workspace_busy_timeout_is_structured(self):
        with tempfile.TemporaryDirectory() as temp_root:
            workspace = self._workspace(temp_root)
            apply_operation_batch(workspace, self._initial_batch())
            ready = Path(temp_root) / "holder.ready"
            holder = subprocess.Popen(
                [sys.executable, "-c", _LOCK_HOLDER, str(workspace), str(ready)],
                cwd=temp_root,
                env=_agentcanvas_env(),
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            try:
                self._wait_for_marker(ready, holder)
                old_timeout = os.environ.get("AGENTCANVAS_LOCK_TIMEOUT_SECONDS")
                os.environ["AGENTCANVAS_LOCK_TIMEOUT_SECONDS"] = "0.05"
                try:
                    with self.assertRaises(CanvasStoreError) as raised:
                        apply_operation_batch(
                            workspace,
                            {
                                "base_revision": 1,
                                "operations": [
                                    {"op": "set_app", "app": {"name": "Busy loser"}}
                                ],
                            },
                        )
                finally:
                    if old_timeout is None:
                        os.environ.pop("AGENTCANVAS_LOCK_TIMEOUT_SECONDS", None)
                    else:
                        os.environ["AGENTCANVAS_LOCK_TIMEOUT_SECONDS"] = old_timeout
                self.assertEqual(raised.exception.code, "WORKSPACE_BUSY")
                self.assertTrue(raised.exception.details["retryable"])
            finally:
                holder.communicate(timeout=10)

    def test_stale_dead_pid_lock_can_be_broken(self):
        with tempfile.TemporaryDirectory() as temp_root:
            workspace = self._workspace(temp_root)
            lock_path = workspace_lock_path(workspace)
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            lock_path.write_text(
                json.dumps(
                    {
                        "schema": "agentcanvas.workspace_lock.v1",
                        "pid": 99999999,
                        "writer": "dead-writer",
                        "acquired_at_epoch": 0,
                    }
                ),
                encoding="utf-8",
            )

            with workspace_write_lock(workspace, writer="breaker", lease_seconds=0.01) as lock:
                self.assertTrue(lock.break_events)
                self.assertTrue(lock_path.exists())

            self.assertFalse(lock_path.exists())
            break_log = workspace / ".agentcanvas" / "history" / "workspace-lock.breaks.jsonl"
            self.assertTrue(break_log.is_file())
            self.assertIn("dead-writer", break_log.read_text(encoding="utf-8"))

    def test_live_transaction_journal_is_left_untouched(self):
        with tempfile.TemporaryDirectory() as temp_root:
            workspace = self._workspace(temp_root)
            apply_operation_batch(workspace, self._initial_batch())
            canvas = load_canvas_document(workspace)
            history_dir = workspace / ".agentcanvas" / "history"
            txn_path = history_dir / ("canvas.txn.%s-live.json" % os.getpid())
            txn_path.write_text(
                json.dumps(
                    {
                        "schema": "agentcanvas.canvas_transaction.v1",
                        "pid": os.getpid(),
                        "started_at_epoch": time.time(),
                        "previous_canvas": canvas,
                    }
                ),
                encoding="utf-8",
            )

            loaded = load_canvas_document(workspace)

            self.assertEqual(loaded["revision"], 1)
            self.assertTrue(txn_path.exists())

    def _wait_for_marker(self, marker, process):
        for _ in range(500):
            if marker.exists():
                return
            if process.poll() is not None:
                stdout, stderr = process.communicate()
                self.fail("process exited before marker\nSTDOUT:%s\nSTDERR:%s" % (stdout, stderr))
            time.sleep(0.01)
        self.fail("timed out waiting for %s" % marker)

    def _payload(self, returncode, stdout, stderr):
        self.assertIn(returncode, {0, 2}, stdout + stderr)
        try:
            return json.loads(stdout)
        except ValueError:
            self.fail("worker did not return JSON\nSTDOUT:%s\nSTDERR:%s" % (stdout, stderr))


if __name__ == "__main__":
    unittest.main()
