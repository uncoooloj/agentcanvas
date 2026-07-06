import { useMemo, useState, type ComponentType } from "react"
import { ChevronDown, CornerDownRight, Pencil, Plus, Split, Trash2, X } from "lucide-react"
import { cn } from "@/lib/utils"
import { ROLE, RuleRole } from "@/lib/roles"
import { Button } from "@/components/ui/button"
import { ChangeKind, useChanges, type ChangeEntry } from "@/lib/changeset"
import { FlowAction, FlowNodeKind, StepRole, type FlowNode } from "@/lib/types"

interface Props {
  node: FlowNode | null
  onAction: (action: FlowAction) => void
  onModifyChange: (change: ChangeEntry) => void
  onCancelChange: (id: string) => void
}

export function Inspector({ node, onAction, onModifyChange, onCancelChange }: Props) {
  const [showTech, setShowTech] = useState(false)
  const changes = useChanges((s) => s.changes)
  const queuedNext = useChanges((s) => s.queuedNext)
  const pending = useMemo(
    () => [
      ...changes.filter((c) => c.targetNodeId === node?.id),
      ...queuedNext.filter((c) => c.targetNodeId === node?.id),
    ],
    [changes, node?.id, queuedNext]
  )

  if (!node) return null

  const isBranch = node.kind === FlowNodeKind.Branch
  const headChip = isBranch ? ROLE[RuleRole.If] : ROLE[node.role === StepRole.When ? StepRole.When : StepRole.Do]
  const HeadIcon = headChip.icon

  return (
    <div className="flex h-full flex-col">
      <div className="border-b px-5 py-4">
        <span
          className={cn(
            "inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-[11px] font-medium",
            headChip.chip
          )}
        >
          <HeadIcon className="h-3 w-3" />
          {isBranch ? "Rule" : headChip.label}
        </span>
        <p className="mt-2.5 text-[15px] font-medium leading-snug text-foreground">
          {isBranch ? `If ${node.condition}` : node.text}
        </p>
        {!isBranch && node.detail && (
          <p className="mt-1.5 text-sm text-muted-foreground">{node.detail}</p>
        )}
        {isBranch && (
          <p className="mt-1.5 text-sm text-muted-foreground">
            Two paths: one when this is true, one when it isn't.
          </p>
        )}
      </div>

      <div className="flex flex-col gap-2 px-5 py-4">
        <p className="mb-0.5 text-xs font-medium uppercase tracking-wide text-muted-foreground">
          {isBranch ? "Change this rule" : "Change this step"}
        </p>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          {isBranch ? (
            <>
              <InspectorAction icon={Pencil} label="Change" fullLabel="Change the condition" onClick={() => onAction(FlowAction.ChangeCondition)} />
              <InspectorAction icon={CornerDownRight} label="Yes path" fullLabel="Add a step to the “yes” path" onClick={() => onAction(FlowAction.AddThen)} />
              <InspectorAction icon={CornerDownRight} label="Else path" fullLabel="Add a step to the “otherwise” path" onClick={() => onAction(FlowAction.AddElse)} />
              <InspectorAction icon={Trash2} label="Remove" fullLabel="Remove this rule" danger onClick={() => onAction(FlowAction.Remove)} />
            </>
          ) : (
            <>
              <InspectorAction icon={Pencil} label="Change" fullLabel="Change what happens" onClick={() => onAction(FlowAction.Change)} />
              <InspectorAction icon={Plus} label="Add step" fullLabel="Add a step after this" onClick={() => onAction(FlowAction.AddAfter)} />
              <InspectorAction icon={Split} label="Add rule" fullLabel="Add a rule" onClick={() => onAction(FlowAction.AddRule)} />
              <InspectorAction icon={Trash2} label="Remove" fullLabel="Remove this step" danger onClick={() => onAction(FlowAction.Remove)} />
            </>
          )}
        </div>
      </div>

      {pending.length > 0 && (
        <div className="border-y bg-secondary/30 px-5 py-4">
          <p className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Waiting to update
          </p>
          <div className="flex flex-col gap-2">
            {pending.map((change) => (
              <PendingChange
                key={change.id}
                change={change}
                onModify={() => onModifyChange(change)}
                onCancel={() => onCancelChange(change.id)}
              />
            ))}
          </div>
        </div>
      )}

      {node.tech?.refs?.length ? (
        <div className="mt-auto border-t px-5 py-3">
          <button
            type="button"
            onClick={() => setShowTech((v) => !v)}
            className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
          >
            <ChevronDown className={cn("h-3.5 w-3.5 transition-transform", showTech && "rotate-180")} />
            Show the technical bits
          </button>
          {showTech && (
            <ul className="mt-2 flex flex-col gap-1">
              {node.tech.refs.map((ref) => (
                <li
                  key={ref}
                  className="truncate rounded-md bg-secondary px-2 py-1 font-mono text-xs text-muted-foreground"
                >
                  {ref}
                </li>
              ))}
            </ul>
          )}
        </div>
      ) : null}
    </div>
  )
}

