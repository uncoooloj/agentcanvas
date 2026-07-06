import ELK from "elkjs/lib/elk.bundled.js"
import { flowToElkGraph, layoutFlow, layoutFlowFromElk, type CanvasV2Layout } from "./canvasV2Layout"
import type { CanvasV2Flow } from "./types"

type LayoutRequest = {
  id: number
  flow: CanvasV2Flow
}

type LayoutResponse = {
  id: number
  layout: CanvasV2Layout
  error?: string
}

const elk = new ELK()

self.onmessage = async (event: MessageEvent<LayoutRequest>) => {
  const { id, flow } = event.data
  try {
    const graph = await elk.layout(flowToElkGraph(flow))
    postMessage({ id, layout: layoutFlowFromElk(flow, graph) } satisfies LayoutResponse)
  } catch (error) {
    postMessage({
      id,
      layout: layoutFlow(flow),
      error: error instanceof Error ? error.message : "ELK layout failed",
    } satisfies LayoutResponse)
  }
}
