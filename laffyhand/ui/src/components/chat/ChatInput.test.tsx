import { describe, it, expect, vi } from "vitest"
import { render, screen, fireEvent } from "@testing-library/react"
import { ChatInput } from "./ChatInput"

describe("ChatInput", () => {
  it("calls onSend with trimmed content on submit", () => {
    const onSend = vi.fn()
    render(<ChatInput onSend={onSend} />)

    const textarea = screen.getByPlaceholderText("Type a message...")
    fireEvent.input(textarea, { target: { value: "hello" } })
    fireEvent.keyDown(textarea, { key: "Enter" })

    expect(onSend).toHaveBeenCalledWith("hello")
    expect(textarea).toHaveValue("")
  })

  it("does not call onSend for empty input", () => {
    const onSend = vi.fn()
    render(<ChatInput onSend={onSend} />)

    const textarea = screen.getByPlaceholderText("Type a message...")
    fireEvent.keyDown(textarea, { key: "Enter" })

    expect(onSend).not.toHaveBeenCalled()
  })

  it("shows steer state", () => {
    const onSend = vi.fn()
    const onSteer = vi.fn()
    const onCancel = vi.fn()
    render(<ChatInput onSend={onSend} onSteer={onSteer} onCancel={onCancel} isStreaming={true} />)

    const textarea = screen.getByPlaceholderText("Type to steer the AI...")
    expect(textarea).toBeEnabled()

    const steerButton = screen.getByRole("button", { name: /steer/i })
    // Button is disabled when textarea is empty (controlled input)
    expect(steerButton).toBeDisabled()

    fireEvent.input(textarea, { target: { value: "steer message" } })
    expect(steerButton).toBeEnabled()
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
})
