import { useState } from "react"
import { AlertCircle, Check, Circle, Clipboard, Loader2, RefreshCw, Search, Sparkles } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Progress } from "@/components/ui/progress"
import {
  CanvasSourceTone,
  CanvasStateKind,
  CopyState,
  WorkspaceProgressStage,
  type CanvasSourceSummary,
  type WorkspaceProgressStatus,
} from "@/lib/types"
import { cn } from "@/lib/utils"

const MAPPING_STAGES = [
  "Reading project",
  "Finding where work starts",
  "Naming the flows",
  "Preparing the map",
]
const STUCK_PROGRESS_MS = 10 * 60 * 1000

interface Props {
  kind: CanvasStateKind.Loading | CanvasStateKind.Reindexing | CanvasStateKind.Empty | CanvasStateKind.Error
  stageIndex: number
  workspaceName: string
  message?: string
  detail?: string
  nextSteps?: string[]
  fallbackPrompt?: string
  progress?: WorkspaceProgressStatus | null
  source?: CanvasSourceSummary
  onRetry: () => void
}

export function WorkspaceMappingState({
  kind,
  stageIndex,
  workspaceName,
  message,
  detail,
  nextSteps,
  fallbackPrompt,
  progress: workspaceProgress,
  source,
  onRetry,
}: Props) {
  const active = kind === CanvasStateKind.Loading || kind === CanvasStateKind.Reindexing
  const liveProgress = active && workspaceProgress?.readable ? workspaceProgress : null
  const liveStage = liveProgress?.stage
  const progressStuck = isProgressStuck(liveProgress)
  const clampedStage = liveStage
    ? stageIndexForProgress(liveStage)
    : Math.min(Math.max(stageIndex, 0), MAPPING_STAGES.length - 1)
  const progressPercent = progressValue(liveProgress, clampedStage, active, kind)
  const Icon = kind === CanvasStateKind.Error ? AlertCircle : kind === CanvasStateKind.Empty ? Search : Sparkles
  const title =
    message ||
    (progressStuck ? "Your agent seems to have stopped" : undefined) ||
    (kind === CanvasStateKind.Reindexing
      ? "Refreshing this project"
      : kind === CanvasStateKind.Loading
        ? `Reading ${workspaceName || "your project"}`
        : kind === CanvasStateKind.Empty
          ? "No plain-English map yet"
          : "Couldn't open the project map")
  const body =
    detail ||
    (progressStuck
      ? "AgentCanvas has not seen a mapping progress update for more than 10 minutes. Ask your agent to resume from the last progress stage."
      : undefined) ||
    liveProgress?.message ||
    (active
      ? MAPPING_STAGES[clampedStage]
      : source?.detail ||
        (kind === CanvasStateKind.Empty
          ? "AgentCanvas checked this project, but it does not have a clear list of the main things people can do yet."
          : "AgentCanvas could not open a usable map for this project."))
  const retryLabel = kind === CanvasStateKind.Empty ? "Refresh map" : "Try again"

  return (
    <div className="flex min-h-full items-center justify-center px-6 py-16" aria-live="polite">
      <div className="w-full max-w-xl rounded-2xl border bg-card/85 p-6 shadow-sm">
        <div className="flex items-start gap-4">
          <span
            className={cn(
              "flex size-11 shrink-0 items-center justify-center rounded-xl",
              kind === CanvasStateKind.Error ? "bg-destructive/10 text-destructive" : "bg-when-bg text-when-fg"
            )}
          >
            {active ? <Loader2 className="size-5 animate-spin" /> : <Icon className="size-5" />}
          </span>
          <div className="min-w-0 flex-1">
            <p className="text-base font-medium tracking-tight">{title}</p>
            <p className="mt-1 text-sm leading-relaxed text-muted-foreground">{body}</p>
            {source && (
              <p
                className={cn(
                  "mt-3 inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-medium",
                  source.tone === CanvasSourceTone.Warning
                    ? "border-gold/30 bg-gold/10 text-foreground"
                    : source.tone === CanvasSourceTone.Error
                      ? "border-destructive/25 bg-destructive/10 text-destructive"
                      : "border-border bg-secondary/70 text-muted-foreground"
                )}
                title={source.detail}
              >
                {source.label}
              </p>
            )}
          </div>
        </div>

        {active ? (
          <div className="mt-6">
            <Progress value={progressPercent} className="h-2" />
            {liveProgress && (
              <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
                <span>{stageLabel(liveProgress.stage)}</span>
                {typeof liveProgress.current === "number" && typeof liveProgress.total === "number" && (
                  <span>
                    {liveProgress.current} of {liveProgress.total}
                  </span>
                )}
              </div>
            )}
            {progressStuck && fallbackPrompt && liveProgress && (
              <div className="mt-4 rounded-lg border border-when-accent/25 bg-when-bg/30 p-3">
                <p className="text-sm font-medium text-foreground">Resume mapping</p>
                <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                  Copy this note into your agent so it can continue from the saved progress file.
                </p>
                <div className="mt-3">
                  <CopyMapPrompt prompt={resumePrompt(fallbackPrompt, liveProgress)} />
                </div>
              </div>
            )}
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
          <div className="mt-5 space-y-4">
            {kind === CanvasStateKind.Empty && nextSteps?.length ? (
              <div className="rounded-lg border bg-secondary/35 p-3.5">
                <p className="text-xs font-medium uppercase text-muted-foreground">Next</p>
                <ol className="mt-2 space-y-1.5 text-sm leading-relaxed text-foreground">
                  {nextSteps.map((step) => (
                    <li key={step} className="flex gap-2">
                      <Check className="mt-0.5 size-3.5 shrink-0 text-act-accent" />
                      <span>{step}</span>
                    </li>
                  ))}
                </ol>
              </div>
            ) : null}
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
              <Button type="button" onClick={onRetry} className="w-full gap-2 sm:w-auto">
                <RefreshCw className="size-4" />
                {retryLabel}
              </Button>
              {kind === CanvasStateKind.Empty && fallbackPrompt && <CopyMapPrompt prompt={fallbackPrompt} />}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

function CopyMapPrompt({ prompt }: { prompt: string }) {
  const [copyState, setCopyState] = useState<CopyState>(CopyState.Idle)

  async function copyPrompt() {
    try {
      await navigator.clipboard.writeText(prompt)
      setCopyState(CopyState.Copied)
      window.setTimeout(() => setCopyState(CopyState.Idle), 1600)
    } catch {
      setCopyState(CopyState.Manual)
    }
  }

  return (
    <div className="min-w-0 flex-1">
      <Button
        type="button"
        variant="outline"
        className="w-full shrink-0 sm:w-auto"
        onClick={copyPrompt}
      >
        {copyState === CopyState.Copied ? <Check className="size-3.5" /> : <Clipboard className="size-3.5" />}
        {copyState === CopyState.Copied ? "Copied" : "Copy note for assistant"}
      </Button>
      {copyState === CopyState.Manual && (
        <div className="mt-3 rounded-md border bg-secondary/30 p-3">
          <p className="text-xs font-medium text-muted-foreground">Clipboard blocked. Select this note.</p>
          <div className="mt-2 flex items-center gap-2">
            <Input
              readOnly
              value={prompt}
              aria-label="Instruction to paste into your agent"
              className="h-9 min-w-0 flex-1 text-xs text-muted-foreground"
              onFocus={(event) => event.currentTarget.select()}
            />
          </div>
        </div>
      )}
    </div>
  )
}

function stageIndexForProgress(stage: WorkspaceProgressStage): number {
  switch (stage) {
    case WorkspaceProgressStage.Indexing:
      return 0
    case WorkspaceProgressStage.Surveying:
      return 1
    case WorkspaceProgressStage.MappingFlows:
      return 2
    case WorkspaceProgressStage.Done:
      return 3
  }
}

function stageLabel(stage?: WorkspaceProgressStage): string {
  switch (stage) {
    case WorkspaceProgressStage.Indexing:
      return "Reading project"
    case WorkspaceProgressStage.Surveying:
      return "Finding where work starts"
    case WorkspaceProgressStage.MappingFlows:
      return "Naming the flows"
    case WorkspaceProgressStage.Done:
      return "Preparing the map"
    default:
      return "Mapping project"
  }
}

function progressValue(
  progress: WorkspaceProgressStatus | null,
  clampedStage: number,
  active: boolean,
  kind: Props["kind"],
): number {
  if (progress && typeof progress.current === "number" && typeof progress.total === "number" && progress.total > 0) {
    return Math.min(100, Math.max(0, (progress.current / progress.total) * 100))
  }
  return active ? ((clampedStage + 1) / MAPPING_STAGES.length) * 100 : kind === CanvasStateKind.Empty ? 100 : 0
}

function isProgressStuck(progress: WorkspaceProgressStatus | null): boolean {
  if (!progress || progress.stage === WorkspaceProgressStage.Done || !progress.updated_at) return false
  const updatedAt = Date.parse(progress.updated_at)
  if (Number.isNaN(updatedAt)) return false
  return Date.now() - updatedAt > STUCK_PROGRESS_MS
}

function resumePrompt(fallbackPrompt: string, progress: WorkspaceProgressStatus): string {
  const lines = [
    "AgentCanvas mapping seems stalled.",
    "",
    "Please resume from the latest progress state in `.agentcanvas/progress.json`.",
    `Current stage: ${progress.stage || "unknown"}`,
  ]
  if (progress.message) lines.push(`Last message: ${progress.message}`)
  if (typeof progress.current === "number" && typeof progress.total === "number") {
    lines.push(`Progress: ${progress.current} of ${progress.total}`)
  }
  lines.push("", fallbackPrompt)
  return lines.join("\n")
}
