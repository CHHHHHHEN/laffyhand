import { create } from "zustand"

export type Theme = "light" | "dark" | "system"

export interface UiState {
  sidebarOpen: boolean
  theme: Theme

  toggleSidebar: () => void
  setSidebarOpen: (open: boolean) => void
  setTheme: (theme: Theme) => void
}

export const useUiStore = create<UiState>((set) => ({
  sidebarOpen: true,
  theme: "system",

  toggleSidebar: () => set((state) => ({ sidebarOpen: !state.sidebarOpen })),

  setSidebarOpen: (sidebarOpen) => set({ sidebarOpen }),

  setTheme: (theme) => set({ theme }),
}))
