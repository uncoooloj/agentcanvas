import { ArrowRight, ArrowUpRight, GitCompare } from "lucide-react"
import { BrandMark } from "@/components/BrandMark"
import { Button } from "@/components/ui/button"
import { LANDING_BOOTSTRAP_PERMISSION_PROMPTS, LANDING_BOOTSTRAP_PROMPT } from "@/lib/landingBootstrapPrompt"
import { InteractiveHeroCanvas } from "./landing/InteractiveHeroCanvas"
import { CommandStrip, StartSection } from "./landing/Initiation"
import { StudioShowcase } from "./landing/StudioShowcase"
import { getSandboxUrl, type SandboxTab } from "./landing/studioDemo"

const shell = "mx-auto max-w-[1280px] px-4 sm:px-8 lg:px-10"
const focus = "rounded-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-ring"

export function LandingPage({
  onEnterApp,
  onTrySandbox,
}: {
  onEnterApp?: () => void
  onTrySandbox?: (initialTab?: "system" | "flows" | "diff") => void
} = {}) {
  function openSandbox(tab: SandboxTab) {
    if (onTrySandbox) {
      onTrySandbox(tab)
    } else {
      window.location.href = getSandboxUrl(window.location.href, tab)
    }
  }

  const primaryAction = onEnterApp ?? (() => openSandbox("flows"))

  return (
    <div id="top" className="min-h-screen bg-background text-foreground antialiased">
      <header className="sticky top-0 z-40 border-b bg-background/95 backdrop-blur">
        <div className={`${shell} flex min-h-16 items-center justify-between gap-3`}>
          <a href="#top" className={`${focus} flex items-center gap-1.5 text-[15px] font-bold tracking-tight`}>
            <BrandMark />
            AgentCanvas
            <span className="ml-1 hidden rounded border bg-card px-1.5 py-0.5 font-mono text-[9px] font-normal tracking-normal text-muted-foreground sm:inline">
              local-first
            </span>
          </a>
          <nav aria-label="Landing page" className="hidden items-center gap-7 text-[13px] font-medium text-muted-foreground md:flex">
            <a href="#canvas" className={`${focus} hover:text-foreground`}>Live Canvas</a>
            <a href="#visual-diff" className={`${focus} hover:text-foreground`}>Visual Diff</a>
            <a href="#start" className={`${focus} hover:text-foreground`}>Start in 10s</a>
          </nav>
          <Button type="button" size="sm" onClick={primaryAction} className="rounded-full px-3.5 text-xs sm:px-4">
            {onEnterApp ? "Back to studio" : "Try sandbox"}
            <ArrowUpRight aria-hidden="true" className="size-3.5" />
          </Button>
        </div>
      </header>

      <main>
        <div className={`${shell} grid items-start gap-10 pb-14 pt-12 sm:pb-16 sm:pt-16 lg:grid-cols-[minmax(0,0.86fr)_minmax(0,1fr)] lg:gap-9 lg:pb-24 lg:pt-20 xl:gap-12`}>
          <section aria-labelledby="landing-title" className="min-w-0 lg:pt-3">
            <h1 id="landing-title" className="text-balance text-[clamp(2.7rem,5.05vw,5.15rem)] font-bold leading-[1.02] tracking-[-0.055em]">
              <span className="block">See what your codebase does.</span>
              <span className="mt-1 block text-[#a7472c] dark:text-clay">Steer your agent visually.</span>
            </h1>
            <p className="mt-5 max-w-xl text-pretty text-[15px] leading-relaxed text-muted-foreground sm:text-[17px]">
              A local spatial studio for Codex and Claude Code. Map real product flows grounded in code,
              review visual behavior diffs before a line changes, and steer builds with spatial pins.
            </p>
            <div className="mt-6 max-w-[480px]">
              <CommandStrip />
            </div>
            <div className="mt-4 flex flex-wrap items-center gap-2">
              <Button type="button" onClick={primaryAction} className="h-10 rounded-full px-3.5 sm:px-5">
                {onEnterApp ? "Back to studio" : "Try live sandbox"}
                <ArrowRight aria-hidden="true" className="size-4" />
              </Button>
              <Button type="button" variant="outline" onClick={() => openSandbox("diff")} className="h-10 rounded-full bg-card px-3.5 sm:px-5">
                <GitCompare aria-hidden="true" className="size-4" /> See visual diff
              </Button>
            </div>
            <ul aria-label="Compatibility" className="mt-4 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] font-medium text-muted-foreground">
              {["Works locally with Codex", "Claude Code", "Any git repo", "Zero cloud telemetry"].map((item) => (
                <li key={item} className="flex items-center gap-2 before:size-1 before:rounded-full before:bg-clay before:content-[''] first:before:hidden">{item}</li>
              ))}
            </ul>
          </section>

          <InteractiveHeroCanvas />
        </div>

        <div className="border-y bg-card/55">
          <div className={shell}>
            <StudioShowcase />
          </div>
        </div>

        <div className={shell}>
          <StartSection>
            <details className="mt-5 text-xs text-muted-foreground">
              <summary className={`${focus} w-fit cursor-pointer font-medium hover:text-foreground`}>
                Agent setup permissions and copy mode
              </summary>
              <div className="mt-3 max-w-xl space-y-3 rounded-xl border bg-card p-4">
                <p>AgentCanvas indexes repo evidence locally. The full setup prompt includes copy mode for agents without a direct connection.</p>
                <dl className="grid gap-2 sm:grid-cols-3">
                  {LANDING_BOOTSTRAP_PERMISSION_PROMPTS.map(({ label, reason }) => (
                    <div key={label}>
                      <dt className="font-semibold text-foreground">{label}</dt>
                      <dd className="mt-1">{reason}</dd>
                    </div>
                  ))}
                </dl>
                <a
                  className={`${focus} inline-block font-medium text-foreground underline underline-offset-4`}
                  download="agentcanvas-setup.txt"
                  href={`data:text/plain;charset=utf-8,${encodeURIComponent(LANDING_BOOTSTRAP_PROMPT)}`}
                >
                  Download the full setup prompt
                </a>
              </div>
            </details>
          </StartSection>
        </div>

        <section className="relative isolate overflow-hidden border-y bg-secondary/60">
          <div aria-hidden="true" className="pointer-events-none absolute inset-0 -z-10 bg-[radial-gradient(circle,hsl(var(--muted-foreground)/0.20)_0.75px,transparent_0.9px)] [background-size:18px_18px]" />
          <div className={`${shell} py-16 text-center sm:py-24`}>
            <h2 className="mx-auto max-w-3xl text-balance text-3xl font-bold leading-[1.05] tracking-[-0.035em] sm:text-5xl">
              Stop reading 2,000-line diffs to guess what your app does.
            </h2>
            <div className="mt-7 flex flex-wrap justify-center gap-2.5">
              <Button type="button" onClick={() => openSandbox("flows")} className="h-11 rounded-full px-5">
                Launch interactive sandbox <ArrowRight aria-hidden="true" className="size-4" />
              </Button>
              <Button type="button" variant="outline" onClick={() => openSandbox("diff")} className="h-11 rounded-full bg-card px-5">
                Explore a visual diff
              </Button>
            </div>
          </div>
        </section>
      </main>

      <footer className={`${shell} flex flex-wrap items-center justify-between gap-x-4 gap-y-2 py-6`}>
        <a href="#top" className={`${focus} flex items-center gap-1.5 text-sm font-bold tracking-tight`}>
          <BrandMark className="size-6" iconClassName="size-5" />
          AgentCanvas
        </a>
        <p className="text-xs text-muted-foreground">Local-first. Open source. Zero telemetry.</p>
      </footer>
    </div>
  )
}
