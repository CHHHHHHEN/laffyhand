import { useState } from "react"
import type { Message } from "@/types/session"
import { AiAvatar, UserAvatar, ReasoningBlock, ToolCallCard, UsageBadge } from "./ChatComponents"
import { MarkdownContent } from "./MarkdownContent"
import { rpcClient } from "@/lib/rpc"

function CopyButton({ content }: { content: string }) {
  const [copied, setCopied] = useState(false)

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(content)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      // Clipboard not available
    }
  }

  return (
    <button
      onClick={handleCopy}
      className="opacity-0 group-hover:opacity-100 transition-opacity duration-150 absolute top-1 right-1 p-1 rounded text-[var(--text-faint)] hover:text-[var(--text-base)] hover:bg-[var(--overlay-hover)] cursor-pointer z-10"
      title="Copy message"
    >
      {copied ? (
        <span className="text-[10px] font-medium">Copied!</span>
      ) : (
        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
        </svg>
      )}
    </button>
  )
}

interface MessageBubbleProps {
  message: Message
  onResolvePermission?: (messageId: string) => void
}

function SystemMessageBlock({ content }: { content: string }) {
  const [expanded, setExpanded] = useState(false)

  return (
    <div className="flex justify-center mb-6">
      <div className="max-w-[85%] min-w-0">
        <div className="bg-[var(--bg-layer-1)] border border-[var(--border-base)] rounded-lg px-4 py-2 text-center">
          <button
            onClick={() => setExpanded(!expanded)}
            className="flex items-center justify-center gap-1.5 w-full text-[11px] text-[var(--text-muted)] hover:text-[var(--text-base)] transition-colors cursor-pointer select-none"
          >
            <svg
              className={`w-3 h-3 transition-transform duration-150 ${expanded ? "rotate-90" : ""}`}
              fill="none" stroke="currentColor" viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
            </svg>
            <span>System prompt</span>
          </button>
          {expanded && (
            <div className="mt-2 pt-2 border-t border-[var(--border-muted)] text-left">
              <pre className="text-[11px] text-[var(--text-muted)] whitespace-pre-wrap font-sans leading-relaxed">
                {content}
              </pre>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export function MessageBubble({ message, onResolvePermission }: MessageBubbleProps) {
  const isUser = message.role === "user"

  if (message.role === "system") {
    return <SystemMessageBlock content={message.content} />
  }

  if (message.role === "permission-request" && message.permissionInfo) {
    const info = message.permissionInfo
    return (
      <div className="flex justify-center mb-6">
        <div className="max-w-[85%] min-w-0 w-full">
          <div className="bg-[var(--state-warning-bg)] border border-[var(--border-base)] rounded-lg px-4 py-3">
            <div className="text-sm text-[var(--state-warning-fg)] mb-3 flex items-center gap-1.5">
              <svg className="w-4 h-4 shrink-0 text-amber-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z" />
              </svg>
              <span>Allow <span className="font-semibold">{info.permission}</span> '<span className="font-mono text-xs">{info.pattern}</span>'?</span>
            </div>
            {info.resolved ? (
              <div className="text-xs text-[var(--state-warning-fg)] italic">
                Resolved
              </div>
            ) : (
              <div className="flex gap-2 justify-end">
                <button
                  onClick={async () => {
                    await rpcClient.permissionRespond(info.requestId, "deny")
                    onResolvePermission?.(message.id)
                  }}
                  className="px-3 py-1.5 text-xs rounded-lg border border-[var(--border-strong)] text-[var(--text-muted)] hover:bg-[var(--overlay-hover)] transition-colors cursor-pointer"
                >
                  Deny
                </button>
                <button
                  onClick={async () => {
                    await rpcClient.permissionRespond(info.requestId, "allow")
                    onResolvePermission?.(message.id)
                  }}
                  className="px-3 py-1.5 text-xs rounded-lg bg-[var(--accent)] text-white hover:opacity-90 transition-opacity cursor-pointer"
                >
                  Allow Once
                </button>
                <button
                  onClick={async () => {
                    await rpcClient.permissionRespond(info.requestId, "always")
                    onResolvePermission?.(message.id)
                  }}
                  className="px-3 py-1.5 text-xs rounded-lg bg-[var(--state-success-fg)] text-white hover:opacity-90 transition-opacity cursor-pointer"
                >
                  Always Allow
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="flex items-start gap-3 mb-6 animate-[message-in_0.25s_ease-out]">
      {isUser ? <UserAvatar /> : <AiAvatar />}

      <div className="flex-1 min-w-0">
        {isUser ? (
          <div className="bg-[var(--bg-layer-1)] rounded-lg px-4 py-2.5 border border-[var(--border-muted)] group relative">
            <CopyButton content={message.content} />
            <p className="whitespace-pre-wrap text-sm text-[var(--text-base)] leading-relaxed">{message.content}</p>
            {message.createdAt && (
              <div className="mt-1 text-[10px] text-[var(--text-faint)]">
                {new Date(message.createdAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
              </div>
            )}
          </div>
        ) : (
          <div className="space-y-2 group relative">
            <CopyButton content={message.content} />
            {message.reasoning && <ReasoningBlock text={message.reasoning} />}

            {message.content && (
              <MarkdownContent content={message.content} />
            )}

            {message.toolCalls && message.toolCalls.length > 0 && (
              <div className="space-y-1.5">
                <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-[var(--text-faint)] font-medium">
                  <span>Tool calls</span>
                  <span className="text-[var(--border-strong)]">·</span>
                  <span>{message.toolCalls.length}</span>
                </div>
                {message.toolCalls.map((tc) => (
                  <ToolCallCard key={tc.id} toolCall={tc} />
                ))}
              </div>
            )}

            {(message.usage || message.createdAt) && (
              <div className="flex items-center justify-between gap-2 pt-1">
                {message.usage && <UsageBadge usage={message.usage} />}
                {message.createdAt && (
                  <div className="text-[10px] text-[var(--text-faint)]">
                    {new Date(message.createdAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
