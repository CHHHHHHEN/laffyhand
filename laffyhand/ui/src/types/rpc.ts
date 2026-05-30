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
  server_info: string
  session_id: string | null
}

export interface SessionInfo {
  id: string
  status: string
  title: string | null
  message_count: number
  turn_count: number
  usage?: { input_tokens: number; output_tokens: number }
  created_at: number
  updated_at?: number
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

export interface SessionLoadResult {
  session_id: string
  messages_count: number
  turn_count: number
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
