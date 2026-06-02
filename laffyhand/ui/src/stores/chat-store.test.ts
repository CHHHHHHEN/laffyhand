import { describe, it, expect, beforeEach } from "vitest"
import { useChatStore, resetMessageCounter } from "./chat-store"

beforeEach(() => {
  resetMessageCounter()
  useChatStore.setState({
    messages: [],
    isStreaming: false,
    streamContent: "",
    streamReasoning: "",
    streamToolCalls: [],
    currentAssistantMessageId: null,
    error: null,
    foregroundSubagents: [],
    backgroundSubagents: [],
  })
})

describe("chat-store", () => {
  it("adds user message", () => {
    const store = useChatStore.getState()
    store.addUserMessage("hello")
    const messages = useChatStore.getState().messages
    expect(messages).toHaveLength(1)
    expect(messages[0]!.role).toBe("user")
    expect(messages[0]!.content).toBe("hello")
  })

  it("starts streaming and finalizes message", () => {
    const store = useChatStore.getState()
    store.addUserMessage("hello")
    store.startStreaming()

    let state = useChatStore.getState()
    expect(state.isStreaming).toBe(true)
    expect(state.currentAssistantMessageId).toBeTruthy()

    store.appendContent("Hi ")
    store.appendContent("there!")
    store.finalizeMessage({ inputTokens: 10, outputTokens: 5 })

    state = useChatStore.getState()
    expect(state.isStreaming).toBe(false)
    expect(state.messages).toHaveLength(2)
    expect(state.messages[1]!.role).toBe("assistant")
    expect(state.messages[1]!.content).toBe("Hi there!")
    expect(state.messages[1]!.usage?.inputTokens).toBe(10)
  })

  it("preserves reasoning in finalized message", () => {
    const store = useChatStore.getState()
    store.startStreaming()
    store.setReasoning("thinking step by step")
    store.appendContent("Here's the answer")
    store.finalizeMessage()

    const message = useChatStore.getState().messages[0]!
    expect(message.reasoning).toBe("thinking step by step")
    expect(message.content).toBe("Here's the answer")
  })

  it("handles tool calls during streaming", () => {
    const store = useChatStore.getState()
    store.startStreaming()

    store.addToolCall({
      id: "call-1",
      name: "read_file",
      arguments: { path: "/test" },
    })

    store.updateToolCallStatus("call-1", "completed", "file content")

    store.finalizeMessage()

    const message = useChatStore.getState().messages[0]!
    expect(message.toolCalls).toHaveLength(1)
    expect(message.toolCalls![0]!.name).toBe("read_file")
    expect(message.toolCalls![0]!.result).toBe("file content")
  })

  it("updates tool status in finalized message when status arrives after finalization", () => {
    const store = useChatStore.getState()
    store.startStreaming()

    store.addToolCall({
      id: "call-1",
      name: "read_file",
      arguments: { path: "/test" },
    })

    // Finalize while tool is still running (as happens in real streaming)
    store.finalizeMessage()

    // Tool result arrives after finalization
    store.updateToolCallStatus("call-1", "completed", "file content")

    const message = useChatStore.getState().messages[0]!
    expect(message.toolCalls).toHaveLength(1)
    expect(message.toolCalls![0]!.status).toBe("completed")
    expect(message.toolCalls![0]!.result).toBe("file content")
  })

  it("sets error and stops streaming", () => {
    useChatStore.getState().startStreaming()
    useChatStore.getState().setError("Connection failed")

    const state = useChatStore.getState()
    expect(state.error).toBe("Connection failed")
    expect(state.isStreaming).toBe(false)
  })

  it("clears all messages", () => {
    useChatStore.getState().addUserMessage("hello")
    useChatStore.getState().clearMessages()

    expect(useChatStore.getState().messages).toHaveLength(0)
  })

  it("loads existing messages", () => {
    const messages = [
      {
        id: "m1",
        role: "user" as const,
        content: "hi",
        createdAt: 100,
      },
      {
        id: "m2",
        role: "assistant" as const,
        content: "hello",
        createdAt: 200,
      },
    ]

    useChatStore.getState().loadMessages(messages)
    expect(useChatStore.getState().messages).toHaveLength(2)
  })

  // ── Per-turn token delta tracking ──

  it("saves turnStartUsage on startStreaming", () => {
    const store = useChatStore.getState()
    store.setSessionInfo("test-model", {
      total_input: 1000,
      total_output: 500,
      total_reasoning: 50,
      context_size: 128000,
    })
    store.startStreaming()

    const state = useChatStore.getState()
    expect(state._turnStartUsage).toEqual({
      total_input: 1000,
      total_output: 500,
      total_reasoning: 50,
      context_size: 128000,
    })
  })

  it("computes turnUsage delta on finalizeMessage", () => {
    const store = useChatStore.getState()
    store.setSessionInfo("test-model", {
      total_input: 1000,
      total_output: 500,
      total_reasoning: 50,
      context_size: 128000,
    })
    store.startStreaming()
    store.appendContent("response")
    store.finalizeMessage(undefined, {
      total_input: 1500,
      total_output: 700,
      total_reasoning: 80,
      context_size: 128000,
    })

    const state = useChatStore.getState()
    expect(state.turnUsage).toEqual({
      input: 500,
      output: 200,
      reasoning: 30,
    })
  })

  it("sets turnUsage to null when finalizeMessage without sessionUsage", () => {
    const store = useChatStore.getState()
    store.startStreaming()
    store.appendContent("no usage")
    store.finalizeMessage() // no sessionUsage

    const state = useChatStore.getState()
    expect(state.turnUsage).toBeNull()
  })

  it("resets turn tracking on clearMessages", () => {
    const store = useChatStore.getState()
    store.startStreaming()
    store.appendContent("test")
    store.finalizeMessage(undefined, {
      total_input: 500,
      total_output: 300,
      total_reasoning: 0,
      context_size: 128000,
    })
    store.clearMessages()

    const state = useChatStore.getState()
    expect(state.turnUsage).toBeNull()
    expect(state._turnStartUsage).toBeNull()
  })

  it("resets turn tracking on setSessionInfo", () => {
    const store = useChatStore.getState()
    store.startStreaming()
    store.appendContent("test")
    store.finalizeMessage(undefined, {
      total_input: 500,
      total_output: 300,
      total_reasoning: 0,
      context_size: 128000,
    })
    store.setSessionInfo("new-model", null)

    const state = useChatStore.getState()
    expect(state.turnUsage).toBeNull()
    expect(state._turnStartUsage).toBeNull()
  })

  // ── Content/reasoning promotion ──

  it("keeps reasoning separate when content is empty", () => {
    const store = useChatStore.getState()
    store.startStreaming()
    store.setReasoning("only reasoning no content")
    store.finalizeMessage()

    const message = useChatStore.getState().messages[0]!
    expect(message.content).toBe("")
    expect(message.reasoning).toBe("only reasoning no content")
  })

  it("keeps reasoning separate when content exists", () => {
    const store = useChatStore.getState()
    store.startStreaming()
    store.setReasoning("thinking step by step")
    store.appendContent("actual answer")
    store.finalizeMessage()

    const message = useChatStore.getState().messages[0]!
    expect(message.content).toBe("actual answer")
    expect(message.reasoning).toBe("thinking step by step")
  })

  it("uses empty string when neither content nor reasoning", () => {
    const store = useChatStore.getState()
    store.startStreaming()
    store.finalizeMessage()

    const message = useChatStore.getState().messages[0]!
    expect(message.content).toBe("")
    expect(message.reasoning).toBeUndefined()
  })

  // ── Permission request messages ──

  it("addPermissionRequest appends a permission-request message", () => {
    const store = useChatStore.getState()
    store.addPermissionRequest({ requestId: "req-1", permission: "skill", pattern: "test-tool" })
    const messages = useChatStore.getState().messages
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
    store.addPermissionRequest({ requestId: "r1", permission: "write", pattern: "/tmp/test" })
    const msg = useChatStore.getState().messages[0]!
    expect(msg.content).toBe("Allow write '/tmp/test'?")
  })

  it("resolvePermissionRequest marks message as resolved", () => {
    const store = useChatStore.getState()
    store.addPermissionRequest({ requestId: "req-1", permission: "skill", pattern: "test" })
    const msgId = useChatStore.getState().messages[0]!.id
    store.resolvePermissionRequest(msgId)
    const msg = useChatStore.getState().messages[0]!
    expect(msg.permissionInfo?.resolved).toBe(true)
  })

  it("resolvePermissionRequest does nothing for unknown id", () => {
    const store = useChatStore.getState()
    store.addPermissionRequest({ requestId: "req-1", permission: "skill", pattern: "test" })
    store.resolvePermissionRequest("nonexistent")
    const msg = useChatStore.getState().messages[0]!
    expect(msg.permissionInfo?.resolved).toBeUndefined()
  })

  // ── Subagent tracking ──

  it("startSubagent adds foreground subagent", () => {
    const store = useChatStore.getState()
    store.startSubagent({
      id: "sa-1",
      agent_type: "explore",
      description: "searching files",
      mode: "foreground",
      depth: 0,
    })
    const state = useChatStore.getState()
    expect(state.foregroundSubagents).toHaveLength(1)
    expect(state.backgroundSubagents).toHaveLength(0)
    expect(state.foregroundSubagents[0]!.id).toBe("sa-1")
    expect(state.foregroundSubagents[0]!.status).toBe("running")
    expect(state.foregroundSubagents[0]!.mode).toBe("foreground")
  })

  it("startSubagent adds background subagent", () => {
    const store = useChatStore.getState()
    store.startSubagent({
      id: "sa-2",
      agent_type: "general",
      description: "background task",
      mode: "background",
      depth: 1,
    })
    const state = useChatStore.getState()
    expect(state.backgroundSubagents).toHaveLength(1)
    expect(state.foregroundSubagents).toHaveLength(0)
    expect(state.backgroundSubagents[0]!.parentId).toBeNull()
    expect(state.backgroundSubagents[0]!.depth).toBe(1)
  })

  it("startSubagent with parentId sets parentId correctly", () => {
    const store = useChatStore.getState()
    store.startSubagent({
      id: "sa-child",
      parent_id: "sa-parent",
      agent_type: "explore",
      description: "child task",
      mode: "foreground",
      depth: 1,
    })
    const sa = useChatStore.getState().foregroundSubagents[0]!
    expect(sa.parentId).toBe("sa-parent")
  })

  it("updateSubagent appends text content", () => {
    const store = useChatStore.getState()
    store.startSubagent({ id: "sa-1", agent_type: "explore", description: "testing", mode: "foreground", depth: 0 })
    store.updateSubagent("sa-1", { kind: "text", content: "Hello " })
    store.updateSubagent("sa-1", { kind: "text", content: "World" })
    expect(useChatStore.getState().foregroundSubagents[0]!.text).toBe("Hello World")
  })

  it("updateSubagent appends reasoning content", () => {
    const store = useChatStore.getState()
    store.startSubagent({ id: "sa-1", agent_type: "explore", description: "testing", mode: "foreground", depth: 0 })
    store.updateSubagent("sa-1", { kind: "reasoning", content: "thinking..." })
    expect(useChatStore.getState().foregroundSubagents[0]!.reasoning).toBe("thinking...")
  })

  it("updateSubagent adds tool calls", () => {
    const store = useChatStore.getState()
    store.startSubagent({ id: "sa-1", agent_type: "explore", description: "testing", mode: "foreground", depth: 0 })
    store.updateSubagent("sa-1", { kind: "tool", tool_name: "read_file", tool_input: '{"path": "/test"}' })
    const sa = useChatStore.getState().foregroundSubagents[0]!
    expect(sa.toolCount).toBe(1)
    expect(sa.tools[0]!.name).toBe("read_file")
  })

  it("updateSubagent handles error kind", () => {
    const store = useChatStore.getState()
    store.startSubagent({ id: "sa-1", agent_type: "explore", description: "testing", mode: "foreground", depth: 0 })
    store.updateSubagent("sa-1", { kind: "error", content: "something went wrong" })
    const sa = useChatStore.getState().foregroundSubagents[0]!
    expect(sa.status).toBe("error")
    expect(sa.text).toContain("something went wrong")
  })

  it("updateSubagent does nothing for unknown id", () => {
    const store = useChatStore.getState()
    store.startSubagent({ id: "sa-1", agent_type: "explore", description: "testing", mode: "foreground", depth: 0 })
    const before = useChatStore.getState().foregroundSubagents[0]!.text
    store.updateSubagent("nonexistent", { kind: "text", content: "should not appear" })
    expect(useChatStore.getState().foregroundSubagents[0]!.text).toBe(before)
  })

  it("endSubagent updates status and token counts", () => {
    const store = useChatStore.getState()
    store.startSubagent({ id: "sa-1", agent_type: "explore", description: "testing", mode: "foreground", depth: 0 })
    store.endSubagent("sa-1", {
      status: "completed",
      summary: "done",
      input_tokens: 100,
      output_tokens: 50,
    })
    const sa = useChatStore.getState().foregroundSubagents[0]!
    expect(sa.status).toBe("completed")
    expect(sa.summary).toBe("done")
    expect(sa.inputTokens).toBe(100)
    expect(sa.outputTokens).toBe(50)
  })

  it("endSubagent preserves existing fields when event fields are missing", () => {
    const store = useChatStore.getState()
    store.startSubagent({ id: "sa-1", agent_type: "explore", description: "testing", mode: "foreground", depth: 0 })
    store.endSubagent("sa-1", { status: "completed" })
    const sa = useChatStore.getState().foregroundSubagents[0]!
    expect(sa.inputTokens).toBe(0)
    expect(sa.summary).toBeUndefined()
  })

  it("clearForegroundSubagents empties foreground array only", () => {
    const store = useChatStore.getState()
    store.startSubagent({ id: "fg", agent_type: "explore", description: "fg", mode: "foreground", depth: 0 })
    store.startSubagent({ id: "bg", agent_type: "explore", description: "bg", mode: "background", depth: 0 })
    store.clearForegroundSubagents()
    const state = useChatStore.getState()
    expect(state.foregroundSubagents).toHaveLength(0)
    expect(state.backgroundSubagents).toHaveLength(1)
  })

  it("clearMessages clears both subagent arrays", () => {
    const store = useChatStore.getState()
    store.startSubagent({ id: "sa-1", agent_type: "explore", description: "test", mode: "foreground", depth: 0 })
    store.startSubagent({ id: "sa-2", agent_type: "explore", description: "test", mode: "background", depth: 0 })
    store.clearMessages()
    const state = useChatStore.getState()
    expect(state.foregroundSubagents).toHaveLength(0)
    expect(state.backgroundSubagents).toHaveLength(0)
  })
})
