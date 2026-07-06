import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it } from "vitest"
import { CanvasV2FlowCanvas } from "./CanvasV2FlowCanvas"
import { TooltipProvider } from "./ui/tooltip"
import { nativeNodeToDisplayNode } from "@/lib/nativeDisplay"
import { CanvasV2EdgeKind, CanvasV2NodeKind, type CanvasV2Flow } from "@/lib/types"

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
          onAction={() => undefined}
        />
      </TooltipProvider>
    )

    expect(html).toContain("Take payment")
    expect(html).toContain('aria-label="Change"')
    expect(html).toContain('aria-label="Add a step after"')
    expect(html).not.toContain('disabled=""')
  })
})
