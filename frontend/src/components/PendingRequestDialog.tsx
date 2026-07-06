import { useEffect, useState } from "react"
import { AlertCircle, FileJson, FileText, Loader2, Send } from "lucide-react"
import {
  answerPendingRequest,
  describeApiError,
  fetchPending,
  fetchPendingRequest,
} from "@/lib/api"
import { cn } from "@/lib/utils"
import {
  ConversationRole,
  ConversationTurnKind,
  PendingStatus,
  pendingStatusLabel,
  type PendingItem,
} from "@/lib/types"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Textarea } from "@/components/ui/textarea"
import type { PendingRequestLink } from "@/components/CanvasV2FlowCanvas"

interface Props {
  link: PendingRequestLink | null
  onOpenChange: (open: boolean) => void
}

export function PendingRequestDialog({ link, onOpenChange }: Props) {
  const open = Boolean(link)
  const [pending, setPending] = useState<PendingItem | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!link) {
      setPending(null)
      setError(null)
      return
    }
    let cancelled = false
    setLoading(true)
    setError(null)
    resolvePendingRequest(link)
      .then((item) => {
        if (!cancelled) setPending(item)
      })
      .catch((reason) => {
        if (cancelled) return
        setPending(null)
        setError(describeApiError(reason))
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [link])

  async function refresh() {
    if (!link) return
    setLoading(true)
    setError(null)
    try {
      setPending(await resolvePendingRequest(link))
    } catch (reason) {
      setPending(null)
      setError(describeApiError(reason))
    } finally {
      setLoading(false)
    }
  }

  async function answer(text: string) {
    if (!pending?.id) return
    await answerPendingRequest(pending.id, text)
    await refresh()
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[86vh] max-w-xl grid-rows-[auto,minmax(0,1fr)] gap-0 overflow-hidden p-0">
        <DialogHeader className="border-b px-5 py-4">
          <DialogTitle className="text-base font-semibold">Pending request</DialogTitle>
          <DialogDescription>
            The agent work linked to this proposed canvas step.
          </DialogDescription>
        </DialogHeader>

        <ScrollArea className="min-h-0 px-5 py-4">
          {loading ? (
            <div className="flex items-center gap-2 rounded-md border bg-secondary/30 px-3 py-3 text-sm text-muted-foreground">
              <Loader2 className="size-4 animate-spin" />
              Loading request...
            </div>
          ) : error ? (
            <div className="rounded-md border border-destructive/20 bg-destructive/10 px-3 py-3 text-sm text-destructive">
              {error}
            </div>
          ) : pending ? (
            <PendingRequestDetails pending={pending} onAnswer={answer} />
          ) : (
            <div className="rounded-md border border-dashed px-3 py-6 text-center text-sm text-muted-foreground">
              No pending request found for this canvas step yet.
            </div>
          )}
        </ScrollArea>
      </DialogContent>
    </Dialog>
  )
}

async function resolvePendingRequest(link: PendingRequestLink): Promise<PendingItem> {
  if (link.pendingRequestId) return fetchPendingRequest(link.pendingRequestId)
  if (!link.clientChangeId) throw new Error("This proposed node is missing a pending request id.")
  const pending = await fetchPending()
  const match = pending.find((item) => item.changeId === link.clientChangeId)
  if (!match) throw new Error(`No pending request found for change ${link.clientChangeId}.`)
  return fetchPendingRequest(match.id)
}

function PendingRequestDetails({
  pending,
  onAnswer,
}: {
  pending: PendingItem
  onAnswer: (answer: string) => Promise<void>
}) {
  return (
    <div className="space-y-4">
      <div className="rounded-md border bg-background px-3 py-3">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant={pending.status === PendingStatus.NeedsInput ? "default" : "secondary"}>
            {pendingStatusLabel(pending.status)}
          </Badge>
          <span className="font-mono text-[11px] text-muted-foreground">{pending.id}</span>
        </div>
        <h3 className="mt-2 text-sm font-semibold text-foreground">{pending.title}</h3>
        {(pending.note || pending.summary || pending.target) && (
          <p className="mt-1 text-sm leading-snug text-muted-foreground">
            {pending.note || pending.summary || pending.target}
          </p>
        )}
        <div className="mt-3 grid gap-1.5">
          <PathRow icon={FileText} label="Markdown" value={pending.markdownPath} />
          <PathRow icon={FileJson} label="JSON" value={pending.jsonPath} />
        </div>
      </div>

      {pending.conversation?.length ? <Conversation turns={pending.conversation} /> : null}
      {pending.status === PendingStatus.NeedsInput && (
        <AnswerBox
          question={pending.conversationSummary?.unansweredQuestion?.text || pending.note || "What should the agent know?"}
          onAnswer={onAnswer}
        />
      )}
    </div>
  )
}

function PathRow({
  icon: Icon,
  label,
  value,
}: {
  icon: typeof FileText
  label: string
  value?: string | null
}) {
  if (!value) return null
  return (
    <div className="flex min-w-0 items-center gap-2 rounded-md bg-secondary/60 px-2 py-1.5 text-xs text-muted-foreground">
      <Icon className="size-3.5 shrink-0" />
      <span className="font-medium text-foreground/70">{label}</span>
      <span className="truncate font-mono">{value}</span>
    </div>
  )
}

function Conversation({ turns }: { turns: NonNullable<PendingItem["conversation"]> }) {
  return (
    <div className="rounded-md border bg-background">
      <div className="border-b px-3 py-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
        Conversation
      </div>
      <div className="space-y-2 px-3 py-3">
        {turns.map((turn) => (
          <div key={turn.id} className="text-sm leading-snug">
            <span
              className={cn(
                "mr-2 rounded-md px-1.5 py-0.5 text-[11px] font-medium",
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
    </div>
  )
}

function AnswerBox({
  question,
  onAnswer,
}: {
  question: string
  onAnswer: (answer: string) => Promise<void>
}) {
  const [answer, setAnswer] = useState("")
  const [submitting, setSubmitting] = useState(false)

  async function submit() {
    const text = answer.trim()
    if (!text || submitting) return
    setSubmitting(true)
    try {
      await onAnswer(text)
      setAnswer("")
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="rounded-md border border-when-accent/30 bg-when-bg/30 p-3">
      <div className="mb-2 flex items-start gap-2">
        <AlertCircle className="mt-0.5 size-4 shrink-0 text-when-fg" />
        <p className="text-sm leading-snug text-foreground">{question}</p>
      </div>
      <Textarea
        value={answer}
        onChange={(event) => setAnswer(event.target.value)}
        placeholder="Type your answer..."
        className="min-h-20 bg-background text-sm"
      />
      <div className="mt-2 flex justify-end">
        <Button size="sm" onClick={submit} disabled={!answer.trim() || submitting}>
          {submitting ? <Loader2 className="size-3.5 animate-spin" /> : <Send className="size-3.5" />}
          Send answer
        </Button>
      </div>
    </div>
  )
}

function conversationLabel(role: ConversationRole, kind: ConversationTurnKind): string {
  if (kind === ConversationTurnKind.Question) return "Question"
  if (kind === ConversationTurnKind.Answer) return "Answer"
  return role === ConversationRole.User ? "You" : "Agent"
}
