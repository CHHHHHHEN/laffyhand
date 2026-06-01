import { describe, it, expect, vi, beforeEach } from "vitest"
import { render, screen, fireEvent } from "@testing-library/react"
import { ChatInput } from "./ChatInput"
import { useUiStore } from "@/stores/ui-store"

beforeEach(() => {
  useUiStore.setState({ sidebarOpen: true, busyMode: "interrupt" })
})

describe("ChatInput", () => {
  // ── 基础发送 ──

  it("calls onSend with trimmed content on submit", () => {
    const onSend = vi.fn()
    render(<ChatInput onSend={onSend} />)

    const textarea = screen.getByPlaceholderText("Type a message...")
    fireEvent.input(textarea, { target: { value: "  hello world  " } })
    fireEvent.keyDown(textarea, { key: "Enter" })

    expect(onSend).toHaveBeenCalledWith("hello world")
    expect(textarea).toHaveValue("")
  })

  it("does not call onSend for empty input", () => {
    const onSend = vi.fn()
    render(<ChatInput onSend={onSend} />)

    const textarea = screen.getByPlaceholderText("Type a message...")
    fireEvent.keyDown(textarea, { key: "Enter" })

    expect(onSend).not.toHaveBeenCalled()
  })

  it("submits on button click", () => {
    const onSend = vi.fn()
    render(<ChatInput onSend={onSend} />)

    const textarea = screen.getByPlaceholderText("Type a message...")
    fireEvent.input(textarea, { target: { value: "click submit" } })

    const button = screen.getByRole("button", { name: /send/i })
    fireEvent.click(button)

    expect(onSend).toHaveBeenCalledWith("click submit")
  })

  it("does not submit with Shift+Enter", () => {
    const onSend = vi.fn()
    render(<ChatInput onSend={onSend} />)

    const textarea = screen.getByPlaceholderText("Type a message...")
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
    const textarea = screen.getByPlaceholderText("Type a message...")
    fireEvent.input(textarea, { target: { value: "text" } })
    expect(sendButton).toBeEnabled()

    // 清除内容后 disabled
    fireEvent.input(textarea, { target: { value: "" } })
    expect(sendButton).toBeDisabled()
  })

  // ── Streaming 状态 ──

  it("shows different placeholder text when streaming", () => {
    render(<ChatInput onSend={vi.fn()} isStreaming={true} />)

    expect(screen.getByPlaceholderText("Type a message to steer the AI...")).toBeInTheDocument()
    expect(screen.queryByPlaceholderText("Type a message...")).not.toBeInTheDocument()
  })

  it("shows busy mode selector when streaming", () => {
    render(<ChatInput onSend={vi.fn()} isStreaming={true} />)

    expect(screen.getByText("When busy:")).toBeInTheDocument()
    expect(screen.getByText("Interrupt")).toBeInTheDocument()
    expect(screen.getByText("Steer")).toBeInTheDocument()
    expect(screen.getByText("Queue")).toBeInTheDocument()
  })

  it("does not show busy mode selector when not streaming", () => {
    render(<ChatInput onSend={vi.fn()} />)
    expect(screen.queryByText("When busy:")).not.toBeInTheDocument()
  })

  it("shows cancel button when streaming", () => {
    const onCancel = vi.fn()
    render(<ChatInput onSend={vi.fn()} onCancel={onCancel} isStreaming={true} />)

    const cancelButton = screen.getByTitle("Cancel current response")
    expect(cancelButton).toBeInTheDocument()
    fireEvent.click(cancelButton)
    expect(onCancel).toHaveBeenCalled()
  })

  it("does not show cancel button when not streaming", () => {
    render(<ChatInput onSend={vi.fn()} />)
    expect(screen.queryByTitle("Cancel current response")).not.toBeInTheDocument()
  })

  // ── Busy Mode ──

  it("default busy mode is interrupt", () => {
    render(<ChatInput onSend={vi.fn()} isStreaming={true} />)

    // Interrupt 按钮应有 active 样式
    const interruptBtn = screen.getByTitle("Cancel current response and send")
    expect(interruptBtn.className).toContain("bg-amber-50")
    // 提交按钮显示 ⚡ Interrupt
    expect(screen.getByText("⚡")).toBeInTheDocument()
  })

  it("calls onInterrupt when submitting in interrupt mode during streaming", () => {
    const onInterrupt = vi.fn()
    render(<ChatInput onSend={vi.fn()} onInterrupt={onInterrupt} isStreaming={true} />)

    const textarea = screen.getByPlaceholderText("Type a message to steer the AI...")
    fireEvent.input(textarea, { target: { value: "interrupt message" } })
    fireEvent.keyDown(textarea, { key: "Enter" })

    expect(onInterrupt).toHaveBeenCalledWith("interrupt message")
  })

  it("calls onSteer when submitting in steer mode during streaming", () => {
    const onSteer = vi.fn()
    useUiStore.getState().setBusyMode("steer")
    render(<ChatInput onSend={vi.fn()} onSteer={onSteer} isStreaming={true} />)

    const textarea = screen.getByPlaceholderText("Type a message to steer the AI...")
    fireEvent.input(textarea, { target: { value: "steer message" } })
    fireEvent.keyDown(textarea, { key: "Enter" })

    expect(onSteer).toHaveBeenCalledWith("steer message")
  })

  it("calls onQueue when submitting in queue mode during streaming", () => {
    const onQueue = vi.fn()
    useUiStore.getState().setBusyMode("queue")
    render(<ChatInput onSend={vi.fn()} onQueue={onQueue} isStreaming={true} />)

    const textarea = screen.getByPlaceholderText("Type a message to steer the AI...")
    fireEvent.input(textarea, { target: { value: "queue message" } })
    fireEvent.keyDown(textarea, { key: "Enter" })

    expect(onQueue).toHaveBeenCalledWith("queue message")
  })

  it("switches busy mode on button click", () => {
    render(<ChatInput onSend={vi.fn()} isStreaming={true} />)

    // 默认 interrupt，找到 Queue busy mode 按钮并点击
    const queueBtn = screen.getByTitle("Send after current response finishes")
    expect(queueBtn).toBeInTheDocument()

    // 点击 Queue
    fireEvent.click(queueBtn)
    // 提交按钮文字更新
    expect(screen.getByText("📥")).toBeInTheDocument()
  })

  // ── 底部提示 ──

  it("shows bottom hint text", () => {
    render(<ChatInput onSend={vi.fn()} />)
    expect(screen.getByText("Shift+Enter for new line")).toBeInTheDocument()
  })

  // ── 按钮文字 ──

  it("shows 'Interrupt' submit button text in interrupt mode during streaming", () => {
    render(<ChatInput onSend={vi.fn()} isStreaming={true} />)
    // 提交按钮包含 ⚡ 和 Interrupt
    expect(screen.getByText("Interrupt")).toBeInTheDocument()
  })

  it("shows 'Steer' submit button text in steer mode during streaming", () => {
    useUiStore.getState().setBusyMode("steer")
    render(<ChatInput onSend={vi.fn()} isStreaming={true} />)
    expect(screen.getByText("Steer")).toBeInTheDocument()
  })

  it("shows 'Queue' submit button text in queue mode during streaming", () => {
    useUiStore.getState().setBusyMode("queue")
    render(<ChatInput onSend={vi.fn()} isStreaming={true} />)
    expect(screen.getByText("Queue")).toBeInTheDocument()
  })

  // ── 边缘情况 ──

  it("handles missing callback handlers gracefully", () => {
    // 只传 onSend，不传其他回调
    render(<ChatInput onSend={vi.fn()} isStreaming={true} />)
    const textarea = screen.getByPlaceholderText("Type a message to steer the AI...")
    // 点击 Submit 不应崩溃
    fireEvent.input(textarea, { target: { value: "test" } })
    const submitBtn = screen.getByText("Interrupt")
    expect(() => fireEvent.click(submitBtn)).not.toThrow()
  })
})