function InspectorAction({
  icon: Icon,
  label,
  fullLabel,
  danger,
  onClick,
}: {
  icon: ComponentType<{ className?: string }>
  label: string
  fullLabel: string
  danger?: boolean
  onClick: () => void
}) {
  return (
    <Button
      variant="outline"
      className={cn(
        "h-auto min-h-14 flex-col gap-1 px-2 py-2 text-xs",
        danger && "border-destructive/30 text-destructive hover:bg-destructive/10 hover:text-destructive"
      )}
      onClick={onClick}
      aria-label={fullLabel}
    >
      <Icon className="h-4 w-4" />
      <span>{label}</span>
    </Button>
  )
}

function PendingChange({
  change,
  onModify,
  onCancel,
}: {
  change: ChangeEntry
  onModify: () => void
  onCancel: () => void
}) {
  return (
    <div className="rounded-lg border bg-card px-3 py-2.5 shadow-sm">
      <div className="flex items-center gap-2">
        <ChangePill kind={change.kind} />
        <span className="text-xs text-muted-foreground">Not sent yet</span>
      </div>
      <p className="mt-2 text-sm leading-snug text-foreground">{changeSummary(change)}</p>
      {change.text1 && (
        <p className="mt-2 rounded-md bg-secondary px-2 py-1.5 text-sm text-foreground">
          {changeValueLabel(change)}
          <span className="font-medium">{change.text1}</span>
        </p>
      )}
      {change.text2 && (
        <p className="mt-1 rounded-md bg-secondary px-2 py-1.5 text-sm text-foreground">
          Then: <span className="font-medium">{change.text2}</span>
        </p>
      )}
      <div className="mt-3 flex items-center gap-2">
        <Button variant="outline" size="sm" className="h-8 flex-1" onClick={onModify}>
          <Pencil className="h-3.5 w-3.5" />
          Modify
        </Button>
        <Button variant="ghost" size="sm" className="h-8 flex-1 text-muted-foreground" onClick={onCancel}>
          <X className="h-3.5 w-3.5" />
          Cancel
        </Button>
      </div>
    </div>
  )
}

function ChangePill({ kind }: { kind: ChangeKind }) {
  const label = kind === ChangeKind.Edited ? "Edited" : kind === ChangeKind.New ? "New" : "Removing"
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-md px-1.5 py-0.5 text-[11px] font-medium",
        kind === ChangeKind.Edited && "bg-when-bg text-when-fg",
        kind === ChangeKind.New && "bg-act-bg text-act-fg",
        kind === ChangeKind.Removing && "bg-destructive/10 text-destructive"
      )}
    >
      {label}
    </span>
  )
}

function changeSummary(change: ChangeEntry): string {
  switch (change.action) {
    case FlowAction.Change:
      return "This step will change to:"
    case FlowAction.ChangeCondition:
      return "This rule will use a new condition:"
    case FlowAction.AddAfter:
      return "A new step will be added after this:"
    case FlowAction.AddRule:
      return "A new rule will be added after this step:"
    case FlowAction.AddThen:
      return "A new step will be added to the yes path:"
    case FlowAction.AddElse:
      return "A new step will be added to the otherwise path:"
    case FlowAction.Remove:
      return change.text1 ? "This will be removed for this reason:" : "This will be removed."
  }
}

function changeValueLabel(change: ChangeEntry): string {
  switch (change.action) {
    case FlowAction.ChangeCondition:
    case FlowAction.AddRule:
      return "If: "
    case FlowAction.Remove:
      return "Reason: "
    default:
      return ""
  }
}
