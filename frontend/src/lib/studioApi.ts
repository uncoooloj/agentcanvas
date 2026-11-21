import type {
  AnnotationInput,
  FileDiff,
  FileSlice,
  RunInput,
  StudioAnnotation,
  StudioBootstrapResponse,
  StudioDocument,
  StudioEvent,
  StudioRun,
} from "./studioTypes"
import { demoBootstrap, demoFileDiff, demoFileSlice } from "./studioDemo"

export type StudioBootstrapOptions = { diffBase?: string | null; demo?: boolean; token?: string | null }
export type StudioApiOptions = { baseUrl?: string; token?: string | null }
export type StudioEventSubscription = { close: () => void }
export type StudioEventHandlers = {
  onEvent: (event: StudioEvent) => void
  onOpen?: () => void
  onError?: () => void
  onCanvasUpdated?: () => void
}

export class StudioApiError extends Error {
  readonly status: number
  readonly path: string
  readonly kind: "auth" | "unreachable" | "request"

  constructor(path: string, status: number, message: string, kind: StudioApiError["kind"] = "request") {
    super(message)
    this.name = "StudioApiError"
    this.path = path
    this.status = status
    this.kind = kind
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

function isDemo(options?: Pick<StudioBootstrapOptions, "demo">) {
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
    active_run: wire.active_run ?? null,
    recent_runs: wire.recent_runs ?? [],
  }
}

function isStudioDocument(value: unknown): value is StudioDocument {
  if (!value || typeof value !== "object") return false
  const document = value as Partial<StudioDocument>
  return document.schema === "agentcanvas.studio.v3" && Array.isArray(document.components)
    && Array.isArray(document.component_edges) && Array.isArray(document.flows)
}

function parseStudioEvent(type: StudioEvent["type"], value: unknown): StudioEvent | null {
  if (!value || typeof value !== "object") return null
  const payload = value as Record<string, unknown>
  if (type === "studio.updated") {
    const { document, has_mapped_canvas, stale_node_ids } = payload
    if (!isStudioDocument(document) || typeof has_mapped_canvas !== "boolean" || !Array.isArray(stale_node_ids)) return null
    return { type, payload: { document, has_mapped_canvas, stale_node_ids: stale_node_ids.filter((id): id is string => typeof id === "string") } }
  }
  if (type === "run.updated") {
    const run = payload.run as StudioRun | undefined
    return run && typeof run.id === "string" && typeof run.status === "string" ? { type, payload: { run } } : null
  }
  if (type === "run.log") {
    const entry = payload.entry ?? payload
    if (typeof payload.run_id !== "string" || !entry || typeof entry !== "object") return null
    const log = entry as Record<string, unknown>
    if (typeof log.message !== "string") return null
    return { type, payload: {
      run_id: payload.run_id,
      entry: {
        message: log.message,
        id: typeof log.id === "string" ? log.id : undefined,
        stage: typeof log.stage === "string" ? log.stage : undefined,
        tool: typeof log.tool === "string" ? log.tool : undefined,
        timestamp: typeof log.timestamp === "string" ? log.timestamp : undefined,
      },
    } }
  }
  if (Array.isArray(payload.annotations)) return { type, payload: { annotations: payload.annotations as StudioAnnotation[] } }
  const annotation = payload.annotation as StudioAnnotation | undefined
  if (annotation && typeof annotation.id === "string") return { type, payload: { annotation } }
  const deleted = typeof payload.deleted === "string" ? payload.deleted : payload.deleted === true && typeof payload.id === "string" ? payload.id : null
  return deleted ? { type, payload: { deleted } } : null
}

export class StudioApi {
  private readonly options: StudioApiOptions

  constructor(options: StudioApiOptions = {}) { this.options = options }

  private token(token?: string | null) {
    const stored = browserToken()
    return token ?? this.options.token ?? stored
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
      const payload = await response.json().catch(() => null) as { error?: unknown } | null
      if (!response.ok) {
        const message = typeof payload?.error === "string" ? payload.error : response.statusText
        const isStaticMiss = path === "/api/studio" && (response.status === 404 || response.status === 405)
        throw new StudioApiError(path, response.status, message || `Request failed (${response.status})`, response.status === 401 || response.status === 403 ? "auth" : isStaticMiss ? "unreachable" : "request")
      }
      if (!payload || typeof payload !== "object") throw new StudioApiError(path, 0, "AgentCanvas is unreachable. Start or reconnect the local session.", "unreachable")
      return payload as T
    } catch (error) {
      if (error instanceof StudioApiError) throw error
      throw new StudioApiError(path, 0, "AgentCanvas is unreachable. Start or reconnect the local session.", "unreachable")
    }
  }

