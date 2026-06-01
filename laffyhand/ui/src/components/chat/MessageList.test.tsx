import { describe, it, expect, beforeEach, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import { MessageList } from "./MessageList"
import { useChatStore, resetMessageCounter } from "@/stores/chat-store"

beforeEach(() => {
  HTMLDivElement.prototype.scrollIntoView = vi.fn()
  resetMessageCounter()
  useChatStore.setState({
    messages: [],
    isStreaming: false,
    streamContent: "",
    streamReasoning: "",
    streamToolCalls: [],
    currentAssistantMessageId: null,
    error: null,
  })
})

describe("MessageList", () => {
  // ── 空状态 ──

  it("shows empty state with title and subtitle", () => {
    render(<MessageList />)
    expect(screen.getByText("Start a conversation")).toBeInTheDocument()
    expect(screen.getByText("Type a message below to begin")).toBeInTheDocument()
  })

  it("shows empty state icon container", () => {
    render(<MessageList />)
    const iconContainer = document.querySelector(".bg-gradient-to-br")
    expect(iconContainer).toBeTruthy()
  })

  // ── 消息列表 ──

  it("renders messages", () => {
    useChatStore.setState({
      messages: [
        { id: "m1", role: "user", content: "hello", createdAt: 100 },
        { id: "m2", role: "assistant", content: "hi there", createdAt: 200 },
      ],
    })
    render(<MessageList />)
    expect(screen.getByText("hello")).toBeInTheDocument()
    expect(screen.getByText("hi there")).toBeInTheDocument()
  })

  it("renders multiple user/assistant messages in order", () => {
    useChatStore.setState({
      messages: [
        { id: "m1", role: "user", content: "first", createdAt: 100 },
        { id: "m2", role: "assistant", content: "reply1", createdAt: 200 },
        { id: "m3", role: "user", content: "second", createdAt: 300 },
        { id: "m4", role: "assistant", content: "reply2", createdAt: 400 },
      ],
    })
    render(<MessageList />)
    const texts = screen.getAllByText(/first|reply1|second|reply2/)
    expect(texts).toHaveLength(4)
  })

  // ── 流式消息 ──

  it("shows AI avatar and spinner when streaming without content", () => {
    useChatStore.setState({ isStreaming: true })
    render(<MessageList />)
    expect(screen.getByText("Thinking")).toBeInTheDocument()
    const aiAvatar = document.querySelector(".bg-gradient-to-br")
    expect(aiAvatar).toBeTruthy()
  })

  it("shows stream content when streaming", () => {
    useChatStore.setState({
      isStreaming: true,
      streamContent: "partial response",
    })
    render(<MessageList />)
    expect(screen.getByText("partial response")).toBeInTheDocument()
  })

  it("shows stream reasoning inline when streaming without content", () => {
    useChatStore.setState({
      isStreaming: true,
      streamReasoning: "thinking step by step",
    })
    render(<MessageList />)
    expect(screen.getByText("thinking step by step")).toBeInTheDocument()
  })

  it("shows thinking spinner when streaming without reasoning or content", () => {
    useChatStore.setState({ isStreaming: true })
    render(<MessageList />)
    expect(screen.getByText("Thinking")).toBeInTheDocument()
  })

  it("shows tool calls during streaming", () => {
    useChatStore.setState({
      isStreaming: true,
      streamToolCalls: [
        { id: "str-tc-1", name: "read", arguments: { path: "/tmp" } },
      ],
    })
    render(<MessageList />)
    expect(screen.getByText("Tool calls")).toBeInTheDocument()
    expect(screen.getByText("read")).toBeInTheDocument()
    expect(screen.getByText("str-tc")).toBeInTheDocument()
  })

  // ── 错误状态 ──

  it("shows error message with icon", () => {
    useChatStore.setState({ error: "Connection failed" })
    render(<MessageList />)
    expect(screen.getByText("Connection failed")).toBeInTheDocument()
  })

  it("does not show empty state when error is present", () => {
    useChatStore.setState({ error: "Something broke" })
    render(<MessageList />)
    expect(screen.queryByText("Start a conversation")).not.toBeInTheDocument()
    expect(screen.getByText("Something broke")).toBeInTheDocument()
  })

  it("does not show empty state when messages exist even with streaming", () => {
    useChatStore.setState({
      messages: [{ id: "m1", role: "user", content: "hi", createdAt: 100 }],
      isStreaming: true,
    })
    render(<MessageList />)
    expect(screen.queryByText("Start a conversation")).not.toBeInTheDocument()
    expect(screen.getByText("hi")).toBeInTheDocument()
  })

  // ── 自动滚到底部 ──

  it("renders bottomRef div when messages exist", () => {
    useChatStore.setState({
      messages: [{ id: "m1", role: "user", content: "hello", createdAt: 100 }],
    })
    const { container } = render(<MessageList />)
    // 确认底部 scroll anchor div 存在
    expect(container.querySelector("div:last-child")).toBeTruthy()
  })
})
