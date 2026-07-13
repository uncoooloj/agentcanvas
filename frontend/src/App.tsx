import { useEffect, useMemo, useRef, useState } from "react"
import { useLocation, useNavigate } from "react-router-dom"
import {
  Check,
  ChevronLeft,
  Clipboard,
  History,
  Lightbulb,
  ListChecks,
  Moon,
  PanelLeftClose,
  PanelLeftOpen,
  RefreshCw,
  Loader2,
  Sparkles,
  Sun,
  X,
} from "lucide-react"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { ActivityDialog } from "@/components/ActivityDialog"
import { BrandMark } from "@/components/BrandMark"
import { CanvasHistoryDialog } from "@/components/CanvasHistoryDialog"
import { CanvasV2FlowCanvas } from "@/components/CanvasV2FlowCanvas"
import { FlowColumn } from "@/components/FlowCanvas"
import { Overview } from "@/components/Overview"
import { Inspector } from "@/components/Inspector"
import { PendingRequestDialog } from "@/components/PendingRequestDialog"
import { Provenance } from "@/components/Provenance"
import { BottomDock } from "@/components/BottomDock"
import { LandingPage } from "@/components/LandingPage"
import { MappingRequestStatus, WorkspaceMappingState } from "@/components/WorkspaceMappingState"
import { DEMO_MODEL, emptyAppModel } from "@/lib/behavioral"
import {
  HandoffItemStatus,
  HandoffPhase,
  applyChanges,
  changeRequestFor,
  kindForAction,
  useChanges,
  type ChangeEntry,
  type HandoffItem,
} from "@/lib/changeset"
import { ApiError, applyCanvasBatch, fetchCanvas, fetchMapHealth, fetchProgress, isApiAuthExpired, postChange, reindexCanvas } from "@/lib/api"
import { AppContextMode, RuntimeConnectionState, useAppContext, type AppContext } from "@/lib/appcontext"
import { EditDelivery, type EditRequest, type StagedEdit } from "@/lib/edits"
import {
  buildMapEditOperations,
  mapEditCreatesProposedNodes,
  proposedNodeIdsFromOperations,
  withPendingRequestMetadata,
} from "@/lib/canvasMapOps"
import { CANVAS_POLL_INTERVAL_MS, documentIsVisible, HEALTH_POLL_INTERVAL_MS, PENDING_ACTIVITY_POLL_INTERVAL_MS } from "@/lib/polling"
import {
  CanvasStateKind,
  CanvasMappingMode,
  CanvasSourceKind,
  CanvasSourceTone,
  CopyState,
  FlowAction,
  JourneyActivity,
  MapFreshnessStatus,
  MapHealthStatus,
  PendingRefKind,
  WorkspaceProgressStage,
  findNode,
  type AppModel,
  type CanvasMapping,
  type CanvasSourceSummary,
  type CanvasV2Document,
  type CanvasV2Flow,
  type CanvasV2Node,
  type FlowNode,
  type Journey,
  type MapHealth,
  type PendingRef,
  type WorkspaceProgressStatus,
} from "@/lib/types"
import { findNativeDisplayNodeByDisplayId, findNodeByNativeId, nativeNodeToDisplayNode } from "@/lib/nativeDisplay"
import type { PendingRequestLink } from "@/components/CanvasV2FlowCanvas"

const HOME = "__home__"
const AUTH_EXPIRED_NOTICE = "This AgentCanvas link cannot sync anymore. Reopen AgentCanvas from your assistant to keep this page up to date."
const ONBOARDING_MAJOR_VERSION = "1"
const MAPPING_STAGES = [
  "Looking through your project",
  "Finding how people use it",
  "Putting the important parts together",
  "Almost ready to show you",
]

type CanvasState =
  | { kind: CanvasStateKind.Idle | CanvasStateKind.Ready; notice?: string; mapping?: CanvasMapping }
  | {
      kind: CanvasStateKind.Loading | CanvasStateKind.Reindexing | CanvasStateKind.Empty | CanvasStateKind.Error
      message?: string
      detail?: string
      nextSteps?: string[]
      fallbackPrompt?: string
      notice?: string
      mapping?: CanvasMapping
    }

type WorkspaceModelResult = {
  model: AppModel
  mapping?: CanvasMapping
  notice?: string
  revision?: number
  canvasV2?: CanvasV2Document
}

type MapRefreshAction = {
  title: string
  detail: string
  prompt: string
}

enum MapInstructionKind {
  Refresh = "refresh",
  Starter = "starter",
  Author = "author",
}

function hasProgressAfterRequest(progress: WorkspaceProgressStatus | null, requestStartedAt: number | null): boolean {
  if (!progress?.readable || !requestStartedAt || !progress.updated_at) return false
  const updatedAt = Date.parse(progress.updated_at)
  return !Number.isNaN(updatedAt) && updatedAt >= requestStartedAt
}

function progressLabel(progress: WorkspaceProgressStatus | null): string | null {
  switch (progress?.stage) {
    case WorkspaceProgressStage.Indexing:
      return "Looking through your project"
    case WorkspaceProgressStage.Surveying:
      return "Finding how people use it"
    case WorkspaceProgressStage.MappingFlows:
      return "Putting the important parts together"
    case WorkspaceProgressStage.Done:
      return "Almost ready to show you"
    default:
      return null
  }
}

