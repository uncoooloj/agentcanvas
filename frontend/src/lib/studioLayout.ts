import type { StudioComponent, StudioDocument, StudioFlow, StudioNode } from "./studioTypes"

export const SYSTEM_WIDTH = 276
export const FLOW_WIDTH = 300

type Size = { width: number; height: number }
type GraphItem = Size & { id: string }
type GraphEdge = { id: string; source: string; target: string }
export type MeasuredSizes = Readonly<Record<string, Size>>
export type LayoutNode = GraphItem & { x: number; y: number }

// Estimate before the first paint. The canvas refines these dimensions with the
// measured cards, including wrapped text, badges, and touch action rows.
function textRows(text: string | undefined, columns: number) {
  return (text ?? "").split("\n").reduce((rows, line) => rows + Math.max(1, Math.ceil(line.length / columns)), 0)
}

export function systemNodeHeight(component: StudioComponent) {
  return 138 + textRows(component.name, 23) * 23 + textRows(component.summary, 32) * 19
    + textRows(component.path, 30) * 16 + Math.ceil(component.tech.join("   ").length / 29) * 25
}

export function flowNodeHeight(node: StudioNode) {
  return 92 + textRows(node.title, 25) * 23 + (node.summary ? textRows(node.summary, 35) * 19 : 0)
    + (node.code_refs[0] ? textRows(node.code_refs[0].path, 33) * 16 + 14 : 0)
}

/**
 * Fast, deterministic layered DAG layout (<1ms, zero bundle overhead).
 * Handles cycles gracefully via Kahn/DFS layering and minimizes crossings with
 * a barycenter pass over parent ranks while respecting measured node bounds.
 */
