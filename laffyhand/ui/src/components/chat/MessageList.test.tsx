import { describe, it, expect, beforeEach, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import { MessageList } from "./MessageList"
import { useChatStore, resetMessageCounter } from "@/stores/chat-store"

beforeEach(() => {
  // jsdom does not implement scrollIntoView
  HTMLDivElement.prototype.scrollIntoView = vi.fn()
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

describe("MessageList", () => {
  it("shows empty state when no messages", () => {
    render(<MessageList />)
    expect(screen.getByText("Send a message to start chatting")).toBeInTheDocument()
  })

  it("renders messages", () => {
    useChatStore.setState({
      messages: [
        {
          id: "m1",
          role: "user",
          content: "hello",
          createdAt: 100,
        },
        {
          id: "m2",
          role: "assistant",
          content: "hi there",
          createdAt: 200,
        },
      ],
    })
    render(<MessageList />)
    expect(screen.getByText("hello")).toBeInTheDocument()
    expect(screen.getByText("hi there")).toBeInTheDocument()
  })

  it("shows thinking indicator when streaming without content", () => {
    useChatStore.setState({ isStreaming: true })
    render(<MessageList />)
    expect(screen.getByText("Thinking...")).toBeInTheDocument()
  })

  it("shows stream content when streaming", () => {
    useChatStore.setState({
      isStreaming: true,
      streamContent: "partial response",
    })
    render(<MessageList />)
    expect(screen.getByText("partial response")).toBeInTheDocument()
  })

  it("shows stream reasoning when streaming", () => {
    useChatStore.setState({
      isStreaming: true,
      streamReasoning: "thinking step by step",
    })
    render(<MessageList />)
    expect(screen.getByText("thinking step by step")).toBeInTheDocument()
  })

  it("shows error message", () => {
    useChatStore.setState({ error: "Connection failed" })
    render(<MessageList />)
    expect(screen.getByText("Connection failed")).toBeInTheDocument()
  })

  it("does not show empty state when error is present", () => {
    useChatStore.setState({ error: "Something broke" })
    render(<MessageList />)
    expect(screen.queryByText("Send a message to start chatting")).not.toBeInTheDocument()
    expect(screen.getByText("Something broke")).toBeInTheDocument()
  })
})
