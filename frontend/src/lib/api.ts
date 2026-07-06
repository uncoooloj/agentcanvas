import {
  CanvasMappingMode,
  CanvasSourceKind,
  CanvasSourceReason,
  CanvasSourceStatus,
  CanvasStepKind,
  CanvasV2EdgeKind,
  CanvasV2NodeKind,
  CanvasV2Schema,
  ConversationRole,
  ConversationTurnKind,
  FlowNodeKind,
  LegacyPendingStatus,
  MapFreshnessStatus,
  MapHealthReason,
  MapHealthStatus,
  MappingStageStatus,
  PendingStatus,
  StepRole,
  type AppModel,
  type BranchNode,
  type CanvasApplyBatch,
  type CanvasApplyResult,
  type CanvasHistoryEntry,
  type CanvasHistoryResponse,
  type CanvasMapping,
  type CanvasRestoreRequest,
  type CanvasRestoreResult,
  type CanvasSourceMetadata,
  type CanvasV2Document,
  type CanvasV2Edge,
  type CanvasV2Flow,
  type CanvasV2NativeRef,
  type CanvasV2Node,
  type ChangeKind,
  type CodeGraph,
  type FlowAction,
  type FlowNode,
  type Journey,
  type MapHealth,
  type MapHealthFileRef,
  type MappingStage,
  type PendingConversationSummary,
  type PendingConversationTurn,
  type PendingItem,
  type PendingStatusHistoryEntry,
  type StepNode,
} from "./types"

export class ApiError extends Error {
  readonly path: string
  readonly status: number
  readonly code?: string
  readonly details?: unknown
  readonly payload?: unknown

  constructor(path: string, status: number, detail?: string, options: { code?: string; details?: unknown; payload?: unknown } = {}) {
    super(`${status}${detail ? `: ${detail}` : ""}`)
    this.name = "ApiError"
    this.path = path
    this.status = status
    this.code = options.code
    this.details = options.details
    this.payload = options.payload
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
    throw apiError(path, res.status, data, res.statusText)
  }
  return data as T
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(url(path), {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  })
  const data = (await res.json().catch(() => null)) as T | { error?: unknown } | null
  if (!res.ok) {
    throw apiError(path, res.status, data, res.statusText)
  }
  return data as T
}

function apiError(path: string, status: number, payload: unknown, fallback: string): ApiError {
  const root = recordValue(payload)
  const error = recordValue(root?.error)
  if (error) {
    return new ApiError(
      path,
      status,
      stringValue(error.message) || stringValue(error.code) || fallback,
      {
        code: stringValue(error.code),
        details: error.details,
        payload,
      },
    )
  }
  const plain = root?.error
  return new ApiError(path, status, plain ? String(plain) : fallback, { payload })
}

export async function fetchCanvasModel(): Promise<AppModel> {
  const data = await getJson<unknown>("/api/canvas")
  return normalizeCanvasPayload(data)
}

export interface CanvasResponse {
  model: AppModel
  mapping?: CanvasMapping
  revision?: number
  canvasV2?: CanvasV2Document
}

export async function fetchCanvas(): Promise<CanvasResponse> {
  const data = await getJson<unknown>("/api/canvas")
  return normalizeCanvasResponse(data)
}

export async function fetchGraph(): Promise<CodeGraph> {
  const data = await getJson<{ ok: boolean; graph: CodeGraph }>("/api/graph")
  return data.graph
}

export async function fetchPending(): Promise<PendingItem[]> {
  const data = await getJson<{ ok: boolean; pending: unknown[] }>("/api/pending")
  return (data.pending || []).map(normalizePending)
}

export async function fetchPendingRequest(id: string, options: { since?: string } = {}): Promise<PendingItem> {
  const path = pendingPath(id, options.since)
  const data = await getJson<{ ok: boolean; pending: unknown }>(path)
  return normalizePending(data.pending)
}

export async function answerPendingRequest(id: string, answer: string): Promise<PendingItem> {
  const data = await postJson<{ ok: boolean; pending: unknown }>(`${pendingPath(id)}/answer`, {
    answer,
    sessionId: sessionId(),
  })
  return normalizePending(data.pending)
}

