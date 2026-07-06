import { useEffect, useState } from "react"
import { AlertCircle, Check, CircleCheck, Clipboard, Clock, Loader2, RefreshCw, Send } from "lucide-react"
import { cn } from "@/lib/utils"
import { HandoffItemStatus, HandoffPhase, useChanges, type HandoffItem } from "@/lib/changeset"
import { Button } from "@/components/ui/button"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Textarea } from "@/components/ui/textarea"
import { documentIsVisible, PENDING_ACTIVITY_POLL_INTERVAL_MS } from "@/lib/polling"
import { CanvasSourceTone, ConversationRole, ConversationTurnKind, CopyState } from "@/lib/types"

interface Props {
  onAcknowledge: () => void
  onDismiss: () => void
}

export function HandoffOverlay({ onAcknowledge, onDismiss }: Props) {
  const { handoff, assistantName, refreshHandoff, answerHandoffQuestion } = useChanges()
  const { phase, items, summary, question, prompt, error } = handoff

  useEffect(() => {
    if (phase === HandoffPhase.Composing || phase === HandoffPhase.Done) return
    const id = window.setInterval(() => {
      if (!documentIsVisible()) return
      refreshHandoff()
    }, PENDING_ACTIVITY_POLL_INTERVAL_MS)
    return () => window.clearInterval(id)
  }, [phase, refreshHandoff])

  if (phase === HandoffPhase.Composing) return null

  if (phase === HandoffPhase.Sending || phase === HandoffPhase.Working) {
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
        {question && <StatusCallout tone={CanvasSourceTone.Warning} message={question} />}
        {error && <StatusCallout tone={CanvasSourceTone.Error} message={error} />}

        {prompt && <CopyPrompt prompt={prompt} />}

        <div className="border-t border-border px-5 py-3">
          <p className="text-xs text-muted-foreground">
            Keep this open to watch status. Or copy the prompt and paste it into your agent.
          </p>
        </div>
      </div>
    )
  }

  if (phase === HandoffPhase.Done) {
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

  if (phase === HandoffPhase.NeedsInput || phase === HandoffPhase.Blocked || phase === HandoffPhase.Stopped) {
    const blocked = phase === HandoffPhase.Blocked || phase === HandoffPhase.Stopped
    const needsInputItems = items.filter((item) => item.status === HandoffItemStatus.NeedsInput)
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
        {!blocked &&
          needsInputItems.map((item) => (
            <AnswerQuestion key={item.pendingId || item.changeId} item={item} onAnswer={answerHandoffQuestion} />
          ))}
        {prompt && <CopyPrompt prompt={prompt} />}
        <div className="border-t border-border px-5 py-4">
          <Button onClick={onDismiss}>Got it</Button>
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
  [HandoffItemStatus.Queued]: {
    label: "Creating",
    detail: "Writing pending files",
    Icon: Clock,
    iconClassName: "text-muted-foreground",
    badgeClassName: "border-border bg-secondary text-muted-foreground",
  },
  [HandoffItemStatus.Sent]: {
    label: "Sent",
    detail: "Pending file created",
    Icon: Clock,
    iconClassName: "text-muted-foreground",
    badgeClassName: "border-border bg-secondary text-muted-foreground",
  },
  [HandoffItemStatus.InProgress]: {
    label: "In progress",
    detail: "Agent started work",
    Icon: Loader2,
    iconClassName: "animate-spin text-primary",
    badgeClassName: "border-primary/20 bg-accent text-accent-foreground",
  },
  [HandoffItemStatus.Implemented]: {
    label: "Implemented",
    detail: "Waiting for verification",
    Icon: Clock,
    iconClassName: "text-primary",
    badgeClassName: "border-primary/20 bg-accent text-accent-foreground",
  },
  [HandoffItemStatus.Verified]: {
    label: "Verified",
    detail: "Checks passed",
    Icon: CircleCheck,
    iconClassName: "text-act-fg",
    badgeClassName: "border-act-accent/20 bg-act-bg text-act-fg",
  },
  [HandoffItemStatus.Done]: {
    label: "Done",
    detail: "Implemented",
    Icon: CircleCheck,
    iconClassName: "text-act-fg",
    badgeClassName: "border-act-accent/20 bg-act-bg text-act-fg",
  },
  [HandoffItemStatus.NeedsInput]: {
    label: "Needs input",
    detail: "Waiting on a reply",
    Icon: AlertCircle,
    iconClassName: "text-when-fg",
    badgeClassName: "border-when-accent/30 bg-when-bg text-when-fg",
  },
  [HandoffItemStatus.Blocked]: {
    label: "Blocked",
    detail: "Cannot continue yet",
    Icon: AlertCircle,
    iconClassName: "text-destructive",
    badgeClassName: "border-destructive/20 bg-destructive/10 text-destructive",
  },
  [HandoffItemStatus.Cancelled]: {
    label: "Cancelled",
    detail: "Stopped before completion",
    Icon: AlertCircle,
    iconClassName: "text-muted-foreground",
    badgeClassName: "border-border bg-secondary text-muted-foreground",
  },
  [HandoffItemStatus.Rejected]: {
    label: "Rejected",
    detail: "Will not be applied",
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

function StatusCallout({ tone, message }: { tone: CanvasSourceTone.Warning | CanvasSourceTone.Error; message: string }) {
  return (
    <div
      className={cn(
        "mx-5 mb-4 rounded-md border px-3 py-2 text-xs",
        tone === CanvasSourceTone.Error
          ? "border-destructive/20 bg-destructive/10 text-destructive"
          : "border-when-accent/30 bg-when-bg text-when-fg"
      )}
    >
      {message}
    </div>
  )
}

function AnswerQuestion({
  item,
  onAnswer,
}: {
  item: HandoffItem
  onAnswer: (pendingId: string, answer: string) => Promise<void>
}) {
  const [answer, setAnswer] = useState("")
  const [submitting, setSubmitting] = useState(false)
  const question = item.conversationSummary?.unansweredQuestion?.text || item.note || "What should your agent know?"
  const canSubmit = Boolean(item.pendingId && answer.trim()) && !submitting

  async function submit() {
    if (!item.pendingId || !answer.trim()) return
    setSubmitting(true)
    try {
      await onAnswer(item.pendingId, answer)
      setAnswer("")
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="mx-5 mb-4 rounded-md border border-when-accent/30 bg-when-bg/40 p-3">
      <div className="flex flex-col gap-2">
        <p className="text-xs font-medium uppercase tracking-wide text-when-fg">Question</p>
        <p className="text-sm leading-snug text-foreground">{question}</p>
        {item.conversation?.length ? <ConversationThread item={item} /> : null}
        <Textarea
          value={answer}
          onChange={(event) => setAnswer(event.target.value)}
          placeholder="Type your answer..."
          className="min-h-20 bg-background text-sm"
        />
        <div className="flex items-center justify-end gap-2">
          <Button type="button" variant="ghost" size="sm" onClick={() => setAnswer("")} disabled={!answer || submitting}>
            Clear
          </Button>
          <Button type="button" size="sm" onClick={submit} disabled={!canSubmit}>
            {submitting ? <Loader2 className="size-3.5 animate-spin" /> : <Send className="size-3.5" />}
            Send answer
          </Button>
        </div>
      </div>
    </div>
  )
}

function ConversationThread({ item }: { item: HandoffItem }) {
  const turns = item.conversation || []
  if (!turns.length) return null
  return (
    <ScrollArea className="max-h-36 rounded-md border bg-background/70">
      <div className="flex flex-col gap-2 px-2.5 py-2">
        {turns.map((turn) => (
          <div key={turn.id} className="text-xs leading-snug">
            <span
              className={cn(
                "mr-1.5 rounded-md px-1.5 py-0.5 font-medium",
                turn.role === ConversationRole.User ? "bg-act-bg text-act-fg" : "bg-secondary text-muted-foreground",
                turn.kind === ConversationTurnKind.Question && "bg-when-bg text-when-fg"
              )}
            >
              {conversationLabel(turn.role, turn.kind)}
            </span>
            <span className="text-muted-foreground">{turn.text}</span>
          </div>
        ))}
      </div>
    </ScrollArea>
  )
}

function conversationLabel(role: ConversationRole, kind: ConversationTurnKind): string {
  if (kind === ConversationTurnKind.Question) return "Question"
  if (kind === ConversationTurnKind.Answer) return "Answer"
  return role === ConversationRole.User ? "You" : "Agent"
}

function CopyPrompt({ prompt }: { prompt: string }) {
  const [copyState, setCopyState] = useState<CopyState>(CopyState.Idle)
  async function copy() {
    try {
      await navigator.clipboard.writeText(prompt)
      setCopyState(CopyState.Copied)
      window.setTimeout(() => setCopyState(CopyState.Idle), 1600)
    } catch {
      setCopyState(CopyState.Manual)
    }
  }

  return (
    <div className="mx-5 mb-4 rounded-md border bg-secondary/30">
      <div className="flex items-center justify-between gap-3 border-b px-3 py-2">
        <p className="text-xs font-medium text-muted-foreground">Copy fallback prompt</p>
        <Button variant="outline" size="sm" onClick={copy}>
          {copyState === CopyState.Copied ? <Check className="h-3.5 w-3.5" /> : <Clipboard className="h-3.5 w-3.5" />}
          {copyState === CopyState.Copied ? "Copied" : "Copy"}
        </Button>
      </div>
      {copyState === CopyState.Manual && (
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
