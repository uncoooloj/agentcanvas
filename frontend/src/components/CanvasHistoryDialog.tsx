import { useEffect, useMemo, useState } from "react"
import { Clock3, RotateCcw } from "lucide-react"
import { ApiError, describeApiError, fetchCanvasHistory, restoreCanvasRevision } from "@/lib/api"
import type { CanvasHistoryEntry, CanvasHistoryResponse } from "@/lib/types"
import { cn } from "@/lib/utils"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Separator } from "@/components/ui/separator"

enum CanvasHistoryErrorCode {
  RevisionConflict = "REVISION_CONFLICT",
}

export function CanvasHistoryDialog({
  open,
  onOpenChange,
  currentRevision,
  onRestored,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  currentRevision?: number | null
  onRestored: () => Promise<void> | void
}) {
  const [history, setHistory] = useState<CanvasHistoryResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [restoringRevision, setRestoringRevision] = useState<number | null>(null)
  const [confirmEntry, setConfirmEntry] = useState<CanvasHistoryEntry | null>(null)
  const [error, setError] = useState<string | null>(null)

  const activeRevision = history?.currentRevision ?? currentRevision ?? null
  const latestSnapshot = history?.history[0] ?? null

  useEffect(() => {
    if (!open) return
    let cancelled = false
    setLoading(true)
    setError(null)
    setConfirmEntry(null)

    fetchCanvasHistory()
      .then((payload) => {
        if (!cancelled) setHistory(payload)
      })
      .catch((caught) => {
        if (!cancelled) setError(describeApiError(caught))
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [open])

  const entries = useMemo(() => {
    if (!history) return []
    return [history.current, ...history.history].filter((entry): entry is CanvasHistoryEntry => Boolean(entry))
  }, [history])

  async function restore(entry: CanvasHistoryEntry) {
    if (activeRevision == null) return
    setRestoringRevision(entry.revision)
    setError(null)
    try {
      await restoreCanvasRevision({
        revision: entry.revision,
        baseRevision: activeRevision,
        authoredBy: "agentcanvas-web",
      })
      await onRestored()
      onOpenChange(false)
    } catch (caught) {
      if (caught instanceof ApiError && caught.code === CanvasHistoryErrorCode.RevisionConflict) {
        setError("This map changed since history was opened. Refresh the history and try again.")
      } else {
        setError(describeApiError(caught))
      }
    } finally {
      setRestoringRevision(null)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[86vh] max-w-2xl grid-rows-[auto,minmax(0,1fr)] gap-0 overflow-hidden p-0">
        <DialogHeader className="border-b px-5 py-4">
          <div className="flex items-start justify-between gap-4 pr-8">
            <div>
              <DialogTitle className="flex items-center gap-2 text-base font-semibold">
                <Clock3 className="size-4 text-muted-foreground" />
                Canvas history
              </DialogTitle>
              <DialogDescription className="mt-1">
                Restore an earlier plain-English map as a new saved version.
              </DialogDescription>
            </div>
            <Button
              variant="outline"
              size="sm"
              disabled={!latestSnapshot || loading || restoringRevision != null}
              onClick={() => latestSnapshot && setConfirmEntry(latestSnapshot)}
            >
              <RotateCcw className="size-3.5" />
              Undo latest
            </Button>
          </div>
        </DialogHeader>

        <div className="min-h-0 space-y-4 overflow-y-auto px-5 py-4">
          {error && (
            <div className="rounded-md border border-destructive/25 bg-destructive/10 px-3 py-2 text-sm text-destructive">
              {error}
            </div>
          )}

          {confirmEntry && (
            <div className="rounded-md border bg-secondary/40 p-3">
              <div className="text-sm font-semibold">Restore revision {confirmEntry.revision}?</div>
              <p className="mt-1 text-sm text-muted-foreground">
                This creates a new revision from that snapshot. The current saved map stays in history.
              </p>
              <p className="mt-2 text-sm text-muted-foreground">
                Includes {flowSummary(confirmEntry)}.
              </p>
              <div className="mt-3 flex flex-wrap justify-end gap-2">
                <Button
                  variant="ghost"
                  size="sm"
                  disabled={restoringRevision != null}
                  onClick={() => setConfirmEntry(null)}
                >
                  Cancel
                </Button>
                <Button
                  size="sm"
                  disabled={activeRevision == null || restoringRevision != null}
                  onClick={() => restore(confirmEntry)}
                >
                  {restoringRevision === confirmEntry.revision ? "Restoring..." : "Restore this version"}
                </Button>
              </div>
            </div>
          )}

          <div className="space-y-2">
            {loading ? (
              <HistorySkeleton />
            ) : entries.length ? (
              entries.map((entry) => (
                <HistoryRow
                  key={`${entry.revision}-${entry.path || "current"}`}
                  entry={entry}
                  isCurrent={entry.revision === activeRevision}
                  disabled={restoringRevision != null}
                  onRestore={() => setConfirmEntry(entry)}
                />
              ))
            ) : (
              <div className="rounded-md border border-dashed px-4 py-8 text-center text-sm text-muted-foreground">
                No earlier versions yet.
              </div>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}

function HistoryRow({
  entry,
  isCurrent,
  disabled,
  onRestore,
}: {
  entry: CanvasHistoryEntry
  isCurrent: boolean
  disabled: boolean
  onRestore: () => void
}) {
  const opSummary = operationSummary(entry)

  return (
    <div
      className={cn(
        "rounded-md border px-3 py-3",
        isCurrent ? "border-primary/25 bg-primary/5" : "bg-background",
      )}
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0 space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-semibold">Revision {entry.revision}</span>
            {isCurrent && <Badge variant="secondary">Current</Badge>}
            {entry.allowRewriteReason && <Badge variant="outline">Rewrite allowed</Badge>}
          </div>
          <div className="text-xs text-muted-foreground">
            {formatDate(entry.updatedAt)} {entry.authoredBy ? `by ${entry.authoredBy}` : ""}
          </div>
          <div className="text-sm text-muted-foreground">{flowSummary(entry)}</div>
          {opSummary && (
            <>
              <Separator className="my-2" />
              <div className="text-xs text-muted-foreground">{opSummary}</div>
            </>
          )}
        </div>
        <Button variant="outline" size="sm" disabled={isCurrent || disabled} onClick={onRestore}>
          Restore
        </Button>
      </div>
    </div>
  )
}

function HistorySkeleton() {
  return (
    <>
      {[0, 1, 2].map((index) => (
        <div key={index} className="rounded-md border px-3 py-3">
          <div className="h-4 w-32 rounded bg-muted" />
          <div className="mt-2 h-3 w-52 rounded bg-muted" />
          <div className="mt-3 h-3 w-full max-w-sm rounded bg-muted" />
        </div>
      ))}
    </>
  )
}

function flowSummary(entry: CanvasHistoryEntry): string {
  const summary = entry.flowSummary
  if (!summary) return "the saved map"
  if (summary.count === 0) return "no flows"
  const named = summary.titles.length ? summary.titles.join(", ") : `${summary.count} flow${summary.count === 1 ? "" : "s"}`
  return `${summary.count} flow${summary.count === 1 ? "" : "s"}: ${named}${summary.truncated ? ", and more" : ""}`
}

function operationSummary(entry: CanvasHistoryEntry): string | null {
  const summary = entry.opSummary
  if (!summary) return null
  const parts = [
    countLabel(summary.operation_count, "operation"),
    countLabel(summary.deleted_node_count, "removed step"),
    countLabel(summary.deleted_flow_count, "removed flow"),
  ].filter(Boolean)
  return parts.length ? parts.join(" | ") : null
}

function countLabel(value: unknown, label: string): string | null {
  if (typeof value !== "number" || value <= 0) return null
  return `${value} ${label}${value === 1 ? "" : "s"}`
}

function formatDate(value?: string | null): string {
  if (!value) return "Saved time unknown"
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  })
}
