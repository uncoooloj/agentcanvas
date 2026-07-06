import json
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_ROOT = PROJECT_ROOT / "frontend"
FIXTURE_DIR = PROJECT_ROOT / "tests" / "fixtures" / "canvas_v2"


class FrontendCanvasV2LayoutTests(unittest.TestCase):
    maxDiff = None

    def test_layout_flow_is_deterministic_for_canvas_v2_fixtures(self):
        fixtures = []
        for path in sorted(FIXTURE_DIR.glob("*.json")):
            with path.open(encoding="utf-8") as handle:
                fixtures.append({"name": path.name, "canvas": json.load(handle)})

        with tempfile.TemporaryDirectory() as temp_root:
            script_path = Path(temp_root) / "layout-v2.cjs"
            script_path.write_text(_node_script(), encoding="utf-8")
            completed = subprocess.run(
                [
                    "node",
                    str(script_path),
                    str(FRONTEND_ROOT / "src" / "lib" / "canvasV2Layout.ts"),
                    str(FRONTEND_ROOT / "node_modules" / "typescript"),
                ],
                input=json.dumps(fixtures),
                cwd=str(FRONTEND_ROOT),
                text=True,
                capture_output=True,
                timeout=20,
            )

        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertEqual(
            json.loads(completed.stdout),
            {
                "checked": ["all_node_kinds.json", "photo_upload_combined.json"],
                "edgeKinds": ["branch", "error", "loop_back", "loop_body", "loop_exit", "normal", "parallel"],
                "nodeKinds": ["Decision", "Do", "End", "Join", "Loop", "Parallel", "SubFlow", "Wait", "When"],
            },
        )


def _node_script():
    return textwrap.dedent(
        """
        const fs = require("fs");
        const vm = require("vm");
        const ts = require(process.argv[3]);

        const source = fs.readFileSync(process.argv[2], "utf8");
        const compiled = ts.transpileModule(source, {
          compilerOptions: {
            module: ts.ModuleKind.CommonJS,
            target: ts.ScriptTarget.ES2020,
          },
        }).outputText;

        const localModule = { exports: {} };
        const context = {
          module: localModule,
          exports: localModule.exports,
          require,
        };
        vm.createContext(context);
        vm.runInContext(compiled, context, { filename: process.argv[2] });

        const { layoutFlow } = localModule.exports;
        const fixtures = JSON.parse(fs.readFileSync(0, "utf8"));
        const checked = [];
        const nodeKinds = new Set();
        const edgeKinds = new Set();

        for (const fixture of fixtures) {
          checked.push(fixture.name);
          for (const flow of fixture.canvas.flows) {
            const once = layoutFlow(flow);
            const twice = layoutFlow(flow);
            if (JSON.stringify(once) !== JSON.stringify(twice)) {
              throw new Error(`${fixture.name}/${flow.id}: layout is not deterministic`);
            }
            if (once.width <= 0 || once.height <= 0) {
              throw new Error(`${fixture.name}/${flow.id}: layout size is invalid`);
            }
            const laidOutNodes = new Set(once.nodes.map((node) => node.id));
            for (const node of flow.nodes) {
              nodeKinds.add(node.kind);
              if (!laidOutNodes.has(node.id)) {
                throw new Error(`${fixture.name}/${flow.id}: missing node ${node.id}`);
              }
            }
            const laidOutEdges = new Set(once.edges.map((edge) => edge.id));
            for (const edge of flow.edges) {
              edgeKinds.add(edge.kind);
              if (!laidOutEdges.has(edge.id)) {
                throw new Error(`${fixture.name}/${flow.id}: missing edge ${edge.id}`);
              }
            }
          }
        }

        process.stdout.write(JSON.stringify({
          checked,
          edgeKinds: [...edgeKinds].sort(),
          nodeKinds: [...nodeKinds].sort(),
        }));
        """
    )


if __name__ == "__main__":
    unittest.main()
