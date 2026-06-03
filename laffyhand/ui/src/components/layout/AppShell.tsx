import { Outlet } from "react-router-dom"
import { Sidebar } from "./Sidebar"
import { ErrorBoundary } from "@/components/ui/ErrorBoundary"
import { useUiStore } from "@/stores/ui-store"
import { TodoPanel } from "@/components/todo/TodoPanel"
import { useTodoStore } from "@/stores/todo-store"
import { useChatStore } from "@/stores/chat-store"
import { ConfigPanel } from "@/components/chat/ConfigPanel"
import { SubagentFooter } from "@/components/chat/SubagentFooter"
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
  const taskCount = useTodoStore((s) => s.tasks.length)
  const darkMode = useUiStore((s) => s.darkMode)
  const toggleDarkMode = useUiStore((s) => s.toggleDarkMode)

  const isStreaming = useChatStore((s) => s.isStreaming)
  const model = useChatStore((s) => s.model)
  const sessionUsage = useChatStore((s) => s.sessionUsage)
  const turnUsage = useChatStore((s) => s.turnUsage)

  // Sync dark mode class to <html>
  useEffect(() => {
    document.documentElement.classList.toggle("dark", darkMode)
  }, [darkMode])

  const ctxSize = sessionUsage?.context_size ?? 0
  const contextTokens = sessionUsage?.curr_context_usage ?? 0

  return (
    <div className="flex h-full overflow-hidden bg-white dark:bg-gray-900 transition-colors duration-200">
      {/* 左侧边栏 */}
      <div
        className={`${
          sidebarOpen ? "w-64" : "w-0 overflow-hidden"
        } border-r border-gray-200 dark:border-gray-800 shrink-0 transition-all duration-300 ease-in-out`}
      >
        {sidebarOpen && <Sidebar />}
      </div>

      {/* 主内容区 */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {/* 合并后的顶部栏 — 导航 + 工具栏 */}
        <div className="flex items-center gap-1.5 px-2 h-11 border-b border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 shrink-0 select-none">
          <button
            onClick={toggleSidebar}
            className="p-1.5 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100 dark:hover:text-gray-300 dark:hover:bg-gray-800 transition-colors cursor-pointer"
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
          <span className="text-xs font-semibold text-gray-400 dark:text-gray-500 tracking-wide select-none shrink-0">
            LAFFYHAND
          </span>

          {/* Model + Token usage — 上下文信息 */}
          {(model || sessionUsage) && (
            <>
              <span className="w-px h-4 bg-gray-200 dark:bg-gray-700 mx-1 shrink-0" />
              {model && (
                <span className="font-mono flex items-center gap-1.5 text-[11px] text-gray-500 dark:text-gray-400 shrink-0" title="Model">
                  <span className="w-1.5 h-1.5 rounded-full bg-blue-500 shrink-0" />
                  <span className="truncate max-w-[120px]">{model}</span>
                </span>
              )}

              {turnUsage && (
                <>
                  <span className="text-gray-300 dark:text-gray-600 select-none text-xs shrink-0">|</span>

                  <span className="flex items-center gap-1.5 text-gray-500 dark:text-gray-400 text-[11px] shrink-0" title="Context usage / Context size">
                    <svg className="w-3 h-3 text-gray-400 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4" />
                    </svg>
                    <span className="font-medium">{formatTokens(contextTokens)}</span>
                    <span className="text-gray-400 dark:text-gray-500">/ {formatTokens(ctxSize)}</span>
                    {ctxSize > 0 && contextTokens > 0 && (
                      <span className={`text-[10px] font-medium ${
                        contextTokens / ctxSize > 0.8
                          ? "text-amber-500 dark:text-amber-400"
                          : "text-gray-400 dark:text-gray-500"
                      }`}>
                        ({Math.round((contextTokens / ctxSize) * 100)}%)
                      </span>
                    )}
                    {ctxSize > 0 && contextTokens > 0 && (
                      <span className="w-14 h-1.5 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden shrink-0">
                        <span
                          className={`block h-full rounded-full transition-all duration-300 ${
                            contextTokens / ctxSize > 0.8
                              ? "bg-amber-400"
                              : contextTokens / ctxSize > 0.5
                                ? "bg-blue-400"
                                : "bg-green-400"
                          }`}
                          style={{ width: `${Math.min((contextTokens / ctxSize) * 100, 100)}%` }}
                        />
                      </span>
                    )}
                  </span>

                  <span className="flex items-center gap-1 text-gray-500 dark:text-gray-400 text-[11px] shrink-0">
                    <span className="flex items-center gap-0.5" title="Input tokens">
                      <svg className="w-3 h-3 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 11l5-5m0 0l5 5m-5-5v12" />
                      </svg>
                      <span>{formatTokens(turnUsage.input)}</span>
                    </span>
                    <svg className="w-2.5 h-2.5 text-gray-300 dark:text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
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
                    <span className="flex items-center gap-1 text-gray-500 dark:text-gray-400 text-[11px] shrink-0" title="Reasoning tokens">
                      <span className="text-gray-300 dark:text-gray-600 select-none shrink-0">·</span>
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
                  <span className="text-gray-300 dark:text-gray-600 select-none text-xs shrink-0">|</span>
                  <span className="flex items-center gap-1.5 text-gray-500 dark:text-gray-400 text-[11px] shrink-0" title="Context usage / Context size">
                    <svg className="w-3 h-3 text-gray-400 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4" />
                    </svg>
                    <span className="font-medium">{formatTokens(contextTokens)}</span>
                    <span className="text-gray-400 dark:text-gray-500">/ {formatTokens(ctxSize)}</span>
                    {ctxSize > 0 && contextTokens > 0 && (
                      <span className={`text-[10px] font-medium ${
                        contextTokens / ctxSize > 0.8
                          ? "text-amber-500 dark:text-amber-400"
                          : "text-gray-400 dark:text-gray-500"
                      }`}>
                        ({Math.round((contextTokens / ctxSize) * 100)}%)
                      </span>
                    )}
                    {ctxSize > 0 && contextTokens > 0 && (
                      <span className="w-14 h-1.5 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden shrink-0">
                        <span
                          className={`block h-full rounded-full transition-all duration-300 ${
                            contextTokens / ctxSize > 0.8
                              ? "bg-amber-400"
                              : contextTokens / ctxSize > 0.5
                                ? "bg-blue-400"
                                : "bg-green-400"
                          }`}
                          style={{ width: `${Math.min((contextTokens / ctxSize) * 100, 100)}%` }}
                        />
                      </span>
                    )}
                  </span>
                </>
              )}
            </>
          )}

          {/* Streaming indicator */}
          {isStreaming && (
            <>
              <span className="w-px h-4 bg-gray-200 dark:bg-gray-700 mx-1 shrink-0" />
              <span className="flex items-center gap-1.5 text-green-600 dark:text-green-400 text-[11px] shrink-0">
                <span className="relative flex h-2 w-2">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75" />
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-green-500" />
                </span>
                <span className="font-medium">Streaming</span>
              </span>
            </>
          )}

          <div className="flex-1 min-w-2" />

          {/* 右侧操作按钮组 */}
          <button
            onClick={toggleDarkMode}
            className="p-1.5 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100 dark:hover:text-gray-300 dark:hover:bg-gray-800 transition-colors cursor-pointer"
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
            className="p-1.5 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100 dark:hover:text-gray-300 dark:hover:bg-gray-800 transition-colors cursor-pointer relative"
            title="Tasks"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" />
            </svg>
            {taskCount > 0 && (
              <span className="absolute -top-0.5 -right-0.5 bg-amber-500 text-white text-[9px] font-bold rounded-full min-w-[16px] h-4 flex items-center justify-center px-1 shadow-sm">
                {taskCount > 9 ? "9+" : taskCount}
              </span>
            )}
          </button>
        </div>

        <div className="flex-1 flex flex-col min-h-0">
          <ErrorBoundary>
            <Outlet />
          </ErrorBoundary>
        </div>
        <SubagentFooter />
      </div>

      {/* 右侧 TODO 面板 */}
      <TodoPanel />
    </div>
  )
}
