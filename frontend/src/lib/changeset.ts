import { create } from "zustand"
import { fetchPending, postChange, type ChangeRequest } from "./api"
import {
  ChangeKind,
  FlowAction,
  FlowNodeKind,
  PendingStatus,
  StepRole,
  type AppModel,
  type BranchNode,
  type CanvasV2NodeKind,
  type FlowNode,
  type PendingItem,
  type StepNode,
} from "./types"
export { ChangeKind } from "./types"

// ---- Change-set model ----

export interface ChangeEntry {
  id: string
  action: FlowAction
  kind: ChangeKind
  summary: string // plain sentence shown in the tray
  journeyId: string
  journeyTitle: string
  targetNodeId: string
  targetNativeNodeId?: string
  targetNativeKind?: CanvasV2NodeKind
  targetFlowId?: string
  text1?: string // primary input (new step text / new condition / reason)
  text2?: string // secondary input (the "then" action for add_rule)
  createdAt: number
  updatedAt: number
}

export enum HandoffPhase {
  Composing = "composing",
  Sending = "sending",
  Working = "working",
  Done = "done",
  NeedsInput = "needs_input",
  Blocked = "blocked",
  Stopped = "stopped",
}
export enum HandoffItemStatus {
  Queued = "queued",
  Sent = "sent",
  InProgress = "in_progress",
  Implemented = "implemented",
  NeedsInput = "needs_input",
  Blocked = "blocked",
  Verified = "verified",
  Done = "done",
  Cancelled = "cancelled",
  Rejected = "rejected",
}

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
  phase: HandoffPhase
  items: HandoffItem[]
  summary?: string
  question?: string
  prompt?: string
  error?: string
}

export function kindForAction(action: FlowAction): ChangeKind {
  if (action === FlowAction.Remove) return ChangeKind.Removing
  if (action === FlowAction.Change || action === FlowAction.ChangeCondition) return ChangeKind.Edited
  return ChangeKind.New
}

const VERB: Record<ChangeKind, string> = {
  [ChangeKind.New]: "Adding",
  [ChangeKind.Edited]: "Updating",
  [ChangeKind.Removing]: "Removing",
}

function summarize(changes: ChangeEntry[]): string {
  const n = changes.filter((c) => c.kind === ChangeKind.New).length
  const e = changes.filter((c) => c.kind === ChangeKind.Edited).length
  const r = changes.filter((c) => c.kind === ChangeKind.Removing).length
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
  dismissHandoff: () => void
  badgeForNode: (nodeId: string) => ChangeKind | null
}

let counter = 0
const newId = () => `c${Date.now().toString(36)}${counter++}`

const idle: HandoffState = { phase: HandoffPhase.Composing, items: [] }

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
    const working = get().handoff.phase !== HandoffPhase.Composing
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
    if (handoff.phase !== HandoffPhase.Composing || !changes.length) return

    const items: HandoffItem[] = changes.map((c) => ({
      changeId: c.id,
      label: `${VERB[c.kind]}: ${c.summary}`,
      status: HandoffItemStatus.Queued,
    }))
    set({ handoff: { phase: HandoffPhase.Sending, items, prompt: buildHandoffPrompt(changes, get().assistantName) } })

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
              phase: HandoffPhase.Blocked,
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
    if (
      handoff.phase === HandoffPhase.Composing ||
      handoff.phase === HandoffPhase.Done ||
      handoff.phase === HandoffPhase.Stopped
    ) {
      return
    }
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
        const needsInput = items.find((item) => item.status === HandoffItemStatus.NeedsInput)
        const blocked = items.find((item) => STOPPED_STATUSES.has(item.status))
        return {
          handoff: {
            ...s.handoff,
            phase,
            items,
            summary: phase === HandoffPhase.Done ? summarize(get().changes) : s.handoff.summary,
            question: needsInput?.note || blocked?.note || s.handoff.question,
            error:
              phase === HandoffPhase.Working || phase === HandoffPhase.Done
                ? undefined
                : blocked?.note || s.handoff.error,
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
    if (get().handoff.phase !== HandoffPhase.Done) return []
    const applied = get().changes
    const promoted = get().queuedNext
    set({ changes: promoted, queuedNext: [], handoff: idle })
    return applied
  },

  dismissHandoff: () => {
    set({ handoff: idle })
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
    targetNativeNodeId: change.targetNativeNodeId,
    targetNativeKind: change.targetNativeKind,
    targetFlowId: change.targetFlowId,
    text1: change.text1,
    text2: change.text2,
  }
}

function handoffItemFromPending(item: HandoffItem, pending: PendingItem): HandoffItem {
  const status = normalizePendingStatus(pending.status)
  return {
    ...item,
    status: status === PendingStatus.Pending ? HandoffItemStatus.Sent : status,
    pendingId: pending.id,
    title: pending.title,
    note: pending.note || pending.error,
    jsonPath: pending.jsonPath,
    markdownPath: pending.markdownPath,
  }
}

