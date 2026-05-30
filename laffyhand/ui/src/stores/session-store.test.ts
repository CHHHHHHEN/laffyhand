import { describe, it, expect, beforeEach } from "vitest"
import { useSessionStore } from "./session-store"

beforeEach(() => {
  useSessionStore.setState({
    currentSessionId: null,
  })
})

describe("session-store", () => {
  it("sets current session id", () => {
    useSessionStore.getState().setCurrentSessionId("s1")
    expect(useSessionStore.getState().currentSessionId).toBe("s1")
  })

  it("clears current session id", () => {
    useSessionStore.getState().setCurrentSessionId("s1")
    useSessionStore.getState().setCurrentSessionId(null)
    expect(useSessionStore.getState().currentSessionId).toBeNull()
  })
})
