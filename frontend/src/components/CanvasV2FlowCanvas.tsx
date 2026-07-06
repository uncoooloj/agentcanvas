import { useEffect, useMemo, useRef, useState, type ComponentType, type KeyboardEvent, type ReactNode } from "react"
import {
  CircleStop,
  Clock,
  ExternalLink,
  GitBranch,
  GitMerge,
  Pencil,
  Play,
  Plus,
  RefreshCcw,
  Split,
  Trash2,
  Workflow,
} from "lucide-react"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { layoutFlow, type CanvasV2Layout, type CanvasV2LayoutEdge, type CanvasV2LayoutNode } from "@/lib/canvasV2Layout"
import { cn } from "@/lib/utils"
import {
  CanvasV2EdgeKind,
  CanvasV2NodeKind,
  CanvasV2Status,
  FlowAction,
  FlowNodeKind,
  type CanvasV2Flow,
  type CanvasV2Node,
  type FlowNode,
} from "@/lib/types"

export enum CanvasV2KeyboardDirection {
  First = "first",
  Last = "last",
  Next = "next",
  Previous = "previous",
}

interface Props {
  flow: CanvasV2Flow
  selectedDisplayId: string | null
  displayNodeForNativeId: (nativeId: string) => FlowNode | null
  onSelectDisplayNode: (id: string) => void
  onOpenFlow?: (flowId: string) => void
  onAction: (action: FlowAction, node: FlowNode) => void
}

export function CanvasV2FlowCanvas({
  flow,
  selectedDisplayId,
  displayNodeForNativeId,
  onSelectDisplayNode,
  onOpenFlow,
  onAction,
}: Props) {
  const fallbackLayout = useMemo(() => layoutFlow(flow), [flow])
  const [layout, setLayout] = useState<CanvasV2Layout>(fallbackLayout)
  const layoutRequestRef = useRef(0)
  const nodes = useMemo(() => new Map(flow.nodes.map((node) => [node.id, node])), [flow.nodes])
  const layoutOrder = useMemo(() => layout.nodes.map((node) => node.id), [layout.nodes])

  useEffect(() => {
    setLayout(fallbackLayout)
    if (typeof Worker === "undefined") return

    const requestId = layoutRequestRef.current + 1
    layoutRequestRef.current = requestId
    const worker = new Worker(new URL("../lib/canvasV2LayoutWorker.ts", import.meta.url), { type: "module" })
    worker.onmessage = (event: MessageEvent<{ id: number; layout: CanvasV2Layout }>) => {
      if (event.data.id === layoutRequestRef.current) setLayout(event.data.layout)
    }
    worker.postMessage({ id: requestId, flow })
    return () => worker.terminate()
  }, [fallbackLayout, flow])

  function moveSelectionFrom(nodeId: string, direction: CanvasV2KeyboardDirection) {
    const targetId = keyboardTargetForNode(flow, layout.nodes, nodeId, direction)
    if (!targetId) return
    const displayNode = displayNodeForNativeId(targetId)
    if (!displayNode) return
    onSelectDisplayNode(displayNode.id)
    if (typeof document !== "undefined") {
      window.requestAnimationFrame(() => {
        const target = Array.from(document.querySelectorAll<HTMLButtonElement>("[data-canvas-v2-node-id]")).find(
          (button) => button.dataset.canvasV2NodeId === targetId
        )
        target?.focus()
      })
    }
  }

  return (
    <div className="overflow-x-auto pb-4">
      <div
        className="relative mx-auto"
        style={{ width: layout.width, height: layout.height }}
        aria-label={`${flow.title} map`}
      >
        <svg className="pointer-events-none absolute inset-0 h-full w-full overflow-visible" aria-hidden="true">
          <defs>
            <marker id="canvas-v2-arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto">
              <path d="M0,0 L8,4 L0,8 z" className="fill-muted-foreground/50" />
            </marker>
          </defs>
          {layout.edges.map((edge) => (
            <path
              key={edge.id}
              d={pathFor(edge.points)}
              fill="none"
              markerEnd="url(#canvas-v2-arrow)"
              className={cn("stroke-2", edgeClassName(edge.kind))}
            />
          ))}
          {layout.edges.map((edge) =>
            edge.label && edge.points.length ? (
              <EdgeLabel key={`${edge.id}:label`} edge={edge} />
            ) : null
          )}
        </svg>

        {layout.nodes.map((item) => {
          const node = nodes.get(item.id)
          if (!node) return null
          const displayNode = displayNodeForNativeId(node.id)
          const selected = Boolean(displayNode && displayNode.id === selectedDisplayId)
          return (
            <div
              key={node.id}
              className="absolute"
              style={{ left: item.x, top: item.y, width: item.w, minHeight: item.h }}
            >
              <NativeNodeCard
                node={node}
                selected={selected}
                displayNode={displayNode}
                tabIndex={displayNode ? (selected || (!selectedDisplayId && layoutOrder[0] === node.id) ? 0 : -1) : undefined}
                onSelect={() => {
                  if (node.kind === CanvasV2NodeKind.SubFlow && node.flowRef && onOpenFlow) {
                    onOpenFlow(node.flowRef)
                    return
                  }
                  if (displayNode) onSelectDisplayNode(displayNode.id)
                }}
                onNavigate={(direction) => moveSelectionFrom(node.id, direction)}
                onAction={onAction}
              />
            </div>
          )
        })}
      </div>
    </div>
  )
}