export default function App() {
  const navigate = useNavigate()
  const location = useLocation()
  const path = location.pathname
  const launchParams = new URLSearchParams(location.search)
  const hasRuntimeLaunchContext = Boolean(
    launchParams.get("token") ||
      launchParams.get("demo") ||
      launchParams.get("sessionId") ||
      launchParams.get("session_id")
  )
  // A workspace link can keep a stale /welcome path in an existing browser tab.
  // Runtime context must always win so a launched canvas never turns into marketing.
  const onWelcome = path === "/welcome" && !hasRuntimeLaunchContext
  const journeyMatch = path.match(/^\/flows\/(.+?)\/?$/)
  const routeJourneyId = journeyMatch ? decodeURIComponent(journeyMatch[1]) : null
  const view = routeJourneyId ?? HOME
  // Preserve the query (token, demo) across navigations so deep links + reloads work.
  const go = (to: string) => navigate({ pathname: to, search: location.search })

  const {
    context,
    loading: contextLoading,
    connection: runtimeConnection,
    error: runtimeConnectionError,
    retry: retryContext,
  } = useAppContext()
  const [model, setModel] = useState<AppModel>(emptyAppModel())
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [editRequest, setEditRequest] = useState<EditRequest | null>(null)
  const [leftOpen, setLeftOpen] = useState(true)
  const [canvasState, setCanvasState] = useState<CanvasState>({ kind: CanvasStateKind.Loading })
  const [dark, setDark] = useState(false)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [activityOpen, setActivityOpen] = useState(false)
  const [pendingRequestLink, setPendingRequestLink] = useState<PendingRequestLink | null>(null)
  const mappingActive = canvasState.kind === CanvasStateKind.Loading || canvasState.kind === CanvasStateKind.Reindexing
  const [mappingStage, setMappingStage] = useState(0)
  const [mappingProgress, setMappingProgress] = useState<WorkspaceProgressStatus | null>(null)
  const [mapHealth, setMapHealth] = useState<MapHealth | null>(null)
  const [canvasV2, setCanvasV2] = useState<CanvasV2Document | null>(null)
  const [authNotice, setAuthNotice] = useState<string | null>(null)
  const [mapRequestStatus, setMapRequestStatus] = useState<MappingRequestStatus>(MappingRequestStatus.Idle)
  const [mapRequestError, setMapRequestError] = useState<string | null>(null)
  const [mapRequestPendingId, setMapRequestPendingId] = useState<string | null>(null)
  const [mapRequestStartedAt, setMapRequestStartedAt] = useState<number | null>(null)
  const [onboardingVisible, setOnboardingVisible] = useState(false)
  const canvasSignatureRef = useRef<string | null>(null)
  const canvasRevisionRef = useRef<number | null>(null)
  const lastUsableWorkspaceResultRef = useRef<WorkspaceModelResult | null>(null)
  const mapRequestInFlightRef = useRef(false)
  const pollBlockedRef = useRef(false)

  const phase = useChanges((s) => s.handoff.phase)
  const handoffItems = useChanges((s) => s.handoff.items)
  const refreshHandoff = useChanges((s) => s.refreshHandoff)
  const stagedChanges = useChanges((s) => s.changes)
  const queuedNext = useChanges((s) => s.queuedNext)
  const orderingChanges = useMemo(() => [...stagedChanges, ...queuedNext], [queuedNext, stagedChanges])
  const localChanges = useMemo(
    () => (phase === HandoffPhase.Composing ? stagedChanges : queuedNext),
    [phase, queuedNext, stagedChanges]
  )
  const locked = phase === HandoffPhase.Sending || phase === HandoffPhase.Working
  const hasLocalPendingChanges =
    Boolean(editRequest) || stagedChanges.length > 0 || queuedNext.length > 0 || phase !== HandoffPhase.Composing
  const journeyActivity = useMemo(
    () => getJourneyActivity(model.journeys, localChanges, orderingChanges, phase, handoffItems),
    [handoffItems, localChanges, model.journeys, orderingChanges, phase]
  )
  const canvasSource = useMemo(
    () => describeCanvasSource(context, model, canvasState, mapHealth),
    [context, model, canvasState, mapHealth]
  )
  const mapRefreshAction = useMemo(
    () => describeMapRefreshAction(canvasSource, context, model.appName),
    [canvasSource, context, model.appName]
  )

  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark)
  }, [dark])

  useEffect(() => {
    pollBlockedRef.current = hasLocalPendingChanges
  }, [hasLocalPendingChanges])

  useEffect(() => {
    setMappingProgress(context.progress ?? null)
  }, [context.progress])

  useEffect(() => {
    setMapRequestStatus(MappingRequestStatus.Idle)
    setMapRequestError(null)
    setMapRequestPendingId(null)
    setMapRequestStartedAt(null)
    lastUsableWorkspaceResultRef.current = null
    mapRequestInFlightRef.current = false
  }, [context.workspacePath, context.workspace])

  // Switching flows (or returning to All Flows) clears any in-progress step
  // edit, so the composer never lingers on a page where it has no context.
  useEffect(() => {
    setEditRequest(null)
  }, [view])

  function rememberWorkspaceResult(result: WorkspaceModelResult) {
    canvasSignatureRef.current = canvasSignature(result)
    canvasRevisionRef.current = result.revision ?? null
  }

  function showWorkspaceResult(result: WorkspaceModelResult) {
    setCanvasV2(result.canvasV2 ?? null)
    if (!isUnreadyMap(result.mapping) && result.model.journeys.length > 0) {
      lastUsableWorkspaceResultRef.current = result
    }
    if (isUnreadyMap(result.mapping)) {
      setModel(emptyAppModel(result.model.appName || context.workspace || "Your app"))
      setCanvasState({
        kind: CanvasStateKind.Empty,
        message: unreadyMapTitle(result),
        detail: starterMapDetail(result, context.assistant),
        nextSteps: mapNextSteps(result, context),
        fallbackPrompt: mapFallbackPrompt(result, context),
        mapping: result.mapping,
      })
    } else if (!result.model.journeys.length) {
      setModel(emptyAppModel(result.model.appName || context.workspace || "Your app"))
      setCanvasState({
        kind: CanvasStateKind.Empty,
        message: "No plain-English map yet",
        detail: emptyWorkspaceDetail(result),
        nextSteps: mapNextSteps(result, context),
        fallbackPrompt: mapFallbackPrompt(result, context),
        mapping: result.mapping,
      })
    } else {
      setModel((current) => preserveLocalJourneyRecency(result.model, current))
      setCanvasState({ kind: CanvasStateKind.Ready, notice: result.notice, mapping: result.mapping })
      setMapRequestStatus(MappingRequestStatus.Idle)
      setMapRequestError(null)
      setMapRequestPendingId(null)
    }
  }

  async function load({ refresh = false }: { refresh?: boolean } = {}) {
    // Demo mode shows the curated, hand-authored flows (great first impression);
    // the heuristic projection over real code isn't good enough to lead with yet.
    // Edits still write real pending requests via /api/changes.
    if (context.mode === AppContextMode.Demo) {
      setModel((current) => preserveLocalJourneyRecency(DEMO_MODEL, current))
      setSelectedId(null)
      setMapHealth(null)
      setCanvasV2(null)
      setAuthNotice(null)
      canvasSignatureRef.current = null
      canvasRevisionRef.current = null
      setCanvasState({ kind: CanvasStateKind.Ready })
      return
    }

    setMappingStage(0)
    setMappingProgress(context.progress ?? null)
    setMapHealth(null)
    setCanvasState({ kind: refresh ? CanvasStateKind.Reindexing : CanvasStateKind.Loading })
    try {
      const result = await loadWorkspaceModel(refresh)
      rememberWorkspaceResult(result)
      showWorkspaceResult(result)
      setAuthNotice(null)
    } catch (error) {
      if (isApiAuthExpired(error)) setAuthNotice(AUTH_EXPIRED_NOTICE)
      const lastUsable = lastUsableWorkspaceResultRef.current
      if (refresh && lastUsable) {
        setModel(lastUsable.model)
        setCanvasV2(lastUsable.canvasV2 ?? null)
        setCanvasState({
          kind: CanvasStateKind.Ready,
          notice: refreshLoadErrorNotice(error),
          mapping: lastUsable.mapping,
        })
      } else {
        setModel(emptyAppModel(context.workspace || model.appName || "Your app"))
        setCanvasState({
          kind: CanvasStateKind.Error,
          message: "Couldn't open the project map",
          detail: plainLoadError(error),
        })
      }
    } finally {
      setSelectedId(null)
    }
  }

  useEffect(() => {
    if (contextLoading || context.mode === AppContextMode.Landing) return
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [contextLoading, context.mode])

  useEffect(() => {
    if (contextLoading || context.mode !== AppContextMode.Workspace || onWelcome) return

    let cancelled = false
    let inFlight = false

    async function pollCanvas() {
      if (inFlight || pollBlockedRef.current) return
      inFlight = true
      try {
        const result = await loadWorkspaceModel(false)
        if (cancelled || pollBlockedRef.current) return

        if (typeof result.revision === "number" && result.revision === canvasRevisionRef.current) {
          setAuthNotice(null)
          return
        }

        const signature = canvasSignature(result)
        if (typeof result.revision !== "number" && signature === canvasSignatureRef.current) {
          setAuthNotice(null)
          return
        }

        rememberWorkspaceResult(result)
        showWorkspaceResult(result)
        setAuthNotice(null)
      } catch (error) {
        if (!cancelled && isApiAuthExpired(error)) setAuthNotice(AUTH_EXPIRED_NOTICE)
        // Other polling failures are quiet; keep the current canvas visible through transient read errors.
      } finally {
        inFlight = false
      }
    }

    const timer = window.setInterval(pollCanvas, CANVAS_POLL_INTERVAL_MS)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [contextLoading, context.mode, context.workspace, onWelcome])

  useEffect(() => {
    if (
      contextLoading ||
      context.mode !== AppContextMode.Workspace ||
      onWelcome ||
      phase === HandoffPhase.Composing ||
      phase === HandoffPhase.Done ||
      phase === HandoffPhase.Stopped
    ) {
      return
    }

    let cancelled = false
    let inFlight = false

    async function pollPendingActivity() {
      if (inFlight || !documentIsVisible()) return
      inFlight = true
      try {
        await refreshHandoff()
        if (!cancelled) setAuthNotice(null)
      } catch (error) {
        if (!cancelled && isApiAuthExpired(error)) setAuthNotice(AUTH_EXPIRED_NOTICE)
      } finally {
        inFlight = false
      }
    }

    void pollPendingActivity()
    const timer = window.setInterval(pollPendingActivity, PENDING_ACTIVITY_POLL_INTERVAL_MS)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [contextLoading, context.mode, context.workspace, onWelcome, phase, refreshHandoff])

  useEffect(() => {
    if (contextLoading || context.mode !== AppContextMode.Workspace || !mappingActive || onWelcome) return

    let cancelled = false
    let inFlight = false

    async function pollProgress() {
      if (inFlight || !documentIsVisible()) return
      inFlight = true
      try {
        const progress = await fetchProgress()
        if (!cancelled) {
          setMappingProgress(progress)
          setAuthNotice(null)
        }
      } catch (error) {
        if (!cancelled && isApiAuthExpired(error)) setAuthNotice(AUTH_EXPIRED_NOTICE)
      } finally {
        inFlight = false
      }
    }

    void pollProgress()
    const timer = window.setInterval(pollProgress, PENDING_ACTIVITY_POLL_INTERVAL_MS)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [contextLoading, context.mode, context.workspace, mappingActive, onWelcome])

  useEffect(() => {
    if (contextLoading || context.mode !== AppContextMode.Workspace || onWelcome) return

    let cancelled = false
    let inFlight = false

    async function pollHealth() {
      if (inFlight || !documentIsVisible()) return
      inFlight = true
      try {
        const health = await fetchMapHealth()
        if (!cancelled) {
          setMapHealth(health)
          setAuthNotice(null)
        }
      } catch (error) {
        if (!cancelled && isApiAuthExpired(error)) setAuthNotice(AUTH_EXPIRED_NOTICE)
      } finally {
        inFlight = false
      }
    }

    void pollHealth()
    const timer = window.setInterval(pollHealth, HEALTH_POLL_INTERVAL_MS)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [contextLoading, context.mode, context.workspace, onWelcome])

  const routeCanvasV2Flow: CanvasV2Flow | null = useMemo(
    () => (view === HOME ? null : canvasV2?.flows.find((flow) => flow.id === view) ?? null),
    [canvasV2, view]
  )
  const activeJourney: Journey | null = useMemo(
    () =>
      view === HOME
        ? null
        : model.journeys.find((j) => j.id === view) ??
          (routeCanvasV2Flow ? journeyFromCanvasV2Flow(routeCanvasV2Flow) : null),
    [model.journeys, routeCanvasV2Flow, view]
  )
  const activeCanvasV2Flow: CanvasV2Flow | null = useMemo(
    () => (activeJourney ? canvasV2?.flows.find((flow) => flow.id === activeJourney.id) ?? null : null),
    [activeJourney, canvasV2]
  )
  const orderedJourneys = useMemo(
    () => orderJourneysByEdit(model.journeys, orderingChanges),
    [model.journeys, orderingChanges]
  )
  const selectedNode: FlowNode | null = useMemo(
    () =>
      activeJourney && selectedId
        ? findNode(activeJourney.nodes, selectedId) ?? findNativeDisplayNodeByDisplayId(activeCanvasV2Flow, selectedId)
        : null,
    [activeCanvasV2Flow, activeJourney, selectedId]
  )
  const selectedNativeNode: CanvasV2Node | null = useMemo(() => {
    if (!canvasV2 || !selectedNode?.native) return null
    const flowId = selectedNode.native.flowId || activeJourney?.id
    if (!flowId) return null
    return findCanvasV2Node(canvasV2, flowId, selectedNode.native.nodeId)
  }, [activeJourney?.id, canvasV2, selectedNode])

  function openAction(action: FlowAction, node: FlowNode) {
    if (!activeJourney || locked) return
    setEditRequest({ action, node, journeyTitle: activeJourney.title })
    setSelectedId(null) // the action moves to the bottom composer; let the popover go
  }

  async function stageEdit(edit: StagedEdit) {
    if (!activeJourney) return
    if (edit.delivery === EditDelivery.CanvasMap) {
      setEditRequest(null)
      try {
        await applyCanvasMapEdit(edit, canvasV2, activeJourney.id)
        await load()
      } catch (error) {
        if (
          error instanceof ApiError &&
          error.code === "REVISION_CONFLICT" &&
          !mapEditCreatesProposedNodes(edit.action)
        ) {
          try {
            const latest = await fetchCanvas()
            await applyCanvasMapEdit(edit, latest.canvasV2 ?? null, activeJourney.id)
            await load()
            return
          } catch {
            setAuthNotice("The map changed before that edit could be saved. Refresh and try again.")
            return
          }
        }
        setAuthNotice(canvasMapEditErrorNotice(error))
      }
      return
    }
    const input = {
      action: edit.action,
      summary: edit.summary,
      journeyId: activeJourney.id,
      journeyTitle: edit.journeyTitle,
      targetNodeId: edit.node.id,
      targetNativeNodeId: edit.node.native?.nodeId,
      targetNativeKind: edit.node.native?.nodeKind,
      targetFlowId: edit.node.native?.flowId || activeJourney.id,
      text1: edit.text1,
      text2: edit.text2,
    }
    if (edit.changeId) {
      useChanges.getState().updateChange(edit.changeId, input)
    } else {
      useChanges.getState().addChange(input)
    }
    setEditRequest(null)
  }

  function locateChange(change: ChangeEntry) {
    const journey = model.journeys.find((j) => j.id === change.journeyId) ?? null
    const nativeFlow = canvasV2?.flows.find((flow) => flow.id === change.journeyId) ?? null
    const node = journey
      ? findNode(journey.nodes, change.targetNodeId) ?? findNativeDisplayNodeByDisplayId(nativeFlow, change.targetNodeId)
      : null
    return { journey, node }
  }

  function selectChange(change: ChangeEntry) {
    const { journey, node } = locateChange(change)
    if (!journey || !node) return
    go(`/flows/${encodeURIComponent(journey.id)}`)
    setSelectedId(node.id)
    setEditRequest(null)
  }

  function modifyChange(change: ChangeEntry) {
    const { journey, node } = locateChange(change)
    if (!journey || !node) return
    go(`/flows/${encodeURIComponent(journey.id)}`)
    setSelectedId(node.id)
    setEditRequest({
      action: change.action,
      node,
      journeyTitle: change.journeyTitle,
      changeId: change.id,
      initialText1: change.text1 ?? "",
      initialText2: change.text2 ?? "",
    })
  }

  function onHandoffDone() {
    const applied = useChanges.getState().acknowledgeDone()
    if (!applied.length) return
    const editedAtByJourney = new Map<string, number>()
    for (const change of applied) {
      const editedAt = change.updatedAt || change.createdAt
      editedAtByJourney.set(
        change.journeyId,
        Math.max(editedAtByJourney.get(change.journeyId) ?? 0, editedAt)
      )
    }
    setModel((m) => {
      const next = applyChanges(m, applied)
      return {
        ...next,
        journeys: next.journeys.map((journey) => {
          const editedAt = editedAtByJourney.get(journey.id)
          return editedAt ? { ...journey, lastEditedAt: editedAt } : journey
        }),
      }
    })
    setSelectedId(null)
  }

  function onHandoffDismiss() {
    useChanges.getState().dismissHandoff()
  }

  async function requestMapFromAssistant() {
    if (
      canvasState.kind !== CanvasStateKind.Empty ||
      mapRequestInFlightRef.current ||
      mapRequestStatus === MappingRequestStatus.Sending ||
      mapRequestStatus === MappingRequestStatus.Sent
    ) {
      return
    }

    mapRequestInFlightRef.current = true

    const workspace = context.workspace || model.appName || "this project"
    const assistant = context.assistant || "your assistant"
    const clientChangeId = `map-request-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`
    const requestStartedAt = Date.now()
    const instruction =
      canvasState.fallbackPrompt ||
      [
        `Please explain how ${workspace} works in a simple guide.`,
        "Use the current project as the source of truth.",
        "If anything is unclear, ask me a focused question before changing files.",
        "Describe the main things people can do, save the AgentCanvas guide to .agentcanvas/canvas.ir.json, and update AgentCanvas progress while you work.",
      ].join(" ")

    setMapRequestStatus(MappingRequestStatus.Sending)
    setMapRequestError(null)
    try {
      const pending = await postChange({
        changeId: clientChangeId,
        clientChangeId,
        kind: kindForAction(FlowAction.Change),
        action: FlowAction.Change,
        title: `Write the AgentCanvas map for ${workspace}`,
        summary: instruction,
        journey: "All flows",
        journeyId: "map",
        journeyTitle: "All flows",
        targetStep: null,
        targetNodeId: null,
        refs: [],
        text1: `Create or refresh a simple guide to how ${workspace} works.`,
        text2: `Assigned to ${assistant}.`,
      })
      setMapRequestPendingId(pending.id)
      setMapRequestStatus(MappingRequestStatus.Sent)
      setMapRequestStartedAt(requestStartedAt)
      setMappingStage(0)
      setMappingProgress(null)
      setCanvasState({
        kind: CanvasStateKind.Reindexing,
        message: `Waiting for ${assistant}`,
        detail: `Your request is saved. Updates will appear here when ${assistant} starts.`,
      })
      try {
        await refreshHandoff()
      } catch (refreshError) {
        if (isApiAuthExpired(refreshError)) setAuthNotice(AUTH_EXPIRED_NOTICE)
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : "AgentCanvas could not create the map request."
      setMapRequestError(message)
      setMapRequestStatus(MappingRequestStatus.Failed)
      setMapRequestStartedAt(null)
    } finally {
      mapRequestInFlightRef.current = false
    }
  }

  const inJourney = view !== HOME && !!activeJourney
  const runtimeConnectionFailed = !contextLoading && runtimeConnection === RuntimeConnectionState.Disconnected
  const appAvailable = !contextLoading && context.mode !== AppContextMode.Landing
  const landing =
    onWelcome ||
    (!hasRuntimeLaunchContext && contextLoading) ||
    (!runtimeConnectionFailed && !contextLoading && context.mode === AppContextMode.Landing)
  const loading = mappingActive
  const workspaceState =
    canvasState.kind === CanvasStateKind.Loading ||
    canvasState.kind === CanvasStateKind.Reindexing ||
    canvasState.kind === CanvasStateKind.Empty ||
    canvasState.kind === CanvasStateKind.Error
      ? canvasState
      : null
  const readyMapRefreshAction = canvasState.kind === CanvasStateKind.Ready && !model.isDemo ? mapRefreshAction : null
  const refreshWorkspaceConnection = () => {
    retryContext()
    void load({ refresh: true })
  }
  const mapRequestHasProgress = hasProgressAfterRequest(mappingProgress, mapRequestStartedAt)
  const headerStatus =
    runtimeConnectionFailed
      ? "Connection needed"
      : mapRequestStatus === MappingRequestStatus.Sent && !mapRequestHasProgress
        ? `Waiting for ${context.assistant || "your assistant"}`
        : mappingActive && mapRequestHasProgress
          ? progressLabel(mappingProgress) || MAPPING_STAGES[mappingStage]
          : canvasSource.shortLabel
  const canvasHistoryAvailable =
    context.mode === AppContextMode.Workspace &&
    canvasState.kind === CanvasStateKind.Ready &&
    !model.isDemo &&
    !context.isDemo &&
    !loading
  const canvasHistoryBlocked = !canvasHistoryAvailable || hasLocalPendingChanges
  const activityAvailable =
    context.mode === AppContextMode.Workspace &&
    canvasState.kind === CanvasStateKind.Ready &&
    !model.isDemo &&
    !context.isDemo &&
    !loading
  const onboardingKey = useMemo(
    () => onboardingStorageKey(context.workspacePath || context.workspace || "unknown"),
    [context.workspace, context.workspacePath]
  )

  useEffect(() => {
    if (contextLoading || context.mode !== AppContextMode.Workspace || !context.workspacePath) {
      setOnboardingVisible(false)
      return
    }
    try {
      setOnboardingVisible(window.localStorage.getItem(onboardingKey) !== "dismissed")
    } catch {
      setOnboardingVisible(false)
    }
  }, [context.mode, context.workspacePath, contextLoading, onboardingKey])

  function dismissOnboarding() {
    try {
      window.localStorage.setItem(onboardingKey, "dismissed")
    } catch {
      // localStorage may be blocked; the in-memory dismissal still keeps this session quiet.
    }
    setOnboardingVisible(false)
  }

  if (landing) {
    return <LandingPage onEnterApp={appAvailable ? () => go("/") : undefined} />
  }

  if (contextLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background text-sm text-muted-foreground">
        <Sparkles className="mr-2 size-4 animate-pulse text-primary" />
        Opening AgentCanvas…
      </div>
    )
  }

  if (runtimeConnectionFailed) {
    return (
      <WorkspaceMappingState
        kind={CanvasStateKind.Error}
        stageIndex={0}
        workspaceName=""
        connectionError={runtimeConnectionError}
        onRetry={retryContext}
      />
    )
  }

  return (
    <div className="flex h-screen flex-col bg-background text-foreground">
      <header className="flex h-14 shrink-0 items-center gap-3 border-b px-4">
        {inJourney && (
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setLeftOpen((v) => !v)}
            aria-label={leftOpen ? "Hide menu" : "Show menu"}
            className="hidden shrink-0 text-muted-foreground md:flex"
          >
            {leftOpen ? <PanelLeftClose className="h-4 w-4" /> : <PanelLeftOpen className="h-4 w-4" />}
          </Button>
        )}
        <button
          type="button"
          onClick={() => go("/welcome")}
          aria-label="Back to the AgentCanvas home page"
          title="Home"
          className="shrink-0 transition-opacity hover:opacity-85"
        >
          <BrandMark />
        </button>
        <div className="min-w-0 flex-1">
          <Provenance context={context} demoMode={model.isDemo || context.isDemo} source={canvasSource} />
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          <span className="mr-1 hidden text-xs text-muted-foreground sm:inline">
            {headerStatus}
          </span>
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setHistoryOpen(true)}
            aria-label="Canvas history"
            title={hasLocalPendingChanges ? "Finish or discard pending changes before restoring history" : "Canvas history"}
            disabled={canvasHistoryBlocked}
          >
            <History className="h-4 w-4" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setActivityOpen(true)}
            aria-label="Activity"
            title="Activity"
            disabled={!activityAvailable}
          >
            <ListChecks className="h-4 w-4" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            onClick={() => load({ refresh: true })}
            aria-label="Refresh"
            disabled={loading}
          >
            <RefreshCw className={cn("h-4 w-4", loading && "animate-spin")} />
          </Button>
          <Button variant="ghost" size="icon" onClick={() => setDark((v) => !v)} aria-label="Toggle theme">
            {dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
          </Button>
        </div>
      </header>
      <CanvasHistoryDialog
        open={historyOpen}
        onOpenChange={setHistoryOpen}
        currentRevision={canvasRevisionRef.current ?? canvasV2?.revision ?? null}
        onRestored={() => load()}
      />
      <ActivityDialog open={activityOpen} onOpenChange={setActivityOpen} />
      <PendingRequestDialog
        link={pendingRequestLink}
        onOpenChange={(open) => {
          if (!open) setPendingRequestLink(null)
        }}
      />

      <div className="relative flex min-h-0 flex-1">
        {(!inJourney || leftOpen) && (
          <Rail
            journeys={orderedJourneys}
            activity={journeyActivity}
            activeId={view}
            onHome={() => {
              go("/")
              setSelectedId(null)
            }}
            onSelect={(id) => {
              go(`/flows/${encodeURIComponent(id)}`)
              setSelectedId(null)
            }}
          />
        )}

        <main className="min-w-0 flex-1 overflow-auto">
          {(model.isDemo || context.isDemo) && <DemoBanner thin={model.thin} />}
          {authNotice ? (
            <WorkspaceNotice message={authNotice} />
          ) : readyMapRefreshAction ? (
            <MapRefreshNotice
              action={readyMapRefreshAction}
              loading={loading}
              onRefresh={() => load({ refresh: true })}
            />
          ) : !model.isDemo && canvasState.kind === CanvasStateKind.Ready && canvasState.notice ? (
            <WorkspaceNotice message={canvasState.notice} />
          ) : null}
          {onboardingVisible && !model.isDemo && !context.isDemo && (
            <FirstRunTour workspaceName={context.workspace || model.appName} onDismiss={dismissOnboarding} />
          )}
          {workspaceState ? (
            <WorkspaceMappingState
              kind={workspaceState.kind}
              stageIndex={mappingStage}
              workspaceName={context.workspace || model.appName}
              message={workspaceState.message}
              detail={workspaceState.detail}
              nextSteps={workspaceState.nextSteps}
              fallbackPrompt={workspaceState.fallbackPrompt}
              progress={mappingProgress}
              source={canvasSource}
              assistantName={context.assistant || "your assistant"}
              requestStatus={mapRequestStatus}
              requestError={mapRequestError ?? undefined}
              requestPendingId={mapRequestPendingId ?? undefined}
              requestHasProgress={mapRequestHasProgress}
              agentConnected={Boolean(context.agentPresence?.connected)}
              onRequestMap={context.mode === AppContextMode.Workspace ? requestMapFromAssistant : undefined}
              onRetry={refreshWorkspaceConnection}
            />
          ) : inJourney ? (
            <JourneyView
              journey={activeJourney!}
              nativeFlow={activeCanvasV2Flow}
              selectedId={selectedId}
              locked={locked}
              onBack={() => {
                go("/")
                setSelectedId(null)
              }}
              onSelect={(id) => setSelectedId((cur) => (cur === id ? null : id))}
              onOpenFlow={(flowId) => {
                go(`/flows/${encodeURIComponent(flowId)}`)
                setSelectedId(null)
              }}
              onOpenPendingRequest={(link) => setPendingRequestLink(link)}
              onAction={openAction}
            />
          ) : (
            <Overview
              appName={model.appName}
              productLanguage={context.productLanguage}
              source={canvasSource}
              journeys={orderedJourneys}
              changes={localChanges}
              activity={journeyActivity}
              onOpen={(id) => go(`/flows/${encodeURIComponent(id)}`)}
            />
          )}
        </main>

        {/* Ephemeral step popover — floats over the canvas on desktop */}
        {inJourney && selectedNode && (
          <StepDetailsPanel
            node={selectedNode}
            nativeNode={selectedNativeNode}
            className="absolute bottom-24 right-4 top-4 z-30 hidden w-[340px] lg:flex"
            onClose={() => setSelectedId(null)}
            onAction={(a) => selectedNode && openAction(a, selectedNode)}
            onModifyChange={modifyChange}
            onCancelChange={(id) => useChanges.getState().undoChange(id)}
          />
        )}

        {/* Mobile stack + one dynamic bottom surface: composer / change tray / handoff */}
        <div className="pointer-events-none absolute inset-x-0 bottom-3 z-40 flex flex-col items-center gap-2 px-3 lg:bottom-6 lg:px-4">
          {inJourney && selectedNode && (
            <StepDetailsPanel
              node={selectedNode}
              nativeNode={selectedNativeNode}
              className="flex max-h-[52vh] w-full lg:hidden"
              onClose={() => setSelectedId(null)}
              onAction={(a) => selectedNode && openAction(a, selectedNode)}
              onModifyChange={modifyChange}
              onCancelChange={(id) => useChanges.getState().undoChange(id)}
            />
          )}
          <div className="pointer-events-auto flex w-full max-w-2xl justify-center">
            <BottomDock
              request={editRequest}
              onSubmitEdit={stageEdit}
              onCancelEdit={() => setEditRequest(null)}
              onHandoffDone={onHandoffDone}
              onHandoffDismiss={onHandoffDismiss}
              onSelectChange={selectChange}
              onModifyChange={modifyChange}
            />
          </div>
        </div>
      </div>
    </div>
  )
}

function onboardingStorageKey(workspaceKey: string): string {
  return `agentcanvas:onboarding:v${ONBOARDING_MAJOR_VERSION}:${hashWorkspaceKey(workspaceKey)}`
}

function hashWorkspaceKey(value: string): string {
  let hash = 2166136261
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index)
    hash = Math.imul(hash, 16777619)
  }
  return (hash >>> 0).toString(36)
}

