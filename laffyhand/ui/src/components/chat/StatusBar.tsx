import { useChatStore } from "@/stores/chat-store"

function formatTokens(n: number): string {
  if (n < 1000) return `${n}`
  const k = (n / 1000).toFixed(1).replace(/\.0$/, "")
  return `${k}k`
}

export function StatusBar() {
  const isStreaming = useChatStore((s) => s.isStreaming)
  const model = useChatStore((s) => s.model)
  const sessionUsage = useChatStore((s) => s.sessionUsage)

  if (!model && !sessionUsage) return null

  const totalTokens = sessionUsage
    ? sessionUsage.total_input + sessionUsage.total_output
    : 0
  const ctxSize = sessionUsage?.context_size ?? 0

  return (
    <div className="flex items-center gap-3 px-4 py-1.5 text-xs text-gray-400 dark:text-gray-500 border-b border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/50 shrink-0">
      {model && (
        <span className="font-mono" title="Model">
          {model}
        </span>
      )}
      {sessionUsage && (
        <>
          <span className="text-gray-300 dark:text-gray-600">|</span>
          <span title="Total tokens used">
            {formatTokens(totalTokens)} / {formatTokens(ctxSize)} tokens
          </span>
          <span className="text-gray-300 dark:text-gray-600">|</span>
          <span title="Breakdown">
            ↑{formatTokens(sessionUsage.total_input)}
            {' '}
            ↓{formatTokens(sessionUsage.total_output)}
          </span>
          {sessionUsage.total_reasoning > 0 && (
            <>
              {' '}
              <span className="text-gray-300 dark:text-gray-600">·</span>
              {' '}
              <span title="Reasoning tokens">
                🧠 {formatTokens(sessionUsage.total_reasoning)}
              </span>
            </>
          )}
        </>
      )}
      {isStreaming && (
        <>
          <span className="text-gray-300 dark:text-gray-600">|</span>
          <span className="text-green-500 animate-pulse">● Streaming</span>
        </>
      )}
    </div>
  )
}
