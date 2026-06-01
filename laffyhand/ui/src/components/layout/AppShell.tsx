import { Outlet } from "react-router-dom"
import { Sidebar } from "./Sidebar"
import { ErrorBoundary } from "@/components/ui/ErrorBoundary"
import { useUiStore } from "@/stores/ui-store"
import { TodoPanel } from "@/components/todo/TodoPanel"
import { useTodoStore } from "@/stores/todo-store"

export function AppShell() {
  const sidebarOpen = useUiStore((s) => s.sidebarOpen)
  const toggleSidebar = useUiStore((s) => s.toggleSidebar)
  const toggleTodoPanel = useUiStore((s) => s.toggleTodoPanel)
  const taskCount = useTodoStore((s) => s.tasks.length)

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
        {/* 顶部栏 */}
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
          <span className="text-xs font-medium text-gray-400 dark:text-gray-500 select-none">
            Laffyhand
          </span>
          <div className="flex-1" />
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
