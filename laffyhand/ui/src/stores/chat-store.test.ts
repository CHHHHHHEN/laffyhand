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
    streamToolResults: [],
    currentAssistantMessageId: null,
    error: null,
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

    store.addToolResult({
      id: "call-1",
      name: "read_file",
      result: "file content",
    })

    store.finalizeMessage()

    const message = useChatStore.getState().messages[0]!
    expect(message.toolCalls).toHaveLength(1)
    expect(message.toolCalls![0]!.name).toBe("read_file")
    expect(message.toolResults).toHaveLength(1)
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

  it("promotes reasoning to content when content is empty", () => {
    const store = useChatStore.getState()
    store.startStreaming()
    store.setReasoning("only reasoning no content")
    store.finalizeMessage()

    const message = useChatStore.getState().messages[0]!
    expect(message.content).toBe("only reasoning no content")
    expect(message.reasoning).toBeUndefined()
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
})