function NativeNodeCard({
  node,
  selected,
  displayNode,
  tabIndex,
  onSelect,
  onNavigate,
  onAction,
}: {
  node: CanvasV2Node
  selected: boolean
  displayNode: FlowNode | null
  tabIndex?: number
  onSelect: () => void
  onNavigate: (direction: CanvasV2KeyboardDirection) => void
  onAction: (action: FlowAction, node: FlowNode) => void
}) {
  const Icon = iconForKind(node.kind)
  const canEdit = Boolean(displayNode)
  function onKeyDown(event: KeyboardEvent<HTMLButtonElement>) {
    const direction = keyboardDirectionFromKey(event.key)
    if (!direction) return
    event.preventDefault()
    onNavigate(direction)
  }

  return (
    <div className="group relative">
      <button
        type="button"
        onClick={onSelect}
        onKeyDown={onKeyDown}
        disabled={!displayNode}
        tabIndex={tabIndex}
        data-canvas-v2-node-id={node.id}
        className={cn(
          "flex min-h-[74px] w-full items-start gap-3 rounded-lg border bg-card px-3.5 py-3 text-left shadow-sm transition-all",
          selected ? "border-primary/70 ring-2 ring-primary/15" : "border-border hover:border-foreground/20",
          !displayNode && "cursor-default opacity-80",
          node.kind === CanvasV2NodeKind.Parallel && "border-primary/25 bg-primary/5",
          node.kind === CanvasV2NodeKind.Join && "border-primary/20 bg-secondary",
          node.kind === CanvasV2NodeKind.End && "border-act-accent/30 bg-act-bg/40"
        )}
      >
        <span className={cn("mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-md", iconTone(node.kind))}>
          <Icon className="size-4" />
        </span>
        <span className="min-w-0 flex-1">
          <span className="flex flex-wrap items-center gap-1.5">
            <span className={cn("text-[11px] font-medium", labelTone(node.kind))}>{kindLabel(node.kind)}</span>
            {node.kind === CanvasV2NodeKind.SubFlow && node.flowRef && (
              <span className="rounded-md bg-secondary px-1.5 py-0.5 text-[10px] text-muted-foreground">
                Opens {node.flowRef.replace(/^flow:/, "")}
              </span>
            )}
            {node.status === CanvasV2Status.Proposed && (
              <span className="rounded-md bg-rule-bg px-1.5 py-0.5 text-[10px] font-medium text-rule-fg">
                Not built yet
              </span>
            )}
          </span>
          <span className="mt-1 block text-[13px] font-medium leading-snug text-foreground">{node.title}</span>
          {node.summary && (
            <span className="mt-1 line-clamp-2 block text-xs leading-snug text-muted-foreground">{node.summary}</span>
          )}
        </span>
      </button>
      {canEdit && displayNode && (
        <div className="pointer-events-none absolute right-2 top-2 flex items-center gap-1 rounded-lg border bg-card/95 p-1 opacity-0 shadow-sm backdrop-blur transition-opacity group-hover:pointer-events-auto group-hover:opacity-100 group-focus-within:pointer-events-auto group-focus-within:opacity-100">
          <NodeAction label="Change" onClick={() => onAction(changeActionFor(displayNode), displayNode)}>
            <Pencil className="size-3.5" />
          </NodeAction>
          {canAddAfter(node.kind) && (
            <NodeAction label="Add a step after" onClick={() => onAction(FlowAction.AddAfter, displayNode)}>
              <Plus className="size-3.5" />
            </NodeAction>
          )}
          {canAddRule(node.kind) && (
            <NodeAction label="Add a rule" onClick={() => onAction(FlowAction.AddRule, displayNode)}>
              <Split className="size-3.5" />
            </NodeAction>
          )}
          <NodeAction label="Remove" danger onClick={() => onAction(FlowAction.Remove, displayNode)}>
            <Trash2 className="size-3.5" />
          </NodeAction>
        </div>
      )}
    </div>
  )
}

