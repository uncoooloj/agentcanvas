import type {
  AppModel,
  BranchNode,
  CodeGraph,
  CodeNode,
  FlowNode,
  Journey,
  StepNode,
} from "./types"

let seq = 0
const sid = () => `n${seq++}`

function step(role: "when" | "do", text: string, extra: Partial<StepNode> = {}): StepNode {
  return { kind: "step", id: sid(), role, text, ...extra }
}
function branch(
  condition: string,
  then: FlowNode[],
  otherwise: FlowNode[] = [],
  extra: Partial<BranchNode> = {}
): BranchNode {
  return { kind: "branch", id: sid(), condition, then, otherwise, ...extra }
}

// A hand-authored, fully non-technical example. Shown on first run or when we
// can't read a real app yet — so the first impression is always behavior, never
// the tool's own plumbing. Each journey is one user entry point.
export const DEMO_MODEL: AppModel = {
  appName: "Your online shop",
  isDemo: true,
  journeys: [
    {
      id: "ordering",
      title: "Placing an order",
      summary: "What happens from the moment someone checks out.",
      entry: "Someone places an order",
      nodes: [
        step("when", "Someone places an order"),
        step("do", "Check the items are still in stock", {
          tech: { refs: ["checks the inventory service"] },
        }),
        branch(
          "everything is in stock",
          [
            step("do", "Work out the total, including any discount code"),
            step("do", "Charge their card", {
              detail: "Happens right after the total is worked out.",
              tech: { refs: ["payments/charge.js"] },
            }),
            branch(
              "the card is approved",
              [
                step("do", "Send them an order confirmation email"),
                step("do", "Start preparing the order for delivery"),
              ],
              [step("do", "Ask them to try another card")]
            ),
          ],
          [
            step("do", "Tell them which item sold out"),
            step("do", "Save their cart so they can finish later"),
          ]
        ),
      ],
    },
    {
      id: "signup",
      title: "Creating an account",
      summary: "How someone new gets set up.",
      entry: "Someone creates an account",
      nodes: [
        step("when", "Someone creates an account"),
        branch(
          "that email is already used",
          [step("do", "Ask them to sign in instead")],
          [
            step("do", "Save their account securely"),
            step("do", "Send them a welcome email"),
          ]
        ),
      ],
    },
    {
      id: "signin",
      title: "Signing in",
      summary: "What happens when someone comes back.",
      entry: "Someone tries to sign in",
      nodes: [
        step("when", "Someone tries to sign in"),
        branch(
          "the password is correct",
          [step("do", "Let them in and show their dashboard")],
          [
            branch(
              "they've gotten it wrong too many times",
              [step("do", "Pause the account for a little while")],
              [step("do", "Ask them to try again")]
            ),
          ]
        ),
      ],
    },
    {
      id: "refunds",
      title: "Refunds & returns",
      summary: "What happens when someone wants their money back.",
      entry: "Someone asks for a refund",
      nodes: [
        step("when", "Someone asks for a refund"),
        branch(
          "the order is more than 30 days old",
          [step("do", "Send it to a person to review")],
          [
            step("do", "Put the money back on their card"),
            step("do", "Let them know the refund is on its way"),
          ]
        ),
      ],
    },
  ],
}

export function emptyAppModel(appName = "Your project", thin = true): AppModel {
  return {
    appName,
    journeys: [],
    isDemo: false,
    thin,
  }
}

// ---- Heuristic projection: code IR -> behavior tree ----

const JOURNEY_RULES: Array<{ id: string; title: string; summary: string; match: RegExp }> = [
  {
    id: "ordering",
    title: "Placing an order",
    summary: "Checkout, payment and order handling.",
    match: /checkout|order|cart|payment|pay|charge|stripe|invoice|purchase/i,
  },
  {
    id: "accounts",
    title: "Signing up & signing in",
    summary: "Accounts, sign-in and access.",
    match: /auth|login|signin|signup|register|account|user|session|password/i,
  },
  {
    id: "refunds",
    title: "Refunds & returns",
    summary: "Refunds, returns and cancellations.",
    match: /refund|return|cancel|dispute|chargeback/i,
  },
  {
    id: "messaging",
    title: "Messages & notifications",
    summary: "Emails, texts and alerts your app sends.",
    match: /email|mail|notif|message|sms|webhook|alert/i,
  },
  {
    id: "content",
    title: "Browsing & content",
    summary: "Pages and content people can view.",
    match: /product|catalog|search|page|feed|list|browse|home/i,
  },
]

function refsOf(node: CodeNode): string[] {
  const raw = (node.source_refs || node.sources || []) as Array<
    string | { path?: string; file?: string }
  >
  const refs = raw.map((r) => (typeof r === "string" ? r : r?.path || r?.file || "")).filter(Boolean)
  const data = (node as unknown as { path?: string; data?: { file?: string; path?: string } }).data
  const path = (node as unknown as { path?: string }).path || data?.file || data?.path
  if (path) refs.push(path)
  return Array.from(new Set(refs))
}

