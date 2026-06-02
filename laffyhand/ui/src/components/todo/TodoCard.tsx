import type { TodoItem } from "@/types/session"

const priorityColors: Record<string, string> = {
  high: "text-red-600 dark:text-red-400",
  medium: "text-yellow-600 dark:text-yellow-400",
  low: "text-gray-500 dark:text-gray-400",
}

const statusIcons: Record<string, string> = {
  pending: "○",
  in_progress: "◉",
  completed: "✓",
  cancelled: "✕",
  blocked: "⊘",
}

interface TodoCardProps {
  task: TodoItem
}

export function TodoCard({ task }: TodoCardProps) {
  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 px-3 py-2.5 text-xs shadow-sm hover:border-gray-300 dark:hover:border-gray-600 hover:shadow-md transition-all duration-150">
      <div className="flex items-start justify-between gap-2">
        <span className="text-gray-800 dark:text-gray-200 break-words flex-1 leading-relaxed">
          {task.content}
        </span>
        <span className={`shrink-0 font-semibold text-sm ${priorityColors[task.priority] ?? ""}`}>
          {statusIcons[task.status] ?? "○"}
        </span>
      </div>
      {task.blockedBy.length > 0 && (
        <div className="mt-1.5 flex items-center gap-1 text-[10px] text-red-500 dark:text-red-400">
          <svg className="w-2.5 h-2.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z" />
          </svg>
          <span>blocked by: {task.blockedBy.map((id) => id.slice(0, 8)).join(", ")}</span>
        </div>
      )}
      {task.dependsOn.length > 0 && task.blockedBy.length === 0 && (
        <div className="mt-1.5 flex items-center gap-1 text-[10px] text-gray-400 dark:text-gray-500">
          <svg className="w-2.5 h-2.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
          </svg>
          <span>depends on: {task.dependsOn.map((id) => id.slice(0, 8)).join(", ")}</span>
        </div>
      )}
    </div>
  )
}
