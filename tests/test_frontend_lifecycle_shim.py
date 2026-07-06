import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class FrontendLifecycleShimTests(unittest.TestCase):
    def test_pending_status_enum_includes_phase1_lifecycle_values(self):
        types_source = (PROJECT_ROOT / "frontend" / "src" / "lib" / "types.ts").read_text(encoding="utf-8")
        changeset_source = (PROJECT_ROOT / "frontend" / "src" / "lib" / "changeset.ts").read_text(encoding="utf-8")
        api_source = (PROJECT_ROOT / "frontend" / "src" / "lib" / "api.ts").read_text(encoding="utf-8")
        activity_source = (PROJECT_ROOT / "frontend" / "src" / "components" / "ActivityDialog.tsx").read_text(encoding="utf-8")

        self.assertIn("export enum PendingStatus", types_source)
        self.assertIn("export enum HandoffItemStatus", changeset_source)
        self.assertIn("export enum HandoffPhase", changeset_source)
        self.assertIn("export const PENDING_STATUS_LABELS: Record<PendingStatus, string>", types_source)
        self.assertIn("export function pendingStatusLabel", types_source)
        self.assertIn("const PENDING_STATUS_SET = new Set<PendingStatus>", api_source)
        self.assertIn("function isPendingStatus(value: unknown): value is PendingStatus", api_source)
        self.assertIn("LegacyPendingStatus.Queued", api_source)
        self.assertIn("pendingStatusLabel(status.status)", activity_source)
        self.assertIn("[HandoffItemStatus.Creating]: \"creating pending file\"", changeset_source)
        self.assertNotIn('Queued = "queued"', changeset_source)
        self.assertNotIn('if (status === "queued") return', changeset_source)
        self.assertNotIn("function statusLabel(status: PendingStatus)", activity_source)
        self.assertNotIn("case PendingStatus.", activity_source)
        for member, value in (
            ("Pending", "pending"),
            ("Sent", "sent"),
            ("InProgress", "in_progress"),
            ("Implemented", "implemented"),
            ("NeedsInput", "needs_input"),
            ("Blocked", "blocked"),
            ("Verified", "verified"),
            ("Done", "done"),
            ("Cancelled", "cancelled"),
            ("Rejected", "rejected"),
        ):
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

    def test_pending_activity_polling_is_app_level_and_visibility_aware(self):
        app = (PROJECT_ROOT / "frontend" / "src" / "App.tsx").read_text(encoding="utf-8")
        overlay = (PROJECT_ROOT / "frontend" / "src" / "components" / "HandoffOverlay.tsx").read_text(encoding="utf-8")

        self.assertIn("PENDING_ACTIVITY_POLL_INTERVAL_MS", app)
        self.assertIn("async function pollPendingActivity()", app)
        self.assertIn("await refreshHandoff()", app)
        self.assertIn("!documentIsVisible()", app)
        self.assertIn("phase === HandoffPhase.Composing", app)
        self.assertIn("phase === HandoffPhase.Done", app)
        self.assertIn("phase === HandoffPhase.Stopped", app)
        self.assertNotIn("setInterval", overlay)
        self.assertNotIn("PENDING_ACTIVITY_POLL_INTERVAL_MS", overlay)

    def test_progress_polling_uses_activity_cadence_not_health_cadence(self):
        app = (PROJECT_ROOT / "frontend" / "src" / "App.tsx").read_text(encoding="utf-8")

        self.assertIn("async function pollProgress()", app)
        progress_section = app.split("async function pollProgress()", 1)[1].split("async function pollHealth()", 1)[0]
        self.assertIn("fetchProgress()", progress_section)
        self.assertIn("PENDING_ACTIVITY_POLL_INTERVAL_MS", progress_section)
        self.assertNotIn("HEALTH_POLL_INTERVAL_MS", progress_section)

    def test_canvas_v2_renderer_uses_elk_worker_with_sync_fallback(self):
        canvas = (PROJECT_ROOT / "frontend" / "src" / "components" / "CanvasV2FlowCanvas.tsx").read_text(encoding="utf-8")
        layout = (PROJECT_ROOT / "frontend" / "src" / "lib" / "canvasV2Layout.ts").read_text(encoding="utf-8")
        worker = (PROJECT_ROOT / "frontend" / "src" / "lib" / "canvasV2LayoutWorker.ts").read_text(encoding="utf-8")
        package = (PROJECT_ROOT / "frontend" / "package.json").read_text(encoding="utf-8")

        self.assertIn('"elkjs"', package)
        self.assertIn("ELK_LAYOUT_OPTIONS", layout)
        self.assertIn('"elk.algorithm": "layered"', layout)
        self.assertIn("flowToElkGraph", layout)
        self.assertIn("layoutFlowFromElk", layout)
        self.assertIn("new Worker(new URL(\"../lib/canvasV2LayoutWorker.ts\", import.meta.url)", canvas)
        self.assertIn("setLayout(fallbackLayout)", canvas)
        self.assertIn('import ELK from "elkjs/lib/elk.bundled.js"', worker)
        self.assertIn("await elk.layout(flowToElkGraph(flow))", worker)

    def test_direct_canvas_map_edits_include_add_and_remove(self):
        edits = (PROJECT_ROOT / "frontend" / "src" / "lib" / "edits.ts").read_text(encoding="utf-8")
        composer = (PROJECT_ROOT / "frontend" / "src" / "components" / "StepComposer.tsx").read_text(encoding="utf-8")
        app = (PROJECT_ROOT / "frontend" / "src" / "App.tsx").read_text(encoding="utf-8")

        self.assertIn("export enum EditDelivery", edits)
        self.assertIn('CanvasMap = "canvas_map"', edits)
        self.assertIn('ImplementationRequest = "implementation_request"', edits)
        self.assertIn("canSaveToMapAction", edits)
        self.assertIn("case FlowAction.AddAfter:", edits)
        self.assertIn("case FlowAction.Remove:", edits)
        self.assertIn("CanvasApplyOperation", types := (PROJECT_ROOT / "frontend" / "src" / "lib" / "types.ts").read_text(encoding="utf-8"))
        self.assertIn("CanvasV2NodeOperationPayload", types)
        self.assertIn("CanvasV2EdgeOperationPayload", types)
        self.assertIn("canSaveToMap", composer)
        self.assertIn("Fix map", composer)
        self.assertIn("Change app", composer)
        self.assertIn("Save to map", composer)
        self.assertIn("Ask agent", composer)
        self.assertIn("EditDelivery.CanvasMap", composer)
        self.assertIn("applyCanvasBatch", app)
        self.assertIn("applyCanvasMapEdit", app)
        self.assertIn("buildAddAfterOperations", app)
        self.assertIn("buildRemoveNodeOperations", app)
        self.assertIn("canvasNodePayload", app)
        self.assertIn("canvasEdgePayload", app)
        self.assertIn("evidence_refs", app)
        self.assertIn("is_default", app)
        self.assertIn('op: "upsert_node"', app)
        self.assertIn('op: "upsert_edge"', app)
        self.assertIn('op: "delete_edge"', app)
        self.assertIn('op: "delete_node"', app)
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

    def test_native_v2_nodes_have_display_fallbacks(self):
        app = (PROJECT_ROOT / "frontend" / "src" / "App.tsx").read_text(encoding="utf-8")
        adapter = (PROJECT_ROOT / "frontend" / "src" / "lib" / "nativeDisplay.ts").read_text(encoding="utf-8")
        canvas = (PROJECT_ROOT / "frontend" / "src" / "components" / "CanvasV2FlowCanvas.tsx").read_text(encoding="utf-8")

        self.assertIn("nativeNodeToDisplayNode", adapter)
        self.assertIn("findNativeDisplayNodeByDisplayId", app)
        self.assertIn("nativeDisplayNodeId", adapter)
        self.assertIn("findNodeByNativeId(journey.nodes, nativeId)", app)
        self.assertIn("nativeNode ? nativeNodeToDisplayNode", app)
        self.assertIn("disabled={!displayNode}", canvas)

    def test_native_v2_subflows_open_referenced_flows(self):
        app = (PROJECT_ROOT / "frontend" / "src" / "App.tsx").read_text(encoding="utf-8")
        adapter = (PROJECT_ROOT / "frontend" / "src" / "lib" / "nativeDisplay.ts").read_text(encoding="utf-8")
        canvas = (PROJECT_ROOT / "frontend" / "src" / "components" / "CanvasV2FlowCanvas.tsx").read_text(encoding="utf-8")

        self.assertIn("...(node.flowRef ? { flowRef: node.flowRef } : {})", adapter)
        self.assertIn("routeCanvasV2Flow", app)
        self.assertIn("journeyFromCanvasV2Flow", app)
        self.assertIn("onOpenFlow={(flowId) => {", app)
        self.assertIn("onOpenFlow?: (flowId: string) => void", canvas)
        self.assertIn("onOpenFlow(node.flowRef)", canvas)
        self.assertIn("CanvasV2NodeKind.SubFlow && node.flowRef", canvas)

    def test_native_v2_graph_cards_support_keyboard_navigation(self):
        canvas = (PROJECT_ROOT / "frontend" / "src" / "components" / "CanvasV2FlowCanvas.tsx").read_text(encoding="utf-8")

        self.assertIn("export enum CanvasV2KeyboardDirection", canvas)
        self.assertIn("keyboardDirectionFromKey", canvas)
        self.assertIn("keyboardTargetForNode", canvas)
        self.assertIn('data-canvas-v2-node-id={node.id}', canvas)
        self.assertIn("onKeyDown={onKeyDown}", canvas)
        self.assertIn("ArrowDown", canvas)
        self.assertIn("ArrowUp", canvas)
        self.assertIn("Home", canvas)
        self.assertIn("End", canvas)

    def test_inspector_shows_native_v2_evidence_citations(self):
        inspector = (PROJECT_ROOT / "frontend" / "src" / "components" / "Inspector.tsx").read_text(encoding="utf-8")
        app = (PROJECT_ROOT / "frontend" / "src" / "App.tsx").read_text(encoding="utf-8")
        api = (PROJECT_ROOT / "frontend" / "src" / "lib" / "api.ts").read_text(encoding="utf-8")
        types = (PROJECT_ROOT / "frontend" / "src" / "lib" / "types.ts").read_text(encoding="utf-8")

        self.assertIn("export enum CanvasV2Status", types)
        self.assertIn("export enum CanvasV2ConfidenceLevel", types)
        self.assertIn("export interface CanvasV2Evidence", types)
        self.assertIn("normalizeCanvasV2Status", api)
        self.assertIn("normalizeCanvasV2Confidence", api)
        self.assertIn("normalizeCanvasV2EvidenceList", api)
        self.assertIn("selectedNativeNode", app)
        self.assertIn("findCanvasV2Node", app)
        self.assertIn("nativeNode={selectedNativeNode}", app)
        self.assertIn("Why this is here", inspector)
        self.assertIn("nativeNode?.evidence.length", inspector)
        self.assertIn("node.evidence.map", inspector)
        self.assertIn("statusLabel", inspector)
        self.assertIn("confidenceLabel", inspector)
        self.assertIn("Project references AgentCanvas used", inspector)

    def test_activity_dialog_merges_canvas_history_and_pending_status(self):
        activity = (PROJECT_ROOT / "frontend" / "src" / "components" / "ActivityDialog.tsx").read_text(encoding="utf-8")
        app = (PROJECT_ROOT / "frontend" / "src" / "App.tsx").read_text(encoding="utf-8")

        self.assertIn("ActivityDialog", activity)
        self.assertIn("fetchCanvasHistory", activity)
        self.assertIn("fetchPending", activity)
        self.assertIn("ActivityEventKind", activity)
        self.assertIn("buildActivityEvents", activity)
        self.assertIn("statusHistory", activity)
        self.assertIn("compareActivityEvents", activity)
        self.assertIn("ActivityDialog", app)
        self.assertIn("activityOpen", app)
        self.assertIn("aria-label=\"Activity\"", app)

    def test_workspace_mapping_state_uses_durable_progress(self):
        app = (PROJECT_ROOT / "frontend" / "src" / "App.tsx").read_text(encoding="utf-8")
        api = (PROJECT_ROOT / "frontend" / "src" / "lib" / "api.ts").read_text(encoding="utf-8")
        types = (PROJECT_ROOT / "frontend" / "src" / "lib" / "types.ts").read_text(encoding="utf-8")
        state = (PROJECT_ROOT / "frontend" / "src" / "components" / "WorkspaceMappingState.tsx").read_text(encoding="utf-8")

        self.assertIn("export enum WorkspaceProgressStage", types)
        self.assertIn("export async function fetchProgress", api)
        self.assertIn("normalizeWorkspaceProgress", api)
        self.assertIn("fetchProgress()", app)
        self.assertIn("setMappingProgress(progress)", app)
        self.assertIn("progress={mappingProgress}", app)
        self.assertIn("WorkspaceProgressStage.MappingFlows", state)
        self.assertIn("liveProgress?.message", state)
        self.assertIn("progress.current / progress.total", state)
        self.assertIn("STUCK_PROGRESS_MS = 10 * 60 * 1000", state)
        self.assertIn("Your agent seems to have stopped", state)
        self.assertIn("resumePrompt(fallbackPrompt, liveProgress)", state)
        self.assertIn("`.agentcanvas/progress.json`", state)

    def test_first_run_tour_is_scoped_to_workspace_and_major_version(self):
        app = (PROJECT_ROOT / "frontend" / "src" / "App.tsx").read_text(encoding="utf-8")

        self.assertIn('const ONBOARDING_MAJOR_VERSION = "1"', app)
        self.assertIn("function onboardingStorageKey", app)
        self.assertIn("hashWorkspaceKey(workspaceKey)", app)
        self.assertIn("context.mode !== AppContextMode.Workspace", app)
        self.assertIn("context.workspacePath", app)
        self.assertIn("window.localStorage.getItem(onboardingKey)", app)
        self.assertIn("window.localStorage.setItem(onboardingKey, \"dismissed\")", app)
        self.assertIn("FirstRunTour", app)
        self.assertIn("Dismiss first-run tour", app)


if __name__ == "__main__":
    unittest.main()
