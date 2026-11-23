import { ChevronRight, PanelLeftClose, Pin, Search } from "lucide-react"
import { useState } from "react"
import { useStudioStore, visibleDocument } from "@/lib/studioStore"
import { diffCounts, type StudioComponent } from "@/lib/studioTypes"
import { componentIcons } from "./StudioNodes"
import { DiffCounts } from "./StudioTopBar"

const groups: { title: string; kinds: StudioComponent["kind"][] }[] = [
  { title: "Apps", kinds: ["web", "mobile"] },
  { title: "Services", kinds: ["service", "package", "worker"] },
  { title: "Infra & External", kinds: ["db", "external"] },
]

export function StudioSidebar({ onOpenFlowPin }: { onOpenFlowPin: (flowId: string) => void }) {
  const state = useStudioStore()
  const document = visibleDocument(state)
  const [pinsExpanded, setPinsExpanded] = useState(false)
  if (!document) return null
  const {
    activeTab, activeFlowId, inspectedComponentId, data, searchQuery, setSearchQuery,
    setSidebarOpen, setTab, setActiveFlowId, setInspectedNode, setInspectedComponent, setPinMode, setDiffOnlyFilter,
  } = state
  const term = searchQuery.trim().toLowerCase()
  const componentById = new Map(document.components.map((component) => [component.id, component]))
  const matches = (...parts: (string | undefined)[]) => !term || parts.some((part) => part?.toLowerCase().includes(term))
  const matchedComponents = document.components.filter((c) => matches(c.name, c.path, c.summary, ...c.tech, ...c.entrypoints))
  const matchedSteps = term ? document.flows.flatMap((flow) => flow.nodes
    .filter((step) => matches(step.title, step.summary, ...step.code_refs.map((ref) => ref.path)))
    .map((step) => ({ step, flow }))) : []
  const flows = document.flows.filter((flow) => matches(flow.title, flow.trigger, flow.summary, ...flow.component_ids.map((id) => componentById.get(id)?.name))
    || matchedSteps.some((hit) => hit.flow.id === flow.id))
  const openPins = (data?.annotations ?? []).filter((pin) => !pin.resolved)

  function closeOnNarrowScreen() {
    if (window.matchMedia("(max-width: 660px)").matches) setSidebarOpen(false)
  }

  function openStep(flowId: string, nodeId: string, pins = false) {
    if (activeTab === "system") setTab("flows")
    setActiveFlowId(flowId)
    setPinMode(pins)
    setDiffOnlyFilter(false)
    setInspectedNode(nodeId)
    closeOnNarrowScreen()
  }

  function openComponent(id: string, pins = false) {
    setTab("system")
    setPinMode(pins)
    setInspectedComponent(id)
    closeOnNarrowScreen()
  }

  return (
    <aside className="s-sidebar" aria-label="Studio navigator">
      <div className="s-sidebar-head">
        <div className="s-sidebar-title"><h2>{term ? "Search" : activeTab === "system" ? "Components" : "Journeys"}</h2><button type="button" className="s-icon" onClick={() => setSidebarOpen(false)} aria-label="Collapse sidebar" title="Collapse sidebar ([)"><PanelLeftClose size={16} /></button></div>
        <label className="s-search"><Search size={15} /><input id="studio-search" type="search" aria-label="Search workspace" placeholder="Search workspace" value={searchQuery} onChange={(event) => setSearchQuery(event.target.value)} /><kbd>/</kbd></label>
      </div>

      <div className="s-directory">
        {(activeTab === "system" || term) && groups.map(({ title, kinds }) => {
          const components = matchedComponents.filter(({ kind }) => kinds.includes(kind))
          if (!components.length) return null
          return <section className="s-directory-group" key={title}><h3>{title}</h3>
            {components.map((component) => {
              const Icon = componentIcons[component.kind]
              return <button type="button" className="s-directory-row s-component-row" key={component.id} aria-current={activeTab === "system" && inspectedComponentId === component.id ? "true" : undefined} onClick={() => openComponent(component.id)}>
                <span className="s-directory-icon"><Icon size={15} /></span>
                <span className="min-w-0"><strong>{component.name}</strong><code>{component.path}</code></span>
                <span className="s-directory-end">{component.diff_status && component.diff_status !== "unchanged" && <i data-diff={component.diff_status} title={component.diff_status} />}<ChevronRight size={13} /></span>
              </button>
            })}
          </section>
        })}

        {(activeTab !== "system" || term) && <section className="s-directory-group">
          {term && flows.length > 0 && <h3>Journeys</h3>}
          {flows.map((flow) => {
            const stale = flow.nodes.some((node) => node.status === "stale" || data?.stale_node_ids.includes(node.id))
            return <button type="button" key={flow.id} className="s-directory-row s-journey-row" aria-current={activeTab !== "system" && flow.id === activeFlowId ? "true" : undefined} onClick={() => {
              if (activeTab === "system") setTab("flows")
              setActiveFlowId(flow.id)
              closeOnNarrowScreen()
            }}>
              <span className="s-journey-title"><strong>{flow.title}</strong>{stale && <i className="s-stale-dot" title="Contains stale steps" />}</span>
              <span className="s-journey-trigger">{flow.trigger}</span>
              <span className="s-journey-meta"><span>{flow.nodes.length} steps</span><DiffCounts counts={diffCounts(flow.nodes)} /></span>
              <span className="s-journey-chips">{flow.component_ids.flatMap((id) => {
                const component = componentById.get(id)
                return component ? [<span key={id} className="s-chip">{component.name}</span>] : []
              })}</span>
            </button>
          })}
          {!flows.length && !term && <p className="s-sidebar-empty">Mapped journeys will appear here.</p>}
        </section>}

        {matchedSteps.length > 0 && <section className="s-directory-group"><h3>Steps & files</h3>
          {matchedSteps.map(({ flow, step }) => <button type="button" className="s-directory-row s-search-step" key={`${flow.id}:${step.id}`} onClick={() => openStep(flow.id, step.id)}>
            <strong>{step.title}</strong><code>{step.code_refs[0]?.path ?? flow.title}</code>
          </button>)}
        </section>}
        {term && !matchedComponents.length && !flows.length && <p className="s-sidebar-empty">No matches for “{searchQuery}”.</p>}
      </div>

      <div className="s-open-pins">
        <button type="button" aria-expanded={pinsExpanded} onClick={() => setPinsExpanded(!pinsExpanded)}>
          <Pin size={15} /> <strong>Open Pins</strong><span className="s-chip">{openPins.length}</span><ChevronRight size={14} className={pinsExpanded ? "rotate-90" : ""} />
        </button>
        {pinsExpanded && <ul>
          {!openPins.length && <li className="s-sidebar-empty">No open pins.</li>}
          {openPins.map((pin) => <li key={pin.id}>
            <button type="button" title={pin.text} onClick={() => {
              if (pin.target_type === "component") openComponent(pin.target_id, true)
              else if (pin.target_type === "node") {
                const flow = document.flows.find((candidate) => candidate.id === pin.flow_id) ?? document.flows.find((candidate) => candidate.nodes.some((node) => node.id === pin.target_id))
                if (flow) openStep(flow.id, pin.target_id, true)
              } else {
                if (activeTab === "system") setTab("flows")
                setActiveFlowId(pin.target_id)
                state.clearInspection()
                setPinMode(true)
                onOpenFlowPin(pin.target_id)
                closeOnNarrowScreen()
              }
            }}>{pin.text}</button>
          </li>)}
        </ul>}
      </div>
    </aside>
  )
}
