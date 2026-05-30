import { create } from "zustand"
import type { Message, ToolCall, ToolResult } from "@/types/session"

export interface ChatState {
  messages: Message[]
  isStreaming: boolean
  streamContent: string
  streamReasoning: string
  streamToolCalls: ToolCall[]
  streamToolResults: ToolResult[]
  currentAssistantMessageId: string | null
  error: string | null

  addUserMessage: (content: string) => void
  startStreaming: () => void
  appendContent: (text: string) => void
  setReasoning: (text: string) => void
  addToolCall: (toolCall: ToolCall) => void
  addToolResult: (toolResult: ToolResult) => void
  finalizeMessage: (usage?: { inputTokens: number; outputTokens: number }) => void
  setError: (error: string) => void
  clearMessages: () => void
  loadMessages: (messages: Message[]) => void
}

let messageCounter = 0
export function resetMessageCounter() {
  messageCounter = 0
}
function nextMessageId(): string {
  messageCounter++
  return `msg-${Date.now()}-${messageCounter}`
}

export const useChatStore = create<ChatState>((set) => ({
  messages: [],
  isStreaming: false,
  streamContent: "",
  streamReasoning: "",
  streamToolCalls: [],
  streamToolResults: [],
  currentAssistantMessageId: null,
  error: null,

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
    set({
      isStreaming: true,
      streamContent: "",
      streamReasoning: "",
      streamToolCalls: [],
      streamToolResults: [],
      currentAssistantMessageId: id,
      error: null,
    })
  },

  appendContent: (text) =>
    set((state) => ({
      streamContent: state.streamContent + text,
    })),

  setReasoning: (text) =>
    set(() => ({
      streamReasoning: text,
    })),

  addToolCall: (toolCall) =>
    set((state) => ({
      streamToolCalls: [...state.streamToolCalls, toolCall],
    })),

  addToolResult: (toolResult) =>
    set((state) => ({
      streamToolResults: [...state.streamToolResults, toolResult],
    })),

  finalizeMessage: (usage) =>
    set((state) => {
      const assistantMessage: Message = {
        id: state.currentAssistantMessageId ?? nextMessageId(),
        role: "assistant",
        content: state.streamContent,
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

      return {
        messages: [...state.messages, assistantMessage],
        isStreaming: false,
        streamContent: "",
        streamReasoning: "",
        streamToolCalls: [],
        streamToolResults: [],
        currentAssistantMessageId: null,
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
    }),
}))
