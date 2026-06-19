import { useEffect, useRef, useState, type ReactNode } from "react"
import {
  ArrowRight,
  ArrowUp,
  Check,
  CircleCheck,
  Clipboard,
  GitBranch,
  Loader2,
  MousePointer2,
  Orbit,
  Play,
  Send,
  Sparkles,
  SquareTerminal,
  X,
  Zap,
} from "lucide-react"
import { siClaudecode, siCursor, siGooglegemini } from "simple-icons"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { BrandMark } from "@/components/BrandMark"
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
            <BrandMark />
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
            <span>
              Works with{" "}
              <span className="font-medium text-foreground">Claude Code, Codex, Cursor</span> &amp; more
            </span>
          </Badge>
          <h1 className="text-balance text-[2.75rem] font-semibold leading-[1.03] tracking-[-0.02em] sm:text-[4.25rem]">
            Your app, in plain English.
            <br />
            <span className="text-foreground/55">Your AI agent, too.</span>
          </h1>
          <p className="mx-auto mt-6 max-w-xl text-balance text-lg leading-relaxed text-muted-foreground sm:text-xl">
            A friendlier way to steer the app an AI is building for you. See what it does, change it
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

        <WorksWith />

        <HowItWorks />

        <AgentPrompt />

        {/* Try it */}
        <section id="try" className="border-t border-border/60 bg-secondary/30">
          <div className="mx-auto max-w-2xl px-6 py-24 text-center">
            <h2 className="text-3xl font-semibold tracking-tight sm:text-4xl">Have a look around.</h2>
            <p className="mx-auto mt-3 max-w-md text-muted-foreground">
              The demo is a small online shop. Nothing to install. Click through it and try changing
              a step.
            </p>
            <Button type="button" size="lg" onClick={openDemo} className="mt-7 h-12 rounded-full px-7 text-base">
              <Play className="size-4" />
              {onEnterApp ? "Back to your app" : "Open the demo"}
            </Button>

            <div className="mx-auto mt-14 max-w-md rounded-2xl border bg-card p-5 text-left">
              <p className="text-sm font-medium">Already have a project?</p>
              <p className="mt-1 text-sm text-muted-foreground">
                Point AgentCanvas at it from your terminal, or ask whoever set it up to run:
              </p>
              <CopyBox text="agentcanvas start --workspace ./your-project" oneLine />
            </div>
          </div>
        </section>
      </main>

      <footer className="border-t border-border/60">
        <div className="mx-auto flex max-w-5xl flex-col items-center gap-3 px-6 py-12 text-center">
          <span className="flex items-center gap-2 text-sm font-semibold">
            <BrandMark className="size-6" iconClassName="size-4" />
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

// ---- "Works with" logo strip ----

function SimpleLogo({ path }: { path: string }) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" className="size-[18px] fill-current">
      <path d={path} />
    </svg>
  )
}

function WorksWith() {
  const tools = [
    { name: "Claude Code", logo: <SimpleLogo path={siClaudecode.path} /> },
    { name: "Codex", logo: <SquareTerminal className="size-[18px]" /> },
    { name: "Cursor", logo: <SimpleLogo path={siCursor.path} /> },
    { name: "Antigravity", logo: <Orbit className="size-[18px]" /> },
    { name: "Gemini", logo: <SimpleLogo path={siGooglegemini.path} /> },
  ]
  return (
    <section className="mx-auto max-w-4xl px-6 pb-16">
      <p className="mb-7 text-center text-xs font-medium uppercase tracking-wide text-muted-foreground">
        Works with your AI coding agent
      </p>
      <div className="flex flex-wrap items-center justify-center gap-x-9 gap-y-5">
        {tools.map((t) => (
          <span
            key={t.name}
            className="inline-flex items-center gap-2 text-[15px] font-medium text-foreground/70 transition-colors hover:text-foreground"
          >
            {t.logo}
            {t.name}
          </span>
        ))}
      </div>
    </section>
  )
}

// ---- Demo timeline (5 steps, auto-advancing + looping, jumpable) ----

const STEP_MS = [2000, 2000, 2900, 2200, 2900]

function useDemo() {
  const [step, setStepRaw] = useState(0)
  const timer = useRef<number | undefined>(undefined)
  useEffect(() => {
    timer.current = window.setTimeout(() => setStepRaw((s) => (s + 1) % STEP_MS.length), STEP_MS[step])
    return () => window.clearTimeout(timer.current)
  }, [step])
  return { step, setStep: setStepRaw }
}

