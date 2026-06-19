import { useEffect, useRef, useState, type ReactNode } from "react"
import {
  ArrowRight,
  ArrowUp,
  Check,
  CircleCheck,
  Clipboard,
  GitBranch,
  Loader2,
  Play,
  Send,
  Sparkles,
  Zap,
} from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

export function LandingPage({ onEnterApp }: { onEnterApp?: () => void } = {}) {
  // When opened from inside the app (logo → home), CTAs return you to the app.
  // On a genuine first visit, they enter the demo by reloading with ?demo=1.
  function openDemo() {
    if (onEnterApp) {
      onEnterApp()
      return
    }
    const url = new URL(window.location.href)
    url.searchParams.set("demo", "1")
    window.location.href = url.toString()
  }
  const ctaLabel = onEnterApp ? "Back to your app" : "Try the demo"

  return (
    <div className="min-h-screen bg-background text-foreground antialiased">
      <header className="sticky top-0 z-40 border-b border-border/60 bg-background/80 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-5xl items-center px-6">
          <span className="flex items-center gap-2 font-semibold">
            <span className="flex size-7 items-center justify-center rounded-md bg-primary text-primary-foreground">
              <Sparkles className="size-4" />
            </span>
            AgentCanvas
          </span>
          <nav className="ml-auto hidden items-center gap-7 text-sm text-muted-foreground sm:flex">
            <a href="#how" className="transition-colors hover:text-foreground">
              How it works
            </a>
            <a href="#agent" className="transition-colors hover:text-foreground">
              For your agent
            </a>
            <a href="#try" className="transition-colors hover:text-foreground">
              Try it
            </a>
          </nav>
          <Button type="button" size="sm" onClick={openDemo} className="ml-7 rounded-full">
            {ctaLabel}
          </Button>
        </div>
      </header>

      <main>
        {/* Hero */}
        <section className="mx-auto max-w-3xl px-6 pb-12 pt-20 text-center sm:pt-28">
          <Badge variant="secondary" className="mb-7 rounded-full px-3 py-1 font-normal text-muted-foreground">
            Works with Claude Code, Codex, Cursor &amp; more
          </Badge>
          <h1 className="text-balance text-[2.75rem] font-semibold leading-[1.03] tracking-[-0.02em] sm:text-[4.25rem]">
            Your app, in plain English.
            <br />
            <span className="text-foreground/55">Your AI agent, too.</span>
          </h1>
          <p className="mx-auto mt-6 max-w-xl text-balance text-lg leading-relaxed text-muted-foreground sm:text-xl">
            A friendlier way to steer the app an AI is building for you — see what it does, change it
            in plain English, and tell your coding agent exactly what to build.
          </p>
          <div className="mt-9 flex flex-wrap justify-center gap-3">
            <Button type="button" size="lg" onClick={openDemo} className="h-12 rounded-full px-7 text-base">
              {ctaLabel}
              <ArrowRight className="size-4" />
            </Button>
            <Button asChild variant="outline" size="lg" className="h-12 rounded-full px-7 text-base">
              <a href="#how">See how it works</a>
            </Button>
          </div>
        </section>

        <section className="mx-auto max-w-3xl px-6 pb-24">
          <BrowserFrame />
        </section>

        <Walkthrough />

        <AgentPrompt />

        {/* Try it */}
        <section id="try" className="border-t border-border/60 bg-secondary/30">
          <div className="mx-auto max-w-2xl px-6 py-24 text-center">
            <h2 className="text-3xl font-semibold tracking-tight sm:text-4xl">Have a look around.</h2>
            <p className="mx-auto mt-3 max-w-md text-muted-foreground">
              The demo is a small online shop. Nothing to install — click through it and try changing
              a step.
            </p>
            <Button type="button" size="lg" onClick={openDemo} className="mt-7 h-12 rounded-full px-7 text-base">
              <Play className="size-4" />
              {onEnterApp ? "Back to your app" : "Open the demo"}
            </Button>

            <div className="mx-auto mt-14 max-w-md rounded-2xl border bg-card p-5 text-left">
              <p className="text-sm font-medium">Already have a project?</p>
              <p className="mt-1 text-sm text-muted-foreground">
                Point AgentCanvas at it from your terminal — or ask whoever set it up to run:
              </p>
              <CopyBox text="agentcanvas start --workspace ./your-project" oneLine />
            </div>
          </div>
        </section>
      </main>

      <footer className="border-t border-border/60">
        <div className="mx-auto flex max-w-5xl flex-col items-center gap-3 px-6 py-12 text-center">
          <span className="flex items-center gap-2 text-sm font-semibold">
            <span className="flex size-6 items-center justify-center rounded-md bg-primary text-primary-foreground">
              <Sparkles className="size-3.5" />
            </span>
            AgentCanvas
          </span>
          <p className="max-w-sm text-sm text-muted-foreground">
            A friendlier way to steer the app an AI is building for you.
          </p>
        </div>
      </footer>
    </div>
  )
}

