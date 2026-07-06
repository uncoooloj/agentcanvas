import { useEffect, useMemo, useState } from "react"
import { GitPullRequestArrow, History, ListChecks } from "lucide-react"
import { describeApiError, fetchCanvasHistory, fetchPending } from "@/lib/api"
import {
  pendingStatusLabel,
  type CanvasHistoryEntry,
  type CanvasHistoryResponse,
  type PendingItem,
  type PendingStatusHistoryEntry,
} from "@/lib/types"
import { Badge } from "@/components/ui/badge"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { ScrollArea } from "@/components/ui/scroll-area"

enum ActivityEventKind {
  Canvas = "canvas",
  Pending = "pending",
}

interface ActivityEvent {
  id: string
  kind: ActivityEventKind
  title: string
  detail: string
  at?: string
}

export function ActivityDialog({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const [history, setHistory] = useState<CanvasHistoryResponse | null>(null)
  const [pending, setPending] = useState<PendingItem[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!open) return
    let cancelled = false
    setLoading(true)
    setError(null)

    Promise.allSettled([fetchCanvasHistory(), fetchPending()])
      .then(([historyResult, pendingResult]) => {
        if (cancelled) return
        if (historyResult.status === "fulfilled") {
          setHistory(historyResult.value)
        } else {
          setHistory(null)
        }
        if (pendingResult.status === "fulfilled") {
          setPending(pendingResult.value)
        } else {
          setPending([])
        }
        const failures = [historyResult, pendingResult].filter((result) => result.status === "rejected")
        setError(failures.length ? describeApiError(failures[0].reason) : null)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [open])

  const events = useMemo(() => buildActivityEvents(history, pending), [history, pending])

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[86vh] max-w-2xl grid-rows-[auto,minmax(0,1fr)] gap-0 overflow-hidden p-0">
        <DialogHeader className="border-b px-5 py-4">
          <DialogTitle className="flex items-center gap-2 text-base font-semibold">
            <ListChecks className="size-4 text-muted-foreground" />
            Activity
          </DialogTitle>
          <DialogDescription>
            Recent map saves and agent request updates.
          </DialogDescription>
        </DialogHeader>

        <ScrollArea className="min-h-0 px-5 py-4">
          {error && (
            <div className="mb-3 rounded-md border border-when-accent/25 bg-when-bg/30 px-3 py-2 text-sm text-when-fg">
              Some activity could not be loaded: {error}
            </div>
          )}
          {loading ? (
            <ActivitySkeleton />
          ) : events.length ? (
            <ol className="space-y-2">
              {events.map((event) => (
                <ActivityRow key={event.id} event={event} />
              ))}
            </ol>
          ) : (
            <div className="rounded-md border border-dashed px-4 py-8 text-center text-sm text-muted-foreground">
              No activity yet.
            </div>
          )}
        </ScrollArea>
      </DialogContent>
    </Dialog>
  )
}

function ActivityRow({ event }: { event: ActivityEvent }) {
  const Icon = event.kind === ActivityEventKind.Canvas ? History : GitPullRequestArrow
  return (
    <li className="rounded-md border bg-background px-3 py-3">
      <div className="flex gap-3">
        <span className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-md bg-secondary text-muted-foreground">
          <Icon className="size-4" />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-sm font-medium text-foreground">{event.title}</p>
            <Badge variant="outline">{event.kind === ActivityEventKind.Canvas ? "Map" : "Agent"}</Badge>
          </div>
          <p className="mt-1 text-sm leading-snug text-muted-foreground">{event.detail}</p>
          <p className="mt-1 text-xs text-muted-foreground">{formatDate(event.at)}</p>
        </div>
      </div>
    </li>
  )
}

function ActivitySkeleton() {
  return (
    <div className="space-y-2">
      {[0, 1, 2].map((index) => (
        <div key={index} className="rounded-md border px-3 py-3">
          <div className="h-4 w-36 rounded bg-muted" />
          <div className="mt-2 h-3 w-full max-w-sm rounded bg-muted" />
        </div>
      ))}
    </div>
  )
}

function buildActivityEvents(history: CanvasHistoryResponse | null, pending: PendingItem[]): ActivityEvent[] {
  const events: ActivityEvent[] = []
  if (history?.current) events.push(canvasEvent(history.current, "Current map version"))
  for (const entry of history?.history ?? []) {
    events.push(canvasEvent(entry, `Saved map revision ${entry.revision}`))
  }
  for (const item of pending) {
    const statusHistory = item.statusHistory?.length
      ? item.statusHistory
      : [{ status: item.status, updatedAt: item.updatedAt || item.createdAt, note: item.note }]
    for (const [index, status] of statusHistory.entries()) {
      events.push(pendingEvent(item, status, index))
    }
  }
  return events.sort(compareActivityEvents).slice(0, 40)
}

function canvasEvent(entry: CanvasHistoryEntry, title: string): ActivityEvent {
  return {
    id: `canvas:${entry.revision}:${entry.updatedAt || entry.path || "unknown"}`,
    kind: ActivityEventKind.Canvas,
    title,
    detail: `${flowSummary(entry)}${entry.authoredBy ? ` saved by ${entry.authoredBy}` : ""}.`,
    at: entry.updatedAt || undefined,
  }
}

function pendingEvent(item: PendingItem, status: PendingStatusHistoryEntry, index: number): ActivityEvent {
  return {
    id: `pending:${item.id}:${index}:${status.status}`,
    kind: ActivityEventKind.Pending,
    title: `${item.title || item.id}: ${pendingStatusLabel(status.status)}`,
    detail: status.note || item.note || item.summary || item.target || "Agent request updated.",
    at: status.updatedAt || item.updatedAt || item.createdAt,
  }
}

function compareActivityEvents(a: ActivityEvent, b: ActivityEvent): number {
  const aTime = timestamp(a.at)
  const bTime = timestamp(b.at)
  return bTime - aTime || a.id.localeCompare(b.id)
}

function timestamp(value?: string): number {
  if (!value) return 0
  const parsed = Date.parse(value)
  return Number.isNaN(parsed) ? 0 : parsed
}

function flowSummary(entry: CanvasHistoryEntry): string {
  const summary = entry.flowSummary
  if (!summary) return `Revision ${entry.revision}`
  if (summary.count === 0) return "No flows"
  const named = summary.titles.length ? summary.titles.join(", ") : `${summary.count} flow${summary.count === 1 ? "" : "s"}`
  return `${summary.count} flow${summary.count === 1 ? "" : "s"}: ${named}${summary.truncated ? ", and more" : ""}`
}

function formatDate(value?: string): string {
  if (!value) return "Time unknown"
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  })
}
