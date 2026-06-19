import { useMemo, useState } from "react"
import {
  ArrowRight,
  Loader2,
  Mail,
  RefreshCcw,
  Search,
  ShoppingCart,
  Sparkles,
  UserRound,
  Zap,
  type LucideIcon,
} from "lucide-react"
import { Input } from "@/components/ui/input"
import { countSteps, type Journey } from "@/lib/types"
import type { ChangeEntry } from "@/lib/changeset"

type JourneyActivity = "idle" | "edited" | "working"

interface Props {
  appName: string
  journeys: Journey[]
  changes: ChangeEntry[]
  activity: Map<string, JourneyActivity>
  onOpen: (id: string) => void
}

export function Overview({ appName, journeys, changes, activity, onOpen }: Props) {
  const [query, setQuery] = useState("")
  const pendingByJourney = useMemo(() => {
    const m = new Map<string, number>()
    for (const c of changes) m.set(c.journeyId, (m.get(c.journeyId) ?? 0) + 1)
    return m
  }, [changes])

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return journeys
    return journeys.filter((j) =>
      `${j.title} ${j.entry} ${j.summary}`.toLowerCase().includes(q)
    )
  }, [journeys, query])

  const displayName = appName.trim() || "your app"
  const showSearch = journeys.length > 6

  return (
    <div className="mx-auto max-w-4xl px-6 py-12 pb-36">
      <header className="mb-9 text-center">
        <h1 className="text-2xl font-medium tracking-tight sm:text-[28px]">
          What {displayName.toLowerCase()} does
        </h1>
        <p className="mx-auto mt-2.5 max-w-md text-[15px] leading-relaxed text-muted-foreground">
          Each card is a moment someone uses your app. Open one to see exactly what happens —
          step by step, in plain language.
        </p>
      </header>

      {showSearch && (
        <div className="relative mx-auto mb-7 max-w-sm">
          <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Find a flow…"
            className="rounded-full pl-9"
          />
        </div>
      )}

      {filtered.length ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {filtered.map((journey) => (
            <FlowCard
              key={journey.id}
              journey={journey}
              pending={pendingByJourney.get(journey.id) ?? 0}
              status={activity.get(journey.id) ?? "idle"}
              onOpen={() => onOpen(journey.id)}
            />
          ))}
        </div>
      ) : (
        <p className="py-12 text-center text-sm text-muted-foreground">
          Nothing matches “{query.trim()}”.
        </p>
      )}
    </div>
  )
}

function FlowCard({
  journey,
  pending,
  status,
  onOpen,
}: {
  journey: Journey
  pending: number
  status: JourneyActivity
  onOpen: () => void
}) {
  const Icon = flowIcon(journey)
  const steps = countSteps(journey.nodes)

  return (
    <button
      type="button"
      onClick={onOpen}
      className="group flex flex-col items-start gap-3 rounded-2xl border bg-card p-5 text-left transition-all hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-md"
    >
      <div className="flex w-full items-center justify-between">
        <span className="flex size-10 items-center justify-center rounded-xl bg-when-bg text-when-fg">
          <Icon className="size-[18px]" />
        </span>
        {status === "working" ? (
          <span className="inline-flex items-center gap-1.5 rounded-full bg-secondary px-2.5 py-1 text-xs text-muted-foreground">
            <Loader2 className="size-3 animate-spin" /> Updating
          </span>
        ) : pending > 0 ? (
          <span className="inline-flex items-center gap-1.5 rounded-full bg-when-bg px-2.5 py-1 text-xs font-medium text-when-fg">
            <Sparkles className="size-3" />
            {pending} {pending === 1 ? "change" : "changes"}
          </span>
        ) : null}
      </div>

      <div className="flex-1">
        <p className="text-[15px] font-medium leading-snug">{journey.title}</p>
        <p className="mt-1 text-sm leading-relaxed text-muted-foreground">{journey.entry}</p>
      </div>

      <div className="flex w-full items-center justify-between pt-1">
        <span className="text-xs text-muted-foreground">
          {steps} {steps === 1 ? "step" : "steps"}
        </span>
        <span className="inline-flex items-center gap-1 text-xs font-medium text-primary opacity-0 transition-opacity group-hover:opacity-100">
          See what happens <ArrowRight className="size-3.5" />
        </span>
      </div>
    </button>
  )
}

function flowIcon(journey: Journey): LucideIcon {
  const t = `${journey.id} ${journey.title}`.toLowerCase()
  if (/order|checkout|cart|pay|buy|purchase/.test(t)) return ShoppingCart
  if (/sign|account|login|user|register/.test(t)) return UserRound
  if (/refund|return|cancel/.test(t)) return RefreshCcw
  if (/email|message|notif|mail/.test(t)) return Mail
  return Zap
}
