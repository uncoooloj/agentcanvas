import { useMemo, useState } from "react"
import {
  ArrowRight,
  Bell,
  CreditCard,
  GitBranch,
  LockKeyhole,
  Mail,
  PackageCheck,
  Play,
  Receipt,
  RefreshCcw,
  Route,
  Search,
  ShieldCheck,
  ShoppingCart,
  Sparkles,
  UserRound,
  Zap,
  type LucideIcon,
} from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Separator } from "@/components/ui/separator"
import { cn } from "@/lib/utils"
import { countSteps, type BranchNode, type FlowNode, type Journey, type StepNode } from "@/lib/types"
import type { ChangeEntry } from "@/lib/changeset"

type JourneyActivity = "idle" | "edited" | "working"

interface Props {
  appName: string
  journeys: Journey[]
  changes: ChangeEntry[]
  activity: Map<string, JourneyActivity>
  onOpen: (id: string) => void
}

interface FlowIcon {
  Icon: LucideIcon
  className: string
  label: string
}

interface FlowCounts {
  triggers: number
  actions: number
  rules: number
  refs: number
  uncertain: number
}

interface FlowSummary {
  journey: Journey
  status: JourneyActivity
  latestChange?: ChangeEntry
  stats: FlowCounts
  steps: number
  searchText: string
}

interface Signal {
  label: string
  value: string
  Icon: LucideIcon
  className: string
}

export function Overview({ appName, journeys, changes, activity, onOpen }: Props) {
  const [query, setQuery] = useState("")
  const latestChangeByJourney = useMemo(() => latestChanges(changes), [changes])
  const flows = useMemo<FlowSummary[]>(
    () =>
      journeys.map((journey) => {
        const latestChange = latestChangeByJourney.get(journey.id)
        const stats = countNodeKinds(journey.nodes)
        return {
          journey,
          status: activity.get(journey.id) ?? "idle",
          latestChange,
          stats,
          steps: countSteps(journey.nodes),
          searchText: searchableText(journey, latestChange),
        }
      }),
    [activity, journeys, latestChangeByJourney]
  )
  const totals = useMemo(() => summarizeFlows(flows), [flows])
  const entryCount = useMemo(
    () => new Set(flows.map((flow) => flow.journey.entry || flow.journey.title)).size,
    [flows]
  )
  const filtered = useMemo(() => {
    const tokens = query
      .trim()
      .toLowerCase()
      .split(/\s+/)
      .filter(Boolean)
    if (!tokens.length) return flows
    return flows.filter((flow) => tokens.every((token) => flow.searchText.includes(token)))
  }, [flows, query])
  const hasQuery = query.trim().length > 0
  const displayName = appName.trim() || "Your app"

  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-6 px-5 py-6 pb-32 lg:px-8">
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_380px]">
        <div className="flex min-w-0 flex-col gap-5">
          <div className="flex flex-col gap-3">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="secondary">{journeys.length} flows</Badge>
              <Badge variant="outline">{totals.steps} steps</Badge>
              {totals.active > 0 && <Badge>{totals.active} active edits</Badge>}
            </div>
            <div className="flex flex-col gap-2">
              <h1 className="text-2xl font-medium">All flows</h1>
              <p className="max-w-3xl text-sm leading-6 text-muted-foreground">
                {displayName} as an operational map of entry points, decisions, actions, and local changes.
              </p>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <MetricCard
              Icon={Route}
              label="Visible"
              value={filtered.length}
              detail={hasQuery ? `${journeys.length} total flows` : "Flow inventory"}
            />
            <MetricCard
              Icon={Zap}
              label="Entry points"
              value={entryCount}
              detail={`${totals.triggers} ${plural("trigger", totals.triggers)}`}
              tone="when"
            />
            <MetricCard
              Icon={GitBranch}
              label="Decisions"
              value={totals.rules}
              detail={shapeLabel(totals)}
              tone="rule"
            />
            <MetricCard
              Icon={Sparkles}
              label="Local edits"
              value={changes.length}
              detail={totals.working > 0 ? `${totals.working} working` : "Ready for handoff"}
              tone="act"
            />
          </div>
        </div>

        <Card className="rounded-lg shadow-sm">
          <CardHeader className="p-4 pb-3">
            <div className="flex items-center justify-between gap-3">
              <div className="min-w-0">
                <CardTitle className="text-base font-medium">Flow index</CardTitle>
                <CardDescription className="mt-1">
                  {hasQuery ? `${filtered.length} matched` : `${journeys.length} indexed`}
                </CardDescription>
              </div>
              <Badge variant="outline">{totals.refs} refs</Badge>
            </div>
          </CardHeader>
          <CardContent className="flex flex-col gap-3 p-4 pt-0">
            <div className="relative">
              <Search
                aria-hidden="true"
                className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
              />
              <Input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Search flows..."
                className="pl-9"
              />
            </div>
            <div className="flex flex-wrap gap-2">
              <Badge variant="secondary">{totals.triggers} when</Badge>
              <Badge variant="secondary">{totals.actions} do</Badge>
              <Badge variant="secondary">{totals.rules} rules</Badge>
              {totals.uncertain > 0 && <Badge variant="outline">{totals.uncertain} to review</Badge>}
            </div>
          </CardContent>
        </Card>
      </div>

      <Separator />

      {filtered.length ? (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {filtered.map((flow) => (
            <FlowCard
              key={flow.journey.id}
              journey={flow.journey}
              status={flow.status}
              latestChange={flow.latestChange}
              stats={flow.stats}
              steps={flow.steps}
              onOpen={() => onOpen(flow.journey.id)}
            />
          ))}
        </div>
      ) : (
        <Card className="rounded-lg shadow-sm">
          <CardHeader>
            <CardTitle>No matching flows</CardTitle>
            <CardDescription>Nothing in the current flow index matches "{query.trim()}".</CardDescription>
          </CardHeader>
          <CardFooter>
            <Button type="button" variant="outline" onClick={() => setQuery("")}>
              Clear search
            </Button>
          </CardFooter>
        </Card>
      )}
    </div>
  )
}

