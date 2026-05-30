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
  const { sendMessage, steerMessage, cancelStream } = useChat()
  const { isLoading } = useCurrentSession(sessionId)
  const isStreaming = useChatStore((s) => s.isStreaming)
  const messages = useChatStore((s) => s.messages)

  if (!sessionId) {
    return (
      <div className="flex-1 flex items-center justify-center text-gray-400 dark:text-gray-500">
        <p>Select or create a session to start</p>
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
    <div className="flex-1 flex flex-col h-full">
      <StatusBar />
      <MessageList />
      <ChatInput
        onSend={sendMessage}
        onSteer={steerMessage}
        onCancel={cancelStream}
        isStreaming={isStreaming}
      />
    </div>
  )
}
