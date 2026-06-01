import { Outlet } from "react-router-dom"
import { Sidebar } from "./Sidebar"
import { ErrorBoundary } from "@/components/ui/ErrorBoundary"
import { useUiStore } from "@/stores/ui-store"
import { TodoPanel } from "@/components/todo/TodoPanel"
import { useTodoStore } from "@/stores/todo-store"
import { useChatStore } from "@/stores/chat-store"
import { ConfigPanel } from "@/components/chat/ConfigPanel"

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

  const isStreaming = useChatStore((s) => s.isStreaming)
  const model = useChatStore((s) => s.model)
  const sessionUsage = useChatStore((s) => s.sessionUsage)
  const turnUsage = useChatStore((s) => s.turnUsage)

  const showStatus = model || sessionUsage
  const totalTokens = sessionUsage
    ? sessionUsage.total_input + sessionUsage.total_output
    : 0
  const ctxSize = sessionUsage?.context_size ?? 0

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
        {/* 合并后的顶部栏 */}
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

          {/* Session status info */}
          {showStatus && (
            <>
              <span className="w-px h-4 bg-gray-200 dark:bg-gray-700" />

              {model && (
                <span className="font-mono flex items-center gap-1.5 text-[11px] text-gray-500 dark:text-gray-400 shrink-0" title="Model">
                  <span className="w-1.5 h-1.5 rounded-full bg-blue-500" />
                  {model}
                </span>
              )}

              {turnUsage && (
                <span className="flex items-center gap-1.5 text-[11px] text-gray-500 dark:text-gray-400 shrink-0" title="This turn / Cumulative / Context size">
                  <svg className="w-3 h-3 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4" />
                  </svg>
                  <span className="font-medium">{formatTokens(turnUsage.input + turnUsage.output)}</span>
                  <span className="text-gray-400 dark:text-gray-500">/ {formatTokens(totalTokens)}</span>
                  <span className="text-gray-300 dark:text-gray-500">/ {formatTokens(ctxSize)}</span>
                </span>
              )}

              {!turnUsage && sessionUsage && (
                <span className="flex items-center gap-1.5 text-[11px] text-gray-500 dark:text-gray-400 shrink-0" title="Cumulative tokens / Context size">
                  <svg className="w-3 h-3 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4" />
                  </svg>
                  <span className="font-medium">{formatTokens(totalTokens)}</span>
                  <span className="text-gray-400 dark:text-gray-500">/ {formatTokens(ctxSize)}</span>
                </span>
              )}

              {/* Streaming indicator */}
              {isStreaming && (
                <span className="flex items-center gap-1.5 text-green-600 dark:text-green-400 text-[11px] shrink-0">
                  <span className="relative flex h-2 w-2">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75" />
                    <span className="relative inline-flex rounded-full h-2 w-2 bg-green-500" />
                  </span>
                  <span className="font-medium">Streaming</span>
                </span>
              )}
            </>
          )}

          <div className="flex-1 min-w-2" />

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

        <ErrorBoundary>
          <Outlet />
        </ErrorBoundary>
      </div>

      {/* 右侧 TODO 面板 */}
      <TodoPanel />
    </div>
  )
}
