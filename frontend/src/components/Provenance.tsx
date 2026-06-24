import { useEffect } from "react"
import { AlertCircle, Folder, Info, Sparkles } from "lucide-react"
import { cn } from "@/lib/utils"
import type { AppContext } from "@/lib/appcontext"
import type { CanvasSourceSummary } from "@/lib/types"
import { useChanges } from "@/lib/changeset"

export function Provenance({
  context,
  demoMode = false,
  source,
}: {
  context: AppContext
  demoMode?: boolean
  source?: CanvasSourceSummary
}) {
  const isDemo = Boolean(demoMode || context.isDemo)
  const noun = context.productLanguage?.workspace_noun || context.productLanguage?.singular || "project"
  const sourceToneClass =
    source?.tone === "warning"
      ? "border-gold/30 bg-gold/10 text-foreground"
      : source?.tone === "error"
        ? "border-destructive/25 bg-destructive/10 text-destructive"
        : isDemo
          ? "border-primary/20 bg-primary/10 text-primary"
          : "border-border bg-secondary"

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

      {/* Right: source pill */}
      <div
        className={cn(
          "hidden sm:flex items-center gap-1.5 shrink-0",
          "rounded-full border px-3 py-1",
          sourceToneClass
        )}
        title={source?.detail}
      >
        <SourceIcon source={source} isDemo={isDemo} />
        {source ? (
          <>
            <span
              className={cn(
                "text-xs font-medium",
                source.tone === "error" ? "text-destructive" : "text-foreground"
              )}
            >
              {source.shortLabel}
            </span>
            <span className="hidden text-xs text-muted-foreground lg:inline">
              · {source.label}
            </span>
          </>
        ) : isDemo ? (
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

function SourceIcon({ source, isDemo }: { source?: CanvasSourceSummary; isDemo: boolean }) {
  if (source?.tone === "warning" || source?.tone === "error") {
    return <AlertCircle className="h-3.5 w-3.5 shrink-0" />
  }
  if (source) {
    return <Info className="h-3.5 w-3.5 shrink-0 text-primary" />
  }
  return <Sparkles className={cn("h-3.5 w-3.5 shrink-0", isDemo ? "text-primary" : "text-primary")} />
}
