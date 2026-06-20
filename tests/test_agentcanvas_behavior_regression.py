import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping

from agentcanvas.core import app_surface_for_path
from agentcanvas.indexer import build_workflow_ir
from agentcanvas.projection import build_projection_contract


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_ROOT = PROJECT_ROOT / "frontend"

FIXTURE_PREFIXES = (
    "agentcanvas/demo_project/",
    "demo_projects/",
    "examples/",
    "tests/fixtures/",
)


def _write(root: Path, relative_path: str, content: str) -> None:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _path_strings(value: Any) -> Iterable[str]:
    if isinstance(value, Mapping):
        for key, item in value.items():
            lowered = str(key).lower()
            if lowered in {"file", "path", "source", "resolved_path"} and isinstance(item, str):
                yield item
            yield from _path_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _path_strings(item)
    elif isinstance(value, str) and "/" in value:
        yield value


def _is_fixture_path(path: str) -> bool:
    return path.startswith(FIXTURE_PREFIXES)


def _is_behavior_enabled(fact: Mapping[str, Any]) -> bool:
    attributes = fact.get("attributes")
    if not isinstance(attributes, Mapping):
        attributes = {}
    return not (
        fact.get("behavior_source") is False
        or fact.get("is_fixture") is True
        or fact.get("projection_role") in {"demo", "fixture", "test_fixture"}
        or attributes.get("behavior_source") is False
        or attributes.get("is_fixture") is True
        or attributes.get("projection_role") in {"demo", "fixture", "test_fixture"}
    )


def _agentcanvas_repo_fixture(root: Path) -> None:
    _write(
        root,
        "pyproject.toml",
        "\n".join(
            [
                "[project]",
                'name = "use-agentcanvas"',
                "",
                "[project.scripts]",
                'agentcanvas = "agentcanvas.cli:main"',
                "",
            ]
        ),
    )
    _write(root, "agentcanvas/cli.py", "def main():\n    return 0\n")
    _write(root, "agentcanvas/indexer.py", "def build_workflow_ir():\n    pass\n")
    _write(root, "agentcanvas/core/mapper.py", "def repo_facts_to_canvas_model():\n    pass\n")
    _write(
        root,
        "agentcanvas/demo_project/src/routes/orders.js",
        "router.post('/orders', createOrder)\n",
    )
    _write(
        root,
        "agentcanvas/demo_project/tests/order-flow.test.js",
        "test('order flow', () => {})\n",
    )
    _write(
        root,
        "demo_projects/agentcanvas-demo/src/routes/returns.js",
        "router.post('/returns', requestReturn)\n",
    )
    _write(
        root,
        "examples/sample-js-app/src/routes/checkout.js",
        "router.post('/checkout', checkout)\n",
    )
    _write(
        root,
        "tests/fixtures/js_ts/src/routes/checkout.ts",
        "router.post('/checkout', checkout)\n",
    )


