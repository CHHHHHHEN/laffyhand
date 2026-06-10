import { describe, it, expect } from "vitest"
import { render, screen, fireEvent } from "@testing-library/react"
import { SubagentCard, SubagentTreeCard } from "./SubagentCard"
import type { ActiveSubagent, SubagentTool, SubagentEvent } from "@/types/session"
import type { SubagentTreeNode } from "@/lib/subagentTree"

function makeTool(overrides: Partial<SubagentTool> = {}): SubagentTool {
  return { name: "grep", input: "search pattern", ...overrides }
}

function makeSubagent(overrides: Partial<ActiveSubagent> = {}): ActiveSubagent {
  return {
    id: "sa-1",
    parentId: null,
    agentType: "explore",
    description: "Search the codebase for test files",
    depth: 0,
    status: "completed",
    text: "",
    reasoning: "",
    tools: [],
    toolCount: 0,
    summary: undefined,
    inputTokens: 0,
    outputTokens: 0,
    events: [],
    ...overrides,
  }
}

describe("SubagentCard", () => {
  describe("header", () => {
    it("shows agent type name", () => {
      render(<SubagentCard subagent={makeSubagent({ agentType: "general" })} />)
      expect(screen.getByText("general")).toBeInTheDocument()
    })

    it("shows running label when status is running", () => {
      render(<SubagentCard subagent={makeSubagent({ status: "running" })} />)
      expect(screen.getByText("running")).toBeInTheDocument()
    })

    it("shows tool count in header when completed with tools", () => {
      const sub = makeSubagent({ toolCount: 3, status: "completed" })
      render(<SubagentCard subagent={sub} />)
      expect(screen.getByText("3 tools")).toBeInTheDocument()
    })

    it("shows description text in header", () => {
      const sub = makeSubagent({ description: "Find all TODO comments" })
      render(<SubagentCard subagent={sub} />)
      expect(screen.getByText("Find all TODO comments")).toBeInTheDocument()
    })
  })

  describe("default expanded state", () => {
    it("is expanded by default when running", () => {
      const sub = makeSubagent({ status: "running", summary: "working on it" })
      render(<SubagentCard subagent={sub} />)
      expect(screen.getByText("working on it")).toBeInTheDocument()
    })

    it("is expanded by default when completed", () => {
      const sub = makeSubagent({ status: "completed", summary: "done" })
      render(<SubagentCard subagent={sub} />)
      expect(screen.getByText("done")).toBeInTheDocument()
    })
  })

  describe("expanded content", () => {
    it("shows reasoning when present", () => {
      const sub = makeSubagent({ reasoning: "Let me analyze this" })
      render(<SubagentCard subagent={sub} />)
      expect(screen.getByText("Let me analyze this")).toBeInTheDocument()
    })

    it("shows text output when present", () => {
      const sub = makeSubagent({ text: "Found 42 matches" })
      render(<SubagentCard subagent={sub} />)
      expect(screen.getByText("Found 42 matches")).toBeInTheDocument()
    })

    it("shows tool calls when present", () => {
      const sub = makeSubagent({
        tools: [makeTool({ name: "grep", input: "TODO" })],
        toolCount: 1,
      })
      render(<SubagentCard subagent={sub} />)
      expect(screen.getByText("grep")).toBeInTheDocument()
      expect(screen.getByText("TODO")).toBeInTheDocument()
    })

    it("shows tool result when tool has result and result is expanded", () => {
      const sub = makeSubagent({
        tools: [makeTool({ name: "grep", input: "TODO", result: "file1.ts:42" })],
        toolCount: 1,
      })
      render(<SubagentCard subagent={sub} />)
      fireEvent.click(screen.getByText("Result"))
      expect(screen.getByText("file1.ts:42")).toBeInTheDocument()
    })

    it("marks error tool results with error styling", () => {
      const sub = makeSubagent({
        tools: [makeTool({ name: "bash", input: "invalid cmd", result: "command not found", isError: true })],
        toolCount: 1,
      })
      render(<SubagentCard subagent={sub} />)
      fireEvent.click(screen.getByText("Result"))
      const errorText = screen.getByText("command not found")
      expect(errorText).toBeInTheDocument()
      expect(errorText.className).toContain("text-red-500")
    })

    it("shows summary when present", () => {
      const sub = makeSubagent({ summary: "Found 42 results" })
      render(<SubagentCard subagent={sub} />)
      expect(screen.getByText("Found 42 results")).toBeInTheDocument()
    })

    it("shows token usage when present", () => {
      const sub = makeSubagent({ inputTokens: 150, outputTokens: 75 })
      render(<SubagentCard subagent={sub} />)
      expect(screen.getByText((c) => c.includes("150"))).toBeInTheDocument()
      expect(screen.getByText((c) => c.includes("75"))).toBeInTheDocument()
    })

    it("shows thinking spinner when running without text or reasoning", () => {
      const sub = makeSubagent({ status: "running", text: "", reasoning: "" })
      render(<SubagentCard subagent={sub} />)
      expect(screen.getByText("Thinking")).toBeInTheDocument()
    })
  })

  describe("prompt", () => {
    it("shows prompt toggle when prompt is present", () => {
      const sub = makeSubagent({ prompt: "Find all bugs in the codebase" })
      render(<SubagentCard subagent={sub} />)
      expect(screen.getByText("Prompt")).toBeInTheDocument()
    })

    it("shows prompt content when toggled", () => {
      const sub = makeSubagent({ prompt: "Find all bugs in the codebase" })
      render(<SubagentCard subagent={sub} />)
      fireEvent.click(screen.getByText("Prompt"))
      expect(screen.getByText("Find all bugs in the codebase")).toBeInTheDocument()
    })

    it("hides prompt content when toggled again", () => {
      const sub = makeSubagent({ prompt: "Find all bugs in the codebase" })
      render(<SubagentCard subagent={sub} />)
      fireEvent.click(screen.getByText("Prompt"))
      expect(screen.getByText("Find all bugs in the codebase")).toBeInTheDocument()
      fireEvent.click(screen.getByText("Prompt"))
      expect(screen.queryByText("Find all bugs in the codebase")).not.toBeInTheDocument()
    })

    it("does not show prompt toggle when prompt is absent", () => {
      const sub = makeSubagent({ prompt: undefined })
      render(<SubagentCard subagent={sub} />)
      expect(screen.queryByText("Prompt")).not.toBeInTheDocument()
    })
  })

  describe("tool results", () => {
    it("shows result toggle button when tool has result", () => {
      const sub = makeSubagent({
        tools: [makeTool({ result: "output here" })],
        toolCount: 1,
      })
      render(<SubagentCard subagent={sub} />)
      expect(screen.getByText("Result")).toBeInTheDocument()
    })

    it("hides result toggle button when tool has no result", () => {
      const sub = makeSubagent({
        tools: [makeTool({ result: undefined })],
        toolCount: 1,
      })
      render(<SubagentCard subagent={sub} />)
      expect(screen.queryByText("Result")).not.toBeInTheDocument()
    })

    it("toggles result visibility on click", () => {
      const sub = makeSubagent({
        tools: [makeTool({ result: "detailed output" })],
        toolCount: 1,
      })
      render(<SubagentCard subagent={sub} />)
      fireEvent.click(screen.getByText("Result"))
      expect(screen.getByText("detailed output")).toBeInTheDocument()
      fireEvent.click(screen.getByText("Hide"))
      expect(screen.queryByText("detailed output")).not.toBeInTheDocument()
    })
  })

  describe("interaction", () => {
    it("toggles expanded state on header click", () => {
      const sub = makeSubagent({ summary: "hidden content" })
      render(<SubagentCard subagent={sub} />)
      expect(screen.getByText("hidden content")).toBeInTheDocument()
      fireEvent.click(screen.getByText("explore"))
      expect(screen.queryByText("hidden content")).not.toBeInTheDocument()
      fireEvent.click(screen.getByText("explore"))
      expect(screen.getByText("hidden content")).toBeInTheDocument()
    })
  })

  describe("depth indentation", () => {
    it("applies marginLeft based on depth", () => {
      const sub = makeSubagent()
      const { container } = render(<SubagentCard subagent={sub} depth={2} />)
      const inner = container.firstChild as HTMLElement
      expect(inner.style.marginLeft).toBe("32px")
    })
  })

  // ── Event-based chronological rendering ──

  describe("event rendering", () => {
    it("renders events in chronological order", () => {
      const events: SubagentEvent[] = [
        { kind: "text", content: "First I search" },
        { kind: "tool", toolName: "grep", toolInput: "pattern" },
        { kind: "tool_result", content: "found it" },
        { kind: "text", content: "Then I found the answer" },
      ]
      const sub = makeSubagent({
        events,
        text: "First I searchThen I found the answer",
        tools: [makeTool({ name: "grep", input: "pattern", result: "found it" })],
        toolCount: 1,
      })
      render(<SubagentCard subagent={sub} />)
      const blocks = screen.getByText("First I search").closest("div")!.parentElement!
      expect(blocks.textContent).toMatch(/First I search.*grep.*Then I found the answer/s)
    })

    it("renders reasoning events as reasoning blocks", () => {
      const events: SubagentEvent[] = [
        { kind: "reasoning", content: "Let me think..." },
        { kind: "text", content: "Answer" },
      ]
      const sub = makeSubagent({ events, reasoning: "Let me think...", text: "Answer" })
      render(<SubagentCard subagent={sub} />)
      expect(screen.getByText("Let me think...")).toBeInTheDocument()
      expect(screen.getByText("Answer")).toBeInTheDocument()
    })

    it("renders tool events with result inline", () => {
      const events: SubagentEvent[] = [
        { kind: "tool", toolName: "bash", toolInput: "ls" },
        { kind: "tool_result", content: "file1.txt" },
      ]
      const sub = makeSubagent({
        events,
        tools: [makeTool({ name: "bash", input: "ls", result: "file1.txt" })],
        toolCount: 1,
      })
      render(<SubagentCard subagent={sub} />)
      expect(screen.getByText("bash")).toBeInTheDocument()
      expect(screen.getByText("ls")).toBeInTheDocument()
    })

    it("renders error events with error styling", () => {
      const events: SubagentEvent[] = [
        { kind: "error", content: "Something went wrong" },
      ]
      const sub = makeSubagent({ events, status: "error" })
      render(<SubagentCard subagent={sub} />)
      const errorEl = screen.getByText("Something went wrong")
      expect(errorEl.className).toContain("text-red-500")
    })

    it("skips tool_result events in rendering and attaches result to tool", () => {
      const events: SubagentEvent[] = [
        { kind: "tool", toolName: "grep", toolInput: "TODO" },
        { kind: "tool_result", content: "result text" },
      ]
      const sub = makeSubagent({
        events,
        tools: [makeTool({ name: "grep", input: "TODO", result: "result text" })],
        toolCount: 1,
      })
      render(<SubagentCard subagent={sub} />)
      // The "Result" toggle button is visible (tool has a result)
      expect(screen.getByText("Result")).toBeInTheDocument()
      // Click to reveal tool result content
      fireEvent.click(screen.getByText("Result"))
      expect(screen.getByText("result text")).toBeInTheDocument()
    })
  })
})

