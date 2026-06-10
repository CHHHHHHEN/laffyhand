import { create } from "zustand"
import type { Message, ToolCall, ToolCallStatus, PermissionInfo, ActiveSubagent } from "@/types/session"
import type { SessionUsage } from "@/types/rpc"

export interface TurnUsage {
  input: number
  output: number
  reasoning: number
}

export interface SessionChatState {
  messages: Message[]
  isStreaming: boolean
  streamContent: string
  streamReasoning: string
  streamToolCalls: ToolCall[]
  currentAssistantMessageId: string | null
  error: string | null
  model: string
  sessionUsage: SessionUsage | null
  turnUsage: TurnUsage | null
  _turnStartUsage: SessionUsage | null
  foregroundSubagents: ActiveSubagent[]
  pendingQueue: string[]
}

export interface ChatStore {
  sessions: Record<string, SessionChatState>

  addSession: (sessionId: string) => void
  removeSession: (sessionId: string) => void

  addUserMessage: (sessionId: string, content: string) => void
  startStreaming: (sessionId: string) => void
  appendContent: (sessionId: string, text: string) => void
  setReasoning: (sessionId: string, text: string) => void
  addToolCall: (sessionId: string, toolCall: ToolCall) => void
  updateToolCallStatus: (sessionId: string, id: string, status: ToolCallStatus, result?: string, isError?: boolean) => void
  finalizeMessage: (sessionId: string, usage?: { inputTokens: number; outputTokens: number; reasoningTokens?: number }, sessionUsage?: SessionUsage | null) => void
  setError: (sessionId: string, error: string) => void
  clearMessages: (sessionId: string) => void
  loadMessages: (sessionId: string, messages: Message[]) => void
  setStreaming: (sessionId: string, streaming: boolean) => void
  updateSessionUsage: (sessionId: string, usage: SessionUsage) => void
  setSessionInfo: (sessionId: string, model: string, usage: SessionUsage | null) => void
  enqueueMessage: (sessionId: string, content: string) => void
  dequeueMessage: (sessionId: string) => string | undefined
  hasPendingMessages: (sessionId: string) => boolean
  addPermissionRequest: (sessionId: string, req: PermissionInfo) => void
  resolvePermissionRequest: (sessionId: string, messageId: string, denyReason?: string) => void
  startSubagent: (sessionId: string, event: { id: string; parent_id?: string; agent_type: string; description: string; prompt?: string; depth: number }) => void
  updateSubagent: (sessionId: string, id: string, event: { kind: string; content?: string; tool_name?: string; tool_input?: string }) => void
  endSubagent: (sessionId: string, id: string, event: { status: string; summary?: string; tool_count?: number; input_tokens?: number; output_tokens?: number }) => void
  clearForegroundSubagents: (sessionId: string) => void
}

let messageCounter = 0
export function resetMessageCounter() {
  messageCounter = 0
}
function nextMessageId(): string {
  messageCounter++
  return `msg-${Date.now()}-${messageCounter}`
}

function createInitialSessionState(): SessionChatState {
  return {
    messages: [],
    isStreaming: false,
    streamContent: "",
    streamReasoning: "",
    streamToolCalls: [],
    currentAssistantMessageId: null,
    error: null,
    model: "",
    sessionUsage: null,
    turnUsage: null,
    _turnStartUsage: null,
    foregroundSubagents: [],
    pendingQueue: [],
  }
}

