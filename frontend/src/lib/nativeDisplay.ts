import {
  CanvasV2NodeKind,
  CanvasV2Schema,
  FlowNodeKind,
  StepRole,
  type CanvasV2Flow,
  type CanvasV2Node,
  type FlowNode,
} from "./types"

export function findNodeByNativeId(nodes: FlowNode[], nativeId: string): FlowNode | null {
  for (const node of nodes) {
    if (node.native?.nodeId === nativeId) return node
    if (node.kind === FlowNodeKind.Branch) {
      const found = findNodeByNativeId(node.then, nativeId) ?? findNodeByNativeId(node.otherwise, nativeId)
      if (found) return found
    }
  }
  return null
}

export function findNativeDisplayNodeByDisplayId(
  flow: CanvasV2Flow | null | undefined,
  displayId: string
): FlowNode | null {
  if (!flow) return null
  const nativeNode = flow.nodes.find((node) => nativeDisplayNodeId(flow.id, node.id) === displayId)
  return nativeNode ? nativeNodeToDisplayNode(flow.id, nativeNode) : null
}

export function nativeNodeToDisplayNode(flowId: string, node: CanvasV2Node): FlowNode {
  const native = {
    schema: CanvasV2Schema.Canvas,
    flowId,
    nodeId: node.id,
    nodeKind: node.kind,
    ...(node.flowRef ? { flowRef: node.flowRef } : {}),
  }
  if (node.kind === CanvasV2NodeKind.Decision) {
    return {
      kind: FlowNodeKind.Branch,
      id: nativeDisplayNodeId(flowId, node.id),
      condition: node.title,
      then: [],
      otherwise: [],
      native,
    }
  }
  return {
    kind: FlowNodeKind.Step,
    id: nativeDisplayNodeId(flowId, node.id),
    role: node.kind === CanvasV2NodeKind.When ? StepRole.When : StepRole.Do,
    text: node.title,
    detail: node.summary,
    native,
  }
}

export function nativeDisplayNodeId(flowId: string, nodeId: string): string {
  return `native:${flowId}:${nodeId}`
}
