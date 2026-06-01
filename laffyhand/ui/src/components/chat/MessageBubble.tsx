import { useMemo } from "react"
import { marked } from "marked"
import DOMPurify from "dompurify"
import type { Message } from "@/types/session"
import { AiAvatar, UserAvatar, ReasoningBlock, ToolCallCard, UsageBadge } from "./ChatComponents"

interface MessageBubbleProps {
  message: Message
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

export function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === "user"

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
          <div className="bg-blue-600 text-white rounded-2xl rounded-tr-md px-4 py-2.5 shadow-sm">
            <p className="whitespace-pre-wrap text-sm leading-relaxed">{message.content}</p>
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
          </div>
        )}
      </div>
    </div>
  )
}
