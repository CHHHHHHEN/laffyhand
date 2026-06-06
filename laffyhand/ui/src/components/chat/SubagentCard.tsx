import { useState, useMemo } from "react"
import type { ActiveSubagent, SubagentEvent, SubagentTool } from "@/types/session"
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

function ToolResultBlock({ tool }: { tool: SubagentTool }) {
  const [showResult, setShowResult] = useState(false)
  const hasResult = tool.result !== undefined
  const inputStr = tool.input.length > 120 ? tool.input.slice(0, 120) + "…" : tool.input

  return (
    <div className="rounded border border-[var(--border-muted)] bg-[var(--bg-deep)] overflow-hidden">
      <div className="flex items-start gap-1.5 px-2 py-1.5 font-mono text-xs">
        <span className={`${tool.isError ? "text-red-500" : "text-blue-500"} shrink-0 mt-0.5`}>
          {tool.isError ? "✗" : "⚙"}
        </span>
        <div className="min-w-0 flex-1">
          <span className="font-medium text-[var(--text-base)]">{tool.name}</span>
          <span className="text-[var(--text-faint)] ml-1.5 truncate block sm:inline-block max-w-full align-top">
            {inputStr}
          </span>
        </div>
        {hasResult && (
          <button
            onClick={() => setShowResult(!showResult)}
            className="shrink-0 text-[10px] text-[var(--accent)] hover:opacity-80 transition-opacity cursor-pointer font-sans"
          >
            {showResult ? "Hide" : "Result"}
          </button>
        )}
      </div>
      {hasResult && showResult && (
        <div className="border-t border-dashed border-[var(--border-muted)] px-2 py-1.5">
          <pre className={`overflow-x-auto whitespace-pre-wrap break-all text-xs leading-relaxed font-mono ${tool.isError ? "text-red-500" : "text-[var(--text-muted)]"}`}>
            {tool.result}
          </pre>
        </div>
      )}
    </div>
  )
}

function mergeAdjacentEvents(events: SubagentEvent[]) {
  const merged: SubagentEvent[] = []
  for (const evt of events) {
    const last = merged[merged.length - 1]
    if (last && last.kind === evt.kind && (evt.kind === "text" || evt.kind === "reasoning")) {
      last.content = (last.content ?? "") + (evt.content ?? "")
    } else {
      merged.push({ ...evt })
    }
  }
  return merged
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
  const [expanded, setExpanded] = useState(true)
  const [showPrompt, setShowPrompt] = useState(false)
  const isRunning = subagent.status === "running"
  const isDone = subagent.status === "completed"
  const color = useMemo(() => agentColor(subagent.agentType), [subagent.agentType])

  return (
    <div style={{ marginLeft: depth * 16 }}>
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-2 px-3 py-1.5 text-sm rounded-lg border border-[var(--border-muted)] bg-[var(--bg-base)] hover:bg-[var(--overlay-hover)] transition-colors cursor-pointer text-left"
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

        <span className="font-semibold shrink-0 capitalize text-sm" style={{ color }}>
          {subagent.agentType}
        </span>

        <span className="text-[var(--text-muted)] truncate min-w-0 text-sm">
          {subagent.description}
        </span>

        <span className="ml-auto flex items-center gap-1.5 shrink-0">
          {isRunning && (
            <span className="text-[11px] text-blue-500 dark:text-blue-400 font-medium">
              running
            </span>
          )}
          {isDone && subagent.toolCount > 0 && (
            <span className="text-[11px] text-[var(--text-faint)]">
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
        <div className="ml-3 pl-3 border-l border-[var(--border-muted)] mt-1 space-y-2 pb-1">
          {subagent.prompt && (
            <div>
              <button
                onClick={() => setShowPrompt(!showPrompt)}
                className="flex items-center gap-1 text-[11px] text-[var(--text-muted)] hover:text-[var(--text-base)] transition-colors cursor-pointer font-sans"
              >
                <svg
                  className={`w-2.5 h-2.5 transition-transform duration-150 ${showPrompt ? "rotate-90" : ""}`}
                  fill="none" stroke="currentColor" viewBox="0 0 24 24"
                >
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                </svg>
                <span className="font-medium">Prompt</span>
              </button>
              {showPrompt && (
                <div className="mt-1 bg-[var(--bg-deep)] rounded border border-[var(--border-muted)] px-2.5 py-2">
                  <pre className="text-xs text-[var(--text-muted)] whitespace-pre-wrap font-sans leading-relaxed">
                    {subagent.prompt}
                  </pre>
                </div>
              )}
            </div>
          )}

          {/* Chronological event rendering */}
          {subagent.events && subagent.events.length > 0 ? (
            (() => {
              const merged = mergeAdjacentEvents(subagent.events)
              let toolIdx = 0
              return merged.map((evt, i) => {
                // Use a stable ID derived from the original event indices so React
                // can reorder rather than remount when a new chunk is appended.
                switch (evt.kind) {
                  case "reasoning":
                    return evt.content ? (
                      <ReasoningBlock key={i} text={evt.content} defaultExpanded />
                    ) : null
                  case "text":
                    return evt.content ? (
                      <div key={i} className="leading-relaxed whitespace-pre-wrap text-sm text-[var(--text-base)]">
                        {evt.content}
                      </div>
                    ) : null
                  case "tool": {
                    const tool = subagent.tools[toolIdx++]
                    return tool ? <ToolResultBlock key={i} tool={tool} /> : null
                  }
                  case "tool_result":
                    // Result already attached to the corresponding tool entry
                    return null
                  case "error":
                    return evt.content ? (
                      <div key={i} className="text-sm text-red-500">
                        {evt.content}
                      </div>
                    ) : null
                  default:
                    return null
                }
              })
            })()
          ) : (
            /* Legacy accumulator rendering (for subagents loaded from server data) */
            <>
              {subagent.reasoning && <ReasoningBlock text={subagent.reasoning} defaultExpanded />}

              {subagent.text && (
                <div className="leading-relaxed whitespace-pre-wrap text-sm text-[var(--text-base)]">
                  {subagent.text}
                </div>
              )}

              {subagent.tools.length > 0 && (
                <div>
                  <div className="text-[11px] uppercase tracking-wider text-[var(--text-faint)] font-medium mb-1.5">
                    Tool calls · {subagent.tools.length}
                  </div>
                  <div className="space-y-1">
                    {subagent.tools.map((tool, i) => (
                      <ToolResultBlock key={i} tool={tool} />
                    ))}
                  </div>
                </div>
              )}
            </>
          )}

          {isRunning && !subagent.text && !subagent.reasoning && (
            <div className="flex items-center gap-2 py-1">
              <Spinner size="sm" />
              <span className="text-sm text-[var(--text-muted)]">Thinking</span>
            </div>
          )}

          {children}

          {(subagent.summary || subagent.inputTokens > 0 || subagent.outputTokens > 0) && (
            <div className="flex items-center gap-3 text-[11px] text-[var(--text-muted)] pt-1">
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