function FlowCard({
  journey,
  status,
  latestChange,
  stats,
  steps,
  onOpen,
}: {
  journey: Journey
  status: JourneyActivity
  latestChange?: ChangeEntry
  stats: FlowCounts
  steps: number
  onOpen: () => void
}) {
  const icon = flowIcon(journey)
  const Icon = icon.Icon
  const editedAt = latestChange?.updatedAt ?? latestChange?.createdAt ?? journey.lastEditedAt
  const signals = useMemo(() => flowSignals(journey.nodes), [journey.nodes])

  return (
    <Card className="group overflow-hidden rounded-lg shadow-sm transition-all hover:border-primary/50 hover:shadow-md">
      <CardHeader className="p-4 pb-3">
        <div className="flex items-start justify-between gap-3">
          <div className="flex min-w-0 gap-3">
            <span
              aria-label={icon.label}
              className={cn(
                "flex size-11 shrink-0 items-center justify-center rounded-lg",
                icon.className
              )}
              role="img"
            >
              <Icon aria-hidden="true" className="size-5" />
            </span>
            <div className="min-w-0">
              <CardTitle className="text-base font-medium leading-tight">
                <button
                  type="button"
                  onClick={onOpen}
                  className="min-w-0 text-left outline-none hover:text-primary focus-visible:rounded-sm focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <span className="line-clamp-2">{journey.title}</span>
                </button>
              </CardTitle>
              <CardDescription className="mt-2 line-clamp-3 leading-6">
                {flowDescription(journey, stats)}
              </CardDescription>
            </div>
          </div>
          <StatusBadge status={status} editedAt={editedAt} />
        </div>
      </CardHeader>

      <CardContent className="flex flex-col gap-4 px-4 pb-4">
        <div className="grid gap-3 md:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)]">
          <div className="rounded-lg border bg-background/80 p-3">
            <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
              <Zap aria-hidden="true" className="size-3.5" />
              Entry point
            </div>
            <p className="mt-2 line-clamp-2 text-sm font-medium leading-6 text-foreground">
              {journey.entry || journey.title}
            </p>
          </div>

          <div className="rounded-lg bg-secondary/70 p-3">
            <div className="flex items-center justify-between gap-3">
              <div className="min-w-0">
                <p className="text-xs font-medium text-muted-foreground">Path shape</p>
                <p className="mt-1 truncate text-sm font-medium">{shapeLabel(stats)}</p>
              </div>
              <Badge variant="outline">{steps} {plural("step", steps)}</Badge>
            </div>
            <CompositionBar stats={stats} />
          </div>
        </div>

        <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
          <RoleStat Icon={Zap} label="When" value={stats.triggers} className="bg-when-bg text-when-fg" />
          <RoleStat Icon={Play} label="Do" value={stats.actions} className="bg-act-bg text-act-fg" />
          <RoleStat Icon={GitBranch} label="Rules" value={stats.rules} className="bg-rule-bg text-rule-fg" />
        </div>

        {signals.length > 0 && (
          <div className="grid gap-2 sm:grid-cols-2">
            {signals.map((signal) => (
              <FlowSignal key={`${signal.label}-${signal.value}`} signal={signal} />
            ))}
          </div>
        )}

        {latestChange && (
          <div className="rounded-lg border border-when-accent/30 bg-when-bg/60 p-3">
            <div className="flex items-center gap-2 text-xs font-medium text-when-fg">
              <Sparkles aria-hidden="true" className="size-3.5" />
              Local edit
            </div>
            <p className="mt-2 line-clamp-2 text-sm leading-6 text-foreground">{latestChange.summary}</p>
          </div>
        )}
      </CardContent>

      <CardFooter className="flex flex-wrap items-center justify-between gap-3 px-4 pb-4 pt-0">
        <div className="flex min-w-0 flex-wrap items-center gap-2 text-xs text-muted-foreground">
          {stats.refs > 0 && <Badge variant="outline">{stats.refs} source refs</Badge>}
          {stats.uncertain > 0 && <Badge variant="outline">{stats.uncertain} to review</Badge>}
          {stats.refs === 0 && stats.uncertain === 0 && <span>{steps} mapped steps</span>}
        </div>
        <Button type="button" variant="ghost" size="sm" onClick={onOpen}>
          Open
          <ArrowRight data-icon="inline-end" />
        </Button>
      </CardFooter>
    </Card>
  )
}

