import { useState } from "react"
import {
  ArrowRight,
  Check,
  Clipboard,
  GitBranch,
  Play,
  Sparkles,
  Zap,
  type LucideIcon,
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
      {/* Nav */}
      <header className="sticky top-0 z-40 border-b border-border/60 bg-background/80 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-5xl items-center px-6">
          <span className="flex items-center gap-2 font-medium">
            <span className="flex size-7 items-center justify-center rounded-md bg-primary text-primary-foreground">
              <Sparkles className="size-4" />
            </span>
            AgentCanvas
          </span>
          <nav className="ml-auto hidden items-center gap-7 text-sm text-muted-foreground sm:flex">
            <a href="#how" className="transition-colors hover:text-foreground">
              How it works
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
            See what your app does, change it in your own words, and tell your AI coding agent —
            Claude Code, Codex, Cursor — exactly what to build. All in plain English.
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

        {/* Hero product visual */}
        <section className="mx-auto max-w-3xl px-6 pb-24">
          <BrowserFrame />
        </section>

        {/* How you use it */}
        <section id="how" className="border-t border-border/60 bg-secondary/30">
          <div className="mx-auto max-w-5xl px-6 py-24">
            <div className="mx-auto max-w-2xl text-center">
              <p className="text-sm font-medium uppercase tracking-wide text-primary">How you use it</p>
              <h2 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">
                No code. Just what your app does.
              </h2>
              <p className="mx-auto mt-3 max-w-md text-muted-foreground">
                Five plain steps — from opening your app to watching a change get built.
              </p>
            </div>

            <ol className="mx-auto mt-14 max-w-2xl space-y-3">
              {STEPS.map((step, i) => (
                <li
                  key={step.title}
                  className="flex items-start gap-5 rounded-2xl border bg-card p-5 sm:p-6"
                >
                  <span className="flex size-9 shrink-0 items-center justify-center rounded-full bg-primary/10 text-sm font-medium text-primary">
                    {i + 1}
                  </span>
                  <div className="pt-1">
                    <p className="text-base font-medium">{step.title}</p>
                    <p className="mt-1 text-[15px] leading-relaxed text-muted-foreground">{step.body}</p>
                  </div>
                </li>
              ))}
            </ol>
          </div>
        </section>

        {/* Reassurance band */}
        <section className="mx-auto max-w-5xl px-6 py-24">
          <div className="grid gap-10 md:grid-cols-3">
            <Value
              Icon={Zap}
              title="It reads like a story"
              body="“When someone places an order, charge their card.” No files, no code, no jargon — just what happens."
            />
            <Value
              Icon={GitBranch}
              title="You're in control"
              body="Change a step, add a rule, or remove one — in your own words. Nothing happens until you say go."
            />
            <Value
              Icon={Sparkles}
              title="Work with your agent in plain English"
              body="Describe a change like you'd tell a teammate. Claude Code, Codex, or Cursor gets a clear request — and builds it for you."
            />
          </div>
        </section>

        {/* Try it */}
        <section id="try" className="border-t border-border/60 bg-secondary/30">
          <div className="mx-auto max-w-2xl px-6 py-24 text-center">
            <h2 className="text-3xl font-semibold tracking-tight sm:text-4xl">Have a look around.</h2>
            <p className="mx-auto mt-3 max-w-md text-muted-foreground">
              The demo is a small online shop. Nothing to install — click through it and try
              changing a step.
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
              <CopyCommand command="agentcanvas start --workspace ./your-project" />
            </div>
          </div>
        </section>
      </main>

      <footer className="border-t border-border/60">
        <div className="mx-auto flex max-w-5xl flex-col items-center gap-3 px-6 py-12 text-center">
          <span className="flex items-center gap-2 text-sm font-medium">
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

const STEPS = [
  { title: "Open your app", body: "Point AgentCanvas at your project — or just try the demo. It reads everything and lays it out for you." },
  { title: "See what it does", body: "Every part of your app, written as plain steps you can actually read — grouped by what people do." },
  { title: "Change a step", body: "Click anything and say what you want instead, in your own words. Add a step, add a rule, or remove one." },
  { title: "Send it off", body: "Your changes become one clear request for your AI assistant — no technical handoff needed." },
  { title: "Watch it happen", body: "Your assistant builds it, and the map updates to match. You always see what changed." },
]

function Value({ Icon, title, body }: { Icon: LucideIcon; title: string; body: string }) {
  return (
    <div>
      <span className="flex size-11 items-center justify-center rounded-xl bg-primary/10 text-primary">
        <Icon className="size-5" />
      </span>
      <p className="mt-5 text-lg font-medium">{title}</p>
      <p className="mt-2 text-[15px] leading-relaxed text-muted-foreground">{body}</p>
    </div>
  )
}

function BrowserFrame() {
  return (
    <div className="overflow-hidden rounded-2xl border bg-card shadow-2xl shadow-primary/5">
      <div className="flex items-center gap-2 border-b bg-secondary/50 px-4 py-3">
        <span className="size-2.5 rounded-full bg-muted-foreground/25" />
        <span className="size-2.5 rounded-full bg-muted-foreground/25" />
        <span className="size-2.5 rounded-full bg-muted-foreground/25" />
        <span className="ml-3 inline-flex items-center gap-1.5 rounded-md bg-background px-3 py-1 text-xs text-muted-foreground">
          <Sparkles className="size-3 text-primary" /> your-app · what your app does
        </span>
      </div>
      <div className="p-6 sm:p-8">
        <p className="text-sm font-medium">Placing an order</p>
        <p className="mb-5 text-xs text-muted-foreground">What happens when someone checks out</p>
        <div className="space-y-2.5">
          <Step tone="when" label="When" text="Someone places an order" />
          <Step tone="act" label="Do" text="Check the items are in stock" />
          <Branch text="If everything is in stock" />
          <Step tone="act" label="Do" text="Charge their card" indent />
          <Step tone="act" label="Do" text="Send them a confirmation email" indent />
        </div>
      </div>
    </div>
  )
}

function Step({
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

function Branch({ text }: { text: string }) {
  return (
    <div className="flex justify-center py-1">
      <span className="inline-flex items-center gap-1.5 rounded-full bg-rule-bg px-3.5 py-1.5 text-[13px] font-medium text-rule-fg">
        <GitBranch className="size-3.5" />
        {text}
      </span>
    </div>
  )
}

function CopyCommand({ command }: { command: string }) {
  const [copied, setCopied] = useState(false)
  async function copy() {
    await navigator.clipboard.writeText(command)
    setCopied(true)
    window.setTimeout(() => setCopied(false), 1200)
  }
  return (
    <div className="mt-3 flex items-center gap-2 rounded-lg border bg-secondary/50 px-3 py-2">
      <code className="min-w-0 flex-1 truncate font-mono text-xs text-muted-foreground">{command}</code>
      <button
        type="button"
        onClick={copy}
        aria-label="Copy command"
        className="shrink-0 rounded-md p-1 text-muted-foreground hover:bg-secondary hover:text-foreground"
      >
        {copied ? <Check className="size-3.5" /> : <Clipboard className="size-3.5" />}
      </button>
    </div>
  )
}
