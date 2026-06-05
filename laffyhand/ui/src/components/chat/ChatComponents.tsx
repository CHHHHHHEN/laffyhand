import { useState, useRef, useEffect, useMemo } from "react"
import type { ToolCall } from "@/types/session"
import { DiffView } from "./DiffView"

export function AiAvatar() {
  return (
    <div className="shrink-0 w-7 h-7 rounded-full bg-gradient-to-br from-[var(--accent)] to-blue-600 dark:to-blue-500 flex items-center justify-center ring-1 ring-white/20 dark:ring-white/10 shadow-sm">
      <svg className="w-3.5 h-3.5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
      </svg>
    </div>
  )
}

export function UserAvatar() {
  return (
    <div className="shrink-0 w-7 h-7 rounded-full bg-gradient-to-br from-[var(--icon-muted)] to-[var(--text-muted)] flex items-center justify-center ring-1 ring-white/20 dark:ring-white/10 shadow-sm">
      <svg className="w-3.5 h-3.5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
      </svg>
    </div>
  )
}

export function ReasoningBlock({ text, defaultExpanded = false }: { text: string; defaultExpanded?: boolean }) {
  const [expanded, setExpanded] = useState(defaultExpanded)
  const scrollRef = useRef<HTMLDivElement>(null)
  const lineCount = text.split('\n').length

  useEffect(() => {
    if (expanded && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [text, expanded])

  return (
    <div className="rounded-lg border border-[var(--border-muted)] overflow-hidden bg-[var(--bg-deep)]">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-1.5 px-3 py-1.5 text-sm text-[var(--text-muted)] hover:bg-[var(--overlay-hover)] transition-colors cursor-pointer select-none"
      >
        <svg
          className={`w-3 h-3 transition-transform duration-200 ${expanded ? "rotate-90" : ""}`}
          fill="none" stroke="currentColor" viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
        </svg>
        <span style={{ fontWeight: 500 }}>Thinking</span>
        <span className="ml-auto text-[var(--text-faint)]">
          {expanded ? "Hide" : `Show (${lineCount} lines)`}
        </span>
      </button>
      {expanded && (
        <div
          ref={scrollRef}
          className="px-3 py-2 text-sm text-[var(--text-base)] whitespace-pre-wrap leading-relaxed border-t border-[var(--border-muted)] max-h-60 overflow-y-auto"
        >
          {text}
        </div>
      )}
    </div>
  )
}

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
        <span className="w-2.5 h-2.5 shrink-0 rounded-full bg-green-500 flex items-center justify-center">
          <svg className="w-1.5 h-1.5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
          </svg>
        </span>
      )
    case "error":
      return (
        <span className="w-2.5 h-2.5 shrink-0 rounded-full bg-red-500 flex items-center justify-center">
          <svg className="w-1.5 h-1.5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </span>
      )
    default:
      return <span className="w-2.5 h-2.5 shrink-0 rounded-full bg-[var(--border-strong)]" />
  }
}

export function splitDiff(result: string): { summary: string; diff: string | null } {
  const idx = result.search(/\n--- /)
  if (idx === -1) return { summary: result, diff: null }
  const nextNewline = result.indexOf("\n", idx + 1)
  if (nextNewline === -1) return { summary: result, diff: null }
  // Verify there's a +++ line following the --- line
  const afterHeader = result.slice(nextNewline + 1)
  if (!afterHeader.startsWith("+++ ")) return { summary: result, diff: null }
  return {
    summary: result.slice(0, idx).trimEnd(),
    diff: result.slice(idx + 1),
  }
}

