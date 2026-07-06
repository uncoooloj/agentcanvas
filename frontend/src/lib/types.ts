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

// A trigger or an action. (When only appears as the first node of a journey.)
export enum StepRole {
  When = "when",
  Do = "do",
}

export enum FlowNodeKind {
  Step = "step",
  Branch = "branch",
}

export enum CodeGraphNodeType {
  AppSurface = "app_surface",
  Component = "component",
  Export = "export",
  File = "file",
}

export enum CanvasStepKind {
  When = "when",
  Do = "do",
  If = "if",
  ElseIf = "elseIf",
  Else = "else",
}

export enum FlowAction {
  Change = "change",
  AddAfter = "add_after",
  AddRule = "add_rule",
  Remove = "remove",
  ChangeCondition = "change_condition",
  AddThen = "add_then",
  AddElse = "add_else",
}

export interface StepNode {
  kind: FlowNodeKind.Step
  id: string
  role: StepRole
  text: string
  detail?: string
  uncertain?: boolean
  tech?: { nodeId?: string; refs: string[] }
  native?: CanvasV2NativeRef
}

// A decision: the "then" path runs when the condition holds, "otherwise" when it doesn't.
export interface BranchNode {
  kind: FlowNodeKind.Branch
  id: string
  condition: string
  then: FlowNode[]
  otherwise: FlowNode[]
  uncertain?: boolean
  tech?: { nodeId?: string; refs: string[] }
  native?: CanvasV2NativeRef
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

export enum CanvasV2Schema {
  Canvas = "agentcanvas.canvas.v2",
}

export enum CanvasV2NodeKind {
  When = "When",
  Do = "Do",
  Decision = "Decision",
  Loop = "Loop",
  Parallel = "Parallel",
  Join = "Join",
  Wait = "Wait",
  SubFlow = "SubFlow",
  End = "End",
}

export enum CanvasV2EdgeKind {
  Normal = "normal",
  Branch = "branch",
  LoopBody = "loop_body",
  LoopBack = "loop_back",
  LoopExit = "loop_exit",
  Parallel = "parallel",
  Error = "error",
  Async = "async",
}

export interface CanvasV2Node {
  id: string
  kind: CanvasV2NodeKind
  title: string
  summary?: string
  evidenceRefs: string[]
  flowRef?: string
  metadata?: Record<string, unknown>
}

export interface CanvasV2Edge {
  id: string
  kind: CanvasV2EdgeKind
  source: string
  target: string
  label?: string
  isDefault?: boolean
  metadata?: Record<string, unknown>
}

export interface CanvasV2Flow {
  id: string
  title: string
  summary: string
  entryNode?: string
  altitude?: string
  nodes: CanvasV2Node[]
  edges: CanvasV2Edge[]
  evidenceRefs: string[]
  metadata?: Record<string, unknown>
}

export interface CanvasV2Document {
  schema: CanvasV2Schema
  revision: number
  authoredBy?: string
  updatedAt?: string | null
  evidence?: Record<string, unknown>
  app: {
    name: string
    summary: string
    isDemo: boolean
  }
  flows: CanvasV2Flow[]
  metadata?: Record<string, unknown>
}

export interface CanvasV2NativeRef {
  schema: CanvasV2Schema
  flowId?: string
  nodeId: string
  nodeKind: CanvasV2NodeKind
  edgeKinds?: CanvasV2EdgeKind[]
  flowRef?: string
}

export interface MappingStage {
  id: string
  label: string
  status: MappingStageStatus
  detail?: string
}

export enum MappingStageStatus {
  Pending = "pending",
  Active = "active",
  Done = "done",
  Ready = "ready",
  Error = "error",
}

export enum CanvasStateKind {
  Idle = "idle",
  Ready = "ready",
  Loading = "loading",
  Reindexing = "reindexing",
  Empty = "empty",
  Error = "error",
}

export enum JourneyActivity {
  Idle = "idle",
  Edited = "edited",
  Working = "working",
}

export interface CanvasMapping {
  schema?: string
  status?: CanvasSourceStatus
  mode?: CanvasMappingMode
  primaryMode?: CanvasMappingMode
  fallbackMode?: CanvasMappingMode
  flowCount?: number
  displayFlowCount?: number
  stale?: boolean
  empty?: boolean
  demoFallback?: boolean
  cacheStatus?: CanvasSourceStatus
  source?: CanvasSourceMetadata
  warnings?: string[]
  stages?: MappingStage[]
}

export interface CanvasSourceMetadata {
  kind?: CanvasSourceKind
  status?: CanvasSourceStatus
  label?: string
  reason?: CanvasSourceReason
  flowCount?: number
  isDemoContent?: boolean
  isFallback?: boolean
  isStale?: boolean
  isEmpty?: boolean
}

export enum CanvasSourceKind {
  AgentAuthored = "agent-authored",
  HeuristicProjection = "heuristic-projection",
  Demo = "demo",
  DemoFallback = "demo-fallback",
  Empty = "empty",
  Workspace = "workspace",
  StaleCache = "stale-cache",
  NoFlow = "no-flow",
  Loading = "loading",
  Error = "error",
  Unknown = "unknown",
}

export enum CanvasSourceStatus {
  Ready = "ready",
  Demo = "demo",
  DemoFallback = "demo_fallback",
  Empty = "empty",
  StaleCache = "stale_cache",
  Workspace = "workspace",
}

export enum CanvasSourceReason {
  DemoWorkspace = "demo_workspace",
  LaunchPageWithoutWorkspace = "launch_page_without_workspace",
  RequestedDemoWorkspace = "requested_demo_workspace",
}

export enum CanvasMappingMode {
  AgentAuthored = "agent-authored",
  Deterministic = "deterministic",
  Empty = "empty",
  Heuristic = "heuristic",
  HeuristicProjection = "heuristic-projection",
  LlmAssisted = "llm-assisted",
  V2Compat = "v2-compat",
}

export enum CanvasSourceTone {
  Default = "default",
  Info = "info",
  Warning = "warning",
  Error = "error",
}

export enum CopyState {
  Idle = "idle",
  Copied = "copied",
  Manual = "manual",
}

export interface CanvasSourceSummary {
  kind: CanvasSourceKind
  label: string
  shortLabel: string
  detail: string
  tone: CanvasSourceTone
  flowCount?: number
}

export enum PendingStatus {
  Pending = "pending",
  Sent = "sent",
  InProgress = "in_progress",
  Implemented = "implemented",
  NeedsInput = "needs_input",
  Blocked = "blocked",
  Verified = "verified",
  Done = "done",
  Cancelled = "cancelled",
  Rejected = "rejected",
}

export enum LegacyPendingStatus {
  Queued = "queued",
}

export enum ChangeKind {
  New = "new",
  Edited = "edited",
  Removing = "removing",
}

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
    if (n.kind === FlowNodeKind.Branch) {
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
    if (n.kind === FlowNodeKind.Branch) c += countSteps(n.then) + countSteps(n.otherwise)
  }
  return c
}
