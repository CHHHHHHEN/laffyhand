import { useMemo } from "react"
import { marked } from "marked"
import type { Message } from "@/types/session"

interface MessageBubbleProps {
  message: Message
}

function MarkdownContent({ content }: { content: string }) {
  const html = useMemo(() => {
    try {
      return marked.parse(content, { async: false }) as string
    } catch {
      return content
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
    <div className={`flex ${isUser ? "justify-end" : "justify-start"} mb-4`}>
      <div
        className={`max-w-[80%] rounded-lg px-4 py-2 ${
          isUser
            ? "bg-blue-600 text-white"
            : "bg-gray-100 dark:bg-gray-800 text-gray-900 dark:text-gray-100"
        }`}
      >
        {isUser ? (
          <p className="whitespace-pre-wrap">{message.content}</p>
        ) : (
          <>
            {message.content && <MarkdownContent content={message.content} />}
            {message.toolCalls && message.toolCalls.length > 0 && (
              <div className="mt-2 border-t border-gray-300 dark:border-gray-600 pt-2">
                <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">
                  Tool calls:
                </p>
                {message.toolCalls.map((tc) => (
                  <div
                    key={tc.id}
                    className="bg-gray-200 dark:bg-gray-700 rounded px-2 py-1 mb-1 text-xs font-mono"
                  >
                    {tc.name}({JSON.stringify(tc.arguments)})
                  </div>
                ))}
              </div>
            )}
            {message.usage && (
              <div className="mt-1 text-xs text-gray-400 dark:text-gray-500">
                ↑{message.usage.inputTokens} ↓{message.usage.outputTokens}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
