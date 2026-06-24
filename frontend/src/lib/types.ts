// The code-shaped IR that the Python indexer produces.
export interface CodeNode {
  id: string
  label?: string
  name?: string
  title?: string
  type?: string
  kind?: string
  group?: string
  component?: string
  module?: string
  confidence?: number
  source_refs?: Array<string | { path?: string; file?: string; line?: number }>
  sources?: Array<string | { path?: string }>
  inputs?: string[]
  outputs?: string[]
  notes?: string[] | string
}

export interface CodeEdge {
  id?: string
  source?: string
  target?: string
  from?: string
  to?: string
  label?: string
  kind?: string
}

export interface CodeGraph {
  schema?: string
  generated_at?: string
  workspace?: string
  summary?: Record<string, unknown>
  nodes?: CodeNode[]
  edges?: CodeEdge[]
  components?: unknown[]
  groups?: unknown[]
  metadata?: Record<string, unknown>
}

// ---- The behavioral projection that the canvas renders ----

// A trigger or an action. ("when" only appears as the first node of a journey.)
export type StepRole = "when" | "do"

export interface StepNode {
  kind: "step"
  id: string
  role: StepRole
  text: string
  detail?: string
  uncertain?: boolean
  tech?: { nodeId?: string; refs: string[] }
}

// A decision: the "then" path runs when the condition holds, "otherwise" when it doesn't.
export interface BranchNode {
  kind: "branch"
  id: string
  condition: string
  then: FlowNode[]
  otherwise: FlowNode[]
  uncertain?: boolean
  tech?: { nodeId?: string; refs: string[] }
}

export type FlowNode = StepNode | BranchNode

export interface Journey {
  id: string
  title: string
  summary: string
  // Plain entry-point phrasing for the landing canvas, e.g. "Someone places an order".
  entry: string
  nodes: FlowNode[]
  lastEditedAt?: number
}

export interface AppModel {
  appName: string
  journeys: Journey[]
  isDemo: boolean
  thin?: boolean
}

export interface MappingStage {
  id: string
  label: string
  status: "pending" | "active" | "done" | "ready" | "error"
  detail?: string
}

export interface CanvasMapping {
  schema?: string
  status?: string
  mode?: string
  primaryMode?: string
  fallbackMode?: string
  flowCount?: number
  displayFlowCount?: number
  stale?: boolean
  empty?: boolean
  demoFallback?: boolean
  cacheStatus?: string
  source?: CanvasSourceMetadata
  warnings?: string[]
  stages?: MappingStage[]
}

export interface CanvasSourceMetadata {
  kind?: string
  status?: string
  label?: string
  reason?: string
  flowCount?: number
  isDemoContent?: boolean
  isFallback?: boolean
  isStale?: boolean
  isEmpty?: boolean
}

export type CanvasSourceKind =
  | "agent-authored"
  | "heuristic-projection"
  | "demo"
  | "demo-fallback"
  | "stale-cache"
  | "no-flow"
  | "loading"
  | "error"
  | "unknown"

export interface CanvasSourceSummary {
  kind: CanvasSourceKind
  label: string
  shortLabel: string
  detail: string
  tone: "default" | "info" | "warning" | "error"
  flowCount?: number
}

export type PendingStatus = "pending" | "sent" | "in_progress" | "done" | "needs_input" | "blocked"

export interface PendingStatusHistoryEntry {
  status: PendingStatus
  updatedAt?: string
  note?: string
}

export interface PendingItem {
  id: string
  title: string
  target: string
  status: PendingStatus
  localOnly?: boolean
  summary?: string
  note?: string
  error?: string
  workspace?: string
  sessionId?: string
  changeId?: string
  createdAt?: string
  updatedAt?: string
  jsonPath?: string | null
  markdownPath?: string | null
  statusHistory?: PendingStatusHistoryEntry[]
}

// ---- helpers ----

export function findNode(nodes: FlowNode[], id: string): FlowNode | null {
  for (const n of nodes) {
    if (n.id === id) return n
    if (n.kind === "branch") {
      const found = findNode(n.then, id) ?? findNode(n.otherwise, id)
      if (found) return found
    }
  }
  return null
}

export function countSteps(nodes: FlowNode[]): number {
  let c = 0
  for (const n of nodes) {
    c += 1
    if (n.kind === "branch") c += countSteps(n.then) + countSteps(n.otherwise)
  }
  return c
}
