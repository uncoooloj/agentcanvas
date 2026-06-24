import type {
  AppModel,
  BranchNode,
  CanvasMapping,
  CanvasSourceMetadata,
  CodeGraph,
  FlowNode,
  Journey,
  MappingStage,
  PendingItem,
  PendingStatus,
  PendingStatusHistoryEntry,
  StepNode,
} from "./types"

export class ApiError extends Error {
  readonly path: string
  readonly status: number

  constructor(path: string, status: number, detail?: string) {
    super(`${status}${detail ? `: ${detail}` : ""}`)
    this.name = "ApiError"
    this.path = path
    this.status = status
  }
}

function token(): string | null {
  return new URLSearchParams(window.location.search).get("token")
}

function sessionId(): string | null {
  const params = new URLSearchParams(window.location.search)
  return params.get("sessionId") || params.get("session_id")
}

function url(path: string): string {
  const u = new URL(path, window.location.origin)
  const t = token()
  if (t) u.searchParams.set("token", t)
  const sid = sessionId()
  if (sid) u.searchParams.set("sessionId", sid)
  return u.toString()
}

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(url(path), { headers: { "content-type": "application/json" } })
  const data = (await res.json().catch(() => null)) as T | { error?: unknown } | null
  if (!res.ok) {
    const error = recordValue(data)?.error
    throw new ApiError(path, res.status, error ? String(error) : res.statusText)
  }
  return data as T
}

export async function fetchCanvasModel(): Promise<AppModel> {
  const data = await getJson<unknown>("/api/canvas")
  return normalizeCanvasPayload(data)
}

export interface CanvasResponse {
  model: AppModel
  mapping?: CanvasMapping
}

export async function fetchCanvas(): Promise<CanvasResponse> {
  const data = await getJson<unknown>("/api/canvas")
  const root = recordValue(data)
  return {
    model: normalizeCanvasPayload(data),
    mapping: normalizeCanvasMapping(recordValue(root?.mapping)),
  }
}

export async function fetchGraph(): Promise<CodeGraph> {
  const data = await getJson<{ ok: boolean; graph: CodeGraph }>("/api/graph")
  return data.graph
}

export async function fetchPending(): Promise<PendingItem[]> {
  const data = await getJson<{ ok: boolean; pending: unknown[] }>("/api/pending")
  return (data.pending || []).map(normalizePending)
}

export async function reindex(): Promise<CodeGraph> {
  const res = await fetch(url("/api/reindex"), {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ source: "agentcanvas-web" }),
  })
  if (!res.ok) {
    const data = (await res.json().catch(() => null)) as { error?: unknown } | null
    throw new ApiError("/api/reindex", res.status, data?.error ? String(data.error) : res.statusText)
  }
  const data = (await res.json()) as { graph: CodeGraph }
  return data.graph
}

export async function reindexCanvas(): Promise<CanvasResponse> {
  const res = await fetch(url("/api/reindex"), {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ source: "agentcanvas-web" }),
  })
  if (!res.ok) {
    const data = (await res.json().catch(() => null)) as { error?: unknown } | null
    throw new ApiError("/api/reindex", res.status, data?.error ? String(data.error) : res.statusText)
  }
  const data = await res.json()
  const root = recordValue(data)
  return {
    model: normalizeCanvasPayload(data),
    mapping: normalizeCanvasMapping(recordValue(root?.mapping)),
  }
}

export function isApiNotFound(error: unknown): boolean {
  return error instanceof ApiError && error.status === 404
}

export function describeApiError(error: unknown): string {
  if (error instanceof ApiError) return `${error.path} returned ${error.message}`
  if (error instanceof Error) return error.message
  return String(error)
}

// A behavioral change request — plain intent the user expressed on the canvas.
export interface ChangeRequest {
  changeId: string
  clientChangeId: string
  kind: string
  title: string
  summary: string // the plain-language instruction, in the user's words
  journey?: string
  journeyId?: string
  journeyTitle?: string
  afterStep?: string | null
  targetStep?: string | null
  targetNodeId?: string | null
  action?: string
  text1?: string
  text2?: string
}

