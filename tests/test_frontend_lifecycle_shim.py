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

    def test_needs_input_handoff_can_be_answered_from_overlay(self):
        changeset = (PROJECT_ROOT / "frontend" / "src" / "lib" / "changeset.ts").read_text(encoding="utf-8")
        overlay = (PROJECT_ROOT / "frontend" / "src" / "components" / "HandoffOverlay.tsx").read_text(encoding="utf-8")
        api = (PROJECT_ROOT / "frontend" / "src" / "lib" / "api.ts").read_text(encoding="utf-8")

        self.assertIn("answerPendingRequest", api)
        self.assertIn("answerPendingRequest", changeset)
        self.assertIn("fetchPendingRequest", changeset)
        self.assertIn("hydratePendingDetails", changeset)
        self.assertIn("answerHandoffQuestion", changeset)
        self.assertIn("conversationSummary", changeset)
        self.assertIn("conversation", changeset)
        self.assertIn("AnswerQuestion", overlay)
        self.assertIn("Textarea", overlay)
        self.assertIn("Send answer", overlay)
        self.assertIn("ConversationThread", overlay)
        self.assertIn("needsInputItems.map", overlay)
        self.assertIn("onAnswer(item.pendingId, answer)", overlay)

    def test_text_edits_default_to_silent_canvas_map_apply(self):
        edits = (PROJECT_ROOT / "frontend" / "src" / "lib" / "edits.ts").read_text(encoding="utf-8")
        composer = (PROJECT_ROOT / "frontend" / "src" / "components" / "StepComposer.tsx").read_text(encoding="utf-8")
        app = (PROJECT_ROOT / "frontend" / "src" / "App.tsx").read_text(encoding="utf-8")

        self.assertIn("export enum EditDelivery", edits)
        self.assertIn('CanvasMap = "canvas_map"', edits)
        self.assertIn('ImplementationRequest = "implementation_request"', edits)
        self.assertIn("canSaveToMap", composer)
        self.assertIn("Fix map", composer)
        self.assertIn("Change app", composer)
        self.assertIn("Save to map", composer)
        self.assertIn("Ask agent", composer)
        self.assertIn("EditDelivery.CanvasMap", composer)
        self.assertIn("applyCanvasBatch", app)
        self.assertIn("applyCanvasMapTextEdit", app)
        self.assertIn('op: "upsert_node"', app)
        self.assertIn("REVISION_CONFLICT", app)

    def test_canvas_history_dialog_restores_prior_revisions(self):
        dialog = (PROJECT_ROOT / "frontend" / "src" / "components" / "CanvasHistoryDialog.tsx").read_text(encoding="utf-8")
        app = (PROJECT_ROOT / "frontend" / "src" / "App.tsx").read_text(encoding="utf-8")
        api = (PROJECT_ROOT / "frontend" / "src" / "lib" / "api.ts").read_text(encoding="utf-8")
        types = (PROJECT_ROOT / "frontend" / "src" / "lib" / "types.ts").read_text(encoding="utf-8")

        self.assertIn("CanvasHistoryDialog", dialog)
        self.assertIn("fetchCanvasHistory", dialog)
        self.assertIn("restoreCanvasRevision", dialog)
        self.assertIn("baseRevision: activeRevision", dialog)
        self.assertIn("CanvasHistoryErrorCode", dialog)
        self.assertIn("RevisionConflict", dialog)
        self.assertIn("Undo latest", dialog)
        self.assertIn("Restore this version", dialog)
        self.assertIn("flowSummary", dialog)
        self.assertIn("CanvasHistoryDialog", app)
        self.assertIn("historyOpen", app)
        self.assertIn("Canvas history", app)
        self.assertIn("hasLocalPendingChanges", app)
        self.assertIn("flowSummary", types)
        self.assertIn("normalizeCanvasHistoryFlowSummary", api)

    def test_inspector_shows_native_v2_evidence_citations(self):
        inspector = (PROJECT_ROOT / "frontend" / "src" / "components" / "Inspector.tsx").read_text(encoding="utf-8")
        app = (PROJECT_ROOT / "frontend" / "src" / "App.tsx").read_text(encoding="utf-8")
        api = (PROJECT_ROOT / "frontend" / "src" / "lib" / "api.ts").read_text(encoding="utf-8")
        types = (PROJECT_ROOT / "frontend" / "src" / "lib" / "types.ts").read_text(encoding="utf-8")

        self.assertIn("export enum CanvasV2Status", types)
        self.assertIn("export enum CanvasV2ConfidenceLevel", types)
        self.assertIn("normalizeCanvasV2Status", api)
        self.assertIn("normalizeCanvasV2Confidence", api)
        self.assertIn("selectedNativeNode", app)
        self.assertIn("findCanvasV2Node", app)
        self.assertIn("nativeNode={selectedNativeNode}", app)
        self.assertIn("Why this is here", inspector)
        self.assertIn("nativeNode?.evidenceRefs", inspector)
        self.assertIn("statusLabel", inspector)
        self.assertIn("confidenceLabel", inspector)
        self.assertIn("Project references AgentCanvas used", inspector)


if __name__ == "__main__":
    unittest.main()
