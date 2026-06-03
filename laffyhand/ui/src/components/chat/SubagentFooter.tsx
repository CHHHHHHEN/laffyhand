import { useMemo, useRef } from "react"
import { useChatStore } from "@/stores/chat-store"
import { useSessionStore } from "@/stores/session-store"
import { buildSubagentTree } from "@/lib/subagentTree"
import { SubagentCard } from "./SubagentCard"

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
    <div className="border-t border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 shrink-0">
      {/* Tab bar */}
      <div className="flex items-center gap-2 px-3 py-1.5 text-xs text-gray-500 dark:text-gray-400 overflow-x-auto">
        <span className="font-medium text-gray-600 dark:text-gray-300 shrink-0">
          Background Tasks
        </span>
        <span className="text-gray-300 dark:text-gray-600 shrink-0">·</span>
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

      {/* Content area */}
      {tree.length > 0 && (
        <div className="px-3 pb-2 space-y-1.5 max-h-48 overflow-y-auto">
          {tree.map((node) => (
            <SubagentCard key={node.item.id} subagent={node.item} />
          ))}
        </div>
      )}
    </div>
  )
}
