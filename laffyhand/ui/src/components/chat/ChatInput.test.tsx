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

  it("shows disabled state", () => {
    const onSend = vi.fn()
    render(<ChatInput onSend={onSend} disabled={true} />)

    const textarea = screen.getByPlaceholderText("Waiting for response...")
    expect(textarea).toBeDisabled()

    const button = screen.getByRole("button", { name: /send/i })
    expect(button).toBeDisabled()
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
