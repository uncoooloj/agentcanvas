import { useEffect, useRef, useState } from "react"
import { ArrowUp, Trash2, X } from "lucide-react"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import {
  buildSummary,
  canSaveToMapAction,
  EDIT_META,
  EditDelivery,
  FieldKind,
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
  const [delivery, setDelivery] = useState(EditDelivery.CanvasMap)
  const firstRef = useRef<HTMLInputElement>(null)
  const canSaveToMap = !request.changeId && canSaveToMapAction(request.action) && Boolean(request.node.native?.nodeId)

  useEffect(() => {
    setFirst(request.initialText1 ?? "")
    setSecond(request.initialText2 ?? "")
    setDelivery(
      !request.changeId && canSaveToMapAction(request.action) && request.node.native?.nodeId
        ? EditDelivery.CanvasMap
        : EditDelivery.ImplementationRequest
    )
    const t = window.setTimeout(() => firstRef.current?.focus(), 30)
    return () => window.clearTimeout(t)
  }, [request])

  const canSubmit =
    meta.field === FieldKind.Reason ? true : meta.field === FieldKind.Double ? first.trim() && second.trim() : first.trim()

  function submit(deliveryOverride = delivery) {
    if (!canSubmit) return
    const selectedDelivery = canSaveToMap ? deliveryOverride : EditDelivery.ImplementationRequest
    const t1 = first.trim()
    const t2 = second.trim()
    onSubmit({
      action: request.action,
      node: request.node,
      journeyTitle: request.journeyTitle,
      summary: buildSummary(request.action, label, t1, t2),
      changeId: request.changeId,
      delivery: selectedDelivery,
      text1: t1 || undefined,
      text2: t2 || undefined,
    })
  }

  function onKey(e: React.KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey && meta.field !== FieldKind.Double) {
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

      {canSaveToMap && (
        <div className="mb-2 grid grid-cols-2 gap-1 rounded-lg bg-secondary p-1">
          <DeliveryOption
            active={delivery === EditDelivery.CanvasMap}
            title="Fix map"
            detail="Update what this picture shows."
            onClick={() => setDelivery(EditDelivery.CanvasMap)}
          />
          <DeliveryOption
            active={delivery === EditDelivery.ImplementationRequest}
            title="Change app"
            detail="Ask your assistant to change how the app works."
            onClick={() => setDelivery(EditDelivery.ImplementationRequest)}
          />
        </div>
      )}

      {meta.field === FieldKind.Double ? (
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
            <Button onClick={() => submit()} disabled={!canSubmit} className="shrink-0">
              {request.changeId ? "Update" : meta.cta}
            </Button>
          </div>
        </div>
      ) : meta.field === FieldKind.Reason ? (
        <div className="flex items-center gap-2">
          <Input
            ref={firstRef}
            placeholder={meta.firstPlaceholder}
            value={first}
            onChange={(e) => setFirst(e.target.value)}
            onKeyDown={onKey}
          />
          <Button variant="destructive" onClick={() => submit()} className="shrink-0">
            <Trash2 className="h-4 w-4" />
            {request.changeId ? "Update" : meta.cta}
          </Button>
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          <div className="flex items-center gap-2">
            <Input
              ref={firstRef}
              placeholder={meta.firstPlaceholder}
              value={first}
              onChange={(e) => setFirst(e.target.value)}
              onKeyDown={onKey}
            />
            <Button
              size={canSaveToMap ? "default" : "icon"}
              onClick={() => submit()}
              disabled={!canSubmit}
              aria-label={request.changeId ? "Update" : delivery === EditDelivery.CanvasMap ? "Save to map" : meta.cta}
              className={cn("shrink-0", canSaveToMap ? "rounded-lg" : "rounded-full")}
            >
              {canSaveToMap ? (
                delivery === EditDelivery.CanvasMap ? "Save to map" : "Ask agent"
              ) : (
                <ArrowUp className="h-4 w-4" />
              )}
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}

function DeliveryOption({
  active,
  title,
  detail,
  onClick,
}: {
  active: boolean
  title: string
  detail: string
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "rounded-md px-3 py-2 text-left transition-colors",
        active ? "bg-card shadow-sm" : "text-muted-foreground hover:bg-background/60"
      )}
    >
      <span className="block text-xs font-medium text-foreground">{title}</span>
      <span className="mt-0.5 block text-[11px] leading-snug text-muted-foreground">{detail}</span>
    </button>
  )
}
