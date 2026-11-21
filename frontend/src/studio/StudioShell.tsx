import { useEffect, useRef, useState } from "react"
import { studioStore, useStudioStore } from "@/lib/studioStore"
import { studioTabs } from "@/lib/studioTypes"
import { CommandDock } from "./CommandDock"
import { EvidenceDrawer } from "./EvidenceDrawer"
import { SpatialCanvas } from "./SpatialCanvas"
import { StudioSidebar } from "./StudioSidebar"
import { StudioTopBar } from "./StudioTopBar"

function focusCommand() {
  studioStore.getState().setCommandDockOpen(true)
  requestAnimationFrame(() => document.getElementById("studio-command-input")?.focus())
}

export default function StudioShell({ onWelcome }: { onWelcome: () => void }) {
  const [flowPinId, setFlowPinId] = useState<string | null>(null)
  const stageRef = useRef<HTMLElement>(null)
  const dockRef = useRef<HTMLDivElement>(null)
  const darkMode = useStudioStore((state) => state.darkMode)
  const connectionError = useStudioStore((state) => state.data?.mode === "workspace" ? state.error : null)
  const sidebarOpen = useStudioStore((state) => state.sidebarOpen)

  useEffect(() => {
    document.documentElement.classList.toggle("dark", darkMode)
    return () => document.documentElement.classList.remove("dark")
  }, [darkMode])

  useEffect(() => {
    const stage = stageRef.current
    const dock = dockRef.current
    if (!stage || !dock) return
    const updateDockHeight = () => stage.style.setProperty("--studio-dock-height", `${Math.ceil(dock.getBoundingClientRect().height)}px`)
    updateDockHeight()
    const observer = new ResizeObserver(updateDockHeight)
    observer.observe(dock)
    return () => {
      observer.disconnect()
      stage.style.removeProperty("--studio-dock-height")
    }
  }, [])

  useEffect(() => {
    function handleShortcut(event: KeyboardEvent) {
      if (event.defaultPrevented || event.isComposing || event.repeat) return
      const state = studioStore.getState()
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault()
        focusCommand()
        return
      }
      const target = event.target
      const localControl = target instanceof HTMLElement && target.closest<HTMLElement>("input, textarea, select, [contenteditable], [role=textbox]")
      if (event.key === "Escape") {
        if (localControl) {
          localControl.blur()
          return
        }
        state.setCommandDockOpen(false)
        state.clearInspection()
        state.setSelectedNodeIds([])
        state.setIncludeAllPins(false)
        state.setPinMode(false)
        setFlowPinId(null)
        return
      }
      if (event.metaKey || event.ctrlKey || event.altKey) return
      if (localControl) return
      if (event.key === "[") {
        event.preventDefault()
        state.setSidebarOpen(!state.sidebarOpen)
      } else if (event.key === "/") {
        event.preventDefault()
        state.setSidebarOpen(true)
        requestAnimationFrame(() => document.getElementById("studio-search")?.focus())
      } else if (event.key === "1" || event.key === "2" || event.key === "3") {
        event.preventDefault()
        state.setTab(studioTabs[Number(event.key) - 1])
      }
    }
    window.addEventListener("keydown", handleShortcut)
    return () => window.removeEventListener("keydown", handleShortcut)
  }, [])

  return (
    <div className="s-studio">
      <StudioTopBar onWelcome={onWelcome} focusCommand={focusCommand} />
      {connectionError && <p className="border-b border-when-accent/30 bg-when-bg px-4 py-1.5 text-xs text-when-fg" role="status">{connectionError}</p>}
      <div className="s-body">
        {sidebarOpen && <StudioSidebar onOpenFlowPin={setFlowPinId} />}
        <main ref={stageRef} className="s-stage">
          <SpatialCanvas focusCommand={focusCommand} onPaneClear={() => {
            studioStore.getState().clearInspection()
            setFlowPinId(null)
          }} />
          <div ref={dockRef} className="s-dock"><CommandDock /></div>
          <EvidenceDrawer flowPinId={flowPinId} onCloseFlowPin={() => setFlowPinId(null)} />
        </main>
      </div>
    </div>
  )
}
