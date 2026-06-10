import { Outlet } from "react-router-dom"
import { Sidebar } from "./Sidebar"
import { ErrorBoundary } from "@/components/ui/ErrorBoundary"
import { useUiStore } from "@/stores/ui-store"
import { TodoPanel } from "@/components/todo/TodoPanel"
import { useTodoStore } from "@/stores/todo-store"
import { useChatStore } from "@/stores/chat-store"
import { useSessionStore } from "@/stores/session-store"
import { ConfigPanel } from "@/components/chat/ConfigPanel"
import { SessionTabs } from "@/components/chat/SessionTabs"
import { useEffect } from "react"

function formatTokens(n: number): string {
  if (n < 1000) return `${n}`
  const k = (n / 1000).toFixed(1).replace(/\.0$/, "")
  return `${k}k`
}

export function AppShell() {
  const sidebarOpen = useUiStore((s) => s.sidebarOpen)
  const toggleSidebar = useUiStore((s) => s.toggleSidebar)
  const toggleTodoPanel = useUiStore((s) => s.toggleTodoPanel)
  const activeSessionId = useSessionStore((s) => s.activeSessionId)
  const taskCount = useTodoStore((s) =>
    activeSessionId ? (s.taskMap[activeSessionId] ?? []).length : 0,
  )
  const darkMode = useUiStore((s) => s.darkMode)
  const toggleDarkMode = useUiStore((s) => s.toggleDarkMode)

  const sessionState = useChatStore((s) => activeSessionId ? s.sessions[activeSessionId] : undefined)!
  const isStreaming = sessionState?.isStreaming ?? false
  const model = sessionState?.model ?? ""
  const sessionUsage = sessionState?.sessionUsage ?? null
  const turnUsage = sessionState?.turnUsage ?? null

  useEffect(() => {
    document.documentElement.classList.toggle("dark", darkMode)
  }, [darkMode])

  const ctxSize = sessionUsage?.context_size ?? 0
  const contextTokens = sessionUsage?.curr_context_usage ?? 0

  return (
    <div className="flex h-full overflow-hidden bg-[var(--bg-base)]">
      <div
        className={`${
          sidebarOpen ? "w-64" : "w-0 overflow-hidden"
        } border-r border-[var(--border-muted)] shrink-0 transition-all duration-300 ease-in-out`}
      >
        {sidebarOpen && <Sidebar />}
      </div>

      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        <div className="flex items-center gap-1.5 px-3 h-10 border-b border-[var(--border-muted)] bg-[var(--bg-base)] shrink-0 select-none">
          <button
            onClick={toggleSidebar}
            className="p-1 rounded-md text-[var(--icon-muted)] hover:text-[var(--icon-base)] hover:bg-[var(--overlay-hover)] transition-colors cursor-pointer"
            title={sidebarOpen ? "Close sidebar" : "Open sidebar"}
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              {sidebarOpen ? (
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 19l-7-7 7-7m8 14l-7-7 7-7" />
              ) : (
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 5l7 7-7 7M5 5l7 7-7 7" />
              )}
            </svg>
          </button>
          <span className="text-sm font-semibold text-[var(--text-faint)] tracking-wide select-none shrink-0">
            LAFFYHAND
          </span>

          {(model || sessionUsage) && (
            <>
              <span className="w-px h-3 bg-[var(--border-muted)] mx-1 shrink-0" />
              {model && (
                <span className="font-mono flex items-center gap-1.5 text-[11px] text-[var(--text-muted)] shrink-0" title="Model">
                  <span className="w-1.5 h-1.5 rounded-full bg-[var(--accent)] shrink-0" />
                  <span className="truncate max-w-[120px]" style={{ fontWeight: 440 }}>{model}</span>
                </span>
              )}

              {turnUsage && (
                <>
                  <span className="text-[var(--border-strong)] select-none text-xs shrink-0">|</span>

                  <span className="flex items-center gap-1.5 text-[var(--text-muted)] text-[11px] shrink-0" title="Context usage / Context size">
                    <svg className="w-3 h-3 text-[var(--icon-muted)] shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4" />
                    </svg>
                    <span className="font-medium" style={{ fontWeight: 500 }}>{formatTokens(contextTokens)}</span>
                    <span className="text-[var(--text-faint)]">/ {formatTokens(ctxSize)}</span>
                  </span>

                  <span className="flex items-center gap-1 text-[var(--text-muted)] text-[11px] shrink-0">
                    <span className="flex items-center gap-0.5" title="Input tokens">
                      <svg className="w-3 h-3 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 11l5-5m0 0l5 5m-5-5v12" />
                      </svg>
                      <span>{formatTokens(turnUsage.input)}</span>
                    </span>
                    <svg className="w-2.5 h-2.5 text-[var(--border-strong)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 13l-5 5m0 0l-5-5m5 5V6" />
                    </svg>
                    <span className="flex items-center gap-0.5" title="Output tokens">
                      <svg className="w-3 h-3 text-orange-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 13l-5 5m0 0l-5-5m5 5V6" />
                      </svg>
                      <span>{formatTokens(turnUsage.output)}</span>
                    </span>
                  </span>

                  {turnUsage.reasoning > 0 && (
                    <span className="flex items-center gap-1 text-[var(--text-muted)] text-[11px] shrink-0" title="Reasoning tokens">
                      <span className="text-[var(--border-strong)] select-none shrink-0">·</span>
                      <span className="flex items-center gap-0.5">
                        <svg className="w-3 h-3 text-purple-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
                        </svg>
                        <span>{formatTokens(turnUsage.reasoning)}</span>
                      </span>
                    </span>
                  )}
                </>
              )}

              {!turnUsage && sessionUsage && (
                <>
                  <span className="text-[var(--border-strong)] select-none text-xs shrink-0">|</span>
                  <span className="flex items-center gap-1.5 text-[var(--text-muted)] text-[11px] shrink-0" title="Context usage / Context size">
                    <svg className="w-3 h-3 text-[var(--icon-muted)] shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4" />
                    </svg>
                    <span className="font-medium" style={{ fontWeight: 500 }}>{formatTokens(contextTokens)}</span>
                    <span className="text-[var(--text-faint)]">/ {formatTokens(ctxSize)}</span>
                  </span>
                </>
              )}
            </>
          )}

          {isStreaming && (
            <>
              <span className="w-px h-3 bg-[var(--border-muted)] mx-1 shrink-0" />
              <span className="flex items-center gap-1.5 text-green-600 dark:text-green-400 text-[11px] shrink-0">
                <span className="relative flex h-2 w-2">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75" />
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-green-500" />
                </span>
                <span className="font-medium" style={{ fontWeight: 500 }}>Streaming</span>
              </span>
            </>
          )}

          <div className="flex-1 min-w-2" />

          <button
            onClick={toggleDarkMode}
            className="p-1 rounded-md text-[var(--icon-muted)] hover:text-[var(--icon-base)] hover:bg-[var(--overlay-hover)] transition-colors cursor-pointer"
            title={darkMode ? "Switch to light mode" : "Switch to dark mode"}
          >
            {darkMode ? (
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
              </svg>
            ) : (
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
              </svg>
            )}
          </button>

          <ConfigPanel />

          <button
            onClick={toggleTodoPanel}
            className="p-1 rounded-md text-[var(--icon-muted)] hover:text-[var(--icon-base)] hover:bg-[var(--overlay-hover)] transition-colors cursor-pointer relative"
            title="Tasks"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" />
            </svg>
            {taskCount > 0 && (
              <span className="absolute -top-0.5 -right-0.5 bg-amber-500 text-white text-[9px] font-bold rounded-full min-w-[16px] h-4 flex items-center justify-center px-1">
                {taskCount > 9 ? "9+" : taskCount}
              </span>
            )}
          </button>
        </div>

        <SessionTabs />

        <div className="flex-1 flex flex-col min-h-0">
          <ErrorBoundary>
            <Outlet />
          </ErrorBoundary>
        </div>
      </div>

      <TodoPanel />
    </div>
  )
}
