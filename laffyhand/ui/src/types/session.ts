export interface Session {
  id: string
  title: string | null
  status: SessionStatus
  messageCount: number
  turnCount: number
  createdAt: string
  updatedAt?: string
}

export type SessionStatus = "active" | "archived" | "deleted"

export type TodoStatus = "pending" | "in_progress" | "completed" | "cancelled" | "blocked"
export type TodoPriority = "high" | "medium" | "low"

export interface TodoItem {
  id: string
  sessionId: string
  content: string
  status: TodoStatus
  priority: TodoPriority
  dependsOn: string[]
  blockedBy: string[]
  createdAt: string
  updatedAt: string
  completedAt: string | null
  taskToolId: string | null
}

export interface PermissionInfo {
  requestId: string
  permission: string
  pattern: string
  resolved?: boolean
}

export interface Message {
  id: string
  role: "user" | "assistant" | "system" | "tool" | "permission-request"
  content: string
  reasoning?: string
  toolCalls?: ToolCall[]
  toolResults?: ToolResult[]
  finishReason?: string
  usage?: { inputTokens: number; outputTokens: number }
  permissionInfo?: PermissionInfo
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
