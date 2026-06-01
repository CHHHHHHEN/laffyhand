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
    <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 px-3 py-2 text-xs shadow-sm">
      <div className="flex items-start justify-between gap-2">
        <span className="text-gray-800 dark:text-gray-200 break-words flex-1 leading-relaxed">
          {task.content}
        </span>
        <span className={`shrink-0 font-semibold ${priorityColors[task.priority] ?? ""}`}>
          {statusIcons[task.status] ?? "○"}
        </span>
      </div>
      {task.blockedBy.length > 0 && (
        <div className="mt-1 text-[10px] text-red-500 dark:text-red-400">
          blocked by: {task.blockedBy.map((id) => id.slice(0, 8)).join(", ")}
        </div>
      )}
      {task.dependsOn.length > 0 && task.blockedBy.length === 0 && (
        <div className="mt-1 text-[10px] text-gray-400 dark:text-gray-500">
          depends on: {task.dependsOn.map((id) => id.slice(0, 8)).join(", ")}
        </div>
      )}
    </div>
  )
}
