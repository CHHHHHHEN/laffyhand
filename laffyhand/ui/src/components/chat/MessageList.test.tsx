import { describe, it, expect, beforeEach, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import { MessageList } from "./MessageList"
import { useChatStore, resetMessageCounter } from "@/stores/chat-store"

const SID = "test-sess"

beforeEach(() => {
  HTMLDivElement.prototype.scrollIntoView = vi.fn()
  resetMessageCounter()
  useChatStore.setState({ sessions: {} })
  useChatStore.getState().addSession(SID)
})

function renderList() {
  return render(<MessageList sessionId={SID} />)
}

describe("MessageList", () => {
  it("shows empty state with title and subtitle", () => {
    renderList()
    expect(screen.getByText("Start a conversation")).toBeDefined()
    expect(screen.getByText("Send a message to begin chatting with your AI agent")).toBeDefined()
  })

  it("shows empty state icon container", () => {
    renderList()
    const iconContainer = document.querySelector(".rounded-2xl")
    expect(iconContainer).toBeTruthy()
  })

  it("renders messages", () => {
    useChatStore.getState().loadMessages(SID, [
      { id: "m1", role: "user", content: "hello", createdAt: 100 },
      { id: "m2", role: "assistant", content: "hi there", createdAt: 200 },
    ])
    renderList()
    expect(screen.getByText("hello")).toBeInTheDocument()
    expect(screen.getByText("hi there")).toBeInTheDocument()
  })

  it("renders multiple user/assistant messages in order", () => {
    useChatStore.getState().loadMessages(SID, [
      { id: "m1", role: "user", content: "first", createdAt: 100 },
      { id: "m2", role: "assistant", content: "reply1", createdAt: 200 },
      { id: "m3", role: "user", content: "second", createdAt: 300 },
      { id: "m4", role: "assistant", content: "reply2", createdAt: 400 },
    ])
    renderList()
    const texts = screen.getAllByText(/first|reply1|second|reply2/)
    expect(texts).toHaveLength(4)
  })

  it("shows AI avatar and spinner when streaming without content", () => {
    useChatStore.getState().startStreaming(SID)
    renderList()
    expect(screen.getByText("Thinking")).toBeInTheDocument()
    const aiAvatar = document.querySelector(".ring-1")
    expect(aiAvatar).toBeTruthy()
  })

  it("shows stream content when streaming", () => {
    useChatStore.getState().startStreaming(SID)
    useChatStore.getState().appendContent(SID, "partial response")
    renderList()
    expect(screen.getByText("partial response")).toBeInTheDocument()
  })

  it("renders markdown in stream content", () => {
    useChatStore.getState().startStreaming(SID)
    useChatStore.getState().appendContent(SID, "hello **bold** world")
    renderList()
    expect(screen.getByText("bold").tagName).toBe("STRONG")
  })

  it("renders code fence in stream content", () => {
    useChatStore.getState().startStreaming(SID)
    useChatStore.getState().appendContent(SID, "```\ncode\n```")
    renderList()
    expect(document.querySelector("pre")).toBeTruthy()
  })

  it("shows stream reasoning inside ReasoningBlock when streaming without content", () => {
    useChatStore.getState().startStreaming(SID)
    useChatStore.getState().setReasoning(SID, "thinking step by step")
    renderList()
    expect(screen.getByText("Hide")).toBeInTheDocument()
    expect(screen.getByText("thinking step by step")).toBeInTheDocument()
  })

  it("shows thinking spinner when streaming without reasoning or content", () => {
    useChatStore.getState().startStreaming(SID)
    renderList()
    expect(screen.getByText("Thinking")).toBeInTheDocument()
  })

  it("shows tool calls during streaming", () => {
    useChatStore.getState().startStreaming(SID)
    useChatStore.getState().addToolCall(SID, {
      id: "str-tc-1",
      name: "read",
      arguments: { path: "/tmp" },
    })
    renderList()
    expect(screen.getByText("Tool calls")).toBeInTheDocument()
    expect(screen.getByText("read")).toBeInTheDocument()
    expect(screen.getByText("str-tc")).toBeInTheDocument()
  })

  it("shows error message with icon", () => {
    useChatStore.getState().setError(SID, "Connection failed")
    renderList()
    expect(screen.getByText("Connection failed")).toBeInTheDocument()
  })

  it("does not show empty state when error is present", () => {
    useChatStore.getState().setError(SID, "Something broke")
    renderList()
    expect(screen.queryByText("Start a conversation")).not.toBeInTheDocument()
    expect(screen.getByText("Something broke")).toBeInTheDocument()
  })

  it("does not show empty state when messages exist even with streaming", () => {
    useChatStore.getState().loadMessages(SID, [
      { id: "m1", role: "user", content: "hi", createdAt: 100 },
    ])
    useChatStore.getState().startStreaming(SID)
    renderList()
    expect(screen.queryByText("Start a conversation")).not.toBeInTheDocument()
    expect(screen.getByText("hi")).toBeInTheDocument()
  })

  it("renders bottomRef div when messages exist", () => {
    useChatStore.getState().loadMessages(SID, [
      { id: "m1", role: "user", content: "hello", createdAt: 100 },
    ])
    const { container } = renderList()
    expect(container.querySelector("div:last-child")).toBeTruthy()
  })
})