export async function postChange(change: ChangeRequest): Promise<PendingItem> {
  const res = await fetch(url("/api/changes"), {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ ...change, sessionId: sessionId(), created_from: "agentcanvas-web" }),
  })
  const data = (await res.json().catch(() => null)) as { pending?: unknown; error?: unknown } | null
  if (!res.ok) {
    const detail = data?.error ? `: ${String(data.error)}` : ""
    throw new Error(`${res.status}${detail}`)
  }
  if (!data?.pending) throw new Error("Created pending request was missing from the response.")
  return normalizePending(data.pending)
}

function normalizePending(item: unknown): PendingItem {
  const it = (item || {}) as Record<string, unknown>
  const change = recordValue(it.change)
  return {
    id: String(it.id || it.key || `pending-${Math.random().toString(36).slice(2, 8)}`),
    title: String(it.title || it.summary || "Change request"),
    target: String(it.target || it.journey || ""),
    status: normalizePendingStatus(it.status),
    localOnly: Boolean(it.localOnly),
    summary: it.summary ? String(it.summary) : undefined,
    note: it.note ? String(it.note) : undefined,
    error: it.error ? String(it.error) : undefined,
    workspace: it.workspace ? String(it.workspace) : undefined,
    sessionId: stringValue(it.sessionId) || stringValue(it.session_id),
    changeId:
      stringValue(it.changeId) ||
      stringValue(it.change_id) ||
      stringValue(change?.changeId) ||
      stringValue(change?.clientChangeId) ||
      stringValue(change?.change_id),
    createdAt: stringValue(it.created_at) || stringValue(it.createdAt),
    updatedAt: stringValue(it.updated_at) || stringValue(it.updatedAt),
    jsonPath: typeof it.json_path === "string" ? it.json_path : typeof it.jsonPath === "string" ? it.jsonPath : null,
    markdownPath:
      typeof it.markdown_path === "string"
        ? it.markdown_path
        : typeof it.markdownPath === "string"
          ? it.markdownPath
          : null,
    statusHistory: normalizeStatusHistory(it.status_history || it.statusHistory),
  }
}

function normalizeCanvasPayload(data: unknown): AppModel {
  const payload = unwrapCanvasPayload(data)
  const journeys = Array.isArray(payload.journeys) ? payload.journeys : []

  if (
    payload.schema === "agentcanvas.canvas.v1" ||
    journeys.some((journey) => Array.isArray(recordValue(journey)?.steps))
  ) {
    return normalizeCanonicalCanvas(payload)
  }

  if (journeys.some((journey) => Array.isArray(recordValue(journey)?.nodes))) {
    return normalizeExistingAppModel(payload)
  }

  if (Array.isArray(payload.journeys)) {
    return {
      appName: appNameFromPayload(payload),
      journeys: [],
      isDemo: false,
      thin: true,
    }
  }

  throw new Error("Canvas response did not include journeys.")
}

function normalizeCanvasMapping(value: Record<string, unknown> | undefined): CanvasMapping | undefined {
  if (!value) return undefined
  return {
    schema: stringValue(value.schema),
    status: stringValue(value.status),
    mode: stringValue(value.mode),
    primaryMode: stringValue(value.primaryMode) || stringValue(value.primary_mode),
    fallbackMode: stringValue(value.fallbackMode) || stringValue(value.fallback_mode),
    flowCount: typeof value.flowCount === "number" ? value.flowCount : undefined,
    displayFlowCount: typeof value.displayFlowCount === "number" ? value.displayFlowCount : undefined,
    stale:
      booleanValue(value.stale) ||
      booleanValue(value.staleCache) ||
      booleanValue(value.stale_cache) ||
      stringLooksStale(value.status) ||
      stringLooksStale(value.cacheStatus) ||
      stringLooksStale(value.cache_status),
    empty: booleanValue(value.empty),
    demoFallback: booleanValue(value.demoFallback) || booleanValue(value.demo_fallback),
    cacheStatus: stringValue(value.cacheStatus) || stringValue(value.cache_status),
    source: normalizeCanvasSource(value.source) || sourceFromLegacyFields(value),
    warnings: Array.isArray(value.warnings) ? value.warnings.map((item) => String(item)).filter(Boolean) : undefined,
    stages: Array.isArray(value.stages)
      ? value.stages.map(normalizeMappingStage).filter((stage): stage is MappingStage => Boolean(stage))
      : undefined,
  }
}

