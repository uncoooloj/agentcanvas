import { afterEach, describe, expect, it, vi } from "vitest"
import { AppContextMode, fetchAppContext, hasRuntimeLaunchContext, RuntimeConnectionState } from "./appcontext"

afterEach(() => vi.unstubAllGlobals())

describe("hasRuntimeLaunchContext", () => {
  it("recognizes a workspace launch even with a stale welcome route", () => {
    expect(hasRuntimeLaunchContext("?token=launch-token&sessionId=abc")).toBe(true)
  })

  it("does not treat a marketing visit as a runtime launch", () => {
    expect(hasRuntimeLaunchContext("?utm_source=share")).toBe(false)
  })

  it("does not treat demo mode as a broken workspace launch", () => {
    expect(hasRuntimeLaunchContext("?demo=1")).toBe(false)
  })

  it("keeps a failed runtime launch out of the marketing fallback", async () => {
    vi.stubGlobal("window", { location: { origin: "http://127.0.0.1:8765", search: "?token=launch-token&sessionId=abc" } })
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("connection refused")))

    const result = await fetchAppContext()

    expect(result.connection).toBe(RuntimeConnectionState.Disconnected)
    expect(result.context.mode).toBe(AppContextMode.Landing)
    expect(result.error).toContain("could not reach")
  })
})