export async function fetchMapHealth(): Promise<MapHealth> {
  const data = await getJson<{ ok: boolean; health: unknown }>("/api/health")
  return normalizeMapHealth(data.health)
}

export async function fetchCanvasHistory(): Promise<CanvasHistoryResponse> {
  const data = await getJson<unknown>("/api/canvas/history")
  return normalizeCanvasHistory(data)
}

export async function applyCanvasBatch(batch: CanvasApplyBatch): Promise<CanvasApplyResult> {
  const data = await postJson<unknown>("/api/canvas/apply", batch)
  return normalizeCanvasApplyResult(data)
}

export async function restoreCanvasRevision(request: CanvasRestoreRequest): Promise<CanvasRestoreResult> {
  const data = await postJson<unknown>("/api/canvas/restore", {
    revision: request.revision,
    base_revision: request.baseRevision,
    authored_by: request.authoredBy,
  })
  return normalizeCanvasRestoreResult(data)
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

function pendingPath(id: string, since?: string): string {
  const path = `/api/pending/${encodeURIComponent(id)}`
  if (!since) return path
  return `${path}?since=${encodeURIComponent(since)}`
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
  return normalizeCanvasResponse(data)
}

export function normalizeCanvasResponse(data: unknown): CanvasResponse {
  const root = recordValue(data)
  const canvasV2 = normalizeCanvasV2Document(root?.canvas_v2 || root?.canvasV2)
  const revision = numberValue(root?.revision) ?? canvasV2?.revision
  return {
    model: normalizeCanvasPayload(data),
    mapping: normalizeCanvasMapping(recordValue(root?.mapping)),
    revision,
    canvasV2,
  }
}

export function normalizeMapHealth(value: unknown): MapHealth {
  const health = recordValue(value)
  const freshness = recordValue(health?.freshness)
  return {
    schema: "agentcanvas.map_health.v1",
    workspacePath: stringValue(health?.workspacePath) || stringValue(health?.workspace_path) || "",
    stateDir: normalizeMapHealthFile(health?.stateDir || health?.state_dir),
    workflowIr: normalizeMapHealthFile(health?.workflowIr || health?.workflow_ir),
    canvasIr: normalizeMapHealthFile(health?.canvasIr || health?.canvas_ir),
    freshness: {
      status: normalizeMapFreshnessStatus(freshness?.status),
      stale: booleanOrNull(freshness?.stale),
      reason: stringValue(freshness?.reason) || null,
    },
    pendingFiles: {
      ...normalizeMapHealthFile(health?.pendingFiles || health?.pending_files),
      fileCount: numberValue(recordValue(health?.pendingFiles || health?.pending_files)?.fileCount) ??
        numberValue(recordValue(health?.pendingFiles || health?.pending_files)?.file_count) ??
        0,
      changeCount: numberValue(recordValue(health?.pendingFiles || health?.pending_files)?.changeCount) ??
        numberValue(recordValue(health?.pendingFiles || health?.pending_files)?.change_count) ??
        0,
    },
    status: normalizeMapHealthStatus(health?.status),
    ready: booleanValue(health?.ready),
    summary: stringList(health?.summary),
  }
}

export function normalizeCanvasHistory(value: unknown): CanvasHistoryResponse {
  const history = recordValue(value)
  return {
    ok: booleanValue(history?.ok),
    currentRevision: numberValue(history?.current_revision) ?? numberValue(history?.currentRevision) ?? 0,
    current: normalizeCanvasHistoryEntry(history?.current),
    history: Array.isArray(history?.history)
      ? history.history.map(normalizeCanvasHistoryEntry).filter((entry): entry is CanvasHistoryEntry => Boolean(entry))
      : [],
  }
}

export function normalizeCanvasApplyResult(value: unknown): CanvasApplyResult {
  const result = recordValue(value)
  return {
    ok: booleanValue(result?.ok),
    autoMigrated: booleanValue(result?.auto_migrated) || booleanValue(result?.autoMigrated),
    dryRun: booleanValue(result?.dry_run) || booleanValue(result?.dryRun),
    revision: numberValue(result?.revision) ?? 0,
    baseRevision: numberValue(result?.base_revision) ?? numberValue(result?.baseRevision) ?? 0,
    path: stringValue(result?.path),
  }
}

export function normalizeCanvasRestoreResult(value: unknown): CanvasRestoreResult {
  const result = recordValue(value)
  return {
    ok: booleanValue(result?.ok),
    revision: numberValue(result?.revision) ?? 0,
    baseRevision: numberValue(result?.base_revision) ?? numberValue(result?.baseRevision) ?? 0,
    restoredRevision: numberValue(result?.restored_revision) ?? numberValue(result?.restoredRevision) ?? 0,
    path: stringValue(result?.path),
  }
}

export function isApiNotFound(error: unknown): boolean {
  return error instanceof ApiError && error.status === 404
}

export function isApiAuthExpired(error: unknown): boolean {
  return error instanceof ApiError && (error.status === 401 || error.status === 403)
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
  kind: ChangeKind
  title: string
  summary: string // the plain-language instruction, in the user's words
  journey?: string
  journeyId?: string
  journeyTitle?: string
  afterStep?: string | null
  targetStep?: string | null
  targetNodeId?: string | null
  targetNativeNodeId?: string | null
  targetNativeKind?: string | null
  targetFlowId?: string | null
  action?: FlowAction
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
    conversationSummary: normalizePendingConversationSummary(it.conversation_summary || it.conversationSummary),
    conversation: normalizePendingConversation(it.conversation),
  }
}