function normalizeCanvasSource(value: unknown): CanvasSourceMetadata | undefined {
  const source = recordValue(value)
  if (!source) return undefined
  return {
    kind: stringValue(source.kind),
    status: stringValue(source.status),
    label: stringValue(source.label),
    reason: stringValue(source.reason),
    flowCount: typeof source.flowCount === "number" ? source.flowCount : undefined,
    isDemoContent: booleanValue(source.isDemoContent) || booleanValue(source.is_demo_content),
    isFallback: booleanValue(source.isFallback) || booleanValue(source.is_fallback),
    isStale: booleanValue(source.isStale) || booleanValue(source.is_stale),
    isEmpty: booleanValue(source.isEmpty) || booleanValue(source.is_empty),
  }
}

function sourceFromLegacyFields(value: Record<string, unknown>): CanvasSourceMetadata | undefined {
  const label = stringValue(value.sourceLabel) || stringValue(value.source_label) || stringValue(value.source)
  if (!label) return undefined
  return { label }
}

function normalizeMappingStage(value: unknown): MappingStage | null {
  const stage = recordValue(value)
  if (!stage) return null
  const id = stringValue(stage.id) || slug(stringValue(stage.label) || "stage", "stage")
  const label = stringValue(stage.label) || "Mapping workspace"
  const status = stringValue(stage.status)
  return {
    id,
    label,
    status:
      status === "pending" || status === "active" || status === "done" || status === "ready" || status === "error"
        ? status
        : "pending",
    detail: stringValue(stage.detail),
  }
}

function unwrapCanvasPayload(data: unknown): Record<string, unknown> {
  const root = recordValue(data)
  if (!root) throw new Error("Canvas response was empty.")
  return (
    recordValue(root.canvas) ||
    recordValue(root.canvas_model) ||
    recordValue(root.canvasModel) ||
    recordValue(root.model) ||
    root
  )
}

function normalizeExistingAppModel(payload: Record<string, unknown>): AppModel {
  const journeys = (Array.isArray(payload.journeys) ? payload.journeys : [])
    .map(normalizeExistingJourney)
    .filter((journey): journey is Journey => Boolean(journey))

  return {
    appName: appNameFromPayload(payload),
    journeys,
    isDemo: false,
    thin: Boolean(payload.thin) || journeys.length === 0 || undefined,
  }
}

function normalizeExistingJourney(value: unknown): Journey | null {
  const journey = recordValue(value)
  if (!journey) return null
  const nodes = (Array.isArray(journey.nodes) ? journey.nodes : [])
    .map(normalizeFlowNode)
    .filter((node): node is FlowNode => Boolean(node))
  if (!nodes.length) return null

  const title = stringValue(journey.title) || "Workspace flow"
  const firstWhen = nodes.find((node): node is StepNode => node.kind === "step" && node.role === "when")
  return {
    id: stringValue(journey.id) || slug(title, "journey"),
    title,
    summary: stringValue(journey.summary) || "Mapped from your workspace.",
    entry: stringValue(journey.entry) || firstWhen?.text || title,
    nodes,
  }
}

function normalizeCanonicalCanvas(payload: Record<string, unknown>): AppModel {
  const journeys = (Array.isArray(payload.journeys) ? payload.journeys : [])
    .map(normalizeCanvasJourney)
    .filter((journey): journey is Journey => Boolean(journey))

  return {
    appName: appNameFromPayload(payload),
    journeys,
    isDemo: false,
    thin: journeys.length === 0 || undefined,
  }
}

