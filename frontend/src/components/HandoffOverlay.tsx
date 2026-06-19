import { useEffect, useState } from "react"
import { AlertCircle, Check, CircleCheck, Clipboard, Clock, Loader2, RefreshCw } from "lucide-react"
import { cn } from "@/lib/utils"
import { useChanges, type HandoffItem, type HandoffItemStatus } from "@/lib/changeset"
import { Button } from "@/components/ui/button"
import { ScrollArea } from "@/components/ui/scroll-area"

interface Props {
  onAcknowledge: () => void
}

export function HandoffOverlay({ onAcknowledge }: Props) {
  const { handoff, assistantName, refreshHandoff } = useChanges()
  const { phase, items, summary, question, prompt, error } = handoff

  useEffect(() => {
    if (phase === "composing" || phase === "done") return
    const id = window.setInterval(() => {
      refreshHandoff()
    }, 2500)
    return () => window.clearInterval(id)
  }, [phase, refreshHandoff])

  if (phase === "composing") return null

  if (phase === "sending" || phase === "working") {
    return (
      <div className="w-full max-w-lg animate-fade-in rounded-lg border border-border bg-card shadow-lg">
        <div className="flex items-center gap-3 px-5 py-4">
          <Loader2 className="h-5 w-5 shrink-0 animate-spin text-primary" />
          <div className="min-w-0 flex-1">
            <p className="text-sm font-medium text-foreground">
              Waiting for {assistantName}
            </p>
            <p className="mt-0.5 text-xs text-muted-foreground">
              Pending requests were written locally. Your agent can pick them up now.
            </p>
          </div>
          <Button variant="ghost" size="icon" onClick={() => refreshHandoff()} aria-label="Refresh status">
            <RefreshCw className="h-4 w-4" />
          </Button>
        </div>

        <HandoffItemList items={items} />
        {question && <StatusCallout tone="warning" message={question} />}
        {error && <StatusCallout tone="error" message={error} />}

        {prompt && <CopyPrompt prompt={prompt} />}

        <div className="border-t border-border px-5 py-3">
          <p className="text-xs text-muted-foreground">
            Keep this open to watch status. Or copy the prompt and paste it into your agent.
          </p>
        </div>
      </div>
    )
  }

  if (phase === "done") {
    return (
      <div className="w-full max-w-lg animate-fade-in rounded-lg border border-border bg-card shadow-lg">
        <div className="flex items-start gap-3 px-5 py-5">
          <CircleCheck className="mt-0.5 h-5 w-5 shrink-0 text-act-fg" />
          <div className="flex-1">
            <p className="text-sm font-semibold text-foreground">
              All set - your changes are live
            </p>
            {summary && (
              <p className="mt-1 text-sm text-muted-foreground">{summary}</p>
            )}
          </div>
        </div>
        <HandoffItemList items={items} />
        <div className="flex items-center gap-2 border-t border-border px-5 py-4">
          <Button onClick={onAcknowledge}>Got it</Button>
          <Button variant="ghost" onClick={onAcknowledge}>
            Review what changed
          </Button>
        </div>
      </div>
    )
  }

  if (phase === "needs_input" || phase === "blocked") {
    const blocked = phase === "blocked"
    return (
      <div className="w-full max-w-lg animate-fade-in rounded-lg border border-border bg-card shadow-lg">
        <div className="flex items-start gap-3 px-5 py-5">
          <AlertCircle className={cn("mt-0.5 h-5 w-5 shrink-0", blocked ? "text-destructive" : "text-when-fg")} />
          <div className="flex-1">
            <p className="text-sm font-semibold text-foreground">
              {blocked ? `${assistantName} is blocked` : `${assistantName} needs input`}
            </p>
            {question && <p className="mt-1.5 text-sm text-muted-foreground">{question}</p>}
            {error && <p className="mt-1.5 text-xs text-destructive">{error}</p>}
          </div>
        </div>
        <HandoffItemList items={items} />
        {prompt && <CopyPrompt prompt={prompt} />}
        <div className="border-t border-border px-5 py-4">
          <Button onClick={onAcknowledge}>Got it</Button>
        </div>
      </div>
    )
  }

  return null
}

const STATUS_VIEW: Record<
  HandoffItemStatus,
  {
    label: string
    detail: string
    Icon: typeof Clock
    iconClassName: string
    badgeClassName: string
  }
