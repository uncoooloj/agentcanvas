import type {
  AnnotationInput,
  FileDiff,
  FileSlice,
  RunInput,
  StudioAnnotation,
  StudioBootstrapResponse,
  StudioDocument,
  StudioEvent,
  RunLog,
  StudioRun,
  RunStatus,
  RunVerification,
  StudioComponent,
} from "./studioTypes"
import { demoBootstrap, demoFileDiff, demoFileSlice } from "./studioDemo"

export type StudioBootstrapOptions = { diffBase?: string | null; demo?: boolean; token?: string | null; sessionId?: string | null }
export type StudioApiOptions = { baseUrl?: string; token?: string | null }
export type StudioEventSubscription = { close: () => void }
export type StudioEventHandlers = {
  onEvent: (event: StudioEvent) => void
  onOpen?: () => void
  onError?: () => void
  onCanvasUpdated?: () => void
  /** Called before delivering a frame that leaves a gap in the server sequence. */
  onSequenceGap?: (expected: number, received: number) => void
}

export class StudioApiError extends Error {
  readonly status: number
  readonly path: string
  readonly kind: "auth" | "not_found" | "html" | "invalid_response" | "unreachable" | "request"

  constructor(path: string, status: number, message: string, kind: StudioApiError["kind"] = "request") {
    super(message)
    this.name = "StudioApiError"
    this.path = path
    this.status = status
    this.kind = kind
  }
}

type UnknownRecord = Record<string, unknown>
const runStatuses = new Set<RunStatus>(["queued", "running", "needs_input", "awaiting_approval", "copy_ready", "completed", "failed", "cancelled", "discarded"])
const runKinds = new Set<StudioRun["kind"]>(["map", "diff", "plan", "build"])
const runners = new Set<StudioRun["runner"]>(["codex", "claude", "copy"])
const componentKinds = new Set<StudioComponent["kind"]>(["web", "mobile", "service", "package", "worker", "db", "external"])

function isRecord(value: unknown): value is UnknownRecord {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value)
}

function stringValue(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() ? value : undefined
}

function stringList(value: unknown) {
  if (!Array.isArray(value)) return []
  return [...new Set(value.flatMap((item) => {
    const text = stringValue(item)
    return text ? [text] : []
  }))]
}

function normalizeLog(value: unknown): RunLog | null {
  if (!isRecord(value)) return null
  const canonical = "text" in value
  const text = stringValue(canonical ? value.text : value.message)
  const at = stringValue(canonical ? value.at : value.timestamp) ?? (canonical ? undefined : "")
  const kind = canonical ? stringValue(value.kind) : stringValue(value.stage) ?? "runner"
  if (!text || at === undefined || !kind) return null
  const id = stringValue(value.id)
  const tool = stringValue(value.tool)
  return { at, kind, text, ...(id ? { id } : {}), ...(tool ? { tool } : {}) }
}

export function uniqueRunLogs(logs: RunLog[]) {
  const ids = new Set<string>()
  const entries = new Set<string>()
  return logs.filter(({ id, at, kind, text }) => {
    const key = JSON.stringify([at, kind, text])
    const duplicate = (id && ids.has(id)) || entries.has(key)
    if (id) ids.add(id)
    entries.add(key)
    return !duplicate
  })
}

function normalizeVerification(value: unknown): RunVerification | null {
  if (!isRecord(value)) return null
  const tests = Array.isArray(value.tests) ? value.tests.flatMap((candidate) => {
    if (!isRecord(candidate)) return []
    const command = stringValue(candidate.command)
    const passed = typeof candidate.passed === "boolean" ? candidate.passed : undefined
    const output = stringValue(candidate.output)
    if (!command && passed === undefined && !output) return []
    return [{ ...(command ? { command } : {}), ...(passed === undefined ? {} : { passed }), ...(output ? { output } : {}) }]
  }) : []
  const summary = stringValue(value.summary)
  const output = stringValue(value.output)
  const command = stringValue(value.command)
  const passed = typeof value.passed === "boolean" ? value.passed : undefined
  const changed_files = stringList(value.changed_files)
  return {
    ...(summary ? { summary } : {}),
    ...(output ? { output } : {}),
    ...(command ? { command } : {}),
    ...(passed === undefined ? {} : { passed }),
    ...(Array.isArray(value.tests) ? { tests } : {}),
    ...(Array.isArray(value.changed_files) ? { changed_files } : {}),
  }
}

