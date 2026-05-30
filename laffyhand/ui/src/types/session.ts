export interface Session {
  id: string
  title: string | null
  status: SessionStatus
  messageCount: number
  turnCount: number
  createdAt: number
  updatedAt?: number
}

export type SessionStatus = "active" | "archived" | "deleted"

export interface Message {
  id: string
  role: "user" | "assistant" | "system" | "tool"
  content: string
  reasoning?: string
  toolCalls?: ToolCall[]
  toolResults?: ToolResult[]
  finishReason?: string
  usage?: { inputTokens: number; outputTokens: number }
  createdAt: number
}

export interface ToolCall {
  id: string
  name: string
  arguments: Record<string, unknown>
}

export interface ToolResult {
  id: string
  name: string
  result: string
  isError?: boolean
}

export interface StreamChunk {
  type: "reasoning" | "content" | "tool_calls" | "tool_result" | "finish" | "error"
  text: string
  finishReason?: string
  usage?: { inputTokens: number; outputTokens: number }
  toolCalls?: ToolCall[]
  toolResults?: ToolResult[]
}
