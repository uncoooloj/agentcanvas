import { afterEach, describe, expect, it, vi } from "vitest"
import { createElement } from "react"
import { renderToStaticMarkup } from "react-dom/server"
import { createStudioApi } from "@/lib/studioApi"
import { demoBootstrap, demoFileDiff, demoFileSlice, demoProposal, demoVerified } from "@/lib/studioDemo"
import { layoutFlow, layoutSystem, type LayoutNode } from "@/lib/studioLayout"
import { createStudioStore, visibleDocument } from "@/lib/studioStore"
import { diffCounts, type StudioAnnotation, type StudioRun } from "@/lib/studioTypes"
import { RunVerification } from "./CommandDock"

const demo = demoBootstrap()
const workspace = { ...demo, mode: "workspace" as const }
const runFixture = (overrides: Partial<StudioRun> = {}): StudioRun => ({
  id: "run-1", kind: "plan", status: "running", runner: "codex", logs: [], changed_files: [], ...overrides,
})

class StudioEventSource extends EventTarget {
  static current: StudioEventSource
  constructor() { super(); StudioEventSource.current = this }
  emit(type: string, payload: unknown) {
    this.dispatchEvent(new MessageEvent(type, { data: JSON.stringify(payload) }))
  }
  close() {}
}
const eventSource = StudioEventSource as unknown as typeof EventSource

function assertGraph(nodes: LayoutNode[], ids: string[]) {
  expect(nodes.map(({ id }) => id)).toEqual(ids)
  for (const [index, node] of nodes.entries()) {
    expect([node.x, node.y, node.width, node.height].every(Number.isFinite)).toBe(true)
    expect(node.width).toBeGreaterThan(0)
    expect(node.height).toBeGreaterThan(0)
    for (const other of nodes.slice(index + 1)) {
      const overlap = node.x < other.x + other.width && node.x + node.width > other.x
        && node.y < other.y + other.height && node.y + node.height > other.y
      expect(overlap, `${node.id} overlaps ${other.id}`).toBe(false)
    }
  }
}

describe("Studio layout", () => {
  it("positions every architectural component without overlaps", async () => {
    const { document } = demo
    assertGraph(await layoutSystem(document), document.components.map(({ id }) => id))
  })

  it("lays out each journey and fits uneven measured cards, cycles, and branches", async () => {
    for (const flow of demo.document.flows) {
      const tallId = flow.nodes[0].id
      const nodes = await layoutFlow(flow, { [tallId]: { width: 300, height: 450 } })
      assertGraph(nodes, flow.nodes.map(({ id }) => id))
      expect(nodes.find(({ id }) => id === tallId)?.height).toBe(450)
    }
  })
})

describe("Interactive Sandbox fixtures", () => {
  it("connects real graph endpoints and provides code evidence for every step", () => {
    const { document, git } = demo
    const components = new Set(document.components.map(({ id }) => id))
    const flowIds = new Set(document.flows.map(({ id }) => id))
    expect(components.size).toBe(6)
    expect(flowIds.size).toBe(4)
    expect(git.branch).toBe("feature/retry-sms-receipt")
    expect(diffCounts(document.flows.flatMap(({ nodes }) => nodes))).toEqual({ added: 2, modified: 2, removed: 1 })
    for (const { source, target } of document.component_edges) {
      expect(components.has(source) && components.has(target)).toBe(true)
    }
    for (const flow of document.flows) {
      const nodeIds = new Set(flow.nodes.map(({ id }) => id))
      expect(nodeIds.size).toBe(flow.nodes.length)
      expect(flow.nodes.length).toBeGreaterThanOrEqual(5)
      expect(flow.component_ids.every((id) => components.has(id))).toBe(true)
      for (const { source, target } of flow.edges) {
        expect(nodeIds.has(source) && nodeIds.has(target)).toBe(true)
      }
      for (const node of flow.nodes) {
        if (node.component_id) expect(components.has(node.component_id)).toBe(true)
        if (node.flow_ref) expect(flowIds.has(node.flow_ref)).toBe(true)
        expect(node.code_refs.length).toBeGreaterThan(0)
        for (const ref of node.code_refs) {
          const slice = demoFileSlice(ref.path, ref.line)
          expect(slice.lines.some(({ text }) => text.trim())).toBe(true)
          if (ref.line) expect(slice.lines.some(({ number }) => number === ref.line)).toBe(true)
        }
        if (node.diff_status && node.diff_status !== "unchanged") {
          expect(node.code_refs.some(({ path }) => demoFileDiff(path).has_diff)).toBe(true)
        }
      }
    }
  })

  it("can replan an already approved scope without duplicate steps or broken connections", () => {
    const source = demo.document.flows[0]
    const plan = demoProposal(demo.document, source.id, ["order-create"], "Record failed attempts")
    const secondPlan = demoProposal(demoVerified(plan), source.id, ["order-persist"], "Retry temporary storage errors")
    const flow = secondPlan.flows.find(({ id }) => id === source.id)!
    const ids = new Set(flow.nodes.map(({ id }) => id))
    expect(ids.size).toBe(source.nodes.length + 2)
    expect(flow.nodes.filter((node) => node.diff_status === "added").every((node) => node.status === "proposed")).toBe(true)
    expect(flow.edges.every((edge) => ids.has(edge.source) && ids.has(edge.target))).toBe(true)
    expect(flow.edges.filter((edge) => edge.source === "order-persist")).toHaveLength(1)
  })
})

