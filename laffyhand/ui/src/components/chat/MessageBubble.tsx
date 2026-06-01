import { useState, useMemo } from "react"
import { marked } from "marked"
import DOMPurify from "dompurify"
import type { Message } from "@/types/session"
import { AiAvatar, UserAvatar, ReasoningBlock, ToolCallCard, UsageBadge } from "./ChatComponents"
import { rpcClient } from "@/lib/rpc"

interface MessageBubbleProps {
  message: Message
  onResolvePermission?: (messageId: string) => void
}

function MarkdownContent({ content }: { content: string }) {
  const html = useMemo(() => {
    try {
      const raw = marked.parse(content, { async: false }) as string
      return DOMPurify.sanitize(raw)
    } catch (err) {
      console.warn("[MessageBubble] Markdown parse failed:", err)
      return DOMPurify.sanitize(content)
    }
  }, [content])

  return (
    <div
      className="prose prose-sm dark:prose-invert max-w-none break-words"
      dangerouslySetInnerHTML={{ __html: html }}
    />
  )
}

/** 系统消息：居中、低显眼度、默认折叠 */
function SystemMessageBlock({ content }: { content: string }) {
  const [expanded, setExpanded] = useState(false)

  return (
    <div className="flex justify-center mb-5 animate-[fade-in_0.2s_ease-out]">
      <div className="max-w-[85%] min-w-0">
        <div className="bg-gray-50/60 dark:bg-gray-800/30 border border-dashed border-gray-200 dark:border-gray-700/50 rounded-xl px-4 py-2 text-center">
          <button
            onClick={() => setExpanded(!expanded)}
            className="flex items-center justify-center gap-1.5 w-full text-[11px] text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-400 transition-colors cursor-pointer"
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
            <div className="mt-2 pt-2 border-t border-gray-200/50 dark:border-gray-700/30 text-left">
              <pre className="text-[11px] text-gray-500 dark:text-gray-400 whitespace-pre-wrap font-sans leading-relaxed">
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
      <div className="flex justify-center mb-5 animate-[fade-in_0.2s_ease-out]">
        <div className="max-w-[85%] min-w-0 w-full">
          <div className="bg-amber-50 dark:bg-amber-900/15 border border-amber-200 dark:border-amber-700/40 rounded-xl px-4 py-3">
            <div className="text-sm text-amber-900 dark:text-amber-200 mb-3">
              Allow <span className="font-medium">{info.permission}</span> '<span className="font-mono text-xs">{info.pattern}</span>'?
            </div>
            {info.resolved ? (
              <div className="text-xs text-amber-600 dark:text-amber-400 italic">
                Resolved
              </div>
            ) : (
              <div className="flex gap-2 justify-end">
                <button
                  onClick={async () => {
                    await rpcClient.permissionRespond(info.requestId, "deny")
                    onResolvePermission?.(message.id)
                  }}
                  className="px-3 py-1.5 text-xs rounded-lg border border-amber-300 dark:border-amber-600 text-amber-700 dark:text-amber-300 hover:bg-amber-100 dark:hover:bg-amber-800/30 cursor-pointer"
                >
                  Deny
                </button>
                <button
                  onClick={async () => {
                    await rpcClient.permissionRespond(info.requestId, "allow")
                    onResolvePermission?.(message.id)
                  }}
                  className="px-3 py-1.5 text-xs rounded-lg bg-blue-600 text-white hover:bg-blue-700 cursor-pointer"
                >
                  Allow Once
                </button>
                <button
                  onClick={async () => {
                    await rpcClient.permissionRespond(info.requestId, "always")
                    onResolvePermission?.(message.id)
                  }}
                  className="px-3 py-1.5 text-xs rounded-lg bg-green-600 text-white hover:bg-green-700 cursor-pointer"
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
    <div
      className={`flex items-start gap-3 mb-5 ${
        isUser ? "flex-row-reverse" : "flex-row"
      } animate-[message-in_0.25s_ease-out]`}
    >
      {/* 头像 */}
      {isUser ? <UserAvatar /> : <AiAvatar />}

      {/* 消息内容 */}
      <div className={`max-w-[75%] min-w-0 ${isUser ? "items-end" : "items-start"}`}>
        {isUser ? (
          <div className="bg-blue-500 text-white rounded-2xl rounded-tr-md px-4 py-2.5 shadow-sm">
            <p className="whitespace-pre-wrap text-sm leading-relaxed">{message.content}</p>
            {message.createdAt && (
              <div className="mt-1 text-[10px] text-blue-200 text-right">
                {new Date(message.createdAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
              </div>
            )}
          </div>
        ) : (
          <div className="bg-gray-100 dark:bg-gray-700/80 text-gray-900 dark:text-gray-100 rounded-2xl rounded-tl-md px-4 py-2.5 shadow-sm">
            {message.reasoning && <ReasoningBlock text={message.reasoning} />}

            {message.content && <MarkdownContent content={message.content} />}

            {message.toolCalls && message.toolCalls.length > 0 && (
              <div className="mt-3 space-y-1.5">
                <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-gray-400 dark:text-gray-500 font-medium">
                  <span>Tool calls</span>
                  <span className="text-gray-300 dark:text-gray-600">·</span>
                  <span>{message.toolCalls.length}</span>
                </div>
                {message.toolCalls.map((tc) => (
                  <ToolCallCard key={tc.id} toolCall={tc} />
                ))}
              </div>
            )}

            {message.usage && <UsageBadge usage={message.usage} />}

            {message.createdAt && (
              <div className="mt-1 text-[10px] text-gray-400 dark:text-gray-500 text-right">
                {new Date(message.createdAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
