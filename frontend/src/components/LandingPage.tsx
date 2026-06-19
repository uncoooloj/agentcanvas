import { useMemo, useState } from "react"
import {
  ArrowRight,
  Bot,
  Braces,
  Check,
  Clipboard,
  Code2,
  FolderOpen,
  GitBranch,
  Globe2,
  Play,
  Radio,
  Route,
  Sparkles,
  Terminal,
  Zap,
  type LucideIcon,
} from "lucide-react"
import heroImage from "@/assets/hero.png"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { cn } from "@/lib/utils"

const AGENTS = [
  { id: "generic", label: "Copy mode" },
  { id: "codex", label: "Codex" },
  { id: "claude-code", label: "Claude Code" },
  { id: "cursor", label: "Cursor" },
  { id: "antigravity", label: "Antigravity" },
]

const NAV = ["Overview", "Install", "Skill", "MCP", "API", "Webhooks"]

export function LandingPage() {
  const [agent, setAgent] = useState("generic")
  const [githubUrl, setGithubUrl] = useState("https://github.com/your-org/your-app")
  const [folderPath, setFolderPath] = useState("/path/to/your-app")
  const selectedAgent = AGENTS.find((item) => item.id === agent) ?? AGENTS[0]
  const agentFlag = agent === "generic" ? "" : ` --agent ${agent}`
  const githubName = useMemo(() => repoNameFromUrl(githubUrl), [githubUrl])
  const githubCommand = `git clone ${githubUrl} ${githubName}\nagentcanvas start --workspace ${githubName}${agentFlag}`
  const folderCommand = `agentcanvas start --workspace ${folderPath}${agentFlag}`

  function openDemo() {
    const url = new URL(window.location.href)
    url.searchParams.set("demo", "1")
    window.location.href = url.toString()
  }

  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="sticky top-0 z-40 border-b bg-background/92 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-6xl items-center gap-4 px-5">
          <a href="#overview" className="flex items-center gap-2 font-medium">
            <span className="flex size-7 items-center justify-center rounded-md bg-primary text-primary-foreground">
              <Sparkles className="size-4" />
            </span>
            AgentCanvas
          </a>
          <nav className="ml-auto hidden items-center gap-5 text-sm text-muted-foreground md:flex">
            {NAV.map((item) => (
              <a key={item} href={`#${item.toLowerCase()}`} className="hover:text-foreground">
                {item}
              </a>
            ))}
          </nav>
          <Button type="button" size="sm" onClick={openDemo}>
            <Play className="size-4" />
            Demo
          </Button>
        </div>
      </header>

      <main>
        <section
          id="overview"
          className="relative isolate overflow-hidden border-b bg-secondary/25"
        >
          <img
            src={heroImage}
            alt=""
            aria-hidden="true"
            className="pointer-events-none absolute right-[4%] top-12 -z-10 hidden w-[340px] opacity-80 md:block"
          />
          <div className="mx-auto grid min-h-[560px] max-w-6xl content-center gap-10 px-5 py-16 lg:grid-cols-[minmax(0,0.9fr)_minmax(320px,0.55fr)]">
            <div className="max-w-2xl">
              <Badge variant="secondary" className="mb-5">
                Local-first workflow canvas
              </Badge>
              <h1 className="text-5xl font-medium leading-[1.02] sm:text-6xl">AgentCanvas</h1>
              <p className="mt-5 max-w-xl text-lg leading-8 text-muted-foreground">
                Point it at a repo. It turns scattered app logic into simple When, Do, If flows that your coding agent can understand and act on.
              </p>
              <div className="mt-7 flex flex-wrap gap-3">
                <Button type="button" onClick={openDemo}>
                  Try demo
                  <ArrowRight data-icon="inline-end" />
                </Button>
                <Button asChild variant="outline">
                  <a href="#install">
                    Install
                  </a>
                </Button>
              </div>
              <div className="mt-7 flex flex-wrap gap-2 text-xs text-muted-foreground">
                <Badge variant="outline">Claude Code</Badge>
                <Badge variant="outline">Codex</Badge>
                <Badge variant="outline">Cursor</Badge>
                <Badge variant="outline">Antigravity</Badge>
                <Badge variant="outline">Any agent with files</Badge>
              </div>
            </div>

            <div className="self-end">
              <FlowPreview />
            </div>
          </div>
        </section>

        <section id="install" className="border-b">
          <div className="mx-auto grid max-w-6xl gap-8 px-5 py-12 lg:grid-cols-[0.85fr_1.15fr]">
            <SectionIntro
              eyebrow="Start here"
              title="Pick how you want to open a project."
              body="No hidden magic. Start from a GitHub URL, a folder on your machine, or the bundled demo. If no agent is connected, AgentCanvas stays in copy mode."
            />
            <div className="grid gap-4">
                <LaunchPanel
                Icon={Globe2}
                title="GitHub URL"
                body="Use this when the project is not on your machine yet."
                value={githubUrl}
                onChange={setGithubUrl}
                command={githubCommand}
              />
              <LaunchPanel
                Icon={FolderOpen}
                title="Local folder"
                body="Use this when the repo is already cloned."
                value={folderPath}
                onChange={setFolderPath}
                command={folderCommand}
              />
              <div className="rounded-lg border bg-card p-4">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm font-medium">Agent mode</span>
                  {AGENTS.map((item) => (
                    <button
                      key={item.id}
                      type="button"
                      onClick={() => setAgent(item.id)}
                      className={cn(
                        "rounded-md border px-2.5 py-1 text-xs transition-colors",
                        agent === item.id
                          ? "border-primary bg-primary text-primary-foreground"
                          : "bg-background text-muted-foreground hover:text-foreground"
                      )}
                    >
                      {item.label}
                    </button>
                  ))}
                </div>
                <p className="mt-2 text-sm text-muted-foreground">
                  Current default: {selectedAgent.label}. Copy mode creates pending files and gives you a prompt to paste into any assistant.
                </p>
              </div>
            </div>
          </div>
        </section>

        <section className="border-b">
          <div className="mx-auto grid max-w-6xl gap-4 px-5 py-12 md:grid-cols-3">
            <HowStep Icon={Route} title="Map" body="AgentCanvas indexes the repo and shows the app as flows, not files." />
            <HowStep Icon={GitBranch} title="Edit" body="Change, add, reroute, or remove steps in plain language." />
            <HowStep Icon={Bot} title="Send" body="Your agent gets a structured request, status contract, and copy fallback." />
          </div>
        </section>

        <section id="skill" className="border-b">
          <div className="mx-auto grid max-w-6xl gap-8 px-5 py-12 lg:grid-cols-[0.85fr_1.15fr]">
            <SectionIntro
              eyebrow="Skill"
              title="The easiest path for non-technical users."
              body="A skill can launch AgentCanvas, explain what the user is seeing, poll pending work, and keep the agent loop moving without asking them to install random extras."
            />
            <CapabilityGrid
              items={[
                { Icon: Sparkles, title: "Launch canvas", body: "Open the local UI with workspace, agent, and session context." },
                { Icon: Clipboard, title: "Read requests", body: "Poll .agentcanvas/pending and pick up changes as they are created." },
                { Icon: Check, title: "Report status", body: "Move work through pending, in progress, needs input, and done." },
              ]}
            />
          </div>
        </section>

        <section id="mcp" className="border-b">
          <div className="mx-auto grid max-w-6xl gap-8 px-5 py-12 lg:grid-cols-[0.85fr_1.15fr]">
            <SectionIntro
              eyebrow="MCP"
              title="The no-copy-paste path."
              body="The MCP server should let agents list sessions, watch pending changes, acknowledge work, reply with questions, and resolve requests."
            />
            <CodePanel
              title="Planned tools"
              code={[
                "agentcanvas_list_sessions",
                "agentcanvas_get_pending",
                "agentcanvas_watch_changes",
                "agentcanvas_acknowledge",
                "agentcanvas_reply",
                "agentcanvas_resolve",
              ].join("\n")}
            />
          </div>
        </section>

        <section id="api" className="border-b">
          <div className="mx-auto grid max-w-6xl gap-8 px-5 py-12 lg:grid-cols-[0.85fr_1.15fr]">
            <SectionIntro
              eyebrow="API"
              title="A small local contract any agent can use."
              body="The app already exposes local endpoints for context, graph, pending requests, status updates, and reindexing. That keeps the product agent-agnostic."
            />
            <CapabilityGrid
              items={[
                { Icon: Globe2, title: "/api/context", body: "Workspace, mode, assistant, session id." },
                { Icon: Braces, title: "/api/changes", body: "Create structured pending requests from canvas edits." },
                { Icon: Radio, title: "/api/pending", body: "Read status and file paths the agent can act on." },
              ]}
            />
          </div>
        </section>

        <section id="webhooks">
          <div className="mx-auto grid max-w-6xl gap-8 px-5 py-12 lg:grid-cols-[0.85fr_1.15fr]">
            <SectionIntro
              eyebrow="Webhooks"
              title="For teams that want AgentCanvas events elsewhere."
              body="The webhook path should send change.created, status.updated, reply.added, and request.resolved events to Slack, GitHub, CI, or a custom dashboard."
            />
            <CodePanel
              title="Event sketch"
              code={'{\n  "event": "change.created",\n  "sessionId": "agent-session-123",\n  "pendingId": "change-src-services",\n  "status": "pending"\n}'}
            />
          </div>
        </section>
      </main>
    </div>
  )
}