describe("Studio transport", () => {
  afterEach(() => vi.unstubAllGlobals())

  it("authenticates API fetches with a header and the event stream with a query token", async () => {
    const fetcher = vi.fn<(url: string, init: RequestInit) => Promise<Response>>(async () => Response.json(demo))
    vi.stubGlobal("fetch", fetcher)
    const api = createStudioApi({ baseUrl: "http://studio.test", token: "studio-fixture-token" })
    await api.bootstrap({ diffBase: "main..HEAD" })
    const [request, init] = fetcher.mock.calls[0]
    expect(new URL(request).pathname).toBe("/api/studio")
    expect(new URL(request).searchParams.get("diffBase")).toBe("main..HEAD")
    expect(new URL(request).searchParams.has("token")).toBe(false)
    expect(new Headers(init.headers).get("X-AgentCanvas-Token")).toBe("studio-fixture-token")
    expect(new URL(api.eventUrl()).searchParams.get("token")).toBe("studio-fixture-token")
  })

  it("normalizes malformed runs and log entries across snapshots, run responses, and SSE", async () => {
    const log = { at: "2026-11-21T01:00:00Z", kind: "build", text: "Applying changes" }
    const run = {
      ...runFixture(),
      logs: [log, { ...log, id: "replay" }, null, "malformed", { at: log.at, kind: "build", text: 42 },
        { timestamp: log.at, message: "Runner emitted legacy activity" }],
      changed_files: ["src/main.ts", 12, null],
    }
    const malformedRun = { ...run, id: "malformed", status: "imaginary" }
    const fetcher = vi.fn().mockResolvedValueOnce(Response.json({
      ...workspace, active_run: { ...run, logs: { text: "not a list" } }, recent_runs: [malformedRun, null, run],
    })).mockResolvedValueOnce(Response.json({ ok: true, run }))
    vi.stubGlobal("fetch", fetcher)
    const api = createStudioApi()
    const snapshot = await api.bootstrap()
    expect(snapshot.active_run?.logs).toEqual([])
    expect(snapshot.recent_runs).toHaveLength(1)
    const expectedLogs = [log, { at: log.at, kind: "runner", text: "Runner emitted legacy activity" }]
    expect(snapshot.recent_runs[0].logs).toEqual(expectedLogs)
    const started = await api.startRun({ kind: "plan" })
    expect(started.run.logs).toEqual(expectedLogs)
    expect(started.run.changed_files).toEqual(["src/main.ts"])

    const onEvent = vi.fn()
    const subscription = api.subscribeEvents({}, { onEvent }, eventSource)
    StudioEventSource.current.emit("run.updated", { run: malformedRun })
    StudioEventSource.current.emit("run.updated", { run, seq: 1 })
    expect(onEvent).toHaveBeenCalledTimes(1)
    expect(onEvent).toHaveBeenCalledWith({ type: "run.updated", seq: 1, payload: { run: started.run } })
    subscription.close()
  })

  it("renders Lane A verification with a summary, output, tests, or changed files", async () => {
    const api = createStudioApi()
    const nested = {
      summary: "Verified checkout retries.",
      output: "Typecheck succeeded.",
      tests: [{ command: "vitest run checkout", passed: true, output: "4 tests passed." }],
      changed_files: ["checkout.ts"],
    }
    for (const verification of [
      { summary: nested.summary },
      { output: nested.output },
      { tests: nested.tests },
      { changed_files: nested.changed_files },
      { command: "tsc -b", passed: false },
      nested,
    ]) {
      vi.stubGlobal("fetch", async () => Response.json({
        ok: true, run: { ...runFixture({ kind: "build", status: "completed" }), verification },
      }))
      const { run } = await api.startRun({ kind: "build" })
      const html = renderToStaticMarkup(createElement(RunVerification, { run }))
      expect(html).toContain('aria-label="Verification"')
      if ("summary" in verification) expect(html).toContain(nested.summary)
      if ("output" in verification) expect(html).toContain(nested.output)
      if ("tests" in verification) expect(html).toContain("4 tests passed.")
      if ("changed_files" in verification) expect(html).toContain("checkout.ts")
      if ("command" in verification) expect(html).toContain("Failed")
    }
    vi.stubGlobal("fetch", async () => Response.json({
      ok: true, run: { ...runFixture({ kind: "build", status: "completed" }), verification_summary: "Agent verification complete." },
    }))
    const { run } = await api.startRun({ kind: "build" })
    expect(renderToStaticMarkup(createElement(RunVerification, { run }))).toContain("Agent verification complete.")
  })
})

