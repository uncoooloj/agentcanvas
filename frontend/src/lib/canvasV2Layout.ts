import type { CanvasV2Edge, CanvasV2Flow } from "./types"

export interface CanvasV2LayoutNode {
  id: string
  x: number
  y: number
  w: number
  h: number
}

export interface CanvasV2LayoutEdge {
  id: string
  source: string
  target: string
  kind: CanvasV2Edge["kind"]
  label?: string
  points: Array<{ x: number; y: number }>
}

export interface CanvasV2Layout {
  width: number
  height: number
  nodes: CanvasV2LayoutNode[]
  edges: CanvasV2LayoutEdge[]
}

const NODE_W = 260
const NODE_H = 74
const X_GAP = 56
const Y_GAP = 82
const PAD_X = 36
const PAD_Y = 28

export const ELK_LAYOUT_OPTIONS: Record<string, string> = {
  "elk.algorithm": "layered",
  "elk.direction": "DOWN",
  "elk.edgeRouting": "ORTHOGONAL",
  "elk.layered.spacing.nodeNodeBetweenLayers": String(Y_GAP),
  "elk.spacing.nodeNode": String(X_GAP),
  "elk.padding": `[top=${PAD_Y},left=${PAD_X},bottom=${PAD_Y},right=${PAD_X}]`,
}

interface ElkPoint {
  x?: number
  y?: number
}

interface ElkSection {
  startPoint?: ElkPoint
  bendPoints?: ElkPoint[]
  endPoint?: ElkPoint
}

interface ElkNode {
  id: string
  x?: number
  y?: number
  width?: number
  height?: number
}

interface ElkEdge {
  id: string
  sources?: string[]
  targets?: string[]
  labels?: Array<{ text: string; width: number; height: number }>
  sections?: ElkSection[]
}

export interface ElkWorkerGraph {
  id: string
  width?: number
  height?: number
  children?: ElkNode[]
  edges?: ElkEdge[]
  layoutOptions?: Record<string, string>
}

export function layoutFlow(flow: CanvasV2Flow): CanvasV2Layout {
  const nodes = [...flow.nodes].sort((a, b) => a.id.localeCompare(b.id))
  const nodeIds = new Set(nodes.map((node) => node.id))
  const edgeList = [...flow.edges]
    .filter((edge) => nodeIds.has(edge.source) && nodeIds.has(edge.target))
    .sort((a, b) => a.id.localeCompare(b.id))
  const levels = assignLevels(flow.entryNode, nodes.map((node) => node.id), edgeList)
  const byLevel = new Map<number, string[]>()

  for (const node of nodes) {
    const level = levels.get(node.id) ?? 0
    byLevel.set(level, [...(byLevel.get(level) ?? []), node.id])
  }

  const layoutNodes: CanvasV2LayoutNode[] = []
  let minX = 0
  let maxX = 0
  let maxY = 0

  for (const [level, ids] of [...byLevel.entries()].sort((a, b) => a[0] - b[0])) {
    ids.sort((a, b) => a.localeCompare(b))
    const rowWidth = ids.length * NODE_W + Math.max(0, ids.length - 1) * X_GAP
    const startX = -rowWidth / 2
    for (const [index, id] of ids.entries()) {
      const x = startX + index * (NODE_W + X_GAP)
      const y = PAD_Y + level * (NODE_H + Y_GAP)
      minX = Math.min(minX, x)
      maxX = Math.max(maxX, x + NODE_W)
      maxY = Math.max(maxY, y + NODE_H)
      layoutNodes.push({ id, x, y, w: NODE_W, h: NODE_H })
    }
  }

  const shiftX = PAD_X - minX
  for (const node of layoutNodes) node.x += shiftX

  const positions = new Map(layoutNodes.map((node) => [node.id, node]))
  const width = Math.ceil(maxX - minX + PAD_X * 2)
  const height = Math.ceil(maxY + PAD_Y)
  const edges = edgeList.map((edge) => layoutEdge(edge, positions, width))

  return {
    width,
    height,
    nodes: layoutNodes.sort((a, b) => a.id.localeCompare(b.id)),
    edges,
  }
}

export function flowToElkGraph(flow: CanvasV2Flow): ElkWorkerGraph {
  const nodeIds = new Set(flow.nodes.map((node) => node.id))
  return {
    id: flow.id,
    layoutOptions: ELK_LAYOUT_OPTIONS,
    children: [...flow.nodes]
      .sort((a, b) => a.id.localeCompare(b.id))
      .map((node) => ({
        id: node.id,
        width: NODE_W,
        height: NODE_H,
      })),
    edges: [...flow.edges]
      .filter((edge) => nodeIds.has(edge.source) && nodeIds.has(edge.target))
      .sort((a, b) => a.id.localeCompare(b.id))
      .map((edge) => ({
        id: edge.id,
        sources: [edge.source],
        targets: [edge.target],
        labels: edge.label ? [{ text: edge.label, width: 88, height: 28 }] : undefined,
      })),
  }
}

