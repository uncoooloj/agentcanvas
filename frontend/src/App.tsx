import { lazy, Suspense, useEffect } from "react"
import { useLocation, useMatch, useNavigate } from "react-router-dom"
import { LandingPage } from "@/components/LandingPage"
import { BrandMark } from "@/components/BrandMark"
import { studioStore, useStudioStore } from "@/lib/studioStore"
import { studioTabs, type StudioTab } from "@/lib/studioTypes"

const StudioShell = lazy(() => import("@/studio/StudioShell"))

function StudioLoading() {
  return <main className="s-startup" role="status"><BrandMark /><p>Opening Studio…</p></main>
}

export default function App() {
  const navigate = useNavigate()
  const location = useLocation()
  const params = new URLSearchParams(location.search)
  const demo = params.get("demo") === "1"
  const urlToken = params.get("token")
  const diffBase = params.get("diffBase")
  const urlTab = params.get("tab")
  const legacyFlowId = useMatch("/flows/:id")?.params.id
  const routeTab = legacyFlowId ? "flows" : studioTabs.find((tab) => tab === urlTab) ?? (diffBase ? "diff" : "system")
  const sessionId = params.get("sessionId") || params.get("session_id")
  const welcome = location.pathname.replace(/\/$/, "") === "/welcome" && !urlToken && !sessionId && !demo
  const returnSearch = typeof location.state?.studioReturnSearch === "string" ? location.state.studioReturnSearch : ""
  const data = useStudioStore((state) => state.data)
  const loading = useStudioStore((state) => state.loading)
  const error = useStudioStore((state) => state.error)
  const bootstrap = useStudioStore((state) => state.bootstrap)

  useEffect(() => {
    if (welcome) return
    studioStore.getState().setTab(routeTab)
    if (legacyFlowId) studioStore.getState().setActiveFlowId(legacyFlowId)
  }, [welcome, routeTab, legacyFlowId])

  useEffect(() => {
    if (welcome) return
    void bootstrap({ diffBase, demo, sessionId, token: urlToken ?? undefined })
    return () => studioStore.getState().disconnectEvents()
  }, [bootstrap, welcome, demo, urlToken, sessionId, diffBase])

  useEffect(() => {
    if (welcome) return
    const path = window.location.pathname
    return studioStore.subscribe((state, previous) => {
      if (window.location.pathname !== path) return
      const changedFlow = legacyFlowId && state.activeFlowId && state.activeFlowId !== previous.activeFlowId
      if (state.activeTab === previous.activeTab && !changedFlow) return
      const search = new URLSearchParams(window.location.search)
      const pathname = legacyFlowId && state.activeTab === "flows" && state.activeFlowId
        ? `/flows/${encodeURIComponent(state.activeFlowId)}`
        : legacyFlowId ? "/" : location.pathname
      if (search.get("tab") === state.activeTab && pathname === location.pathname) return
      search.set("tab", state.activeTab)
      navigate({ pathname, search: search.toString() }, { replace: true })
    })
  }, [welcome, location.pathname, legacyFlowId, navigate])

  function trySandbox(tab: StudioTab = "system") {
    navigate({ pathname: "/", search: new URLSearchParams({ demo: "1", tab }).toString() })
  }

  if (welcome || (data?.mode === "landing" && !demo && !loading)) {
    return <LandingPage
      onEnterApp={data?.mode === "workspace" ? () => navigate({ pathname: "/", search: returnSearch }) : undefined}
      onTrySandbox={trySandbox}
    />
  }

  if (!data || (demo && data.mode !== "demo")) {
    if (loading || !error) return <StudioLoading />
    return (
      <main className="s-startup">
        <BrandMark />
        <h1>Studio could not connect</h1>
        <p role="alert">{error}</p>
        <div className="s-init-actions">
          <button type="button" className="s-button s-primary" onClick={() => void bootstrap({ diffBase, demo, sessionId, token: urlToken ?? undefined })}>Retry connection</button>
          <button type="button" className="s-button" onClick={() => trySandbox()}>Try the sandbox</button>
        </div>
      </main>
    )
  }

  function openWelcome() {
    const search = new URLSearchParams(location.search)
    search.delete("token")
    search.delete("sessionId")
    search.delete("session_id")
    search.delete("demo")
    navigate("/welcome", { state: { studioReturnSearch: search.toString() } })
  }

  return <Suspense fallback={<StudioLoading />}><StudioShell onWelcome={openWelcome} /></Suspense>
}
