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
})
