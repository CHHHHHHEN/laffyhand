import { describe, it, expect, vi, beforeEach } from "vitest"
import { render, screen, fireEvent } from "@testing-library/react"
import { SubagentCard, SubagentTreeCard } from "./SubagentCard"
import type { ActiveSubagent } from "@/types/session"
import type { SubagentTreeNode } from "@/lib/subagentTree"

function makeSubagent(overrides: Partial<ActiveSubagent> = {}): ActiveSubagent {
  return {
    id: "sa-1",
    parentId: null,
    agentType: "explore",
    description: "Search the codebase for test files",
    mode: "foreground",
    depth: 0,
    status: "running",
    text: "",
    reasoning: "",
    tools: [],
    toolCount: 0,
    summary: undefined,
    inputTokens: 0,
    outputTokens: 0,
    ...overrides,
  }
}

describe("SubagentCard", () => {
  describe("header", () => {
    it("shows agent type name", () => {
      render(<SubagentCard subagent={makeSubagent({ agentType: "general" })} />)
      expect(screen.getByText("general")).toBeInTheDocument()
    })

    it("shows running badge when status is running", () => {
      render(<SubagentCard subagent={makeSubagent({ status: "running" })} />)
      expect(screen.getByText("Running")).toBeInTheDocument()
    })

    it("shows completed badge when status is completed", () => {
      render(<SubagentCard subagent={makeSubagent({ status: "completed" })} />)
      expect(screen.getByText("Completed")).toBeInTheDocument()
    })

    it("shows failed badge when status is error", () => {
      render(<SubagentCard subagent={makeSubagent({ status: "error" })} />)
      expect(screen.getByText("Failed")).toBeInTheDocument()
    })

    it("shows failed badge when status is cancelled", () => {
      render(<SubagentCard subagent={makeSubagent({ status: "cancelled" })} />)
      expect(screen.getByText("Failed")).toBeInTheDocument()
    })

    it("shows truncated instruction preview for long descriptions", () => {
      const long = "a".repeat(100)
      const sub = makeSubagent({ description: long })
      render(<SubagentCard subagent={sub} />)
      const expected = "a".repeat(60) + "…"
      expect(screen.getByText(expected)).toBeInTheDocument()
    })

    it("shows tool count in header when tools exist", () => {
      const sub = makeSubagent({
        toolCount: 3,
        tools: [
          { name: "read", input: "/tmp" },
          { name: "write", input: "/tmp/test" },
          { name: "glob", input: "**/*.ts" },
        ],
        status: "completed",
      })
      render(<SubagentCard subagent={sub} />)
      expect(screen.getByText("3 tools")).toBeInTheDocument()
    })

    it("is expanded by default when running", () => {
      render(<SubagentCard subagent={makeSubagent({ status: "running", text: "searching…" })} />)
      expect(screen.getByText("searching…")).toBeInTheDocument()
    })

    it("is collapsed by default when completed", () => {
      const sub = makeSubagent({ status: "completed", text: "found 42 files" })
      render(<SubagentCard subagent={sub} />)
      expect(screen.queryByText("found 42 files")).not.toBeInTheDocument()
    })
  })

  describe("instruction message", () => {
    it("shows instruction as user message when expanded", () => {
      const sub = makeSubagent({ status: "running", description: "Find all TODO comments" })
      render(<SubagentCard subagent={sub} />)
      // text appears in both header preview and expanded message body
      const all = screen.getAllByText("Find all TODO comments")
      expect(all).toHaveLength(2)
    })
  })

  describe("assistant content", () => {
    it("shows text output", () => {
      const sub = makeSubagent({ status: "running", text: "Found 5 test files" })
      render(<SubagentCard subagent={sub} />)
      expect(screen.getByText("Found 5 test files")).toBeInTheDocument()
    })

    it("shows thinking spinner when running with no text and no reasoning", () => {
      render(<SubagentCard subagent={makeSubagent({ status: "running", text: "", reasoning: "" })} />)
      expect(screen.getByText("Thinking")).toBeInTheDocument()
    })

    it("shows ReasoningBlock when reasoning exists", () => {
      const sub = makeSubagent({ status: "running", reasoning: "analyzing patterns" })
      render(<SubagentCard subagent={sub} />)
      // ReasoningBlock header is visible (collapsed by default)
      expect(screen.getByText("Thinking")).toBeInTheDocument()
      // Click to expand and verify content
      const reasonButtons = screen.getAllByText("Thinking")
      fireEvent.click(reasonButtons[reasonButtons.length - 1]!)
      expect(screen.getByText("analyzing patterns")).toBeInTheDocument()
    })

    it("shows tool call list when tools exist", () => {
      const sub = makeSubagent({
        status: "running",
        tools: [{ name: "read", input: '{"path": "/tmp"}' }],
        toolCount: 1,
      })
      render(<SubagentCard subagent={sub} />)
      expect(screen.getByText("Tool calls · 1")).toBeInTheDocument()
      expect(screen.getByText("read")).toBeInTheDocument()
    })
  })

  describe("completed footer", () => {
    it("shows summary when completed with summary", () => {
      const sub = makeSubagent({
        status: "completed",
        summary: "Found 42 results",
        inputTokens: 100,
        outputTokens: 50,
      })
      render(<SubagentCard subagent={sub} />)
      expect(screen.getByText((c) => c.includes("Found 42 results"))).toBeInTheDocument()
    })

    it("shows token usage in footer", () => {
      const sub = makeSubagent({
        status: "completed",
        text: "done",
        inputTokens: 150,
        outputTokens: 75,
      })
      render(<SubagentCard subagent={sub} />)
      expect(screen.getByText((c) => c.includes("150"))).toBeInTheDocument()
      expect(screen.getByText((c) => c.includes("75"))).toBeInTheDocument()
    })
  })

  describe("collapsed state hint", () => {
    it("shows hint line when completed and collapsed", () => {
      const sub = makeSubagent({
        status: "completed",
        toolCount: 2,
        tools: [{ name: "read", input: "a" }, { name: "write", input: "b" }],
        inputTokens: 100,
        outputTokens: 50,
        summary: "Done",
      })
      render(<SubagentCard subagent={sub} />)
      expect(screen.getByText("2 tool calls")).toBeInTheDocument()
      expect(screen.getByText(/↗100/)).toBeInTheDocument()
      expect(screen.getByText(/↘50/)).toBeInTheDocument()
      expect(screen.getByText((c) => c.includes("Done"))).toBeInTheDocument()
    })
  })

  describe("interaction", () => {
    it("toggles expanded state on header click", () => {
      const sub = makeSubagent({ status: "completed", text: "hidden content" })
      render(<SubagentCard subagent={sub} />)
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

  // SubagentTreeCard expects a flat array of SubagentTreeNode.
  // Nesting is tracked via parentId on the item, not tree nesting.
  const flatAgg = { totalTools: 0, activeCount: 0, descendantCount: 0, maxDepthFromHere: 0, inputTokens: 0, outputTokens: 0 }
  const flatTree: SubagentTreeNode[] = [
    { item: root, children: [], aggregate: flatAgg },
    { item: child, children: [], aggregate: flatAgg },
    { item: grandchild, children: [], aggregate: flatAgg },
  ]

  it("renders root level subagent", () => {
    render(<SubagentTreeCard subagent={root} tree={flatTree} />)
    expect(screen.getByText("Main task")).toBeInTheDocument()
  })

  it("renders child subagents recursively after expanding root", () => {
    render(<SubagentTreeCard subagent={root} tree={flatTree} depth={0} />)
    fireEvent.click(screen.getByText("Main task"))
    expect(screen.getByText("Sub task")).toBeInTheDocument()
    fireEvent.click(screen.getByText("Sub task"))
    expect(screen.getByText("Grandchild task")).toBeInTheDocument()
  })

  it("passes increased depth to children after expanding", () => {
    const { container } = render(<SubagentTreeCard subagent={root} tree={flatTree} depth={0} />)
    fireEvent.click(screen.getByText("Main task"))
    fireEvent.click(screen.getByText("Sub task"))

    const allCards = container.querySelectorAll('[style*="margin-left"]')
    const margins = Array.from(allCards).map((el) => (el as HTMLElement).style.marginLeft)
    expect(margins).toContain("0px")
    expect(margins).toContain("16px")
    expect(margins).toContain("32px")
  })
})
