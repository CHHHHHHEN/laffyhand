import { useNavigate, useParams } from "react-router-dom"
import { useSessions } from "@/hooks/use-sessions"
import { useSessionStore } from "@/stores/session-store"
import { Button } from "@/components/ui/Button"
import { Spinner } from "@/components/ui/Spinner"

export function Sidebar() {
  const navigate = useNavigate()
  const { sessionId } = useParams()
  const { sessions, isLoading, createSession, isCreating } = useSessions()
  const currentSessionId = useSessionStore((s) => s.currentSessionId)

  const handleNewSession = async () => {
    const id = await createSession(undefined)
    navigate(`/chat/${id}`)
  }

  return (
    <div className="h-full flex flex-col bg-gray-50 dark:bg-gray-900">
      <div className="p-3 border-b border-gray-200 dark:border-gray-700">
        <Button
          onClick={handleNewSession}
          disabled={isCreating}
          size="sm"
          className="w-full"
        >
          {isCreating ? "Creating..." : "+ New Session"}
        </Button>
      </div>

      <div className="flex-1 overflow-y-auto p-2 space-y-1">
        {isLoading && (
          <div className="flex justify-center py-4">
            <Spinner size="sm" />
          </div>
        )}

        {sessions.map((s) => (
          <button
            key={s.id}
            onClick={() => navigate(`/chat/${s.id}`)}
            className={`w-full text-left px-3 py-2 rounded-md text-sm transition-colors cursor-pointer ${
              (sessionId ?? currentSessionId) === s.id
                ? "bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300"
                : "text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-800"
            }`}
          >
            <div className="truncate font-medium">
              {s.title || "Untitled"}
            </div>
            <div className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">
              {s.messageCount} messages
            </div>
          </button>
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