function FirstRunTour({ workspaceName, onDismiss }: { workspaceName: string; onDismiss: () => void }) {
  return (
    <section className="border-b bg-clay/5 px-4 py-3">
      <div className="mx-auto flex max-w-5xl items-start gap-3">
        <div className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg bg-clay text-white">
          <Sparkles className="size-4" />
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold text-foreground">AgentCanvas is ready for {workspaceName}.</p>
          <p className="mt-1 text-sm leading-relaxed text-muted-foreground">
            Review the flows, change the map in plain English, and keep this page open while your agent works through requests.
          </p>
        </div>
        <Button variant="ghost" size="icon" onClick={onDismiss} aria-label="Dismiss first-run tour" className="shrink-0">
          <X className="size-4" />
        </Button>
      </div>
    </section>
  )
}

async function loadWorkspaceModel(refresh: boolean): Promise<WorkspaceModelResult> {
  const result = refresh ? await reindexCanvas() : await fetchCanvas()
  return {
    model: result.model,
    mapping: result.mapping,
    notice: mappingNotice(result.mapping),
    revision: result.revision,
    canvasV2: result.canvasV2,
  }
}

async function applyCanvasMapEdit(
  edit: StagedEdit,
  document: CanvasV2Document | null,
  fallbackFlowId: string
) {
  if (!document) throw new Error("No native canvas is available.")
  const flowId = edit.node.native?.flowId || fallbackFlowId
  const nodeId = edit.node.native?.nodeId
  if (!flowId || !nodeId) throw new Error("This canvas step is missing a native node reference.")

  const flow = findCanvasV2Flow(document, flowId)
  if (!flow) throw new Error("That canvas flow moved or no longer exists.")
  const node = flow.nodes.find((item) => item.id === nodeId) ?? null
  if (!node) throw new Error("That canvas step moved or no longer exists.")

  const clientChangeId = newCanvasMapChangeId()
  const operations = buildMapEditOperations(flow, node, edit.action, edit.text1, edit.text2, { clientChangeId })
  const applyResult = await applyCanvasBatch({
    base_revision: document.revision,
    authored_by: "agentcanvas-web",
    operations,
  })

  if (mapEditCreatesProposedNodes(edit.action)) {
    const proposedNodeIds = proposedNodeIdsFromOperations(operations)
    const proposedRefs = pendingRefsForProposedNodes(flow.id, proposedNodeIds)
    const request = changeRequestFor({
      id: clientChangeId,
      action: edit.action,
      kind: kindForAction(edit.action),
      summary: edit.summary,
      journeyId: flow.id,
      journeyTitle: edit.journeyTitle,
      targetNodeId: edit.node.id,
      targetNativeNodeId: node.id,
      targetNativeKind: node.kind,
      targetFlowId: flow.id,
      text1: edit.text1,
      text2: edit.text2,
      createdAt: Date.now(),
      updatedAt: Date.now(),
    })
    const pending = await postChange({ ...request, refs: [...(request.refs ?? []), ...proposedRefs] })
    const metadataOperations = withProposedNodeRefs(
      withPendingRequestMetadata(operations, {
        clientChangeId,
        pendingRequestId: pending.id,
      }),
      proposedNodeIds,
      proposedRefs
    ).filter((operation): operation is Extract<ReturnType<typeof buildMapEditOperations>[number], { op: "upsert_node" }> => {
      return operation.op === "upsert_node" && proposedNodeIds.includes(operation.node.id)
    })
    if (metadataOperations.length) {
      await applyCanvasMetadataBatch(metadataOperations, applyResult.revision)
    }
  }
}

