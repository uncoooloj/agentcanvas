import { useEffect, useRef, useState } from "react"
import { ArrowUp, Trash2, X } from "lucide-react"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import {
  buildSummary,
  EDIT_META,
  nodeLabel,
  type EditRequest,
  type StagedEdit,
} from "@/lib/edits"

interface Props {
  request: EditRequest
  onSubmit: (edit: StagedEdit) => void
  onCancel: () => void
}

export function StepComposer({ request, onSubmit, onCancel }: Props) {
  const meta = EDIT_META[request.action]
  const label = nodeLabel(request.node)
  const [first, setFirst] = useState(request.initialText1 ?? "")
  const [second, setSecond] = useState(request.initialText2 ?? "")
  const firstRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    setFirst(request.initialText1 ?? "")
    setSecond(request.initialText2 ?? "")
    const t = window.setTimeout(() => firstRef.current?.focus(), 30)
    return () => window.clearTimeout(t)
  }, [request])

  const canSubmit =
    meta.field === "reason" ? true : meta.field === "double" ? first.trim() && second.trim() : first.trim()

  function submit() {
    if (!canSubmit) return
    const t1 = first.trim()
    const t2 = second.trim()
    onSubmit({
      action: request.action,
      node: request.node,
      journeyTitle: request.journeyTitle,
      summary: buildSummary(request.action, label, t1, t2),
      changeId: request.changeId,
      text1: t1 || undefined,
      text2: t2 || undefined,
    })
  }

  function onKey(e: React.KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey && meta.field !== "double") {
      e.preventDefault()
      submit()
    }
    if (e.key === "Escape") onCancel()
  }

  return (
    <div className="w-full max-w-2xl animate-fade-in rounded-xl border bg-card p-3 shadow-lg">
      <div className="mb-2 flex items-center justify-between gap-2 px-1">
        <div className="flex min-w-0 items-center gap-2">
          <Badge
            variant="secondary"
            className={cn("shrink-0", meta.danger && "bg-destructive/10 text-destructive")}
          >
            {meta.title}
          </Badge>
          <span className="truncate text-xs text-muted-foreground">{meta.context(label)}</span>
        </div>
        <button
          type="button"
          aria-label="Cancel"
          onClick={onCancel}
          className="shrink-0 rounded-md p-1 text-muted-foreground hover:bg-secondary hover:text-foreground"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      {meta.field === "double" ? (
        <div className="flex flex-col gap-2">
          <Input
            ref={firstRef}
            placeholder={meta.firstPlaceholder}
            value={first}
            onChange={(e) => setFirst(e.target.value)}
            onKeyDown={onKey}
          />
          <div className="flex items-center gap-2">
            <Input
              placeholder={meta.secondPlaceholder}
              value={second}
              onChange={(e) => setSecond(e.target.value)}
              onKeyDown={onKey}
            />
            <Button onClick={submit} disabled={!canSubmit} className="shrink-0">
              {request.changeId ? "Update" : meta.cta}
            </Button>
          </div>
        </div>
      ) : meta.field === "reason" ? (
        <div className="flex items-center gap-2">
          <Input
            ref={firstRef}
            placeholder={meta.firstPlaceholder}
            value={first}
            onChange={(e) => setFirst(e.target.value)}
            onKeyDown={onKey}
          />
          <Button variant="destructive" onClick={submit} className="shrink-0">
            <Trash2 className="h-4 w-4" />
            {request.changeId ? "Update" : meta.cta}
          </Button>
        </div>
      ) : (
        <div className="flex items-center gap-2">
          <Input
            ref={firstRef}
            placeholder={meta.firstPlaceholder}
            value={first}
            onChange={(e) => setFirst(e.target.value)}
            onKeyDown={onKey}
          />
          <Button
            size="icon"
            onClick={submit}
            disabled={!canSubmit}
            aria-label={request.changeId ? "Update" : meta.cta}
            className="shrink-0 rounded-full"
          >
            <ArrowUp className="h-4 w-4" />
          </Button>
        </div>
      )}
    </div>
  )
}
