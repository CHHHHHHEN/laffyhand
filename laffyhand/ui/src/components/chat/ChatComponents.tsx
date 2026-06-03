import { useState } from "react"
import type { ToolCall } from "@/types/session"

/** AI 头像：蓝-靛渐变，带机器人图标 */
export function AiAvatar() {
  return (
    <div className="shrink-0 w-7 h-7 rounded-full bg-gradient-to-br from-blue-500 via-blue-600 to-indigo-700 flex items-center justify-center shadow-sm ring-1 ring-white/20 dark:ring-white/10">
      <svg className="w-3.5 h-3.5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
      </svg>
    </div>
  )
}

/** 用户头像：优雅的灰色渐变圆形 */
export function UserAvatar() {
  return (
    <div className="shrink-0 w-7 h-7 rounded-full bg-gradient-to-br from-gray-400 to-gray-500 dark:from-gray-500 dark:to-gray-600 flex items-center justify-center shadow-sm ring-1 ring-white/20 dark:ring-white/10">
      <svg className="w-3.5 h-3.5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
      </svg>
    </div>
  )
}

/** 推理过程折叠面板 — 更精致的 UI */
export function ReasoningBlock({ text }: { text: string }) {
  const [expanded, setExpanded] = useState(false)
  const [showAll, setShowAll] = useState(false)
  const lineCount = text.split('\n').length

  return (
    <div className="mb-2 rounded-lg border border-amber-200/60 dark:border-amber-700/40 overflow-hidden bg-amber-50/30 dark:bg-amber-900/10">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-1.5 px-3 py-1.5 text-xs text-amber-600 dark:text-amber-400 hover:bg-amber-100/50 dark:hover:bg-amber-900/20 transition-colors cursor-pointer select-none"
      >
        <svg
          className={`w-3 h-3 transition-transform duration-200 ${expanded ? "rotate-90" : ""}`}
          fill="none" stroke="currentColor" viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
        </svg>
        <span className="font-medium">Thinking</span>
        <span className="ml-auto text-amber-500 dark:text-amber-500/70">
          {expanded ? "Hide" : `Show (${lineCount} lines)`}
        </span>
      </button>
      {expanded && (
        <div className="relative">
          <div
            className={`px-3 py-2 text-xs text-amber-800 dark:text-amber-200/80 bg-white/50 dark:bg-gray-900/30 whitespace-pre-wrap leading-relaxed border-t border-amber-200/40 dark:border-amber-700/30 animate-[fade-in_0.15s_ease-out] ${
              !showAll ? "max-h-60 overflow-hidden" : ""
            }`}
          >
            {text}
          </div>
          {!showAll && lineCount > 20 && (
            <>
              <div className="absolute bottom-0 left-0 right-0 h-8 bg-gradient-to-t from-white/50 dark:from-gray-900/50 to-transparent pointer-events-none" />
              <button
                onClick={() => setShowAll(true)}
                className="w-full text-[10px] py-1 text-amber-600 dark:text-amber-400 bg-white/50 dark:bg-gray-900/30 hover:bg-amber-50/50 dark:hover:bg-amber-900/20 transition-colors cursor-pointer font-sans border-t border-amber-200/30 dark:border-amber-700/20"
              >
                Show all ({lineCount} lines)
              </button>
            </>
          )}
          {showAll && lineCount > 20 && (
            <button
              onClick={() => setShowAll(false)}
              className="w-full text-[10px] py-1 text-amber-600 dark:text-amber-400 bg-white/50 dark:bg-gray-900/30 hover:bg-amber-50/50 dark:hover:bg-amber-900/20 transition-colors cursor-pointer font-sans border-t border-amber-200/30 dark:border-amber-700/20"
            >
              Show less
            </button>
          )}
        </div>
      )}
    </div>
  )
}

/** 状态指示器圆点 */
function StatusDot({ status }: { status: ToolCall["status"] }) {
  switch (status) {
    case "running":
      return (
        <span className="relative flex h-2.5 w-2.5 shrink-0">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75" />
          <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-blue-500" />
        </span>
      )
    case "completed":
      return (
        <span className="w-2.5 h-2.5 shrink-0 rounded-full bg-green-500 flex items-center justify-center ring-1 ring-green-300 dark:ring-green-700">
          <svg className="w-1.5 h-1.5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
          </svg>
        </span>
      )
    case "error":
      return (
        <span className="w-2.5 h-2.5 shrink-0 rounded-full bg-red-500 flex items-center justify-center ring-1 ring-red-300 dark:ring-red-700">
          <svg className="w-1.5 h-1.5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </span>
      )
    default:
      return <span className="w-2.5 h-2.5 shrink-0 rounded-full bg-gray-300 dark:bg-gray-600" />
  }
}

