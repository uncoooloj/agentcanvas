import { FlowAction, FlowNodeKind, type FlowNode } from "./types"

export enum EditDelivery {
  CanvasMap = "canvas_map",
  ImplementationRequest = "implementation_request",
}

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
  delivery?: EditDelivery
  text1?: string
  text2?: string
}

export function nodeLabel(node: FlowNode): string {
  return node.kind === FlowNodeKind.Branch ? `If ${node.condition}` : node.text
}

export enum FieldKind {
  Single = "single",
  Double = "double",
  Reason = "reason",
}

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
  [FlowAction.Change]: {
    title: "Change this step",
    context: (s) => `How should “${s}” work instead?`,
    cta: "Save",
    field: FieldKind.Single,
    firstPlaceholder: "e.g. Also add loyalty points before charging",
  },
  [FlowAction.AddAfter]: {
    title: "Add a step",
    context: (s) => `What should happen right after “${s}”?`,
    cta: "Add",
    field: FieldKind.Single,
    firstPlaceholder: "e.g. Text them the delivery date",
  },
  [FlowAction.AddRule]: {
    title: "Add a rule",
    context: (s) => `Add an “if…” around “${s}”.`,
    cta: "Add",
    field: FieldKind.Double,
    firstPlaceholder: "If… e.g. the order is over £100",
    secondPlaceholder: "then… e.g. send it to a manager to approve",
  },
  [FlowAction.ChangeCondition]: {
    title: "Change the condition",
    context: (s) => `When should this path be taken? (now: “${s}”)`,
    cta: "Save",
    field: FieldKind.Single,
    firstPlaceholder: "e.g. the order is over £100",
  },
  [FlowAction.AddThen]: {
    title: "Add a step",
    context: (s) => `What should happen when “${s}” is true?`,
    cta: "Add",
    field: FieldKind.Single,
    firstPlaceholder: "e.g. Send a thank-you note",
  },
  [FlowAction.AddElse]: {
    title: "Add a step",
    context: (s) => `What should happen otherwise — when “${s}” is not true?`,
    cta: "Add",
    field: FieldKind.Single,
    firstPlaceholder: "e.g. Ask them to try again",
  },
  [FlowAction.Remove]: {
    title: "Remove this",
    context: (s) => `Remove “${s}”? We'll ask your assistant to take it out safely.`,
    cta: "Remove",
    danger: true,
    field: FieldKind.Reason,
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
    case FlowAction.Change:
      return `Change the step “${label}” so that instead it: ${text1}`
    case FlowAction.AddAfter:
      return `Right after “${label}”, add a new step: ${text1}`
    case FlowAction.AddRule:
      return `Around “${label}”, add a rule: if ${text1}, then ${text2}`
    case FlowAction.ChangeCondition:
      return `Change the rule “${label}” so the condition becomes: ${text1}`
    case FlowAction.AddThen:
      return `In the rule “${label}”, on the path where it is true, add a step: ${text1}`
    case FlowAction.AddElse:
      return `In the rule “${label}”, on the otherwise path, add a step: ${text1}`
    case FlowAction.Remove:
      return `Remove “${label}”.${text1 ? ` Reason: ${text1}` : ""}`
  }
}
