import { useState, useMemo } from "react"
import type { ActiveSubagent } from "@/types/session"
import type { SubagentTreeNode } from "@/lib/subagentTree"
import { Spinner } from "@/components/ui/Spinner"
import { ReasoningBlock } from "./ChatComponents"

const AGENT_PALETTE = [
  "var(--accent)",
  "var(--state-success-bg, #22c55e)",
  "var(--state-warning-bg, #f59e0b)",
  "var(--state-danger-bg, #ef4444)",
  "var(--text-muted)",
  "var(--text-base)",
]

function agentColor(agentType: string): string {
  let hash = 0
  for (const ch of agentType) hash = (hash * 31 + ch.charCodeAt(0)) >>> 0
  return AGENT_PALETTE[hash % AGENT_PALETTE.length]!
}

function toolPreview(tool: ActiveSubagent["tools"][number]): string {
  const input = typeof tool.input === "string" ? tool.input : JSON.stringify(tool.input)
  return input.length > 80 ? input.slice(0, 80) + "…" : input
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
  const color = useMemo(() => agentColor(subagent.agentType), [subagent.agentType])

  return (
    <div style={{ marginLeft: depth * 16 }}>
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-2 px-3 py-1.5 text-xs rounded-lg border border-[var(--border-muted)] bg-[var(--bg-base)] hover:bg-[var(--overlay-hover)] transition-colors cursor-pointer text-left"
      >
        <span className="shrink-0 flex items-center justify-center" style={{ color }}>
          {isRunning ? (
            <Spinner size="sm" />
          ) : (
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d={isDone ? "M5 13l4 4L19 7" : "M6 18L18 6M6 6l12 12"} />
            </svg>
          )}
        </span>

        <span className="font-semibold shrink-0 capitalize" style={{ color }}>
          {subagent.agentType}
        </span>

        <span className="text-[var(--text-muted)] truncate min-w-0">
          {subagent.description}
        </span>

        <span className="ml-auto flex items-center gap-1.5 shrink-0">
          {isRunning && (
            <span className="text-[10px] text-blue-500 dark:text-blue-400 font-medium">
              running
            </span>
          )}
          {isDone && subagent.toolCount > 0 && (
            <span className="text-[10px] text-[var(--text-faint)]">
              {subagent.toolCount} tools
            </span>
          )}
          <svg
            className={`w-3 h-3 text-[var(--icon-muted)] transition-transform ${expanded ? "rotate-90" : ""}`}
            fill="none" stroke="currentColor" viewBox="0 0 24 24"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
          </svg>
        </span>
      </button>

      {expanded && (
        <div className="ml-3 pl-3 border-l border-[var(--border-muted)] mt-1 space-y-2 pb-1 text-xs">
          {subagent.reasoning && <ReasoningBlock text={subagent.reasoning} defaultExpanded />}

          {subagent.text && (
            <div className="leading-relaxed whitespace-pre-wrap text-xs text-[var(--text-base)]">
              {subagent.text}
            </div>
          )}

          {isRunning && !subagent.text && !subagent.reasoning && (
            <div className="flex items-center gap-2 py-1">
              <Spinner size="sm" />
              <span className="text-[var(--text-muted)]">Thinking</span>
            </div>
          )}

          {subagent.tools.length > 0 && (
            <div>
              <div className="text-[10px] uppercase tracking-wider text-[var(--text-faint)] font-medium mb-1">
                Tool calls · {subagent.tools.length}
              </div>
              <div className="space-y-1">
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
                      {toolPreview(tool)}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {children}

          {(subagent.summary || subagent.inputTokens > 0 || subagent.outputTokens > 0) && (
            <div className="flex items-center gap-3 text-[10px] text-[var(--text-muted)] pt-1">
              {subagent.summary && (
                <span className="truncate">{subagent.summary}</span>
              )}
              {(subagent.inputTokens > 0 || subagent.outputTokens > 0) && (
                <span className="flex items-center gap-2 shrink-0">
                  <span title="Input tokens">↗ {subagent.inputTokens}</span>
                  <span title="Output tokens">↘ {subagent.outputTokens}</span>
                </span>
              )}
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
        <div className="pt-1 space-y-1">
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
