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

export async function fetchAppContext(): Promise<AppContext> {
  try {
    const token = new URLSearchParams(window.location.search).get("token")
    const sessionId =
      new URLSearchParams(window.location.search).get("sessionId") ||
      new URLSearchParams(window.location.search).get("session_id")
    const demo = new URLSearchParams(window.location.search).get("demo")
    const u = new URL("/api/context", window.location.origin)
    if (token) u.searchParams.set("token", token)
    if (sessionId) u.searchParams.set("sessionId", sessionId)
    if (demo) u.searchParams.set("demo", demo)
    const res = await fetch(u.toString())
    if (!res.ok) throw new Error(`${res.status}`)
    const data = (await res.json()) as { ok: boolean; context: AppContext }
    return data.context
  } catch {
    return DEMO_CONTEXT
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
