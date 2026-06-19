import { useState } from "react"
import {
  ArrowRight,
  Check,
  Clipboard,
  GitBranch,
  MessageSquare,
  MousePointerClick,
  Play,
  Sparkles,
  Wand2,
  Zap,
  type LucideIcon,
} from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

export function LandingPage() {
  function openDemo() {
    const url = new URL(window.location.href)
    url.searchParams.set("demo", "1")
    window.location.href = url.toString()
  }

  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="sticky top-0 z-40 border-b bg-background/85 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-5xl items-center px-6">
          <span className="flex items-center gap-2 font-medium">
            <span className="flex size-7 items-center justify-center rounded-md bg-primary text-primary-foreground">
              <Sparkles className="size-4" />
            </span>
            AgentCanvas
          </span>
          <Button type="button" size="sm" onClick={openDemo} className="ml-auto rounded-full">
            <Play className="size-4" />
            Try the demo
          </Button>
        </div>
      </header>

      <main>
        {/* Hero */}
        <section className="mx-auto max-w-3xl px-6 pb-10 pt-16 text-center sm:pt-24">
          <Badge variant="secondary" className="mb-6 rounded-full px-3 py-1 font-normal">
            Works with Claude Code, Codex, Cursor & more
          </Badge>
          <h1 className="text-balance text-4xl font-medium leading-[1.08] tracking-tight sm:text-[56px]">
            See what your app actually does.
          </h1>
          <p className="mx-auto mt-5 max-w-xl text-balance text-lg leading-relaxed text-muted-foreground">
            AgentCanvas turns your app into a simple map of what happens — in plain English. Change
            how it works by editing the map, and your AI assistant makes it real.
          </p>
          <div className="mt-8 flex flex-wrap justify-center gap-3">
            <Button type="button" size="lg" onClick={openDemo} className="rounded-full px-6">
              Try the demo
              <ArrowRight className="size-4" />
            </Button>
            <Button asChild variant="outline" size="lg" className="rounded-full px-6">
              <a href="#how">See how it works</a>
            </Button>
          </div>
        </section>

        {/* Visual */}
        <section className="mx-auto max-w-lg px-6 pb-20">
          <FlowPreview />
        </section>

        {/* How it works */}
        <section id="how" className="border-t bg-secondary/30">
          <div className="mx-auto max-w-4xl px-6 py-16">
            <h2 className="text-center text-2xl font-medium tracking-tight">
              No code. Just what your app does.
            </h2>
            <div className="mt-10 grid gap-5 md:grid-cols-3">
              <HowStep
                Icon={MousePointerClick}
                title="See it"
                body="Open your app and read it like a story — “when someone places an order, charge their card.” No files, no jargon."
              />
              <HowStep
                Icon={Wand2}
                title="Change it"
                body="Click a step and describe what you want instead, in your own words. Add a step, add a rule, or remove one."
              />
              <HowStep
                Icon={MessageSquare}
                title="It gets built"
                body="Your changes go to your AI coding assistant as a clear request. You watch it happen and the map updates."
              />
            </div>
          </div>
        </section>

        {/* Try it */}
        <section className="mx-auto max-w-3xl px-6 py-20 text-center">
          <h2 className="text-2xl font-medium tracking-tight">Have a look around.</h2>
          <p className="mx-auto mt-2.5 max-w-md text-muted-foreground">
            The demo is a small online shop. Nothing to install — click through it and try changing
            a step.
          </p>
          <Button type="button" size="lg" onClick={openDemo} className="mt-6 rounded-full px-6">
            <Play className="size-4" />
            Open the demo
          </Button>

          <div className="mx-auto mt-12 max-w-md rounded-2xl border bg-card p-5 text-left">
            <p className="text-sm font-medium">Already have a project?</p>
            <p className="mt-1 text-sm text-muted-foreground">
              Point AgentCanvas at it from your terminal — or ask whoever set it up to run:
            </p>
            <CopyCommand command="agentcanvas start --workspace ./your-project" />
          </div>
        </section>
      </main>

      <footer className="border-t">
        <div className="mx-auto flex max-w-5xl flex-col items-center gap-2 px-6 py-8 text-center text-xs text-muted-foreground">
          <span className="flex items-center gap-1.5">
            <Sparkles className="size-3.5" /> AgentCanvas
          </span>
          <span>A friendlier way to steer the app an AI is building for you.</span>
        </div>
      </footer>
    </div>
  )
}

function HowStep({ Icon, title, body }: { Icon: LucideIcon; title: string; body: string }) {
  return (
    <div className="rounded-2xl border bg-card p-6">
      <span className="flex size-10 items-center justify-center rounded-xl bg-primary/10 text-primary">
        <Icon className="size-5" />
      </span>
      <p className="mt-4 text-base font-medium">{title}</p>
      <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{body}</p>
    </div>
  )
}

function FlowPreview() {
  return (
    <div className="rounded-2xl border bg-card p-5 shadow-xl">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <p className="text-sm font-medium">Placing an order</p>
          <p className="text-xs text-muted-foreground">What happens when someone checks out</p>
        </div>
        <Badge variant="secondary" className="rounded-full font-normal">
          Example
        </Badge>
      </div>
      <div className="space-y-2.5">
        <PreviewStep tone="when" Icon={Zap} label="When" text="Someone places an order" />
        <PreviewStep tone="act" Icon={Play} label="Do" text="Check the items are in stock" />
        <PreviewStep tone="rule" Icon={GitBranch} label="If" text="The card is approved" />
        <PreviewStep tone="act" Icon={Play} label="Do" text="Send them a confirmation email" />
      </div>
    </div>
  )
}

function PreviewStep({
  tone,
  Icon,
  label,
  text,
}: {
  tone: "when" | "act" | "rule"
  Icon: LucideIcon
  label: string
  text: string
}) {
  return (
    <div className="flex items-center gap-3 rounded-xl border bg-background p-3">
      <span
        className={cn(
          "flex shrink-0 items-center gap-1.5 rounded-md px-2 py-1 text-[11px] font-medium",
          tone === "when" && "bg-when-bg text-when-fg",
          tone === "act" && "bg-act-bg text-act-fg",
          tone === "rule" && "bg-rule-bg text-rule-fg"
        )}
      >
        <Icon className="size-3" />
        {label}
      </span>
      <span className="min-w-0 truncate text-sm">{text}</span>
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
      <code className="min-w-0 flex-1 truncate font-mono text-xs text-muted-foreground">
        {command}
      </code>
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
