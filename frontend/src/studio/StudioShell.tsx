import { useEffect, useState } from "react"
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
  const darkMode = useStudioStore((state) => state.darkMode)
  const connectionError = useStudioStore((state) => state.data?.mode === "workspace" ? state.error : null)
  const sidebarOpen = useStudioStore((state) => state.sidebarOpen)

  useEffect(() => {
    document.documentElement.classList.toggle("dark", darkMode)
    return () => document.documentElement.classList.remove("dark")
  }, [darkMode])

  useEffect(() => {
    function handleShortcut(event: KeyboardEvent) {
      if (event.defaultPrevented || event.isComposing || event.repeat) return
      const state = studioStore.getState()
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault()
        focusCommand()
        return
      }
      if (event.key === "Escape") {
        if (document.activeElement instanceof HTMLElement && document.activeElement.closest(".s-dock")) document.activeElement.blur()
        state.setCommandDockOpen(false)
        state.clearInspection()
        state.setSelectedNodeIds([])
        state.setPinMode(false)
        setFlowPinId(null)
        return
      }
      if (event.metaKey || event.ctrlKey || event.altKey) return
      const target = event.target
      if (target instanceof HTMLElement && target.closest("input, textarea, select, [contenteditable], [role=textbox]")) return
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
        <main className="s-stage">
          <SpatialCanvas focusCommand={focusCommand} onPaneClear={() => {
            studioStore.getState().clearInspection()
            setFlowPinId(null)
          }} />
          <div className="s-dock"><CommandDock /></div>
          <EvidenceDrawer flowPinId={flowPinId} onCloseFlowPin={() => setFlowPinId(null)} />
        </main>
      </div>
    </div>
  )
}
