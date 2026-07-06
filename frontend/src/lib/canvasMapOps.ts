import {
  CanvasV2EdgeKind,
  CanvasV2NodeKind,
  CanvasV2Status,
  FlowAction,
  type CanvasApplyOperation,
  type CanvasV2Edge,
  type CanvasV2EdgeOperationPayload,
  type CanvasV2Flow,
  type CanvasV2Node,
  type CanvasV2NodeOperationPayload,
} from "./types"

export function buildMapEditOperations(
  flow: CanvasV2Flow,
  node: CanvasV2Node,
  action: FlowAction,
  text1?: string,
  text2?: string,
  context: CanvasMapPendingContext = {}
): CanvasApplyOperation[] {
  switch (action) {
    case FlowAction.Change:
    case FlowAction.ChangeCondition:
      return [
        {
          op: "upsert_node",
          flow: flow.id,
          node: canvasNodePayload({
            ...node,
            title: requiredText(text1, "This map change needs new text."),
          }),
        },
      ]
    case FlowAction.AddAfter:
      return buildAddAfterOperations(flow, node, requiredText(text1, "This map change needs the new step text."), context)
    case FlowAction.AddRule:
      return buildAddRuleOperations(
        flow,
        node,
        requiredText(text1, "This map change needs the rule condition."),
        requiredText(text2, "This map change needs the step for the true path."),
        context
      )
    case FlowAction.AddThen:
      return buildAddDecisionPathOperations(flow, node, requiredText(text1, "This map change needs the new step text."), true, context)
    case FlowAction.AddElse:
      return buildAddDecisionPathOperations(flow, node, requiredText(text1, "This map change needs the new step text."), false, context)
    case FlowAction.Remove:
      return buildRemoveNodeOperations(flow, node)
  }
}

export enum CanvasMapPendingMetadataKey {
  ClientChangeId = "client_change_id",
  PendingRequestId = "pending_request_id",
}

export interface CanvasMapPendingContext {
  clientChangeId?: string
  pendingRequestId?: string
}

export function mapEditCreatesProposedNodes(action: FlowAction): boolean {
  return (
    action === FlowAction.AddAfter ||
    action === FlowAction.AddRule ||
    action === FlowAction.AddThen ||
    action === FlowAction.AddElse
  )
}

export function proposedNodeIdsFromOperations(operations: CanvasApplyOperation[]): string[] {
  return operations
    .filter((operation): operation is Extract<CanvasApplyOperation, { op: "upsert_node" }> => operation.op === "upsert_node")
    .filter((operation) => operation.node.status === CanvasV2Status.Proposed)
    .map((operation) => operation.node.id)
}

export function withPendingRequestMetadata(
  operations: CanvasApplyOperation[],
  context: CanvasMapPendingContext
): CanvasApplyOperation[] {
  return operations.map((operation) => {
    if (operation.op !== "upsert_node" || operation.node.status !== CanvasV2Status.Proposed) return operation
    return {
      ...operation,
      node: {
        ...operation.node,
        metadata: {
          ...(operation.node.metadata ?? {}),
          ...pendingMetadata(context),
        },
      },
    }
  })
}

export function buildAddAfterOperations(
  flow: CanvasV2Flow,
  node: CanvasV2Node,
  title: string,
  context: CanvasMapPendingContext = {}
): CanvasApplyOperation[] {
  const outgoing = flow.edges.filter((edge) => edge.source === node.id)
  const newNodeId = uniqueCanvasId(
    `node:${node.id}:after:${slugId(title) || "step"}`,
    flow.nodes.map((item) => item.id)
  )
  const operations: CanvasApplyOperation[] = outgoing.map((edge) => ({
    op: "delete_edge",
    flow: flow.id,
    target: edge.id,
  }))
  operations.push({
    op: "upsert_node",
    flow: flow.id,
    node: proposedDoNode(newNodeId, title, context),
  })
  const usedEdgeIds = flow.edges.map((edge) => edge.id)
  const insertedEdgeId = uniqueCanvasId(`edge:${node.id}:${newNodeId}`, usedEdgeIds)
  operations.push({
    op: "upsert_edge",
    flow: flow.id,
    edge: {
      id: insertedEdgeId,
      kind: CanvasV2EdgeKind.Normal,
      source: node.id,
      target: newNodeId,
    },
  })
  for (const edge of outgoing) {
    const edgeId = uniqueCanvasId(`edge:${newNodeId}:${edge.target}:${edge.kind}`, usedEdgeIds)
    operations.push({
      op: "upsert_edge",
      flow: flow.id,
      edge: canvasEdgePayload({
        ...edgeToOperationPayload(edge),
        id: edgeId,
        source: newNodeId,
      }),
    })
  }
  return operations
}