class AgentCanvasBehaviorRegressionTests(unittest.TestCase):
    maxDiff = None

    def test_pyproject_scripts_create_python_cli_app_surface(self):
        with tempfile.TemporaryDirectory() as temp_root:
            root = Path(temp_root) / "agentcanvas"
            root.mkdir()
            _agentcanvas_repo_fixture(root)

            workflow_ir = build_workflow_ir(root)
            surfaces = workflow_ir.get("app_surfaces") or []
            root_surface = next(
                (surface for surface in surfaces if surface.get("root") == "."),
                None,
            )

            self.assertIsNotNone(
                root_surface,
                "Expected a root Python CLI/core app surface from pyproject.toml "
                "[project.scripts].",
            )
            self.assertIn("pyproject.toml", root_surface["manifest_paths"])
            self.assertIn("python", root_surface["languages"])
            self.assertEqual(
                root_surface["id"],
                app_surface_for_path("agentcanvas/cli.py", surfaces)["id"],
            )
            self.assertTrue(
                any(
                    hint.get("path") == "agentcanvas/cli.py"
                    and "entry" in hint.get("kind", "").lower()
                    for hint in root_surface.get("entry_hints") or []
                ),
                "Expected the project script to point at agentcanvas/cli.py as "
                "a CLI/core entrypoint.",
            )

    def test_demo_and_fixture_routes_are_not_behavior_sources(self):
        with tempfile.TemporaryDirectory() as temp_root:
            root = Path(temp_root) / "agentcanvas"
            root.mkdir()
            _agentcanvas_repo_fixture(root)

            workflow_ir = build_workflow_ir(root)
            behavior_route_facts = []
            for fact in workflow_ir["source_facts"]["facts"]:
                fact_paths = set(_path_strings(fact))
                if not fact_paths or not any(_is_fixture_path(path) for path in fact_paths):
                    continue
                if fact.get("kind") == "language_route":
                    behavior_route_facts.append(fact)
                    continue
                attributes = fact.get("attributes")
                node = attributes.get("node") if isinstance(attributes, Mapping) else None
                if isinstance(node, Mapping) and node.get("type") == "route":
                    behavior_route_facts.append(fact)

            promoted = [
                {"id": fact.get("id"), "paths": sorted(set(_path_strings(fact)))}
                for fact in behavior_route_facts
                if _is_behavior_enabled(fact)
            ]

            self.assertEqual(
                [],
                promoted,
                "Demo projects, examples, and test fixtures may be indexed as "
                "supporting code, but their routes must be filtered or marked so "
                "they cannot become product journeys.",
            )

    def test_projection_contract_rejects_raw_file_inventory_journeys(self):
        workflow_ir: Dict[str, Any] = {
            "schema": "agentcanvas.workflow_ir.v1",
            "version": "0.1.0",
            "workspace": {"root": "/tmp/agentcanvas", "name": "agentcanvas"},
            "summary": {"app_surfaces": 1},
            "package": {},
            "git": {},
            "focus": {},
            "app_surfaces": [
                {
                    "id": "app:root",
                    "root": ".",
                    "name": "AgentCanvas CLI",
                    "type": "cli",
                    "manifest_paths": ["pyproject.toml"],
                    "languages": ["python"],
                    "entry_hints": [
                        {
                            "kind": "cli-entry",
                            "path": "agentcanvas/cli.py",
                            "detail": "agentcanvas project script",
                        }
                    ],
                }
            ],
            "components": [],
            "nodes": [
                {
                    "id": "file:agentcanvas/cli.py",
                    "type": "file",
                    "label": "cli.py",
                    "path": "agentcanvas/cli.py",
                    "data": {},
                },
                {
                    "id": "export:agentcanvas/cli.py:main:function",
                    "type": "export",
                    "label": "main",
                    "path": "agentcanvas/cli.py",
                    "data": {},
                },
            ],
            "edges": [],
        }

        contract = build_projection_contract(workflow_ir)
        instructions = " ".join(contract["instructions"])

        self.assertIn("app_surfaces", instructions)
        self.assertIn("human-readable AgentCanvas journeys", instructions)
        self.assertIn("Do not create top-level journeys from raw file inventories", instructions)
        self.assertIn("files, tests, and services belong in provenance", instructions)

    def test_frontend_behavior_projection_is_entrypoint_bounded(self):
        model = self._project_to_behavior(
            {
                "workspace": "/tmp/agentcanvas",
                "nodes": [
                    {
                        "id": "file:agentcanvas/cli.py",
                        "type": "file",
                        "label": "cli.py",
                        "source_refs": ["agentcanvas/cli.py"],
                    },
                    {
                        "id": "export:agentcanvas/cli.py:main:function",
                        "type": "export",
                        "label": "main",
                        "source_refs": ["agentcanvas/cli.py"],
                    },
                    {
                        "id": "file:agentcanvas/indexer.py",
                        "type": "file",
                        "label": "indexer.py",
                        "source_refs": ["agentcanvas/indexer.py"],
                    },
                    {
                        "id": "route:agentcanvas/demo_project/src/routes/orders.js:POST:/orders",
                        "type": "route",
                        "label": "/orders",
                        "source_refs": ["agentcanvas/demo_project/src/routes/orders.js"],
                    },
                    {
                        "id": "route:demo_projects/agentcanvas-demo/src/routes/returns.js:POST:/returns",
                        "type": "route",
                        "label": "/returns",
                        "source_refs": ["demo_projects/agentcanvas-demo/src/routes/returns.js"],
                    },
                    {
                        "id": "route:examples/sample-js-app/src/routes/checkout.js:POST:/checkout",
                        "type": "route",
                        "label": "/checkout",
                        "source_refs": ["examples/sample-js-app/src/routes/checkout.js"],
                    },
                ],
            }
        )

        self.assertTrue(model["journeys"])
        self.assertNotIn(
            "Other behaviors",
            [journey["title"] for journey in model["journeys"]],
            "Raw file/export inventory must not render as a giant Other behaviors flow.",
        )
        self.assertEqual(
            [],
            [
                ref
                for journey in model["journeys"]
                for ref in self._journey_refs(journey)
                if _is_fixture_path(ref)
            ],
            "Demo/example/test fixture refs must not become product journey steps.",
        )
        for journey in model["journeys"]:
            self.assertLessEqual(
                len(journey["nodes"]),
                5,
                "Top-level behavior steps should stay bounded to entrypoint-backed flow steps.",
            )
            first = journey["nodes"][0]
            self.assertEqual("step", first["kind"])
            self.assertEqual(
                "when",
                first["role"],
                "Each rendered journey should start from a runtime/product entrypoint.",
            )

    def _project_to_behavior(self, graph: Mapping[str, Any]) -> Dict[str, Any]:
        tsc = FRONTEND_ROOT / "node_modules" / ".bin" / "tsc"
        node = shutil.which("node")
        if not tsc.is_file() or not node:
            self.skipTest("frontend TypeScript toolchain is not available")

        with tempfile.TemporaryDirectory() as temp_root:
            temp = Path(temp_root)
            compiled = temp / "compiled"
            compiled.mkdir()
            completed = subprocess.run(
                [
                    str(tsc),
                    str(FRONTEND_ROOT / "src" / "lib" / "behavioral.ts"),
                    "--outDir",
                    str(compiled),
                    "--module",
                    "ES2020",
                    "--target",
                    "ES2020",
                    "--moduleResolution",
                    "Bundler",
                    "--skipLibCheck",
                    "--strict",
                    "false",
                ],
                cwd=PROJECT_ROOT,
                text=True,
                capture_output=True,
                timeout=15,
                check=False,
            )
            self.assertEqual(
                completed.returncode,
                0,
                completed.stdout + completed.stderr,
            )

            graph_path = temp / "graph.json"
            graph_path.write_text(json.dumps(graph), encoding="utf-8")
            (temp / "package.json").write_text('{"type":"module"}', encoding="utf-8")
            runner_path = temp / "project-behavior.mjs"
            runner_path.write_text(
                "\n".join(
                    [
                        "import fs from 'node:fs';",
                        "import { projectToBehavior } from './compiled/behavioral.js';",
                        "const graph = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));",
                        "console.log(JSON.stringify(projectToBehavior(graph)));",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            completed = subprocess.run(
                [node, str(runner_path), str(graph_path)],
                cwd=temp,
                text=True,
                capture_output=True,
                timeout=15,
                check=False,
            )
            self.assertEqual(
                completed.returncode,
                0,
                completed.stdout + completed.stderr,
            )
            return json.loads(completed.stdout)

    def _journey_refs(self, journey: Mapping[str, Any]) -> List[str]:
        refs: List[str] = []

        def visit(nodes: Iterable[Mapping[str, Any]]) -> None:
            for node in nodes:
                tech = node.get("tech")
                if isinstance(tech, Mapping):
                    refs.extend(str(ref) for ref in tech.get("refs") or [])
                if node.get("kind") == "branch":
                    visit(node.get("then") or [])
                    visit(node.get("otherwise") or [])

        visit(journey.get("nodes") or [])
        return refs


if __name__ == "__main__":
    unittest.main()
