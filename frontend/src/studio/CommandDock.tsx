import { AtSign, Check, Clipboard, CornerDownLeft, LoaderCircle, Pin, Play, Send, Square, X } from "lucide-react"
import { useEffect, useRef, useState } from "react"
import { useShallow } from "zustand/react/shallow"
import { toast } from "sonner"
import { studioStore, useStudioStore, visibleDocument } from "@/lib/studioStore"
import { diffCounts, isPendingRun, runnerLabels, type RunKind, type RunLog, type StudioRun } from "@/lib/studioTypes"
import { DiffCounts } from "./StudioTopBar"

const runLabels: Record<StudioRun["status"], string> = {
  queued: "Queued",
  running: "Running",
  needs_input: "Needs your input",
  awaiting_approval: "Awaiting approval",
  completed: "Completed",
  failed: "Failed",
  cancelled: "Cancelled",
  discarded: "Plan discarded",
}

function RunLogs({ logs }: { logs: RunLog[] }) {
  const viewport = useRef<HTMLDivElement>(null)
  const following = useRef(true)
  const newest = logs.at(-1)
  useEffect(() => {
    const element = viewport.current
    if (element && following.current) element.scrollTop = element.scrollHeight
  }, [newest])
  return <div ref={viewport} role="log" aria-label="Agent activity" tabIndex={0}
    className="max-h-[7rem] overflow-auto rounded-lg border bg-background/60 px-2.5 py-1.5 font-mono text-[10.5px] leading-[1.65]"
    onScroll={(event) => {
      const element = event.currentTarget
      following.current = element.scrollHeight - element.scrollTop - element.clientHeight < 24
    }}>
    {logs.map((entry, index) => <p key={entry.id ?? index} className="break-words">
      {entry.stage && <strong className="mr-1.5 font-semibold text-when-fg">{entry.stage}</strong>}
      {entry.tool && <span className="mr-1.5 text-muted-foreground">{entry.tool}</span>}
      {entry.message}
    </p>)}
  </div>
}

function Clarification({ run }: { run: StudioRun }) {
  const [answer, setAnswer] = useState("")
  const [sending, setSending] = useState(false)
  return <form className="space-y-2 rounded-lg border border-when-accent/35 bg-when-bg p-2.5" onSubmit={async (event) => {
    event.preventDefault()
    if (!answer.trim() || sending) return
    setSending(true)
    try { await studioStore.getState().answerRun(answer.trim()) }
    finally { setSending(false) }
  }}>
    <label htmlFor="studio-run-answer" className="block text-xs font-semibold text-when-fg">{run.question || "The agent needs one more detail."}</label>
    <div className="flex flex-wrap items-center gap-2">
      <input id="studio-run-answer" value={answer} onChange={(event) => setAnswer(event.target.value)} autoComplete="off"
        className="min-w-36 flex-1 rounded-lg border bg-card px-2.5 py-2 text-sm placeholder:text-muted-foreground" placeholder="Answer and continue…" />
      <button type="submit" className="s-button s-primary" disabled={sending || !answer.trim()}><Send size={13} />Send Answer</button>
    </div>
  </form>
}

function Verification({ run }: { run: StudioRun }) {
  const tests = run.verification?.tests ?? []
  const files = run.verification?.changed_files ?? run.changed_files ?? []
  if (!tests.length && !files.length && !run.error) return null
  return <div className="space-y-2 rounded-lg border bg-background/60 p-2.5">
    {run.error && <p role="alert" className="text-xs text-destructive">{run.error}</p>}
    {tests.map((test, index) => <div key={`${test.command}:${index}`} className="text-xs">
      <div className="flex flex-wrap items-center gap-2">
        <span className={`s-chip ${test.passed ? "bg-act-bg text-act-fg" : "bg-destructive/10 text-destructive"}`}>{test.passed ? <Check size={12} /> : <X size={12} />}{test.passed ? "Passed" : "Failed"}</span>
        <code className="break-all">{test.command}</code>
      </div>
      {test.output && <p className="mt-1 whitespace-pre-wrap break-words text-[11px] text-muted-foreground">{test.output}</p>}
    </div>)}
    {files.length > 0 && <ul aria-label="Changed files" className="flex flex-wrap gap-1">
      {files.map((path) => <li className="s-chip max-w-full break-all font-mono" key={path}>{path}</li>)}
    </ul>}
  </div>
}