async function applyCanvasMetadataBatch(
  operations: Extract<ReturnType<typeof buildMapEditOperations>[number], { op: "upsert_node" }>[],
  baseRevision: number
) {
  try {
    await applyCanvasBatch({
      base_revision: baseRevision,
      authored_by: "agentcanvas-web",
      operations,
    })
  } catch (error) {
    if (!(error instanceof ApiError) || error.code !== "REVISION_CONFLICT") throw error
    const latest = await fetchCanvas()
    await applyCanvasBatch({
      base_revision: latest.revision,
      authored_by: "agentcanvas-web",
      operations,
    })
  }
}

function newCanvasMapChangeId(): string {
  return `map-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`
}

function pendingRefsForProposedNodes(flowId: string, nodeIds: string[]): PendingRef[] {
  return nodeIds.map((id) => ({
    kind: PendingRefKind.Node,
    id,
    flow: flowId,
    source: "canvas.proposed_node",
  }))
}

function withProposedNodeRefs(
  operations: ReturnType<typeof buildMapEditOperations>,
  nodeIds: string[],
  refs: PendingRef[]
): ReturnType<typeof buildMapEditOperations> {
  if (!nodeIds.length || !refs.length) return operations
  return operations.map((operation) => {
    if (operation.op !== "upsert_node" || !nodeIds.includes(operation.node.id)) return operation
    return {
      ...operation,
      node: {
        ...operation.node,
        metadata: {
          ...(operation.node.metadata ?? {}),
          pending_refs: refs,
        },
      },
    }
  })
}

