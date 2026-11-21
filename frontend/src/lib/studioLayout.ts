import type { StudioComponent, StudioDocument, StudioFlow, StudioNode } from "./studioTypes"

export const SYSTEM_WIDTH = 276
export const FLOW_WIDTH = 300

type Size = { width: number; height: number }
type GraphItem = Size & { id: string }
type GraphEdge = { id: string; source: string; target: string }
export type MeasuredSizes = Readonly<Record<string, Size>>
export type LayoutNode = GraphItem & { x: number; y: number }

let engine: Promise<InstanceType<typeof import("elkjs/lib/elk.bundled.js").default>> | undefined

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

async function layout(items: GraphItem[], edges: GraphEdge[], direction: "RIGHT" | "DOWN"): Promise<LayoutNode[]> {
  if (!items.length) return []
  const ids = new Set(items.map(({ id }) => id))
  engine ??= import("elkjs/lib/elk.bundled.js").then(({ default: Elk }) => new Elk())
  const elk = await engine
  const graph = await elk.layout({
    id: "studio",
    children: items,
    edges: edges.filter(({ source, target }) => ids.has(source) && ids.has(target)).map(({ id, source, target }) => ({
      id: `edge:${id}`, sources: [source], targets: [target],
    })),
    layoutOptions: {
      "elk.algorithm": "layered",
      "elk.direction": direction,
      "elk.spacing.nodeNode": "72",
      "elk.layered.spacing.nodeNodeBetweenLayers": direction === "RIGHT" ? "134" : "92",
    },
  })
  const positions = new Map(graph.children?.map((node) => [node.id, node]))
  return items.map((item) => ({ ...item, x: positions.get(item.id)?.x ?? 0, y: positions.get(item.id)?.y ?? 0 }))
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
