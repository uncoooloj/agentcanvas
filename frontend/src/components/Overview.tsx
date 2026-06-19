import { useMemo, useState } from "react"
import {
  ArrowRight,
  CalendarClock,
  CreditCard,
  Loader2,
  Mail,
  MessageSquare,
  PackageCheck,
  RefreshCcw,
  Search,
  ShieldCheck,
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
    const tokens = query.trim().toLowerCase().split(/\s+/).filter(Boolean)
    if (!tokens.length) return journeys
    return journeys.filter((j) => {
      const hay = `${j.title} ${j.entry} ${j.summary}`.toLowerCase()
      return tokens.every((t) => hay.includes(t))
    })
  }, [journeys, query])

  const displayName = appName.trim() || "your app"
  const total = journeys.length
  const hasQuery = query.trim().length > 0

  return (
    <div className="mx-auto max-w-5xl px-6 pb-36">
      <header className="pt-12 text-center">
        <h1 className="text-2xl font-semibold tracking-tight sm:text-[28px]">
          What {displayName.toLowerCase()} does
        </h1>
        <p className="mx-auto mt-2.5 max-w-md text-[15px] leading-relaxed text-muted-foreground">
          Each card is a moment someone uses your app. Open one to see exactly what happens — in
          plain language.
        </p>
      </header>

      {/* Sticky search — always available so this scales to a big app */}
      <div className="sticky top-0 z-10 -mx-6 mb-6 mt-8 bg-background/85 px-6 py-3 backdrop-blur">
        <div className="mx-auto flex max-w-xl items-center gap-3">
          <div className="relative flex-1">
            <Search className="pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={`Search ${total} ${total === 1 ? "flow" : "flows"}…`}
              className="h-11 rounded-full pl-10 text-[15px]"
            />
          </div>
          <span className="hidden shrink-0 text-sm text-muted-foreground sm:block">
            {hasQuery ? `${filtered.length} of ${total}` : `${total} ${total === 1 ? "flow" : "flows"}`}
          </span>
        </div>
      </div>

      {filtered.length ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
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
        <div className="py-16 text-center">
          <p className="text-sm text-muted-foreground">Nothing matches “{query.trim()}”.</p>
          <button
            type="button"
            onClick={() => setQuery("")}
            className="mt-2 text-sm font-medium text-primary hover:underline"
          >
            Clear search
          </button>
        </div>
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
  const description = journey.summary?.trim()

  return (
    <button
      type="button"
      onClick={onOpen}
      className="group flex h-full flex-col gap-3 rounded-2xl border bg-card p-5 text-left transition-all hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-md"
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
        {description && (
          <p className="mt-1 line-clamp-2 text-sm leading-relaxed text-muted-foreground">
            {description}
          </p>
        )}
      </div>

      <div className="flex items-start gap-1.5 text-xs text-muted-foreground">
        <Zap className="mt-0.5 size-3.5 shrink-0 text-when-fg" />
        <span className="line-clamp-2">
          <span className="text-muted-foreground/70">Starts when </span>
          {lowerFirst(journey.entry)}
        </span>
      </div>

      <div className="flex items-center justify-between border-t pt-3">
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

function lowerFirst(s: string): string {
  return s ? s.charAt(0).toLowerCase() + s.slice(1) : s
}

function flowIcon(journey: Journey): LucideIcon {
  const t = `${journey.id} ${journey.title} ${journey.entry}`.toLowerCase()
  if (/checkout|order|cart|buy|purchase/.test(t)) return ShoppingCart
  if (/pay|charge|invoice|billing|card/.test(t)) return CreditCard
  if (/sign|account|login|register|auth|user/.test(t)) return UserRound
  if (/refund|return|cancel/.test(t)) return RefreshCcw
  if (/email|mail|message|notif|sms/.test(t)) return /mail|email/.test(t) ? Mail : MessageSquare
  if (/ship|deliver|fulfil|dispatch|package/.test(t)) return PackageCheck
  if (/permission|secure|verify|guard|fraud/.test(t)) return ShieldCheck
  if (/job|schedule|cron|event|queue/.test(t)) return CalendarClock
  return Zap
}
