import { create } from "zustand"
import type { TodoItem } from "@/types/session"

export interface TodoState {
  /** sessionId -> tasks */
  taskMap: Record<string, TodoItem[]>
  setSessionTasks: (sessionId: string, tasks: TodoItem[]) => void
  addTask: (sessionId: string, task: TodoItem) => void
  updateTask: (sessionId: string, taskId: string, updates: Partial<TodoItem>) => void
  removeTask: (sessionId: string, taskId: string) => void
  clearSessionTasks: (sessionId: string) => void
}

export const useTodoStore = create<TodoState>((set) => ({
  taskMap: {},

  setSessionTasks: (sessionId, tasks) =>
    set((state) => ({
      taskMap: { ...state.taskMap, [sessionId]: tasks },
    })),

  addTask: (sessionId, task) =>
    set((state) => {
      const current = state.taskMap[sessionId] ?? []
      return {
        taskMap: { ...state.taskMap, [sessionId]: [...current, task] },
      }
    }),

  updateTask: (sessionId, taskId, updates) =>
    set((state) => {
      const current = state.taskMap[sessionId]
      if (!current) return state
      return {
        taskMap: {
          ...state.taskMap,
          [sessionId]: current.map((t) =>
            t.id === taskId ? { ...t, ...updates } : t,
          ),
        },
      }
    }),

  removeTask: (sessionId, taskId) =>
    set((state) => {
      const current = state.taskMap[sessionId]
      if (!current) return state
      return {
        taskMap: {
          ...state.taskMap,
          [sessionId]: current.filter((t) => t.id !== taskId),
        },
      }
    }),

  clearSessionTasks: (sessionId) =>
    set((state) => {
      const { [sessionId]: _, ...rest } = state.taskMap
      return { taskMap: rest }
    }),
}))
