import {
  ArrowDown,
  ArrowRight,
  Check,
  CircleCheck,
  CircleDot,
  Code2,
  GitBranch,
  GitCommitHorizontal,
  Globe2,
  MessageSquare,
  Radio,
  Server,
  Smartphone,
  Terminal,
  Workflow,
  type LucideIcon,
} from "lucide-react"
import type { ReactNode } from "react"
import { cn } from "@/lib/utils"

const BEFORE_CODE = [
  "const total = cart.subtotal + cart.tax",
  "const charge = await stripe.charge(total)",
  "if (charge.status === \"paid\") {",
  "  await sendLegacyEmail(order)",
  "  return redirect(\"/thanks\")",
  "}",
  "",
  "// retry when the webhook arrives late",
  "await orders.update(order.id, { charged: true })",
  "return { ok: true, orderId: order.id }",
]

type DiffTone = "added" | "changed" | "removed"

const DIFF_ARTIFACTS: Array<{ tone: DiffTone; label: string; detail: string }> = [
  { tone: "added", label: "SMS receipt", detail: "after the charge settles" },
  { tone: "changed", label: "Idempotent charge", detail: "same order, one payment" },
  { tone: "removed", label: "Legacy email fallback", detail: "no longer reachable" },
]

function DiffArtifact({ tone, label, detail }: { tone: DiffTone; label: string; detail: string }) {
  const toneStyles = {
    added: "bg-act-bg/80 text-act-fg",
    changed: "bg-rule-bg/80 text-rule-fg",
    removed: "bg-destructive/10 text-[#a43628] dark:text-[#ff9384]",
  }
  const marks = { added: "+", changed: "~", removed: "-" }

  return (
    <div className={cn("flex items-start gap-2.5 rounded-lg px-3 py-2.5", toneStyles[tone])}>
      <span className="mt-px w-3 shrink-0 font-mono text-sm font-semibold leading-5">{marks[tone]}</span>
      <span className="min-w-0">
        <span className="block text-[13px] font-semibold leading-5">{label}</span>
        <span className="block text-[11px] leading-4">{detail}</span>
      </span>
    </div>
  )
}

function ShowcaseCard({
  children,
  className,
}: {
  children: ReactNode
  className?: string
}) {
  return (
    <article
      className={cn(
        "relative overflow-hidden rounded-[1.35rem] border border-foreground/10 bg-card text-card-foreground shadow-[0_1px_0_rgba(31,28,24,0.04)]",
        className
      )}
    >
      {children}
    </article>
  )
}

function CardKicker({ children }: { children: ReactNode }) {
  return (
    <p className="font-mono text-[10px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">{children}</p>
  )
}

function Node({
  icon: Icon,
  label,
  detail,
  className,
}: {
  icon: LucideIcon
  label: string
  detail?: string
  className?: string
}) {
  return (
    <div className={cn("flex items-center gap-2.5 rounded-xl border bg-background px-3 py-2.5", className)}>
      <span className="flex size-7 shrink-0 items-center justify-center rounded-lg bg-secondary text-muted-foreground">
        <Icon className="size-3.5" strokeWidth={1.8} />
      </span>
      <span className="min-w-0">
        <span className="block truncate text-xs font-semibold">{label}</span>
        {detail && <span className="mt-0.5 block truncate text-[10px] text-muted-foreground">{detail}</span>}
      </span>
    </div>
  )
}

