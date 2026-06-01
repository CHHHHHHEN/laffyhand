import { useParams } from "react-router-dom"
import { ChatInput } from "@/components/chat/ChatInput"
import { MessageList } from "@/components/chat/MessageList"
import { useChat } from "@/hooks/use-chat"
import { useCurrentSession } from "@/hooks/use-sessions"
import { useChatStore } from "@/stores/chat-store"
import { Spinner } from "@/components/ui/Spinner"

export function ChatPage() {
  const { sessionId } = useParams()
  const { sendMessage, interruptMessage, steerMessage, queueMessage, cancelStream } = useChat()
  const { isLoading } = useCurrentSession(sessionId)
  const isStreaming = useChatStore((s) => s.isStreaming)
  const messages = useChatStore((s) => s.messages)

  if (!sessionId) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center text-gray-500 dark:text-gray-400 space-y-4">
        <svg className="w-16 h-16" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
        </svg>
        <p className="text-lg">Select or create a session to start</p>
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
