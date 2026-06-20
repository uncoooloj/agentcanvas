import { AlertCircle, Check, Circle, Loader2, RefreshCw, Search, Sparkles } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Progress } from "@/components/ui/progress"
import { cn } from "@/lib/utils"

export type WorkspaceMappingKind = "loading" | "reindexing" | "empty" | "error"

const MAPPING_STAGES = [
  "Scanning workspace",
  "Finding app surfaces",
  "Translating flows",
  "Preparing canvas",
]

interface Props {
  kind: WorkspaceMappingKind
  stageIndex: number
  workspaceName: string
  message?: string
  detail?: string
  onRetry: () => void
}

export function WorkspaceMappingState({
  kind,
  stageIndex,
  workspaceName,
  message,
  detail,
  onRetry,
}: Props) {
  const active = kind === "loading" || kind === "reindexing"
  const clampedStage = Math.min(Math.max(stageIndex, 0), MAPPING_STAGES.length - 1)
  const progress = active ? ((clampedStage + 1) / MAPPING_STAGES.length) * 100 : kind === "empty" ? 100 : 0
  const Icon = kind === "error" ? AlertCircle : kind === "empty" ? Search : Sparkles
  const title =
    message ||
    (kind === "reindexing"
      ? "Refreshing workspace map"
      : kind === "loading"
        ? `Mapping ${workspaceName || "your workspace"}`
        : kind === "empty"
          ? "Workspace map isn't ready yet"
          : "Couldn't load workspace map")
  const body =
    detail ||
    (active
      ? MAPPING_STAGES[clampedStage]
      : kind === "empty"
        ? "AgentCanvas did not receive any workspace flows to show."
        : "The workspace canvas API did not return a usable map.")

  return (
    <div className="flex min-h-full items-center justify-center px-6 py-16" aria-live="polite">
      <div className="w-full max-w-xl rounded-2xl border bg-card/85 p-6 shadow-sm">
        <div className="flex items-start gap-4">
          <span
            className={cn(
              "flex size-11 shrink-0 items-center justify-center rounded-xl",
              kind === "error" ? "bg-destructive/10 text-destructive" : "bg-when-bg text-when-fg"
            )}
          >
            {active ? <Loader2 className="size-5 animate-spin" /> : <Icon className="size-5" />}
          </span>
          <div className="min-w-0 flex-1">
            <p className="text-base font-medium tracking-tight">{title}</p>
            <p className="mt-1 text-sm leading-relaxed text-muted-foreground">{body}</p>
          </div>
        </div>

        {active ? (
          <div className="mt-6">
            <Progress value={progress} className="h-2" />
            <div className="mt-5 grid gap-3 sm:grid-cols-2">
              {MAPPING_STAGES.map((stage, index) => {
                const done = index < clampedStage
                const current = index === clampedStage
                return (
                  <div
                    key={stage}
                    className={cn(
                      "flex items-center gap-2 rounded-lg border px-3 py-2 text-sm",
                      current ? "border-primary/25 bg-secondary/70 text-foreground" : "bg-background/45 text-muted-foreground"
                    )}
                  >
                    {done ? (
                      <Check className="size-3.5 shrink-0 text-act-accent" />
                    ) : current ? (
                      <Loader2 className="size-3.5 shrink-0 animate-spin text-primary" />
                    ) : (
                      <Circle className="size-3.5 shrink-0" />
                    )}
                    <span className="truncate">{stage}</span>
                  </div>
                )
              })}
            </div>
          </div>
        ) : (
          <div className="mt-5 flex flex-wrap items-center gap-3">
            <Button type="button" onClick={onRetry} className="gap-2">
              <RefreshCw className="size-4" />
              Retry mapping
            </Button>
          </div>
        )}
      </div>
    </div>
  )
}