// ---- Walkthrough: sticky sidebar + scroll-snapping panels (agentation-style) ----

const WSTEPS: { title: string; body: string; visual: () => ReactNode }[] = [
  {
    title: "Open your app",
    body: "Point AgentCanvas at your project — or just try the demo. It reads everything and lays it out for you.",
    visual: VisualOpen,
  },
  {
    title: "See what it does",
    body: "Every part of your app, written as plain steps you can actually read — grouped by what people do.",
    visual: VisualFlow,
  },
  {
    title: "Change a step",
    body: "Click anything and say what you want instead, in your own words. Add a step, add a rule, or remove one.",
    visual: VisualCompose,
  },
  {
    title: "Send it off",
    body: "Your changes become one clear request for your AI agent — no technical handoff needed.",
    visual: VisualSend,
  },
  {
    title: "Watch it happen",
    body: "Your agent builds it, and the map updates to match. You always see what changed.",
    visual: VisualBuilt,
  },
]

function Walkthrough() {
  const [active, setActive] = useState(0)
  const refs = useRef<(HTMLDivElement | null)[]>([])

  useEffect(() => {
    document.documentElement.style.scrollSnapType = "y proximity"
    const obs = new IntersectionObserver(
      (entries) => {
        entries.forEach((e) => {
          if (e.isIntersecting) setActive(Number((e.target as HTMLElement).dataset.index))
        })
      },
      { rootMargin: "-45% 0px -45% 0px" }
    )
    refs.current.forEach((el) => el && obs.observe(el))
    return () => {
      obs.disconnect()
      document.documentElement.style.scrollSnapType = ""
    }
  }, [])

  return (
    <section id="how" className="border-t border-border/60 bg-secondary/30">
      <div className="mx-auto max-w-5xl px-6 py-20 sm:py-24">
        <div className="max-w-2xl">
          <p className="text-sm font-medium uppercase tracking-wide text-clay">How you use it</p>
          <h2 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">
            No code. Just what your app does.
          </h2>
          <p className="mt-3 max-w-md text-muted-foreground">
            Five plain steps — from opening your app to watching a change get built.
          </p>
        </div>

        <div className="mt-12 grid gap-12 lg:grid-cols-[220px_1fr] lg:gap-16">
          {/* Sticky stepper */}
          <nav className="sticky top-24 hidden h-fit flex-col gap-1 self-start lg:flex">
            {WSTEPS.map((s, i) => (
              <button
                key={s.title}
                type="button"
                onClick={() => refs.current[i]?.scrollIntoView({ behavior: "smooth", block: "center" })}
                className={cn(
                  "flex items-center gap-3 rounded-lg px-3 py-2 text-left text-sm transition-colors",
                  active === i ? "bg-card font-medium text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"
                )}
              >
                <span
                  className={cn(
                    "flex size-6 shrink-0 items-center justify-center rounded-full text-xs font-medium",
                    active === i ? "bg-clay text-white" : "bg-clay/12 text-clay"
                  )}
                >
                  {i + 1}
                </span>
                {s.title}
              </button>
            ))}
          </nav>

          {/* Panels */}
          <div className="flex flex-col gap-16 lg:gap-0">
            {WSTEPS.map((s, i) => {
              const Visual = s.visual
              return (
                <div
                  key={s.title}
                  ref={(el) => {
                    refs.current[i] = el
                  }}
                  data-index={i}
                  className="flex scroll-mt-24 flex-col justify-center lg:min-h-[80vh]"
                  style={{ scrollSnapAlign: "center" }}
                >
                  <p className="text-sm font-medium text-clay">Step {i + 1}</p>
                  <h3 className="mt-2 text-2xl font-semibold tracking-tight">{s.title}</h3>
                  <p className="mt-2 max-w-md text-[15px] leading-relaxed text-muted-foreground">{s.body}</p>
                  <div className="mt-7">
                    <Visual />
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      </div>
    </section>
  )
}

// ---- Agent prompt section ----

const AGENT_PROMPT = `Use AgentCanvas to help me change this app.

1. Start it: run \`agentcanvas start --workspace .\` (if it isn't installed, run \`pip install agentcanvas\` first). Open the local URL it prints so I can see and edit my app's flows in plain English.
2. When I make a change there, AgentCanvas writes it to \`.agentcanvas/pending/\` as a plain-English request (a .md and a .json per change).
3. For each pending request: read it, make the change in the code, run the relevant tests, then re-index with \`agentcanvas index --workspace .\` and tell me what changed.

Keep checking \`.agentcanvas/pending/\` for new requests while we work.`

function AgentPrompt() {
  return (
    <section id="agent" className="mx-auto max-w-3xl px-6 py-24 text-center">
      <p className="text-sm font-medium uppercase tracking-wide text-clay">For your agent</p>
      <h2 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">
        Already chatting with an AI coding agent?
      </h2>
      <p className="mx-auto mt-3 max-w-lg text-muted-foreground">
        Paste this into Claude Code, Codex, or Cursor and it'll launch AgentCanvas and pick up the
        changes you make — no setup from you.
      </p>
      <CopyBox text={AGENT_PROMPT} className="mt-8 text-left" />
    </section>
  )
}

// ---- Visuals ----

function MockCard({ children }: { children: ReactNode }) {
  return <div className="rounded-2xl border bg-card p-4 shadow-lg sm:p-5">{children}</div>
}

function VisualOpen() {
  return (
    <MockCard>
      <div className="mb-3 flex items-center gap-2 text-xs text-muted-foreground">
        <Sparkles className="size-3.5 text-clay" /> your-app · what your app does
      </div>
      <div className="grid grid-cols-2 gap-2.5">
        {["Placing an order", "Signing in", "Refunds & returns", "Sending emails"].map((t) => (
          <div key={t} className="rounded-xl border bg-background p-3 text-sm font-medium">
            {t}
          </div>
        ))}
      </div>
    </MockCard>
  )
}

function VisualFlow() {
  return (
    <MockCard>
      <div className="space-y-2.5">
        <FlowStep tone="when" label="When" text="Someone places an order" />
        <FlowStep tone="act" label="Do" text="Check the items are in stock" />
        <div className="flex justify-center py-0.5">
          <span className="inline-flex items-center gap-1.5 rounded-full bg-rule-bg px-3 py-1 text-xs font-medium text-rule-fg">
            <GitBranch className="size-3" /> If the card is approved
          </span>
        </div>
        <FlowStep tone="act" label="Do" text="Send them a confirmation email" indent />
      </div>
    </MockCard>
  )
}

function VisualCompose() {
  return (
    <MockCard>
      <div className="mb-2 flex items-center gap-2">
        <Badge variant="secondary" className="rounded-md">Add a step</Badge>
        <span className="text-xs text-muted-foreground">after “Charge their card”</span>
      </div>
      <div className="flex items-center gap-2 rounded-xl border bg-background px-3 py-2">
        <span className="flex-1 text-sm">Text them the delivery date</span>
        <span className="flex size-7 items-center justify-center rounded-full bg-primary text-primary-foreground">
          <ArrowUp className="size-4" />
        </span>
      </div>
    </MockCard>
  )
}

function VisualSend() {
  return (
    <MockCard>
      <div className="mb-3 flex items-center justify-between">
        <span className="text-sm font-medium">2 changes ready</span>
        <span className="inline-flex items-center gap-1.5 rounded-full bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground">
          <Send className="size-3" /> Send to Claude Code
        </span>
      </div>
      <div className="space-y-2 text-sm">
        <div className="flex items-center gap-2">
          <Badge className="rounded-md bg-act-bg text-act-fg hover:bg-act-bg">New</Badge>
          <span className="truncate text-muted-foreground">Text the delivery date after the order ships</span>
        </div>
        <div className="flex items-center gap-2">
          <Badge className="rounded-md bg-when-bg text-when-fg hover:bg-when-bg">Edited</Badge>
          <span className="truncate text-muted-foreground">Charge the card — also apply loyalty points</span>
        </div>
      </div>
    </MockCard>
  )
}

function VisualBuilt() {
  return (
    <MockCard>
      <div className="mb-3 flex items-center gap-2 text-sm font-medium">
        <CircleCheck className="size-4 text-act-fg" /> All set — your changes are live
      </div>
      <div className="space-y-2 text-sm text-muted-foreground">
        <div className="flex items-center gap-2">
          <CircleCheck className="size-3.5 text-act-fg" /> Added the delivery text message
        </div>
        <div className="flex items-center gap-2">
          <Loader2 className="size-3.5 animate-spin text-primary" /> Updating how the card is charged…
        </div>
      </div>
    </MockCard>
  )
}

// ---- Hero browser frame + shared bits ----

function BrowserFrame() {
  return (
    <div className="overflow-hidden rounded-2xl border bg-card shadow-2xl shadow-primary/5">
      <div className="flex items-center gap-2 border-b bg-secondary/50 px-4 py-3">
        <span className="size-2.5 rounded-full bg-muted-foreground/25" />
        <span className="size-2.5 rounded-full bg-muted-foreground/25" />
        <span className="size-2.5 rounded-full bg-muted-foreground/25" />
        <span className="ml-3 inline-flex items-center gap-1.5 rounded-md bg-background px-3 py-1 text-xs text-muted-foreground">
          <Sparkles className="size-3 text-clay" /> your-app · what your app does
        </span>
      </div>
      <div className="p-6 sm:p-8">
        <p className="text-sm font-medium">Placing an order</p>
        <p className="mb-5 text-xs text-muted-foreground">What happens when someone checks out</p>
        <div className="space-y-2.5">
          <FlowStep tone="when" label="When" text="Someone places an order" />
          <FlowStep tone="act" label="Do" text="Check the items are in stock" />
          <div className="flex justify-center py-1">
            <span className="inline-flex items-center gap-1.5 rounded-full bg-rule-bg px-3.5 py-1.5 text-[13px] font-medium text-rule-fg">
              <GitBranch className="size-3.5" /> If everything is in stock
            </span>
          </div>
          <FlowStep tone="act" label="Do" text="Charge their card" indent />
          <FlowStep tone="act" label="Do" text="Send them a confirmation email" indent />
        </div>
      </div>
    </div>
  )
}

function FlowStep({
  tone,
  label,
  text,
  indent,
}: {
  tone: "when" | "act"
  label: string
  text: string
  indent?: boolean
}) {
  return (
    <div className={cn("flex items-center gap-3 rounded-xl border bg-background p-3", indent && "ml-6")}>
      <span
        className={cn(
          "flex shrink-0 items-center gap-1.5 rounded-md px-2 py-1 text-[11px] font-medium",
          tone === "when" ? "bg-when-bg text-when-fg" : "bg-act-bg text-act-fg"
        )}
      >
        {tone === "when" ? <Zap className="size-3" /> : <Play className="size-3" />}
        {label}
      </span>
      <span className="min-w-0 truncate text-sm">{text}</span>
    </div>
  )
}

function CopyBox({
  text,
  oneLine,
  className,
}: {
  text: string
  oneLine?: boolean
  className?: string
}) {
  const [copied, setCopied] = useState(false)
  async function copy() {
    await navigator.clipboard.writeText(text)
    setCopied(true)
    window.setTimeout(() => setCopied(false), 1400)
  }
  return (
    <div className={cn("overflow-hidden rounded-xl border bg-card", className)}>
      <div className="flex items-center justify-between gap-3 border-b bg-secondary/40 px-3 py-2">
        <span className="text-xs font-medium text-muted-foreground">
          {oneLine ? "Terminal" : "Prompt"}
        </span>
        <button
          type="button"
          onClick={copy}
          className="inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-xs font-medium text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
        >
          {copied ? <Check className="size-3.5" /> : <Clipboard className="size-3.5" />}
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <pre
        className={cn(
          "overflow-x-auto px-4 py-3 font-mono text-xs leading-relaxed text-foreground/80",
          oneLine ? "whitespace-pre" : "whitespace-pre-wrap"
        )}
      >
        {text}
      </pre>
    </div>
  )
}