> = {
  queued: {
    label: "Creating",
    detail: "Writing pending files",
    Icon: Clock,
    iconClassName: "text-muted-foreground",
    badgeClassName: "border-border bg-secondary text-muted-foreground",
  },
  sent: {
    label: "Sent",
    detail: "Pending file created",
    Icon: Clock,
    iconClassName: "text-muted-foreground",
    badgeClassName: "border-border bg-secondary text-muted-foreground",
  },
  in_progress: {
    label: "In progress",
    detail: "Agent started work",
    Icon: Loader2,
    iconClassName: "animate-spin text-primary",
    badgeClassName: "border-primary/20 bg-accent text-accent-foreground",
  },
  done: {
    label: "Done",
    detail: "Implemented",
    Icon: CircleCheck,
    iconClassName: "text-act-fg",
    badgeClassName: "border-act-accent/20 bg-act-bg text-act-fg",
  },
  needs_input: {
    label: "Needs input",
    detail: "Waiting on a reply",
    Icon: AlertCircle,
    iconClassName: "text-when-fg",
    badgeClassName: "border-when-accent/30 bg-when-bg text-when-fg",
  },
  blocked: {
    label: "Blocked",
    detail: "Cannot continue yet",
    Icon: AlertCircle,
    iconClassName: "text-destructive",
    badgeClassName: "border-destructive/20 bg-destructive/10 text-destructive",
  },
}

function HandoffItemList({ items }: { items: HandoffItem[] }) {
  if (!items.length) return null

  return (
    <ul className="flex flex-col gap-2 px-5 pb-4">
      {items.map((item) => {
        const cfg = STATUS_VIEW[item.status]
        const path = item.markdownPath || item.jsonPath
        return (
          <li key={item.changeId} className="rounded-md border border-border bg-background/60 px-3 py-2">
            <div className="flex items-start gap-2.5">
              <cfg.Icon className={cn("mt-0.5 h-4 w-4 shrink-0", cfg.iconClassName)} />
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className={cn("rounded-full border px-2 py-0.5 text-[11px] font-medium", cfg.badgeClassName)}>
                    {cfg.label}
                  </span>
                  <span className="text-xs text-muted-foreground">{cfg.detail}</span>
                </div>
                <p className="mt-1 break-words text-sm text-foreground">{item.label}</p>
                {item.note && <p className="mt-1 break-words text-xs text-muted-foreground">{item.note}</p>}
                {path && <p className="mt-1 truncate font-mono text-[11px] text-muted-foreground">{path}</p>}
              </div>
            </div>
          </li>
        )
      })}
    </ul>
  )
}

function StatusCallout({ tone, message }: { tone: "warning" | "error"; message: string }) {
  return (
    <div
      className={cn(
        "mx-5 mb-4 rounded-md border px-3 py-2 text-xs",
        tone === "error"
          ? "border-destructive/20 bg-destructive/10 text-destructive"
          : "border-when-accent/30 bg-when-bg text-when-fg"
      )}
    >
      {message}
    </div>
  )
}

function CopyPrompt({ prompt }: { prompt: string }) {
  const [copyState, setCopyState] = useState<"idle" | "copied" | "manual">("idle")
  async function copy() {
    try {
      await navigator.clipboard.writeText(prompt)
      setCopyState("copied")
      window.setTimeout(() => setCopyState("idle"), 1600)
    } catch {
      setCopyState("manual")
    }
  }

  return (
    <div className="mx-5 mb-4 rounded-md border bg-secondary/30">
      <div className="flex items-center justify-between gap-3 border-b px-3 py-2">
        <p className="text-xs font-medium text-muted-foreground">Copy fallback prompt</p>
        <Button variant="outline" size="sm" onClick={copy}>
          {copyState === "copied" ? <Check className="h-3.5 w-3.5" /> : <Clipboard className="h-3.5 w-3.5" />}
          {copyState === "copied" ? "Copied" : "Copy"}
        </Button>
      </div>
      {copyState === "manual" && (
        <p className="border-b px-3 py-2 text-xs text-muted-foreground">
          Clipboard blocked. The prompt below is selectable.
        </p>
      )}
      <ScrollArea className="max-h-32">
        <pre className="whitespace-pre-wrap px-3 py-2 text-xs leading-5 text-muted-foreground">
          {prompt}
        </pre>
      </ScrollArea>
    </div>
  )
}
