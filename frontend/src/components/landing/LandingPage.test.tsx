import { describe, expect, it } from "vitest"
import { checkout, createProposal, getSandboxUrl, services, steeringExamples } from "./studioDemo"

describe("landing sandbox links", () => {
  it("opens the demo at the current base path and clears old tab and anchor state", () => {
    expect(getSandboxUrl("https://example.test/agentcanvas/welcome?tab=diff#start", "flows"))
      .toBe("https://example.test/agentcanvas/welcome?demo=1")
  })

  it("adds the requested diff tab while keeping unrelated query parameters", () => {
    expect(getSandboxUrl("https://example.test/welcome?preview=1#visual-diff", "diff"))
      .toBe("https://example.test/welcome?preview=1&demo=1&tab=diff")
  })
})

describe("playable checkout studio", () => {
  it("shows a five-step map with two additions and one modification in the branch diff", () => {
    expect(checkout.filter((node) => node.change !== "Added")).toHaveLength(5)
    expect(checkout.filter((node) => node.change === "Added")).toHaveLength(2)
    expect(checkout.filter((node) => node.change === "Modified")).toHaveLength(1)
    expect(checkout.filter((node) => node.change).every((node) => node.diff?.startsWith("@@"))).toBe(true)
    expect(services.map((node) => node.label)).toEqual(["Web App", "Order API", "Inventory", "Stripe", "Notify Worker"])
  })

  it("grounds each example pin in the relevant file", () => {
    expect(createProposal(steeringExamples[0])).toMatchObject({
      file: "src/payments/charge.ts",
      label: "Screen orders over $500",
      draft: expect.stringContaining("fraud.screen(order)"),
    })
    expect(createProposal(steeringExamples[1])).toMatchObject({
      file: "src/notify/receipt.ts",
      draft: expect.stringContaining("retryWithBackoff"),
    })
  })

  it("keeps a visitor's custom pin and ignores whitespace-only input", () => {
    expect(createProposal("  Offer pickup at checkout  ")).toMatchObject({
      label: "Offer pickup at checkout",
      draft: expect.stringContaining("+// Steering pin: Offer pickup at checkout"),
    })
    expect(createProposal("  ")).toBeNull()
  })
})
