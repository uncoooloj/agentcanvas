import { ArrowDownRight, ArrowRight, AtSign, Braces, Cable, CircleHelp, Database, Layers3, Monitor, Pin, Smartphone, Workflow, Zap } from "lucide-react"
import { Handle, Position, type Node, type NodeProps } from "@xyflow/react"
import { useShallow } from "zustand/react/shallow"
import { useStudioStore } from "@/lib/studioStore"
import { formatRef, type DiffStatus, type StudioComponent, type StudioNode } from "@/lib/studioTypes"

export const componentIcons = { web: Monitor, mobile: Smartphone, service: Layers3, package: Braces, worker: Zap, db: Database, external: Cable }
export const componentLabels = { web: "Web", mobile: "Mobile", service: "Service", package: "Package", worker: "Worker", db: "Database", external: "External" }

type ComponentData = {
  component: StudioComponent
  inspect: (pins?: boolean) => void
  viewFlows?: () => void
}

type StepData = {
  step: StudioNode
  component?: StudioComponent
  flowId?: string
  inspect: (pins?: boolean) => void
  steer: () => void
  jump?: () => void
}

export type SystemGraphNode = Node<ComponentData, "system">
export type FlowGraphNode = Node<StepData, "step">
export type StudioGraphNode = SystemGraphNode | FlowGraphNode

const diffLabels = { added: "+ Added", modified: "~ Modified", removed: "− Removed" }

function DiffBadge({ status }: { status?: DiffStatus }) {
  if (!status || status === "unchanged") return null
  return <span className="s-diff-chip" data-diff={status}>{diffLabels[status]}</span>
}

function Ports({ system = false }: { system?: boolean }) {
  return <>
    <Handle type="target" position={system ? Position.Left : Position.Top} isConnectable={false} />
    <Handle type="source" position={system ? Position.Right : Position.Bottom} isConnectable={false} />
  </>
}

function NodePin({ count, onClick }: { count: number; onClick: () => void }) {
  if (!count) return null
  return (
    <button type="button" className="s-pin-badge nodrag nopan" onClick={(event) => { event.stopPropagation(); onClick() }} aria-label={`Open ${count} pins`}>
      <Pin size={12} />{count}
    </button>
  )
}

export function SystemNode({ data }: NodeProps<SystemGraphNode>) {
  const { component, inspect, viewFlows } = data
  const { inspected, pins } = useStudioStore(useShallow((state) => ({
    inspected: state.inspectedComponentId === component.id,
    pins: state.data?.annotations.filter((pin) => !pin.resolved && pin.target_type === "component" && pin.target_id === component.id).length ?? 0,
  })))
  const Icon = componentIcons[component.kind]
  return (
    <article className="s-node s-system-node" data-diff={component.diff_status} data-inspected={inspected}>
      <Ports system />
      <NodePin count={pins} onClick={() => inspect(true)} />
      <div className="s-node-header">
        <span className="s-component-icon"><Icon size={15} /></span>
        <span className="s-node-type">{componentLabels[component.kind]}</span>
        <DiffBadge status={component.diff_status} />
      </div>
      <button className="s-node-title nodrag nopan" type="button" onClick={(event) => { event.stopPropagation(); inspect() }}>{component.name}</button>
      <p className="s-node-summary">{component.summary}</p>
      {component.path && <code className="s-path">{component.path}</code>}
      {component.tech.length > 0 && <div className="s-node-tags">{component.tech.map((tech) => <span className="s-chip" key={tech}>{tech}</span>)}</div>}
      {viewFlows && <button type="button" className="s-node-link nodrag nopan" onClick={(event) => { event.stopPropagation(); viewFlows() }}>View flows <ArrowRight size={13} /></button>}
    </article>
  )
}

export function FlowStepNode({ data }: NodeProps<FlowGraphNode>) {
  const { step, component, flowId, inspect, steer, jump } = data
  const { inspected, steered, stale, pins } = useStudioStore(useShallow((state) => ({
    inspected: state.inspectedNodeId === step.id,
    steered: state.selectedNodeIds.includes(step.id),
    stale: state.data?.stale_node_ids.includes(step.id),
    pins: state.data?.annotations.filter((pin) => !pin.resolved && pin.target_type === "node"
      && pin.target_id === step.id && (!pin.flow_id || pin.flow_id === flowId)).length ?? 0,
  })))
  const ref = step.code_refs[0]
  const role = step.kind === "When" ? "when" : step.kind === "Do" || step.kind === "End" ? "act" : "rule"
  const status = stale ? "stale" : step.status
  return (
    <article className="s-node s-step-node" data-diff={step.diff_status} data-inspected={inspected} data-steered={steered}>
      <Ports />
      <NodePin count={pins} onClick={() => inspect(true)} />
      <div className="s-node-header">
        <span className="s-role-chip" data-role={role}>{step.kind}</span>
        <span className="s-step-status" data-status={status}><i />{status}</span>
        <DiffBadge status={step.diff_status} />
      </div>
      {component && <p className="s-node-component">{component.name}</p>}
      <button type="button" className="s-node-title nodrag nopan" onClick={(event) => {
        if (event.metaKey || event.ctrlKey || event.shiftKey) return
        event.stopPropagation()
        inspect()
      }}>{step.title}</button>
      {step.summary && <p className="s-node-summary">{step.summary}</p>}
      {ref && (
        <button type="button" className="s-path nodrag nopan" onClick={(event) => { event.stopPropagation(); inspect() }}>
          <Braces size={13} className="shrink-0" /><code>{formatRef(ref)}</code>
        </button>
      )}
      <div className="s-quick-actions nodrag nopan" onClick={(event) => event.stopPropagation()}>
        <button type="button" title="Pin note" aria-label="Pin note" onClick={() => inspect(true)}><Pin size={14} /></button>
        <button type="button" title="Inspect code" aria-label="Inspect code" onClick={() => inspect(false)}>{ref ? <Braces size={14} /> : <CircleHelp size={14} />}</button>
        <button type="button" title="Steer with this step" aria-label="Steer with this step" aria-pressed={steered} onClick={steer}><AtSign size={14} /></button>
        {jump && <button type="button" onClick={jump}><Workflow size={14} /> Jump to flow <ArrowDownRight size={12} /></button>}
      </div>
    </article>
  )
}

export const studioNodeTypes = { system: SystemNode, step: FlowStepNode }
