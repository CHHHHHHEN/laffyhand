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

const MODE_CONFIG: Record<BusyMode, { label: string; icon: string; description: string; color: string }> = {
  interrupt: {
    label: "Interrupt",
    icon: "⚡",
    description: "Cancel current response and send",
    color: "text-amber-600 dark:text-amber-400 bg-amber-50 dark:bg-amber-900/20 border-amber-200 dark:border-amber-800",
  },
  steer: {
    label: "Steer",
    icon: "↗",
    description: "Guide the AI without interrupting",
    color: "text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-900/20 border-blue-200 dark:border-blue-800",
  },
  queue: {
    label: "Queue",
    icon: "📥",
    description: "Send after current response finishes",
    color: "text-purple-600 dark:text-purple-400 bg-purple-50 dark:bg-purple-900/20 border-purple-200 dark:border-purple-800",
  },
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

  const currentMode = MODE_CONFIG[busyMode]
  const submitLabel = isStreaming ? currentMode.label : "Send"

  return (
    <div className="border-t border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 px-4 py-3 transition-colors duration-200">
      {/* Busy mode 选择器 */}
      {isStreaming && (
        <div className="flex items-center gap-2 mb-2.5 animate-[fade-in_0.15s_ease-out]">
          <span className="text-[11px] font-medium text-gray-400 dark:text-gray-500 uppercase tracking-wider mr-1">
            When busy:
          </span>
          <div className="flex items-center gap-1 bg-gray-50 dark:bg-gray-800/50 rounded-lg p-0.5 border border-gray-200 dark:border-gray-700">
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
                      : "text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700/50"
                  }`}
                >
                  <span>{config.icon}</span>
                  <span>{config.label}</span>
                </button>
              )
            })}
          </div>
        </div>
      )}

      {/* 输入区 */}
      <div className="flex items-center gap-2">
        <div className="flex-1 relative">
          <textarea
            ref={textareaRef}
            onChange={handleInputChange}
            onKeyDown={handleKeyDown}
            placeholder={
              isStreaming
                ? "Type a message to steer the AI..."
                : "Type a message..."
            }
            rows={1}
            className="w-full resize-none rounded-xl border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 pl-4 pr-10 py-2.5 text-sm outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-500/15 transition-all placeholder-gray-400 dark:placeholder-gray-500"
          />
        </div>

        {/* 取消按钮 */}
        {isStreaming && onCancel && (
          <button
            type="button"
            onClick={onCancel}
            title="Cancel current response"
            className="self-center p-2.5 text-gray-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-xl transition-colors cursor-pointer"
          >
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="size-5">
              <path d="M6.28 5.22a.75.75 0 00-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 101.06 1.06L10 11.06l3.72 3.72a.75.75 0 101.06-1.06L11.06 10l3.72-3.72a.75.75 0 00-1.06-1.06L10 8.94 6.28 5.22z" />
            </svg>
          </button>
        )}

        {/* 发送按钮 */}
        <Button
          variant={isStreaming ? "secondary" : "primary"}
          onClick={handleSubmit}
          disabled={!inputValue.trim()}
          className={`transition-all duration-150 ${inputValue.trim() ? "opacity-100" : "opacity-50"}`}
        >
          {isStreaming ? currentMode.icon : (
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 12h14m0 0l-7-7m7 7l-7 7" />
            </svg>
          )}
          {' '}
          {submitLabel}
        </Button>
      </div>

      {/* 底部提示 */}
      <div className="flex items-center justify-between mt-1.5 px-1">
        <span className="text-[10px] text-gray-400 dark:text-gray-500 select-none">
          Shift+Enter for new line
        </span>
      </div>
    </div>
  )
}
