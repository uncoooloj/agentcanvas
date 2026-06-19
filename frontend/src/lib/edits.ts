import type { FlowAction } from "@/components/FlowCanvas"
import type { FlowNode } from "./types"

export interface EditRequest {
  action: FlowAction
  node: FlowNode
  journeyTitle: string
  changeId?: string
  initialText1?: string
  initialText2?: string
}

export interface StagedEdit {
  action: FlowAction
  node: FlowNode
  journeyTitle: string
  summary: string
  changeId?: string
  text1?: string
  text2?: string
}

export function nodeLabel(node: FlowNode): string {
  return node.kind === "branch" ? `If ${node.condition}` : node.text
}

export type FieldKind = "single" | "double" | "reason"

interface EditMeta {
  title: string
  context: (label: string) => string
  cta: string
  danger?: boolean
  field: FieldKind
  firstPlaceholder: string
  secondPlaceholder?: string
}

export const EDIT_META: Record<FlowAction, EditMeta> = {
  change: {
    title: "Change this step",
    context: (s) => `How should “${s}” work instead?`,
    cta: "Save",
    field: "single",
    firstPlaceholder: "e.g. Also add loyalty points before charging",
  },
  add_after: {
    title: "Add a step",
    context: (s) => `What should happen right after “${s}”?`,
    cta: "Add",
    field: "single",
    firstPlaceholder: "e.g. Text them the delivery date",
  },
  add_rule: {
    title: "Add a rule",
    context: (s) => `Add an “if…” around “${s}”.`,
    cta: "Add",
    field: "double",
    firstPlaceholder: "If… e.g. the order is over £100",
    secondPlaceholder: "then… e.g. send it to a manager to approve",
  },
  change_condition: {
    title: "Change the condition",
    context: (s) => `When should this path be taken? (now: “${s}”)`,
    cta: "Save",
    field: "single",
    firstPlaceholder: "e.g. the order is over £100",
  },
  add_then: {
    title: "Add a step",
    context: (s) => `What should happen when “${s}” is true?`,
    cta: "Add",
    field: "single",
    firstPlaceholder: "e.g. Send a thank-you note",
  },
  add_else: {
    title: "Add a step",
    context: (s) => `What should happen otherwise — when “${s}” is not true?`,
    cta: "Add",
    field: "single",
    firstPlaceholder: "e.g. Ask them to try again",
  },
  remove: {
    title: "Remove this",
    context: (s) => `Remove “${s}”? We'll ask your assistant to take it out safely.`,
    cta: "Remove",
    danger: true,
    field: "reason",
    firstPlaceholder: "Why remove it? (optional)",
  },
}

export function buildSummary(
  action: FlowAction,
  label: string,
  text1: string,
  text2: string
): string {
  switch (action) {
    case "change":
      return `Change the step “${label}” so that instead it: ${text1}`
    case "add_after":
      return `Right after “${label}”, add a new step: ${text1}`
    case "add_rule":
      return `Around “${label}”, add a rule: if ${text1}, then ${text2}`
    case "change_condition":
      return `Change the rule “${label}” so the condition becomes: ${text1}`
    case "add_then":
      return `In the rule “${label}”, on the path where it is true, add a step: ${text1}`
    case "add_else":
      return `In the rule “${label}”, on the otherwise path, add a step: ${text1}`
    case "remove":
      return `Remove “${label}”.${text1 ? ` Reason: ${text1}` : ""}`
  }
}