function normalizeCanvasJourney(value: unknown): Journey | null {
  const journey = recordValue(value)
  if (!journey) return null
  const nodes = canvasStepsToFlow(journey.steps)
  if (!nodes.length) return null

  const metadata = recordValue(journey.metadata)
  const title = stringValue(journey.title) || stringValue(metadata?.title) || "Workspace flow"
  const firstWhen = nodes.find((node): node is StepNode => node.kind === "step" && node.role === "when")
  return {
    id: stringValue(journey.id) || slug(title, "journey"),
    title,
    summary:
      stringValue(journey.summary) ||
      stringValue(metadata?.summary) ||
      stringValue(metadata?.description) ||
      "Mapped from your workspace canvas.",
    entry: stringValue(journey.entry) || stringValue(metadata?.entry) || firstWhen?.text || title,
    nodes,
  }
}

function canvasStepsToFlow(value: unknown): FlowNode[] {
  const steps = Array.isArray(value) ? value.map(recordValue).filter(Boolean) : []
  const nodes: FlowNode[] = []

  for (let index = 0; index < steps.length; index += 1) {
    const step = steps[index]
    const kind = canvasStepKind(step?.kind)

    if (kind === "if") {
      const chain = [step]
      while (index + 1 < steps.length) {
        const next = steps[index + 1]
        const nextKind = canvasStepKind(next?.kind)
        if (nextKind !== "elseIf" && nextKind !== "else") break
        chain.push(next)
        index += 1
        if (nextKind === "else") break
      }
      nodes.push(branchFromCanvasChain(chain))
      continue
    }

    if (kind === "elseIf" || kind === "else") {
      continue
    }

    nodes.push(stepFromCanvas(step, kind === "when" ? "when" : "do"))
  }

  return nodes
}

function branchFromCanvasChain(chain: Array<Record<string, unknown> | undefined>): BranchNode {
  const [head, ...rest] = chain
  const next = rest[0]
  const nextKind = canvasStepKind(next?.kind)
  const refs = refsFromCanvasStep(head)

  return {
    kind: "branch",
    id: stepId(head, "branch"),
    condition: conditionText(head),
    then: canvasStepsToFlow(head?.steps),
    otherwise:
      nextKind === "elseIf"
        ? [branchFromCanvasChain(rest)]
        : nextKind === "else"
          ? canvasStepsToFlow(next?.steps)
          : [],
    uncertain: isUncertain(head),
    tech: refs.length ? { refs } : undefined,
  }
}

function stepFromCanvas(step: Record<string, unknown> | undefined, role: "when" | "do"): StepNode {
  const refs = refsFromCanvasStep(step)
  return {
    kind: "step",
    id: stepId(step, role),
    role,
    text: stringValue(step?.text) || stringValue(step?.label) || (role === "when" ? "Someone uses this flow" : "Do the mapped step"),
    uncertain: isUncertain(step),
    tech: refs.length ? { refs } : undefined,
  }
}

function normalizeFlowNode(value: unknown): FlowNode | null {
  const node = recordValue(value)
  if (!node) return null
  if (node.kind === "branch") {
    const thenNodes = (Array.isArray(node.then) ? node.then : [])
      .map(normalizeFlowNode)
      .filter((child): child is FlowNode => Boolean(child))
    const otherwiseNodes = (Array.isArray(node.otherwise) ? node.otherwise : [])
      .map(normalizeFlowNode)
      .filter((child): child is FlowNode => Boolean(child))
    return {
      kind: "branch",
      id: stringValue(node.id) || slug(stringValue(node.condition) || "branch", "branch"),
      condition: stringValue(node.condition) || "mapped condition",
      then: thenNodes,
      otherwise: otherwiseNodes,
      uncertain: Boolean(node.uncertain),
      tech: normalizeTech(node.tech),
    }
  }
  if (node.kind === "step") {
    const role = node.role === "when" ? "when" : "do"
    return {
      kind: "step",
      id: stringValue(node.id) || slug(stringValue(node.text) || role, role),
      role,
      text: stringValue(node.text) || "Mapped step",
      detail: stringValue(node.detail),
      uncertain: Boolean(node.uncertain),
      tech: normalizeTech(node.tech),
    }
  }
  return null
}

function normalizeTech(value: unknown): { nodeId?: string; refs: string[] } | undefined {
  const tech = recordValue(value)
  if (!tech) return undefined
  const refs = Array.isArray(tech.refs) ? tech.refs.map((item) => String(item)).filter(Boolean) : []
  if (!refs.length) return undefined
  return { nodeId: stringValue(tech.nodeId), refs }
}

