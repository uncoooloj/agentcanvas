import { Pencil, Plus, Send, Trash2, X } from "lucide-react"
import { cn } from "@/lib/utils"
import { useChanges, type ChangeEntry, type ChangeKind } from "@/lib/changeset"
import { Button } from "@/components/ui/button"
import { ScrollArea } from "@/components/ui/scroll-area"

// ---- Kind badge config ----

interface KindConfig {
  label: string
  className: string
  Icon: React.ComponentType<{ className?: string }>
}

const KIND_CONFIG: Record<ChangeKind, KindConfig> = {
  new: {
    label: "New",
    className: "bg-act-bg text-act-fg",
    Icon: Plus,
  },
  edited: {
    label: "Edited",
    className: "bg-when-bg text-when-fg",
    Icon: Pencil,
  },
  removing: {
    label: "Removing",
    className: "bg-destructive/10 text-destructive",
    Icon: Trash2,
  },
}

interface Props {
  onSelectChange: (change: ChangeEntry) => void
  onModifyChange: (change: ChangeEntry) => void
}

// ---- Component ----

export function ChangeTray({ onSelectChange, onModifyChange }: Props) {
  const { changes, handoff, assistantName, undoChange, discardAll, send } = useChanges()

  if (changes.length === 0 || handoff.phase !== "composing") return null

  const count = changes.length
  const headingText = `${count} ${count === 1 ? "change" : "changes"} ready`

  return (
    <div
      className={cn(
        "w-full max-w-2xl rounded-lg border bg-card shadow-lg",
        "animate-fade-in"
      )}
    >
      {/* Header row */}
      <div className="flex items-center justify-between gap-4 px-4 py-3">
        <p className="text-sm font-semibold text-foreground">{headingText}</p>
        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="sm"
            className="text-muted-foreground hover:text-foreground"
            onClick={discardAll}
          >
            Discard
          </Button>
          <Button size="sm" onClick={send}>
            <Send className="h-3.5 w-3.5" />
            Send to {assistantName}
          </Button>
        </div>
      </div>

      {/* Divider */}
      <div className="mx-4 border-t border-border" />

      {/* Change list */}
      <ScrollArea className={cn(changes.length > 4 ? "h-[168px]" : undefined)}>
        <ul className="flex flex-col gap-0.5 px-3 py-2">
          {changes.map((entry) => {
            const cfg = KIND_CONFIG[entry.kind]
            const isRemoving = entry.kind === "removing"

            return (
              <li
                key={entry.id}
                className="group flex items-center gap-2 rounded-md px-1.5 py-1.5 transition-colors hover:bg-secondary"
              >
                <button
                  type="button"
                  onClick={() => onSelectChange(entry)}
                  className="flex min-w-0 flex-1 items-center gap-2.5 rounded px-1 py-0.5 text-left focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                >
                  {/* Kind badge */}
                  <span
                    className={cn(
                      "inline-flex shrink-0 items-center gap-1 rounded-md px-1.5 py-0.5 text-[11px] font-medium leading-none",
                      cfg.className
                    )}
                  >
                    <cfg.Icon className="h-3 w-3" />
                    {cfg.label}
                  </span>

                  {/* Summary text */}
                  <span
                    className={cn(
                      "min-w-0 flex-1 truncate text-sm",
                      isRemoving
                        ? "text-muted-foreground line-through"
                        : "text-foreground"
                    )}
                    title={entry.summary}
                  >
                    {entry.summary}
                  </span>
                </button>

                {/* Modify button */}
                <button
                  type="button"
                  aria-label="Modify this change"
                  onClick={() => onModifyChange(entry)}
                  className={cn(
                    "shrink-0 rounded p-1 text-muted-foreground transition-colors",
                    "hover:bg-accent hover:text-accent-foreground",
                    "focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                  )}
                >
                  <Pencil className="h-3.5 w-3.5" />
                </button>

                {/* Cancel button */}
                <button
                  type="button"
                  aria-label="Cancel this change"
                  onClick={() => undoChange(entry.id)}
                  className={cn(
                    "shrink-0 rounded p-1 text-muted-foreground transition-colors",
                    "hover:bg-accent hover:text-accent-foreground",
                    "focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                  )}
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              </li>
            )
          })}
        </ul>
      </ScrollArea>
    </div>
  )
}
