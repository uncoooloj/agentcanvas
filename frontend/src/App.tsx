import { lazy, Suspense, useEffect, type ComponentType } from "react"
import { useLocation, useNavigate } from "react-router-dom"
import { LandingPage } from "@/components/LandingPage"
import { BrandMark } from "@/components/BrandMark"
import { studioStore, useStudioStore } from "@/lib/studioStore"
import { studioTabs, type StudioTab } from "@/lib/studioTypes"

const StudioShell = lazy(() => import("@/studio/StudioShell"))
const Landing = LandingPage as ComponentType<{ onEnterApp?: () => void; onTrySandbox?: (tab?: StudioTab) => void }>

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
  const routeTab = studioTabs.find((tab) => tab === urlTab) ?? (diffBase ? "diff" : "system")
  const welcome = location.pathname.replace(/\/$/, "") === "/welcome" && !urlToken && !demo
  const returnSearch = typeof location.state?.studioReturnSearch === "string" ? location.state.studioReturnSearch : ""
  const data = useStudioStore((state) => state.data)
  const loading = useStudioStore((state) => state.loading)
  const error = useStudioStore((state) => state.error)
  const bootstrap = useStudioStore((state) => state.bootstrap)

  useEffect(() => {
    if (welcome) return
    studioStore.getState().setTab(routeTab)
  }, [welcome, routeTab])

  useEffect(() => {
    if (welcome) return
    void bootstrap({ diffBase, demo, token: urlToken ?? undefined })
    return () => studioStore.getState().disconnectEvents()
  }, [bootstrap, welcome, demo, urlToken, diffBase])

  useEffect(() => {
    if (welcome) return
    const path = window.location.pathname
    return studioStore.subscribe((state, previous) => {
      if (window.location.pathname !== path || state.activeTab === previous.activeTab) return
      const search = new URLSearchParams(window.location.search)
      if (search.get("tab") === state.activeTab) return
      search.set("tab", state.activeTab)
      navigate({ pathname: location.pathname, search: search.toString() }, { replace: true })
    })
  }, [welcome, location.pathname, navigate])

  function trySandbox(tab: StudioTab = "system") {
    navigate({ pathname: "/", search: new URLSearchParams({ demo: "1", tab }).toString() })
  }

  if (welcome || (data?.mode === "landing" && !demo && !loading)) {
    return <Landing
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
          <button type="button" className="s-button s-primary" onClick={() => void bootstrap({ diffBase, demo, token: urlToken ?? undefined })}>Retry connection</button>
          <button type="button" className="s-button" onClick={() => trySandbox()}>Try the sandbox</button>
        </div>
      </main>
    )
  }

  function openWelcome() {
    const search = new URLSearchParams(location.search)
    search.delete("token")
    search.delete("demo")
    navigate("/welcome", { state: { studioReturnSearch: search.toString() } })
  }

  return <Suspense fallback={<StudioLoading />}><StudioShell onWelcome={openWelcome} /></Suspense>
}