function RunActivity({ run, demo }: { run: StudioRun; demo: boolean }) {
  const [now, setNow] = useState(Date.now)
  const pending = isPendingRun(run)
  const live = run.status === "queued" || run.status === "running"
  const origin = Date.parse(run.started_at ?? run.created_at ?? "")
  const finish = Date.parse(run.finished_at ?? run.updated_at ?? "")
  const end = pending || !Number.isFinite(finish) ? now : finish
  const seconds = Number.isFinite(origin) ? Math.max(0, Math.floor((end - origin) / 1000)) : null
  const plan = run.status === "awaiting_approval" ? run.proposed_document : null
  const counts = plan ? diffCounts(plan.flows.flatMap((flow) => flow.nodes)) : null

  useEffect(() => {
    if (!pending) return
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [pending])

  return <div className="mb-2 max-h-[46dvh] space-y-2 overflow-auto rounded-xl border bg-card p-2.5 motion-safe:animate-fade-in" aria-label="Run activity">
    <div className="flex flex-wrap items-center gap-2 text-xs">
      {live && <span className="s-live-dot inline-block size-2 rounded-full bg-clay" aria-hidden="true" />}
      <span className="font-bold" role="status">{runLabels[run.status] ?? run.status}</span>
      <span className="s-chip">{demo ? `Simulated ${runnerLabels[run.runner]}` : runnerLabels[run.runner]}</span>
      {seconds !== null && <time className="ml-auto font-mono text-[11px] text-muted-foreground">{seconds}s</time>}
      {pending && run.status !== "awaiting_approval" && <button type="button" className="s-button" onClick={() => void studioStore.getState().cancelRun()}><Square size={12} />Cancel</button>}
      {!pending && <button type="button" className="s-icon" onClick={() => studioStore.getState().dismissRun()} aria-label="Dismiss run" title="Dismiss"><X size={15} /></button>}
    </div>
    {Boolean(run.logs?.length) && <RunLogs logs={run.logs ?? []} />}
    {live && !run.logs?.length && <p className="flex items-center gap-2 text-xs text-muted-foreground"><LoaderCircle size={13} className="motion-safe:animate-spin" />Waiting for agent activity…</p>}
    {run.status === "needs_input" && <Clarification key={run.question} run={run} />}
    {run.status === "awaiting_approval" && <div className="space-y-2 rounded-lg border border-when-accent/35 bg-when-bg p-2.5">
      <p className="text-xs font-semibold text-when-fg">{run.plan_summary || "Review the proposed behavior before applying it."}</p>
      <div className="flex flex-wrap items-center gap-2">
        {counts && <DiffCounts counts={counts} showZero />}
        <button type="button" className="s-button s-primary" onClick={() => void studioStore.getState().approvePlan()}><Play size={13} />Approve &amp; Build</button>
        <button type="button" className="s-button" onClick={() => void studioStore.getState().discardPlan()}>Discard</button>
      </div>
    </div>}
    {(run.status === "completed" || run.status === "failed") && <Verification run={run} />}
  </div>
}

export function CommandDock() {
  const document = useStudioStore(visibleDocument)
  const { run, runner, demo, activeFlowId, selectedIds, openPinCount, expanded, actionError } = useStudioStore(useShallow((state) => ({
    run: state.activeRun,
    runner: state.data?.runner.preferred ?? "copy",
    demo: state.data?.mode === "demo",
    activeFlowId: state.activeFlowId,
    selectedIds: state.selectedNodeIds,
    openPinCount: state.data?.annotations.filter((item) => !item.resolved).length ?? 0,
    expanded: state.commandDockOpen,
    actionError: state.actionError,
  })))
  const [prompt, setPrompt] = useState("")
  const [starting, setStarting] = useState(false)
  const selected = document?.flows.find((flow) => flow.id === activeFlowId)?.nodes.filter((step) => selectedIds.includes(step.id)) ?? []
  const copyMode = runner === "copy" && !demo
  const disabled = copyMode || starting || isPendingRun(run) || !prompt.trim()

  async function start(kind: RunKind) {
    if (disabled) return
    setStarting(true)
    try { await studioStore.getState().startRun({ kind, prompt: prompt.trim() }) }
    finally { setStarting(false) }
  }

  return <section className="s-command-card s-surface w-full rounded-2xl p-2" data-expanded={expanded} aria-label="Studio command dock">
    {run && <RunActivity key={run.id} run={run} demo={demo} />}
    <form onSubmit={(event) => { event.preventDefault(); void start("plan") }}>
      <label className="flex items-center gap-2 rounded-lg border bg-card px-2.5 py-0.5">
        <AtSign size={15} className="shrink-0 text-muted-foreground" />
        <input id="studio-command-input" value={prompt} onChange={(event) => setPrompt(event.target.value)}
          aria-label="Steer the agent" autoComplete="off"
          className="min-w-0 flex-1 rounded-sm bg-transparent py-2 text-sm placeholder:text-muted-foreground"
          placeholder={copyMode ? "Describe the change for your coding agent…" : `Ask ${runnerLabels[runner]} to plan or build a change on these flows…`} />
      </label>
      <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
        <div className="flex min-w-0 flex-wrap items-center gap-1">
          {selected.map((step) => <button key={step.id} type="button" className="s-chip min-w-0 max-w-40" title={`Remove @${step.title}`}
            aria-label={`Remove ${step.title} from scope`} onClick={() => studioStore.getState().toggleNodeSelection(step.id)}>
            <span className="truncate">@{step.title}</span><X size={12} className="shrink-0" />
          </button>)}
          <span className="s-chip"><Pin size={11} />{openPinCount} open {openPinCount === 1 ? "pin" : "pins"}</span>
        </div>
        <div className="ml-auto flex items-center gap-1.5">
          <button type="submit" className="s-button s-primary" disabled={disabled}>Plan Diff<CornerDownLeft size={12} aria-hidden="true" /></button>
          <button type="button" className="s-button s-clay" disabled={disabled} onClick={() => void start("build")}><Play size={13} />Build</button>
          <button type="button" className="s-button" aria-label="Copy Brief" title="Copy Brief" onClick={async () => {
            if (await studioStore.getState().copySpatialBrief(prompt)) toast.success("Spatial brief copied")
          }}><Clipboard size={14} /><span className="hidden min-[420px]:inline">Copy Brief</span></button>
        </div>
      </div>
    </form>
    {actionError && <p role="alert" className="px-1 pt-1.5 text-xs text-destructive">{actionError}</p>}
  </section>
}
