import json
import os
import tempfile
import unittest
from pathlib import Path
from urllib.parse import urlparse
from unittest.mock import patch

from agentcanvas.core import build_behavior_canvas
from agentcanvas import indexer
from agentcanvas.indexer import build_workflow_ir, index_workspace
from agentcanvas.server import make_handler


def _write(root: Path, relative_path: str, content: str) -> None:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _agentcanvas_like_workspace(root: Path) -> None:
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
    _write(
        root,
        "agentcanvas/cli.py",
        """
import argparse


def build_parser():
    parser = argparse.ArgumentParser(prog="agentcanvas")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("index", help="index a workspace into workflow IR")
    subparsers.add_parser("start", help="start the local canvas server")
    return parser


def main():
    return 0
""",
    )
    _write(
        root,
        "agentcanvas/server.py",
        """
def handle_api_get(parsed):
    if parsed.path == "/api/graph":
        return "graph"
    if parsed.path == "/api/canvas":
        return "canvas"


def handle_api_post(parsed):
    if parsed.path == "/api/reindex":
        return "reindex"
    if parsed.path == "/api/changes":
        return "changes"
""",
    )
    _write(
        root,
        "frontend/package.json",
        json.dumps(
            {
                "name": "frontend",
                "scripts": {"dev": "vite", "build": "tsc -b && vite build"},
                "dependencies": {"vite": "latest", "react": "latest"},
            }
        ),
    )
    _write(root, "frontend/src/main.tsx", "export function boot() {}\n")
    _write(
        root,
        "tests/test_core_model.py",
        """
def test_fixture_route():
    route = "router.post('/checkout', checkout)"
    return route
""",
    )


class _FakeHandler:
    def __init__(self, handler_cls):
        self.handler_cls = handler_cls
        self.response = None

    def authorized(self, _parsed):
        return True

    def write_json(self, payload, status=200):
        self.response = {"status": status, "payload": payload}


class BehaviorCanvasApiTests(unittest.TestCase):
    maxDiff = None

    def test_core_canvas_uses_entrypoints_and_filters_fixture_routes(self):
        with tempfile.TemporaryDirectory() as temp_root:
            root = Path(temp_root)
            _agentcanvas_like_workspace(root)
            workflow_ir = build_workflow_ir(root)

            wrapper = build_behavior_canvas(workflow_ir, workspace=root)
            canvas = wrapper["canvas"]
            titles = [journey["title"] for journey in canvas["journeys"]]

            self.assertIn("`agentcanvas start`", titles)
            self.assertIn("GET /api/canvas", titles)
            self.assertIn("POST /api/reindex", titles)
            self.assertTrue(any("frontend web app" in title.lower() for title in titles))
            self.assertNotIn("POST /checkout", titles)
            self.assertLess(len(titles), workflow_ir["summary"]["nodes"])

            for journey in canvas["journeys"]:
                first = journey["nodes"][0]
                self.assertEqual("step", first["kind"])
                self.assertEqual("when", first["role"])
                self.assertLessEqual(len(journey["nodes"]), 5)

    def test_api_canvas_returns_persisted_behavior_canvas(self):
        with tempfile.TemporaryDirectory() as temp_root:
            root = Path(temp_root)
            _agentcanvas_like_workspace(root)
            handler_cls = make_handler(
                root,
                token="token",
                assistant_id="codex",
                assistant_name="Codex",
            )
            fake = _FakeHandler(handler_cls)

            handler_cls.handle_api_get(fake, urlparse("/api/canvas?token=token"))

            self.assertEqual(fake.response["status"], 200)
            payload = fake.response["payload"]
            self.assertEqual("agentcanvas.behavior_canvas_response.v1", payload["schema"])
            self.assertIn("canvas", payload)
            self.assertIn("mapping", payload)
            self.assertTrue(payload["canvas"]["journeys"])
            self.assertTrue((root / ".agentcanvas" / "canvas.ir.json").is_file())

    def test_api_canvas_rebuilds_when_workflow_ir_is_newer_than_canvas(self):
        with tempfile.TemporaryDirectory() as temp_root:
            root = Path(temp_root)
            _agentcanvas_like_workspace(root)
            handler_cls = make_handler(
                root,
                token="token",
                assistant_id="codex",
                assistant_name="Codex",
            )
            fake = _FakeHandler(handler_cls)

            handler_cls.handle_api_get(fake, urlparse("/api/canvas?token=token"))
            initial_titles = [journey["title"] for journey in fake.response["payload"]["canvas"]["journeys"]]
            self.assertNotIn("`agentcanvas status`", initial_titles)

            _write(
                root,
                "agentcanvas/cli.py",
                """
import argparse


def build_parser():
    parser = argparse.ArgumentParser(prog="agentcanvas")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("index", help="index a workspace into workflow IR")
    subparsers.add_parser("start", help="start the local canvas server")
    subparsers.add_parser("status", help="update a pending request status")
    return parser


def main():
    return 0
""",
            )
            index_workspace(root)
            canvas_path = root / ".agentcanvas" / "canvas.ir.json"
            os.utime(canvas_path, (1, 1))

            handler_cls.handle_api_get(fake, urlparse("/api/canvas?token=token"))
            refreshed_titles = [journey["title"] for journey in fake.response["payload"]["canvas"]["journeys"]]

            self.assertIn("`agentcanvas status`", refreshed_titles)

    def test_manifest_surfaces_survive_source_file_truncation(self):
        with tempfile.TemporaryDirectory() as temp_root:
            root = Path(temp_root)
            source_path = (root / "src" / "main.ts").resolve()
            _write(root, "src/main.ts", "export function main() {}\n")
            _write(
                root,
                "sdk/typescript/package.json",
                json.dumps(
                    {
                        "name": "@example/typescript-sdk",
                        "scripts": {"build": "tsc -b", "test": "vitest run"},
                        "dependencies": {"typescript": "latest"},
                    }
                ),
            )
            _write(
                root,
                "sdk/python/pyproject.toml",
                "\n".join(["[project]", 'name = "example-python-sdk"', ""]),
            )

            with patch.object(indexer, "discover_files", return_value=([source_path], True)):
                workflow_ir = build_workflow_ir(root)

            manifests = {
                manifest["path"]
                for manifest in workflow_ir["package"]["manifests"]
            }
            surface_roots = {
                surface["root"]
                for surface in workflow_ir["app_surfaces"]
            }

            self.assertIn("sdk/typescript/package.json", manifests)
            self.assertIn("sdk/typescript", surface_roots)
            self.assertIn("sdk/python", surface_roots)
            self.assertTrue(workflow_ir["summary"]["source_file_scan_truncated"])
            self.assertGreaterEqual(workflow_ir["summary"]["manifest_files_seen"], 2)


if __name__ == "__main__":
    unittest.main()
