import { useState, useEffect } from "react"

export type AppContext = {
  workspace: string
  workspacePath: string
  assistant: string
  assistantId: string
  mode?: "landing" | "workspace" | "demo"
  isDemo?: boolean
  demoFixture?: string | null
  sessionId?: string | null
}

const DEMO_CONTEXT: AppContext = {
  workspace: "Your app",
  workspacePath: "",
  assistant: "Your assistant",
  assistantId: "generic",
  mode: "landing",
  isDemo: false,
  sessionId: null,
}

const DEMO_FALLBACK: AppContext = {
  workspace: "Your online shop",
  workspacePath: "",
  assistant: "Claude Code",
  assistantId: "claude-code",
  mode: "demo",
  isDemo: true,
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
    if (demo && data.context.mode !== "demo") {
      return { ...data.context, mode: "demo", isDemo: true }
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