function MetricCard({
  Icon,
  label,
  value,
  detail,
  tone,
}: {
  Icon: LucideIcon
  label: string
  value: number
  detail: string
  tone?: "when" | "act" | "rule"
}) {
  return (
    <Card className="rounded-lg shadow-sm">
      <CardHeader className="p-3 pb-1">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <CardDescription className="text-xs">{label}</CardDescription>
            <CardTitle className="mt-1 text-xl font-medium">{value}</CardTitle>
          </div>
          <span
            className={cn(
              "flex size-8 shrink-0 items-center justify-center rounded-md bg-secondary text-muted-foreground",
              tone === "when" && "bg-when-bg text-when-fg",
              tone === "act" && "bg-act-bg text-act-fg",
              tone === "rule" && "bg-rule-bg text-rule-fg"
            )}
          >
            <Icon aria-hidden="true" className="size-4" />
          </span>
        </div>
      </CardHeader>
      <CardContent className="p-3 pt-0">
        <p className="truncate text-xs text-muted-foreground">{detail}</p>
      </CardContent>
    </Card>
  )
}

function RoleStat({
  Icon,
  label,
  value,
  className,
}: {
  Icon: LucideIcon
  label: string
  value: number
  className: string
}) {
  return (
    <div className="flex min-w-0 items-center gap-2 rounded-lg border bg-background/70 p-2">
      <span className={cn("flex size-7 shrink-0 items-center justify-center rounded-md", className)}>
        <Icon aria-hidden="true" className="size-3.5" />
      </span>
      <div className="min-w-0">
        <p className="text-sm font-medium leading-none">{value}</p>
        <p className="mt-1 truncate text-xs text-muted-foreground">{label}</p>
      </div>
    </div>
  )
}

function FlowSignal({ signal }: { signal: Signal }) {
  const Icon = signal.Icon
  return (
    <div className="flex min-w-0 gap-2 rounded-lg border bg-background/70 p-3">
      <span className={cn("flex size-7 shrink-0 items-center justify-center rounded-md", signal.className)}>
        <Icon aria-hidden="true" className="size-3.5" />
      </span>
      <div className="min-w-0">
        <p className="text-xs font-medium text-muted-foreground">{signal.label}</p>
        <p className="mt-1 line-clamp-2 text-sm leading-5">{signal.value}</p>
      </div>
    </div>
  )
}