function normalizePendingConversation(value: unknown): PendingConversationTurn[] | undefined {
  if (!Array.isArray(value)) return undefined
  const turns = value.map(normalizePendingConversationTurn).filter((turn): turn is PendingConversationTurn => Boolean(turn))
  return turns.length ? turns : undefined
}

function normalizePendingConversationTurn(value: unknown): PendingConversationTurn | null {
  const turn = recordValue(value)
  if (!turn) return null
  const id = stringValue(turn.id)
  const text = stringValue(turn.text)
  if (!id || !text) return null
  return {
    id,
    at: stringValue(turn.at),
    role: normalizeConversationRole(turn.role),
    kind: normalizeConversationTurnKind(turn.kind),
    text,
  }
}

function normalizePendingConversationSummary(value: unknown): PendingConversationSummary | undefined {
  const summary = recordValue(value)
  if (!summary) return undefined
  const unanswered = recordValue(summary.unanswered_question || summary.unansweredQuestion)
  return {
    turns: numberValue(summary.turns) ?? 0,
    lastRole: normalizeOptionalConversationRole(summary.last_role || summary.lastRole),
    lastKind: normalizeOptionalConversationTurnKind(summary.last_kind || summary.lastKind),
    lastAt: stringValue(summary.last_at) || stringValue(summary.lastAt),
    unansweredQuestion: unanswered
      ? {
          id: stringValue(unanswered.id),
          text: stringValue(unanswered.text),
          at: stringValue(unanswered.at),
        }
      : undefined,
  }
}

export function normalizeCanvasPayload(data: unknown): AppModel {
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
    status: normalizeCanvasSourceStatus(value.status),
    mode: normalizeCanvasMappingMode(value.mode),
    primaryMode: normalizeCanvasMappingMode(value.primaryMode || value.primary_mode),
    fallbackMode: normalizeCanvasMappingMode(value.fallbackMode || value.fallback_mode),
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
    cacheStatus: normalizeCanvasSourceStatus(value.cacheStatus || value.cache_status),
    source: normalizeCanvasSource(value.source) || sourceFromLegacyFields(value),
    warnings: Array.isArray(value.warnings) ? value.warnings.map((item) => String(item)).filter(Boolean) : undefined,
    stages: Array.isArray(value.stages)
      ? value.stages.map(normalizeMappingStage).filter((stage): stage is MappingStage => Boolean(stage))
      : undefined,
  }
}

