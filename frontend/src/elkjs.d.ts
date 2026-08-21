declare module "elkjs/lib/elk.bundled.js" {
  type ElkGraph = import("./lib/canvasV2Layout").ElkWorkerGraph

  class ELK {
    layout(graph: ElkGraph): Promise<ElkGraph>
  }

  export default ELK
}