function CompositionBar({ stats }: { stats: FlowCounts }) {
  const segments = [
    { label: "when", value: stats.triggers, className: "bg-when-accent" },
    { label: "do", value: stats.actions, className: "bg-act-accent" },
    { label: "rules", value: stats.rules, className: "bg-rule-accent" },
  ].filter((segment) => segment.value > 0)

  return (
    <div
      aria-label={`${stats.triggers} triggers, ${stats.actions} actions, ${stats.rules} rules`}
      className="mt-3 flex h-2 overflow-hidden rounded-full bg-background"
      role="img"
    >
      {segments.map((segment) => (
        <span
          key={segment.label}
          className={cn("min-w-2", segment.className)}
          style={{ flexGrow: segment.value }}
        />
      ))}
    </div>
  )
}

function StatusBadge({ status, editedAt }: { status: JourneyActivity; editedAt?: number }) {
  if (status === "working") {
    return <Badge>Working</Badge>
  }
  if (status === "edited") {
    return <Badge className="border-transparent bg-when-bg text-when-fg hover:bg-when-bg">Edited</Badge>
  }
  if (editedAt) {
    return <Badge variant="secondary">{relativeEditedAt(editedAt)}</Badge>
  }
  return <Badge variant="outline">Stable</Badge>
}

function latestChanges(changes: ChangeEntry[]) {
  const byJourney = new Map<string, ChangeEntry>()
  for (const change of changes) {
    const current = byJourney.get(change.journeyId)
    if (!current || (change.updatedAt || change.createdAt) > (current.updatedAt || current.createdAt)) {
      byJourney.set(change.journeyId, change)
    }
  }
  return byJourney
}

function summarizeFlows(flows: FlowSummary[]): FlowCounts & { active: number; steps: number; working: number } {
  return flows.reduce(
    (totals, flow) => ({
      triggers: totals.triggers + flow.stats.triggers,
      actions: totals.actions + flow.stats.actions,
      rules: totals.rules + flow.stats.rules,
      refs: totals.refs + flow.stats.refs,
      uncertain: totals.uncertain + flow.stats.uncertain,
      active: totals.active + (flow.status === "idle" ? 0 : 1),
      working: totals.working + (flow.status === "working" ? 1 : 0),
      steps: totals.steps + flow.steps,
    }),
    { triggers: 0, actions: 0, rules: 0, refs: 0, uncertain: 0, active: 0, working: 0, steps: 0 }
  )
}

function countNodeKinds(nodes: FlowNode[]): FlowCounts {
  const counts: FlowCounts = { triggers: 0, actions: 0, rules: 0, refs: 0, uncertain: 0 }
  for (const node of nodes) {
    counts.refs += node.tech?.refs.length ?? 0
    counts.uncertain += node.uncertain ? 1 : 0
    if (node.kind === "branch") {
      counts.rules += 1
      mergeCounts(counts, countNodeKinds(node.then))
      mergeCounts(counts, countNodeKinds(node.otherwise))
    } else if (node.role === "when") {
      counts.triggers += 1
    } else {
      counts.actions += 1
    }
  }
  return counts
}

function mergeCounts(target: FlowCounts, source: FlowCounts) {
  target.triggers += source.triggers
  target.actions += source.actions
  target.rules += source.rules
  target.refs += source.refs
  target.uncertain += source.uncertain
}

function searchableText(journey: Journey, latestChange?: ChangeEntry) {
  const parts = [journey.title, journey.summary, journey.entry, latestChange?.summary ?? ""]
  collectNodeText(journey.nodes, parts)
  return parts.join(" ").toLowerCase()
}

function collectNodeText(nodes: FlowNode[], parts: string[]) {
  for (const node of nodes) {
    parts.push(node.id)
    parts.push(node.tech?.refs.join(" ") ?? "")
    if (node.kind === "branch") {
      parts.push(node.condition)
      collectNodeText(node.then, parts)
      collectNodeText(node.otherwise, parts)
    } else {
      parts.push(node.role, node.text, node.detail ?? "")
    }
  }
}

function flowDescription(journey: Journey, stats: FlowCounts) {
  const summary = (journey.summary || `${journey.title} starting from ${journey.entry}`).replace(/[.?!]\s*$/, "")
  const parts = [
    `${stats.triggers} ${plural("trigger", stats.triggers)}`,
    `${stats.actions} ${plural("action", stats.actions)}`,
  ]
  if (stats.rules > 0) parts.push(`${stats.rules} ${plural("decision", stats.rules)}`)
  return `${summary}. ${parts.join(", ")}.`
}

