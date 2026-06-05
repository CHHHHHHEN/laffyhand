import { useState, useMemo } from "react"
import type { Message } from "@/types/session"
import { AiAvatar, UserAvatar, ReasoningBlock, ToolCallCard, UsageBadge } from "./ChatComponents"
import { MarkdownContent } from "./MarkdownContent"
import { buildSubagentTree } from "@/lib/subagentTree"
import { SubagentTreeCard } from "./SubagentCard"

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

function SubagentTreeSection({ subagents }: { subagents: Message["subagents"] }) {
  const tree = useMemo(() => buildSubagentTree(subagents ?? []), [subagents])
  if (tree.length === 0) return null
  return (
    <div className="space-y-1.5">
      <div className="flex items-center gap-1.5 text-[11px] uppercase tracking-wider text-[var(--text-faint)] font-medium">
        <span>Sub-agents</span>
        <span className="text-[var(--border-strong)]">·</span>
        <span>{subagents?.length}</span>
      </div>
      {tree.map((node) => (
        <SubagentTreeCard key={node.item.id} subagent={node.item} tree={tree} />
      ))}
    </div>
  )
}

export function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === "user"

  if (message.role === "system") {
    return <SystemMessageBlock content={message.content} />
  }

  // Permission requests are rendered via PermissionBanner at the top of the chat area
  if (message.role === "permission-request") {
    return null
  }

  return (
    <div className="flex items-start gap-3 mb-6 animate-[message-in_0.25s_ease-out]">
      {isUser ? <UserAvatar /> : <AiAvatar />}

      <div className="flex-1 min-w-0">
        {isUser ? (
          <div className="bg-[var(--accent-muted)] rounded-lg px-4 py-2.5 border border-[var(--border-muted)] group relative transition-colors">
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
                <div className="flex items-center gap-1.5 text-[11px] uppercase tracking-wider text-[var(--text-faint)] font-medium">
                  <span>Tool calls</span>
                  <span className="text-[var(--border-strong)]">·</span>
                  <span>{message.toolCalls.length}</span>
                </div>
                {message.toolCalls.map((tc) => (
                  <ToolCallCard key={tc.id} toolCall={tc} />
                ))}
              </div>
            )}

            {message.subagents && message.subagents.length > 0 && (
              <SubagentTreeSection subagents={message.subagents} />
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
