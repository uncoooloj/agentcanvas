import { useEffect, useMemo, useState } from "react"
import {
  ChevronLeft,
  Lightbulb,
  Moon,
  PanelLeftClose,
  PanelLeftOpen,
  RefreshCw,
  Loader2,
  Sparkles,
  Sun,
  X,
} from "lucide-react"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { FlowColumn, type FlowAction } from "@/components/FlowCanvas"
import { Overview } from "@/components/Overview"
import { Inspector } from "@/components/Inspector"
import { Provenance } from "@/components/Provenance"
import { BottomDock } from "@/components/BottomDock"
import { LandingPage } from "@/components/LandingPage"
import { DEMO_MODEL, projectToBehavior } from "@/lib/behavioral"
import { applyChanges, useChanges, type ChangeEntry, type HandoffItem, type Phase } from "@/lib/changeset"
import { fetchGraph, reindex } from "@/lib/api"
import { useAppContext } from "@/lib/appcontext"
import type { EditRequest, StagedEdit } from "@/lib/edits"
import { findNode, type AppModel, type FlowNode, type Journey } from "@/lib/types"

const HOME = "__home__"

export default function App() {
  const { context, loading: contextLoading } = useAppContext()
  const [model, setModel] = useState<AppModel>(DEMO_MODEL)
  const [view, setView] = useState<string>(HOME)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [editRequest, setEditRequest] = useState<EditRequest | null>(null)
  const [leftOpen, setLeftOpen] = useState(true)
  const [loading, setLoading] = useState(true)
  const [dark, setDark] = useState(false)

  const phase = useChanges((s) => s.handoff.phase)
  const handoffItems = useChanges((s) => s.handoff.items)
  const stagedChanges = useChanges((s) => s.changes)
  const queuedNext = useChanges((s) => s.queuedNext)
  const orderingChanges = useMemo(() => [...stagedChanges, ...queuedNext], [queuedNext, stagedChanges])
  const localChanges = useMemo(
    () => (phase === "composing" ? stagedChanges : queuedNext),
    [phase, queuedNext, stagedChanges]
  )
  const locked = phase === "sending" || phase === "working"
  const journeyActivity = useMemo(
    () => getJourneyActivity(model.journeys, localChanges, orderingChanges, phase, handoffItems),
    [handoffItems, localChanges, model.journeys, orderingChanges, phase]
  )

  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark)
  }, [dark])

  // Switching flows (or returning to All Flows) clears any in-progress step
  // edit, so the composer never lingers on a page where it has no context.
  useEffect(() => {
    setEditRequest(null)
  }, [view])

  async function load({ refresh = false }: { refresh?: boolean } = {}) {
    // Demo mode shows the curated, hand-authored flows (great first impression);
    // the heuristic projection over real code isn't good enough to lead with yet.
    // Edits still write real pending requests via /api/changes.
    if (context.mode === "demo") {
      setModel((current) => preserveLocalJourneyRecency(DEMO_MODEL, current))
      setView(HOME)
      setSelectedId(null)
      setLoading(false)
      return
    }
    setLoading(true)
    try {
      const graph = refresh ? await reindex() : await fetchGraph()
      setModel((current) => preserveLocalJourneyRecency(projectToBehavior(graph), current))
    } catch {
      setModel((current) => preserveLocalJourneyRecency(DEMO_MODEL, current))
    } finally {
      setView(HOME)
      setSelectedId(null)
      setLoading(false)
    }
  }

  useEffect(() => {
    if (contextLoading || context.mode === "landing") return
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [contextLoading, context.mode])

  const activeJourney: Journey | null = useMemo(
    () => (view === HOME ? null : model.journeys.find((j) => j.id === view) ?? null),
    [model, view]
  )
  const orderedJourneys = useMemo(
    () => orderJourneysByEdit(model.journeys, orderingChanges),
    [model.journeys, orderingChanges]
  )
  const selectedNode: FlowNode | null = useMemo(
    () => (activeJourney && selectedId ? findNode(activeJourney.nodes, selectedId) : null),
    [activeJourney, selectedId]
  )

  function openAction(action: FlowAction, node: FlowNode) {
    if (!activeJourney || locked) return
    setEditRequest({ action, node, journeyTitle: activeJourney.title })
    setSelectedId(null) // the action moves to the bottom composer; let the popover go
  }

  function stageEdit(edit: StagedEdit) {
    if (!activeJourney) return
    const input = {
      action: edit.action,
      summary: edit.summary,
      journeyId: activeJourney.id,
      journeyTitle: edit.journeyTitle,
      targetNodeId: edit.node.id,
      text1: edit.text1,
      text2: edit.text2,
    }
    if (edit.changeId) {
      useChanges.getState().updateChange(edit.changeId, input)
    } else {
      useChanges.getState().addChange(input)
    }
    setEditRequest(null)
  }

  function locateChange(change: ChangeEntry) {
    const journey = model.journeys.find((j) => j.id === change.journeyId) ?? null
    const node = journey ? findNode(journey.nodes, change.targetNodeId) : null
    return { journey, node }
  }

  function selectChange(change: ChangeEntry) {
    const { journey, node } = locateChange(change)
    if (!journey || !node) return
    setView(journey.id)
    setSelectedId(node.id)
    setEditRequest(null)
  }

  function modifyChange(change: ChangeEntry) {
    const { journey, node } = locateChange(change)
    if (!journey || !node) return
    setView(journey.id)
    setSelectedId(node.id)
    setEditRequest({
      action: change.action,
      node,
      journeyTitle: change.journeyTitle,
      changeId: change.id,
      initialText1: change.text1 ?? "",
      initialText2: change.text2 ?? "",
    })
  }

  function onHandoffDone() {
    const applied = useChanges.getState().acknowledgeDone()
    const editedAtByJourney = new Map<string, number>()
    for (const change of applied) {
      const editedAt = change.updatedAt || change.createdAt
      editedAtByJourney.set(
        change.journeyId,
        Math.max(editedAtByJourney.get(change.journeyId) ?? 0, editedAt)
      )
    }
    setModel((m) => {
      const next = applyChanges(m, applied)
      return {
        ...next,
        journeys: next.journeys.map((journey) => {
          const editedAt = editedAtByJourney.get(journey.id)
          return editedAt ? { ...journey, lastEditedAt: editedAt } : journey
        }),
      }
    })
    setSelectedId(null)
  }

  const inJourney = view !== HOME && !!activeJourney
  const landing = !contextLoading && context.mode === "landing"

  if (contextLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background text-sm text-muted-foreground">
        <Sparkles className="mr-2 size-4 animate-pulse text-primary" />
        Opening AgentCanvas…
      </div>
    )
  }

  if (landing) {
    return <LandingPage />
  }

  return (
    <div className="flex h-screen flex-col bg-background text-foreground">
      <header className="flex h-14 shrink-0 items-center gap-3 border-b px-4">
        {inJourney && (
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setLeftOpen((v) => !v)}
            aria-label={leftOpen ? "Hide menu" : "Show menu"}
            className="hidden shrink-0 text-muted-foreground md:flex"
          >
            {leftOpen ? <PanelLeftClose className="h-4 w-4" /> : <PanelLeftOpen className="h-4 w-4" />}
          </Button>
        )}
        <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-primary text-primary-foreground">
          <Sparkles className="h-4 w-4" />
        </span>
        <div className="min-w-0 flex-1">
          <Provenance context={context} demoMode={model.isDemo || context.isDemo} />
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          <span className="mr-1 hidden text-xs text-muted-foreground sm:inline">
            {loading ? "Reading your app…" : "Up to date"}
          </span>
          <Button variant="ghost" size="icon" onClick={() => load({ refresh: true })} aria-label="Refresh">
            <RefreshCw className={cn("h-4 w-4", loading && "animate-spin")} />
          </Button>
          <Button variant="ghost" size="icon" onClick={() => setDark((v) => !v)} aria-label="Toggle theme">
            {dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
          </Button>
        </div>
      </header>

      <div className="relative flex min-h-0 flex-1">
        {(!inJourney || leftOpen) && (
          <Rail
            journeys={orderedJourneys}
            activity={journeyActivity}
            activeId={view}
            onHome={() => {
              setView(HOME)
              setSelectedId(null)
            }}
            onSelect={(id) => {
              setView(id)
              setSelectedId(null)
            }}
          />
        )}

        <main className="min-w-0 flex-1 overflow-auto">
          {(model.isDemo || context.isDemo) && <DemoBanner thin={model.thin} />}
          {inJourney ? (
            <JourneyView
              journey={activeJourney!}
              selectedId={selectedId}
              locked={locked}
              onBack={() => {
                setView(HOME)
                setSelectedId(null)
              }}
              onSelect={(id) => setSelectedId((cur) => (cur === id ? null : id))}
              onAction={openAction}
            />
          ) : (
            <Overview
              appName={model.appName}
              journeys={orderedJourneys}
              changes={localChanges}
              activity={journeyActivity}
              onOpen={(id) => setView(id)}
            />
          )}
        </main>

        {/* Ephemeral step popover — floats over the canvas on desktop */}
        {inJourney && selectedNode && (
          <StepDetailsPanel
            node={selectedNode}
            className="absolute bottom-24 right-4 top-4 z-30 hidden w-[340px] lg:flex"
            onClose={() => setSelectedId(null)}
            onAction={(a) => selectedNode && openAction(a, selectedNode)}
            onModifyChange={modifyChange}
            onCancelChange={(id) => useChanges.getState().undoChange(id)}
          />
        )}

        {/* Mobile stack + one dynamic bottom surface: composer / change tray / handoff */}
        <div className="pointer-events-none absolute inset-x-0 bottom-3 z-40 flex flex-col items-center gap-2 px-3 lg:bottom-6 lg:px-4">
          {inJourney && selectedNode && (
            <StepDetailsPanel
              node={selectedNode}
              className="flex max-h-[52vh] w-full lg:hidden"
              onClose={() => setSelectedId(null)}
              onAction={(a) => selectedNode && openAction(a, selectedNode)}
              onModifyChange={modifyChange}
              onCancelChange={(id) => useChanges.getState().undoChange(id)}
            />
          )}
          <div className="pointer-events-auto flex w-full max-w-2xl justify-center">
            <BottomDock
              request={editRequest}
              onSubmitEdit={stageEdit}
              onCancelEdit={() => setEditRequest(null)}
              onHandoffDone={onHandoffDone}
              onSelectChange={selectChange}
              onModifyChange={modifyChange}
            />
          </div>
        </div>
      </div>
    </div>
  )
}