  async bootstrap(options: StudioBootstrapOptions = {}) {
    if (isDemo(options)) return demoBootstrap()
    const data = await this.request<StudioBootstrapWire>("GET", "/api/studio", undefined, {
      diffBase: options.diffBase ?? undefined,
    }, options.token)
    if (!isStudioDocument(data.document)) {
      throw new StudioApiError("/api/studio", 0, "AgentCanvas is unreachable. Start or reconnect the local session.", "unreachable")
    }
    return normalizeStudioBootstrap(data)
  }

  fileSlice(path: string, line?: number, context = 12, signal?: AbortSignal) {
    if (isDemo()) return Promise.resolve(demoFileSlice(path, line, context))
    return this.request<FileSlice>("GET", "/api/file-slice", undefined, { path, line: line?.toString(), context: context.toString() }, undefined, signal)
  }

  fileDiff(path: string, base?: string | null, signal?: AbortSignal) {
    if (isDemo()) return Promise.resolve(demoFileDiff(path))
    return this.request<FileDiff>("GET", "/api/file-diff", undefined, { path, base: base ?? undefined }, undefined, signal)
  }

  createAnnotation(input: AnnotationInput) { return this.request<{ ok: true; annotation: StudioAnnotation }>("POST", "/api/annotations", input) }
  updateAnnotation(id: string, patch: Partial<AnnotationInput & Pick<StudioAnnotation, "resolved">>) { return this.request<{ ok: true; annotation: StudioAnnotation }>("PATCH", `/api/annotations/${encodeURIComponent(id)}`, patch) }
  deleteAnnotation(id: string) { return this.request<{ ok: true }>("DELETE", `/api/annotations/${encodeURIComponent(id)}`) }
  startRun(input: RunInput) { return this.request<{ ok: true; run: StudioRun }>("POST", "/api/runs", input, { diffBase: input.diff_base }) }
  answerRun(id: string, input: { answer?: string; approve?: boolean }) {
    return this.request<{ ok: true; run: StudioRun }>("POST", `/api/runs/${encodeURIComponent(id)}/answer`, input)
  }
  cancelRun(id: string) { return this.request<{ ok: true; run: StudioRun }>("POST", `/api/runs/${encodeURIComponent(id)}/cancel`) }
  discardRun(id: string) { return this.request<{ ok: true; run?: StudioRun }>("POST", `/api/runs/${encodeURIComponent(id)}/discard`) }

  eventUrl(options: StudioBootstrapOptions = {}) {
    return this.url("/api/events", { token: this.token(options.token) })
  }

  /** Native EventSource reconnects itself; callers should reconcile state in onOpen. */
  subscribeEvents(options: StudioBootstrapOptions, handlers: StudioEventHandlers, Source?: typeof EventSource): StudioEventSubscription {
    const EventSourceImpl = Source ?? (typeof EventSource === "undefined" ? undefined : EventSource)
    if (isDemo(options) || !EventSourceImpl) return { close() {} }
    const source = new EventSourceImpl(this.eventUrl(options))
    source.onopen = () => handlers.onOpen?.()
    source.onerror = () => handlers.onError?.()
    for (const type of ["studio.updated", "run.updated", "run.log", "annotations.updated"] as const) {
      source.addEventListener(type, (message) => {
        try {
          const payload: unknown = JSON.parse((message as MessageEvent<string>).data)
          const event = parseStudioEvent(type, payload)
          if (event) handlers.onEvent(event)
        } catch {
          // Ignore malformed frames; EventSource will reconnect and the caller can reconcile on open.
        }
      })
    }
    source.addEventListener("canvas.updated", () => handlers.onCanvasUpdated?.())
    return { close: () => source.close() }
  }
}

export const createStudioApi = (options?: StudioApiOptions) => new StudioApi(options)
export const studioApi = createStudioApi()