/** Converts permissive runner output into the single frontend run contract. */
function normalizeStudioRun(value: unknown): StudioRun | null {
  if (!isRecord(value)) return null
  const id = stringValue(value.id)
  const status = stringValue(value.status)
  const kind = value.kind as StudioRun["kind"]
  const runner = value.runner as StudioRun["runner"]
  if (!id || !runStatuses.has(status as RunStatus) || !runKinds.has(kind) || !runners.has(runner)) return null
  if (status === "awaiting_approval" && kind !== "plan") return null
  const logs = Array.isArray(value.logs) ? value.logs.flatMap((entry) => normalizeLog(entry) ?? []) : []
  return {
    id, kind, runner,
    status: status as RunStatus,
    prompt: stringValue(value.prompt),
    diff_base: stringValue(value.diff_base),
    flow_id: stringValue(value.flow_id),
    node_ids: stringList(value.node_ids),
    annotation_ids: stringList(value.annotation_ids),
    created_at: stringValue(value.created_at),
    updated_at: stringValue(value.updated_at),
    started_at: stringValue(value.started_at),
    finished_at: stringValue(value.finished_at),
    question: stringValue(value.question),
    plan_summary: stringValue(value.plan_summary),
    error: stringValue(value.error),
    proposed_document: isStudioDocument(value.proposed_document) ? value.proposed_document : null,
    logs: uniqueRunLogs(logs),
    changed_files: stringList(value.changed_files),
    verification: normalizeVerification(value.verification),
    verification_summary: stringValue(value.verification_summary),
  }
}

type StudioBootstrapWire = Partial<StudioBootstrapResponse> & {
  document: StudioBootstrapResponse["document"]
  annotations?: StudioAnnotation[]
  runners?: { preferred?: StudioRun["runner"]; available?: unknown[] }
  git?: Record<string, unknown>
  diff_base?: string | null
}

function browserToken() {
  if (typeof window === "undefined") return null
  const fromQuery = new URLSearchParams(window.location.search).get("token")
  if (fromQuery) {
    try { window.sessionStorage.setItem("agentcanvas-token", fromQuery) } catch { /* private browsing can deny storage */ }
    return fromQuery
  }
  try { return window.sessionStorage.getItem("agentcanvas-token") } catch { return null }
}

export function isDemoLaunch(options?: Pick<StudioBootstrapOptions, "demo">) {
  if (options?.demo) return true
  return typeof window !== "undefined" && new URLSearchParams(window.location.search).get("demo") === "1"
}

function normalizeStudioBootstrap(wire: StudioBootstrapWire): StudioBootstrapResponse {
  const git: Record<string, unknown> = wire.git ?? {}
  const runners = wire.runners
  return {
    ok: true,
    mode: wire.mode === "landing" || wire.mode === "workspace" || wire.mode === "demo" ? wire.mode : "workspace",
    workspace: typeof wire.workspace === "string" ? wire.workspace : String((wire.document as unknown as { workspace?: string }).workspace ?? ""),
    workspace_name: typeof wire.workspace_name === "string" ? wire.workspace_name : String((wire.document as unknown as { workspace_name?: string }).workspace_name ?? "Workspace"),
    git: {
      branch: typeof git.branch === "string" ? git.branch : null,
      head: typeof git.head === "string" ? git.head : null,
      dirty: Boolean(git.dirty),
      changed_files: Array.isArray(git.changed_files) ? git.changed_files.filter((value): value is string => typeof value === "string") : [],
      diff_base: wire.diff_base ?? (typeof git.diff_base === "string" ? git.diff_base : null),
    },
    runner: {
      preferred: runners?.preferred ?? wire.runner?.preferred ?? "copy",
      available: Array.isArray(runners?.available)
        ? runners.available.flatMap((value) => typeof value === "string" && (value === "codex" || value === "claude")
          ? [{ id: value, label: value === "codex" ? "Codex" : "Claude", binary: value }]
          : typeof value === "object" && value !== null && "id" in value ? [value as { id: "codex" | "claude"; label: string; binary: string; version?: string }] : [])
        : wire.runner?.available ?? [],
    },
    has_mapped_canvas: Boolean(wire.has_mapped_canvas),
    stale_node_ids: wire.stale_node_ids ?? [],
    document: wire.document,
    annotations: wire.annotations ?? [],
    active_run: normalizeStudioRun(wire.active_run),
    recent_runs: (Array.isArray(wire.recent_runs) ? wire.recent_runs : []).flatMap((run) => {
      const normalized = normalizeStudioRun(run)
      return normalized ? [normalized] : []
    }),
  }
}

