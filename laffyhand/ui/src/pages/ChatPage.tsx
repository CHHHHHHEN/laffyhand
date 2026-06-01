import { useEffect } from "react"
import { useParams } from "react-router-dom"
import { ChatInput } from "@/components/chat/ChatInput"
import { MessageList } from "@/components/chat/MessageList"
import { StatusBar } from "@/components/chat/StatusBar"
import { useChat } from "@/hooks/use-chat"
import { useCurrentSession } from "@/hooks/use-sessions"
import { useChatStore } from "@/stores/chat-store"
import { Spinner } from "@/components/ui/Spinner"

export function ChatPage() {
  const { sessionId } = useParams()
  const { sendMessage, interruptMessage, steerMessage, queueMessage, cancelStream } = useChat()
  const { isLoading, session } = useCurrentSession(sessionId)
  const isStreaming = useChatStore((s) => s.isStreaming)
  const messages = useChatStore((s) => s.messages)

  // Update page title with session name
  useEffect(() => {
    const title = session?.title
      ? `${session.title} — Laffyhand`
      : "Laffyhand"
    document.title = title
  }, [session?.title])

  if (!sessionId) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center text-gray-500 dark:text-gray-400 space-y-4 animate-[fade-in_0.3s_ease-out]">
        <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-blue-50 to-indigo-100 dark:from-blue-900/20 dark:to-indigo-900/20 flex items-center justify-center">
          <svg className="w-8 h-8 text-blue-400 dark:text-blue-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
          </svg>
        </div>
        <div className="text-center">
          <p className="text-sm font-medium text-gray-500 dark:text-gray-400">Select or create a session to start</p>
          <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">Use the sidebar or press Ctrl+K to search</p>
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
      <StatusBar />
      <MessageList />
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