const STEPS = [
  {
    title: "Open your app",
    body: "Point AgentCanvas at your project. It reads everything and lays your app out as plain flows.",
  },
  {
    title: "See what it does",
    body: "Every part of your app, written as plain steps you can read: when this happens, do that, with the branches in between.",
  },
  {
    title: "Change a step",
    body: "Click any step and say what you want instead, in your own words.",
  },
  {
    title: "Send it off",
    body: "Your changes line up, then go to your agent as one clear request.",
  },
  {
    title: "Watch it happen",
    body: "Your agent builds it, and the map updates to match.",
  },
]

function HowItWorks() {
  const { step, setStep } = useDemo()
  return (
    <section id="how" className="border-t border-border/60 bg-secondary/30">
      <div className="mx-auto max-w-6xl px-6 py-20 sm:py-24">
        <div className="text-center">
          <p className="text-sm font-medium uppercase tracking-wide text-clay">How it works</p>
          <h2 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">
            No code. Just what your app does.
          </h2>
        </div>

        <div className="mt-12 grid items-start gap-10 lg:grid-cols-[300px_1fr]">
          <nav className="flex flex-col gap-1.5">
            {STEPS.map((s, i) => {
              const active = i === step
              return (
                <button
                  key={s.title}
                  type="button"
                  onClick={() => setStep(i)}
                  className={cn(
                    "flex items-start gap-3 rounded-xl border px-4 py-3 text-left transition-all",
                    active ? "border-clay/30 bg-card shadow-sm" : "border-transparent hover:bg-card/60"
                  )}
                >
                  <span
                    className={cn(
                      "mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-full text-xs font-medium transition-colors",
                      active ? "bg-clay text-white" : "bg-clay/12 text-clay"
                    )}
                  >
                    {i + 1}
                  </span>
                  <span>
                    <span className={cn("text-sm font-medium", !active && "text-muted-foreground")}>
                      {s.title}
                    </span>
                    {active && (
                      <span className="mt-1 block text-[13px] leading-relaxed text-muted-foreground">
                        {s.body}
                      </span>
                    )}
                  </span>
                </button>
              )
            })}
          </nav>

          <div className="lg:sticky lg:top-24">
            <DemoFrame step={step} />
          </div>
        </div>
      </div>
    </section>
  )
}

// ---- The animated product frame, driven by `step` (0..4) ----

