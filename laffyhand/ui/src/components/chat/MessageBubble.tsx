import { useMemo } from "react"
import { marked } from "marked"
import DOMPurify from "dompurify"
import type { Message } from "@/types/session"

interface MessageBubbleProps {
  message: Message
}

function MarkdownContent({ content }: { content: string }) {
  const html = useMemo(() => {
    try {
      const raw = marked.parse(content, { async: false }) as string
      return DOMPurify.sanitize(raw)
    } catch {
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
    <div className={`flex ${isUser ? "justify-end" : "justify-start"} mb-6`}>
      <div
        className={`max-w-[80%] rounded-lg px-4 py-2 shadow-sm ${
          isUser
            ? "bg-blue-600 text-white"
            : "bg-gray-200 dark:bg-gray-700 text-gray-900 dark:text-gray-100"
        }`}
      >
        {isUser ? (
          <p className="whitespace-pre-wrap">{message.content}</p>
        ) : (
          <>
            {message.reasoning && (
              <div className="text-xs text-gray-400 dark:text-gray-500 mb-2 italic border-l-2 border-gray-300 dark:border-gray-600 pl-2">
                {message.reasoning}
              </div>
            )}
            {message.content && <MarkdownContent content={message.content} />}
            {message.toolCalls && message.toolCalls.length > 0 && (
              <div className="mt-2 border-t border-gray-300 dark:border-gray-600 pt-2">
                <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">
                  Tool calls:
                </p>
                {message.toolCalls.map((tc) => (
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
