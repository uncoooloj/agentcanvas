import { useShallow } from "zustand/react/shallow"
import { useCallback, useEffect, useMemo, useRef, useState, type MouseEvent } from "react"
import {
  Background, BackgroundVariant, Controls, MarkerType, MiniMap, Panel,
  ReactFlow, ReactFlowProvider, useReactFlow, type Edge, type OnNodesChange,
} from "@xyflow/react"
import { ArrowRight, GitCompareArrows, Layers3, PanelLeftOpen, Pin, Sparkles, Workflow } from "lucide-react"
import { FLOW_WIDTH, SYSTEM_WIDTH, layoutFlow, layoutSystem, type LayoutNode, type MeasuredSizes } from "@/lib/studioLayout"
import { diffCounts, isPendingRun, runnerLabels, type StudioDocument, type StudioFlow } from "@/lib/studioTypes"
import { studioStore, useStudioStore, visibleDocument } from "@/lib/studioStore"
import { CopyMappingPrompt, DiffCounts } from "./StudioTopBar"
import { studioNodeTypes, type StudioGraphNode } from "./StudioNodes"

const emptyNodes: LayoutNode[] = []
const fitOptions = { padding: { top: "110px", bottom: "145px", x: "36px" }, maxZoom: 1.05 } as const
const diffFitOptions = { ...fitOptions, padding: { ...fitOptions.padding, top: "174px" } } as const

type SpatialCanvasProps = { focusCommand: () => void; onPaneClear: () => void }

export function SpatialCanvas(props: SpatialCanvasProps) {
  const document = useStudioStore(visibleDocument)
  const tab = useStudioStore((state) => state.activeTab)
  const flowId = useStudioStore((state) => state.activeFlowId)
  const flow = document?.flows.find((item) => item.id === flowId) ?? document?.flows[0]
  return (
    <section className="s-canvas" aria-label="Spatial canvas">
      {document && (
        <ReactFlowProvider key={tab === "system" ? "system" : `${tab}:${flow?.id ?? "empty"}`}>
          <CanvasGraph {...props} document={document} flow={flow} />
        </ReactFlowProvider>
      )}
    </section>
  )
}

