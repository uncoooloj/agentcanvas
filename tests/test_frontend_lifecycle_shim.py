import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class FrontendLifecycleShimTests(unittest.TestCase):
    def test_studio_entry_routes_landing_sandbox_and_legacy_flows(self):
        app = (PROJECT_ROOT / "frontend" / "src" / "App.tsx").read_text(encoding="utf-8")
        self.assertIn('import { LandingPage } from "@/components/LandingPage"', app)
        self.assertIn('import("@/studio/StudioShell")', app)
        self.assertIn('useMatch("/flows/:id")', app)
        self.assertIn("onTrySandbox={trySandbox}", app)
        self.assertIn("disconnectEvents()", app)

    def test_studio_uses_sse_not_legacy_polling_intervals(self):
        api = (PROJECT_ROOT / "frontend" / "src" / "lib" / "studioApi.ts").read_text(encoding="utf-8")
        store = (PROJECT_ROOT / "frontend" / "src" / "lib" / "studioStore.ts").read_text(encoding="utf-8")
        self.assertIn("EventSource", api)
        self.assertIn("/api/events", api)
        self.assertIn("studio.resync", api)
        self.assertIn("studio.updated", store)
        self.assertIn("annotations.updated", store)

    def test_spatial_canvas_uses_react_flow_and_elk_layout(self):
        canvas = (PROJECT_ROOT / "frontend" / "src" / "studio" / "SpatialCanvas.tsx").read_text(encoding="utf-8")
        layout = (PROJECT_ROOT / "frontend" / "src" / "lib" / "studioLayout.ts").read_text(encoding="utf-8")
        pkg = (PROJECT_ROOT / "frontend" / "package.json").read_text(encoding="utf-8")
        self.assertIn('"@xyflow/react"', pkg)
        self.assertIn('"elkjs"', pkg)
        self.assertIn("ReactFlow", canvas)
        self.assertIn("export function layoutFlow", layout)
        self.assertIn("export function layoutSystem", layout)

    def test_evidence_drawer_and_command_dock_are_wired(self):
        shell = (PROJECT_ROOT / "frontend" / "src" / "studio" / "StudioShell.tsx").read_text(encoding="utf-8")
        dock = (PROJECT_ROOT / "frontend" / "src" / "studio" / "CommandDock.tsx").read_text(encoding="utf-8")
        drawer = (PROJECT_ROOT / "frontend" / "src" / "studio" / "EvidenceDrawer.tsx").read_text(encoding="utf-8")
        self.assertIn("CommandDock", shell)
        self.assertIn("EvidenceDrawer", shell)
        self.assertIn("SpatialCanvas", shell)
        self.assertIn("Approve &amp; Build", dock)
        self.assertIn("Plan Diff", dock)
        self.assertIn("fileSlice", drawer)
        self.assertIn("fileDiff", drawer)


if __name__ == "__main__":
    unittest.main()
