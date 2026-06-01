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

export function AppShell() {
  const sidebarOpen = useUiStore((s) => s.sidebarOpen)
  const toggleSidebar = useUiStore((s) => s.toggleSidebar)
  const toggleTodoPanel = useUiStore((s) => s.toggleTodoPanel)
  const taskCount = useTodoStore((s) => s.tasks.length)
  const darkMode = useUiStore((s) => s.darkMode)
  const toggleDarkMode = useUiStore((s) => s.toggleDarkMode)

  const isStreaming = useChatStore((s) => s.isStreaming)

  // Sync dark mode class to <html>
  useEffect(() => {
    document.documentElement.classList.toggle("dark", darkMode)
  }, [darkMode])

  return (
    <div className="flex h-full overflow-hidden">
      {/* 左侧边栏 */}
      <div
        className={`${
          sidebarOpen ? "w-64" : "w-0 overflow-hidden"
        } border-r border-gray-200 dark:border-gray-700 shrink-0 transition-all duration-300 ease-in-out`}
      >
        {sidebarOpen && <Sidebar />}
      </div>

      {/* 主内容区 */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {/* 合并后的顶部栏 — 导航 + 工具栏 */}
        <div className="flex items-center gap-2 px-3 h-10 border-b border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 shrink-0">
          <button
            onClick={toggleSidebar}
            className="p-1.5 rounded-md text-gray-500 hover:text-gray-700 hover:bg-gray-100 dark:hover:text-gray-300 dark:hover:bg-gray-800 transition-colors cursor-pointer"
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
          <span className="text-xs font-medium text-gray-400 dark:text-gray-500 select-none shrink-0">
            Laffyhand
          </span>

          {/* Streaming indicator — 仅有 streaming 时在顶部栏显示简洁提示 */}
          {isStreaming && (
            <>
              <span className="w-px h-4 bg-gray-200 dark:bg-gray-700" />
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

          <button
            onClick={toggleDarkMode}
            className="p-1.5 rounded-md text-gray-500 hover:text-gray-700 hover:bg-gray-100 dark:hover:text-gray-300 dark:hover:bg-gray-800 transition-colors cursor-pointer"
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
            className="p-1.5 rounded-md text-gray-500 hover:text-gray-700 hover:bg-gray-100 dark:hover:text-gray-300 dark:hover:bg-gray-800 transition-colors cursor-pointer relative"
            title="Tasks"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" />
            </svg>
            {taskCount > 0 && (
              <span className="absolute -top-0.5 -right-0.5 bg-amber-500 text-white text-[9px] rounded-full w-4 h-4 flex items-center justify-center">
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
