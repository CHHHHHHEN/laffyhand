import { useRef, useEffect } from "react"
import DOMPurify from "dompurify"
import { useChatStore } from "@/stores/chat-store"
import { Spinner } from "@/components/ui/Spinner"
import { MessageBubble } from "./MessageBubble"

export function MessageList() {
  const messages = useChatStore((s) => s.messages)
  const isStreaming = useChatStore((s) => s.isStreaming)
  const streamContent = useChatStore((s) => s.streamContent)
  const streamReasoning = useChatStore((s) => s.streamReasoning)
  const streamToolCalls = useChatStore((s) => s.streamToolCalls)
  const error = useChatStore((s) => s.error)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages, streamContent, streamReasoning, streamToolCalls])

  if (messages.length === 0 && !isStreaming && !error) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center text-gray-400 dark:text-gray-500 space-y-3">
        <svg className="w-12 h-12" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
        </svg>
        <p className="text-sm">Send a message to start chatting</p>
      </div>
    )
  }

  return (
    <div className="flex-1 overflow-y-auto px-4 py-4">
      {messages.map((msg) => (
        <MessageBubble key={msg.id} message={msg} />
      ))}

      {isStreaming && (
        <div className="flex justify-start mb-6">
          <div className="max-w-[80%] rounded-lg px-4 py-2 bg-gray-200 dark:bg-gray-700 shadow-sm">
            {streamReasoning && (
              <div className="text-xs text-gray-400 dark:text-gray-500 mb-2 italic border-l-2 border-gray-300 dark:border-gray-600 pl-3 whitespace-pre-wrap">
                {streamReasoning}
              </div>
            )}
            {streamContent ? (
              <div
                className="prose prose-sm dark:prose-invert max-w-none"
                dangerouslySetInnerHTML={{
                  __html: DOMPurify.sanitize(streamContent.replace(/\n/g, "<br>")),
                }}
              />
            ) : (
              <div className="flex items-center gap-2">
                <Spinner size="sm" />
                <span className="text-sm text-gray-500">Thinking...</span>
              </div>
            )}
            {streamToolCalls.length > 0 && (
              <div className="mt-2 border-t border-gray-300 dark:border-gray-600 pt-2">
                <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">
                  Tool calls:
                </p>
                {streamToolCalls.map((tc) => (
                  <div
                    key={tc.id}
                    className="bg-gray-100 dark:bg-gray-800 rounded-md px-3 py-2 mb-2 text-xs font-mono border border-gray-200 dark:border-gray-700"
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-semibold text-blue-600 dark:text-blue-400">
                        {tc.name}
                      </span>
                      <span className="text-gray-400 dark:text-gray-500 text-xs">
                        {tc.id.slice(0, 8)}
                      </span>
                    </div>
                    <pre className="mt-1 text-gray-600 dark:text-gray-300 whitespace-pre-wrap break-all">
                      {JSON.stringify(tc.arguments, null, 2)}
                    </pre>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {error && (
        <div className="flex justify-center mb-6">
          <div className="bg-red-50 dark:bg-red-900/30 text-red-600 dark:text-red-400 rounded-lg px-4 py-2 text-sm">
            {error}
          </div>
        </div>
      )}

      <div ref={bottomRef} />
    </div>
  )
}