function StepDetailsPanel({
  node,
  className,
  onClose,
  onAction,
  onModifyChange,
  onCancelChange,
}: {
  node: FlowNode
  className?: string
  onClose: () => void
  onAction: (action: FlowAction) => void
  onModifyChange: (change: ChangeEntry) => void
  onCancelChange: (id: string) => void
}) {
  return (
    <div
      className={cn(
        "pointer-events-auto flex-col overflow-hidden rounded-xl border bg-card shadow-xl animate-fade-in",
        className
      )}
    >
      <div className="flex items-center justify-between border-b px-3 py-2">
        <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
          Step details
        </span>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close"
          className="rounded-md p-1 text-muted-foreground hover:bg-secondary hover:text-foreground"
        >
          <X className="h-4 w-4" />
        </button>
      </div>
      <div className="min-h-0 flex-1 overflow-auto">
        <Inspector
          node={node}
          onAction={onAction}
          onModifyChange={onModifyChange}
          onCancelChange={onCancelChange}
        />
      </div>
    </div>
  )
}

function Rail({
  journeys,
  activity,
  activeId,
  onHome,
  onSelect,
}: {
  journeys: Journey[]
  activity: Map<string, JourneyActivity>
  activeId: string
  onHome: () => void
  onSelect: (id: string) => void
}) {
  return (
    <nav className="hidden w-64 shrink-0 flex-col border-r bg-card/60 px-3 py-4 md:flex">
      <button
        type="button"
        onClick={onHome}
        className={cn(
          "mb-1 flex items-center gap-2.5 rounded-lg px-3 py-2.5 text-left text-sm transition-colors",
          activeId === HOME ? "bg-secondary font-medium" : "text-muted-foreground hover:bg-secondary/60"
        )}
      >
        <Sparkles className={cn("h-4 w-4", activeId === HOME ? "text-primary" : "opacity-60")} />
        All flows
      </button>
      <p className="px-2 pb-2 pt-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
        Journeys
      </p>
      <div className="flex flex-col gap-0.5">
        {journeys.map((j) => {
          const active = j.id === activeId
          const state = activity.get(j.id) ?? "idle"
          return (
            <button
              key={j.id}
              type="button"
              onClick={() => onSelect(j.id)}
              className={cn(
                "flex items-center gap-2.5 rounded-lg px-3 py-2.5 text-left text-sm transition-colors",
                active ? "bg-secondary font-medium text-foreground" : "text-muted-foreground hover:bg-secondary/60"
              )}
            >
              <JourneyDot state={state} active={active} />
              <span className="truncate">{j.title}</span>
            </button>
          )
        })}
      </div>
    </nav>
  )
}

