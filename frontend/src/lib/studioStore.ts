import { useStore } from "zustand"
import { createStore } from "zustand/vanilla"
import { isDemoLaunch, studioApi, uniqueRunLogs, StudioApiError, type StudioApi, type StudioBootstrapOptions, type StudioEventSubscription } from "./studioApi"
import { demoBootstrap, demoProposal, demoVerified } from "./studioDemo"
import {
  diffCounts, formatRef, isPendingRun, type AnnotationInput, type RunInput, type RunLog,
  type StudioAnnotation, type StudioBootstrapResponse, type StudioDocument, type StudioEvent,
  type StudioFlow, type StudioRun, type StudioTab,
} from "./studioTypes"

type StudioStoreOptions = { api?: StudioApi; eventSource?: typeof EventSource }
type AnnotationPatch = Partial<Pick<StudioAnnotation, "text" | "resolved">>

export interface StudioState {
  data: StudioBootstrapResponse | null
  activeRun: StudioRun | null
  loading: boolean
  error: string | null
  actionError: string | null
  activeTab: StudioTab
  activeFlowId: string | null
  selectedNodeIds: string[]
  includeAllPins: boolean
  inspectedNodeId: string | null
  inspectedComponentId: string | null
  diffOnlyFilter: boolean
  searchQuery: string
  pinMode: boolean
  commandDockOpen: boolean
  darkMode: boolean
  sidebarOpen: boolean
  setTab: (tab: StudioTab) => void
  setActiveFlowId: (id: string | null) => void
  setSelectedNodeIds: (ids: string[]) => void
  toggleNodeSelection: (id: string) => void
  setIncludeAllPins: (value: boolean) => void
  setInspectedNode: (id: string | null) => void
  setInspectedComponent: (id: string | null) => void
  clearInspection: () => void
  goToFlow: (id: string) => void
  setDiffOnlyFilter: (value: boolean) => void
  setSearchQuery: (value: string) => void
  setPinMode: (value: boolean) => void
  setCommandDockOpen: (value: boolean) => void
  setDarkMode: (value: boolean) => void
  setSidebarOpen: (value: boolean) => void
  bootstrap: (options?: StudioBootstrapOptions) => Promise<void>
  startRun: (input: RunInput) => Promise<void>
  answerRun: (answer: string) => Promise<void>
  approvePlan: () => Promise<void>
  discardPlan: () => Promise<void>
  cancelRun: () => Promise<void>
  dismissRun: () => void
  addAnnotation: (input: AnnotationInput) => Promise<void>
  editAnnotation: (id: string, patch: AnnotationPatch) => Promise<void>
  resolveAnnotation: (id: string, resolved: boolean) => Promise<void>
  deleteAnnotation: (id: string) => Promise<void>
  copySpatialBrief: (prompt?: string) => Promise<string | null>
  handleEvent: (event: StudioEvent) => void
  disconnectEvents: () => void
}

type StudioData = Pick<StudioState, "data" | "activeRun">

const clearInspection = { inspectedNodeId: null, inspectedComponentId: null }

const landingSnapshot: StudioBootstrapResponse = {
  ok: true, mode: "landing", workspace: "", workspace_name: "",
  git: { branch: null, head: null, dirty: false, changed_files: [] },
  runner: { preferred: "copy", available: [] },
  has_mapped_canvas: false, stale_node_ids: [],
  document: { schema: "agentcanvas.studio.v3", components: [], component_edges: [], flows: [] },
  annotations: [], active_run: null, recent_runs: [],
}

function timestamp() { return new Date().toISOString() }

function failureMessage(error: unknown) {
  if (error instanceof StudioApiError && error.kind === "auth") return "This AgentCanvas link is no longer authorized. Reopen Studio from the terminal."
  return error instanceof Error ? error.message : "The request could not be completed."
}

function withAnnotation(data: StudioBootstrapResponse, annotation: StudioAnnotation): StudioBootstrapResponse {
  const annotations = data.annotations.some((item) => item.id === annotation.id)
    ? data.annotations.map((item) => item.id === annotation.id ? annotation : item)
    : [...data.annotations, annotation]
  return { ...data, annotations }
}

function mergeLogs(previous: RunLog[], incoming: RunLog[]) {
  const logs = uniqueRunLogs([...previous, ...incoming])
  if (logs.length === previous.length) return previous
  return logs.sort((a, b) => a.at.localeCompare(b.at)).slice(-300)
}