export function buildAddRuleOperations(
  flow: CanvasV2Flow,
  node: CanvasV2Node,
  condition: string,
  thenTitle: string,
  context: CanvasMapPendingContext = {}
): CanvasApplyOperation[] {
  const incoming = flow.edges.filter((edge) => edge.target === node.id)
  const usedNodeIds = flow.nodes.map((item) => item.id)
  const decisionId = uniqueCanvasId(`node:${node.id}:rule:${slugId(condition) || "condition"}`, usedNodeIds)
  const thenNodeId = uniqueCanvasId(`node:${decisionId}:then:${slugId(thenTitle) || "step"}`, usedNodeIds)
  const operations: CanvasApplyOperation[] = incoming.map((edge) => ({
    op: "delete_edge",
    flow: flow.id,
    target: edge.id,
  }))
  if (flow.entryNode === node.id) {
    operations.push({
      op: "upsert_flow",
      flow: {
        id: flow.id,
        entry_node: decisionId,
      },
    })
  }
  operations.push(
    {
      op: "upsert_node",
      flow: flow.id,
      node: {
        id: decisionId,
        kind: CanvasV2NodeKind.Decision,
        title: condition,
        evidence_refs: [],
        status: CanvasV2Status.Proposed,
        metadata: pendingMetadata(context),
      },
    },
    {
      op: "upsert_node",
      flow: flow.id,
      node: proposedDoNode(thenNodeId, thenTitle, context),
    }
  )
  const usedEdgeIds = flow.edges.map((edge) => edge.id)
  for (const edge of incoming) {
    const edgeId = uniqueCanvasId(`edge:${edge.source}:${decisionId}:${edge.kind}`, usedEdgeIds)
    operations.push({
      op: "upsert_edge",
      flow: flow.id,
      edge: canvasEdgePayload({
        ...edgeToOperationPayload(edge),
        id: edgeId,
        target: decisionId,
      }),
    })
  }
  operations.push(
    {
      op: "upsert_edge",
      flow: flow.id,
      edge: {
        id: uniqueCanvasId(`edge:${decisionId}:${thenNodeId}:yes`, usedEdgeIds),
        kind: CanvasV2EdgeKind.Branch,
        source: decisionId,
        target: thenNodeId,
        label: "Yes",
      },
    },
    {
      op: "upsert_edge",
      flow: flow.id,
      edge: {
        id: uniqueCanvasId(`edge:${decisionId}:${node.id}:otherwise`, usedEdgeIds),
        kind: CanvasV2EdgeKind.Branch,
        source: decisionId,
        target: node.id,
        label: "Otherwise",
        is_default: true,
      },
    },
    {
      op: "upsert_edge",
      flow: flow.id,
      edge: {
        id: uniqueCanvasId(`edge:${thenNodeId}:${node.id}`, usedEdgeIds),
        kind: CanvasV2EdgeKind.Normal,
        source: thenNodeId,
        target: node.id,
      },
    }
  )
  return operations
}

export function buildAddDecisionPathOperations(
  flow: CanvasV2Flow,
  node: CanvasV2Node,
  title: string,
  positivePath: boolean,
  context: CanvasMapPendingContext = {}
): CanvasApplyOperation[] {
  if (node.kind !== CanvasV2NodeKind.Decision && node.kind !== CanvasV2NodeKind.Loop) {
    throw new Error("Steps can only be added to rule paths on a decision or loop.")
  }
  const pathEdge = findPathEdge(flow, node.id, positivePath)
  if (!pathEdge) {
    throw new Error("That rule path could not be found.")
  }
  const newNodeId = uniqueCanvasId(
    `node:${node.id}:${positivePath ? "then" : "else"}:${slugId(title) || "step"}`,
    flow.nodes.map((item) => item.id)
  )
  const usedEdgeIds = flow.edges.map((edge) => edge.id)
  return [
    {
      op: "delete_edge",
      flow: flow.id,
      target: pathEdge.id,
    },
    {
      op: "upsert_node",
      flow: flow.id,
      node: proposedDoNode(newNodeId, title, context),
    },
    {
      op: "upsert_edge",
      flow: flow.id,
      edge: canvasEdgePayload({
        ...edgeToOperationPayload(pathEdge),
        id: uniqueCanvasId(`edge:${node.id}:${newNodeId}:${pathEdge.kind}`, usedEdgeIds),
        target: newNodeId,
      }),
    },
    {
      op: "upsert_edge",
      flow: flow.id,
      edge: {
        id: uniqueCanvasId(`edge:${newNodeId}:${pathEdge.target}`, usedEdgeIds),
        kind: CanvasV2EdgeKind.Normal,
        source: newNodeId,
        target: pathEdge.target,
      },
    },
  ]
}

