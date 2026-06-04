import { useState, useMemo, useRef, useEffect, useCallback } from "react"
import { useNavigate, useParams } from "react-router-dom"
import { useQueryClient } from "@tanstack/react-query"
import { useSessions, useAgents } from "@/hooks/use-sessions"
import { useSessionStore } from "@/stores/session-store"
import { rpcClient } from "@/lib/rpc"
import { Button } from "@/components/ui/Button"
import { Spinner } from "@/components/ui/Spinner"

export function Sidebar() {
  const navigate = useNavigate()
  const { sessionId } = useParams()
  const {
    sessions, isLoading, createSession, isCreating,
    deleteSession, forkSession, isForking,
  } = useSessions()
  const { agents } = useAgents()
  const activeSessionId = useSessionStore((s) => s.activeSessionId)
  const [selectedAgent, setSelectedAgent] = useState("build")
  const [searchQuery, setSearchQuery] = useState("")
  const searchRef = useRef<HTMLInputElement>(null)
  const renameRef = useRef<HTMLInputElement>(null)
  const queryClient = useQueryClient()
  const [renamingId, setRenamingId] = useState<string | null>(null)
  const [renameValue, setRenameValue] = useState("")

  const startRename = useCallback((e: React.MouseEvent, id: string, currentTitle: string | null) => {
    e.stopPropagation()
    setRenamingId(id)
    setRenameValue(currentTitle || "")
    // Focus the input on next tick after render
    requestAnimationFrame(() => renameRef.current?.focus())
  }, [])

  const commitRename = useCallback(async (id: string) => {
    const title = renameValue.trim()
    if (title) {
      try {
        await rpcClient.sessionSetTitle(id, title)
        queryClient.invalidateQueries({ queryKey: ["sessions"] })
      } catch {
        // ignore
      }
    }
    setRenamingId(null)
    setRenameValue("")
  }, [renameValue, queryClient])

  const handleRenameKeyDown = useCallback(
    (e: React.KeyboardEvent, id: string) => {
      if (e.key === "Enter") {
        e.preventDefault()
        commitRename(id)
      } else if (e.key === "Escape") {
        setRenamingId(null)
        setRenameValue("")
      }
    },
    [commitRename],
  )

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
    const id = await createSession(undefined, selectedAgent)
    navigate(`/chat/${id}`)
  }

  const handleFork = async () => {
    const targetId = sessionId ?? activeSessionId
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
    if ((sessionId ?? activeSessionId) === id) {
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
    <div className="h-full flex flex-col bg-gray-50 dark:bg-gray-900/50 transition-colors duration-200">
      {/* 操作按钮区 */}
      <div className="p-3 border-b border-gray-200 dark:border-gray-800 space-y-2">
        <Button
          onClick={handleNewSession}
          disabled={isCreating}
          size="sm"
          variant="primary"
          className="w-full font-medium"
        >
          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          {isCreating ? "Creating..." : "New Session"}
        </Button>
        {(sessionId ?? activeSessionId) && (
          <Button
            onClick={handleFork}
            disabled={isForking}
            variant="secondary"
            size="sm"
            className="w-full"
          >
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 5v14l9-7-9-7z" />
            </svg>
            {isForking ? "Forking..." : "Fork"}
          </Button>
        )}
        {/* Agent 选择器 */}
        {agents.length > 0 && (
          <div className="relative">
            <select
              value={selectedAgent}
              onChange={(e) => setSelectedAgent(e.target.value)}
              className="w-full px-2.5 py-1.5 text-xs rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 outline-none focus:border-blue-400 focus:ring-1 focus:ring-blue-400/30 transition-all appearance-none cursor-pointer"
            >
              {agents.map((a) => (
                <option key={a.name} value={a.name}>
                  {a.name}{a.description ? ` — ${a.description}` : ""}
                </option>
              ))}
            </select>
            <svg
              className="absolute right-2.5 top-1/2 -translate-y-1/2 w-3 h-3 text-gray-400 pointer-events-none"
              fill="none" stroke="currentColor" viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
            </svg>
          </div>
        )}
        {/* 搜索框 */}
        <div className="relative">
          <svg
            className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-400 pointer-events-none"
            fill="none" stroke="currentColor" viewBox="0 0 24 24"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
          <input
            ref={searchRef}
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search sessions... (⌘K)"
            className="w-full pl-8 pr-8 py-1.5 text-xs rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 placeholder-gray-400 dark:placeholder-gray-500 outline-none focus:border-blue-400 focus:ring-1 focus:ring-blue-400/30 transition-all"
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
      <div className="flex-1 overflow-y-auto p-2 space-y-0.5">
        {isLoading && (
          <div className="flex justify-center py-6">
            <Spinner size="sm" />
          </div>
        )}

        {!isLoading && searchQuery && filteredSessions.length === 0 && (
          <p className="text-xs text-gray-400 text-center py-6">
            No sessions match "<span className="font-medium">{searchQuery}</span>"
          </p>
        )}

        {filteredSessions.map((s) => {
          const isActive = (sessionId ?? activeSessionId) === s.id
          const isRenaming = renamingId === s.id
          return (
            <div
              key={s.id}
              className="group relative"
            >
              {isRenaming ? (
                <div className="w-full px-3 py-2.5 rounded-lg bg-blue-100 dark:bg-blue-900/35">
                  <input
                    ref={renameRef}
                    type="text"
                    value={renameValue}
                    onChange={(e) => setRenameValue(e.target.value)}
                    onBlur={() => commitRename(s.id)}
                    onKeyDown={(e) => handleRenameKeyDown(e, s.id)}
                    onClick={(e) => e.stopPropagation()}
                    className="w-full bg-transparent text-sm font-medium text-blue-700 dark:text-blue-300 outline-none"
                  />
                </div>
              ) : (
                <button
                  onClick={() => navigate(`/chat/${s.id}`)}
                  className={`w-full text-left px-3 py-2.5 rounded-lg text-sm transition-all duration-150 cursor-pointer ${
                    isActive
                      ? "bg-blue-100 dark:bg-blue-900/35 text-blue-700 dark:text-blue-300 shadow-sm"
                      : "text-gray-600 dark:text-gray-400 hover:bg-gray-200/60 dark:hover:bg-gray-800/60"
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
              )}
              {/* 操作按钮 */}
              <div className="absolute right-2 top-1/2 -translate-y-1/2 flex items-center gap-0.5">
                {!isRenaming && (
                  <button
                    onClick={(e) => startRename(e, s.id, s.title)}
                    className="p-1 rounded-md transition-all duration-150 cursor-pointer opacity-0 group-hover:opacity-100 text-gray-400 hover:text-blue-500 hover:bg-blue-50 dark:hover:bg-blue-900/25"
                    title="Rename session"
                  >
                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                    </svg>
                  </button>
                )}
                {!isRenaming && (
                  <button
                    onClick={(e) => handleDelete(e, s.id)}
                    className="p-1 rounded-md transition-all duration-150 cursor-pointer opacity-0 group-hover:opacity-100 text-gray-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/25"
                    title="Delete session"
                  >
                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                    </svg>
                  </button>
                )}
              </div>
            </div>
          )
        })}

        {!isLoading && !searchQuery && sessions.length === 0 && (
          <p className="text-xs text-gray-400 text-center py-6">
            No sessions yet
          </p>
        )}
      </div>
    </div>
  )
}