export function layoutFlowFromElk(flow: CanvasV2Flow, graph: ElkWorkerGraph): CanvasV2Layout {
  const fallback = layoutFlow(flow)
  const elkNodes = new Map((graph.children || []).map((node) => [node.id, node]))
  if (!elkNodes.size) return fallback

  const layoutNodes = fallback.nodes.map((fallbackNode) => {
    const node = elkNodes.get(fallbackNode.id)
    return {
      id: fallbackNode.id,
      x: numberOrFallback(node?.x, fallbackNode.x),
      y: numberOrFallback(node?.y, fallbackNode.y),
      w: numberOrFallback(node?.width, fallbackNode.w),
      h: numberOrFallback(node?.height, fallbackNode.h),
    }
  })
  const elkEdges = new Map((graph.edges || []).map((edge) => [edge.id, edge]))
  const edges = fallback.edges.map((fallbackEdge) => {
    const sections = elkEdges.get(fallbackEdge.id)?.sections || []
    const points = pointsFromElkSections(sections)
    return points.length ? { ...fallbackEdge, points } : fallbackEdge
  })

  return {
    width: Math.ceil(numberOrFallback(graph.width, fallback.width)),
    height: Math.ceil(numberOrFallback(graph.height, fallback.height)),
    nodes: layoutNodes.sort((a, b) => a.id.localeCompare(b.id)),
    edges,
  }
}

function assignLevels(entryNode: string | undefined, nodeIds: string[], edges: CanvasV2Edge[]): Map<string, number> {
  const levels = new Map<string, number>()
  const start = entryNode && nodeIds.includes(entryNode) ? entryNode : nodeIds[0]
  if (start) levels.set(start, 0)

  for (const id of nodeIds) {
    if (!levels.has(id)) levels.set(id, 0)
  }

  for (let pass = 0; pass < nodeIds.length; pass += 1) {
    let changed = false
    for (const edge of edges) {
      if (edge.kind === "loop_back") continue
      const sourceLevel = levels.get(edge.source) ?? 0
      const targetLevel = levels.get(edge.target) ?? 0
      const nextLevel = sourceLevel + 1
      if (nextLevel > targetLevel) {
        levels.set(edge.target, nextLevel)
        changed = true
      }
    }
    if (!changed) break
  }

  return levels
}

function pointsFromElkSections(sections: ElkSection[]): Array<{ x: number; y: number }> {
  const points: Array<{ x: number; y: number }> = []
  for (const section of sections) {
    pushPoint(points, section.startPoint)
    for (const bend of section.bendPoints || []) pushPoint(points, bend)
    pushPoint(points, section.endPoint)
  }
  return points
}

function pushPoint(points: Array<{ x: number; y: number }>, point: ElkPoint | undefined) {
  if (typeof point?.x !== "number" || typeof point.y !== "number") return
  const next = { x: point.x, y: point.y }
  const previous = points[points.length - 1]
  if (!previous || previous.x !== next.x || previous.y !== next.y) points.push(next)
}

function numberOrFallback(value: unknown, fallback: number): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback
}

function layoutEdge(edge: CanvasV2Edge, positions: Map<string, CanvasV2LayoutNode>, width: number): CanvasV2LayoutEdge {
  const source = positions.get(edge.source)
  const target = positions.get(edge.target)
  if (!source || !target) {
    return { id: edge.id, source: edge.source, target: edge.target, kind: edge.kind, label: edge.label, points: [] }
  }

  if (edge.kind === "loop_back") {
    const routeX = width - PAD_X
    return {
      id: edge.id,
      source: edge.source,
      target: edge.target,
      kind: edge.kind,
      label: edge.label,
      points: [
        { x: source.x + source.w, y: source.y + source.h / 2 },
        { x: routeX, y: source.y + source.h / 2 },
        { x: routeX, y: target.y + target.h / 2 },
        { x: target.x + target.w, y: target.y + target.h / 2 },
      ],
    }
  }

  const start = { x: source.x + source.w / 2, y: source.y + source.h }
  const end = { x: target.x + target.w / 2, y: target.y }
  const midY = start.y + Math.max(20, (end.y - start.y) / 2)
  return {
    id: edge.id,
    source: edge.source,
    target: edge.target,
    kind: edge.kind,
    label: edge.label,
    points: [start, { x: start.x, y: midY }, { x: end.x, y: midY }, end],
  }
}
