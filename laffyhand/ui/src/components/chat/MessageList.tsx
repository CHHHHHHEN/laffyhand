import { useRef, useEffect } from "react"
import DOMPurify from "dompurify"
import { useChatStore } from "@/stores/chat-store"
import { Spinner } from "@/components/ui/Spinner"
import { MessageBubble } from "./MessageBubble"
import { AiAvatar, ToolCallCard, ReasoningBlock } from "./ChatComponents"

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
      <div className="flex-1 flex flex-col items-center justify-center text-gray-400 dark:text-gray-500 space-y-4 animate-[fade-in_0.3s_ease-out]">
        <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-blue-50 to-indigo-100 dark:from-blue-900/20 dark:to-indigo-900/20 flex items-center justify-center">
          <svg className="w-8 h-8 text-blue-400 dark:text-blue-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
          </svg>
        </div>
        <div className="text-center">
          <p className="text-sm font-medium text-gray-500 dark:text-gray-400">Start a conversation</p>
          <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">Type a message below to begin</p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex-1 overflow-y-auto px-4 py-5 space-y-1">
      {messages.map((msg) => (
        <MessageBubble key={msg.id} message={msg} />
      ))}

      {/* 流式消息 */}
      {isStreaming && (
        <div className="flex items-start gap-3 mb-5 animate-[message-in_0.25s_ease-out]">
          <AiAvatar />
          <div className="max-w-[75%] min-w-0">
            <div className="bg-gray-100 dark:bg-gray-700/80 text-gray-900 dark:text-gray-100 rounded-2xl rounded-tl-md px-4 py-2.5 shadow-sm">
              {/* 流式推理 — 使用折叠面板 */}
              {streamReasoning && <ReasoningBlock text={streamReasoning} />}

              {/* 流式内容 */}
              {streamContent ? (
                <div
                  className="prose prose-sm dark:prose-invert max-w-none"
                  dangerouslySetInnerHTML={{
                    __html: DOMPurify.sanitize(streamContent.replace(/\n/g, "<br>")),
                  }}
                />
              ) : (
                <div className="flex items-center gap-2.5 py-1">
                  <Spinner size="sm" />
                  <span className="text-sm text-gray-400">Thinking</span>
                </div>
              )}

              {/* 流式工具调用 */}
              {streamToolCalls.length > 0 && (
                <div className="mt-3 space-y-1.5">
                  <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-gray-400 dark:text-gray-500 font-medium">
                    <span>Tool calls</span>
                    <span className="text-gray-300 dark:text-gray-600">·</span>
                    <span>{streamToolCalls.length}</span>
                  </div>
                  {streamToolCalls.map((tc) => (
                    <ToolCallCard key={tc.id} toolCall={tc} />
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* 错误提示 */}
      {error && (
        <div className="flex justify-center mb-5 animate-[fade-in_0.2s_ease-out]">
          <div className="flex items-center gap-2 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800/40 text-red-600 dark:text-red-400 rounded-xl px-4 py-2.5 text-sm shadow-sm">
            <svg className="w-4 h-4 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <span>{error}</span>
          </div>
        </div>
      )}

      <div ref={bottomRef} />
    </div>
  )
}