type JourneyActivity = "idle" | "edited" | "working"

function JourneyDot({ state, active }: { state: JourneyActivity; active: boolean }) {
  if (state === "working") {
    return <Loader2 aria-hidden="true" className="h-3.5 w-3.5 shrink-0 animate-spin text-primary" />
  }
  return (
    <span
      aria-hidden="true"
      className={cn(
        "h-2.5 w-2.5 shrink-0 rounded-full",
        state === "edited" ? "bg-when-accent" : "bg-muted-foreground/35",
        active && "ring-4 ring-primary/10"
      )}
    />
  )
}

function orderJourneysByEdit(journeys: Journey[], changes: ChangeEntry[]) {
  const changedAtByJourney = new Map<string, number>()
  for (const change of changes) {
    const editedAt = change.updatedAt || change.createdAt
    changedAtByJourney.set(
      change.journeyId,
      Math.max(changedAtByJourney.get(change.journeyId) ?? 0, editedAt)
    )
  }
  return journeys
    .map((journey, index) => ({
      journey,
      index,
      editedAt: changedAtByJourney.get(journey.id) ?? journey.lastEditedAt ?? 0,
    }))
    .sort((a, b) => b.editedAt - a.editedAt || a.index - b.index)
    .map((item) => item.journey)
}

function getJourneyActivity(
  journeys: Journey[],
  localChanges: ChangeEntry[],
  orderingChanges: ChangeEntry[],
  phase: Phase,
  handoffItems: HandoffItem[]
) {
  const active = new Map<string, JourneyActivity>()
  for (const journey of journeys) {
    if (localChanges.some((change) => change.journeyId === journey.id)) {
      active.set(journey.id, "edited")
    }
  }

  if (phase === "sending" || phase === "working") {
    const changesById = new Map(orderingChanges.map((change) => [change.id, change]))
    for (const item of handoffItems) {
      if (item.status === "in_progress") {
        const change = changesById.get(item.changeId)
        if (change) active.set(change.journeyId, "working")
      }
    }
  }

  return active
}

