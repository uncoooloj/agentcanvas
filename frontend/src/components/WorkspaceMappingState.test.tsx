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

    expect(html).toContain("Claude is making the app map")
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
    expect(sentEmptyHtml).toContain("Claude is making your app map")
    expect(sentEmptyHtml).toContain("Refresh map")
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

    expect(html).toContain("We could not ask Claude just now.")
    expect(html).toContain('aria-label="Ask Claude to make the map"')
    expect(html).not.toContain("Mapping request sent")
  })

  it("keeps the first-run map request plain and focused", () => {
    const html = renderToStaticMarkup(
      <WorkspaceMappingState
        kind={CanvasStateKind.Empty}
        stageIndex={0}
        workspaceName="Checkout"
        assistantName="Codex"
        message="Starter map needs review"
        detail="Technical details should not take over this screen."
        fallbackPrompt="Make the map"
        onRequestMap={() => undefined}
        onRetry={() => undefined}
      />
    )

    expect(html).toContain("Let&#x27;s make a clear map of your app")
    expect(html).toContain("Create my app map")
    expect(html).toContain("Working with another assistant?")
    expect(html).not.toContain("Starter map needs review")
    expect(html).not.toContain("Best next step")
    expect(html).not.toContain("Fallback")
  })
})
