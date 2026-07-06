import { useState, useEffect } from "react"
import type { WorkspaceProgressStatus } from "@/lib/types"

export enum AppContextMode {
  Landing = "landing",
  Workspace = "workspace",
  Demo = "demo",
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
  assistant: "Claude Code",
  assistantId: "claude-code",
  mode: AppContextMode.Demo,
  isDemo: true,
  isDemoContent: true,
  demoFallback: false,
  sessionId: null,
}

export async function fetchAppContext(): Promise<AppContext> {
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
      return { ...data.context, mode: AppContextMode.Demo, isDemo: true, isDemoContent: true, demoFallback: false }
    }
    return data.context
  } catch {
    // No API (e.g. static host) — honour ?demo=1 client-side, else show landing.
    return demo ? DEMO_FALLBACK : DEMO_CONTEXT
  }
}

export function useAppContext(): { context: AppContext; loading: boolean } {
  const [context, setContext] = useState<AppContext>(DEMO_CONTEXT)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetchAppContext().then((ctx) => {
      setContext(ctx)
      setLoading(false)
    })
  }, [])

  return { context, loading }
}
