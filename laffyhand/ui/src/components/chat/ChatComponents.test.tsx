import { describe, it, expect, vi, beforeAll } from "vitest"
import { render, screen, fireEvent } from "@testing-library/react"
import { ToolCallCard } from "./ChatComponents"
import type { ToolCall } from "@/types/session"

// Mock ResizeObserver for DiffView (used inside ToolCallCard when result has diff)
class MockResizeObserver {
  callback: ResizeObserverCallback
  constructor(callback: ResizeObserverCallback) {
    this.callback = callback
  }
  observe = vi.fn()
  unobserve = vi.fn()
  disconnect = vi.fn()
}

beforeAll(() => {
  vi.stubGlobal("ResizeObserver", MockResizeObserver)
})

function makeToolCall(overrides: Partial<ToolCall> = {}): ToolCall {
  return {
    id: "tc-abc123",
    name: "edit",
    arguments: { file_path: "/test.txt", old_string: "foo", new_string: "bar" },
    status: "completed",
    ...overrides,
  }
}

describe("ToolCallCard", () => {
  it("renders tool name and id", () => {
    render(<ToolCallCard toolCall={makeToolCall({ name: "bash" })} />)
    expect(screen.getByText("bash")).toBeInTheDocument()
    expect(screen.getByText("tc-abc")).toBeInTheDocument()
  })

  it("shows done badge for completed status", () => {
    render(<ToolCallCard toolCall={makeToolCall({ status: "completed" })} />)
    expect(screen.getByText("done")).toBeInTheDocument()
  })

  it("shows failed badge for error status", () => {
    render(<ToolCallCard toolCall={makeToolCall({ status: "error" })} />)
    expect(screen.getByText("failed")).toBeInTheDocument()
  })

  it("renders arguments as JSON", () => {
    render(
      <ToolCallCard
        toolCall={makeToolCall({
          arguments: { cmd: "ls", path: "/tmp" },
        })}
      />,
    )
    expect(screen.getByText(/"cmd"/)).toBeInTheDocument()
    expect(screen.getByText(/"ls"/)).toBeInTheDocument()
  })

  describe("result auto-expand", () => {
    it("auto-expands result when it contains a diff", () => {
      const toolCall = makeToolCall({
        result: [
          "Edited file: replaced 1 occurrence",
          "",
          "--- /path/to/file",
          "+++ /path/to/file",
          "@@ -1 +1 @@",
          "-foo",
          "+bar",
        ].join("\n"),
      })
      render(<ToolCallCard toolCall={toolCall} />)
      // The diff content should be visible without clicking
      expect(screen.getByText("bar")).toBeInTheDocument()
      expect(screen.getByText("foo")).toBeInTheDocument()
    })

    it("collapses result when it has no diff", () => {
      const toolCall = makeToolCall({
        result: "File written: /tmp/test.txt (42 chars)",
      })
      render(<ToolCallCard toolCall={toolCall} />)
      // Summary should show in collapsed form as text next to "Result" label
      expect(screen.getByText(/42 chars/)).toBeInTheDocument()
      // Diff content should not be visible
      expect(screen.queryByText("Result")).toBeInTheDocument()
    })

    it("toggles result on click when auto-expanded", () => {
      const toolCall = makeToolCall({
        result: [
          "Edited file: replaced 1 occurrence",
          "",
          "--- /path/to/file",
          "+++ /path/to/file",
          "@@ -1 +1 @@",
          "-foo",
          "+bar",
        ].join("\n"),
      })
      render(<ToolCallCard toolCall={toolCall} />)
      // Initially expanded - diff visible
      expect(screen.getByText("bar")).toBeInTheDocument()

      // Click to collapse
      fireEvent.click(screen.getByText(/Result/))
      expect(screen.queryByText("bar")).not.toBeInTheDocument()

      // Click to expand again
      fireEvent.click(screen.getByText(/Result/))
      expect(screen.getByText("bar")).toBeInTheDocument()
    })
  })
})
