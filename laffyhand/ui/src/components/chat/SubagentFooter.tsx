import { useMemo, useRef } from "react"
import { useChatStore } from "@/stores/chat-store"
import { useSessionStore } from "@/stores/session-store"
import { buildSubagentTree } from "@/lib/subagentTree"
import { SubagentTreeCard } from "./SubagentCard"

export function SubagentFooter() {
  const activeSessionId = useSessionStore((s) => s.activeSessionId)
  const emptyRef = useRef<never[]>([])
  const backgroundSubagents = useChatStore(
    (s) => {
      if (!activeSessionId) return emptyRef.current
      return s.sessions[activeSessionId]?.backgroundSubagents ?? emptyRef.current
    },
  )

  const tree = useMemo(
    () => buildSubagentTree(backgroundSubagents),
    [backgroundSubagents],
  )

  if (backgroundSubagents.length === 0) return null

  const runningCount = backgroundSubagents.filter((s) => s.status === "running").length
  const totalCount = backgroundSubagents.length

  return (
    <div className="border-t border-[var(--border-muted)] bg-[var(--bg-base)] shrink-0">
      <div className="flex items-center gap-2 px-3 py-1.5 text-xs text-[var(--text-muted)] overflow-x-auto">
        <span className="text-[var(--text-base)] shrink-0" style={{ fontWeight: 500 }}>
          Background Tasks
        </span>
        <span className="text-[var(--border-strong)] shrink-0">·</span>
        <span className="shrink-0">
          {runningCount > 0 ? `${runningCount} running` : `${totalCount} total`}
        </span>

        {runningCount > 0 && (
          <span className="relative flex h-2 w-2 shrink-0">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75" />
            <span className="relative inline-flex rounded-full h-2 w-2 bg-blue-500" />
          </span>
        )}
      </div>

      {tree.length > 0 && (
        <div className="px-3 pb-2 space-y-1 max-h-48 overflow-y-auto">
          {tree.map((node) => (
            <SubagentTreeCard key={node.item.id} subagent={node.item} tree={tree} />
          ))}
        </div>
      )}
    </div>
  )
}