function flowSignals(nodes: FlowNode[]): Signal[] {
  const action = findFirstStep(nodes, "do")
  const rule = findFirstBranch(nodes)
  const signals: Signal[] = []
  if (action) {
    signals.push({
      label: "Next action",
      value: action.text,
      Icon: Play,
      className: "bg-act-bg text-act-fg",
    })
  }
  if (rule) {
    signals.push({
      label: "Decision",
      value: `If ${rule.condition}`,
      Icon: GitBranch,
      className: "bg-rule-bg text-rule-fg",
    })
  }
  return signals
}

function findFirstStep(nodes: FlowNode[], role: "when" | "do"): StepNode | null {
  for (const node of nodes) {
    if (node.kind === "step" && node.role === role) return node
    if (node.kind === "branch") {
      const nested = findFirstStep(node.then, role) ?? findFirstStep(node.otherwise, role)
      if (nested) return nested
    }
  }
  return null
}

function findFirstBranch(nodes: FlowNode[]): BranchNode | null {
  for (const node of nodes) {
    if (node.kind === "branch") return node
  }
  return null
}

function shapeLabel(stats: Pick<FlowCounts, "rules" | "triggers" | "actions">) {
  if (stats.rules >= 3) return "Branch-heavy"
  if (stats.rules > 0) return "Decision path"
  if (stats.triggers > 1) return "Multi-entry"
  if (stats.actions > 3) return "Action run"
  return "Straight path"
}

function flowIcon(journey: Journey): FlowIcon {
  const text = `${journey.title} ${journey.summary} ${journey.entry}`.toLowerCase()
  if (/permission|secure|security|access|role|lock|admin/.test(text)) {
    return { Icon: ShieldCheck, className: "bg-rule-bg text-rule-fg", label: "Access flow" }
  }
  if (/password|auth|login|signin|sign in|signup|sign up|session/.test(text)) {
    return { Icon: LockKeyhole, className: "bg-rule-bg text-rule-fg", label: "Authentication flow" }
  }
  if (/account|profile|customer|member|user/.test(text)) {
    return { Icon: UserRound, className: "bg-rule-bg text-rule-fg", label: "Account flow" }
  }
  if (/payment|pay|charge|card|stripe/.test(text)) {
    return { Icon: CreditCard, className: "bg-when-bg text-when-fg", label: "Payment flow" }
  }
  if (/cart|order|checkout|purchase/.test(text)) {
    return { Icon: ShoppingCart, className: "bg-when-bg text-when-fg", label: "Commerce flow" }
  }
  if (/refund|return|cancel|chargeback/.test(text)) {
    return { Icon: RefreshCcw, className: "bg-secondary text-secondary-foreground", label: "Return flow" }
  }
  if (/ship|deliver|fulfill|package|inventory|stock/.test(text)) {
    return { Icon: PackageCheck, className: "bg-act-bg text-act-fg", label: "Fulfillment flow" }
  }
  if (/invoice|receipt|billing/.test(text)) {
    return { Icon: Receipt, className: "bg-when-bg text-when-fg", label: "Billing flow" }
  }
  if (/message|notification|email|mail|sms|alert/.test(text)) {
    return { Icon: Mail, className: "bg-act-bg text-act-fg", label: "Messaging flow" }
  }
  if (/notify|bell/.test(text)) {
    return { Icon: Bell, className: "bg-act-bg text-act-fg", label: "Notification flow" }
  }
  if (/branch|rule|condition|if|decision|approval|review/.test(text)) {
    return { Icon: GitBranch, className: "bg-rule-bg text-rule-fg", label: "Decision flow" }
  }
  return { Icon: Route, className: "bg-secondary text-muted-foreground", label: "General flow" }
}

function relativeEditedAt(value: number) {
  const minutes = Math.max(0, Math.round((Date.now() - value) / 60000))
  if (minutes < 1) return "Edited now"
  if (minutes < 60) return `Edited ${minutes}m ago`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `Edited ${hours}h ago`
  return "Recently edited"
}

function plural(word: string, count: number) {
  return count === 1 ? word : `${word}s`
}
