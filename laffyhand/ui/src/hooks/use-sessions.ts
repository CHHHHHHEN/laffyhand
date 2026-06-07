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
    mutationFn: async (sessionId: string) => {
      const result = await rpcClient.sessionFork(sessionId)
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
    // Auto-refresh every 2s while the session is streaming on the server
    // (covers the page-refresh / reconnect scenario where the SSE stream
    // was lost but the server continues processing).
    refetchInterval: (query) => {
      const data = query.state.data
      if (data?.is_streaming) {
        // Don't poll when the frontend has an active SSE stream —
        // SSE events already provide live updates, and polling would
        // overwrite in-progress messages mid-stream (loadMessages
        // resets isStreaming & streaming buffers), causing the
        // finish event to append a duplicate assistant message.
        const [, sid] = query.queryKey
        const chatState = useChatStore.getState()
        const sess = typeof sid === "string" ? chatState.sessions[sid] : undefined
        if (sess?.isStreaming) return false
        return 2000
      }
      return false
    },
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
          dependsOn: t.dependsOn,
          blockedBy: t.blockedBy,
          createdAt: t.createdAt,
          updatedAt: t.updatedAt,
          completedAt: t.completedAt,
          taskToolId: t.taskToolId,
        }))
        useTodoStore.getState().setSessionTasks(sessionId, tasks)
      }).catch(() => {})
    }
  }, [session, sessionId, addSession, loadMessages, setSessionInfoAction])

  return { session, isLoading, isError }
}