/** 工具调用卡片：精致卡片式设计，支持流式状态 + 可展开结果 */
export function ToolCallCard({ toolCall }: { toolCall: ToolCall }) {
  const argStr = JSON.stringify(toolCall.arguments, null, 2)
  const displayInput = argStr
  const argLines = displayInput.split('\n').length
  const [showAllArgs, setShowAllArgs] = useState(argLines <= 6)

  // Result expand/collapse
  const hasResult = toolCall.status === "completed" || toolCall.status === "error"
  const [resultExpanded, setResultExpanded] = useState(false)
  const [resultShowAll, setResultShowAll] = useState(false)

  // Border color by status
  const borderColor = toolCall.status === "error"
    ? "border-red-200 dark:border-red-700/50"
    : toolCall.status === "completed"
      ? "border-green-200 dark:border-green-700/40"
      : toolCall.status === "running"
        ? "border-blue-200 dark:border-blue-600/50 animate-pulse"
        : "border-gray-200 dark:border-gray-700"

  const bgColor = toolCall.status === "error"
    ? "bg-red-50/40 dark:bg-red-900/8"
    : toolCall.status === "completed"
      ? "bg-green-50/40 dark:bg-green-900/8"
      : toolCall.status === "running"
        ? "bg-blue-50/50 dark:bg-blue-900/12"
        : "bg-gray-50 dark:bg-gray-800/60"

  return (
    <div className={`rounded-lg px-3 py-2 text-xs font-mono border transition-all duration-150 ${borderColor} ${bgColor}`}>
      {/* Header: status + name + id */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <StatusDot status={toolCall.status || "pending"} />
          <span className="font-semibold text-gray-700 dark:text-gray-200 truncate">
            {toolCall.name}
          </span>
          <span className="text-gray-400 dark:text-gray-500 text-[10px] font-mono">
            {toolCall.id?.slice(0, 6)}
          </span>
          {/* Status label badge */}
          {toolCall.status === "error" && (
            <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-red-100 dark:bg-red-900/30 text-red-600 dark:text-red-400 font-semibold leading-none">
              failed
            </span>
          )}
          {toolCall.status === "completed" && (
            <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-green-100 dark:bg-green-900/30 text-green-600 dark:text-green-400 font-semibold leading-none">
              done
            </span>
          )}
        </div>
      </div>

      {/* Arguments area */}
      {displayInput && (
        <>
          <pre className={`mt-1.5 text-gray-500 dark:text-gray-400 whitespace-pre-wrap break-all leading-relaxed ${showAllArgs ? "" : "line-clamp-3"}`}>
            {displayInput}
          </pre>
          {argLines > 6 && (
            <button
              onClick={() => setShowAllArgs(!showAllArgs)}
              className="mt-1 text-[10px] text-blue-500 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300 transition-colors cursor-pointer font-sans"
            >
              {showAllArgs ? "Show less" : `Show all (${argLines} lines)`}
            </button>
          )}
        </>
      )}

      {/* Result area (only for completed/error tool calls) */}
      {hasResult && toolCall.result && (
        <div className="mt-2 pt-2 border-t border-dashed border-gray-200 dark:border-gray-700">
          <button
            onClick={() => {
              setResultExpanded(!resultExpanded)
              setResultShowAll(false)
            }}
            className="flex items-center gap-1 text-[10px] text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300 transition-colors cursor-pointer font-sans"
          >
            <svg
              className={`w-2.5 h-2.5 transition-transform duration-150 ${resultExpanded ? "rotate-90" : ""}`}
              fill="none" stroke="currentColor" viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
            </svg>
            <span className={toolCall.isError ? "text-red-500 font-medium" : "text-green-600 dark:text-green-400 font-medium"}>
              {toolCall.isError ? "Error" : "Result"}
            </span>
            {!resultExpanded && (
              <span className="text-gray-400 dark:text-gray-500 truncate max-w-[200px]">
                — {toolCall.result.length > 60 ? toolCall.result.slice(0, 60) + "..." : toolCall.result}
              </span>
            )}
          </button>
          {resultExpanded && (
            <div className="relative mt-1">
              <pre
                className={`text-[11px] text-gray-600 dark:text-gray-300 whitespace-pre-wrap break-all leading-relaxed bg-white/50 dark:bg-gray-900/30 rounded px-2 py-1.5 border border-gray-100 dark:border-gray-700/50 ${
                  !resultShowAll ? "max-h-40 overflow-hidden" : ""
                }`}
              >
                {toolCall.result}
              </pre>
              {!resultShowAll && toolCall.result.length > 1000 && (
                <>
                  <div className="absolute bottom-0 left-0 right-0 h-6 bg-gradient-to-t from-white/80 dark:from-gray-900/80 to-transparent pointer-events-none" />
                  <button
                    onClick={() => setResultShowAll(true)}
                    className="w-full text-[10px] py-0.5 text-blue-500 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300 transition-colors cursor-pointer font-sans"
                  >
                    Show full result ({toolCall.result.length} chars)
                  </button>
                </>
              )}
              {resultShowAll && toolCall.result.length > 1000 && (
                <button
                  onClick={() => setResultShowAll(false)}
                  className="w-full text-[10px] py-0.5 text-blue-500 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300 transition-colors cursor-pointer font-sans"
                >
                  Show less
                </button>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

/** Token 消耗标签 */
export function UsageBadge({ usage }: { usage: { inputTokens: number; outputTokens: number } }) {
  return (
    <div className="flex items-center gap-2 text-[10px] text-gray-400 dark:text-gray-500 bg-gray-50 dark:bg-gray-800/50 rounded-md px-2 py-1 w-fit">
      <span className="flex items-center gap-0.5" title="Input tokens">
        <svg className="w-2.5 h-2.5 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 11l5-5m0 0l5 5m-5-5v12" />
        </svg>
        {usage.inputTokens}
      </span>
      <span className="text-gray-300 dark:text-gray-600">·</span>
      <span className="flex items-center gap-0.5" title="Output tokens">
        <svg className="w-2.5 h-2.5 text-orange-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 13l-5 5m0 0l-5-5m5 5V6" />
        </svg>
        {usage.outputTokens}
      </span>
    </div>
  )
}
