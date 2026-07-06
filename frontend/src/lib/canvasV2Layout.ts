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
