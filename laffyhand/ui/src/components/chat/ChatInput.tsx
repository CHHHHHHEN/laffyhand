import { useRef, useEffect, useState, type KeyboardEvent, type ChangeEvent } from "react"
import { useUiStore, type BusyMode } from "@/stores/ui-store"

interface ChatInputProps {
  onSend: (content: string) => void
  onInterrupt?: (content: string) => void
  onSteer?: (content: string) => void
  onQueue?: (content: string) => void
  onCancel?: () => void
  isStreaming?: boolean
}

const MODE_CONFIG: Record<BusyMode, { label: string; description: string; color: string }> = {
  interrupt: {
    label: "Interrupt",
    description: "Cancel and send new",
    color: "bg-amber-50 dark:bg-amber-900/20 text-amber-700 dark:text-amber-400",
  },
  steer: {
    label: "Steer",
    description: "Guide without interrupting",
    color: "bg-blue-50 dark:bg-blue-900/20 text-blue-700 dark:text-blue-400",
  },
  queue: {
    label: "Queue",
    description: "Send after current response",
    color: "bg-purple-50 dark:bg-purple-900/20 text-purple-700 dark:text-purple-400",
  },
}

export function ChatInput({ onSend, onInterrupt, onSteer, onQueue, onCancel, isStreaming }: ChatInputProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const [inputValue, setInputValue] = useState("")
  const busyMode = useUiStore((s) => s.busyMode)
  const setBusyMode = useUiStore((s) => s.setBusyMode)

  useEffect(() => {
    textareaRef.current?.focus()
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

  return (
    <div className="border-t border-[var(--border-muted)] bg-[var(--bg-base)] px-4 py-3">
      {/* Busy mode selector */}
      {isStreaming && (
        <div className="flex items-center gap-2 mb-2">
          <div className="flex items-center gap-1 bg-[var(--bg-deep)] rounded-md p-0.5 border border-[var(--border-muted)]">
            {(Object.keys(MODE_CONFIG) as BusyMode[]).map((mode) => {
              const config = MODE_CONFIG[mode]
              const isActive = busyMode === mode
              return (
                <button
                  key={mode}
                  type="button"
                  onClick={() => setBusyMode(mode)}
                  title={config.description}
                  className={`flex items-center gap-1 px-2.5 py-1 text-xs rounded-md transition-all duration-150 cursor-pointer select-none ${
                    isActive
                      ? `${config.color} shadow-sm font-medium`
                      : "text-[var(--text-muted)] hover:text-[var(--text-base)] hover:bg-[var(--overlay-hover)]"
                  }`}
                >
                  <span className="font-medium">{config.label}</span>
                </button>
              )
            })}
          </div>
        </div>
      )}

      {/* Input area */}
      <div className="flex items-center gap-2">
        <div className="flex-1 relative">
          <textarea
            ref={textareaRef}
            onChange={handleInputChange}
            onKeyDown={handleKeyDown}
            placeholder="Type a message..."
            rows={1}
            className="w-full resize-none rounded-lg border border-[var(--border-base)] bg-[var(--bg-deep)] px-3 py-2.5 text-sm text-[var(--text-base)] outline-none focus:border-[var(--accent)] transition-colors placeholder:text-[var(--text-faint)]"
            style={{ fontFamily: "var(--font-sans)", fontWeight: 440 }}
          />
        </div>

        {isStreaming && onCancel && (
          <button
            type="button"
            onClick={onCancel}
            title="Cancel"
            className="p-2.5 text-[var(--icon-muted)] hover:text-[var(--state-danger-fg)] hover:bg-[var(--state-danger-bg)] rounded-lg transition-colors cursor-pointer"
          >
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="size-4">
              <path d="M6.28 5.22a.75.75 0 00-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 101.06 1.06L10 11.06l3.72 3.72a.75.75 0 101.06-1.06L11.06 10l3.72-3.72a.75.75 0 00-1.06-1.06L10 8.94 6.28 5.22z" />
            </svg>
          </button>
        )}

        <button
          type="button"
          onClick={handleSubmit}
          disabled={!inputValue.trim()}
          className="flex items-center gap-1.5 px-3 py-2.5 text-sm rounded-lg bg-[var(--accent)] text-white hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed transition-all cursor-pointer"
          style={{ fontWeight: 500 }}
        >
          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 12h14m0 0l-7-7m7 7l-7 7" />
          </svg>
          Send
        </button>
      </div>

      <div className="mt-1 px-1">
        <span className="text-[10px] text-[var(--text-faint)]">Shift+Enter for new line</span>
      </div>
    </div>
  )
}