function foregroundRun(active: StudioRun | null, recent: StudioRun[]) {
  return isPendingRun(active) ? active : recent.find(isPendingRun) ?? active
}

function withRun(state: StudioData, incoming: StudioRun): StudioData {
  if (!state.data) return state
  const previous = state.activeRun?.id === incoming.id ? state.activeRun : state.data.recent_runs.find((run) => run.id === incoming.id)
  const run = { ...incoming, logs: mergeLogs(previous?.logs ?? [], incoming.logs) }
  const recent = [run, ...state.data.recent_runs.filter((item) => item.id !== run.id)]
  const activeRun = foregroundRun(isPendingRun(state.activeRun) && state.activeRun?.id !== run.id ? state.activeRun : run, recent)
  return {
    activeRun,
    data: {
      ...state.data,
      active_run: isPendingRun(activeRun) ? activeRun : null,
      recent_runs: recent.filter((item, index) => index < 20 || isPendingRun(item)),
    },
  }
}

function appendLog(run: StudioRun | null, runId: string, entry: RunLog) {
  if (!run || run.id !== runId) return run
  const logs = mergeLogs(run.logs, [entry])
  return logs === run.logs ? run : { ...run, logs }
}

export function reduceStudioEvent(state: StudioData, event: StudioEvent): StudioData {
  const { data } = state
  if (!data) return state
  switch (event.type) {
    case "studio.updated":
      return { ...state, data: { ...data, ...event.payload } }
    case "run.updated":
      return withRun(state, event.payload.run)
    case "studio.resync":
      return state
    case "run.log": {
      const { run_id, entry } = event.payload
      return {
        activeRun: appendLog(state.activeRun, run_id, entry),
        data: {
          ...data,
          active_run: appendLog(data.active_run, run_id, entry),
          recent_runs: data.recent_runs.map((run) => appendLog(run, run_id, entry) ?? run),
        },
      }
    }
    case "annotations.updated": {
      const payload = event.payload
      if ("annotations" in payload) return { ...state, data: { ...data, annotations: payload.annotations } }
      if ("annotation" in payload) return { ...state, data: withAnnotation(data, payload.annotation) }
      const id = "id" in payload ? payload.id : payload.deleted
      return { ...state, data: { ...data, annotations: data.annotations.filter((item) => item.id !== id) } }
    }
  }
}

export function visibleDocument(state: Pick<StudioState, "data" | "activeRun" | "activeTab">): StudioDocument | null {
  const run = state.activeRun
  return (state.activeTab === "diff" && run?.status === "awaiting_approval" ? run.proposed_document : null) ?? state.data?.document ?? null
}

function hasDiff(flow: StudioFlow) {
  const counts = diffCounts(flow.nodes)
  return counts.added + counts.modified + counts.removed > 0
    || Boolean(flow.diff_status && flow.diff_status !== "unchanged")
    || flow.edges.some((edge) => edge.diff_status && edge.diff_status !== "unchanged")
}

function chooseFlow(document: StudioDocument | null | undefined, id: string | null, preferDiff = false) {
  const current = document?.flows.find((flow) => flow.id === id)
  if (current && (!preferDiff || hasDiff(current))) return current.id
  return (preferDiff ? document?.flows.find(hasDiff)?.id : null) ?? current?.id ?? document?.flows[0]?.id ?? null
}

function proposalView(state: StudioState, run: StudioRun | null) {
  if (run?.kind !== "plan" || run.status !== "awaiting_approval" || !run.proposed_document) return {}
  if (state.activeRun?.id === run.id && state.activeRun.status === "awaiting_approval") return {}
  return {
    activeTab: "diff" as const,
    activeFlowId: chooseFlow(run.proposed_document, run.flow_id ?? state.activeFlowId, true),
    diffOnlyFilter: true, ...clearInspection, selectedNodeIds: [],
  }
}

