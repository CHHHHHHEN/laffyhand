import { describe, it, expect, beforeEach } from "vitest"
import { useSessionStore } from "./session-store"
import type { Session } from "@/types/session"

function createSession(id: string): Session {
  return {
    id,
    title: `Session ${id}`,
    status: "active",
    messageCount: 0,
    turnCount: 0,
    createdAt: Date.now(),
  }
}

beforeEach(() => {
  useSessionStore.setState({
    sessions: [],
    currentSessionId: null,
    isLoading: false,
    error: null,
  })
})

describe("session-store", () => {
  it("sets sessions list", () => {
    const sessions = [createSession("s1"), createSession("s2")]
    useSessionStore.getState().setSessions(sessions)
    expect(useSessionStore.getState().sessions).toHaveLength(2)
  })

  it("adds a session at the beginning", () => {
    useSessionStore.getState().setSessions([createSession("s1")])
    useSessionStore.getState().addSession(createSession("s2"))
    expect(useSessionStore.getState().sessions).toHaveLength(2)
    expect(useSessionStore.getState().sessions[0]!.id).toBe("s2")
  })

  it("removes a session and clears currentSessionId if removed", () => {
    useSessionStore.getState().setSessions([createSession("s1"), createSession("s2")])
    useSessionStore.getState().setCurrentSessionId("s1")
    useSessionStore.getState().removeSession("s1")
    expect(useSessionStore.getState().sessions).toHaveLength(1)
    expect(useSessionStore.getState().sessions[0]!.id).toBe("s2")
    expect(useSessionStore.getState().currentSessionId).toBeNull()
  })

  it("updates session fields", () => {
    useSessionStore.getState().setSessions([createSession("s1")])
    useSessionStore.getState().updateSession("s1", { title: "Updated", messageCount: 5 })
    const s = useSessionStore.getState().sessions[0]!
    expect(s.title).toBe("Updated")
    expect(s.messageCount).toBe(5)
  })

  it("sets current session id", () => {
    useSessionStore.getState().setCurrentSessionId("s1")
    expect(useSessionStore.getState().currentSessionId).toBe("s1")
  })

  it("sets loading state", () => {
    useSessionStore.getState().setLoading(true)
    expect(useSessionStore.getState().isLoading).toBe(true)
    useSessionStore.getState().setLoading(false)
    expect(useSessionStore.getState().isLoading).toBe(false)
  })

  it("sets error state", () => {
    useSessionStore.getState().setError("Something went wrong")
    expect(useSessionStore.getState().error).toBe("Something went wrong")
    useSessionStore.getState().setError(null)
    expect(useSessionStore.getState().error).toBeNull()
  })
})
