import { useEffect } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { rpcClient } from "@/lib/rpc"
import { useChatStore } from "@/stores/chat-store"
import { useTodoStore } from "@/stores/todo-store"
import type { Session, Message, TodoItem, ToolCallStatus } from "@/types/session"
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

export function useAgents() {
  const query = useQuery({
    queryKey: ["agents"],
    queryFn: async () => {
      const result = await rpcClient.agentList()
      return result.agents
    },
    staleTime: 60_000,
  })
  return {
    agents: query.data ?? [],
    isLoading: query.isLoading,
    error: query.error?.message ?? null,
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
    mutationFn: async (params?: { title?: string; agent?: string }) => {
      const result = await rpcClient.sessionCreate(params ?? {})
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
    createSession: (title?: string, agent?: string) => createMutation.mutateAsync({ title, agent }),
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
      status: tc.status as ToolCallStatus | undefined,
      result: tc.result,
      isError: tc.isError,
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
  const addSession = useChatStore((s) => s.addSession)
  const loadMessages = useChatStore((s) => s.loadMessages)
  const setSessionInfoAction = useChatStore((s) => s.setSessionInfo)

  const { data: session, isLoading, isError } = useQuery({
    queryKey: ["session", sessionId],
    queryFn: async () => {
      if (!sessionId) return null
      return rpcClient.sessionLoad(sessionId)
    },
    enabled: !!sessionId,
    refetchOnWindowFocus: false,
  })

  useEffect(() => {
    if (session && sessionId) {
      addSession(sessionId)
      setSessionInfoAction(
        sessionId,
        session.model ?? "",
        session.usage ?? null,
      )
      if (session.messages) {
        loadMessages(sessionId, session.messages.map(toStoreMessage))
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
      }).catch(() => {})
    }
  }, [session, sessionId, addSession, loadMessages, setSessionInfoAction])

  // Poll for reconnection when the server is still processing an agent turn
  // after a page refresh (SSE was lost, but server continues running).
  useEffect(() => {
    if (!session?.is_streaming || !sessionId) return

    // Don't poll if we already have an active SSE stream on the frontend
    const sess = useChatStore.getState().sessions[sessionId]
    if (sess?.isStreaming) return

    const interval = setInterval(async () => {
      try {
        const result = await rpcClient.sessionLoad(sessionId)
        addSession(sessionId)
        setSessionInfoAction(sessionId, result.model ?? "", result.usage ?? null)
        if (result.messages) {
          loadMessages(sessionId, result.messages.map(toStoreMessage))
        }
        if (!result.is_streaming) {
          clearInterval(interval)
        }
      } catch {
        clearInterval(interval)
      }
    }, 2000)

    return () => clearInterval(interval)
  }, [session?.is_streaming, sessionId, addSession, loadMessages, setSessionInfoAction])

  return { session, isLoading, isError }
}
