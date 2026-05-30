import { create } from "zustand"
import type { Session } from "@/types/session"

export interface SessionState {
  sessions: Session[]
  currentSessionId: string | null
  isLoading: boolean
  error: string | null

  setSessions: (sessions: Session[]) => void
  addSession: (session: Session) => void
  removeSession: (id: string) => void
  updateSession: (id: string, updates: Partial<Session>) => void
  setCurrentSessionId: (id: string | null) => void
  setLoading: (loading: boolean) => void
  setError: (error: string | null) => void
}

export const useSessionStore = create<SessionState>((set) => ({
  sessions: [],
  currentSessionId: null,
  isLoading: false,
  error: null,

  setSessions: (sessions) => set({ sessions }),

  addSession: (session) =>
    set((state) => ({ sessions: [session, ...state.sessions] })),

  removeSession: (id) =>
    set((state) => ({
      sessions: state.sessions.filter((s) => s.id !== id),
      currentSessionId:
        state.currentSessionId === id ? null : state.currentSessionId,
    })),

  updateSession: (id, updates) =>
    set((state) => ({
      sessions: state.sessions.map((s) =>
        s.id === id ? { ...s, ...updates } : s,
      ),
    })),

  setCurrentSessionId: (id) => set({ currentSessionId: id }),

  setLoading: (isLoading) => set({ isLoading }),

  setError: (error) => set({ error }),
}))
