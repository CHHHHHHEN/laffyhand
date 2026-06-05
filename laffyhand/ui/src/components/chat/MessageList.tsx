import { useRef, useEffect, useCallback, useState } from "react"
import { useChatStore } from "@/stores/chat-store"
import { Spinner } from "@/components/ui/Spinner"
import { MessageBubble } from "./MessageBubble"
import { MarkdownContent } from "./MarkdownContent"
import { AiAvatar, ToolCallCard, ReasoningBlock } from "./ChatComponents"
import { SubagentTreeCard } from "./SubagentCard"
import { buildSubagentTree } from "@/lib/subagentTree"

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

interface MessageListProps {
  sessionId: string
  onRetry?: () => void
}

export function MessageList({ sessionId, onRetry }: MessageListProps) {
  const sess = useChatStore((s) => (sessionId ? s.sessions[sessionId] : undefined))
  const messages = sess?.messages ?? []
  const isStreaming = sess?.isStreaming ?? false
  const streamContent = sess?.streamContent ?? ""
  const streamReasoning = sess?.streamReasoning ?? ""
  const streamToolCalls = sess?.streamToolCalls ?? []
  const foregroundSubagents = sess?.foregroundSubagents ?? []
  const error = sess?.error ?? null
  const containerRef = useRef<HTMLDivElement>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  const [isNearBottom, setIsNearBottom] = useState(true)
  const [showScrollBtn, setShowScrollBtn] = useState(false)

  const checkNearBottom = useCallback(() => {
    const el = containerRef.current
    if (!el) return
    const near = el.scrollHeight - el.scrollTop - el.clientHeight < 150
    setIsNearBottom(near)
    setShowScrollBtn(!near)
  }, [])

  useEffect(() => {
    if (isNearBottom) {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" })
    }
  }, [messages, streamContent, streamReasoning, streamToolCalls, isNearBottom])

  const scrollToBottom = () => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" })
    setShowScrollBtn(false)
    setIsNearBottom(true)
  }

  if (messages.length === 0 && !isStreaming && !error) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center text-[var(--text-muted)] select-none">
        <div className="flex flex-col items-center gap-5 max-w-xs text-center">
          <div className="w-14 h-14 rounded-2xl bg-[var(--bg-layer-1)] flex items-center justify-center border border-[var(--border-muted)]">
            <svg className="w-7 h-7 text-[var(--icon-muted)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
            </svg>
          </div>
          <div className="space-y-1">
            <p className="text-sm text-[var(--text-muted)]" style={{ fontWeight: 500 }}>Start a conversation</p>
            <p className="text-sm text-[var(--text-faint)] leading-relaxed">Send a message to begin chatting with your AI agent</p>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="flex-1 relative min-h-0">
      <div
        ref={containerRef}
        onScroll={checkNearBottom}
        className="h-full overflow-y-auto"
      >
        <div className="mx-auto max-w-3xl px-4 py-6">
          {messages.map((msg, i) => {
            const prevMsg = i > 0 ? messages[i - 1] : null
            const showDateSep = prevMsg
              ? new Date(msg.createdAt).toDateString() !== new Date(prevMsg.createdAt).toDateString()
              : true
            return (
              <div key={msg.id}>
                {showDateSep && (
                  <div className="flex items-center gap-3 my-6 select-none">
                    <span className="flex-1 h-px bg-[var(--border-muted)]" />
                    <span className="text-[10px] font-medium text-[var(--text-muted)] uppercase tracking-wider">
                      {formatDateSeparator(new Date(msg.createdAt))}
                    </span>
                    <span className="flex-1 h-px bg-[var(--border-muted)]" />
                  </div>
                )}
                <MessageBubble message={msg} />
              </div>
            )
          })}

          {isStreaming && (
            <div className="flex items-start gap-3 mb-6 animate-[message-in_0.25s_ease-out]">
              <AiAvatar />
              <div className="flex-1 min-w-0 space-y-2">
                {streamReasoning && <ReasoningBlock text={streamReasoning} defaultExpanded />}

                {streamContent ? (
                  <MarkdownContent content={streamContent} />
                ) : (
                  <div className="flex items-center gap-2 py-1">
                    <Spinner size="sm" />
                    <span className="text-sm text-[var(--text-muted)]">Thinking</span>
                  </div>
                )}

                {foregroundSubagents.length > 0 && (() => {
                  const tree = buildSubagentTree(foregroundSubagents)
                  return (
                    <div className="space-y-1.5">
                      {tree.map((node) => (
                        <SubagentTreeCard key={node.item.id} subagent={node.item} tree={tree} />
                      ))}
                    </div>
                  )
                })()}

                {streamToolCalls.length > 0 && (
                  <div className="space-y-1.5">
                    <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-[var(--text-faint)] font-medium">
                      <span>Tool calls</span>
                      <span className="text-[var(--border-strong)]">·</span>
                      <span>{streamToolCalls.length}</span>
                    </div>
                    {streamToolCalls.map((tc) => (
                      <ToolCallCard key={tc.id} toolCall={tc} />
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}

          {error && (
            <div className="flex justify-center mb-6">
              <div className="flex flex-col items-center gap-2.5 bg-[var(--state-danger-bg)] border border-[var(--border-base)] rounded-lg px-5 py-3 text-sm">
                <div className="flex items-center gap-2.5">
                  <svg className="w-4 h-4 shrink-0 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  <span className="text-[var(--state-danger-fg)] text-xs">{error}</span>
                </div>
                {onRetry && (
                  <button
                    onClick={onRetry}
                    className="flex items-center gap-1.5 px-3 py-1 text-xs font-medium rounded-md bg-[var(--state-danger-bg)] text-[var(--state-danger-fg)] hover:bg-[var(--overlay-hover)] transition-colors cursor-pointer border border-[var(--border-base)]"
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
      </div>

      {showScrollBtn && (
        <button
          onClick={scrollToBottom}
          className="absolute bottom-4 right-8 w-8 h-8 rounded-lg bg-[var(--bg-base)] border border-[var(--border-base)] shadow-lg flex items-center justify-center text-[var(--icon-muted)] hover:text-[var(--accent)] hover:border-[var(--accent)] transition-all duration-200 cursor-pointer z-10"
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
