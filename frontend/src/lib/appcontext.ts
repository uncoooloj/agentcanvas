import { useCallback, useEffect, useState } from "react"
import type { WorkspaceProgressStatus } from "@/lib/types"

export enum AppContextMode {
  Landing = "landing",
  Workspace = "workspace",
  Demo = "demo",
}

export enum RuntimeConnectionState {
  Ready = "ready",
  Disconnected = "disconnected",
}

export type AppContext = {
  workspace: string
  workspacePath: string
  workspaceKind?: string
  workspaceProfile?: WorkspaceProfile
  productLanguage?: ProductLanguage
  assistant: string
  assistantId: string
  mode?: AppContextMode
  isDemo?: boolean
  isDemoContent?: boolean
  demoFallback?: boolean
  demoFixture?: string | null
  source?: RuntimeSource
  agentPresence?: AgentPresence
  sessionId?: string | null
  progress?: WorkspaceProgressStatus
}

export type ProductLanguage = {
  singular?: string
  plural?: string
  workspace_noun?: string
  entry_noun?: string
}

export type WorkspaceProfile = {
  kind?: string
  label?: string
  product_language?: ProductLanguage
}

export type RuntimeSource = {
  kind?: string
  status?: string
  demoContent?: boolean
  demoFallback?: boolean
  demoFixture?: string | null
  reason?: string | null
}

export type AgentPresence = {
  connected: boolean
  agent?: string
  agentName?: string
  sessionId?: string | null
  updatedAt?: string
}

export type AppContextLoadResult = {
  context: AppContext
  connection: RuntimeConnectionState
  error?: string
}

const DEMO_CONTEXT: AppContext = {
  workspace: "Your project",
  workspacePath: "",
  productLanguage: { singular: "project", workspace_noun: "project", entry_noun: "flow" },
  assistant: "Your assistant",
  assistantId: "generic",
  mode: AppContextMode.Landing,
  isDemo: false,
  isDemoContent: false,
  demoFallback: false,
  sessionId: null,
}

const DEMO_FALLBACK: AppContext = {
  workspace: "Your online shop",
  workspacePath: "",
  productLanguage: { singular: "app", workspace_noun: "app", entry_noun: "flow" },
  assistant: "No agent connected",
  assistantId: "generic",
  mode: AppContextMode.Demo,
  isDemo: true,
  isDemoContent: true,
  demoFallback: false,
  sessionId: null,
}

export function hasRuntimeLaunchContext(search = window.location.search): boolean {
  const params = new URLSearchParams(search)
  return Boolean(params.get("token") || params.get("sessionId") || params.get("session_id"))
}

export async function fetchAppContext(): Promise<AppContextLoadResult> {
  const params = new URLSearchParams(window.location.search)
  const demo = params.get("demo")
  try {
    const token = params.get("token")
    const sessionId = params.get("sessionId") || params.get("session_id")
    const u = new URL("/api/context", window.location.origin)
    if (token) u.searchParams.set("token", token)
    if (sessionId) u.searchParams.set("sessionId", sessionId)
    if (demo) u.searchParams.set("demo", demo)
    const res = await fetch(u.toString())
    if (!res.ok) throw new Error(`${res.status}`)
    const data = (await res.json()) as { ok: boolean; context: AppContext }
    // ?demo=1 always enters demo mode, even if the server didn't say so.
    if (demo && data.context.mode !== AppContextMode.Demo) {
      return {
        context: { ...data.context, mode: AppContextMode.Demo, isDemo: true, isDemoContent: true, demoFallback: false },
        connection: RuntimeConnectionState.Ready,
      }
    }
    return { context: data.context, connection: RuntimeConnectionState.Ready }
  } catch {
    // A launched workspace must never silently become the marketing site when its
    // local server has stopped or its link has expired.
    if (hasRuntimeLaunchContext()) {
      return {
        context: DEMO_CONTEXT,
        connection: RuntimeConnectionState.Disconnected,
        error: "We could not reach the AgentCanvas session behind this link.",
      }
    }
    // No API (for example a static host) can still show demo mode or the public landing page.
    return { context: demo ? DEMO_FALLBACK : DEMO_CONTEXT, connection: RuntimeConnectionState.Ready }
  }
}

export function useAppContext(): {
  context: AppContext
  loading: boolean
  connection: RuntimeConnectionState
  error?: string
  retry: () => void
} {
  const [context, setContext] = useState<AppContext>(DEMO_CONTEXT)
  const [loading, setLoading] = useState(true)
  const [connection, setConnection] = useState(RuntimeConnectionState.Ready)
  const [error, setError] = useState<string | undefined>()
  const [attempt, setAttempt] = useState(0)
  const retry = useCallback(() => setAttempt((current) => current + 1), [])

  useEffect(() => {
    setLoading(true)
    fetchAppContext().then((result) => {
      setContext(result.context)
      setConnection(result.connection)
      setError(result.error)
      setLoading(false)
    })
  }, [attempt])

  return { context, loading, connection, error, retry }
}
