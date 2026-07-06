import { describe, expect, it } from "vitest"
import { buildMapEditOperations } from "./canvasMapOps"
import {
  CanvasV2EdgeKind,
  CanvasV2NodeKind,
  CanvasV2Status,
  FlowAction,
  type CanvasApplyOperation,
  type CanvasV2Flow,
  type CanvasV2Node,
} from "./types"

function node(id: string, kind: CanvasV2NodeKind, title = id): CanvasV2Node {
  return {
    id,
    kind,
    title,
    evidence: [],
    evidenceRefs: [],
    status: CanvasV2Status.Verified,
  }
}

function flow(): CanvasV2Flow {
  return {
    id: "flow:checkout",
    title: "Checkout",
    summary: "Checkout",
    entryNode: "n:start",
    nodes: [
      node("n:start", CanvasV2NodeKind.When, "Someone checks out"),
      node("n:pay", CanvasV2NodeKind.Do, "Take payment"),
      node("n:decision", CanvasV2NodeKind.Decision, "Can pay?"),
      node("n:success", CanvasV2NodeKind.Do, "Confirm order"),
      node("n:failure", CanvasV2NodeKind.Do, "Show error"),
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
      {
        id: "e:decision:success",
        kind: CanvasV2EdgeKind.Branch,
        source: "n:decision",
        target: "n:success",
        label: "Yes",
        evidence: [],
        evidenceRefs: [],
      },
      {
        id: "e:decision:failure",
        kind: CanvasV2EdgeKind.Branch,
        source: "n:decision",
        target: "n:failure",
        label: "Otherwise",
        isDefault: true,
        evidence: [],
        evidenceRefs: [],
      },
    ],
    evidence: [],
    evidenceRefs: [],
  }
}

function op<T extends CanvasApplyOperation["op"]>(operations: CanvasApplyOperation[], name: T): Extract<CanvasApplyOperation, { op: T }>[] {
  return operations.filter((operation): operation is Extract<CanvasApplyOperation, { op: T }> => operation.op === name)
}

describe("canvas map operation builders", () => {
  it("wraps a step in a proposed decision for add-rule map edits", () => {
    const subject = flow()
    const operations = buildMapEditOperations(
      subject,
      subject.nodes[1],
      FlowAction.AddRule,
      "the order is expensive",
      "ask a manager to review it"
    )

    expect(op(operations, "delete_edge")).toEqual([{ op: "delete_edge", flow: "flow:checkout", target: "e:start:pay" }])
    expect(op(operations, "upsert_node")).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          node: expect.objectContaining({
            kind: CanvasV2NodeKind.Decision,
            title: "the order is expensive",
            status: CanvasV2Status.Proposed,
          }),
        }),
        expect.objectContaining({
          node: expect.objectContaining({
            kind: CanvasV2NodeKind.Do,
            title: "ask a manager to review it",
            status: CanvasV2Status.Proposed,
          }),
        }),
      ])
    )
    expect(op(operations, "upsert_edge")).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ edge: expect.objectContaining({ source: "n:start", target: expect.stringContaining(":rule:") }) }),
        expect.objectContaining({ edge: expect.objectContaining({ kind: CanvasV2EdgeKind.Branch, label: "Yes" }) }),
        expect.objectContaining({ edge: expect.objectContaining({ kind: CanvasV2EdgeKind.Branch, label: "Otherwise", is_default: true }) }),
      ])
    )
  })

  it("moves the flow entry when a rule wraps the first node", () => {
    const subject = flow()
    subject.entryNode = "n:pay"
    subject.edges = []
    const operations = buildMapEditOperations(
      subject,
      subject.nodes[1],
      FlowAction.AddRule,
      "payment needs review",
      "ask a manager"
    )

    const decisionId = op(operations, "upsert_node").find((operation) => operation.node.kind === CanvasV2NodeKind.Decision)
      ?.node.id
    expect(op(operations, "upsert_flow")).toEqual([
      {
        op: "upsert_flow",
        flow: {
          id: "flow:checkout",
          entry_node: decisionId,
        },
      },
    ])
  })

  it("inserts proposed steps into decision yes and otherwise paths", () => {
    const subject = flow()
    const decision = subject.nodes[2]
    const yesOps = buildMapEditOperations(subject, decision, FlowAction.AddThen, "send a receipt")
    const elseOps = buildMapEditOperations(subject, decision, FlowAction.AddElse, "offer a retry")

    expect(op(yesOps, "delete_edge")).toEqual([{ op: "delete_edge", flow: "flow:checkout", target: "e:decision:success" }])
    expect(op(yesOps, "upsert_node")[0].node).toEqual(
      expect.objectContaining({ title: "send a receipt", status: CanvasV2Status.Proposed })
    )
    expect(op(yesOps, "upsert_edge")).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ edge: expect.objectContaining({ source: "n:decision", label: "Yes" }) }),
        expect.objectContaining({ edge: expect.objectContaining({ target: "n:success" }) }),
      ])
    )

    expect(op(elseOps, "delete_edge")).toEqual([{ op: "delete_edge", flow: "flow:checkout", target: "e:decision:failure" }])
    expect(op(elseOps, "upsert_node")[0].node).toEqual(
      expect.objectContaining({ title: "offer a retry", status: CanvasV2Status.Proposed })
    )
    expect(op(elseOps, "upsert_edge")[0].edge).toEqual(
      expect.objectContaining({ source: "n:decision", label: "Otherwise", is_default: true })
    )
  })
})
