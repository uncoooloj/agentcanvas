import type { ReactNode } from "react"
import { ArrowDown, Check, Pencil, Plus, Split, Trash2, X } from "lucide-react"
import { cn } from "@/lib/utils"
import { ROLE } from "@/lib/roles"
import { useChanges, type ChangeKind } from "@/lib/changeset"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import type { BranchNode, FlowNode, StepNode } from "@/lib/types"

function useNodeBadge(nodeId: string): ChangeKind | null {
  return useChanges((s) => {
    const m = s.changes.find((c) => c.targetNodeId === nodeId)
    return m && (m.kind === "edited" || m.kind === "removing") ? m.kind : null
  })
}

export type FlowAction =
  | "change"
  | "add_after"
  | "add_rule"
  | "remove"
  | "change_condition"
  | "add_then"
  | "add_else"

interface CommonProps {
  selectedId: string | null
  onSelect: (id: string) => void
  onAction: (action: FlowAction, node: FlowNode) => void
}

type BranchPresentation = "if" | "elseIf"
type FlowPath = "root" | "then" | "otherwise"

export function FlowColumn({
  nodes,
  depth = 0,
  path = "root",
  ...rest
}: CommonProps & { nodes: FlowNode[]; depth?: number; path?: FlowPath }) {
  if (!nodes.length) {
    return null
  }
  return (
    <div className="flex flex-col">
      {nodes.map((node, i) => (
        <div key={node.id} className="animate-fade-in">
          {node.kind === "step" ? (
            <StepCard node={node} stacked={depth > 0} {...rest} />
          ) : (
            <BranchCard
              node={node}
              depth={depth}
              presentation={path === "otherwise" && i === 0 ? "elseIf" : "if"}
              {...rest}
            />
          )}
          {i < nodes.length - 1 && <Connector />}
        </div>
      ))}
    </div>
  )
}

function StepCard({
  node,
  stacked,
  selectedId,
  onSelect,
  onAction,
}: CommonProps & { node: StepNode; stacked?: boolean }) {
  const role = ROLE[node.role === "when" ? "when" : "do"]
  const Icon = role.icon
  const selected = node.id === selectedId
  const badge = useNodeBadge(node.id)
  const removing = badge === "removing"
  return (
    <div className="group relative">
      <button
        type="button"
        onClick={() => onSelect(node.id)}
        className={cn(
          "flex w-full overflow-hidden rounded-lg border bg-card px-4 py-3.5 text-left transition-all",
          stacked ? "flex-col gap-2" : "items-start gap-3",
          "hover:border-foreground/20 hover:shadow-sm",
          selected ? "border-primary/60 ring-2 ring-primary/15" : "border-border",
          removing && "opacity-60"
        )}
      >
        <span
          className={cn(
            "absolute inset-y-2 left-2 w-1 rounded-full",
            removing ? "bg-destructive" : role.accent
          )}
        />
        <span className="flex items-center gap-2">
          <span
            className={cn(
              "inline-flex shrink-0 items-center gap-1.5 rounded-md px-2 py-1 text-[11px] font-medium",
              role.chip
            )}
          >
            <Icon className="h-3 w-3" />
            {role.label}
          </span>
          {badge && <ChangeBadge kind={badge} />}
        </span>
        <span className={cn("flex min-w-0 flex-col gap-1", stacked ? "w-full pr-1" : "pt-0.5 pr-16")}>
          <span
            className={cn(
              "text-[13px] leading-snug text-foreground",
              removing && "line-through text-muted-foreground"
            )}
          >
            {node.text}
          </span>
          {node.uncertain && (
            <span className="text-xs text-muted-foreground">
              We're not fully sure about this part
            </span>
          )}
        </span>
      </button>
      <HoverActions>
        <ActionIcon label="Change what happens" onClick={() => onAction("change", node)}>
          <Pencil className="h-3.5 w-3.5" />
        </ActionIcon>
        <ActionIcon label="Add a step after" onClick={() => onAction("add_after", node)}>
          <Plus className="h-3.5 w-3.5" />
        </ActionIcon>
        <ActionIcon label="Add a rule" onClick={() => onAction("add_rule", node)}>
          <Split className="h-3.5 w-3.5" />
        </ActionIcon>
        <ActionIcon
          label="Remove this step"
          danger
          onClick={() => onAction("remove", node)}
        >
          <Trash2 className="h-3.5 w-3.5" />
        </ActionIcon>
      </HoverActions>
    </div>
  )
}

