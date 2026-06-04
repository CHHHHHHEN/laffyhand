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

  describe("result formatting", () => {
    function expandResult(toolCall: ToolCall) {
      const utils = render(<ToolCallCard toolCall={toolCall} />)
      // Result is collapsed by default for non-diff results — click to expand
      const resultBtn = screen.getByText(/^Result$/)
      fireEvent.click(resultBtn)
      return utils
    }

    it("renders result as plain pre-formatted text, not Markdown", () => {
      const { container } = expandResult(makeToolCall({ result: "File **updated** successfully" }))
      // No Markdown rendering: bold syntax appears as literal text
      expect(screen.getByText("File **updated** successfully")).toBeInTheDocument()
      // The result is wrapped in a <pre> element
      expect(container.querySelector("pre")).toBeTruthy()
    })

    it("preserves whitespace and newlines in result", () => {
      const { container } = expandResult(makeToolCall({
        result: "Contents of /path (depth=2):\n  dir/\n  file.txt (42 lines)",
      }))
      const pres = container.querySelectorAll("pre")
      // First <pre> is arguments, second <pre> is the result
      const resultPre = pres[1]
      expect(resultPre).toBeTruthy()
      expect(resultPre?.textContent).toContain("Contents of /path (depth=2):")
      expect(resultPre?.textContent).toContain("  dir/")
      expect(resultPre?.textContent).toContain("  file.txt (42 lines)")
    })

    it("renders inline code as literal text in result", () => {
      expandResult(makeToolCall({ result: "Use `npx tsc` to check" }))
      // Backticks are literal, not code syntax
      expect(screen.getByText(/`npx tsc`/)).toBeInTheDocument()
    })

    it("renders code fence as literal text in result", () => {
      const { container } = expandResult(makeToolCall({ result: "```\nhello()\n```" }))
      const pres = container.querySelectorAll("pre")
      // Second <pre> is the result
      const resultPre = pres[1]
      expect(resultPre).toBeTruthy()
      expect(resultPre?.textContent).toContain("```")
      expect(resultPre?.textContent).toContain("hello()")
    })

    it("renders list markers as literal text in result", () => {
      expandResult(makeToolCall({ result: "- item 1\n- item 2" }))
      expect(screen.getByText(/- item 1/)).toBeInTheDocument()
      expect(screen.getByText(/- item 2/)).toBeInTheDocument()
    })

    it("renders links as literal text in result", () => {
      expandResult(makeToolCall({ result: "[open file](file:///test)" }))
      // Literal Markdown link syntax, not an <a> tag
      expect(screen.getByText(/\[open file\]/)).toBeInTheDocument()
    })

    it("renders HTML tags as literal text (safe, no XSS vector)", () => {
      expandResult(makeToolCall({ result: '<script>alert("xss")</script>clean result' }))
      // Inside <pre>, React escapes HTML — script tag is literal text
      expect(screen.getByText(/<script>alert/)).toBeInTheDocument()
      expect(screen.getByText(/clean result/)).toBeInTheDocument()
    })

    it("preserves whitespace alongside diff when result has both", () => {
      const toolCall = makeToolCall({
        result: [
          "File edited — replaced 1 occurrence",
          "",
          "--- /path/to/file",
          "+++ /path/to/file",
          "@@ -1 +1 @@",
          "-foo",
          "+bar",
        ].join("\n"),
      })
      render(<ToolCallCard toolCall={toolCall} />)
      // Auto-expanded due to diff — summary text is literal in <pre>
      expect(screen.getByText(/File edited — replaced 1 occurrence/)).toBeInTheDocument()
      // Diff content still visible
      expect(screen.getByText("bar")).toBeInTheDocument()
    })
  })
})
