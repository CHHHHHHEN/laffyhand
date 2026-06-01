import type { TodoItem, TodoStatus } from "@/types/session"
import { TodoCard } from "./TodoCard"

const columnStyles: Record<TodoStatus, { label: string; headerClass: string; containerClass: string }> = {
  blocked: {
    label: "Blocked",
    headerClass: "text-red-600 dark:text-red-400",
    containerClass: "bg-red-50 dark:bg-red-950/20",
  },
  pending: {
    label: "Pending",
    headerClass: "text-gray-500 dark:text-gray-400",
    containerClass: "bg-gray-50 dark:bg-gray-900/50",
  },
  in_progress: {
    label: "In Progress",
    headerClass: "text-blue-600 dark:text-blue-400",
    containerClass: "bg-blue-50 dark:bg-blue-950/20",
  },
  completed: {
    label: "Completed",
    headerClass: "text-green-600 dark:text-green-400",
    containerClass: "bg-green-50 dark:bg-green-950/20",
  },
  cancelled: {
    label: "Cancelled",
    headerClass: "text-gray-400 dark:text-gray-500",
    containerClass: "bg-gray-50 dark:bg-gray-900/30",
  },
}

interface TodoColumnProps {
  status: TodoStatus
  tasks: TodoItem[]
}

export function TodoColumn({ status, tasks }: TodoColumnProps) {
  const style = columnStyles[status] ?? columnStyles.pending!

  return (
    <div className={`rounded-lg p-2 ${style.containerClass}`}>
      <div className={`text-xs font-semibold mb-2 px-1 ${style.headerClass}`}>
        {style.label} ({tasks.length})
      </div>
      <div className="space-y-2">
        {tasks.map((task) => (
          <TodoCard key={task.id} task={task} />
        ))}
        {tasks.length === 0 && (
          <div className="text-[10px] text-gray-400 dark:text-gray-500 text-center py-4">
            —
          </div>
        )}
      </div>
    </div>
  )
}