function DemoFrame({ step }: { step: number }) {
  const FULL = "Text them the delivery date"
  const [typed, setTyped] = useState("")
  useEffect(() => {
    if (step < 2) {
      setTyped("")
      return
    }
    if (step > 2) {
      setTyped(FULL)
      return
    }
    setTyped("")
    let i = 0
    const id = window.setInterval(() => {
      i += 1
      setTyped(FULL.slice(0, i))
      if (i >= FULL.length) window.clearInterval(id)
    }, 1700 / FULL.length)
    return () => window.clearInterval(id)
  }, [step])

  // step 4 plays "working" then "done"
  const [done, setDone] = useState(false)
  useEffect(() => {
    if (step !== 4) {
      setDone(false)
      return
    }
    setDone(false)
    const t = window.setTimeout(() => setDone(true), 1200)
    return () => window.clearTimeout(t)
  }, [step])

  const overview = step === 0
  const highlight = step === 2 || step === 3 || (step === 4 && !done)
  const showNew = step === 4 && done

  return (
    <div className="overflow-hidden rounded-2xl border bg-card shadow-2xl shadow-primary/5">
      <div className="flex items-center gap-2 border-b bg-secondary/50 px-4 py-3">
        <span className="size-2.5 rounded-full bg-muted-foreground/25" />
        <span className="size-2.5 rounded-full bg-muted-foreground/25" />
        <span className="size-2.5 rounded-full bg-muted-foreground/25" />
        <span className="ml-2 inline-flex items-center gap-1.5 rounded-md bg-background px-3 py-1 text-xs text-muted-foreground">
          <Sparkles className="size-3 text-clay" /> your-app · what your app does
        </span>
        <span className="ml-auto hidden items-center gap-1.5 rounded-full border bg-background px-2.5 py-1 text-[11px] text-muted-foreground sm:inline-flex">
          <Sparkles className="size-3 text-clay" /> Assistant:{" "}
          <span className="font-medium text-foreground">Claude Code</span>
        </span>
      </div>

      <div className="flex">
        <aside className="hidden w-44 shrink-0 flex-col gap-0.5 border-r bg-secondary/20 p-3 md:flex">
          <span
            className={cn(
              "mb-1 inline-flex items-center gap-2 rounded-lg px-2.5 py-1.5 text-xs font-medium",
              overview ? "bg-background shadow-sm" : "text-muted-foreground"
            )}
          >
            <Sparkles className={cn("size-3.5", overview ? "text-clay" : "opacity-60")} /> All flows
          </span>
          <p className="px-2 pb-1 pt-2 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
            Journeys
          </p>
          {[
            { t: "Placing an order", active: !overview },
            { t: "Signing in", active: false },
            { t: "Refunds & returns", active: false },
          ].map((j) => (
            <span
              key={j.t}
              className={cn(
                "flex items-center gap-2 rounded-lg px-2.5 py-1.5 text-xs",
                j.active ? "bg-background font-medium shadow-sm" : "text-muted-foreground"
              )}
            >
              <span className={cn("size-1.5 rounded-full", j.active ? "bg-clay" : "bg-muted-foreground/35")} />
              {j.t}
            </span>
          ))}
        </aside>

        <div className="min-h-[360px] min-w-0 flex-1 p-5 sm:p-6">
          {overview ? (
            <>
              <p className="text-sm font-medium">What your app does</p>
              <p className="mb-4 text-xs text-muted-foreground">Each card is a moment someone uses your app</p>
              <div className="grid grid-cols-2 gap-2.5">
                {["Placing an order", "Signing in", "Refunds & returns", "Sending emails"].map((t) => (
                  <div key={t} className="rounded-xl border bg-background p-3 text-[13px] font-medium">
                    {t}
                  </div>
                ))}
              </div>
            </>
          ) : (
            <>
              <p className="text-sm font-medium">Placing an order</p>
              <p className="mb-4 text-xs text-muted-foreground">What happens when someone checks out</p>
              <div className="space-y-2.5">
                <HeroRow tone="when" label="When" text="Someone places an order" />
                <HeroRow tone="act" label="Do" text="Check the items are in stock" />
                <div className="flex justify-center py-0.5">
                  <span className="inline-flex items-center gap-1.5 rounded-full bg-rule-bg px-3 py-1 text-xs font-medium text-rule-fg">
                    <GitBranch className="size-3" /> If everything is in stock
                  </span>
                </div>
                <div className="grid gap-3 sm:grid-cols-2">
                  <Lane tone="yes" label="If yes">
                    <HeroRow tone="act" label="Do" text="Work out the total" compact />
                    <HeroRow
                      tone="act"
                      label="Do"
                      text="Charge their card"
                      compact
                      highlight={highlight}
                      cursor={step === 2 && typed.length === 0}
                    />
                    <div
                      className={cn(
                        "grid transition-all duration-500 ease-out",
                        showNew ? "grid-rows-[1fr] opacity-100" : "grid-rows-[0fr] opacity-0"
                      )}
                    >
                      <div className="overflow-hidden">
                        <div className="pt-2">
                          <HeroRow tone="act" label="Do" text="Text them the delivery date" compact fresh />
                        </div>
                      </div>
                    </div>
                  </Lane>
                  <Lane tone="no" label="Otherwise">
                    <HeroRow tone="act" label="Do" text="Tell them what's sold out" compact />
                    <HeroRow tone="act" label="Do" text="Save their cart for later" compact />
                  </Lane>
                </div>
              </div>

              <div className="relative mt-4 min-h-[66px]">
                {step === 2 && (
                  <div className="flex animate-fade-in items-center gap-2 rounded-xl border bg-background px-3 py-2">
                    <Badge variant="secondary" className="shrink-0 rounded-md text-[11px]">
                      Add a step
                    </Badge>
                    <span className="min-w-0 flex-1 truncate text-sm">
                      {typed}
                      <span className="ml-px inline-block h-3.5 w-px translate-y-[2px] animate-pulse bg-foreground/60 align-middle" />
                    </span>
                    <span className="relative flex size-7 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground">
                      <ArrowUp className="size-4" />
                      {typed.length >= FULL.length && <Cursor className="-bottom-1 -right-1" />}
                    </span>
                  </div>
                )}
                {step === 3 && (
                  <div className="animate-fade-in rounded-xl border bg-background p-3">
                    <div className="mb-2 flex items-center justify-between">
                      <span className="text-sm font-medium">1 change ready</span>
                      <span className="relative inline-flex items-center gap-1.5 rounded-full bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground">
                        <Send className="size-3" /> Send to Claude Code
                        <Cursor className="-bottom-1.5 -right-1.5" />
                      </span>
                    </div>
                    <div className="flex items-center gap-2 text-sm">
                      <Badge className="shrink-0 rounded-md bg-act-bg text-act-fg hover:bg-act-bg">New</Badge>
                      <span className="truncate text-muted-foreground">
                        Text the delivery date after charging the card
                      </span>
                    </div>
                  </div>
                )}
                {step === 4 && !done && (
                  <div className="flex animate-fade-in items-center gap-2.5 rounded-xl border bg-background px-3 py-3 text-sm">
                    <Loader2 className="size-4 shrink-0 animate-spin text-primary" />
                    <span className="text-muted-foreground">Claude Code is making your change…</span>
                  </div>
                )}
                {step === 4 && done && (
                  <div className="flex animate-fade-in items-center gap-2.5 rounded-xl border bg-background px-3 py-3 text-sm">
                    <CircleCheck className="size-4 shrink-0 text-act-fg" />
                    <span className="font-medium">All set, your change is live</span>
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}

function Lane({ tone, label, children }: { tone: "yes" | "no"; label: string; children: ReactNode }) {
  return (
    <div
      className={cn(
        "rounded-xl border border-dashed p-2.5",
        tone === "yes" ? "border-act-accent/40 bg-act-bg/20" : "border-border bg-secondary/30"
      )}
    >
      <div className="mb-2 flex items-center gap-1.5 px-0.5">
        <span
          className={cn(
            "flex size-3.5 items-center justify-center rounded-full text-white",
            tone === "yes" ? "bg-act-accent" : "bg-muted-foreground"
          )}
        >
          {tone === "yes" ? <Check className="size-2.5" /> : <X className="size-2.5" />}
        </span>
        <span className="text-[11px] font-medium text-muted-foreground">{label}</span>
      </div>
      <div className="space-y-2">{children}</div>
    </div>
  )
}

function Cursor({ className }: { className?: string }) {
  return (
    <span className={cn("pointer-events-none absolute z-10 animate-fade-in", className)}>
      <MousePointer2 className="size-4 fill-foreground text-foreground drop-shadow-sm" />
    </span>
  )
}

function HeroRow({
  tone,
  label,
  text,
  compact,
  highlight,
  cursor,
  fresh,
}: {
  tone: "when" | "act"
  label: string
  text: string
  compact?: boolean
  highlight?: boolean
  cursor?: boolean
  fresh?: boolean
}) {
  return (
    <div
      className={cn(
        "relative flex items-center gap-2.5 rounded-lg border bg-background transition-all duration-300",
        compact ? "p-2" : "rounded-xl p-3",
        highlight && "border-primary/50 ring-2 ring-primary/15",
        fresh && "border-act-accent/60"
      )}
    >
      <span
        className={cn(
          "flex shrink-0 items-center gap-1.5 rounded-md px-1.5 py-0.5 text-[11px] font-medium",
          tone === "when" ? "bg-when-bg text-when-fg" : "bg-act-bg text-act-fg"
        )}
      >
        {tone === "when" ? <Zap className="size-3" /> : <Play className="size-3" />}
        {label}
      </span>
      <span className="min-w-0 truncate text-[13px]">{text}</span>
      {cursor && <Cursor className="right-2.5 top-1/2" />}
    </div>
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
        changes you make. No setup from you.
      </p>
      <CopyBox text={AGENT_PROMPT} className="mt-8 text-left" />
    </section>
  )
}

function CopyBox({ text, oneLine, className }: { text: string; oneLine?: boolean; className?: string }) {
  const [copied, setCopied] = useState(false)
  async function copy() {
    await navigator.clipboard.writeText(text)
    setCopied(true)
    window.setTimeout(() => setCopied(false), 1400)
  }
  return (
    <div className={cn("overflow-hidden rounded-xl border bg-card", className)}>
      <div className="flex items-center justify-between gap-3 border-b bg-secondary/40 px-3 py-2">
        <span className="text-xs font-medium text-muted-foreground">{oneLine ? "Terminal" : "Prompt"}</span>
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