function blockedHandoffItem(item: HandoffItem, note: string): HandoffItem {
  return { ...item, status: HandoffItemStatus.Blocked, note }
}

function normalizePendingStatus(status: PendingStatus): HandoffItemStatus | PendingStatus.Pending {
  if (status === PendingStatus.Pending) return PendingStatus.Pending
  return PENDING_TO_HANDOFF_STATUS[status]
}

const PENDING_TO_HANDOFF_STATUS: Record<Exclude<PendingStatus, PendingStatus.Pending>, HandoffItemStatus> = {
  [PendingStatus.Sent]: HandoffItemStatus.Sent,
  [PendingStatus.InProgress]: HandoffItemStatus.InProgress,
  [PendingStatus.Implemented]: HandoffItemStatus.Implemented,
  [PendingStatus.NeedsInput]: HandoffItemStatus.NeedsInput,
  [PendingStatus.Blocked]: HandoffItemStatus.Blocked,
  [PendingStatus.Verified]: HandoffItemStatus.Verified,
  [PendingStatus.Done]: HandoffItemStatus.Done,
  [PendingStatus.Cancelled]: HandoffItemStatus.Cancelled,
  [PendingStatus.Rejected]: HandoffItemStatus.Rejected,
}

const FINISHED_STATUSES = new Set<HandoffItemStatus>([HandoffItemStatus.Done, HandoffItemStatus.Verified])
const WORKING_STATUSES = new Set<HandoffItemStatus>([
  HandoffItemStatus.Sent,
  HandoffItemStatus.InProgress,
  HandoffItemStatus.Implemented,
])
const STOPPED_STATUSES = new Set<HandoffItemStatus>([
  HandoffItemStatus.Blocked,
  HandoffItemStatus.Cancelled,
  HandoffItemStatus.Rejected,
])

function phaseForItems(items: HandoffItem[]): HandoffPhase {
  if (!items.length) return HandoffPhase.Composing
  if (items.some((item) => item.status === HandoffItemStatus.Queued)) return HandoffPhase.Sending
  if (items.every((item) => FINISHED_STATUSES.has(item.status))) return HandoffPhase.Done
  if (items.some((item) => STOPPED_STATUSES.has(item.status))) return HandoffPhase.Stopped
  if (items.some((item) => item.status === HandoffItemStatus.NeedsInput)) return HandoffPhase.NeedsInput
  if (items.some((item) => WORKING_STATUSES.has(item.status))) return HandoffPhase.Working
  return HandoffPhase.Working
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
        ...(change.targetNativeNodeId ? [`   - Native node: ${change.targetNativeNodeId}`] : []),
        ...(change.targetNativeKind ? [`   - Native kind: ${change.targetNativeKind}`] : []),
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
  return status ? STATUS_LABELS[status] : "not sent"
}

const STATUS_LABELS: Record<HandoffItemStatus, string> = {
  [HandoffItemStatus.Queued]: "creating pending file",
  [HandoffItemStatus.Sent]: "sent",
  [HandoffItemStatus.InProgress]: "in progress",
  [HandoffItemStatus.Implemented]: "implemented",
  [HandoffItemStatus.Verified]: "verified",
  [HandoffItemStatus.Done]: "done",
  [HandoffItemStatus.NeedsInput]: "needs input",
  [HandoffItemStatus.Blocked]: "blocked",
  [HandoffItemStatus.Cancelled]: "cancelled",
  [HandoffItemStatus.Rejected]: "rejected",
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
  return { kind: FlowNodeKind.Step, id: newId(), role: StepRole.Do, text }
}
function mkBranch(condition: string, thenText?: string): BranchNode {
  return {
    kind: FlowNodeKind.Branch,
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
      if (c.action === FlowAction.Remove) {
        continue // drop it
      }
      if (c.action === FlowAction.Change && node.kind === FlowNodeKind.Step) {
        out.push({ ...node, text: c.text1 || node.text })
        continue
      }
      if (c.action === FlowAction.ChangeCondition && node.kind === FlowNodeKind.Branch) {
        out.push({ ...node, condition: c.text1 || node.condition })
        continue
      }
      if (c.action === FlowAction.AddAfter) {
        out.push(node)
        out.push(mkStep(c.text1 || "New step"))
        continue
      }
      if (c.action === FlowAction.AddRule) {
        out.push(node)
        out.push(mkBranch(c.text1 || "this applies", c.text2))
        continue
      }
      if (c.action === FlowAction.AddThen && node.kind === FlowNodeKind.Branch) {
        out.push({ ...node, then: [...node.then, mkStep(c.text1 || "New step")] })
        continue
      }
      if (c.action === FlowAction.AddElse && node.kind === FlowNodeKind.Branch) {
        out.push({ ...node, otherwise: [...node.otherwise, mkStep(c.text1 || "New step")] })
        continue
      }
    }
    // recurse into branches
    if (node.kind === FlowNodeKind.Branch) {
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
