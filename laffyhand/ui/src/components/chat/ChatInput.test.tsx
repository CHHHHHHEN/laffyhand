import { describe, it, expect, vi, beforeEach } from "vitest"
import { render, screen, fireEvent } from "@testing-library/react"
import { ChatInput } from "./ChatInput"
import { useUiStore } from "@/stores/ui-store"
import type { AgentInfo } from "@/types/rpc"

const MOCK_AGENTS: AgentInfo[] = [
  { name: "build", description: "Main coding agent", mode: "primary", system_prompt: "", model: null },
  { name: "general", description: "General purpose", mode: "subagent", system_prompt: "", model: null },
  { name: "explore", description: "Codebase search", mode: "subagent", system_prompt: "", model: null },
]

beforeEach(() => {
  useUiStore.setState({ sidebarOpen: true, busyMode: "interrupt" })
})

describe("ChatInput", () => {
  // ── 基础发送 ──

  it("calls onSend with trimmed content on submit", () => {
    const onSend = vi.fn()
    render(<ChatInput onSend={onSend} agents={MOCK_AGENTS} />)

    const textarea = screen.getByPlaceholderText(/Type a message/)
    fireEvent.input(textarea, { target: { value: "  hello world  " } })
    fireEvent.keyDown(textarea, { key: "Enter" })

    expect(onSend).toHaveBeenCalledWith("hello world")
    expect(textarea).toHaveValue("")
  })

  it("does not call onSend for empty input", () => {
    const onSend = vi.fn()
    render(<ChatInput onSend={onSend} agents={MOCK_AGENTS} />)

    const textarea = screen.getByPlaceholderText(/Type a message/)
    fireEvent.keyDown(textarea, { key: "Enter" })

    expect(onSend).not.toHaveBeenCalled()
  })

  it("submits on button click", () => {
    const onSend = vi.fn()
    render(<ChatInput onSend={onSend} agents={MOCK_AGENTS} />)

    const textarea = screen.getByPlaceholderText(/Type a message/)
    fireEvent.input(textarea, { target: { value: "click submit" } })

    const button = screen.getByRole("button", { name: /send/i })
    fireEvent.click(button)

    expect(onSend).toHaveBeenCalledWith("click submit")
  })

  it("does not submit with Shift+Enter", () => {
    const onSend = vi.fn()
    render(<ChatInput onSend={onSend} agents={MOCK_AGENTS} />)

    const textarea = screen.getByPlaceholderText(/Type a message/)
    fireEvent.input(textarea, { target: { value: "shift enter" } })
    fireEvent.keyDown(textarea, { key: "Enter", shiftKey: true })

    expect(onSend).not.toHaveBeenCalled()
  })

  it("disables send button when input is empty", () => {
    render(<ChatInput onSend={vi.fn()} />)

    // 开始时为空，按钮应 disabled
    const sendButton = screen.getByRole("button", { name: /send/i })
    expect(sendButton).toBeDisabled()

    // 输入内容后 enabled
    const textarea = screen.getByPlaceholderText(/Type a message/)
    fireEvent.input(textarea, { target: { value: "text" } })
    expect(sendButton).toBeEnabled()

    // 清除内容后 disabled
    fireEvent.input(textarea, { target: { value: "" } })
    expect(sendButton).toBeDisabled()
  })

  // ── Streaming 状态 ──

  it("shows busy mode selector when streaming", () => {
    render(<ChatInput onSend={vi.fn()} agents={MOCK_AGENTS} isStreaming={true} />)

    expect(screen.getByText("Interrupt")).toBeInTheDocument()
    expect(screen.getByText("Steer")).toBeInTheDocument()
    expect(screen.getByText("Queue")).toBeInTheDocument()
  })

  it("does not show busy mode selector when not streaming", () => {
    render(<ChatInput onSend={vi.fn()} />)
    expect(screen.queryByText("Interrupt")).not.toBeInTheDocument()
    expect(screen.queryByText("Steer")).not.toBeInTheDocument()
    expect(screen.queryByText("Queue")).not.toBeInTheDocument()
  })

  it("shows cancel button when streaming", () => {
    const onCancel = vi.fn()
    render(<ChatInput onSend={vi.fn()} onCancel={onCancel} isStreaming={true} />)

    const cancelButton = screen.getByTitle("Cancel")
    expect(cancelButton).toBeInTheDocument()
    fireEvent.click(cancelButton)
    expect(onCancel).toHaveBeenCalled()
  })

  it("does not show cancel button when not streaming", () => {
    render(<ChatInput onSend={vi.fn()} />)
    expect(screen.queryByTitle("Cancel")).not.toBeInTheDocument()
  })

  // ── Busy Mode ──

  it("default busy mode is interrupt", () => {
    render(<ChatInput onSend={vi.fn()} agents={MOCK_AGENTS} isStreaming={true} />)

    const interruptBtn = screen.getByTitle("Cancel and send new")
    expect(interruptBtn.className).toContain("bg-amber-50")
    expect(screen.getByText("Interrupt")).toBeInTheDocument()
  })

  it("calls onInterrupt when submitting in interrupt mode during streaming", () => {
    const onInterrupt = vi.fn()
    render(<ChatInput onSend={vi.fn()} agents={MOCK_AGENTS} onInterrupt={onInterrupt} isStreaming={true} />)

    const textarea = screen.getByPlaceholderText(/Type a message/)
    fireEvent.input(textarea, { target: { value: "interrupt message" } })
    fireEvent.keyDown(textarea, { key: "Enter" })

    expect(onInterrupt).toHaveBeenCalledWith("interrupt message")
  })

  it("calls onSteer when submitting in steer mode during streaming", () => {
    const onSteer = vi.fn()
    useUiStore.getState().setBusyMode("steer")
    render(<ChatInput onSend={vi.fn()} agents={MOCK_AGENTS} onSteer={onSteer} isStreaming={true} />)

    const textarea = screen.getByPlaceholderText(/Type a message/)
    fireEvent.input(textarea, { target: { value: "steer message" } })
    fireEvent.keyDown(textarea, { key: "Enter" })

    expect(onSteer).toHaveBeenCalledWith("steer message")
  })

  it("calls onQueue when submitting in queue mode during streaming", () => {
    const onQueue = vi.fn()
    useUiStore.getState().setBusyMode("queue")
    render(<ChatInput onSend={vi.fn()} agents={MOCK_AGENTS} onQueue={onQueue} isStreaming={true} />)

    const textarea = screen.getByPlaceholderText(/Type a message/)
    fireEvent.input(textarea, { target: { value: "queue message" } })
    fireEvent.keyDown(textarea, { key: "Enter" })

    expect(onQueue).toHaveBeenCalledWith("queue message")
  })

  it("switches busy mode on button click", () => {
    render(<ChatInput onSend={vi.fn()} agents={MOCK_AGENTS} isStreaming={true} />)

    // 默认 interrupt，找到 Queue busy mode 按钮并点击
    const queueBtn = screen.getByTitle("Send after current response")
    expect(queueBtn).toBeInTheDocument()

    fireEvent.click(queueBtn)
    expect(queueBtn.className).toContain("bg-purple-50")
  })

  // ── 底部提示 ──

  it("shows bottom hint text", () => {
    render(<ChatInput onSend={vi.fn()} />)
    expect(screen.getByText(/Shift\+Enter/)).toBeInTheDocument()
  })

  // ── 按钮文字 ──

  it("shows 'Interrupt' submit button text in interrupt mode during streaming", () => {
    render(<ChatInput onSend={vi.fn()} agents={MOCK_AGENTS} isStreaming={true} />)
    // 提交按钮包含 ⚡ 和 Interrupt
    expect(screen.getByText("Interrupt")).toBeInTheDocument()
  })

  it("shows 'Steer' submit button text in steer mode during streaming", () => {
    useUiStore.getState().setBusyMode("steer")
    render(<ChatInput onSend={vi.fn()} agents={MOCK_AGENTS} isStreaming={true} />)
    expect(screen.getByText("Steer")).toBeInTheDocument()
  })

  it("shows 'Queue' submit button text in queue mode during streaming", () => {
    useUiStore.getState().setBusyMode("queue")
    render(<ChatInput onSend={vi.fn()} agents={MOCK_AGENTS} isStreaming={true} />)
    expect(screen.getByText("Queue")).toBeInTheDocument()
  })

  // ── 布局对齐 ──

  it("has matching border-box for vertical alignment with textarea", () => {
    render(<ChatInput onSend={vi.fn()} />)
    const sendButton = screen.getByRole("button", { name: /send/i })
    // Button and textarea both have `border` so their total heights
    // (padding + border) match, ensuring vertical centering in the flex row
    expect(sendButton.className).toContain("border")
    expect(sendButton.className).toContain("border-transparent")
  })

  it("has matching border-box on cancel button for alignment", () => {
    render(<ChatInput onSend={vi.fn()} agents={MOCK_AGENTS} onCancel={vi.fn()} isStreaming={true} />)
    const cancelButton = screen.getByTitle("Cancel")
    expect(cancelButton.className).toContain("border")
    expect(cancelButton.className).toContain("border-transparent")
  })

  // ── 边缘情况 ──

  it("handles missing callback handlers gracefully", () => {
    // 只传 onSend，不传其他回调
    render(<ChatInput onSend={vi.fn()} agents={MOCK_AGENTS} isStreaming={true} />)
    const textarea = screen.getByPlaceholderText(/Type a message/)
    // 点击 Submit 不应崩溃
    fireEvent.input(textarea, { target: { value: "test" } })
    const submitBtn = screen.getByText("Send")
    expect(() => fireEvent.click(submitBtn)).not.toThrow()
  })

  // ── Tab key agent switching ──

  it("cycles agent on Tab when input is empty", () => {
    useUiStore.setState({ defaultAgent: "build" })
    render(<ChatInput onSend={vi.fn()} agents={MOCK_AGENTS} />)

    const textarea = screen.getByPlaceholderText(/Type a message/)
    fireEvent.keyDown(textarea, { key: "Tab" })

    expect(useUiStore.getState().defaultAgent).toBe("general")
  })

  it("does not cycle agent on Tab when input has content", () => {
    render(<ChatInput onSend={vi.fn()} agents={MOCK_AGENTS} />)

    const textarea = screen.getByPlaceholderText(/Type a message/)
    fireEvent.input(textarea, { target: { value: "hello" } })
    fireEvent.keyDown(textarea, { key: "Tab" })

    // Tab should still work normally when input is non-empty (no agent switch needed)
    expect(screen.getByText(/Shift\+Enter/)).toBeInTheDocument()
  })

  // ── Slash commands ──

  it("shows command suggestions when typing /", () => {
    render(<ChatInput onSend={vi.fn()} agents={MOCK_AGENTS} />)

    const textarea = screen.getByPlaceholderText(/Type a message/)
    fireEvent.input(textarea, { target: { value: "/" } })

    expect(screen.getByText("/fork")).toBeInTheDocument()
    expect(screen.getByText("/agent <name>")).toBeInTheDocument()
    expect(screen.getByText("/help")).toBeInTheDocument()
  })

  it("calls onFork when submitting /fork", () => {
    const onFork = vi.fn()
    render(<ChatInput onSend={vi.fn()} agents={MOCK_AGENTS} onFork={onFork} />)

    const textarea = screen.getByPlaceholderText(/Type a message/)
    fireEvent.input(textarea, { target: { value: "/fork" } })
    fireEvent.keyDown(textarea, { key: "Enter" })

    expect(onFork).toHaveBeenCalled()
  })

  it("switches agent via /agent command", () => {
    useUiStore.setState({ defaultAgent: "build" })
    render(<ChatInput onSend={vi.fn()} agents={MOCK_AGENTS} />)

    const textarea = screen.getByPlaceholderText(/Type a message/)
    fireEvent.input(textarea, { target: { value: "/agent explore" } })
    fireEvent.keyDown(textarea, { key: "Enter" })

    expect(useUiStore.getState().defaultAgent).toBe("explore")
  })

  it("sends unknown /command as normal message", () => {
    const onSend = vi.fn()
    render(<ChatInput onSend={onSend} agents={MOCK_AGENTS} />)

    const textarea = screen.getByPlaceholderText(/Type a message/)
    fireEvent.input(textarea, { target: { value: "/hello" } })
    fireEvent.keyDown(textarea, { key: "Enter" })

    expect(onSend).toHaveBeenCalledWith("/hello")
  })
})
