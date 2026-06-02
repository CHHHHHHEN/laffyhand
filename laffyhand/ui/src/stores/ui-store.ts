import { create } from "zustand"

export type BusyMode = "interrupt" | "steer" | "queue"

export interface UiState {
  sidebarOpen: boolean
  todoPanelOpen: boolean
  busyMode: BusyMode
  darkMode: boolean
  toggleSidebar: () => void
  setSidebarOpen: (open: boolean) => void
  toggleTodoPanel: () => void
  setTodoPanelOpen: (open: boolean) => void
  setBusyMode: (mode: BusyMode) => void
  toggleDarkMode: () => void
  setDarkMode: (dark: boolean) => void
}

function getInitialDarkMode(): boolean {
  if (typeof window === "undefined") return false
  try {
    const stored = localStorage.getItem("laffyhand-dark-mode")
    if (stored !== null) return stored === "true"
  } catch {
    // localStorage may not be available in test environments
  }
  try {
    return window.matchMedia("(prefers-color-scheme: dark)").matches
  } catch {
    return false
  }
}

export const useUiStore = create<UiState>((set) => ({
  sidebarOpen: true,
  todoPanelOpen: false,
  busyMode: "interrupt",
  darkMode: getInitialDarkMode(),

  toggleSidebar: () => set((state) => ({ sidebarOpen: !state.sidebarOpen })),

  setSidebarOpen: (sidebarOpen) => set({ sidebarOpen }),

  toggleTodoPanel: () => set((state) => ({ todoPanelOpen: !state.todoPanelOpen })),

  setTodoPanelOpen: (todoPanelOpen) => set({ todoPanelOpen }),

  setBusyMode: (busyMode) => set({ busyMode }),

  toggleDarkMode: () => set((state) => {
    const next = !state.darkMode
    localStorage.setItem("laffyhand-dark-mode", String(next))
    return { darkMode: next }
  }),

  setDarkMode: (darkMode) => {
    localStorage.setItem("laffyhand-dark-mode", String(darkMode))
    set({ darkMode })
  },
}))
