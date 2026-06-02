import { describe, it, expect, vi, beforeEach } from "vitest"
import { renderHook, act } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { useChat } from "./use-chat"
import { useChatStore, resetMessageCounter } from "@/stores/chat-store"
import type { StreamEvent } from "@/types/rpc"
import type { ReactNode } from "react"

// Mock react-router-dom
vi.mock("react-router-dom", () => ({
  useParams: () => ({ sessionId: "sess-test" }),
}))

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    )
  }
}

// Mock rpcClient
const mockChatStream = vi.fn()
const mockCancelStream = vi.fn()
vi.mock("@/lib/rpc", () => ({
  rpcClient: {
    chatStream: (...args: unknown[]) => mockChatStream(...args),
    cancelStream: () => mockCancelStream(),
    todoList: () => Promise.resolve({ tasks: [] }),
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

beforeEach(() => {
  vi.clearAllMocks()
  resetMessageCounter()
  useChatStore.setState({
    messages: [],
    isStreaming: false,
    streamContent: "",
    streamReasoning: "",
    streamToolCalls: [],
    streamToolResults: [],
    currentAssistantMessageId: null,
    error: null,
  })
})

describe("useChat", () => {
  it("sends message and starts streaming", async () => {
    mockChatStream.mockImplementation(
      async (
        _message: string,
        callbacks: {
          onEvent: (event: StreamEvent) => void
          onComplete: () => void
          onError: (error: Error) => void
        },
        _signal?: AbortSignal,
      ) => {
        callbacks.onEvent({ type: "text-delta", id: "t1", text: "Hello!" })
        callbacks.onEvent({ type: "step-finish", index: 1, reason: "stop", usage: { input_tokens: 10, output_tokens: 5 } })
        callbacks.onEvent({ type: "finish", reason: "stop" })
        callbacks.onComplete()
      },
    )

    const { result } = renderHook(() => useChat(), { wrapper: createWrapper() })

    await act(async () => {
      await result.current.sendMessage("hi")
    })

    const state = useChatStore.getState()
    expect(state.messages.length).toBeGreaterThanOrEqual(1)
    const lastMsg = state.messages[state.messages.length - 1]
    expect(lastMsg?.role).toBe("assistant")
    expect(lastMsg?.content).toBe("Hello!")
  })

  it("does not send empty messages", async () => {
    const { result } = renderHook(() => useChat(), { wrapper: createWrapper() })

    await act(async () => {
      await result.current.sendMessage("  ")
    })

    expect(mockChatStream).not.toHaveBeenCalled()
  })

  it("does not send when already streaming", async () => {
    useChatStore.setState({ isStreaming: true })

    const { result } = renderHook(() => useChat(), { wrapper: createWrapper() })

    await act(async () => {
      await result.current.sendMessage("hello")
    })

    expect(mockChatStream).not.toHaveBeenCalled()
  })

  it("sets error on stream failure", async () => {
    mockChatStream.mockRejectedValue(new Error("Network error"))

    const { result } = renderHook(() => useChat(), { wrapper: createWrapper() })

    await act(async () => {
      await result.current.sendMessage("hello")
    })

    const state = useChatStore.getState()
    expect(state.error).toBe("Network error")
    expect(state.isStreaming).toBe(false)
  })

  it("cancels stream and finalizes if content exists", async () => {
    let resolvePromise: () => void = () => {}
    mockChatStream.mockImplementation(
      async (
        _message: string,
        callbacks: {
          onEvent: (event: StreamEvent) => void
          onComplete: () => void
          onError: (error: Error) => void
        },
        signal?: AbortSignal,
      ) => {
        callbacks.onEvent({ type: "text-delta", id: "t1", text: "partial" })
        await new Promise<void>((resolve) => {
          resolvePromise = resolve
          signal?.addEventListener("abort", () => resolve())
        })
      },
    )

    const { result } = renderHook(() => useChat(), { wrapper: createWrapper() })

    await act(async () => {
      result.current.sendMessage("hello")
    })

    mockCancelStream.mockResolvedValue({ status: "cancelled" })

    await act(async () => {
      await result.current.cancelStream()
    })

    expect(mockCancelStream).toHaveBeenCalled()
  })

  it("shows error if cancel with no content", async () => {
    let resolvePromise: () => void = () => {}
    mockChatStream.mockImplementation(
      async (
        _message: string,
        _callbacks: unknown,
        signal?: AbortSignal,
      ) => {
        await new Promise<void>((resolve) => {
          resolvePromise = resolve
          signal?.addEventListener("abort", () => resolve())
        })
      },
    )

    const { result } = renderHook(() => useChat(), { wrapper: createWrapper() })

    await act(async () => {
      result.current.sendMessage("hello")
      await new Promise((r) => setTimeout(r, 10))
    })

    mockCancelStream.mockResolvedValue({ status: "cancelled" })

    await act(async () => {
      await result.current.cancelStream()
    })

    const state = useChatStore.getState()
    expect(state.error).toBe("Stream cancelled")
  })
})
