import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { rpcClient } from "@/lib/rpc"
import { useSessionStore } from "@/stores/session-store"
import type { Session } from "@/types/session"
import type { SessionInfo } from "@/types/rpc"

function toSession(rpc: SessionInfo): Session {
  return {
    id: rpc.id,
    title: rpc.title,
    status: rpc.status as Session["status"],
    messageCount: rpc.message_count,
    turnCount: rpc.turn_count,
    createdAt: rpc.created_at,
    updatedAt: rpc.updated_at,
  }
}

export function useSessions() {
  const queryClient = useQueryClient()
  const setSessions = useSessionStore((s) => s.setSessions)
  const setLoading = useSessionStore((s) => s.setLoading)

  const query = useQuery({
    queryKey: ["sessions"],
    queryFn: async () => {
      setLoading(true)
      try {
        const result = await rpcClient.sessionList()
        const sessions = result.sessions.map(toSession)
        setSessions(sessions)
        return sessions
      } finally {
        setLoading(false)
      }
    },
    refetchOnMount: true,
  })

  const createMutation = useMutation({
    mutationFn: async (title?: string) => {
      const result = await rpcClient.sessionCreate(
        title ? { title } : undefined,
      )
      return result.session_id
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["sessions"] })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: async (sessionId: string) => {
      await rpcClient.sessionDelete(sessionId)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["sessions"] })
    },
  })

  return {
    sessions: query.data ?? [],
    isLoading: query.isLoading,
    error: query.error?.message ?? null,
    refetch: query.refetch,
    createSession: createMutation.mutateAsync,
    deleteSession: deleteMutation.mutateAsync,
    isCreating: createMutation.isPending,
    isDeleting: deleteMutation.isPending,
  }
}

export function useCurrentSession(sessionId: string | undefined) {
  const setCurrentSessionId = useSessionStore((s) => s.setCurrentSessionId)

  const { data: session, isLoading } = useQuery({
    queryKey: ["session", sessionId],
    queryFn: async () => {
      if (!sessionId) return null
      setCurrentSessionId(sessionId)
      const result = await rpcClient.sessionLoad(sessionId)
      return result
    },
    enabled: !!sessionId,
  })

  return { session, isLoading }
}
