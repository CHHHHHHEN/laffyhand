import { describe, it, expect, vi, beforeEach } from "vitest"
import { renderHook, act, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import type { ReactNode } from "react"
import { useSessions, useCurrentSession } from "./use-sessions"
import { useChatStore, resetMessageCounter } from "@/stores/chat-store"

// Mock rpcClient
const mockSessionList = vi.fn()
const mockSessionCreate = vi.fn()
const mockSessionDelete = vi.fn()
const mockSessionFork = vi.fn()
const mockSessionLoad = vi.fn()
const mockTodoList = vi.fn().mockResolvedValue({ tasks: [] })

vi.mock("@/lib/rpc", () => ({
  rpcClient: {
    sessionList: (...args: unknown[]) => mockSessionList(...args),
    sessionCreate: (...args: unknown[]) => mockSessionCreate(...args),
    sessionDelete: (...args: unknown[]) => mockSessionDelete(...args),
    sessionFork: (...args: unknown[]) => mockSessionFork(...args),
    sessionLoad: (...args: unknown[]) => mockSessionLoad(...args),
    todoList: (...args: unknown[]) => mockTodoList(...args),
  },
  RpcError: class extends Error {
    constructor(
      public code: number,
      message: string,
      public data?: unknown,
    ) {
      super(message)
      this.name = "RpcError"
    }
  },
}))

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  })
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  }
}

const mockSessions = [
  {
    id: "sess-1",
    status: "active",
    title: "Test Session",
    message_count: 5,
    turn_count: 3,
    created_at: 1000,
    updated_at: 2000,
  },
  {
    id: "sess-2",
    status: "archived",
    title: "Old Session",
    message_count: 2,
    turn_count: 1,
    created_at: 500,
    updated_at: 1500,
  },
]

beforeEach(() => {
  vi.clearAllMocks()
  resetMessageCounter()
  useChatStore.setState({ sessions: {} })
})

describe("useSessions", () => {
  it("returns session list", async () => {
    mockSessionList.mockResolvedValue({ sessions: mockSessions })

    const { result } = renderHook(() => useSessions(), { wrapper: createWrapper() })

    await waitFor(() => expect(result.current.isLoading).toBe(false))

    expect(result.current.sessions).toHaveLength(2)
    expect(result.current.sessions[0]?.id).toBe("sess-1")
    expect(result.current.sessions[0]?.title).toBe("Test Session")
  })

  it("creates a new session", async () => {
    mockSessionList.mockResolvedValue({ sessions: [] })
    mockSessionCreate.mockResolvedValue({ session_id: "sess-new" })

    const { result } = renderHook(() => useSessions(), { wrapper: createWrapper() })

    await waitFor(() => expect(result.current.isLoading).toBe(false))

    let newId: string
    await act(async () => {
      newId = await result.current.createSession("New Chat")
    })

    expect(newId!).toBe("sess-new")
    expect(mockSessionCreate).toHaveBeenCalledWith({ title: "New Chat" })
  })

  it("deletes a session", async () => {
    mockSessionList.mockResolvedValue({ sessions: mockSessions })
    mockSessionDelete.mockResolvedValue({ status: "deleted", session_id: "sess-1" })

    const { result } = renderHook(() => useSessions(), { wrapper: createWrapper() })

    await waitFor(() => expect(result.current.isLoading).toBe(false))

    await act(async () => {
      await result.current.deleteSession("sess-1")
    })

    expect(mockSessionDelete).toHaveBeenCalledWith("sess-1")
  })

  it("forks the current session", async () => {
    mockSessionList.mockResolvedValue({ sessions: mockSessions })
    mockSessionFork.mockResolvedValue({ session_id: "sess-forked" })

    const { result } = renderHook(() => useSessions(), { wrapper: createWrapper() })

    await waitFor(() => expect(result.current.isLoading).toBe(false))

    let forkedId: string
    await act(async () => {
      forkedId = await result.current.forkSession()
    })

    expect(forkedId!).toBe("sess-forked")
    expect(mockSessionFork).toHaveBeenCalled()
  })
})

