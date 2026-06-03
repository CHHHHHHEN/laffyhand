import { create } from "zustand"

const STORAGE_KEY = "laffyhand-active-sessions"

function loadPersistedIds(): string[] {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

function persistIds(ids: string[]) {
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(ids))
  } catch {
    // quota exceeded or private browsing — best effort
  }
}

export interface SessionState {
  activeSessionId: string | null
  activeSessionIds: string[]
  setActiveSessionId: (id: string | null) => void
  addActiveSession: (id: string) => void
  removeActiveSession: (id: string) => void
}

export const useSessionStore = create<SessionState>((set) => ({
  activeSessionId: null,
  activeSessionIds: loadPersistedIds(),

  setActiveSessionId: (id) => set({ activeSessionId: id }),

  addActiveSession: (id) =>
    set((state) => {
      if (state.activeSessionIds.includes(id)) return state
      const ids = [...state.activeSessionIds, id]
      persistIds(ids)
      return { activeSessionIds: ids }
    }),

  removeActiveSession: (id) =>
    set((state) => {
      const ids = state.activeSessionIds.filter((sid) => sid !== id)
      persistIds(ids)
      return { activeSessionIds: ids }
    }),
}))
