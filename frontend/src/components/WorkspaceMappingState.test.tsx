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
        requestHasProgress
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

    expect(html).toContain("Claude has started looking through your app")
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
    expect(sentEmptyHtml).toContain("Waiting for Claude")
    expect(sentEmptyHtml).toContain("Check for updates")
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

    expect(html).toContain("We could not save your request.")
    expect(html).toContain('aria-label="Ask Claude to explain your app"')
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

    expect(html).toContain("Let&#x27;s understand your app")
    expect(html).toContain("Ask Codex to explain my app")
    expect(html).toContain("Working with another assistant?")
    expect(html).not.toContain("Starter map needs review")
    expect(html).not.toContain("Best next step")
    expect(html).not.toContain("Fallback")
  })

  it("waits for saved progress before claiming the assistant has started", () => {
    const html = renderToStaticMarkup(
      <WorkspaceMappingState
        kind={CanvasStateKind.Reindexing}
        stageIndex={0}
        workspaceName="Checkout"
        assistantName="Codex"
        requestStatus={MappingRequestStatus.Sent}
        fallbackPrompt="Explain the app"
        onRetry={() => undefined}
      />
    )

    expect(html).toContain("Waiting for Codex")
    expect(html).toContain("Your request is saved")
    expect(html).not.toContain("Codex has started looking through your app")
    expect(html).not.toContain('aria-label="Mapping progress"')
  })

  it("shows a reconnect state instead of a marketing fallback", () => {
    const html = renderToStaticMarkup(
      <WorkspaceMappingState
        kind={CanvasStateKind.Error}
        stageIndex={0}
        workspaceName=""
        connectionError="We could not reach the AgentCanvas session behind this link."
        onRetry={() => undefined}
      />
    )

    expect(html).toContain("We can&#x27;t reach this project")
    expect(html).toContain("Reopen AgentCanvas from your assistant")
    expect(html).toContain("Try again")
  })
})