export function StudioShowcase() {
  return (
    <section id="visual-diff" className="scroll-mt-20 py-16 sm:py-24">
      <h2
        id="visual-diff-title"
        className="text-balance text-4xl font-semibold leading-[0.98] tracking-[-0.045em] sm:text-6xl"
      >
        Why teams ditch chat walls.
      </h2>

      <div className="mt-10 grid gap-4 md:grid-cols-12 md:grid-rows-[minmax(0,1fr)_minmax(0,1fr)]">
          <ShowcaseCard className="md:col-span-7 md:row-span-2 md:min-h-[540px]">
            <div className="flex h-full flex-col p-5 sm:p-7">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <CardKicker>agentcanvas diff main..HEAD</CardKicker>
                  <h3 className="mt-2 text-xl font-semibold tracking-tight sm:text-2xl">Visual Behavioral Diffs</h3>
                  <p className="mt-2 text-sm leading-relaxed text-muted-foreground">Code-level edits become reviewable behavior.</p>
                </div>
                <div className="flex shrink-0 flex-col items-end gap-1 font-mono text-[10px] text-muted-foreground">
                  <span className="rounded-full bg-act-bg px-2 py-1 font-semibold text-act-fg">+482</span>
                  <span className="rounded-full bg-destructive/10 px-2 py-1 font-semibold text-[#a43628] dark:text-[#ff9384]">-119</span>
                  <span className="mt-0.5">14 files</span>
                </div>
              </div>

              <div className="mt-8 grid flex-1 gap-3 sm:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] sm:items-center">
                <div className="min-w-0 rounded-xl bg-primary p-3.5 text-primary-foreground shadow-inner sm:p-4">
                  <div className="mb-3 flex items-center justify-between border-b border-primary-foreground/10 pb-2.5">
                    <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-primary-foreground/85">
                      before
                    </span>
                    <span className="font-mono text-[10px] text-primary-foreground/85">checkout.ts</span>
                  </div>
                  <div role="region" aria-label="Before code in checkout.ts" tabIndex={0} className="space-y-1 overflow-x-auto rounded-sm font-mono text-[10px] leading-4 focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary-foreground sm:text-[11px]">
                    {BEFORE_CODE.map((line, index) => (
                      <div key={`${line}-${index}`} className={cn("flex gap-2", !line && "h-2")}>
                        <span aria-hidden="true" className="w-4 shrink-0 text-right text-primary-foreground/80">{index + 38}</span>
                        <code className={cn("whitespace-pre text-primary-foreground/85", index === 2 && "text-primary-foreground")}>
                          {line || " "}
                        </code>
                      </div>
                    ))}
                  </div>
                  <div className="mt-4 flex items-center gap-1.5 text-[10px] text-primary-foreground/85">
                    <Code2 className="size-3" />
                    <span>dense implementation detail</span>
                  </div>
                </div>

                <div className="flex justify-center text-clay sm:px-1">
                  <ArrowDown className="size-4 sm:hidden" />
                  <ArrowRight className="hidden size-4 sm:block" />
                </div>

                <div className="rounded-xl border border-border bg-background p-3.5 sm:p-4">
                  <div className="mb-3 flex items-center justify-between border-b border-border pb-2.5">
                    <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">after</span>
                    <span className="inline-flex items-center gap-1 font-mono text-[10px] text-act-fg">
                      <CircleCheck className="size-3" /> readable
                    </span>
                  </div>
                  <div className="space-y-2.5">
                    {DIFF_ARTIFACTS.map((artifact) => (
                      <DiffArtifact key={artifact.label} {...artifact} />
                    ))}
                  </div>
                </div>
              </div>

              <div className="mt-7 flex items-center gap-2 border-t border-border pt-4 text-[11px] text-muted-foreground">
                <span className="size-1.5 rounded-full bg-act-accent" />
                <span>behavior map updated from the same change set</span>
              </div>
            </div>
          </ShowcaseCard>

          <ShowcaseCard className="border-primary/80 bg-primary text-primary-foreground md:col-span-5">
            <div className="flex h-full flex-col p-5 sm:p-6">
              <div>
                <h3 className="mt-2 text-xl font-semibold tracking-tight">Direct Local Agent Loop</h3>
                <p className="mt-2 text-sm leading-relaxed text-primary-foreground/85">Run an agent beside the canvas over local SSE.</p>
              </div>

              <div className="mt-6 rounded-xl border border-primary-foreground/15 bg-primary-foreground/[0.06] p-3.5 font-mono text-[11px]">
                <div className="flex items-center gap-2 text-primary-foreground/85">
                  <Terminal className="size-3.5" />
                  <span>$ codex exec</span>
                  <span>/</span>
                  <span>claude</span>
                  <span className="ml-auto rounded-full bg-primary-foreground/10 px-2 py-0.5 text-[9px] text-primary-foreground">
                    local SSE
                  </span>
                </div>
                <div className="my-3 h-px bg-primary-foreground/10" />
                <div className="flex items-start gap-2.5">
                  <Radio className="mt-0.5 size-3.5 shrink-0 text-act-accent" />
                  <div className="min-w-0">
                    <p className="text-primary-foreground/85">trace checkout → canvas</p>
                    <div className="mt-2 flex items-center gap-2 rounded-lg border border-primary-foreground/15 bg-primary-foreground/[0.06] px-2.5 py-2 text-[10px] text-primary-foreground/85">
                      <MessageSquare className="size-3 shrink-0 text-when-accent" />
                      <span className="leading-4">Which billing source should this use?</span>
                    </div>
                  </div>
                </div>
              </div>

              <div className="mt-auto flex flex-wrap gap-x-4 gap-y-2 pt-5 text-[10px] font-medium text-primary-foreground/85">
                <span className="inline-flex items-center gap-1.5">
                  <Check className="size-3 text-act-accent" /> no copy-paste
                </span>
                <span className="inline-flex items-center gap-1.5">
                  <Check className="size-3 text-act-accent" /> no MCP polling
                </span>
              </div>
            </div>
          </ShowcaseCard>

          <ShowcaseCard className="md:col-span-5">
            <div className="flex h-full flex-col p-5 sm:p-6">
              <div>
                <h3 className="mt-2 text-xl font-semibold tracking-tight">Grounded in real code and Git</h3>
                <p className="mt-2 text-sm leading-relaxed text-muted-foreground">Example evidence ties this behavior to a file, commit, and test result.</p>
              </div>

              <div className="mt-6 overflow-hidden rounded-xl border border-border bg-background font-mono text-[10px]">
                <div className="flex items-center gap-2 border-b border-border px-3 py-2.5 text-muted-foreground">
                  <GitBranch className="size-3.5 text-rule-fg" />
                  <span className="truncate text-foreground">src/orders/checkout.ts:42</span>
                  <span className="ml-auto shrink-0 text-[9px] text-muted-foreground">main</span>
                </div>
                <div className="flex items-center gap-2 border-b border-border px-3 py-2.5 text-act-fg">
                  <CircleCheck className="size-3.5" />
                  <span>Verified · 14 tests passed</span>
                </div>
                <div className="flex items-center gap-2 px-3 py-2.5 text-muted-foreground">
                  <GitCommitHorizontal className="size-3.5" />
                  <span>7f3d2a1</span>
                  <span className="ml-auto inline-flex items-center gap-1.5 rounded-full bg-when-bg px-2 py-0.5 text-[9px] text-when-fg">
                    <CircleDot className="size-2.5" /> git-hash staleness
                  </span>
                </div>
              </div>

              <div className="mt-auto flex items-center gap-2 pt-5 text-[10px] text-muted-foreground">
                <span className="size-1.5 rounded-full bg-rule-accent" />
                Flags evidence when the commit changes
              </div>
            </div>
          </ShowcaseCard>

          <ShowcaseCard className="md:col-span-12">
            <div className="grid gap-8 p-5 sm:p-7 lg:grid-cols-[minmax(220px,0.72fr)_minmax(0,1.8fr)] lg:items-center">
              <div>
                <h3 className="mt-2 text-xl font-semibold tracking-tight sm:text-2xl">Topology that scales with the repo</h3>
                <p className="mt-2 text-sm leading-relaxed text-muted-foreground">Two app surfaces feed shared services in a 17-service monorepo.</p>
                <div className="mt-5 inline-flex items-center gap-2 rounded-full bg-secondary px-3 py-1.5 font-mono text-[10px] font-semibold text-secondary-foreground">
                  <Server className="size-3" /> 17 services / one source of truth
                </div>
              </div>

              <div className="grid gap-3 sm:grid-cols-[minmax(0,0.78fr)_auto_minmax(0,1.22fr)] sm:items-center">
                <div className="grid gap-2">
                  <Node icon={Smartphone} label="Mobile App" detail="ios / android" />
                  <Node icon={Globe2} label="Web App" detail="customer portal" />
                </div>

                <div className="flex justify-center text-clay">
                  <ArrowDown className="size-4 sm:hidden" />
                  <div className="hidden flex-col items-center gap-1 sm:flex">
                    <ArrowRight className="size-4" />
                    <span className="font-mono text-[9px] uppercase tracking-[0.16em] text-muted-foreground">feeds</span>
                    <ArrowRight className="size-4" />
                  </div>
                </div>

                <div className="grid gap-2">
                  <Node icon={Workflow} label="Checkout" detail="shared behavior contract" className="border-primary/15" />
                  <Node icon={GitBranch} label="Auth" detail="identity service" />
                  <Node icon={Server} label="Billing" detail="payments service" />
                  <div className="flex items-center gap-2 px-1 text-[10px] font-medium text-muted-foreground">
                    <span className="size-1.5 rounded-full bg-rule-accent" />
                    + 14 more services
                  </div>
                </div>
              </div>
            </div>
          </ShowcaseCard>
      </div>
    </section>
  )
}
