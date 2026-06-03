import { useCallback, useEffect, useRef } from "react"
import { useParams } from "react-router-dom"
import { useQueryClient } from "@tanstack/react-query"
import { rpcClient } from "@/lib/rpc"
import { useChatStore } from "@/stores/chat-store"
import { useTodoStore } from "@/stores/todo-store"
import type { TodoItem } from "@/types/session"

export function useChat() {
  const queryClient = useQueryClient()
  const abortRef = useRef<AbortController | null>(null)
  const leftoverSteerRef = useRef<string | null>(null)
  const { sessionId: urlSessionId } = useParams()
  const sessionIdRef = useRef(urlSessionId)
  sessionIdRef.current = urlSessionId

  // Refresh session list and TODO list when streaming ends
  const isStreaming = useChatStore((s) => s.isStreaming)
  const prevStreamingRef = useRef(isStreaming)
  useEffect(() => {
    const wasStreaming = prevStreamingRef.current
    prevStreamingRef.current = isStreaming
    if (wasStreaming && !isStreaming) {
      queryClient.invalidateQueries({ queryKey: ["sessions"] })
      if (urlSessionId) {
        rpcClient.todoList(urlSessionId).then((result) => {
          const tasks: TodoItem[] = result.tasks.map((t) => ({
            id: t.id,
            sessionId: t.sessionId,
            content: t.content,
            status: t.status as TodoItem["status"],
            priority: t.priority as TodoItem["priority"],
            dependsOn: t.dependsOn,
            blockedBy: t.blockedBy,
            createdAt: t.createdAt,
            updatedAt: t.updatedAt,
            completedAt: t.completedAt,
            taskToolId: t.taskToolId,
          }))
          useTodoStore.getState().setTasks(tasks)
        }).catch(() => {})
      }
    }
  }, [isStreaming, queryClient, urlSessionId])

  const _cancelAndFinalize = useCallback(async () => {
    if (abortRef.current) {
      abortRef.current.abort()
      abortRef.current = null
    }
    try {
      await rpcClient.cancelStream()
    } catch (err) {
      console.warn("cancelStream failed", err)
    }
    const state = useChatStore.getState()
    if (!state.isStreaming) return false
    if (state.streamContent || state.streamToolCalls.length > 0) {
      state.finalizeMessage()
    } else {
      state.setError("Stream cancelled")
    }
    return true
  }, [])

  const sendMessage = useCallback(
    async (content: string, bypassBusyCheck = false) => {
      const chatStore = useChatStore.getState()

      if (!content.trim()) return
      if (!bypassBusyCheck && chatStore.isStreaming) return

      chatStore.addUserMessage(content)
      chatStore.startStreaming()

      const abortController = new AbortController()
      abortRef.current = abortController
      const sessionAtSend = sessionIdRef.current

      try {
        await rpcClient.chatStream(
          content,
          {
            onEvent: (event) => {
              const store = useChatStore.getState()
              if (!store.isStreaming && event.type !== "step-start") return
              switch (event.type) {
                case "step-start":
                  if (!store.isStreaming) {
                    store.startStreaming()
                  }
                  break
                case "text-delta":
                  if (event.text) {
                    store.appendContent(event.text)
                  }
                  break
                case "reasoning-delta":
                  if (event.text) {
                    store.setReasoning(event.text)
                  }
                  break
                case "tool-call": {
                  let args: Record<string, unknown> = {}
                  try {
                    args = JSON.parse(event.input)
                  } catch {
                    args = {}
                  }
                  store.addToolCall({
                    id: event.id,
                    name: event.name,
                    arguments: args,
                  })
                  break
                }
                case "tool-result":
                  store.updateToolCallStatus(event.id, "completed", event.result)
                  break
                case "tool-error":
                  store.updateToolCallStatus(event.id, "error", event.message, true)
                  break
                case "step-finish":
                  if (event.reason === "tool_calls") {
                    const stepUsage = event.usage
                      ? {
                          inputTokens: event.usage.input_tokens,
                          outputTokens: event.usage.output_tokens,
                        }
                      : undefined
                    store.finalizeMessage(stepUsage)
                  }
                  break
                case "finish": {
                  const usage = event.usage
                    ? {
                        inputTokens: event.usage.input_tokens,
                        outputTokens: event.usage.output_tokens,
                      }
                    : undefined
                  store.finalizeMessage(usage, event.session_usage ?? null)

                  if (event.leftover_steer) {
                    leftoverSteerRef.current = event.leftover_steer
                  }
                  break
                }
                case "permission-request":
                  store.addPermissionRequest({
                    requestId: event.request_id,
                    permission: event.permission,
                    pattern: event.pattern,
                  })
                  break
                case "subagent-start":
                  store.startSubagent(event)
                  break
                case "subagent-delta":
                  store.updateSubagent(event.id, event)
                  break
                case "subagent-end":
                  store.endSubagent(event.id, event)
                  break
                case "provider-error":
                  store.setError(event.message)
                  break
              }
            },
            onError: (error) => {
              if (abortController.signal.aborted) return
              if (sessionIdRef.current !== sessionAtSend) return
              useChatStore.getState().setError(error.message)
            },
            onComplete: () => {
              // handled in finish event
            },
          },
          abortController.signal,
          urlSessionId,
        )
      } catch (err) {
        if (abortController.signal.aborted) return
        if (sessionIdRef.current !== sessionAtSend) return
        const store = useChatStore.getState()
        store.setError(
          err instanceof Error ? err.message : "Unknown error",
        )
      }

      if (sessionIdRef.current !== sessionAtSend) return

      if (leftoverSteerRef.current) {
        const steer = leftoverSteerRef.current
        leftoverSteerRef.current = null
        await sendMessage(steer, true)
        return
      }

      if (useChatStore.getState().hasPendingMessages()) {
        const next = useChatStore.getState().dequeueMessage()
        if (next) {
          await sendMessage(next, true)
        }
      }
    },
    [urlSessionId],
  )

  const interruptMessage = useCallback(
    async (content: string) => {
      if (!content.trim()) return
      const store = useChatStore.getState()
      if (!store.isStreaming) {
        await sendMessage(content)
        return
      }

      await _cancelAndFinalize()
      await sendMessage(content, true)
    },
    [sendMessage, _cancelAndFinalize],
  )

  const steerMessage = useCallback(
    async (content: string) => {
      const store = useChatStore.getState()
      if (!content.trim()) return
      if (!store.isStreaming) return

      try {
        await rpcClient.steerMessage(content, urlSessionId)
      } catch (err) {
        const store = useChatStore.getState()
        store.setError(err instanceof Error ? err.message : "Steer failed")
      }
    },
    [urlSessionId],
  )

  const queueMessage = useCallback(
    async (content: string) => {
      if (!content.trim()) return
      useChatStore.getState().enqueueMessage(content)
    },
    [],
  )

  const cancelStream = useCallback(async () => {
    await _cancelAndFinalize()
  }, [_cancelAndFinalize])

  return { sendMessage, interruptMessage, steerMessage, queueMessage, cancelStream }
}
