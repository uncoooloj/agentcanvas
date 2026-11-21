import { useEffect, useRef, useState, type ReactNode } from "react"
import { Check, Clipboard, Terminal } from "lucide-react"
import { cn } from "@/lib/utils"

type CommandId = "map" | "diff" | "install"

const COMMANDS: ReadonlyArray<{
  id: CommandId
  label: string
  context: string
  command: string
}> = [
  { id: "map", label: "Map", context: "repo", command: "agentcanvas ." },
  { id: "diff", label: "Diff", context: "branch", command: "agentcanvas diff main..HEAD" },
  { id: "install", label: "Install", context: "", command: "pip install use-agentcanvas" },
]

function useCopyFeedback() {
  const [copied, setCopied] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const timer = useRef<number | undefined>(undefined)
  const request = useRef(0)

  useEffect(() => {
    return () => {
      request.current += 1
      if (timer.current !== undefined) window.clearTimeout(timer.current)
    }
  }, [])

  async function copy(id: string, value: string) {
    const requestId = request.current + 1
    request.current = requestId
    if (timer.current !== undefined) {
      window.clearTimeout(timer.current)
      timer.current = undefined
    }
    setCopied(null)
    setError(null)

    try {
      if (typeof navigator === "undefined" || !navigator.clipboard?.writeText) {
        throw new Error("Clipboard unavailable")
      }
      await navigator.clipboard.writeText(value)
      if (request.current !== requestId) return
      setCopied(id)
      timer.current = window.setTimeout(() => {
        if (request.current !== requestId) return
        setCopied(null)
        timer.current = undefined
      }, 1600)
    } catch {
      if (request.current !== requestId) return
      setCopied(null)
      setError("Could not copy. Select the command and copy it manually.")
    }
  }

  return { copied, error, copy }
}

export function CommandStrip() {
  const [selectedId, setSelectedId] = useState<CommandId>("map")
  const { copied, error, copy } = useCopyFeedback()
  const selected = COMMANDS.find(({ id }) => id === selectedId) ?? COMMANDS[0]

  return (
    <div className="overflow-hidden rounded-[15px] border border-primary/20 bg-primary text-primary-foreground shadow-[0_18px_42px_-28px_rgba(42,27,19,0.9)]">
      <div className="flex items-center gap-3 border-b border-primary-foreground/10 px-3.5 py-2.5 sm:px-4">
        <div className="flex min-w-0 items-center gap-2 font-mono text-[10px] tracking-[0.02em] text-primary-foreground/75">
          <Terminal aria-hidden="true" className="size-3.5 shrink-0" />
          <span className="truncate">agentcanvas</span>
        </div>
      </div>

      <div role="group" aria-label="AgentCanvas commands" className="flex flex-wrap gap-1 border-b border-primary-foreground/10 px-2.5 py-2">
        {COMMANDS.map((item) => {
          const active = selectedId === item.id
          return (
            <button
              key={item.id}
              type="button"
              aria-pressed={active}
              onClick={() => setSelectedId(item.id)}
              className={cn(
                "inline-flex min-h-8 items-center gap-1.5 rounded-md border px-2.5 text-[10px] font-semibold transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-primary-foreground",
                active
                  ? "border-primary-foreground/20 bg-primary-foreground/10 text-primary-foreground"
                  : "border-transparent text-primary-foreground/55 hover:border-primary-foreground/10 hover:bg-primary-foreground/5 hover:text-primary-foreground/85",
              )}
            >
              {item.label}
              {item.context && <span className="font-mono text-[9px] font-normal text-primary-foreground/45">{item.context}</span>}
            </button>
          )
        })}
      </div>

      <div className="flex items-center gap-2.5 px-3.5 py-3 sm:px-4">
        <span aria-hidden="true" className="font-mono text-[11px] text-primary-foreground/45">$</span>
        <code className="min-w-0 flex-1 overflow-x-auto whitespace-nowrap font-mono text-[11px] leading-6 text-primary-foreground sm:text-xs">
          {selected.command}
        </code>
        <button
          type="button"
          onClick={() => void copy(selected.id, selected.command)}
          aria-label={`Copy ${selected.label.toLowerCase()} command`}
          className="inline-flex min-h-8 shrink-0 items-center gap-1.5 rounded-md border border-primary-foreground/15 px-2.5 text-[10px] font-semibold text-primary-foreground/75 transition-colors hover:border-primary-foreground/30 hover:bg-primary-foreground/10 hover:text-primary-foreground focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-primary-foreground"
        >
          {copied === selected.id ? <Check aria-hidden="true" className="size-3.5" /> : <Clipboard aria-hidden="true" className="size-3.5" />}
          <span>{copied === selected.id ? "Copied" : "Copy"}</span>
        </button>
      </div>

      <span role="status" aria-live="polite" className="sr-only">
        {copied === selected.id ? "Copied to clipboard." : ""}
      </span>

      {error && (
        <p role="status" className="border-t border-destructive-foreground/10 px-3.5 py-2 text-[10px] leading-relaxed text-primary-foreground/70 sm:px-4">
          {error}
        </p>
      )}
    </div>
  )
}

