import { useEffect } from "react"
import { Folder, Sparkles } from "lucide-react"
import { cn } from "@/lib/utils"
import type { AppContext } from "@/lib/appcontext"
import { useChanges } from "@/lib/changeset"

export function Provenance({
  context,
  demoMode = false,
}: {
  context: AppContext
  demoMode?: boolean
}) {
  const isDemo = demoMode || context.isDemo
  const noun = context.productLanguage?.workspace_noun || context.productLanguage?.singular || "project"

  useEffect(() => {
    useChanges.getState().setAssistantName(context.assistant || "your assistant")
  }, [context.assistant])

  return (
    <div className="flex items-center justify-between gap-4 w-full">
      {/* Left: workspace */}
      <div
        className="flex items-center gap-2 min-w-0"
        title={context.workspacePath}
      >
        <Folder className="h-4 w-4 shrink-0 text-muted-foreground" />
        <span className="font-medium text-sm text-foreground truncate">
          {context.workspace}
        </span>
        <span className="text-sm text-muted-foreground hidden md:inline truncate">
          · what this {noun} does
        </span>
      </div>

      {/* Right: assistant pill */}
      <div
        className={cn(
          "hidden sm:flex items-center gap-1.5 shrink-0",
          "rounded-full border px-3 py-1",
          isDemo
            ? "border-primary/20 bg-primary/10 text-primary"
            : "border-border bg-secondary"
        )}
      >
        <Sparkles className={cn("h-3.5 w-3.5", isDemo ? "text-primary" : "text-primary")} />
        {isDemo ? (
          <>
            <span className="text-xs font-medium text-primary">Demo mode</span>
            <span className="hidden text-xs text-primary/70 md:inline">
              · {context.assistant || "No agent connected"}
            </span>
          </>
        ) : (
          <>
            <span className="text-xs text-muted-foreground">Assistant:</span>
            <span className="text-xs font-medium text-foreground">{context.assistant}</span>
          </>
        )}
      </div>
    </div>
  )
}
