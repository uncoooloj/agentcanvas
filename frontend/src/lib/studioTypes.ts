export const studioTabs = ["system", "flows", "diff"] as const
export type StudioTab = typeof studioTabs[number]
export type DiffStatus = "added" | "modified" | "removed" | "unchanged"
export type ComponentKind = "web" | "mobile" | "service" | "package" | "worker" | "db" | "external"
export type RunnerId = "codex" | "claude" | "copy"
export type RunKind = "map" | "diff" | "plan" | "build"
export type RunStatus = "queued" | "running" | "needs_input" | "awaiting_approval" | "copy_ready" | "completed" | "failed" | "cancelled" | "discarded"
export type TargetType = "node" | "component" | "flow"

export interface CodeRef {
  path: string
  line?: number
  end_line?: number
  symbol?: string
}

export interface StudioComponent {
  id: string
  name: string
  kind: ComponentKind
  path: string
  summary: string
  tech: string[]
  entrypoints: string[]
  diff_status?: DiffStatus
}

export interface ComponentEdge {
  id: string
  source: string
  target: string
  label: string
  protocol?: string
  diff_status?: DiffStatus
}

export interface StudioNode {
  id: string
  kind: "When" | "Do" | "Decision" | "Loop" | "Parallel" | "Join" | "Wait" | "SubFlow" | "End"
  title: string
  summary?: string
  component_id?: string
  flow_ref?: string
  status: "verified" | "inferred" | "proposed" | "stale"
  diff_status?: DiffStatus
  diff_summary?: string | null
  code_refs: CodeRef[]
  test_ref?: string
}

export interface StudioEdge {
  id: string
  source: string
  target: string
  kind: "normal" | "branch" | "loop_back" | "parallel" | "error" | "async"
  label?: string
  diff_status?: DiffStatus
}

export interface StudioFlow {
  id: string
  title: string
  summary: string
  trigger: string
  component_ids: string[]
  diff_status?: DiffStatus
  diff_summary?: string | null
  nodes: StudioNode[]
  edges: StudioEdge[]
}

export interface StudioDocument {
  schema: "agentcanvas.studio.v3"
  components: StudioComponent[]
  component_edges: ComponentEdge[]
  flows: StudioFlow[]
}

export interface AnnotationInput {
  target_type: TargetType
  target_id: string
  flow_id?: string
  text: string
}

export interface StudioAnnotation extends AnnotationInput {
  id: string
  resolved: boolean
  author?: string
  created_at?: string
  updated_at?: string
}

export interface RunInput {
  kind: RunKind
  prompt?: string
  diff_base?: string
  node_ids?: string[]
  flow_id?: string
  annotation_ids?: string[]
  runner?: RunnerId
}

export interface RunLog {
  id?: string
  at: string
  kind: string
  text: string
  tool?: string
}

export interface RunTest {
  command?: string
  passed?: boolean
  output?: string
}

export interface RunVerification {
  summary?: string | null
  output?: string | null
  command?: string
  passed?: boolean
  tests?: RunTest[]
  changed_files?: string[]
}

export interface StudioRun extends RunInput {
  id: string
  runner: RunnerId
  status: RunStatus
  created_at?: string
  started_at?: string
  updated_at?: string
  finished_at?: string
  logs: RunLog[]
  question?: string | null
  plan_summary?: string | null
  proposed_document?: StudioDocument | null
  verification?: RunVerification | null
  verification_summary?: string | null
  changed_files: string[]
  error?: string | null
}

export interface StudioBootstrapResponse {
  ok: true
  mode: "landing" | "workspace" | "demo"
  workspace: string
  workspace_name: string
  git: { branch: string | null; head: string | null; dirty: boolean; changed_files: string[]; diff_base?: string | null }
  runner: { preferred: RunnerId; available: { id: Exclude<RunnerId, "copy">; label: string; binary: string; version?: string }[] }
  has_mapped_canvas: boolean
  stale_node_ids: string[]
  document: StudioDocument
  annotations: StudioAnnotation[]
  active_run: StudioRun | null
  recent_runs: StudioRun[]
}

export interface FileSlice {
  ok: true
  path: string
  start_line: number
  end_line: number
  highlight_line: number | null
  lines: { number: number; text: string }[]
  language: string
  absolute_path: string
}

export interface DiffHunk {
  header: string
  lines: (string | { text: string; kind?: string })[]
}

export interface FileDiff {
  ok: true
  path: string
  base: string | null
  has_diff: boolean
  hunks: (DiffHunk | string)[]
  additions: number
  deletions: number
}

export type StudioEvents = {
  "studio.updated": Pick<StudioBootstrapResponse, "document" | "has_mapped_canvas" | "stale_node_ids">
  "run.updated": { run: StudioRun }
  "run.log": { run_id: string; entry: RunLog }
  /** A server-directed snapshot reconciliation request. */
  "studio.resync": { reason?: string }
  "annotations.updated": { annotations: StudioAnnotation[] } | { annotation: StudioAnnotation } | { deleted: string } | { id: string; deleted: true }
}

export type StudioEvent = { [K in keyof StudioEvents]: { type: K; payload: StudioEvents[K]; seq?: number } }[keyof StudioEvents]

export function diffCounts(nodes: readonly { diff_status?: DiffStatus }[]) {
  const counts = { added: 0, modified: 0, removed: 0 }
  for (const { diff_status: status } of nodes) {
    if (status && status !== "unchanged") counts[status]++
  }
  return counts
}

export function formatRef(ref: CodeRef) {
  return ref.line ? `${ref.path}:${ref.line}` : ref.path
}

export const runnerLabels: Record<RunnerId, string> = { codex: "Codex", claude: "Claude", copy: "Copy Mode" }
export const isPendingRun = (run?: StudioRun | null) => Boolean(run && (
  run.status === "queued" || run.status === "running" || run.status === "needs_input" || run.status === "awaiting_approval"
))