function preserveLocalJourneyRecency(next: AppModel, current: AppModel) {
  const editedAtByJourney = new Map(
    current.journeys
      .filter((journey) => journey.lastEditedAt)
      .map((journey) => [journey.id, journey.lastEditedAt!])
  )
  if (!editedAtByJourney.size) return next
  return {
    ...next,
    journeys: next.journeys.map((journey) => {
      const editedAt = editedAtByJourney.get(journey.id)
      return editedAt ? { ...journey, lastEditedAt: editedAt } : journey
    }),
  }
}

function JourneyView({
  journey,
  selectedId,
  locked,
  onBack,
  onSelect,
  onAction,
}: {
  journey: Journey
  selectedId: string | null
  locked: boolean
  onBack: () => void
  onSelect: (id: string) => void
  onAction: (action: FlowAction, node: FlowNode) => void
}) {
  return (
    <div className="mx-auto max-w-3xl px-6 py-7 pb-40">
      <button
        type="button"
        onClick={onBack}
        className="mb-4 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ChevronLeft className="h-4 w-4" /> All flows
      </button>
      <div className="mb-5">
        <h1 className="text-xl font-medium">{journey.title}</h1>
        <p className="mt-1 text-sm text-muted-foreground">{journey.summary}</p>
        <p className="mt-3 inline-flex items-center gap-1.5 rounded-full bg-secondary px-3 py-1 text-xs text-muted-foreground">
          <Lightbulb className="h-3.5 w-3.5" />
          Click a step to change it — or hover a step to add, branch, or remove right there.
        </p>
      </div>
      <div className={cn("transition-opacity", locked && "pointer-events-none opacity-60")}>
        <FlowColumn nodes={journey.nodes} selectedId={selectedId} onSelect={onSelect} onAction={onAction} />
      </div>
    </div>
  )
}

function DemoBanner({ thin }: { thin?: boolean }) {
  return (
    <div className="border-b bg-accent/40 px-6 py-2.5 text-center text-xs text-accent-foreground">
      {thin
        ? "We're still learning your app — here's what we can see so far."
        : "This is an example. Open AgentCanvas inside your own project to see what your app does."}
    </div>
  )
}