function isStudioDocument(value: unknown): value is StudioDocument {
  if (!isRecord(value) || value.schema !== "agentcanvas.studio.v3") return false
  const strings = (items: unknown) => Array.isArray(items) && items.every((item) => typeof item === "string")
  const fields = (record: UnknownRecord, keys: string[]) => keys.every((key) => typeof record[key] === "string")
  const edges = (items: unknown) => Array.isArray(items) && items.every((edge) => isRecord(edge) && fields(edge, ["id", "source", "target"])
    && (edge.label == null || typeof edge.label === "string") && (edge.protocol == null || typeof edge.protocol === "string"))
  return Array.isArray(value.components) && value.components.every((component) => isRecord(component)
    && fields(component, ["id", "name", "path", "summary"]) && componentKinds.has(component.kind as StudioComponent["kind"])
    && strings(component.tech) && strings(component.entrypoints))
    && edges(value.component_edges) && Array.isArray(value.flows) && value.flows.every((flow) => isRecord(flow)
      && fields(flow, ["id", "title", "summary", "trigger"]) && strings(flow.component_ids) && edges(flow.edges)
      && (flow.diff_summary == null || typeof flow.diff_summary === "string")
      && Array.isArray(flow.nodes) && flow.nodes.every((node) => isRecord(node) && fields(node, ["id", "kind", "title", "status"])
        && [node.summary, node.diff_summary, node.test_ref].every((text) => text == null || typeof text === "string")
        && Array.isArray(node.code_refs) && node.code_refs.every((ref) => isRecord(ref) && typeof ref.path === "string")))
}

function eventSequence(value: UnknownRecord, fallback?: string) {
  if (Number.isSafeInteger(value.seq) && (value.seq as number) >= 0) return value.seq as number
  const parsed = fallback && /^\d+$/.test(fallback) ? Number(fallback) : undefined
  return Number.isSafeInteger(parsed) ? parsed : undefined
}

function parseStudioEvent(type: StudioEvent["type"], payload: unknown, seq?: number): StudioEvent | null {
  if (!isRecord(payload)) return null
  if (type === "studio.updated") {
    const { document, has_mapped_canvas, stale_node_ids } = payload
    if (!isStudioDocument(document) || typeof has_mapped_canvas !== "boolean" || !Array.isArray(stale_node_ids)) return null
    return { type, payload: { document, has_mapped_canvas, stale_node_ids: stale_node_ids.filter((id): id is string => typeof id === "string") }, ...(seq === undefined ? {} : { seq }) }
  }
  if (type === "run.updated") {
    const run = normalizeStudioRun(payload.run)
    return run ? { type, payload: { run }, ...(seq === undefined ? {} : { seq }) } : null
  }
  if (type === "run.log") {
    const entry = payload.entry ?? payload
    if (typeof payload.run_id !== "string" || !entry || typeof entry !== "object") return null
    const log = normalizeLog(entry)
    return log ? { type, payload: { run_id: payload.run_id, entry: log }, ...(seq === undefined ? {} : { seq }) } : null
  }
  if (type === "studio.resync") return { type, payload: { ...(stringValue(payload.reason) ? { reason: payload.reason as string } : {}) }, ...(seq === undefined ? {} : { seq }) }
  if (Array.isArray(payload.annotations)) return { type, payload: { annotations: payload.annotations as StudioAnnotation[] }, ...(seq === undefined ? {} : { seq }) }
  const annotation = payload.annotation as StudioAnnotation | undefined
  if (annotation && typeof annotation.id === "string") return { type, payload: { annotation }, ...(seq === undefined ? {} : { seq }) }
  const deleted = typeof payload.deleted === "string" ? payload.deleted : payload.deleted === true && typeof payload.id === "string" ? payload.id : null
  return deleted ? { type, payload: { deleted }, ...(seq === undefined ? {} : { seq }) } : null
}