function canvasMapEditErrorNotice(error: unknown): string {
  if (error instanceof ApiError && error.code === "REFERENCED_ID_REMOVED") {
    const ids = referencedIdsFromError(error)
    return ids.length
      ? `This map change would remove something an open request still needs (${ids.join(", ")}). Finish or cancel that request first.`
      : "This map change would remove something an open request still needs. Finish or cancel that request first."
  }
  if (error instanceof ApiError && error.code === "WORKSPACE_BUSY") {
    return "AgentCanvas is already saving another map change. Try again in a moment."
  }
  return "AgentCanvas could not save that map change. Ask your agent to make the change instead."
}

function referencedIdsFromError(error: ApiError): string[] {
  const details = error.details
  if (!details || typeof details !== "object" || !("ids" in details)) return []
  const ids = (details as { ids?: unknown }).ids
  return Array.isArray(ids) ? ids.map((id) => String(id)).filter(Boolean) : []
}

function findCanvasV2Node(document: CanvasV2Document, flowId: string, nodeId: string): CanvasV2Node | null {
  const flow = findCanvasV2Flow(document, flowId)
  return flow?.nodes.find((node) => node.id === nodeId) ?? null
}

function findCanvasV2Flow(document: CanvasV2Document, flowId: string): CanvasV2Flow | null {
  return document.flows.find((item) => item.id === flowId) ?? null
}

