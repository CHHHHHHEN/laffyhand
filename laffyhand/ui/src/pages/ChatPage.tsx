import { useEffect, useCallback } from "react"
import { useParams, useNavigate } from "react-router-dom"
import { ChatInput } from "@/components/chat/ChatInput"
import { MessageList } from "@/components/chat/MessageList"
import { useChat } from "@/hooks/use-chat"
import { useCurrentSession } from "@/hooks/use-sessions"
import { useChatStore } from "@/stores/chat-store"
import { useSessionStore } from "@/stores/session-store"
import { Spinner } from "@/components/ui/Spinner"

export function ChatPage() {
  const { sessionId } = useParams()
  const navigate = useNavigate()
  const { sendMessage, interruptMessage, steerMessage, queueMessage, cancelStream } = useChat()
  const { isLoading, session, isError } = useCurrentSession(sessionId)

  const setActiveSessionId = useSessionStore((s) => s.setActiveSessionId)
  const addActiveSession = useSessionStore((s) => s.addActiveSession)

  useEffect(() => {
    if (sessionId) {
      setActiveSessionId(sessionId)
      addActiveSession(sessionId)
    }
  }, [sessionId, setActiveSessionId, addActiveSession])

  const sessionState = useChatStore((s) => (sessionId ? s.sessions[sessionId] : undefined))
  const isStreaming = sessionState?.isStreaming ?? false
  const messages = sessionState?.messages ?? []

  useEffect(() => {
    if (isError) {
      navigate("/chat", { replace: true })
    }
  }, [isError, navigate])

  const retryLastMessage = useCallback(() => {
    if (!sessionId) return
    const state = useChatStore.getState()
    const sess = state.sessions[sessionId]
    if (!sess) return
    const lastUserMsg = [...sess.messages].reverse().find((m) => m.role === "user")
    if (lastUserMsg) {
      sendMessage(lastUserMsg.content)
    }
  }, [sendMessage, sessionId])

  useEffect(() => {
    const title = session?.title
      ? `${session.title} — Laffyhand`
      : "Laffyhand"
    document.title = title
  }, [session?.title])

  if (!sessionId) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center text-[var(--text-muted)] select-none">
        <div className="flex flex-col items-center gap-5 max-w-xs text-center">
          <div className="w-14 h-14 rounded-2xl bg-[var(--bg-layer-1)] flex items-center justify-center border border-[var(--border-muted)]">
            <svg className="w-7 h-7 text-[var(--icon-muted)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
            </svg>
          </div>
          <div className="space-y-1">
            <p className="text-sm text-[var(--text-muted)]" style={{ fontWeight: 500 }}>Select or create a session</p>
            <p className="text-xs text-[var(--text-faint)] leading-relaxed">Use the sidebar or press Ctrl+K to search sessions</p>
          </div>
        </div>
      </div>
    )
  }

  if (isLoading && messages.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <Spinner />
      </div>
    )
  }

  return (
    <div className="flex-1 flex flex-col min-h-0">
      {session?.is_streaming && !isStreaming && (
        <div className="flex items-center gap-2 px-4 py-1.5 text-xs text-amber-700 dark:text-amber-400 bg-amber-50/80 dark:bg-amber-900/20 border-b border-amber-200/50 dark:border-amber-700/30 shrink-0 backdrop-blur-sm">
          <span className="relative flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-75" />
            <span className="relative inline-flex rounded-full h-2 w-2 bg-amber-500" />
          </span>
          <span className="font-medium" style={{ fontWeight: 500 }}>Reconnecting</span>
          <span className="text-amber-600/70 dark:text-amber-400/70">— session is still processing on the server</span>
        </div>
      )}
      <MessageList sessionId={sessionId} onRetry={retryLastMessage} />
      <ChatInput
        onSend={sendMessage}
        onInterrupt={interruptMessage}
        onSteer={steerMessage}
        onQueue={queueMessage}
        onCancel={cancelStream}
        isStreaming={isStreaming}
      />
    </div>
  )
}