export class StudioApi {
  private readonly options: StudioApiOptions

  constructor(options: StudioApiOptions = {}) { this.options = options }

  private token(token?: string | null) {
    const stored = browserToken()
    return token ?? this.options.token ?? stored
  }
  /** Identity used to retain a workspace across URL and session-storage navigation. */
  workspaceSessionKey(options: StudioBootstrapOptions = {}) {
    const token = this.token(options.token)
    if (token) return `token:${token}`
    return options.sessionId ? `session:${options.sessionId}` : null
  }
  private url(path: string, params: Record<string, string | null | undefined> = {}) {
    const base = this.options.baseUrl ?? (typeof window === "undefined" ? "http://localhost" : window.location.origin)
    const url = new URL(path, base)
    for (const [key, value] of Object.entries(params)) if (value != null) url.searchParams.set(key, value)
    return url.toString()
  }

  private async request<T>(method: string, path: string, body?: unknown, params?: Record<string, string | null | undefined>, token?: string | null, signal?: AbortSignal): Promise<T> {
    const accessToken = this.token(token)
    try {
      const response = await fetch(this.url(path, params), {
        method,
        headers: { "content-type": "application/json", ...(accessToken ? { "X-AgentCanvas-Token": accessToken } : {}) },
        ...(body === undefined ? {} : { body: JSON.stringify(body) }), signal,
      })
      const raw = await response.text()
      const contentType = response.headers.get("content-type") ?? ""
      let payload: { error?: unknown } | null = null
      try { payload = raw ? JSON.parse(raw) as { error?: unknown } : null } catch { /* classified below */ }
      if (!response.ok) {
        const message = typeof payload?.error === "string" ? payload.error : response.statusText
        const kind = response.status === 401 || response.status === 403 ? "auth"
          : response.status === 404 ? "not_found"
          : path === "/api/studio" && response.status === 405 ? "unreachable"
          : contentType.includes("text/html") ? "html"
          : "request"
        throw new StudioApiError(path, response.status, message || `Request failed (${response.status})`, kind)
      }
      if (!payload || typeof payload !== "object") {
        const kind = contentType.includes("text/html") || /^\s*</.test(raw) ? "html" : "invalid_response"
        throw new StudioApiError(path, response.status, "AgentCanvas returned an invalid API response.", kind)
      }
      return payload as T
    } catch (error) {
      if (error instanceof StudioApiError) throw error
      throw new StudioApiError(path, 0, "AgentCanvas is unreachable. Start or reconnect the local session.", "unreachable")
    }
  }

  async bootstrap(options: StudioBootstrapOptions = {}) {
    if (isDemoLaunch(options)) return demoBootstrap()
    const data = await this.request<StudioBootstrapWire>("GET", "/api/studio", undefined, {
      diffBase: options.diffBase ?? undefined,
      sessionId: options.sessionId,
    }, options.token)
    if (!isStudioDocument(data.document)) {
      throw new StudioApiError("/api/studio", 0, "AgentCanvas returned an invalid studio response.", "invalid_response")
    }
    return normalizeStudioBootstrap(data)
  }

  private normalizeRunResponse(value: unknown, path: string): { ok: true; run: StudioRun }
  private normalizeRunResponse(value: unknown, path: string, required: false): { ok: true; run?: StudioRun }
  private normalizeRunResponse(value: unknown, path: string, required = true): { ok: true; run?: StudioRun } {
    if (!isRecord(value)) throw new StudioApiError(path, 0, "AgentCanvas returned an invalid run response.", "invalid_response")
    const run = normalizeStudioRun(value.run)
    if (run) return { ok: true as const, run }
    if (!required) return { ok: true as const, run: undefined }
    throw new StudioApiError(path, 0, "AgentCanvas returned an invalid run response.", "invalid_response")
  }

  fileSlice(path: string, line?: number, context = 12, signal?: AbortSignal) {
    if (isDemoLaunch()) return Promise.resolve(demoFileSlice(path, line, context))
    return this.request<FileSlice>("GET", "/api/file-slice", undefined, { path, line: line?.toString(), context: context.toString() }, undefined, signal)
  }