function humanize(input: string): string {
  return input
    .replace(/\.[a-z0-9]+$/i, "")
    .replace(/[_-]+/g, " ")
    .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
    .replace(/[/\\]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .toLowerCase()
}

function sentenceCase(s: string): string {
  const t = s.trim()
  return t ? t.charAt(0).toUpperCase() + t.slice(1) : t
}

type Role = "when" | "do" | "if"

function classify(node: CodeNode): Role | null {
  const type = `${node.type || node.kind || ""}`.toLowerCase()
  const text = `${type} ${node.label || node.name || ""} ${refsOf(node).join(" ")}`.toLowerCase()
  const refs = refsOf(node)
  if (refs.some(isFixtureRef) || /test|spec|coverage/.test(text)) return null
  if (type === "file") return refs.some(isEntrypointRef) ? "when" : null
  if (type === "export") return null
  if (type === "component" || type === "app_surface") return null
  if (/route|endpoint|page|screen|handler|controller|webhook/.test(text)) return "when"
  if (/valid|check|guard|branch|decision|condition|permission/.test(text)) return "if"
  if (/action|service|job|queue|function|mutation|command|send|create|update|delete|charge/.test(text))
    return "do"
  return null
}

function pickJourney(node: CodeNode): { id: string; title: string; summary: string } {
  const hay = `${node.group || node.component || node.module || ""} ${node.label || node.name || ""} ${refsOf(
    node
  ).join(" ")}`
  for (const rule of JOURNEY_RULES) if (rule.match.test(hay)) return rule
  if (/cli\.py|__main__\.py|command|script/i.test(hay)) {
    return {
      id: "commands",
      title: "Running project commands",
      summary: "Command-line entrypoints detected in the workspace.",
    }
  }
  if (/api|endpoint|server/i.test(hay)) {
    return {
      id: "api",
      title: "Using the local API",
      summary: "HTTP/API entrypoints detected in the workspace.",
    }
  }
  return {
    id: "workspace-entrypoints",
    title: "Workspace entrypoints",
    summary: "High-confidence entrypoints detected in the workspace.",
  }
}

export function projectToBehavior(graph: CodeGraph | null | undefined): AppModel {
  const nodes = graph?.nodes || []
  if (!nodes.length) return emptyAppModel(appNameFromGraph(graph))

  const buckets = new Map<string, Journey>()
  let kept = 0

  for (const node of nodes) {
    const role = classify(node)
    if (!role) continue
    const j = pickJourney(node)
    if (!buckets.has(j.id)) {
      buckets.set(j.id, { id: j.id, title: j.title, summary: j.summary, entry: "", nodes: [] })
    }
    const refs = refsOf(node)
    const tech = refs.length ? { nodeId: node.id, refs } : undefined
    const uncertain = typeof node.confidence === "number" && node.confidence < 0.6
    const label = node.label || node.name || node.title || refs[0] || node.id
    const h = humanize(label)

    let fnode: FlowNode
    if (role === "if") {
      fnode = { kind: "branch", id: node.id || sid(), condition: h, then: [], otherwise: [], uncertain, tech }
    } else {
      fnode = {
        kind: "step",
        id: node.id || sid(),
        role: role === "when" ? "when" : "do",
        text: role === "when" ? sentenceCase(`someone uses ${h}`) : sentenceCase(h),
        uncertain,
        tech,
      }
    }
    buckets.get(j.id)!.nodes.push(fnode)
    kept++
  }

  const journeys = Array.from(buckets.values()).filter((j) => j.nodes.length)
  if (!kept || !journeys.length) return emptyAppModel(appNameFromGraph(graph))

  for (const j of journeys) {
    j.nodes.sort((a, b) => order(a) - order(b))
    const firstWhen = j.nodes.find((n) => n.kind === "step" && n.role === "when") as StepNode | undefined
    j.entry = firstWhen?.text || j.title
  }

  return {
    appName: sentenceCase(humanize(appNameFromGraph(graph))),
    journeys,
    isDemo: false,
    thin: kept < 4,
  }
}

function isFixtureRef(ref: string): boolean {
  const normalized = ref.toLowerCase()
  return /(^|\/)(__tests__|demo_project|demo_projects|examples|fixtures?|tests?)(\/|$)/.test(normalized)
}

function isEntrypointRef(ref: string): boolean {
  const normalized = ref.toLowerCase()
  return /(^|\/)(cli|__main__|main|server|app|index)\.(py|tsx?|jsx?|mjs|cjs)$/.test(normalized)
}

function appNameFromGraph(graph: CodeGraph | null | undefined): string {
  if (typeof graph?.workspace === "string") {
    return graph.workspace.split(/[/\\]/).filter(Boolean).pop() || graph.workspace
  }
  if (graph?.workspace && typeof graph.workspace === "object") {
    const workspace = graph.workspace as Record<string, unknown>
    if (typeof workspace.name === "string" && workspace.name.trim()) return workspace.name
    if (typeof workspace.root === "string" && workspace.root.trim()) {
      return workspace.root.split(/[/\\]/).filter(Boolean).pop() || workspace.root
    }
  }
  return "Your app"
}

function order(n: FlowNode): number {
  if (n.kind === "step") return n.role === "when" ? 0 : 1
  return 2
}
