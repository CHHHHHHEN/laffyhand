import { useState } from "react"
import type { ToolCall } from "@/types/session"

/** AI 头像：蓝-靛渐变圆形 */
export function AiAvatar() {
  return (
    <div className="shrink-0 w-7 h-7 rounded-full bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center shadow-sm">
      <svg className="w-3.5 h-3.5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
      </svg>
    </div>
  )
}

/** 用户头像：灰色圆形 */
export function UserAvatar() {
  return (
    <div className="shrink-0 w-7 h-7 rounded-full bg-gray-300 dark:bg-gray-600 flex items-center justify-center shadow-sm">
      <svg className="w-3.5 h-3.5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
      </svg>
    </div>
  )
}

/** 推理过程折叠面板 */
export function ReasoningBlock({ text }: { text: string }) {
  const [expanded, setExpanded] = useState(false)
  const [showAll, setShowAll] = useState(false)
  const lineCount = text.split('\n').length

  return (
    <div className="mb-2 rounded-lg border border-gray-200 dark:border-gray-600 overflow-hidden">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-1.5 px-3 py-1.5 text-xs text-gray-500 dark:text-gray-400 bg-gray-50 dark:bg-gray-800/50 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors cursor-pointer"
      >
        <svg
          className={`w-3 h-3 transition-transform duration-200 ${expanded ? "rotate-90" : ""}`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
        </svg>
        <span>Thinking</span>
        <span className="ml-auto text-gray-400 dark:text-gray-500">
          {expanded ? "Hide" : `Show (${lineCount} lines)`}
        </span>
      </button>
      {expanded && (
        <div className="relative">
          <div
            className={`px-3 py-2 text-xs text-gray-500 dark:text-gray-400 bg-white dark:bg-gray-800 whitespace-pre-wrap leading-relaxed border-t border-gray-100 dark:border-gray-700 animate-[fade-in_0.15s_ease-out] ${
              !showAll ? "max-h-60 overflow-hidden" : ""
            }`}
          >
            {text}
          </div>
          {!showAll && lineCount > 20 && (
            <>
              <div className="absolute bottom-0 left-0 right-0 h-8 bg-gradient-to-t from-white dark:from-gray-800 to-transparent pointer-events-none" />
              <button
                onClick={() => setShowAll(true)}
                className="w-full text-[10px] py-1 text-blue-500 dark:text-blue-400 bg-white dark:bg-gray-800 hover:bg-gray-50 dark:hover:bg-gray-750 transition-colors cursor-pointer font-sans border-t border-gray-100 dark:border-gray-700"
              >
                Show all ({lineCount} lines)
              </button>
            </>
          )}
          {showAll && lineCount > 20 && (
            <button
              onClick={() => setShowAll(false)}
              className="w-full text-[10px] py-1 text-blue-500 dark:text-blue-400 bg-white dark:bg-gray-800 hover:bg-gray-50 dark:hover:bg-gray-750 transition-colors cursor-pointer font-sans border-t border-gray-100 dark:border-gray-700"
            >
              Show less
            </button>
          )}
        </div>
      )}
    </div>
  )
}

/** 工具调用卡片 */
export function ToolCallCard({ toolCall }: { toolCall: ToolCall }) {
  const argStr = JSON.stringify(toolCall.arguments, null, 2)
  const argLines = argStr.split('\n').length
  const [showAll, setShowAll] = useState(argLines <= 6)

  return (
    <div className="bg-gray-50 dark:bg-gray-800/80 rounded-lg px-3 py-2 text-xs font-mono border border-gray-200 dark:border-gray-700 transition-all duration-150 hover:border-blue-300 dark:hover:border-blue-700 hover:shadow-sm">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5 min-w-0">
          <svg className="w-3 h-3 shrink-0 text-blue-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
          </svg>
          <span className="font-semibold text-blue-600 dark:text-blue-400 truncate">
            {toolCall.name}
          </span>
        </div>
        <span className="shrink-0 text-gray-400 dark:text-gray-500">
          {toolCall.id.slice(0, 6)}
        </span>
      </div>
      {showAll ? (
        <pre className="mt-1.5 text-gray-600 dark:text-gray-300 whitespace-pre-wrap break-all leading-relaxed">
          {argStr}
        </pre>
      ) : (
        <pre className="mt-1.5 text-gray-600 dark:text-gray-300 whitespace-pre-wrap break-all leading-relaxed line-clamp-3">
          {argStr}
        </pre>
      )}
      {argLines > 6 && (
        <button
          onClick={() => setShowAll(!showAll)}
          className="mt-1 text-[10px] text-blue-500 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300 transition-colors cursor-pointer font-sans"
        >
          {showAll ? "Show less" : `Show all (${argLines} lines)`}
        </button>
      )}
    </div>
  )
}

/** Token 消耗标签 */
export function UsageBadge({ usage }: { usage: { inputTokens: number; outputTokens: number } }) {
  return (
    <div className="mt-1.5 flex items-center gap-2 text-[10px] text-gray-400 dark:text-gray-500">
      <span className="flex items-center gap-0.5">
        <svg className="w-2.5 h-2.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 11l5-5m0 0l5 5m-5-5v12" />
        </svg>
        {usage.inputTokens}
      </span>
      <span className="flex items-center gap-0.5">
        <svg className="w-2.5 h-2.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 13l-5 5m0 0l-5-5m5 5V6" />
        </svg>
        {usage.outputTokens}
      </span>
    </div>
  )
}