function emptyWorkspaceDetail(result: WorkspaceModelResult): string {
  const source =
    "AgentCanvas checked this project, but it does not have a clear list of the main things people can do yet."
  return result.notice ? `${result.notice} ${source}` : source
}

function mappingNotice(mapping?: CanvasMapping): string | undefined {
  const warning = mapping?.warnings?.find(Boolean)
  if (warning) return plainMappingWarning(warning)
  if (isHeuristicMap(mapping)) {
    return "This is a rough first pass. Ask your assistant to review it before you rely on it."
  }
  return undefined
}

function isStarterMap(mapping?: CanvasMapping): boolean {
  return isHeuristicMap(mapping) && mapping?.primaryMode === CanvasMappingMode.LlmAssisted
}

function isUnreadyMap(mapping?: CanvasMapping): boolean {
  return Boolean(mapping?.empty || mapping?.source?.isEmpty || mapping?.mode === CanvasMappingMode.Empty || isStarterMap(mapping))
}

function unreadyMapTitle(result: WorkspaceModelResult): string {
  if (isStarterMap(result.mapping) && !result.mapping?.empty && !result.mapping?.source?.isEmpty) {
    return "Starter map needs review"
  }
  return "No plain-English map yet"
}

function starterMapDetail(result: WorkspaceModelResult, assistant?: string): string {
  const helper = assistant || "your assistant"
  if (result.mapping?.empty || result.mapping?.source?.isEmpty) {
    return `AgentCanvas checked the project, but it does not have a clear map yet. Ask ${helper} to write the main flows in everyday language; this page will update after the map is saved.`
  }
  const count = result.model.journeys.length
  const starter = count
    ? `AgentCanvas found ${count} possible flow${count === 1 ? "" : "s"}, but this is still a rough first pass.`
    : "AgentCanvas checked the project, but it does not have a clear map yet."
  return `${starter} Ask ${helper} to review it and write the map in everyday language; this page will update after the map is saved.`
}

function mapNextSteps(result: WorkspaceModelResult, context: AppContext): string[] {
  const helper = context.assistant || "your assistant"
  const starter = isStarterMap(result.mapping) && !result.mapping?.empty && !result.mapping?.source?.isEmpty

  if (starter) {
    return [
      `Copy the note below and send it to ${helper}.`,
      "Ask for the rough map to be checked and rewritten in plain English.",
      "When they are done, refresh this page.",
    ]
  }

  return [
    "Refresh to check whether a map was just added.",
    `If this still appears, copy the note below and send it to ${helper}.`,
    "When they are done, refresh this page.",
  ]
}

function mapFallbackPrompt(result: WorkspaceModelResult, context: AppContext): string {
  const workspace = context.workspace || result.model.appName || "this project"
  const action =
    isStarterMap(result.mapping) && !result.mapping?.empty && !result.mapping?.source?.isEmpty
      ? "review the AgentCanvas starter map"
      : "author an AgentCanvas map"
  return [
    `Please ${action} for ${workspace}.`,
    "Use the current project as the source of truth.",
    "If anything is unclear, ask me a focused question before changing files.",
    "Name the main user flows in plain English, save the AgentCanvas map to .agentcanvas/canvas.ir.json, and tell me to refresh this page.",
  ].join(" ")
}

function describeMapRefreshAction(
  source: CanvasSourceSummary,
  context: AppContext,
  appName: string
): MapRefreshAction | null {
  const workspace = context.workspace || appName || "this project"

  if (source.kind === CanvasSourceKind.StaleCache) {
    return {
      title: "This saved map may be out of date",
      detail: "Refresh to check the project now, or ask your assistant to update the saved map.",
      prompt: mapInstructionPrompt(MapInstructionKind.Refresh, workspace),
    }
  }

  if (source.kind === CanvasSourceKind.HeuristicProjection) {
    return {
      title: "Starter map needs review",
      detail: "Refresh to check for a newer map, or ask your assistant to rewrite this in plain English.",
      prompt: mapInstructionPrompt(MapInstructionKind.Starter, workspace),
    }
  }

  if (source.kind === CanvasSourceKind.NoFlow) {
    return {
      title: "No plain-English map yet",
      detail: "Refresh to check again, or ask your assistant to make the first map.",
      prompt: mapInstructionPrompt(MapInstructionKind.Author, workspace),
    }
  }

  return null
}

function mapInstructionPrompt(kind: MapInstructionKind, workspace: string): string {
  const opening =
    kind === MapInstructionKind.Refresh
      ? `Please refresh the AgentCanvas map for ${workspace}.`
      : kind === MapInstructionKind.Starter
        ? `Please turn the AgentCanvas starter view for ${workspace} into a clear plain-English map.`
        : `Please make an AgentCanvas map for ${workspace}.`

  return [
    opening,
    "Use the current project as the source of truth.",
    "If anything is unclear, ask me a focused question before changing files.",
    "Save the map to .agentcanvas/canvas.ir.json, then tell me to refresh this page.",
  ].join(" ")
}

function canvasSignature(result: WorkspaceModelResult): string {
  return JSON.stringify({
    model: result.model,
    mapping: result.mapping,
    notice: result.notice,
  })
}

