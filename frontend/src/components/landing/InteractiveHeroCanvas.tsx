import { useEffect, useId, useRef, useState, type FormEvent } from "react"
import {
  ArrowRight, ArrowUpRight, Check, CodeXml, Command, GitBranch, GitCompare,
  Layers, Network, Pin, ScanLine, X,
} from "lucide-react"
import { cn } from "@/lib/utils"
import { checkout, createProposal, services, steeringExamples, type StudioMode } from "./studioDemo"

const modes = [
  { id: "current", label: "Current Map", icon: Layers },
  { id: "diff", label: "Visual Diff", icon: GitCompare },
  { id: "system", label: "System Map", icon: Network },
] as const

const roles = {
  When: "bg-when-bg text-when-fg",
  Do: "bg-act-bg text-act-fg",
  If: "bg-rule-bg text-rule-fg",
  Service: "bg-secondary text-secondary-foreground",
}

const topology = {
  current: "Current Map. POST /orders leads to Reserve stock, then In stock. When in stock, the flow continues to Charge Stripe, then Send confirmation.",
  diff: "Visual Diff. POST /orders leads to Reserve stock, then In stock, then the modified Charge Stripe step and Send confirmation. Send confirmation leads to the added Text delivery ETA via Twilio step, which leads to the added Queue manual retry fallback.",
  system: "System Map. Web App calls Order API. Order API connects to Inventory, Stripe, and Notify Worker.",
}

type Proposal = NonNullable<ReturnType<typeof createProposal>>
type Plan = { proposal: Proposal; phase: "reading" | "drafting" | "proposed" | "applied" }

