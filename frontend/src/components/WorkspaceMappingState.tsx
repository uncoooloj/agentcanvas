import { useState } from "react"
import { AlertCircle, Check, Circle, Clipboard, Loader2, RefreshCw, Search, Send, Sparkles } from "lucide-react"
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
  "Looking through your project",
  "Finding what people can do",
  "Putting the story together",
  "Getting your guide ready",
]
const STUCK_PROGRESS_MS = 10 * 60 * 1000

export enum MappingRequestStatus {
  Idle = "idle",
  Sending = "sending",
  Sent = "sent",
  Failed = "failed",
}

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
  assistantName?: string
  requestStatus?: MappingRequestStatus
  requestError?: string
  requestPendingId?: string
  onRequestMap?: () => void
  onRetry: () => void
}

export function WorkspaceMappingState({
  kind,
  stageIndex,
  workspaceName,
  message,
  detail,
  fallbackPrompt,
  progress: workspaceProgress,
  source,
  assistantName = "your assistant",
  requestStatus = MappingRequestStatus.Idle,
  requestError,
  onRequestMap,
  onRetry,
}: Props) {
  const [showInstructions, setShowInstructions] = useState(false)
  const active = kind === CanvasStateKind.Loading || kind === CanvasStateKind.Reindexing
  const liveProgress = active && workspaceProgress?.readable ? workspaceProgress : null
  const liveStage = liveProgress?.stage
  const progressStuck = isProgressStuck(liveProgress)
  const clampedStage = liveStage
    ? stageIndexForProgress(liveStage)
    : Math.min(Math.max(stageIndex, 0), MAPPING_STAGES.length - 1)
  const progressPercent = progressValue(liveProgress, clampedStage, active, kind)
  const requestSent = requestStatus === MappingRequestStatus.Sent
  const requestSending = requestStatus === MappingRequestStatus.Sending
  const requestFailed = requestStatus === MappingRequestStatus.Failed
  const Icon = kind === CanvasStateKind.Error ? AlertCircle : kind === CanvasStateKind.Empty ? Search : Sparkles
  const title =
    requestSent && active
      ? `${assistantName} is understanding your app`
      : kind === CanvasStateKind.Empty
      ? requestSent
        ? `${assistantName} is understanding your app`
        : "Let's understand your app"
      : message ||
    (progressStuck ? "Your agent seems to have stopped" : undefined) ||
    (kind === CanvasStateKind.Reindexing
      ? "Refreshing this project"
      : kind === CanvasStateKind.Loading
        ? `Reading ${workspaceName || "your project"}`
        : "Couldn't open the project map")
  const body =
    requestSent && active
      ? "It is looking through the project and putting together a simple guide. You can keep this page open."
      : kind === CanvasStateKind.Empty
      ? requestSent
        ? "It is looking through the project and putting together a simple guide. You can keep this page open."
        : `AgentCanvas found a starting point. Ask ${assistantName} to turn it into a simple guide to what your app does and how people use it.`
      : detail ||
    (progressStuck
      ? "AgentCanvas has not seen a mapping progress update for more than 10 minutes. Ask your agent to resume from the last progress stage."
      : undefined) ||
    liveProgress?.message ||
    (active
      ? MAPPING_STAGES[clampedStage]
      : source?.detail || "AgentCanvas could not open a usable map for this project.")
  const retryLabel = kind === CanvasStateKind.Empty ? "Check for map" : "Try again"
  const canRequestMap = kind === CanvasStateKind.Empty && Boolean(onRequestMap)
  const requestAnnouncement = requestSending
    ? `Asking ${assistantName} to make the app map.`
    : requestSent
      ? `${assistantName} is making the app map.`
      : requestFailed
        ? `We could not ask ${assistantName} to make the app map. ${requestError || "Try again."}`
        : active
          ? `Mapping progress: ${stageLabel(liveStage)}.`
          : ""

  return (
    <div
      className="flex min-h-full items-center justify-center px-6 py-16"
      role="region"
      aria-labelledby="workspace-mapping-state-title"
      aria-busy={active || requestSending}
    >
      <div className="w-full max-w-xl rounded-2xl border bg-card/85 p-6 shadow-sm">
        <div className="sr-only" role="status" aria-live="polite">
          {requestAnnouncement}
        </div>
        <div className="flex items-start gap-4">
          <span
            className={cn(
              "flex size-11 shrink-0 items-center justify-center rounded-xl",
              kind === CanvasStateKind.Error ? "bg-destructive/10 text-destructive" : "bg-when-bg text-when-fg"
            )}
          >
            {active ? <Loader2 aria-hidden="true" className="size-5 animate-spin" /> : <Icon aria-hidden="true" className="size-5" />}
          </span>
          <div className="min-w-0 flex-1">
            <h2 id="workspace-mapping-state-title" className="text-base font-medium tracking-tight">
              {title}
            </h2>
            <p className="mt-1 text-sm leading-relaxed text-muted-foreground">{body}</p>
            {source && kind !== CanvasStateKind.Empty && (
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
            <Progress
              value={progressPercent}
              aria-label="Mapping progress"
              aria-valuetext={`${Math.round(progressPercent)}% complete`}
              className="h-2"
            />
            {(requestSending || requestSent) && (
              <p className="mt-3 text-sm text-muted-foreground" role="status" aria-live="polite">
                {requestSending
                  ? `Asking ${assistantName} to look through your app...`
                  : `${assistantName} is working on your app guide.`}
              </p>
            )}
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
          <div className="mt-6 space-y-3">
            {requestFailed && requestError && (
              <p className="text-sm leading-relaxed text-destructive" role="status">
                We could not ask {assistantName} just now. Try again, or copy the instructions instead.
              </p>
            )}
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
              {canRequestMap && !requestSent && (
                <Button
                  type="button"
                  onClick={onRequestMap}
                  disabled={requestSending}
                  aria-label={`Ask ${assistantName} to make the map`}
                  className="w-full gap-2 sm:w-auto"
                >
                  {requestSending ? <Loader2 className="size-4 animate-spin" /> : <Send className="size-4" />}
                  {requestSending ? "Asking..." : "Explain my app"}
                </Button>
              )}
              {(kind !== CanvasStateKind.Empty || requestSent || !canRequestMap) && (
                <Button
                  type="button"
                  variant={canRequestMap ? "outline" : "default"}
                  onClick={onRetry}
                  className="w-full gap-2 sm:w-auto"
                >
                  <RefreshCw className="size-4" />
                  {requestSent ? "Check for updates" : retryLabel}
                </Button>
              )}
            </div>
            {kind === CanvasStateKind.Empty && fallbackPrompt && !requestSent && (
              <div>
                {showInstructions ? (
                  <CopyMapPrompt prompt={fallbackPrompt} compact />
                ) : (
                  <Button type="button" variant="link" size="sm" onClick={() => setShowInstructions(true)}>
                    Working with another assistant?
                  </Button>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

function CopyMapPrompt({ prompt, compact = false }: { prompt: string; compact?: boolean }) {
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
        variant={compact ? "ghost" : "outline"}
        className="w-full shrink-0 sm:w-auto"
        onClick={copyPrompt}
      >
        {copyState === CopyState.Copied ? <Check className="size-3.5" /> : <Clipboard className="size-3.5" />}
        {copyState === CopyState.Copied ? "Copied" : compact ? "Copy instructions" : "Copy note for assistant"}
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
      return "Looking through your project"
    case WorkspaceProgressStage.Surveying:
      return "Finding what people can do"
    case WorkspaceProgressStage.MappingFlows:
      return "Putting the story together"
    case WorkspaceProgressStage.Done:
      return "Getting your guide ready"
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
