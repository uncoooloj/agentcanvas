import { create } from "zustand"
import { fetchPending, postChange, type ChangeRequest } from "./api"
import type { FlowAction } from "@/components/FlowCanvas"
import type { AppModel, BranchNode, FlowNode, PendingItem, PendingStatus, StepNode } from "./types"

// ---- Change-set model ----

export type ChangeKind = "new" | "edited" | "removing"

export interface ChangeEntry {
  id: string
  action: FlowAction
  kind: ChangeKind
  summary: string // plain sentence shown in the tray
  journeyId: string
  journeyTitle: string
  targetNodeId: string
  text1?: string // primary input (new step text / new condition / reason)
  text2?: string // secondary input (the "then" action for add_rule)
  createdAt: number
  updatedAt: number
}

export type Phase = "composing" | "sending" | "working" | "done" | "needs_input" | "blocked"
export type HandoffItemStatus = "queued" | Exclude<PendingStatus, "pending">

export interface HandoffItem {
  changeId: string
  label: string
  status: HandoffItemStatus
  pendingId?: string
  note?: string
  title?: string
  jsonPath?: string | null
  markdownPath?: string | null
}

export interface HandoffState {
  phase: Phase
  items: HandoffItem[]
  summary?: string
  question?: string
  prompt?: string
  error?: string
}

export function kindForAction(action: FlowAction): ChangeKind {
  if (action === "remove") return "removing"
  if (action === "change" || action === "change_condition") return "edited"
  return "new"
}

const VERB: Record<ChangeKind, string> = {
  new: "Adding",
  edited: "Updating",
  removing: "Removing",
}

function summarize(changes: ChangeEntry[]): string {
  const n = changes.filter((c) => c.kind === "new").length
  const e = changes.filter((c) => c.kind === "edited").length
  const r = changes.filter((c) => c.kind === "removing").length
  const parts: string[] = []
  if (n) parts.push(`added ${n} step${n === 1 ? "" : "s"}`)
  if (e) parts.push(`updated ${e}`)
  if (r) parts.push(`removed ${r}`)
  return parts.length ? `${capitalize(parts.join(", "))}.` : "No changes."
}

function capitalize(s: string) {
  return s ? s.charAt(0).toUpperCase() + s.slice(1) : s
}

// ---- Store ----

interface ChangeStore {
  changes: ChangeEntry[]
  queuedNext: ChangeEntry[] // edits made while the assistant was working
  handoff: HandoffState
  assistantName: string

  setAssistantName: (name: string) => void
  addChange: (input: Omit<ChangeEntry, "id" | "createdAt" | "updatedAt" | "kind">) => void
  updateChange: (id: string, input: Omit<ChangeEntry, "id" | "createdAt" | "updatedAt" | "kind">) => void
  undoChange: (id: string) => void
  discardAll: () => void
  send: () => void
  refreshHandoff: () => Promise<void>
  acknowledgeDone: () => ChangeEntry[] // returns the applied changes so the caller can update the model
  badgeForNode: (nodeId: string) => ChangeKind | null
}

let counter = 0
const newId = () => `c${Date.now().toString(36)}${counter++}`

const idle: HandoffState = { phase: "composing", items: [] }

