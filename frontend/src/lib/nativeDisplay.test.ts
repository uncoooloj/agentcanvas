import { describe, expect, it } from "vitest"
import {
  CanvasV2EdgeKind,
  CanvasV2NodeKind,
  CanvasV2Schema,
  FlowNodeKind,
  StepRole,
  type CanvasV2Flow,
  type FlowNode,
} from "./types"
import {
  findNativeDisplayNodeByDisplayId,
  findNodeByNativeId,
  nativeDisplayNodeId,
  nativeNodeToDisplayNode,
} from "./nativeDisplay"

describe("native display node adapter", () => {
  const nativeFlow: CanvasV2Flow = {
    id: "flow:checkout",
    title: "Checkout",
    summary: "How checkout works.",
    entryNode: "n:start",
    evidence: [],
    evidenceRefs: [],
    nodes: [
      {
        id: "n:start",
        kind: CanvasV2NodeKind.When,
        title: "Someone starts checkout",
        evidence: [{ ref: "src/routes/checkout.ts:10" }],
        evidenceRefs: ["src/routes/checkout.ts:10"],
      },
      {
        id: "n:pay",
        kind: CanvasV2NodeKind.Do,
        title: "Take payment",
        summary: "Charge the saved card.",
        evidence: [{ ref: "src/payments.ts:42" }],
        evidenceRefs: ["src/payments.ts:42"],
      },
      {
        id: "n:risk",
        kind: CanvasV2NodeKind.Decision,
        title: "Payment looks risky",
        evidence: [{ ref: "src/risk.ts:8" }],
        evidenceRefs: ["src/risk.ts:8"],
      },
    ],
    edges: [
      {
        id: "e:start:pay",
        kind: CanvasV2EdgeKind.Normal,
        source: "n:start",
        target: "n:pay",
        evidence: [],
        evidenceRefs: [],
      },
    ],
  }

  it("creates editable synthetic display nodes for native-only v2 steps", () => {
    const node = nativeNodeToDisplayNode("flow:checkout", nativeFlow.nodes[1])

    expect(node.kind).toBe(FlowNodeKind.Step)
    if (node.kind !== FlowNodeKind.Step) throw new Error("expected a step node")
    expect(node.id).toBe("native:flow:checkout:n:pay")
    expect(node.role).toBe(StepRole.Do)
    expect(node.text).toBe("Take payment")
    expect(node.detail).toBe("Charge the saved card.")
    expect(node.native).toEqual({
      schema: CanvasV2Schema.Canvas,
      flowId: "flow:checkout",
      nodeId: "n:pay",
      nodeKind: CanvasV2NodeKind.Do,
    })
  })

  it("creates branch display nodes for native decision nodes", () => {
    const node = nativeNodeToDisplayNode("flow:checkout", nativeFlow.nodes[2])

    expect(node.kind).toBe(FlowNodeKind.Branch)
    if (node.kind !== FlowNodeKind.Branch) throw new Error("expected a branch node")
    expect(node.condition).toBe("Payment looks risky")
    expect(node.then).toEqual([])
    expect(node.otherwise).toEqual([])
    expect(node.native?.nodeKind).toBe(CanvasV2NodeKind.Decision)
  })

  it("resolves existing flattened nodes before synthetic fallbacks", () => {
    const flattened: FlowNode[] = [
      {
        kind: FlowNodeKind.Step,
        id: "display-pay",
        role: StepRole.Do,
        text: "Existing display payment",
        native: {
          schema: CanvasV2Schema.Canvas,
          flowId: "flow:checkout",
          nodeId: "n:pay",
          nodeKind: CanvasV2NodeKind.Do,
        },
      },
    ]

    expect(findNodeByNativeId(flattened, "n:pay")?.id).toBe("display-pay")
    expect(findNativeDisplayNodeByDisplayId(nativeFlow, nativeDisplayNodeId("flow:checkout", "n:pay"))?.id).toBe(
      "native:flow:checkout:n:pay"
    )
  })
})
