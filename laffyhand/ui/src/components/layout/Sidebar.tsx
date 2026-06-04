import { useState } from "react"
import { useNavigate, useParams } from "react-router-dom"
import { useSessions, useAgents } from "@/hooks/use-sessions"
import { useSessionStore } from "@/stores/session-store"
import { useChatStore } from "@/stores/chat-store"
import { useUiStore } from "@/stores/ui-store"
import { Spinner } from "@/components/ui/Spinner"
import { rpcClient } from "@/lib/rpc"

export function Sidebar() {
  const navigate = useNavigate()
  const { sessionId } = useParams()
  const { sessions, isLoading, refetch, createSession, forkSession, deleteSession } = useSessions()
  const addActiveSession = useSessionStore((s) => s.addActiveSession)
  const removeActiveSession = useSessionStore((s) => s.removeActiveSession)
  const addSession = useChatStore((s) => s.addSession)
  const removeSession = useChatStore((s) => s.removeSession)

  const [search, setSearch] = useState("")
  const [renamingId, setRenamingId] = useState<string | null>(null)
  const [renameValue, setRenameValue] = useState("")
  const [showAgentSelect, setShowAgentSelect] = useState(false)
  const [showDeleteConfirm, setShowDeleteConfirm] = useState<string | null>(null)
  const [deleting, setDeleting] = useState(false)

  const { agents } = useAgents()
  const defaultAgent = useUiStore((s) => s.defaultAgent)
  const setDefaultAgent = useUiStore((s) => s.setDefaultAgent)

  const filteredSessions = (sessions ?? []).filter((s) =>
    !search || (s.title ?? s.id).toLowerCase().includes(search.toLowerCase()),
  )

  const handleSelect = (id: string) => {
    addActiveSession(id)
    addSession(id)
    navigate(`/chat/${id}`)
  }

  const handleNew = async () => {
    try {
      const id = await createSession(undefined, defaultAgent)
      addActiveSession(id)
      addSession(id)
      navigate(`/chat/${id}`)
    } catch (err) {
      console.error("Failed to create session:", err)
    }
  }

  const handleFork = async () => {
    if (!sessionId) return
    try {
      const id = await forkSession()
      addActiveSession(id)
      addSession(id)
      navigate(`/chat/${id}`)
    } catch (err) {
      console.error("Failed to fork session:", err)
    }
  }

  const handleStartRename = (id: string, currentTitle: string | null | undefined) => {
    setRenamingId(id)
    setRenameValue(currentTitle ?? "")
  }

  const handleSaveRename = async (id: string) => {
    const trimmed = renameValue.trim()
    if (trimmed) {
      try {
        await rpcClient.sessionSetTitle(id, trimmed)
        await refetch()
      } catch (err) {
        console.error("Failed to rename session:", err)
      }
    }
    setRenamingId(null)
  }

  const handleDelete = async (id: string) => {
    setDeleting(true)
    try {
      await deleteSession(id)
      removeActiveSession(id)
      removeSession(id)
      if (sessionId === id) navigate("/chat")
      setShowDeleteConfirm(null)
      await refetch()
    } catch (err) {
      console.error("Failed to delete session:", err)
    } finally {
      setDeleting(false)
    }
  }

  return (
    <div className="h-full flex flex-col bg-[var(--bg-base)]">
      {/* New session area */}
      <div className="p-2 border-b border-[var(--border-muted)] space-y-1.5">
        <button
          onClick={handleNew}
          className="w-full flex items-center justify-center gap-1.5 px-3 py-1.5 text-sm rounded-md bg-[var(--accent)] text-white hover:opacity-90 hover:shadow-sm transition-all cursor-pointer select-none"
          style={{ fontWeight: 500 }}
        >
          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          New Session
        </button>

        <div className="flex items-center gap-1">
          <button
            onClick={handleFork}
            disabled={!sessionId}
            className="flex-1 px-2 py-1 text-sm rounded-md bg-[var(--bg-deep)] border border-[var(--border-base)] text-[var(--text-muted)] hover:text-[var(--text-base)] hover:bg-[var(--overlay-hover)] disabled:opacity-40 disabled:cursor-not-allowed transition-colors cursor-pointer select-none"
          >
            Fork
          </button>
          <div className="relative">
            <button
              onClick={() => setShowAgentSelect(!showAgentSelect)}
              className="px-2 py-1 text-xs rounded-md border border-[var(--border-base)] text-[var(--text-muted)] hover:text-[var(--text-base)] hover:bg-[var(--overlay-hover)] transition-colors cursor-pointer select-none flex items-center gap-1"
            >
              <span className="truncate max-w-[60px]">{defaultAgent}</span>
              <svg className={`w-3 h-3 transition-transform ${showAgentSelect ? "rotate-180" : ""}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
              </svg>
            </button>
            {showAgentSelect && (
              <>
                <div className="fixed inset-0 z-10" onClick={() => setShowAgentSelect(false)} />
                <div className="absolute right-0 top-full mt-1 min-w-[120px] bg-[var(--bg-base)] border border-[var(--border-base)] rounded-md shadow-lg z-20 py-1">
                  {agents.map((agent) => (
                    <button
                      key={agent.name}
                      onClick={() => { setDefaultAgent(agent.name); setShowAgentSelect(false) }}
                      className={`w-full text-left px-2.5 py-1.5 text-sm hover:bg-[var(--overlay-hover)] transition-colors cursor-pointer ${
                        defaultAgent === agent.name ? "text-[var(--accent)]" : "text-[var(--text-muted)]"
                      }`}
                    >
                      {agent.name}
                    </button>
                  ))}
                </div>
              </>
            )}
          </div>
        </div>

        {/* Search */}
        <div className="relative">
          <svg className="absolute left-2 top-1/2 -translate-y-1/2 w-3 h-3 text-[var(--icon-muted)] pointer-events-none" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search sessions..."
            className="w-full pl-6 pr-2 py-1.5 text-sm rounded-md border border-[var(--border-base)] bg-[var(--bg-deep)] text-[var(--text-base)] outline-none focus:border-[var(--accent)] transition-colors placeholder:text-[var(--text-faint)]"
            style={{ fontWeight: 440 }}
          />
        </div>
      </div>

      {/* Sessions list */}
      <div className="flex-1 overflow-y-auto">
        {isLoading ? (
          <div className="flex items-center justify-center py-8">
            <Spinner size="sm" />
          </div>
        ) : filteredSessions.length === 0 ? (
          <div className="px-3 py-6 text-center">
            <p className="text-sm text-[var(--text-faint)]">
              {search ? "No sessions match your search" : "No sessions yet"}
            </p>
          </div>
        ) : (
          filteredSessions.map((s) => {
            const isActive = s.id === sessionId
            const displayTitle = s.title ?? "Untitled"
            const timeAgo = s.updatedAt
              ? (() => {
                  const diff = Date.now() - new Date(s.updatedAt).getTime()
                  const mins = Math.floor(diff / 60000)
                  if (mins < 1) return "just now"
                  if (mins < 60) return `${mins}m`
                  const hours = Math.floor(mins / 60)
                  if (hours < 24) return `${hours}h`
                  const days = Math.floor(hours / 24)
                  return `${days}d`
                })()
              : ""

            return (
              <div
                key={s.id}
                className={`group flex items-center gap-1 px-2 py-1.5 cursor-pointer select-none border-b border-[var(--border-muted)] last:border-b-0 transition-colors ${
                  isActive ? "bg-[var(--accent-muted)]" : "hover:bg-[var(--overlay-hover)]"
                }`}
                onClick={() => !renamingId && handleSelect(s.id)}
              >
                {renamingId === s.id ? (
                  <div className="flex-1 min-w-0" onClick={(e) => e.stopPropagation()}>
                    <input
                      type="text"
                      value={renameValue}
                      onChange={(e) => setRenameValue(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") handleSaveRename(s.id)
                        if (e.key === "Escape") setRenamingId(null)
                      }}
                      onBlur={() => handleSaveRename(s.id)}
                      autoFocus
                      className="w-full px-1 py-0.5 text-sm rounded border border-[var(--accent)] bg-[var(--bg-base)] text-[var(--text-base)] outline-none"
                      style={{ fontWeight: 440 }}
                    />
                  </div>
                ) : (
                  <>
                    <div className="flex-1 min-w-0">
                      <div className={`text-sm truncate ${isActive ? "text-[var(--accent)]" : "text-[var(--text-base)]"}`} style={{ fontWeight: 450 }}>
                        {displayTitle}
                      </div>
                      <div className="text-xs text-[var(--text-muted)]">{timeAgo}</div>
                    </div>
                    <div className="hidden group-hover:flex items-center gap-0.5">
                      <button
                        onClick={(e) => { e.stopPropagation(); handleStartRename(s.id, s.title) }}
                        className="p-0.5 rounded text-[var(--icon-muted)] hover:text-[var(--icon-base)] hover:bg-[var(--overlay-hover)] transition-colors"
                        title="Rename"
                      >
                        <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                        </svg>
                      </button>
                      <button
                        onClick={(e) => { e.stopPropagation(); setShowDeleteConfirm(s.id) }}
                        className="p-0.5 rounded text-[var(--icon-muted)] hover:text-red-500 hover:bg-[var(--state-danger-bg)] transition-colors"
                        title="Delete"
                      >
                        <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                        </svg>
                      </button>
                    </div>
                  </>
                )}
              </div>
            )
          })
        )}
      </div>

      {/* Delete confirm dialog */}
      {showDeleteConfirm && (
        <>
          <div className="fixed inset-0 bg-black/30 z-40" onClick={() => setShowDeleteConfirm(null)} />
          <div className="fixed left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 bg-[var(--bg-base)] border border-[var(--border-base)] rounded-lg shadow-lg z-50 p-4 min-w-[200px]">
            <p className="text-xs text-[var(--text-base)] mb-3" style={{ fontWeight: 440 }}>Delete this session?</p>
            <div className="flex gap-2 justify-end">
              <button
                onClick={() => setShowDeleteConfirm(null)}
                className="px-2.5 py-1 text-xs rounded-md border border-[var(--border-base)] text-[var(--text-muted)] hover:text-[var(--text-base)] transition-colors cursor-pointer"
              >
                Cancel
              </button>
              <button
                onClick={() => handleDelete(showDeleteConfirm)}
                disabled={deleting}
                className="px-2.5 py-1 text-xs rounded-md bg-red-500 text-white hover:bg-red-600 disabled:opacity-50 transition-colors cursor-pointer"
              >
                {deleting ? "Deleting..." : "Delete"}
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
