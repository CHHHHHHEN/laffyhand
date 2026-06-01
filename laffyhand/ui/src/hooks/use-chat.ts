import { useCallback, useRef } from "react"
import { useParams } from "react-router-dom"
import { rpcClient } from "@/lib/rpc"
import { useChatStore } from "@/stores/chat-store"

export function useChat() {
  const abortRef = useRef<AbortController | null>(null)
  const { sessionId: urlSessionId } = useParams()

  const sendMessage = useCallback(
    async (content: string) => {
      const chatStore = useChatStore.getState()

      if (!content.trim()) return
      if (chatStore.isStreaming) return

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
                case "content":
                  store.appendContent(event.data)
                  break
                case "reasoning":
                  store.setReasoning(event.data)
                  break
                case "tool_calls":
                  try {
                    const calls = JSON.parse(event.data)
                    if (Array.isArray(calls)) {
                      for (const call of calls) {
                        let args: Record<string, unknown> = {}
                        try {
                          args =
                            typeof call.arguments === "string"
                              ? JSON.parse(call.arguments)
                              : (call.arguments ?? {})
                        } catch {
                          args = {}
                        }
                        store.addToolCall({
                          id: call.id ?? "unknown",
                          name: call.name ?? "unknown",
                          arguments: args,
                        })
                      }
                    }
                  } catch {
                    // skip unparseable tool calls
                  }
                  break
                case "tool_result":
                  try {
                    const result = JSON.parse(event.data)
                    store.addToolResult({
                      id: result.id ?? "unknown",
                      name: result.name ?? "unknown",
                      result: result.result ?? event.data,
                      isError: result.isError,
                    })
                  } catch {
                    // skip unparseable
                  }
                  break
                case "error":
                  store.setError(event.data)
                  break
                case "finish": {
                  const usage = event.usage
                    ? {
                        inputTokens: event.usage.input_tokens,
                        outputTokens: event.usage.output_tokens,
                      }
                    : undefined
                  store.finalizeMessage(usage, event.session_usage ?? null)
                  break
                }
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
    },
    [urlSessionId],
  )

  const steerMessage = useCallback(
    async (content: string) => {
      const store = useChatStore.getState()
      if (!content.trim()) return
      if (!store.isStreaming) return

      store.addUserMessage(content)
      try {
        await rpcClient.steerMessage(content, urlSessionId)
      } catch {
        // best effort
      }
    },
    [urlSessionId],
  )

  const cancelStream = useCallback(async () => {
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
    if (!state.isStreaming) return
    if (state.streamContent || state.streamToolCalls.length > 0) {
      state.finalizeMessage()
    } else {
      state.setError("Stream cancelled")
    }
  }, [])

  return { sendMessage, steerMessage, cancelStream }
}
