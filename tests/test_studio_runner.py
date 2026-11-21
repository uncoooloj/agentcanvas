import io
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from agentcanvas.runner import RunManager, detect_runners
from agentcanvas.graph import build_demo_studio_document
from agentcanvas.events import EventBus


class _Bus:
    def __init__(self):
        self.events = []

    def publish(self, event_type, payload):
        self.events.append((event_type, payload))


class _Process:
    def __init__(self, lines=(), code=0):
        self.stdout = io.StringIO("".join(json.dumps(line) + "\n" for line in lines))
        self.returncode = code
        self.pid = 99999999
        self.terminated = False
    def wait(self, timeout=None): return self.returncode
    def communicate(self, timeout=None): return ("", "")
    def poll(self): return self.returncode
    def terminate(self): self.terminated = True
    def kill(self): self.terminated = True


class StudioRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.bus = _Bus()

    def tearDown(self):
        self.temp.cleanup()

    def _document(self):
        document = build_demo_studio_document()
        document["workspace"] = str(self.root)
        return document

    def _manager(self, results):
        calls = []
        def factory(command, **kwargs):
            source = kwargs.get("stdin")
            prompt = source.read().decode("utf-8") if source is not None else ""
            calls.append((command, kwargs, prompt))
            return _Process(results.pop(0) if results else ())
        manager = RunManager(self.root, self.bus, command_factory=factory)
        manager._runner_info = {"preferred": "codex", "available": ["codex", "copy"]}
        return manager, calls

    def _wait(self, manager, run):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            current = manager.get_run(run["id"])
            if current["status"] != "running":
                return current
            time.sleep(0.01)
        self.fail("run did not reach its next state")

    def test_map_diff_plan_and_approved_build(self):
        document = self._document()
        map_events = [{"type": "thread.started", "thread_id": "thread-1"},
                      {"type": "item.completed", "item": {"type": "agent_message", "text": json.dumps(document)}},
                      {"type": "turn.completed"}]
        manager, calls = self._manager([map_events])
        mapped = self._wait(manager, manager.start_run("map", prompt="map it"))
        self.assertEqual(mapped["status"], "completed")
        self.assertEqual(mapped["thread_id"], "thread-1")
        self.assertIn("read-only", " ".join(calls[0][0]))
        self.assertTrue((self.root / ".agentcanvas" / "studio.json").exists())

        diff_events = [{"type": "item.completed", "item": {"type": "agent_message", "text": json.dumps(document)}},
                       {"type": "turn.completed"}]
        manager, calls = self._manager([diff_events])
        self.assertEqual(self._wait(manager, manager.start_run("diff", diff_base="HEAD"))["status"], "completed")
        self.assertIn("Workspace diff", calls[0][2])

        plan = {"status": "ready", "question": None, "plan_summary": "change node", "document": document}
        build = {"status": "ready", "question": None, "verification_summary": "tests passed", "document": document}
        manager, calls = self._manager([[{"type": "thread.started", "thread_id": "thread-p"},
                                         {"type": "item.completed", "item": {"type": "agent_message", "text": json.dumps(plan)}},
                                         {"type": "turn.completed"}],
                                        [{"type": "item.completed", "item": {"type": "agent_message", "text": json.dumps(build)}},
                                         {"type": "turn.completed"}]])
        planned = self._wait(manager, manager.start_run("plan", prompt="plan it"))
        self.assertEqual(planned["status"], "awaiting_approval")
        built = self._wait(manager, manager.answer_run(planned["id"], approve=True))
        self.assertEqual(built["status"], "completed")
        self.assertEqual(built["verification_summary"], "tests passed")
        self.assertIn("resume", calls[1][0])
        self.assertIn("workspace-write", " ".join(calls[1][0]))
        self.assertTrue(any(kind == "canvas.updated" for kind, _ in self.bus.events))
        self.assertTrue(any(kind == "run.log" for kind, _ in self.bus.events))

    def test_copy_fallback_and_broken_shim(self):
        manager, _ = self._manager([])
        copied = manager.start_run("plan", runner="copy")
        self.assertEqual(copied["status"], "copy_ready")
        self.assertIn("copy_prompt", copied)

        with patch("agentcanvas.runner.shutil.which", return_value="/bad/codex"):
            info = detect_runners(lambda command, **kwargs: _Process(code=1))
        self.assertEqual(info["preferred"], "copy")
        self.assertEqual(info["available"], ["copy"])

    @unittest.skipUnless(os.name == "posix", "requires POSIX process-group signals")
    def test_cancels_running_build_and_kills_a_term_resistant_process(self):
        script = (
            "import json, signal, time\n"
            "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
            "print(json.dumps({'type': 'thread.started', 'thread_id': 'stalled-build'}), flush=True)\n"
            "time.sleep(60)\n"
        )
        processes = []

        def factory(_command, **kwargs):
            process = subprocess.Popen([sys.executable, "-u", "-c", script], **kwargs)
            processes.append(process)
            return process

        manager = RunManager(self.root, self.bus, command_factory=factory)
        self.addCleanup(manager.shutdown)
        manager._runner_info = {"preferred": "codex", "available": ["codex", "copy"]}
        run_id = manager.start_run("build", prompt="implement checkout")["id"]
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and not manager.get_run(run_id)["thread_id"]:
            time.sleep(0.01)
        self.assertEqual(manager.get_run(run_id)["thread_id"], "stalled-build")
        with self.assertRaisesRegex(RuntimeError, "already running"):
            manager.start_run("build")
        self.assertEqual(manager.cancel_run(run_id)["status"], "cancelled")
        self.assertEqual(processes[0].wait(timeout=2), -signal.SIGKILL)
        self.assertFalse((self.root / ".agentcanvas" / "studio.json").exists())
        self.assertFalse(any(name == "canvas.updated" for name, _ in self.bus.events))

    def test_discards_a_persisted_proposal(self):
        plan = {"status": "ready", "question": None, "plan_summary": "Change checkout", "document": self._document()}
        result = {"type": "item.completed", "item": {"type": "agent_message", "text": json.dumps(plan)}}
        manager, _ = self._manager([[result]])
        proposed = self._wait(manager, manager.start_run("plan"))
        self.assertEqual(proposed["status"], "awaiting_approval")
        reloaded = RunManager(self.root, self.bus)
        self.assertEqual(reloaded.get_run(proposed["id"])["plan_summary"], "Change checkout")
        discarded = reloaded.discard_run(proposed["id"])
        self.assertEqual(discarded["status"], "cancelled")
        self.assertIsNone(discarded["proposed_document"])
        self.assertFalse((self.root / ".agentcanvas" / "studio.json").exists())

    def test_event_bus_drops_oldest_only_for_the_slow_subscriber(self):
        bus = EventBus(queue_size=2)
        slow, fast = bus.subscribe(), bus.subscribe()
        for index in range(3):
            bus.publish("run.log", {"sequence": index})
            self.assertEqual(fast.get_nowait(), ("run.log", {"sequence": index}))
            fast.task_done()
        self.assertEqual([slow.get_nowait()[1]["sequence"] for _ in range(2)], [1, 2])
        bus.unsubscribe(fast)
        bus.publish("run.log", {"sequence": 3})
        self.assertTrue(fast.empty())

    def test_event_bus_receives_run_lifecycle(self):
        document = self._document()
        bus = EventBus(queue_size=20)
        queue = bus.subscribe()
        manager = RunManager(self.root, bus, command_factory=lambda command, **kwargs: _Process([
            {"type": "item.completed", "item": {"type": "agent_message", "text": json.dumps(document)}},
            {"type": "turn.completed"},
        ]))
        manager._runner_info = {"preferred": "codex", "available": ["codex", "copy"]}
        run = self._wait(manager, manager.start_run("map"))
        received = [queue.get_nowait() for _ in range(queue.qsize())]
        self.assertEqual(run["status"], "completed")
        self.assertIn("run.updated", [kind for kind, _ in received])
        self.assertIn("canvas.updated", [kind for kind, _ in received])
        self.assertIn("studio.updated", [kind for kind, _ in received])

    def test_plan_needs_input_then_answer_and_approval(self):
        document = self._document()
        needs_input = {"status": "needs_input", "question": "Which retry policy?", "plan_summary": None, "document": None}
        ready_plan = {"status": "ready", "question": None, "plan_summary": "Add bounded retries", "document": document}
        built = {"status": "ready", "question": None, "verification_summary": "unit tests passed", "document": document}
        manager, calls = self._manager([
            [{"type": "thread.started", "thread_id": "thread-needs-input"},
             {"type": "item.completed", "item": {"type": "agent_message", "text": json.dumps(needs_input)}}],
            [{"type": "item.completed", "item": {"type": "agent_message", "text": json.dumps(ready_plan)}}],
            [{"type": "item.completed", "item": {"type": "agent_message", "text": json.dumps(built)}}],
        ])
        run = self._wait(manager, manager.start_run("plan", prompt="improve retry"))
        self.assertEqual((run["status"], run["question"]), ("needs_input", "Which retry policy?"))
        planned = self._wait(manager, manager.answer_run(run["id"], answer="Three attempts"))
        self.assertEqual(planned["status"], "awaiting_approval")
        completed = self._wait(manager, manager.answer_run(run["id"], approve=True))
        self.assertEqual(completed["status"], "completed")
        self.assertIn("resume", calls[1][0])
        self.assertIn("workspace-write", " ".join(calls[2][0]))
