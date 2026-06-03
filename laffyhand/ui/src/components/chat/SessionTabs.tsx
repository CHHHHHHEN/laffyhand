import { useMemo } from "react"
import { useNavigate } from "react-router-dom"
import { useSessionStore } from "@/stores/session-store"
import { useChatStore } from "@/stores/chat-store"
import { useSessions } from "@/hooks/use-sessions"

export function SessionTabs() {
  const navigate = useNavigate()
  const activeSessionId = useSessionStore((s) => s.activeSessionId)
  const activeSessionIds = useSessionStore((s) => s.activeSessionIds)
  const removeActiveSession = useSessionStore((s) => s.removeActiveSession)
  const { sessions } = useSessions()
  const allSessionStates = useChatStore((s) => s.sessions)

  // Map session IDs to their titles and streaming status
  const tabs = useMemo(() => {
    const sessionMap = new Map(sessions.map((s) => [s.id, s.title]))
    return activeSessionIds.map((id) => ({
      id,
      title: sessionMap.get(id) ?? null,
      isStreaming: allSessionStates[id]?.isStreaming ?? false,
    }))
  }, [activeSessionIds, sessions, allSessionStates])

  if (tabs.length === 0) return null

  return (
    <div className="flex items-center gap-0 px-1 pt-1 bg-white dark:bg-gray-900 border-b border-gray-200 dark:border-gray-800 overflow-x-auto shrink-0">
      {tabs.map((tab) => (
        <div
          key={tab.id}
          className={`group flex items-center gap-1.5 px-2.5 py-1 text-xs rounded-t-md cursor-pointer select-none shrink-0 max-w-[160px] transition-colors ${
            tab.id === activeSessionId
              ? "bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-200 border border-gray-200 dark:border-gray-700 border-b-transparent"
              : "text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800/50"
          }`}
          onClick={() => navigate(`/chat/${tab.id}`)}
        >
          {tab.isStreaming && (
            <span className="relative flex h-1.5 w-1.5 shrink-0">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75" />
              <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-green-500" />
            </span>
          )}
          <span className="truncate">{tab.title ?? tab.id.slice(0, 8)}</span>
          <button
            onClick={(e) => {
              e.stopPropagation()
              removeActiveSession(tab.id)
            }}
            className="p-0.5 rounded opacity-0 group-hover:opacity-100 hover:bg-gray-200 dark:hover:bg-gray-700 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-all cursor-pointer"
            title="Close tab"
          >
            <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      ))}
    </div>
  )
}