describe("useCurrentSession", () => {
  it("loads and sets messages for a session", async () => {
    mockSessionLoad.mockResolvedValue({
      session_id: "sess-1",
      messages_count: 2,
      turn_count: 2,
      messages: [
        { id: "m1", role: "user" as const, content: "hello", createdAt: 100 },
        { id: "m2", role: "assistant" as const, content: "hi", createdAt: 200, usage: { inputTokens: 10, outputTokens: 5 } },
      ],
    })

    const { result } = renderHook(() => useCurrentSession("sess-1"), { wrapper: createWrapper() })

    await waitFor(() => expect(result.current.isLoading).toBe(false))

    expect(mockSessionLoad).toHaveBeenCalledWith("sess-1")
    const state = useChatStore.getState().sessions["sess-1"]
    expect(state).toBeDefined()
    expect(state!.messages).toHaveLength(2)
    expect(state!.messages[0]?.content).toBe("hello")
    expect(state!.messages[1]?.content).toBe("hi")
  })

  it("does not set global currentSessionId in session-store", async () => {
    mockSessionLoad.mockResolvedValue({
      session_id: "sess-target",
      messages_count: 0,
      turn_count: 0,
      messages: [],
    })

    const { result } = renderHook(() => useCurrentSession("sess-target"), { wrapper: createWrapper() })

    await waitFor(() => expect(result.current.isLoading).toBe(false))

    const state = useChatStore.getState().sessions["sess-target"]
    expect(state).toBeDefined()
    expect(state!.messages).toHaveLength(0)
  })

  it("returns null for undefined sessionId", async () => {
    const { result } = renderHook(() => useCurrentSession(undefined), { wrapper: createWrapper() })

    expect(result.current.session).toBeUndefined()
    expect(result.current.isLoading).toBe(false)
    expect(mockSessionLoad).not.toHaveBeenCalled()
  })

  // ── Reconnection polling ──

  it("polls session/load when is_streaming is true", async () => {
    mockSessionLoad.mockResolvedValueOnce({
      session_id: "sess-poll",
      messages_count: 1,
      turn_count: 1,
      is_streaming: true,
      messages: [
        { id: "m1", role: "assistant" as const, content: "partial", createdAt: 100 },
      ],
    })

    renderHook(() => useCurrentSession("sess-poll"), { wrapper: createWrapper() })

    await waitFor(() => expect(mockSessionLoad).toHaveBeenCalledTimes(1))

    // Second call returns final data
    mockSessionLoad.mockResolvedValue({
      session_id: "sess-poll",
      messages_count: 2,
      turn_count: 1,
      is_streaming: false,
      messages: [
        { id: "m1", role: "assistant" as const, content: "partial", createdAt: 100 },
        { id: "m2", role: "assistant" as const, content: "complete", createdAt: 200 },
      ],
    })

    // Wait for the 2s polling interval to fire
    await waitFor(() => expect(mockSessionLoad).toHaveBeenCalledTimes(2), { timeout: 5000 })

    const state = useChatStore.getState().sessions["sess-poll"]
    expect(state!.messages).toHaveLength(2)
    expect(state!.messages[1]!.content).toBe("complete")
  }, 10000)

  it("does not poll when is_streaming is false", async () => {
    mockSessionLoad.mockResolvedValue({
      session_id: "sess-no-poll",
      messages_count: 0,
      turn_count: 0,
      is_streaming: false,
      messages: [],
    })

    renderHook(() => useCurrentSession("sess-no-poll"), { wrapper: createWrapper() })

    await waitFor(() => expect(mockSessionLoad).toHaveBeenCalledTimes(1))

    // Small delay — no polling should trigger
    await act(async () => {
      await new Promise((r) => setTimeout(r, 100))
    })

    expect(mockSessionLoad).toHaveBeenCalledTimes(1)
  })

  it("does not poll when frontend is already streaming", async () => {
    // Pre-seed the store with a session that has isStreaming=true (SSE active)
    useChatStore.getState().addSession("sess-live")
    useChatStore.setState((s) => ({
      sessions: {
        ...s.sessions,
        ["sess-live"]: {
          ...s.sessions["sess-live"]!,
          isStreaming: true,
        },
      },
    }))

    mockSessionLoad.mockResolvedValue({
      session_id: "sess-live",
      messages_count: 1,
      turn_count: 1,
      is_streaming: true,
      messages: [
        { id: "m1", role: "assistant" as const, content: "partial", createdAt: 100 },
      ],
    })

    renderHook(() => useCurrentSession("sess-live"), { wrapper: createWrapper() })

    await waitFor(() => expect(mockSessionLoad).toHaveBeenCalledTimes(1))

    // Even with is_streaming=true on the server, the frontend's
    // active SSE stream should suppress polling.
    await act(async () => {
      await new Promise((r) => setTimeout(r, 150))
    })

    expect(mockSessionLoad).toHaveBeenCalledTimes(1)
  })

  it("resumes polling after frontend streaming stops", async () => {
    // Start with isStreaming=true (SSE active), then set it to false
    useChatStore.getState().addSession("sess-resume")
    useChatStore.setState((s) => ({
      sessions: {
        ...s.sessions,
        ["sess-resume"]: {
          ...s.sessions["sess-resume"]!,
          isStreaming: true,
        },
      },
    }))

    mockSessionLoad.mockResolvedValue({
      session_id: "sess-resume",
      messages_count: 2,
      turn_count: 1,
      is_streaming: true,
      messages: [
        { id: "m1", role: "assistant" as const, content: "partial", createdAt: 100 },
      ],
    })

    renderHook(() => useCurrentSession("sess-resume"), { wrapper: createWrapper() })

    await waitFor(() => expect(mockSessionLoad).toHaveBeenCalledTimes(1))

    // Now stop the frontend SSE — polling should activate
    useChatStore.setState((s) => ({
      sessions: {
        ...s.sessions,
        ["sess-resume"]: {
          ...s.sessions["sess-resume"]!,
          isStreaming: false,
        },
      },
    }))

    mockSessionLoad.mockResolvedValue({
      session_id: "sess-resume",
      messages_count: 3,
      turn_count: 2,
      is_streaming: true,
      messages: [
        { id: "m1", role: "assistant" as const, content: "partial", createdAt: 100 },
        { id: "m2", role: "user" as const, content: "next", createdAt: 200 },
      ],
    })

    await waitFor(() => expect(mockSessionLoad).toHaveBeenCalledTimes(2), { timeout: 5000 })

    expect(mockSessionLoad).toHaveBeenCalledWith("sess-resume")
  }, 10000)
})