export function InteractiveHeroCanvas() {
  const [mode, setMode] = useState<StudioMode>("current")
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [request, setRequest] = useState("")
  const [plan, setPlan] = useState<Plan | null>(null)
  const lastNode = useRef<HTMLButtonElement | null>(null)
  const proposalNode = useRef<HTMLButtonElement>(null)
  const composer = useRef<HTMLInputElement>(null)
  const inspectorTitle = useRef<HTMLHeadingElement>(null)
  const canvasId = useId()
  const canvasTitleId = useId()
  const topologyId = useId()
  const inspectorId = useId()
  const isDiff = mode === "diff"
  const isSystem = mode === "system"
  const isPlanning = plan?.phase === "reading" || plan?.phase === "drafting"
  const visiblePlan = isDiff && (plan?.phase === "proposed" || plan?.phase === "applied") ? plan : null
  const nodes = isSystem ? services : isDiff ? checkout : checkout.filter((node) => node.change !== "Added")
  const selected = nodes.find((node) => node.id === selectedId)
  const selectedPlan = selectedId === "proposal" ? visiblePlan?.proposal : null
  const proposalAnchor = visiblePlan && checkout.find((node) => node.id === visiblePlan.proposal.anchor)
  const inspector = selectedPlan
    ? { label: selectedPlan.label, file: selectedPlan.file, line: selectedPlan.line, code: selectedPlan.draft }
    : selected && {
      label: selected.label, file: selected.file, line: selected.line,
      code: isDiff && selected.diff ? selected.diff : selected.source,
    }

  useEffect(() => {
    if (plan?.phase !== "reading" && plan?.phase !== "drafting") return
    const { proposal, phase } = plan
    const timer = window.setTimeout(() => {
      setPlan({ proposal, phase: phase === "reading" ? "drafting" : "proposed" })
    }, phase === "reading" ? 500 : 700)
    return () => window.clearTimeout(timer)
  }, [plan])

  useEffect(() => {
    if (selectedId) inspectorTitle.current?.focus()
  }, [selectedId])

  function inspect(id: string, button: HTMLButtonElement) {
    lastNode.current = button
    setSelectedId(id)
  }

  function closeInspector() {
    setSelectedId(null)
    const trigger = selectedId === "proposal" ? proposalNode.current : lastNode.current
    trigger?.focus()
  }

  function draft(input: string) {
    const proposal = createProposal(input)
    if (!proposal || isPlanning) return
    setSelectedId(null)
    setMode("diff")
    setRequest("")
    setPlan({ proposal, phase: "reading" })
    composer.current?.focus({ preventScroll: true })
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    draft(request)
  }

  return (
    <section
      id="canvas"
      aria-label="Interactive checkout studio"
      className="relative min-w-0 scroll-mt-24 rounded-[22px] border bg-card shadow-[0_18px_55px_-35px_rgba(52,32,19,0.48)] dark:shadow-black/50"
      onKeyDown={(event) => {
        if (event.key === "Escape" && inspector) closeInspector()
        if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
          event.preventDefault()
          composer.current?.focus()
        }
      }}
    >
      <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-2 px-3.5 py-3.5 sm:px-5">
        <div className="flex min-w-0 items-center gap-2.5">
          <span className="grid size-7 shrink-0 place-items-center rounded-lg border bg-background text-clay">
            <GitBranch aria-hidden="true" className="size-3.5" />
          </span>
          <div className="min-w-0 font-mono text-[10px] leading-[1.45] sm:text-[11px]">
            <p className="font-semibold">shop-platform</p>
            <p className="break-words text-muted-foreground">feature/retry-sms-receipt</p>
          </div>
        </div>
        <span className="flex items-center gap-1.5 text-[11px] font-medium text-muted-foreground">
          <span className="size-1.5 rounded-full bg-act-accent" /> Playable demo
        </span>
      </div>

      <div aria-label="Canvas view" role="group" className="flex flex-wrap gap-1 border-y bg-background px-2 py-1.5 sm:px-3">
        {modes.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            type="button"
            aria-pressed={mode === id}
            aria-controls={canvasId}
            onClick={() => {
              setSelectedId(null)
              setMode(id)
            }}
            className={cn(
              "inline-flex min-h-8 items-center gap-1 rounded-lg border px-1.5 text-[10px] font-semibold focus-visible:outline focus-visible:outline-2 focus-visible:outline-ring sm:gap-1.5 sm:px-2.5 sm:text-xs",
              mode === id ? "border-border bg-card shadow-sm" : "border-transparent text-muted-foreground hover:bg-secondary",
            )}
          >
            <Icon aria-hidden="true" className="size-3.5 shrink-0" />
            {label}
            {id === "diff" && <span className="rounded bg-when-bg px-1 font-mono text-[9px] tabular-nums text-when-fg">+2 ~1</span>}
          </button>
        ))}
      </div>

      <div className="[container-type:inline-size]">
        <div className="flex flex-col [@container_(min-width:560px)]:flex-row">
          <div
            id={canvasId}
            role="region"
            aria-labelledby={canvasTitleId}
            aria-describedby={topologyId}
            className="min-w-0 flex-1 bg-secondary/35 bg-[radial-gradient(circle,hsl(var(--muted-foreground)/0.28)_0.75px,transparent_0.9px)] [background-size:15px_15px]"
          >
            <div className="flex items-center justify-between gap-2 px-3.5 pt-3.5 sm:px-5">
              <h2 id={canvasTitleId} className="text-xs font-semibold">{isSystem ? "Service topology" : "Checkout flow"}</h2>
              <span className="flex items-center gap-1.5 font-mono text-[10px] text-muted-foreground">
                <ScanLine aria-hidden="true" className="size-3" /> {isDiff ? "main..HEAD" : isSystem ? "5 services" : "main"}
              </span>
            </div>
            <p id={topologyId} className="sr-only">
              {topology[mode]}
              {visiblePlan && proposalAnchor && ` ${visiblePlan.phase === "applied" ? "Applied change" : "Steering proposal"}: ${visiblePlan.proposal.label} attaches to ${proposalAnchor.label}.`}
            </p>
            <div key={mode} className="relative mx-2 grid h-[278px] grid-cols-3 grid-rows-3 items-center gap-x-2 py-0 sm:mx-4 sm:h-[285px] sm:gap-x-5 motion-safe:animate-fade-in">
              <Connections mode={mode} proposalAnchor={visiblePlan?.proposal.anchor} />
              {nodes.map((node) => {
                const change = isDiff ? node.change : undefined
                return (
                  <button
                    key={node.id}
                    type="button"
                    aria-expanded={selectedId === node.id}
                    aria-controls={selectedId === node.id ? inspectorId : undefined}
                    onClick={(event) => inspect(node.id, event.currentTarget)}
                    className={cn(
                      "relative z-10 flex min-h-[58px] min-w-0 flex-col items-start justify-center gap-1 rounded-xl border bg-card px-1.5 py-1.5 text-left shadow-sm hover:ring-1 hover:ring-clay focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring sm:px-2.5",
                      node.position,
                      change === "Modified" && "border-when-accent/75",
                      change === "Added" && "border-act-accent/60",
                      isDiff && node.id === "sms" && "motion-safe:animate-fade-in",
                      selectedId === node.id && "ring-1 ring-clay",
                    )}
                  >
                    <span className={cn("rounded px-1 font-mono text-[9px] leading-4", roles[node.role])}>{node.role}</span>
                    <span className="break-words text-[11px] font-semibold leading-tight sm:text-[12px]">{node.label}</span>
                    {change && (
                      <span className={cn(
                        "text-[9px] font-semibold leading-tight",
                        change === "Added" ? "text-act-fg" : "text-when-fg",
                      )}>
                        {change === "Added" ? "+ Added" : "~ Modified"}
                      </span>
                    )}
                    {change === "Modified" && (
                      <span className="text-[9px] leading-tight text-muted-foreground">Adds idempotency key + 3x backoff</span>
                    )}
                  </button>
                )
              })}
              {visiblePlan && (
                <button
                  ref={proposalNode}
                  type="button"
                  aria-expanded={selectedId === "proposal"}
                  aria-controls={selectedId === "proposal" ? inspectorId : undefined}
                  onClick={(event) => inspect("proposal", event.currentTarget)}
                  className={cn(
                    "relative z-10 row-start-3 min-h-[58px] min-w-0 rounded-xl border border-act-accent/70 bg-act-bg p-1.5 text-left text-act-fg shadow-sm hover:ring-1 hover:ring-act-accent focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring motion-safe:animate-fade-in sm:px-2.5",
                    visiblePlan.proposal.anchor === "charge" ? "col-start-3" : "col-start-2",
                  )}
                >
                  <span className="flex items-center gap-1 font-mono text-[9px]">
                    <Pin aria-hidden="true" className="size-3 shrink-0" /> {visiblePlan.phase === "applied" ? "+ Applied" : "+ Proposed"}
                  </span>
                  <span title={visiblePlan.proposal.label} className="mt-1 line-clamp-2 text-[11px] font-semibold [overflow-wrap:anywhere] sm:text-xs">
                    {visiblePlan.proposal.label}
                  </span>
                </button>
              )}
              {mode === "current" && (
                <p className="col-span-2 col-start-1 row-start-3 flex items-center gap-1.5 self-end pb-4 pl-1 text-[10px] text-muted-foreground sm:text-[11px]">
                  <CodeXml aria-hidden="true" className="size-3.5" /> Select a step to inspect its source
                </p>
              )}
            </div>
          </div>

          {inspector && (
            <div className="flex min-w-0 justify-end border-t bg-secondary/35 [@container_(min-width:560px)]:w-[226px] [@container_(min-width:560px)]:shrink-0 [@container_(min-width:560px)]:border-l [@container_(min-width:560px)]:border-t-0">
              <aside id={inspectorId} aria-label="Source inspector" className="w-full min-w-0 bg-background px-3.5 py-3 motion-safe:animate-in motion-safe:fade-in motion-safe:slide-in-from-right-2 motion-safe:duration-200 sm:max-w-[90%] sm:border-l sm:px-3.5 [@container_(min-width:560px)]:max-w-none [@container_(min-width:560px)]:border-l-0">
                <div className="mb-2 flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <h3 ref={inspectorTitle} tabIndex={-1} className="break-words text-sm font-semibold">
                      {inspector.label}
                    </h3>
                    <p className="break-all font-mono text-[10px] text-muted-foreground">{inspector.file}:{inspector.line}</p>
                  </div>
                  <button
                    type="button"
                    onClick={closeInspector}
                    aria-label="Close source inspector"
                    className="grid size-7 shrink-0 place-items-center rounded-md text-muted-foreground hover:bg-secondary focus-visible:outline focus-visible:outline-2 focus-visible:outline-ring"
                  >
                    <X aria-hidden="true" className="size-4" />
                  </button>
                </div>
                <SyntaxCode source={inspector.code} />
              </aside>
            </div>
          )}
        </div>
      </div>

      <div className="space-y-2.5 border-t px-3.5 py-3.5 sm:px-5">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="mr-0.5 inline-flex items-center gap-1 text-xs font-semibold"><Pin aria-hidden="true" className="size-3.5 text-clay" /> Try steering</span>
          {steeringExamples.map((example) => (
            <button
              key={example}
              type="button"
              disabled={isPlanning}
              onClick={() => draft(example)}
              className="inline-flex min-h-7 items-center gap-1 rounded-full border px-2 text-[10px] font-medium hover:bg-secondary focus-visible:outline focus-visible:outline-2 focus-visible:outline-ring disabled:opacity-50"
            >
              {example} <ArrowUpRight aria-hidden="true" className="size-3" />
            </button>
          ))}
        </div>
        <form onSubmit={submit} className="flex min-w-0 items-center gap-2 rounded-[11px] border bg-background p-1.5 pl-2.5 focus-within:ring-1 focus-within:ring-clay">
          <kbd aria-hidden="true" className="flex shrink-0 items-center gap-0.5 font-mono text-[10px] text-muted-foreground">
            <Command className="size-3" /> K
          </kbd>
          <input
            ref={composer}
            aria-label="What should checkout do differently?"
            aria-keyshortcuts="Meta+K Control+K"
            placeholder="What should checkout do differently?"
            value={request}
            maxLength={140}
            onChange={(event) => setRequest(event.target.value)}
            className="min-w-0 flex-1 bg-transparent py-1.5 text-xs outline-none placeholder:text-muted-foreground focus-visible:underline focus-visible:decoration-clay focus-visible:underline-offset-4"
          />
          <button
            type="submit"
            disabled={!request.trim() || isPlanning}
            className="inline-flex min-h-7 shrink-0 items-center gap-1.5 rounded-md bg-primary px-2 text-[10px] font-semibold text-primary-foreground focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:opacity-45"
          >
            Plan diff <ArrowRight aria-hidden="true" className="size-3" />
          </button>
        </form>
        <div className="flex min-h-7 flex-wrap items-center justify-between gap-2">
          <p role="status" className="flex min-w-0 items-center gap-1.5 text-[11px] text-muted-foreground">
            {plan?.phase === "reading" && <>Reading {plan.proposal.file.replace("src/", "")}…</>}
            {plan?.phase === "drafting" && "Drafting visual diff…"}
            {plan?.phase === "proposed" && "1 proposed change · ready for review"}
            {plan?.phase === "applied" && <><Check aria-hidden="true" className="size-3.5 shrink-0 text-act-fg" /> Change applied to the demo canvas</>}
            {!plan && "Pins draft a simulated change on this canvas."}
          </p>
          {plan?.phase === "proposed" && (
            <button
              type="button"
              onClick={() => {
                if (!isDiff) {
                  setMode("diff")
                  setSelectedId("proposal")
                  return
                }
                setPlan({ ...plan, phase: "applied" })
                composer.current?.focus()
              }}
              className="min-h-7 rounded-md bg-act-bg px-2 text-[11px] font-semibold text-act-fg hover:ring-1 hover:ring-act-accent focus-visible:outline focus-visible:outline-2 focus-visible:outline-ring"
            >
              {isDiff ? "Approve & Build" : "Review proposal"}
            </button>
          )}
        </div>
      </div>
    </section>
  )
}

