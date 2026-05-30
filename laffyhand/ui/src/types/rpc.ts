export interface JsonRpcRequest<TParams = unknown> {
  jsonrpc: "2.0"
  id: string | number
  method: string
  params?: TParams
}

export interface JsonRpcResponse<TResult = unknown> {
  jsonrpc: "2.0"
  id: string | number
  result: TResult
}

export interface JsonRpcError {
  jsonrpc: "2.0"
  id: string | number | null
  error: {
    code: number
    message: string
    data?: unknown
  }
}

export interface JsonRpcNotification<TParams = unknown> {
  jsonrpc: "2.0"
  method: string
  params: TParams
}

export type JsonRpcMessage =
  | JsonRpcRequest
  | JsonRpcResponse
  | JsonRpcError
  | JsonRpcNotification

export interface ServerInfo {
  protocol_version: string
  server_info: { name: string; version: string }
  session_id: string | null
}

export interface SessionInfo {
  id: string
  status: string
  title: string | null
  model?: string
  message_count: number
  turn_count: number
  usage?: { input_tokens: number; output_tokens: number }
  created_at: string
  updated_at?: string
}

export interface SessionListResult {
  sessions: SessionInfo[]
}

export interface SessionCreateParams {
  system_prompt?: string
  title?: string
  cwd?: string
  model?: string
}

export interface SessionCreateResult {
  session_id: string
}

export interface MessageData {
  id: string
  role: "user" | "assistant" | "system" | "tool"
  content: string
  reasoning?: string
  toolCalls?: { id: string; name: string; arguments: unknown }[]
  usage?: { inputTokens?: number; outputTokens?: number }
  createdAt: number
}

export interface SessionUsage {
  total_input: number
  total_output: number
  total_reasoning: number
  context_size: number
}

export interface SessionLoadResult {
  session_id: string
  model?: string
  messages_count: number
  turn_count: number
  usage?: SessionUsage
  messages: MessageData[]
}

export interface SessionDeleteResult {
  status: string
  session_id: string
}

export interface SessionForkResult {
  session_id: string
}

export interface ChatParams {
  message: string
  session_id?: string
  system_prompt?: string
  title?: string
  cwd?: string
  model?: string
}

export interface ChatResult {
  content: string
  finish_reason: string
  usage: Usage
  session_id: string
}

export interface Usage {
  input_tokens: number
  output_tokens: number
  total_tokens?: number
}

export interface AgentEvent {
  type: AgentEventType
  data: string
  finish_reason?: string
  usage?: Usage
  session_usage?: SessionUsage
}

export type AgentEventType =
  | "reasoning"
  | "content"
  | "tool_calls"
  | "tool_result"
  | "compacting"
  | "finish"
  | "error"

export interface ToolDefinition {
  name: string
  description: string
  input_schema: Record<string, unknown>
}

export interface ToolsListResult {
  tools: ToolDefinition[]
}

export interface CancelResult {
  status: "cancelled" | "no_active_stream"
}