export function keyboardDirectionFromKey(key: string): CanvasV2KeyboardDirection | null {
  switch (key) {
    case "ArrowDown":
    case "ArrowRight":
      return CanvasV2KeyboardDirection.Next
    case "ArrowUp":
    case "ArrowLeft":
      return CanvasV2KeyboardDirection.Previous
    case "Home":
      return CanvasV2KeyboardDirection.First
    case "End":
      return CanvasV2KeyboardDirection.Last
    default:
      return null
  }
}

export function keyboardTargetForNode(
  flow: CanvasV2Flow,
  layoutNodes: CanvasV2LayoutNode[],
  nodeId: string,
  direction: CanvasV2KeyboardDirection
): string | null {
  const order = layoutNodes.map((node) => node.id)
  const index = order.indexOf(nodeId)
  if (direction === CanvasV2KeyboardDirection.First) return order[0] ?? null
  if (direction === CanvasV2KeyboardDirection.Last) return order[order.length - 1] ?? null
  if (direction === CanvasV2KeyboardDirection.Next) {
    const outgoing = flow.edges
      .filter((edge) => edge.source === nodeId)
      .map((edge) => edge.target)
      .sort((a, b) => orderIndex(order, a) - orderIndex(order, b))
    return outgoing[0] ?? order[index + 1] ?? null
  }
  const incoming = flow.edges
    .filter((edge) => edge.target === nodeId)
    .map((edge) => edge.source)
    .sort((a, b) => orderIndex(order, b) - orderIndex(order, a))
  return incoming[0] ?? (index > 0 ? order[index - 1] : null)
}

function orderIndex(order: string[], id: string): number {
  const index = order.indexOf(id)
  return index === -1 ? Number.MAX_SAFE_INTEGER : index
}

function NodeAction({
  label,
  danger,
  onClick,
  children,
}: {
  label: string
  danger?: boolean
  onClick: () => void
  children: ReactNode
}) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          aria-label={label}
          onClick={onClick}
          className={cn(
            "flex size-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-secondary",
            danger ? "hover:text-destructive" : "hover:text-foreground"
          )}
        >
          {children}
        </button>
      </TooltipTrigger>
      <TooltipContent>{label}</TooltipContent>
    </Tooltip>
  )
}

function EdgeLabel({ edge }: { edge: CanvasV2LayoutEdge }) {
  const point = edge.points[Math.floor(edge.points.length / 2)]
  return (
    <foreignObject x={point.x - 44} y={point.y - 14} width="88" height="28">
      <div className="flex h-full items-center justify-center">
        <span className="max-w-[84px] truncate rounded-full border bg-background px-2 py-0.5 text-[10px] text-muted-foreground shadow-sm">
          {edge.label}
        </span>
      </div>
    </foreignObject>
  )
}

