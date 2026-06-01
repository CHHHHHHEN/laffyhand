import { create } from "zustand"
import type { TodoItem } from "@/types/session"

export interface TodoState {
  tasks: TodoItem[]
  setTasks: (tasks: TodoItem[]) => void
  addTask: (task: TodoItem) => void
  updateTask: (taskId: string, updates: Partial<TodoItem>) => void
  removeTask: (taskId: string) => void
  clearTasks: () => void
}

export const useTodoStore = create<TodoState>((set) => ({
  tasks: [],

  setTasks: (tasks) => set({ tasks }),

  addTask: (task) =>
    set((state) => ({ tasks: [...state.tasks, task] })),

  updateTask: (taskId, updates) =>
    set((state) => ({
      tasks: state.tasks.map((t) =>
        t.id === taskId ? { ...t, ...updates } : t,
      ),
    })),

  removeTask: (taskId) =>
    set((state) => ({
      tasks: state.tasks.filter((t) => t.id !== taskId),
    })),

  clearTasks: () => set({ tasks: [] }),
}))
