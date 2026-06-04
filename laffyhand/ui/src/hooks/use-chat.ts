import { useCallback, useRef } from "react"
import { useParams } from "react-router-dom"
import { useQueryClient } from "@tanstack/react-query"
import { rpcClient } from "@/lib/rpc"
import { useChatStore } from "@/stores/chat-store"
import { useTodoStore } from "@/stores/todo-store"
import { useUiStore } from "@/stores/ui-store"
import type { TodoItem } from "@/types/session"
import type { SessionUsage } from "@/types/rpc"

function refreshTodo(sessionId: string) {
  rpcClient.todoList(sessionId).then((result) => {
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

export function useChat() {
  const queryClient = useQueryClient()
  const abortRef = useRef<AbortController | null>(null)
  const leftoverSteerRef = useRef<string | null>(null)
  const { sessionId: urlSessionId } = useParams()
  const sessionIdRef = useRef(urlSessionId)
  sessionIdRef.current = urlSessionId

  const _cancelAndFinalize = useCallback(async (sessionId: string) => {
    if (abortRef.current) {
      abortRef.current.abort()
      abortRef.current = null
    }
    try {
      await rpcClient.cancelStream()
    } catch (err) {
      console.warn("cancelStream failed", err)
    }
    const store = useChatStore.getState()
    const sess = store.sessions[sessionId]
    if (!sess || !sess.isStreaming) return false
    if (sess.streamContent || sess.streamToolCalls.length > 0) {
      store.finalizeMessage(sessionId)
    } else {
      store.setError(sessionId, "Stream cancelled")
    }
    return true
  }, [])

  const sendMessage = useCallback(
    async (content: string, bypassBusyCheck = false, skipAddUser = false) => {
      const chatStore = useChatStore.getState()
      const sessionId = sessionIdRef.current
      if (!sessionId) return
      if (!content.trim()) return

      // Ensure session state exists in the store
      chatStore.addSession(sessionId)

      const sess = chatStore.sessions[sessionId]
      if (!bypassBusyCheck && sess?.isStreaming) return

      if (!skipAddUser) {
        chatStore.addUserMessage(sessionId, content)
      }
      chatStore.startStreaming(sessionId)

      const abortController = new AbortController()
      abortRef.current = abortController
      const sessionAtSend = sessionId

      try {
        await rpcClient.chatStream(
          content,
          {
            onEvent: (event) => {
              const store = useChatStore.getState()
              const currentSess = store.sessions[sessionId]
              if (!currentSess?.isStreaming && event.type !== "step-start") return
              switch (event.type) {
                case "step-start":
                  if (!currentSess?.isStreaming) {
                    store.startStreaming(sessionId)
                  }
                  break
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
                  let args: Record<string, unknown> = {}
                  try {
                    args = JSON.parse(event.input)
                  } catch {
                    args = {}
                  }
                  store.addToolCall(sessionId, {
                    id: event.id,
                    name: event.name,
                    arguments: args,
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
                case "finish": {
                  const usage = event.usage
                    ? {
                        inputTokens: event.usage.input_tokens,
                        outputTokens: event.usage.output_tokens,
                        reasoningTokens: event.usage.reasoning_tokens,
                      }
                    : undefined
                  store.finalizeMessage(sessionId, usage, event.session_usage ?? null)

                  if (event.leftover_steer) {
                    leftoverSteerRef.current = event.leftover_steer
                  }

                  queryClient.invalidateQueries({ queryKey: ["sessions"] })
                  refreshTodo(sessionId)
                  break
                }
                case "usage-update":
                  store.updateSessionUsage(sessionId, event.session_usage as SessionUsage)
                  break
                case "todo-update":
                  refreshTodo(sessionId)
                  if (!useUiStore.getState().todoPanelOpen) {
                    useUiStore.getState().setTodoPanelOpen(true)
                  }
                  break
                case "permission-request":
                  store.addPermissionRequest(sessionId, {
                    requestId: event.request_id,
                    permission: event.permission,
                    pattern: event.pattern,
                  })
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
                case "provider-error":
                  store.setError(sessionId, event.message)
                  break
              }
            },
            onError: (error) => {
              if (abortController.signal.aborted) return
              if (sessionIdRef.current !== sessionAtSend) return
              useChatStore.getState().setError(sessionId, error.message)
              queryClient.invalidateQueries({ queryKey: ["sessions"] })
              refreshTodo(sessionId)
            },
            onComplete: () => {},
          },
          abortController.signal,
          urlSessionId,
        )
      } catch (err) {
        if (abortController.signal.aborted) return
        if (sessionIdRef.current !== sessionAtSend) return
        useChatStore.getState().setError(
          sessionId,
          err instanceof Error ? err.message : "Unknown error",
        )
        queryClient.invalidateQueries({ queryKey: ["sessions"] })
        refreshTodo(sessionId)
      }

      if (sessionIdRef.current !== sessionAtSend) return

      if (leftoverSteerRef.current) {
        const steer = leftoverSteerRef.current
        leftoverSteerRef.current = null
        // skipAddUser=true because steerMessage() already added the message to the store
        await sendMessage(steer, true, true)
        return
      }

      if (useChatStore.getState().hasPendingMessages(sessionId)) {
        const next = useChatStore.getState().dequeueMessage(sessionId)
        if (next) {
          await sendMessage(next, true)
        }
      }
    },
    [urlSessionId, queryClient],
  )

  const interruptMessage = useCallback(
    async (content: string) => {
      const sessionId = sessionIdRef.current
      if (!sessionId) return
      if (!content.trim()) return
      const store = useChatStore.getState()
      const sess = store.sessions[sessionId]
      if (!sess?.isStreaming) {
        await sendMessage(content)
        return
      }

      await _cancelAndFinalize(sessionId)
      await sendMessage(content, true)
    },
    [sendMessage, _cancelAndFinalize],
  )

  const steerMessage = useCallback(
    async (content: string) => {
      const sessionId = sessionIdRef.current
      if (!sessionId) return
      if (!content.trim()) return
      const sess = useChatStore.getState().sessions[sessionId]
      if (!sess?.isStreaming) return

      // Add the steer message to chat history immediately so the user
      // sees their input even while the existing stream continues.
      useChatStore.getState().addUserMessage(sessionId, content)

      try {
        await rpcClient.steerMessage(content, urlSessionId)
      } catch (err) {
        useChatStore.getState().setError(
          sessionId,
          err instanceof Error ? err.message : "Steer failed",
        )
      }
    },
    [urlSessionId],
  )

  const queueMessage = useCallback(
    async (content: string) => {
      const sessionId = sessionIdRef.current
      if (!sessionId) return
      if (!content.trim()) return
      useChatStore.getState().enqueueMessage(sessionId, content)
    },
    [],
  )

  const cancelStream = useCallback(async () => {
    const sessionId = sessionIdRef.current
    if (!sessionId) return
    await _cancelAndFinalize(sessionId)
  }, [_cancelAndFinalize])

  return { sendMessage, interruptMessage, steerMessage, queueMessage, cancelStream }
}