function FlowPreview() {
  return (
    <div className="rounded-lg border bg-card/88 p-4 shadow-xl backdrop-blur">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <p className="text-sm font-medium">Checkout flow</p>
          <p className="text-xs text-muted-foreground">What the app does</p>
        </div>
        <Badge variant="outline">4 refs</Badge>
      </div>
      <div className="space-y-3">
        <PreviewStep Icon={Zap} tone="when" label="When" text="Someone places an order" />
        <PreviewStep Icon={Play} tone="act" label="Do" text="Check inventory" />
        <PreviewStep Icon={GitBranch} tone="rule" label="If" text="The card is approved" />
        <PreviewStep Icon={Play} tone="act" label="Do" text="Send confirmation email" />
      </div>
    </div>
  )
}

function PreviewStep({
  Icon,
  tone,
  label,
  text,
}: {
  Icon: LucideIcon
  tone: "when" | "act" | "rule"
  label: string
  text: string
}) {
  return (
    <div className="flex items-center gap-3 rounded-lg border bg-background p-3">
      <span
        className={cn(
          "flex items-center gap-1.5 rounded-md px-2 py-1 text-xs font-medium",
          tone === "when" && "bg-when-bg text-when-fg",
          tone === "act" && "bg-act-bg text-act-fg",
          tone === "rule" && "bg-rule-bg text-rule-fg"
        )}
      >
        <Icon className="size-3.5" />
        {label}
      </span>
      <span className="min-w-0 truncate text-sm">{text}</span>
    </div>
  )
}