export function normalizeCanvasV2Document(value: unknown): CanvasV2Document | undefined {
  const document = recordValue(value)
  if (!document || document.schema !== CanvasV2Schema.Canvas) return undefined
  const app = recordValue(document.app)
  return {
    schema: CanvasV2Schema.Canvas,
    revision: numberValue(document.revision) ?? 0,
    authoredBy: stringValue(document.authored_by) || stringValue(document.authoredBy),
    updatedAt: stringValue(document.updated_at) || stringValue(document.updatedAt) || null,
    evidence: recordValue(document.evidence),
    app: {
      name: stringValue(app?.name) || "Your app",
      summary: stringValue(app?.summary) || "",
      isDemo: booleanValue(app?.is_demo) || booleanValue(app?.isDemo),
    },
    flows: Array.isArray(document.flows)
      ? document.flows.map(normalizeCanvasV2Flow).filter((flow): flow is CanvasV2Flow => Boolean(flow))
      : [],
    metadata: recordValue(document.metadata),
  }
}

function normalizeCanvasV2Flow(value: unknown): CanvasV2Flow | null {
  const flow = recordValue(value)
  const id = stringValue(flow?.id)
  if (!flow || !id) return null
  const title = stringValue(flow.title) || id
  return {
    id,
    title,
    summary: stringValue(flow.summary) || "",
    entryNode: stringValue(flow.entry_node) || stringValue(flow.entryNode),
    altitude: stringValue(flow.altitude),
    nodes: Array.isArray(flow.nodes)
      ? flow.nodes.map(normalizeCanvasV2Node).filter((node): node is CanvasV2Node => Boolean(node))
      : [],
    edges: Array.isArray(flow.edges)
      ? flow.edges.map(normalizeCanvasV2Edge).filter((edge): edge is CanvasV2Edge => Boolean(edge))
      : [],
    evidenceRefs: stringList(flow.evidence_refs || flow.evidenceRefs),
    metadata: recordValue(flow.metadata),
  }
}

function normalizeCanvasV2Node(value: unknown): CanvasV2Node | null {
  const node = recordValue(value)
  const id = stringValue(node?.id)
  if (!node || !id) return null
  return {
    id,
    kind: normalizeCanvasV2NodeKind(node.kind),
    title: stringValue(node.title) || stringValue(node.label) || id,
    summary: stringValue(node.summary),
    evidenceRefs: stringList(node.evidence_refs || node.evidenceRefs),
    flowRef: stringValue(node.flow_ref) || stringValue(node.flowRef),
    metadata: recordValue(node.metadata),
  }
}

function normalizeCanvasV2Edge(value: unknown): CanvasV2Edge | null {
  const edge = recordValue(value)
  const id = stringValue(edge?.id)
  const source = stringValue(edge?.source)
  const target = stringValue(edge?.target)
  if (!edge || !id || !source || !target) return null
  return {
    id,
    kind: normalizeCanvasV2EdgeKind(edge.kind),
    source,
    target,
    label: stringValue(edge.label),
    isDefault: booleanValue(edge.is_default) || booleanValue(edge.isDefault),
    metadata: recordValue(edge.metadata),
  }
}

function normalizeMapHealthFile(value: unknown): MapHealthFileRef {
  const file = recordValue(value)
  return {
    path: stringValue(file?.path) || "",
    relativePath: stringValue(file?.relativePath) || stringValue(file?.relative_path) || "",
    exists: booleanValue(file?.exists),
    readable: optionalBoolean(file?.readable),
    reason: normalizeOptionalMapHealthReason(file?.reason),
    error: stringValue(file?.error),
  }
}

function normalizeCanvasHistoryEntry(value: unknown): CanvasHistoryEntry | undefined {
  const entry = recordValue(value)
  const revision = numberValue(entry?.revision)
  if (!entry || revision === undefined) return undefined
  return {
    revision,
    sha256: stringValue(entry.sha256),
    updatedAt: stringValue(entry.updated_at) || stringValue(entry.updatedAt) || null,
    authoredBy: stringValue(entry.authored_by) || stringValue(entry.authoredBy),
    path: stringValue(entry.path),
    sizeBytes: numberValue(entry.size_bytes) ?? numberValue(entry.sizeBytes),
    opSummary: recordValue(entry.op_summary) || recordValue(entry.opSummary),
    allowRewriteReason: stringValue(entry.allow_rewrite_reason) || stringValue(entry.allowRewriteReason) || null,
    document: normalizeCanvasV2Document(entry.document),
  }
}

