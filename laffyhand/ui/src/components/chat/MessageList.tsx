import { useRef, useEffect } from "react"
import { useChatStore } from "@/stores/chat-store"
import { Spinner } from "@/components/ui/Spinner"
import { MessageBubble } from "./MessageBubble"

export function MessageList() {
  const messages = useChatStore((s) => s.messages)
  const isStreaming = useChatStore((s) => s.isStreaming)
  const streamContent = useChatStore((s) => s.streamContent)
  const streamReasoning = useChatStore((s) => s.streamReasoning)
  const error = useChatStore((s) => s.error)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages, streamContent, streamReasoning])

  if (messages.length === 0 && !isStreaming && !error) {
    return (
      <div className="flex-1 flex items-center justify-center text-gray-400 dark:text-gray-500">
        <p>Send a message to start chatting</p>
      </div>
    )
  }

  return (
    <div className="flex-1 overflow-y-auto px-4 py-4">
      {messages.map((msg) => (
        <MessageBubble key={msg.id} message={msg} />
      ))}

      {isStreaming && (
        <div className="flex justify-start mb-4">
          <div className="max-w-[80%] rounded-lg px-4 py-2 bg-gray-100 dark:bg-gray-800">
            {streamReasoning && (
              <div className="text-xs text-gray-400 dark:text-gray-500 mb-1 italic">
                {streamReasoning}
              </div>
            )}
            {streamContent ? (
              <div
                className="prose prose-sm dark:prose-invert max-w-none"
                dangerouslySetInnerHTML={{
                  __html: streamContent.replace(/\n/g, "<br>"),
                }}
              />
            ) : (
              <div className="flex items-center gap-2">
                <Spinner size="sm" />
                <span className="text-sm text-gray-500">Thinking...</span>
              </div>
            )}
          </div>
        </div>
      )}

      {error && (
        <div className="flex justify-center mb-4">
          <div className="bg-red-50 dark:bg-red-900/30 text-red-600 dark:text-red-400 rounded-lg px-4 py-2 text-sm">
            {error}
          </div>
        </div>
      )}

      <div ref={bottomRef} />
    </div>
  )
}
