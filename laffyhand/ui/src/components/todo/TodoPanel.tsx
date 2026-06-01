import { useMemo } from "react"
import { useTodoStore } from "@/stores/todo-store"
import { useUiStore } from "@/stores/ui-store"
import { TodoColumn } from "./TodoColumn"
import type { TodoStatus } from "@/types/session"

const COLUMNS: TodoStatus[] = ["blocked", "pending", "in_progress", "completed", "cancelled"]

export function TodoPanel() {
  const tasks = useTodoStore((s) => s.tasks)
  const todoPanelOpen = useUiStore((s) => s.todoPanelOpen)
  const setTodoPanelOpen = useUiStore((s) => s.setTodoPanelOpen)

  const grouped = useMemo(() => {
    const map: Record<TodoStatus, typeof tasks> = {
      blocked: [], pending: [], in_progress: [], completed: [], cancelled: [],
    }
    for (const t of tasks) {
      const bucket = map[t.status] ?? map.pending
      bucket.push(t)
    }
    return map
  }, [tasks])

  const totalCount = tasks.length

  return (
    <div
      className={`${
        todoPanelOpen ? "w-72" : "w-0 overflow-hidden"
      } border-l border-gray-200 dark:border-gray-700 shrink-0 transition-all duration-300 ease-in-out bg-white dark:bg-gray-900`}
    >
      {todoPanelOpen && (
        <div className="w-72 h-full flex flex-col">
          {/* header */}
          <div className="flex items-center justify-between px-3 h-10 border-b border-gray-200 dark:border-gray-700 shrink-0">
            <span className="text-xs font-semibold text-gray-600 dark:text-gray-300">
              Tasks ({totalCount})
            </span>
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
