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
        self.assertEqual(
            result["clients"],
            [
                "answer-pending",
                "apply-error",
                "apply-success",
                "health",
                "history",
                "pending-detail",
                "restore",
            ],
        )


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
              CanvasMappingMode: {
                AgentAuthored: "agent-authored",
                Deterministic: "deterministic",
                Empty: "empty",
                Heuristic: "heuristic",
                HeuristicProjection: "heuristic-projection",
                LlmAssisted: "llm-assisted",
                V2Compat: "v2-compat",
              },
              CanvasSourceKind: {
                AgentAuthored: "agent-authored",
                HeuristicProjection: "heuristic-projection",
                Demo: "demo",
                DemoFallback: "demo-fallback",
                Empty: "empty",
                Workspace: "workspace",
                StaleCache: "stale-cache",
                NoFlow: "no-flow",
                Loading: "loading",
                Error: "error",
                Unknown: "unknown",
              },
              CanvasSourceStatus: {
                Ready: "ready",
                Demo: "demo",
                DemoFallback: "demo_fallback",
                Empty: "empty",
                StaleCache: "stale_cache",
                Workspace: "workspace",
              },
              CanvasSourceReason: {
                DemoWorkspace: "demo_workspace",
                LaunchPageWithoutWorkspace: "launch_page_without_workspace",
                RequestedDemoWorkspace: "requested_demo_workspace",
              },
              ConversationRole: {
                Agent: "agent",
                User: "user",
              },
              ConversationTurnKind: {
                Question: "question",
                Answer: "answer",
                Note: "note",
              },
              MapFreshnessStatus: {
                Unknown: "unknown",
                Stale: "stale",
                Fresh: "fresh",
              },
              MapHealthStatus: {
                Ready: "ready",
                MissingWorkflowIr: "missing_workflow_ir",
                MissingCanvasIr: "missing_canvas_ir",
                UnreadableCanvasIr: "unreadable_canvas_ir",
                StaleCanvasIr: "stale_canvas_ir",
              },
              MapHealthReason: {
                Missing: "missing",
                InvalidJson: "invalid_json",
                InvalidShape: "invalid_shape",
                Unreadable: "unreadable",
              },
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
              LegacyPendingStatus: {
                Queued: "queued",
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

        function response(status, payload) {
          return {
            ok: status >= 200 && status < 300,
            status,
            statusText: status >= 200 && status < 300 ? "OK" : "Error",
            json: async () => payload,
          };
        }

        function queueFetch(context, routes) {
          const calls = [];
          context.window.location.search = "?token=test-token&sessionId=session-1";
          context.fetch = async (requestUrl, options = {}) => {
            const url = new URL(String(requestUrl));
            const method = options.method || "GET";
            const key = `${method} ${url.pathname}`;
            const items = routes.get(key);
            if (!items || !items.length) {
              throw new Error(`Unexpected fetch ${key}`);
            }
            calls.push({ key, url, options });
            return response(...items.shift());
          };
          return calls;
        }

        async function runClientChecks(api, context) {
          const routes = new Map([
            ["GET /api/health", [[200, { ok: true, health: {
              schema: "agentcanvas.map_health.v1",
              workspacePath: "/workspace",
              stateDir: { path: "/workspace/.agentcanvas", relativePath: ".agentcanvas", exists: true },
              workflowIr: { path: "/workspace/.agentcanvas/workflow.ir.json", relativePath: ".agentcanvas/workflow.ir.json", exists: true },
              canvasIr: { path: "/workspace/.agentcanvas/canvas.ir.json", relativePath: ".agentcanvas/canvas.ir.json", exists: true, readable: true, reason: null, error: null },
              freshness: { status: "stale", stale: true, reason: "Canvas map is older." },
              pendingFiles: { path: "/workspace/.agentcanvas/pending", relativePath: ".agentcanvas/pending", exists: true, readable: true, fileCount: 2, changeCount: 1, error: null },
              status: "stale_canvas_ir",
              ready: false,
              summary: ["Freshness: stale"],
            } }]]],
            ["GET /api/canvas/history", [[200, { ok: true, current_revision: 2, current: { revision: 2, authored_by: "codex", updated_at: "now", path: "/canvas", size_bytes: 12, op_summary: { operation_count: 1 }, allow_rewrite_reason: null }, history: [{ revision: 1, authored_by: "agent", updated_at: "then", path: "/history/1", size_bytes: 10, op_summary: {}, allow_rewrite_reason: "cleanup" }] }]]],
            ["POST /api/canvas/apply", [
              [200, { ok: true, auto_migrated: false, dry_run: false, revision: 3, base_revision: 2, path: "/canvas" }],
              [409, { ok: false, revision: 3, error: { code: "REVISION_CONFLICT", message: "base_revision does not match", details: { current_revision: 3 } } }],
            ]],
            ["POST /api/canvas/restore", [[200, { ok: true, revision: 4, base_revision: 3, restored_revision: 1, path: "/canvas" }]]],
            ["GET /api/pending/request-1", [[200, { ok: true, pending: {
              id: "request-1",
              title: "Clarify checkout",
              status: "needs_input",
              conversation_summary: { turns: 1, last_role: "agent", last_kind: "question", last_at: "t1", unanswered_question: { id: "q1", text: "Which flow?", at: "t1" } },
              conversation: [{ id: "q1", at: "t1", role: "agent", kind: "question", text: "Which flow?" }],
            } }]]],
            ["POST /api/pending/request-1/answer", [[200, { ok: true, pending: {
              id: "request-1",
              title: "Clarify checkout",
              status: "in_progress",
              conversation_summary: { turns: 2, last_role: "user", last_kind: "answer", last_at: "t2", unanswered_question: null },
              conversation: [{ id: "a1", at: "t2", role: "user", kind: "answer", text: "Signup" }],
            } }]]],
          ]);
          const calls = queueFetch(context, routes);
          const checked = [];

          const health = await api.fetchMapHealth();
          if (health.status !== "stale_canvas_ir" || health.freshness.status !== "stale" || health.pendingFiles.changeCount !== 1) {
            throw new Error("health client did not normalize map health");
          }
          checked.push("health");

          const history = await api.fetchCanvasHistory();
          if (history.currentRevision !== 2 || history.history[0].allowRewriteReason !== "cleanup") {
            throw new Error("history client did not normalize history");
          }
          checked.push("history");

          const apply = await api.applyCanvasBatch({ base_revision: 2, operations: [{ op: "set_app" }] });
          if (apply.revision !== 3 || apply.baseRevision !== 2) {
            throw new Error("apply client did not normalize apply result");
          }
          const applyCall = calls.find((call) => call.key === "POST /api/canvas/apply");
          if (!applyCall || JSON.parse(applyCall.options.body).base_revision !== 2) {
            throw new Error("apply client did not send operation batch");
          }
          checked.push("apply-success");

          const restore = await api.restoreCanvasRevision({ revision: 1, baseRevision: 3, authoredBy: "web" });
          if (restore.restoredRevision !== 1 || restore.baseRevision !== 3) {
            throw new Error("restore client did not normalize restore result");
          }
          const restoreCall = calls.find((call) => call.key === "POST /api/canvas/restore");
          if (!restoreCall || JSON.parse(restoreCall.options.body).base_revision !== 3) {
            throw new Error("restore client did not send restore body");
          }
          checked.push("restore");

          const pending = await api.fetchPendingRequest("request-1", { since: "q0" });
          const pendingCall = calls.find((call) => call.key === "GET /api/pending/request-1");
          if (pending.status !== "needs_input" || pending.conversation?.[0]?.kind !== "question" || pendingCall.url.searchParams.get("since") !== "q0") {
            throw new Error("pending detail client did not normalize conversation or since");
          }
          checked.push("pending-detail");

          const answered = await api.answerPendingRequest("request-1", "Signup");
          const answerCall = calls.find((call) => call.key === "POST /api/pending/request-1/answer");
          if (answered.status !== "in_progress" || JSON.parse(answerCall.options.body).sessionId !== "session-1") {
            throw new Error("answer client did not post answer with session");
          }
          checked.push("answer-pending");

          try {
            await api.applyCanvasBatch({ base_revision: 2, operations: [] });
            throw new Error("apply conflict did not throw");
          } catch (error) {
            if (error.code !== "REVISION_CONFLICT" || error.details.current_revision !== 3) {
              throw error;
            }
          }
          checked.push("apply-error");

          for (const call of calls) {
            if (call.url.searchParams.get("token") !== "test-token" || call.url.searchParams.get("sessionId") !== "session-1") {
              throw new Error(`missing auth/session query on ${call.key}`);
            }
          }
          return checked.sort();
        }

        (async () => {
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
          const clients = await runClientChecks(localModule.exports, context);
          process.stdout.write(JSON.stringify({ checked, clients }));
        })().catch((error) => {
          console.error(error && error.stack ? error.stack : error);
          process.exit(1);
        });
        """
    )


if __name__ == "__main__":
    unittest.main()