export function ToolCallCard({ toolCall }: { toolCall: ToolCall }) {
  const argStr = JSON.stringify(toolCall.arguments, null, 2)
  const displayInput = argStr
  const argLines = displayInput.split('\n').length
  const [showAllArgs, setShowAllArgs] = useState(false)

  const hasResult = toolCall.status === "completed" || toolCall.status === "error"

  const resultParts = useMemo(() => toolCall.result ? splitDiff(toolCall.result) : { summary: "", diff: null }, [toolCall.result])
  const [resultExpanded, setResultExpanded] = useState(() => resultParts.diff !== null)

  const borderColor = toolCall.status === "error"
    ? "border-red-200 dark:border-red-700/50"
    : toolCall.status === "completed"
      ? "border-green-200 dark:border-green-700/40"
      : toolCall.status === "running"
        ? "border-blue-200 dark:border-blue-600/50 animate-pulse"
        : "border-[var(--border-muted)]"

  const bgColor = toolCall.status === "error"
    ? "bg-red-50/40 dark:bg-red-900/8"
    : toolCall.status === "completed"
      ? "bg-green-50/40 dark:bg-green-900/8"
      : toolCall.status === "running"
        ? "bg-blue-50/50 dark:bg-blue-900/12"
        : "bg-[var(--bg-deep)]"

  return (
    <div className={`rounded-lg px-3 py-2 text-sm font-mono border transition-all duration-150 ${borderColor} ${bgColor}`}>
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <StatusDot status={toolCall.status || "pending"} />
          <span className="font-semibold text-[var(--text-base)] truncate">
            {toolCall.name}
          </span>
          <span className="text-[var(--text-faint)] text-[10px] font-mono">
            {toolCall.id?.slice(0, 6)}
          </span>
          {toolCall.status === "error" && (
            <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-[var(--state-danger-bg)] text-[var(--state-danger-fg)] font-semibold leading-none">
              failed
            </span>
          )}
          {toolCall.status === "completed" && (
            <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-[var(--state-success-bg)] text-[var(--state-success-fg)] font-semibold leading-none">
              done
            </span>
          )}
        </div>
      </div>

      {displayInput && (
        <>
          <pre className={`mt-1.5 text-[var(--text-muted)] whitespace-pre-wrap break-all leading-relaxed ${showAllArgs ? "" : "line-clamp-3"}`}>
            {displayInput}
          </pre>
          <button
            onClick={() => setShowAllArgs(!showAllArgs)}
            className="mt-1 text-[10px] text-[var(--accent)] hover:opacity-80 transition-opacity cursor-pointer font-sans"
          >
            {showAllArgs ? "Show less" : `Show all (${argLines} lines)`}
          </button>
        </>
      )}

      {hasResult && toolCall.result && (
        <div className="mt-2 pt-2 border-t border-dashed border-[var(--border-muted)]">
          <button
            onClick={() => setResultExpanded(!resultExpanded)}
            className="flex items-center gap-1 text-[10px] text-[var(--text-muted)] hover:text-[var(--text-base)] transition-colors cursor-pointer font-sans"
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
              <span className="text-[var(--text-faint)] truncate max-w-[200px]">
                — {resultParts.summary.length > 60 ? resultParts.summary.slice(0, 60) + "..." : resultParts.summary}
              </span>
            )}
          </button>
          {resultExpanded && (
            <div className="mt-1 space-y-1">
              <pre className="whitespace-pre-wrap break-all text-[var(--text-muted)] leading-relaxed font-mono text-xs">
                {resultParts.summary}
              </pre>
              {resultParts.diff && (
                <DiffView diff={resultParts.diff} />
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export function UsageBadge({ usage }: { usage: { inputTokens: number; outputTokens: number; reasoningTokens?: number } }) {
  return (
    <div className="flex items-center gap-2 text-xs text-[var(--text-muted)] bg-[var(--bg-deep)] rounded-md px-2 py-1 w-fit border border-[var(--border-muted)]">
      <span className="flex items-center gap-0.5" title="Input tokens">
        <svg className="w-2.5 h-2.5 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 11l5-5m0 0l5 5m-5-5v12" />
        </svg>
        {usage.inputTokens}
      </span>
      <span className="text-[var(--border-strong)]">·</span>
      <span className="flex items-center gap-0.5" title="Output tokens">
        <svg className="w-2.5 h-2.5 text-orange-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 13l-5 5m0 0l-5-5m5 5V6" />
        </svg>
        {usage.outputTokens}
      </span>
      {usage.reasoningTokens !== undefined && (
        <>
          <span className="text-[var(--border-strong)]">·</span>
          <span className="flex items-center gap-0.5" title="Reasoning tokens">
            <svg className="w-2.5 h-2.5 text-purple-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
            </svg>
            {usage.reasoningTokens}
          </span>
        </>
      )}
    </div>
  )
}