function CanvasGraph({ document, flow, focusCommand, onPaneClear }: SpatialCanvasProps & { document: StudioDocument; flow?: StudioFlow }) {
  const {
    activeTab, diffOnlyFilter, setDiffOnlyFilter, sidebarOpen, setSidebarOpen, pinMode, setPinMode,
    inspectedNodeId, inspectedComponentId, setInspectedNode, setInspectedComponent,
    toggleNodeSelection, goToFlow, startRun, approvePlan, discardPlan, setTab,
    workspacePath, unmapped, runner, busy, proposal,
  } = useStudioStore(useShallow((state) => ({
    activeTab: state.activeTab, diffOnlyFilter: state.diffOnlyFilter, setDiffOnlyFilter: state.setDiffOnlyFilter,
    sidebarOpen: state.sidebarOpen, setSidebarOpen: state.setSidebarOpen, pinMode: state.pinMode, setPinMode: state.setPinMode,
    inspectedNodeId: state.inspectedNodeId, inspectedComponentId: state.inspectedComponentId,
    setInspectedNode: state.setInspectedNode, setInspectedComponent: state.setInspectedComponent,
    toggleNodeSelection: state.toggleNodeSelection, goToFlow: state.goToFlow, startRun: state.startRun,
    approvePlan: state.approvePlan, discardPlan: state.discardPlan, setTab: state.setTab,
    workspacePath: state.data?.workspace,
    unmapped: state.data?.mode === "workspace" && !state.data.has_mapped_canvas,
    runner: state.data?.runner.preferred ?? "copy",
    busy: isPendingRun(state.data?.active_run),
    proposal: state.data?.active_run?.status === "awaiting_approval" ? state.data.active_run.proposed_document : null,
  })))
  const system = activeTab === "system"
  const diff = activeTab === "diff"
  const [layoutError, setLayoutError] = useState("")
  const [positions, setPositions] = useState(emptyNodes)
  const [measured, setMeasured] = useState<MeasuredSizes>({})
  const { fitView, setCenter } = useReactFlow<StudioGraphNode>()
  const lastFit = useRef("")
  const filteredFlow = useMemo(() => {
    if (!flow || !diff || !diffOnlyFilter) return flow
    const changedEdges = flow.edges.filter((edge) => edge.diff_status && edge.diff_status !== "unchanged")
    const changedIds = new Set(changedEdges.flatMap((edge) => [edge.source, edge.target]))
    const nodes = flow.nodes.filter((node) => changedIds.has(node.id) || (node.diff_status && node.diff_status !== "unchanged"))
    const visibleIds = new Set(nodes.map((node) => node.id))
    return { ...flow, nodes, edges: flow.edges.filter((edge) => visibleIds.has(edge.source) && visibleIds.has(edge.target)) }
  }, [flow, diff, diffOnlyFilter])
  const { components, component_edges: componentEdges } = document

  useEffect(() => {
    let current = true
    const task = system
      ? layoutSystem({ components, component_edges: componentEdges }, measured)
      : filteredFlow ? layoutFlow(filteredFlow, measured) : Promise.resolve(emptyNodes)
    void task.then((result) => {
      if (!current) return
      setPositions(result)
      setLayoutError("")
    }).catch(() => {
      if (!current) return
      setLayoutError("The graph layout could not load. Switch views to retry.")
    })
    return () => { current = false }
  }, [system, components, componentEdges, filteredFlow, measured])

  const geometry = positions.map(({ id }) => id).join("\0")
  const ready = Boolean(geometry) && positions.every(({ id, width, height }) => measured[id]?.width === width && measured[id].height === height)
  useEffect(() => {
    if (!ready || lastFit.current === geometry) return
    lastFit.current = geometry
    const firstY = Math.min(...positions.map((node) => node.y))
    const entryNodes = positions.filter((node) => node.y <= firstY + 110).map(({ id }) => ({ id }))
    void fitView({ ...(diff ? diffFitOptions : fitOptions), nodes: system || diff ? undefined : entryNodes, duration: 0 })
  }, [positions, geometry, ready, system, diff, fitView])

  const inspectedId = system ? inspectedComponentId : inspectedNodeId
  const inspection = positions.find(({ id }) => id === inspectedId)
  useEffect(() => {
    if (!inspection) return
    const frame = requestAnimationFrame(() => {
      // Keep the selection near the unobstructed left half when the evidence drawer is open.
      const drawerWidth = Math.min(420, window.innerWidth * 0.91)
      const offset = window.innerWidth > 660 ? drawerWidth * 0.27 : 0
      const duration = window.matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 180
      void setCenter(inspection.x + inspection.width / 2 + offset, inspection.y + inspection.height / 2, { zoom: 0.93, duration })
    })
    return () => cancelAnimationFrame(frame)
  }, [inspection, setCenter])

  const onNodesChange: OnNodesChange<StudioGraphNode> = (changes) => {
    const dimensions = changes.getByType("dimensions")
    if (!dimensions.length) return
    setMeasured((previous) => {
      let next: Record<string, { width: number; height: number }> | undefined
      for (const change of dimensions) {
        if (!change.dimensions) continue
        const { width, height } = change.dimensions
        const size = previous[change.id]
        if (width <= 0 || height <= 0 || (size?.width === width && size.height === height)) continue
        next ??= { ...previous }
        next[change.id] = { width, height }
      }
      return next ?? previous
    })
  }

  const inspect = useCallback((id: string, pins = studioStore.getState().pinMode) => {
    setPinMode(pins)
    if (system) setInspectedComponent(id)
    else setInspectedNode(id)
  }, [system, setPinMode, setInspectedComponent, setInspectedNode])

  const nodes = useMemo(() => {
    const componentById = new Map(components.map((component) => [component.id, component]))
    const stepById = new Map(filteredFlow?.nodes.map((step) => [step.id, step]))
    return positions.flatMap<StudioGraphNode>(({ id, x, y }) => {
      const position = { x, y }
      const component = componentById.get(id)
      if (system && component) {
        const firstFlow = document.flows.find((item) => item.component_ids.includes(id))
        return [{
          id, position, type: "system", draggable: false, measured: measured[id],
          style: { width: SYSTEM_WIDTH }, ariaLabel: component.name,
          data: { component, inspect: (pins) => inspect(id, pins), viewFlows: firstFlow && (() => goToFlow(firstFlow.id)) },
        }]
      }
      const step = stepById.get(id)
      if (system || !step) return []
      const nextFlow = step.flow_ref
      return [{
        id, position, type: "step", draggable: false, measured: measured[id], style: { width: FLOW_WIDTH }, ariaLabel: step.title,
        data: {
          step, flowId: filteredFlow?.id, component: step.component_id ? componentById.get(step.component_id) : undefined,
          inspect: (pins) => inspect(id, pins),
          steer: () => { toggleNodeSelection(id); focusCommand() },
          jump: nextFlow && document.flows.some((item) => item.id === nextFlow) ? () => goToFlow(nextFlow) : undefined,
        },
      }]
    })
  }, [components, document.flows, filteredFlow, focusCommand, goToFlow, inspect, measured, positions, system, toggleNodeSelection])

  const edges = useMemo<Edge[]>(() => {
    const nodeIds = new Set(nodes.map((node) => node.id))
    return (system ? componentEdges : filteredFlow?.edges ?? [])
      .filter((edge) => nodeIds.has(edge.source) && nodeIds.has(edge.target))
      .map((edge) => ({
        id: edge.id, source: edge.source, target: edge.target, type: "smoothstep",
        label: "protocol" in edge && edge.protocol ? [edge.label, edge.protocol].filter(Boolean).join(" · ") : edge.label, selectable: false, focusable: false,
        markerEnd: { type: MarkerType.ArrowClosed, color: "var(--s-edge)", width: 14, height: 14 },
        className: `s-edge ${"kind" in edge ? `s-edge-${edge.kind}` : ""} ${edge.diff_status ? `s-edge-${edge.diff_status}` : ""}`,
      }))
  }, [nodes, system, componentEdges, filteredFlow?.edges])
  const counts = diffCounts(proposal && !diff ? proposal.flows.flatMap((item) => item.nodes) : flow?.nodes ?? [])
  const heading = system ? "System topology" : flow?.title ?? (diff ? "Behavioral diff" : "Flows")
  const caption = system
    ? `${components.length} components · ${componentEdges.length} connections`
    : flow ? (diff ? flow.diff_summary || flow.summary : flow.summary) : ""
  const displayedError = layoutError || (!nodes.length && (system ? !components.length : !filteredFlow?.nodes.length)
    ? diff && flow ? "This journey has no changed steps." : "There’s no graph for this view yet."
    : "")

  function handleNodeClick(event: MouseEvent, node: StudioGraphNode) {
    if (!system && (event.metaKey || event.ctrlKey || event.shiftKey)) {
      toggleNodeSelection(node.id)
      return
    }
    inspect(node.id)
  }

  return (
    <ReactFlow
      nodes={nodes} edges={edges} nodeTypes={studioNodeTypes} onNodesChange={onNodesChange}
      onNodeClick={handleNodeClick} onPaneClick={onPaneClear}
      nodesDraggable={false} nodesConnectable={false} nodesFocusable={false} elementsSelectable={false}
      deleteKeyCode={null} minZoom={0.08} maxZoom={2.2} className="s-flow"
    >
      <Background variant={BackgroundVariant.Dots} gap={21} size={1.25} color="var(--s-grid)" />
      <Panel position="top-left" className="s-canvas-title">
        {!sidebarOpen && <button type="button" className="s-button s-expand-sidebar" onClick={() => setSidebarOpen(true)} aria-label="Expand sidebar" title="Expand sidebar ([)"><PanelLeftOpen size={17} /></button>}
        <div className="s-canvas-title-text">
          <span className="s-canvas-kicker">{system ? <Layers3 size={13} /> : diff ? <GitCompareArrows size={13} /> : <Workflow size={13} />}{system ? "Architecture" : diff ? "Behavioral diff" : "Product journey"}</span>
          <h1>{heading}</h1>
          {caption && <p title={caption}>{caption}</p>}
        </div>
      </Panel>
      <Panel position="top-right" className="s-canvas-tools">
        <button type="button" className="s-button" aria-label="Pin mode" aria-pressed={pinMode} onClick={() => setPinMode(!pinMode)} title="Select a card to pin a note"><Pin size={15} /><span>Pin mode</span></button>
      </Panel>
      {(diff || proposal) && <Panel position="top-center" className="s-diff-strip">
        {proposal && <strong>Proposed Visual Diff</strong>}
        <DiffCounts counts={counts} showZero />
        {diff ? <div className="s-diff-filter" aria-label="Diff context">
          <button type="button" className="s-button" aria-pressed={diffOnlyFilter} onClick={() => setDiffOnlyFilter(true)}>Changed only</button>
          <button type="button" className="s-button" aria-pressed={!diffOnlyFilter} onClick={() => setDiffOnlyFilter(false)}>Full context</button>
        </div> : <button type="button" className="s-button" onClick={() => setTab("diff")}>View proposed diff</button>}
        {proposal && <>
          <button type="button" className="s-button s-primary" onClick={() => void approvePlan()}>Approve &amp; Build</button>
          <button type="button" className="s-button" onClick={() => void discardPlan()}>Discard Plan</button>
        </>}
      </Panel>}
      {!unmapped && displayedError && <div className="s-canvas-empty" role={layoutError ? "alert" : "status"}>{displayedError}</div>}
      {unmapped && system && (
        <div className="s-init-wrap">
          <section className="s-init-card">
            <span className="s-init-icon"><Sparkles size={22} /></span>
            <h2>Map this codebase{runner !== "copy" ? ` with ${runnerLabels[runner]}` : ""}</h2>
            <p>{components.length ? "Your detected components are on the canvas. Map the repo to trace the journeys through them." : "Trace product journeys through the repo and pin notes to the steps you want to change."}</p>
            <div className="s-init-actions">
              {runner === "copy"
                ? <CopyMappingPrompt workspace={workspacePath ?? ""} />
                : <button type="button" className="s-button s-primary" disabled={busy} onClick={() => void startRun({ kind: "map" })}>Map Repo <ArrowRight size={14} /></button>}
              <button type="button" className="s-button" disabled={busy} onClick={() => {
                setTab("diff")
                if (runner !== "copy") void startRun({ kind: "diff" })
              }}><GitCompareArrows size={14} />Visual Diff</button>
            </div>
          </section>
        </div>
      )}
      <Controls position="bottom-left" showInteractive={false} fitViewOptions={diff ? diffFitOptions : fitOptions} />
      {nodes.length > 0 && <MiniMap<StudioGraphNode> position="bottom-right" nodeColor={(node) => {
        const status = node.type === "system" ? node.data.component.diff_status : node.data.step.diff_status
        return status && status !== "unchanged" ? `var(--s-${status})` : "var(--s-minimap-node)"
      }} nodeBorderRadius={8} pannable zoomable ariaLabel="Canvas overview" />}
    </ReactFlow>
  )
}
