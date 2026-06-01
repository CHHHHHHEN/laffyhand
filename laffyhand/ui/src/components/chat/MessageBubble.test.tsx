import { describe, it, expect } from "vitest"
import { render, screen } from "@testing-library/react"
import { MessageBubble } from "./MessageBubble"
import type { Message } from "@/types/session"

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
  it("renders user message", () => {
    render(<MessageBubble message={makeMessage({ role: "user", content: "test message" })} />)
    expect(screen.getByText("test message")).toBeInTheDocument()
  })

  it("renders assistant message", () => {
    render(<MessageBubble message={makeMessage({ role: "assistant", content: "assistant reply" })} />)
    expect(screen.getByText("assistant reply")).toBeInTheDocument()
  })

  it("renders tool calls when present", () => {
    render(
      <MessageBubble
        message={makeMessage({
          role: "assistant",
          content: "using tool",
          toolCalls: [{ id: "tc1", name: "bash", arguments: { cmd: "ls" } }],
        })}
      />,
    )
    expect(screen.getByText("bash")).toBeInTheDocument()
    expect(screen.getByText('{', { exact: false })).toBeInTheDocument()
  })

  it("renders usage info when present", () => {
    render(
      <MessageBubble
        message={makeMessage({
          role: "assistant",
          content: "done",
          usage: { inputTokens: 100, outputTokens: 50 },
        })}
      />,
    )
    expect(screen.getByText("↑100 ↓50")).toBeInTheDocument()
  })

  it("renders reasoning for assistant messages", () => {
    render(
      <MessageBubble
        message={makeMessage({
          role: "assistant",
          content: "answer",
          reasoning: "step by step",
        })}
      />,
    )
    expect(screen.getByText("step by step")).toBeInTheDocument()
  })
})