export function buildRemoveNodeOperations(flow: CanvasV2Flow, node: CanvasV2Node): CanvasApplyOperation[] {
  if (flow.entryNode === node.id) {
    throw new Error("The first step in a flow cannot be removed directly from the map yet.")
  }
  const incoming = flow.edges.filter((edge) => edge.target === node.id)
  const outgoing = flow.edges.filter((edge) => edge.source === node.id)
  const removedEdgeIds = new Set([...incoming, ...outgoing].map((edge) => edge.id))
  const existingEdgeKeys = new Set(
    flow.edges
      .filter((edge) => !removedEdgeIds.has(edge.id))
      .map((edge) => edgeKey(edge.source, edge.target, edge.kind, edge.label))
  )
  const operations: CanvasApplyOperation[] = [...incoming, ...outgoing].map((edge) => ({
    op: "delete_edge",
    flow: flow.id,
    target: edge.id,
  }))
  const usedEdgeIds = flow.edges.map((edge) => edge.id)
  for (const sourceEdge of incoming) {
    for (const targetEdge of outgoing) {
      if (sourceEdge.source === targetEdge.target) continue
      const template = reconnectEdgeTemplate(sourceEdge, targetEdge)
      const key = edgeKey(sourceEdge.source, targetEdge.target, template.kind, template.label)
      if (existingEdgeKeys.has(key)) continue
      existingEdgeKeys.add(key)
      const edgeId = uniqueCanvasId(`edge:${sourceEdge.source}:${targetEdge.target}:${template.kind}`, usedEdgeIds)
      operations.push({
        op: "upsert_edge",
        flow: flow.id,
        edge: canvasEdgePayload({
          ...edgeToOperationPayload(template),
          id: edgeId,
          source: sourceEdge.source,
          target: targetEdge.target,
        }),
      })
    }
  }
  operations.push({
    op: "delete_node",
    flow: flow.id,
    target: node.id,
  })
  return operations
}

function findPathEdge(flow: CanvasV2Flow, nodeId: string, positivePath: boolean): CanvasV2Edge | undefined {
  const outgoing = flow.edges.filter((edge) => edge.source === nodeId)
  if (positivePath) {
    return (
      outgoing.find((edge) => !edge.isDefault && /^(yes|true|then|continue)$/i.test(edge.label ?? "")) ??
      outgoing.find((edge) => !edge.isDefault) ??
      outgoing[0]
    )
  }
  return (
    outgoing.find((edge) => edge.isDefault) ??
    outgoing.find((edge) => /^(no|false|else|otherwise)$/i.test(edge.label ?? "")) ??
    outgoing[outgoing.length - 1]
  )
}

function proposedDoNode(id: string, title: string, context: CanvasMapPendingContext = {}): CanvasV2NodeOperationPayload {
  return {
    id,
    kind: CanvasV2NodeKind.Do,
    title,
    evidence_refs: [],
    status: CanvasV2Status.Proposed,
    metadata: pendingMetadata(context),
  }
}

function pendingMetadata(context: CanvasMapPendingContext): Record<string, string> | undefined {
  const metadata: Record<string, string> = {}
  if (context.clientChangeId) metadata[CanvasMapPendingMetadataKey.ClientChangeId] = context.clientChangeId
  if (context.pendingRequestId) metadata[CanvasMapPendingMetadataKey.PendingRequestId] = context.pendingRequestId
  return Object.keys(metadata).length ? metadata : undefined
}

export function canvasNodePayload(node: CanvasV2Node): CanvasV2NodeOperationPayload {
  return stripUndefined({
    id: node.id,
    kind: node.kind,
    title: node.title,
    summary: node.summary,
    evidence: node.evidence,
    evidence_refs: node.evidenceRefs,
    confidence: node.confidence,
    status: node.status,
    flow_ref: node.flowRef,
    metadata: node.metadata,
  })
}

function edgeToOperationPayload(edge: CanvasV2Edge): CanvasV2EdgeOperationPayload {
  return {
    id: edge.id,
    kind: edge.kind,
    source: edge.source,
    target: edge.target,
    label: edge.label,
    is_default: edge.isDefault,
    evidence: edge.evidence,
    evidence_refs: edge.evidenceRefs,
    confidence: edge.confidence,
    metadata: edge.metadata,
  }
}

function reconnectEdgeTemplate(sourceEdge: CanvasV2Edge, targetEdge: CanvasV2Edge): CanvasV2Edge {
  const sourceCarriesPathMeaning =
    sourceEdge.kind !== CanvasV2EdgeKind.Normal || Boolean(sourceEdge.label) || sourceEdge.isDefault !== undefined
  return sourceCarriesPathMeaning ? sourceEdge : targetEdge
}

function canvasEdgePayload(edge: CanvasV2EdgeOperationPayload): CanvasV2EdgeOperationPayload {
  return stripUndefined(edge)
}

function stripUndefined<T extends object>(value: T): T {
  return Object.fromEntries(Object.entries(value).filter(([, item]) => item !== undefined)) as T
}

function edgeKey(source: string, target: string, kind: CanvasV2EdgeKind, label?: string): string {
  return `${source}\u0000${target}\u0000${kind}\u0000${label ?? ""}`
}

function uniqueCanvasId(base: string, existing: string[]): string {
  const used = new Set(existing)
  let candidate = base
  let suffix = 2
  while (used.has(candidate)) {
    candidate = `${base}-${suffix}`
    suffix += 1
  }
  existing.push(candidate)
  return candidate
}

function slugId(value: string): string {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 48)
}

function requiredText(value: string | undefined, message: string): string {
  const text = value?.trim()
  if (!text) throw new Error(message)
  return text
}