const CANVAS_V2_NODE_KINDS = new Set<string>(Object.values(CanvasV2NodeKind))
const CANVAS_V2_EDGE_KINDS = new Set<string>(Object.values(CanvasV2EdgeKind))

function normalizeCanvasV2NodeKind(value: unknown): CanvasV2NodeKind {
  const kind = String(value || CanvasV2NodeKind.Do)
  return CANVAS_V2_NODE_KINDS.has(kind) ? (kind as CanvasV2NodeKind) : CanvasV2NodeKind.Do
}

function normalizeCanvasV2EdgeKind(value: unknown): CanvasV2EdgeKind {
  const kind = String(value || CanvasV2EdgeKind.Normal)
  return CANVAS_V2_EDGE_KINDS.has(kind) ? (kind as CanvasV2EdgeKind) : CanvasV2EdgeKind.Normal
}

const CANVAS_MAPPING_MODES = new Set<string>(Object.values(CanvasMappingMode))
const CANVAS_SOURCE_KINDS = new Set<string>(Object.values(CanvasSourceKind))
const CANVAS_SOURCE_STATUSES = new Set<string>(Object.values(CanvasSourceStatus))
const CANVAS_SOURCE_REASONS = new Set<string>(Object.values(CanvasSourceReason))
const MAP_FRESHNESS_STATUSES = new Set<string>(Object.values(MapFreshnessStatus))
const MAP_HEALTH_STATUSES = new Set<string>(Object.values(MapHealthStatus))
const MAP_HEALTH_REASONS = new Set<string>(Object.values(MapHealthReason))
const CONVERSATION_ROLES = new Set<string>(Object.values(ConversationRole))
const CONVERSATION_TURN_KINDS = new Set<string>(Object.values(ConversationTurnKind))

function normalizeCanvasMappingMode(value: unknown): CanvasMappingMode | undefined {
  const mode = stringValue(value)
  return mode && CANVAS_MAPPING_MODES.has(mode) ? (mode as CanvasMappingMode) : undefined
}

function normalizeCanvasSourceKind(value: unknown): CanvasSourceKind | undefined {
  const kind = stringValue(value)
  return kind && CANVAS_SOURCE_KINDS.has(kind) ? (kind as CanvasSourceKind) : undefined
}

function normalizeCanvasSourceStatus(value: unknown): CanvasSourceStatus | undefined {
  const status = stringValue(value)
  return status && CANVAS_SOURCE_STATUSES.has(status) ? (status as CanvasSourceStatus) : undefined
}

function normalizeCanvasSourceReason(value: unknown): CanvasSourceReason | undefined {
  const reason = stringValue(value)
  return reason && CANVAS_SOURCE_REASONS.has(reason) ? (reason as CanvasSourceReason) : undefined
}

function normalizeMapFreshnessStatus(value: unknown): MapFreshnessStatus {
  const status = stringValue(value)
  return status && MAP_FRESHNESS_STATUSES.has(status) ? (status as MapFreshnessStatus) : MapFreshnessStatus.Unknown
}

function normalizeMapHealthStatus(value: unknown): MapHealthStatus {
  const status = stringValue(value)
  return status && MAP_HEALTH_STATUSES.has(status) ? (status as MapHealthStatus) : MapHealthStatus.Ready
}

function normalizeOptionalMapHealthReason(value: unknown): MapHealthReason | undefined {
  const reason = stringValue(value)
  return reason && MAP_HEALTH_REASONS.has(reason) ? (reason as MapHealthReason) : undefined
}

function normalizeConversationRole(value: unknown): ConversationRole {
  return normalizeOptionalConversationRole(value) || ConversationRole.Agent
}

function normalizeOptionalConversationRole(value: unknown): ConversationRole | undefined {
  const role = stringValue(value)
  return role && CONVERSATION_ROLES.has(role) ? (role as ConversationRole) : undefined
}

function normalizeConversationTurnKind(value: unknown): ConversationTurnKind {
  return normalizeOptionalConversationTurnKind(value) || ConversationTurnKind.Note
}

