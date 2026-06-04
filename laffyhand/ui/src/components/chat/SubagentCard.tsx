import { useState, useMemo } from "react"
import type { ActiveSubagent } from "@/types/session"
import type { SubagentTreeNode } from "@/lib/subagentTree"
import { ReasoningBlock } from "./ChatComponents"
import { Spinner } from "@/components/ui/Spinner"

function AgentAvatar({ agentType }: { agentType: string }) {
  const initials = agentType.slice(0, 2).toUpperCase()
  const colors: Record<string, string> = {
    general: "bg-purple-500",
    explore: "bg-teal-500",
  }
  return (
    <div
      className={`shrink-0 w-5 h-5 rounded-full flex items-center justify-center text-white text-[9px] font-bold ${
        colors[agentType] ?? "bg-blue-500"
      }`}
    >
      {initials}
    </div>
  )
}

export function SubagentCard({
  subagent,
  children,
  depth = 0,
}: {
  subagent: ActiveSubagent
  children?: React.ReactNode
  depth?: number
}) {
  const [expanded, setExpanded] = useState(subagent.status === "running")
  const isRunning = subagent.status === "running"
  const isDone = subagent.status === "completed"
  const isError = subagent.status === "error" || subagent.status === "cancelled"

  const instructionPreview =
    subagent.description.length > 60
      ? subagent.description.slice(0, 60) + "…"
      : subagent.description

  const expandLabel =
    isRunning ? "Running"
    : isDone ? "Completed"
    : "Failed"

  return (
    <div
      className={`rounded-lg border ${
        isRunning
          ? "border-blue-200 dark:border-blue-700/50"
          : isError
            ? "border-red-200 dark:border-red-800/40"
            : "border-green-200 dark:border-green-700/50"
      } overflow-hidden bg-[var(--bg-base)]`}
      style={{ marginLeft: depth * 16 }}
    >
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-2 px-3 py-2 text-xs hover:bg-[var(--overlay-hover)] transition-colors cursor-pointer"
      >
        <AgentAvatar agentType={subagent.agentType} />

        <span className="font-semibold text-[var(--text-base)] shrink-0">
          {subagent.agentType}
        </span>

        <span className={`shrink-0 text-[10px] font-medium px-1.5 py-0.5 rounded-full ${
          isRunning
            ? "bg-blue-100 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400"
            : isDone
              ? "bg-green-100 dark:bg-green-900/30 text-green-600 dark:text-green-400"
              : "bg-red-100 dark:bg-red-900/30 text-red-600 dark:text-red-400"
        }`}>
          {expandLabel}
        </span>

        <span className="text-[var(--text-muted)] truncate">
          {instructionPreview}
        </span>

        <span className="ml-auto flex items-center gap-2 text-[var(--text-muted)] shrink-0">
          {subagent.toolCount > 0 && (
            <span title="Tool calls">{subagent.toolCount} tools</span>
          )}
          <svg
            className={`w-3 h-3 transition-transform ${expanded ? "rotate-90" : ""}`}
            fill="none" stroke="currentColor" viewBox="0 0 24 24"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
          </svg>
        </span>
      </button>

      {expanded && (
        <div className="border-t border-[var(--border-muted)] px-4 py-3 space-y-3 text-xs">
          <div className="flex items-start gap-2 justify-end">
            <div className="bg-blue-50 dark:bg-blue-900/20 text-blue-800 dark:text-blue-200 rounded-xl rounded-tr-md px-3 py-2 max-w-[85%] leading-relaxed whitespace-pre-wrap">
              {subagent.description}
            </div>
            <div className="shrink-0 w-5 h-5 rounded-full bg-blue-500 flex items-center justify-center text-white text-[9px] font-bold">
              U
            </div>
          </div>

          <div className="flex items-start gap-2">
            <AgentAvatar agentType={subagent.agentType} />
            <div className="text-[var(--text-base)] space-y-2 min-w-0">
              {subagent.reasoning && (
                <ReasoningBlock text={subagent.reasoning} />
              )}

              {subagent.text ? (
                <div className="leading-relaxed whitespace-pre-wrap text-xs">
                  {subagent.text}
                </div>
              ) : isRunning && !subagent.reasoning ? (
                <div className="flex items-center gap-2 py-1">
                  <Spinner size="sm" />
                  <span className="text-[var(--text-muted)]">Thinking</span>
                </div>
              ) : null}

              {subagent.tools.length > 0 && (
                <div className="space-y-1">
                  <div className="text-[10px] uppercase tracking-wider text-[var(--text-faint)] font-medium">
                    Tool calls · {subagent.tools.length}
                  </div>
                  {subagent.tools.map((tool, i) => (
                    <div
                      key={i}
                      className="flex items-start gap-1.5 font-mono text-[var(--text-muted)]"
                    >
                      <span className="text-blue-500 shrink-0">⚙</span>
                      <span className="font-medium text-blue-600 dark:text-blue-400 shrink-0">
                        {tool.name}
                      </span>
                      <span className="truncate text-[var(--text-faint)]">
                        {tool.input.length > 80 ? tool.input.slice(0, 80) + "…" : tool.input}
                      </span>
                    </div>
                  ))}
                </div>
              )}

              {children}
            </div>
          </div>

          {(isDone || isError) && (
            <div className="flex items-center justify-between text-[10px] text-[var(--text-muted)] pt-1">
              <div className="flex items-center gap-3">
                {subagent.summary && (
                  <span className="truncate max-w-[300px]">{subagent.summary}</span>
                )}
                {(subagent.inputTokens > 0 || subagent.outputTokens > 0) && (
                  <span className="flex items-center gap-2 shrink-0">
                    <span title="Input tokens">↗ {subagent.inputTokens}</span>
                    <span title="Output tokens">↘ {subagent.outputTokens}</span>
                  </span>
                )}
              </div>
            </div>
          )}
        </div>
      )}

      {!expanded && isDone && (
        <div className="px-3 pb-2 flex items-center gap-2 text-[10px] text-[var(--text-muted)]">
          {subagent.toolCount > 0 && <span>{subagent.toolCount} tool calls</span>}
          {(subagent.inputTokens > 0 || subagent.outputTokens > 0) && (
            <span>· ↗{subagent.inputTokens} ↘{subagent.outputTokens}</span>
          )}
          {subagent.summary && (
            <span className="truncate">· {subagent.summary}</span>
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
        <div className="space-y-2 mt-3">
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
