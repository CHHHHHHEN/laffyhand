import { useRef, useEffect, useState, useMemo, type KeyboardEvent, type ChangeEvent } from "react"
import { useUiStore, type BusyMode } from "@/stores/ui-store"
import type { AgentInfo } from "@/types/rpc"

const SLASH_COMMANDS = [
  { command: "/fork", description: "Fork current session into a new one" },
  { command: "/agent <name>", description: "Switch to a different agent type" },
  { command: "/help", description: "Show available commands" },
] as const

interface ChatInputProps {
  onSend: (content: string) => void
  onInterrupt?: (content: string) => void
  onSteer?: (content: string) => void
  onQueue?: (content: string) => void
  onCancel?: () => void
  onFork?: () => void
  agents: AgentInfo[]
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

export function ChatInput({ onSend, onInterrupt, onSteer, onQueue, onCancel, onFork, agents, isStreaming }: ChatInputProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const [inputValue, setInputValue] = useState("")
  const busyMode = useUiStore((s) => s.busyMode)
  const setBusyMode = useUiStore((s) => s.setBusyMode)
  const defaultAgent = useUiStore((s) => s.defaultAgent)
  const setDefaultAgent = useUiStore((s) => s.setDefaultAgent)
  const [showCommands, setShowCommands] = useState(false)
  const [selectedCmdIdx, setSelectedCmdIdx] = useState(0)
  const [agentNotification, setAgentNotification] = useState<string | null>(null)

  const currentAgent = useMemo(
    () => agents.find((a) => a.name === defaultAgent),
    [agents, defaultAgent],
  )
  const agentDisplayName = currentAgent?.name ?? defaultAgent

  const filteredCommands = useMemo(() => {
    if (!inputValue.startsWith("/")) return []
    const partial = inputValue.toLowerCase()
    return SLASH_COMMANDS.filter((c) => c.command.startsWith(partial))
  }, [inputValue])

  useEffect(() => {
    if (inputValue.startsWith("/")) {
      setShowCommands(true)
      setSelectedCmdIdx(0)
    } else {
      setShowCommands(false)
    }
  }, [inputValue])

  let notificationTimer: ReturnType<typeof setTimeout> | null = null
  const showNotification = (msg: string) => {
    setAgentNotification(msg)
    if (notificationTimer) clearTimeout(notificationTimer)
    notificationTimer = setTimeout(() => setAgentNotification(null), 2000)
  }

  const cycleAgent = () => {
    if (agents.length === 0) return
    const idx = agents.findIndex((a) => a.name === defaultAgent)
    const next = agents[(idx + 1) % agents.length]
    if (!next) return
    setDefaultAgent(next.name)
    showNotification(`Agent: ${defaultAgent} → ${next.name}`)
  }

  const executeSlashCommand = (content: string): boolean => {
    const trimmed = content.trim()

    if (trimmed === "/fork") {
      onFork?.()
      return true
    }

    const agentMatch = trimmed.match(/^\/agent\s+(.+)/)
    if (agentMatch) {
      const name = agentMatch[1]!.trim()
      const match = agents.find(
        (a) => a.name.toLowerCase() === name.toLowerCase(),
      )
      if (match) {
        setDefaultAgent(match.name)
        showNotification(`Switched to agent: ${match.name}`)
      }
      return true
    }

    if (trimmed === "/help") {
      const cmdList = SLASH_COMMANDS.map(
        (c) => `• ${c.command} — ${c.description}`,
      ).join("\n")
      showNotification(cmdList)
      return true
    }

    return false
  }

  const handleSubmit = () => {
    const textarea = textareaRef.current
    if (!textarea) return
    const content = textarea.value.trim()
    if (!content) return

    if (content.startsWith("/")) {
      if (executeSlashCommand(content)) {
        textarea.value = ""
        setInputValue("")
        textarea.style.height = "auto"
        return
      }
    }

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
    if (e.key === "Tab" && !e.shiftKey && !inputValue) {
      e.preventDefault()
      cycleAgent()
      return
    }

    if (e.key === "Tab" && showCommands && filteredCommands.length > 0) {
      e.preventDefault()
      const cmd = filteredCommands[selectedCmdIdx]!
      if (cmd.command.endsWith(">")) {
        const prefix = cmd.command.split("<")[0]!
        setInputValue(prefix)
      } else {
        setInputValue(cmd.command + " ")
      }
      return
    }

    if (e.key === "ArrowDown" && showCommands) {
      e.preventDefault()
      setSelectedCmdIdx((p) => Math.min(p + 1, filteredCommands.length - 1))
      return
    }

    if (e.key === "ArrowUp" && showCommands) {
      e.preventDefault()
      setSelectedCmdIdx((p) => Math.max(p - 1, 0))
      return
    }

    if (e.key === "Escape" && showCommands) {
      e.preventDefault()
      setShowCommands(false)
      return
    }

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

  const handleCmdClick = (cmd: string) => {
    if (cmd.endsWith(">")) {
      setInputValue(cmd.split("<")[0]!)
    } else {
      setInputValue(cmd + " ")
    }
    textareaRef.current?.focus()
  }

  return (
    <div className="border-t border-[var(--border-muted)] bg-[var(--bg-base)] px-4 py-3">
      {/* Agent switch notification */}
      {agentNotification && (
        <div className="mb-2 px-3 py-1.5 text-xs rounded-md bg-[var(--accent-muted)] border border-[var(--border-muted)] text-[var(--text-base)]">
          {agentNotification}
        </div>
      )}

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
                  className={`flex items-center gap-1 px-2.5 py-1 text-sm rounded-md transition-all duration-150 cursor-pointer select-none ${
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
        {/* Agent indicator */}
        {agents.length > 0 && (
          <button
            type="button"
            onClick={cycleAgent}
            title={`Agent: ${agentDisplayName} — Click to switch (Tab)`}
            className="flex items-center gap-1.5 px-2.5 py-2 text-xs font-medium rounded-lg border border-[var(--border-base)] bg-[var(--bg-deep)] text-[var(--text-base)] hover:text-[var(--accent)] hover:border-[var(--accent)] transition-all cursor-pointer shrink-0"
          >
            <span className="w-2 h-2 rounded-full bg-[var(--accent)] shrink-0" />
            <span className="max-w-24 truncate">{agentDisplayName}</span>
          </button>
        )}
        <div className="flex-1 relative">
          <textarea
            ref={textareaRef}
            onChange={handleInputChange}
            onKeyDown={handleKeyDown}
            placeholder="Type a message... (Tab to switch agent, / for commands)"
            rows={1}
            className="w-full resize-none rounded-lg border border-[var(--border-base)] bg-[var(--bg-deep)] px-3 py-2.5 text-sm text-[var(--text-base)] outline-none focus:border-[var(--accent)] focus:bg-[var(--bg-base)] transition-all placeholder:text-[var(--text-faint)]"
            style={{ fontFamily: "var(--font-sans)", fontWeight: 440 }}
          />

          {/* Slash command suggestions */}
          {showCommands && filteredCommands.length > 0 && (
            <div className="absolute bottom-full left-0 right-0 mb-1 bg-[var(--bg-base)] border border-[var(--border-muted)] rounded-lg shadow-lg overflow-hidden">
              {filteredCommands.map((cmd, i) => (
                <button
                  key={cmd.command}
                  onClick={() => handleCmdClick(cmd.command)}
                  className={`w-full text-left px-3 py-2 text-sm flex items-center justify-between transition-colors cursor-pointer ${
                    i === selectedCmdIdx
                      ? "bg-[var(--accent-muted)] text-[var(--accent)]"
                      : "text-[var(--text-muted)] hover:bg-[var(--overlay-hover)]"
                  }`}
                >
                  <span className="font-mono">{cmd.command}</span>
                  <span className="text-xs text-[var(--text-faint)] ml-4">{cmd.description}</span>
                </button>
              ))}
            </div>
          )}
        </div>

        {isStreaming && onCancel && (
          <button
            type="button"
            onClick={onCancel}
            title="Cancel"
            className="p-2.5 text-[var(--icon-muted)] hover:text-[var(--state-danger-fg)] hover:bg-[var(--state-danger-bg)] rounded-lg border border-transparent transition-colors cursor-pointer"
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
          className="flex items-center justify-center gap-1.5 px-3.5 py-2.5 text-sm rounded-lg bg-[var(--accent)] text-white hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed transition-all border border-transparent cursor-pointer shrink-0"
          style={{ fontWeight: 500, minWidth: 80 }}
        >
          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 12h14m0 0l-7-7m7 7l-7 7" />
          </svg>
          Send
        </button>
      </div>

      <div className="mt-1 px-1">
        <span className="text-xs text-[var(--text-faint)]">
          Shift+Enter for new line · Tab to switch agent · / for commands
        </span>
      </div>
    </div>
  )
}
