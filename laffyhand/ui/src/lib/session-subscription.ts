import type { StreamEvent, SessionUsage } from "@/types/rpc"
import { useChatStore } from "@/stores/chat-store"
import { useCallback, useEffect, useRef } from "react"
import { useQueryClient } from "@tanstack/react-query"
import { rpcClient } from "./rpc"
import { useTodoStore } from "@/stores/todo-store"
import type { TodoItem } from "@/types/session"

// ── Global subscription tracker ──────────────────────────────
// Allows useChat to stop subscription before starting a new chatStream.

let _activeSubCancel: (() => void) | null = null

export function stopActiveSubscription(_sessionId: string): void {
  if (_activeSubCancel) {
    _activeSubCancel()
    _activeSubCancel = null
  }
}

function setActiveCancel(cancel: () => void): void {
  _activeSubCancel = cancel
}

function clearActiveCancel(): void {
  _activeSubCancel = null
}

// ── Todo refresh helper ──────────────────────────────────────

function refreshTodo(sessionId: string) {
  rpcClient.todoList(sessionId).then((result) => {
    const tasks: TodoItem[] = result.tasks.map((t) => ({
      id: t.id,
      sessionId: t.sessionId,
      content: t.content,
      status: t.status as TodoItem["status"],
      dependsOn: t.dependsOn,
      blockedBy: t.blockedBy,
      createdAt: t.createdAt,
      updatedAt: t.updatedAt,
      completedAt: t.completedAt,
      taskToolId: t.taskToolId,
    }))
    useTodoStore.getState().setSessionTasks(sessionId, tasks)
  }).catch(() => {})
}

// ── Event handler (applies events to chat store) ─────────────

function handleEvent(sessionId: string, event: StreamEvent) {
  const store = useChatStore.getState()
  switch (event.type) {
    case "text-delta":
      if (event.text) {
        store.appendContent(sessionId, event.text)
      }
      break
    case "reasoning-delta":
      if (event.text) {
        store.setReasoning(sessionId, event.text)
      }
      break
    case "tool-call": {
      let parsed: Record<string, unknown> = {}
      try {
        parsed = JSON.parse(event.args)
      } catch {
        parsed = {}
      }
      store.addToolCall(sessionId, {
        id: event.tool_call_id,
        name: event.tool_name,
        arguments: parsed,
      })
      break
    }
    case "tool-result":
      store.updateToolCallStatus(sessionId, event.id, "completed", event.result)
      break
    case "tool-error":
      store.updateToolCallStatus(sessionId, event.id, "error", event.message, true)
      break
    case "step-finish":
      if (event.reason === "tool_calls") {
        const stepUsage = event.usage
          ? {
              inputTokens: event.usage.input_tokens,
              outputTokens: event.usage.output_tokens,
              reasoningTokens: event.usage.reasoning_tokens,
            }
          : undefined
        store.finalizeMessage(sessionId, stepUsage)
      }
      break
    case "finish":
      store.finalizeMessage(
        sessionId,
        event.usage
          ? {
              inputTokens: event.usage.input_tokens,
              outputTokens: event.usage.output_tokens,
              reasoningTokens: event.usage.reasoning_tokens,
            }
          : undefined,
        (event.session_usage as SessionUsage) ?? null,
      )
      break
    case "usage-update":
      store.updateSessionUsage(sessionId, event.session_usage as SessionUsage)
      break
    case "todo-update":
      refreshTodo(sessionId)
      break
    case "permission-request":
      store.addPermissionRequest(sessionId, {
        requestId: event.request_id,
        permission: event.permission,
        pattern: event.pattern,
      })
      break
    case "provider-error":
      store.setError(sessionId, event.message)
      break
    case "subagent-start":
      store.startSubagent(sessionId, event)
      break
    case "subagent-delta":
      store.updateSubagent(sessionId, event.id, event)
      break
    case "subagent-end":
      store.endSubagent(sessionId, event.id, event)
      break
  }
}

// ── SSE subscription with auto-reconnect ─────────────────────

export interface SessionSubscriptionOptions {
  sessionId: string
  onReconnect?: () => void
  signal?: AbortSignal
}

export async function createSessionSubscription(
  opts: SessionSubscriptionOptions,
): Promise<void> {
  const { sessionId, signal } = opts
  let retryDelay = 1000

  const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))

  const getBaseUrl = () => {
    if (import.meta.env.VITE_API_BASE_URL) return import.meta.env.VITE_API_BASE_URL
    const protocol = location.protocol === "https:" ? "https:" : "http:"
    return `${protocol}//${location.hostname}:9090`
  }

  while (true) {
    if (signal?.aborted) return

    const controller = new AbortController()
    if (signal) {
      signal.addEventListener("abort", () => controller.abort(), { once: true })
    }

    // Expose cancel so useChat can stop us
    setActiveCancel(() => controller.abort())

    try {
      const body = JSON.stringify({
        jsonrpc: "2.0",
        method: "session/subscribe",
        params: { session_id: sessionId },
        id: crypto.randomUUID(),
      })

      const response = await fetch(`${getBaseUrl()}/rpc`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "text/event-stream",
        },
        body,
        signal: controller.signal,
      })

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`)
      }

      if (!response.body) {
        throw new Error("Response body is null")
      }

      retryDelay = 1000
      opts.onReconnect?.()

      const reader = response.body.getReader()
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
                  handleEvent(sessionId, event as StreamEvent)
                }
              } catch {
                // skip unparseable lines
              }
            }
          }
        }
      } finally {
        reader.releaseLock()
      }

      // Stream ended normally (server sent finish), exit reconnect
      return
    } catch {
      if (signal?.aborted || controller.signal.aborted) return

      // Check if session finished while disconnected
      try {
        const session = await rpcClient.sessionLoad(sessionId)
        if (!session.is_streaming) return
      } catch {
        // session load failed, retry
      }

      await sleep(retryDelay)
      retryDelay = Math.min(retryDelay * 2, 30_000)
    } finally {
      clearActiveCancel()
    }
  }
}

// ── React hook ───────────────────────────────────────────────

export function useSessionSubscription(_sessionId: string | undefined) {
  const abortRef = useRef<AbortController | null>(null)
  const queryClient = useQueryClient()

  const stop = useCallback(() => {
    if (abortRef.current) {
      abortRef.current.abort()
      abortRef.current = null
    }
  }, [])

  const start = useCallback(
    (sid: string) => {
      stop()
      const controller = new AbortController()
      abortRef.current = controller

      createSessionSubscription({
        sessionId: sid,
        signal: controller.signal,
        onReconnect: () => {
          queryClient.invalidateQueries({ queryKey: ["session", sid] })
        },
      }).catch(() => {})
    },
    [stop, queryClient],
  )

  useEffect(() => {
    return () => {
      stop()
    }
  }, [stop])

  return { start, stop }
}
