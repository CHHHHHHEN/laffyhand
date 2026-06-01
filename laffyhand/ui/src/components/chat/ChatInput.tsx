import { useRef, useEffect, useState, type KeyboardEvent, type ChangeEvent } from "react"
import { Button } from "@/components/ui/Button"
import { useUiStore, type BusyMode } from "@/stores/ui-store"

interface ChatInputProps {
  onSend: (content: string) => void
  onInterrupt?: (content: string) => void
  onSteer?: (content: string) => void
  onQueue?: (content: string) => void
  onCancel?: () => void
  isStreaming?: boolean
}

const MODE_LABELS: Record<BusyMode, string> = {
  interrupt: "Interrupt",
  steer: "Steer",
  queue: "Queue",
}

const MODE_ICONS: Record<BusyMode, string> = {
  interrupt: "⚡",
  steer: "↗",
  queue: "📥",
}

const MODE_DESCRIPTIONS: Record<BusyMode, string> = {
  interrupt: "Cancel current response and send",
  steer: "Guide the AI without interrupting",
  queue: "Send after current response finishes",
}

export function ChatInput({ onSend, onInterrupt, onSteer, onQueue, onCancel, isStreaming }: ChatInputProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const [inputValue, setInputValue] = useState("")
  const busyMode = useUiStore((s) => s.busyMode)
  const setBusyMode = useUiStore((s) => s.setBusyMode)

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

    if (isStreaming) {
      switch (busyMode) {
        case "interrupt":
          onInterrupt?.(content)
          break
        case "steer":
          onSteer?.(content)
          break
        case "queue":
          onQueue?.(content)
          break
      }
    } else {
      onSend(content)
    }
    textarea.value = ""
    setInputValue("")
    textarea.style.height = "auto"
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }

  const handleInputChange = (e: ChangeEvent<HTMLTextAreaElement>) => {
    const value = e.target.value
    setInputValue(value)
    const textarea = textareaRef.current
    if (!textarea) return
    textarea.style.height = "auto"
    textarea.style.height = `${Math.min(textarea.scrollHeight, 200)}px`
  }

  const submitLabel = isStreaming ? MODE_LABELS[busyMode] : "Send"

  return (
    <div className="border-t border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-4 py-3">
      {isStreaming && (
        <div className="flex items-center gap-1 mb-2">
          <span className="text-xs text-gray-400 mr-1">When busy:</span>
          {(Object.keys(MODE_LABELS) as BusyMode[]).map((mode) => (
            <button
              key={mode}
              type="button"
              onClick={() => setBusyMode(mode)}
              title={MODE_DESCRIPTIONS[mode]}
              className={`text-xs px-2 py-1 rounded cursor-pointer transition-colors ${
                busyMode === mode
                  ? "bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300 font-medium"
                  : "text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800"
              }`}
            >
              {MODE_ICONS[mode]} {MODE_LABELS[mode]}
            </button>
          ))}
        </div>
      )}
      <div className="flex items-end gap-2">
        <textarea
          ref={textareaRef}
          onChange={handleInputChange}
          onKeyDown={handleKeyDown}
          placeholder={
            isStreaming
              ? "Type a message..."
              : "Type a message..."
          }
          rows={1}
          className="flex-1 resize-none rounded-lg border border-gray-300 dark:border-gray-600 bg-gray-50 dark:bg-gray-800 px-3 py-2 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 transition-colors"
        />
        {isStreaming && onCancel && (
          <button
            type="button"
            onClick={onCancel}
            title="Cancel current response"
            className="self-center p-2 text-gray-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-md transition-colors cursor-pointer"
          >
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="size-5">
              <path d="M6.28 5.22a.75.75 0 00-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 101.06 1.06L10 11.06l3.72 3.72a.75.75 0 101.06-1.06L11.06 10l3.72-3.72a.75.75 0 00-1.06-1.06L10 8.94 6.28 5.22z" />
            </svg>
          </button>
        )}
        <Button
          variant="primary"
          onClick={handleSubmit}
          disabled={!inputValue.trim()}
          className="transition-all"
        >
          {submitLabel}
        </Button>
      </div>
    </div>
  )
}
