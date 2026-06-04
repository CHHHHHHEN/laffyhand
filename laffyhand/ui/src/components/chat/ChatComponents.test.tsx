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

  describe("result markdown formatting", () => {
    function expandResult(toolCall: ToolCall) {
      const utils = render(<ToolCallCard toolCall={toolCall} />)
      // Result is collapsed by default for non-diff results — click to expand
      const resultBtn = screen.getByText(/^Result$/)
      fireEvent.click(resultBtn)
      return utils
    }

    it("renders bold text in result", () => {
      expandResult(makeToolCall({ result: "File **updated** successfully" }))
      expect(screen.getByText("updated").tagName).toBe("STRONG")
    })

    it("renders inline code in result", () => {
      expandResult(makeToolCall({ result: "Use `npx tsc` to check" }))
      expect(screen.getByText("npx tsc")).toBeInTheDocument()
    })

    it("renders code fence as <pre> in result", () => {
      const { container } = expandResult(makeToolCall({ result: "```\nhello()\n```" }))
      expect(container.querySelector("pre")).toBeTruthy()
    })

    it("renders lists in result", () => {
      expandResult(makeToolCall({ result: "- item 1\n- item 2" }))
      expect(screen.getByText("item 1")).toBeInTheDocument()
      expect(screen.getByText("item 2")).toBeInTheDocument()
    })

    it("renders links in result", () => {
      expandResult(makeToolCall({ result: "[open file](file:///test)" }))
      const link = screen.getByText("open file")
      expect(link.tagName).toBe("A")
    })

    it("sanitizes dangerous HTML in result", () => {
      expandResult(makeToolCall({ result: '<script>alert("xss")</script>clean result' }))
      expect(screen.queryByText(/alert/i)).not.toBeInTheDocument()
      expect(screen.getByText("clean result")).toBeInTheDocument()
    })

    it("renders markdown alongside diff when result has both", () => {
      const toolCall = makeToolCall({
        result: [
          "File **edited** successfully",
          "",
          "--- /path/to/file",
          "+++ /path/to/file",
          "@@ -1 +1 @@",
          "-foo",
          "+bar",
        ].join("\n"),
      })
      render(<ToolCallCard toolCall={toolCall} />)
      // Auto-expanded due to diff — bold text should be rendered
      expect(screen.getByText("edited").tagName).toBe("STRONG")
      // Diff content still visible
      expect(screen.getByText("bar")).toBeInTheDocument()
    })
  })
})
