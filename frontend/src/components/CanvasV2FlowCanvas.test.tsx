import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it } from "vitest"
import {
  CanvasV2FlowCanvas,
  CanvasV2KeyboardDirection,
  keyboardDirectionFromKey,
  keyboardTargetForNode,
  pendingRequestLinkForNode,
} from "./CanvasV2FlowCanvas"
import { TooltipProvider } from "./ui/tooltip"
import { nativeNodeToDisplayNode } from "@/lib/nativeDisplay"
import { CanvasV2EdgeKind, CanvasV2NodeKind, CanvasV2Status, type CanvasV2Flow } from "@/lib/types"

describe("CanvasV2FlowCanvas", () => {
  const flow: CanvasV2Flow = {
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
        evidence: [],
        evidenceRefs: [],
      },
      {
        id: "n:pay",
        kind: CanvasV2NodeKind.Do,
        title: "Take payment",
        evidence: [],
        evidenceRefs: [],
        status: CanvasV2Status.Proposed,
        metadata: {
          pending_request_id: "pending-123",
        },
      },
      {
        id: "n:receipt",
        kind: CanvasV2NodeKind.SubFlow,
        title: "Send receipt",
        flowRef: "flow:receipt",
        evidence: [],
        evidenceRefs: [],
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
      {
        id: "e:pay:receipt",
        kind: CanvasV2EdgeKind.Normal,
        source: "n:pay",
        target: "n:receipt",
        evidence: [],
        evidenceRefs: [],
      },
    ],
  }

  it("keeps native-only nodes rendered as enabled action targets through synthetic display nodes", () => {
    const html = renderToStaticMarkup(
      <TooltipProvider>
        <CanvasV2FlowCanvas
          flow={flow}
          selectedDisplayId={null}
          displayNodeForNativeId={(nativeId) => {
            const node = flow.nodes.find((item) => item.id === nativeId)
            return node ? nativeNodeToDisplayNode(flow.id, node) : null
          }}
          onSelectDisplayNode={() => undefined}
          onOpenPendingRequest={() => undefined}
          onAction={() => undefined}
        />
      </TooltipProvider>
    )

    expect(html).toContain("Take payment")
    expect(html).toContain("Not built yet")
    expect(html).toContain('aria-label="View request"')
    expect(html).toContain("Send receipt")
    expect(html).toContain("Opens receipt")
    expect(html).toContain('data-canvas-v2-node-id="n:start"')
    expect(html).toContain('aria-label="Change"')
    expect(html).toContain('aria-label="Add a step after"')
    expect(html).not.toContain('disabled=""')
  })

  it("maps keyboard keys to graph navigation targets", () => {
    const layoutNodes = [
      { id: "n:start", x: 0, y: 0, w: 260, h: 74 },
      { id: "n:pay", x: 0, y: 100, w: 260, h: 74 },
      { id: "n:receipt", x: 0, y: 200, w: 260, h: 74 },
    ]

    expect(keyboardDirectionFromKey("ArrowDown")).toBe(CanvasV2KeyboardDirection.Next)
    expect(keyboardDirectionFromKey("ArrowLeft")).toBe(CanvasV2KeyboardDirection.Previous)
    expect(keyboardDirectionFromKey("Home")).toBe(CanvasV2KeyboardDirection.First)
    expect(keyboardDirectionFromKey("x")).toBeNull()
    expect(keyboardTargetForNode(flow, layoutNodes, "n:start", CanvasV2KeyboardDirection.Next)).toBe("n:pay")
    expect(keyboardTargetForNode(flow, layoutNodes, "n:receipt", CanvasV2KeyboardDirection.Previous)).toBe("n:pay")
    expect(keyboardTargetForNode(flow, layoutNodes, "n:pay", CanvasV2KeyboardDirection.First)).toBe("n:start")
    expect(keyboardTargetForNode(flow, layoutNodes, "n:pay", CanvasV2KeyboardDirection.Last)).toBe("n:receipt")
  })

  it("reads pending request links from proposed node metadata", () => {
    expect(pendingRequestLinkForNode(flow.nodes[1])).toEqual({
      pendingRequestId: "pending-123",
    })
    expect(
      pendingRequestLinkForNode({
        ...flow.nodes[1],
        metadata: { client_change_id: "client-456" },
      })
    ).toEqual({ clientChangeId: "client-456" })
    expect(pendingRequestLinkForNode(flow.nodes[0])).toBeNull()
  })
})
