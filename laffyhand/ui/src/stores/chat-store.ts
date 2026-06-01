import { create } from "zustand"
import type { Message, ToolCall, ToolResult } from "@/types/session"
import type { SessionUsage } from "@/types/rpc"

export interface TurnUsage {
  input: number
  output: number
  reasoning: number
}

export interface PermissionRequest {
  requestId: string
  permission: string
  pattern: string
}

export interface ChatState {
  messages: Message[]
  isStreaming: boolean
  streamContent: string
  streamReasoning: string
  streamToolCalls: ToolCall[]
  streamToolResults: ToolResult[]
  currentAssistantMessageId: string | null
  error: string | null

  // Persistent session info
  model: string
  sessionUsage: SessionUsage | null

  // Per-turn token delta tracking
  turnUsage: TurnUsage | null
  _turnStartUsage: SessionUsage | null

  // Queue for busy_mode="queue"
  pendingQueue: string[]

  // Permission request from backend
  pendingPermission: PermissionRequest | null

  addUserMessage: (content: string) => void
  startStreaming: () => void
  appendContent: (text: string) => void
  setReasoning: (text: string) => void
  addToolCall: (toolCall: ToolCall) => void
  addToolResult: (toolResult: ToolResult) => void
  finalizeMessage: (usage?: { inputTokens: number; outputTokens: number }, sessionUsage?: SessionUsage | null) => void
  setError: (error: string) => void
  clearMessages: () => void
  loadMessages: (messages: Message[]) => void
  setSessionInfo: (model: string, usage: SessionUsage | null) => void
  enqueueMessage: (content: string) => void
  dequeueMessage: () => string | undefined
  hasPendingMessages: () => boolean
  setPendingPermission: (req: PermissionRequest | null) => void
}

let messageCounter = 0
export function resetMessageCounter() {
  messageCounter = 0
}
function nextMessageId(): string {
  messageCounter++
  return `msg-${Date.now()}-${messageCounter}`
}

export const useChatStore = create<ChatState>((set, get) => ({
  messages: [],
  isStreaming: false,
  streamContent: "",
  streamReasoning: "",
  streamToolCalls: [],
  streamToolResults: [],
  currentAssistantMessageId: null,
  error: null,
  model: "",
  sessionUsage: null,
  turnUsage: null,
  _turnStartUsage: null,
  pendingQueue: [],
  pendingPermission: null,

  setPendingPermission: (req) => set({ pendingPermission: req }),

  addUserMessage: (content) =>
    set((state) => ({
      messages: [
        ...state.messages,
        {
          id: nextMessageId(),
          role: "user",
          content,
          createdAt: Date.now(),
        },
      ],
      error: null,
    })),

  startStreaming: () => {
    const id = nextMessageId()
    const { sessionUsage } = get()
    set({
      isStreaming: true,
      streamContent: "",
      streamReasoning: "",
      streamToolCalls: [],
      streamToolResults: [],
      currentAssistantMessageId: id,
      error: null,
      _turnStartUsage: sessionUsage,
    })
  },

  appendContent: (text) =>
    set((state) => ({
      streamContent: state.streamContent + text,
    })),

  setReasoning: (text) =>
    set((state) => ({
      streamReasoning: state.streamReasoning + text,
    })),

  addToolCall: (toolCall) =>
    set((state) => ({
      streamToolCalls: [...state.streamToolCalls, toolCall],
    })),

  addToolResult: (toolResult) =>
    set((state) => ({
      streamToolResults: [...state.streamToolResults, toolResult],
    })),

  finalizeMessage: (usage, sessionUsage) =>
    set((state) => {
      // If content empty but reasoning exists, promote reasoning to content
      const content = state.streamContent || state.streamReasoning || ""
      const reasoning = state.streamContent ? (state.streamReasoning || undefined) : undefined

      const assistantMessage: Message = {
        id: state.currentAssistantMessageId ?? nextMessageId(),
        role: "assistant",
        content,
        reasoning,
        toolCalls:
          state.streamToolCalls.length > 0
            ? state.streamToolCalls
            : undefined,
        toolResults:
          state.streamToolResults.length > 0
            ? state.streamToolResults
            : undefined,
        finishReason: "stop",
        usage,
        createdAt: Date.now(),
      }

      // Compute per-turn token delta
      let turnUsage: TurnUsage | null = null
      if (sessionUsage && state._turnStartUsage) {
        turnUsage = {
          input: sessionUsage.total_input - state._turnStartUsage.total_input,
          output: sessionUsage.total_output - state._turnStartUsage.total_output,
          reasoning: sessionUsage.total_reasoning - state._turnStartUsage.total_reasoning,
        }
      }

      return {
        messages: [...state.messages, assistantMessage],
        isStreaming: false,
        streamContent: "",
        streamReasoning: "",
        streamToolCalls: [],
        streamToolResults: [],
        currentAssistantMessageId: null,
        sessionUsage: sessionUsage ?? state.sessionUsage,
        turnUsage,
        _turnStartUsage: null,
      }
    }),

  setError: (error) =>
    set({ error, isStreaming: false }),

  clearMessages: () =>
    set({
      messages: [],
      isStreaming: false,
      streamContent: "",
      streamReasoning: "",
      streamToolCalls: [],
      streamToolResults: [],
      currentAssistantMessageId: null,
      error: null,
      turnUsage: null,
      _turnStartUsage: null,
    }),

  loadMessages: (messages) =>
    set({
      messages,
      isStreaming: false,
      streamContent: "",
      streamReasoning: "",
      streamToolCalls: [],
      streamToolResults: [],
      currentAssistantMessageId: null,
      error: null,
      turnUsage: null,
      _turnStartUsage: null,
    }),

  setSessionInfo: (model, usage) =>
    set({ model, sessionUsage: usage, turnUsage: null, _turnStartUsage: null }),

  enqueueMessage: (content) =>
    set((state) => ({
      pendingQueue: [...state.pendingQueue, content],
    })),

  dequeueMessage: () => {
    const { pendingQueue } = get()
    if (pendingQueue.length === 0) return undefined
    const [first, ...rest] = pendingQueue
    set({ pendingQueue: rest })
    return first
  },

  hasPendingMessages: () => get().pendingQueue.length > 0,
}))
