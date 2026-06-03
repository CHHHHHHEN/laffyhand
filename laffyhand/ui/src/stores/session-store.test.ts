import { describe, it, expect, beforeEach } from "vitest"
import { useSessionStore } from "./session-store"

beforeEach(() => {
  sessionStorage.clear()
  useSessionStore.setState({
    activeSessionId: null,
    activeSessionIds: [],
  })
})

describe("session-store", () => {
  it("sets active session id", () => {
    useSessionStore.getState().setActiveSessionId("s1")
    expect(useSessionStore.getState().activeSessionId).toBe("s1")
  })

  it("clears active session id", () => {
    useSessionStore.getState().setActiveSessionId("s1")
    useSessionStore.getState().setActiveSessionId(null)
    expect(useSessionStore.getState().activeSessionId).toBeNull()
  })

  it("adds an active session to the list", () => {
    useSessionStore.getState().addActiveSession("s1")
    expect(useSessionStore.getState().activeSessionIds).toEqual(["s1"])
  })

  it("does not duplicate active sessions", () => {
    useSessionStore.getState().addActiveSession("s1")
    useSessionStore.getState().addActiveSession("s1")
    expect(useSessionStore.getState().activeSessionIds).toEqual(["s1"])
  })

  it("removes an active session from the list", () => {
    useSessionStore.getState().addActiveSession("s1")
    useSessionStore.getState().addActiveSession("s2")
    useSessionStore.getState().removeActiveSession("s1")
    expect(useSessionStore.getState().activeSessionIds).toEqual(["s2"])
  })

  it("removing a non-existent session is a no-op", () => {
    useSessionStore.getState().addActiveSession("s1")
    useSessionStore.getState().removeActiveSession("nonexistent")
    expect(useSessionStore.getState().activeSessionIds).toEqual(["s1"])
  })

  it("persists active session ids to sessionStorage", () => {
    useSessionStore.getState().addActiveSession("s1")
    useSessionStore.getState().addActiveSession("s2")
    const stored = JSON.parse(sessionStorage.getItem("laffyhand-active-sessions")!)
    expect(stored).toEqual(["s1", "s2"])
  })

  it("restores active session ids from sessionStorage on init", () => {
    sessionStorage.setItem("laffyhand-active-sessions", JSON.stringify(["s1", "s2"]))
    // Re-create store to trigger load from storage
    useSessionStore.setState({
      activeSessionId: null,
      activeSessionIds: JSON.parse(sessionStorage.getItem("laffyhand-active-sessions")!),
    })
    expect(useSessionStore.getState().activeSessionIds).toEqual(["s1", "s2"])
  })
})