export const useChanges = create<ChangeStore>((set, get) => ({
  changes: [],
  queuedNext: [],
  handoff: idle,
  assistantName: "your assistant",

  setAssistantName: (name) => set({ assistantName: name }),

  addChange: (input) => {
    const now = Date.now()
    const entry: ChangeEntry = {
      ...input,
      id: newId(),
      kind: kindForAction(input.action),
      createdAt: now,
      updatedAt: now,
    }
    const working = get().handoff.phase !== "composing"
    if (working) {
      set((s) => ({ queuedNext: [...s.queuedNext, entry] }))
    } else {
      set((s) => ({ changes: [...s.changes, entry] }))
    }
  },

  updateChange: (id, input) =>
    set((s) => ({
      changes: s.changes.map((c) =>
        c.id === id ? { ...c, ...input, kind: kindForAction(input.action), updatedAt: Date.now() } : c
      ),
      queuedNext: s.queuedNext.map((c) =>
        c.id === id ? { ...c, ...input, kind: kindForAction(input.action), updatedAt: Date.now() } : c
      ),
    })),

  undoChange: (id) =>
    set((s) => ({
      changes: s.changes.filter((c) => c.id !== id),
      queuedNext: s.queuedNext.filter((c) => c.id !== id),
    })),

  discardAll: () => set({ changes: [], handoff: idle }),

  send: () => {
    const { changes, handoff } = get()
    if (handoff.phase !== "composing" || !changes.length) return

    const items: HandoffItem[] = changes.map((c) => ({
      changeId: c.id,
      label: `${VERB[c.kind]}: ${c.summary}`,
      status: "queued",
    }))
    set({ handoff: { phase: "sending", items, prompt: buildHandoffPrompt(changes, get().assistantName) } })

    Promise.allSettled(changes.map((change) => postChange(changeRequestFor(change))))
      .then((results) => {
        const hasCreatedRequest = results.some((result) => result.status === "fulfilled")
        const failures = results.filter((result) => result.status === "rejected")
        set((s) => {
          const nextItems = s.handoff.items.map((item, index) => {
            const result = results[index]
            return result?.status === "fulfilled"
              ? handoffItemFromPending(item, result.value)
              : blockedHandoffItem(item, rejectionMessage(result))
          })
          return {
            handoff: {
              ...s.handoff,
              phase: phaseForItems(nextItems),
              items: nextItems,
              error: failures.length ? `${failures.length} pending request${failures.length === 1 ? "" : "s"} could not be created.` : undefined,
              question: failures.length
                ? "Some pending files were not created. Copy the fallback prompt below for those requests, or retry after checking the local AgentCanvas server."
                : undefined,
              prompt: buildHandoffPrompt(s.changes, s.assistantName, nextItems),
            },
          }
        })
        if (hasCreatedRequest) void get().refreshHandoff()
      })
      .catch((error: unknown) => {
        const message = error instanceof Error ? error.message : "Could not create pending requests."
        set((s) => {
          const nextItems = s.handoff.items.map((item) => blockedHandoffItem(item, message))
          return {
            handoff: {
              ...s.handoff,
              phase: "blocked",
              error: message,
              items: nextItems,
              question: "AgentCanvas could not write the pending files. Copy the fallback prompt below and paste it into your assistant instead.",
              prompt: buildHandoffPrompt(s.changes, s.assistantName, nextItems),
            },
          }
        })
      })
  },

  refreshHandoff: async () => {
    const handoff = get().handoff
    if (handoff.phase === "composing" || handoff.phase === "done") return
    try {
      const pending = await fetchPending()
      const byId = new Map(pending.map((item) => [item.id, item]))
      const byChangeId = new Map(pending.filter((item) => item.changeId).map((item) => [item.changeId!, item]))
      set((s) => {
        const items = s.handoff.items.map((item) => {
          const pendingItem = (item.pendingId ? byId.get(item.pendingId) : undefined) || byChangeId.get(item.changeId)
          return pendingItem ? handoffItemFromPending(item, pendingItem) : item
        })
        const phase = phaseForItems(items)
        const needsInput = items.find((item) => item.status === "needs_input")
        const blocked = items.find((item) => item.status === "blocked")
        return {
          handoff: {
            ...s.handoff,
            phase,
            items,
            summary: phase === "done" ? summarize(get().changes) : s.handoff.summary,
            question: needsInput?.note || blocked?.note || s.handoff.question,
            error: phase === "working" || phase === "done" ? undefined : s.handoff.error,
            prompt: buildHandoffPrompt(s.changes, s.assistantName, items),
          },
        }
      })
    } catch (error) {
      const message = error instanceof Error ? error.message : "Could not refresh pending request status."
      set((s) => ({
        handoff: {
          ...s.handoff,
          error: `Status refresh failed: ${message}`,
          prompt: buildHandoffPrompt(s.changes, s.assistantName, s.handoff.items),
        },
      }))
    }
  },

  acknowledgeDone: () => {
    const applied = get().changes
    const promoted = get().queuedNext
    set({ changes: promoted, queuedNext: [], handoff: idle })
    return applied
  },

  badgeForNode: (nodeId) => {
    const match = get().changes.find((c) => c.targetNodeId === nodeId)
    return match ? match.kind : null
  },
}))

function changeRequestFor(change: ChangeEntry): ChangeRequest {
  return {
    changeId: change.id,
    clientChangeId: change.id,
    kind: change.kind,
    action: change.action,
    title: change.summary,
    summary: change.summary,
    journey: change.journeyTitle,
    journeyId: change.journeyId,
    journeyTitle: change.journeyTitle,
    targetStep: change.targetNodeId,
    targetNodeId: change.targetNodeId,
    text1: change.text1,
    text2: change.text2,
  }
}

function handoffItemFromPending(item: HandoffItem, pending: PendingItem): HandoffItem {
  const status = normalizePendingStatus(pending.status)
  return {
    ...item,
    status: status === "pending" ? "sent" : status,
    pendingId: pending.id,
    title: pending.title,
    note: pending.note || pending.error,
    jsonPath: pending.jsonPath,
    markdownPath: pending.markdownPath,
  }
}

function blockedHandoffItem(item: HandoffItem, note: string): HandoffItem {
  return { ...item, status: "blocked", note }
}

function normalizePendingStatus(status: PendingStatus): HandoffItemStatus | "pending" {
  return status
}

function phaseForItems(items: HandoffItem[]): Phase {
  if (!items.length) return "composing"
  if (items.some((item) => item.status === "queued")) return "sending"
  if (items.every((item) => item.status === "done")) return "done"
  if (items.some((item) => item.status === "sent" || item.status === "in_progress")) return "working"
  if (items.some((item) => item.status === "blocked")) return "blocked"
  if (items.some((item) => item.status === "needs_input")) return "needs_input"
  return "working"
}