function SectionIntro({
  eyebrow,
  title,
  body,
}: {
  eyebrow: string
  title: string
  body: string
}) {
  return (
    <div>
      <p className="mb-3 text-xs font-medium uppercase tracking-wide text-muted-foreground">{eyebrow}</p>
      <h2 className="max-w-lg text-2xl font-medium leading-tight">{title}</h2>
      <p className="mt-3 max-w-xl text-sm leading-6 text-muted-foreground">{body}</p>
    </div>
  )
}

function LaunchPanel({
  Icon,
  title,
  body,
  value,
  onChange,
  command,
}: {
  Icon: LucideIcon
  title: string
  body: string
  value: string
  onChange: (value: string) => void
  command: string
}) {
  return (
    <div className="rounded-lg border bg-card p-4">
      <div className="flex gap-3">
        <span className="flex size-9 shrink-0 items-center justify-center rounded-md bg-secondary text-muted-foreground">
          <Icon className="size-4" />
        </span>
        <div className="min-w-0 flex-1">
          <p className="font-medium">{title}</p>
          <p className="mt-1 text-sm text-muted-foreground">{body}</p>
          <Input value={value} onChange={(event) => onChange(event.target.value)} className="mt-3" />
          <CopyableCommand command={command} />
        </div>
      </div>
    </div>
  )
}

function CopyableCommand({ command }: { command: string }) {
  const [copied, setCopied] = useState(false)
  async function copy() {
    await navigator.clipboard.writeText(command)
    setCopied(true)
    window.setTimeout(() => setCopied(false), 1200)
  }
  return (
    <div className="mt-3 overflow-hidden rounded-md border bg-secondary/50">
      <div className="flex items-center justify-between gap-3 border-b px-3 py-2">
        <span className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
          <Terminal className="size-3.5" />
          Terminal
        </span>
        <Button type="button" variant="ghost" size="sm" onClick={copy}>
          {copied ? <Check className="size-3.5" /> : <Clipboard className="size-3.5" />}
          {copied ? "Copied" : "Copy"}
        </Button>
      </div>
      <pre className="overflow-x-auto whitespace-pre-wrap px-3 py-2 text-xs leading-5 text-muted-foreground">
        {command}
      </pre>
    </div>
  )
}

function HowStep({ Icon, title, body }: { Icon: LucideIcon; title: string; body: string }) {
  return (
    <div className="rounded-lg border bg-card p-4">
      <span className="mb-4 flex size-9 items-center justify-center rounded-md bg-secondary text-muted-foreground">
        <Icon className="size-4" />
      </span>
      <p className="font-medium">{title}</p>
      <p className="mt-2 text-sm leading-6 text-muted-foreground">{body}</p>
    </div>
  )
}

function CapabilityGrid({
  items,
}: {
  items: Array<{ Icon: LucideIcon; title: string; body: string }>
}) {
  return (
    <div className="grid gap-4 md:grid-cols-3">
      {items.map(({ Icon, title, body }) => (
        <div key={title} className="rounded-lg border bg-card p-4">
          <span className="mb-4 flex size-9 items-center justify-center rounded-md bg-secondary text-muted-foreground">
            <Icon className="size-4" />
          </span>
          <p className="font-medium">{title}</p>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">{body}</p>
        </div>
      ))}
    </div>
  )
}

function CodePanel({ title, code }: { title: string; code: string }) {
  return (
    <div className="overflow-hidden rounded-lg border bg-card">
      <div className="flex items-center gap-2 border-b px-4 py-3 text-sm font-medium">
        <Code2 className="size-4 text-muted-foreground" />
        {title}
      </div>
      <pre className="overflow-x-auto whitespace-pre-wrap p-4 text-sm leading-6 text-muted-foreground">
        {code}
      </pre>
    </div>
  )
}

function repoNameFromUrl(url: string) {
  const clean = url.trim().replace(/\/+$/, "").replace(/\.git$/, "")
  const name = clean.split("/").filter(Boolean).pop()
  return name && !name.includes(":") ? name : "agentcanvas-project"
}
