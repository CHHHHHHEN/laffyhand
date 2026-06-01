import { create } from "zustand"

export type BusyMode = "interrupt" | "steer" | "queue"

export interface UiState {
  sidebarOpen: boolean
  busyMode: BusyMode
  toggleSidebar: () => void
  setSidebarOpen: (open: boolean) => void
  setBusyMode: (mode: BusyMode) => void
}

export const useUiStore = create<UiState>((set) => ({
  sidebarOpen: true,
  busyMode: "interrupt",

  toggleSidebar: () => set((state) => ({ sidebarOpen: !state.sidebarOpen })),

  setSidebarOpen: (sidebarOpen) => set({ sidebarOpen }),

  setBusyMode: (busyMode) => set({ busyMode }),
}))
