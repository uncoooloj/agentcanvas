import type { CodeGraph, PendingItem, PendingStatus, PendingStatusHistoryEntry } from "./types"

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
    const detail = error ? `: ${String(error)}` : ""
    throw new Error(`${res.status}${detail}`)
  }
  return data as T
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
  if (!res.ok) throw new Error(`${res.status}`)
  const data = (await res.json()) as { graph: CodeGraph }
  return data.graph
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