function canvasStepKind(value: unknown): "when" | "do" | "if" | "elseIf" | "else" {
  const normalized = String(value || "Do").replace(/[_-]+/g, "").toLowerCase()
  if (normalized === "when") return "when"
  if (normalized === "if") return "if"
  if (normalized === "elseif" || normalized === "elif") return "elseIf"
  if (normalized === "else") return "else"
  return "do"
}

function stepId(step: Record<string, unknown> | undefined, fallback: string): string {
  return stringValue(step?.id) || slug(stringValue(step?.text) || stringValue(step?.condition) || fallback, fallback)
}

function conditionText(step: Record<string, unknown> | undefined): string {
  return stringValue(step?.condition) || stringValue(step?.text) || "mapped condition"
}

function refsFromCanvasStep(step: Record<string, unknown> | undefined): string[] {
  const refs = Array.isArray(step?.refs) ? step.refs.map((item) => String(item)).filter(Boolean) : []
  const provenance = Array.isArray(step?.provenance) ? step.provenance : []
  for (const entry of provenance) {
    const record = recordValue(entry)
    const location = recordValue(record?.location)
    const path = stringValue(location?.path) || stringValue(record?.path)
    if (path) refs.push(path)
  }
  return Array.from(new Set(refs))
}

function isUncertain(step: Record<string, unknown> | undefined): boolean | undefined {
  const confidence = confidenceScore(step?.confidence)
  return typeof confidence === "number" ? confidence < 0.6 : undefined
}

function confidenceScore(value: unknown): number | undefined {
  if (typeof value === "number") return value
  const record = recordValue(value)
  const score = record?.score
  return typeof score === "number" ? score : undefined
}

function appNameFromPayload(payload: Record<string, unknown>): string {
  const metadata = recordValue(payload.metadata)
  const workspace = payload.workspace
  const workspaceRecord = recordValue(workspace)
  const raw =
    stringValue(payload.appName) ||
    stringValue(payload.app_name) ||
    stringValue(payload.title) ||
    stringValue(metadata?.title) ||
    stringValue(workspaceRecord?.name) ||
    stringValue(workspaceRecord?.root) ||
    (typeof workspace === "string" ? workspace : undefined) ||
    stringValue(payload.name) ||
    "Your app"
  return titleFromPath(raw)
}

function titleFromPath(value: string): string {
  const last = value.split(/[/\\]/).filter(Boolean).pop() || value
  return last
    .replace(/\.[a-z0-9]+$/i, "")
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/^./, (char) => char.toUpperCase())
}

function slug(value: string, fallback: string): string {
  const cleaned = value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
  return cleaned || fallback
}

export function hasToken(): boolean {
  return Boolean(token())
}

const PENDING_STATUSES: PendingStatus[] = ["pending", "sent", "in_progress", "done", "needs_input", "blocked"]

function normalizePendingStatus(status: unknown): PendingStatus {
  const value = String(status || "pending")
  if ((PENDING_STATUSES as string[]).includes(value)) return value as PendingStatus
  return value === "queued" ? "pending" : "blocked"
}

function normalizeStatusHistory(value: unknown): PendingStatusHistoryEntry[] | undefined {
  if (!Array.isArray(value)) return undefined
  return value.map((entry) => {
    const record = recordValue(entry)
    return {
      status: normalizePendingStatus(record?.status),
      updatedAt: stringValue(record?.updated_at) || stringValue(record?.updatedAt),
      note: stringValue(record?.note),
    }
  })
}

function recordValue(value: unknown): Record<string, unknown> | undefined {
  return value && typeof value === "object" ? (value as Record<string, unknown>) : undefined
}

function stringValue(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() ? value : undefined
}

function booleanValue(value: unknown): boolean {
  return value === true || value === "true" || value === "1"
}

function stringLooksStale(value: unknown): boolean {
  return typeof value === "string" && /stale|out[-_\s]?of[-_\s]?date|expired/i.test(value)
}
