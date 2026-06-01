import { create } from "zustand"

export type BusyMode = "interrupt" | "steer" | "queue"

export interface UiState {
  sidebarOpen: boolean
  todoPanelOpen: boolean
  busyMode: BusyMode
  toggleSidebar: () => void
  setSidebarOpen: (open: boolean) => void
  toggleTodoPanel: () => void
  setTodoPanelOpen: (open: boolean) => void
  setBusyMode: (mode: BusyMode) => void
}

export const useUiStore = create<UiState>((set) => ({
  sidebarOpen: true,
  todoPanelOpen: false,
  busyMode: "interrupt",

  toggleSidebar: () => set((state) => ({ sidebarOpen: !state.sidebarOpen })),

  setSidebarOpen: (sidebarOpen) => set({ sidebarOpen }),

  toggleTodoPanel: () => set((state) => ({ todoPanelOpen: !state.todoPanelOpen })),

  setTodoPanelOpen: (todoPanelOpen) => set({ todoPanelOpen }),

  setBusyMode: (busyMode) => set({ busyMode }),
}))