function normalizeOptionalConversationTurnKind(value: unknown): ConversationTurnKind | undefined {
  const kind = stringValue(value)
  return kind && CONVERSATION_TURN_KINDS.has(kind) ? (kind as ConversationTurnKind) : undefined
}

function normalizeCanvasSource(value: unknown): CanvasSourceMetadata | undefined {
  const source = recordValue(value)
  if (!source) return undefined
  return {
    kind: normalizeCanvasSourceKind(source.kind),
    status: normalizeCanvasSourceStatus(source.status),
    label: stringValue(source.label),
    reason: normalizeCanvasSourceReason(source.reason),
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
    status: normalizeMappingStageStatus(status),
    detail: stringValue(stage.detail),
  }
}

const MAPPING_STAGE_STATUSES = new Set<string>(Object.values(MappingStageStatus))

function normalizeMappingStageStatus(status: string | undefined): MappingStageStatus {
  return status && MAPPING_STAGE_STATUSES.has(status)
    ? (status as MappingStageStatus)
    : MappingStageStatus.Pending
}

function unwrapCanvasPayload(data: unknown): Record<string, unknown> {
  const root = recordValue(data)
  if (!root) throw new Error("Canvas response was empty.")
  const displayCanvas = recordValue(root.canvas)
  if (displayCanvas) return displayCanvas
  return (
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
  const firstWhen = nodes.find((node): node is StepNode => node.kind === FlowNodeKind.Step && node.role === StepRole.When)
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
  const firstWhen = nodes.find((node): node is StepNode => node.kind === FlowNodeKind.Step && node.role === StepRole.When)
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

    if (kind === CanvasStepKind.If) {
      const chain = [step]
      while (index + 1 < steps.length) {
        const next = steps[index + 1]
        const nextKind = canvasStepKind(next?.kind)
        if (nextKind !== CanvasStepKind.ElseIf && nextKind !== CanvasStepKind.Else) break
        chain.push(next)
        index += 1
        if (nextKind === CanvasStepKind.Else) break
      }
      nodes.push(branchFromCanvasChain(chain))
      continue
    }

    if (kind === CanvasStepKind.ElseIf || kind === CanvasStepKind.Else) {
      continue
    }

    nodes.push(stepFromCanvas(step, kind === CanvasStepKind.When ? StepRole.When : StepRole.Do))
  }

  return nodes
}

function branchFromCanvasChain(chain: Array<Record<string, unknown> | undefined>): BranchNode {
  const [head, ...rest] = chain
  const next = rest[0]
  const nextKind = canvasStepKind(next?.kind)
  const refs = refsFromCanvasStep(head)

  return {
    kind: FlowNodeKind.Branch,
    id: stepId(head, FlowNodeKind.Branch),
    condition: conditionText(head),
    then: canvasStepsToFlow(head?.steps),
    otherwise:
      nextKind === CanvasStepKind.ElseIf
        ? [branchFromCanvasChain(rest)]
        : nextKind === CanvasStepKind.Else
          ? canvasStepsToFlow(next?.steps)
          : [],
    uncertain: isUncertain(head),
    tech: refs.length ? { refs } : undefined,
    native: normalizeNativeRef(head?.native),
  }
}

function stepFromCanvas(step: Record<string, unknown> | undefined, role: StepRole): StepNode {
  const refs = refsFromCanvasStep(step)
  return {
    kind: FlowNodeKind.Step,
    id: stepId(step, role),
    role,
    text: stringValue(step?.text) || stringValue(step?.label) || (role === StepRole.When ? "Someone uses this flow" : "Do the mapped step"),
    uncertain: isUncertain(step),
    tech: refs.length ? { refs } : undefined,
    native: normalizeNativeRef(step?.native),
  }
}

