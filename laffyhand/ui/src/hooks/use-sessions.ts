import { useEffect } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { rpcClient } from "@/lib/rpc"
import { useSessionStore } from "@/stores/session-store"
import { useChatStore } from "@/stores/chat-store"
import { useTodoStore } from "@/stores/todo-store"
import type { Session, Message, TodoItem } from "@/types/session"
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

function safeParseJSON(s: string): Record<string, unknown> {
  try {
    return JSON.parse(s)
  } catch {
    return {}
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
          ? safeParseJSON(tc.arguments)
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
      return rpcClient.sessionLoad(sessionId)
    },
    enabled: !!sessionId,
  })

  useEffect(() => {
    if (session && sessionId) {
      setCurrentSessionId(sessionId)
      useChatStore.getState().setSessionInfo(
        session.model ?? "",
        session.usage ?? null,
      )
      if (session.messages) {
        loadMessages(session.messages.map(toStoreMessage))
      }
      rpcClient.todoList(sessionId).then((result) => {
        const tasks: TodoItem[] = result.tasks.map((t) => ({
          id: t.id,
          sessionId: t.sessionId,
          content: t.content,
          status: t.status as TodoItem["status"],
          priority: t.priority as TodoItem["priority"],
          dependsOn: t.dependsOn,
          blockedBy: t.blockedBy,
          createdAt: t.createdAt,
          updatedAt: t.updatedAt,
          completedAt: t.completedAt,
          taskToolId: t.taskToolId,
        }))
        useTodoStore.getState().setTasks(tasks)
      }).catch(() => {
        // best effort
      })
    }
  }, [session, sessionId, setCurrentSessionId, loadMessages])

  return { session, isLoading }
}
