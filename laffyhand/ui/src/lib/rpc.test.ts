import { describe, it, expect, vi, beforeEach } from "vitest"
import { rpcClient, RpcError } from "./rpc"

beforeEach(() => {
  vi.restoreAllMocks()
})

function mockFetch(status: number, body: unknown) {
  globalThis.fetch = vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(body),
  })
}

describe("rpcClient.sessionList", () => {
  it("returns session list", async () => {
    mockFetch(200, {
      jsonrpc: "2.0",
      id: 1,
      result: {
        sessions: [
          {
            id: "sess-1",
            status: "active",
            title: "Test",
            message_count: 5,
            turn_count: 3,
            created_at: 1000,
          },
        ],
      },
    })

    const result = await rpcClient.sessionList()
    expect(result.sessions).toHaveLength(1)
    expect(result.sessions[0]!.id).toBe("sess-1")
  })

  it("throws RpcError on error response", async () => {
    mockFetch(200, {
      jsonrpc: "2.0",
      id: 1,
      error: { code: -32601, message: "Method not found" },
    })

    await expect(rpcClient.sessionList()).rejects.toThrow(RpcError)
  })
})

describe("rpcClient.initialize", () => {
  it("returns server info", async () => {
    mockFetch(200, {
      jsonrpc: "2.0",
      id: 1,
      result: {
        protocol_version: "1.0",
        server_info: "laffyhand",
        session_id: null,
      },
    })

    const info = await rpcClient.initialize()
    expect(info.protocol_version).toBe("1.0")
  })
})

describe("rpcClient.sessionCreate", () => {
  it("creates session with title", async () => {
    mockFetch(200, {
      jsonrpc: "2.0",
      id: 1,
      result: { session_id: "sess-new" },
    })

    const result = await rpcClient.sessionCreate({ title: "New Chat" })
    expect(result.session_id).toBe("sess-new")
  })
})

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

describe("chatStream", () => {
  it("parses SSE events and calls onEvent", async () => {
    const stream = makeReadableStream([
      "data: {\"type\":\"content\",\"data\":\"Hello\"}\n\n",
      "data: {\"type\":\"content\",\"data\":\" World\"}\n\n",
    ])
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      body: stream,
      headers: new Headers(),
    })

    const { chatStream } = await import("./rpc")
    const onEvent = vi.fn()
    const onError = vi.fn()
    const onComplete = vi.fn()

    await chatStream("hi", { onEvent, onError, onComplete })

    expect(onEvent).toHaveBeenCalledTimes(2)
    expect(onEvent).toHaveBeenNthCalledWith(1, { type: "content", data: "Hello" })
    expect(onEvent).toHaveBeenNthCalledWith(2, { type: "content", data: " World" })
    expect(onError).not.toHaveBeenCalled()
  })

  it("calls onComplete on finish event", async () => {
    const stream = makeReadableStream([
      "data: {\"type\":\"finish\",\"data\":\"\"}\n\n",
    ])
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      body: stream,
      headers: new Headers(),
    })

    const { chatStream } = await import("./rpc")
    const onEvent = vi.fn()
    const onError = vi.fn()
    const onComplete = vi.fn()

    await chatStream("hi", { onEvent, onError, onComplete })

    expect(onComplete).toHaveBeenCalledOnce()
    expect(onError).not.toHaveBeenCalled()
  })

  it("calls onError on stream failure", async () => {
    const stream = new ReadableStream({
      start(controller) {
        controller.error(new Error("stream broken"))
      },
    })
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      body: stream,
      headers: new Headers(),
    })

    const { chatStream } = await import("./rpc")
    const onEvent = vi.fn()
    const onError = vi.fn()
    const onComplete = vi.fn()

    await chatStream("hi", { onEvent, onError, onComplete })

    expect(onError).toHaveBeenCalled()
    expect(onComplete).not.toHaveBeenCalled()
  })

  it("skips unparseable SSE lines silently", async () => {
    const stream = makeReadableStream([
      "data: not json\n\n",
      "data: {\"type\":\"content\",\"data\":\"ok\"}\n\n",
    ])
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      body: stream,
      headers: new Headers(),
    })

    const { chatStream } = await import("./rpc")
    const onEvent = vi.fn()
    const onError = vi.fn()
    const onComplete = vi.fn()

    await chatStream("hi", { onEvent, onError, onComplete })

    // Only the valid line should be processed
    expect(onEvent).toHaveBeenCalledTimes(1)
    expect(onEvent).toHaveBeenCalledWith({ type: "content", data: "ok" })
  })

  it("handles abort signal gracefully", async () => {
    const abortController = new AbortController()

    // Stream that errors on read
    const stream = new ReadableStream({
      pull() {
        throw new Error("stream error")
      },
    })
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      body: stream,
      headers: new Headers(),
    })

    const { chatStream } = await import("./rpc")
    const onError = vi.fn()
    const onComplete = vi.fn()

    // Pre-abort the signal — the catch block checks signal.aborted before calling onError
    abortController.abort()
    await chatStream("hi", { onEvent: vi.fn(), onError, onComplete }, abortController.signal)

    expect(onError).not.toHaveBeenCalled()
    expect(onComplete).not.toHaveBeenCalled()
  })
})