function normalizeFlowNode(value: unknown): FlowNode | null {
  const node = recordValue(value)
  if (!node) return null
  if (node.kind === FlowNodeKind.Branch) {
    const thenNodes = (Array.isArray(node.then) ? node.then : [])
      .map(normalizeFlowNode)
      .filter((child): child is FlowNode => Boolean(child))
    const otherwiseNodes = (Array.isArray(node.otherwise) ? node.otherwise : [])
      .map(normalizeFlowNode)
      .filter((child): child is FlowNode => Boolean(child))
    return {
      kind: FlowNodeKind.Branch,
      id: stringValue(node.id) || slug(stringValue(node.condition) || FlowNodeKind.Branch, FlowNodeKind.Branch),
      condition: stringValue(node.condition) || "mapped condition",
      then: thenNodes,
      otherwise: otherwiseNodes,
      uncertain: Boolean(node.uncertain),
      tech: normalizeTech(node.tech),
      native: normalizeNativeRef(node.native),
    }
  }
  if (node.kind === FlowNodeKind.Step) {
    const role = node.role === StepRole.When ? StepRole.When : StepRole.Do
    return {
      kind: FlowNodeKind.Step,
      id: stringValue(node.id) || slug(stringValue(node.text) || role, role),
      role,
      text: stringValue(node.text) || "Mapped step",
      detail: stringValue(node.detail),
      uncertain: Boolean(node.uncertain),
      tech: normalizeTech(node.tech),
      native: normalizeNativeRef(node.native),
    }
  }
  return null
}

function normalizeNativeRef(value: unknown): CanvasV2NativeRef | undefined {
  const native = recordValue(value)
  if (!native || native.schema !== CanvasV2Schema.Canvas) return undefined
  const nodeId = stringValue(native.nodeId) || stringValue(native.node_id)
  if (!nodeId) return undefined
  const edgeKinds = stringList(native.edgeKinds || native.edge_kinds)
    .map(normalizeCanvasV2EdgeKind)
    .filter(Boolean)
  return {
    schema: CanvasV2Schema.Canvas,
    flowId: stringValue(native.flowId) || stringValue(native.flow_id),
    nodeId,
    nodeKind: normalizeCanvasV2NodeKind(native.nodeKind || native.node_kind),
    edgeKinds: edgeKinds.length ? edgeKinds : undefined,
    flowRef: stringValue(native.flowRef) || stringValue(native.flow_ref),
  }
}

function normalizeTech(value: unknown): { nodeId?: string; refs: string[] } | undefined {
  const tech = recordValue(value)
  if (!tech) return undefined
  const refs = Array.isArray(tech.refs) ? tech.refs.map((item) => String(item)).filter(Boolean) : []
  if (!refs.length) return undefined
  return { nodeId: stringValue(tech.nodeId), refs }
}

function canvasStepKind(value: unknown): CanvasStepKind {
  const normalized = String(value || "Do").replace(/[_-]+/g, "").toLowerCase()
  if (normalized === "when") return CanvasStepKind.When
  if (normalized === "if") return CanvasStepKind.If
  if (normalized === "elseif" || normalized === "elif") return CanvasStepKind.ElseIf
  if (normalized === "else") return CanvasStepKind.Else
  return CanvasStepKind.Do
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

const PENDING_STATUSES = new Set<string>(Object.values(PendingStatus))

function normalizePendingStatus(status: unknown): PendingStatus {
  const value = String(status || PendingStatus.Pending)
  if (PENDING_STATUSES.has(value)) return value as PendingStatus
  return value === LegacyPendingStatus.Queued ? PendingStatus.Pending : PendingStatus.Rejected
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

function numberValue(value: unknown): number | undefined {
  if (typeof value === "number" && Number.isFinite(value)) return value
  if (typeof value === "string" && value.trim() && Number.isFinite(Number(value))) {
    return Number(value)
  }
  return undefined
}

function stringList(value: unknown): string[] {
  return Array.isArray(value) ? value.map((item) => String(item)).filter(Boolean) : []
}

function booleanValue(value: unknown): boolean {
  return value === true || value === "true" || value === "1"
}

function optionalBoolean(value: unknown): boolean | undefined {
  if (value === true || value === "true" || value === "1") return true
  if (value === false || value === "false" || value === "0") return false
  return undefined
}

function booleanOrNull(value: unknown): boolean | null {
  return optionalBoolean(value) ?? null
}

function stringLooksStale(value: unknown): boolean {
  return typeof value === "string" && /stale|out[-_\s]?of[-_\s]?date|expired/i.test(value)
}