describe("SubagentTreeCard", () => {
  const root: ActiveSubagent = makeSubagent({
    id: "root",
    agentType: "general",
    description: "Main task",
    status: "completed",
  })

  const child: ActiveSubagent = makeSubagent({
    id: "child-1",
    parentId: "root",
    agentType: "explore",
    description: "Sub task",
    status: "completed",
  })

  const grandchild: ActiveSubagent = makeSubagent({
    id: "gc-1",
    parentId: "child-1",
    agentType: "explore",
    description: "Grandchild task",
    status: "completed",
  })

  const flatAgg = {
    totalTools: 0, activeCount: 0, descendantCount: 0,
    totalDuration: 0, maxDepthFromHere: 0, inputTokens: 0, outputTokens: 0,
  }
  const flatTree: SubagentTreeNode[] = [
    { item: root, children: [], aggregate: flatAgg },
    { item: child, children: [], aggregate: flatAgg },
    { item: grandchild, children: [], aggregate: flatAgg },
  ]

  it("renders root level subagent", () => {
    render(<SubagentTreeCard subagent={root} tree={flatTree} />)
    expect(screen.getByText("Main task")).toBeInTheDocument()
  })

  it("renders child subagents recursively", () => {
    render(<SubagentTreeCard subagent={root} tree={flatTree} depth={0} />)
    expect(screen.getByText("Sub task")).toBeInTheDocument()
    expect(screen.getByText("Grandchild task")).toBeInTheDocument()
  })

  it("passes increased depth to children", () => {
    const { container } = render(<SubagentTreeCard subagent={root} tree={flatTree} depth={0} />)

    const allCards = container.querySelectorAll('[style*="margin-left"]')
    const margins = Array.from(allCards).map((el) => (el as HTMLElement).style.marginLeft)
    expect(margins).toContain("0px")
    expect(margins).toContain("16px")
    expect(margins).toContain("32px")
  })
})