function describeCanvasSource(
  context: AppContext,
  model: AppModel,
  state: CanvasState,
  health?: MapHealth | null
): CanvasSourceSummary {
  const mapping = state.mapping
  const source = mapping?.source
  const sourceKind = source?.kind || mapping?.mode
  const flowCount = source?.flowCount ?? mapping?.flowCount ?? model.journeys.length

  if (sourceKind === CanvasSourceKind.DemoFallback || mapping?.demoFallback || context.demoFallback) {
    return {
      kind: CanvasSourceKind.DemoFallback,
      label: "Example map",
      shortLabel: "Example",
      detail: "This is sample content because no project was connected yet.",
      tone: CanvasSourceTone.Info,
      flowCount,
    }
  }

  if (
    model.isDemo ||
    context.isDemo ||
    context.isDemoContent ||
    context.mode === AppContextMode.Demo ||
    sourceKind === CanvasSourceKind.Demo
  ) {
    return {
      kind: CanvasSourceKind.Demo,
      label: "Example project",
      shortLabel: "Example",
      detail: "You are looking at sample flows, not your own project.",
      tone: CanvasSourceTone.Info,
      flowCount,
    }
  }

  if (state.kind === CanvasStateKind.Loading || state.kind === CanvasStateKind.Reindexing) {
    return {
      kind: CanvasSourceKind.Loading,
      label: "Understanding your app",
      shortLabel: "Working",
      detail: "AgentCanvas is looking through the project and preparing a simple guide.",
      tone: CanvasSourceTone.Info,
      flowCount,
    }
  }

  if (state.kind === CanvasStateKind.Error) {
    return {
      kind: CanvasSourceKind.Error,
      label: "Project unavailable",
      shortLabel: "Needs attention",
      detail: "AgentCanvas could not open this project.",
      tone: CanvasSourceTone.Error,
      flowCount,
    }
  }

  if (state.kind === CanvasStateKind.Empty || !model.journeys.length) {
    return {
      kind: CanvasSourceKind.NoFlow,
      label: "Ready to understand your app",
      shortLabel: "Ready",
      detail: "Your assistant can turn this project into a clear guide to what people can do.",
      tone: CanvasSourceTone.Warning,
      flowCount,
    }
  }

  if (isStaleHealth(health)) {
    return {
      kind: CanvasSourceKind.StaleCache,
      label: "This may be out of date",
      shortLabel: "Needs refresh",
      detail: health?.freshness.reason || "The project changed after this was saved. Ask your assistant to refresh it if the behavior changed.",
      tone: CanvasSourceTone.Warning,
      flowCount,
    }
  }

  if (isStaleMap(mapping)) {
    return {
      kind: CanvasSourceKind.StaleCache,
      label: "This may be out of date",
      shortLabel: "Needs refresh",
      detail: "The project changed after this was saved. Ask your assistant to refresh it if the behavior changed.",
      tone: CanvasSourceTone.Warning,
      flowCount,
    }
  }

  if (isAgentAuthoredMap(mapping)) {
    return {
      kind: CanvasSourceKind.AgentAuthored,
      label: "Reviewed by your assistant",
      shortLabel: "Reviewed",
      detail: "Your assistant checked this project and wrote this explanation.",
      tone: CanvasSourceTone.Info,
      flowCount,
    }
  }

  if (isHeuristicMap(mapping)) {
    return {
      kind: CanvasSourceKind.HeuristicProjection,
      label: "First look",
      shortLabel: "Needs review",
      detail: "AgentCanvas found some early clues. Ask your assistant to check them before you rely on this explanation.",
      tone: CanvasSourceTone.Warning,
      flowCount,
    }
  }

  return {
    kind: CanvasSourceKind.Unknown,
    label: source?.label || "Saved explanation",
    shortLabel: "Saved",
    detail: "This is the latest explanation saved for this project.",
    tone: CanvasSourceTone.Default,
    flowCount,
  }
}

function isAgentAuthoredMap(mapping?: CanvasMapping): boolean {
  return (
    mapping?.mode === CanvasMappingMode.AgentAuthored ||
    mapping?.primaryMode === CanvasMappingMode.AgentAuthored ||
    mapping?.source?.kind === CanvasSourceKind.AgentAuthored
  )
}

function isHeuristicMap(mapping?: CanvasMapping): boolean {
  return (
    mapping?.mode === CanvasMappingMode.Heuristic ||
    mapping?.mode === CanvasMappingMode.HeuristicProjection ||
    mapping?.mode === CanvasMappingMode.Deterministic ||
    mapping?.source?.kind === CanvasSourceKind.HeuristicProjection
  )
}

function isStaleMap(mapping?: CanvasMapping): boolean {
  return Boolean(
    mapping?.stale ||
      mapping?.source?.isStale ||
      looksStale(mapping?.status) ||
      looksStale(mapping?.cacheStatus) ||
      looksStale(mapping?.source?.status) ||
      mapping?.warnings?.some((warning) => looksStale(warning) || /refreshed after|kept the canvas|behavior changed/i.test(warning))
  )
}

function isStaleHealth(health?: MapHealth | null): boolean {
  return Boolean(
    health &&
      (health.freshness.stale ||
        health.freshness.status === MapFreshnessStatus.Stale ||
        health.status === MapHealthStatus.StaleCanvasIr)
  )
}

function looksStale(value?: string): boolean {
  return Boolean(value && /stale|out[-_\s]?of[-_\s]?date|expired/i.test(value))
}

function plainMappingWarning(warning: string): string {
  if (/refreshed after|kept the canvas|behavior changed|stale|out[-_\s]?of[-_\s]?date/i.test(warning)) {
    return "This saved map may be out of date because the project changed after it was written."
  }
  if (/no displayable flows|no authored flows|no flows/i.test(warning)) {
    return "AgentCanvas could not find a clear plain-English map for this project yet."
  }
  if (/projection|llm|deterministic|heuristic|schema|contract|\.agentcanvas/i.test(warning)) {
    return "AgentCanvas found details that still need to be rewritten in plain English."
  }
  return warning
}

function plainLoadError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 401 || error.status === 403) {
      return "This AgentCanvas link does not have access to the project anymore. Open AgentCanvas again from the project."
    }
    if (error.status === 404) {
      return "The local AgentCanvas server did not have a map ready. Try again, or restart AgentCanvas for this project."
    }
  }
  return "Try again, or restart AgentCanvas if the local app stopped."
}

function refreshLoadErrorNotice(error: unknown): string {
  return `Couldn't refresh the project map. Showing the last saved map. ${plainLoadError(error)}`
}

function MapRefreshNotice({
  action,
  loading,
  onRefresh,
}: {
  action: MapRefreshAction
  loading: boolean
  onRefresh: () => void
}) {
  const [copyState, setCopyState] = useState<CopyState>(CopyState.Idle)

  async function copyPrompt() {
    try {
      await navigator.clipboard.writeText(action.prompt)
      setCopyState(CopyState.Copied)
      window.setTimeout(() => setCopyState(CopyState.Idle), 1600)
    } catch {
      setCopyState(CopyState.Manual)
    }
  }

  return (
    <div className="border-b bg-gold/10 px-4 py-2.5" aria-live="polite">
      <div className="mx-auto flex max-w-6xl flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <p className="text-sm font-medium text-foreground">{action.title}</p>
          <p className="text-xs text-muted-foreground">{action.detail}</p>
        </div>
        <div className="flex shrink-0 flex-wrap gap-2">
          <Button type="button" size="sm" onClick={onRefresh} disabled={loading}>
            <RefreshCw className={cn("size-3.5", loading && "animate-spin")} />
            Refresh map
          </Button>
          <Button type="button" variant="outline" size="sm" onClick={copyPrompt}>
            {copyState === CopyState.Copied ? <Check className="size-3.5" /> : <Clipboard className="size-3.5" />}
            {copyState === CopyState.Copied ? "Copied" : "Copy note for assistant"}
          </Button>
        </div>
      </div>
      {copyState === CopyState.Manual && (
        <div className="mx-auto mt-2 max-w-6xl">
          <Input
            readOnly
            value={action.prompt}
            aria-label="Instruction to paste into your agent"
            className="h-8 text-xs text-muted-foreground"
            onFocus={(event) => event.currentTarget.select()}
          />
        </div>
      )}
    </div>
  )
}

function WorkspaceNotice({ message }: { message: string }) {
  return (
    <div className="border-b bg-secondary/70 px-6 py-2.5 text-center text-xs text-muted-foreground">
      {message}
    </div>
  )
}

