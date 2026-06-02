import { useRef, useEffect, useCallback, useState, useMemo } from "react"
import DOMPurify from "dompurify"
import { useChatStore } from "@/stores/chat-store"
import { Spinner } from "@/components/ui/Spinner"
import { MessageBubble } from "./MessageBubble"
import { AiAvatar, ToolCallCard, ReasoningBlock } from "./ChatComponents"
import { SubagentCard } from "./SubagentCard"

/** Format a date for the date separator */
function formatDateSeparator(date: Date): string {
  const now = new Date()
  const isToday = date.toDateString() === now.toDateString()
  const yesterday = new Date(now)
  yesterday.setDate(yesterday.getDate() - 1)
  const isYesterday = date.toDateString() === yesterday.toDateString()

  if (isToday) return "Today"
  if (isYesterday) return "Yesterday"
  return date.toLocaleDateString([], { weekday: "long", month: "short", day: "numeric", year: date.getFullYear() !== now.getFullYear() ? "numeric" : undefined })
}

/** Format a timestamp as a short time string */
function formatTime(ts: number): string {
  return new Date(ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
}

interface MessageListProps {
  onRetry?: () => void
}

export function MessageList({ onRetry }: MessageListProps) {
  const messages = useChatStore((s) => s.messages)
  const isStreaming = useChatStore((s) => s.isStreaming)
  const streamContent = useChatStore((s) => s.streamContent)
  const streamReasoning = useChatStore((s) => s.streamReasoning)
  const streamToolCalls = useChatStore((s) => s.streamToolCalls)
  const foregroundSubagents = useChatStore((s) => s.foregroundSubagents)
  const error = useChatStore((s) => s.error)
  const resolvePermissionRequest = useChatStore((s) => s.resolvePermissionRequest)
  const containerRef = useRef<HTMLDivElement>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  const [isNearBottom, setIsNearBottom] = useState(true)
  const [showScrollBtn, setShowScrollBtn] = useState(false)

  const handleResolvePermission = useCallback(
    (messageId: string) => resolvePermissionRequest(messageId),
    [resolvePermissionRequest],
  )

  // Check if user is near bottom
  const checkNearBottom = useCallback(() => {
    const el = containerRef.current
    if (!el) return
    const near = el.scrollHeight - el.scrollTop - el.clientHeight < 150
    setIsNearBottom(near)
    setShowScrollBtn(!near)
  }, [])

  // Auto-scroll only when near bottom
  useEffect(() => {
    if (isNearBottom) {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" })
    }
  }, [messages, streamContent, streamReasoning, streamToolCalls, isNearBottom])

  // Scroll to bottom button
  const scrollToBottom = () => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" })
    setShowScrollBtn(false)
    setIsNearBottom(true)
  }

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
    <div className="flex-1 relative min-h-0">
      <div
        ref={containerRef}
        onScroll={checkNearBottom}
        className="h-full overflow-y-auto px-4 py-5 space-y-1"
      >
      {messages.map((msg, i) => {
        // Date separator between messages from different days
        const prevMsg = i > 0 ? messages[i - 1] : null
        const showDateSep = prevMsg
          ? new Date(msg.createdAt).toDateString() !== new Date(prevMsg.createdAt).toDateString()
          : true // show date on first message
        return (
          <div key={msg.id}>
            {showDateSep && (
              <div className="flex items-center gap-3 my-6 select-none">
                <span className="flex-1 h-px bg-gray-200 dark:bg-gray-700/50" />
                <span className="text-[10px] font-medium text-gray-400 dark:text-gray-500 uppercase tracking-wider">
                  {formatDateSeparator(new Date(msg.createdAt))}
                </span>
                <span className="flex-1 h-px bg-gray-200 dark:bg-gray-700/50" />
              </div>
            )}
            <MessageBubble message={msg} onResolvePermission={handleResolvePermission} />
          </div>
        )
      })}

      {/* 流式消息 */}
      {isStreaming && (
        <div className="flex items-start gap-3 mb-5 animate-[message-in_0.25s_ease-out]">
          <AiAvatar />
          <div className="max-w-[75%] min-w-0">
            <div className="bg-gray-100 dark:bg-gray-700/80 text-gray-900 dark:text-gray-100 rounded-2xl rounded-tl-md px-4 py-2.5 shadow-sm">
              {/* 流式推理 — 使用折叠面板 */}
              {streamReasoning && <ReasoningBlock text={streamReasoning} />}

              {/* 流式内容：优先显示 content，若为空则回退显示 reasoning */}
              {streamContent ? (
                <div
                  className="prose prose-sm dark:prose-invert max-w-none"
                  dangerouslySetInnerHTML={{
                    __html: DOMPurify.sanitize(streamContent.replace(/\n/g, "<br>")),
                  }}
                />
              ) : streamReasoning ? (
                <div className="text-sm text-gray-600 dark:text-gray-300 whitespace-pre-wrap leading-relaxed">
                  {streamReasoning}
                </div>
              ) : (
                <div className="flex items-center gap-2.5 py-1">
                  <Spinner size="sm" />
                  <span className="text-sm text-gray-400">Thinking</span>
                </div>
              )}

              {/* 流式 subagents */}
              {foregroundSubagents.length > 0 && (
                <div className="mt-3 space-y-2">
                  {foregroundSubagents.map((sa) => (
                    <SubagentCard key={sa.id} subagent={sa} />
                  ))}
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
          <div className="flex flex-col items-center gap-2 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800/40 rounded-xl px-4 py-2.5 text-sm shadow-sm">
            <div className="flex items-center gap-2">
              <svg className="w-4 h-4 shrink-0 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <span className="text-red-600 dark:text-red-400">{error}</span>
            </div>
            {onRetry && (
              <button
                onClick={onRetry}
                className="flex items-center gap-1.5 px-3 py-1 text-xs font-medium rounded-lg bg-red-100 dark:bg-red-800/30 text-red-700 dark:text-red-300 hover:bg-red-200 dark:hover:bg-red-800/50 transition-colors cursor-pointer"
              >
                <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                </svg>
                Retry
              </button>
            )}
          </div>
        </div>
      )}

      <div ref={bottomRef} />
      </div>

      {/* Scroll to bottom button */}
      {showScrollBtn && (
        <button
          onClick={scrollToBottom}
          className="absolute bottom-4 right-8 w-8 h-8 rounded-full bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 shadow-lg flex items-center justify-center text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300 hover:shadow-xl transition-all duration-200 cursor-pointer z-10 animate-[fade-in_0.15s_ease-out]"
          title="Scroll to bottom"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 14l-7 7m0 0l-7-7m7 7V3" />
          </svg>
        </button>
      )}
    </div>
  )
}
