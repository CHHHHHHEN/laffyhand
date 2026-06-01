import type {
  JsonRpcRequest,
  JsonRpcResponse,
  JsonRpcError,
  ServerInfo,
  SessionListResult,
  SessionCreateParams,
  SessionCreateResult,
  SessionLoadResult,
  SessionDeleteResult,
  SessionForkResult,
  CancelResult,
  ToolsListResult,
  StreamEvent,
  TodoListResult,
  TodoItemData,
} from "@/types/rpc"

export class RpcError extends Error {
  constructor(
    public code: number,
    message: string,
    public data?: unknown,
  ) {
    super(message)
    this.name = "RpcError"
  }
}

let requestId = 1

function nextId(): number {
  return requestId++
}

function getBaseUrl(): string {
  if (import.meta.env.VITE_API_BASE_URL) return import.meta.env.VITE_API_BASE_URL
  const protocol = location.protocol === "https:" ? "https:" : "http:"
  return `${protocol}//${location.hostname}:9090`
}

async function call<TResult>(
  method: string,
  params?: unknown,
  signal?: AbortSignal,
  timeoutMs = 30000,
): Promise<TResult> {
  const body: JsonRpcRequest = {
    jsonrpc: "2.0",
    id: nextId(),
    method,
    params,
  }

  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs)
  if (signal) {
    signal.addEventListener("abort", () => controller.abort(), { once: true })
  }

  try {
    const response = await fetch(`${getBaseUrl()}/rpc`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: controller.signal,
    })

    if (!response.ok) {
      const errorBody = await response.text()
      throw new RpcError(response.status, `HTTP ${response.status}: ${errorBody}`)
    }

    const raw: unknown = await response.json()
    const data = raw as JsonRpcResponse<TResult> | JsonRpcError

    if ("error" in data && data.error != null) {
      throw new RpcError(data.error.code, data.error.message, data.error.data)
    }

    return (data as JsonRpcResponse<TResult>).result
  } finally {
    clearTimeout(timeoutId)
  }
}

async function callStream(
  method: string,
  params?: unknown,
  signal?: AbortSignal,
): Promise<ReadableStream<Uint8Array>> {
  const body: JsonRpcRequest = {
    jsonrpc: "2.0",
    id: nextId(),
    method,
    params,
  }

  const controller = new AbortController()
  if (signal) {
    signal.addEventListener("abort", () => controller.abort(), { once: true })
  }

  const response = await fetch(`${getBaseUrl()}/rpc`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    },
    body: JSON.stringify(body),
    signal: controller.signal,
  })

  if (!response.ok) {
    const errorBody = await response.text()
    throw new RpcError(response.status, `HTTP ${response.status}: ${errorBody}`)
  }

  if (!response.body) {
    throw new RpcError(0, "Response body is null")
  }

  return response.body
}

export interface ChatStreamCallbacks {
  onEvent: (event: StreamEvent) => void
  onError: (error: Error) => void
  onComplete: () => void
}

export async function chatStream(
  message: string,
  callbacks: ChatStreamCallbacks,
  signal?: AbortSignal,
  sessionId?: string,
): Promise<void> {
  const params: Record<string, unknown> = { message }
  if (sessionId) {
    params.session_id = sessionId
  }
  const stream = await callStream("chat/stream", params, signal)
  const reader = stream.getReader()
  const decoder = new TextDecoder()
  let buffer = ""

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split("\n")
      buffer = lines.pop() ?? ""

      for (const line of lines) {
        if (!line.trim()) continue

        if (line.startsWith("data: ")) {
          try {
            const raw = JSON.parse(line.slice(6))
            const notification = raw as {
              method?: string
              params?: Record<string, unknown>
            }
            const event: Record<string, unknown> | undefined =
              notification.params ?? (raw as Record<string, unknown>)
            if (event?.type) {
              callbacks.onEvent(event as StreamEvent)
            }
            if (event?.type === "finish") {
              callbacks.onComplete()
            }
          } catch {
            // skip unparseable lines
          }
        }
      }
    }
  } catch (err) {
    if (signal?.aborted) return
    callbacks.onError(
      err instanceof Error ? err : new Error(String(err)),
    )
  } finally {
    reader.releaseLock()
  }
}

export interface ConfigProvidersResult {
  default_provider: string
  providers: Record<string, {
    type: string
    base_url: string
    models: { name: string; context_size: number }[]
  }>
}

export interface MCPStatusResult {
  servers: { name: string; status: string }[]
}

export const rpcClient = {
  initialize(): Promise<ServerInfo> {
    return call<ServerInfo>("initialize")
  },

  sessionList(limit = 50, offset = 0): Promise<SessionListResult> {
    return call<SessionListResult>("session/list", { limit, offset })
  },

  sessionCreate(
    params?: SessionCreateParams,
  ): Promise<SessionCreateResult> {
    return call<SessionCreateResult>("session/create", params ?? {})
  },

  sessionLoad(
    sessionId: string,
  ): Promise<SessionLoadResult> {
    return call<SessionLoadResult>("session/load", { session_id: sessionId })
  },

  sessionDelete(sessionId: string): Promise<SessionDeleteResult> {
    return call<SessionDeleteResult>("session/delete", {
      session_id: sessionId,
    })
  },

  sessionFork(): Promise<SessionForkResult> {
    return call<SessionForkResult>("session/fork")
  },

  toolsList(): Promise<ToolsListResult> {
    return call<ToolsListResult>("tools/list")
  },

  configProviders(): Promise<ConfigProvidersResult> {
    return call<ConfigProvidersResult>("config/providers")
  },

  mcpStatus(): Promise<MCPStatusResult> {
    return call<MCPStatusResult>("mcp/status")
  },

  sessionSetConfig(params: { provider: string; model: string }): Promise<{ session_id: string }> {
    return call<{ session_id: string }>("session/set_config", params)
  },

  cancelStream(): Promise<CancelResult> {
    return call<CancelResult>("chat/cancel")
  },

  steerMessage(
    message: string,
    sessionId?: string,
  ): Promise<{ status: string; session_id: string }> {
    const params: Record<string, unknown> = { message }
    if (sessionId) {
      params.session_id = sessionId
    }
    return call<{ status: string; session_id: string }>("chat/steer", params)
  },

  permissionRespond(requestId: string, action: "allow" | "always" | "deny"): Promise<{ status: string }> {
    return call<{ status: string }>("permission/respond", { request_id: requestId, action })
  },

  todoList(sessionId?: string): Promise<TodoListResult> {
    const params: Record<string, unknown> = {}
    if (sessionId) params.session_id = sessionId
    return call<TodoListResult>("todo/list", params)
  },

  todoUpdate(taskId: string, updates: { status?: string; priority?: string; content?: string }, sessionId?: string): Promise<TodoItemData> {
    const params: Record<string, unknown> = { task_id: taskId, ...updates }
    if (sessionId) params.session_id = sessionId
    return call<TodoItemData>("todo/update", params)
  },

  chatStream: (
    message: string,
    callbacks: ChatStreamCallbacks,
    signal?: AbortSignal,
    sessionId?: string,
  ) => chatStream(message, callbacks, signal, sessionId),
}
