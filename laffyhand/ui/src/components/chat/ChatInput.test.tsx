import { describe, it, expect, vi } from "vitest"
import { render, screen, fireEvent } from "@testing-library/react"
import { ChatInput } from "./ChatInput"
import { useUiStore } from "@/stores/ui-store"

describe("ChatInput", () => {
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

  it("shows busy mode selector and steer button when streaming", () => {
    const onSend = vi.fn()
    const onCancel = vi.fn()
    render(<ChatInput onSend={onSend} onSteer={vi.fn()} onCancel={onCancel} isStreaming={true} />)

    const textarea = screen.getByPlaceholderText("Type a message...")
    expect(textarea).toBeEnabled()

    // Busy mode selector should be visible
    expect(screen.getByText("When busy:")).toBeInTheDocument()

    // Default mode is "interrupt", so the submit button reads "Interrupt"
    const submitButtons = screen.getAllByText("Interrupt")
    const submitButton = submitButtons.find((btn) => btn.tagName === "BUTTON" && btn.getAttribute("type") === "button")
    expect(submitButton).toBeDefined()
    expect(submitButton).toBeDisabled()

    fireEvent.input(textarea, { target: { value: "a message" } })
    expect(submitButton).toBeEnabled()
  })

  it("calls onInterrupt when submitting in interrupt mode during streaming", () => {
    const onInterrupt = vi.fn()
    useUiStore.getState().setBusyMode("interrupt")
    render(<ChatInput onSend={vi.fn()} onInterrupt={onInterrupt} isStreaming={true} />)

    const textarea = screen.getByPlaceholderText("Type a message...")
    fireEvent.input(textarea, { target: { value: "interrupt message" } })
    fireEvent.keyDown(textarea, { key: "Enter" })

    expect(onInterrupt).toHaveBeenCalledWith("interrupt message")
  })

  it("calls onSteer when submitting in steer mode during streaming", () => {
    const onSteer = vi.fn()
    useUiStore.getState().setBusyMode("steer")
    render(<ChatInput onSend={vi.fn()} onSteer={onSteer} isStreaming={true} />)

    const textarea = screen.getByPlaceholderText("Type a message...")
    fireEvent.input(textarea, { target: { value: "steer message" } })
    fireEvent.keyDown(textarea, { key: "Enter" })

    expect(onSteer).toHaveBeenCalledWith("steer message")
  })

  it("calls onQueue when submitting in queue mode during streaming", () => {
    const onQueue = vi.fn()
    useUiStore.getState().setBusyMode("queue")
    render(<ChatInput onSend={vi.fn()} onQueue={onQueue} isStreaming={true} />)

    const textarea = screen.getByPlaceholderText("Type a message...")
    fireEvent.input(textarea, { target: { value: "queue message" } })
    fireEvent.keyDown(textarea, { key: "Enter" })

    expect(onQueue).toHaveBeenCalledWith("queue message")
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

  it("renders and triggers cancel button during streaming", () => {
    const onCancel = vi.fn()
    render(<ChatInput onSend={vi.fn()} onCancel={onCancel} isStreaming={true} />)

    const cancelButton = screen.getByTitle("Cancel current response")
    expect(cancelButton).toBeInTheDocument()
    fireEvent.click(cancelButton)
    expect(onCancel).toHaveBeenCalled()
  })
})