export function scopedContext(state: StudioState) {
  const document = visibleDocument(state)
  const system = state.activeTab === "system"
  const flow = system ? undefined : document?.flows.find((item) => item.id === state.activeFlowId) ?? document?.flows[0]
  const component = system ? document?.components.find((item) => item.id === state.inspectedComponentId) : undefined
  const selected = flow?.nodes.filter((node) => state.selectedNodeIds.includes(node.id)) ?? []
  const pins = state.data?.annotations.filter((pin) => {
    if (pin.resolved) return false
    if (system) return state.includeAllPins || (component && pin.target_type === "component" && pin.target_id === component.id)
    if (!flow || (pin.flow_id && pin.flow_id !== flow.id)) return false
    if (pin.target_type === "flow") return pin.target_id === flow.id
    if (pin.target_type === "component") return flow.component_ids.includes(pin.target_id)
    return flow.nodes.some((node) => node.id === pin.target_id)
  }) ?? []
  return { document, flow, component, selected, pins }
}

export function spatialBrief(state: StudioState, prompt?: string): string | null {
  const { document, flow, component, selected, pins } = scopedContext(state)
  if (!document || !state.data) return null
  const { git, workspace_name, mode } = state.data
  const names = new Map(document.components.map(({ id, name }) => [id, name]))
  const steps = selected.length ? selected : state.activeTab !== "system" ? flow?.nodes ?? [] : []
  const lines = [
    `# AgentCanvas spatial brief · ${workspace_name}`,
    mode === "demo" ? "Interactive Sandbox fixture" : "",
    git.branch ? `Branch: ${git.branch}` : "",
    git.diff_base ? `Diff base: ${git.diff_base}` : "",
    prompt?.trim() ? `\n## Request\n\n${prompt.trim()}` : "",
    flow ? `\n## Journey\n\n${flow.title} · ${flow.trigger}\n\n${flow.summary}` : "",
    component ? `\n## Component\n\n${component.name} · ${component.path}\n\n${component.summary}` : "",
    steps.length ? `\n## ${selected.length ? "Selected steps" : "Journey steps"}` : "",
    ...steps.map((node) => {
      const component = node.component_id ? names.get(node.component_id) : undefined
      const refs = node.code_refs.map((ref) => `\`${formatRef(ref)}\``).join(", ")
      return `- **@${node.title}** (${node.kind}${component ? `, ${component}` : ""})${refs ? ` — ${refs}` : ""}`
    }),
    pins.length ? "\n## Open pins" : "",
    ...pins.map((pin) => `- ${pin.target_type} \`${pin.target_id}\`${pin.flow_id ? ` in \`${pin.flow_id}\`` : ""}: ${pin.text}`),
  ]
  return lines.filter(Boolean).join("\n") + "\n"
}

type RunChange = "answer" | "approve" | "cancel" | "discard"

export function createStudioStore({ api = studioApi, eventSource }: StudioStoreOptions = {}) {
  let connection: StudioEventSubscription | undefined
  let launch: StudioBootstrapOptions = {}
  let workspaceSessionKey: string | null = null
  let session = 0
  let sequence = 0
  let changingRun = false
  let reconnectEvents: StudioEvent[] | null = null
  let refreshQueued = false
  const streamedRuns = new Map<string, number>()
  const deletedAnnotationIds = new Set<string>()
  const delays = new Map<ReturnType<typeof setTimeout>, () => void>()

  function resetConnection() {
    session++
    connection?.close()
    connection = undefined
    reconnectEvents = null
    refreshQueued = false
    streamedRuns.clear()
    deletedAnnotationIds.clear()
    changingRun = false
    for (const cancel of delays.values()) cancel()
    delays.clear()
  }

  function delay(ms: number) {
    return new Promise<boolean>((resolve) => {
      const timer = setTimeout(() => {
        delays.delete(timer)
        resolve(true)
      }, ms)
      delays.set(timer, () => { clearTimeout(timer); resolve(false) })
    })
  }

  return createStore<StudioState>((set, get) => {
    const actionError = (error: unknown) => set({ actionError: failureMessage(error) })

    function setRun(run: StudioRun, showProposal = true) {
      set((state) => {
        const updated = withRun(state, run)
        return {
          ...updated, actionError: null,
          ...(showProposal || updated.activeRun?.id !== run.id ? proposalView(state, updated.activeRun) : {}),
        }
      })
    }

    async function refreshSnapshot(savedSession: number) {
      const events: StudioEvent[] = []
      reconnectEvents = events
      refreshQueued = false
      try {
        const snapshot = await api.bootstrap(launch)
        if (savedSession !== session || reconnectEvents !== events) return
        if (snapshot.mode !== "workspace") throw new Error("The workspace session is no longer available. Reopen Studio from the terminal.")
        const previous = get()
        const mergeRun = (run: StudioRun) => {
          const cached = previous.activeRun?.id === run.id ? previous.activeRun : previous.data?.recent_runs.find(({ id }) => id === run.id)
          return { ...run, logs: mergeLogs(cached?.logs ?? [], run.logs) }
        }
        const recent_runs = snapshot.recent_runs.map(mergeRun)
        const latest = snapshot.active_run ? mergeRun(snapshot.active_run) : recent_runs.find((run) => run.id === previous.activeRun?.id)
        const activeRun = foregroundRun(latest ?? (isPendingRun(previous.activeRun) ? null : previous.activeRun), recent_runs)
        const data = events.reduce<StudioData>(reduceStudioEvent, {
          data: { ...snapshot, recent_runs, active_run: isPendingRun(activeRun) ? activeRun : null,
            annotations: snapshot.annotations.filter(({ id }) => !deletedAnnotationIds.has(id)) },
          activeRun,
        })
        const tabState = proposalView(previous, data.activeRun)
        const document = visibleDocument({ ...previous, ...data, ...tabState })
        set({ ...data, error: null, activeFlowId: chooseFlow(document, previous.activeFlowId), ...tabState })
      } catch (error) {
        if (savedSession === session && reconnectEvents === events) set({ error: failureMessage(error) })
      } finally {
        if (reconnectEvents === events) {
          reconnectEvents = null
          if (refreshQueued) void refreshSnapshot(savedSession)
        }
      }
    }

    function subscribe(savedSession: number) {
      const reconcile = () => { if (savedSession === session) void refreshSnapshot(savedSession) }
      const reconcileAfterPending = () => {
        if (savedSession !== session) return
        if (reconnectEvents) refreshQueued = true
        else reconcile()
      }
      connection = api.subscribeEvents(launch, {
        onOpen: reconcile,
        onSequenceGap: reconcileAfterPending,
        onCanvasUpdated: reconcileAfterPending,
        onError: () => {
          if (savedSession === session) set({ error: "Live updates disconnected. Reconnecting…" })
        },
        onEvent: (event) => {
          if (savedSession === session) get().handleEvent(event)
        },
      }, eventSource)
    }

    async function runRequest(action: () => Promise<{ run: StudioRun }>, showProposal = true) {
      if (changingRun) return
      changingRun = true
      const savedSession = session
      const sequenceBeforeRequest = sequence
      set({ actionError: null })
      try {
        const { run } = await action()
        if (savedSession === session && (streamedRuns.get(run.id) ?? 0) <= sequenceBeforeRequest) {
          reconnectEvents?.push({ type: "run.updated", payload: { run } })
          setRun(run, showProposal)
        }
      } catch (error) {
        if (savedSession === session) actionError(error)
      } finally {
        if (savedSession === session) changingRun = false
      }
    }

    async function streamDemo(run: StudioRun, messages: [stage: string, tool: string, message: string][]) {
      const savedSession = session
      for (const [stage, tool, message] of messages) {
        if (!await delay(400) || savedSession !== session || get().activeRun?.id !== run.id || get().activeRun?.status !== "running") return false
        get().handleEvent({
          type: "run.log",
          payload: { run_id: run.id, entry: { id: crypto.randomUUID(), at: timestamp(), kind: stage, text: message, tool } },
        })
      }
      return true
    }

    async function startDemo(input: RunInput, data: StudioBootstrapResponse) {
      const run: StudioRun = {
        ...input, id: crypto.randomUUID(), status: "running", runner: "codex", created_at: timestamp(), started_at: timestamp(),
        logs: [], changed_files: [],
      }
      setRun(run)
      if (input.kind === "diff") get().setTab("diff")
      const plan = input.kind === "plan"
      const build = input.kind === "build"
      const scope = data.document.flows.find((flow) => flow.id === input.flow_id)?.title ?? "Shopfront Commerce"
      if (!await streamDemo(run, [
        ["Scope", "canvas.read", `Read the graph and pins for ${scope}.`],
        ["Trace", "code.search", "Followed the request through the checkout and receipt boundaries."],
        ["Review", "git.diff", "Compared referenced behavior with main."],
        ["Draft", "canvas.layout", plan || build ? "Staged behavior changes and their code references." : "Updated the diagram with the sandbox snapshot."],
        ["Ready", "studio.publish", build ? "Prepared the changes to apply." : plan ? "Proposed diff is ready to review." : "Sandbox diagram is ready."],
      ])) return
      if (!plan && !build) {
        setRun({ ...run, status: "completed", finished_at: timestamp() })
        return
      }
      const document = demoProposal(data.document, input.flow_id ?? "", input.node_ids ?? [], input.prompt ?? "")
      if (build) {
        await applyDemo(run, document)
        return
      }
      setRun({
        ...run, status: "awaiting_approval", proposed_document: document,
        plan_summary: "Record a durable attempt, retry only temporary failures, and keep the surrounding journey connected.",
      })
    }

    async function applyDemo(running: StudioRun, proposal: StudioDocument) {
      if (!await streamDemo(running, [
        ["Apply", "workspace.patch", "Applied the behavior changes to the sandbox."],
        ["Check", "typecheck", "TypeScript validation passed."],
        ["Verify", "vitest", "Replay safety and transient retry tests passed."],
        ["Record", "git.status", "Collected changed fixture files and code references."],
        ["Complete", "studio.publish", "Verified the affected steps."],
      ])) return
      const document = demoVerified(proposal)
      const changedFiles = [...new Set(document.flows.flatMap((flow) => flow.nodes)
        .filter((node) => node.diff_status === "added" || node.diff_status === "modified")
        .flatMap((node) => node.code_refs.map((ref) => ref.path)))]
      get().handleEvent({ type: "studio.updated", payload: { document, has_mapped_canvas: true, stale_node_ids: get().data?.stale_node_ids ?? [] } })
      set((state) => state.data ? { data: { ...state.data, git: { ...state.data.git, dirty: true, changed_files: changedFiles } } } : {})
      setRun({
        ...running, status: "completed", proposed_document: null, finished_at: timestamp(), changed_files: changedFiles,
        verification: {
          tests: [{ command: "vitest run checkout/retry.test.ts", passed: true, output: "4 tests passed · replay safety, retry limits, and failure reporting" }],
          changed_files: changedFiles,
        },
      })
    }

    async function changeRun(change: RunChange, answer?: string) {
      const { data, activeRun: run } = get()
      if (!data || !run || !isPendingRun(run)) return
      if (change === "approve" && (run.kind !== "plan" || run.status !== "awaiting_approval")) return
      if (change === "answer" && (run.status !== "needs_input" || !answer?.trim())) return
      if (change === "discard" && (run.kind !== "plan" || run.status !== "awaiting_approval")) return
      if (data.mode === "demo") {
        if (change === "approve" && run.proposed_document) {
          const running: StudioRun = { ...run, kind: "build", status: "running", started_at: timestamp() }
          setRun(running)
          await applyDemo(running, run.proposed_document)
        }
        if (change === "cancel" || change === "discard") {
          setRun({ ...run, status: change === "cancel" ? "cancelled" : "discarded", finished_at: timestamp() })
        }
        return
      }
      await runRequest(async () => {
        if (change === "approve") return api.answerRun(run.id, { approve: true })
        if (change === "answer") return api.answerRun(run.id, { answer: answer?.trim() })
        if (change === "discard") {
          const result = await api.discardRun(run.id)
          return { run: result.run ?? { ...run, status: "discarded" as const, finished_at: timestamp() } }
        }
        return api.cancelRun(run.id)
      }, false)
    }

    async function updatePins(mutation: (data: StudioBootstrapResponse) => Promise<StudioEvent | null>) {
      const { data } = get()
      if (!data) return
      const savedSession = session
      set({ actionError: null })
      try {
        const event = await mutation(data)
        if (event && savedSession === session) get().handleEvent(event)
      } catch (error) {
        if (savedSession === session) actionError(error)
      }
    }

    return {
      data: null, activeRun: null, loading: false, error: null, actionError: null,
      activeTab: "system", activeFlowId: null, selectedNodeIds: [], includeAllPins: false, ...clearInspection,
      diffOnlyFilter: false, searchQuery: "", pinMode: false, commandDockOpen: false, darkMode: false,
      sidebarOpen: typeof window === "undefined" || !window.matchMedia?.("(max-width: 660px)").matches,
      setTab: (activeTab) => set((state) => {
        if (activeTab === state.activeTab) return state
        const document = visibleDocument({ ...state, activeTab })
        const activeFlowId = chooseFlow(document, state.activeFlowId, activeTab === "diff")
        const keepSelection = activeFlowId === state.activeFlowId && activeTab !== "system" && state.activeTab !== "system"
        return { activeTab, activeFlowId, ...clearInspection, pinMode: false, includeAllPins: false, selectedNodeIds: keepSelection ? state.selectedNodeIds : [] }
      }),
      setActiveFlowId: (activeFlowId) => set((state) => activeFlowId === state.activeFlowId ? state : { activeFlowId, selectedNodeIds: [], ...clearInspection }),
      goToFlow: (id) => { get().setTab("flows"); get().setActiveFlowId(id) },
      setSelectedNodeIds: (ids) => set({ selectedNodeIds: [...new Set(ids)] }),
      toggleNodeSelection: (id) => set((state) => ({ selectedNodeIds: state.selectedNodeIds.includes(id)
        ? state.selectedNodeIds.filter((candidate) => candidate !== id)
        : [...state.selectedNodeIds, id] })),
      setIncludeAllPins: (includeAllPins) => set({ includeAllPins }),
      setInspectedNode: (inspectedNodeId) => set({ inspectedNodeId, inspectedComponentId: null }),
      setInspectedComponent: (inspectedComponentId) => set({ inspectedComponentId, inspectedNodeId: null }),
      clearInspection: () => set(clearInspection),
      setDiffOnlyFilter: (diffOnlyFilter) => set({ diffOnlyFilter }),
      setSearchQuery: (searchQuery) => set({ searchQuery }),
      setPinMode: (pinMode) => set({ pinMode }),
      setCommandDockOpen: (commandDockOpen) => set({ commandDockOpen }),
      setDarkMode: (darkMode) => set({ darkMode }),
      setSidebarOpen: (sidebarOpen) => set({ sidebarOpen }),

      bootstrap: async (options = {}) => {
        const previous = get()
        const demo = isDemoLaunch(options)
        const nextSessionKey = demo ? null : api.workspaceSessionKey(options)
        const knownWorkspace = previous.data?.mode === "workspace" && !demo && workspaceSessionKey === nextSessionKey
        resetConnection()
        launch = options
        workspaceSessionKey = nextSessionKey
        const savedSession = session
        set({ data: knownWorkspace ? previous.data : null, activeRun: knownWorkspace ? previous.activeRun : null,
          loading: true, error: null, actionError: null, ...clearInspection, selectedNodeIds: [], includeAllPins: false, pinMode: false })
        const bootstrap = (data: StudioBootstrapResponse) => {
          if (savedSession !== session) return
          const activeRun = foregroundRun(data.active_run, data.recent_runs)
          const activeFlowId = chooseFlow(data.document, get().activeFlowId, get().activeTab === "diff")
          set({ data: { ...data, active_run: isPendingRun(activeRun) ? activeRun : null }, activeRun, activeFlowId, loading: false })
          if (data.mode === "workspace") subscribe(savedSession)
        }
        try {
          if (demo) bootstrap(demoBootstrap())
          else {
            const data = await api.bootstrap(options)
            if (data.mode !== "workspace" && (knownWorkspace || nextSessionKey)) {
              throw new Error("The workspace session is no longer available. Reopen Studio from the terminal.")
            }
            bootstrap(data.mode === "demo" ? landingSnapshot : data)
          }
        } catch (error) {
          if (savedSession !== session) return
          const unavailable = error instanceof StudioApiError && ["unreachable", "not_found", "html"].includes(error.kind)
          if (unavailable && !knownWorkspace && !nextSessionKey) bootstrap(landingSnapshot)
          else set({ loading: false, error: failureMessage(error) })
        }
      },

      handleEvent: (event) => {
        const previous = get()
        if (event.type === "studio.resync") {
          if (previous.data?.mode === "workspace") void refreshSnapshot(session)
          return
        }
        if (event.type === "annotations.updated") {
          const payload = event.payload
          if ("annotation" in payload && deletedAnnotationIds.has(payload.annotation.id)) return
          if ("annotations" in payload) {
            const ids = new Set(payload.annotations.map(({ id }) => id))
            for (const { id } of previous.data?.annotations ?? []) if (!ids.has(id)) deletedAnnotationIds.add(id)
            event = { ...event, payload: { annotations: payload.annotations.filter(({ id }) => !deletedAnnotationIds.has(id)) } }
          } else if ("deleted" in payload) {
            deletedAnnotationIds.add("id" in payload ? payload.id : payload.deleted)
          }
        }
        reconnectEvents?.push(event)
        const updated = reduceStudioEvent({ data: previous.data, activeRun: previous.activeRun }, event)
        if (event.type === "run.updated") {
          streamedRuns.set(event.payload.run.id, ++sequence)
          set({ ...updated, ...proposalView(previous, updated.activeRun) })
          return
        }
        if (event.type === "studio.updated") {
          const document = event.payload.document
          const activeFlowId = chooseFlow(document, previous.activeFlowId)
          const nodes = document.flows.find((item) => item.id === activeFlowId)?.nodes ?? []
          const selectedNodeIds = previous.selectedNodeIds.filter((id) => nodes.some((node) => node.id === id))
          const inspectedNodeId = nodes.some((node) => node.id === previous.inspectedNodeId) ? previous.inspectedNodeId : null
          const inspectedComponentId = document.components.some((component) => component.id === previous.inspectedComponentId) ? previous.inspectedComponentId : null
          set({ ...updated, activeFlowId, selectedNodeIds, inspectedNodeId, inspectedComponentId })
          return
        }
        set(updated)
      },

      startRun: async (input) => {
        const state = get()
        if (!state.data || state.data.mode === "landing" || isPendingRun(state.activeRun) || changingRun) return
        const { flow, component, selected, pins } = scopedContext(state)
        const ids = component ? [component.id] : selected.map(({ id }) => id)
        const scoped = input.kind === "plan" || input.kind === "build"
        const details: RunInput = {
          ...input,
          runner: input.runner ?? state.data.runner.preferred,
          diff_base: input.diff_base ?? launch.diffBase ?? state.data.git.diff_base ?? undefined,
          flow_id: input.flow_id ?? (scoped ? flow?.id : undefined),
          node_ids: input.node_ids ?? (scoped && ids.length ? ids : undefined),
          annotation_ids: input.annotation_ids ?? (scoped ? pins.map(({ id }) => id) : undefined),
        }
        if (state.data.mode === "demo") await startDemo(details, state.data)
        else if (details.runner === "copy") actionError(new Error("Copy Brief to continue in your coding agent."))
        else await runRequest(() => api.startRun(details))
      },
      answerRun: (answer) => changeRun("answer", answer),
      approvePlan: () => changeRun("approve"),
      cancelRun: () => changeRun("cancel"),
      discardPlan: () => changeRun("discard"),
      dismissRun: () => { if (!isPendingRun(get().activeRun)) set({ activeRun: null }) },

      addAnnotation: async (input) => updatePins(async (data) => {
        const text = input.text.trim()
        if (!text) throw new Error("Enter a note before adding the pin.")
        const annotation = data.mode === "demo"
          ? { ...input, id: crypto.randomUUID(), text, resolved: false, created_at: timestamp() }
          : (await api.createAnnotation({ ...input, text })).annotation
        return { type: "annotations.updated", payload: { annotation } }
      }),
      editAnnotation: async (id, patch) => updatePins(async (data) => {
        const existing = data.annotations.find((pin) => pin.id === id)
        if (!existing) return null
        const annotation = data.mode === "demo" ? { ...existing, ...patch } : (await api.updateAnnotation(id, patch)).annotation
        if (!get().data?.annotations.some((pin) => pin.id === id)) return null
        return { type: "annotations.updated", payload: { annotation } }
      }),
      resolveAnnotation: (id, resolved) => get().editAnnotation(id, { resolved }),
      deleteAnnotation: async (id) => updatePins(async (data) => {
        if (data.mode !== "demo") await api.deleteAnnotation(id)
        return { type: "annotations.updated", payload: { deleted: id } }
      }),
      copySpatialBrief: async (prompt) => {
        const brief = spatialBrief(get(), prompt)
        if (!brief) return null
        try {
          await navigator.clipboard.writeText(brief)
          set({ actionError: null })
          return brief
        } catch {
          actionError(new Error("Clipboard is unavailable."))
          return null
        }
      },

      disconnectEvents: resetConnection,
    }
  })
}

export const studioStore = createStudioStore()
const identity = (state: StudioState) => state

export function useStudioStore<T = StudioState>(selector: (state: StudioState) => T = identity as (state: StudioState) => T): T {
  return useStore(studioStore, selector)
}
