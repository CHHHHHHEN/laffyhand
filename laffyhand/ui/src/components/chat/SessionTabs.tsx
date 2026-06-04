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
    <div className="flex items-center gap-0 px-1 pt-0.5 bg-[var(--bg-base)] border-b border-[var(--border-muted)] overflow-x-auto shrink-0">
      {tabs.map((tab) => (
        <div
          key={tab.id}
          className={`group flex items-center gap-1.5 px-2.5 py-1 text-xs rounded-t-md cursor-pointer select-none shrink-0 max-w-[160px] transition-all ${
            tab.id === activeSessionId
              ? "bg-[var(--bg-base)] text-[var(--text-base)] border border-[var(--border-muted)] border-b-transparent mt-0 -mb-px shadow-[0_-1px_2px_rgba(0,0,0,0.02)]"
              : "text-[var(--text-muted)] hover:text-[var(--text-base)] hover:bg-[var(--overlay-hover)] border border-transparent border-b-0"
          }`}
          onClick={() => navigate(`/chat/${tab.id}`)}
        >
          {tab.isStreaming && (
            <span className="relative flex h-1.5 w-1.5 shrink-0">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75" />
              <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-green-500" />
            </span>
          )}
          <span className="truncate" style={{ fontWeight: 440 }}>{tab.title || "Untitled"}</span>
          <button
            onClick={(e) => {
              e.stopPropagation()
              removeActiveSession(tab.id)
            }}
            className="p-0.5 rounded opacity-0 group-hover:opacity-100 hover:bg-[var(--overlay-hover)] text-[var(--icon-muted)] hover:text-[var(--icon-base)] transition-all cursor-pointer"
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
