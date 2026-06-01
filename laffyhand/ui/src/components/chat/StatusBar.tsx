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
    <div className="flex items-center gap-3 px-4 py-1.5 text-xs text-gray-500 dark:text-gray-400 border-b border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900/50 shrink-0">
      {/* Model */}
      {model && (
        <span className="font-mono flex items-center gap-1.5 text-[11px]" title="Model">
          <span className="w-1.5 h-1.5 rounded-full bg-blue-500" />
          {model}
        </span>
      )}

      {/* Token Usage */}
      {sessionUsage && (
        <>
          <span className="text-gray-300 dark:text-gray-600 select-none">|</span>

          {/* Total / Context */}
          <span className="flex items-center gap-1.5" title="Total tokens used / Context size">
            <svg className="w-3 h-3 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4" />
            </svg>
            <span className="font-medium">{formatTokens(totalTokens)}</span>
            <span className="text-gray-400 dark:text-gray-500">/ {formatTokens(ctxSize)}</span>
          </span>

          {/* Input / Output */}
          <span className="flex items-center gap-1.5" title="Input → Output breakdown">
            <span className="flex items-center gap-0.5">
              <svg className="w-3 h-3 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 11l5-5m0 0l5 5m-5-5v12" />
              </svg>
              <span>{formatTokens(sessionUsage.total_input)}</span>
            </span>
            <svg className="w-2.5 h-2.5 text-gray-300 dark:text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 13l-5 5m0 0l-5-5m5 5V6" />
            </svg>
            <span className="flex items-center gap-0.5">
              <svg className="w-3 h-3 text-orange-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 13l-5 5m0 0l-5-5m5 5V6" />
              </svg>
              <span>{formatTokens(sessionUsage.total_output)}</span>
            </span>
          </span>

          {/* Reasoning */}
          {sessionUsage.total_reasoning > 0 && (
            <span className="flex items-center gap-1" title="Reasoning tokens">
              <span className="text-gray-300 dark:text-gray-600 select-none">·</span>
              <span className="flex items-center gap-0.5">
                <span className="text-[11px]">🧠</span>
                <span>{formatTokens(sessionUsage.total_reasoning)}</span>
              </span>
            </span>
          )}
        </>
      )}

      {/* Streaming indicator */}
      {isStreaming && (
        <>
          <span className="text-gray-300 dark:text-gray-600 select-none">|</span>
          <span className="flex items-center gap-1.5 text-green-600 dark:text-green-400">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-green-500" />
            </span>
            <span className="text-[11px] font-medium">Streaming</span>
          </span>
        </>
      )}
    </div>
  )
}
