import { describe, expect, it } from "vitest"
import { changeRequestFor, refsForChange, type ChangeEntry } from "./changeset"
import { CanvasV2NodeKind, ChangeKind, FlowAction, PendingRefKind } from "./types"

function change(overrides: Partial<ChangeEntry> = {}): ChangeEntry {
  const now = Date.now()
  return {
    id: "change-1",
    action: FlowAction.Change,
    kind: ChangeKind.Edited,
    summary: "Change checkout copy",
    journeyId: "flow:checkout",
    journeyTitle: "Checkout",
    targetNodeId: "native:flow:checkout:n:pay",
    targetNativeNodeId: "n:pay",
    targetNativeKind: CanvasV2NodeKind.Do,
    targetFlowId: "flow:checkout",
    createdAt: now,
    updatedAt: now,
    ...overrides,
  }
}

describe("change request payloads", () => {
  it("sends typed refs as the primary pending request contract", () => {
    const payload = changeRequestFor(change())

    expect(payload.refs).toEqual([
      {
        kind: PendingRefKind.Flow,
        id: "flow:checkout",
        source: "change.targetFlowId",
      },
      {
        kind: PendingRefKind.Node,
        id: "n:pay",
        flow: "flow:checkout",
        source: "change.targetNativeNodeId",
      },
    ])
    expect(payload.journeyId).toBe("flow:checkout")
    expect(payload.targetNodeId).toBe("native:flow:checkout:n:pay")
    expect(payload.targetNativeNodeId).toBe("n:pay")
  })

  it("falls back to display ids when native refs are unavailable", () => {
    expect(
      refsForChange(
        change({
          targetNodeId: "display-pay",
          targetNativeNodeId: undefined,
          targetNativeKind: undefined,
          targetFlowId: undefined,
        })
      )
    ).toEqual([
      {
        kind: PendingRefKind.Flow,
        id: "flow:checkout",
        source: "change.journeyId",
      },
      {
        kind: PendingRefKind.Node,
        id: "display-pay",
        flow: "flow:checkout",
        source: "change.targetNodeId",
      },
    ])
  })
})
