import { useState, useMemo, useRef, useEffect } from "react"
import { useNavigate, useParams } from "react-router-dom"
import { useSessions } from "@/hooks/use-sessions"
import { useSessionStore } from "@/stores/session-store"
import { Button } from "@/components/ui/Button"
import { Spinner } from "@/components/ui/Spinner"

export function Sidebar() {
  const navigate = useNavigate()
  const { sessionId } = useParams()
  const {
    sessions, isLoading, createSession, isCreating,
    deleteSession, forkSession, isForking,
  } = useSessions()
  const currentSessionId = useSessionStore((s) => s.currentSessionId)
  const [searchQuery, setSearchQuery] = useState("")
  const searchRef = useRef<HTMLInputElement>(null)

  // 键盘快捷键: Ctrl+K / Cmd+K 聚焦搜索
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault()
        searchRef.current?.focus()
      }
    }
    window.addEventListener("keydown", handleKeyDown)
    return () => window.removeEventListener("keydown", handleKeyDown)
  }, [])

  const filteredSessions = useMemo(() => {
    if (!searchQuery.trim()) return sessions
    const q = searchQuery.toLowerCase()
    return sessions.filter((s) => {
      const title = (s.title || "").toLowerCase()
      return title.includes(q) || s.messageCount.toString().includes(q)
    })
  }, [sessions, searchQuery])

  const handleNewSession = async () => {
    const id = await createSession(undefined)
    navigate(`/chat/${id}`)
  }

  const handleFork = async () => {
    const targetId = sessionId ?? currentSessionId
    if (!targetId) return
    const childId = await forkSession()
    navigate(`/chat/${childId}`)
  }

  const handleDelete = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation()
    const session = sessions.find((s) => s.id === id)
    const title = session?.title || "Untitled"
    if (!confirm(`Delete session "${title}"?`)) return
    await deleteSession(id)
    if ((sessionId ?? currentSessionId) === id) {
      navigate("/chat", { replace: true })
    }
  }

  const formatRelativeTime = (dateString: string | undefined): string => {
    if (!dateString) return ""
    const date = new Date(dateString)
    const now = new Date()
    const diffMs = now.getTime() - date.getTime()
    const diffSec = Math.floor(diffMs / 1000)
    const diffMin = Math.floor(diffSec / 60)
    const diffHour = Math.floor(diffMin / 60)
    const diffDay = Math.floor(diffHour / 24)

    if (diffDay > 0) {
      return diffDay === 1 ? "1d" : `${diffDay}d`
    } else if (diffHour > 0) {
      return diffHour === 1 ? "1h" : `${diffHour}h`
    } else if (diffMin > 0) {
      return diffMin === 1 ? "1m" : `${diffMin}m`
    } else {
      return "now"
    }
  }

  return (
    <div className="h-full flex flex-col bg-gray-50 dark:bg-gray-900 transition-colors duration-200">
      {/* 操作按钮区 */}
      <div className="p-3 border-b border-gray-200 dark:border-gray-700 space-y-2">
        <Button
          onClick={handleNewSession}
          disabled={isCreating}
          size="sm"
          variant="primary"
          className="w-full font-medium shadow-sm"
        >
          {isCreating ? "Creating..." : "+ New Session"}
        </Button>
        {(sessionId ?? currentSessionId) && (
          <Button
            onClick={handleFork}
            disabled={isForking}
            variant="secondary"
            size="sm"
            className="w-full text-xs"
          >
            <span className="flex items-center gap-1">
              <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 5v14l9-7-9-7z" />
              </svg>
              {isForking ? "Forking..." : "Fork"}
            </span>
          </Button>
        )}
        {/* 搜索框 */}
        <div className="relative">
          <svg
            className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-400 pointer-events-none"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
          <input
            ref={searchRef}
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search sessions... (⌘K)"
            className="w-full pl-8 pr-2 py-1.5 text-xs rounded-md border border-gray-200 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 placeholder-gray-400 dark:placeholder-gray-500 outline-none focus:border-blue-400 focus:ring-1 focus:ring-blue-400/30 transition-all"
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery("")}
              className="absolute right-2 top-1/2 -translate-y-1/2 p-0.5 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 cursor-pointer"
            >
              <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          )}
        </div>
      </div>

      {/* 会话列表 */}
      <div className="flex-1 overflow-y-auto p-2 space-y-1">
        {isLoading && (
          <div className="flex justify-center py-4">
            <Spinner size="sm" />
          </div>
        )}

        {!isLoading && searchQuery && filteredSessions.length === 0 && (
          <p className="text-xs text-gray-400 text-center py-4">
            No sessions match "{searchQuery}"
          </p>
        )}

        {filteredSessions.map((s) => {
          const isActive = (sessionId ?? currentSessionId) === s.id
          return (
            <div
              key={s.id}
              className="group relative animate-[fade-in_0.2s_ease-out] border-b border-gray-100 dark:border-gray-800 last:border-0"
            >
              <button
                onClick={() => navigate(`/chat/${s.id}`)}
                className={`w-full text-left px-3 py-2.5 rounded-lg text-sm transition-all duration-150 cursor-pointer ${
                  isActive
                    ? "bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300 shadow-sm border-l-2 border-blue-500 dark:border-blue-400"
                    : "text-gray-700 dark:text-gray-300 hover:bg-gray-200/70 dark:hover:bg-gray-800/70 hover:translate-x-0.5"
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="truncate font-medium text-sm">
                    {s.title || "Untitled"}
                  </div>
                  {s.updatedAt && (
                    <span className="shrink-0 text-[10px] text-gray-400 dark:text-gray-500 opacity-0 group-hover:opacity-100 transition-opacity">
                      {formatRelativeTime(s.updatedAt)}
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-2 mt-0.5">
                  <span className="text-[11px] text-gray-400 dark:text-gray-500">
                    {s.messageCount} {s.messageCount === 1 ? "msg" : "msgs"}
                  </span>
                </div>
              </button>
              {/* 删除按钮 */}
              <button
                onClick={(e) => handleDelete(e, s.id)}
                className={`absolute right-2 top-1/2 -translate-y-1/2 p-1 rounded-md transition-all duration-150 cursor-pointer opacity-0 group-hover:opacity-100 text-gray-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/30`}
                title="Delete session"
              >
                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                </svg>
              </button>
            </div>
          )
        })}

        {!isLoading && !searchQuery && sessions.length === 0 && (
          <p className="text-xs text-gray-400 text-center py-4">
            No sessions yet
          </p>
        )}
      </div>
    </div>
  )
}
