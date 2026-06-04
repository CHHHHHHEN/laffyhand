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
  denyReason?: string
}

export interface Message {
  id: string
  role: "user" | "assistant" | "system" | "tool" | "permission-request"
  content: string
  reasoning?: string
  toolCalls?: ToolCall[]
  finishReason?: string
  usage?: { inputTokens: number; outputTokens: number; reasoningTokens?: number }
  permissionInfo?: PermissionInfo
  createdAt: number
}

export type ToolCallStatus = "pending" | "running" | "completed" | "error"

export interface ToolCall {
  id: string
  name: string
  arguments: Record<string, unknown>
  status?: ToolCallStatus
  result?: string
  isError?: boolean
}

export interface SubagentEvent {
  kind: "text" | "reasoning" | "tool" | "tool_result" | "error"
  content?: string
  toolName?: string
  toolInput?: string
}

export interface ActiveSubagent {
  id: string
  parentId: string | null
  agentType: string
  description: string
  mode: "foreground" | "background"
  depth: number
  status: "running" | "completed" | "error" | "cancelled"
  text: string
  reasoning: string
  tools: { name: string; input: string }[]
  toolCount: number
  summary?: string
  inputTokens: number
  outputTokens: number
}

export interface StreamChunk {
  type: "reasoning" | "content" | "tool_calls" | "finish" | "error"
  text: string
  finishReason?: string
  usage?: { inputTokens: number; outputTokens: number; reasoningTokens?: number }
  toolCalls?: ToolCall[]
}
