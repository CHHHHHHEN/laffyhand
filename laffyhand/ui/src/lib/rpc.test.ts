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