function pathFor(points: Array<{ x: number; y: number }>): string {
  if (!points.length) return ""
  return points.map((point, index) => `${index === 0 ? "M" : "L"}${point.x},${point.y}`).join(" ")
}

function edgeClassName(kind: CanvasV2EdgeKind): string {
  switch (kind) {
    case CanvasV2EdgeKind.Branch:
      return "stroke-rule-accent/70"
    case CanvasV2EdgeKind.Parallel:
      return "stroke-primary/55"
    case CanvasV2EdgeKind.LoopBack:
      return "stroke-gold/80"
    case CanvasV2EdgeKind.Error:
      return "stroke-destructive/70 [stroke-dasharray:5_5]"
    case CanvasV2EdgeKind.Async:
      return "stroke-muted-foreground/60 [stroke-dasharray:5_5]"
    default:
      return "stroke-border"
  }
}

function changeActionFor(node: FlowNode): FlowAction {
  return node.kind === FlowNodeKind.Branch ? FlowAction.ChangeCondition : FlowAction.Change
}

function iconForKind(kind: CanvasV2NodeKind): ComponentType<{ className?: string }> {
  switch (kind) {
    case CanvasV2NodeKind.When:
      return Play
    case CanvasV2NodeKind.Decision:
      return GitBranch
    case CanvasV2NodeKind.Loop:
      return RefreshCcw
    case CanvasV2NodeKind.Parallel:
      return Split
    case CanvasV2NodeKind.Join:
      return GitMerge
    case CanvasV2NodeKind.Wait:
      return Clock
    case CanvasV2NodeKind.SubFlow:
      return ExternalLink
    case CanvasV2NodeKind.End:
      return CircleStop
    default:
      return Workflow
  }
}

function kindLabel(kind: CanvasV2NodeKind): string {
  switch (kind) {
    case CanvasV2NodeKind.When:
      return "When"
    case CanvasV2NodeKind.Do:
      return "Do"
    case CanvasV2NodeKind.Decision:
      return "Decision"
    case CanvasV2NodeKind.Loop:
      return "Loop"
    case CanvasV2NodeKind.Parallel:
      return "Parallel"
    case CanvasV2NodeKind.Join:
      return "Join"
    case CanvasV2NodeKind.Wait:
      return "Wait"
    case CanvasV2NodeKind.SubFlow:
      return "Sub-flow"
    case CanvasV2NodeKind.End:
      return "End"
  }
}

function iconTone(kind: CanvasV2NodeKind): string {
  switch (kind) {
    case CanvasV2NodeKind.When:
      return "bg-when-bg text-when-fg"
    case CanvasV2NodeKind.Decision:
      return "bg-rule-bg text-rule-fg"
    case CanvasV2NodeKind.End:
      return "bg-act-bg text-act-fg"
    case CanvasV2NodeKind.Loop:
    case CanvasV2NodeKind.Parallel:
    case CanvasV2NodeKind.Join:
      return "bg-primary/10 text-primary"
    default:
      return "bg-secondary text-muted-foreground"
  }
}

function labelTone(kind: CanvasV2NodeKind): string {
  if (kind === CanvasV2NodeKind.When) return "text-when-fg"
  if (kind === CanvasV2NodeKind.Decision) return "text-rule-fg"
  if (kind === CanvasV2NodeKind.End) return "text-act-fg"
  return "text-muted-foreground"
}

function canAddAfter(kind: CanvasV2NodeKind): boolean {
  return (
    kind === CanvasV2NodeKind.When ||
    kind === CanvasV2NodeKind.Do ||
    kind === CanvasV2NodeKind.Wait ||
    kind === CanvasV2NodeKind.SubFlow
  )
}

function canAddRule(kind: CanvasV2NodeKind): boolean {
  return kind === CanvasV2NodeKind.Do || kind === CanvasV2NodeKind.When
}
