import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class FrontendLifecycleShimTests(unittest.TestCase):
    def test_pending_status_enum_includes_phase1_lifecycle_values(self):
        types_source = (PROJECT_ROOT / "frontend" / "src" / "lib" / "types.ts").read_text(encoding="utf-8")
        changeset_source = (PROJECT_ROOT / "frontend" / "src" / "lib" / "changeset.ts").read_text(encoding="utf-8")

        self.assertIn("export enum PendingStatus", types_source)
        self.assertIn("export enum HandoffItemStatus", changeset_source)
        self.assertIn("export enum HandoffPhase", changeset_source)
        self.assertIn("const STATUS_LABELS", changeset_source)
        self.assertNotIn('if (status === "queued") return', changeset_source)
        for member, value in [
            ("Implemented", "implemented"),
            ("Verified", "verified"),
            ("Cancelled", "cancelled"),
            ("Rejected", "rejected"),
        ]:
            self.assertIn('%s = "%s"' % (member, value), types_source)

    def test_stopped_handoff_dismiss_does_not_acknowledge_done(self):
        changeset = (PROJECT_ROOT / "frontend" / "src" / "lib" / "changeset.ts").read_text(encoding="utf-8")
        overlay = (PROJECT_ROOT / "frontend" / "src" / "components" / "HandoffOverlay.tsx").read_text(encoding="utf-8")
        bottom_dock = (PROJECT_ROOT / "frontend" / "src" / "components" / "BottomDock.tsx").read_text(encoding="utf-8")
        app = (PROJECT_ROOT / "frontend" / "src" / "App.tsx").read_text(encoding="utf-8")

        self.assertIn("if (get().handoff.phase !== HandoffPhase.Done) return []", changeset)
        self.assertIn("dismissHandoff", changeset)
        self.assertIn("phase === HandoffPhase.Stopped", overlay)
        self.assertIn("onDismiss", overlay)
        self.assertIn("onHandoffDismiss", bottom_dock)
        self.assertIn("onHandoffDismiss", app)


if __name__ == "__main__":
    unittest.main()
