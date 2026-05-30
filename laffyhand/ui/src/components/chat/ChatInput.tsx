import { useRef, useEffect, type KeyboardEvent } from "react"
import { Button } from "@/components/ui/Button"

interface ChatInputProps {
  onSend: (content: string) => void
  onSteer?: (content: string) => void
  onCancel?: () => void
  isStreaming?: boolean
}

export function ChatInput({ onSend, onSteer, onCancel, isStreaming }: ChatInputProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.focus()
    }
  }, [])

  const handleSubmit = () => {
    const textarea = textareaRef.current
    if (!textarea) return
    const content = textarea.value.trim()
    if (!content) return

    if (isStreaming && onSteer) {
      onSteer(content)
    } else {
      onSend(content)
    }
    textarea.value = ""
    textarea.style.height = "auto"
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }

  const handleInput = () => {
    const textarea = textareaRef.current
    if (!textarea) return
    textarea.style.height = "auto"
    textarea.style.height = `${Math.min(textarea.scrollHeight, 200)}px`
  }

  return (
    <div className="flex items-end gap-2 border-t border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-4 py-3">
      <textarea
        ref={textareaRef}
        onInput={handleInput}
        onKeyDown={handleKeyDown}
        placeholder={
          isStreaming
            ? "Type to steer the AI..."
            : "Type a message..."
        }
        rows={1}
        className="flex-1 resize-none rounded-lg border border-gray-300 dark:border-gray-600 bg-gray-50 dark:bg-gray-800 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-blue-500"
      />
      {isStreaming && onCancel && (
        <button
          type="button"
          onClick={onCancel}
          title="Cancel current response"
          className="self-center p-1 text-gray-400 hover:text-red-500 transition-colors cursor-pointer"
        >
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="size-5">
            <path d="M6.28 5.22a.75.75 0 00-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 101.06 1.06L10 11.06l3.72 3.72a.75.75 0 101.06-1.06L11.06 10l3.72-3.72a.75.75 0 00-1.06-1.06L10 8.94 6.28 5.22z" />
          </svg>
        </button>
      )}
      <Button
        variant={isStreaming ? "primary" : "primary"}
        onClick={handleSubmit}
      >
        {isStreaming ? "Steer" : "Send"}
      </Button>
    </div>
  )
}