describe("Studio state", () => {
  afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals() })

  it.each([
    () => Promise.resolve(new Response("Not found", { status: 404 })),
    () => Promise.resolve(new Response("<html>Static site</html>", { headers: { "content-type": "text/html" } })),
    () => Promise.reject(new TypeError("Failed to fetch")),
  ])("shows the landing page on a public static URL and enters demo only for ?demo=1", async (fetchResponse) => {
    vi.stubGlobal("fetch", fetchResponse)
    const location = { origin: "https://studio.test", search: "" }
    vi.stubGlobal("window", { location, sessionStorage: { getItem: () => null } })
    const store = createStudioStore()
    await store.getState().bootstrap()
    expect(store.getState().data?.mode).toBe("landing")
    location.search = "?demo=1"
    await store.getState().bootstrap()
    expect(store.getState().data?.mode).toBe("demo")
  })

  it("keeps connection errors for token-bound and previously open workspaces", async () => {
    const api = createStudioApi({ token: "recognized-token" })
    vi.stubGlobal("fetch", async () => new Response(null, { status: 404 }))
    const store = createStudioStore({ api })
    await store.getState().bootstrap()
    expect(store.getState().data).toBeNull()
    expect(store.getState().error).toBeTruthy()

    vi.stubGlobal("fetch", async () => Response.json(workspace))
    await store.getState().bootstrap()
    vi.stubGlobal("fetch", async () => { throw new TypeError("Network offline") })
    await store.getState().bootstrap()
    expect(store.getState().data?.mode).toBe("workspace")
    expect(store.getState().error).toMatch(/unreachable/)
  })

  it("recognizes the same workspace after its token moves from the URL to session storage", async () => {
    const location = { origin: "https://studio.test", search: "?token=recognized-token" }
    const storage = new Map<string, string>()
    vi.stubGlobal("window", { location, sessionStorage: {
      getItem: (key: string) => storage.get(key) ?? null,
      setItem: (key: string, value: string) => storage.set(key, value),
    } })
    const store = createStudioStore()
    vi.stubGlobal("fetch", async () => Response.json(workspace))
    await store.getState().bootstrap({ token: "recognized-token" })

    location.search = ""
    vi.stubGlobal("fetch", async () => { throw new TypeError("Workspace offline") })
    await store.getState().bootstrap()
    expect(store.getState().data?.mode).toBe("workspace")
    expect(store.getState().error).toMatch(/unreachable/)
  })

  it("handles SSE graph, run, log, and annotation updates", async () => {
    const store = createStudioStore()
    await store.getState().bootstrap({ demo: true })
    const { handleEvent } = store.getState()
    const document = { ...demo.document, components: demo.document.components.slice(0, 1) }
    handleEvent({ type: "studio.updated", payload: { document, has_mapped_canvas: true, stale_node_ids: ["old-step"] } })
    expect(store.getState().data?.document).toBe(document)
    expect(store.getState().data?.stale_node_ids).toEqual(["old-step"])

    const run = runFixture({ id: "run-sse" })
    handleEvent({ type: "run.updated", payload: { run } })
    const entry = { id: "log-sse", at: "2026-11-21T01:00:00Z", kind: "Inspect", tool: "read_file", text: "Read checkout route" }
    handleEvent({ type: "run.log", payload: { run_id: run.id, entry } })
    expect(store.getState().data?.active_run?.logs).toContainEqual(entry)
    handleEvent({ type: "run.updated", payload: { run: { ...run, status: "completed" } } })
    expect(store.getState().activeRun?.logs).toContainEqual(entry)

    const pin: StudioAnnotation = { id: "pin-sse", target_type: "node", target_id: "old-step", text: "Retain this", resolved: false }
    handleEvent({ type: "annotations.updated", payload: { annotations: [pin] } })
    expect(store.getState().data?.annotations).toEqual([pin])
    handleEvent({ type: "annotations.updated", payload: { id: pin.id, deleted: true } })
    expect(store.getState().data?.annotations).toEqual([])
    store.getState().disconnectEvents()
  })

  it("keeps a streamed terminal status when the start response arrives late", async () => {
    const api = createStudioApi()
    vi.spyOn(api, "bootstrap").mockResolvedValue({ ...demo, mode: "workspace" })
    let settle!: (value: { ok: true; run: StudioRun }) => void
    const deferred = new Promise<{ ok: true; run: StudioRun }>((resolve) => { settle = resolve })
    vi.spyOn(api, "startRun").mockReturnValue(deferred)
    const store = createStudioStore({ api })
    await store.getState().bootstrap()
    const starting = store.getState().startRun({ kind: "map" })
    const run = runFixture({ id: "map-fast", kind: "map" })
    store.getState().handleEvent({ type: "run.updated", payload: { run: { ...run, status: "completed" } } })
    settle({ ok: true, run })
    await starting
    expect(store.getState().activeRun?.status).toBe("completed")
    expect(store.getState().data?.active_run).toBeNull()
    store.getState().disconnectEvents()
  })

  it("omits implicit flow and node scope on System and includes pins only when explicitly scoped", async () => {
    const [flow, other] = demo.document.flows
    const [componentId] = flow.component_ids
    const annotations: StudioAnnotation[] = [
      { id: "flow-pin", target_type: "node", target_id: flow.nodes[0].id, flow_id: flow.id, text: "Flow note", resolved: false },
      { id: "other-pin", target_type: "flow", target_id: other.id, flow_id: other.id, text: "Other note", resolved: false },
      { id: "component-pin", target_type: "component", target_id: componentId, text: "Component note", resolved: false },
    ]
    const api = createStudioApi()
    vi.spyOn(api, "bootstrap").mockResolvedValue({ ...workspace, annotations })
    const startRun = vi.spyOn(api, "startRun").mockResolvedValue({ ok: true, run: runFixture({ status: "completed" }) })
    const store = createStudioStore({ api })
    await store.getState().bootstrap()
    const state = store.getState()
    state.goToFlow(flow.id)
    state.toggleNodeSelection(flow.nodes[0].id)
    await state.startRun({ kind: "plan" })
    expect(startRun).toHaveBeenLastCalledWith(expect.objectContaining({
      flow_id: flow.id, node_ids: [flow.nodes[0].id], annotation_ids: ["flow-pin", "component-pin"],
    }))
    state.setTab("system")
    await state.startRun({ kind: "plan" })
    const payload = JSON.parse(JSON.stringify(startRun.mock.lastCall![0]))
    expect(payload).not.toHaveProperty("flow_id")
    expect(payload).not.toHaveProperty("node_ids")
    expect(payload.annotation_ids).toEqual([])
    state.setInspectedComponent(componentId)
    await state.startRun({ kind: "build" })
    expect(startRun).toHaveBeenLastCalledWith(expect.objectContaining({ node_ids: [componentId], annotation_ids: ["component-pin"] }))
    state.setIncludeAllPins(true)
    await state.startRun({ kind: "build" })
    expect(startRun).toHaveBeenLastCalledWith(expect.objectContaining({
      annotation_ids: ["flow-pin", "other-pin", "component-pin"],
    }))
  })

  it.each(["delete", "SSE removal", "SSE replacement"])("ignores a late pin edit after %s", async (removal) => {
    const pin: StudioAnnotation = { id: "pin-1", target_type: "flow", target_id: demo.document.flows[0].id, text: "Original", resolved: false }
    const api = createStudioApi()
    vi.spyOn(api, "bootstrap").mockResolvedValue({ ...workspace, annotations: [pin] })
    vi.spyOn(api, "deleteAnnotation").mockResolvedValue({ ok: true })
    let settle!: (value: { ok: true; annotation: StudioAnnotation }) => void
    vi.spyOn(api, "updateAnnotation").mockReturnValue(new Promise((resolve) => { settle = resolve }))
    const store = createStudioStore({ api })
    await store.getState().bootstrap()
    const { editAnnotation, deleteAnnotation, handleEvent } = store.getState()
    const editing = editAnnotation(pin.id, { text: "A late edit" })
    if (removal === "delete") await deleteAnnotation(pin.id)
    else handleEvent({ type: "annotations.updated", payload: removal === "SSE removal" ? { deleted: pin.id } : { annotations: [] } })
    settle({ ok: true, annotation: { ...pin, text: "A late edit" } })
    await editing
    expect(store.getState().data?.annotations).toEqual([])
  })

  it("promotes a waiting run when the foreground run ends", async () => {
    const store = createStudioStore()
    await store.getState().bootstrap({ demo: true })
    const active = runFixture()
    const waiting = runFixture({ id: "waiting", status: "needs_input", question: "Which provider?" })
    const { handleEvent } = store.getState()
    handleEvent({ type: "run.updated", payload: { run: active } })
    handleEvent({ type: "run.updated", payload: { run: waiting } })
    expect(store.getState().activeRun?.id).toBe(active.id)
    handleEvent({ type: "run.updated", payload: { run: { ...active, status: "failed" } } })
    expect(store.getState().activeRun).toEqual(waiting)
    expect(store.getState().data?.active_run).toEqual(waiting)
  })

  it("resyncs on a gap or overflow and ignores a superseded refresh failure", async () => {
    const api = createStudioApi()
    const bootstrap = vi.spyOn(api, "bootstrap").mockResolvedValueOnce(workspace)
    const store = createStudioStore({ api, eventSource })
    await store.getState().bootstrap()
    const source = StudioEventSource.current
    let rejectRefresh!: (error: Error) => void
    bootstrap.mockReturnValueOnce(new Promise((_resolve, reject) => { rejectRefresh = reject }))
    const run = runFixture()
    const entry = { at: "2026-11-21T01:00:00Z", kind: "runner", text: "Working" }
    bootstrap.mockResolvedValueOnce({ ...workspace, active_run: { ...run, logs: [entry] } })
    source.emit("run.updated", { seq: 1, run })
    source.emit("run.log", { seq: 3, run_id: run.id, entry })
    expect(bootstrap).toHaveBeenCalledTimes(2)
    source.emit("studio.resync", { seq: 8 })
    expect(bootstrap).toHaveBeenCalledTimes(3)
    await Promise.resolve()
    rejectRefresh(new Error("Old request failed"))
    await Promise.resolve()
    expect(store.getState().error).toBeNull()
    source.emit("run.log", { seq: 9, run_id: run.id, entry })
    expect(store.getState().activeRun?.logs).toEqual([entry])
    bootstrap.mockResolvedValueOnce({ ...workspace, active_run: { ...run, logs: [entry] } })
    source.emit("run.updated", { seq: 10, run: { id: run.id, status: "invalid" } })
    expect(bootstrap).toHaveBeenCalledTimes(4)
    await Promise.resolve()
    store.getState().disconnectEvents()
  })

  it("toggles multiple selected steps and supports pin create, resolve, reopen, and delete", async () => {
    const store = createStudioStore()
    await store.getState().bootstrap({ demo: true })
    const flow = demo.document.flows[0]
    const [first, second] = flow.nodes
    store.getState().goToFlow(flow.id)
    store.getState().toggleNodeSelection(first.id)
    store.getState().toggleNodeSelection(second.id)
    expect(store.getState().selectedNodeIds).toEqual([first.id, second.id])
    store.getState().toggleNodeSelection(first.id)
    expect(store.getState().selectedNodeIds).toEqual([second.id])

    await store.getState().addAnnotation({ target_type: "node", target_id: second.id, flow_id: flow.id, text: "Retry safely" })
    const pin = store.getState().data?.annotations.find(({ text }) => text === "Retry safely")
    expect(pin?.resolved).toBe(false)
    await store.getState().resolveAnnotation(pin!.id, true)
    expect(store.getState().data?.annotations.find(({ id }) => id === pin!.id)?.resolved).toBe(true)
    await store.getState().resolveAnnotation(pin!.id, false)
    expect(store.getState().data?.annotations.find(({ id }) => id === pin!.id)?.resolved).toBe(false)
    await store.getState().deleteAnnotation(pin!.id)
    expect(store.getState().data?.annotations.some(({ id }) => id === pin!.id)).toBe(false)
  })

  it("streams a sandbox plan, previews its visual diff and verifies the approved build", async () => {
    vi.useFakeTimers()
    const store = createStudioStore()
    await store.getState().bootstrap({ demo: true })
    const flow = demo.document.flows[0]
    store.getState().goToFlow(flow.id)
    store.getState().toggleNodeSelection(flow.nodes.find((node) => node.kind === "Do")!.id)
    const original = store.getState().data?.document
    const planning = store.getState().startRun({ kind: "plan", prompt: "Record delivery attempts and retry temporary failures." })
    await vi.advanceTimersByTimeAsync(1000)
    expect(store.getState().data?.active_run?.status).toBe("running")
    expect(store.getState().data?.active_run?.logs?.length).toBeGreaterThan(0)
    await vi.advanceTimersByTimeAsync(1500)
    await planning
    const planned = store.getState()
    const proposal = planned.data?.active_run?.proposed_document
    expect(planned.data?.active_run?.status).toBe("awaiting_approval")
    expect(planned.activeTab).toBe("diff")
    expect(planned.data?.document).toBe(original)
    expect(visibleDocument(planned)).toBe(proposal)
    const proposed = proposal?.flows.flatMap(({ nodes }) => nodes).filter((node) => node.status === "proposed") ?? []
    expect(proposed.length).toBeGreaterThan(0)

    const applying = store.getState().approvePlan()
    await vi.advanceTimersByTimeAsync(2500)
    await applying
    const finished = store.getState().data
    expect(store.getState().activeRun?.status).toBe("completed")
    expect(store.getState().activeRun?.verification?.tests).toEqual(expect.arrayContaining([expect.objectContaining({ passed: true })]))
    const verified = finished?.document.flows.flatMap(({ nodes }) => nodes) ?? []
    for (const step of proposed) expect(verified.find(({ id }) => id === step.id)?.status).toBe("verified")
  })

  it("streams and directly applies a sandbox Build without needing approval", async () => {
    vi.useFakeTimers()
    const store = createStudioStore()
    await store.getState().bootstrap({ demo: true })
    const original = store.getState().data?.document
    const statuses = new Set<string>()
    const unsubscribe = store.subscribe(({ activeRun }) => { if (activeRun) statuses.add(activeRun.status) })
    const building = store.getState().startRun({ kind: "build", prompt: "Retry transient provider errors." })
    await vi.advanceTimersByTimeAsync(2100)
    expect(store.getState().activeRun?.status).toBe("running")
    await vi.advanceTimersByTimeAsync(2500)
    await building
    expect([...statuses]).toEqual(["running", "completed"])
    expect(store.getState().data?.document).not.toBe(original)
    expect(store.getState().activeRun?.logs.map(({ kind }) => kind)).toEqual(expect.arrayContaining(["Apply", "Verify"]))
    expect(store.getState().activeRun?.verification?.tests?.[0]?.passed).toBe(true)
    unsubscribe()
  })
})
