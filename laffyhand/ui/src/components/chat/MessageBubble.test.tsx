import { describe, it, expect, vi } from "vitest"
import { render, screen, fireEvent, waitFor } from "@testing-library/react"
import { MessageBubble } from "./MessageBubble"
import type { Message } from "@/types/session"

vi.mock("@/lib/rpc", () => ({
  rpcClient: {
    permissionRespond: vi.fn().mockResolvedValue({ status: "ok" }),
  },
}))

const mockWriteText = vi.fn().mockResolvedValue(undefined)
Object.assign(navigator, {
  clipboard: { writeText: mockWriteText },
})

function makeMessage(overrides: Partial<Message> = {}): Message {
  return {
    id: "msg-1",
    role: "user",
    content: "Hello",
    createdAt: Date.now(),
    ...overrides,
  }
}

describe("MessageBubble", () => {
  // ── 基础渲染 ──

  it("renders user message with user avatar", () => {
    render(<MessageBubble message={makeMessage({ role: "user", content: "test message" })} />)
    expect(screen.getByText("test message")).toBeInTheDocument()
    const bubbleContainer = document.querySelector(".flex.items-start.gap-3")
    expect(bubbleContainer?.querySelector(".rounded-full")).toBeTruthy()
  })

  it("renders assistant message with AI avatar", () => {
    render(<MessageBubble message={makeMessage({ role: "assistant", content: "assistant reply" })} />)
    expect(screen.getByText("assistant reply")).toBeInTheDocument()
    const bubbleContainer = document.querySelector(".flex.items-start.gap-3")
    expect(bubbleContainer?.querySelector(".rounded-full")).toBeTruthy()
  })

  it("renders avatar on the left for both user and assistant", () => {
    const { rerender } = render(
      <MessageBubble message={makeMessage({ role: "user" })} />,
    )
    let container = document.querySelector(".flex.items-start.gap-3")
    expect(container).toBeTruthy()
    expect(container!.className).not.toContain("flex-row-reverse")

    rerender(<MessageBubble message={makeMessage({ role: "assistant" })} />)
    container = document.querySelector(".flex.items-start.gap-3")
    expect(container).toBeTruthy()
    expect(container!.className).not.toContain("flex-row-reverse")
  })

  // ── 工具调用 ──

  it("renders tool calls in card format when present", () => {
    render(
      <MessageBubble
        message={makeMessage({
          role: "assistant",
          content: "using tool",
          toolCalls: [{ id: "tc-abc123", name: "bash", arguments: { cmd: "ls" } }],
        })}
      />,
    )
    // 工具名称
    expect(screen.getByText("bash")).toBeInTheDocument()
    // 参数 JSON
    expect(screen.getByText(/"cmd"/)).toBeInTheDocument()
    expect(screen.getByText(/"ls"/)).toBeInTheDocument()
    // 短 ID（前6位）
    expect(screen.getByText("tc-abc")).toBeInTheDocument()
    // TOOL CALLS 标题（大写）
    expect(screen.getByText("Tool calls")).toBeInTheDocument()
    // 计数
    expect(screen.getByText("1")).toBeInTheDocument()
  })

  it("does not render tool calls section for empty array", () => {
    render(
      <MessageBubble
        message={makeMessage({
          role: "assistant",
          content: "no tools",
          toolCalls: [],
        })}
      />,
    )
    expect(screen.getByText("no tools")).toBeInTheDocument()
    expect(screen.queryByText("TOOL CALLS")).not.toBeInTheDocument()
  })

  it("renders multiple tool calls", () => {
    render(
      <MessageBubble
        message={makeMessage({
          role: "assistant",
          content: "multiple tools",
          toolCalls: [
            { id: "tc1", name: "read", arguments: { path: "/a" } },
            { id: "tc2", name: "write", arguments: { path: "/b" } },
          ],
        })}
      />,
    )
    expect(screen.getByText("read")).toBeInTheDocument()
    expect(screen.getByText("write")).toBeInTheDocument()
    // 分隔符 · 和计数的 2
    expect(screen.getByText("2")).toBeInTheDocument()
  })

  // ── Token 用量 ──

  it("renders usage badge with formatted numbers", () => {
    render(
      <MessageBubble
        message={makeMessage({
          role: "assistant",
          content: "done",
          usage: { inputTokens: 100, outputTokens: 50 },
        })}
      />,
    )
    // 用量分两个独立 span 显示
    expect(screen.getByText("100")).toBeInTheDocument()
    expect(screen.getByText("50")).toBeInTheDocument()
  })

  it("does not render usage badge when usage is absent", () => {
    render(
      <MessageBubble
        message={makeMessage({ role: "assistant", content: "no usage", createdAt: undefined })}
      />,
    )
    expect(screen.getByText("no usage")).toBeInTheDocument()
    const usageContainer = document.querySelector(".flex.items-center.justify-between.gap-2.pt-1")
    expect(usageContainer).toBeNull()
  })

  // ── 推理（折叠面板） ──

  it("shows reasoning collapsible button but hides content initially", () => {
    render(
      <MessageBubble
        message={makeMessage({
          role: "assistant",
          content: "answer",
          reasoning: "step by step",
        })}
      />,
    )
    // 折叠按钮可见
    expect(screen.getByText("Thinking")).toBeInTheDocument()
    expect(screen.getByText(/^Show/)).toBeInTheDocument()
    // 内容默认隐藏（不在 DOM 中）
    expect(screen.queryByText("step by step")).not.toBeInTheDocument()
  })

  it("expands reasoning content when clicking the button", () => {
    render(
      <MessageBubble
        message={makeMessage({
          role: "assistant",
          content: "final answer",
          reasoning: "deep thoughts here",
        })}
      />,
    )
    // 点击展开
    fireEvent.click(screen.getByText(/^Show/))
    expect(screen.getByText("deep thoughts here")).toBeInTheDocument()
    // 按钮文字变为 Hide
    expect(screen.getByText("Hide")).toBeInTheDocument()
  })

  it("collapses reasoning when clicking again", () => {
    render(
      <MessageBubble
        message={makeMessage({
          role: "assistant",
          content: "answer",
          reasoning: "toggle test",
        })}
      />,
    )
    const button = screen.getByText(/^Show/)
    fireEvent.click(button) // expand
    expect(screen.getByText("toggle test")).toBeInTheDocument()
    fireEvent.click(screen.getByText("Hide")) // collapse
    expect(screen.queryByText("toggle test")).not.toBeInTheDocument()
  })

  it("does not render reasoning block when reasoning is absent", () => {
    render(
      <MessageBubble
        message={makeMessage({ role: "assistant", content: "no reasoning" })}
      />,
    )
    expect(screen.getByText("no reasoning")).toBeInTheDocument()
    expect(screen.queryByText("Thinking")).not.toBeInTheDocument()
  })

  // ── 边缘情况 ──

  it("renders long content without crashing", () => {
    const longContent = "A".repeat(10000)
    render(
      <MessageBubble message={makeMessage({ role: "user", content: longContent })} />,
    )
    expect(screen.getByText(longContent)).toBeInTheDocument()
  })

  it("renders empty content gracefully", () => {
    render(
      <MessageBubble message={makeMessage({ role: "assistant", content: "" })} />,
    )
    const bubble = document.querySelector(".flex.items-start.gap-3")
    expect(bubble).toBeInTheDocument()
  })

  it("has entrance animation class", () => {
    render(<MessageBubble message={makeMessage({ role: "user" })} />)
    const container = document.querySelector(".flex.items-start.gap-3")
    expect(container!.className).toContain("animate-[message-in")
  })

  // ── 系统消息 ──

  it("renders system message with collapsed toggle", () => {
    render(
      <MessageBubble
        message={makeMessage({ role: "system", content: "You are a helpful assistant." })}
      />,
    )
    expect(screen.getByText("System prompt")).toBeInTheDocument()
    expect(screen.queryByText("You are a helpful assistant.")).not.toBeInTheDocument()
    // 切换箭头可见
    const chevron = document.querySelector(".rotate-90")
    expect(chevron).toBeNull() // 默认折叠，箭头不旋转
  })

  it("expands system message content on click", () => {
    render(
      <MessageBubble
        message={makeMessage({ role: "system", content: "System instruction here" })}
      />,
    )
    fireEvent.click(screen.getByText("System prompt"))
    expect(screen.getByText("System instruction here")).toBeInTheDocument()
  })

  it("collapses system message on second click", () => {
    render(
      <MessageBubble
        message={makeMessage({ role: "system", content: "Toggle me" })}
      />,
    )
    fireEvent.click(screen.getByText("System prompt")) // expand
    expect(screen.getByText("Toggle me")).toBeInTheDocument()
    fireEvent.click(screen.getByText("System prompt")) // collapse
    expect(screen.queryByText("Toggle me")).not.toBeInTheDocument()
  })

  it("renders system message container", () => {
    render(
      <MessageBubble
        message={makeMessage({ role: "system", content: "border test" })}
      />,
    )
    const container = document.querySelector(".rounded-lg")
    expect(container).toBeTruthy()
  })

  // ── 系统消息与普通消息不混淆 ──

  it("does not render system toggle for assistant messages", () => {
    render(
      <MessageBubble
        message={makeMessage({ role: "assistant", content: "reply" })}
      />,
    )
    expect(screen.queryByText("System prompt")).not.toBeInTheDocument()
  })

  it("does not render system toggle for user messages", () => {
    render(
      <MessageBubble
        message={makeMessage({ role: "user", content: "question" })}
      />,
    )
    expect(screen.queryByText("System prompt")).not.toBeInTheDocument()
  })

  // ── Permission request message ──

  it("renders permission request with permission and pattern", () => {
    render(
      <MessageBubble
        message={makeMessage({
          role: "permission-request",
          content: "Allow skill 'code-review'?",
          permissionInfo: { requestId: "r1", permission: "skill", pattern: "code-review" },
        })}
      />,
    )
    expect(screen.getByText("skill")).toBeInTheDocument()
    expect(screen.getByText((content) => content.includes("code-review"))).toBeInTheDocument()
  })

  it("shows three action buttons for unresolved permission", () => {
    render(
      <MessageBubble
        message={makeMessage({
          role: "permission-request",
          content: "Allow skill 'test'?",
          permissionInfo: { requestId: "r1", permission: "skill", pattern: "test" },
        })}
      />,
    )
    expect(screen.getByText("Deny")).toBeInTheDocument()
    expect(screen.getByText("Allow Once")).toBeInTheDocument()
    expect(screen.getByText("Always Allow")).toBeInTheDocument()
  })

  it("shows resolved text when permission is resolved", () => {
    render(
      <MessageBubble
        message={makeMessage({
          role: "permission-request",
          content: "Allow skill 'test'?",
          permissionInfo: { requestId: "r1", permission: "skill", pattern: "test", resolved: true },
        })}
      />,
    )
    expect(screen.getByText("Resolved")).toBeInTheDocument()
    expect(screen.queryByText("Deny")).not.toBeInTheDocument()
  })

  it("calls onResolvePermission after clicking Deny", async () => {
    const onResolve = vi.fn()
    render(
      <MessageBubble
        message={makeMessage({
          role: "permission-request",
          content: "Allow skill 'test'?",
          permissionInfo: { requestId: "r1", permission: "skill", pattern: "test" },
        })}
        onResolvePermission={onResolve}
      />,
    )
    fireEvent.click(screen.getByText("Deny"))
    await waitFor(() => expect(onResolve).toHaveBeenCalledWith("msg-1"))
  })

  it("calls onResolvePermission after clicking Allow Once", async () => {
    const onResolve = vi.fn()
    render(
      <MessageBubble
        message={makeMessage({
          role: "permission-request",
          content: "Allow skill 'test'?",
          permissionInfo: { requestId: "r1", permission: "skill", pattern: "test" },
        })}
        onResolvePermission={onResolve}
      />,
    )
    fireEvent.click(screen.getByText("Allow Once"))
    await waitFor(() => expect(onResolve).toHaveBeenCalledWith("msg-1"))
  })

  it("calls onResolvePermission after clicking Always Allow", async () => {
    const onResolve = vi.fn()
    render(
      <MessageBubble
        message={makeMessage({
          role: "permission-request",
          content: "Allow skill 'test'?",
          permissionInfo: { requestId: "r1", permission: "skill", pattern: "test" },
        })}
        onResolvePermission={onResolve}
      />,
    )
    fireEvent.click(screen.getByText("Always Allow"))
    await waitFor(() => expect(onResolve).toHaveBeenCalledWith("msg-1"))
  })

  it("does not render permission UI for non-permission messages", () => {
    render(
      <MessageBubble
        message={makeMessage({ role: "user", content: "hello" })}
      />,
    )
    expect(screen.queryByText("Allow")).not.toBeInTheDocument()
  })

  // ── Copy button ──

  it("renders copy button for user messages", () => {
    render(<MessageBubble message={makeMessage({ role: "user", content: "copy me" })} />)
    const copyBtn = screen.getByTitle("Copy message")
    expect(copyBtn).toBeInTheDocument()
  })

  it("renders copy button for assistant messages", () => {
    render(<MessageBubble message={makeMessage({ role: "assistant", content: "copy me too" })} />)
    const copyBtn = screen.getByTitle("Copy message")
    expect(copyBtn).toBeInTheDocument()
  })

  it("does not render copy button for system messages", () => {
    render(<MessageBubble message={makeMessage({ role: "system", content: "system msg" })} />)
    expect(screen.queryByTitle("Copy message")).not.toBeInTheDocument()
  })

  it("does not render copy button for permission-request messages", () => {
    render(
      <MessageBubble
        message={makeMessage({
          role: "permission-request",
          content: "allow?",
          permissionInfo: { requestId: "r1", permission: "skill", pattern: "test" },
        })}
      />,
    )
    expect(screen.queryByTitle("Copy message")).not.toBeInTheDocument()
  })

  it("copies message content to clipboard when clicked", async () => {
    mockWriteText.mockClear()
    render(<MessageBubble message={makeMessage({ role: "user", content: "content to copy" })} />)
    fireEvent.click(screen.getByTitle("Copy message"))
    await waitFor(() => {
      expect(mockWriteText).toHaveBeenCalledWith("content to copy")
    })
  })

  it("copies assistant message content to clipboard when clicked", async () => {
    mockWriteText.mockClear()
    render(<MessageBubble message={makeMessage({ role: "assistant", content: "assistant content" })} />)
    fireEvent.click(screen.getByTitle("Copy message"))
    await waitFor(() => {
      expect(mockWriteText).toHaveBeenCalledWith("assistant content")
    })
  })

  it("shows Copied! text after clicking and then reverts to copy icon", async () => {
    render(<MessageBubble message={makeMessage({ role: "user", content: "hello" })} />)
    fireEvent.click(screen.getByTitle("Copy message"))
    await waitFor(() => {
      expect(screen.getByText("Copied!")).toBeInTheDocument()
    })
    // After the copy feedback, the button should still be in the DOM
    expect(screen.getByTitle("Copy message")).toBeInTheDocument()
  })
})