export const useChatStore = create<ChatStore>((set, get) => ({
  sessions: {},

  addSession: (sessionId) =>
    set((state) => {
      if (state.sessions[sessionId]) return state
      return {
        sessions: { ...state.sessions, [sessionId]: createInitialSessionState() },
      }
    }),

  removeSession: (sessionId) =>
    set((state) => {
      const { [sessionId]: _, ...rest } = state.sessions
      return { sessions: rest }
    }),

  setStreaming: (sessionId, streaming) =>
    set((state) => {
      const sess = state.sessions[sessionId]
      if (!sess || sess.isStreaming === streaming) return state
      return {
        sessions: {
          ...state.sessions,
          [sessionId]: { ...sess, isStreaming: streaming },
        },
      }
    }),

  addPermissionRequest: (sessionId, req) =>
    set((state) => {
      const sess = state.sessions[sessionId]
      if (!sess) return state
      const msg: Message = {
        id: nextMessageId(),
        role: "permission-request",
        content: `Allow ${req.permission} '${req.pattern}'?`,
        permissionInfo: req,
        createdAt: Date.now(),
      }
      return {
        sessions: {
          ...state.sessions,
          [sessionId]: { ...sess, messages: [...sess.messages, msg] },
        },
      }
    }),

  resolvePermissionRequest: (sessionId, messageId, denyReason?: string) =>
    set((state) => {
      const sess = state.sessions[sessionId]
      if (!sess) return state
      return {
        sessions: {
          ...state.sessions,
          [sessionId]: {
            ...sess,
            messages: sess.messages.map((msg) =>
              msg.id === messageId && msg.permissionInfo
                ? { ...msg, permissionInfo: { ...msg.permissionInfo, resolved: true, denyReason: denyReason ?? msg.permissionInfo.denyReason } }
                : msg,
            ),
          },
        },
      }
    }),

  addUserMessage: (sessionId, content) =>
    set((state) => {
      const sess = state.sessions[sessionId]
      if (!sess) return state
      return {
        sessions: {
          ...state.sessions,
          [sessionId]: {
            ...sess,
            messages: [
              ...sess.messages,
              {
                id: nextMessageId(),
                role: "user",
                content,
                createdAt: Date.now(),
              },
            ],
            error: null,
          },
        },
      }
    }),

  startStreaming: (sessionId) => {
    const sess = get().sessions[sessionId]
    if (!sess) return
    const id = nextMessageId()
    set({
      sessions: {
        ...get().sessions,
        [sessionId]: {
          ...sess,
          isStreaming: true,
          streamContent: "",
          streamReasoning: "",
          streamToolCalls: [],
          currentAssistantMessageId: id,
          error: null,
          _turnStartUsage: sess.sessionUsage,
        },
      },
    })
  },

  appendContent: (sessionId, text) =>
    set((state) => {
      const sess = state.sessions[sessionId]
      if (!sess) return state
      return {
        sessions: {
          ...state.sessions,
          [sessionId]: { ...sess, streamContent: sess.streamContent + text },
        },
      }
    }),

  setReasoning: (sessionId, text) =>
    set((state) => {
      const sess = state.sessions[sessionId]
      if (!sess) return state
      return {
        sessions: {
          ...state.sessions,
          [sessionId]: { ...sess, streamReasoning: sess.streamReasoning + text },
        },
      }
    }),

  addToolCall: (sessionId, toolCall) =>
    set((state) => {
      const sess = state.sessions[sessionId]
      if (!sess) return state
      return {
        sessions: {
          ...state.sessions,
          [sessionId]: {
            ...sess,
            streamToolCalls: [...sess.streamToolCalls, { ...toolCall, status: "running" as const }],
          },
        },
      }
    }),

  updateToolCallStatus: (sessionId, id, status, result, isError) =>
    set((state) => {
      const sess = state.sessions[sessionId]
      if (!sess) return state
      if (sess.isStreaming) {
        return {
          sessions: {
            ...state.sessions,
            [sessionId]: {
              ...sess,
              streamToolCalls: sess.streamToolCalls.map((tc) =>
                tc.id === id ? { ...tc, status, ...(result !== undefined ? { result } : {}), ...(isError !== undefined ? { isError } : {}) } : tc,
              ),
            },
          },
        }
      }
      return {
        sessions: {
          ...state.sessions,
          [sessionId]: {
            ...sess,
            messages: sess.messages.map((msg) => {
              if (msg.role !== "assistant" || !msg.toolCalls) return msg
              return {
                ...msg,
                toolCalls: msg.toolCalls.map((tc) =>
                  tc.id === id
                    ? { ...tc, status, ...(result !== undefined ? { result } : {}), ...(isError !== undefined ? { isError } : {}) }
                    : tc,
                ),
              }
            }),
          },
        },
      }
    }),

  finalizeMessage: (sessionId, usage, sessionUsage) =>
    set((state) => {
      const sess = state.sessions[sessionId]
      if (!sess) return state

      const content = sess.streamContent || ""
      const reasoning = sess.streamReasoning || undefined

      const finalizedToolCalls = sess.streamToolCalls.length > 0
        ? sess.streamToolCalls
        : undefined

      let turnUsage: TurnUsage | null = null
      const finalUsage = sessionUsage ?? sess.sessionUsage
      if (finalUsage && sess._turnStartUsage) {
        turnUsage = {
          input: finalUsage.total_input - sess._turnStartUsage.total_input,
          output: finalUsage.total_output - sess._turnStartUsage.total_output,
          reasoning: finalUsage.total_reasoning - sess._turnStartUsage.total_reasoning,
        }
      }

      if (!content && !reasoning && !finalizedToolCalls && !sess.isStreaming) {
        return {
          sessions: {
            ...state.sessions,
            [sessionId]: {
              ...sess,
              isStreaming: false,
              sessionUsage: finalUsage,
              turnUsage,
              _turnStartUsage: null,
            },
          },
        }
      }

      const assistantMessage: Message = {
        id: sess.currentAssistantMessageId ?? nextMessageId(),
        role: "assistant",
        content,
        reasoning,
        toolCalls: finalizedToolCalls as Message["toolCalls"],
        subagents: sess.foregroundSubagents.length > 0 ? sess.foregroundSubagents : undefined,
        finishReason: "stop",
        usage,
        createdAt: Date.now(),
      }

      return {
        sessions: {
          ...state.sessions,
          [sessionId]: {
            ...sess,
            messages: [...sess.messages, assistantMessage],
            isStreaming: false,
            streamContent: "",
            streamReasoning: "",
            streamToolCalls: [],
            currentAssistantMessageId: null,
            foregroundSubagents: [],
            sessionUsage: finalUsage,
            turnUsage,
            _turnStartUsage: null,
          },
        },
      }
    }),

  setError: (sessionId, error) =>
    set((state) => {
      const sess = state.sessions[sessionId]
      if (!sess) return state
      return {
        sessions: {
          ...state.sessions,
          [sessionId]: { ...sess, error, isStreaming: false },
        },
      }
    }),

  clearMessages: (sessionId) =>
    set((state) => {
      const sess = state.sessions[sessionId]
      if (!sess) return state
      return {
        sessions: {
          ...state.sessions,
          [sessionId]: {
            ...sess,
            messages: [],
            isStreaming: false,
            streamContent: "",
            streamReasoning: "",
            streamToolCalls: [],
            currentAssistantMessageId: null,
            foregroundSubagents: [],
            error: null,
            turnUsage: null,
            _turnStartUsage: null,
          },
        },
      }
    }),

  loadMessages: (sessionId, messages) =>
    set((state) => {
      const sess = state.sessions[sessionId]
      if (!sess) return state
      return {
        sessions: {
          ...state.sessions,
          [sessionId]: {
            ...sess,
            messages,
            isStreaming: false,
            streamContent: "",
            streamReasoning: "",
            streamToolCalls: [],
            currentAssistantMessageId: null,
            error: null,
            turnUsage: null,
            _turnStartUsage: null,
          },
        },
      }
    }),

  updateSessionUsage: (sessionId, usage) =>
    set((state) => {
      const sess = state.sessions[sessionId]
      if (!sess) return state
      return {
        sessions: {
          ...state.sessions,
          [sessionId]: { ...sess, sessionUsage: usage },
        },
      }
    }),

  setSessionInfo: (sessionId, model, usage) =>
    set((state) => {
      const sess = state.sessions[sessionId]
      if (!sess) return state
      return {
        sessions: {
          ...state.sessions,
          [sessionId]: { ...sess, model, sessionUsage: usage, turnUsage: null, _turnStartUsage: null },
        },
      }
    }),

  enqueueMessage: (sessionId, content) =>
    set((state) => {
      const sess = state.sessions[sessionId]
      if (!sess) return state
      return {
        sessions: {
          ...state.sessions,
          [sessionId]: { ...sess, pendingQueue: [...sess.pendingQueue, content] },
        },
      }
    }),

  dequeueMessage: (sessionId) => {
    const sess = get().sessions[sessionId]
    if (!sess || sess.pendingQueue.length === 0) return undefined
    const [first, ...rest] = sess.pendingQueue
    set({
      sessions: {
        ...get().sessions,
        [sessionId]: { ...sess, pendingQueue: rest },
      },
    })
    return first
  },

  hasPendingMessages: (sessionId) => {
    const sess = get().sessions[sessionId]
    return sess ? sess.pendingQueue.length > 0 : false
  },

  startSubagent: (sessionId, event) =>
    set((state) => {
      const sess = state.sessions[sessionId]
      if (!sess) return state
      const sa: ActiveSubagent = {
        id: event.id,
        parentId: event.parent_id ?? null,
        agentType: event.agent_type,
        description: event.description,
        prompt: event.prompt,
        depth: event.depth,
        status: "running",
        text: "",
        reasoning: "",
        tools: [],
        toolCount: 0,
        inputTokens: 0,
        outputTokens: 0,
        events: [],
      }
      return {
        sessions: {
          ...state.sessions,
          [sessionId]: { ...sess, foregroundSubagents: [...sess.foregroundSubagents, sa] },
        },
      }
    }),

  updateSubagent: (sessionId, id, event) =>
    set((state) => {
      const sess = state.sessions[sessionId]
      if (!sess) return state
      const update = (sa: ActiveSubagent): ActiveSubagent => {
        if (sa.id !== id) return sa
        switch (event.kind) {
          case "text":
            return { ...sa, text: sa.text + (event.content ?? ""), events: [...sa.events, { kind: "text", content: event.content }] }
          case "reasoning":
            return { ...sa, reasoning: sa.reasoning + (event.content ?? ""), events: [...sa.events, { kind: "reasoning", content: event.content }] }
          case "tool":
            return {
              ...sa,
              tools: [...sa.tools, { name: event.tool_name ?? "", input: event.tool_input ?? "" }],
              toolCount: sa.toolCount + 1,
              events: [...sa.events, { kind: "tool", toolName: event.tool_name, toolInput: event.tool_input }],
            }
          case "tool_result": {
            const tools = [...sa.tools]
            // Attach result to the last tool with matching name, or last tool
            for (let i = tools.length - 1; i >= 0; i--) {
              if (!tools[i]!.result && tools[i]!.name === (event.tool_name ?? "")) {
                tools[i] = { ...tools[i]!, result: event.content, isError: false }
                break
              }
            }
            return { ...sa, tools, events: [...sa.events, { kind: "tool_result", toolName: event.tool_name, content: event.content }] }
          }
          case "error":
            return { ...sa, status: "error", text: sa.text + (event.content ?? ""), events: [...sa.events, { kind: "error", content: event.content }] }
          default:
            return sa
        }
      }
      return {
        sessions: {
          ...state.sessions,
          [sessionId]: {
            ...sess,
            foregroundSubagents: sess.foregroundSubagents.map(update),
          },
        },
      }
    }),

  endSubagent: (sessionId, id, event) =>
    set((state) => {
      const sess = state.sessions[sessionId]
      if (!sess) return state
      const update = (sa: ActiveSubagent): ActiveSubagent => {
        if (sa.id !== id) return sa
        return {
          ...sa,
          status: event.status as ActiveSubagent["status"],
          summary: event.summary ?? sa.summary,
          inputTokens: event.input_tokens ?? sa.inputTokens,
          outputTokens: event.output_tokens ?? sa.outputTokens,
        }
      }
      return {
        sessions: {
          ...state.sessions,
          [sessionId]: {
            ...sess,
            foregroundSubagents: sess.foregroundSubagents.map(update),
          },
        },
      }
    }),

  clearForegroundSubagents: (sessionId) =>
    set((state) => {
      const sess = state.sessions[sessionId]
      if (!sess) return state
      return {
        sessions: {
          ...state.sessions,
          [sessionId]: { ...sess, foregroundSubagents: [] },
        },
      }
    }),
}))