const START_CARDS = [
  {
    eyebrow: "Install + map",
    title: "Run in your repo",
    detail: "Install once, then map the current directory.",
    command: "pip install use-agentcanvas\nagentcanvas .",
  },
  {
    eyebrow: "Branch diff",
    title: "Review a branch visually",
    detail: "See the behavior delta before you merge.",
    command: "agentcanvas diff main..HEAD",
  },
  {
    eyebrow: "Codex / Claude",
    title: "Hand one line to your agent",
    detail: "A tiny prompt for the repo you are already in.",
    command: "Install AgentCanvas here:\npip install use-agentcanvas\nagentcanvas .",
  },
] as const

function StartCard({
  eyebrow,
  title,
  detail,
  command,
}: (typeof START_CARDS)[number]) {
  const { copied, error, copy } = useCopyFeedback()

  return (
    <article className="flex min-w-0 flex-col rounded-xl border border-border/80 bg-card/70 p-4 sm:p-5">
      <p className="font-mono text-[10px] font-semibold uppercase tracking-[0.13em] text-clay">{eyebrow}</p>
      <h3 className="mt-3 text-[17px] font-bold leading-tight tracking-[-0.035em]">{title}</h3>
      <p className="mt-1.5 min-h-10 text-xs leading-relaxed text-muted-foreground">{detail}</p>
      <div className="mt-5 flex min-h-[72px] flex-1 flex-col overflow-hidden rounded-lg border border-border/75 bg-background">
        <pre className="min-w-0 flex-1 overflow-x-auto whitespace-pre-wrap break-words px-3 py-3 font-mono text-[11px] leading-[1.65] text-foreground/85">
          {command}
        </pre>
        <div className="flex justify-end border-t border-border/70 px-2 py-1.5">
          <button
            type="button"
            onClick={() => void copy("card", command)}
            aria-label={`Copy ${title.toLowerCase()} command`}
            className="inline-flex min-h-7 items-center gap-1.5 rounded-md px-2 text-[10px] font-semibold text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-ring"
          >
            {copied === "card" ? <Check aria-hidden="true" className="size-3.5" /> : <Clipboard aria-hidden="true" className="size-3.5" />}
            {copied === "card" ? "Copied" : "Copy"}
          </button>
        </div>
      </div>
      {error && <p role="status" className="mt-2 text-[10px] leading-relaxed text-destructive">{error}</p>}
    </article>
  )
}

export function StartSection({ children }: { children?: ReactNode } = {}) {
  return (
    <section id="start" className="scroll-mt-20 py-16 sm:py-24">
      <div className="max-w-2xl">
        <p className="font-mono text-[10px] font-semibold uppercase tracking-[0.16em] text-clay">Start locally</p>
        <h2 className="mt-3 text-balance text-3xl font-bold leading-[1.05] tracking-[-0.045em] sm:text-5xl">
          Up and running in 10 seconds
        </h2>
      </div>

      <div className="mt-10 grid gap-3.5 md:grid-cols-3">
        {START_CARDS.map((card) => <StartCard key={card.eyebrow} {...card} />)}
      </div>
      {children}
    </section>
  )
}
