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
    <div className="flex items-center gap-3 px-4 py-2 text-xs text-gray-500 dark:text-gray-400 border-b border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/30 shrink-0">
      {model && (
        <span className="font-mono flex items-center gap-1" title="Model">
          <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
          </svg>
          {model}
        </span>
      )}
      {sessionUsage && (
        <>
          <span className="text-gray-300 dark:text-gray-600">|</span>
          <span className="flex items-center gap-1" title="Total tokens used">
            <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4" />
            </svg>
            {formatTokens(totalTokens)} / {formatTokens(ctxSize)}
          </span>
          <span className="text-gray-300 dark:text-gray-600">|</span>
          <span className="flex items-center gap-1" title="Breakdown">
            <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 11l5-5m0 0l5 5m-5-5v12" />
            </svg>
            {formatTokens(sessionUsage.total_input)}
            <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 13l-5 5m0 0l-5-5m5 5V6" />
            </svg>
            {formatTokens(sessionUsage.total_output)}
          </span>
          {sessionUsage.total_reasoning > 0 && (
            <>
              {' '}
              <span className="text-gray-300 dark:text-gray-600">·</span>
              {' '}
              <span className="flex items-center gap-1" title="Reasoning tokens">
                🧠 {formatTokens(sessionUsage.total_reasoning)}
              </span>
            </>
          )}
        </>
      )}
      {isStreaming && (
        <>
          <span className="text-gray-300 dark:text-gray-600">|</span>
          <span className="flex items-center gap-1 text-green-500">
            <span className="w-2 h-2 bg-green-500 rounded-full animate-pulse" />
            Streaming
          </span>
        </>
      )}
    </div>
  )
}
