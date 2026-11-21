import { useCallback, useEffect, useState, type KeyboardEvent, type ReactNode } from "react"
import { Check, Clipboard, Code2, ExternalLink, GitCompareArrows, Pin, RotateCcw, Trash2, X } from "lucide-react"
import { useShallow } from "zustand/react/shallow"
import { toast } from "sonner"
import { studioApi } from "@/lib/studioApi"
import { demoFileDiff, demoFileSlice } from "@/lib/studioDemo"
import { studioStore, useStudioStore, visibleDocument } from "@/lib/studioStore"
import { formatRef, type AnnotationInput, type CodeRef, type FileDiff, type FileSlice, type StudioAnnotation, type StudioComponent } from "@/lib/studioTypes"

const tabs = [
  { id: "code", label: "Code & Provenance", icon: Code2 },
  { id: "diff", label: "Git Diff", icon: GitCompareArrows },
  { id: "pins", label: "Pins", icon: Pin },
] as const

type EvidenceTab = typeof tabs[number]["id"]
type PinTarget = Omit<AnnotationInput, "text">

function componentRefs(component: StudioComponent | undefined): CodeRef[] {
  if (!component) return []
  const root = component.path.replace(/^\.\/|\/$/g, "")
  return component.entrypoints.map((entry) => {
    const path = entry.replace(/^\.\//, "")
    return { path: !root || root === "." || path.startsWith(`${root}/`) ? path : `${root}/${path}` }
  })
}

function editorHref(scheme: "cursor" | "vscode", path: string, line?: number) {
  const normalized = path.replace(/\\/g, "/").replace(/^\/+/, "")
  const location = normalized.split("/").map((part, index) => index === 0 && /^[a-z]:$/i.test(part) ? part : encodeURIComponent(part)).join("/")
  return `${scheme}://file/${location}${line ? `:${line}` : ""}`
}

type EvidenceResult<T> = { value: T } | { error: string }

function tintedCode(text: string) {
  const parts = text.split(/(\/\/.*$|"[^"]*"|'[^']*'|`[^`]*`|\b(?:async|await|const|export|import|let|return|throw|if|else|new|type|interface|function|class|true|false|null|undefined)\b|\b\d+\b)/g)
  return parts.map((part, index) => {
    if (index % 2 === 0) return part
    const color = part.startsWith("//") ? "text-muted-foreground" : /^["'`]/.test(part) ? "text-act-fg" : "text-rule-fg"
    return <span key={index} className={color}>{part}</span>
  })
}

function CodeSlice({ slice, reference, demo }: { slice: FileSlice; reference: CodeRef; demo: boolean }) {
  return <>
    <div className="overflow-hidden rounded-xl border bg-background">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b px-3 py-2 text-[11px] text-muted-foreground">
        <span>{slice.language || "Source"}</span><span>Lines {slice.start_line}–{slice.end_line}</span>
      </div>
      <pre className="overflow-x-auto py-2 text-[11.5px] leading-5" aria-label="Referenced source code">
        <code>{slice.lines.map(({ number, text }) => (
          <span key={number} className={`flex w-max min-w-full border-l-2 pr-3 ${number === slice.highlight_line ? "border-gold bg-when-bg" : "border-transparent"}`}>
            <span aria-hidden="true" className="w-11 shrink-0 select-none pr-3 text-right text-muted-foreground">{number}</span>
            <span>{tintedCode(text || " ")}</span>
          </span>
        ))}</code>
      </pre>
    </div>
    {!demo && slice.absolute_path && <div className="mt-3 flex flex-wrap gap-2">
      <a className="s-button" href={editorHref("cursor", slice.absolute_path, reference.line)}><ExternalLink size={13} />Open in Cursor</a>
      <a className="s-button" href={editorHref("vscode", slice.absolute_path, reference.line)}><ExternalLink size={13} />Open in VS Code</a>
    </div>}
  </>
}

function DiffLines({ diff }: { diff: FileDiff }) {
  if (!diff.has_diff) return <p className="rounded-lg border bg-background p-3 text-sm text-muted-foreground">No changes for this file.</p>
  function row(text: string, kind?: string, key?: string) {
    const added = kind === "add" || kind === "added" || (text.startsWith("+") && !text.startsWith("+++"))
    const removed = kind === "remove" || kind === "removed" || (text.startsWith("-") && !text.startsWith("---"))
    const color = added ? "bg-act-bg text-act-fg" : removed ? "bg-destructive/10 text-destructive" : text.startsWith("@@") ? "bg-when-bg text-when-fg" : ""
    return <span key={key} className={`block w-max min-w-full px-3 ${color}`}>{text || " "}</span>
  }
  return <>
    <div className="mb-2 flex items-center gap-2 text-xs font-semibold" aria-label={`${diff.additions} additions, ${diff.deletions} deletions`}>
      <span className="rounded bg-act-bg px-1.5 py-0.5 text-act-fg">+{diff.additions}</span>
      <span className="rounded bg-destructive/10 px-1.5 py-0.5 text-destructive">−{diff.deletions}</span>
      {diff.base && <code className="min-w-0 truncate font-normal text-muted-foreground">{diff.base}</code>}
    </div>
    <pre className="overflow-x-auto rounded-xl border bg-background py-2 text-[11px] leading-5" aria-label="Unified Git diff">
      <code>{diff.hunks.map((hunk, index) => typeof hunk === "string" ? (
        <span key={index}>{hunk.split("\n").map((line, lineIndex) => row(line, undefined, String(lineIndex)))}</span>
      ) : (
        <span key={index}>
          {row(hunk.header)}
          {hunk.lines.map((line, lineIndex) => typeof line === "string" ? row(line, undefined, String(lineIndex)) : row(line.text, line.kind, String(lineIndex)))}
        </span>
      ))}</code>
    </pre>
  </>
}

function SourceEvidence({ reference, demo }: { reference: CodeRef; demo: boolean }) {
  const { path, line } = reference
  const load = useCallback((signal: AbortSignal) => studioApi.fileSlice(path, line, 12, signal), [path, line])
  if (demo) return <CodeSlice slice={demoFileSlice(path, line, 12)} reference={reference} demo />
  return <RemoteEvidence load={load} requestKey={formatRef(reference)}>
    {(slice) => <CodeSlice slice={slice} reference={reference} demo={false} />}
  </RemoteEvidence>
}

function GitEvidence({ path, base, demo }: { path: string; base?: string | null; demo: boolean }) {
  const load = useCallback((signal: AbortSignal) => studioApi.fileDiff(path, base, signal), [path, base])
  if (demo) return <DiffLines diff={demoFileDiff(path)} />
  return <RemoteEvidence load={load} requestKey={`${path}:${base ?? ""}`}>
    {(diff) => <DiffLines diff={diff} />}
  </RemoteEvidence>
}

function RemoteEvidence<T>({ load, requestKey, children }: {
  load: (signal: AbortSignal) => Promise<T>
  requestKey: string
  children: (value: T) => ReactNode
}) {
  const [result, setResult] = useState<{ key: string; payload: EvidenceResult<T> } | null>(null)
  useEffect(() => {
    const controller = new AbortController()
    void load(controller.signal).then((value) => {
      if (!controller.signal.aborted) setResult({ key: requestKey, payload: { value } })
    }).catch((error: unknown) => {
      if (!controller.signal.aborted) {
        setResult({ key: requestKey, payload: { error: error instanceof Error ? error.message : "Evidence could not be loaded." } })
      }
    })
    return () => controller.abort()
  }, [requestKey, load])
  if (result?.key !== requestKey) return <p className="text-sm text-muted-foreground" role="status">Loading evidence…</p>
  if ("error" in result.payload) return <p className="rounded-lg border border-destructive/40 bg-destructive/5 px-3 py-2 text-sm text-destructive" role="alert">{result.payload.error}</p>
  return children(result.payload.value)
}

function PinPanel({ target, pins }: { target: PinTarget; pins: StudioAnnotation[] }) {
  const { addAnnotation, resolveAnnotation, deleteAnnotation } = studioStore.getState()
  const [draft, setDraft] = useState("")
  const [saving, setSaving] = useState(false)
  return <div className="space-y-3">
    <form className="space-y-2 rounded-xl border bg-background p-3" onSubmit={async (event) => {
      event.preventDefault()
      if (!draft.trim() || saving) return
      setSaving(true)
      try {
        await addAnnotation({ ...target, text: draft.trim() })
        if (!studioStore.getState().actionError) setDraft("")
      } finally { setSaving(false) }
    }}>
      <label htmlFor="studio-pin-text" className="block text-xs font-semibold">New pin</label>
      <textarea id="studio-pin-text" value={draft} onChange={(event) => setDraft(event.target.value)} placeholder="What needs attention?" className="min-h-20 w-full resize-y rounded-lg border bg-card p-2 text-sm placeholder:text-muted-foreground" />
      <button type="submit" className="s-button s-primary" disabled={!draft.trim() || saving}><Pin size={14} />Add pin</button>
    </form>
    {pins.length === 0 && <p className="text-sm text-muted-foreground">No pins on this card.</p>}
    {pins.map((pin) => (
      <article key={pin.id} className={`rounded-xl border p-3 ${pin.resolved ? "bg-muted/40" : "border-clay/35 bg-clay/5"}`}>
        <p className="whitespace-pre-wrap break-words text-sm">{pin.text}</p>
        <div className="mt-2 flex items-center gap-1">
          <span className="s-chip mr-auto">{pin.resolved ? "Resolved" : "Open"}</span>
          <button type="button" className="s-icon" aria-label={pin.resolved ? "Reopen pin" : "Resolve pin"} title={pin.resolved ? "Reopen pin" : "Resolve pin"} onClick={() => void resolveAnnotation(pin.id, !pin.resolved)}>{pin.resolved ? <RotateCcw size={15} /> : <Check size={15} />}</button>
          <button type="button" className="s-icon text-destructive" aria-label="Delete pin" title="Delete pin" onClick={() => void deleteAnnotation(pin.id)}><Trash2 size={15} /></button>
        </div>
      </article>
    ))}
  </div>
}

interface EvidenceContentProps {
  title: string
  subtitle: string
  refs: CodeRef[]
  target: PinTarget
  pins: StudioAnnotation[]
  showPins: boolean
  demo: boolean
  diffBase?: string | null
  diffSummary?: string | null
  testRef?: string | null
  onClose: () => void
}

function EvidenceContent(props: EvidenceContentProps) {
  const { title, subtitle, refs, target, pins, showPins, demo, diffBase, diffSummary, testRef } = props
  const [tab, setTab] = useState<EvidenceTab>(showPins ? "pins" : "code")
  const [refIndex, setRefIndex] = useState(0)
  const reference = refs[refIndex] ?? refs[0]
  const openPins = pins.filter((pin) => !pin.resolved).length
  function tabShortcut(event: KeyboardEvent<HTMLDivElement>) {
    const current = tabs.findIndex((item) => item.id === tab)
    const index = event.key === "ArrowRight" ? (current + 1) % tabs.length
      : event.key === "ArrowLeft" ? (current + tabs.length - 1) % tabs.length
      : event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1 : null
    if (index === null) return
    event.preventDefault()
    setTab(tabs[index].id)
    event.currentTarget.querySelectorAll("button")[index]?.focus()
  }
  return <aside className="s-evidence s-surface flex flex-col overflow-hidden rounded-2xl" aria-label="Evidence panel">
    <header className="flex items-start justify-between gap-2 px-4 pb-3 pt-4">
      <div className="min-w-0"><p className="text-xs text-muted-foreground">{subtitle}</p><h2 className="break-words text-lg font-bold leading-tight tracking-tight">{title}</h2></div>
      <button type="button" className="s-icon shrink-0" onClick={props.onClose} aria-label="Close evidence panel"><X size={17} /></button>
    </header>
    <div className="flex flex-wrap gap-1 border-b px-2" role="tablist" aria-label="Evidence views" onKeyDown={tabShortcut}>
      {tabs.map(({ id, label, icon: Icon }) => (
        <button key={id} type="button" id={`studio-evidence-${id}`} role="tab" tabIndex={tab === id ? 0 : -1}
          aria-selected={tab === id} aria-controls="studio-evidence-content" onClick={() => setTab(id)}
          className={`inline-flex items-center gap-1 rounded-t-lg border-b-2 px-2 py-2 text-xs font-semibold ${tab === id ? "border-clay text-foreground" : "border-transparent text-muted-foreground hover:bg-muted"}`}>
          <Icon size={13} aria-hidden="true" />{label}{id === "pins" && ` (${openPins})`}
        </button>
      ))}
    </div>
    <div id="studio-evidence-content" role="tabpanel" aria-labelledby={`studio-evidence-${tab}`} className="min-h-0 flex-1 overflow-auto p-4">
      {tab === "pins" ? <PinPanel target={target} pins={pins} /> : <>
        {tab === "diff" && diffSummary && <p className="mb-3 rounded-lg border border-when-accent/30 bg-when-bg p-3 text-sm text-when-fg">{diffSummary}</p>}
        {reference && <div className="mb-3 flex flex-wrap items-center gap-2">
          {refs.length > 1 ? <select className="min-w-0 flex-1 rounded-lg border bg-background p-2 font-mono text-[11px]" value={refs[refIndex] ? refIndex : 0} aria-label="Evidence reference" onChange={(event) => setRefIndex(Number(event.target.value))}>
            {refs.map((item, index) => <option value={index} key={`${item.path}:${item.line ?? ""}:${index}`}>{formatRef(item)}</option>)}
          </select> : <code className="min-w-0 flex-1 break-all text-[11.5px] text-muted-foreground">{formatRef(reference)}</code>}
          <button type="button" className="s-button" onClick={async () => {
            try { await navigator.clipboard.writeText(formatRef(reference)); toast.success("Reference copied") }
            catch { toast.error("Clipboard is unavailable.") }
          }}><Clipboard size={13} />Copy ref</button>
        </div>}
        {reference ? (
          tab === "code"
            ? <SourceEvidence key={formatRef(reference)} reference={reference} demo={demo} />
            : <GitEvidence key={`${reference.path}:${diffBase ?? ""}`} path={reference.path} base={diffBase} demo={demo} />
        ) : <p className="text-sm text-muted-foreground">No file references for this card.</p>}
        {tab === "code" && testRef && <p className="mt-3 break-all text-xs text-muted-foreground">Test · <code>{testRef}</code></p>}
      </>}
    </div>
  </aside>
}

export function EvidenceDrawer({ flowPinId, onCloseFlowPin }: { flowPinId: string | null; onCloseFlowPin: () => void }) {
  const document = useStudioStore(visibleDocument)
  const { activeFlowId, nodeId, componentId, pinMode, annotations, demo, diffBase } = useStudioStore(useShallow((state) => ({
    activeFlowId: state.activeFlowId, nodeId: state.inspectedNodeId, componentId: state.inspectedComponentId, pinMode: state.pinMode,
    annotations: state.data?.annotations, demo: state.data?.mode === "demo", diffBase: state.data?.git.diff_base,
  })))
  if (!document) return null
  const flow = document.flows.find((item) => item.id === activeFlowId && item.nodes.some((node) => node.id === nodeId))
    ?? document.flows.find((item) => item.nodes.some((node) => node.id === nodeId))
  const node = flow?.nodes.find((item) => item.id === nodeId)
  const component = document.components.find((item) => item.id === componentId)
  const pinnedFlow = pinMode && flowPinId === activeFlowId ? document.flows.find((item) => item.id === flowPinId) : undefined
  const target: PinTarget | null = node ? { target_type: "node", target_id: node.id, flow_id: flow?.id }
    : component ? { target_type: "component", target_id: component.id }
    : pinnedFlow ? { target_type: "flow", target_id: pinnedFlow.id, flow_id: pinnedFlow.id } : null
  if (!target) return null
  const pins = annotations?.filter((pin) => pin.target_type === target.target_type && pin.target_id === target.target_id
    && (!pin.flow_id || pin.flow_id === target.flow_id)) ?? []
  return <EvidenceContent
    key={`${target.target_type}:${target.flow_id ?? ""}:${target.target_id}:${pinMode}`}
    title={node?.title ?? component?.name ?? pinnedFlow?.title ?? "Evidence"} subtitle={flow?.title ?? (component ? "Component evidence" : "Journey evidence")}
    refs={node?.code_refs ?? componentRefs(component)} target={target} pins={pins} showPins={pinMode}
    demo={demo} diffBase={diffBase} diffSummary={node?.diff_summary ?? pinnedFlow?.diff_summary} testRef={node?.test_ref}
    onClose={() => {
      const state = studioStore.getState()
      state.clearInspection()
      state.setPinMode(false)
      onCloseFlowPin()
    }}
  />
}