  fileDiff(path: string, base?: string | null, signal?: AbortSignal) {
    if (isDemoLaunch()) return Promise.resolve(demoFileDiff(path))
    return this.request<FileDiff>("GET", "/api/file-diff", undefined, { path, base: base ?? undefined }, undefined, signal)
  }

  createAnnotation(input: AnnotationInput) { return this.request<{ ok: true; annotation: StudioAnnotation }>("POST", "/api/annotations", input) }
  updateAnnotation(id: string, patch: Partial<AnnotationInput & Pick<StudioAnnotation, "resolved">>) { return this.request<{ ok: true; annotation: StudioAnnotation }>("PATCH", `/api/annotations/${encodeURIComponent(id)}`, patch) }
  deleteAnnotation(id: string) { return this.request<{ ok: true }>("DELETE", `/api/annotations/${encodeURIComponent(id)}`) }
  async startRun(input: RunInput) {
    return this.normalizeRunResponse(await this.request<unknown>("POST", "/api/runs", input, { diffBase: input.diff_base }), "/api/runs")
  }
  async answerRun(id: string, input: { answer?: string; approve?: boolean }) {
    const path = `/api/runs/${encodeURIComponent(id)}/answer`
    return this.normalizeRunResponse(await this.request<unknown>("POST", path, input), path)
  }
  async cancelRun(id: string) {
    const path = `/api/runs/${encodeURIComponent(id)}/cancel`
    return this.normalizeRunResponse(await this.request<unknown>("POST", path), path)
  }
  async discardRun(id: string) {
    const path = `/api/runs/${encodeURIComponent(id)}/discard`
    return this.normalizeRunResponse(await this.request<unknown>("POST", path), path, false)
  }

  eventUrl(options: StudioBootstrapOptions = {}) {
    return this.url("/api/events", { token: this.token(options.token) })
  }

  /** Native EventSource reconnects itself; callers should reconcile state in onOpen. */
  subscribeEvents(options: StudioBootstrapOptions, handlers: StudioEventHandlers, Source?: typeof EventSource): StudioEventSubscription {
    const EventSourceImpl = Source ?? (typeof EventSource === "undefined" ? undefined : EventSource)
    if (isDemoLaunch(options) || !EventSourceImpl) return { close() {} }
    const source = new EventSourceImpl(this.eventUrl(options))
    let lastSequence: number | undefined
    source.onopen = () => {
      lastSequence = undefined
      handlers.onOpen?.()
    }
    source.onerror = () => handlers.onError?.()
    const observeSequence = (received: number | undefined, reconcile: boolean) => {
      if (received === undefined) return
      if (reconcile && lastSequence !== undefined && received > lastSequence + 1) handlers.onSequenceGap?.(lastSequence + 1, received)
      if (lastSequence === undefined || received > lastSequence) lastSequence = received
    }
    function readFrame(message: MessageEvent<string>) {
      let payload: unknown
      try { payload = JSON.parse(message.data) } catch { /* an invalid sequenced frame requires a snapshot */ }
      return { payload, seq: eventSequence(isRecord(payload) ? payload : {}, message.lastEventId) }
    }
    for (const type of ["studio.updated", "run.updated", "run.log", "studio.resync", "annotations.updated"] as const) {
      source.addEventListener(type, (message) => {
        const frame = readFrame(message as MessageEvent<string>)
        const event = parseStudioEvent(type, frame.payload, frame.seq)
        observeSequence(frame.seq, Boolean(event) && type !== "studio.resync")
        if (event) handlers.onEvent(event)
        else if (frame.seq !== undefined) handlers.onEvent({ type: "studio.resync", seq: frame.seq, payload: { reason: "invalid_frame" } })
      })
    }
    source.addEventListener("canvas.updated", (message) => {
      observeSequence(readFrame(message as MessageEvent<string>).seq, false)
      handlers.onCanvasUpdated?.()
    })
    return { close: () => source.close() }
  }
}

export const createStudioApi = (options?: StudioApiOptions) => new StudioApi(options)
export const studioApi = createStudioApi()
