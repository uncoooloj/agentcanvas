import { afterEach, describe, expect, it, vi } from "vitest"
import { createStudioApi } from "@/lib/studioApi"
import { demoBootstrap, demoFileDiff, demoFileSlice, demoProposal, demoVerified } from "@/lib/studioDemo"
import { layoutFlow, layoutSystem, type LayoutNode } from "@/lib/studioLayout"
import { createStudioStore, visibleDocument } from "@/lib/studioStore"
import { diffCounts, type StudioAnnotation, type StudioRun } from "@/lib/studioTypes"

const demo = demoBootstrap()

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
    const fetcher = vi.fn(async (_url: string, _init: RequestInit) => Response.json(demo))
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
})

describe("Studio state", () => {
  afterEach(() => vi.useRealTimers())

  it("handles SSE graph, run, log, and annotation updates", async () => {
    const store = createStudioStore()
    await store.getState().bootstrap({ demo: true })
    const { handleEvent } = store.getState()
    const document = { ...demo.document, components: demo.document.components.slice(0, 1) }
    handleEvent({ type: "studio.updated", payload: { document, has_mapped_canvas: true, stale_node_ids: ["old-step"] } })
    expect(store.getState().data?.document).toBe(document)
    expect(store.getState().data?.stale_node_ids).toEqual(["old-step"])

    const run: StudioRun = { id: "run-sse", kind: "plan", runner: "codex", status: "running" }
    handleEvent({ type: "run.updated", payload: { run } })
    const entry = { id: "log-sse", stage: "Inspect", tool: "read_file", message: "Read checkout route" }
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
    const run = { id: "map-fast", kind: "map", runner: "codex", status: "running" } as const
    store.getState().handleEvent({ type: "run.updated", payload: { run: { ...run, status: "completed" } } })
    settle({ ok: true, run })
    await starting
    expect(store.getState().activeRun?.status).toBe("completed")
    expect(store.getState().data?.active_run).toBeNull()
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
})