async function layout(items: GraphItem[], edges: GraphEdge[], direction: "RIGHT" | "DOWN"): Promise<LayoutNode[]> {
  if (!items.length) return []
  const byId = new Map(items.map((item) => [item.id, item]))
  const orderIndex = new Map(items.map((item, idx) => [item.id, idx]))
  const validEdges = edges.filter(({ source, target }) => source !== target && byId.has(source) && byId.has(target))

  // Build adjacency while breaking back-edges deterministically via DFS.
  const outgoing = new Map<string, string[]>(items.map(({ id }) => [id, []]))
  const incoming = new Map<string, string[]>(items.map(({ id }) => [id, []]))
  for (const edge of validEdges) {
    outgoing.get(edge.source)!.push(edge.target)
    incoming.get(edge.target)!.push(edge.source)
  }

  const state = new Map<string, 0 | 1 | 2>()
  const dagEdges: GraphEdge[] = []
  function dfs(id: string) {
    state.set(id, 1)
    for (const next of outgoing.get(id) ?? []) {
      const nextState = state.get(next) ?? 0
      if (nextState === 1) continue // skip cycle back-edge
      dagEdges.push({ id: `${id}->${next}`, source: id, target: next })
      if (nextState === 0) dfs(next)
    }
    state.set(id, 2)
  }
  // Start from roots (in-degree 0), then any remaining nodes in stable order.
  const roots = items.filter(({ id }) => (incoming.get(id)?.length ?? 0) === 0).map(({ id }) => id)
  for (const root of [...roots, ...items.map(({ id }) => id)]) {
    if ((state.get(root) ?? 0) === 0) dfs(root)
  }

  // Assign topological longest-path layers on the acyclic edge set.
  const dagParents = new Map<string, string[]>(items.map(({ id }) => [id, []]))
  const dagChildren = new Map<string, string[]>(items.map(({ id }) => [id, []]))
  for (const edge of dagEdges) {
    dagParents.get(edge.target)!.push(edge.source)
    dagChildren.get(edge.source)!.push(edge.target)
  }

  const rank = new Map<string, number>()
  for (const { id } of items) rank.set(id, 0)
  for (let pass = 0; pass < items.length; pass += 1) {
    let changed = false
    for (const edge of dagEdges) {
      const nextRank = (rank.get(edge.source) ?? 0) + 1
      if (nextRank > (rank.get(edge.target) ?? 0)) {
        rank.set(edge.target, nextRank)
        changed = true
      }
    }
    if (!changed) break
  }

  const maxRank = Math.max(0, ...rank.values())
  const layers: GraphItem[][] = Array.from({ length: maxRank + 1 }, () => [])
  for (const item of items) {
    layers[rank.get(item.id) ?? 0].push(item)
  }

  // Order within each layer using parent barycenter to reduce edge crossings.
  const slot = new Map<string, number>()
  layers[0].forEach((item, idx) => slot.set(item.id, idx))
  for (let r = 1; r <= maxRank; r += 1) {
    layers[r].sort((a, b) => {
      const parentsA = dagParents.get(a.id) ?? []
      const parentsB = dagParents.get(b.id) ?? []
      const avgA = parentsA.length
        ? parentsA.reduce((sum, p) => sum + (slot.get(p) ?? 0), 0) / parentsA.length
        : (orderIndex.get(a.id) ?? 0)
      const avgB = parentsB.length
        ? parentsB.reduce((sum, p) => sum + (slot.get(p) ?? 0), 0) / parentsB.length
        : (orderIndex.get(b.id) ?? 0)
      return avgA - avgB || (orderIndex.get(a.id) ?? 0) - (orderIndex.get(b.id) ?? 0)
    })
    layers[r].forEach((item, idx) => slot.set(item.id, idx))
  }

  const nodeGap = direction === "RIGHT" ? 56 : 64
  const layerGap = direction === "RIGHT" ? 128 : 84
  const positioned = new Map<string, LayoutNode>()

  if (direction === "DOWN") {
    let y = 0
    for (const layer of layers) {
      if (!layer.length) continue
      const totalWidth = layer.reduce((sum, n) => sum + n.width, 0) + Math.max(0, layer.length - 1) * nodeGap
      let x = -totalWidth / 2
      let rowHeight = 0
      for (const node of layer) {
        positioned.set(node.id, { ...node, x: Math.round(x), y: Math.round(y) })
        x += node.width + nodeGap
        rowHeight = Math.max(rowHeight, node.height)
      }
      y += rowHeight + layerGap
    }
  } else {
    let x = 0
    for (const layer of layers) {
      if (!layer.length) continue
      const totalHeight = layer.reduce((sum, n) => sum + n.height, 0) + Math.max(0, layer.length - 1) * nodeGap
      let y = -totalHeight / 2
      let colWidth = 0
      for (const node of layer) {
        positioned.set(node.id, { ...node, x: Math.round(x), y: Math.round(y) })
        y += node.height + nodeGap
        colWidth = Math.max(colWidth, node.width)
      }
      x += colWidth + layerGap
    }
  }

  // Normalize coordinates so top-left starts cleanly at (40, 40).
  const all = items.map((item) => positioned.get(item.id)!)
  const minX = Math.min(...all.map((n) => n.x))
  const minY = Math.min(...all.map((n) => n.y))
  return all.map((n) => ({ ...n, x: n.x - minX + 40, y: n.y - minY + 40 }))
}

export function layoutSystem(
  document: Pick<StudioDocument, "components" | "component_edges">,
  measured: MeasuredSizes = {},
) {
  return layout(document.components.map((component) => ({
    id: component.id,
    ...(measured[component.id] ?? { width: SYSTEM_WIDTH, height: systemNodeHeight(component) }),
  })), document.component_edges, "RIGHT")
}

export function layoutFlow(flow: Pick<StudioFlow, "nodes" | "edges">, measured: MeasuredSizes = {}) {
  return layout(flow.nodes.map((node) => ({
    id: node.id,
    ...(measured[node.id] ?? { width: FLOW_WIDTH, height: flowNodeHeight(node) }),
  })), flow.edges, "DOWN")
}
