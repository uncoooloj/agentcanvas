import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it } from "vitest"
import { WorkspaceMappingState, MappingRequestStatus } from "./WorkspaceMappingState"
import { CanvasStateKind, WorkspaceProgressStage } from "@/lib/types"

describe("WorkspaceMappingState", () => {
  it("shows sent requests with live progress and prevents another send", () => {
    const html = renderToStaticMarkup(
      <WorkspaceMappingState
        kind={CanvasStateKind.Reindexing}
        stageIndex={1}
        workspaceName="Checkout"
        assistantName="Claude"
        requestStatus={MappingRequestStatus.Sent}
        progress={{
          exists: true,
          readable: true,
          stage: WorkspaceProgressStage.Surveying,
          message: "Finding entry points",
          current: 2,
          total: 4,
        }}
        onRetry={() => undefined}
      />
    )

    expect(html).toContain("Mapping request sent to Claude")
    expect(html).toContain('role="status"')
    expect(html).toContain('aria-label="Mapping progress"')

    const sentEmptyHtml = renderToStaticMarkup(
      <WorkspaceMappingState
        kind={CanvasStateKind.Empty}
        stageIndex={0}
        workspaceName="Checkout"
        assistantName="Claude"
        requestStatus={MappingRequestStatus.Sent}
        onRequestMap={() => undefined}
        onRetry={() => undefined}
      />
    )
    expect(sentEmptyHtml).toContain('aria-label="Mapping request sent to Claude"')
    expect(sentEmptyHtml).toContain('disabled=""')
  })

  it("announces request failures and keeps retry available", () => {
    const html = renderToStaticMarkup(
      <WorkspaceMappingState
        kind={CanvasStateKind.Empty}
        stageIndex={0}
        workspaceName="Checkout"
        assistantName="Claude"
        requestStatus={MappingRequestStatus.Failed}
        requestError="The local server is unavailable."
        onRequestMap={() => undefined}
        onRetry={() => undefined}
      />
    )

    expect(html).toContain("The local server is unavailable.")
    expect(html).toContain('aria-label="Send map request to Claude"')
    expect(html).not.toContain('aria-label="Mapping request sent to Claude"')
  })
})