function BranchCard({
  node,
  depth,
  presentation,
  selectedId,
  onSelect,
  onAction,
}: CommonProps & { node: BranchNode; depth: number; presentation: BranchPresentation }) {
  const selected = node.id === selectedId
  const sideBySide = depth === 0
  const badge = useNodeBadge(node.id)
  const leadingElseIf = getLeadingElseIf(node.otherwise)
  return (
    <div className="flex flex-col items-stretch">
      <div className="group relative mx-auto w-full max-w-md">
        <button
          type="button"
          onClick={() => onSelect(node.id)}
          className={cn(
            "flex w-full items-center justify-center gap-2 rounded-full border px-4 py-2.5 text-center transition-all",
            "bg-rule-bg hover:shadow-sm",
            selected ? "border-primary/60 ring-2 ring-primary/15" : "border-rule-accent/40",
            badge === "removing" && "opacity-60"
          )}
        >
          <Split className="h-3.5 w-3.5 text-rule-fg" />
          <span
            className={cn(
              "text-[13px] font-medium text-rule-fg",
              badge === "removing" && "line-through"
            )}
          >
            {presentation === "elseIf" ? "Else if" : "If"} {node.condition}
          </span>
          {badge && <ChangeBadge kind={badge} />}
        </button>
        <HoverActions>
          <ActionIcon
            label="Change the condition"
            onClick={() => onAction("change_condition", node)}
          >
            <Pencil className="h-3.5 w-3.5" />
          </ActionIcon>
          <ActionIcon label="Remove this rule" danger onClick={() => onAction("remove", node)}>
            <Trash2 className="h-3.5 w-3.5" />
          </ActionIcon>
        </HoverActions>
      </div>

      <div
        className={cn(
          "mt-3 grid gap-4",
          sideBySide ? "grid-cols-1 sm:grid-cols-2" : "grid-cols-1"
        )}
      >
        <Lane
          tone="yes"
          label={`If yes — ${node.condition}`.slice(0, 52)}
          empty="Nothing else happens"
          isEmpty={node.then.length === 0}
          onAdd={() => onAction("add_then", node)}
        >
          <FlowColumn
            nodes={node.then}
            depth={depth + 1}
            path="then"
            selectedId={selectedId}
            onSelect={onSelect}
            onAction={onAction}
          />
        </Lane>
        <Lane
          tone="no"
          label={
            leadingElseIf
              ? `Else if — ${leadingElseIf.condition}`.slice(0, 52)
              : `Otherwise — if not ${node.condition}`.slice(0, 52)
          }
          empty="Nothing else happens"
          isEmpty={node.otherwise.length === 0}
          onAdd={() => onAction("add_else", node)}
        >
          <FlowColumn
            nodes={node.otherwise}
            depth={depth + 1}
            path="otherwise"
            selectedId={selectedId}
            onSelect={onSelect}
            onAction={onAction}
          />
        </Lane>
      </div>
    </div>
  )
}

function getLeadingElseIf(nodes: FlowNode[]): BranchNode | null {
  const first = nodes[0]
  return first?.kind === "branch" ? first : null
}

function Lane({
  tone,
  label,
  empty,
  isEmpty,
  onAdd,
  children,
}: {
  tone: "yes" | "no"
  label: string
  empty: string
  isEmpty: boolean
  onAdd: () => void
  children: ReactNode
}) {
  return (
    <div
      className={cn(
        "rounded-xl border border-dashed p-3",
        tone === "yes" ? "border-act-accent/40 bg-act-bg/30" : "border-border bg-secondary/30"
      )}
    >
      <div className="mb-2 flex items-center gap-1.5 px-1">
        <span
          className={cn(
            "inline-flex h-4 w-4 items-center justify-center rounded-full text-white",
            tone === "yes" ? "bg-act-accent" : "bg-muted-foreground"
          )}
        >
          {tone === "yes" ? <Check className="h-2.5 w-2.5" /> : <X className="h-2.5 w-2.5" />}
        </span>
        <span className="truncate text-xs font-medium text-muted-foreground">{label}</span>
      </div>
      {isEmpty ? (
        <p className="px-1 py-2 text-xs italic text-muted-foreground/70">{empty}</p>
      ) : (
        children
      )}
      <button
        type="button"
        onClick={onAdd}
        className="mt-2 flex w-full items-center justify-center gap-1.5 rounded-lg border border-dashed border-border py-2 text-xs text-muted-foreground transition-colors hover:border-foreground/30 hover:text-foreground"
      >
        <Plus className="h-3 w-3" /> Add a step
      </button>
    </div>
  )
}

function HoverActions({ children }: { children: ReactNode }) {
  return (
    <div className="pointer-events-none absolute right-2 top-1/2 flex -translate-y-1/2 items-center gap-1 rounded-lg border bg-card/95 p-1 opacity-0 shadow-sm backdrop-blur transition-opacity group-hover:pointer-events-auto group-hover:opacity-100 group-focus-within:pointer-events-auto group-focus-within:opacity-100">
      {children}
    </div>
  )
}

function ActionIcon({
  label,
  danger,
  onClick,
  children,
}: {
  label: string
  danger?: boolean
  onClick: () => void
  children: ReactNode
}) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          aria-label={label}
          onClick={onClick}
          className={cn(
            "flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-secondary",
            danger ? "hover:text-destructive" : "hover:text-foreground"
          )}
        >
          {children}
        </button>
      </TooltipTrigger>
      <TooltipContent>{label}</TooltipContent>
    </Tooltip>
  )
}

function Connector() {
  return (
    <div className="flex h-6 items-center justify-center" aria-hidden="true">
      <div className="flex h-full flex-col items-center">
        <div className="w-px flex-1 bg-border" />
        <ArrowDown className="h-3 w-3 text-muted-foreground/50" />
        <div className="w-px flex-1 bg-border" />
      </div>
    </div>
  )
}

function ChangeBadge({ kind }: { kind: ChangeKind }) {
  const label = kind === "edited" ? "Edited" : "Removing"
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center rounded-md px-1.5 py-0.5 text-[10px] font-medium",
        kind === "edited" ? "bg-when-bg text-when-fg" : "bg-destructive/10 text-destructive"
      )}
    >
      {label}
    </span>
  )
}