function rejectionMessage(result: PromiseSettledResult<PendingItem> | undefined): string {
  if (!result || result.status === "fulfilled") return "Could not create pending request."
  return result.reason instanceof Error ? result.reason.message : "Could not create pending request."
}

export function buildHandoffPrompt(changes: ChangeEntry[], assistantName = "your coding agent", items: HandoffItem[] = []): string {
  const itemsByChangeId = new Map(items.map((item) => [item.changeId, item]))
  const payloads = changes.map(changeRequestFor)
  const lines = [
    `Use AgentCanvas to implement these ${changes.length === 1 ? "change" : "changes"}.`,
    "",
    "Workspace instructions:",
    "1. Run `agentcanvas pending --workspace .` and find the newest pending requests.",
    "2. Read each pending Markdown file first, then the matching JSON file for structure.",
    "3. Mark a request `in_progress` when you start it:",
    "   `agentcanvas status --workspace . <pending-id> --status in_progress`",
    "4. Make the smallest code change that satisfies the request.",
    "5. Run the relevant test or smoke check.",
    "6. Re-index with `agentcanvas index --workspace .`.",
    "7. Mark the request done, or needs_input with a clear note if blocked:",
    "   `agentcanvas status --workspace . <pending-id> --status done --note \"Implemented and verified.\"`",
    "",
    `Target assistant: ${assistantName}`,
    "",
    "Pending requests:",
    ...changes.flatMap((change, index) => {
      const item = itemsByChangeId.get(change.id)
      return [
        `${index + 1}. ${change.summary}`,
        `   - Client change ID: ${change.id}`,
        `   - Status: ${statusLabel(item?.status)}`,
        `   - Pending ID: ${item?.pendingId || "not created yet"}`,
        `   - Markdown: ${item?.markdownPath || "not available"}`,
        `   - JSON: ${item?.jsonPath || "not available"}`,
        `   - Journey: ${change.journeyTitle} (${change.journeyId})`,
        `   - Target node: ${change.targetNodeId}`,
        `   - Action: ${change.action}`,
        ...(change.text1 ? [`   - Primary text: ${change.text1}`] : []),
        ...(change.text2 ? [`   - Secondary text: ${change.text2}`] : []),
        ...(item?.note ? [`   - Note: ${item.note}`] : []),
      ]
    }),
    "",
    "If the pending files above do not exist, use this structured fallback payload:",
    "```json",
    JSON.stringify(payloads, null, 2),
    "```",
  ]
  return lines.join("\n")
}

function statusLabel(status?: HandoffItemStatus): string {
  if (status === "queued") return "creating pending file"
  if (status === "sent") return "sent"
  if (status === "in_progress") return "in progress"
  if (status === "done") return "done"
  if (status === "needs_input") return "needs input"
  if (status === "blocked") return "blocked"
  return "not sent"
}

// ---- Optimistic apply: reflect staged changes on the model when the assistant "finishes" ----

export function applyChanges(model: AppModel, changes: ChangeEntry[]): AppModel {
  let journeys = model.journeys
  for (const c of changes) {
    journeys = journeys.map((j) =>
      j.id === c.journeyId ? { ...j, nodes: applyToNodes(j.nodes, c) } : j
    )
  }
  return { ...model, journeys }
}

function mkStep(text: string): StepNode {
  return { kind: "step", id: newId(), role: "do", text }
}
function mkBranch(condition: string, thenText?: string): BranchNode {
  return {
    kind: "branch",
    id: newId(),
    condition,
    then: thenText ? [mkStep(thenText)] : [],
    otherwise: [],
  }
}

function applyToNodes(nodes: FlowNode[], c: ChangeEntry): FlowNode[] {
  const out: FlowNode[] = []
  for (const node of nodes) {
    if (node.id === c.targetNodeId) {
      if (c.action === "remove") {
        continue // drop it
      }
      if (c.action === "change" && node.kind === "step") {
        out.push({ ...node, text: c.text1 || node.text })
        continue
      }
      if (c.action === "change_condition" && node.kind === "branch") {
        out.push({ ...node, condition: c.text1 || node.condition })
        continue
      }
      if (c.action === "add_after") {
        out.push(node)
        out.push(mkStep(c.text1 || "New step"))
        continue
      }
      if (c.action === "add_rule") {
        out.push(node)
        out.push(mkBranch(c.text1 || "this applies", c.text2))
        continue
      }
      if (c.action === "add_then" && node.kind === "branch") {
        out.push({ ...node, then: [...node.then, mkStep(c.text1 || "New step")] })
        continue
      }
      if (c.action === "add_else" && node.kind === "branch") {
        out.push({ ...node, otherwise: [...node.otherwise, mkStep(c.text1 || "New step")] })
        continue
      }
    }
    // recurse into branches
    if (node.kind === "branch") {
      out.push({
        ...node,
        then: applyToNodes(node.then, c),
        otherwise: applyToNodes(node.otherwise, c),
      })
    } else {
      out.push(node)
    }
  }
  return out
}
