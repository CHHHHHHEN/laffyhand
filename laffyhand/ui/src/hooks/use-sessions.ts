import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { rpcClient } from "@/lib/rpc"
import { useSessionStore } from "@/stores/session-store"
import { useChatStore } from "@/stores/chat-store"
import type { Session, Message } from "@/types/session"
import type { SessionInfo, MessageData } from "@/types/rpc"

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

  const query = useQuery({
    queryKey: ["sessions"],
    queryFn: async () => {
      const result = await rpcClient.sessionList()
      return result.sessions.map(toSession)
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

  const forkMutation = useMutation({
    mutationFn: async () => {
      const result = await rpcClient.sessionFork()
      return result.session_id
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
    forkSession: forkMutation.mutateAsync,
    isCreating: createMutation.isPending,
    isDeleting: deleteMutation.isPending,
    isForking: forkMutation.isPending,
  }
}

function toStoreMessage(m: MessageData): Message {
  const msg: Message = {
    id: m.id,
    role: m.role,
    content: m.content,
    reasoning: m.reasoning,
    createdAt: m.createdAt,
  }
  if (m.toolCalls) {
    msg.toolCalls = m.toolCalls.map((tc) => ({
      id: tc.id,
      name: tc.name,
      arguments:
        typeof tc.arguments === "string"
          ? JSON.parse(tc.arguments)
          : (tc.arguments as Record<string, unknown>),
    }))
  }
  if (m.usage) {
    msg.usage = {
      inputTokens: m.usage.inputTokens ?? 0,
      outputTokens: m.usage.outputTokens ?? 0,
    }
  }
  return msg
}

export function useCurrentSession(sessionId: string | undefined) {
  const setCurrentSessionId = useSessionStore((s) => s.setCurrentSessionId)
  const loadMessages = useChatStore((s) => s.loadMessages)

  const { data: session, isLoading } = useQuery({
    queryKey: ["session", sessionId],
    queryFn: async () => {
      if (!sessionId) return null
      setCurrentSessionId(sessionId)
      const result = await rpcClient.sessionLoad(sessionId)
      if (result.messages) {
        loadMessages(result.messages.map(toStoreMessage))
      }
      return result
    },
    enabled: !!sessionId,
  })

  return { session, isLoading }
}