const proposalPaths = {
  charge: "M250 184V215",
  sms: "M50 175V196H150V215",
  confirm: "M150 175V215",
}

function Connections({ mode, proposalAnchor }: { mode: StudioMode; proposalAnchor?: Proposal["anchor"] }) {
  const arrow = useId()
  const branchArrow = useId()
  const paths = mode === "system"
    ? ["M150 75V115", "M150 175V200H50V215", "M150 175V215", "M150 175V200H250V215"]
    : ["M88 50H102", "M188 50H204", "M250 74V112", "M212 150H198"]
  const branches = [
    ...(mode === "diff" ? ["M112 150H96", "M50 176V207"] : []),
    ...(proposalAnchor ? [proposalPaths[proposalAnchor]] : []),
  ]

  return (
    <svg aria-hidden="true" viewBox="0 0 300 300" preserveAspectRatio="none" className="pointer-events-none absolute inset-0 size-full overflow-visible text-muted-foreground">
      <defs>
        <marker id={arrow} viewBox="0 0 8 8" refX="7" refY="4" markerWidth="6" markerHeight="6" orient="auto">
          <path d="M1 1L7 4L1 7" fill="none" stroke="currentColor" strokeWidth="1.25" />
        </marker>
        <marker id={branchArrow} viewBox="0 0 8 8" refX="7" refY="4" markerWidth="6" markerHeight="6" orient="auto">
          <path d="M1 1L7 4L1 7" fill="none" stroke="hsl(var(--act-accent))" strokeWidth="1.25" />
        </marker>
      </defs>
      {paths.map((path) => <path key={path} d={path} fill="none" stroke="currentColor" strokeOpacity=".7" strokeWidth="1" vectorEffect="non-scaling-stroke" markerEnd={`url(#${arrow})`} />)}
      {branches.map((path) => <path key={path} d={path} fill="none" stroke="hsl(var(--act-accent))" strokeDasharray="3 2" strokeWidth="1.2" vectorEffect="non-scaling-stroke" markerEnd={`url(#${branchArrow})`} />)}
    </svg>
  )
}

function SyntaxCode({ source }: { source: string }) {
  return (
    <pre className="overflow-hidden rounded-lg border bg-card p-2.5 font-mono text-[11px] leading-relaxed">
      <code>
        {source.split("\n").map((line, index) => (
          <span key={index} className={cn(
            "block whitespace-pre-wrap [overflow-wrap:anywhere]",
            line.startsWith("+") && "bg-act-bg text-act-fg",
            line.startsWith("-") && "bg-when-bg text-when-fg",
            line.startsWith("@@") && "text-muted-foreground",
          )}>
            {line.split(/("(?:[^"\\]|\\.)*"|`[^`]*`|\b(?:async|await|const|export|function|return|if|catch|new)\b)/g).map((token, tokenIndex) => (
              <span key={tokenIndex} className={cn(
                /^["`]/.test(token) && "text-act-fg",
                /^(async|await|const|export|function|return|if|catch|new)$/.test(token) && "text-rule-fg",
              )}>{token}</span>
            ))}
          </span>
        ))}
      </code>
    </pre>
  )
}