function StepDetailsPanel({
  node,
  nativeNode,
  className,
  onClose,
  onAction,
  onModifyChange,
  onCancelChange,
}: {
  node: FlowNode
  nativeNode?: CanvasV2Node | null
  className?: string
  onClose: () => void
  onAction: (action: FlowAction) => void
  onModifyChange: (change: ChangeEntry) => void
  onCancelChange: (id: string) => void
}) {
  return (
    <div
      className={cn(
        "pointer-events-auto flex-col overflow-hidden rounded-xl border bg-card shadow-xl animate-fade-in",
        className
      )}
    >
      <div className="flex items-center justify-between border-b px-3 py-2">
        <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
          Step details
        </span>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close"
          className="rounded-md p-1 text-muted-foreground hover:bg-secondary hover:text-foreground"
        >
          <X className="h-4 w-4" />
        </button>
      </div>
      <div className="min-h-0 flex-1 overflow-auto">
        <Inspector
          node={node}
          nativeNode={nativeNode}
          onAction={onAction}
          onModifyChange={onModifyChange}
          onCancelChange={onCancelChange}
        />
      </div>
    </div>
  )
}

function Rail({
  journeys,
  activity,
  activeId,
  onHome,
  onSelect,
}: {
  journeys: Journey[]
  activity: Map<string, JourneyActivity>
  activeId: string
  onHome: () => void
  onSelect: (id: string) => void
}) {
  return (
    <nav className="hidden w-64 shrink-0 flex-col border-r bg-card/60 px-3 py-4 md:flex">
      <button
        type="button"
        onClick={onHome}
        className={cn(
          "mb-1 flex items-center gap-2.5 rounded-lg px-3 py-2.5 text-left text-sm transition-colors",
          activeId === HOME ? "bg-secondary font-medium" : "text-muted-foreground hover:bg-secondary/60"
        )}
      >
        <Sparkles className={cn("h-4 w-4", activeId === HOME ? "text-clay" : "opacity-60")} />
        All flows
      </button>
      <p className="px-2 pb-2 pt-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
        Journeys
      </p>
      <div className="flex flex-col gap-0.5">
        {journeys.map((j) => {
          const active = j.id === activeId
          const state = activity.get(j.id) ?? JourneyActivity.Idle
          return (
            <button
              key={j.id}
              type="button"
              onClick={() => onSelect(j.id)}
              className={cn(
                "flex items-center gap-2.5 rounded-lg px-3 py-2.5 text-left text-sm transition-colors",
                active ? "bg-secondary font-medium text-foreground" : "text-muted-foreground hover:bg-secondary/60"
              )}
            >
              <JourneyDot state={state} active={active} />
              <span className="truncate">{j.title}</span>
            </button>
          )
        })}
      </div>
    </nav>
  )
}

function JourneyDot({ state, active }: { state: JourneyActivity; active: boolean }) {
  if (state === JourneyActivity.Working) {
    return <Loader2 aria-hidden="true" className="h-3.5 w-3.5 shrink-0 animate-spin text-primary" />
  }
  return (
    <span
      aria-hidden="true"
      className={cn(
        "h-2.5 w-2.5 shrink-0 rounded-full",
        state === JourneyActivity.Edited ? "bg-when-accent" : "bg-muted-foreground/35",
        active && "ring-4 ring-primary/10"
      )}
    />
  )
}

function orderJourneysByEdit(journeys: Journey[], changes: ChangeEntry[]) {
  const changedAtByJourney = new Map<string, number>()
  for (const change of changes) {
    const editedAt = change.updatedAt || change.createdAt
    changedAtByJourney.set(
      change.journeyId,
      Math.max(changedAtByJourney.get(change.journeyId) ?? 0, editedAt)
    )
  }
  return journeys
    .map((journey, index) => ({
      journey,
      index,
      editedAt: changedAtByJourney.get(journey.id) ?? journey.lastEditedAt ?? 0,
    }))
    .sort((a, b) => b.editedAt - a.editedAt || a.index - b.index)
    .map((item) => item.journey)
}

function getJourneyActivity(
  journeys: Journey[],
  localChanges: ChangeEntry[],
  orderingChanges: ChangeEntry[],
  phase: HandoffPhase,
  handoffItems: HandoffItem[]
) {
  const active = new Map<string, JourneyActivity>()
  for (const journey of journeys) {
    if (localChanges.some((change) => change.journeyId === journey.id)) {
      active.set(journey.id, JourneyActivity.Edited)
    }
  }

  if (phase === HandoffPhase.Sending || phase === HandoffPhase.Working) {
    const changesById = new Map(orderingChanges.map((change) => [change.id, change]))
    for (const item of handoffItems) {
      if (item.status === HandoffItemStatus.InProgress || item.status === HandoffItemStatus.Implemented) {
        const change = changesById.get(item.changeId)
        if (change) active.set(change.journeyId, JourneyActivity.Working)
      }
    }
  }

  return active
}

function preserveLocalJourneyRecency(next: AppModel, current: AppModel) {
  const editedAtByJourney = new Map(
    current.journeys
      .filter((journey) => journey.lastEditedAt)
      .map((journey) => [journey.id, journey.lastEditedAt!])
  )
  if (!editedAtByJourney.size) return next
  return {
    ...next,
    journeys: next.journeys.map((journey) => {
      const editedAt = editedAtByJourney.get(journey.id)
      return editedAt ? { ...journey, lastEditedAt: editedAt } : journey
    }),
  }
}

function journeyFromCanvasV2Flow(flow: CanvasV2Flow): Journey {
  const entryNode = flow.nodes.find((node) => node.id === flow.entryNode)
  return {
    id: flow.id,
    title: flow.title,
    summary: flow.summary,
    entry: entryNode?.title || flow.title,
    nodes: [],
  }
}

function JourneyView({
  journey,
  nativeFlow,
  selectedId,
  locked,
  onBack,
  onSelect,
  onOpenFlow,
  onOpenPendingRequest,
  onAction,
}: {
  journey: Journey
  nativeFlow?: CanvasV2Flow | null
  selectedId: string | null
  locked: boolean
  onBack: () => void
  onSelect: (id: string) => void
  onOpenFlow: (flowId: string) => void
  onOpenPendingRequest: (link: PendingRequestLink) => void
  onAction: (action: FlowAction, node: FlowNode) => void
}) {
  const displayNodeForNativeId = useMemo(
    () => (nativeId: string) => {
      const existing = findNodeByNativeId(journey.nodes, nativeId)
      if (existing) return existing
      const nativeNode = nativeFlow?.nodes.find((node) => node.id === nativeId)
      return nativeFlow && nativeNode ? nativeNodeToDisplayNode(nativeFlow.id, nativeNode) : null
    },
    [journey.nodes, nativeFlow]
  )

  return (
    <div className="mx-auto max-w-3xl px-6 py-7 pb-40">
      <button
        type="button"
        onClick={onBack}
        className="mb-4 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ChevronLeft className="h-4 w-4" /> All flows
      </button>
      <div className="mb-5">
        <h1 className="text-xl font-semibold tracking-tight">{journey.title}</h1>
        <p className="mt-1 text-sm text-muted-foreground">{journey.summary}</p>
        <p className="mt-3 inline-flex items-center gap-1.5 rounded-full bg-gold/10 px-3 py-1 text-xs text-muted-foreground">
          <Lightbulb className="h-3.5 w-3.5 text-gold" />
          Click a step to change it, or hover a step to add, branch, or remove right there.
        </p>
      </div>
      <div className={cn("transition-opacity", locked && "pointer-events-none opacity-60")}>
        {nativeFlow ? (
          <CanvasV2FlowCanvas
            flow={nativeFlow}
            selectedDisplayId={selectedId}
            displayNodeForNativeId={displayNodeForNativeId}
            onSelectDisplayNode={onSelect}
            onOpenFlow={onOpenFlow}
            onOpenPendingRequest={onOpenPendingRequest}
            onAction={onAction}
          />
        ) : (
          <FlowColumn nodes={journey.nodes} selectedId={selectedId} onSelect={onSelect} onAction={onAction} />
        )}
      </div>
    </div>
  )
}

function DemoBanner({ thin }: { thin?: boolean }) {
  return (
    <div className="border-b bg-accent/40 px-6 py-2.5 text-center text-xs text-accent-foreground">
      {thin
        ? "We're still learning this project. Here's what we can see so far."
        : "This is an example. Open AgentCanvas inside your own project to see what it does."}
    </div>
  )
}
