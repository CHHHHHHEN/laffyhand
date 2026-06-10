import { describe, it, expect, beforeEach } from "vitest"
import { useChatStore, resetMessageCounter } from "./chat-store"

const SID = "test-sess"

beforeEach(() => {
  resetMessageCounter()
  useChatStore.setState({ sessions: {} })
  useChatStore.getState().addSession(SID)
})

describe("chat-store", () => {
  it("adds a session", () => {
    expect(useChatStore.getState().sessions[SID]).toBeDefined()
    expect(useChatStore.getState().sessions[SID]!.messages).toEqual([])
  })

  it("addSession is idempotent", () => {
    useChatStore.getState().addSession(SID)
    expect(Object.keys(useChatStore.getState().sessions)).toHaveLength(1)
  })

  it("removes a session", () => {
    useChatStore.getState().removeSession(SID)
    expect(useChatStore.getState().sessions[SID]).toBeUndefined()
  })

  it("adds user message", () => {
    const store = useChatStore.getState()
    store.addUserMessage(SID, "hello")
    const messages = useChatStore.getState().sessions[SID]!.messages
    expect(messages).toHaveLength(1)
    expect(messages[0]!.role).toBe("user")
    expect(messages[0]!.content).toBe("hello")
  })

  it("starts streaming and finalizes message", () => {
    const store = useChatStore.getState()
    store.addUserMessage(SID, "hello")
    store.startStreaming(SID)

    let state = useChatStore.getState().sessions[SID]!
    expect(state.isStreaming).toBe(true)
    expect(state.currentAssistantMessageId).toBeTruthy()

    store.appendContent(SID, "Hi ")
    store.appendContent(SID, "there!")
    store.finalizeMessage(SID, { inputTokens: 10, outputTokens: 5 })

    state = useChatStore.getState().sessions[SID]!
    expect(state.isStreaming).toBe(false)
    expect(state.messages).toHaveLength(2)
    expect(state.messages[1]!.role).toBe("assistant")
    expect(state.messages[1]!.content).toBe("Hi there!")
    expect(state.messages[1]!.usage?.inputTokens).toBe(10)
  })

  it("preserves reasoning in finalized message", () => {
    const store = useChatStore.getState()
    store.startStreaming(SID)
    store.setReasoning(SID, "thinking step by step")
    store.appendContent(SID, "Here's the answer")
    store.finalizeMessage(SID)

    const message = useChatStore.getState().sessions[SID]!.messages[0]!
    expect(message.reasoning).toBe("thinking step by step")
    expect(message.content).toBe("Here's the answer")
  })

  it("handles tool calls during streaming", () => {
    const store = useChatStore.getState()
    store.startStreaming(SID)

    store.addToolCall(SID, {
      id: "call-1",
      name: "read_file",
      arguments: { path: "/test" },
    })

    store.updateToolCallStatus(SID, "call-1", "completed", "file content")

    store.finalizeMessage(SID)

    const message = useChatStore.getState().sessions[SID]!.messages[0]!
    expect(message.toolCalls).toHaveLength(1)
    expect(message.toolCalls![0]!.name).toBe("read_file")
    expect(message.toolCalls![0]!.result).toBe("file content")
  })

  it("updates tool status in finalized message when status arrives after finalization", () => {
    const store = useChatStore.getState()
    store.startStreaming(SID)

    store.addToolCall(SID, {
      id: "call-1",
      name: "read_file",
      arguments: { path: "/test" },
    })

    store.finalizeMessage(SID)

    store.updateToolCallStatus(SID, "call-1", "completed", "file content")

    const message = useChatStore.getState().sessions[SID]!.messages[0]!
    expect(message.toolCalls).toHaveLength(1)
    expect(message.toolCalls![0]!.status).toBe("completed")
    expect(message.toolCalls![0]!.result).toBe("file content")
  })

  it("sets error and stops streaming", () => {
    useChatStore.getState().startStreaming(SID)
    useChatStore.getState().setError(SID, "Connection failed")

    const state = useChatStore.getState().sessions[SID]!
    expect(state.error).toBe("Connection failed")
    expect(state.isStreaming).toBe(false)
  })

  it("clears all messages", () => {
    useChatStore.getState().addUserMessage(SID, "hello")
    useChatStore.getState().clearMessages(SID)

    expect(useChatStore.getState().sessions[SID]!.messages).toHaveLength(0)
  })

  it("loads existing messages", () => {
    const messages = [
      { id: "m1", role: "user" as const, content: "hi", createdAt: 100 },
      { id: "m2", role: "assistant" as const, content: "hello", createdAt: 200 },
    ]

    useChatStore.getState().loadMessages(SID, messages)
    expect(useChatStore.getState().sessions[SID]!.messages).toHaveLength(2)
  })

  // ── Per-turn token delta tracking ──

  it("saves turnStartUsage on startStreaming", () => {
    const store = useChatStore.getState()
    store.setSessionInfo(SID, "test-model", {
      curr_context_usage: 0,
      total_input: 1000,
      total_output: 500,
      total_reasoning: 50,
      context_size: 128000,
    })
    store.startStreaming(SID)

    const state = useChatStore.getState().sessions[SID]!
    expect(state._turnStartUsage).toEqual({
      curr_context_usage: 0,
      total_input: 1000,
      total_output: 500,
      total_reasoning: 50,
      context_size: 128000,
    })
  })

  it("computes turnUsage delta on finalizeMessage", () => {
    const store = useChatStore.getState()
    store.setSessionInfo(SID, "test-model", {
      curr_context_usage: 0,
      total_input: 1000,
      total_output: 500,
      total_reasoning: 50,
      context_size: 128000,
    })
    store.startStreaming(SID)
    store.appendContent(SID, "response")
    store.finalizeMessage(SID, undefined, {
      curr_context_usage: 0,
      total_input: 1500,
      total_output: 700,
      total_reasoning: 80,
      context_size: 128000,
    })

    const state = useChatStore.getState().sessions[SID]!
    expect(state.turnUsage).toEqual({
      input: 500,
      output: 200,
      reasoning: 30,
    })
  })

  it("sets turnUsage to null when finalizeMessage without sessionUsage", () => {
    const store = useChatStore.getState()
    store.startStreaming(SID)
    store.appendContent(SID, "no usage")
    store.finalizeMessage(SID)

    const state = useChatStore.getState().sessions[SID]!
    expect(state.turnUsage).toBeNull()
  })

  it("resets turn tracking on clearMessages", () => {
    const store = useChatStore.getState()
    store.startStreaming(SID)
    store.appendContent(SID, "test")
    store.finalizeMessage(SID, undefined, {
      curr_context_usage: 0,
      total_input: 500,
      total_output: 300,
      total_reasoning: 0,
      context_size: 128000,
    })
    store.clearMessages(SID)

    const state = useChatStore.getState().sessions[SID]!
    expect(state.turnUsage).toBeNull()
    expect(state._turnStartUsage).toBeNull()
  })

  it("resets turn tracking on setSessionInfo", () => {
    const store = useChatStore.getState()
    store.startStreaming(SID)
    store.appendContent(SID, "test")
    store.finalizeMessage(SID, undefined, {
      curr_context_usage: 0,
      total_input: 500,
      total_output: 300,
      total_reasoning: 0,
      context_size: 128000,
    })
    store.setSessionInfo(SID, "new-model", null)

    const state = useChatStore.getState().sessions[SID]!
    expect(state.turnUsage).toBeNull()
    expect(state._turnStartUsage).toBeNull()
  })

  // ── Content/reasoning promotion ──

  it("keeps reasoning separate when content is empty", () => {
    const store = useChatStore.getState()
    store.startStreaming(SID)
    store.setReasoning(SID, "only reasoning no content")
    store.finalizeMessage(SID)

    const message = useChatStore.getState().sessions[SID]!.messages[0]!
    expect(message.content).toBe("")
    expect(message.reasoning).toBe("only reasoning no content")
  })

  it("keeps reasoning separate when content exists", () => {
    const store = useChatStore.getState()
    store.startStreaming(SID)
    store.setReasoning(SID, "thinking step by step")
    store.appendContent(SID, "actual answer")
    store.finalizeMessage(SID)

    const message = useChatStore.getState().sessions[SID]!.messages[0]!
    expect(message.content).toBe("actual answer")
    expect(message.reasoning).toBe("thinking step by step")
  })

  it("uses empty string when neither content nor reasoning", () => {
    const store = useChatStore.getState()
    store.startStreaming(SID)
    store.finalizeMessage(SID)

    const message = useChatStore.getState().sessions[SID]!.messages[0]!
    expect(message.content).toBe("")
    expect(message.reasoning).toBeUndefined()
  })

  // ── Permission request messages ──

  it("addPermissionRequest appends a permission-request message", () => {
    const store = useChatStore.getState()
    store.addPermissionRequest(SID, { requestId: "req-1", permission: "skill", pattern: "test-tool" })
    const messages = useChatStore.getState().sessions[SID]!.messages
    expect(messages).toHaveLength(1)
    const msg = messages[0]!
    expect(msg.role).toBe("permission-request")
    expect(msg.permissionInfo?.requestId).toBe("req-1")
    expect(msg.permissionInfo?.permission).toBe("skill")
    expect(msg.permissionInfo?.pattern).toBe("test-tool")
    expect(msg.permissionInfo?.resolved).toBeUndefined()
  })

  it("addPermissionRequest sets content from permission and pattern", () => {
    const store = useChatStore.getState()
    store.addPermissionRequest(SID, { requestId: "r1", permission: "write", pattern: "/tmp/test" })
    const msg = useChatStore.getState().sessions[SID]!.messages[0]!
    expect(msg.content).toBe("Allow write '/tmp/test'?")
  })

  it("resolvePermissionRequest marks message as resolved", () => {
    const store = useChatStore.getState()
    store.addPermissionRequest(SID, { requestId: "req-1", permission: "skill", pattern: "test" })
    const msgId = useChatStore.getState().sessions[SID]!.messages[0]!.id
    store.resolvePermissionRequest(SID, msgId)
    const msg = useChatStore.getState().sessions[SID]!.messages[0]!
    expect(msg.permissionInfo?.resolved).toBe(true)
    expect(msg.permissionInfo?.denyReason).toBeUndefined()
  })

  it("resolvePermissionRequest stores denyReason", () => {
    const store = useChatStore.getState()
    store.addPermissionRequest(SID, { requestId: "req-1", permission: "skill", pattern: "test" })
    const msgId = useChatStore.getState().sessions[SID]!.messages[0]!.id
    store.resolvePermissionRequest(SID, msgId, "not needed")
    const msg = useChatStore.getState().sessions[SID]!.messages[0]!
    expect(msg.permissionInfo?.resolved).toBe(true)
    expect(msg.permissionInfo?.denyReason).toBe("not needed")
  })

  it("resolvePermissionRequest does nothing for unknown id", () => {
    const store = useChatStore.getState()
    store.addPermissionRequest(SID, { requestId: "req-1", permission: "skill", pattern: "test" })
    store.resolvePermissionRequest(SID, "nonexistent")
    const msg = useChatStore.getState().sessions[SID]!.messages[0]!
    expect(msg.permissionInfo?.resolved).toBeUndefined()
  })

  // ── Subagent tracking ──

  it("startSubagent adds foreground subagent", () => {
    const store = useChatStore.getState()
    store.startSubagent(SID, {
      id: "sa-1",
      agent_type: "explore",
      description: "searching files",
      depth: 0,
    })
    const state = useChatStore.getState().sessions[SID]!
    expect(state.foregroundSubagents).toHaveLength(1)
    expect(state.foregroundSubagents[0]!.id).toBe("sa-1")
    expect(state.foregroundSubagents[0]!.status).toBe("running")
  })

  it("startSubagent with parentId sets parentId correctly", () => {
    const store = useChatStore.getState()
    store.startSubagent(SID, {
      id: "sa-child",
      parent_id: "sa-parent",
      agent_type: "explore",
      description: "child task",
      depth: 1,
    })
    const sa = useChatStore.getState().sessions[SID]!.foregroundSubagents[0]!
    expect(sa.parentId).toBe("sa-parent")
  })

  it("updateSubagent appends text content", () => {
    const store = useChatStore.getState()
    store.startSubagent(SID, { id: "sa-1", agent_type: "explore", description: "testing", depth: 0 })
    store.updateSubagent(SID, "sa-1", { kind: "text", content: "Hello " })
    store.updateSubagent(SID, "sa-1", { kind: "text", content: "World" })
    expect(useChatStore.getState().sessions[SID]!.foregroundSubagents[0]!.text).toBe("Hello World")
  })

  it("updateSubagent appends reasoning content", () => {
    const store = useChatStore.getState()
    store.startSubagent(SID, { id: "sa-1", agent_type: "explore", description: "testing", depth: 0 })
    store.updateSubagent(SID, "sa-1", { kind: "reasoning", content: "thinking..." })
    expect(useChatStore.getState().sessions[SID]!.foregroundSubagents[0]!.reasoning).toBe("thinking...")
  })

  it("updateSubagent adds tool calls", () => {
    const store = useChatStore.getState()
    store.startSubagent(SID, { id: "sa-1", agent_type: "explore", description: "testing", depth: 0 })
    store.updateSubagent(SID, "sa-1", { kind: "tool", tool_name: "read_file", tool_input: '{"path": "/test"}' })
    const sa = useChatStore.getState().sessions[SID]!.foregroundSubagents[0]!
    expect(sa.toolCount).toBe(1)
    expect(sa.tools[0]!.name).toBe("read_file")
  })

  it("updateSubagent handles error kind", () => {
    const store = useChatStore.getState()
    store.startSubagent(SID, { id: "sa-1", agent_type: "explore", description: "testing", depth: 0 })
    store.updateSubagent(SID, "sa-1", { kind: "error", content: "something went wrong" })
    const sa = useChatStore.getState().sessions[SID]!.foregroundSubagents[0]!
    expect(sa.status).toBe("error")
    expect(sa.text).toContain("something went wrong")
  })

  it("updateSubagent does nothing for unknown id", () => {
    const store = useChatStore.getState()
    store.startSubagent(SID, { id: "sa-1", agent_type: "explore", description: "testing", depth: 0 })
    const before = useChatStore.getState().sessions[SID]!.foregroundSubagents[0]!.text
    store.updateSubagent(SID, "nonexistent", { kind: "text", content: "should not appear" })
    expect(useChatStore.getState().sessions[SID]!.foregroundSubagents[0]!.text).toBe(before)
  })

  it("endSubagent updates status and token counts", () => {
    const store = useChatStore.getState()
    store.startSubagent(SID, { id: "sa-1", agent_type: "explore", description: "testing", depth: 0 })
    store.endSubagent(SID, "sa-1", {
      status: "completed",
      summary: "done",
      input_tokens: 100,
      output_tokens: 50,
    })
    const sa = useChatStore.getState().sessions[SID]!.foregroundSubagents[0]!
    expect(sa.status).toBe("completed")
    expect(sa.summary).toBe("done")
    expect(sa.inputTokens).toBe(100)
    expect(sa.outputTokens).toBe(50)
  })

  it("endSubagent preserves existing fields when event fields are missing", () => {
    const store = useChatStore.getState()
    store.startSubagent(SID, { id: "sa-1", agent_type: "explore", description: "testing", depth: 0 })
    store.endSubagent(SID, "sa-1", { status: "completed" })
    const sa = useChatStore.getState().sessions[SID]!.foregroundSubagents[0]!
    expect(sa.inputTokens).toBe(0)
    expect(sa.summary).toBeUndefined()
  })

  it("clearForegroundSubagents empties foreground array", () => {
    const store = useChatStore.getState()
    store.startSubagent(SID, { id: "sa-1", agent_type: "explore", description: "test", depth: 0 })
    store.clearForegroundSubagents(SID)
    const state = useChatStore.getState().sessions[SID]!
    expect(state.foregroundSubagents).toHaveLength(0)
  })

  it("clearMessages clears subagent arrays", () => {
    const store = useChatStore.getState()
    store.startSubagent(SID, { id: "sa-1", agent_type: "explore", description: "test", depth: 0 })
    store.clearMessages(SID)
    const state = useChatStore.getState().sessions[SID]!
    expect(state.foregroundSubagents).toHaveLength(0)
  })

  // ── Multiple sessions isolation ──

  it("maintains isolated state for different sessions", () => {
    const store = useChatStore.getState()
    store.addSession("sess-a")
    store.addSession("sess-b")

    store.addUserMessage("sess-a", "hello from A")
    store.addUserMessage("sess-b", "hello from B")

    expect(useChatStore.getState().sessions["sess-a"]!.messages).toHaveLength(1)
    expect(useChatStore.getState().sessions["sess-b"]!.messages).toHaveLength(1)
    expect(useChatStore.getState().sessions["sess-a"]!.messages[0]!.content).toBe("hello from A")
    expect(useChatStore.getState().sessions["sess-b"]!.messages[0]!.content).toBe("hello from B")
  })

  it("streaming in one session does not affect another", () => {
    const store = useChatStore.getState()
    store.addSession("sess-a")
    store.addSession("sess-b")

    store.startStreaming("sess-a")
    store.appendContent("sess-a", "streaming in A")

    expect(useChatStore.getState().sessions["sess-a"]!.isStreaming).toBe(true)
    expect(useChatStore.getState().sessions["sess-b"]!.isStreaming).toBe(false)
  })
})
