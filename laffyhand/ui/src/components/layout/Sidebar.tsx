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

  const handleNewSession = async () => {
    const id = await createSession(undefined)
    navigate(`/chat/${id}`)
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

  const handleFork = async () => {
    const targetId = sessionId ?? currentSessionId
    if (!targetId) return
    const childId = await forkSession()
    navigate(`/chat/${childId}`)
  }

  return (
    <div className="h-full flex flex-col bg-gray-50 dark:bg-gray-900">
      <div className="p-3 border-b border-gray-200 dark:border-gray-700 space-y-2">
        <Button
          onClick={handleNewSession}
          disabled={isCreating}
          size="sm"
          className="w-full"
        >
          {isCreating ? "Creating..." : "+ New Session"}
        </Button>
        {(sessionId ?? currentSessionId) && (
          <Button
            onClick={handleFork}
            disabled={isForking}
            variant="secondary"
            size="sm"
            className="w-full"
          >
            {isForking ? "Forking..." : "Fork"}
          </Button>
        )}
      </div>

      <div className="flex-1 overflow-y-auto p-2 space-y-1">
        {isLoading && (
          <div className="flex justify-center py-4">
            <Spinner size="sm" />
          </div>
        )}

        {sessions.map((s) => (
          <div
            key={s.id}
            className="group relative"
          >
            <button
              onClick={() => navigate(`/chat/${s.id}`)}
              className={`w-full text-left px-3 py-2 rounded-md text-sm transition-colors cursor-pointer ${
                (sessionId ?? currentSessionId) === s.id
                  ? "bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300"
                  : "text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-800"
              }`}
            >
              <div className="truncate font-medium pr-6">
                {s.title || "Untitled"}
              </div>
              <div className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">
                {s.messageCount} messages
              </div>
            </button>
            <button
              onClick={(e) => handleDelete(e, s.id)}
              className="absolute right-1 top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100 p-1 rounded text-gray-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/30 transition-opacity cursor-pointer"
              title="Delete session"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
              </svg>
            </button>
          </div>
        ))}

        {!isLoading && sessions.length === 0 && (
          <p className="text-xs text-gray-400 text-center py-4">
            No sessions yet
          </p>
        )}
      </div>
    </div>
  )
}
