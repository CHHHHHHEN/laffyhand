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

  it("forks the current session with session ID", async () => {
    mockSessionList.mockResolvedValue({ sessions: mockSessions })
    mockSessionFork.mockResolvedValue({ session_id: "sess-forked" })

    const { result } = renderHook(() => useSessions(), { wrapper: createWrapper() })

    await waitFor(() => expect(result.current.isLoading).toBe(false))

    let forkedId: string
    await act(async () => {
      forkedId = await result.current.forkSession("sess-1")
    })

    expect(forkedId!).toBe("sess-forked")
    expect(mockSessionFork).toHaveBeenCalledWith("sess-1")
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

  // ── Single-load behavior (polling removed, SSE subscription handles reconnection) ──

  it("loads session once regardless of is_streaming", async () => {
    mockSessionLoad.mockResolvedValue({
      session_id: "sess-load",
      messages_count: 0,
      turn_count: 0,
      is_streaming: true,
      messages: [],
    })

    renderHook(() => useCurrentSession("sess-load"), { wrapper: createWrapper() })

    await waitFor(() => expect(mockSessionLoad).toHaveBeenCalledTimes(1))

    // No polling — should stay at 1 call
    await act(async () => {
      await new Promise((r) => setTimeout(r, 300))
    })

    expect(mockSessionLoad).toHaveBeenCalledTimes(1)
  })

  it("loads session once when is_streaming is false", async () => {
    mockSessionLoad.mockResolvedValue({
      session_id: "sess-no-poll",
      messages_count: 0,
      turn_count: 0,
      is_streaming: false,
      messages: [],
    })

    renderHook(() => useCurrentSession("sess-no-poll"), { wrapper: createWrapper() })

    await waitFor(() => expect(mockSessionLoad).toHaveBeenCalledTimes(1))

    await act(async () => {
      await new Promise((r) => setTimeout(r, 100))
    })

    expect(mockSessionLoad).toHaveBeenCalledTimes(1)
  })
})
