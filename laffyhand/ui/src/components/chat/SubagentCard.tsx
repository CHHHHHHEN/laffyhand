import { useState, useMemo } from "react"
import type { ActiveSubagent } from "@/types/session"
import type { SubagentTreeNode } from "@/lib/subagentTree"

export function SubagentCard({
  subagent,
  children,
  depth = 0,
}: {
  subagent: ActiveSubagent
  children?: React.ReactNode
  depth?: number
}) {
  const [expanded, setExpanded] = useState(true)
  const isRunning = subagent.status === "running"
  const isDone = subagent.status === "completed"
  const isError = subagent.status === "error" || subagent.status === "cancelled"

  return (
    <div
      className={`rounded-lg border ${
        isRunning
          ? "border-blue-200 dark:border-blue-700/50 bg-blue-50/50 dark:bg-blue-900/10"
          : isError
            ? "border-red-200 dark:border-red-800/40 bg-red-50/50 dark:bg-red-900/10"
            : "border-green-200 dark:border-green-700/50 bg-green-50/50 dark:bg-green-900/10"
      } overflow-hidden`}
      style={{ marginLeft: depth * 16 }}
    >
      {/* Header */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-2 px-3 py-2 text-xs hover:bg-black/5 dark:hover:bg-white/5 transition-colors cursor-pointer"
      >
        {/* Status icon */}
        {isRunning ? (
          <span className="relative flex h-3 w-3 shrink-0">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75" />
            <span className="relative inline-flex rounded-full h-3 w-3 bg-blue-500" />
          </span>
        ) : isDone ? (
          <svg className="w-3 h-3 shrink-0 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
          </svg>
        ) : (
          <svg className="w-3 h-3 shrink-0 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        )}

        {/* Agent type + description */}
        <span className="font-medium text-gray-700 dark:text-gray-200 truncate">
          {subagent.agentType}
        </span>
        <span className="text-gray-400 dark:text-gray-500 truncate">
          {subagent.description}
        </span>

        {/* Stats */}
        <span className="ml-auto flex items-center gap-2 text-gray-400 dark:text-gray-500 shrink-0">
          {subagent.toolCount > 0 && (
            <span>{subagent.toolCount} tools</span>
          )}
          <svg
            className={`w-3 h-3 transition-transform ${expanded ? "rotate-90" : ""}`}
            fill="none" stroke="currentColor" viewBox="0 0 24 24"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
          </svg>
        </span>
      </button>

      {/* Expanded details */}
      {expanded && (
        <div className="border-t border-gray-200/50 dark:border-gray-700/30 px-3 py-2 space-y-1.5 text-xs animate-[fade-in_0.15s_ease-out]">
          {/* Reasoning */}
          {subagent.reasoning && (
            <div className="text-gray-500 dark:text-gray-400 italic leading-relaxed whitespace-pre-wrap">
              {subagent.reasoning}
            </div>
          )}

          {/* Text output */}
          {subagent.text && (
            <div className="text-gray-700 dark:text-gray-300 leading-relaxed whitespace-pre-wrap">
              {subagent.text}
            </div>
          )}

          {/* Tool calls */}
          {subagent.tools.length > 0 && (
            <div className="space-y-1">
              {subagent.tools.map((tool, i) => (
                <div
                  key={i}
                  className="flex items-start gap-1.5 text-gray-500 dark:text-gray-400 font-mono"
                >
                  <span className="text-blue-500 shrink-0">⚙</span>
                  <span className="font-medium text-blue-600 dark:text-blue-400 shrink-0">
                    {tool.name}
                  </span>
                  <span className="truncate text-gray-400 dark:text-gray-500">
                    {tool.input.length > 80 ? tool.input.slice(0, 80) + "..." : tool.input}
                  </span>
                </div>
              ))}
            </div>
          )}

          {/* Children (nested subagents) */}
          {children}

          {/* Summary */}
          {isDone && subagent.summary && (
            <div className="mt-1.5 pt-1.5 border-t border-gray-100 dark:border-gray-700/30 text-gray-400 dark:text-gray-500">
              {subagent.summary}
            </div>
          )}

          {/* Token usage */}
          {(subagent.inputTokens > 0 || subagent.outputTokens > 0) && (
            <div className="flex items-center gap-2 text-[10px] text-gray-400 dark:text-gray-500">
              <span>↗ {subagent.inputTokens}</span>
              <span>↘ {subagent.outputTokens}</span>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export function SubagentTreeCard({
  subagent,
  tree,
  depth = 0,
}: {
  subagent: ActiveSubagent
  tree: SubagentTreeNode[]
  depth?: number
}) {
  const children = useMemo(
    () => tree.filter((n) => n.item.parentId === subagent.id),
    [tree, subagent.id],
  )

  return (
    <SubagentCard subagent={subagent} depth={depth}>
      {children.length > 0 && (
        <div className="space-y-1.5 mt-2">
          {children.map((node) => (
            <SubagentTreeCard
              key={node.item.id}
              subagent={node.item}
              tree={tree}
              depth={depth + 1}
            />
          ))}
        </div>
      )}
    </SubagentCard>
  )
}
