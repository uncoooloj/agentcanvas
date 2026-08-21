export const CANVAS_POLL_INTERVAL_MS = 2500
export const PENDING_ACTIVITY_POLL_INTERVAL_MS = 5000
export const HEALTH_POLL_INTERVAL_MS = 30000

export function documentIsVisible(doc?: Pick<Document, "visibilityState"> | null): boolean {
  const current = doc ?? (typeof document === "undefined" ? undefined : document)
  return !current || current.visibilityState === "visible"
}
