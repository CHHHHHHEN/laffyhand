import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"
import { useChatStore } from "@/stores/chat-store"

function makeReadableStream(chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder()
  return new ReadableStream({
    async pull(controller) {
      for (const chunk of chunks) {
        controller.enqueue(encoder.encode(chunk))
      }
      controller.close()
    },
  })
}

function mockFetchStream(body: ReadableStream<Uint8Array>) {
  return vi.fn().mockResolvedValue({
    ok: true,
    body,
    headers: new Headers(),
  })
}

function makeAbortableFetch(): {
  fetch: typeof globalThis.fetch
  abort: () => void
} {
  let abortHandler: (() => void) | null = null
  const fetch = vi.fn().mockImplementation(
    (_url: string, options?: RequestInit) =>
      new Promise((_resolve, reject) => {
        const signal = options?.signal as AbortSignal | undefined
        if (signal?.aborted) {
          reject(new DOMException("Aborted", "AbortError"))
          return
        }
        const onAbort = () => reject(new DOMException("Aborted", "AbortError"))
        signal?.addEventListener("abort", onAbort, { once: true })
        abortHandler = () => {
          signal?.removeEventListener("abort", onAbort)
          reject(new DOMException("Aborted", "AbortError"))
        }
      }),
  ) as unknown as typeof globalThis.fetch
  return { fetch, abort: () => abortHandler?.() }
}

beforeEach(() => {
  vi.restoreAllMocks()
  useChatStore.setState({ sessions: {} })
})

afterEach(() => {
  useChatStore.setState({ sessions: {} })
})

describe("createSessionSubscription", () => {
  it("receives events and dispatches to store", async () => {
    useChatStore.getState().addSession("sess-1")
    useChatStore.getState().startStreaming("sess-1")

    const stream = makeReadableStream([
      'data: {"method":"event","params":{"type":"text-delta","text":"Hello"}}\n\n',
      'data: {"method":"event","params":{"type":"finish"}}\n\n',
    ])
    globalThis.fetch = mockFetchStream(stream)

    const { createSessionSubscription } = await import("./session-subscription")
    await createSessionSubscription({ sessionId: "sess-1" })

    const sess = useChatStore.getState().sessions["sess-1"]
    expect(sess?.messages.some((m) => m.content === "Hello")).toBe(true)
  })

  it("reconnects on fetch failure and checks session status", async () => {
    useChatStore.getState().addSession("sess-1")

    globalThis.fetch = vi
      .fn()
      .mockRejectedValueOnce(new Error("network error"))
      .mockResolvedValueOnce({
        ok: true,
        body: makeReadableStream([
          'data: {"method":"event","params":{"type":"finish"}}\n\n',
        ]),
        headers: new Headers(),
      })

    const mockSessionLoad = vi
      .fn()
      .mockResolvedValueOnce({ is_streaming: true })
    const { rpcClient } = await import("./rpc")
    rpcClient.sessionLoad = mockSessionLoad

    const { createSessionSubscription } = await import("./session-subscription")
    await createSessionSubscription({ sessionId: "sess-1" })

    expect(globalThis.fetch).toHaveBeenCalledTimes(2)
  })

  it("stops reconnecting when session is no longer streaming", async () => {
    useChatStore.getState().addSession("sess-1")

    globalThis.fetch = vi.fn().mockRejectedValue(new Error("network error"))

    const mockSessionLoad = vi
      .fn()
      .mockResolvedValueOnce({ is_streaming: false })
    const { rpcClient } = await import("./rpc")
    rpcClient.sessionLoad = mockSessionLoad

    const { createSessionSubscription } = await import("./session-subscription")
    await createSessionSubscription({ sessionId: "sess-1" })

    expect(globalThis.fetch).toHaveBeenCalledTimes(1)
  })

  it("exits on abort signal", async () => {
    useChatStore.getState().addSession("sess-1")

    const { fetch: mockFetch, abort } = makeAbortableFetch()
    globalThis.fetch = mockFetch

    const { createSessionSubscription } = await import("./session-subscription")
    const controller = new AbortController()

    const promise = createSessionSubscription({
      sessionId: "sess-1",
      signal: controller.signal,
    })

    controller.abort()
    abort()
    await promise

    expect(globalThis.fetch).toHaveBeenCalledTimes(1)
  })

  it("stops reconnecting on normal stream end (finish sent)", async () => {
    useChatStore.getState().addSession("sess-1")
    useChatStore.getState().startStreaming("sess-1")

    const stream = makeReadableStream([
      'data: {"method":"event","params":{"type":"text-delta","text":"done"}}\n\n',
      'data: {"method":"event","params":{"type":"finish"}}\n\n',
    ])
    globalThis.fetch = mockFetchStream(stream)

    const { createSessionSubscription } = await import("./session-subscription")
    await createSessionSubscription({ sessionId: "sess-1" })

    expect(globalThis.fetch).toHaveBeenCalledTimes(1)

    const sess = useChatStore.getState().sessions["sess-1"]
    expect(sess?.messages.some((m) => m.content === "done")).toBe(true)
  })

  it("calls onReconnect callback after successful reconnect", async () => {
    useChatStore.getState().addSession("sess-1")

    globalThis.fetch = vi
      .fn()
      .mockRejectedValueOnce(new Error("fail"))
      .mockResolvedValueOnce({
        ok: true,
        body: makeReadableStream([
          'data: {"method":"event","params":{"type":"finish"}}\n\n',
        ]),
        headers: new Headers(),
      })

    const { rpcClient } = await import("./rpc")
    rpcClient.sessionLoad = vi.fn().mockResolvedValue({ is_streaming: true })

    const { createSessionSubscription } = await import("./session-subscription")
    const onReconnect = vi.fn()
    await createSessionSubscription({
      sessionId: "sess-1",
      onReconnect,
    })

    expect(onReconnect).toHaveBeenCalledOnce()
  })
})

describe("stopActiveSubscription", () => {
  it("stops an active subscription", async () => {
    useChatStore.getState().addSession("sess-1")

    const { fetch: mockFetch, abort } = makeAbortableFetch()
    globalThis.fetch = mockFetch

    const { createSessionSubscription, stopActiveSubscription } = await import(
      "./session-subscription"
    )

    const controller = new AbortController()
    const promise = createSessionSubscription({
      sessionId: "sess-1",
      signal: controller.signal,
    })

    // Stop the subscription
    stopActiveSubscription("sess-1")
    abort()
    await promise

    expect(globalThis.fetch).toHaveBeenCalledTimes(1)
  })
})
