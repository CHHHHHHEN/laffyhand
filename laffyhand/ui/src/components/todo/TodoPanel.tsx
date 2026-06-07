import { useMemo } from "react"
import { useTodoStore } from "@/stores/todo-store"
import { useUiStore } from "@/stores/ui-store"
import { useSessionStore } from "@/stores/session-store"
import { TodoColumn } from "./TodoColumn"
import type { TodoItem, TodoStatus } from "@/types/session"

const COLUMNS: TodoStatus[] = ["blocked", "pending", "in_progress", "completed"]
const EMPTY_TASKS: TodoItem[] = []

export function TodoPanel() {
  const activeSessionId = useSessionStore((s) => s.activeSessionId)
  const tasks = useTodoStore((s) =>
    activeSessionId ? (s.taskMap[activeSessionId] ?? EMPTY_TASKS) : EMPTY_TASKS,
  )
  const todoPanelOpen = useUiStore((s) => s.todoPanelOpen)
  const setTodoPanelOpen = useUiStore((s) => s.setTodoPanelOpen)

  const grouped = useMemo(() => {
    const map: Record<TodoStatus, typeof tasks> = {
      blocked: [], pending: [], in_progress: [], completed: [],
    }
    for (const t of tasks) {
      const bucket = map[t.status] ?? map.pending
      bucket.push(t)
    }
    return map
  }, [tasks])

  const totalCount = tasks.length
  const activeCount = tasks.filter((t) => t.status === "in_progress" || t.status === "pending").length

  return (
    <div
      className={`${
        todoPanelOpen ? "w-72" : "w-0 overflow-hidden"
      } border-l border-gray-200 dark:border-gray-800 shrink-0 transition-all duration-300 ease-in-out bg-white dark:bg-gray-900`}
    >
      {todoPanelOpen && (
        <div className="w-72 h-full flex flex-col">
          {/* header */}
          <div className="flex items-center justify-between px-3 h-11 border-b border-gray-200 dark:border-gray-800 shrink-0">
            <span className="text-xs font-semibold text-gray-600 dark:text-gray-300">
              Tasks
              <span className="text-gray-400 dark:text-gray-500 font-normal ml-1">({totalCount})</span>
            </span>
            {activeCount > 0 && (
              <span className="text-[10px] text-blue-500 dark:text-blue-400 font-medium">
                {activeCount} active
              </span>
            )}
            <button
              onClick={() => setTodoPanelOpen(false)}
              className="p-1 rounded text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 cursor-pointer"
              title="Close tasks panel"
            >
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
          {/* columns */}
          <div className="flex-1 overflow-y-auto p-2 space-y-3">
            {COLUMNS.map((status) => (
              <TodoColumn key={status} status={status} tasks={grouped[status] ?? []} />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
