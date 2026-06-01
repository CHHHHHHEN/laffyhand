import { useCallback, useRef } from "react"
import { useParams } from "react-router-dom"
import { rpcClient } from "@/lib/rpc"
import { useChatStore } from "@/stores/chat-store"

export function useChat() {
  const abortRef = useRef<AbortController | null>(null)
  const leftoverSteerRef = useRef<string | null>(null)
  const { sessionId: urlSessionId } = useParams()

  const _cancelAndFinalize = useCallback(async () => {
    if (abortRef.current) {
      abortRef.current.abort()
      abortRef.current = null
    }
    try {
      await rpcClient.cancelStream()
    } catch {
      // best effort
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

      try {
        await rpcClient.chatStream(
          content,
          {
            onEvent: (event) => {
              const store = useChatStore.getState()
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
                  store.addToolResult({
                    id: event.id,
                    name: event.name,
                    result: event.result,
                    isError: event.error,
                  })
                  break
                case "tool-error":
                  store.addToolResult({
                    id: event.id,
                    name: event.name,
                    result: event.message,
                    isError: true,
                  })
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
                case "provider-error":
                  store.setError(event.message)
                  break
              }
            },
            onError: (error) => {
              if (abortController.signal.aborted) return
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
        const store = useChatStore.getState()
        store.setError(
          err instanceof Error ? err.message : "Unknown error",
        )
      }

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
      } catch {
        // best effort
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
