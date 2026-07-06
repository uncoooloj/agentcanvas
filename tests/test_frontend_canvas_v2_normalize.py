import json
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

from agentcanvas.canvas_v2 import flatten_canvas_v2


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_ROOT = PROJECT_ROOT / "frontend"
FIXTURE_DIR = PROJECT_ROOT / "tests" / "fixtures" / "canvas_v2"


class FrontendCanvasV2NormalizeTests(unittest.TestCase):
    maxDiff = None

    def test_normalize_canvas_payload_accepts_v2_envelope_for_every_fixture(self):
        envelopes = []
        for path in sorted(FIXTURE_DIR.glob("*.json")):
            with path.open(encoding="utf-8") as handle:
                canvas_v2 = json.load(handle)
            envelopes.append(
                {
                    "name": path.name,
                    "payload": {
                        "ok": True,
                        "revision": canvas_v2.get("revision", 0),
                        "canvas": flatten_canvas_v2(canvas_v2),
                        "canvas_v2": canvas_v2,
                    },
                }
            )

        with tempfile.TemporaryDirectory() as temp_root:
            script_path = Path(temp_root) / "normalize-v2-envelope.cjs"
            script_path.write_text(_node_script(), encoding="utf-8")
            completed = subprocess.run(
                [
                    "node",
                    str(script_path),
                    str(FRONTEND_ROOT / "src" / "lib" / "api.ts"),
                    str(FRONTEND_ROOT / "node_modules" / "typescript"),
                ],
                input=json.dumps(envelopes),
                cwd=str(FRONTEND_ROOT),
                text=True,
                capture_output=True,
                timeout=20,
            )

        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        result = json.loads(completed.stdout)
        self.assertEqual(result["checked"], sorted(path.name for path in FIXTURE_DIR.glob("*.json")))


def _node_script():
    return textwrap.dedent(
        """
        const fs = require("fs");
        const vm = require("vm");
        const ts = require(process.argv[3]);

        const apiPath = process.argv[2];
        const source = fs.readFileSync(apiPath, "utf8");
        const compiled = ts.transpileModule(source, {
          compilerOptions: {
            module: ts.ModuleKind.CommonJS,
            target: ts.ScriptTarget.ES2020,
          },
        }).outputText;

        const localModule = { exports: {} };
        const localRequire = (id) => {
          if (id === "./types") {
            return {
              CanvasStepKind: {
                When: "when",
                Do: "do",
                If: "if",
                ElseIf: "elseIf",
                Else: "else",
              },
              CanvasV2Schema: {
                Canvas: "agentcanvas.canvas.v2",
              },
              CanvasV2NodeKind: {
                When: "When",
                Do: "Do",
                Decision: "Decision",
                Loop: "Loop",
                Parallel: "Parallel",
                Join: "Join",
                Wait: "Wait",
                SubFlow: "SubFlow",
                End: "End",
              },
              CanvasV2EdgeKind: {
                Normal: "normal",
                Branch: "branch",
                LoopBody: "loop_body",
                LoopBack: "loop_back",
                LoopExit: "loop_exit",
                Parallel: "parallel",
                Error: "error",
                Async: "async",
              },
              FlowNodeKind: {
                Step: "step",
                Branch: "branch",
              },
              MappingStageStatus: {
                Pending: "pending",
                Active: "active",
                Done: "done",
                Ready: "ready",
                Error: "error",
              },
              StepRole: {
                When: "when",
                Do: "do",
              },
              PendingStatus: {
                Pending: "pending",
                Sent: "sent",
                InProgress: "in_progress",
                Implemented: "implemented",
                NeedsInput: "needs_input",
                Blocked: "blocked",
                Verified: "verified",
                Done: "done",
                Cancelled: "cancelled",
                Rejected: "rejected",
              },
            };
          }
          return require(id);
        };
        const context = {
          module: localModule,
          exports: localModule.exports,
          require: localRequire,
          URL,
          URLSearchParams,
          fetch: async () => { throw new Error("fetch should not be called"); },
          window: { location: { search: "", origin: "http://localhost" } },
        };
        vm.createContext(context);
        vm.runInContext(compiled, context, { filename: apiPath });
        const normalizeCanvasPayload = localModule.exports.normalizeCanvasPayload;
        const normalizeCanvasResponse = localModule.exports.normalizeCanvasResponse;
        if (typeof normalizeCanvasPayload !== "function") {
          throw new Error("normalizeCanvasPayload was not exported");
        }
        if (typeof normalizeCanvasResponse !== "function") {
          throw new Error("normalizeCanvasResponse was not exported");
        }

        const input = JSON.parse(fs.readFileSync(0, "utf8"));
        const checked = [];
        for (const item of input) {
          const model = normalizeCanvasPayload(item.payload);
          if (!model.appName) throw new Error(`${item.name}: missing appName`);
          if (!Array.isArray(model.journeys) || model.journeys.length === 0) {
            throw new Error(`${item.name}: missing journeys`);
          }
          const displayKinds = new Set();
          let subFlowRef = null;
          function visit(nodes) {
            for (const node of nodes || []) {
              if (node.native?.nodeKind) displayKinds.add(node.native.nodeKind);
              if (node.native?.flowRef) subFlowRef = node.native.flowRef;
              if (node.then) visit(node.then);
              if (node.otherwise) visit(node.otherwise);
            }
          }
          for (const journey of model.journeys) visit(journey.nodes);
          const response = normalizeCanvasResponse(item.payload);
          if (response.revision !== item.payload.revision) {
            throw new Error(`${item.name}: revision was not preserved`);
          }
          if (!response.canvasV2 || response.canvasV2.schema !== "agentcanvas.canvas.v2") {
            throw new Error(`${item.name}: canvas_v2 was not preserved`);
          }
          const kinds = new Set();
          for (const flow of response.canvasV2.flows) {
            for (const node of flow.nodes) kinds.add(node.kind);
          }
          if (item.name === "all_node_kinds.json") {
            for (const expected of ["When", "Do", "Decision", "Loop", "Parallel", "Join", "Wait", "SubFlow", "End"]) {
              if (!kinds.has(expected)) throw new Error(`${item.name}: missing v2 kind ${expected}`);
              if (!displayKinds.has(expected)) throw new Error(`${item.name}: missing display native kind ${expected}`);
            }
            if (subFlowRef !== "flow:receipt-follow-up") {
              throw new Error(`${item.name}: SubFlow flowRef was not preserved`);
            }
          }
          checked.push(item.name);
        }
        checked.sort();
        process.stdout.write(JSON.stringify({ checked }));
        """
    )


if __name__ == "__main__":
    unittest.main()
