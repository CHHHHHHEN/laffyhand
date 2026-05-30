import { useEffect } from "react"
import { useParams } from "react-router-dom"
import { ChatInput } from "@/components/chat/ChatInput"
import { MessageList } from "@/components/chat/MessageList"
import { useChat } from "@/hooks/use-chat"
import { useCurrentSession } from "@/hooks/use-sessions"
import { useChatStore } from "@/stores/chat-store"
import { Spinner } from "@/components/ui/Spinner"

export function ChatPage() {
  const { sessionId } = useParams()
  const { sendMessage, cancelStream } = useChat()
  const { isLoading } = useCurrentSession(sessionId)
  const isStreaming = useChatStore((s) => s.isStreaming)
  const clearMessages = useChatStore((s) => s.clearMessages)

  useEffect(() => {
    if (!sessionId) {
      clearMessages()
    }
  }, [sessionId, clearMessages])

  if (!sessionId) {
    return (
      <div className="flex-1 flex items-center justify-center text-gray-400 dark:text-gray-500">
        <p>Select or create a session to start</p>
      </div>
    )
  }

  if (isLoading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <Spinner />
      </div>
    )
  }

  return (
    <div className="flex-1 flex flex-col h-full">
      <MessageList />
      <div className="flex items-center gap-2 px-4">
        {isStreaming && (
          <button
            onClick={cancelStream}
            className="text-sm text-red-500 hover:text-red-700 cursor-pointer mb-3"
          >
            Cancel
          </button>
        )}
      </div>
      <ChatInput onSend={sendMessage} disabled={isStreaming} />
    </div>
  )
}
